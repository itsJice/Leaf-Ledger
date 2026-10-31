"""Adding and removing a crew on one stop (review_template.html).

10/30/2026: "make a way to make a property or stop a dual crew thing". From a
stop's card (Crews) staff add a second crew working that date (or a new crew)
so two or more crews work the stop together, and take one off again. A joint
stop is a row on two or more crew-days the same date; its hours, staffing need
and Trailer Loader boxes split across the crews. At least one crew always keeps
the stop, the date never changes here, and every change is one undo step.
These run the template's own functions in node. Names are made up.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

FNS = ("dynamicJoints", "jointShares", "jointN", "effH", "crewDaysOf", "jointCrewChoices",
       "jointRemoveBlock", "crewsLogId", "clearLoadSplit", "addJointCrew", "removeJointCrew",
       "peekCrewsHTML", "spareCrewOn", "isCrewName", "byCrew", "crewLabel", "withLoadStop",
       "stopShares", "dayNeed")

BOARD = """
const K={CREWS:['Crew 1','Crew 2','Crew 3']};
const C={1:{name:'Lakeside Spot', h26:6, roleNeed:{leads:1, general:6}},
         2:{name:'Other Spot', h26:3, roleNeed:{leads:1, general:2}},
         3:{name:'Third Spot', h26:4, roleNeed:{leads:1, general:2}}};
const CREW_COLORS={}, IC={link:'<i></i>'};
let READONLY=false, days=[], approved=new Set(), notInstalling=new Set(), moves=[], loadStops={},
    undoStack=[], confirms=[], alerts=[], saves=0, renders=0;
