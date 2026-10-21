"""Dallas nights added after the build (state.dallasNights) and joint stops the
build didn't plan, read server-side the way the tool shows them
(schedule_board.derived_day_meta, the twin of refreshDerivedMeta() in
review_template.html). The calendar feed and the profit page read
board.day_meta, so a January Dallas takedown night has to start at 11 PM with
no "Arrive at branch" and no drive back, exactly like a November one.
"""
from app.libs import install_calendar as cal
from app.libs import schedule_board

NOV1 = "2026-11-02|Crew 1|0"
NOV2 = "2026-11-02|Crew 2|0"
NOV3 = "2026-11-02|Crew 3|0"
JAN1 = "2027-01-02|Crew 1|0"
JAN2 = "2027-01-02|Crew 2|0"
JAN3 = "2027-01-02|Crew 3|0"
HOU = "2026-12-01|Crew 1|0"

# Node 0 is the branch (far away); 1-3 are Dallas stops.
DURS = [
    [0, 14000, 14000, 14000],
    [14000, 0, 600, 900],
    [14000, 600, 0, 1200],
    [14000, 900, 1200, 0],
]
NIGHT_META = {"cat": "M Crowd", "anchored": False, "stacked": 1, "win": 450, "lunchMin": 0,
              "half": [], "joint": "", "startRow": None, "note": "built night",
              "winReason": "Mi Cocina night shift, 11pm-6:30am", "zones": ["Uptown"]}
PAYLOAD = {
    "depot": {"lat": 29.7, "lon": -95.4},
    "node": {"1": 1, "2": 2, "3": 3},
    "durs": DURS,
    "spec": {
        "version": "v1",
        "const": {"NIGHT": 450, "LUNCH": 40, "DAY_CAP": 600, "CREWS": ["Crew 1", "Crew 2", "Crew 3"]},
        "calendar": [
            {"date": "2026-11-02", "kind": "dallas_night"},
            {"date": "2026-12-01", "kind": "weekday"},
            {"date": "2027-01-02", "kind": "saturday", "optional": True},
        ],
        "dayMeta": {
            # Crew 3's built day is the 9-5 corporate install: not a night to copy.
            NOV3: {**NIGHT_META, "win": 480, "note": "daytime"},
            NOV1: {**NIGHT_META, "half": [1], "joint": "Crew 2", "startRow": 1},
            NOV2: {**NIGHT_META, "half": [1], "joint": "Crew 1", "startRow": 1},
        },
    },
    "clients": {
        "1": {"name": "M Crowd Lake Highlands", "h26": 7.0, "street": "1 A St"},
        "2": {"name": "M Crowd Lakewood", "h26": 2.0, "street": "2 B St"},
        "3": {"name": "M Crowd Uptown", "h26": 1.5, "street": "3 C St"},
    },
    "days": [
        {"id": NOV1, "date": "2026-11-02", "crew": "Crew 1", "stops": [1, 2]},
        {"id": NOV2, "date": "2026-11-02", "crew": "Crew 2", "stops": [1, 3]},
    ],
}
# The takedown visits: rows under the locations' own names, half the hours.
TAKEDOWNS = [
    {"row": 900010, "name": "M Crowd Lake Highlands", "hours": 3.5, "visitType": "Takedown", "street": "1 A St",
     "outRow": DURS[1], "inCol": [r[1] for r in DURS]},
    {"row": 900011, "name": "M Crowd Lakewood", "hours": 1.0, "visitType": "Takedown", "street": "2 B St",
     "outRow": DURS[2], "inCol": [r[2] for r in DURS]},
]


def state(**extra):
    return {"newClients": TAKEDOWNS,
            "placement": {"1": [NOV1, NOV2], "2": [NOV1], "3": [NOV2],
                          "900010": [JAN1, JAN2], "900011": [JAN1]},
            **extra}


def test_a_marked_january_night_gets_the_built_night_meta():
    b = schedule_board.resolve("2026", PAYLOAD, state(dallasNights=["2027-01-02"]))
    m = b.day_meta[JAN1]
    assert (m["win"], m["anchored"], m["lunchMin"], m["cat"]) == (450, False, 0, "M Crowd")
    # Only the joint wiring of THIS night, none of November's note or zones.
    assert m["half"] == [900010] and m["joint"] == "Crew 2" and m["startRow"] == 900010
    assert m["note"] == "" and m["zones"] == []
    assert b.day_meta[JAN2]["joint"] == "Crew 1"
    # Built days are untouched.
    assert b.day_meta[NOV1]["note"] == "built night"
    assert b.day_notes.get(JAN1) is None


def test_crew_without_a_built_night_copies_the_first_one_not_the_daytime_install():
    b = schedule_board.resolve("2026", PAYLOAD, state(dallasNights=["2027-01-02"],
                               placement={"3": [JAN3]}))
    assert b.day_meta[JAN3]["win"] == 450 and b.day_meta[JAN3]["anchored"] is False


def test_feed_runs_the_january_night_like_november():
    b = schedule_board.resolve("2026", PAYLOAD, state(dallasNights=["2027-01-02"]))
    tl = cal.day_timeline(b, b.days[JAN1])
    assert tl["start"] == 23 * 60 and tl["anchored"] is False and tl["back"] is None
    # Lake Highlands takedown is joint: 3.5h / 2 on each crew.
    first = tl["stops"][0]
    assert first["row"] == 900010 and first["end"] - first["start"] == 105
    summaries = [e["summary"] for e in cal.day_events(b, b.days[JAN1])]
    assert not any("Arrive at branch" in s or "Drive back" in s for s in summaries)


def test_unmarked_date_stays_a_houston_day_but_still_splits_a_joint_stop():
    b = schedule_board.resolve("2026", PAYLOAD, state())
    m = b.day_meta[JAN1]
    assert m["anchored"] is True and m["win"] == 600 and m["half"] == [900010]
    assert cal.day_timeline(b, b.days[JAN1])["start"] == 8 * 60 + 30
    # A day with no joint stop and no Dallas mark has no derived meta at all.
    b = schedule_board.resolve("2026", PAYLOAD, {"placement": {"2": [HOU]}})
    assert HOU not in b.day_meta


def test_junk_in_dallas_nights_is_ignored():
    assert schedule_board.dallas_dates(PAYLOAD["spec"], {"dallasNights": ["2027-01-02", 5, "Jan 3", None]}) \
        == {"2026-11-02", "2027-01-02"}
