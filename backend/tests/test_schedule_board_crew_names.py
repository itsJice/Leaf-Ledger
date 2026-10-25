"""Crew names staff gave a shift on the Staffing tab (state.crewNames, see
crewNames in scheduler/review_template.html), read server-side: the calendar
feed, the lead pages, crew-day profit and the Changes feed name the crew the
way the tool does ("Lesly's crew (Crew 1)"). Each Dallas night is its own
shift (10/24/2026); a name saved under a Dallas run's old week key still
covers every night of that run until a night gets its own.
"""
import copy

from app.apis import schedule_changes as api
from app.libs import install_calendar as cal
from app.libs import schedule_board
from app.libs import schedule_changes as sc

from tests.test_schedule_board_dallas_nights import HOU, JAN1, JAN2, NOV1, NOV2, PAYLOAD, state


def board(**extra):
    st = state(**extra)
    st["placement"] = {**st["placement"], "2": [NOV1, HOU]}
    return schedule_board.resolve("2026", PAYLOAD, st)


def test_houston_day_name_is_keyed_by_its_day_id():
    b = board(crewNames={HOU: "  Team   A  "})
    assert b.crew_names == {HOU: "Team A"}
    assert b.shift_key(b.days[HOU]) == HOU
    assert b.crew_title(b.days[HOU]) == "Team A (Crew 1)"
    assert b.crew_title(b.days[NOV1]) == "Crew 1"


def test_old_dallas_week_name_covers_every_night_of_its_run():
    b = board(dallasNights=["2027-01-02", "2027-01-03"],
              crewNames={"dallas|2027-01-02|Crew 1": "Night A", "dallas|2026-11-02|Crew 2": "Nov B"})
    assert b.shift_key(b.days[JAN1]) == JAN1
    assert b.dallas_week_key(b.days[JAN1]) == "dallas|2027-01-02|Crew 1"
    assert b.dallas_week_key(b.days[HOU]) is None
    assert b.crew_title(b.days[JAN1]) == "Night A (Crew 1)"
    assert b.crew_title(b.days[JAN2]) == "Crew 2"
    assert b.crew_title(b.days[NOV2]) == "Nov B (Crew 2)"
    assert schedule_board.dallas_run_start("2027-01-03", {"2027-01-02", "2027-01-03"}) == "2027-01-02"


def test_a_dallas_night_name_wins_over_the_old_week_name():
    b = board(crewNames={"dallas|2026-11-02|Crew 1": "Week A", NOV1: "Mon A"})
    assert b.shift_key(b.days[NOV1]) == NOV1
    assert b.crew_title(b.days[NOV1]) == "Mon A (Crew 1)"
    b2 = board(crewNames={NOV2: "Mon B"})
    assert b2.crew_title(b2.days[NOV2]) == "Mon B (Crew 2)"


def test_names_are_normalized_and_junk_dropped():
    raw = {"a": "x" * 60, "b": "   ", "c": 5, 7: "seven", "d": " ok "}
    assert schedule_board.norm_crew_names(raw) == {"a": "x" * 40, "d": "ok"}
    assert schedule_board.norm_crew_names(None) == {}
    assert schedule_board.norm_crew_names(["a"]) == {}


def test_calendar_feed_keeps_the_emoji_and_adds_the_name():
    b = board(crewNames={HOU: "Team A"})
    summaries = [e["summary"] for e in cal.day_events(b, b.days[HOU])]
    assert summaries and all(s.startswith("🔴 Team A (Crew 1) · ") for s in summaries)
    plain = board()
    assert all(e["summary"].startswith("🔴 Crew 1 · ") for e in cal.day_events(plain, plain.days[HOU]))


def test_changes_feed_names_the_crew_but_a_rename_is_not_a_crew_switch():
    b = board(crewNames={HOU: "Team A"})
    ctx = api.context_for(b)
    base = state()
    base["placement"] = {**base["placement"], "2": [NOV1, HOU]}
    named = {**copy.deepcopy(base), "crewNames": {HOU: "Team A"}}
    # Renaming alone changes nothing on the schedule.
    assert sc.diff(base, named, ctx) == []
    approved = {**copy.deepcopy(named), "approved": [HOU]}
    assert [e["text"] for e in sc.diff(named, approved, ctx)] == ["Team A (Crew 1) approved for Tue 12/1"]
    view = sc.view_of({**named, "dallasNights": ["2027-01-02"],
                       "crewNames": {"dallas|2027-01-02|Crew 1": "Night A"}}, ctx)
    assert view.title(JAN1) == "Night A (Crew 1)"
    # a per-night name (the key the tool writes now) wins
    view2 = sc.view_of({**named, "dallasNights": ["2027-01-02"],
                        "crewNames": {"dallas|2027-01-02|Crew 1": "Night A", JAN1: "Sat A"}}, ctx)
    assert view2.title(JAN1) == "Sat A (Crew 1)"
    assert view.label(JAN1) == "Crew 1"
