"""Teams on the Install Schedule (review_template.html), and the Staff
dialog's Undo and Clear.

User, 2026-10-24: "give me a function to create teams, base teams by year
that i can edit ... when I hit staff this shift, I can hit Alberto's team,
select it, and if I need to edit it, I can deselect a person and select
somebody different depending on the day." And: "I need an undo button and a
clear button on the staff / edit crew on the staffing page."

Shared state `teams` is [{id, name, season, leadId, members, color?}]. These
run the template's own functions in node. FAKE people only.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_dallas_nights import MERGE, fns

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

HELPERS = "\nconst TEAM_NAME_MAX=40;\n" + fns(
    "normTeamName", "normTeams", "teamsForSeason", "teamOfPerson", "withTeam", "withoutTeam",
    "teamStats", "teamApplyPlan", "staffingWith", "staffingCleared", "teamApplyNote", "stfUndoLeft")


def run(body):
    return json.loads(run_js(HELPERS + body))


def test_teams_are_normalized_as_saved():
    out = run("""console.log(JSON.stringify([
      normTeams([
        {id:'t1', name:'  Team   A ', season:'2026', leadId:'p1', members:['p2','p2','p9'], color:'#AABBCC'},
        {id:'t1', name:'duplicate id', season:2026, members:['p3']},
        {id:'t2', name:'', season:2026, members:['p3']},
        {id:'', name:'No id', season:2026, members:['p3']},
        {id:'t3', name:'Team B', season:'nope', leadId:'p8', members:['p3', 4, 'p4']},
        null, 'junk', ['x'],
      ], ['p1','p2','p3','p4'], 2026),
      normTeams(null, null, 2026), normTeams({a:1}, null, 2026)]))""")
    assert out == [[
        # the lead is always a member; unknown people drop; color kept lowercase
        {"id": "t1", "name": "Team A", "season": 2026, "leadId": "p1", "members": ["p1", "p2"], "color": "#aabbcc"},
        # a bad year gets the default; a lead who is not on the roster is dropped
        {"id": "t3", "name": "Team B", "season": 2026, "leadId": "", "members": ["p3", "p4"]},
    ], [], []]


def test_one_team_per_person_per_season_on_load():
    out = run("""console.log(JSON.stringify(normTeams([
        {id:'a', name:'A', season:2026, members:['p1','p2']},
        {id:'b', name:'B', season:2026, leadId:'p2', members:['p2','p3']},
        {id:'c', name:'C', season:2027, members:['p1']},
      ], null, 2026).map(t=>[t.id, t.leadId, t.members])))""")
    assert out == [["a", "", ["p1", "p2"]], ["b", "", ["p3"]], ["c", "", ["p1"]]]


def test_saving_a_team_moves_people_off_their_other_team_that_season():
    out = run("""
      let L=[{id:'a', name:'A', season:2026, leadId:'p1', members:['p1','p2']},
             {id:'z', name:'Z', season:2027, leadId:'', members:['p2']}];
      L=withTeam(L, {id:'b', name:'B', season:2026, leadId:'', members:['p1','p3']});
      const moved=L.map(t=>[t.id, t.leadId, t.members]);
      const on=[teamOfPerson(L,'p1',2026)?.id, teamOfPerson(L,'p1',2026,'b'), teamOfPerson(L,'p2',2027)?.id];
      L=withTeam(L, {id:'a', name:'A renamed', season:2026, leadId:'', members:['p2']});
      const renamed=L.map(t=>[t.id, t.name]);
      console.log(JSON.stringify({moved, on, renamed,
        season:teamsForSeason(L, 2026).map(t=>t.name), gone:withoutTeam(L,'a').map(t=>t.id)}));
    """)
    # p1 leaves A (and A loses its lead); the 2027 team is untouched
    assert out["moved"] == [["a", "", ["p2"]], ["z", "", ["p2"]], ["b", "", ["p1", "p3"]]]
    assert out["on"] == ["b", None, "z"]
    assert out["renamed"] == [["a", "A renamed"], ["z", "Z"], ["b", "B"]]
    assert out["season"] == ["A renamed", "B"]
    assert out["gone"] == ["z", "b"]


def test_team_stats_count_and_average_rating():
    out = run("""
      const P={p1:{r:8}, p2:{r:0}, p3:{r:9}};
      console.log(JSON.stringify([
        teamStats({members:['p1','p2','p3','gone']}, id=>P[id]||null, p=>p.r),
        teamStats({members:['p2']}, id=>P[id]||null, p=>p.r)]));
    """)
    assert out == [{"count": 3, "rated": 2, "avg": 8.5}, {"count": 1, "rated": 0, "avg": 0}]


APPLY = """
  const P={
    p1:{id:'p1', name:'Ana Lead', active:true},
    p2:{id:'p2', name:'Ben', active:true},
    p3:{id:'p3', name:'Cy', active:true},
    p4:{id:'p4', name:'Di', active:true},
    p5:{id:'p5', name:'Ed', active:false},
    p6:{id:'p6', name:'Flo', active:true},
  };
  const team={id:'t', name:"Ana's team", members:['p1','p2','p3','p4','p5','p6','p7']};
  const o={person:id=>P[id]||null, onShift:new Set(['p6']),
    avail:p=>p.id==='p3' ? {ok:false, why:'no day shifts'} : {ok:true, why:''},
    otherCrew:id=>id==='p4' ? 'Crew 2' : ''};
  const plan=teamApplyPlan(team, o);
