"""The printed crew sheet starts at the shift's real start (review_template.html).

A January Dallas takedown night (Jan 3) printed its timeline from 8:30 AM,
the Houston roll-out, because manifestHTML started its clock at DEPART_MIN.
The day cards, Staffing, the shift detail and the reminders already took the
start from shiftStart(d): 11 PM for any night (d.win===K.NIGHT -- the built
November Mi Cocina nights and the dallasNights added later, like the January
takedowns), 9 AM for the Dallas corporate daytime install, 8:30 AM for a
Houston day. The crew sheet now uses that same source, and the 12-hour clock
rolls past midnight (11:00 PM, 12:15 AM, ...).
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

FNS = ["visitKind", "dayKind", "dayKindLabel", "stopKindWord",
       "shiftStart", "fmtClock", "manifestHTML"]

# Everything around the sheet stubbed: three stops, 75 min each, a 15 min
# drive between them (and from/to the depot), nobody assigned.
STUBS = """
  const TAKEDOWN_CUTOFF='2026-12-25', ARRIVE_MIN=480, DEPART_MIN=510, LUNCH=40;
  const K={NIGHT:450, DAY_CAP:600};
  const C={1:{name:'Stop One', boxes:2}, 2:{name:'Stop Two', boxes:3}, 3:{name:'Stop Three', boxes:1}};
  const N={1:1, 2:2, 3:3}, stopPin={}, PIN_LABEL={}, PREF_LABEL={};
  const hold=new Set();
  const dayCalc=d=>({order:d.stops, inst:3.75, drive:45, total:270});
  const leg=()=>900, effH=()=>1.25;
  const addrParts=()=>({street:'1 Main', city:'Dallas', st:'TX', zip:'75201'});
  const installNoteFor=()=>null, productionNoteFor=()=>null, staffAlertOf=()=>null, prefOf=()=>null;
  const fmtPhone=s=>s, dayBoxes=()=>6;
  const stopBoxes=r=>(C[r]&&C[r].boxes!=null)?C[r].boxes:null;
  const crewTitle=()=>'Crew 1', dowName=()=>'Sun', fmtMDYYYY=s=>s;
  const shiftOfDay=()=>null, dayCoverage=()=>({who:[], state:'ok'}), shiftCoverage=dayCoverage;
  const coverageLabel=()=>'', shiftNoteOf=()=>null;
"""


def run(body):
    src = "\n".join(js_function(n) for n in FNS) + STUBS + body
    return json.loads(run_js(src))


def arrive_times(html):
    """The "Arrive ≈" column, stop by stop."""
    import re
    return re.findall(r'<td class="c">([0-9:]+ [AP]M)</td></tr>', html)


@needs_node
def test_january_takedown_night_starts_at_11_pm_and_rolls_past_midnight():
    # Jan 3: a dallasNights date, so metaFor gives it the night window and
    # anchored:false (no depot legs).
    html = run("console.log(JSON.stringify(manifestHTML("
               "{date:'2027-01-03', stops:[1,2,3], win:450, anchored:false, lunchMin:0})));")
    assert arrive_times(html) == ["11:00 PM", "12:30 AM", "2:00 AM"]
    assert "8:30 AM" not in html
    assert "Depot" not in html
    assert "<b>Takedown</b> · 3 stops" in html


@needs_node
def test_november_dallas_install_night_starts_at_11_pm():
    html = run("console.log(JSON.stringify(manifestHTML("
               "{date:'2026-11-03', stops:[1,2], win:450, anchored:false, lunchMin:0})));")
    assert arrive_times(html) == ["11:00 PM", "12:30 AM"]
    assert "8:30 AM" not in html


@needs_node
def test_dallas_daytime_install_starts_at_9_am():
    html = run("console.log(JSON.stringify(manifestHTML("
               "{date:'2026-11-02', stops:[1], win:480, anchored:false, lunchMin:0})));")
    assert arrive_times(html) == ["9:00 AM"]


@needs_node
def test_houston_day_still_departs_the_depot_at_8_30():
    html = run("console.log(JSON.stringify(manifestHTML("
               "{date:'2026-11-17', stops:[1,2], win:600, anchored:true})));")
    assert "Depot — depart 8:30 AM" in html
    # 8:30 roll-out + 15 min to the first stop; 75 min there + 15 min drive.
    assert arrive_times(html) == ["8:45 AM", "10:15 AM"]
    assert "Return to depot ≈ 11:45 AM" in html


@needs_node
def test_clock_is_12_hour_and_crosses_midnight():
    out = run("console.log(JSON.stringify([1380, 1439.7, 1440, 1455, 1500, 1830, 510, 720]"
              ".map(fmtClock)));")
    assert out == ["11:00 PM", "12:00 AM", "12:00 AM", "12:15 AM", "1:00 AM",
                   "6:30 AM", "8:30 AM", "12:00 PM"]


def test_crew_sheet_takes_its_start_from_shift_start():
    m = js_function("manifestHTML")
    assert "shiftStart(d)" in m
    assert "DEPART_MIN" not in m
