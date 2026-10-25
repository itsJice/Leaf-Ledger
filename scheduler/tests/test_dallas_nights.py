"""Dallas nights booked after the build (review_template.html).

10/21/2026: the Mi Cocina (M Crowd) takedowns go to Dallas on Jan 2-4, 2027,
"just like the November Dallas Nights ... we're going to use the same timing."
The build (DATA/SPEC) can't change -- a new DATA is a new version and the
board would look wiped -- so those dates live in shared state (dallasNights,
like trainingDays) and the page derives the rest: a crew-day there runs like a
built Mi Cocina night, a stop on two crews that night is a joint stop, the
crews are staffed for the whole run, and the takedown visits (rows under the
locations' own names, visit type Takedown) don't get mistaken for the
install rows. These run the template's own functions in node, like
test_stale_tab_merge.py. Every name below is a Dallas location the page
already shows; nothing personal.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def fns(*names):
    return "\n".join(js_function(n) for n in names)


def const_line(name):
    m = re.search(rf"^const {name}=.*$", TEMPLATE, re.M)
    assert m, name
    return m.group(0)


NIGHT = {"cat": "M Crowd", "anchored": False, "stacked": 1, "win": 450, "lunchMin": 0,
         "half": [], "joint": "", "startRow": None, "note": "built", "flags": ["x"],
         "winReason": "Mi Cocina night shift, 11pm-6:30am", "zones": ["Uptown/Park Cities"]}
SPEC = {
    "const": {"NIGHT": 450, "DAY_CAP": 600, "LUNCH": 40, "CREWS": ["Crew 1", "Crew 2", "Crew 3"]},
    "calendar": [{"date": d, "kind": "dallas_night", "dow": ""} for d in
                 ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06")]
                + [{"date": "2026-12-01", "kind": "weekday", "dow": "Tue"}]
                + [{"date": d, "kind": "weekday", "dow": "", "optional": True} for d in
                   ("2027-01-01", "2027-01-02", "2027-01-03", "2027-01-04", "2027-01-05")],
    "dayMeta": {
        "2026-11-02|Crew 1|0": {**NIGHT, "half": [63], "joint": "Crew 2", "startRow": 63, "note": "JOINT"},
        "2026-11-02|Crew 2|0": {**NIGHT, "half": [63], "joint": "Crew 1", "startRow": 63},
        "2026-11-02|Crew 3|0": {**NIGHT, "win": 480, "note": "DAYTIME install"},
        "2026-11-02|Crew 3|1": {**NIGHT, "note": "crew 3 night"},
    },
}

BOARD = f"""
const SPEC={json.dumps(SPEC)}, K=SPEC.const;
const DALLAS_CAL = new Set(SPEC.calendar.filter(c=>c.kind==='dallas_night').map(c=>c.date));
let dallasNights = new Set();
let days = [];
""" + fns("normDallasNights", "isDallasDate", "dallasNightMeta", "metaFor", "hydrate",
          "dynamicJoints", "refreshDerivedMeta", "crewLabel", "isDallasNight", "dallasRunStart",
          "shiftKeyOf", "addDays", "dateOf", "isoOf", "isCrewName") + """