function roBlocked(){ return READONLY; }
function pushUndo(){ undoStack.push(JSON.stringify({days, loadStops})); }
function undo(){ const s=JSON.parse(undoStack.pop()); days=s.days; loadStops=s.loadStops; refresh(); }
function persist(){ saves++; }
function render(){ renders++; refresh(); }
function confirm(m){ confirms.push(m); return true; }
function alert(m){ alerts.push(m); }
function crewTitle(d){ return crewLabel(d); }
function fmtMDYYYY(s){ return s; }
function peekEsc(s){ return String(s); }
function pkSection(cls, title, body){ return `<section class="${cls}"><b>${title}</b>${body}</section>`; }
function jointStopName(r){ return C[r].name; }
function hydrate(d){ return {...d, stops:[...d.stops], half:[], joint:'', win:600}; }
function dayById(id, create){
  let d=days.find(x=>x.id===id); if(d || !create) return d;
  const [date,crew]=id.split('|'); d=hydrate({id, date, crew, stops:[]}); days.push(d); return d;
}
function dayCalc(d){ return {total:60*d.stops.reduce((a,r)=>a+effH(d,r),0)}; }
function refresh(){
  const j=dynamicJoints(days, ()=>false, crewLabel), sh=jointShares(days);
  days.forEach(d=>{ Object.assign(d, j[d.id]||{half:[], joint:''}); d.share=sh[d.id]||{}; });
}
const mk=(id, stops)=>{ const [date,crew]=id.split('|'); return {id, date, crew, stops, half:[], joint:'', win:600}; };
const SPEC={calendar:[]};
""" + "\n".join(js_function(n) for n in FNS) + """
function board(){
  days=[mk('2026-11-04|Crew 1|0',[1,2]), mk('2026-11-04|Crew 2|0',[3]), mk('2026-11-05|Crew 1|0',[2])];
  refresh();
}
const place=()=>{ const m={}; days.forEach(d=>d.stops.forEach(r=>(m[r]=m[r]||[]).push(d.id))); return m; };
const hrs=id=>{ const d=days.find(x=>x.id===id); return d ? dayCalc(d).total/60 : null; };
"""


def run(body):
    return json.loads(run_js(BOARD + body))


def test_add_a_second_crew_splits_the_hours_and_remove_puts_it_back():
    out = run("""
      board();
      const before=place();
      const choices=jointCrewChoices(1, '2026-11-04', days).map(o=>[o.id, o.isNew]);
      const added=addJointCrew(1, '2026-11-04|Crew 2|0');
      const joint={place:place(), h1:hrs('2026-11-04|Crew 1|0'), h2:hrs('2026-11-04|Crew 2|0'),
                   badge:days[0].joint, log:moves[moves.length-1]};
      const removed=removeJointCrew(1, '2026-11-04|Crew 2|0');
      console.log(JSON.stringify({before, choices, added, joint, removed, after:place(),
        h1:hrs('2026-11-04|Crew 1|0'), h2:hrs('2026-11-04|Crew 2|0'), undos:undoStack.length, saves}));
    """)
    assert out["choices"] == [["2026-11-04|Crew 2|0", False], ["2026-11-04|Crew 3|0", True]]
    assert out["added"] is True
    assert out["joint"]["place"]["1"] == ["2026-11-04|Crew 1|0", "2026-11-04|Crew 2|0"]
    assert out["joint"]["h1"] == 3 + 3 and out["joint"]["h2"] == 4 + 3   # 6h job, half each
    assert out["joint"]["badge"] == "Crew 2"
    assert out["joint"]["log"] == {"row": 1, "name": "Lakeside Spot",
                                   "from": "CREWS:2026-11-04|Crew 1|0",
                                   "to": "CREWS:2026-11-04|Crew 1|0+2026-11-04|Crew 2|0"}
    assert out["removed"] is True and out["after"] == out["before"]
    assert out["h1"] == 9 and out["h2"] == 4
    assert out["undos"] == 2 and out["saves"] == 2


def test_undo_takes_the_crew_back_off():
    out = run("""
      board(); const before=place();
      addJointCrew(1, '2026-11-04|Crew 2|0'); undo();
      console.log(JSON.stringify({same:JSON.stringify(place())===JSON.stringify(before),
        half:days.map(d=>d.half)}));
    """)
    assert out == {"same": True, "half": [[], [], []]}


def test_a_stop_always_keeps_one_crew():
    out = run("""
      board();
      const ok=removeJointCrew(1, '2026-11-04|Crew 1|0');
      console.log(JSON.stringify({ok, alerts, place:place(), why:jointRemoveBlock(1, '2026-11-04|Crew 1|0', days)}));
    """)
    assert out["ok"] is False and out["alerts"] == ["A stop always keeps at least one crew."]
    assert out["place"]["1"] == ["2026-11-04|Crew 1|0"]


def test_only_the_same_date_and_never_twice():
    out = run("""
      board();
      const other=addJointCrew(1, '2026-11-05|Crew 1|0');   // another date: no
      const self=addJointCrew(1, '2026-11-04|Crew 1|0');    // already on it: no
      console.log(JSON.stringify({other, self, place:place(), undos:undoStack.length}));
    """)
    assert out["other"] is False and out["self"] is False
    assert out["place"]["1"] == ["2026-11-04|Crew 1|0"] and out["undos"] == 0


def test_a_new_crew_and_three_crews_split_three_ways():
    out = run("""
      board();
      addJointCrew(1, '2026-11-04|Crew 2|0');
      addJointCrew(1, '2026-11-04|Crew 3|0');                 // a new crew-day
      const d3=days.find(x=>x.id==='2026-11-04|Crew 3|0');
      const need=dayNeed(d3);
      console.log(JSON.stringify({ids:place()['1'], each:effH(d3, 1), n:jointN(d3, 1), joint:d3.joint, need:need.gen}));
    """)
    assert out["ids"] == ["2026-11-04|Crew 1|0", "2026-11-04|Crew 2|0", "2026-11-04|Crew 3|0"]
    assert out["each"] == 2 and out["n"] == 3 and out["joint"] == "Crew 1 + Crew 2"
    assert out["need"] == 2   # 6 general installers over three crews


def test_removing_a_crews_only_stop_takes_its_day_off_the_board():
    out = run("""
      days=[mk('2026-11-04|Crew 1|0',[1]), mk('2026-11-04|Crew 2|0',[1])]; refresh();
      approved.add('2026-11-04|Crew 1|0');
      removeJointCrew(1, '2026-11-04|Crew 2|0');
      console.log(JSON.stringify({ids:days.map(d=>d.id), approved:[...approved], confirm:confirms.length}));
    """)
    assert out["ids"] == ["2026-11-04|Crew 1|0"]
    assert out["approved"] == []   # a changed day needs approving again


def test_trailer_split_resets_to_even_when_the_crews_change():
    out = run("""
      days=[mk('2026-11-04|Crew 1|0',[1]), mk('2026-11-04|Crew 2|0',[1])]; refresh();
      loadStops={'1':{notReady:true, split:{'2026-11-04|Crew 1|0':30}}};
      addJointCrew(1, '2026-11-04|Crew 3|0');
      const ids=crewDaysOf(1, '2026-11-04', days).map(d=>d.id);
      console.log(JSON.stringify({ls:loadStops, shares:stopShares(ids, 39, (loadStops['1']||{}).split)}));
    """)
    assert out["ls"] == {"1": {"notReady": True}}
    assert sorted(out["shares"].values()) == [13, 13, 13]


def test_read_only_viewers_see_the_crews_but_cannot_change_them():
    out = run("""
      days=[mk('2026-11-04|Crew 1|0',[1]), mk('2026-11-04|Crew 2|0',[1,3])]; refresh();
      const edit=peekCrewsHTML(1, days[0]);
      READONLY=true;
      const view=peekCrewsHTML(1, days[0]);
      const add=addJointCrew(3, '2026-11-04|Crew 1|0'), rm=removeJointCrew(1, '2026-11-04|Crew 2|0');
      console.log(JSON.stringify({edit, view, add, rm, undos:undoStack.length, place:place()}));
    """)
    assert "data-crewrm" in out["edit"] and "pkcrewpick" in out["edit"] and "2 crews" in out["edit"]
    assert "data-crewrm" not in out["view"] and "pkcrewpick" not in out["view"]
    assert "Crew 1" in out["view"] and "Crew 2" in out["view"]
    assert out["add"] is False and out["rm"] is False and out["undos"] == 0
    assert out["place"]["1"] == ["2026-11-04|Crew 1|0", "2026-11-04|Crew 2|0"]


def test_the_stop_card_and_log_are_wired():
    assert "${peekCrewsHTML(row, d)}" in TEMPLATE
    assert "wirePeekCrews(row);" in TEMPLATE
    assert "id.startsWith('CREWS:')" in TEMPLATE   # Session changes reads the log line
