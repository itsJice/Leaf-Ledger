"""Joint shifts on the Staffing view (review_template.html).

10/24/2026, looking at Thu 11/12 where Crew 1 and Crew 2 share all three
stops: "if there are two crews assigned to these days and I assign the
people to crew one, then they need to be represented on crew two as well."
Crew-days on one date working exactly the same stops are ONE shift: one card,
the need added up, one crew list, and staffing it writes the same people to
every crew-day in it (like a Dallas week writes every night). A crew-day
that shares only some stops stays its own shift and says what it shares.
These run the template's own functions in node. Names are made up.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

FNS = ("jointShiftGroups", "jointStaffingState", "sharedStopsOutside", "staffingUnified", "staffingDiffers",
       "unifyJointStaffing", "jointPartnersOf", "shiftShareNotes", "jointStopName",
       "staffingWith", "staffingWithout", "staffingCleared", "buildShifts", "shiftLabelOf",
       "shiftKeyOf", "isDallasNight", "dallasRunStart", "crewLabel", "byCrew", "crewNameKey",
       "crewName", "crewTitle", "shiftFor", "shiftOfDay", "shiftNeed", "shiftCoverage",
       "dayNeed", "coverageLabel", "clashesFor")

BOARD = """
const K={NIGHT:450, DAY_CAP:600, CREWS:['Crew 1','Crew 2','Crew 3']};
const DALLAS=new Set(['2026-11-02','2026-11-03']);
function isDallasDate(dt){ return DALLAS.has(dt); }
function addDays(s,n){ const d=new Date(s+'T12:00:00Z'); d.setUTCDate(d.getUTCDate()+n); return d.toISOString().slice(0,10); }
function dayCalc(d){ return {total: 60*(d.hrs||8), order:d.stops}; }
function fmtMDYYYY(s){ return s; }
const C={1:{name:'Bourque', roleNeed:{leads:1, general:6}, h26:6},
         2:{name:'Bergstrom', roleNeed:{leads:1, general:4}, h26:4},
         3:{name:'Cain', roleNeed:{leads:1, general:2}, h26:2},
         4:{name:'Other', roleNeed:{leads:1, general:3}, h26:5},
         5:{name:'Dallas Spot', roleNeed:{leads:1, general:3}, h26:5}};
let crewNames={}, staffing={};
const roster=[...Array(20)].map((_,i)=>({id:'p'+i, name:'P'+i, active:true,
  title: i<2 ? 'Lead' : 'General Installer'}));
