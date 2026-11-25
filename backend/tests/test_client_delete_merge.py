"""Deleting and merging duplicate client cards (Comments #50, 11/2026).

Nicole: "Can't get this duplicate client profile to delete" -- a second card
"Grace Byrd (Lucas/Eilers Design Associates L.L.P)" next to the real one.
The Clients page deleted by NAME in the path (DELETE /clients/delete/{name}),
and the slash in "Lucas/Eilers" is decoded before routing, so the request
never reached the route: the server answered 405 and the page said only
"Failed to delete client". Deleting is now by id; a card with history is
refused (409) rather than cascading its seasons away, and an admin can merge
it into the client it duplicates instead. All names here are FAKE.
"""
import asyncio
from urllib.parse import quote

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.apis import clients
from app.apis.clients import MergeIn
from app.libs import roles

SLASHED = "Test Byrd (Fake/Example Design Associates L.L.P)"


def run(coro):
    return asyncio.run(coro)


def args_of(fake_db, pattern):
    return [args for _, args in fake_db.calls(pattern)]


# ─── the cause ────────────────────────────────────────────────────────────────


def test_a_slash_in_the_name_never_reached_the_name_route_but_the_id_route_works(monkeypatch):
    """The bug, reproduced through real routing: the name route can't be
    reached with a slash in the name; the id route doesn't care."""
    seen = []

    async def by_name(client_name: str, request=None, delete_projects: bool = False):
        seen.append(("name", client_name))
        return {"deleted": 1}

    async def by_id(client_id: int, request=None, delete_projects: bool = False):
        seen.append(("id", client_id))
        return {"deleted": 1}

    app = FastAPI()
    paths = {r.path: r for r in clients.router.routes if "DELETE" in getattr(r, "methods", set())}
    assert "/clients/delete/{client_name}" in paths and "/clients/{client_id}" in paths
    app.add_api_route("/api/clients/delete/{client_name}", by_name, methods=["DELETE"])
    app.add_api_route("/api/clients/{client_id}", by_id, methods=["DELETE"])

    @app.get("/{full_path:path}")  # main.py's SPA catch-all (GET only)
    def spa(full_path: str):
        return "spa"

    c = TestClient(app)
    assert c.delete("/api/clients/delete/" + quote(SLASHED, safe="")).status_code == 405
    assert c.delete("/api/clients/599").status_code == 200
    assert seen == [("id", 599)]


# ─── delete by id ─────────────────────────────────────────────────────────────


def test_delete_by_id_deletes_the_card_and_unassigns_its_projects(fake_db, fake_request):
    fake_db.on_fetchval("SELECT name FROM clients WHERE id = $1 FOR UPDATE", SLASHED)
    fake_db.on_fetchval(clients.HISTORY_COUNT_SQL, 0)
    fake_db.on_fetchval("SELECT count(*) FROM clients WHERE LOWER(TRIM(name))", 0)
    fake_db.on_execute("UPDATE arrangements", "UPDATE 2")

    out = run(clients.delete_client_by_id(599, fake_request()))

    assert out == {"deleted": 1, "id": 599, "projects_updated": 2}
    assert args_of(fake_db, "DELETE FROM clients WHERE id = $1") == [(599,)]
    assert args_of(fake_db, "UPDATE arrangements SET client_name = NULL") == [(SLASHED,)]


def test_delete_by_id_leaves_projects_alone_when_another_card_has_the_name(fake_db, fake_request):
    fake_db.on_fetchval("SELECT name FROM clients WHERE id = $1 FOR UPDATE", "Sample, Test")
    fake_db.on_fetchval(clients.HISTORY_COUNT_SQL, 0)
    fake_db.on_fetchval("SELECT count(*) FROM clients WHERE LOWER(TRIM(name))", 1)

    out = run(clients.delete_client_by_id(7, fake_request(), delete_projects=True))

    assert out == {"deleted": 1, "id": 7, "projects_deleted": 0, "projects_updated": 0}
    assert not fake_db.seen("arrangements")


def test_delete_by_id_with_projects(fake_db, fake_request):
    fake_db.on_fetchval("SELECT name FROM clients WHERE id = $1 FOR UPDATE", "Sample, Test")
    fake_db.on_fetchval(clients.HISTORY_COUNT_SQL, 0)
    fake_db.on_fetchval("SELECT count(*) FROM clients WHERE LOWER(TRIM(name))", 0)
    fake_db.on_execute("DELETE FROM arrangements", "DELETE 3")

    out = run(clients.delete_client_by_id(7, fake_request(), delete_projects=True))

    assert out["projects_deleted"] == 3 and not fake_db.seen("UPDATE arrangements")


def test_a_card_with_history_is_not_deleted_but_offered_a_merge(fake_db, fake_request):
    fake_db.on_fetchval("SELECT name FROM clients WHERE id = $1 FOR UPDATE", "Sample, Test")
    fake_db.on_fetchval(clients.HISTORY_COUNT_SQL, 2)

    with pytest.raises(HTTPException) as exc:
        run(clients.delete_client_by_id(7, fake_request()))

    assert exc.value.status_code == 409
    assert exc.value.detail["history"] == 2 and exc.value.detail["name"] == "Sample, Test"
    assert "Merge it into the client it duplicates" in exc.value.detail["message"]
    assert "—" not in exc.value.detail["message"]
    assert not fake_db.seen("DELETE FROM clients")


