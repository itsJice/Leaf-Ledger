"""The Install Schedule's stale-tab guard, page side (review_template.html).

10/8/2026: a server-side 1099 import (8:29 PM CT) added 23 roster people and
their contractor fields; a tab opened before it saved its whole state at
9:03 PM while sending mass texts and erased all of it. The server now refuses
a save built on an older document (409 + the current one) and the page
re-applies only what IT changed onto that (mergeShared) and saves again.
These run the template's own functions in node: the merge itself, and the
real save loop (putShared / rebaseOnto) against a fake server with the
backend's guard semantics.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def const_line(name):
    m = re.search(rf"^const {name}=.*$", TEMPLATE, re.M)
    assert m, name
    return m.group(0)


CONSTS = "\n".join(const_line(n) for n in ("SHARED_SET_KEYS", "SHARED_MAP_KEYS", "SHARED_KEYS"))
MERGE = CONSTS + "\nconst TEXT_LOG_MAX=5;\n" + "\n".join(
    js_function(n) for n in ("sharedDocOf", "stableJSON", "mergeShared"))
DATES = "\n".join(js_function(n) for n in ("boardDatesByClient", "boardDateMoves", "placementDayList"))


def run(body):
    return json.loads(run_js(MERGE + "\n" + DATES + "\n" + body))


# The 10/8 documents (FAKE people). Ana was inactive until the import turned
# her on; the import also added legal names/addresses and 23 new people.
SCENARIO = """
const P=(id,first,x)=>Object.assign({id, first, last:'Test', name:first+' Test', title:'General Installer',
  lang:'Both', gender:'Female', email:'', phone:'', notes:'', ratings:{}, texts:[], times:['day','night'],
  dates:['2026-10-26','2026-10-27'], active:true}, x||{});
const clone=x=>JSON.parse(JSON.stringify(x));
const BASE={placement:{'1':['2026-11-13|Crew 1|0'], '2':['2026-11-18|Crew 2|0']}, approved:[], moves:[],
  comments:{}, staffing:{}, newClients:[], roster:[P('p1','Ana',{active:false}), P('p2','Luis')]};
const IMPORT=clone(BASE);
Object.assign(IMPORT.roster[0], {active:true, legalName:'Ana Q Test', street:'1 Main St', city:'Houston',
  state:'TX', zip:'77002', tax1099:true});
