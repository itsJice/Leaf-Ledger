"""Teams builder: reorder the team columns (review_template.html).

User, 2026-10-30: "give me the ability in the teams window to drag and
reorder my view of the vertical teams columns". "My view": the order is this
device's view preference (localStorage, per season), never shared state.
New teams go at the end; deleted teams drop out. Person drag-and-drop is
unchanged: a column drag starts only from the header (the grip with a mouse,
press and hold with a finger). These run the template's own functions in
node. FAKE teams only.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_dallas_nights import const_line, fns

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

PURE = "\n" + const_line("TEAM_COLS_KEY") + "\n" + fns(
    "teamsForSeason", "teamColOrder", "teamColMove", "loadTeamColOrders", "saveTeamColOrder",
    "teamsInColOrder", "teamColMoveLabels", "teamsAfterDrop", "teamLeadFirst", "tbDropIndex")

FAKE_STORAGE = """
  const store={};
  globalThis.localStorage={getItem:k=>k in store ? store[k] : null, setItem:(k,v)=>{ store[k]=String(v); },
                           removeItem:k=>{ delete store[k]; }};
"""

TEAMS = """
  const T=(id, name, season)=>({id, name, season:season||2026, leadId:'', members:[]});
  const teams=[T('a','Alpha'), T('b','Bravo'), T('c','Charlie'), T('d','Delta'), T('x','Old', 2025)];
  const ids=L=>L.map(t=>t.id);
