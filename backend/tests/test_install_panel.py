"""The client page's install panel (Comments #23): the board date and
confirmation, time preference, scheduling restrictions, the job's size and
the season's contact log -- and who may see and change them. No database."""
import asyncio
import datetime as dt
import json

import pytest
from fastapi import HTTPException

from app.apis import clients, install_schedule, lead
from app.auth.user import User
from app.libs import client_import, client_season, install_summary, roles, schedule_board

DAY1 = "2026-11-19|Crew 1|0"
DAY2 = "2026-11-19|Crew 2|0"
DAY3 = "2026-11-20|Crew 1|0"
PAYLOAD = {
    "spec": {"version": "v1", "const": {"NIGHT": 450, "LUNCH": 40, "DAY_CAP": 600},
             "calendar": [], "dayMeta": {},
             "rosterSeed": [{"id": "p1", "first": "Lesly", "last": "Ruiz", "title": "Lead"},
                            {"id": "p2", "first": "Ana", "last": "Diaz", "title": "General Installer"}]},
    "clients": {
        "10": {"name": "Allums, Jennifer", "h26": 3.5, "basis": "2025 real", "bus": "Residence",
               "roleNeed": {"leads": 1, "general": 2}},
        "11": {"name": "Woodlands CC", "h26": 16, "bus": "Business", "people": 8},
        "12": {"name": "Smith, Ann", "h26": 2, "bus": "Residence"},
        "13": {"name": "Off Board Client", "h26": 4, "bus": "Business"},
    },
    "days": [
        {"id": DAY1, "date": "2026-11-19", "crew": "Crew 1", "stops": [10, 12]},
        {"id": DAY2, "date": "2026-11-19", "crew": "Crew 2", "stops": [11]},
        {"id": DAY3, "date": "2026-11-20", "crew": "Crew 1", "stops": [11]},
    ],
}
STATE = {
    "placement": {"10": [DAY1], "12": [DAY1], "11": [DAY2, DAY3]},
    "confirmed": [10, "12", "999", "junk"],
    "hold": [12],
    "staffing": {DAY1: ["p1", "p2"]},
    "roster": PAYLOAD["spec"]["rosterSeed"],
}
JEN = {"id": 1, "name": "Allums, Jennifer", "sheet_name": None, "former_names": []}


def run(coro):
    return asyncio.run(coro)


def board():
    return schedule_board.resolve("2026", PAYLOAD, STATE)


# ─── the board learns the confirmed / hold sets ──────────────────────────────


def test_board_reads_confirmed_and_hold_rows_it_knows():
    b = board()
    assert b.confirmed == {10, 12}  # 999 isn't a client of this build; junk skipped
    assert b.hold == {12}
    assert schedule_board.resolve("2026", PAYLOAD, {}).confirmed == set()
    assert schedule_board.resolve("2026", PAYLOAD, {"confirmed": "nope"}).confirmed == set()


# ─── the contact log ─────────────────────────────────────────────────────────


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr(client_season, "central_today", lambda: dt.date(2026, 11, 8))
    monkeypatch.setattr(client_season, "now_iso", lambda: "2026-11-08T20:00:00+00:00")


def test_clean_contact_entry(today):
    e = client_season.clean_contact_entry({"method": "In Person", "note": "  confirmed 11/19  "}, by="Cynthia")
    assert e == {"date": "2026-11-08", "method": "in_person", "note": "confirmed 11/19",
                 "by": "Cynthia", "at": "2026-11-08T20:00:00+00:00"}
    for m in ("call", "voicemail", "text", "email", "in-person", "IN_PERSON"):
        assert client_season.clean_contact_entry({"method": m}, by=None)["method"] in client_season.CONTACT_METHODS
    assert client_season.clean_contact_entry({"method": "call", "date": "2026-11-01"}, by="x")["date"] == "2026-11-01"


@pytest.mark.parametrize("raw, msg", [
    ({"method": "fax"}, "method must be one of"),
    ({}, "method must be one of"),
    ({"method": "call", "date": "2026-11-09"}, "can't be in the future"),
    ({"method": "call", "date": "11/01/2026"}, "expected YYYY-MM-DD"),
    ({"method": "call", "note": "x" * 1001}, "at most 1000"),
    ("call", "must be an object"),
])
def test_clean_contact_entry_rejects(today, raw, msg):
    with pytest.raises(client_season.FieldError, match=msg):
        client_season.clean_contact_entry(raw, by="x")


