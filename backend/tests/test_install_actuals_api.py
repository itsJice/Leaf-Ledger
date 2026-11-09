"""Install Times API: every role's access, joint crews, corrections as new
rows, and the time placement done server-side."""

import asyncio
import pathlib
import re
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.apis import install_actuals as IA
from app.auth.user import User
from app.libs import install_times as T
from app.libs import roles, schedule_board


def run(coro):
    return asyncio.run(coro)


def user(email):
    return User(sub=email, user_id=email, email=email, name=email.split("@")[0])


NIGHT = 450
PAYLOAD = {
    "spec": {
        "version": "v1",
        "const": {"NIGHT": NIGHT, "CREWS": ["Crew 1", "Crew 2", "Crew 3"]},
        "calendar": [{"date": "2026-11-04", "kind": "dallas_night"}],
        "dayMeta": {
            "2026-11-04|Crew 1|0": {"win": NIGHT},
            "2026-11-04|Crew 2|0": {"win": NIGHT},
            "2026-11-04|Crew 3|0": {"win": NIGHT},
        },
    },
    "clients": {
        "69": {"name": "M Crowd Nebraska Furniture Mart", "cat": "M Crowd", "bus": "Business", "h26": 6.0},
        "70": {"name": "M Crowd On The Park", "cat": "M Crowd", "bus": "Business", "h26": 2.5},
        "63": {"name": "M Crowd Lake Highlands", "cat": "M Crowd", "bus": "Business", "h26": 3.0},
        "10": {"name": "Smith, Ann", "bus": "Residence", "h26": 2.4, "city": "Houston"},
        "11": {"name": "Acme Office", "bus": "Business", "h26": 4.0},
    },
    "days": [
        {"id": "2026-11-04|Crew 1|0", "date": "2026-11-04", "crew": "Crew 1", "stops": [63]},
        {"id": "2026-11-04|Crew 2|0", "date": "2026-11-04", "crew": "Crew 2", "stops": [69, 70]},
        {"id": "2026-11-04|Crew 3|0", "date": "2026-11-04", "crew": "Crew 3", "stops": [69, 70]},
        {"id": "2026-11-19|Crew 1|0", "date": "2026-11-19", "crew": "Crew 1", "stops": [10, 11]},
    ],
}
STATE = {
    "roster": [
        {"id": "p1", "first": "Chris", "last": "Lead", "title": "Lead", "email": "chris@example.com"},
        {"id": "p2", "first": "Alberto", "last": "Lead", "title": "Lead", "email": "alberto@example.com"},
        {"id": "p3", "first": "Lesly", "last": "Lead", "title": "Lead", "email": "lesly@example.com"},
        {"id": "p4", "first": "Bo", "last": "Helper", "title": "General Installer", "email": "bo@example.com"},
    ],
    "staffing": {
        "2026-11-04|Crew 1|0": ["p3"],
        "2026-11-04|Crew 2|0": ["p1", "p4"],
        "2026-11-04|Crew 3|0": ["p1", "p4"],
        # Alberto is staffed (not as the day's lead) on the 11/19 day Lesly leads.
        "2026-11-19|Crew 1|0": ["p3", "p2"],
    },
}
NOW = datetime(2026, 11, 20, 9, 30, tzinfo=T.TZ)


@pytest.fixture
def board(monkeypatch):
    b = schedule_board.resolve("2026", PAYLOAD, STATE)

    async def fake_load(*_, **__):
        return b

    monkeypatch.setattr(schedule_board, "load_board", fake_load)
    monkeypatch.setattr(IA, "now_ct", lambda: NOW)
    roles.clear_cache()
    yield b
    roles.clear_cache()


def as_role(fake_db, role):
    """The ll_app.user_roles row; None falls back to the roster title."""
    fake_db.on_fetchval("FROM ll_app.user_roles", role)


def _saved_row(sql, *a):
    cols = ["client_id", "client_name", "client_row", "season", "kind", "date", "day_id", "crew_label",
            "crew_lead", "arrive_at", "depart_at", "people_count", "photos_done", "scope_note",
            "est_hours_at_time", "job_type", "night", "source", "entered_by", "supersedes_id"]
    return {"id": 501, "created_at": NOW, **dict(zip(cols, a))}


