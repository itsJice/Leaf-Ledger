"""Team chips in Send mass text, step 1 "Choose people" (review_template.html).

User, 2026-10-25: "i should be able to mass text and select teams too".
Each saved team for this page's season gets a group chip after the standard
groups. It behaves like the others: a tap adds the team's textable members,
a second tap takes them off, and groups combine. These run the template's
own functions in node. FAKE people only.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_dallas_nights import fns

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

# Stand-ins for the page globals the group logic reads.
PRELUDE = r"""
const smsNumber=v=>{ const d=String(v||'').replace(/\D/g,''); return d.length===10?d:''; };
const txtActive=p=>p.active!==false;
const TXT_GROUPS=[{key:'all', label:'Everyone', test:txtActive},
                  {key:'en', label:'English speakers', test:p=>txtActive(p)&&p.lang==='English'}];
let txt={picked:[]}; const txtSave=()=>{};
let teams=[
  {id:'tA', name:"Alberto's team", season:2026, leadId:'p1', members:['p1','p2','p3','p4']},
  {id:'tC', name:"Chris's team", season:2026, leadId:'p5', members:['p5','p6']},
  {id:'tOld', name:'Old team', season:2025, leadId:'', members:['p1']},
];
const teamSeasonDefault=()=>2026;
const roster=[
  {id:'p1', name:'Ana Uno', phone:'(713) 555-0101', lang:'English'},
  {id:'p2', name:'Ben Dos', phone:'713-555-0102', lang:'Spanish'},
  {id:'p3', name:'Cy Tres', phone:'', lang:'English'},                 // no phone: greyed, not counted
  {id:'p4', name:'Di Cuatro', phone:'7135550104', lang:'English', active:false}, // not working
  {id:'p5', name:'Ed Cinco', phone:'7135550105', lang:'English'},
  {id:'p6', name:'Flo Seis', phone:'7135550106', lang:'Bilingual'},
  {id:'p7', name:'Gus Siete', phone:'7135550107', lang:'English'},
];
"""
HELPERS = PRELUDE + fns("teamsForSeason", "txtTeamGroups", "txtAllGroups", "txtGroupState", "txtToggle")

# One chip tap, the way txtWirePick does it.
TAP = r"""
function tap(key){
  const g=txtAllGroups().find(x=>x.key===key);
  const st=txtGroupState(roster.filter(g.test), new Set(txt.picked));
  txtToggle(st.ids, !st.on);
  return [...txt.picked].sort();
}
function chip(key){
  const g=txtAllGroups().find(x=>x.key===key);
  const st=txtGroupState(roster.filter(g.test), new Set(txt.picked));
  return {n:st.ids.length, on:st.on};
}
"""


def run(body):
    return json.loads(run_js(HELPERS + TAP + body))


def test_one_chip_per_team_this_season_after_the_standard_groups():
    out = run("""console.log(JSON.stringify(txtAllGroups().map(g=>[g.key, g.label, !!g.team])))""")
    assert out == [
        ["all", "Everyone", False],
        ["en", "English speakers", False],
        ["team:tA", "Alberto's team", True],
        ["team:tC", "Chris's team", True],
    ]


def test_team_chip_counts_only_textable_members_working_this_season():
    out = run("""console.log(JSON.stringify([chip('team:tA'), chip('team:tC')]))""")
    # Alberto's team: p1, p2 count; p3 has no phone; p4 is not working this season.
    assert out == [{"n": 2, "on": False}, {"n": 2, "on": False}]


def test_tap_adds_a_team_second_tap_removes_and_groups_combine():
    out = run("""console.log(JSON.stringify({
      a: tap('team:tA'), aOn: chip('team:tA').on,
      both: tap('team:tC'),
      offA: tap('team:tA'),
      plusEn: tap('en'),
      chipA: chip('team:tA'),
    }))""")
    assert out["a"] == ["p1", "p2"]
    assert out["aOn"] is True
    assert out["both"] == ["p1", "p2", "p5", "p6"]
    assert out["offA"] == ["p5", "p6"]
    # English speakers (p1, p5, p7) combines with Chris's team.
    assert out["plusEn"] == ["p1", "p5", "p6", "p7"]
    # Alberto's team is only partly picked (p1 yes, p2 no), so its chip is off.
    assert out["chipA"] == {"n": 2, "on": False}


def test_no_teams_means_no_team_chips():
    out = run("""teams=[]; console.log(JSON.stringify(txtAllGroups().map(g=>g.key)))""")
    assert out == ["all", "en"]


def test_chooser_draws_and_wires_team_chips():
    pick = js_function("txtPickHTML")
    assert "txtAllGroups().map(" in pick
    assert "IC.users" in pick and "' team'" in pick
    wire = js_function("txtWirePick")
    assert "txtAllGroups().find(" in wire and "if(!g) return;" in wire
    # People rows show their team tag, as the staffing dialog does.
    assert 'class="asgteam"' in js_function("txtRowHTML")
    assert "#txtdlg .txtgrp.team .ic{" in TEMPLATE


def test_no_em_dashes_in_the_new_code():
    for name in ("txtTeamGroups", "txtAllGroups", "txtPickHTML", "txtRowHTML", "txtWirePick"):
        src = js_function(name)
        assert "—" not in src and "\\u2014" not in src