"""


def run(body):
    return json.loads(run_js(PURE + FAKE_STORAGE + TEAMS + body))


def test_reorder_moves_one_column_and_is_pure():
    out = run("""
      const L=['a','b','c','d'];
      console.log(JSON.stringify({
        first:teamColMove(L,'c',0), last:teamColMove(L,'a',3), past:teamColMove(L,'a',99),
        mid:teamColMove(L,'d',1), same:teamColMove(L,'b',1), noidx:teamColMove(L,'a'),
        neg:teamColMove(L,'c',-4), unknown:teamColMove(L,'zz',0), pure:L,
        // the menu's Move left / Move right are index-1 / index+1
        left:teamColMove(L,'c',2-1), right:teamColMove(L,'b',1+1),
      }));
    """)
    assert out["first"] == ["c", "a", "b", "d"]
    assert out["last"] == ["b", "c", "d", "a"]
    assert out["past"] == ["b", "c", "d", "a"]
    assert out["mid"] == ["a", "d", "b", "c"]
    assert out["same"] == ["a", "b", "c", "d"]
    assert out["noidx"] == ["b", "c", "d", "a"]
    assert out["neg"] == ["c", "a", "b", "d"]
    assert out["unknown"] == ["a", "b", "c", "d"]
    assert out["pure"] == ["a", "b", "c", "d"]
    assert out["left"] == ["a", "c", "b", "d"]
    assert out["right"] == ["a", "c", "b", "d"]


def test_saved_order_new_teams_at_the_end_deleted_teams_drop():
    out = run("""
      const S=teamsForSeason(teams, 2026);
      console.log(JSON.stringify({
        none:ids(teamColOrder(S, null)), junk:ids(teamColOrder(S, {a:1})),
        saved:ids(teamColOrder(S, ['d','b','a','c'])),
        // 'c' is new since the order was saved: it goes at the end
        newteam:ids(teamColOrder(S, ['d','b','a'])),
        // 'gone' was deleted: it drops out; duplicates count once
        deleted:ids(teamColOrder(S.filter(t=>t.id!=='b'), ['gone','d','b','d','a','c'])),
        pure:ids(S),
      }));
    """)
    assert out["none"] == ["a", "b", "c", "d"]          # no saved order: by name, as before
    assert out["junk"] == ["a", "b", "c", "d"]
    assert out["saved"] == ["d", "b", "a", "c"]
    assert out["newteam"] == ["d", "b", "a", "c"]
    assert out["deleted"] == ["d", "a", "c"]
    assert out["pure"] == ["a", "b", "c", "d"]


def test_order_is_saved_per_season_on_this_device():
    out = run("""
      const before=ids(teamsInColOrder(teams, 2026));
      saveTeamColOrder(2026, ['c','a','d','b']);
      saveTeamColOrder(2025, ['x']);
      const after=ids(teamsInColOrder(teams, 2026));
      // a new team made later, and a deleted one
      const more=[...teams.filter(t=>t.id!=='a'), T('e','Echo')];
      const later=ids(teamsInColOrder(more, 2026));
      // the next save writes what is on screen, so the deleted team leaves the stored order
      saveTeamColOrder(2026, teamColMove(later, 'e', 0));
      console.log(JSON.stringify({before, after, later, stored:JSON.parse(store[TEAM_COLS_KEY]),
        y2025:ids(teamsInColOrder(teams, 2025))}));
    """)
    assert out["before"] == ["a", "b", "c", "d"]
    assert out["after"] == ["c", "a", "d", "b"]
    assert out["later"] == ["c", "d", "b", "e"]
    assert out["stored"] == {"2025": ["x"], "2026": ["e", "c", "d", "b"]}
    assert out["y2025"] == ["x"]


def test_storage_that_throws_or_holds_junk_never_breaks_the_builder():
    out = json.loads(run_js(PURE + TEAMS + """
      globalThis.localStorage={getItem:()=>{ throw new Error('blocked'); }, setItem:()=>{ throw new Error('blocked'); }};
      const a=ids(teamsInColOrder(teams, 2026));
      saveTeamColOrder(2026, ['b','a']);          // swallowed
      globalThis.localStorage={getItem:()=>'[1,2]', setItem:()=>{}};
      const b=loadTeamColOrders();
      globalThis.localStorage={getItem:()=>'{not json', setItem:()=>{}};
      const c=loadTeamColOrders();
      console.log(JSON.stringify({a, b, c}));
    """))
    assert out == {"a": ["a", "b", "c", "d"], "b": {}, "c": {}}


def test_move_labels_follow_the_layout():
    out = run("console.log(JSON.stringify([teamColMoveLabels(false), teamColMoveLabels(true)]))")
    assert out == [["Move left", "Move right"], ["Move up", "Move down"]]


def test_column_order_is_a_view_pref_not_shared_state():
    assert TEMPLATE.count("TEAM_COLS_KEY") == 3       # the const, one read, one write
    for fn in ("persist", "sharedSnapshot", "mergeShared", "tbCommit"):
        src = js_function(fn)
        assert "TEAM_COLS_KEY" not in src and "saveTeamColOrder" not in src and "colorder" not in src.lower()
    move = js_function("tbMoveCol")
    assert "saveTeamColOrder(tb.season, next)" in move
    assert "pushUndo" not in move and "persist(" not in move and "roBlocked" not in move
    # every localStorage touch is wrapped
    assert "try{" in js_function("loadTeamColOrders") and "try{" in js_function("saveTeamColOrder")


def test_builder_draws_columns_in_the_saved_order_with_a_header_grip():
    draw = js_function("drawTeamBuilder")
    assert "const list=teamsInColOrder(teams, season);" in draw
    col = js_function("tbColHTML")
    assert 'class="tbcolgrip" data-colgrip' in col
    assert col.index("data-colgrip") < col.index("${name}")          # left of the team name
    menu = js_function("tbTeamMenu")
    assert "teamColMoveLabels(tbColsStacked())" in menu
    assert "tbMoveCol(id, ci-1, true)" in menu and "tbMoveCol(id, ci+1, true)" in menu
    assert "disabled:ci<=0" in menu and "ci>=order.length-1" in menu
    # an insertion bar while dragging, and no smooth scrolling anywhere new
    assert ".tbcolmark{" in TEMPLATE and ".tbcolmark.flat{" in TEMPLATE
    upd = js_function("tbColDragUpdate")
    assert "tbDropIndex(" in upd and "d.mark.hidden=false" in upd
    for fn in ("tbMoveCol", "tbColDragUpdate", "tbBeginColDrag", "tbColPointerDown"):
        assert "smooth" not in js_function(fn)


def test_column_drag_starts_only_from_the_header():
    wire = js_function("tbWire")
    assert "body.querySelectorAll('.tbcolhd').forEach(h=>{" in wire
    assert "h.addEventListener('pointerdown', tbColPointerDown);" in wire
    # person cards keep their own handler, unchanged
    assert "c.addEventListener('pointerdown', tbPointerDown);" in wire
    down = js_function("tbColPointerDown")
    assert "type==='mouse' ? !e.target.closest('[data-colgrip]')" in down
    assert "e.target.closest('[data-tmenu],input')" in down
    assert "TB_HOLD_MS" in down and "kind:'col'" in down
    # the shared drag plumbing hands column drags to their own functions
    assert "if(st.kind==='col') return tbBeginColDrag(st, x, y);" in js_function("tbBeginDrag")
    assert "if(d.kind==='col') return tbColDragUpdate();" in js_function("tbDragUpdate")
    assert "if(d.kind==='col'){" in js_function("tbDrop")


POINTER = """
  const listeners={};
  globalThis.document={addEventListener:(t,f)=>{ listeners[t]=f; }, removeEventListener:()=>{}};
  let READONLY=false; const TB_HOLD_MS=380;
  const tb={drag:null, pend:null, renaming:null};
  const began=[];
  function tbBeginDrag(st){ began.push(st.kind||'person'); }
  function tbPointerMove(){} function tbPointerUp(){} function tbPointerCancel(){}
  const cls=()=>({add(){}, remove(){}});
  const col={dataset:{team:'a'}};
  const hd={closest:s=>s==='.tbcol' ? col : null, classList:cls()};
  const card={dataset:{pid:'p1', from:'a'}, classList:cls()};
  const on=sel=>({closest:s=>s===sel ? {} : null});
  const nowhere={closest:()=>null};
  const ev=(target, type, cur)=>({button:0, pointerId:1, clientX:10, clientY:10, pointerType:type,
                                 target, currentTarget:cur, preventDefault(){}});
