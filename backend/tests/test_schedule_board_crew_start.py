"""Start times set by hand per crew-day (state.crewStart, see crewStart in
scheduler/review_template.html), read server-side so the calendar feed's
fallback timeline follows them when no saved timeline matches. A start at
6:00 PM or later runs like a Dallas night (no depot legs, no lunch); a
daytime one only moves the clock (office, 11/17/2026).
"""
from app.libs import install_calendar as cal
from app.libs import schedule_board

from tests.test_schedule_board_dallas_nights import HOU, NOV1, PAYLOAD, state


def board(**extra):
    st = state(**extra)
    st["timeline"] = {}
    st["placement"] = {**st["placement"], "2": [NOV1, HOU]}
    return schedule_board.resolve("2026", PAYLOAD, st)


def test_norm_keeps_whole_minutes_in_range():
    assert schedule_board.norm_crew_start(
        {"a": 1380, "b": "1320", "c": 60, "d": True, "e": "x", "f": 1440, 3: 600}) == {"a": 1380, "b": 1320}
    assert schedule_board.norm_crew_start(None) == {}


def test_evening_start_on_a_houston_day_runs_as_a_night():
    b = board(crewStart={HOU: 1380, "gone|Crew 9|0": 1320})
    assert b.crew_start == {HOU: 1380}
    m = b.day_meta[HOU]
    assert (m["startMin"], m["anchored"], m["lunchMin"]) == (1380, False, 0)
    tl = cal.day_timeline(b, b.days[HOU])
    assert tl["start"] == 1380 and tl["anchored"] is False and tl["back"] is None
    assert tl["stops"][0]["start"] == 1380


def test_daytime_start_only_moves_the_clock():
    b = board(crewStart={HOU: 600})
    tl = cal.day_timeline(b, b.days[HOU])
    assert tl["start"] == 600 and tl["anchored"] is True
    assert tl["stops"][0]["start"] > 600


def test_dallas_night_at_10_pm_and_untouched_days_unchanged():
    plain = board()
    b = board(crewStart={NOV1: 1320})
    assert cal.day_timeline(b, b.days[NOV1])["start"] == 1320
    assert cal.day_timeline(plain, plain.days[NOV1])["start"] == 23 * 60
    assert cal.day_timeline(b, b.days[HOU]) == cal.day_timeline(plain, plain.days[HOU])