"""


def test_applying_a_team_skips_unavailable_busy_and_gone_people():
    out = run(APPLY + """
      const note=teamApplyNote(team, plan, id=>(P[id]||{name:id}).name);
      console.log(JSON.stringify({plan, note}));
    """)
    assert out["plan"] == {"add": ["p1", "p2"], "already": ["p6"],
                           "unavailable": [{"id": "p3", "why": "no day shifts"}],
                           "busy": [{"id": "p4", "crew": "Crew 2"}], "gone": ["p5", "p7"]}
    assert out["note"] == ["Added 2 from Ana's team.", "1 already on this crew.",
                           "1 not available: Cy.", "1 on another crew that day: Di (Crew 2).",
                           "2 not working this season: Ed, p7."]
    for line in out["note"]:
        assert "—" not in line


def test_a_dallas_week_gets_the_team_on_every_night_and_clear_empties_them_all():
    out = run(APPLY + """
      const nights=['2026-11-02|Crew 1|0','2026-11-03|Crew 1|0','2026-11-04|Crew 1|0'];
      const before={'2026-11-02|Crew 1|0':['p6'], '2026-11-03|Crew 1|0':['p6'], '2026-11-02|Crew 2|0':['p4']};
      const after=staffingWith(before, nights, plan.add);
      const cleared=staffingCleared(after, nights);
      console.log(JSON.stringify({after, cleared, same:staffingWith(before, nights, []), untouched:before}));
    """)
    assert out["after"] == {"2026-11-02|Crew 1|0": ["p6", "p1", "p2"], "2026-11-03|Crew 1|0": ["p6", "p1", "p2"],
                            "2026-11-04|Crew 1|0": ["p1", "p2"], "2026-11-02|Crew 2|0": ["p4"]}
    assert out["cleared"] == {"2026-11-02|Crew 2|0": ["p4"]}
    assert out["same"] == out["untouched"]   # pure: the input is never changed
    assert out["untouched"] == {"2026-11-02|Crew 1|0": ["p6"], "2026-11-03|Crew 1|0": ["p6"],
                                "2026-11-02|Crew 2|0": ["p4"]}


def test_nobody_new_note():
    out = run("""console.log(JSON.stringify(teamApplyNote({name:'T'},
      {add:[], already:['a','b'], unavailable:[], busy:[], gone:[]}, x=>x)))""")
    assert out == ["Nobody new added from T.", "2 already on this crew."]


def test_teams_merge_three_ways_on_a_stale_tab():
    out = json.loads(run_js(MERGE + """
      const T=(id,name,members,extra)=>({id, name, season:2026, leadId:'', members, ...(extra||{})});
      const base={placement:{}, teams:[T('a','A',['p1','p2']), T('b','B',['p3']), T('c','C',['p4'])]};
      const mine=clone(base), theirs=clone(base);
      mine.teams=[T('a','A mine',['p1','p2','p5']), T('c','C',['p4']), T('d','D',['p6'])];   // renamed a + added p5, deleted b, added d
      theirs.teams=[T('a','A',['p2','p7']), T('b','B',['p3']), T('c','C',['p4'],{leadId:'p4'}), T('e','E',['p8'])];  // a: -p1 +p7, c: lead, added e
      const r=mergeShared(base, mine, theirs);
      const both=mergeShared({teams:[T('a','A',[])]}, {teams:[T('a','Mine',[])]}, {teams:[T('a','Theirs',[])]});
      const gone=mergeShared({teams:[T('a','A',[])]}, {teams:[T('a','A2',[])]}, {teams:[]});
      const keep=mergeShared({teams:[T('a','A',[])]}, {teams:[]}, {teams:[T('a','A',['p9'])]});
      const old=mergeShared({placement:{}}, {placement:{}, teams:[T('n','New',['p1'])]}, {placement:{}});
      console.log(JSON.stringify({got:r.state.teams.map(t=>[t.id,t.name,t.leadId,t.members]), conflicts:r.conflicts,
        both:[both.state.teams[0].name, both.conflicts], gone:[gone.state.teams, gone.conflicts],
        keep:[keep.state.teams.map(t=>t.id), keep.conflicts], old:old.state.teams.map(t=>t.id)}));
    """))
    assert out["got"] == [
        ["a", "A mine", "", ["p2", "p7", "p5"]],   # my rename + add, their remove + add
        ["c", "C", "p4", ["p4"]],                   # their lead change
        ["e", "E", "", ["p8"]],                     # their new team
        ["d", "D", "", ["p6"]],                     # my new team
    ]                                               # b: deleted by me, unchanged by them
    assert out["conflicts"] == []
    assert out["both"] == ["Theirs", ["Theirs: team name"]]
    assert out["gone"] == [[], ["A2 (deleted by someone else)"]]
    assert out["keep"] == [["a"], ["A (changed by someone else, so not deleted)"]]
    assert out["old"] == ["n"]   # a server document from before teams


def test_every_save_and_load_path_carries_teams():
    assert "'teams'" in re.search(r"const SHARED_KEYS=.*", TEMPLATE).group(0)
    assert "staffing, teams, crewNames, savedAt" in js_function("snapshot")
    assert "staffing, teams, crewNames}" in js_function("stateBlob")
    for fn in ("restoreBlob", "restoreHistoryEntry"):
        src = js_function(fn)
        # after the roster, so members are checked against the right people
        assert src.index("teams = loadTeams(") > src.index("roster = normRoster(")
    boot = TEMPLATE[TEMPLATE.index("const s = JSON.parse(localStorage.getItem(LS_KEY)||'{}');"):]
    assert boot.index("teams = loadTeams(s.teams)") > boot.index("roster = normRoster(s.roster)")
    assert "teams = loadTeams(teams)" in js_function("render")
    assert "teams = loadTeams(j.inherit.teams)" in js_function("pullSharedNow")


def test_read_only_cannot_create_edit_delete_or_apply():
    for fn in ("applyTeamToShift", "saveTeamDraft", "stfUndo", "stfClear"):
        assert "roBlocked()" in js_function(fn), fn
    draw = js_function("drawTeamsDlg")
    assert draw.count("roBlocked()") >= 3        # new, edit, delete
    assert "READONLY?'':" in draw                # no "+ New team" button
    assert "READONLY?'':" in js_function("teamListHTML")
    assert "undoBtn.disabled=READONLY" in js_function("drawStaffDlg")
    assert "clearBtn.disabled=READONLY" in js_function("drawStaffDlg")


def test_staff_dialog_has_teams_undo_and_clear():
    assert 'id="stfundo"' in TEMPLATE and 'id="stfclear"' in TEMPLATE and 'id="stfteams"' in TEMPLATE
    draw = js_function("drawStaffDlg")
    # every change made in the dialog is tracked for its Undo
    assert "stfTrack(()=>assignReadyRosterToShift(sh))" in draw
    assert "stfTrack(()=>pushUndo())" in draw
    assert "stfTrack(()=>setCrewName(sh.key, t.name))" in draw
    assert "stfTrack(" in js_function("applyTeamToShift")
    assert "stfTrack(" in js_function("stfClear")
    # the dialog's Undo is the page's undo, so the toolbar stays in step
    assert "undo();" in js_function("stfUndo")
    assert "undoSeq++" in js_function("pushUndo")
    assert "stfUndoN=0" in js_function("openStaffDlg")
    assert "Remove all ${n} ${n===1?'person':'people'} from this crew?" in js_function("stfClear")
    # naming the crew after the team is offered, never done silently
    assert "setCrewName" not in js_function("applyTeamToShift")
    assert "Name this crew" in js_function("stfTeamsHTML")


def test_dialog_undo_never_goes_past_the_page_stack():
    out = run("console.log(JSON.stringify([stfUndoLeft(3,10), stfUndoLeft(3,1), stfUndoLeft(0,5), stfUndoLeft(2,0)]))")
    assert out == [3, 1, 0, 0]


def test_dialog_undo_steps_back_through_the_page_undo():
    """Run the dialog's track/undo pair against a stand-in page undo stack."""
    src = """
      let READONLY=false, undoSeq=0, undoStack=[], state={n:0}, drawn=0;
      const roBlocked=()=>READONLY;
      function pushUndo(){ undoSeq++; undoStack.push(JSON.stringify(state)); }
      function undo(){ state=JSON.parse(undoStack.pop()); }
      const drawStaffDlg=()=>{ drawn++; };
      let stfUndoN=0, stfTeamNote=null;
    """ + fns("stfTrack", "stfUndoLeft", "stfUndo") + """
      pushUndo(); state.n=99;            // an edit made before the dialog opened
      stfTrack(()=>{ pushUndo(); state.n=1; });
      stfTrack(()=>{ pushUndo(); state.n=2; });
      stfTrack(()=>{});                  // nothing changed: not a step
      const steps=stfUndoN;
      stfUndo(); const a=state.n;
      stfUndo(); const b=state.n;
      stfUndo(); const c=state.n;        // no more dialog steps: the earlier edit stays
      READONLY=true; stfTrack(()=>{ pushUndo(); state.n=5; }); stfUndo(); const ro=state.n;
      console.log(JSON.stringify({steps, a, b, c, ro}));
    """
    assert json.loads(run_js(src)) == {"steps": 2, "a": 1, "b": 99, "c": 99, "ro": 5}


def test_new_ui_text_has_no_em_dashes():
    for fn in ("teamListHTML", "teamEditHTML", "drawTeamsDlg", "saveTeamDraft", "stfTeamsHTML",
               "teamApplyNote", "stfClear", "applyTeamToShift"):
        assert "—" not in js_function(fn), fn
    dlg = TEMPLATE[TEMPLATE.index('<dialog id="teamdlg"'):]
    assert "—" not in dlg[:dlg.index("</dialog>")]
    stf = TEMPLATE[TEMPLATE.index('<div class="btns stfbtns">'):]
    assert "—" not in stf[:stf.index("</dialog>")]
