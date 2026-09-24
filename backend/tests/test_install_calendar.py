"""The office's subscribed install calendar: timed events per crew-day, behind a URL secret."""

import asyncio

import pytest
from fastapi import HTTPException

from app.apis import install_calendar as feed_api
from app.libs import install_calendar as cal
from app.libs import schedule_board

DAY1 = "2026-11-14|Crew 1|0"
DAY3 = "2026-11-14|Crew 3|0"
NIGHT = "2026-11-15|Crew 2|0"

# Node 0 is the branch. Seconds: branch->10 is 20 min, 10->11 is 15, 11->branch is 10.
DURS = [
    [0, 1200, 600, 900, 300],
    [1200, 0, 900, 600, 600],
    [600, 900, 0, 1800, 600],
    [900, 600, 1800, 0, 600],
    [300, 600, 600, 600, 0],
]

PAYLOAD = {
    "depot": {"lat": 32.9, "lon": -96.8},
    "node": {"10": 1, "11": 2, "12": 3, "13": 4},
    "durs": DURS,
    "spec": {
        "version": "v1",
        "const": {"NIGHT": 450, "LUNCH": 40},
        "dayMeta": {
            DAY1: {"note": "Gate code 1234", "anchored": True, "stacked": 1, "win": 600},
            NIGHT: {"anchored": True, "stacked": 1, "win": 450},
        },
    },
    "clients": {
        "10": {"name": "Smith Home", "street": "1 Oak St", "city": "Dallas", "st": "TX", "zip": "75201",
               "phone": "555-0100", "h26": 2.5, "advice": "Side gate, dog in yard"},
        "11": {"name": "Jones, Office", "street": "2 Elm St", "city": "Dallas", "st": "TX", "zip": "75202",
               "h26": 1.0},
        "12": {"name": "Other Crew Client", "street": "3 Pine", "city": "Plano", "st": "TX", "zip": "75023",
               "h26": 3.0},
        "13": {"name": "Mi Cocina", "street": "4 Main", "city": "Dallas", "st": "TX", "zip": "75201",
               "h26": 5.0},
    },
    "days": [
        {"id": DAY1, "date": "2026-11-14", "crew": "Crew 1", "stops": [10, 11]},
        {"id": DAY3, "date": "2026-11-14", "crew": "Crew 3", "stops": [12]},
        {"id": NIGHT, "date": "2026-11-15", "crew": "Crew 2", "stops": [13]},
    ],
}
STATE = {
    "roster": [
        {"id": "p1", "first": "Ana", "last": "Lead", "title": "Lead"},
        {"id": "p2", "first": "Bo", "last": "Helper", "title": "General Installer"},
    ],
    "staffing": {DAY1: ["p1", "p2"]},
}


def board(state=STATE):
    return schedule_board.resolve("2026", PAYLOAD, state)


def test_day_is_branch_arrival_then_alternating_drives_and_installs():
    b = board()
    evs = cal.day_events(b, b.days[DAY1])
    got = [(e["summary"], e["start"], e["end"]) for e in evs]
    assert got == [
        ("🔴 Crew 1 · Arrive at branch", 480, 510),                      # 8:00-8:30
        ("🔴 Crew 1 · Drive to Smith Home (20 min)", 510, 530),
        ("🔴 Crew 1 · Smith Home (2 hr 30 min)", 530, 680),
        ("🔴 Crew 1 · Drive to Jones, Office (15 min)", 680, 695),
        ("🔴 Crew 1 · Jones, Office (1 hr)", 695, 755),
        ("🔴 Crew 1 · Drive back to branch (10 min)", 755, 765),
    ]
    stop = evs[2]
    assert stop["location"] == "1 Oak St, Dallas, TX 75201"
    assert "Side gate, dog in yard" in stop["description"]
    assert "Ana Lead (lead), Bo Helper" in stop["description"]
    assert "Gate code 1234" in stop["description"]


def test_crew_labels_are_positional_like_the_tool():
    # Crew 3 is the second crew out on 11/14, so the tool calls it "Crew 2".
    b = board()
    assert cal.day_events(b, b.days[DAY3])[0]["summary"].startswith("🟢 Crew 2 · ")


