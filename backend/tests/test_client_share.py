"""Client share links: one client group's read-only schedule, nothing else."""

import asyncio
import csv
import io
import re

import pytest
from fastapi import HTTPException

from app.apis import client_share as share_api
from app.apis import client_share_links as links_api
from app.libs import client_share as cs
from app.libs import schedule_board

MON = "2026-11-02|Crew 1|0"
MON2 = "2026-11-02|Crew 2|0"
MON_DAY = "2026-11-02|Crew 3|0"
HOU = "2026-11-02|Crew 3|1"
TAKE = "2026-12-28|Crew 1|0"
TOKEN = "A" * 43

# Node 0 is the branch; legs are 10 minutes everywhere.
DURS = [[0 if i == j else 600 for j in range(6)] for i in range(6)]

SECRETS = [  # strings that must never appear in a share
    "214-555-0199", "gm@micocina.example", "Alarm code 4471", "Repair: 3 broken strands",
    "Ana Lead", "512-555-0101", "Bo Helper", "Gate note for Crew 1", "Smith Home", "713-555-0100",
    "9 Secret Ln", "1234.56", "INV-2025-77",
]

PAYLOAD = {
    "depot": {"lat": 29.8, "lon": -95.4},
    "node": {"10": 1, "11": 2, "12": 3, "13": 4, "14": 5},
    "durs": DURS,
    "spec": {
        "version": "v1",
        "const": {"NIGHT": 450, "LUNCH": 40},
        "dayMeta": {
            MON: {"anchored": False, "stacked": 1, "win": 450, "half": [10], "joint": "Crew 2",
                  "note": "Gate note for Crew 1"},
            MON2: {"anchored": False, "stacked": 1, "win": 450, "half": [10], "joint": "Crew 1"},
            MON_DAY: {"anchored": False, "stacked": 1, "win": 480},
            HOU: {"anchored": True, "stacked": 1, "win": 600},
            TAKE: {"anchored": False, "stacked": 1, "win": 450},
        },
    },
    "clients": {
        "10": {"name": "M Crowd Lake Highlands", "street": "7215 Skillman St #328", "city": "Dallas",
               "st": "TX", "zip": "75231", "h26": 7.0, "phone": "214-555-0199",
               "email": "gm@micocina.example", "advice": "Alarm code 4471",
               "repairNotes": "Repair: 3 broken strands", "installFee": 1234.56,
               "invoice25": "INV-2025-77", "boxes": 9, "people": 6, "crew25": "Crew 1"},
        "11": {"name": "m crowd  Lakewood", "street": "6332 La Vista Dr", "city": "Dallas", "st": "TX",
               "zip": "75214", "h26": 2.0, "phone": "214-555-0199"},
        "12": {"name": "M Crowd Corporate Office", "street": "2455 McIver Ln", "city": "Carrollton",
               "st": "TX", "zip": "75006", "h26": 2.0},
        "13": {"name": "Smith Home", "street": "9 Secret Ln", "city": "Houston", "st": "TX",
               "zip": "77002", "h26": 3.0, "phone": "713-555-0100"},
        "14": {"name": "M Crowd Uptown", "street": "3232 McKinney Ave #175", "city": "Dallas", "st": "TX",
               "zip": "75204", "h26": 1.0, "visitType": "Takedown"},
    },
    "days": [
        {"id": MON, "date": "2026-11-02", "crew": "Crew 1", "stops": [10, 11]},
        {"id": MON2, "date": "2026-11-02", "crew": "Crew 2", "stops": [10]},
        {"id": MON_DAY, "date": "2026-11-02", "crew": "Crew 3", "stops": [12]},
        {"id": HOU, "date": "2026-11-02", "crew": "Crew 3", "stops": [13]},
        {"id": TAKE, "date": "2026-12-28", "crew": "Crew 1", "stops": [14]},
    ],
}
STATE = {
    "roster": [
        {"id": "p1", "first": "Ana", "last": "Lead", "title": "Lead", "phone": "512-555-0101"},
        {"id": "p2", "first": "Bo", "last": "Helper", "title": "General Installer"},
    ],
    "staffing": {MON: ["p1", "p2"], HOU: ["p1"]},
    # Crew 2 starts the joint job 5 minutes after Crew 1.
    "timeline": {MON2: {"start": 1380, "stops": [{"row": 10, "start": 1385, "end": 1595}]}},
}
RULE = cs.Rule(name_prefix="M Crowd ", strip_prefix="M Crowd ")
LINK = {"label": "M Crowd", "name_prefix": "M Crowd ", "client_ids": [], "strip_prefix": "M Crowd ",
        "revoked": False}


