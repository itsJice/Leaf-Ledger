"""Moving a stop onto a date that already passed (review_template.html).

Comments #43 (11/20/2026): Nicole tried to move Michol Ecklund from Crew 3 to
Crew 1 on 11/18 after 11/18 had passed. The Move dialog greyed every past
date out as "Too early to move it there", so the board could not record where
the stop really went. Past dates are now a warning, not a block: they show as
"Wed 11/18/26 (already passed)" and picking one asks a plain "This date
already passed. Move anyway?". The real hard blocks (dropped clients,
confirmed stops, joint-crew integrity) stay. These run the template's own
functions in node. Names are made up.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

TODAY = "2026-11-20"


def top_function(name):
    """A top-level function whose parameters hold braces (a destructured
    default), which js_function's first-brace scan can't take."""
    start = TEMPLATE.index(f"function {name}(")
    return TEMPLATE[start:TEMPLATE.index("\n}\n", start) + 2]

BASE = f"""
function todayISO(){{ return '{TODAY}'; }}
function fmtDate(s){{ return 'Wed '+s; }}
const SPEC={{codes:{{DROPPED:{{msg:'No 2026 install for this client'}}}}, calendar:[]}};
function codeMsg(c){{ return (SPEC.codes[c]||{{}}).msg || c; }}
let HARD={{}};
function hardBlockers(row, date){{ return HARD[row+'|'+date] || []; }}
let DRAFT=null, asked=[], answer=true, alerts=[], applied=[];
function confirm(m){{ asked.push(m); return answer; }}
function alert(m){{ alerts.push(m); }}
function roBlocked(){{ return false; }}
function pushUndo(){{}}
function render(){{}}
function applyMove(row, to){{ applied.push([row, to]); }}
let CHK={{blockers:[], warnings:[]}};
function checkPlan(){{ return CHK; }}
let days=[];
""" + "\n".join(js_function(n) for n in
                ("isPastDate", "dateBlockers", "dateLabel", "rearrangeIntoPast")) + "\n" + top_function("commitPlan") + """
const PAST_CONFIRM='This date already passed. Move anyway?';
"""


def run(body):
    return json.loads(run_js(BASE + body))


def test_past_dates_are_flagged_not_blocked():
    out = run("""
      HARD={'7|2026-11-30':['DROPPED']};
      console.log(JSON.stringify({
        past:['2026-11-18','2026-11-19','2026-11-20','2026-11-21','', 'NOINSTALL'].map(isPastDate),
        blockPast:dateBlockers(5,'2026-11-18'), blockToday:dateBlockers(5,'2026-11-20'),
        labelPast:dateLabel(5,'2026-11-18'), labelFuture:dateLabel(5,'2026-11-24'),
        dropped:dateBlockers(7,'2026-11-30'), droppedLabel:dateLabel(7,'2026-11-30')}));
    """)
    assert out["past"] == [True, True, False, False, False, False]
    # A past date is never a blocker, so its option is selectable...
    assert out["blockPast"] == [] and out["blockToday"] == []
    # ...and says why it is flagged, without the old misleading wording.
    assert out["labelPast"] == " (already passed)"
    assert out["labelFuture"] == ""
    # A real hard block still blocks and still says its own reason.
    assert out["dropped"] == ["DROPPED"]
    assert out["droppedLabel"] == " — No 2026 install for this client"


def test_commit_asks_once_for_a_past_date():
    out = run("""
      const ops=[{row:5, to:'2026-11-18|Crew 1|0'}];
      const res={};
      CHK={blockers:[], warnings:[{code:'PAST', msg:'Michol: Wed 2026-11-18 already passed'}]};
      res.yes=commitPlan(ops); res.askedYes=asked.slice(); res.appliedYes=applied.slice();
      asked=[]; applied=[]; answer=false;
      res.no=commitPlan(ops); res.askedNo=asked.slice(); res.appliedNo=applied.slice();
      // The move dialog already asked when the date was picked.
      asked=[]; applied=[]; answer=true;
      res.pre=commitPlan(ops, {pastOk:true}); res.askedPre=asked.slice();
      // A past date plus another warning: the plain question, then the usual heads-up.
      asked=[];
      CHK={blockers:[], warnings:[{code:'PAST', msg:'x'}, {code:'OVER', msg:'Crew 1 runs long'}]};
      commitPlan(ops); res.askedBoth=asked.slice();
      // In a draft nothing pops up.
      asked=[]; DRAFT={};
      res.draft=commitPlan(ops); res.askedDraft=asked.slice(); DRAFT=null;
      // Hard blocks still refuse, past or not.
      asked=[]; alerts=[];
      CHK={blockers:[{code:'JOINT', msg:'Michol is a joint job'}], warnings:[{code:'PAST', msg:'x'}]};
      res.blocked=commitPlan(ops); res.askedBlocked=asked.slice(); res.alerts=alerts.slice();
      console.log(JSON.stringify(res));
    """)
    q = "This date already passed. Move anyway?"
    assert out["yes"] is True and out["askedYes"] == [q]
    assert out["appliedYes"] == [[5, "2026-11-18|Crew 1|0"]]
    assert out["no"] is False and out["askedNo"] == [q] and out["appliedNo"] == []
    assert out["pre"] is True and out["askedPre"] == []
    assert out["askedBoth"][0] == q
    assert "Crew 1 runs long" in out["askedBoth"][1] and "already passed" not in out["askedBoth"][1]
    assert out["draft"] is True and out["askedDraft"] == []
    assert out["blocked"] is False and out["askedBlocked"] == []
    assert "joint job" in out["alerts"][0]


def test_rearrange_into_the_past_is_flagged():
    out = run("""
      days=[{id:'2026-11-18|Crew 3|0', date:'2026-11-18', stops:[5]},
            {id:'2026-11-24|Crew 1|0', date:'2026-11-24', stops:[6]},
            {id:'2026-11-25|Crew 1|0', date:'2026-11-25', stops:[]}];
      console.log(JSON.stringify({
        sameDayPast:rearrangeIntoPast([['2026-11-18|Crew 3|0','2026-11-18|Crew 1|0']]),
        swapBack:rearrangeIntoPast([['2026-11-24|Crew 1|0','2026-11-18|Crew 3|0']]),
        future:rearrangeIntoPast([['2026-11-24|Crew 1|0','2026-11-25|Crew 2|0']])}));
    """)
    assert out == {"sameDayPast": True, "swapBack": True, "future": False}


def test_every_path_warns_instead_of_blocking():
    # The old floor is gone; nothing words a past date "Too early" any more.
    assert "pastBlockers" not in TEMPLATE and "minAllowedDate" not in TEMPLATE
    code = "\n".join(l for l in TEMPLATE.splitlines() if not l.strip().startswith(("//", "*", "/*")))
    assert "Too early" not in code
    # checkPlan (drag onto a crew card, slot finder, calendar drops) adds PAST as a warning.
    assert "code:'PAST'" in js_function("checkPlan")
    # The move dialog asks when a past date is picked and remembers the answer.
    dlg = js_function("openMoveDlg")
    assert "isPastDate(dsel.value)" in dlg and "PAST_CONFIRM" in dlg and "mvPastOk=dsel.value" in dlg
    assert re.search(r"commitPlan\(planFor\(mvRow, to\), \{pastOk:", TEMPLATE)
    # Whole-day moves ask too.
    assert "rearrangeIntoPast(opt.pairs)" in js_function("applyRearrange")
    # Find a date never suggests a passed date unless it was the one asked for.
    assert "isPastDate(s.date) && s.date!==wantDate" in js_function("findSlots")
