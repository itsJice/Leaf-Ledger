"""A start time for one stop (review_template.html, Comments #35).

11/15/2026: "How do I assign specific start time to an install? Adding
pickups for Mi Cocina jobs in Dallas and it's automatically adding it to the
beginning of the day." A stop can be given a time it won't start before (a
pickup at 2:00 AM after two installs on a Dallas night). The stops after it
move later and the day's order is kept by hand. Shared state `stopStart` is
{"<crewDayId>#<row>": clock minutes}. These run the template's own functions.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_dallas_nights import MERGE

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

LIB = "\n".join(js_function(n) for n in (
    "stopStartKey", "normStopMin", "normStopStart", "withStopStart", "stopAtRel", "walkStops",
    "stopStartChoices", "fmtClock"))


def run(body):
    return json.loads(run_js("let days=[];\n" + LIB + body))


def test_a_2am_pickup_after_two_installs_on_an_11pm_night_waits_and_pushes_later_stops():
    out = run("""
      // two 75-minute installs, 15-minute drives, then the pickup (30 min), then one more stop
      const order=[1,2,3,4], dur={1:75,2:75,3:30,4:60};
      const at={3:stopAtRel(135, 1380)};
      const w=walkStops(1380, order, r=>dur[r], ()=>15, r=>at[r]??null);
      console.log(JSON.stringify(w.map(x=>[x.row, fmtClock(x.start), fmtClock(x.end), Math.round(x.wait)])));
    """)
    assert out == [[1, "11:00 PM", "12:15 AM", 0], [2, "12:30 AM", "1:45 AM", 0],
                   [3, "2:15 AM", "2:45 AM", 15], [4, "3:00 AM", "4:00 AM", 0]]


def test_a_set_time_already_passed_does_not_pull_the_stop_earlier():
    out = run("""
      const w=walkStops(510, [1,2], ()=>120, ()=>30, r=>r===2?600:null);
      console.log(JSON.stringify(w.map(x=>[x.start, x.wait])));
    """)
    assert out == [[510, 0], [660, 0]]


def test_times_before_the_crews_start_are_the_next_morning():
    out = run("console.log(JSON.stringify([stopAtRel(120,1380), stopAtRel(1380,1380), stopAtRel(1410,1380), stopAtRel(600,510), stopAtRel(15,510)]));")
    assert out == [1560, 1380, 1410, 600, 1455]


def test_norm_keeps_stops_still_on_that_crew_day():
    out = run("""
      days=[{id:'2026-11-03|Crew 1|0', stops:[70,71]}];
      console.log(JSON.stringify(normStopStart({'2026-11-03|Crew 1|0#71':120, '2026-11-03|Crew 1|0#99':120,
        'gone|Crew 1|0#70':60, '2026-11-03|Crew 1|0#70':'x', 'nohash':5, '2026-11-03|Crew 1|0#70b':1440})));
    """)
    assert out == {"2026-11-03|Crew 1|0#71": 120}


def test_with_stop_start_sets_and_clears():
    out = run("const a=withStopStart({}, 'D#1', 120); console.log(JSON.stringify([a, withStopStart(a,'D#1',null)]));")
    assert out == [{"D#1": 120}, {}]


def test_choices_run_from_the_crew_start_for_16_hours():
    out = run("const c=stopStartChoices(1380); console.log(JSON.stringify([c.length, fmtClock(c[0]), fmtClock(c[12]), fmtClock(c.at(-1))]));")
    assert out == [65, "11:00 PM", "2:00 AM", "3:00 PM"]


def test_merge_keeps_both_tabs_stop_times():
    out = json.loads(run_js(MERGE + """
      const r=mergeShared({stopStart:{}}, {stopStart:{'D1#3':120}}, {stopStart:{'D2#5':90}});
      console.log(JSON.stringify(r.state.stopStart));
    """))
    assert out == {"D1#3": 120, "D2#5": 90}


def test_wired_through_times_save_undo_and_print():
    assert "stopWalk(d, order)" in js_function("stopTimes")
    assert "r=>stopAtOf(d, r)" in js_function("stopWalk")
    assert "rt.drive + wait +" in js_function("dayCalc")
    assert "crewStart, stopStart," in js_function("snapshot")
    assert "crewStart, stopStart, synHours" in js_function("stateBlob")
    for fn in ("restoreBlob", "restoreHistoryEntry"):
        assert "stopStart = normStopStart(" in js_function(fn)
    assert "stopStart = normStopStart(stopStart);" in js_function("render")
    assert "starts at ${fmtClock(at)}" in js_function("manifestHTML")
    assert "manualOrder[dayId] = [...full];" in js_function("setStopStart")
    for fn in ("stopStartFieldHTML", "stopAtChipHTML"):
        assert "—" not in js_function(fn)
