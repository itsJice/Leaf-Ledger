"""Admin-only contractor info on the install schedule roster (1099 setup).

The router is readable by staff, the warehouse display (viewer) and
production, so legal name, home address, 1099 and direct-deposit flags are
stripped for anyone below admin, and a non-admin's whole-document save can
neither wipe nor change them.
"""

import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.apis import install_schedule as sched
from app.libs import roles

T0 = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)

CONTRACTOR = {
    "legalName": "Alberto Ortiz Legal", "street": "1 Main St", "city": "Houston",
    "state": "TX", "zip": "77001", "tax1099": True, "directDeposit": True,
}


def person(pid, name, **extra):
    return {"id": pid, "name": name, "title": "General Installer", "email": f"{pid}@x.test",
            "phone": "(555) 555-0100", **extra}


def stored_state():
    return {
        "season": "2026",
        "placement": {"12": "d1"},
        "roster": [person("p1", "Alberto", **CONTRACTOR), person("p2", "Bea")],
        "staffing": {"d1": ["p1"]},
    }


def run(coro):
    return asyncio.run(coro)


def roster_of(doc):
    return {p["id"]: p for p in doc["roster"]}


BELOW_ADMIN = ["staff", "lead", "viewer", "production", "crew"]


# ─── who sees it ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role,full", [
    *[(r, False) for r in BELOW_ADMIN], ("admin", True), ("super_admin", True),
    ("", False), (None, False), ("nonsense", False),
])
def test_only_admin_and_up_see_contractor_info(role, full):
    assert sched.sees_contractor_info(role) is full


def test_fields_list():
    assert sched.SENSITIVE_ROSTER_FIELDS == (
        "legalName", "street", "city", "state", "zip", "tax1099", "directDeposit")


# ─── GET /state ──────────────────────────────────────────────────────────────


def _serve_state(fake_db, state):
    fake_db.on_fetchrow("FROM ll_app.install_schedule_state WHERE version = $1",
                        {"state": json.dumps(state), "updated_by": "u", "updated_at": T0})


@pytest.mark.parametrize("role", ["staff", "lead", "viewer", "production"])
def test_get_state_strips_for_below_admin(fake_db, role):
    _serve_state(fake_db, stored_state())
    out = run(sched.get_state("build-1", role=role))
    p1 = roster_of(out["state"])["p1"]
    for k in sched.SENSITIVE_ROSTER_FIELDS:
        assert k not in p1
    # Everything else is untouched, email included.
    assert p1["email"] == "p1@x.test" and p1["phone"] == "(555) 555-0100"
    assert out["state"]["placement"] == {"12": "d1"}
    assert out["state"]["staffing"] == {"d1": ["p1"]}


@pytest.mark.parametrize("role", ["admin", "super_admin"])
def test_get_state_keeps_for_admin(fake_db, role):
    _serve_state(fake_db, stored_state())
    out = run(sched.get_state("build-1", role=role))
    assert out["state"] == stored_state()


def test_get_state_fails_closed_without_a_role(fake_db):
    # Called with no resolved role at all (the Depends default): stripped.
    _serve_state(fake_db, stored_state())
    out = run(sched.get_state("build-1"))
    assert "legalName" not in roster_of(out["state"])["p1"]


def test_inherited_roster_is_stripped_too(fake_db):
    fake_db.on_fetchrow("WHERE version <> $1", {
        "version": "old-build", "state": json.dumps(stored_state()), "updated_at": T0})
    staff = run(sched.get_state("build-2", season="2026", role="staff"))
    assert "street" not in roster_of(staff["inherit"])["p1"]
    admin = run(sched.get_state("build-2", season="2026", role="admin"))
    assert roster_of(admin["inherit"])["p1"]["street"] == "1 Main St"


# ─── history ─────────────────────────────────────────────────────────────────


def test_history_list_carries_no_state(fake_db):
    fake_db.on_fetch("FROM ll_app.install_schedule_history",
                     [{"id": 1, "updated_by": "u", "created_at": T0}])
    out = run(sched.list_history("build-1"))
    assert set(out["entries"][0]) == {"id", "updatedBy", "createdAt"}


@pytest.mark.parametrize("role,full", [("staff", False), ("viewer", False),
                                       ("production", False), ("admin", True)])
def test_history_entry_strips_for_below_admin(fake_db, role, full):
    fake_db.on_fetchrow("FROM ll_app.install_schedule_history WHERE id = $1",
                        {"id": 9, "state": json.dumps(stored_state()), "updated_by": "u",
                         "created_at": T0})
    out = run(sched.get_history_entry(9, "build-1", role=role))
    p1 = roster_of(out["state"])["p1"]
    assert ("legalName" in p1) is full
    assert ("tax1099" in p1) is full


# ─── PUT /state ──────────────────────────────────────────────────────────────