const day=(id, stops)=>{ const [date,crew]=id.split('|'); return hydrate({id, date, crew, stops}); };
"""


def run(body):
    return json.loads(run_js(BOARD + body))


def test_built_night_meta_is_copied_without_that_nights_own_wiring():
    out = run("""
      console.log(JSON.stringify(['Crew 1','Crew 3'].map(c=>dallasNightMeta(SPEC.dayMeta, SPEC.calendar, c, K.NIGHT))));
    """)
    c1, c3 = out
    assert (c1["win"], c1["anchored"], c1["lunchMin"], c1["cat"]) == (450, False, 0, "M Crowd")
    assert c1["winReason"] == "Mi Cocina night shift, 11pm-6:30am"
    assert (c1["note"], c1["half"], c1["joint"], c1["startRow"], c1["zones"], c1["flags"]) == ("", [], "", None, [], [])
    # Crew 3's built daytime install (9-5) is not a night: its night card is copied.
    assert c3["win"] == 450


def test_no_built_night_falls_back_to_a_plain_night():
    out = run("console.log(JSON.stringify(dallasNightMeta({}, [], 'Crew 2', 450)));")
    assert (out["win"], out["anchored"], out["lunchMin"], out["cat"]) == (450, False, 0, "M Crowd")


def test_marking_a_date_makes_its_days_dallas_nights_and_unmarking_undoes_it():
    out = run("""
      days=[day('2027-01-02|Crew 1|0',[900010,900011]), day('2027-01-02|Crew 2|0',[900010,900012]),
            day('2026-12-01|Crew 1|0',[5])];
      const before=days.map(d=>[d.win, d.anchored, d.lunchMin]);
      dallasNights=normDallasNights(['2027-01-02', 'junk', 5]);
      refreshDerivedMeta();
      const after=days.map(d=>[d.win, d.anchored, d.lunchMin, d.cat, isDallasNight(d), shiftKeyOf(d)]);
      dallasNights=new Set(); refreshDerivedMeta();
      console.log(JSON.stringify({before, after, undone:days.map(d=>[d.win, d.anchored, isDallasNight(d)]),
                                  set:[...normDallasNights(['2027-01-02','junk',5])]}));
    """)
    assert out["set"] == ["2027-01-02"]
    assert out["before"][0] == [600, True, 40]
    assert out["after"][0] == [450, False, 0, "M Crowd", True, "dallas|2027-01-02|Crew 1"]
    assert out["after"][2] == [600, True, 40, "Standard", False, "2026-12-01|Crew 1|0"]
    assert out["undone"][0] == [600, True, False]


def test_each_run_of_dallas_nights_is_its_own_whole_shift():
    out = run("""
      dallasNights=new Set(['2027-01-02','2027-01-03','2027-01-04']);
      days=['2026-11-02|Crew 1|0','2026-11-05|Crew 1|0','2027-01-02|Crew 1|0','2027-01-04|Crew 1|0','2027-01-04|Crew 2|0']
        .map(id=>day(id,[1]));
      console.log(JSON.stringify(days.map(shiftKeyOf)));
    """)
    assert out == ["dallas|2026-11-02|Crew 1", "dallas|2026-11-02|Crew 1",
                   "dallas|2027-01-02|Crew 1", "dallas|2027-01-02|Crew 1", "dallas|2027-01-02|Crew 2"]


def test_a_row_on_two_crews_the_same_night_is_a_joint_stop():
    out = run("""
      dallasNights=new Set(['2027-01-02']);
      days=[day('2027-01-02|Crew 1|0',[900011,900010]), day('2027-01-02|Crew 2|0',[900012,900010]),
            day('2027-01-02|Crew 3|0',[900013]), day('2027-01-03|Crew 1|0',[900010])];
      refreshDerivedMeta();
      console.log(JSON.stringify(days.map(d=>[d.half, d.joint, d.startRow])));
    """)
    assert out == [[[900010], "Crew 2", 900010], [[900010], "Crew 1", 900010],
                   [[], "", None], [[], "", None]]


def test_dynamic_joints_cover_built_days_too():
    out = run("""
      const ds=[{id:'a', date:'d', crew:'Crew 1', stops:[1,2]}, {id:'b', date:'d', crew:'Crew 2', stops:[1]},
                {id:'c', date:'d', crew:'Crew 3', stops:[1,3]}, {id:'t', date:'d', crew:'Training', stops:[3], training:true}];
      console.log(JSON.stringify(dynamicJoints(ds, id=>id==='b', d=>d.crew)));
    """)
    assert out == {"a": {"half": [1], "joint": "Crew 2 + Crew 3"},
                   "b": {"half": [1], "joint": "Crew 1 + Crew 3"},
                   "c": {"half": [1], "joint": "Crew 1 + Crew 2"}}


def test_built_night_keeps_its_meta_but_shared_stops_follow_the_board():
    out = run("""
      days=[day('2026-11-02|Crew 1|0',[63,65]), day('2026-11-02|Crew 2|0',[75])];
      refreshDerivedMeta();
      console.log(JSON.stringify(days.map(d=>[d.half, d.joint, d.note])));
    """)
    # Built days keep their note/window and the build's joint rows that are
    # still on them; Crew 2 no longer has 63, so it doesn't count it as half.
    assert out == [[[63], "Crew 2", "JOINT"], [[], "", "built"]]


def test_joint_stop_moved_onto_a_built_night_splits_there():
    out = run("""
      days=[day('2026-11-02|Crew 1|0',[63,65]), day('2026-11-02|Crew 2|0',[63,75])];
      refreshDerivedMeta();
      console.log(JSON.stringify(days.map(d=>[d.half, d.joint])));
    """)
    assert out == [[[63], "Crew 2"], [[63], "Crew 1"]]


# ---- shared state: dallasNights saves, loads and merges like trainingDays ----

MERGE = "\n".join(const_line(n) for n in ("SHARED_SET_KEYS", "SHARED_MAP_KEYS", "SHARED_KEYS")) \
    + "\nconst TEXT_LOG_MAX=5;\n" + fns("sharedDocOf", "stableJSON", "sameNewClient", "mergeShared") \
    + "\nconst clone=x=>JSON.parse(JSON.stringify(x));\n"


def test_dallas_nights_merge_three_ways_on_a_stale_tab():
    out = json.loads(run_js(MERGE + """
      const base={placement:{}, dallasNights:['2027-01-02','2027-01-09']};
      const mine=clone(base), theirs=clone(base);
      mine.dallasNights=['2027-01-02','2027-01-03'];            // I added 1/3, took 1/9 off
      theirs.dallasNights=['2027-01-02','2027-01-09','2027-01-04'];  // they added 1/4
      const r=mergeShared(base, mine, theirs);
      const doc=sharedDocOf({dallasNights:['2027-01-02'], timeline:{}, savedAt:1});
      console.log(JSON.stringify({got:[...r.state.dallasNights].sort(), changed:r.changed, conflicts:r.conflicts, doc}));
    """))
    assert out["got"] == ["2027-01-02", "2027-01-03", "2027-01-04"]
    assert out["changed"] == 2 and out["conflicts"] == []
    assert out["doc"] == {"dallasNights": ["2027-01-02"]}


def test_every_save_and_load_path_carries_dallas_nights():
    assert "dallasNights:[...dallasNights]" in js_function("snapshot")
    assert "dallasNights:[...dallasNights]" in js_function("stateBlob")
    for fn in ("restoreBlob", "restoreHistoryEntry"):
        src = js_function(fn)
        # before applyPlacement, so a day rebuilt there gets its Dallas meta
        assert src.index("dallasNights = normDallasNights(") < src.index("applyPlacement(")
    boot = TEMPLATE[TEMPLATE.index("const s = JSON.parse(localStorage.getItem(LS_KEY)||'{}');"):]
    assert boot.index("dallasNights = normDallasNights(s.dallasNights)") < boot.index("applyPlacement(s.placement)")
    assert "refreshDerivedMeta();" in js_function("applyPlacement")
    assert "refreshDerivedMeta();" in js_function("render")
    assert "refreshDerivedMeta();" in js_function("sharedSnapshot")
    # removing an added date drops its Dallas mark too
    assert "dallasNights.delete(date);" in js_function("removeAddedDate")


def test_new_date_dialog_has_the_dallas_checkbox():
    assert 'id="nddallas"' in TEMPLATE and "Dallas night (hotel)" in TEMPLATE
    dlg = TEMPLATE[TEMPLATE.index("document.getElementById('ndgo').onclick"):]
    dlg = dlg[:dlg.index("\n};") + 3]
    assert "addDallasNight(v)" in dlg and "nddallas" in dlg
    assert "data-undal" in js_function("renderAddedDates")
    # no year or date is written into the feature
    for fn in ("addDallasNight", "removeDallasNight", "dallasNightMeta", "refreshDerivedMeta", "renderAddedDates"):
        assert not re.search(r"20\d\d-\d\d", js_function(fn)), fn
    for fn in ("addDallasNight", "removeDallasNight", "renderAddedDates"):
        assert "—" not in js_function(fn), fn


# ---- takedown visits under the location's own name ----

def test_a_takedown_row_and_another_tabs_install_visit_are_not_the_same_new_client():
    out = json.loads(run_js(MERGE + """
      const td={row:900010, name:'M Crowd Lakewood', street:'2 B St', visitType:'Takedown'};
      const fix={row:900010, name:'M Crowd Lakewood', street:'2 B St', visitType:'Standard'};
      const base={placement:{}, newClients:[]};
      console.log(JSON.stringify({
        same:[sameNewClient(td, {...td}), sameNewClient(td, fix), sameNewClient(fix, {...fix, name:'Renamed'})],
        hard:mergeShared(base, {...base, newClients:[td]}, {...base, newClients:[fix]}).hard}));
    """))
    assert out["same"] == [True, False, True]
    assert out["hard"] == ["New client M Crowd Lakewood"]


DATES = fns("boardDatesByClient", "boardDateMoves", "placementDayList", "normName")


def test_takedown_row_sets_the_cards_takedown_date_not_its_install_date():
    out = json.loads(run_js(DATES + """
      const C={65:{name:'M Crowd Lakewood'}, 900011:{name:'M Crowd Lakewood', visitType:'Takedown'},
               900004:{name:'William Brothers-NRG — TEARDOWN', visitType:'Takedown'}};
      const info=r=>C[r] ? {key:normName(C[r].name), name:C[r].name, id:7, visitType:C[r].visitType} : null;
      const CUT='2026-12-25';
      const at=pl=>boardDatesByClient(placementDayList(pl), CUT, info);
      const a=at({65:['2026-11-02|Crew 1|0'], 900011:['2027-01-02|Crew 1|0']});
      const b=at({65:['2026-11-02|Crew 1|0'], 900011:['2027-01-04|Crew 2|0']});
      const early=at({65:['2026-11-02|Crew 1|0'], 900011:['2026-11-03|Crew 1|0']});
      console.log(JSON.stringify({a, moves:boardDateMoves(b, a), early}));
    """))
    assert out["a"] == {"m crowd lakewood": {"name": "M Crowd Lakewood", "id": 7,
                                             "install": "2026-11-02", "takedown": "2027-01-02"}}
    assert out["moves"] == [{"name": "M Crowd Lakewood", "id": 7, "kind": "takedown",
                             "date": "2027-01-04", "from": "2027-01-02"}]
    # a takedown visit before the cutoff never moves the install date
    assert out["early"]["m crowd lakewood"] == {"name": "M Crowd Lakewood", "id": 7, "install": "2026-11-02"}


def test_only_the_install_row_speaks_for_the_client():
    out = json.loads(run_js(fns("normName", "extraVisitRow") + """
      const C={65:{name:'M Crowd Lakewood'}, 900011:{name:'m crowd lakewood', visitType:'Takedown'},
               117:{name:'William Brothers-NRG'}, 900004:{name:'William Brothers-NRG — TEARDOWN', visitType:'Takedown'},
               900020:{name:'Solo Takedown', visitType:'Takedown'}};
      console.log(JSON.stringify([65, 900011, 117, 900004, 900020].map(r=>extraVisitRow(r, C))));
    """))
    assert out == [False, True, False, False, False]
    snap = js_function("snapshot")
    assert "[...notInstalling].filter(speaksForClient)" in snap
    assert "[...hold].filter(speaksForClient)" in snap
    assert "if(!speaksForClient(r)) return;" in snap
    assert "extraVisitRow(r, C)" in js_function("buildBillingRows")


SYNC = fns("normName", "sameNewClient", "syncSyntheticName", "restoreSyntheticClients", "syncBlockedBy") + """
const C={65:{row:65, name:'M Crowd Lakewood', street:'2 B St'}};
let nextSyntheticRow=900001, syncBlocked=false, clientDirectory=null, sharedBase=null;
const banners=[];
function showSyncBanner(o){ banners.push(o); }
function addSyntheticClientSync(d){ C[d.row]={...d, synthetic:true, h26:d.hours}; return d.row; }
const clone=x=>JSON.parse(JSON.stringify(x));
const TD={row:900011, name:'M Crowd Lakewood', street:'2 B St', visitType:'Takedown', hours:1.2};
"""


def test_takedown_row_under_the_install_name_does_not_block_sync():
    out = json.loads(run_js(SYNC + """
      restoreSyntheticClients([clone(TD)]);
      sharedBase={at:'t1', state:{newClients:[clone(TD)]}};
      const saved=syncBlockedBy({state:{newClients:[clone(TD)]}});
      // This tab adds the takedown; another tab saved a Standard visit at that row.
      const mine={...TD, row:900012};
      addSyntheticClientSync(mine);
      const other=syncBlockedBy({state:{newClients:[clone(TD), {...mine, visitType:'Standard', name:'M Crowd Lakewood'}]}});
      console.log(JSON.stringify({saved, other, names:Object.values(C).map(c=>c.name)}));
    """))
    assert out["saved"] is False
    assert out["other"] is True
    assert out["names"] == ["M Crowd Lakewood", "M Crowd Lakewood", "M Crowd Lakewood"]