def test_append_stamps_and_sorts_newest_first(today):
    a = client_season.clean_contact_entry({"method": "voicemail", "date": "2026-11-02"}, by="A")
    b = client_season.clean_contact_entry({"method": "call", "date": "2026-11-05"}, by="B")
    d = client_season.append_contact({"notes": "gate code"}, a)
    d = client_season.append_contact(d, b)
    assert [e["method"] for e in d["contact_log"]] == ["voicemail", "call"]  # stored in order logged
    assert [e["method"] for e in client_season.contact_log_of(d)] == ["call", "voicemail"]
    assert d["app_edits"]["contact_log"] == "2026-11-08T20:00:00+00:00"
    assert d["notes"] == "gate code"
    assert client_season.contact_log_of({"contact_log": ["junk", None]}) == []


def test_log_is_capped(today):
    d = {}
    e = client_season.clean_contact_entry({"method": "text"}, by="x")
    for _ in range(client_season.CONTACT_LOG_MAX + 5):
        d = client_season.append_contact(d, e)
    assert len(d["contact_log"]) == client_season.CONTACT_LOG_MAX


def test_sheet_sync_never_drops_the_log_even_unstamped():
    prior = {"contact_log": [{"date": "2026-11-01", "method": "call"}], "notes": "old"}
    out = client_season.merge_sheet_detail(prior, {"notes": "from sheet"})
    assert out["contact_log"] == prior["contact_log"] and out["notes"] == "from sheet"


def test_season_put_cannot_overwrite_the_log():
    with pytest.raises(client_season.FieldError, match="unknown season field"):
        client_season.apply_edits({}, {"contact_log": []})


# ─── the summary ─────────────────────────────────────────────────────────────


def test_summary_confirmed_residence_with_who_and_when():
    events = [
        {"kind": "approved", "clients": [], "at": "x", "by": "y"},
        {"kind": "confirmed", "clients": ["Allums, Jennifer"], "at": "2026-11-03T16:02:00+00:00", "by": "Cynthia"},
        {"kind": "unconfirmed", "clients": ["Allums, Jennifer"], "at": "2026-11-01T16:02:00+00:00", "by": "Old"},
    ]
    detail = {"install_date": "2026-11-19", "confirmation_notes": " called 9/23 ",
              "contact_log": [{"date": "2026-11-03", "method": "call", "note": "ok", "by": "Cynthia", "at": "t"}]}
    out = install_summary.summarize(board(), JEN, detail, events, season="2026")
    assert out["on_board"] and out["board_date"] == "2026-11-19" and out["card_date"] == "2026-11-19"
    assert not out["date_mismatch"]
    assert out["confirmed"] and out["confirmed_by"] == "Cynthia"
    assert out["confirmed_at"] == "2026-11-03T16:02:00+00:00"
    assert out["crews"] == [{"day_id": DAY1, "date": "2026-11-19", "crew": "Crew 1", "crew_title": "Crew 1",
                             "lead": "Lesly Ruiz", "staffed": 2, "stops": 2}]
    assert out["property_type"] == "Residence"
    assert out["size"] == {"est_hours": 3.5, "hours_basis": "2025 real", "crew_size": 3,
                           "roles": {"leads": 1, "general": 2}, "crew_size_basis": "schedule",
                           "crews": 1, "crew_days": 1, "days": 1, "whole_day": False, "multi_crew": False}
    assert out["legacy_confirmation_notes"] == "called 9/23"
    assert out["contact_count"] == 1 and not out["hold"]


def test_summary_unconfirmed_after_confirm_has_no_who():
    events = [{"kind": "unconfirmed", "clients": ["Allums, Jennifer"], "at": "b", "by": "B"},
              {"kind": "confirmed", "clients": ["Allums, Jennifer"], "at": "a", "by": "A"}]
    out = install_summary.summarize(board(), JEN, {}, events, season="2026")
    assert out["confirmed"]  # the board says so; the feed just can't say who
    assert out["confirmed_by"] is None and out["confirmed_at"] is None