"""


def test_mouse_needs_the_grip_finger_holds_the_header_and_cards_still_drag():
    out = json.loads(run_js(POINTER + fns("tbColPointerDown", "tbPointerDown") + """
      const r={};
      tbColPointerDown(ev(nowhere, 'mouse', hd)); r.mouseName=tb.pend; tb.pend=null;
      tbColPointerDown(ev(on('[data-colgrip]'), 'mouse', hd)); r.mouseGrip=tb.pend && tb.pend.kind; tb.pend=null;
      tbColPointerDown(ev(on('[data-tmenu],input'), 'touch', hd)); r.touchMenu=tb.pend; tb.pend=null;
      tbColPointerDown(ev(nowhere, 'touch', hd)); r.touchHold=tb.pend && [tb.pend.kind, tb.pend.timer>0];
      clearTimeout(tb.pend.timer); tb.pend=null;
      tb.renaming='a'; tbColPointerDown(ev(on('[data-colgrip]'), 'mouse', hd)); r.renaming=tb.pend; tb.renaming=null;
      READONLY=true; tbColPointerDown(ev(on('[data-colgrip]'), 'mouse', hd)); r.ro=tb.pend; READONLY=false;
      // a person card: the person drag, never a column drag
      tbPointerDown(ev(nowhere, 'mouse', card)); r.card=tb.pend && [tb.pend.kind||'person', tb.pend.card===card];
      console.log(JSON.stringify(r));
    """))
    assert out == {"mouseName": None, "mouseGrip": "col", "touchMenu": None,
                   "touchHold": ["col", True], "renaming": None, "ro": None,
                   "card": ["person", True]}


# The people list's training split (user, 2026-10-30: "the sorting came to
# training / didn't come to training needs to be in the team builder").

def test_people_list_splits_attended_training_first_then_by_title():
    out = json.loads(run_js("const TITLES=" + json.dumps(["Lead", "Lead Assist", "Designer", "General Installer"])
                            + ";\n" + fns("tbPoolSections") + """
      const P=(id, name, title, tr)=>({id, name, title, tr});
      const people=[P('1','Zed','General Installer',1), P('2','Amy','General Installer',1), P('3','Bo','Lead',0),
                    P('4','Cy','Designer',0), P('5','Di','General Installer',0), P('6','Ed','Lead Assist',1)];
      const isT=p=>p.title==='Lead' || !!p.tr;
      const r=tbPoolSections(people, isT, TITLES);
      const flat=gs=>gs.map(g=>[g.title, g.people.map(p=>p.name)]);
      console.log(JSON.stringify({trained:flat(r.trained), untrained:flat(r.untrained),
        empty:tbPoolSections([], isT, TITLES), pure:people.map(p=>p.name)}));
    """))
    assert out["trained"] == [["Lead", ["Bo"]], ["Lead Assist", ["Ed"]], ["General Installer", ["Amy", "Zed"]]]
    assert out["untrained"] == [["Designer", ["Cy"]], ["General Installer", ["Di"]]]
    assert out["empty"] == {"trained": [], "untrained": []}
    assert out["pure"] == ["Zed", "Amy", "Bo", "Cy", "Di", "Ed"]


def test_people_list_uses_the_pages_training_data_and_staff_dialog_toggle():
    assert "return p.title==='Lead' || attendedTraining(p, staffing, trainingDays);" in js_function("tbIsTrained")
    pool = js_function("tbPool")
    assert "if(f==='attended') return attendedTraining(p, staffing, trainingDays);" in pool
    draw = js_function("drawTeamBuilder")
    assert "['attended','Attended training']" in draw
    assert "tbPoolSections(people, tbIsTrained, TITLES)" in draw
    assert draw.index("${esc(TRAINED_LBL)}") < draw.index("Didn't attend training <span")
    assert "Show people who didn't attend training" in draw
    assert "const showUn=tbShowUntrained() || !!tb.q.trim();" in draw     # a search finds everyone
    assert "localStorage" in js_function("setTbShowUntrained") and "try{" in js_function("setTbShowUntrained")
    assert "setTbShowUntrained(un.checked)" in js_function("tbWire")
    assert "—" not in draw
