"""A start time set by hand per crew-day (review_template.html).

11/17/2026 (office): the M Crowd nights. Sat 11/21 Crew 2 starts at 11:00 PM,
Sun 11/22 Crews 1 and 2 at 10:00 PM, while Sat 11/21 Crew 1 stays a normal
8:30 AM Houston day. Stops get moved around, so staff set it by hand per
crew-day and it sticks to that crew-day.

Shared state `crewStart` is {crewDayId: minutes}. A start at 6:00 PM or later
runs like a Dallas night (night window, no depot drive, no lunch); a daytime
start only moves the clock. These run the template's own functions in node.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_dallas_nights import BOARD, MERGE, fns

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

START = BOARD + """
const DEPART_MIN=510, ARRIVE_MIN=480, CREW_START_STEP=15;
""" + fns("normCrewStart", "withCrewStart", "usualStartFor", "shiftStart", "startChoices",
          "startQuickPicks", "fmtClock", "arriveFor")


def run(body):
    return json.loads(run_js(START + body))


def test_norm_keeps_valid_times_for_crew_days_on_the_board_only():
    out = run("""
      days=[day('2026-11-21|Crew 1|0',[1]), day('2026-11-21|Crew 2|0',[2])];
      console.log(JSON.stringify(normCrewStart({'2026-11-21|Crew 2|0':1380, '2026-11-21|Crew 1|0':'510',
        'gone|Crew 9|0':1320, 'x':'abc'})));
      """)
    assert out == {"2026-11-21|Crew 1|0": 510, "2026-11-21|Crew 2|0": 1380}


def test_norm_drops_out_of_range_and_junk():
    out = run("""
      days=[day('2026-11-21|Crew 1|0',[1])];
      const k='2026-11-21|Crew 1|0';
      console.log(JSON.stringify([60, 1440, -5, null, true, [], 299, 300, 1425].map(v=>normCrewStart({[k]:v})[k]??null)));
      """)
    assert out == [None, None, None, None, None, None, None, 300, 1425]


def test_with_crew_start_sets_and_clears_each_id():
    out = run("""
      const a=withCrewStart({}, ['A','B'], 1320);
      const b=withCrewStart(a, ['A'], null);
      console.log(JSON.stringify({a, b}));
      """)
    assert out == {"a": {"A": 1320, "B": 1320}, "b": {"B": 1320}}


def test_the_11_21_and_11_22_settings_run_as_nights_and_crew_1_stays_a_day():
    out = run("""
      days=['2026-11-21|Crew 1|0','2026-11-21|Crew 2|0','2026-11-22|Crew 1|0','2026-11-22|Crew 2|0']
        .map((id,i)=>day(id,[i+1]));
      crewStart={'2026-11-21|Crew 2|0':1380, '2026-11-22|Crew 1|0':1320, '2026-11-22|Crew 2|0':1320};
      refreshDerivedMeta();
      console.log(JSON.stringify(days.map(d=>({id:d.id, start:shiftStart(d), win:d.win,
        anchored:d.anchored, lunch:d.lunchMin, clock:fmtClock(shiftStart(d))}))));
      """)
    c1, c2, s1, s2 = out
    assert (c1["start"], c1["win"], c1["anchored"], c1["lunch"]) == (510, 600, True, 40)
    assert (c2["clock"], c2["win"], c2["anchored"], c2["lunch"]) == ("11:00 PM", 450, False, 0)
    assert s1["clock"] == s2["clock"] == "10:00 PM"
    assert s1["anchored"] is False and s2["win"] == 450


def test_clearing_the_start_puts_the_days_shape_back():
    out = run("""
      days=[day('2026-11-21|Crew 2|0',[2])];
      crewStart={'2026-11-21|Crew 2|0':1380}; refreshDerivedMeta();
      const night={start:shiftStart(days[0]), anchored:days[0].anchored};
      crewStart={}; refreshDerivedMeta();
      console.log(JSON.stringify({night, day:{start:shiftStart(days[0]), anchored:days[0].anchored,
        win:days[0].win, lunch:days[0].lunchMin}}));
      """)
    assert out["night"] == {"start": 1380, "anchored": False}
    assert out["day"] == {"start": 510, "anchored": True, "win": 600, "lunch": 40}


def test_a_daytime_start_only_moves_the_clock_and_the_depot_arrival():
    out = run("""
      days=[day('2026-12-01|Crew 1|0',[1])];
      crewStart={'2026-12-01|Crew 1|0':600}; refreshDerivedMeta();
      const d=days[0];
      console.log(JSON.stringify({start:shiftStart(d), anchored:d.anchored, lunch:d.lunchMin,
        arrive:arriveFor(d, true, shiftStart(d))}));
      """)
    assert out == {"start": 600, "anchored": True, "lunch": 40, "arrive": 570}


def test_a_built_dallas_night_can_start_at_10_pm_and_back():
    out = run("""
      days=[day('2026-11-02|Crew 1|0',[63,1])];
      crewStart={'2026-11-02|Crew 1|0':1320}; refreshDerivedMeta();
      const a=[shiftStart(days[0]), days[0].win, days[0].anchored];
      crewStart={}; refreshDerivedMeta();
      console.log(JSON.stringify({a, b:[shiftStart(days[0]), days[0].win]}));
      """)
    assert out == {"a": [1320, 450, False], "b": [1380, 450]}


def test_moving_stops_keeps_the_crew_days_start():
    out = run("""
      days=[day('2026-11-21|Crew 2|0',[2,3]), day('2026-11-22|Crew 1|0',[4])];
      crewStart={'2026-11-21|Crew 2|0':1380};
      days[0].stops=[2]; days[1].stops.push(3); refreshDerivedMeta();
      console.log(JSON.stringify(days.map(shiftStart)));
      """)
    assert out == [1380, 510]


def test_quick_picks_and_choices():
    out = run("""
      console.log(JSON.stringify({q:startQuickPicks(510).map(fmtClock), n:startQuickPicks(1380).map(fmtClock),
        first:fmtClock(startChoices()[0]), last:fmtClock(startChoices().slice(-1)[0]), count:startChoices().length}));
      """)
    assert out["q"] == ["8:30 AM", "10:00 PM", "11:00 PM"]
    assert out["n"] == ["11:00 PM", "10:00 PM"]
    assert (out["first"], out["last"], out["count"]) == ("5:00 AM", "11:45 PM", 76)


def test_merge_keeps_both_tabs_start_times():
    out = json.loads(run_js(MERGE + """
      const base={crewStart:{}}, mine={crewStart:{'2026-11-21|Crew 2|0':1380}},
            theirs={crewStart:{'2026-11-22|Crew 1|0':1320}};
      const r=mergeShared(base, mine, theirs);
      const c=mergeShared({crewStart:{A:1320}}, {crewStart:{A:1380}}, {crewStart:{A:1335}}, (k,x)=>x);
      console.log(JSON.stringify({state:r.state.crewStart, conflicts:c.conflicts, kept:c.state.crewStart}));
      """))
    assert out["state"] == {"2026-11-21|Crew 2|0": 1380, "2026-11-22|Crew 1|0": 1320}
    assert out["conflicts"] == ["Start time for A"]
    assert out["kept"] == {"A": 1335}


def test_wired_through_save_undo_restore_and_render():
    assert "'crewStart'" in js_function("mergeShared") or "crewStart" in TEMPLATE.split("const SHARED_MAP_KEYS=")[1].split("\n")[0]
    assert "hoursOverride, crewStart," in js_function("snapshot")
    assert "crewStart, synHours" in js_function("stateBlob")
    for fn in ("restoreBlob", "restoreHistoryEntry"):
        assert "crewStart = normCrewStart(" in js_function(fn)
    assert "crewStart = normCrewStart(crewStart);" in js_function("render")
    assert "crewStart=swapKeys(crewStart, p.a, p.b);" in js_function("exchangeCrewDays")
    assert "crewStart" in js_function("withScratch")
    assert "start:shiftStart(d)" in js_function("sharedSnapshot")
    assert "if(d.startMin!=null) return d.startMin;" in js_function("shiftStart")


def test_on_screen_words_have_no_em_dash():
    for fn in ("crewStartFieldHTML", "startBarHTML", "schedLineHTML", "drawStartDlg"):
        assert "—" not in js_function(fn), fn
