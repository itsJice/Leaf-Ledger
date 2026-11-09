"""Value pins for app.libs.install_times: typed-time parsing, the midnight
rollover and the report rollups. The frontend twin
(frontend/src/utils/installTimes.ts) is pinned to the same values."""

from datetime import datetime

import pytest

from app.libs import install_times as T


@pytest.mark.parametrize("text,night,want", [
    ("10:15p", False, "10:15 PM"),
    ("10:15P", True, "10:15 PM"),
    ("1:30a", True, "1:30 AM"),
    ("1030pm", False, "10:30 PM"),
    ("1030 pm", True, "10:30 PM"),
    ("10:15 PM", False, "10:15 PM"),
    ("10:15 p.m.", False, "10:15 PM"),
    ("9:00 a.m.", False, "9:00 AM"),
    ("10p", False, "10:00 PM"),
    ("12a", False, "12:00 AM"),
    ("12p", True, "12:00 PM"),
    ("noon", True, "12:00 PM"),
    ("midnight", False, "12:00 AM"),
    ("22:15", False, "10:15 PM"),
    ("0015", False, "12:15 AM"),
    ("09:30", True, "9:30 AM"),
    ("10.15p", False, "10:15 PM"),
    # No am/pm on a DAY shift: 7..11 morning, 12 noon, 1..6 afternoon.
    ("8", False, "8:00 AM"),
    ("830", False, "8:30 AM"),
    ("12:30", False, "12:30 PM"),
    ("3", False, "3:00 PM"),
    ("6:45", False, "6:45 PM"),
    # No am/pm on a NIGHT shift: 6..11 evening, 12 midnight, 1..5 morning.
    ("1030", True, "10:30 PM"),
    ("11", True, "11:00 PM"),
    ("12:20", True, "12:20 AM"),
    ("130", True, "1:30 AM"),
    ("5:15", True, "5:15 AM"),
])
def test_parse_clock(text, night, want):
    assert T.fmt_clock(T.parse_clock(text, night=night)) == want


@pytest.mark.parametrize("text", ["", "   ", None])
def test_blank_is_none(text):
    assert T.parse_clock(text) is None


@pytest.mark.parametrize("text", ["abc", "25:00", "10:75p", "13p", "0a", "10:15x", "1:2", "12345"])
def test_unreadable_times_raise_a_friendly_error(text):
    with pytest.raises(T.TimeParseError) as exc:
        T.parse_clock(text)
    assert "—" not in str(exc.value)  # no em dashes in anything staff read


def test_fmt_clock():
    assert T.fmt_clock(0) == "12:00 AM"
    assert T.fmt_clock(12 * 60) == "12:00 PM"
    assert T.fmt_clock(22 * 60 + 15) == "10:15 PM"
    assert T.fmt_clock(None) == ""


def _hm(ts):
    return ts.strftime("%m/%d %H:%M")


def test_leave_before_arrive_rolls_to_the_next_day():
    e = T.build_entry("2026-11-02", "10:15p", "12:30a", night=True)
    assert (_hm(e.arrive_at), _hm(e.depart_at), e.hours) == ("11/02 22:15", "11/03 00:30", 2.25)


def test_night_arrival_after_midnight_is_the_next_morning():
    # Mon 11/2 crew-day, arrived 2:50 AM: that's Tuesday morning.
    e = T.build_entry("2026-11-02", "2:50a", "5:22a", night=True)
    assert (_hm(e.arrive_at), _hm(e.depart_at), e.hours) == ("11/03 02:50", "11/03 05:22", 2.53)


def test_day_shift_same_day_and_rollover():
    e = T.build_entry("2026-11-19", "8:30", "1:15", night=False)
    assert (_hm(e.arrive_at), _hm(e.depart_at), e.hours) == ("11/19 08:30", "11/19 13:15", 4.75)
    e = T.build_entry("2026-11-19", "8p", "1a", night=False)
    assert (_hm(e.depart_at), e.hours) == ("11/20 01:00", 5.0)


def test_equal_times_mean_a_full_day_not_zero():
    e = T.build_entry("2026-11-19", "9a", "9a", night=False)
    assert e.hours == 24.0
    assert e.warnings and "am/pm" in e.warnings[0]


def test_only_one_time_is_kept_without_hours():
    e = T.build_entry("2026-11-02", "10:15p", "", night=True)
    assert e.depart_at is None and e.hours is None
    e = T.build_entry("2026-11-02", "", "1a", night=True)
    assert e.arrive_at is None and _hm(e.depart_at) == "11/03 01:00"


def test_dst_night_counts_the_real_hours():
    # 11/1/2026 2 AM CDT -> 1 AM CST: 11 PM to 3 AM is five real hours.
    assert T.build_entry("2026-10-31", "11p", "3a", night=True).hours == 5.0