def _saved(fake_db):
    sql, args = next((s, a) for s, a in fake_db.executed
                     if s.startswith("UPDATE ll_app.install_schedule_state"))
    hist = next(a for s, a in fake_db.executed
                if s.startswith("INSERT INTO ll_app.install_schedule_history"))
    assert hist[2] == args[1], "history must record exactly what was saved"
    return json.loads(args[1])


def _put(fake_db, fake_request, state, role):
    fake_db.on_fetchval("FOR UPDATE", json.dumps(stored_state()))
    run(sched.put_state(fake_request("user-7"), {"version": "build-1", "state": state}, role=role))
    return _saved(fake_db)


def _sent_without_fields():
    s = sched.strip_roster(stored_state())
    s["roster"][1]["notes"] = "edited by staff"
    return s


@pytest.mark.parametrize("role", ["staff", "viewer", "production"])
def test_non_admin_put_without_fields_keeps_stored_values(fake_db, fake_request, role):
    saved = _put(fake_db, fake_request, _sent_without_fields(), role)
    p1, p2 = roster_of(saved)["p1"], roster_of(saved)["p2"]
    for k, v in CONTRACTOR.items():
        assert p1[k] == v
    assert p2["notes"] == "edited by staff"
    assert not any(k in p2 for k in sched.SENSITIVE_ROSTER_FIELDS)


def test_staff_put_trying_to_change_fields_is_ignored(fake_db, fake_request):
    sent = stored_state()
    sent["roster"][0].update(legalName="Someone Else", street="9 Elm", tax1099=False,
                             directDeposit=False)
    sent["roster"][1].update(legalName="Bea Legal", zip="00000", directDeposit=True)
    saved = _put(fake_db, fake_request, sent, "staff")
    p1, p2 = roster_of(saved)["p1"], roster_of(saved)["p2"]
    for k, v in CONTRACTOR.items():
        assert p1[k] == v
    assert not any(k in p2 for k in sched.SENSITIVE_ROSTER_FIELDS)


def test_person_added_by_staff_has_none(fake_db, fake_request):
    sent = _sent_without_fields()
    sent["roster"].append(person("p3", "New", legalName="Sneaky", tax1099=True, city="X"))
    saved = _put(fake_db, fake_request, sent, "staff")
    p3 = roster_of(saved)["p3"]
    assert p3["name"] == "New"
    assert not any(k in p3 for k in sched.SENSITIVE_ROSTER_FIELDS)


def test_person_deleted_by_staff_is_gone(fake_db, fake_request):
    sent = _sent_without_fields()
    sent["roster"] = [p for p in sent["roster"] if p["id"] != "p1"]
    saved = _put(fake_db, fake_request, sent, "staff")
    assert list(roster_of(saved)) == ["p2"]


@pytest.mark.parametrize("role", ["admin", "super_admin"])
def test_admin_put_saves_fields_as_sent(fake_db, fake_request, role):
    sent = stored_state()
    sent["roster"][0].update(legalName="Alberto Corrected", directDeposit=False)
    del sent["roster"][0]["street"]
    sent["roster"][1].update(city="Katy", tax1099=True)
    saved = _put(fake_db, fake_request, sent, role)
    assert saved == sent
    p1 = roster_of(saved)["p1"]
    assert p1["legalName"] == "Alberto Corrected" and p1["directDeposit"] is False
    assert "street" not in p1


def test_non_admin_put_on_a_fresh_build_strips(fake_db, fake_request):
    # No stored row yet (fetchval -> None): nothing to keep, nothing accepted.
    sent = stored_state()
    run(sched.put_state(fake_request("u"), {"version": "build-9", "state": sent}, role="staff"))
    saved = _saved(fake_db)
    assert not any(k in p for p in saved["roster"] for k in sched.SENSITIVE_ROSTER_FIELDS)


def test_state_without_roster_is_untouched(fake_db, fake_request):
    sent = {"season": "2026", "placement": {"1": "d"}}
    assert _put(fake_db, fake_request, sent, "staff") == sent


# ─── role plumbing ───────────────────────────────────────────────────────────


def test_caller_role_uses_the_role_require_role_resolved(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    r = type("Req", (), {})()
    r.state = type("S", (), {})()
    r.state.ll_role = "viewer"
    assert run(sched.caller_role(r)) == "viewer"


def test_require_role_stashes_the_role(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)

    async def fake_resolve(email, roster_lookup=None):
        return "staff"

    monkeypatch.setattr(roles, "resolve_role", fake_resolve)
    monkeypatch.setattr(roles, "get_current_user",
                        lambda req: type("U", (), {"email": "s@x.test"})())

    class Req:
        method = "GET"
        scope = {}
        url = type("U", (), {"path": "/api/install-schedule/state"})()
        state = type("S", (), {})()

    req = Req()
    assert run(roles.require_role("staff", viewer_read=True)(req)) == "staff"
    assert req.state.ll_role == "staff"
