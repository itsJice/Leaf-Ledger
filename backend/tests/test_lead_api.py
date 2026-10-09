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
    req.method = "GET"
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


# ─── viewer (warehouse display) ──────────────────────────────────────────────


def test_viewer_reads_the_schedule_and_nothing_else():
    assert roles.allowed("viewer", "staff", "GET", viewer_read=True)
    assert not roles.allowed("viewer", "staff", "PUT", viewer_read=True)  # can't save the board
    assert not roles.allowed("viewer", "staff", "GET")                    # clients, orders, ...
    assert not roles.allowed("viewer", "lead", "GET")                     # lead pages
    assert roles.allowed("viewer", "crew", "GET")                         # /me, preferences
    assert not roles.allowed("lead", "staff", "GET", viewer_read=True)    # leads still can't read the tool
    from app.apis import install_schedule

    assert install_schedule.VIEWER_READ is True


def test_viewer_dependency_uses_the_request_method(fake_db, fake_request, monkeypatch):
    from app.auth import supabase_auth

    roles.clear_cache()
    fake_db.on_fetchval("FROM ll_app.user_roles", "viewer")
    monkeypatch.setattr(roles, "get_current_user",
                        lambda _r: supabase_auth.AuthUser(sub="i", email="ipad@example.com"))
    dep = roles.require_role("staff", viewer_read=True)
    req = fake_request("i")
    req.method = "GET"
    assert run(dep(req)) == "viewer"
    req.method = "PUT"
    with pytest.raises(HTTPException) as exc:
        run(dep(req))
    assert exc.value.status_code == 403
    roles.clear_cache()


def test_me_flags_the_display_login(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", "viewer")
    out = run(me.get_me(user("ipad@example.com")))
    assert (out["role"], out["viewOnly"], out["fieldOnly"]) == ("viewer", True, False)


def test_roles_ddl_widens_an_existing_table_for_viewer():
    assert "DROP CONSTRAINT IF EXISTS user_roles_role_check" in roles.DDL
    assert "'viewer'" in roles.DDL


# ─── production ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method,path,ok", [
    ("GET", "/api/forms/{slug}", True),
    ("POST", "/api/forms/{slug}/responses", True),
    ("GET", "/api/forms/{slug}/responses", True),
    ("PATCH", "/api/forms/responses/{response_id}", True),
    ("PATCH", "/api/forms/{slug}", False),                    # editing the form itself
    ("GET", "/api/products/search", True),
    ("POST", "/api/products/favorite/{product_id}", True),
    ("POST", "/api/products/ornament-match", True),
    ("GET", "/api/jobs/board-list", True),
    ("POST", "/api/jobs/create", False),                      # jobs are view-only
    ("POST", "/api/jobs/{job_id}/touch", True),               # opening a job stamps it
    ("GET", "/api/jobs/po/{order_id}/lines", False),          # purchasing isn't theirs
    ("GET", "/api/jobs/open-orders/search", False),
    ("GET", "/api/suppliers/{supplier_id}/credentials", True),  # they order from vendors
    ("PUT", "/api/suppliers/{supplier_id}", False),           # but can't edit logins
    ("GET", "/api/clients/list", True),
    ("PUT", "/api/clients/{client_id}", False),
    ("POST", "/api/clients/{client_id}/comments", True),
    ("POST", "/api/feedback", True),
    ("GET", "/api/install-schedule/page", True),
    ("PUT", "/api/install-schedule/state", False),
    ("GET", "/api/lead/shifts", True),
    ("POST", "/api/lead/time/start", False),
    ("GET", "/api/pricing/rates", False),                     # Settings rates and costs
    ("GET", "/api/settings/markup", False),
    ("GET", "/api/recipe-intelligence/pricing-rules", False),
    ("GET", "/api/dashboard/summary", False),
    ("GET", "/api/admin/category-index", False),               # Sync Operations
    ("GET", "/api/orders/list", False),
    ("GET", "/api/users", False),
])
def test_production_allowlist(method, path, ok):
    assert roles.allowed("production", "staff", method, False, path) is ok


