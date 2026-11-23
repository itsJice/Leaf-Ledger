"""Return trips linked to their client (11/2026).

Nicole: "every time I add a new install for a callback, it is adding an
entirely new client". The user: "When we make return trips to clients, it's
making duplicates in the system of their client card." A return trip is now
an added stop under the client's own name (visit type Callback, ``of`` = the
client's row, ``returnReason`` = why), like a takedown row: it finds the
client's card by name, is titled "<Client> - Return trip (Fix)", shows on the
client's page under the install, and never speaks for the main install."""
from tests.test_install_panel import DAY1, PAYLOAD, STATE

from app.libs import install_calendar as cal
from app.libs import install_summary
from app.libs import schedule_board as sb
from app.libs.schedule_changes import names_from_state

MAIN = {"row": 36, "name": "Sample, Jane", "visitType": "Standard"}
TRIP = {"row": 900050, "name": "Sample, Jane", "visitType": "Callback", "of": 36, "returnReason": "fix"}
OLD = {"row": 900039, "name": "Jane Sample", "visitType": "Callback"}


def test_a_return_trip_is_titled_and_is_an_extra_visit():
    assert sb.visit_name("Sample, Jane", TRIP) == "Sample, Jane - Return trip (Fix)"
    assert sb.visit_name("Sample, Jane", {**TRIP, "returnReason": None}) == "Sample, Jane - Return trip (Callback)"
    assert sb.visit_name("Sample, Jane", {**TRIP, "returnReason": "bought_more"}) == "Sample, Jane - Return trip (Bought more)"
    assert sb.visit_name("Sample, Jane - Return trip", TRIP) == "Sample, Jane - Return trip"
    # An older callback typed in as a new client keeps its plain wording.
    assert sb.visit_name("Jane Sample", OLD) == "Jane Sample - Callback"
    assert sb.visit_name("Sample, Jane", MAIN) == "Sample, Jane"
    assert sb.is_callback(TRIP) and sb.is_return_trip(TRIP) and not sb.is_return_trip(OLD)
    assert sb.is_extra_visit(TRIP) and sb.is_extra_visit({"visitType": "Takedown"})
    assert not sb.is_extra_visit(MAIN) and not sb.is_extra_visit({"visitType": "Reinstall"})


def test_install_changes_names_the_return_trip_row():
    clients, _ = names_from_state({"newClients": [TRIP], "moves": [{"row": 36, "name": "Sample, Jane"}]})
    assert clients == {36: "Sample, Jane", 900050: "Sample, Jane - Return trip (Fix)"}


def test_storing_is_about_the_main_install_not_the_return_trip():
    board = sb.Board(season="2026", version=None, clients={36: MAIN, 900050: TRIP})
    assert cal.storing_rows(board, [("Sample, Jane", True)]) == {36}


def test_the_board_resolver_keeps_the_link():
    payload = {"clients": {"36": MAIN}, "days": [], "spec": {}}
    board = sb.resolve("2026", payload, {"newClients": [{**TRIP, "notes": "Reattach the garland"}]})
    assert board.clients[900050]["of"] == 36 and board.clients[900050]["returnReason"] == "fix"
    assert board.clients[900050]["advice"] == "Reattach the garland"


def test_the_clients_page_lists_return_trips_under_the_install():
    day = "2026-11-25|Crew 2|0"
    payload = {**PAYLOAD, "days": [*PAYLOAD["days"], {"id": day, "date": "2026-11-25", "crew": "Crew 2", "stops": []}]}
    trip = {"row": 900050, "name": "Allums, Jennifer", "visitType": "Callback", "of": 10, "returnReason": "bought_more",
            "lat": 1, "lon": 1, "hours": 1}
    old = {"row": 900051, "name": "Jennifer Allums", "visitType": "Callback", "lat": 1, "lon": 1, "hours": 1}
    state = {**STATE, "newClients": [trip, old],
             "placement": {**STATE["placement"], "900050": [day], "900051": [day]}}
    board = sb.resolve("2026", payload, state)
    jen = {"id": 1, "name": "Allums, Jennifer", "sheet_name": None, "former_names": []}
    out = install_summary.summarize(board, jen, {}, [], season="2026")
    # The install stays the client's date; the trips are listed, not the install.
    assert out["board_date"] == "2026-11-19" and out["crews"][0]["day_id"] == DAY1
    assert [(t["date"], t["reason"], t["row"]) for t in out["return_trips"]] == [
        ("2026-11-25", "Bought more", 900050), ("2026-11-25", "Callback", 900051)]
