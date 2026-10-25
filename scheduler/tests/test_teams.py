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
    "teamStats", "teamApplyPlan", "staffingWith", "staffingCleared", "teamApplyNote", "stfUndoLeft",
    "stfClearMsg", "staffingWithout", "teamShiftState", "teamRemoveNote")


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
    for fn in ("applyTeamToShift", "toggleTeamOnShift", "saveTeamDraft", "stfUndo", "stfClear"):
        assert "roBlocked()" in js_function(fn), fn
    draw = js_function("drawTeamsDlg")
    assert draw.count("roBlocked()") >= 3        # new, edit, delete
    assert "READONLY?'':" in draw                # no "+ New team" button
    assert "READONLY?'':" in js_function("teamListHTML")
    assert "undoBtn.disabled=READONLY" in js_function("drawStaffDlg")
    assert "clearBtn.disabled=READONLY" in js_function("drawStaffDlg")


def test_staff_dialog_has_teams_undo_and_clear():
    assert 'id="stfundo"' in TEMPLATE and 'id="stfclear"' in TEMPLATE
    draw = js_function("drawStaffDlg")
    # every change made in the dialog is tracked for its Undo
    assert "stfTrack(()=>assignReadyRosterToShift(sh))" in draw
    assert "stfTrack(()=>pushUndo())" in draw
    assert "stfTrack(()=>setCrewName(sh.nameKey, t.name))" in draw
    assert "stfTrack(" in js_function("applyTeamToShift")
    assert "stfTrack(" in js_function("stfClear")
    # the dialog's Undo is the page's undo, so the toolbar stays in step
    assert "undo();" in js_function("stfUndo")
    assert "undoSeq++" in js_function("pushUndo")
    assert "stfUndoN=0" in js_function("openStaffDlg")
    assert "confirm(stfClearMsg(sh, n))" in js_function("stfClear")
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
               "teamApplyNote", "stfClear", "stfClearMsg", "applyTeamToShift", "toggleTeamOnShift",
               "teamRemoveNote"):
        assert "—" not in js_function(fn), fn
    dlg = TEMPLATE[TEMPLATE.index('<dialog id="teamdlg"'):]
    assert "—" not in dlg[:dlg.index("</dialog>")]
    stf = TEMPLATE[TEMPLATE.index('<div class="btns stfbtns">'):]
    assert "—" not in stf[:stf.index("</dialog>")]


# User, 2026-10-24, on the "Training - 10/23/2026" Staffing dialog: "i need to
# be able to select the teams at the top". Team buttons now show on every
# shift, training days included, in a labelled "Teams" row at the very top.

def test_team_buttons_show_on_training_days_too():
    src = js_function("stfTeamsHTML")
    assert "if(sh.training) return ''" not in src
    assert "sh.training" in src                     # wording only, never a gate
    # a "Team" section styled like the Lead / Designer ones: checkbox rows,
    # count in the language-pill spot ("6/7" when some can't work that date)
    assert '<div class="asghdr">Team</div>' in src
    assert 'class="asgrow asgteamrow' in src and 'data-teampick=' in src
    assert '<span class="pill teamcnt"' in src
    assert "`${able}/${st.total}`" in src
    assert "data-partial" in src                    # part-ticked after a swap
    # applying a team on a training day uses the same availability skip
    apply_src = js_function("applyTeamToShift")
    assert "avail:p=>availFor(p, sh)" in js_function("teamPlanFor")
    assert "teamPlanFor(sh, team)" in apply_src
    assert "sh.training ? 'this training' : 'this crew'" in apply_src


def test_team_section_is_first_in_the_people_list():
    draw = js_function("drawStaffDlg")
    assert "list.innerHTML=stfTeamsHTML(sh)+h" in draw    # before LEAD / LEAD ASSIST / ...
    assert "cb.indeterminate=true" in draw
    assert "toggleTeamOnShift(sh, t)" in draw
    assert 'id="stfteams"' not in TEMPLATE                # the old pill row is gone
    assert "stfteambtn" not in TEMPLATE


def test_training_day_note_and_unavailable_skip():
    out = run(APPLY + """
      const note=teamApplyNote(team, plan, id=>(P[id]||{name:id}).name, 'this training');
      console.log(JSON.stringify(note));
    """)
    assert out[1] == "1 already on this training."
    assert out[2] == "1 not available: Cy."          # skipped and listed, like any shift
    # the default wording is unchanged
    assert run("console.log(JSON.stringify(teamApplyNote({name:'T'},"
               "{add:[], already:['a'], unavailable:[], busy:[], gone:[]}, x=>x)))")[1] == "1 already on this crew."