Object.assign(IMPORT.roster[1], {legalName:'Luis R Test', directDeposit:true});
for(let i=3;i<=25;i++) IMPORT.roster.push(P('p'+i, 'New'+i, {legalName:'New'+i+' Legal', tax1099:true}));
const T1={at:'2026-10-09T02:03:00.000Z', lang:'en', body:'Can you work Oct 26?'};
const T2={at:'2026-10-09T02:03:05.000Z', lang:'es', body:'Puedes trabajar el 26 de octubre?'};
"""


def test_10_8_import_survives_a_stale_tab_sending_texts():
    out = run(SCENARIO + """
      const mine=clone(BASE);                     // the tab opened before the import...
      mine.roster[0].texts=[T1]; mine.roster[1].texts=[T2];   // ...sends the mass text
      const r=mergeShared(BASE, mine, IMPORT);
      console.log(JSON.stringify(r));
    """)
    st = out["state"]
    assert out["conflicts"] == [] and out["hard"] == [] and out["changed"] == 2
    roster = {p["id"]: p for p in st["roster"]}
    assert len(roster) == 25                                       # all 23 new people kept
    assert roster["p1"]["texts"][0]["body"] == "Can you work Oct 26?"
    assert roster["p2"]["texts"][0]["lang"] == "es"
    assert roster["p1"]["active"] is True                          # the activation kept
    assert roster["p1"]["legalName"] == "Ana Q Test" and roster["p1"]["tax1099"] is True
    assert roster["p2"]["legalName"] == "Luis R Test" and roster["p2"]["directDeposit"] is True
    assert roster["p25"]["legalName"] == "New25 Legal"


def test_nothing_changed_here_means_nothing_overwritten():
    out = run(SCENARIO + """
      const r=mergeShared(BASE, clone(BASE), IMPORT);
      console.log(JSON.stringify([r.changed, stableJSON(r.state)===stableJSON(IMPORT), r.conflicts]));
    """)
    assert out == [0, True, []]


SAVE_LOOP = """
// The real save loop, with the page's DOM/board stubbed: the board is one
// document, DOC; applying a document replaces it (as applySharedDoc does).
let DOC, sharedBase=null, syncedBoardDates=null, pendingBoardDates=null, syncState='local';
let undoStack=['old step'], redoStack=[], lastPushOk=null, syncBlocked=false;
const AUTH='token', READONLY=false, SPEC={version:'build-1'}, C={};
const CUT='2026-12-25';
const NAMES={1:'Jinks, Amy', 2:'Crane Worldwide'};
const info=r=>NAMES[r] ? {key:NAMES[r].toLowerCase(), name:NAMES[r], id:null} : null;
function snapshot(){ return clone({...DOC, season:'2026', savedAt:1}); }
function applySharedDoc(st){ DOC=clone({...DOC, ...sharedDocOf(st)}); return 0; }
function placementBoardDates(pl){ return boardDatesByClient(placementDayList(pl), CUT, info); }
function sharedSnapshot(){
  const cur=placementBoardDates(DOC.placement);
  const dateMoves=syncedBoardDates ? boardDateMoves(cur, syncedBoardDates) : [];
  if(!syncedBoardDates) syncedBoardDates=cur;
  pendingBoardDates=cur;
  return {...snapshot(), dateMoves};
}
function conflictLabel(kind,key){ return kind==='row' ? (NAMES[key]||key) : key; }
function render(){} function saveLocal(){} function syncToolbar(){}
const banners=[];
function showMergedBanner(j,res){ banners.push({by:j.updatedBy, conflicts:res.conflicts}); }
function showSyncBanner(o){ banners.push({title:o.title}); }
// The backend's guard (install_schedule.put_state), in miniature.
const server={doc:null, at:'2026-10-08T23:00:05.123456+00:00', by:'user-a', n:0, log:[]};
function serverWrite(doc, by){ server.doc=clone(doc); server.by=by; server.at='2026-10-09T01:29:00.'+(++server.n)+'+00:00'; }
async function fetch(url, init){
  const b=JSON.parse(init.body);
  const resp=(status, body)=>({status, ok:status===200, json:async()=>clone(body)});
  if(b.baseUpdatedAt!==server.at){
    server.log.push({status:409, base:b.baseUpdatedAt});
    return resp(409, {conflict:true, state:server.doc, updatedAt:server.at, updatedBy:server.by});
  }
  server.doc=clone(b.state); server.by='user-a'; server.at='2026-10-09T02:03:0'+(++server.n)+'+00:00';
  server.log.push({status:200, base:b.baseUpdatedAt, dateMoves:b.state.dateMoves});
  return resp(200, {ok:true, updatedAt:server.at});
}
""" + "\n".join(js_function(n) for n in ("rebaseOnto", "syncBlockedBy")) + "\nasync " + js_function("putShared") + """
function load(){        // what pullSharedNow does with GET /state
  DOC={}; rebaseOnto({state:clone(server.doc), updatedAt:server.at, updatedBy:server.by}, null, {});
}
"""


def test_10_8_through_the_real_save_loop():
    out = run(SCENARIO + SAVE_LOOP + """
      (async()=>{
        server.doc=clone(BASE);
        load();                                      // tab opens at 7:00 PM
        serverWrite(IMPORT, 'claude-1099-import');   // 8:29 PM import, tab still open
        DOC.roster[0].texts=[T1]; DOC.roster[1].texts=[T2];   // 9:03 PM mass text
        const ok=await putShared();
        console.log(JSON.stringify({ok, log:server.log, doc:server.doc, banners, undo:undoStack.length,
                                    base:sharedBase.at, at:server.at}));
      })();
    """)
    assert out["ok"] is True
    # Refused once (stale base), then saved on the import's stamp.
    assert [x["status"] for x in out["log"]] == [409, 200]
    assert out["log"][1]["base"] == "2026-10-09T01:29:00.1+00:00"
    roster = {p["id"]: p for p in out["doc"]["roster"]}
    assert len(roster) == 25
    assert roster["p1"]["texts"] == [{"at": "2026-10-09T02:03:00.000Z", "lang": "en",
                                      "body": "Can you work Oct 26?"}]
    assert roster["p2"]["texts"][0]["lang"] == "es"
    assert roster["p1"]["legalName"] == "Ana Q Test" and roster["p1"]["active"] is True
    assert roster["p7"]["legalName"] == "New7 Legal"
    # The user is told; old undo steps (which hold the stale copy) are gone;
    # the next save builds on what was just saved.
    assert out["banners"] == [{"by": "claude-1099-import", "conflicts": []}]
    assert out["undo"] == 0
    assert out["base"] == out["at"]


def test_a_stale_tab_never_drags_a_newer_move_back_or_onto_the_card():
    out = run(SCENARIO + SAVE_LOOP + """
      (async()=>{
        server.doc=clone(BASE);
        load();
        // Another tab moves Amy from 11/13 to 11/16 (its save wrote the card).
        serverWrite({...clone(BASE), placement:{...BASE.placement, '1':['2026-11-16|Crew 1|0']}}, 'user-b');
        // This stale tab moves only Crane, 11/18 -> 11/19.
        DOC.placement['2']=['2026-11-19|Crew 2|0'];
        await putShared();
        console.log(JSON.stringify({log:server.log, placement:server.doc.placement, banners}));
      })();
    """)
    assert out["placement"] == {"1": ["2026-11-16|Crew 1|0"], "2": ["2026-11-19|Crew 2|0"]}
    saved = out["log"][-1]
    assert saved["status"] == 200
    # Only this tab's own move goes to the cards; Amy's newer date is left alone.
    assert saved["dateMoves"] == [{"name": "Crane Worldwide", "id": None, "kind": "install",
                                   "date": "2026-11-19", "from": "2026-11-18"}]
    assert out["banners"] == [{"by": "user-b", "conflicts": []}]


def test_both_moved_the_same_stop_keeps_the_newer_and_says_so():
    out = run(SCENARIO + SAVE_LOOP + """
      (async()=>{
        server.doc=clone(BASE);
        load();
        serverWrite({...clone(BASE), placement:{...BASE.placement, '1':['2026-11-16|Crew 1|0']}}, 'user-b');
        DOC.placement['1']=['2026-11-20|Crew 1|0'];      // this tab moved Amy too
        const ok=await putShared();
        console.log(JSON.stringify({ok, log:server.log, placement:server.doc.placement, banners, local:DOC.placement}));
      })();
    """)
    assert out["placement"]["1"] == ["2026-11-16|Crew 1|0"]
    assert out["local"]["1"] == ["2026-11-16|Crew 1|0"]
    assert out["banners"] == [{"by": "user-b", "conflicts": ["Jinks, Amy: day"]}]
    # Nothing of this tab's left to send, so no second save and no card date.
    assert [x["status"] for x in out["log"]] == [409] and out["ok"] is True


def test_sets_comments_and_staffing_merge_both_ways():
    out = run(SCENARIO + """
      const base={...clone(BASE), approved:['d1','d2'], staffing:{d1:['p1'], d2:['p2']},
                  comments:{'1':[{text:'gate code', at:10}]}, moves:[{row:1, to:'x'}]};
      const mine=clone(base), theirs=clone(base);
      mine.approved=['d1','d3'];                 // I approved d3, unapproved d2
      theirs.approved=['d1','d2','d4'];          // they approved d4
      mine.staffing.d1=['p1','p2'];              // I added Luis to d1
      theirs.staffing.d1=['p1','p9'];            // they added p9 to d1
      delete mine.staffing.d2;                   // I took Luis off d2
      mine.comments['1'].unshift({text:'call first', at:30});
      theirs.comments['1']=[];                   // they deleted the gate code note
      theirs.comments['2']=[{text:'dog', at:20}];
      mine.moves.push({row:2, to:'y'}); theirs.moves.push({row:1, to:'z'});
      const r=mergeShared(base, mine, theirs);
      console.log(JSON.stringify(r));
    """)
    st = out["state"]
    assert sorted(st["approved"]) == ["d1", "d3", "d4"]
    assert st["staffing"] == {"d1": ["p1", "p9", "p2"]}
    assert st["comments"] == {"1": [{"text": "call first", "at": 30}], "2": [{"text": "dog", "at": 20}]}
    assert st["moves"] == [{"row": 1, "to": "x"}, {"row": 1, "to": "z"}, {"row": 2, "to": "y"}]
    assert out["conflicts"] == []


def test_roster_conflicts_are_listed_never_silent():
    out = run(SCENARIO + """
      const base=clone(BASE); base.roster.push(P('p3','Rosa'));
      const mine=clone(base), theirs=clone(base);
      const my=id=>mine.roster.find(p=>p.id===id), their=id=>theirs.roster.find(p=>p.id===id);
      my('p2').phone='(713) 555-0101'; their('p2').phone='(713) 555-0202';      // both edited
      my('p2').notes='Has a truck';                                             // only me
      my('p2').texts=[T1,T2]; their('p2').texts=[{at:'2026-10-09T03:00:00.000Z', lang:'en', body:'later'}];
      their('p1').notes='Lead next year'; mine.roster=mine.roster.filter(p=>p.id!=='p1');   // I removed, they edited
      my('p3').notes='x'; theirs.roster=theirs.roster.filter(p=>p.id!=='p3');             // they removed, I edited
      const r=mergeShared(base, mine, theirs);
      console.log(JSON.stringify(r));
    """)
    roster = {p["id"]: p for p in out["state"]["roster"]}
    assert set(roster) == {"p1", "p2"}
    assert roster["p2"]["phone"] == "(713) 555-0202" and roster["p2"]["notes"] == "Has a truck"
    assert [t["body"] for t in roster["p2"]["texts"]] == ["later", "Puedes trabajar el 26 de octubre?",
                                                          "Can you work Oct 26?"]
    assert roster["p1"]["notes"] == "Lead next year"
    assert out["conflicts"] == ["Ana Test (changed by someone else, so not removed)", "Luis Test: phone",
                                "Rosa Test (removed by someone else)"]


def test_two_new_people_on_one_id_both_kept():
    out = run(SCENARIO + """
      const mine=clone(BASE), theirs=clone(BASE);
      mine.roster.push(P('p3','Mia')); mine.staffing={d1:['p3']};
      theirs.roster.push(P('p3','Noah'));
      const r=mergeShared(BASE, mine, theirs);
      console.log(JSON.stringify([r.state.roster.map(p=>p.id+':'+p.first), r.state.staffing, r.conflicts]));
    """)
    assert out == [["p1:Ana", "p2:Luis", "p3:Noah", "p4:Mia"], {"d1": ["p4"]}, []]


def test_new_client_collision_needs_a_reload():
    out = run(SCENARIO + """
      const mine=clone(BASE), theirs=clone(BASE);
      mine.newClients=[{row:900, name:'Smith, Jo'}]; theirs.newClients=[{row:900, name:'Lee, Kim'}];
      console.log(JSON.stringify(mergeShared(BASE, mine, theirs).hard));
    """)
    assert out == ["New client Smith, Jo"]


def test_every_save_path_sends_its_base():
    put = js_function("putShared")
    assert "baseUpdatedAt: sharedBase ? sharedBase.at : null" in put
    assert "if(r.status===409)" in put and "rebaseOnto(j," in put
    assert "baseUpdatedAt: sharedBase ? sharedBase.at : null" in js_function("tbdgFlush")
    # history restore goes through the same guarded save
    assert "await pushSharedNow()" in js_function("restoreHistoryEntry")
    # this device's copy keeps its base, so a reload can merge instead of guess
    assert "_base:sharedBase" in js_function("saveLocal")
    assert "saveLocal();" in js_function("persist")
    # the old "newest timestamp wins the whole document" path is gone
    assert "pushSharedNow();\n        return;" not in js_function("pullSharedNow")