def test_production_me_lists_pages_and_home(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", "production")
    out = run(me.get_me(user("production@example.com")))
    assert out["readOnly"] and out["home"] == "/search"
    assert "/jobs" in out["pages"] and "/settings" not in out["pages"]
    assert not out["fieldOnly"] and not out["viewOnly"]
    # The schedule's four views are four nav entries; production keeps all four.
    for p in ("/install-schedule", "/install-calendar", "/install-staffing", "/install-roster"):
        assert p in out["pages"]


def test_production_sees_every_shift_read_only(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", "production")
    out = run(lead.my_shifts(user("production@example.com")))
    assert len(out["days"]) == 2 and out["readOnly"] is True and out["supervisor"] is False


def test_production_comments_are_own_only(fake_db):
    from app.apis import feedback

    roles.clear_cache()
    fake_db.on_fetchval("FROM ll_app.user_roles", "production")
    t = datetime(2026, 10, 1, tzinfo=timezone.utc)
    fake_db.on_fetch("FROM ll_app.feature_requests", [{
        "id": 1, "message": "Add a size filter", "has_screenshot": False, "page_path": "/search",
        "submitted_name": "production", "status": "new", "created_at": t,
        "claude_status": "fixed", "claude_note": "internal", "claude_link": None,
        "claude_reviewed_at": t, "reply": "On it", "reply_name": "Justice", "replied_at": t}])
    out = run(feedback.list_feedback(User(sub="prod-1", user_id="prod-1", email="production@example.com", name="p")))
    (sql, args), = fake_db.calls("FROM ll_app.feature_requests")
    assert "submitted_by = $2" in sql and args[1] == "prod-1"
    row = out[0]
    assert row.stage == "In process" and row.reply == "On it" and row.claude_note is None
    roles.clear_cache()


def test_stage_wording():
    from app.apis.feedback import stage_of

    assert stage_of("done", None, None) == "Completed"
    assert stage_of("new", "fixed", None) == "In process"
    assert stage_of("new", "needs_human", object()) == "Reviewed"
    assert stage_of("new", None, None) == "Submitted"


# ─── client record on a stop: staff alert, install notes ─────────────────────


def test_stops_carry_staff_alert_and_install_notes(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    fake_db.on_fetchval("information_schema.columns", 3)
    when = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
    fake_db.on_fetch("LEFT JOIN client_activity ca", [
        # renamed in the app: the stop still carries the old (sheet) spelling
        {"id": 1, "name": "Smith Residence", "sheet_name": "Smith Home", "former_names": [],
         "staff_alert": "Dog in the yard", "staff_alert_by": "justice", "staff_alert_at": when,
         "install_notes": "Same day as Jones"},
        {"id": 2, "name": "Jones, Office.", "sheet_name": None, "former_names": ["Old Jones"],
         "staff_alert": None, "staff_alert_by": None, "staff_alert_at": None, "install_notes": None},
    ])
    out = run(lead.my_shifts(user("ana@example.com")))
    by_name = {s["name"]: s for s in out["days"][0]["stops"]}
    smith = by_name["Smith Home"]
    assert smith["staffAlert"] == {"text": "Dog in the yard", "by": "justice", "at": when.isoformat()}
    assert smith["installNotes"] == "Same day as Jones"
    assert by_name["Jones Office"]["staffAlert"] is None
    _, args = fake_db.calls("LEFT JOIN client_activity ca")[0]
    assert args == ("2026",)


def test_stop_extras_failure_does_not_break_shifts(fake_db, board):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)

    def boom(*_):
        raise RuntimeError("no column")

    fake_db.on("LEFT JOIN client_activity ca", boom, method="fetch")
    out = run(lead.my_shifts(user("ana@example.com")))
    assert all(s["staffAlert"] is None for s in out["days"][0]["stops"])


def test_name_index_prefers_sheet_spelling():
    rows = [{"name": "A", "sheet_name": "Shared", "former_names": []},
            {"name": "Shared", "sheet_name": None, "former_names": []}]
    assert lead.index_client_extras(rows)["shared"]["name"] == "A"
    assert lead.norm_name("  Beaver,  Austin. ") == "beaver austin"


# ─── home page Today strip ───────────────────────────────────────────────────


def test_today_summary_office_sees_every_crew_as_counts_only(fake_db, board, on_shift_day):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    out = run(lead.today_summary(user("office@example.com")))
    assert out["today"] == "2026-11-14"
    assert out["day"] == {
        "date": "2026-11-14", "isToday": True, "jobs": 3, "people": 3,
        "crews": [{"label": "Crew 1", "jobs": 2, "people": 2}, {"label": "Crew 2", "jobs": 1, "people": 1}],
    }
    # No client names, addresses or people in it.
    assert "Smith" not in str(out) and "Oak" not in str(out) and "Ana" not in str(out)


def test_today_summary_lead_sees_only_their_own_day(fake_db, board, on_shift_day):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    out = run(lead.today_summary(user("ana@example.com")))
    assert out["day"]["crews"] == [{"label": "Crew 1", "jobs": 2, "people": 2}]
    assert out["day"]["jobs"] == 2


def test_today_summary_next_day_then_none(fake_db, board, monkeypatch):
    fake_db.on_fetchval("FROM ll_app.user_roles", None)
    monkeypatch.setattr(lead, "today", lambda: "2026-10-08")
    out = run(lead.today_summary(user("office@example.com")))
    assert out["day"]["date"] == "2026-11-14" and out["day"]["isToday"] is False
    monkeypatch.setattr(lead, "today", lambda: "2026-12-01")
    assert run(lead.today_summary(user("office@example.com")))["day"] is None


def test_today_summary_production_reads_it_like_shifts(fake_db, board, on_shift_day):
    fake_db.on_fetchval("FROM ll_app.user_roles", "production")
    out = run(lead.today_summary(user("production@example.com")))
    assert out["day"]["jobs"] == 3
    assert roles.production_may("GET", "/api/lead/today-summary")
    assert not roles.production_may("POST", "/api/lead/today-summary")