def board():
    return schedule_board.resolve("2026", PAYLOAD, STATE)


def visits(rule=RULE):
    return cs.visits(board(), rule)


# ---------- what is shown ----------

def test_only_matching_locations_with_the_prefix_stripped():
    assert [(v.date, v.location, v.kind) for v in visits()] == [
        ("2026-11-02", "Corporate Office", "Install"),
        ("2026-11-02", "Lake Highlands", "Install"),
        ("2026-11-02", "Lakewood", "Install"),
        ("2026-12-28", "Uptown", "Takedown"),
    ]


def test_night_times_use_the_schedule_tools_stop_math():
    v = {x.location: x for x in visits()}
    # 11 PM start, crews already in Dallas (not depot-anchored), half of 7 h each.
    assert (v["Lake Highlands"].start, v["Lake Highlands"].end) == (1380, 1590)   # 2:35 -> 2:30 AM
    assert (v["Lakewood"].start, v["Lakewood"].end) == (1605, 1725)   # 2:40-4:40 AM -> 2:45-4:45 AM
    assert (v["Corporate Office"].start, v["Corporate Office"].end) == (540, 660)   # the 9-5 office


def test_joint_stop_is_one_event_spanning_both_crews():
    lh = [x for x in visits() if x.location == "Lake Highlands"]
    assert len(lh) == 1
    assert (lh[0].start, lh[0].end) == (1380, 1590)   # Crew 1's 11:00 PM to Crew 2's 2:35 AM, rounded


def test_explicit_client_ids_match_by_every_spelling():
    rule = share_api.rule_for({"client_ids": [7], "name_prefix": ""},
                              [{"id": 7, "name": "Mi Cocina Corp", "sheet_name": "M Crowd Corporate Office",
                                "former_names": []},
                               {"id": 8, "name": "Smith Home", "sheet_name": None, "former_names": []}])
    assert [v.location for v in visits(rule)] == ["M Crowd Corporate Office"]


def test_renamed_client_shows_its_current_name():
    vs = cs.visits(board(), RULE, names={11: "M Crowd Lakewood (La Vista)"})
    assert "Lakewood (La Vista)" in [v.location for v in vs]


def test_takedown_cutoff():
    assert not cs.is_takedown("2026-12-25", None)
    assert cs.is_takedown("2026-12-26", None) and cs.is_takedown("2027-01-15", None)
    assert cs.is_takedown("2026-11-02", "Takedown")


# ---------- ICS ----------

def ics_text():
    return cs.build_ics("M Crowd", visits())


def unfolded(ics):
    return ics.replace("\r\n ", "")


def test_ics_events_titles_location_description_and_central_times():
    ics = unfolded(ics_text())
    assert "SUMMARY:Lake Highlands – TBDG Christmas install" in ics
    assert "SUMMARY:Uptown – TBDG Christmas takedown" in ics
    assert "LOCATION:7215 Skillman St #328\\, Dallas\\, TX 75231" in ics
    assert ("DESCRIPTION:After-hours install by The Branch Design Group (TBDG). "
            "Times are estimates.") in ics
    assert "DTSTART;TZID=America/Chicago:20261102T230000" in ics
    assert "DTEND;TZID=America/Chicago:20261103T023000" in ics   # runs into the next morning
    assert ics.count("BEGIN:VEVENT") == 4