function personById(id){ return roster.find(p=>p.id===id); }
const mk=(date, crew, stops, extra)=>({id:date+'|'+crew+'|0', date, crew, stops, half:[], win:600, ...(extra||{})});
let days=[];
""" + "\n".join(js_function(n) for n in FNS)


def run(body):
    return json.loads(run_js(BOARD + body))


def test_full_pair_is_one_joint_group_and_partial_is_not():
    out = run("""
      days=[mk('2026-11-12','Crew 1',[1,2,3]), mk('2026-11-12','Crew 2',[3,2,1]),
            mk('2026-11-13','Crew 1',[1,4]), mk('2026-11-13','Crew 2',[1,2])];
      console.log(JSON.stringify(jointShiftGroups(days, isDallasNight)));
    """)
    assert out == {"2026-11-12|Crew 1|0": "joint|2026-11-12|Crew 1|0+2026-11-12|Crew 2|0",
                   "2026-11-12|Crew 2|0": "joint|2026-11-12|Crew 1|0+2026-11-12|Crew 2|0"}


def test_three_crew_joint_and_a_partial_third():
    out = run("""
      days=[mk('2026-11-20','Crew 1',[1]), mk('2026-11-20','Crew 2',[1]), mk('2026-11-20','Crew 3',[1]),
            mk('2026-11-21','Crew 1',[1,2]), mk('2026-11-21','Crew 2',[1,2]), mk('2026-11-21','Crew 3',[1,4])];
      const g=jointShiftGroups(days, isDallasNight);
      console.log(JSON.stringify({g20:days.slice(0,3).map(d=>g[d.id]), g21:days.slice(3).map(d=>g[d.id]||null),
        share:sharedStopsOutside(days[5], days, x=>g[x.id]===g[days[5].id] && !!g[x.id]).map(s=>[s.row, s.days.map(d=>d.crew)])}));
    """)
    assert len(set(out["g20"])) == 1 and out["g20"][0].count("+") == 2
    assert out["g21"][0] == out["g21"][1] and out["g21"][0] and out["g21"][2] is None
    assert out["share"] == [[1, ["Crew 1", "Crew 2"]]]


def test_dallas_training_and_empty_days_are_never_joint():
    out = run("""
      days=[mk('2026-11-02','Crew 1',[5],{win:K.NIGHT}), mk('2026-11-02','Crew 2',[5],{win:K.NIGHT}),
            mk('2026-10-23','Training',[], {training:true}), mk('2026-10-23','Crew 1',[]), mk('2026-10-23','Crew 2',[])];
      const sh=buildShifts();
      console.log(JSON.stringify({g:jointShiftGroups(days, isDallasNight),
        keys:sh.map(s=>s.key), joint:sh.map(s=>s.joint)}));
    """)
    assert out["g"] == {}
    assert "dallas|2026-11-02|Crew 1" in out["keys"] and "dallas|2026-11-02|Crew 2" in out["keys"]
    assert not any(out["joint"])


def test_joint_card_need_label_and_union_of_one_sided_staffing():
    out = run("""
      days=[mk('2026-11-12','Crew 1',[1,2,3],{half:[1,2,3], hrs:7}), mk('2026-11-12','Crew 2',[1,2,3],{half:[1,2,3], hrs:6})];
      crewNames={'2026-11-12|Crew 1|0':'Lesly'};
      staffing={'2026-11-12|Crew 1|0':['p0','p2','p3']};      // staffed on one side only
      const shifts=buildShifts(), sh=shifts[0], cv=shiftCoverage(sh);
      console.log(JSON.stringify({n:shifts.length, label:sh.label, stops:sh.stops, hours:sh.hours,
        need:cv.need, d1:dayNeed(days[0]), who:cv.who.map(p=>p.id), label2:coverageLabel(cv),
        differs:staffingDiffers(staffing, sh.days.map(x=>x.id)),
        sameOnDay2:shiftOfDay(days[1]).key===sh.key, members:sh.members.map(m=>m.key)}));
    """)
    assert out["n"] == 1
    assert out["label"] == "Lesly (Crew 1) + Crew 2 · joint"
    assert out["stops"] == 3 and out["hours"] == 7
    # each crew carries half the shared jobs (ceil) and its own lead; joint = the sum
    assert out["d1"] == {"lead": 1, "assist": 0, "gen": 3, "total": 4}
    assert out["need"] == {"lead": 2, "assist": 0, "gen": 6, "total": 8}
    assert out["who"] == ["p0", "p2", "p3"]           # the union shows on the joint card
    # one Lead on the pair: each crew-day (its own van) still needs its lead
    assert out["label2"] == "SHORT 1 LEAD · short 5 total"
    assert out["differs"] is False                    # one side empty is not "different people"
    assert out["sameOnDay2"] is True
    assert out["members"] == ["2026-11-12|Crew 1|0", "2026-11-12|Crew 2|0"]   # crew names stay per crew-day


def test_staffing_a_joint_shift_writes_both_crew_days():
    out = run("""
      days=[mk('2026-11-12','Crew 1',[1,2,3]), mk('2026-11-12','Crew 2',[1,2,3])];
      staffing={'2026-11-12|Crew 1|0':['p0','p2']};
      const sh=buildShifts()[0], ids=sh.days.map(x=>x.id);
      // what every write path does: unify first, then write each crew-day
      unifyJointStaffing(sh);
      staffing=staffingWith(staffing, ids, ['p5']);
      const afterAdd=JSON.parse(JSON.stringify(staffing));
      unifyJointStaffing(sh);
      staffing=staffingWithout(staffing, ids, ['p2']);
      const afterRm=JSON.parse(JSON.stringify(staffing));
      console.log(JSON.stringify({afterAdd, afterRm, clash:clashesFor('p0')}));
    """)
    a, r = out["afterAdd"], out["afterRm"]
    assert sorted(a["2026-11-12|Crew 1|0"]) == sorted(a["2026-11-12|Crew 2|0"]) == ["p0", "p2", "p5"]
    assert sorted(r["2026-11-12|Crew 1|0"]) == sorted(r["2026-11-12|Crew 2|0"]) == ["p0", "p5"]
    assert out["clash"] == []                          # both crews of a joint shift is not double-booked


def test_different_people_on_each_side_flag_and_make_both_the_same():
    out = run("""
      const ids=['a','b'];
      const m={a:['p1','p2'], b:['p3']};
      console.log(JSON.stringify({d:staffingDiffers(m, ids), u:staffingUnified(m, ids),
        same:staffingDiffers({a:['p1','p2'], b:['p2','p1']}, ids), empty:staffingUnified({x:['p9']}, ids),
        st:[jointStaffingState(m, ids), jointStaffingState({a:['p1']}, ids), jointStaffingState({}, ids),
            jointStaffingState({a:['p1'], b:['p1']}, ids)]}));
    """)
    assert out["d"] is True and out["same"] is False
    assert out["u"] == {"a": ["p1", "p2", "p3"], "b": ["p1", "p2", "p3"]}
    assert out["empty"] == {"x": ["p9"]}
    assert out["st"] == ["differs", "partial", "same", "same"]


def test_partial_day_stays_separate_and_says_what_it_shares():
    out = run("""
      days=[mk('2026-11-13','Crew 1',[1,4]), mk('2026-11-13','Crew 2',[1,2])];
      const sh=buildShifts();
      console.log(JSON.stringify({n:sh.length, joint:sh.map(s=>s.joint), notes:sh.map(shiftShareNotes)}));
    """)
    assert out["n"] == 2 and out["joint"] == [False, False]
    assert out["notes"] == [["Shares Bourque with Crew 2"], ["Shares Bourque with Crew 1"]]


def test_dallas_week_still_one_block_with_max_need():
    out = run("""
      days=[mk('2026-11-02','Crew 1',[5],{win:K.NIGHT}), mk('2026-11-03','Crew 1',[1],{win:K.NIGHT})];
      const sh=buildShifts();
      console.log(JSON.stringify({n:sh.length, days:sh[0].days.length, need:shiftNeed(sh[0]).total, tail:sh[0].tail}));
    """)
    assert out == {"n": 1, "days": 2, "need": 7, "tail": "Dallas week"}


def test_every_staffing_write_path_unifies_a_joint_shift_first():
    for fn in ("crewShiftSection", "toggleTeamOnShift", "applyTeamToShift",
               "assignReadyRosterToShift", "drawStaffDlg", "renderStaffing"):
        assert "unifyJointStaffing(sh)" in js_function(fn), fn
    card = js_function("shiftCardHTML")
    assert "data-jointsync" in card and "Make both the same" in card and "shiftShareNotes(sh)" in card


def test_a_joint_shifts_note_is_kept_on_each_crew_day():
    src = "\n".join(js_function(n) for n in ("shiftNoteKeysFor", "shiftNoteOf", "withShiftNote", "normShiftNoteText"))
    out = json.loads(run_js(src + """
      let shiftNotes={}; const shiftNoteKey=d=>d.id;
      const key='joint|2026-11-12|Crew 1|0+2026-11-12|Crew 2|0';
      shiftNotes=shiftNoteKeysFor(key).reduce((m,k)=>withShiftNote(m,k,'Bring the lift','me','t'), shiftNotes);
      console.log(JSON.stringify({keys:Object.keys(shiftNotes), joint:shiftNoteOf(key).text,
        day2:shiftNoteOf({id:'2026-11-12|Crew 2|0', crew:'Crew 2'}).text, plain:shiftNoteKeysFor('a|b|0')}));
    """))
    assert out == {"keys": ["2026-11-12|Crew 1|0", "2026-11-12|Crew 2|0"], "joint": "Bring the lift",
                   "day2": "Bring the lift", "plain": ["a|b|0"]}
    assert "shiftNoteKeysFor(key).reduce(" in js_function("setShiftNote")