def test_clear_on_a_training_day_warns_it_removes_attendance():
    out = run("""console.log(JSON.stringify([
      stfClearMsg({training:true, days:[{}]}, 12),
      stfClearMsg({training:true, days:[{}]}, 1),
      stfClearMsg({days:[{}]}, 3),
      stfClearMsg({dallas:true, days:[{},{},{},{}]}, 5)]))""")
    assert out[0].startswith("Remove all 12 people from the training? This removes their Attended training status.")
    assert "Undo" in out[0]
    assert out[1].startswith("Remove all 1 person from the training?")
    assert out[2] == "Remove all 3 people from this crew?"
    assert out[3] == "Remove all 5 people from this crew?\n\nThis takes them off all 4 nights of the Dallas week."
    # Clear stays one undo step
    clear = js_function("stfClear")
    assert "pushUndo()" in clear and "stfTrack(" in clear


# User, 2026-10-24: "select the team ... just auto check off all of the people
# on the team so that I could select the team, but switch one person out if I
# wanted to." A team tap ticks its members; once they are all on, the same tap
# takes them back off. Both are one undo step.

def test_team_button_state_and_toggle_off():
    out = run(APPLY + """
      const st=teamShiftState(plan);
      // after the tap: p1, p2 added; Cy unavailable, Di busy stay off
      const after=teamApplyPlan(team, {...o, onShift:new Set(['p6','p1','p2'])});
      const st2=teamShiftState(after);
      // switch one out: Ben unticked, so the team is no longer "all on"
      const st3=teamShiftState(teamApplyPlan(team, {...o, onShift:new Set(['p6','p1'])}));
      const st0=teamShiftState(teamApplyPlan(team, {...o, onShift:new Set()}));
      const days=['d1','d2'];
      const map={d1:['p1','p2','p6','x'], d2:['p1','p2'], d3:['p1']};
      console.log(JSON.stringify({st, st2, st3, st0,
        off:staffingWithout(map, days, after.already), same:staffingWithout(map, days, []), map,
        note:teamRemoveNote(team, 3, 'the training'), none:teamRemoveNote(team, 0)}));
    """)
    assert out["st"] == {"on": 1, "total": 5, "selected": False}
    assert out["st2"] == {"on": 3, "total": 5, "selected": True}     # "3 of 5" with a tick
    assert out["st3"] == {"on": 2, "total": 5, "selected": False}
    assert out["st0"] == {"on": 0, "total": 5, "selected": False}
    assert out["off"] == {"d1": ["x"], "d3": ["p1"]}                  # empty crew-day dropped
    assert out["same"] == out["map"] == {"d1": ["p1", "p2", "p6", "x"], "d2": ["p1", "p2"], "d3": ["p1"]}
    assert out["note"] == ["Took 3 from Ana's team off the training.", "Undo puts them back."]
    assert out["none"][0] == "Nobody from Ana's team was on this crew."


def test_team_tap_wiring_ticks_scrolls_and_tags():
    draw = js_function("drawStaffDlg")
    assert "toggleTeamOnShift(sh, t)" in draw
    assert "applyTeamToShift(sh, t)" not in draw
    tog = js_function("toggleTeamOnShift")
    assert "pushUndo()" in tog and "stfTrack(" in tog and "staffingWithout(" in tog
    assert "applyTeamToShift(sh, team, plan)" in tog
    assert "stfScrollToNew=plan.add.length>0" in js_function("applyTeamToShift")
    # ticked rows flash, get scrolled into view, and every member shows a team tag
    assert "juston" in draw and "stfScrollToNew" in draw and "scrollTo(" in draw
    assert 'class="asgteam"' in draw and "teamOfPerson(teams, p.id, teamSeasonDefault())" in draw
    assert "${st.selected?' checked':''}" in js_function("stfTeamsHTML")


# "why cant i see the whole list and why cant i scroll" (user, 2026-10-24):
# the dialog uses the available height and the people list is the scroller.

def test_staff_dialog_layout_scrolls_the_list():
    css = TEMPLATE[TEMPLATE.index("#stfdlg[open]{display:flex"):]
    css = css[:css.index("@media (prefers-reduced-motion: reduce){\n  #stfdlg")]
    assert "max-height:calc(100dvh - 32px)" in css
    lst = re.search(r"#stfdlg \.asglist\{[^}]*\}", css).group(0)
    for need in ("flex:1 1 auto", "max-height:none", "overflow-y:auto", "overscroll-behavior:contain"):
        assert need in lst, need
    assert "min-height:min(" in lst
    # the redraw keeps the scroll position
    draw = js_function("drawStaffDlg")
    assert "const keepTop=list.scrollTop" in draw and "list.scrollTop=keepTop" in draw


def test_staff_dialog_motion_respects_reduced_motion():
    i = TEMPLATE.index("@media (prefers-reduced-motion: reduce){\n  #stfdlg")
    block = TEMPLATE[i:TEMPLATE.index("\n}\n", i)]
    for sel in ("#stfdlg[open]", "#stfdlg.closing", ".asgrow.juston", ".stfbump", ".asglist.intro .asgrow"):
        assert sel in block, sel
    assert "animation:none" in block and "transition:none" in block
    assert "@keyframes stfin" in TEMPLATE and "@keyframes stfout" in TEMPLATE
    opener = js_function("openStaffDlg")
    assert "stfPrevOn=null" in opener and "classList.add('intro')" in opener
