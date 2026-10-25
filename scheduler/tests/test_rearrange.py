"""Rearranging whole crew-days on the Install Schedule (review_template.html).

10/24/2026: "if I were to try to drag crew one to another day, it wouldn't let
me do it because there's already three crews on every day. But someone's going
to need the flexibility to edit, try, and rearrange." A crew-day dropped on a
full date now offers a SWAP with a crew already there (each group keeps its
stops, in order) or a 4th crew (allowed, flagged); a joint day travels with its
partner; "Try changes" holds a private draft until Apply saves it as one change.
These run the template's own functions in node. Names are made up.
"""
import json
import os
import re
import shutil
import sys

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def fns(*names):
    return "\n".join(js_function(n) for n in names)


BOARD = """
const K={NIGHT:450, DAY_CAP:600, CREWS:['Crew 1','Crew 2','Crew 3']};
const MAX_CREWS=3;
const DALLAS=new Set(['2026-11-02','2026-11-03','2026-11-04','2026-11-05']);
function isDallasDate(dt){ return DALLAS.has(dt); }
function addDays(s,n){ const d=new Date(s+'T12:00:00Z'); d.setUTCDate(d.getUTCDate()+n); return d.toISOString().slice(0,10); }
function fmtDate(s){ return s; }
const C={1:{name:'Lake Spot'}, 2:{name:'Lakewood Spot'}, 3:{name:'Uptown Spot'}, 4:{name:'Corporate'},
         5:{name:'Allen Spot'}, 6:{name:'District Spot'}, 7:{name:'Rockwall Spot'}, 8:{name:'Galleria Spot'},
         9:{name:'Colinas Spot'}, 10:{name:'Forest Spot'}, 11:{name:'Mercury Spot'},
         20:{name:'Houston A'}, 21:{name:'Houston B'}, 22:{name:'Houston C'}, 23:{name:'Houston D'}};
let days=[], staffing={}, crewNames={}, shiftNotes={}, manualOrder={}, approved=new Set(), moves=[];
const mk=(id, stops, extra)=>{ const [date,crew]=id.split('|'); return {id, date, crew, stops, half:[], win:450, ...(extra||{})}; };
function dayById(id, create){
  let d=days.find(x=>x.id===id); if(d || !create) return d;
  const [date,crew]=id.split('|'); d={id, date, crew, stops:[], half:[], win:isDallasDate(date)?450:600}; days.push(d); return d;
}
""" + fns("isCrewName", "spareCrewOn", "crewCountOn", "linkedDays", "rearrangeOptions", "swapKeys",
          "rearrangeDates", "exchangeCrewDays", "crewLabel", "byCrew", "isDallasNight", "dallasRunStart",
          "shiftKeyOf", "crewNameKey", "shiftNoteKey", "jointStopName", "draftLocations", "draftLocText",
          "draftLocKey", "draftDiff") + """
// The Dallas week as it was on 10/24 (stand-in rows): Mon Crew 1 + Crew 2 are
// a joint pair sharing row 1; Wed has three single crews.
function dallasWeek(){
  days=[mk('2026-11-02|Crew 1|0',[1,2]), mk('2026-11-02|Crew 2|0',[1,3]), mk('2026-11-02|Crew 3|0',[4]),
        mk('2026-11-04|Crew 1|0',[5,6]), mk('2026-11-04|Crew 2|0',[7,8]), mk('2026-11-04|Crew 3|0',[9,10,11])];
}
const ids=list=>list.map(d=>d.id);
const where=()=>Object.fromEntries(days.map(d=>[d.id, d.stops]));
"""


def run(body):
    return json.loads(run_js(BOARD + body))


