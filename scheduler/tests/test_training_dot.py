"""Roster "attended training" dot (user, 2026-10-24: "some kind of indicator
that they attended training for this year. A dot that when you hover over it
says attended training"). Who attended is derived from staffing on the
season's training days; nothing new is stored. FAKE people only."""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

HELPERS = "\n".join(js_function(n) for n in (
    "fmtMDYYYY", "esc", "trainingDatesFor", "trainingLabel", "personTrainingLabel",
    "trainingDotHTML", "rosterPrintColumns", "rosterPrintCell"))

PRELUDE = """
function fmtPhone(p){ return p; }
function fmtFreeDays(d){ return ''; }
function fmtTextDay(iso){ return ''; }
let trainingDays = new Set(['2026-10-21','2026-10-23']);
let staffing = {
  '2026-10-23|Training': ['p1','p2'],
  '2026-10-21|Training': ['p2'],
  '2026-10-26|Crew A':   ['p3'],
  '2026-11-02|Training': ['p3'],
};
"""


def run(body):
    return json.loads(run_js(PRELUDE + HELPERS + "\n" + body))


def test_dates_come_from_training_day_staffing_only():
    out = run("""console.log(JSON.stringify([
      trainingDatesFor('p1', staffing, trainingDays),
      trainingDatesFor('p2', staffing, trainingDays),
      trainingDatesFor('p3', staffing, trainingDays),
      trainingDatesFor('p9', staffing, trainingDays),
      trainingDatesFor('p1', {}, trainingDays),
      trainingDatesFor('p1', null, null),
      trainingDatesFor('p1', staffing, ['2026-10-23']),
    ]))""")
    # p3 is on an install day and on a "Training" crew whose date is not a
    # training day any more: neither counts.
    assert out == [["2026-10-23"], ["2026-10-21", "2026-10-23"], [], [], [], [], ["2026-10-23"]]


def test_label_is_mm_dd_yyyy_comma_separated():
    out = run("""console.log(JSON.stringify([
      trainingLabel(['2026-10-23']),
      trainingLabel(['2026-10-21','2026-10-23']),
      trainingLabel([]),
      personTrainingLabel({id:'p2'}),
      personTrainingLabel(null),
    ]))""")
    assert out == ["Attended training 10/23/2026",
                   "Attended training 10/21/2026, 10/23/2026", "", "Attended training 10/21/2026, 10/23/2026", ""]


def test_dot_has_hover_text_and_accessible_label():
    out = run("""console.log(JSON.stringify([trainingDotHTML({id:'p1'}), trainingDotHTML({id:'p3'})]))""")
    dot, none = out
    assert 'class="trdot"' in dot and 'role="img"' in dot
    assert 'title="Attended training 10/23/2026"' in dot
    assert 'aria-label="Attended training 10/23/2026"' in dot
    assert none == ""


def test_print_roster_has_an_attended_training_column():
    out = run("""console.log(JSON.stringify([
      rosterPrintColumns().find(c=>c.key==='training').label,
      rosterPrintCell({id:'p1'}, 'training'),
      rosterPrintCell({id:'p3'}, 'training'),
    ]))""")
    assert out == ["Attended training", "Yes", ""]


def test_dot_is_on_the_roster_row_and_the_person_card():
    assert "<b>${esc(p.name)}</b>${trainingDotHTML(p)}" in TEMPLATE
    assert "<h3>${esc(p.name)}${trainingDotHTML(p)}</h3>" in TEMPLATE
    assert '<span class="pill trained">' in TEMPLATE


def test_no_em_dashes_in_the_new_code():
    for name in ("trainingDatesFor", "trainingLabel", "personTrainingLabel", "trainingDotHTML"):
        src = js_function(name)
        assert "—" not in src and "\\u2014" not in src