# ─── access per role ─────────────────────────────────────────────────────────


def test_router_min_role_and_production_allowlist():
    assert IA.MIN_ROLE == "lead"
    # Crew and the display login are refused by MIN_ROLE; production's
    # allowlist doesn't open these routes for reading or writing.
    assert not roles.allowed("crew", IA.MIN_ROLE, "GET")
    assert not roles.allowed("viewer", IA.MIN_ROLE, "GET")
    for method, path in [("GET", "/api/install-times/day"), ("POST", "/api/install-times/actuals"),
                         ("GET", "/api/install-times/reports")]:
        assert not roles.allowed("production", IA.MIN_ROLE, method, path=path)
    assert roles.allowed("lead", IA.MIN_ROLE, "POST")
    assert roles.allowed("staff", IA.MIN_ROLE, "POST")


def test_office_sees_every_crew_with_joint_crews_merged(fake_db, board):
    as_role(fake_db, "staff")
    out = run(IA.day_view(user("office@example.com"), on="2026-11-04"))
    assert out["office"] is True
    assert out["dates"] == ["2026-11-04", "2026-11-19"]
    labels = [(c["label"], c["dayId"], c["night"], c["lead"]) for c in out["crews"]]
    assert labels == [
        ("Crew 1", "2026-11-04|Crew 1|0", True, "Lesly Lead"),
        ("Crews 2 + 3", "2026-11-04|Crew 2|0", True, "Chris Lead"),
    ]
    joint = out["crews"][1]
    assert joint["dayIds"] == ["2026-11-04|Crew 2|0", "2026-11-04|Crew 3|0"]
    assert joint["headcount"] == 2
    # Joint stops are half each crew's hours on the board: the shared crew's
    # estimate for the visit is the half.
    assert [(s["row"], s["estHours"], s["jobType"]) for s in joint["stops"]] == [
        (69, 3.0, "restaurant"), (70, 1.25, "restaurant")]
    assert all(s["actual"] is None for s in joint["stops"])


def test_default_date_is_last_night_before_noon(fake_db, board):
    as_role(fake_db, "admin")
    assert IA.default_date(["2026-11-04", "2026-11-19"], NOW) == "2026-11-19"
    morning_after = datetime(2026, 11, 5, 9, 0, tzinfo=T.TZ)
    assert IA.default_date(["2026-11-04", "2026-11-05", "2026-11-19"], morning_after) == "2026-11-04"
    afternoon = datetime(2026, 11, 5, 15, 0, tzinfo=T.TZ)
    assert IA.default_date(["2026-11-04", "2026-11-05"], afternoon) == "2026-11-05"
    before_season = datetime(2026, 10, 1, 15, 0, tzinfo=T.TZ)
    assert IA.default_date(["2026-11-04"], before_season) == "2026-11-04"
    assert IA.default_date([], NOW) is None
    out = run(IA.day_view(user("office@example.com"), on=None))
    assert out["date"] == "2026-11-19"


def test_lead_sees_only_crew_days_they_lead_or_are_staffed_on(fake_db, board):
    as_role(fake_db, None)  # roster title Lead -> lead
    chris = run(IA.day_view(user("chris@example.com"), on="2026-11-04"))
    assert chris["role"] == "lead" and chris["office"] is False
    assert chris["dates"] == ["2026-11-04"]
    assert [c["label"] for c in chris["crews"]] == ["Crews 2 + 3"]
    # Alberto is staffed (not lead) on 11/19: he may enter it.
    alberto = run(IA.day_view(user("alberto@example.com"), on="2026-11-19"))
    assert [c["dayId"] for c in alberto["crews"]] == ["2026-11-19|Crew 1|0"]
    assert run(IA.day_view(user("alberto@example.com"), on="2026-11-04"))["crews"] == []