def test_crew_helpers():
    out = run("""
      dallasWeek();
      console.log(JSON.stringify({
        crews:['Crew 1','Crew 4','Crew 12','Crew 0','Crew 1 + Crew 2 (stacked)','Training',''].map(isCrewName),
        spareFull:spareCrewOn(days,'2026-11-04'), sparePromised:spareCrewOn(days,'2026-11-04',['Crew 4']),
        spareGap:spareCrewOn([mk('2026-12-01|Crew 1|0',[20]), mk('2026-12-01|Crew 3|0',[21])],'2026-12-01'),
        count:crewCountOn(days,'2026-11-02'), countEmpty:crewCountOn(days,'2026-11-09'),
        linked:ids(linkedDays(days[1], days)), alone:ids(linkedDays(days[2], days)),
        swapped:swapKeys({a:1, c:3}, 'a', 'b')}));
    """)
    assert out["crews"] == [True, True, True, False, False, False, False]
    assert (out["spareFull"], out["sparePromised"], out["spareGap"]) == ("Crew 4", "Crew 5", "Crew 2")
    assert (out["count"], out["countEmpty"]) == (3, 0)
    assert out["linked"] == ["2026-11-02|Crew 1|0", "2026-11-02|Crew 2|0"]
    assert out["alone"] == ["2026-11-02|Crew 3|0"]
    assert out["swapped"] == {"b": 1, "c": 3}


def test_a_full_date_offers_swaps_and_a_4th_crew_never_a_refusal():
    out = run("""
      dallasWeek();
      const single=rearrangeOptions(days[2], '2026-11-04', days);    // Mon Crew 3 -> Wed (3 crews)
      const joint=rearrangeOptions(days[0], '2026-11-04', days);     // the joint pair -> Wed
      const same=rearrangeOptions(days[3], '2026-11-04', days);      // Wed Crew 1 on its own date
      console.log(JSON.stringify({single, joint, same}));
    """)
    single = out["single"]
    assert [o["kind"] for o in single] == ["swap", "swap", "swap", "move"]
    assert [o["pairs"] for o in single[:3]] == [[["2026-11-02|Crew 3|0", f"2026-11-04|Crew {n}|0"]] for n in (1, 2, 3)]
    # Crew 3 is taken on Wed, so the move lands on a 4th crew.
    assert single[3] == {"kind": "move", "pairs": [["2026-11-02|Crew 3|0", "2026-11-04|Crew 4|0"]], "crews": ["Crew 4"]}
    # The joint pair travels together: swapped two-for-two, or moved as crews 4 and 5.
    joint = out["joint"]
    assert [o["pairs"] for o in joint if o["kind"] == "swap"] == [
        [["2026-11-02|Crew 1|0", "2026-11-04|Crew 1|0"], ["2026-11-02|Crew 2|0", "2026-11-04|Crew 2|0"]],
        [["2026-11-02|Crew 1|0", "2026-11-04|Crew 1|0"], ["2026-11-02|Crew 2|0", "2026-11-04|Crew 3|0"]],
        [["2026-11-02|Crew 1|0", "2026-11-04|Crew 2|0"], ["2026-11-02|Crew 2|0", "2026-11-04|Crew 3|0"]]]
    assert joint[-1]["crews"] == ["Crew 4", "Crew 5"]
    # Same date: swap crew numbers with each other crew, no move.
    assert [o["pairs"][0][1] for o in out["same"]] == ["2026-11-04|Crew 2|0", "2026-11-04|Crew 3|0"]
    assert all(o["kind"] == "swap" for o in out["same"])


def test_a_swap_never_splits_a_joint_group_on_the_other_date():
    out = run("""
      dallasWeek();
      // Wed Crew 1 and Crew 2 now share a stop: a single crew-day can only swap with Crew 3.
      days[4].stops=[5,7,8];
      const o=rearrangeOptions(days[2], '2026-11-04', days);
      console.log(JSON.stringify(o.map(x=>x.pairs.map(p=>p[1]))));
    """)
    assert out == [["2026-11-04|Crew 3|0"], ["2026-11-04|Crew 4|0"]]


def test_move_keeps_the_crew_number_when_it_is_free():
    out = run("""
      days=[mk('2026-11-02|Crew 3|0',[4]), mk('2026-11-05|Crew 1|0',[5])];
      console.log(JSON.stringify(rearrangeOptions(days[0], '2026-11-05', days)));
    """)
    assert out == [{"kind": "swap", "pairs": [["2026-11-02|Crew 3|0", "2026-11-05|Crew 1|0"]]},
                   {"kind": "move", "pairs": [["2026-11-02|Crew 3|0", "2026-11-05|Crew 3|0"]], "crews": ["Crew 3"]}]


