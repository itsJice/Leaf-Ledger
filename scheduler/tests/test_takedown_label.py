"""January days say "Takedown", not "Install" (review_template.html).

The user (2026-10-27): "when anything is represented in January after
Christmas, it is a takedown unless otherwise specified. So when I print it,
it should say takedown on the manifest versus install." A printed Dallas
takedown night read "Install 2.6h · Drive 0.3h · ...". These run the
template's own functions in node: the pure kind rules, and the printed crew
sheet itself with its page globals stubbed.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

KIND_FNS = ["visitKind", "dayKind", "dayKindLabel", "stopKindWord"]
CUT = "2026-12-25"


def run(names, body):
    src = "\n".join(js_function(n) for n in names) + "\n" + body
    return json.loads(run_js(src))


@needs_node
def test_stop_kind_by_date_unless_the_visit_type_says_otherwise():
    out = run(KIND_FNS, f"""
      const CUT='{CUT}';
      console.log(JSON.stringify([
        visitKind('2027-01-02', 'Standard', CUT),   // January: takedown
        visitKind('2027-01-02', undefined, CUT),
        visitKind('2026-12-26', '', CUT),           // the day after Christmas
        visitKind('2026-12-10', 'Standard', CUT),   // December: still install
        visitKind('2026-12-25', null, CUT),         // Christmas itself: install
        visitKind('2027-01-02', 'Install', CUT),    // explicit install wins
        visitKind('2027-01-02', 'Reinstall', CUT),
        visitKind('2026-11-20', 'Takedown', CUT),   // event teardown in Nov
        visitKind('2027-01-02', 'Callback', CUT),   // not an install: date rules
      ]));
    """)
    assert out == ["takedown", "takedown", "takedown", "install", "install",
                   "install", "install", "takedown", "takedown"]


@needs_node
def test_day_kind_is_the_date_unless_every_stop_says_otherwise():
    out = run(KIND_FNS, f"""
      const CUT='{CUT}';
      console.log(JSON.stringify([
        dayKind('2027-01-02', ['Standard','Standard'], CUT),
        dayKind('2027-01-02', [], CUT),                    // no stops yet
        dayKind('2026-12-10', ['Standard'], CUT),
        dayKind('2027-01-02', ['Install','Reinstall'], CUT), // all explicit installs
        dayKind('2027-01-02', ['Install','Standard'], CUT),  // mixed: the date
        dayKind('2026-11-20', ['Takedown'], CUT),            // an event-teardown day
        dayKind('2026-11-20', ['Takedown','Standard'], CUT),
      ]));
    """)
    assert out == ["takedown", "takedown", "install", "install", "takedown",
                   "takedown", "install"]


# The printed crew sheet with everything around it stubbed: two stops, no
# notes, nobody assigned.
MANIFEST_STUBS = f"""
  const TAKEDOWN_CUTOFF='{CUT}', DEPART_MIN=510, LUNCH=40;
  const C={{1:{{name:'Stop One', boxes:2}}, 2:{{name:'Stop Two', boxes:0}},
           3:{{name:'Event Redo', visitType:'Install'}}}};
  const N={{1:1, 2:2, 3:3}}, stopPin={{}}, PIN_LABEL={{}}, PREF_LABEL={{}};
  const hold=new Set([1]);
  const dayCalc=d=>({{order:d.stops, inst:2.6, drive:18, total:174}});
  const leg=()=>600, effH=()=>1.3;
  const addrParts=()=>({{street:'1 Main', city:'Dallas', st:'TX', zip:'75201'}});
  const installNoteFor=()=>null, productionNoteFor=()=>null, staffAlertOf=()=>null, prefOf=()=>null;
  const fmtPhone=s=>s, fmtClock=m=>String(m), dayBoxes=()=>0;
  const stopBoxes=r=>(C[r]&&C[r].boxes!=null)?C[r].boxes:null;
  const crewTitle=()=>'Crew 3', dowName=()=>'Sat', fmtMDYYYY=s=>s;
  const shiftOfDay=()=>null, dayCoverage=()=>({{who:[], state:'ok'}}), shiftCoverage=dayCoverage;
  const coverageLabel=()=>'', shiftNoteOf=()=>null;
"""


def manifest(day_js):
    src = ("\n".join(js_function(n) for n in KIND_FNS + ["manifestHTML"])
           + MANIFEST_STUBS + f"\nconsole.log(JSON.stringify(manifestHTML({day_js})));")
    return json.loads(run_js(src))


@needs_node
def test_a_january_crew_sheet_prints_takedown():
    html = manifest("{date:'2027-01-02', stops:[1,2], lunchMin:0}")
    assert '<div class="sfoot">Takedown 2.6h · Drive 0.3h' in html
    assert "Install" not in html
    assert '<th class="c">Takedown</th>' in html
    assert "<p><b>Takedown</b> · 2 stops" in html
    assert "ON HOLD: confirm before takedown" in html


@needs_node
def test_a_december_crew_sheet_still_prints_install():
    html = manifest("{date:'2026-12-10', stops:[1,2]}")
    assert '<div class="sfoot">Install 2.6h · Drive 0.3h' in html
    assert '<th class="c">Install</th>' in html
    assert "Takedown" not in html
    assert "ON HOLD: confirm before install" in html


@needs_node
def test_an_explicit_install_visit_in_january_prints_install():
    html = manifest("{date:'2027-01-02', stops:[3]}")
    assert '<div class="sfoot">Install 2.6h' in html
    assert "Takedown" not in html


def test_screen_labels_use_the_day_kind():
    # The day card's footer, the stop card's hours and the shift detail.
    assert '<div class="cfsub"><span>${dayKindLabel(d)} ${calc.inst.toFixed(1)}h</span>' in TEMPLATE
    assert "c.h26+'h'} ${stopKindWord(d, r)}`" in TEMPLATE
    assert "<span>${dayKindLabel(d).toLowerCase()}</span>" in TEMPLATE
    assert '<span>Install ${calc.inst' not in TEMPLATE
    assert '<div class="sfoot">Install ' not in TEMPLATE