def test_lead_cannot_save_another_crews_stop(fake_db, board):
    as_role(fake_db, None)
    with pytest.raises(HTTPException) as exc:
        run(IA.save_actual(IA.ActualIn(dayId="2026-11-04|Crew 1|0", row=63, arrive="10p", depart="1a"),
                           user("chris@example.com")))
    assert exc.value.status_code == 404
    assert not fake_db.seen("INSERT INTO ll_app.install_actuals")


def test_crew_member_has_no_lead_rights_even_if_called_directly(fake_db, board):
    as_role(fake_db, None)  # Bo's roster title is General Installer -> crew
    viewer = run(IA._viewer(user("bo@example.com"), board))
    assert viewer.role == "crew"
    assert not IA.may_enter(viewer, board, "2026-11-04|Crew 2|0")


@pytest.mark.parametrize("role", ["viewer", "production"])
def test_outside_roles_cannot_enter_even_if_called_directly(fake_db, board, role):
    as_role(fake_db, role)
    with pytest.raises(HTTPException) as exc:
        run(IA.save_actual(IA.ActualIn(dayId="2026-11-19|Crew 1|0", row=10, arrive="8a"),
                           user("x@example.com")))
    assert exc.value.status_code == 404


@pytest.mark.parametrize("role,email", [(None, "chris@example.com")])
def test_reports_and_client_history_are_office_only(fake_db, board, role, email):
    as_role(fake_db, role)
    for call in (IA.reports(user(email)), IA.client_history(7, user(email))):
        with pytest.raises(HTTPException) as exc:
            run(call)
        assert exc.value.status_code == 403


# ─── saving ──────────────────────────────────────────────────────────────────


def test_lead_saves_their_joint_crew_stop_with_midnight_rollover(fake_db, board):
    as_role(fake_db, None)
    fake_db.on_fetch("SELECT id, name, sheet_name, former_names FROM clients",
                     [{"id": 88, "name": "M Crowd Nebraska Furniture Mart", "sheet_name": None, "former_names": []}])
    fake_db.on("INSERT INTO ll_app.install_actuals", _saved_row, method="fetchrow")
    # Crew 3 is the second crew-day of the joint shift; the visit is keyed by Crew 2's id.
    out = run(IA.save_actual(IA.ActualIn(dayId="2026-11-04|Crew 3|0", row=69, arrive="10:15p", depart="2:15a",
                                         peopleCount=6, photosDone=True, source="claude"),
                             user("chris@example.com")))
    a = out["actual"]
    assert (a["dayId"], a["crewLabel"], a["crewLead"]) == ("2026-11-04|Crew 2|0", "Crews 2 + 3", "Chris Lead")
    assert (a["arrive"], a["depart"], a["actualHours"]) == ("10:15 PM", "2:15 AM", 4.0)
    assert a["departAt"].startswith("2026-11-05T02:15")
    assert (a["clientId"], a["kind"], a["night"], a["jobType"], a["estHours"]) == (88, "install", True, "restaurant", 3.0)
    # A lead's entry is always labeled "lead", whatever the body says.
    assert (a["source"], a["enteredBy"], a["peopleCount"], a["photosDone"]) == ("lead", "chris@example.com", 6, True)
    assert fake_db.seen("pg_advisory_xact_lock")


def test_office_correction_inserts_a_new_row_pointing_at_the_old(fake_db, board):
    as_role(fake_db, "staff")
    fake_db.on_fetchrow("FROM ll_app.install_actuals_latest WHERE season", {
        **_saved_row("", None, "Smith, Ann", 10, "2026", "install", None, "2026-11-19|Crew 1|0", "Crew 1",
                     "Lesly Lead", None, None, None, None, None, 2.4, "residential", False, "office", "a@x", None),
        "id": 400})
    fake_db.on("INSERT INTO ll_app.install_actuals", _saved_row, method="fetchrow")
    fake_db.on_fetchval("SELECT count(*) FROM ll_app.install_actuals", 2)
    out = run(IA.save_actual(IA.ActualIn(dayId="2026-11-19|Crew 1|0", row=10, arrive="830", depart="1:15",
                                         supersedesId=400, source="claude"), user("office@example.com")))
    a = out["actual"]
    assert (a["supersedesId"], a["source"], a["corrections"]) == (400, "claude", 1)
    assert (a["arrive"], a["depart"], a["actualHours"], a["night"]) == ("8:30 AM", "1:15 PM", 4.75, False)
    assert not fake_db.seen("UPDATE ll_app.install_actuals")
    assert not fake_db.seen("DELETE FROM ll_app.install_actuals")