def test_swap_trades_stops_in_order_and_touches_nothing_else():
    out = run("""
      days=[mk('2026-12-01|Crew 1|0',[20,21], {win:600}), mk('2026-12-01|Crew 2|0',[22], {win:600}),
            mk('2026-12-03|Crew 1|0',[23], {win:600}), mk('2026-12-04|Crew 1|0',[5], {win:600})];
      staffing={'2026-12-01|Crew 1|0':['p1'], '2026-12-03|Crew 1|0':['p2'], '2026-12-04|Crew 1|0':['p9']};
      crewNames={'2026-12-01|Crew 1|0':'Lesly crew'};
      shiftNotes={'2026-12-03|Crew 1|0':{text:'gate code'}};
      manualOrder={'2026-12-01|Crew 1|0':[21,20]};
      approved=new Set(['2026-12-01|Crew 1|0','2026-12-04|Crew 1|0']);
      days[0].stops=[21,20];          // as drawn (hand order)
      const untouched=JSON.stringify(days[3]);
      exchangeCrewDays([['2026-12-01|Crew 1|0','2026-12-03|Crew 1|0']]);
      console.log(JSON.stringify({where:where(), staffing, crewNames, shiftNotes, manualOrder,
        approved:[...approved], moves, untouched: untouched===JSON.stringify(days.find(d=>d.id==='2026-12-04|Crew 1|0'))}));
    """)
    assert out["where"] == {"2026-12-01|Crew 1|0": [23], "2026-12-01|Crew 2|0": [22],
                            "2026-12-03|Crew 1|0": [21, 20], "2026-12-04|Crew 1|0": [5]}
    # Houston: the people, name and note go with the itinerary.
    assert out["staffing"] == {"2026-12-01|Crew 1|0": ["p2"], "2026-12-03|Crew 1|0": ["p1"], "2026-12-04|Crew 1|0": ["p9"]}
    assert out["crewNames"] == {"2026-12-03|Crew 1|0": "Lesly crew"}
    assert out["shiftNotes"] == {"2026-12-01|Crew 1|0": {"text": "gate code"}}
    # Each itinerary keeps its sequence.
    assert out["manualOrder"] == {"2026-12-01|Crew 1|0": [23], "2026-12-03|Crew 1|0": [21, 20]}
    assert out["approved"] == ["2026-12-04|Crew 1|0"]
    assert out["untouched"] is True
    assert out["moves"] == [{"row": None, "name": "2026-12-01 Crew 1 swapped with 2026-12-03 Crew 1",
                             "from": "2026-12-01|Crew 1|0", "to": "2026-12-03|Crew 1|0"}]


def test_dallas_swap_keeps_the_weeks_people_and_moves_the_joint_pair():
    out = run("""
      dallasWeek();
      staffing={'2026-11-02|Crew 1|0':['p1'], '2026-11-04|Crew 1|0':['p4'], '2026-11-04|Crew 3|0':['p3']};
      const opt=rearrangeOptions(days[0], '2026-11-04', days)[0];
      exchangeCrewDays(opt.pairs);
      console.log(JSON.stringify({where:where(), staffing}));
    """)
    assert out["where"] == {"2026-11-02|Crew 1|0": [5, 6], "2026-11-02|Crew 2|0": [7, 8], "2026-11-02|Crew 3|0": [4],
                            "2026-11-04|Crew 1|0": [1, 2], "2026-11-04|Crew 2|0": [1, 3], "2026-11-04|Crew 3|0": [9, 10, 11]}
    # A Dallas week is staffed a week at a time: swapping nights leaves people put.
    assert out["staffing"] == {"2026-11-02|Crew 1|0": ["p1"], "2026-11-04|Crew 1|0": ["p4"], "2026-11-04|Crew 3|0": ["p3"]}