def test_ics_meets_google_calendar_requirements():
    ics = ics_text()
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "\n" not in ics.replace("\r\n", "")                       # CRLF only
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n"))
    assert "BEGIN:VTIMEZONE\r\nTZID:America/Chicago" in ics
    events = ics.split("BEGIN:VEVENT")[1:]
    assert all("\r\nUID:" in e and "\r\nDTSTAMP:" in e for e in events)
    uids = re.findall(r"^UID:(.*)$", ics, re.M)
    assert len(uids) == len(set(uids)) == 4


def test_uids_are_stable_when_a_visit_moves_and_carry_no_internal_ids():
    before = {v.location: v.uid for v in visits()}
    moved = {**STATE, "placement": {"10": [MON, MON2], "11": [TAKE.replace("12-28", "11-03")],
                                     "12": [MON_DAY], "13": [HOU], "14": [TAKE]}}
    after = {v.location: v.uid for v in cs.visits(schedule_board.resolve("2026", PAYLOAD, moved), RULE)}
    assert before["Lakewood"] == after["Lakewood"]
    for uid in before.values():
        assert re.fullmatch(r"tbdg-share-[0-9a-f]{20}@leaf-and-ledger", uid)


def test_ics_parses_with_a_real_parser():
    icalendar = pytest.importorskip("icalendar")
    cal = icalendar.Calendar.from_ical(ics_text())
    evs = [c for c in cal.walk("VEVENT")]
    assert len(evs) == 4
    lh = next(e for e in evs if str(e["SUMMARY"]).startswith("Lake Highlands"))
    start = lh["DTSTART"].dt
    assert str(start.tzinfo).endswith("Chicago") or start.utcoffset().total_seconds() == -6 * 3600
    assert start.hour == 23


# ---------- CSV ----------

def csv_rows():
    return list(csv.reader(io.StringIO(cs.build_csv(visits()))))


def test_csv_columns_order_twelve_hour_times_and_takedown_tbd():
    rows = csv_rows()
    assert rows[0] == ["Night", "Location", "Address", "Arrive", "Finish", "Type"]
    assert rows[1] == ["Mon 11/2/2026", "Corporate Office", "2455 McIver Ln, Carrollton, TX 75006",
                       "9:00 AM", "11:00 AM", "Install"]
    assert rows[2] == ["Mon 11/2/2026", "Lake Highlands", "7215 Skillman St #328, Dallas, TX 75231",
                       "11:00 PM", "2:30 AM", "Install"]
    assert rows[3][1] == "Lakewood" and rows[3][3] == "2:45 AM"
    assert rows[4] == ["Mon 12/28/2026", "Uptown", "3232 McKinney Ave #175, Dallas, TX 75204",
                       "11:00 PM", "12:00 AM", "Takedown"]
    tbd = rows[5:]
    assert [r[1] for r in tbd] == ["Corporate Office", "Lake Highlands", "Lakewood"]   # Uptown is scheduled
    assert all(r[0] == r[3] == r[4] == "TBD" and r[5] == "Takedown – TBD" for r in tbd)


def test_csv_cells_cannot_become_formulas():
    v = cs.Visit("=HYPERLINK(1)", "-1 St", "2026-11-02", 1380, 1440, "Install", "u")
    row = list(csv.reader(io.StringIO(cs.build_csv([v]))))[1]
    assert row[1].startswith("'=") and row[2].startswith("'-")


# ---------- strict data exposure ----------

def test_no_other_client_or_private_field_appears_anywhere():
    outputs = [unfolded(ics_text()), cs.build_csv(visits())]
    for out in outputs:
        for s in SECRETS:
            assert s not in out, s
        assert "Crew" not in out                   # no crew labels or names
        assert "Houston" not in out
        assert not re.search(r"\bRow \d|\|Crew|leaf-ledger\.onrender", out)


def test_ics_events_carry_only_the_allowed_properties():
    allowed = {"BEGIN", "END", "UID", "DTSTAMP", "DTSTART", "DTEND", "SUMMARY", "LOCATION",
               "DESCRIPTION", "TRANSP"}
    body = unfolded(ics_text())
    for ev in body.split("BEGIN:VEVENT")[1:]:
        ev = ev.split("END:VEVENT")[0]
        props = {re.split(r"[:;]", l, maxsplit=1)[0] for l in ev.split("\r\n") if l}
        assert props <= allowed, props