def test_delete_by_id_404(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.delete_client_by_id(404, fake_request()))
    assert exc.value.status_code == 404
    assert not fake_db.seen("DELETE")


# ─── merge ───────────────────────────────────────────────────────────────────


def merge_db(fake_db, *, src=None, dst=None):
    src = src if src is not None else {"id": 599, "name": SLASHED, "former_names": ["Test Byrd"]}
    dst = dst if dst is not None else {"id": 303, "name": "Byrd, Test - (Fake/Example Design Associates L.L.P)",
                                       "former_names": ["Byrd, Test"]}

    def pick(sql, cid):
        return {599: src, 303: dst}.get(cid)
    fake_db.on("SELECT id, name, former_names FROM clients WHERE id = $1 FOR UPDATE", pick, method="fetchrow")
    fake_db.on_fetch("JOIN client_activity d", [{"src_id": 11, "dst_id": 21}])
    fake_db.on_execute("UPDATE client_activity SET client_id", "UPDATE 3")
    fake_db.on_execute("UPDATE ll_app.jobs SET client_id", "UPDATE 1")
    fake_db.on_fetchrow("WITH gone AS (DELETE FROM clients", {"id": 303, "name": dst["name"]})
    return src, dst


def test_merge_moves_history_names_and_ids_then_deletes_the_duplicate(fake_db, fake_request):
    src, dst = merge_db(fake_db)

    out = run(clients.merge_client(599, MergeIn(into_id=303), fake_request()))

    assert out["merged"] is True and out["into_id"] == 303 and out["into_name"] == dst["name"]
    assert out["moved"]["seasons_combined"] == 1 and out["moved"]["history"] == 3
    # A season both cards had: the kept one's values win, then the duplicate's row goes.
    assert args_of(fake_db, "UPDATE client_activity d SET detail") == [(21, 11)]
    assert args_of(fake_db, "DELETE FROM client_activity WHERE id = $1") == [(11,)]
    assert args_of(fake_db, "UPDATE client_activity SET client_id = $2") == [(599, 303)]
    # Every text mirror is renamed to the kept client (new, old, duplicate's id) ...
    assert args_of(fake_db, "UPDATE arrangements SET client_name = $1") == [(dst["name"], SLASHED, 599)]
    # ... then the id-keyed tables follow, after the renames.
    assert args_of(fake_db, "UPDATE ll_app.jobs SET client_id = $1 WHERE client_id = $2") == [(303, 599)]
    order = [sql for sql, _ in fake_db.executed]
    assert order.index(next(s for s in order if "UPDATE ll_app.jobs SET client_name" in s)) < \
        order.index(next(s for s in order if "UPDATE ll_app.jobs SET client_id" in s))
    # The duplicate's names are kept as former names, the kept name isn't.
    (into, gone, former), = args_of(fake_db, "WITH gone AS (DELETE FROM clients")
    assert (into, gone) == (303, 599)
    assert former == ["Byrd, Test", SLASHED, "Test Byrd"]


def test_merge_into_itself_or_a_missing_client(fake_db, fake_request):
    with pytest.raises(HTTPException) as same:
        run(clients.merge_client(5, MergeIn(into_id=5), fake_request()))
    assert same.value.status_code == 400
    fake_db.on("SELECT id, name, former_names FROM clients WHERE id = $1 FOR UPDATE",
               lambda sql, cid: {"id": 599, "name": SLASHED, "former_names": []} if cid == 599 else None,
               method="fetchrow")
    with pytest.raises(HTTPException) as missing:
        run(clients.merge_client(599, MergeIn(into_id=303), fake_request()))
    assert missing.value.status_code == 404
    assert not fake_db.seen("DELETE FROM clients")


def test_a_missing_ll_app_table_does_not_abort_the_merge(fake_db, fake_request):
    import asyncpg
    merge_db(fake_db)

    async def missing(sql, *args):
        raise asyncpg.UndefinedTableError("no table")
    fake_db.on("UPDATE ll_app.install_actuals SET client_id", missing, method="execute")

    out = run(clients.merge_client(599, MergeIn(into_id=303), fake_request()))
    assert out["moved"]["install_actuals"] == 0 and out["merged"] is True


@pytest.mark.parametrize("role, ok", [
    ("crew", False), ("viewer", False), ("production", False), ("lead", False),
    ("staff", False), ("admin", True), ("super_admin", True),
])
def test_merge_is_admin_only(role, ok, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    route = next(r for r in clients.router.routes if r.path == "/clients/{client_id}/merge")
    assert route.methods == {"POST"}
    dep = route.dependencies[0].dependency

    async def fake_resolve(email, roster_lookup=None):
        return role
    monkeypatch.setattr(roles, "resolve_role", fake_resolve)
    monkeypatch.setattr(roles, "get_current_user", lambda req: type("U", (), {"email": "x@x.test"})())

    class Req:
        method = "POST"
        scope = {}
        url = type("U", (), {"path": "/api/clients/599/merge"})()
        state = type("S", (), {})()

    if ok:
        assert run(dep(Req())) == role
    else:
        with pytest.raises(HTTPException) as exc:
            run(dep(Req()))
        assert exc.value.status_code == 403


@pytest.mark.parametrize("role, ok", [("lead", False), ("production", False), ("staff", True), ("admin", True)])
def test_delete_by_id_needs_staff(role, ok):
    assert roles.allowed(role, "staff", "DELETE", False, "/api/clients/{client_id}") is ok
