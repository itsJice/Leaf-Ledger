"""Install hours staff edited on the board (state.hoursOverride), read
server-side the way the tool shows them: the spreadsheet's h26 is baked into
the build, so the edit rides in shared state and schedule_board.resolve puts
it onto the client. The calendar feed, the lead page and the profit pages
all read board.clients. An added stop (newClients) keeps its own hours.
"""
from app.libs import schedule_board

DAY = "2026-11-04|Crew 1|0"
PAYLOAD = {
    "spec": {"version": "v1", "const": {"NIGHT": 450, "LUNCH": 40, "DAY_CAP": 600}, "calendar": [], "dayMeta": {}},
    "clients": {
        "63": {"name": "M Crowd Lake Highlands", "h26": 7.29, "basis": "est x0.81"},
        "65": {"name": "M Crowd Lakewood", "h26": 2.43},
    },
    "days": [{"id": DAY, "date": "2026-11-04", "crew": "Crew 1", "stops": [63, 65]}],
}
TAKEDOWN = {"row": 900015, "name": "M Crowd Lake Highlands", "hours": 2, "visitType": "Takedown"}


def test_override_reaches_the_board_and_leaves_the_build_alone():
    state = {"hoursOverride": {"63": 4, "900015": 9, "65": "junk", "99": 3}, "newClients": [TAKEDOWN]}
    b = schedule_board.resolve("2026", PAYLOAD, state)
    assert b.clients[63]["h26"] == 4 and b.clients[63]["basis"] == "staff entry"
    assert b.clients[65]["h26"] == 2.43
    # The added takedown stop keeps its own stored hours.
    assert b.clients[900015]["hours"] == 2 and "h26" not in b.clients[900015]
    assert 99 not in b.clients
    # The build's own table is never mutated.
    assert PAYLOAD["clients"]["63"]["h26"] == 7.29


def test_no_override_is_the_spreadsheet_value():
    for state in ({}, {"hoursOverride": None}, {"hoursOverride": {"63": 0}}, {"hoursOverride": {"63": 30}}):
        assert schedule_board.resolve("2026", PAYLOAD, state).clients[63]["h26"] == 7.29
