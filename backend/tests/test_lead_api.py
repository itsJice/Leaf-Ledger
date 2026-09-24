"""Roles, and the lead pages' guarantee: a lead only ever sees their own days."""

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.apis import lead, me, users
from app.auth.user import User
from app.libs import roles, schedule_board


def run(coro):
    return asyncio.run(coro)


def user(email):
    return User(sub=email, user_id=email, email=email, name=email.split("@")[0])


PAYLOAD = {
    "spec": {"version": "v1", "dayMeta": {"2026-11-14|Crew 1|0": {"note": "Gate code 1234", "startRow": 11}}},
    "clients": {
        "10": {"name": "Smith Home", "street": "1 Oak St", "city": "Dallas", "st": "TX", "zip": "75201", "phone": "555"},
        "11": {"name": "Jones Office", "street": "2 Elm St", "city": "Dallas", "st": "TX", "zip": "75202"},
        "12": {"name": "Other Crew Client", "street": "3 Pine", "city": "Plano", "st": "TX", "zip": "75023"},
    },
    "days": [
        {"id": "2026-11-14|Crew 1|0", "date": "2026-11-14", "crew": "Crew 1", "stops": [10, 11]},
        {"id": "2026-11-14|Crew 3|0", "date": "2026-11-14", "crew": "Crew 3", "stops": [12]},
    ],
}
STATE = {
    "roster": [
        {"id": "p1", "first": "Ana", "last": "Lead", "title": "Lead", "email": "Ana@Example.com"},
        {"id": "p2", "first": "Bo", "last": "Helper", "title": "General Installer", "email": "bo@example.com"},
        {"id": "p3", "first": "Cy", "last": "Other", "title": "Lead", "email": "cy@example.com"},
    ],
    "staffing": {"2026-11-14|Crew 1|0": ["p1", "p2"], "2026-11-14|Crew 3|0": ["p3"]},
}


@pytest.fixture
def board(monkeypatch):
    b = schedule_board.resolve("2026", PAYLOAD, STATE)

    async def fake_load(*_, **__):
        return b

    monkeypatch.setattr(schedule_board, "load_board", fake_load)
    roles.clear_cache()
    yield b
    roles.clear_cache()


@pytest.fixture
def on_shift_day(monkeypatch):
    monkeypatch.setattr(lead, "today", lambda: "2026-11-14")


# ─── board resolution ────────────────────────────────────────────────────────


def test_board_orders_start_row_first_and_labels_crews_by_position(board):
    day = board.days["2026-11-14|Crew 1|0"]
    assert day["stops"] == [11, 10]
    assert board.crew_label(board.days["2026-11-14|Crew 3|0"]) == "Crew 2"
    assert board.lead_of("2026-11-14|Crew 1|0")["id"] == "p1"


def test_board_uses_saved_placement_and_manual_order():
    state = dict(STATE, placement={"10": ["2026-11-14|Crew 3|0"], "12": ["2026-11-14|Crew 3|0"]},
                 manualOrder={"2026-11-14|Crew 3|0": [12, 10]})
    b = schedule_board.resolve("2026", PAYLOAD, state)
    assert b.days["2026-11-14|Crew 3|0"]["stops"] == [12, 10]
    assert "2026-11-14|Crew 1|0" not in b.days  # 11 is unplaced, so Crew 1 has no stops


def test_extract_payload():
    html = '<script>const DATA = {"a": [1, 2]};\nfoo()</script>'
    assert schedule_board.extract_payload(html) == {"a": [1, 2]}


# ─── roles ───────────────────────────────────────────────────────────────────


def test_owner_is_always_super_admin(fake_db):
    assert run(roles.resolve_role("  Justice@Wenzdays.com ")) == "super_admin"
    assert fake_db.executed == []


