"""Built crew-days keep the build's route order after the shared state loads
(review_template.html applyPlacement), and a training day's card comes back
after a drag (render -> materializeTrainingDays).

Found 10/24/2026 while rearranging the Dallas week: every built day the board
loaded showed (and printed) its stops in row-number order -- Wed 11/4 Crew 3
read Mercury Grill, Las Colinas, Preston Forest instead of the planned Las
Colinas, Preston Forest, Mercury Grill -- because applyPlacement pushes rows in
object-key order and routeDay trusts an unedited day's order as planned.
Names are made up.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

HARNESS = """
const K={CREWS:['Crew 1','Crew 2','Crew 3']};
const SPEC={calendar:[{date:'2026-11-04', dow:'Wed'}, {date:'2026-11-05', dow:'Thu'}]};
const DATA={days:[{id:'2026-11-04|Crew 3|0', date:'2026-11-04', crew:'Crew 3', stops:[79,80,74]},
                  {id:'2026-11-05|Crew 3|0', date:'2026-11-05', crew:'Crew 3', stops:[62]}]};
function hydrate(d){ return {...d, stops:[...d.stops]}; }
function refreshDerivedMeta(){}
let days=DATA.days.map(hydrate);
""" + TEMPLATE[TEMPLATE.index("const BASELINE_STOPS = {};"):TEMPLATE.index("let approved = new Set()")] \
    + js_function("applyPlacement") + js_function("currentPlacement")


def run(body):
    return json.loads(run_js(HARNESS + body))


def test_unchanged_built_day_keeps_its_planned_order_after_a_load():
    out = run("""
      // the shared document, as currentPlacement() writes it: row -> [day ids]
      applyPlacement({74:['2026-11-04|Crew 3|0'], 79:['2026-11-04|Crew 3|0'], 80:['2026-11-04|Crew 3|0'],
                      62:['2026-11-05|Crew 3|0']});
      console.log(JSON.stringify(days.map(d=>[d.id, d.stops, !!d.edited])));
    """)
    assert out == [["2026-11-04|Crew 3|0", [79, 80, 74], False], ["2026-11-05|Crew 3|0", [62], False]]


def test_a_changed_day_is_edited_and_an_undo_back_makes_it_planned_again():
    out = run("""
      applyPlacement({74:['2026-11-05|Crew 3|0'], 79:['2026-11-04|Crew 3|0'], 80:['2026-11-04|Crew 3|0'],
                      62:['2026-11-05|Crew 3|0']});
      const moved=days.map(d=>[d.id, d.stops, !!d.edited]);
      applyPlacement({74:['2026-11-04|Crew 3|0'], 79:['2026-11-04|Crew 3|0'], 80:['2026-11-04|Crew 3|0'],
                      62:['2026-11-05|Crew 3|0']});
      console.log(JSON.stringify({moved, back:days.map(d=>[d.id, d.stops, !!d.edited])}));
    """)
    assert out["moved"] == [["2026-11-04|Crew 3|0", [79, 80], True], ["2026-11-05|Crew 3|0", [62, 74], True]]
    assert out["back"] == [["2026-11-04|Crew 3|0", [79, 80, 74], False], ["2026-11-05|Crew 3|0", [62], False]]


def test_training_card_comes_back_on_every_render():
    render = js_function("render")
    assert render.index("refreshDerivedMeta();") < render.index("materializeTrainingDays();") \
        < render.index("days.forEach(d=>{")
    # the record it rebuilds from is trainingDays, which removing a date clears first
    assert "trainingDays.delete(date);" in js_function("removeAddedDate")
