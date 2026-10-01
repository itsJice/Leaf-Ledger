"""A past season rebuilt from real clock times, real crews and invoices."""

import pytest

from app.libs import season_history as sh
from tests.test_crew_day_profit import card


def client(cid, name, **detail):
    return {"id": cid, "name": name, "sheet_name": name, "former_names": [], "zip": detail.pop("zip", "77008"),
            "activity": [{"kind": "christmas_install", "season": "2025", "detail": detail}]}


@pytest.mark.parametrize("lines,expect", [
    (["Lesly Crew", "Alberto", "Evlyn"], ("Lesly", ["Lesly", "Alberto", "Evlyn"], None)),
    (["Crew A (6)"], ("Crew A", [], 6)),
    (["Chris -Monday", "Woodlands CC", "Alberto"], ("Chris", ["Chris", "Alberto"], None)),
    (["Lesly-Monday", "Carlton Woods CC", "Rolando"], ("Lesly", ["Lesly", "Rolando"], None)),
    (["Crew A", "Alberto - Tuesday", "Niurkita"], ("Crew A", ["Alberto", "Niurkita"], None)),
    (["Chris Wenz"], ("Chris", ["Chris Wenz"], None)),
    ([], ("", [], None)),
])
def test_crew_label(lines, expect):
    assert sh.crew_label(lines, None) == expect


def test_daytime_reads_typed_times_as_a_working_day():
    assert sh.daytime(2 * 60 + 15, 3 * 60 + 15) == (14 * 60 + 15, 15 * 60 + 15)     # "02:15" is 2:15 pm
    assert sh.daytime(12 * 60 + 33, 1 * 60 + 14) == (12 * 60 + 33, 13 * 60 + 14)   # 12:33 -> 1:14
    assert sh.daytime(10 * 60 + 50, 23 * 60 + 50) == (10 * 60 + 50, 11 * 60 + 50)  # stray "pm"


def test_date_reads_a_typed_range():
    assert sh._date("2026-01-07") == "2026-01-07"
    assert sh._date("1/2-1/3, 2026") == "2026-01-02"
    assert sh._date("TBD") is None


def job(name, order=None, crew=None, dallas=False):
    return {"name": name, "takedown_order": order, "crew_lines": [crew] if crew else [], "dallas": dallas}


def test_takedown_crews_follow_the_order_numbers():
    jobs = [job("a", 1), job("b", 2), job("c", 1), job("d", 3), job("e", 2), job("f", None, "Lesly Crew"),
            job("g", None, "Lesly Crew"), job("h", None, "Crew B"), job("dal", 1, dallas=True)]
    crews = {label: [j["name"] for j in js] for label, js in sh.takedown_crews(jobs)}
    assert crews == {"Crew A": ["a", "b", "d"], "Crew B": ["c", "e"], "Crew C": ["f", "g"],
                     "Crew D": ["h"], "Dallas": ["dal"]}


def run(clients, history=None):
    return sh.season_days(clients, "2025", history or {"days": [], "jobs": []}, None, card(), [], {})


def test_an_install_day_runs_from_8am_to_the_return():
    out = run([client(1, "Smith, Ann", install_date="2025-11-20", real_start="09:00", real_end="12:00",
                      crew="Crew A (5)", invoice_total=2000, boxes=10, storing=True)])
    d = next(x for x in out["days"] if x["kind"] == "install")
    # 8:00 clock-in; on site 9-12; no road matrix -> a 30-minute drive back
    assert d["clock_out_min"] == 12 * 60 + 30 and d["paid_hours"] == 4.5
    assert d["times"] == "real" and d["crew_source"] == "head count 5" and len(d["crew_people"]) == 5
    # (2000 - 10 boxes x $75) / 2
    assert d["revenue"] == 625


def test_names_on_the_job_beat_the_days_list():
    history = {"jobs": [{"name": "Smith, Ann", "crew_lines": ["Lesly Crew", "Alberto", "Evlyn"]}],
               "days": [{"date": "2025-11-20", "kind": "install", "crew": None, "ppl_needed": 9,
                         "people": [{"name": n, "half": False, "temp": False, "group": "main"}
                                    for n in ("Lesly", "Alberto", "Evlyn", "Karen", "Rolando")]}]}
    out = run([client(1, "Smith, Ann", install_date="2025-11-20", real_start="09:00", real_end="12:00")], history)
    d = next(x for x in out["days"] if x["kind"] == "install")
    assert d["crew_source"] == "crew list" and [p["name"] for p in d["crew_people"]] == ["Lesly", "Alberto", "Evlyn"]
    # Lesly and Alberto lead (Lead rate); Evlyn is General
    assert [p["rate"] for p in d["crew_people"]] == [18, 18, 15]


def test_the_days_list_staffs_a_crew_with_no_names():
    history = {"jobs": [], "days": [{"date": "2025-11-20", "kind": "install", "crew": None, "ppl_needed": 3,
                                     "people": [{"name": "Karen", "half": True, "temp": False, "group": "main"},
                                                {"name": "Rolando", "half": False, "temp": True, "group": "main"}]}]}
    out = run([client(1, "Smith, Ann", install_date="2025-11-20")], history)
    d = next(x for x in out["days"] if x["kind"] == "install")
    assert d["crew_source"] == "crew schedule" and d["times"] == "estimated"
    # half a day for Karen
    assert d["crew_rate"] == 15 * 0.5 + 15


def test_takedown_uses_real_time_or_0_6_of_the_install():
    out = run([client(1, "Smith, Ann", install_date="2025-11-20", real_start="09:00", real_end="14:00",
                      takedown_date="2026-01-07", takedown_order=1, crew="Crew A (4)")])
    td = next(x for x in out["days"] if x["kind"] == "takedown")
    assert td["stops"][0]["onsite_h"] == 3.0          # 5 h install x 0.6
    assert td["crew_source"] == "install crew size" and len(td["crew_people"]) == 4


def test_dallas_is_a_night_not_an_8am_day():
    out = run([client(1, "M Crowd Lakewood", zip="75214", install_date="2025-11-14",
                      real_start="22:00", real_end="01:00")])
    d = out["days"][0]
    assert d["crew"] == "Dallas" and not d["anchored"] and d["paid_hours"] == 3.0
    assert "Dallas trip" in d["notes"][0]


def test_cancelled_jobs_are_left_out():
    out = run([client(1, "Gone", install_date="2025-11-20", cancelled=True)])
    assert out["days"] == []
