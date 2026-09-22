"""validate.run on synthetic schedules (names match conftest's synthetic config)."""
import builtins
import copy
import importlib
import json

import pytest

import validate

_row = iter(range(1, 10_000))


def stop(name, category="Standard", business="Residence", prior=""):
    return {"row": next(_row), "name": name, "category": category,
            "business": business, "prior_install_date": prior}


def day(date, dow, crew, category, stops, total=480, window=600, lunch=40,
        anchored=True, joint_with=""):
    return {"date": date, "dow": dow, "crew": crew, "category": category,
            "stops": stops, "total_min": total, "window_min": window,
            "lunch": lunch, "depot_anchored": anchored, "install_h": 6.0,
            "joint_with": joint_with}


def make_valid_schedule():
    """Smallest schedule that passes every check: 25 Dallas stops (1 daytime
    corporate + 24 across two 3-crew nights), 8 banks on Black Friday, the
    Rotary Sunday, a club with Crew 1, the pinned/grouped/priority clients,
    one Saturday-eligible residence, plus a dropped and a no-address client."""
    days = [day("2026-11-02", "Mon", "Crew 3", "M Crowd",
                [stop("Test M Crowd Corporate Office", "M Crowd", "Business")],
                total=300, window=480, lunch=0, anchored=False)]
    n = 0
    for date, dow in (("2026-11-03", "Tue"), ("2026-11-04", "Wed")):
        for crew in ("Crew 1", "Crew 2", "Crew 3"):
            stops = []
            for _ in range(4):
                n += 1
                stops.append(stop(f"Test M Crowd Store {n}", "M Crowd", "Business"))
            days.append(day(date, dow, crew, "M Crowd", stops, total=420,
                            window=450, lunch=0, anchored=False))
    days += [
        day("2026-11-16", "Mon", "Crew 1", "Country Club",
            [stop("Test Client A"), stop("Test Club R", "Country Club", "Business"),
             stop("Test Client B")]),
        day("2026-11-17", "Tue", "Crew 2", "Standard",
            [stop("Test Client C"), stop("Test Client D")]),
        day("2026-11-24", "Tue", "Crew 1", "Standard",
            [stop("Test Client Priority", "Test Priority"), stop("Test Client E")]),
        day("2026-11-27", "Fri", "Crew 2", "Capital Bank",
            [stop(f"Test Bank {i}", "Capital Bank", "Business") for i in range(1, 9)],
            total=900, window=960),
        day("2026-11-28", "Sat", "Crew 1", "Standard",
            [stop("Test Client Sat", prior="2025-11-15"), stop("Test Client F", prior="2025-11-15")]),
        day("2026-11-29", "Sun", "Crew 3", "Rotary House",
            [stop("Test Rotary House", "Rotary House", "Business")], total=300),
    ]
    placed = {s["row"]: s for x in days for s in x["stops"]}
    dropped = [{"name": "Test Client Dropped", "reason": "NO INSTALL 2026 (client note)"}]
    noaddr = [{"name": "Test Client NoAddr", "reason": "NEED ADDRESS"}]
    return {"depot": {"lat": 29.0, "lon": -95.0}, "days": days,
            "dropped": dropped, "flagged_noaddr": noaddr,
            "all_clients": list(placed.values()) + dropped + noaddr}


def find_day(sched, date):
    return next(x for x in sched["days"] if x["date"] == date)


def test_valid_schedule_passes_every_check():
    ok, warn = validate.run(make_valid_schedule())
    assert warn == []
    assert len(ok) == 27
    assert ("PASS", "R3 banks on Fri Nov 27") in ok
    assert ("PASS", "PIN Test Client C -> 2026-11-17 (got 2026-11-17)") in ok


def test_bank_off_black_friday_fails_r3():
    s = make_valid_schedule()
    find_day(s, "2026-11-27")["date"] = "2026-11-25"
    _, warn = validate.run(s)
    assert warn == [("FAIL", "R3 banks on Fri Nov 27")]


def test_business_on_saturday_fails_r7():
    s = make_valid_schedule()
    find_day(s, "2026-11-28")["stops"].append(stop("Test Business Sat", business="Business"))
    s["all_clients"].append({"name": "Test Business Sat"})
    _, warn = validate.run(s)
    assert warn == [("FAIL", "R7 no business on weekends: 1 violations "
                             "[('2026-11-28', 'Crew 1', 'Test Business Sat')]")]


def test_saturday_without_history_fails_r12():
    s = make_valid_schedule()
    find_day(s, "2026-11-28")["stops"][0]["prior_install_date"] = "2025-11-14"
    _, warn = validate.run(s)
    assert warn == [("FAIL", "R12 Saturday clients all have 2025 Saturday history: "
                             "1 violation(s): [('2026-11-28', 'Crew 1', "
                             "'Test Client Sat', '2025-11-14')]")]


def test_moved_pin_fails_pin_check():
    s = make_valid_schedule()
    find_day(s, "2026-11-17")["date"] = "2026-11-18"
    _, warn = validate.run(s)
    assert warn == [("FAIL", "PIN Test Client C -> 2026-11-17 (got 2026-11-18)")]


def test_club_without_crew_1_fails_r2():
    s = make_valid_schedule()
    find_day(s, "2026-11-16")["crew"] = "Crew 2"
    _, warn = validate.run(s)
    assert warn == [("FAIL", "R2 Crew 1 on every club job: missing on ['Test Club R']")]


def test_over_window_day_fails_r10():
    s = make_valid_schedule()
    find_day(s, "2026-11-17")["total_min"] = 650
    _, warn = validate.run(s)
    assert warn == [("FAIL", "R10 all crew-days within their window (10h day / 7h night): "
                             "1 over [('2026-11-17', 'Crew 2', 650)]")]


def test_explicit_config_is_used_for_r5():
    s = make_valid_schedule()
    cfg = {"single_crew_priority": {"client_name": "Nobody By This Name"}}
    _, warn = validate.run(s, config=cfg)
    assert warn == [("FAIL", "R5 single-crew-priority client covered by exactly "
                             "one well-staffed crew: []")]


def test_import_reads_no_files(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError(f"validate opened a file at import: {a!r}")
    monkeypatch.setattr(builtins, "open", refuse)
    importlib.reload(validate)


def test_main_prints_report(tmp_path, monkeypatch, capsys):
    s = make_valid_schedule()
    find_day(s, "2026-11-27")["date"] = "2026-11-25"
    (tmp_path / "schedule.json").write_text(json.dumps(s))
    monkeypatch.setattr(validate, "CACHE", str(tmp_path))
    validate.main()
    lines = capsys.readouterr().out.splitlines()
    ok, warn = validate.run(copy.deepcopy(s))
    assert lines == validate.report_lines(ok, warn)
    assert lines[0] == lines[-2] == "=" * 70
    assert lines[-3] == "[FAIL] R3 banks on Fri Nov 27"
    assert lines[-1] == "26 pass, 1 warn/fail"
