"""Characterisation tests for ``app.apis.clients``.

Snapshot-style: they pin TODAY's response shapes and the SQL each endpoint
issues so a later refactor can be verified against them. Where behaviour looks
questionable it is pinned as-is and commented. No database -- the shared
``fake_db`` harness from ``conftest.py`` stands in for asyncpg.

All requests are anonymous (``fake_request()``) so ``get_optional_user``
returns ``None`` without trying to verify a Supabase token.
"""

import asyncio
import json
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.apis import clients
from app.apis.clients import ClientCreate, ClientUpdate, CommentIn, SecondaryContact

T0 = datetime(2026, 1, 2, 3, 4, 5)
T1 = datetime(2026, 2, 3, 4, 5, 6)

CLIENT_KEYS = ["id", "name", "email", "phone", "notes", "street", "city", "state", "zip",
               "time_preference", "secondary_contacts", "created_at", "updated_at"]


def run(coro):
    return asyncio.run(coro)


def args_of(fake_db, pattern):
    return [args for _, args in fake_db.calls(pattern)]


def client_row(**values):
    row = dict.fromkeys(CLIENT_KEYS)
    row.update(values)
    return row


# ─── has_item_status_column ──────────────────────────────────────────────────


@pytest.mark.parametrize("value, expected", [(True, True), (False, False), (None, False)])
def test_has_item_status_column(fake_db, value, expected):
    fake_db.on_fetchval("information_schema.columns", value)
    conn = run(clients.get_conn())
    assert run(clients.has_item_status_column(conn)) is expected
    ((sql, args),) = fake_db.executed
    assert "table_name = 'container_items'" in sql and "column_name = 'status'" in sql
    assert args == ()


# ─── list ────────────────────────────────────────────────────────────────────


def test_list_clients(fake_db, fake_request):
    smith = client_row(id=1, name="Smith", email="s@x.com", street="1 Main", city="Austin", state="TX",
                       zip="78701", secondary_contacts='[{"label":"Wife","phone":"555","email":null}]',
                       created_at=T0, updated_at=T1)
    adams = client_row(id=2, name="adams", created_at=T0, updated_at=T0)
    fake_db.on_fetch("FROM clients", [smith, adams])
    fake_db.on_fetch("FROM client_activity", [
        {"client_id": 1, "id": 50, "kind": "christmas_install", "season": "2025", "summary": "Installed",
         "detail": '{"crew":"A"}', "occurred_at": datetime(2025, 12, 1, 9, 0), "created_at": T0},
        {"client_id": 1, "id": 51, "kind": "comment", "season": "x", "summary": "hi",
         "detail": None, "occurred_at": None, "created_at": T1},
        {"client_id": 999, "id": 52, "kind": "comment", "season": "y", "summary": "orphan",
         "detail": {"author": "a"}, "occurred_at": None, "created_at": T1},
    ])
    fake_db.on_fetchval("column_name = 'status'", True)
    fake_db.on_fetch("FROM arrangements a", [
        {"name": "SMITH", "project_count": 2, "bucket_count": 5, "selected_cost": 120.5, "last_project_at": T1},
        {"name": "Unassigned", "project_count": 1, "bucket_count": 0, "selected_cost": 0.0, "last_project_at": T0},
    ])

    out = run(clients.list_clients(fake_request()))

    assert out == [
        {**adams, "secondary_contacts": [], "project_count": 0, "bucket_count": 0, "selected_cost": 0.0,
         "last_project_at": None, "source": "saved", "activity": []},
        {**smith, "secondary_contacts": [{"label": "Wife", "phone": "555", "email": None}],
         "project_count": 2, "bucket_count": 5, "selected_cost": 120.5, "last_project_at": T1,
         "source": "saved",
         "activity": [
             {"id": 50, "kind": "christmas_install", "season": "2025", "summary": "Installed",
              "detail": {"crew": "A"}, "occurred_at": "2025-12-01T09:00:00", "created_at": T0},
             {"id": 51, "kind": "comment", "season": "x", "summary": "hi",
              "detail": None, "occurred_at": None, "created_at": T1},
         ]},
        # project-only client: fixed to carry secondary_contacts: [] like a
        # saved client does, instead of omitting the key entirely.
        {"id": None, "name": "Unassigned", "email": None, "phone": None, "notes": None,
         "street": None, "city": None, "state": None, "zip": None,
         "time_preference": None, "secondary_contacts": [], "created_at": None,
         "updated_at": T0, "project_count": 1, "bucket_count": 0, "selected_cost": 0.0,
         "last_project_at": T0, "source": "from_projects", "activity": []},
    ]
    assert fake_db.seen("COALESCE(SUM(CASE WHEN ci.status = 'selected' THEN ci.quantity * p.current_price ELSE 0 END), 0)::float AS selected_cost")
    assert fake_db.seen("FROM client_activity ORDER BY occurred_at DESC NULLS LAST, season DESC")
    assert not fake_db.seen("created_by")  # team-owned rollup