def test_a_4th_crew_move_creates_the_day_and_empties_the_old_one():
    out = run("""
      dallasWeek();
      staffing={'2026-11-02|Crew 3|0':['p7']};
      const opt=rearrangeOptions(days[2], '2026-11-04', days).find(o=>o.kind==='move');
      exchangeCrewDays(opt.pairs);
      console.log(JSON.stringify({ids:ids(days), staffing, crews:crewCountOn(days,'2026-11-04'),
                                  label:crewLabel(days.find(d=>d.id==='2026-11-04|Crew 4|0'))}));
    """)
    assert "2026-11-02|Crew 3|0" not in out["ids"] and "2026-11-04|Crew 4|0" in out["ids"]
    # The day moved to a new crew-day, so its people go with it (nothing to keep them on).
    assert out["staffing"] == {"2026-11-04|Crew 4|0": ["p7"]}
    assert (out["crews"], out["label"]) == (4, "Crew 4")


def test_compare_lists_only_stops_whose_date_or_crew_changed():
    out = run("""
      dallasWeek();
      const before=draftLocations();
      exchangeCrewDays([['2026-11-02|Crew 3|0','2026-11-04|Crew 3|0']]);
      // a stop that goes away and comes back is not a change
      exchangeCrewDays([['2026-11-04|Crew 1|0','2026-11-04|Crew 2|0']]);
      exchangeCrewDays([['2026-11-04|Crew 1|0','2026-11-04|Crew 2|0']]);
      const diff=draftDiff(before, draftLocations(), r=>C[r].name);
      console.log(JSON.stringify({names:diff.map(x=>x.name),
        lines:diff.map(x=>[draftLocText(x.before, fmtDate), draftLocText(x.after, fmtDate)]),
        joint:draftLocText(before[1], fmtDate), gone:draftLocText(undefined, fmtDate)}));
    """)
    # by new date, then name
    assert out["names"] == ["Colinas Spot", "Forest Spot", "Mercury Spot", "Corporate"]
    assert out["lines"][0] == ["2026-11-04 Crew 3, stop 1 of 3", "2026-11-02 Crew 3, stop 1 of 3"]
    assert out["lines"][3] == ["2026-11-02 Crew 3, stop 1 of 1", "2026-11-04 Crew 3, stop 1 of 1"]
    assert out["joint"] == "2026-11-02 Crew 1 + Crew 2"
    assert out["gone"] == "Not on the board"


DRAFT_HARNESS = """
let READONLY=false, DRAFT=null, undoStack=['u1'], redoStack=['r1'], undoSeq=0, state='S0', calls=[];
const UNDO_LIMIT=100;
function roBlocked(){ return READONLY; }
function stateBlob(){ return state; }
function restoreBlob(b){ state=b; calls.push('restore:'+b); }
function persist(){ calls.push(DRAFT ? 'persist-in-draft' : 'persist'); }
function render(){ calls.push('render'); }
function pullShared(){ calls.push('pull'); }
function draftLocations(){ return {}; }
""" + fns("startDraft", "applyDraft", "discardDraft", "draftChangeCount", "pushUndo")


def test_apply_saves_the_whole_draft_as_one_undo_step():
    out = json.loads(run_js(DRAFT_HARNESS + """
      startDraft();
      const inDraft={undo:[...undoStack], redo:[...redoStack]};
      pushUndo(); state='S1'; pushUndo(); state='S2';
      const n=draftChangeCount();
      applyDraft();
      console.log(JSON.stringify({inDraft, n, undo:undoStack, redo:redoStack, state, draft:DRAFT, calls}));
    """))
    assert out["inDraft"] == {"undo": [], "redo": []}     # draft steps are its own
    assert out["n"] == 2
    assert out["undo"] == ["u1", "S0"]                      # one step back to before the draft
    assert out["redo"] == [] and out["state"] == "S2" and out["draft"] is None
    assert out["calls"].count("persist") == 1               # one save, through persist()


def test_discard_puts_the_board_back_and_saves_nothing():
    out = json.loads(run_js(DRAFT_HARNESS + """
      startDraft(); pushUndo(); state='S1';
      discardDraft();
      console.log(JSON.stringify({undo:undoStack, redo:redoStack, state, draft:DRAFT, calls}));
    """))
    assert out["state"] == "S0" and out["draft"] is None
    assert out["undo"] == ["u1"] and out["redo"] == ["r1"]
    assert "persist" not in out["calls"] and "restore:S0" in out["calls"]
    assert out["calls"][-1] == "pull"                       # catch up on others' saves


