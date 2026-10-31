"""Crew responsibility tags on the Install Schedule (review_template.html).

User, 2026-10-31: "Please add responsibility tags to the crew roster, similar
to the English/Spanish tags. New tags: KIT CAPTAIN, VAN CLEANLINESS, DRIVER,
BOX TRUCK DRIVER ... These are assigned responsibilities, not additional
management positions. Each person should know what they own."

Kit Captain / Van Cleanliness Captain / Driver are per team, on the team
record as kitId / vanId (the #138 Kit / Van Manager fields, renamed) and
driverId. Box Truck Driver isn't tied to a team: one per season, in the
shared `seasonRoles` {"2026": {"boxTruckId": id}}. These run the template's
own functions in node. FAKE people only.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_dallas_nights import MERGE, const_line, fns

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def duties_consts():
    """The DUTIES block (several lines) through SEASON_DUTIES."""
    start = TEMPLATE.index("const DUTIES=[")
    end = TEMPLATE.index("\n", TEMPLATE.index("const TEAM_DUTIES="))
    return TEMPLATE[start:end]


HELPERS = (
    "\nconst TEAM_NAME_MAX=40;\n" + const_line("TEAM_ROLES") + "\n" + duties_consts() + "\n"
    + "function esc(x){ return String(x==null?'':x).replace(/&/g,'&amp;').replace(/</g,'&lt;')"
    + ".replace(/>/g,'&gt;').replace(/\"/g,'&quot;'); }\n"
    + fns("normTeamName", "normTeams", "teamsForSeason", "teamsOfPerson", "teamLeadFirst", "teamsAfterDrop",
          "teamsWithRole", "teamsWithCopy", "teamRolesOf", "normSeasonRoles", "seasonRoleOf", "seasonRolesWith",
          "personDuties", "dutyLines", "dutyPill", "teamDutiesOnShift"))

TEAMS = """
  const L=[
    {id:'a', name:'Crew 1 | Ana', season:2026, leadId:'', members:['p1','p2','p3'], kitId:'p2', vanId:'p3', driverId:'p1'},
    {id:'b', name:'Crew 2 | Ben', season:2026, leadId:'', members:['p4','p5','p2'], kitId:'p4', driverId:'p2'},
    {id:'o', name:'Old', season:2025, leadId:'', members:['p1'], kitId:'p1'},
  ];
  const R={"2026": {boxTruckId:'p2'}};
