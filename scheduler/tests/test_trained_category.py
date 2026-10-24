"""Roster "Attended training" category, and scheduling only from it (user,
2026-10-24: "make another category in the ui that says attended training.
category and i only want to schedule from there"). Attendance is derived from
staffing on the season's training days; nothing new is stored. FAKE people
only."""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

HELPERS = "\n".join(js_function(n) for n in (
    "trainingDatesFor", "rosterRank", "attendedTraining", "rosterGroupKey", "staffPickable"))

PRELUDE = """
let trainingDays = new Set(['2026-10-21','2026-10-23']);
let staffing = {
  '2026-10-23|Training': ['p1','p2','p6'],
  '2026-10-26|Crew A':   ['p3'],
};
const P = {
  p1: {id:'p1', active:true,  title:'General Installer', dates:['2026-10-26'], phone:'5550001'},
  p2: {id:'p2', active:true,  title:'Designer',          dates:[],             phone:''},
  p3: {id:'p3', active:true,  title:'General Installer', dates:['2026-10-26'], phone:'5550003'},
  p4: {id:'p4', active:true,  title:'Lead',              dates:['2026-10-26'], phone:'5550004'},
  p5: {id:'p5', active:true,  title:'Lead Assist',       dates:[],             phone:'5550005'},
  p6: {id:'p6', active:false, title:'General Installer', dates:['2026-10-26'], phone:'5550006'},
  p7: {id:'p7', active:false, title:'Lead',              dates:['2026-10-26'], phone:'5550007'},
};
const ids = Object.keys(P);
"""


def run(body):
    return json.loads(run_js(PRELUDE + HELPERS + "\n" + body))


def test_each_person_lands_in_exactly_one_roster_block():
    out = run("""console.log(JSON.stringify(
      Object.fromEntries(ids.map(id=>[id, rosterGroupKey(P[id], staffing, trainingDays)]))))""")
    assert out == {
        "p1": "trained",   # attended, would otherwise be "Ready to schedule"
        "p2": "trained",   # attended with no dates or phone: still trained, not a rank tier
        "p3": "rank0",     # on an install crew, not on training
        "p4": "rank0",     # Leads are not "attended" by title alone
        "p5": "rank2",
        "p6": "off",       # inactive wins even though they attended
        "p7": "off",
    }


def test_attended_training_needs_a_training_day_staffing():
    out = run("""console.log(JSON.stringify([
      attendedTraining(P.p1, staffing, trainingDays),
      attendedTraining(P.p3, staffing, trainingDays),
      attendedTraining(P.p1, staffing, new Set()),
      attendedTraining(P.p1, {}, trainingDays),
      attendedTraining(null, staffing, trainingDays),
    ]))""")
    assert out == [True, False, False, False, False]


def test_picker_offers_trained_and_leads_only_by_default():
    out = run("""const o={training:false, showAll:false, assigned:new Set(), staffing, trainingDays};
      console.log(JSON.stringify(ids.filter(id=>staffPickable(P[id], o))))""")
    # p1/p2 trained, p4 is a Lead. Inactive people (p6 trained, p7 Lead) stay out.
    assert out == ["p1", "p2", "p4"]


def test_already_assigned_people_never_drop_out_of_the_picker():
    out = run("""const o={training:false, showAll:false, assigned:new Set(['p3','p7']), staffing, trainingDays};
      console.log(JSON.stringify(ids.filter(id=>staffPickable(P[id], o))))""")
    assert out == ["p1", "p2", "p3", "p4", "p7"]


def test_assigned_can_be_an_array():
    out = run("""console.log(JSON.stringify(staffPickable(P.p3, {assigned:['p3'], staffing, trainingDays})))""")
    assert out is True


def test_toggle_and_training_shifts_show_every_active_person():
    out = run("""const all={training:false, showAll:true, assigned:new Set(), staffing, trainingDays};
      const tr={training:true, showAll:false, assigned:new Set(), staffing, trainingDays};
      console.log(JSON.stringify([ids.filter(id=>staffPickable(P[id], all)),
                                  ids.filter(id=>staffPickable(P[id], tr))]))""")
    assert out == [["p1", "p2", "p3", "p4", "p5"], ["p1", "p2", "p3", "p4", "p5"]]


def test_no_training_days_means_only_leads_by_default():
    out = run("""const o={training:false, showAll:false, assigned:new Set(), staffing, trainingDays:new Set()};
      console.log(JSON.stringify(ids.filter(id=>staffPickable(P[id], o))))""")
    assert out == ["p4"]


def test_every_staffing_path_uses_the_picker_rule():
    assign = js_function("assignReadyRosterToShift")
    assert "staffPickable(p, o)" in assign
    dlg = js_function("drawStaffDlg")
    assert "roster.filter(p=>staffPickable(p, pick))" in dlg
    assert "untrainedToggleHTML(sh)" in dlg
    card = js_function("crewShiftSection")
    assert "staffPickable(p, pick)" in card and "untrainedToggleHTML(sh)" in card
    assert '<div id="stftrain"></div>' in TEMPLATE


def test_toggle_is_remembered_with_guarded_storage():
    get, put = js_function("stfShowUntrained"), js_function("setStfShowUntrained")
    assert "try{" in get and "catch(e)" in get
    assert "try{" in put and "catch(e)" in put
    assert "Show people who didn't attend training" in js_function("untrainedToggleHTML")
    # Training shifts list everyone, so no toggle there.
    assert "if(sh.training) return '';" in js_function("untrainedToggleHTML")


def test_roster_and_mass_text_have_the_new_category_first():
    assert "const TRAINED_LBL = 'Attended training';" in TEMPLATE
    secs = js_function("rosterSections")
    assert secs.index("key:'trained'") < secs.index("RANK_LBL.forEach")
    assert "{key:'trained', label:TRAINED_LBL," in TEMPLATE
    pick = js_function("txtPickHTML")
    assert pick.index("section(TRAINED_LBL") < pick.index("RANK_LBL.map")


def test_no_em_dashes_in_the_new_code():
    for name in ("attendedTraining", "rosterGroupKey", "staffPickable", "untrainedToggleHTML",
                 "stfShowUntrained", "setStfShowUntrained", "staffPickOpts", "txtSecKey"):
        src = js_function(name)
        assert "—" not in src and "\\u2014" not in src