def test_stale_page_gets_409_with_the_current_row(fake_db, board):
    as_role(fake_db, "staff")
    fake_db.on_fetchrow("FROM ll_app.install_actuals_latest WHERE season", {
        **_saved_row("", None, "Smith, Ann", 10, "2026", "install", None, "2026-11-19|Crew 1|0", "Crew 1",
                     None, None, None, 4, None, None, 2.4, "residential", False, "lead", "lesly@example.com", None),
        "id": 401})
    with pytest.raises(HTTPException) as exc:
        run(IA.save_actual(IA.ActualIn(dayId="2026-11-19|Crew 1|0", row=10, arrive="9a", supersedesId=None),
                           user("office@example.com")))
    assert exc.value.status_code == 409
    assert exc.value.detail["current"]["id"] == 401
    assert not fake_db.seen("INSERT INTO ll_app.install_actuals")


def test_bad_time_text_is_a_400_with_a_hint(fake_db, board):
    as_role(fake_db, "staff")
    with pytest.raises(HTTPException) as exc:
        run(IA.save_actual(IA.ActualIn(dayId="2026-11-19|Crew 1|0", row=10, arrive="lunch"),
                           user("office@example.com")))
    assert exc.value.status_code == 400 and "10:15p" in exc.value.detail


def test_stop_must_be_on_the_crew_day_and_the_day_must_be_past(fake_db, board, monkeypatch):
    as_role(fake_db, "staff")
    with pytest.raises(HTTPException) as exc:
        run(IA.save_actual(IA.ActualIn(dayId="2026-11-19|Crew 1|0", row=69, arrive="9a"),
                           user("office@example.com")))
    assert exc.value.status_code == 404
    monkeypatch.setattr(IA, "now_ct", lambda: datetime(2026, 11, 10, 12, 0, tzinfo=T.TZ))
    with pytest.raises(HTTPException) as exc:
        run(IA.save_actual(IA.ActualIn(dayId="2026-11-19|Crew 1|0", row=10, arrive="9a"),
                           user("office@example.com")))
    assert exc.value.status_code == 409


def test_day_view_attaches_latest_actuals(fake_db, board):
    as_role(fake_db, "staff")
    row = {**_saved_row("", None, "Smith, Ann", 10, "2026", "install", None, "2026-11-19|Crew 1|0", "Crew 1",
                        "Lesly Lead", datetime(2026, 11, 19, 8, 30, tzinfo=T.TZ),
                        datetime(2026, 11, 19, 11, 0, tzinfo=T.TZ), 4, True, "front only", 2.4,
                        "residential", False, "office", "o@x", 399), "id": 402, "corrections": 1}
    fake_db.on_fetch("FROM ll_app.install_actuals_latest l WHERE", [row])
    out = run(IA.day_view(user("office@example.com"), on="2026-11-19"))
    stops = out["crews"][0]["stops"]
    assert stops[0]["actual"]["actualHours"] == 2.5 and stops[0]["actual"]["corrections"] == 1
    assert stops[1]["actual"] is None
    assert fake_db.seen("CREATE TABLE IF NOT EXISTS ll_app.install_actuals")