def test_read_only_cannot_start_a_draft_and_an_unchanged_draft_just_ends():
    out = json.loads(run_js(DRAFT_HARNESS + """
      READONLY=true; startDraft(); const ro=DRAFT;
      READONLY=false; startDraft(); applyDraft();
      console.log(JSON.stringify({ro, draft:DRAFT, calls}));
    """))
    assert out["ro"] is None and out["draft"] is None
    assert "persist" not in out["calls"]


def test_nothing_leaves_the_tab_during_a_draft():
    assert "if(DRAFT) return;" in js_function("persist")
    assert "if(READONLY || DRAFT) return;" in js_function("saveLocal")
    assert "if(!AUTH || DRAFT) return;" in js_function("pullSharedNow")
    assert "if(DRAFT) return false;" in js_function("putShared")
    for fn in ("restoreHistoryEntry", "resetAll"):
        assert "if(DRAFT){" in js_function(fn), fn
    # warnings show in the banner instead of a pop-up per move
    commit = TEMPLATE[TEMPLATE.index("function commitPlan("):]
    commit = commit[:commit.index("\n}\n")]
    assert "chk.warnings.length && !DRAFT && !confirm(" in commit
    # Apply goes through the normal save path (the stale-tab merge lives in putShared)
    assert "persist();" in js_function("applyDraft")
    assert "btn.hidden=!!READONLY;" in js_function("syncDraftUI")
    assert "syncDraftUI();" in js_function("syncToolbar")


def test_wiring_and_no_more_three_crew_refusal():
    assert "alert(`Every crew already has a day" not in TEMPLATE
    assert "openRearrange(dayId, toDate);" in js_function("moveWholeDay")
    card = js_function("buildDayCard")
    assert "openRearrange(dayid, d.date, d.id)" in card and "mvdaybtn" in card
    assert "if(!isOverview(val)) openRearrange(dayid,val);" in TEMPLATE
    # an extra crew survives reloads/undo and runs as a Dallas night there
    assert "!isCrewName(crew)" in js_function("applyPlacement")
    assert "isCrewName(crew)" in js_function("metaFor")
    # the move dialog always offers a new crew; checkPlan flags a 4th
    assert "spareCrewOn(days, dt)" in TEMPLATE and "code:'CREWS'" in js_function("checkPlan")
    assert "spareCrewOn(days, date, pendingSlots[date]||[])" in js_function("buildAddCrewButton")
    # the chooser previews on a scratch copy and applies as one undo step
    assert "withScratch(" in js_function("previewRearrange")
    src = js_function("applyRearrange")
    assert src.index("pushUndo();") < src.index("exchangeCrewDays(") < src.index("persist();")
    assert 'id="tbdraft"' in TEMPLATE and 'id="draftbanner"' in TEMPLATE and 'id="rrdlg"' in TEMPLATE


def test_new_user_facing_text_has_no_em_dashes_or_hardcoded_dates():
    for fn in ("rearrangeLabel", "renderRearrangeOpts", "openRearrange", "rearrangeBlockers", "boardWarningsFor",
               "syncDraftUI", "openDraftCompare", "exchangeCrewDays", "draftLocText"):
        src = js_function(fn)
        assert "—" not in src, fn
        assert not re.search(r"20\d\d-\d\d", src), fn


def test_notebook_freeze_keeps_an_extra_crew():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import board_state
    payload = {"spec": {"const": {"CREWS": ["Crew 1", "Crew 2", "Crew 3"], "DAY_CAP": 600, "LUNCH": 40},
                        "calendar": [{"date": "2026-12-01"}], "dayMeta": {}},
               "clients": {"20": {"name": "Houston A"}, "21": {"name": "Houston B"}},
               "days": [{"id": "2026-12-01|Crew 1|0", "date": "2026-12-01", "crew": "Crew 1", "stops": [20]}]}
    state = {"placement": {"20": ["2026-12-01|Crew 1|0"], "21": ["2026-12-01|Crew 4|0"]}}
    nb, report = board_state.notebook_from_board(payload, state)
    assert report["bad_days"] == []
    assert sorted((d["crew"], d["stops"]) for d in nb["days"]) == [("Crew 1", ["Houston A"]), ("Crew 4", ["Houston B"])]