def test_summary_card_role_need_wins_and_multi_crew_multi_day():
    cc = {"id": 2, "name": "The Woodlands CC", "sheet_name": "Woodlands CC", "former_names": []}
    out = install_summary.summarize(board(), cc, {"role_need": {"leads": 2, "designer": 1, "general": 5}},
                                    [], season="2026")
    assert out["board_dates"] == ["2026-11-19", "2026-11-20"]
    assert out["property_type"] == "Business" and not out["confirmed"]
    s = out["size"]
    assert (s["crew_size"], s["crew_size_basis"]) == (8, "card")
    assert (s["crews"], s["crew_days"], s["days"]) == (1, 2, 2)
    assert s["whole_day"] is True  # the only stop on each crew-day
    assert s["multi_crew"] is False


def test_summary_joint_stop_is_multi_crew_and_uses_people_when_no_roles():
    st = {**STATE, "placement": {**STATE["placement"], "11": [DAY1, DAY2]}}
    b = schedule_board.resolve("2026", PAYLOAD, st)
    out = install_summary.summarize(b, {"name": "Woodlands CC"}, {}, [], season="2026")
    assert out["size"]["multi_crew"] is True and out["size"]["crews"] == 2
    assert out["size"]["whole_day"] is True  # 16 h over 2 crews = 8 h each
    assert (out["size"]["crew_size"], out["size"]["crew_size_basis"]) == (8, "schedule")


def test_summary_former_name_matches_and_hold():
    ann = {"name": "Ann Smith", "former_names": ["Smith, Ann"]}
    out = install_summary.summarize(board(), ann, {"install_date": "2026-11-13"}, [], season="2026")
    assert out["on_board"] and out["hold"]
    assert out["date_mismatch"] is True  # card 11/13, board 11/19: the board wins


def test_summary_not_on_board():
    out = install_summary.summarize(board(), {"name": "Nobody"}, {"install_date": "2026-11-13", "est_hours": 2},
                                    [], season="2026")
    assert not out["on_board"] and out["board_date"] is None and out["card_date"] == "2026-11-13"
    assert out["size"]["est_hours"] == 2 and out["size"]["hours_basis"] == "season card"
    assert out["property_type"] is None and not out["confirmed"]
    off = install_summary.summarize(board(), {"name": "Off Board Client"}, {}, [], season="2026")
    assert not off["on_board"] and off["property_type"] == "Business"


def test_summary_without_a_board():
    out = install_summary.summarize(None, JEN, {"install_date": "2026-11-19"}, None, season="2026")
    assert out["board_available"] is False and not out["on_board"] and out["card_date"] == "2026-11-19"


def test_summary_never_carries_money():
    detail = {"install_fee": 500, "total": 900, "invoice_total": 850}
    blob = json.dumps(install_summary.summarize(board(), JEN, detail, [], season="2026"))
    for k in ("install_fee", "total", "invoice", "price", "$"):
        assert k not in blob


# ─── GET /clients/{id}/install-summary ───────────────────────────────────────


def test_install_summary_route(fake_db, monkeypatch):
    fake_db.on_fetchrow("FROM clients WHERE id = $1", {
        "id": 1, "name": "Allums, Jennifer", "sheet_name": None, "former_names": None,
        "time_preference": "morning", "schedule_restrictions": "No Fridays"})
    fake_db.on_fetchrow("SELECT detail FROM client_activity", {"detail": json.dumps({"install_date": "2026-11-19"})})

    async def fake_load(season=None, fresh=False):
        return board()

    async def fake_events(conn, b):
        return [{"kind": "confirmed", "clients": ["Allums, Jennifer"], "at": "2026-11-03T16:02:00+00:00",
                 "by": "Cynthia"}]

    from app.apis import schedule_changes
    monkeypatch.setattr(schedule_board, "load_board", fake_load)
    monkeypatch.setattr(schedule_changes, "load_events", fake_events)
    out = run(clients.install_summary(1))
    assert out["client_id"] == 1 and out["season"] == "2026"
    assert out["time_preference"] == "morning" and out["schedule_restrictions"] == "No Fridays"
    assert out["confirmed"] and out["confirmed_by"] == "Cynthia"
    ((_, args),) = fake_db.calls("SELECT detail FROM client_activity")
    assert args == (1, "2026")


