"""common.hours_between -- last season's real install hours off the start/end
cells, since the sheet's own hours formula carries no saved value."""
import datetime

import common as prep


def test_hours_between_times_and_text():
    assert prep.hours_between(datetime.time(9, 45), datetime.time(13, 50)) == 4.08
    assert prep.hours_between("09:45", "12:15") == 2.5
    assert prep.hours_between("10:00 PM", "1:00 AM") == 3.0      # wraps past midnight
    assert prep.hours_between(datetime.datetime(2025, 12, 1, 22, 0), datetime.time(1, 0)) == 3.0
    assert prep.hours_between(None, "12:00") is None
    assert prep.hours_between("Arrive 3:30", "12:00") is None     # a note, not a time
    assert prep.hours_between("12:00", "12:00") is None           # same moment reads as unknown