def test_reports_roll_up_and_never_show_zero_for_missing(fake_db, board):
    as_role(fake_db, "admin")
    rows = [
        {**_saved_row("", 1, "Smith, Ann", 10, "2026", "install", datetime(2026, 11, 19).date(), "d", "Crew 1",
                      "Lesly Lead", datetime(2026, 11, 19, 8, 30, tzinfo=T.TZ),
                      datetime(2026, 11, 19, 11, 30, tzinfo=T.TZ), 4, True, None, 2.4,
                      "residential", False, "office", "o@x", None), "id": 1},
        {**_saved_row("", 2, "Acme Office", 11, "2026", "install", datetime(2026, 11, 19).date(), "d", "Crew 1",
                      "Lesly Lead", None, None, None, None, None, 4.0, "commercial", False, "office", "o@x", None),
         "id": 2},
        {**_saved_row("", 1, "Smith, Ann", None, "2025", "install", datetime(2025, 11, 20).date(), None, None,
                      None, datetime(2025, 11, 20, 9, 0, tzinfo=T.TZ), datetime(2025, 11, 20, 11, 0, tzinfo=T.TZ),
                      None, None, None, 2.0, "residential", False, "imported_sheet", "claude", None), "id": 3},
    ]
    fake_db.on_fetch("FROM ll_app.install_actuals_latest ORDER BY", rows)
    out = run(IA.reports(user("office@example.com"), season="2026"))
    assert out["seasons"] == ["2025", "2026"]
    assert [(r["clientName"], r["actualHours"], r["diffHours"]) for r in out["rows"]] == [
        ("Smith, Ann", 3.0, 0.6), ("Acme Office", None, None)]
    lesly = out["byLead"][0]
    assert (lesly["visits"], lesly["compared"], lesly["missing"]) == (2, 1, 1)
    smith = next(c for c in out["byClient"] if c["clientId"] == 1)
    assert smith["seasons"]["2025"]["actualHours"] == 2.0 and smith["seasons"]["2026"]["actualHours"] == 3.0


def test_client_history_summarizes_each_season(fake_db, board):
    as_role(fake_db, "staff")
    rows = [
        {**_saved_row("", 7, "Smith, Ann", None, "2025", "install", datetime(2025, 11, 20).date(), None, None,
                      None, datetime(2025, 11, 20, 9, 0, tzinfo=T.TZ), datetime(2025, 11, 20, 11, 0, tzinfo=T.TZ),
                      None, None, None, 2.5, "residential", False, "imported_sheet", "claude", None), "id": 3},
        {**_saved_row("", 7, "Smith, Ann", None, "2025", "takedown", datetime(2026, 1, 5).date(), None, None,
                      None, None, None, None, None, None, None, "residential", False, "imported_sheet", "claude",
                      None), "id": 4},
    ]
    fake_db.on_fetch("FROM ll_app.install_actuals_latest WHERE client_id", rows)
    out = run(IA.client_history(7, user("office@example.com")))
    assert out["summary"] == [
        {"season": "2025", "kind": "install", "visits": 1, "actualHours": 2.0, "estHours": 2.5,
         "diffHours": -0.5, "diffPct": -20.0},
        {"season": "2025", "kind": "takedown", "visits": 1, "actualHours": None, "estHours": None,
         "diffHours": None, "diffPct": None},
    ]


def test_migration_file_matches_the_router_ddl():
    mig = (pathlib.Path(__file__).resolve().parent.parent / "migrations" / "028_install_actuals.sql").read_text()

    def norm(sql):
        no_comments = re.sub(r"--[^\n]*", "", sql)
        return re.sub(r"\s+", " ", no_comments).strip()

    assert norm(IA.DDL) == norm(mig)


def _open_row(entered_by):
    """Smith, Ann on 11/19: Arrive 8:30 AM saved an hour ago, no Leave yet."""
    return {**_saved_row("", None, "Smith, Ann", 10, "2026", "install", None, "2026-11-19|Crew 1|0", "Crew 1",
                         "Lesly Lead", datetime(2026, 11, 19, 8, 30, tzinfo=T.TZ), None, 2, False, None, 2.4,
                         "residential", False, "lead", entered_by, None),
            "id": 410, "created_at": datetime(2026, 11, 20, 8, 30, tzinfo=T.TZ)}