def test_past_the_dallas_hard_stop_warns():
    e = T.build_entry("2026-11-03", "11:46p", "8:30a", night=True)
    assert any("8 AM" in w for w in e.warnings)
    assert not T.build_entry("2026-11-03", "11:46p", "5:15a", night=True).warnings


def test_clock_of_round_trips():
    e = T.build_entry("2026-11-02", "10:15p", "1:30a", night=True)
    assert T.fmt_clock(T.clock_of(e.depart_at)) == "1:30 AM"
    assert T.clock_of(None) is None


def test_difference_never_invents_zero():
    assert T.difference(2.0, 2.5) == {"diffHours": 0.5, "diffPct": 25.0}
    assert T.difference(None, 2.5) == {"diffHours": None, "diffPct": None}
    assert T.difference(2.0, None) == {"diffHours": None, "diffPct": None}
    assert T.difference(0, 1.0) == {"diffHours": 1.0, "diffPct": None}


def test_kind_and_job_type():
    assert T.kind_for_date("2026-12-25", "2026") == "install"
    assert T.kind_for_date("2026-12-26", "2026") == "takedown"
    assert T.kind_for_date("2027-01-03", "2026") == "takedown"
    assert T.job_type_of({"cat": "M Crowd", "bus": "Business"}) == "restaurant"
    assert T.job_type_of({"name": "M Crowd Uptown"}) == "restaurant"
    assert T.job_type_of({"bus": "Business"}) == "commercial"
    assert T.job_type_of({"bus": "Residence"}) == "residential"
    assert T.job_type_of({}) is None


def _r(**kw):
    base = {"season": "2026", "kind": "install", "clientId": 1, "clientName": "A", "crewLead": "Ana",
            "jobType": "residential", "night": False, "estHours": 2.0, "actualHours": 3.0}
    return {**base, **kw}


def test_summarize_counts_only_compared_visits():
    rows = [
        _r(),
        _r(clientId=2, clientName="B", actualHours=None),  # not entered: left out of totals
        _r(clientId=3, clientName="M Crowd X", crewLead="Chris", jobType="restaurant", night=True,
           estHours=4.0, actualHours=3.0),
        _r(season="2025", estHours=2.5, actualHours=2.0),
    ]
    s = T.summarize(rows[:3])
    ana = next(x for x in s["byLead"] if x["crewLead"] == "Ana")
    assert (ana["visits"], ana["compared"], ana["missing"], ana["estHours"], ana["actualHours"]) == (2, 1, 1, 2.0, 3.0)
    assert (ana["diffHours"], ana["diffPct"]) == (1.0, 50.0)
    types = {x["type"]: x for x in s["byType"]}
    assert types["residential"]["visits"] == 2
    assert types["restaurant"]["compared"] == 1 and types["dallas_night"]["diffHours"] == -1.0
    assert types["commercial"]["visits"] == 0 and types["commercial"]["actualHours"] is None

    yoy = T.summarize(rows)["byClient"]
    a = next(c for c in yoy if c["clientId"] == 1)
    assert a["seasons"]["2025"]["actualHours"] == 2.0 and a["seasons"]["2026"]["actualHours"] == 3.0
    b = next(c for c in yoy if c["clientId"] == 2)
    assert b["seasons"]["2026"] == {"estHours": 2.0, "actualHours": None, "visits": 1, "missing": 1}


def test_entry_timestamps_are_central():
    e = T.build_entry("2026-11-19", "8a", "9a", night=False)
    assert e.arrive_at.utcoffset().total_seconds() == -6 * 3600
    assert isinstance(e.arrive_at, datetime)


@pytest.mark.parametrize("arrive, leave, night, want", [
    # The 11/9 Byler store stop: typed with no am/pm at all.
    ("10:59", "2:05", False, "2:05 PM"),
    ("2p", "7", False, "7:00 PM"),        # day rule alone would say 7 AM
    ("8", "12:30", False, "12:30 PM"),
    ("11", "11:30", False, "11:30 AM"),
    ("10:15", "1:30", True, "1:30 AM"),   # a Dallas night
    ("9", "11", True, "11:00 PM"),
    ("10:59", "2:05a", False, "2:05 AM"), # explicit am/pm wins
    ("10:59", "14:05", False, "2:05 PM"), # 24-hour taken as written
    ("", "2:05", False, "2:05 PM"),       # no Arrive: the shift rule
])
def test_leave_is_the_soonest_time_after_arrive(arrive, leave, night, want):
    a = T.parse_clock(arrive, night=night)
    assert T.fmt_clock(T.parse_leave(leave, a, night=night)) == want


def test_build_entry_uses_the_smart_leave():
    e = T.build_entry("2026-11-09", "10:59", "2:05", night=False)
    assert (_hm(e.arrive_at), _hm(e.depart_at), e.hours) == ("11/09 10:59", "11/09 14:05", 3.1)
    e = T.build_entry("2026-11-09", "2p", "7", night=False)
    assert (_hm(e.depart_at), e.hours) == ("11/09 19:00", 5.0)