def test_role_row_wins_then_roster_then_staff(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    assert run(roles.resolve_role("ana@example.com")) == "lead"
    assert run(roles.resolve_role("bo@example.com")) == "crew"
    assert run(roles.resolve_role("office@example.com")) == "staff"
    roles.clear_cache()
    fake_db.on_fetchval("FROM ll_app.user_roles", "admin")
    assert run(roles.resolve_role("ana@example.com")) == "admin"


def test_roster_failure_fails_closed(fake_db):
    async def boom(_):
        raise RuntimeError("schedule down")

    roles.clear_cache()
    assert run(roles.resolve_role("office@example.com", roster_lookup=boom)) == "crew"
    assert "office@example.com" not in roles._cache


def test_require_role_blocks_leads_from_staff_routers(fake_db, board, fake_request):
    from app.auth import supabase_auth

    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    dep = roles.require_role("staff")
    req = fake_request("x")
    orig = supabase_auth.get_current_user
    roles.get_current_user = lambda _r: supabase_auth.AuthUser(sub="x", email="ana@example.com")
    try:
        with pytest.raises(HTTPException) as exc:
            run(dep(req))
        assert exc.value.status_code == 403
        roles.get_current_user = lambda _r: supabase_auth.AuthUser(sub="y", email="office@example.com")
        assert run(dep(req)) == "staff"
    finally:
        roles.get_current_user = orig


def test_router_min_roles():
    assert lead.MIN_ROLE == "lead"
    assert me.MIN_ROLE == "crew"
    from app.apis import preferences

    assert preferences.MIN_ROLE == "crew"  # the app shell loads it for everyone
    assert users.MIN_ROLE == "super_admin"
    from app.apis import admin_dashboard, install_schedule, clients

    assert admin_dashboard.MIN_ROLE == "admin"
    # No MIN_ROLE means office staff only -- a lead can't read the full client list.
    assert not hasattr(install_schedule, "MIN_ROLE")
    assert not hasattr(clients, "MIN_ROLE")


def test_me_reports_field_only_for_leads(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    out = run(me.get_me(user("ana@example.com")))
    assert (out["role"], out["fieldOnly"], out["person"]["id"]) == ("lead", True, "p1")


# ─── shifts ──────────────────────────────────────────────────────────────────


def test_lead_sees_only_their_own_days(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    out = run(lead.my_shifts(user("ana@example.com")))
    assert [d["id"] for d in out["days"]] == ["2026-11-14|Crew 1|0"]
    day = out["days"][0]
    assert [s["name"] for s in day["stops"]] == ["Jones Office", "Smith Home"]
    assert day["note"] == "Gate code 1234"
    assert [p["id"] for p in day["crew"]] == ["p1", "p2"]
    assert day["stops"][1]["mapsUrl"].endswith("destination=1+Oak+St%2C+Dallas%2C+TX+75201")
    assert out["leads"] == [] and out["supervisor"] is False
    assert "Other Crew Client" not in str(out)


def test_lead_cannot_ask_for_another_leads_days(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    out = run(lead.my_shifts(user("ana@example.com"), person_id="p3"))
    assert [d["id"] for d in out["days"]] == ["2026-11-14|Crew 1|0"]


def test_office_sees_every_day_and_can_filter_by_lead(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    out = run(lead.my_shifts(user("office@example.com")))
    assert len(out["days"]) == 2 and out["supervisor"]
    assert [p["id"] for p in out["leads"]] == ["p1", "p3"]
    out = run(lead.my_shifts(user("office@example.com"), person_id="p3"))
    assert [d["id"] for d in out["days"]] == ["2026-11-14|Crew 3|0"]


# ─── time ────────────────────────────────────────────────────────────────────


def test_start_closes_the_persons_clock_elsewhere_then_opens_here(fake_db, board, on_shift_day):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    body = lead.ClockIn(dayId="2026-11-14|Crew 1|0", row=10, personIds=["p1", "p2"])
    run(lead.start_time(body, user("ana@example.com")))
    closes = fake_db.calls("UPDATE ll_app.shift_time_entries SET ended_at = $3")
    inserts = fake_db.calls("INSERT INTO ll_app.shift_time_entries")
    assert [a[1] for _, a in closes] == ["p1", "p2"]
    assert [(a[2], a[4], a[7]) for _, a in inserts] == [
        (10, "p1", "ana@example.com"), (10, "p2", "ana@example.com")]


def test_start_rejects_other_crews_stops_and_people(fake_db, board, on_shift_day):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    ana = user("ana@example.com")
    with pytest.raises(HTTPException) as exc:
        run(lead.start_time(lead.ClockIn(dayId="2026-11-14|Crew 3|0", row=12, personIds=["p3"]), ana))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        run(lead.start_time(lead.ClockIn(dayId="2026-11-14|Crew 1|0", row=12, personIds=["p1"]), ana))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        run(lead.start_time(lead.ClockIn(dayId="2026-11-14|Crew 1|0", row=10, personIds=["p3"]), ana))
    assert exc.value.status_code == 400
    assert not fake_db.seen("INSERT INTO ll_app.shift_time_entries")


def test_leads_only_record_time_on_the_day(fake_db, board, monkeypatch):
    monkeypatch.setattr(lead, "today", lambda: "2026-11-15")
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    body = lead.ClockIn(dayId="2026-11-14|Crew 1|0", row=10, personIds=["p1"])
    with pytest.raises(HTTPException) as exc:
        run(lead.start_time(body, user("ana@example.com")))
    assert exc.value.status_code == 409
    run(lead.start_time(body, user("office@example.com")))  # the office can fix any day
    assert fake_db.seen("INSERT INTO ll_app.shift_time_entries")


def test_edit_rejects_stop_before_start(fake_db, board, on_shift_day):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    t = datetime(2026, 11, 14, 15, tzinfo=timezone.utc)
    fake_db.on_fetchrow("FROM ll_app.shift_time_entries WHERE id", {
        "id": 5, "day_id": "2026-11-14|Crew 1|0", "started_at": t, "ended_at": None})
    with pytest.raises(HTTPException) as exc:
        run(lead.edit_time(5, lead.EntryEdit(endedAt=t.replace(hour=14)), user("ana@example.com")))
    assert exc.value.status_code == 400


def test_lead_cannot_edit_another_crews_entry(fake_db, board, on_shift_day):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    fake_db.on_fetchrow("FROM ll_app.shift_time_entries WHERE id", {
        "id": 6, "day_id": "2026-11-14|Crew 3|0", "started_at": datetime.now(timezone.utc), "ended_at": None})
    with pytest.raises(HTTPException) as exc:
        run(lead.delete_time(6, user("ana@example.com")))
    assert exc.value.status_code == 404
    assert not fake_db.seen("DELETE FROM ll_app.shift_time_entries")


# ─── notes ───────────────────────────────────────────────────────────────────


def _note_row(sql, *a):
    return {"id": 1, "day_id": a[1], "client_row": a[2], "kind": a[6], "text": a[7],
            "author": a[8], "activity_id": a[5], "created_at": datetime.now(timezone.utc)}


def test_client_request_goes_to_the_client_record(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    fake_db.on_fetchval("SELECT id FROM clients", 42)
    fake_db.on_fetchval("INSERT INTO client_activity", 900)
    fake_db.on("INSERT INTO ll_app.shift_notes", _note_row, method="fetchrow")
    out = run(lead.add_note(lead.NoteIn(dayId="2026-11-14|Crew 1|0", row=10, kind="client_request",
                                        text=" Wants wreath on garage "), user("ana@example.com")))
    assert out["savedToClient"] and out["kind"] == "client_request"
    (_, args), = fake_db.calls("INSERT INTO client_activity")
    assert args[0] == 42
    assert args[2] == "Client request (2026-11-14): Wants wreath on garage"
    assert '"tag": "client_request"' in args[3]


def test_note_is_kept_even_without_a_matching_client(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    fake_db.on("INSERT INTO ll_app.shift_notes", _note_row, method="fetchrow")
    out = run(lead.add_note(lead.NoteIn(dayId="2026-11-14|Crew 1|0", row=10, text="Broke a bulb"),
                            user("ana@example.com")))
    assert out["savedToClient"] is False
    assert not fake_db.seen("INSERT INTO client_activity")


def test_only_the_author_or_office_deletes_a_note(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    fake_db.on_fetchrow("FROM ll_app.shift_notes WHERE id", {
        "id": 3, "day_id": "2026-11-14|Crew 1|0", "author": "someone@example.com", "activity_id": 77})
    with pytest.raises(HTTPException) as exc:
        run(lead.delete_note(3, user("ana@example.com")))
    assert exc.value.status_code == 403
    run(lead.delete_note(3, user("office@example.com")))
    assert fake_db.calls("DELETE FROM client_activity")[0][1] == (77,)


# ─── users ───────────────────────────────────────────────────────────────────


def test_owner_role_cannot_be_changed(fake_db):
    with pytest.raises(HTTPException):
        run(users.set_role(users.RoleIn(email="JUSTICE@wenzdays.com", role="crew"), user("justice@wenzdays.com")))


def test_set_role_writes_and_clears_cache(fake_db, board):
    roles._cache["bo@example.com"] = (10**12, "crew")
    fake_db.on_fetchval("FROM ll_app.user_roles", "lead")
    out = run(users.set_role(users.RoleIn(email=" Bo@Example.com", role="lead"), user("justice@wenzdays.com")))
    assert out == {"email": "bo@example.com", "role": "lead"}
    assert fake_db.calls("INSERT INTO ll_app.user_roles (email, role, updated_by) VALUES ($1, $2, $3)")[0][1] == (
        "bo@example.com", "lead", "justice@wenzdays.com")