"""


def run(body):
    return json.loads(run_js(HELPERS + TEAMS + body))


def test_the_four_tags_and_their_descriptions():
    out = run("console.log(JSON.stringify(DUTIES.map(d=>[d.key, d.tag, d.label, !!d.season, d.desc])));")
    assert [x[:4] for x in out] == [
        ["kitId", "KIT CAPTAIN", "Kit Captain", False],
        ["vanId", "VAN CLEANLINESS", "Van Cleanliness Captain", False],
        ["driverId", "DRIVER", "Driver", False],
        ["boxTruckId", "BOX TRUCK DRIVER", "Box Truck Driver", True],
    ]
    assert out[0][4].startswith("Account for the crew toolkit each morning")
    assert out[1][4].startswith("Make sure trash is removed daily")
    assert out[2][4] == "Responsible for assigned vehicle operation and coordinating vehicle readiness."


def test_driver_is_stored_like_kit_and_van_and_old_documents_still_load():
    out = run("""
      console.log(JSON.stringify({
        n:normTeams([{id:'x', name:'X', season:2026, members:['p1','p2'], kitId:'p1', vanId:'p2', driverId:'p9'}], null, 2026)[0],
        old:normTeams([{id:'x', name:'X', season:2026, members:['p1','p2'], kitId:'p1', vanId:'p2'}], null, 2026)[0],
        set:teamsWithRole(L, 'a', 'driverId', 'p3')[0].driverId,       // replaces the old holder
        cleared:'driverId' in teamsWithRole(L, 'a', 'driverId', '')[0],
        moved:teamsAfterDrop(L, {pid:'p1', from:'a', to:'b'})[0],     // leaving clears their duties
        copy:teamsWithCopy(L, 'a', 'a2', 'Copy')[1].driverId,
        roles:teamRolesOf(L[0], 'p1'),
      }));
    """)
    # a driver who isn't on the team drops
    assert out["n"] == {"id": "x", "name": "X", "season": 2026, "leadId": "", "members": ["p1", "p2"],
                        "kitId": "p1", "vanId": "p2"}
    assert out["old"]["kitId"] == "p1" and out["old"]["vanId"] == "p2"
    assert out["set"] == "p3" and out["cleared"] is False
    assert "driverId" not in out["moved"] and out["moved"]["members"] == ["p2", "p3"]
    assert out["copy"] == "p1"
    assert out["roles"] == ["Driver"]


def test_box_truck_driver_is_one_per_season():
    out = run("""
      const a=seasonRolesWith({}, 2026, 'boxTruckId', 'p1');
      const b=seasonRolesWith(a, 2026, 'boxTruckId', 'p5');         // replaces p1
      const c=seasonRolesWith(b, 2025, 'boxTruckId', 'p1');
      const d=seasonRolesWith(c, 2026, 'boxTruckId', '');
      console.log(JSON.stringify({a, b, c, d, of:[seasonRoleOf(c, 2026, 'boxTruckId'), seasonRoleOf(c, '2025', 'boxTruckId'),
          seasonRoleOf(null, 2026, 'boxTruckId')],
        norm:normSeasonRoles({"2026":{boxTruckId:'p1', junk:'x'}, "1999":{boxTruckId:'p1'}, "2025":{boxTruckId:'gone'},
                              "2027":'x'}, ['p1']),
        bad:[normSeasonRoles(null), normSeasonRoles([1]), normSeasonRoles('x')]}));
    """)
    assert out["a"] == {"2026": {"boxTruckId": "p1"}}
    assert out["b"] == {"2026": {"boxTruckId": "p5"}}
    assert out["c"] == {"2026": {"boxTruckId": "p5"}, "2025": {"boxTruckId": "p1"}}
    assert out["d"] == {"2025": {"boxTruckId": "p1"}}
    assert out["of"] == ["p5", "p1", ""]
    assert out["norm"] == {"2026": {"boxTruckId": "p1"}}           # unknown people / years / keys drop
    assert out["bad"] == [{}, {}, {}]


def test_what_a_person_owns():
    out = run("""
      const f=(pid, team)=>personDuties(L, R, pid, 2026, team).map(d=>[d.tag, d.teams]);
      console.log(JSON.stringify({p1:f('p1'), p2:f('p2'), p4:f('p4'), p9:f('p9'),
        p2OnA:f('p2', L[0]), p2OnB:f('p2', L[1]),
        lines:dutyLines(personDuties(L, R, 'p1', 2026)),
        pill:dutyPill(personDuties(L, R, 'p2', 2026)[0])}));
    """)
    assert out["p1"] == [["DRIVER", ["Crew 1 | Ana"]]]            # 2025's Kit doesn't count in 2026
    # several at once, in tag order, the box truck with no team
    assert out["p2"] == [["KIT CAPTAIN", ["Crew 1 | Ana"]], ["DRIVER", ["Crew 2 | Ben"]], ["BOX TRUCK DRIVER", []]]
    assert out["p4"] == [["KIT CAPTAIN", ["Crew 2 | Ben"]]]
    assert out["p9"] == []
    assert out["p2OnA"] == [["KIT CAPTAIN", ["Crew 1 | Ana"]], ["BOX TRUCK DRIVER", []]]
    assert out["p2OnB"] == [["DRIVER", ["Crew 2 | Ben"]], ["BOX TRUCK DRIVER", []]]
    assert out["lines"] == ["Driver: Responsible for assigned vehicle operation and coordinating vehicle readiness."]
    assert out["pill"].startswith('<span class="pill duty duty-kit" title="Kit Captain (Crew 1 | Ana): Account for')
    assert out["pill"].endswith(">KIT CAPTAIN</span>")


def test_crew_sheet_duties_come_from_the_team_on_the_shift():
    out = run("""
      console.log(JSON.stringify([
        teamDutiesOnShift([L[0], L[1]], new Set(['p1','p2','p3']), R, 2026),
        teamDutiesOnShift([L[1], L[0]], new Set(['p2','p4','p5']), R, 2026),
        teamDutiesOnShift([L[0]], new Set(['p5']), {}, 2026),
      ]));
    """)
    assert out[0] == {"p2": ["Kit Captain", "Box Truck Driver"], "p3": ["Van Cleanliness Captain"], "p1": ["Driver"]}
    assert out[1] == {"p4": ["Kit Captain"], "p2": ["Driver", "Box Truck Driver"]}
    assert out[2] == {}


def test_season_roles_are_shared_saved_and_merged():
    assert "'seasonRoles'" in re.search(r"const SHARED_MAP_KEYS=.*", TEMPLATE).group(0)
    for fn in ("restoreBlob", "restoreHistoryEntry"):
        src = js_function(fn)
        assert src.index("seasonRoles = loadSeasonRoles(") > src.index("roster = normRoster(")
    boot = TEMPLATE[TEMPLATE.index("const s = JSON.parse(localStorage.getItem(LS_KEY)||'{}');"):]
    assert boot.index("seasonRoles = loadSeasonRoles(s.seasonRoles)") > boot.index("roster = normRoster(s.roster)")
    assert "seasonRoles = loadSeasonRoles(seasonRoles)" in js_function("render")
    assert "seasonRoles = loadSeasonRoles(j.inherit.seasonRoles)" in js_function("pullSharedNow")
    out = json.loads(run_js(MERGE + """
      const r=mergeShared({seasonRoles:{}}, {seasonRoles:{"2026":{boxTruckId:'p1'}}}, {seasonRoles:{}, teams:[]});
      console.log(JSON.stringify([r.state.seasonRoles, r.conflicts]));
    """))
    assert out == [{"2026": {"boxTruckId": "p1"}}, []]


def test_tags_show_where_the_language_tags_do():
    assert "dutyPillsHTML(pid)" in js_function("teamBadgeHTML")          # roster list, Staff, mass text rows
    assert "teamBadgeHTML(p.id)" in js_function("personRow")
    card = js_function("tbCardHTML")
    assert "personDuties(teams, seasonRoles, p.id, tb.season, team)" in card and "tbduties" in card
    det = js_function("personDetailHTML")
    assert "duties.map(dutyPill)" in det and "dutiesHTML(duties)" in det
    assert "d.desc" in js_function("dutiesHTML")
    assert 'id="perduties"' in TEMPLATE and "drawPerDuties(person);" in js_function("openPersonDlg")


def test_assigning_from_the_builder_and_the_popup():
    col = js_function("tbColHTML")
    assert "tbDutyPickersHTML(t, ps)" in col
    pick = js_function("tbDutyPickersHTML")
    assert "ps.map(p=>" in pick                      # only the team's own members
    assert "if(READONLY)" in pick                     # view only: names, no selects
    box = js_function("tbBoxTruckHTML")
    assert 'id="tmboxtruck"' in box and "if(READONLY)" in box
    assert "tbBoxTruckHTML(season)" in js_function("drawTeamBuilder")
    wire = js_function("tbWire")
    assert wire.index("if(READONLY) return;") < wire.index("select[data-duty]")
    assert "teamsWithRole(teams, id, d.key, sel.value)" in wire
    assert "setSeasonRole(tb.season, 'boxTruckId', bx.value)" in wire
    menu = js_function("tbPersonMenu")
    assert "Make Box Truck Driver" in menu and "...TEAM_DUTIES.map(d=>role(d.key, d.label)), box," in menu
    assert "...TEAM_DUTIES.map(d=>({label:`Set ${d.label}`" in js_function("tbTeamMenu")
    assert js_function("setSeasonRole").index("if(roBlocked()) return false;") < js_function("setSeasonRole").index("pushUndo()")
    save = TEMPLATE[TEMPLATE.index("document.getElementById('pergo').onclick"):]
    save = save[:save.index("perdlg.close(); persist(); render();")]
    assert "if(roBlocked()) return;" in save and "seasonRolesWith(seasonRoles, season, 'boxTruckId', pid)" in save


def test_crew_sheet_and_mass_text():
    man = js_function("manifestHTML")
    assert "const own=sh ? shiftDuties(sh) : {};" in man and '<span class="duty">' in man
    assert "teamDutiesOnShift(order, shiftAssigned(sh), seasonRoles, teamSeasonDefault())" in js_function("shiftDuties")
    fields = TEMPLATE[TEMPLATE.index("const TXT_FIELDS=["):TEMPLATE.index("const TXT_LANGS=")]
    assert "{key:'duties', label:'Responsibilities'" in fields and "dutyLines(personDuties(" in fields