def test_visit_records_hold_only_the_shared_fields():
    assert set(cs.Visit.__dataclass_fields__) == {"location", "address", "date", "start", "end", "kind", "uid"}


# ---------- endpoints ----------

@pytest.fixture
def live(monkeypatch, fake_db):
    b = board()

    async def fake_load(*_, **__):
        return b

    monkeypatch.setattr(schedule_board, "load_board", fake_load)
    links = {TOKEN: dict(LINK)}

    def lookup(sql, token):
        row = links.get(token)
        return dict(row) if row and not row["revoked"] else None

    fake_db.on("FROM ll_app.client_share_links WHERE token", lookup, method="fetchrow")
    fake_db.on_fetch("FROM clients", [{"id": 1, "name": "Smith Home", "sheet_name": None, "former_names": []}])
    return links


def test_ics_and_csv_endpoints(live):
    resp = asyncio.run(share_api.share_calendar(TOKEN))
    assert resp.media_type == "text/calendar; charset=utf-8"
    body = resp.body.decode()
    assert "X-WR-CALNAME:TBDG Christmas Installs – M Crowd" in body
    assert "Lakewood – TBDG Christmas install" in unfolded(body)
    assert "Smith Home" not in body
    assert resp.headers["x-robots-tag"].startswith("noindex")

    resp = asyncio.run(share_api.share_csv(TOKEN))
    assert resp.media_type.startswith("text/csv")
    assert "Lake Highlands" in resp.body.decode() and "Smith Home" not in resp.body.decode()


@pytest.mark.parametrize("token", ["", "short", "B" * 43, "A" * 42 + "!", "../" + "A" * 40])
def test_unknown_or_malformed_tokens_404(live, token):
    for handler in (share_api.share_calendar, share_api.share_csv):
        with pytest.raises(HTTPException) as e:
            asyncio.run(handler(token))
        assert e.value.status_code == 404


def test_revoked_link_404s(live):
    assert asyncio.run(share_api.share_calendar(TOKEN)).status_code == 200
    live[TOKEN]["revoked"] = True
    for handler in (share_api.share_calendar, share_api.share_csv):
        with pytest.raises(HTTPException) as e:
            asyncio.run(handler(TOKEN))
        assert e.value.status_code == 404


def test_revoked_flag_is_checked_even_if_the_query_returned_it(live, fake_db):
    fake_db.on("FROM ll_app.client_share_links WHERE token",
               lambda sql, t: {**LINK, "revoked": True}, method="fetchrow")
    with pytest.raises(HTTPException) as e:
        asyncio.run(share_api.share_calendar(TOKEN))
    assert e.value.status_code == 404


def test_public_router_is_reachable_without_sign_in_but_admin_is_not():
    import main

    assert main.is_auth_disabled("client_share")
    assert not main.is_auth_disabled("client_share_links") or main.AUTH_DISABLED
    assert links_api.MIN_ROLE == "super_admin"
    for route in links_api.router.routes:
        assert route.dependencies, f"{route.path} must check super_admin itself"


# ---------- admin ----------

def row(**over):
    r = {"id": 3, "token": TOKEN, "label": "M Crowd", "name_prefix": "M Crowd ", "client_ids": [],
         "strip_prefix": "M Crowd ", "revoked": False, "revoked_at": None,
         "created_by": "owner@example.com", "created_at": None}
    r.update(over)
    return r


def test_create_makes_a_long_random_token(fake_db, fake_user):
    seen = {}

    def insert(sql, token, label, prefix, ids, strip, by):
        seen.update(token=token, label=label, prefix=prefix, strip=strip)
        return row(token=token)

    fake_db.on("INSERT INTO ll_app.client_share_links", insert, method="fetchrow")
    out = asyncio.run(links_api.create_share_link(
        links_api.ShareLinkIn(label=" M  Crowd ", name_prefix="M Crowd ", strip_prefix="M Crowd "), fake_user))
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", seen["token"])          # 256 bits
    assert seen["label"] == "M Crowd" and seen["prefix"] == "M Crowd " and seen["strip"] == "M Crowd "
    assert out.calendar_path == f"/api/share/{seen['token']}/calendar.ics"
    assert out.csv_path == f"/api/share/{seen['token']}/schedule.csv"
    assert share_api.TOKEN_RE.match(seen["token"])


