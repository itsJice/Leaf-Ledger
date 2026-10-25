"""Availability is dates only (user, 2026-10-24: "take out the day and night
options for when people work and just select the dates. If someone selects
the dates for Dallas, let's assume that they can work nights"; follow-up:
"only have them gray unless they have no availability"). The stored `times`
field is kept untouched but never read or shown. FAKE people only."""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

AVAIL = js_function("fmtMDYYYY") + "\n" + js_function("availFor")

# A regular day crew and a Dallas night block (every night of the week).
PRELUDE = """
const DAY = {night:false, dallas:false, days:[{id:'2026-10-26|Crew 1', date:'2026-10-26'}]};
const DAL = {night:true, dallas:true, days:[
  {id:'2026-11-16|Crew 3', date:'2026-11-16'}, {id:'2026-11-17|Crew 3', date:'2026-11-17'},
  {id:'2026-11-18|Crew 3', date:'2026-11-18'}]};
const wk = ['2026-11-16','2026-11-17','2026-11-18'];
"""


def run(body):
    return json.loads(run_js(AVAIL + PRELUDE + body))


@needs_node
def test_availability_ignores_times():
    out = run("""console.log(JSON.stringify([
      availFor({times:[],        dates:['2026-10-26']}, DAY),
      availFor({times:['night'], dates:['2026-10-26']}, DAY),
      availFor({                 dates:['2026-10-26']}, DAY),
      availFor({times:['day','night'], dates:[]}, DAY),
    ]))""")
    assert [o["ok"] for o in out] == [True, True, True, False]
    assert out[3]["why"] == "No dates marked"


@needs_node
def test_dallas_dates_count_for_the_night_shift():
    out = run("""console.log(JSON.stringify([
      availFor({times:['day'], dates:wk}, DAL),
      availFor({times:[],      dates:wk}, DAL),
      availFor({times:['day','night'], dates:['2026-11-16']}, DAL),
    ]))""")
    assert out[0]["ok"] and out[1]["ok"]
    # Missing nights still grey them, with a date reason (no shift-time reason).
    assert out[2] == {"ok": False, "why": "Not available 11/17, 11/18"}


@needs_node
def test_missing_date_reason_is_date_based():
    out = run("""console.log(JSON.stringify(availFor({times:['day','night'], dates:['2026-10-27']}, DAY)))""")
    assert out == {"ok": False, "why": "Not available 10/26"}


@needs_node
def test_norm_roster_keeps_stored_times():
    src = "\n".join([
        "const TITLES=['Lead','Lead Assist','Designer','General Installer'];",
        "const LANGS=['English','Spanish','Both']; let nextPersonId=1;",
        "function workDates(){ return ['2026-10-26','2026-10-27']; }",
        "function normRatings(o){ return o||{}; }",
        "function normTexts(t){ return t||[]; }",
        "function fmtPhone(v){ return String(v||''); }",
        "function contractorFields(){ return {}; }",
        js_function("normRoster"),
        """console.log(JSON.stringify(normRoster([
          {id:'p1', first:'Ann', last:'A', times:['day'], dates:['2026-10-26']},
          {id:'p2', first:'Bo',  last:'B', times:[],      dates:[]},
        ]).map(p=>p.times)))""",
    ])
    assert json.loads(run_js(src)) == [["day"], []]


def test_editor_has_no_day_night_control_and_save_keeps_times():
    assert 'id="pertimes"' not in TEMPLATE
    assert "perTimes" not in TEMPLATE
    assert "Shift times they can work" not in TEMPLATE
    assert "No dates marked yet: this person" in TEMPLATE
    save = TEMPLATE[TEMPLATE.index("getElementById('pergo').onclick"):]
    save = save[:save.index("perdlg.close()")]
    # The edit merges onto the stored record, so not writing `times` keeps it.
    assert not re.search(r"\btimes\s*:", save)
    assert "Object.assign(editingPerson, fields)" in save


def test_cards_and_lists_show_no_shift_time_text():
    for gone in ("no shift times set", "' only'", "day + night", "(off: "):
        assert gone not in TEMPLATE
    # Nothing outside normRoster (carry-through) and the stale-tab merge
    # (keeps both sides' values) reads p.times.
    assert re.findall(r"p\.times", TEMPLATE) == ["p.times", "p.times"]
