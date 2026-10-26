"""Crew names on the Install Schedule (review_template.html).

10/24/2026: "Give me the ability on this staffing page to double tap crew 1,
crew 2, crew 3, and ... change the name via there, and it update globally.
When I do it on Dallas week, I should not be able to edit Dallas week, but I
want to be able to edit the crew name."

Shared state `crewNames` is {shiftKey: name}: a crew-day's own id, Dallas
nights included (each night is its own shift since 10/24/2026). A name saved
under a Dallas run's old week key still shows on every night of that run, and
the first edit of a night splits it onto each night. These run the
template's own functions in node, like test_dallas_nights.py. No real names.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_dallas_nights import BOARD, MERGE, fns

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

NAMES = BOARD + "\nconst CREW_NAME_MAX=40, CREW_TAP_MS=400;\nlet crewNames={};\n" + fns(
    "normCrewName", "crewNameKey", "normCrewNames", "withCrewName", "crewName", "dallasWeekKeyOf",
    "liveShiftKeys", "withWeekKeySplit", "weekSplitFor", "dallasRunNights",
    "crewTitle", "crewLabelShort", "crewTitleShort", "shiftLabelOf", "isDoubleTap")


def run(body):
    return json.loads(run_js(NAMES + body))


def test_key_is_the_day_id_for_houston_and_for_each_dallas_night():
    out = run("""
      days=['2026-11-02|Crew 1|0','2026-11-04|Crew 1|0','2026-11-04|Crew 2|0','2026-12-01|Crew 3|0']
        .map(id=>day(id,[1]));
      days.push(hydrate({id:'2026-12-01|Training|0', date:'2026-12-01', crew:'Training', stops:[], training:true}));
      console.log(JSON.stringify(days.map(crewNameKey)));
    """)
    assert out == ["2026-11-02|Crew 1|0", "2026-11-04|Crew 1|0", "2026-11-04|Crew 2|0",
                   "2026-12-01|Crew 3|0", None]


def test_a_name_saved_on_the_old_week_key_shows_on_every_night_of_that_run():
    out = run("""
      days=['2026-11-02|Crew 1|0','2026-11-03|Crew 1|0','2026-11-06|Crew 1|0','2026-11-03|Crew 2|0']
        .map(id=>day(id,[1]));
      crewNames={'dallas|2026-11-02|Crew 1':"Lead A's crew"};
      console.log(JSON.stringify(days.map(crewTitle)));
    """)
    assert out == ["Lead A's crew (Crew 1)"] * 3 + ["Crew 2"]


def test_a_night_name_wins_over_the_week_name_and_editing_splits_the_week_key():
    out = run("""
      days=['2026-11-02|Crew 1|0','2026-11-03|Crew 1|0','2026-11-04|Crew 1|0','2026-11-03|Crew 2|0']
        .map(id=>day(id,[1]));
      crewNames={'dallas|2026-11-02|Crew 1':'Week A'};
      // what setCrewName does: split the old week key, then set this night
      const sp=weekSplitFor('2026-11-03|Crew 1|0');
      crewNames=withCrewName(withWeekKeySplit(crewNames, sp.weekKey, sp.ids), '2026-11-03|Crew 1|0', 'Tue B');
      const after=days.map(crewName);
      const cleared=withCrewName(crewNames, '2026-11-03|Crew 1|0', '');
      crewNames=cleared;
      console.log(JSON.stringify({sp, after, saved:cleared, afterClear:days.map(crewName),
        houston:weekSplitFor('2026-12-01|Crew 1|0')}));
    """)
    assert out["sp"] == {"weekKey": "dallas|2026-11-02|Crew 1",
                         "ids": ["2026-11-03|Crew 1|0", "2026-11-02|Crew 1|0", "2026-11-04|Crew 1|0"]}
    assert out["after"] == ["Week A", "Tue B", "Week A", ""]
    # the week key is gone once split, so clearing a night really clears it
    assert out["saved"] == {"2026-11-02|Crew 1|0": "Week A", "2026-11-04|Crew 1|0": "Week A"}
    assert out["afterClear"] == ["Week A", "", "Week A", ""]
    assert out["houston"] == {"weekKey": None, "ids": []}


def test_week_key_split_is_pure_and_keeps_night_values():
    out = run("""
      const m={'dallas|2026-11-02|Crew 1':'W', 'a':'A'};
      console.log(JSON.stringify([withWeekKeySplit(m, 'dallas|2026-11-02|Crew 1', ['a','b']), m,
        withWeekKeySplit(m, null, ['a']), withWeekKeySplit(m, 'dallas|x', ['c'])]));
    """)
    assert out[0] == {"a": "A", "b": "W"}
    assert out[1] == {"dallas|2026-11-02|Crew 1": "W", "a": "A"}
    assert out[2] == out[1] and out[3] == out[1]


def test_title_keeps_the_positional_number_and_follows_its_crew_day():
    out = run("""
      days=['2026-12-01|Crew 1|0','2026-12-01|Crew 3|0'].map(id=>day(id,[1]));
      crewNames={'2026-12-01|Crew 3|0':'Team B'};
      const before=days.map(d=>[crewLabel(d), crewTitle(d), crewTitleShort(d), crewName(d)]);
      days=days.slice(1);   // Crew 1's day goes away: stored Crew 3 now reads as Crew 1
      const after=days.map(d=>[crewLabel(d), crewTitle(d)]);
      console.log(JSON.stringify({before, after}));
    """)
    assert out["before"] == [["Crew 1", "Crew 1", "C1", ""], ["Crew 2", "Team B (Crew 2)", "C2 Team B", "Team B"]]
    assert out["after"] == [["Crew 1", "Team B (Crew 1)"]]


def test_names_are_trimmed_capped_and_empty_restores_the_default():
    out = run("""
      const long='x'.repeat(60);
      let n=withCrewName({}, 'k', '  Lesly   crew  ');
      const a={...n};
      n=withCrewName(n, 'k', long); const b=n.k.length;
      n=withCrewName(n, 'k', '   ');
      console.log(JSON.stringify({a, b, c:n}));
    """)
    assert out == {"a": {"k": "Lesly crew"}, "b": 40, "c": {}}


def test_saved_names_are_normalized_and_dropped_for_shifts_that_are_gone():
    out = run("""
      days=['2026-12-01|Crew 1|0','2026-11-03|Crew 2|0'].map(id=>day(id,[1]));
      console.log(JSON.stringify([
        normCrewNames({'2026-12-01|Crew 1|0':' A ', 'dallas|2026-11-02|Crew 2':'B',
                       '2026-12-09|Crew 1|0':'gone', '2026-12-01|Crew 2|0':'', x:5}),
        normCrewNames(null), normCrewNames(['a']),
        normCrewNames({a:'A', b:'B'}, new Set(['a']))]));
    """)
    # an old Dallas week key is kept while that run is on the board
    assert out == [{"2026-12-01|Crew 1|0": "A", "dallas|2026-11-02|Crew 2": "B"}, {}, {}, {"a": "A"}]


def test_shift_label_names_the_crew_but_never_renames_the_tail():
    out = run("""
      console.log(JSON.stringify([
        shiftLabelOf({pos:'Crew 1', name:'Team A', tail:'joint'}),
        shiftLabelOf({pos:'Crew 1', name:'', tail:'joint'}),
        shiftLabelOf({pos:'Crew 2', name:'Team B', tail:'night'}),
        shiftLabelOf({pos:'Crew 3', name:'', tail:''})]));
    """)
    assert out == ["Team A (Crew 1) · joint", "Crew 1 · joint",
                   "Team B (Crew 2) · night", "Crew 3"]


def test_double_tap_timing():
    out = run("""
      const p={key:'a', t:1000};
      console.log(JSON.stringify([isDoubleTap(p,'a',1300), isDoubleTap(p,'a',1500), isDoubleTap(p,'b',1100),
                                  isDoubleTap(null,'a',1100), isDoubleTap(p,'a',900)]));
    """)
    assert out == [True, False, False, False, False]


def test_crew_names_merge_three_ways_on_a_stale_tab():
    out = json.loads(run_js(MERGE + """
      const base={placement:{}, crewNames:{a:'A', b:'B'}};
      const mine=clone(base), theirs=clone(base);
      mine.crewNames={a:'A2', b:'B', c:'C'};      // I renamed a, named c
      theirs.crewNames={a:'A', d:'D'};            // they cleared b, named d
      const r=mergeShared(base, mine, theirs);
      const both=mergeShared(base, {crewNames:{a:'Mine'}}, {crewNames:{a:'Theirs'}}, (k,x)=>x);
      console.log(JSON.stringify({got:r.state.crewNames, conflicts:r.conflicts, both:[both.state.crewNames, both.conflicts]}));
    """))
    assert out["got"] == {"a": "A2", "c": "C", "d": "D"}
    assert out["conflicts"] == []
    assert out["both"] == [{"a": "Theirs"}, ["Crew name for a"]]


def test_every_save_and_load_path_carries_crew_names():
    assert "'crewNames'" in re.search(r"const SHARED_MAP_KEYS=.*", TEMPLATE).group(0)
    assert "crewNames, savedAt" in js_function("snapshot")
    assert "crewNames}" in js_function("stateBlob")
    for fn in ("restoreBlob", "restoreHistoryEntry"):
        src = js_function(fn)
        # after the board is rebuilt, so the shift keys it checks exist
        assert src.index("crewNames = normCrewNames(") > src.index("applyPlacement(")
    boot = TEMPLATE[TEMPLATE.index("const s = JSON.parse(localStorage.getItem(LS_KEY)||'{}');"):]
    assert boot.index("crewNames = normCrewNames(s.crewNames)") > boot.index("applyPlacement(s.placement)")
    assert "crewNames = normCrewNames(crewNames)" in js_function("render")


def test_only_the_crew_part_of_the_card_is_editable_and_read_only_cant():
    src = js_function("crewNameEditHTML")
    assert "READONLY" in src and "sh.training" in src
    assert "READONLY" in js_function("crewNamePencilHTML")
    card = js_function("shiftCardHTML")
    # "joint" / "night" sits outside the editable span
    assert "crewNameEditHTML(sh)" in card and 'class="shctail"' in card
    assert "data-crewname" not in card
    for fn in ("startCrewNameEdit", "setCrewName"):
        assert "roBlocked()" in js_function(fn)
    assert "maxLength=CREW_NAME_MAX" in js_function("startCrewNameEdit")
    for fn in ("crewNameEditHTML", "startCrewNameEdit", "setCrewName", "normCrewNames", "crewTitle"):
        assert "—" not in js_function(fn), fn


def test_names_show_on_days_calendar_print_map_and_exports():
    assert "crewName(d)" in js_function("buildDayCard")
    assert "crewTitleShort(d)" in TEMPLATE and "crewTitle(b.d)" in TEMPLATE
    assert "'Crew name'" in js_function("exportCSV")
    assert "crewName:crewName(d)" in js_function("exportJSON")
    assert "${esc(crewTitle(d))} · ${esc(dowName(d))}" in TEMPLATE      # crew sheet
    assert "esc(crewTitle(d))}<br><b>${miTxt" in TEMPLATE         # map route popup
    # A whole-day move or swap carries a Houston crew's name with its stops
    # (a Dallas week's name stays with the week: its key isn't the day id).
    assert "crewNames=swapKeys(crewNames, p.a, p.b)" in js_function("exchangeCrewDays")
    assert "crewNameKey(A)===p.a && crewNameKey(B)===p.b" in js_function("exchangeCrewDays")