@pytest.mark.parametrize("body", [
    {"label": "x"},                                  # no rule at all
    {"label": "x", "name_prefix": "M "},             # a prefix that sweeps in everyone
    {"label": "   ", "name_prefix": "M Crowd "},
])
def test_create_refuses_rules_that_match_nothing_or_everything(body):
    with pytest.raises(HTTPException) as e:
        links_api.validate(links_api.ShareLinkIn(**body))
    assert e.value.status_code == 422


def test_list_hides_revoked_links_urls(fake_db):
    fake_db.on_fetch("FROM ll_app.client_share_links ORDER BY", [row(), row(id=2, token="B" * 43, revoked=True)])
    out = asyncio.run(links_api.list_share_links())
    assert out[0].calendar_path and out[1].calendar_path is None and out[1].csv_path is None


def test_revoke(fake_db, fake_user):
    fake_db.on("UPDATE ll_app.client_share_links SET revoked = true",
               lambda sql, link_id, by: row(id=link_id, revoked=True), method="fetchrow")
    out = asyncio.run(links_api.revoke_share_link(3, fake_user))
    assert out.revoked and out.calendar_path is None
    fake_db.on_fetchrow("UPDATE ll_app.client_share_links SET revoked = true", None)
    with pytest.raises(HTTPException) as e:
        asyncio.run(links_api.revoke_share_link(99, fake_user))
    assert e.value.status_code == 404


def test_over_http_feed_needs_no_sign_in_and_admin_does(live):
    import contextlib
    import io as _io

    with contextlib.redirect_stdout(_io.StringIO()):
        import main
    from fastapi.testclient import TestClient

    c = TestClient(main.app)
    ok = c.get(f"/api/share/{TOKEN}/calendar.ics")
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/calendar")
    assert c.get(f"/api/share/{TOKEN}/schedule.csv").status_code == 200
    assert c.get(f"/api/share/{'B' * 43}/calendar.ics").status_code == 404
    live[TOKEN]["revoked"] = True
    assert c.get(f"/api/share/{TOKEN}/calendar.ics").status_code == 404
    if not main.AUTH_DISABLED:
        assert c.get("/api/client-share-links").status_code in (401, 403)
        assert c.post("/api/client-share-links", json={"label": "x", "name_prefix": "M Crowd "}).status_code in (401, 403)


def test_times_round_to_the_nearest_quarter_hour_ties_up():
    assert [cs.round_quarter(m) for m in (0, 7, 7.5, 8, 22.4, 22.5, 1432.5, 1446)] == [0, 0, 15, 15, 15, 30, 1440, 1440]


def test_rounded_visit_keeps_at_least_fifteen_minutes_and_rolls_past_midnight():
    payload = {**PAYLOAD, "clients": {**PAYLOAD["clients"], "11": {**PAYLOAD["clients"]["11"], "h26": 0.05}}}
    state = {**STATE, "timeline": {**STATE["timeline"],
             MON: {"start": 1380, "stops": [{"row": 10, "start": 1380, "end": 1590},
                                            {"row": 11, "start": 1433, "end": 1436}]}}}
    v = {x.location: x for x in cs.visits(schedule_board.resolve("2026", payload, state), RULE)}
    assert (v["Lakewood"].start, v["Lakewood"].end) == (1440, 1455)
    ics = unfolded(cs.build_ics("M Crowd", [v["Lakewood"]]))
    assert "DTSTART;TZID=America/Chicago:20261103T000000" in ics
    assert "DTEND;TZID=America/Chicago:20261103T001500" in ics
    assert cs.csv_rows([v["Lakewood"]])[0][3:5] == ("12:00 AM", "12:15 AM")
