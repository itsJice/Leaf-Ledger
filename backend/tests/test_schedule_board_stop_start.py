"""A stop's set start (state.stopStart, Comments #35) in the server's
fallback timeline (the calendar feed when no saved timeline matches)."""
from app.libs import install_calendar as cal
from app.libs import schedule_board

from tests.test_schedule_board_dallas_nights import HOU, NOV1, PAYLOAD, state


def board(**extra):
    st = state(**extra)
    st["timeline"] = {}
    st["placement"] = {**st["placement"], "2": [NOV1, HOU]}
    return schedule_board.resolve("2026", PAYLOAD, st)


def test_norm_and_only_stops_on_that_day():
    assert schedule_board.norm_stop_start({"a#1": 120, "b": 5, "c#2": 1440, "d#3": True}) == {"a#1": 120}
    b = board(stopStart={f"{HOU}#2": 900, f"{HOU}#999": 900})
    assert b.stop_start == {f"{HOU}#2": 900}


def test_a_stop_waits_for_its_set_time_and_a_night_time_is_next_morning():
    plain = board()
    row = plain.days[NOV1]["stops"][-1]
    b = board(stopStart={f"{NOV1}#{row}": 240})
    stop = [s for s in cal.day_timeline(b, b.days[NOV1])["stops"] if s["row"] == row][0]
    assert stop["start"] == 1680
    before = [s for s in cal.day_timeline(plain, plain.days[NOV1])["stops"] if s["row"] == row][0]
    assert before["start"] < stop["start"]