def test_install_summary_survives_a_broken_board(fake_db, monkeypatch):
    fake_db.on_fetchrow("FROM clients WHERE id = $1", {"id": 1, "name": "X", "sheet_name": None,
                                                       "former_names": [], "time_preference": None,
                                                       "schedule_restrictions": None})

    async def boom(season=None, fresh=False):
        raise RuntimeError("db down")

    monkeypatch.setattr(schedule_board, "load_board", boom)
    out = run(clients.install_summary(1, season="2026"))
    assert out["board_available"] is False and out["season"] == "2026"


def test_install_summary_404_and_bad_season(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(clients.install_summary(404))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        run(clients.install_summary(1, season="20x6"))
    assert exc.value.status_code == 400


# ─── POST /clients/{id}/seasons/{season}/contacts ────────────────────────────


USER = User(sub="u1", user_id="u1", email="cynthia@thebranchdesigngroup.com", name="Cynthia")


def test_log_contact_appends_under_a_lock(fake_db, monkeypatch, today):
    async def no_roster(email):
        return None

    monkeypatch.setattr(schedule_board, "roster_person_for_email", no_roster)
    fake_db.on_fetchval("SELECT 1 FROM clients", 1)
    prior = {"install_date": "2026-11-19", "notes": "gate",
             "contact_log": [{"date": "2026-11-01", "method": "voicemail", "note": "", "by": "A", "at": "t0"}]}
    fake_db.on_fetchrow("FOR UPDATE", {"id": 9, "detail": json.dumps(prior)})
    out = run(clients.add_client_contact(1, "2026", clients.ContactIn(method="call", note="confirmed 11/19"), USER))
    assert [e["method"] for e in out["contacts"]] == ["call", "voicemail"]
    assert out["entry"]["by"] == "Cynthia"
    ((sql, args),) = fake_db.calls("INSERT INTO client_activity")
    assert "ON CONFLICT (client_id, kind, season) WHERE kind <> 'comment'" in sql
    saved = json.loads(args[3])
    assert saved["notes"] == "gate" and len(saved["contact_log"]) == 2
    assert "contact_log" in saved["app_edits"]
    assert args[4] == dt.date(2026, 11, 19)


def test_log_contact_creates_the_season_row(fake_db, monkeypatch, today):
    async def no_roster(email):
        return None

    monkeypatch.setattr(schedule_board, "roster_person_for_email", no_roster)
    fake_db.on_fetchval("SELECT 1 FROM clients", 1)
    out = run(clients.add_client_contact(1, "2026", clients.ContactIn(method="text"), USER))
    assert len(out["contacts"]) == 1
    ((_, args),) = fake_db.calls("INSERT INTO client_activity")
    assert args[2] == "No date recorded" and args[4] is None


def test_log_contact_rejects_bad_input_and_unknown_client(fake_db, monkeypatch, today):
    async def no_roster(email):
        return None

    monkeypatch.setattr(schedule_board, "roster_person_for_email", no_roster)
    with pytest.raises(HTTPException) as exc:
        run(clients.add_client_contact(1, "2026", clients.ContactIn(method="pigeon"), USER))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        run(clients.add_client_contact(1, "26", clients.ContactIn(method="call"), USER))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        run(clients.add_client_contact(404, "2026", clients.ContactIn(method="call"), USER))
    assert exc.value.status_code == 404
    assert not fake_db.seen("INSERT INTO client_activity")


# ─── who may see and change it ───────────────────────────────────────────────


@pytest.mark.parametrize("role, ok", [
    ("crew", False), ("viewer", False), ("production", False), ("lead", False),
    ("staff", True), ("admin", True), ("super_admin", True),
])
def test_panel_and_log_are_staff_only(role, ok):
    assert roles.allowed(role, "staff", "GET", False, "/api/clients/{client_id}/install-summary") is ok
    assert roles.allowed(role, "staff", "POST", False, "/api/clients/{client_id}/seasons/{season}/contacts") is ok


def test_routes_declare_the_staff_dependency():
    for suffix, method in (("/install-summary", "GET"), ("/contacts", "POST")):
        route = next(r for r in clients.router.routes if r.path.endswith(suffix))
        assert route.methods == {method}
        assert route.dependencies, f"{suffix} must carry require_role('staff')"


def test_production_list_hides_the_contact_log(fake_db, fake_request):
    fake_db.on_fetch("FROM clients", [{"id": 1, "name": "Allums, Jennifer", "secondary_contacts": "[]"}])
    fake_db.on_fetch("FROM client_activity", [
        {"client_id": 1, "id": 5, "kind": "christmas_install", "season": "2026", "summary": "s",
         "detail": json.dumps({"notes": "n", "contact_log": [{"method": "call"}]}),
         "occurred_at": None, "created_at": None}])

    def as_role(role):
        req = fake_request()
        req.state = type("S", (), {"ll_role": role})()
        return req

    prod = run(clients.list_clients(as_role("production")))
    staff = run(clients.list_clients(as_role("staff")))
    assert prod[0]["activity"][0]["detail"] == {"notes": "n"}
    assert staff[0]["activity"][0]["detail"]["contact_log"] == [{"method": "call"}]


# ─── scheduling restrictions on the client ───────────────────────────────────


def test_restrictions_cleaning():
    assert clients.clean_schedule_restrictions(None) is None
    assert clients.clean_schedule_restrictions("   ") == ""
    assert clients.clean_schedule_restrictions(" No Fridays ") == "No Fridays"
    with pytest.raises(HTTPException) as exc:
        clients.clean_schedule_restrictions("x" * 501)
    assert exc.value.status_code == 400


def test_update_writes_restrictions(fake_db, fake_request):
    fake_db.on_fetchval("SELECT name FROM clients WHERE id = $1", "Smith")
    fake_db.on_fetchrow("UPDATE clients SET", {"id": 5, "name": "Smith", "secondary_contacts": []})
    run(clients.update_client(5, clients.ClientUpdate(schedule_restrictions=" Gate closes at 3 "), fake_request()))
    run(clients.update_client(5, clients.ClientUpdate(schedule_restrictions=""), fake_request()))
    run(clients.update_client(5, clients.ClientUpdate(phone="1"), fake_request()))
    calls = fake_db.calls("UPDATE clients SET")
    assert [a[20] for _, a in calls] == ["Gate closes at 3", "", None]
    assert "schedule_restrictions = CASE WHEN $21::text IS NOT NULL" in calls[0][0]


def test_create_writes_restrictions(fake_db, fake_request):
    fake_db.on_fetchrow("INSERT INTO clients", {"id": 7, "name": "Smith", "secondary_contacts": "[]"})
    run(clients.create_client(clients.ClientCreate(name="Smith", schedule_restrictions="Mornings only"),
                              fake_request()))
    ((_, args),) = fake_db.calls("INSERT INTO clients")
    assert args[17] == "Mornings only"


def test_list_adds_the_restrictions_column_once(fake_db, fake_request):
    fake_db.on_fetch("FROM clients", [])
    run(clients.list_clients(fake_request()))
    run(clients.list_clients(fake_request()))
    assert len(fake_db.calls("ADD COLUMN IF NOT EXISTS schedule_restrictions text")) == 1
    assert "schedule_restrictions" in clients.ENSURED_COLUMNS


def test_import_reads_a_restrictions_column():
    mapping, ignored = client_import.map_headers(["First", "Last", "Scheduling restrictions"])
    assert mapping[2] == "schedule_restrictions" and not ignored
    assert client_import.map_headers(["Restrictions"])[0] == {0: "schedule_restrictions"}
    fields, problems, _ = client_import.build_row(
        {"first_name": "Ana", "last_name": "Diaz", "schedule_restrictions": "No Saturdays"})
    assert fields["schedule_restrictions"] == "No Saturdays" and not problems


def test_schedule_client_links_carry_restrictions(fake_db):
    fake_db.on_fetch("FROM clients", [{"id": 3, "name": "Smith, Ann", "sheet_name": None, "former_names": None,
                                       "drive_folder_url": None, "drive_photos_url": None, "city": None,
                                       "area": None, "zone": None, "schedule_restrictions": "No Fridays"}])
    out = run(install_schedule.client_links())
    assert out[0]["schedule_restrictions"] == "No Fridays"
    ((sql, _),) = fake_db.calls("FROM clients")
    assert "OR schedule_restrictions IS NOT NULL" in sql


def test_lead_stops_carry_restrictions_only():
    row = {"name": "Smith, Ann", "staff_alert": None, "install_notes": "",
           "schedule_restrictions": " No Fridays "}
    assert lead.stop_extras(row) == {"staffAlert": None, "installNotes": "", "scheduleRestrictions": "No Fridays"}
    assert lead.stop_extras(None)["scheduleRestrictions"] == ""