# ─── create ──────────────────────────────────────────────────────────────────


def test_create_client(fake_db, fake_request):
    returned = client_row(id=7, name="Smith", email="s@x.com",
                          secondary_contacts='[{"label": "Wife", "phone": "555", "email": null}]',
                          created_at=T0, updated_at=T0)
    fake_db.on_fetchrow("INSERT INTO clients", returned)
    body = ClientCreate(name="  Smith ", email=" s@x.com ", phone="", notes="   ",
                        secondary_contacts=[SecondaryContact(label="Wife", phone="555")])

    out = run(clients.create_client(body, fake_request()))

    assert out == {
        **returned,
        "secondary_contacts": [{"label": "Wife", "phone": "555", "email": None}],
        "project_count": 0, "bucket_count": 0, "selected_cost": 0.0,
        "last_project_at": None, "source": "saved", "activity": [],
    }
    assert args_of(fake_db, "INSERT INTO clients") == [(
        "Smith", "s@x.com", None, None, None, None, None, None,
        '[{"label": "Wife", "phone": "555", "email": null}]', None, None,
    )]
    assert fake_db.seen("ON CONFLICT (LOWER(TRIM(name))) DO NOTHING")


def test_create_client_conflict_and_blank(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.create_client(ClientCreate(name="   "), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (400, "Client name is required")
    assert fake_db.executed == []

    fake_db.on_fetchrow("INSERT INTO clients", None)
    with pytest.raises(HTTPException) as exc:
        run(clients.create_client(ClientCreate(name="Smith"), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (409, "Client already exists")
    # secondary_contacts omitted -> literal "[]"
    assert args_of(fake_db, "INSERT INTO clients") == [("Smith", None, None, None, None, None, None, None, "[]", None, None)]


# ─── update ──────────────────────────────────────────────────────────────────


def test_update_client(fake_db, fake_request):
    returned = client_row(id=5, name="Smith", secondary_contacts=[], created_at=T0, updated_at=T1)
    fake_db.on_fetchrow("UPDATE clients SET", returned)
    fake_db.on_fetch("FROM client_activity", [
        {"client_id": 5, "id": 60, "kind": "comment", "season": "s", "summary": "mine",
         "detail": '{"author":null}', "occurred_at": None, "created_at": T1},
        {"client_id": 6, "id": 61, "kind": "comment", "season": "s", "summary": "other",
         "detail": None, "occurred_at": None, "created_at": T1},
    ])
    body = ClientUpdate(phone="", secondary_contacts=[])

    out = run(clients.update_client(5, body, fake_request()))

    assert out == {
        **returned,
        "project_count": 0, "bucket_count": 0, "selected_cost": 0.0,
        "last_project_at": None, "source": "saved",
        "activity": [{"id": 60, "kind": "comment", "season": "s", "summary": "mine",
                      "detail": {"author": None}, "occurred_at": None, "created_at": T1}],
    }
    # raw (untrimmed) values are bound; SQL does the NULLIF/TRIM
    assert args_of(fake_db, "UPDATE clients SET") == [(5, None, None, "", None, None, None, None, None, "[]", None)]


def test_update_client_404(fake_db, fake_request):
    fake_db.on_fetchrow("UPDATE clients SET", None)
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client(5, ClientUpdate(name="X"), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (404, "No client with that id")
    assert not fake_db.seen("FROM client_activity")


# ─── delete ──────────────────────────────────────────────────────────────────


def test_delete_client_detaches_projects(fake_db, fake_request):
    fake_db.on_execute("DELETE FROM clients", "DELETE 1")
    fake_db.on_execute("UPDATE arrangements", "UPDATE 3")

    out = run(clients.delete_client("  Smith ", fake_request()))

    assert out == {"deleted": 1, "projects_updated": 3}
    assert args_of(fake_db, "DELETE FROM clients WHERE LOWER(TRIM(name)) = LOWER($1)") == [("Smith",)]
    assert args_of(fake_db, "UPDATE arrangements SET client_name = NULL, updated_at = NOW()") == [("Smith",)]
    assert not fake_db.seen("DELETE FROM arrangements")


def test_delete_client_with_projects(fake_db, fake_request):
    fake_db.on_execute("DELETE FROM clients", "DELETE 0")
    fake_db.on_execute("DELETE FROM arrangements", "DELETE 2")

    out = run(clients.delete_client("Smith", fake_request(), delete_projects=True))

    # Pinned: projects are deleted even when no saved client row matched.
    assert out == {"deleted": 0, "projects_deleted": 2, "projects_updated": 0}
    assert args_of(fake_db, "DELETE FROM arrangements WHERE LOWER(TRIM(COALESCE(client_name, ''))) = LOWER($1)") == [("Smith",)]
    assert not fake_db.seen("UPDATE arrangements")


def test_delete_client_blank_name_400(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.delete_client("   ", fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (400, "Client name is required")
    assert fake_db.executed == []


# ─── comments ────────────────────────────────────────────────────────────────


def test_add_client_comment(fake_db, fake_request):
    fake_db.on_fetchval("SELECT 1 FROM clients WHERE id = $1", 1)
    row = {"id": 60, "kind": "comment", "season": "2026-02-03T04:05:06", "summary": "Needs ladder",
           "detail": '{"author": null}', "occurred_at": None, "created_at": T1}
    fake_db.on_fetchrow("INSERT INTO client_activity", row)

    out = run(clients.add_client_comment(5, CommentIn(text="  Needs ladder  "), fake_request()))

    assert out == row
    ((client_id, season, summary, detail),) = args_of(fake_db, "INSERT INTO client_activity")
    assert (client_id, summary, detail) == (5, "Needs ladder", '{"author": null}')
    assert isinstance(datetime.fromisoformat(season), datetime)  # utcnow().isoformat()
    assert fake_db.seen("VALUES ($1, 'comment', $2, $3, $4, NULL)")


def test_add_client_comment_validation(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.add_client_comment(5, CommentIn(text="   "), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (400, "Comment text is required")

    with pytest.raises(HTTPException) as exc:
        run(clients.add_client_comment(5, CommentIn(text="x" * 2001), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (413, "Comment is too long")
    assert fake_db.executed == []

    # exactly 2000 chars passes validation; unknown client -> 404
    with pytest.raises(HTTPException) as exc:
        run(clients.add_client_comment(5, CommentIn(text="x" * 2000), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (404, "No client with that id")
    assert args_of(fake_db, "SELECT 1 FROM clients WHERE id = $1") == [(5,)]
    assert not fake_db.seen("INSERT")


def test_delete_client_comment(fake_db, fake_request):
    assert run(clients.delete_client_comment(5, 60, fake_request())) == {"deleted": True}
    assert args_of(fake_db, "DELETE FROM client_activity WHERE id = $1 AND client_id = $2 AND kind = 'comment'") == [(60, 5)]

    fake_db.on_execute("DELETE FROM client_activity", "DELETE 0")
    with pytest.raises(HTTPException) as exc:
        run(clients.delete_client_comment(5, 61, fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (404, "No such comment")


def test_recent_comments(fake_db, fake_request):
    fake_db.on_fetch("FROM client_activity ca JOIN clients c", [
        {"id": 60, "client_id": 5, "client_name": "Smith", "summary": "Needs ladder",
         "detail": '{"author":"crew@example.com"}', "created_at": T1},
        {"id": 59, "client_id": 6, "client_name": "Adams", "summary": "Gate code 1234",
         "detail": None, "created_at": T0},
        {"id": 58, "client_id": 6, "client_name": "Adams", "summary": "dict detail",
         "detail": {"author": None, "extra": 1}, "created_at": T0},
    ])

    out = run(clients.recent_comments(fake_request()))

    assert out == [
        {"id": 60, "client_id": 5, "client_name": "Smith", "text": "Needs ladder",
         "author": "crew@example.com", "created_at": T1},
        {"id": 59, "client_id": 6, "client_name": "Adams", "text": "Gate code 1234",
         "author": None, "created_at": T0},
        {"id": 58, "client_id": 6, "client_name": "Adams", "text": "dict detail",
         "author": None, "created_at": T0},
    ]
    assert args_of(fake_db, "WHERE ca.kind = 'comment' ORDER BY ca.created_at DESC LIMIT $1") == [(20,)]

    fake_db.executed.clear()
    run(clients.recent_comments(fake_request(), limit=5))
    assert args_of(fake_db, "LIMIT $1") == [(5,)]


# ─── time_preference ─────────────────────────────────────────────────────────


def test_update_time_preference_binds_and_clears(fake_db, fake_request):
    fake_db.on_fetchrow("UPDATE clients SET", client_row(id=5, name="Smith", time_preference="morning",
                                                         secondary_contacts=[], created_at=T0, updated_at=T1))
    out = run(clients.update_client(5, ClientUpdate(time_preference=" Morning "), fake_request()))
    assert out["time_preference"] == "morning"
    # normalised before binding; "" is passed through so SQL's NULLIF clears it
    assert args_of(fake_db, "UPDATE clients SET")[0][-1] == "morning"
    run(clients.update_client(5, ClientUpdate(time_preference=""), fake_request()))
    assert args_of(fake_db, "UPDATE clients SET")[1][-1] == ""


def test_time_preference_rejects_unknown_value(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client(5, ClientUpdate(time_preference="noon"), fake_request()))
    assert exc.value.status_code == 400 and "morning, afternoon, late" in exc.value.detail
    with pytest.raises(HTTPException):
        run(clients.create_client(ClientCreate(name="X", time_preference="dawn"), fake_request()))
    assert fake_db.executed == []


# ─── per-season fields ───────────────────────────────────────────────────────


def test_update_client_season_merges_and_stamps(fake_db, fake_request, monkeypatch):
    from app.libs import client_season
    monkeypatch.setattr(client_season, "now_iso", lambda: "2026-09-16T12:00:00+00:00")
    fake_db.on_fetchval("SELECT 1 FROM clients WHERE id = $1", 1)
    fake_db.on_fetchrow("FROM client_activity WHERE client_id = $1 AND kind = 'christmas_install' AND season = $2 FOR UPDATE",
                        {"id": 9, "detail": '{"install_date": "2026-11-20", "install_fee": 400, "storing": false}'})
    fake_db.on("INSERT INTO client_activity",
               lambda sql, cid, season, summary, detail, occurred: {
                   "id": 9, "kind": "christmas_install", "season": season, "summary": summary,
                   "detail": detail, "occurred_at": occurred, "created_at": T0}, method="fetchrow")

    body = clients.SeasonFieldsIn(fields={"storing": True, "boxes": "12", "hold": True, "invoice_total": "1,065"})
    out = run(clients.update_client_season(5, "2026", body, fake_request()))

    assert out["detail"] == {
        "install_date": "2026-11-20", "install_fee": 400,
        "storing": True, "boxes": 12, "hold": True, "invoice_total": 1065.0,
        "app_edits": {k: "2026-09-16T12:00:00+00:00" for k in ("storing", "boxes", "hold", "invoice_total")},
    }
    assert out["summary"] == "On hold · Scheduled 11/20/2026 · $400"
    assert out["occurred_at"] == "2026-11-20"
    ((cid, season, summary, detail, occurred),) = args_of(fake_db, "INSERT INTO client_activity")
    assert (cid, season) == (5, "2026") and json.loads(detail) == out["detail"]


def test_update_client_season_validation(fake_db, fake_request):
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client_season(5, "26", clients.SeasonFieldsIn(fields={"hold": True}), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (400, "Bad season")
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client_season(5, "2026", clients.SeasonFieldsIn(fields={}), fake_request()))
    assert exc.value.status_code == 400
    assert fake_db.executed == []

    with pytest.raises(HTTPException) as exc:
        run(clients.update_client_season(5, "2026", clients.SeasonFieldsIn(fields={"hold": True}), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (404, "No client with that id")

    fake_db.on_fetchval("SELECT 1 FROM clients WHERE id = $1", 1)
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client_season(5, "2026", clients.SeasonFieldsIn(fields={"colour": "red"}), fake_request()))
    assert (exc.value.status_code, exc.value.detail) == (400, "unknown season field 'colour'")
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client_season(5, "2026", clients.SeasonFieldsIn(fields={"boxes": "lots"}), fake_request()))
    assert exc.value.status_code == 400
    assert not fake_db.seen("INSERT")