def test_leave_after_your_own_arrive_completes_the_row_not_a_correction(fake_db, board):
    as_role(fake_db, None)  # Lesly: a Lead on the roster
    fake_db.on_fetchrow("FROM ll_app.install_actuals_latest WHERE season", _open_row("lesly@example.com"))

    def updated(sql, rid, arrive, depart, people, photos, note):
        return {**_open_row("lesly@example.com"), "arrive_at": arrive, "depart_at": depart,
                "people_count": people, "photos_done": photos, "scope_note": note}

    fake_db.on("UPDATE ll_app.install_actuals SET", updated, method="fetchrow")
    fake_db.on_fetchval("SELECT count(*) FROM ll_app.install_actuals", 1)
    out = run(IA.save_actual(IA.ActualIn(dayId="2026-11-19|Crew 1|0", row=10, arrive="8:30 AM", depart="11",
                                         peopleCount=2, photosDone=True, supersedesId=410),
                             user("lesly@example.com")))
    a = out["actual"]
    assert (a["id"], a["arrive"], a["depart"], a["actualHours"], a["corrections"]) == (410, "8:30 AM", "11:00 AM", 2.5, 0)
    assert a["photosDone"] is True
    assert not fake_db.seen("INSERT INTO ll_app.install_actuals")
    assert fake_db.calls("UPDATE ll_app.install_actuals SET")[0][1][0] == 410


@pytest.mark.parametrize("who, arrive", [
    ("lesly@example.com", "8:45"),        # her own entry, but the Arrive changed
    ("office@example.com", "8:30 AM"),    # someone else filling it in
])
def test_changing_a_saved_time_or_someone_elses_entry_is_still_a_new_row(fake_db, board, who, arrive):
    as_role(fake_db, "staff" if who.startswith("office") else None)
    fake_db.on_fetchrow("FROM ll_app.install_actuals_latest WHERE season", _open_row("lesly@example.com"))
    fake_db.on("INSERT INTO ll_app.install_actuals", _saved_row, method="fetchrow")
    fake_db.on_fetchval("SELECT count(*) FROM ll_app.install_actuals", 2)
    out = run(IA.save_actual(IA.ActualIn(dayId="2026-11-19|Crew 1|0", row=10, arrive=arrive, depart="11",
                                         peopleCount=2, photosDone=False, supersedesId=410), user(who)))
    assert (out["actual"]["supersedesId"], out["actual"]["corrections"]) == (410, 1)
    assert not fake_db.seen("UPDATE ll_app.install_actuals")


def test_completing_still_refuses_a_stale_page(fake_db, board):
    as_role(fake_db, None)
    fake_db.on_fetchrow("FROM ll_app.install_actuals_latest WHERE season", _open_row("lesly@example.com"))
    with pytest.raises(HTTPException) as exc:
        run(IA.save_actual(IA.ActualIn(dayId="2026-11-19|Crew 1|0", row=10, arrive="8:30 AM", depart="11",
                                       supersedesId=None), user("lesly@example.com")))
    assert exc.value.status_code == 409
    assert not fake_db.seen("UPDATE ll_app.install_actuals") and not fake_db.seen("INSERT INTO ll_app.install_actuals")


def test_office_gets_days_still_missing_times_leads_do_not(fake_db, board):
    as_role(fake_db, "staff")
    # Crew 1's 11/4 stop and one of 11/19's two stops have both times.
    fake_db.on_fetch("SELECT day_id, client_row, kind FROM ll_app.install_actuals_latest", [
        {"day_id": "2026-11-04|Crew 1|0", "client_row": 63, "kind": "install"},
        {"day_id": "2026-11-19|Crew 1|0", "client_row": 10, "kind": "install"},
    ])
    out = run(IA.day_view(user("office@example.com"), on="2026-11-19"))
    assert out["missingDays"] == [
        {"date": "2026-11-04", "missing": 2, "stops": 3},
        {"date": "2026-11-19", "missing": 1, "stops": 2},
    ]
    assert fake_db.calls("SELECT day_id, client_row, kind FROM ll_app.install_actuals_latest")[0][1] == ("2026",)
    roles.clear_cache()
    as_role(fake_db, None)
    lead = run(IA.day_view(user("lesly@example.com"), on="2026-11-19"))
    assert lead["missingDays"] is None


def test_missing_days_stop_at_today(board):
    office = IA.Viewer(email="o@x", role="staff")
    assert [d["date"] for d in IA.missing_by_day(board, office, set(), "2026-11-10")] == ["2026-11-04"]