def test_night_window_starts_at_eleven_and_runs_past_midnight():
    b = board()
    evs = cal.day_events(b, b.days[NIGHT])
    assert evs[0]["start"] == 23 * 60 - 30
    ics = cal.build_ics(b)
    assert "DTSTART;TZID=America/Chicago:20261116T" in ics   # install ends the next morning


def test_stacked_and_half_rows_shorten_the_install_like_effH():
    payload = {**PAYLOAD, "spec": {**PAYLOAD["spec"], "dayMeta": {
        DAY1: {"stacked": 2, "half": [10], "win": 600}}}}
    b = schedule_board.resolve("2026", payload, STATE)
    stops = cal.day_timeline(b, b.days[DAY1])["stops"]
    assert [s["end"] - s["start"] for s in stops] == [37.5, 30.0]


def test_times_saved_by_the_tool_win_over_rebuilding():
    state = {**STATE, "timeline": {DAY1: {"start": 510, "back": 12,
             "stops": [{"row": 11, "start": 540, "end": 600}, {"row": 10, "start": 610, "end": 760}]}}}
    b = board(state)
    evs = cal.day_events(b, b.days[DAY1])
    assert [e["summary"] for e in evs][2] == "🔴 Crew 1 · Jones, Office (1 hr)"
    assert evs[-1]["end"] == 772


def test_stale_saved_times_for_a_different_stop_set_are_ignored():
    state = {**STATE, "timeline": {DAY1: {"start": 510, "stops": [{"row": 10, "start": 540, "end": 600}]}}}
    b = board(state)
    assert len(cal.day_timeline(b, b.days[DAY1])["stops"]) == 2


def test_client_added_in_the_tool_uses_its_saved_osrm_row_and_hours():
    state = {**STATE,
             "newClients": [{"row": 99, "name": "Callback", "lat": 32.9, "lon": -96.8, "hours": 1.5,
                             "outRow": [60, 60, 60, 60, 60], "inCol": [120, 120, 120, 120, 120]}],
             "placement": {"10": [DAY1], "99": [DAY1]}, "manualOrder": {DAY1: [10, 99]}}
    b = board(state)
    tl = cal.day_timeline(b, b.days[DAY1])
    assert tl["stops"][1]["start"] - tl["stops"][0]["end"] == 2      # inCol from node 1
    assert tl["stops"][1]["end"] - tl["stops"][1]["start"] == 90
    assert tl["back"] == 1                                             # outRow to the branch


def test_one_feed_has_every_crew_marked_by_emoji_and_is_well_formed():
    b = board()
    ics = cal.build_ics(b)
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "SUMMARY:🔴 Crew 1 · Jones\\, Office (1 hr)" in ics
    assert "SUMMARY:🟢 Crew 2 · Other Crew Client (3 hr)" in ics
    assert ics.count("BEGIN:VEVENT") == 6 + 4 + 4
    uids = [l for l in ics.split("\r\n") if l.startswith("UID:")]
    assert len(uids) == len(set(uids))
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n"))


def test_feed_needs_the_token_and_404s_without_it(monkeypatch):
    b = board()

    async def fake_load(*_, **__):
        return b

    monkeypatch.setattr(schedule_board, "load_board", fake_load)
    run = asyncio.run

    monkeypatch.delenv("INSTALL_CALENDAR_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e:
        run(feed_api.calendar_feed(token=""))
    assert e.value.status_code == 404

    monkeypatch.setenv("INSTALL_CALENDAR_TOKEN", "s3cret")
    with pytest.raises(HTTPException) as e:
        run(feed_api.calendar_feed(token="wrong"))
    assert e.value.status_code == 404

    resp = run(feed_api.calendar_feed(token="s3cret"))
    assert resp.media_type.startswith("text/calendar")
    assert b"Smith Home" in resp.body


def test_only_the_calendar_router_skips_sign_in():
    import main

    assert main.PUBLIC_ROUTERS == {"install_calendar"}
    assert main.is_auth_disabled("install_calendar")
    assert not main.is_auth_disabled("install_schedule") or main.AUTH_DISABLED
