"""The shift detail panel and the Open day jump (review_template.html).

10/24/2026: "I want to be able to double click on this crew, on this staffing
shift, and it open up in detail what I can see on the install schedule ...
a place to make notes, a place to understand how the drive times in between
each place is ... click into the client pages staying in this window." And:
"a button ... on the staffing page, to click on the crew and it takes me to
the scheduling day."

timelineRows() is pure and runs in node; the rest checks the wiring reuses
the Days view's own functions instead of a copy. No real names.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def rows(t):
    return json.loads(run_js(js_function("timelineRows") + f"\nconsole.log(JSON.stringify(timelineRows({json.dumps(t)})));"))


def test_houston_day_rolls_out_drives_between_stops_and_comes_back():
    out = rows({"anchored": True, "night": False, "arrive": 480, "start": 510, "finish": 1069, "lunchMin": 40,
                "stops": [{"row": 1, "name": "Stop A", "start": 546, "end": 692},
                          {"row": 2, "name": "Stop B", "start": 734, "end": 977}],
                "legs": [{"min": 36.2, "mi": 26.1}, {"min": 41.6, "mi": 27.3}, {"min": 52, "mi": None}]})
    assert [r["kind"] for r in out] == ["mark", "mark", "drive", "stop", "drive", "stop", "lunch", "drive", "mark"]
    assert out[0] == {"kind": "mark", "label": "Arrive at the branch", "t": 480}
    assert out[1]["label"] == "Roll out from the branch"
    assert out[2] == {"kind": "drive", "min": 36, "mi": 26.1, "to": "Stop A"}
    assert out[3]["n"] == 1 and out[3]["hours"] == pytest.approx(146 / 60)
    assert out[4] == {"kind": "drive", "min": 42, "mi": 27.3, "to": "Stop B"}
    assert out[7] == {"kind": "drive", "min": 52, "mi": None, "to": "the branch"}
    # back at the branch is the Days view's Est. Finish (lunch included)
    assert out[8] == {"kind": "mark", "label": "Back at the branch", "t": 1069}


def test_dallas_night_has_no_branch_legs_and_ends_at_the_last_stop():
    out = rows({"anchored": False, "night": True, "arrive": None, "start": 1380, "finish": 1663, "lunchMin": 0,
                "stops": [{"row": 7, "name": "Night A", "start": 1380, "end": 1487},
                          {"row": 8, "name": "Night B", "start": 1501, "end": 1663}],
                "legs": [{"min": 14.6, "mi": 7.1}]})
    assert [r["kind"] for r in out] == ["mark", "stop", "drive", "stop", "mark"]
    assert out[0]["label"] == "Night shift starts" and out[0]["t"] == 1380
    assert out[2]["to"] == "Night B" and out[2]["min"] == 15
    assert out[-1] == {"kind": "mark", "label": "Last stop done", "t": 1663}


def test_a_day_with_no_stops_is_just_its_start():
    assert rows({"anchored": True, "arrive": 480, "start": 510, "finish": 510, "stops": [], "legs": []}) == [
        {"kind": "mark", "label": "Arrive at the branch", "t": 480},
        {"kind": "mark", "label": "Roll out from the branch", "t": 510}]


def test_timeline_reads_the_days_view_numbers():
    src = js_function("dayTimeline")
    for fn in ("dayCalc(d)", "stopTimes(d)", "routeGeom(d)", "shiftStart(d)", "leg("):
        assert fn in src
    # the map and the Staffing date maps draw a day the same way
    assert "addDayRouteLayers(" in js_function("shiftMapDraw")
    assert "addDayRouteLayers(" in js_function("sdDrawMap")
    # crew chips and the note field are shared with the card / Staff this shift
    assert "shiftCrewHTML(cv)" in js_function("shiftCardHTML")
    draw = js_function("sdDraw")
    assert "shiftCrewHTML(cv)" in draw and "shiftNoteFieldHTML(sh, 'sd')" in draw
    assert "openStaffDlg(sh.key)" in draw and "READONLY" in draw


def test_clients_open_inside_the_panel_with_back():
    peek = js_function("openStopPeek")
    assert "sdPeekHost()" in peek and "sdShowClient(row)" in peek
    assert "sdBackToDay()" in js_function("afterPeekClose")
    # a render() while a client is open in the panel leaves it open
    assert "!pk.closest('#sddlg')" in js_function("render")
    assert "sdRefresh()" in js_function("render")
    # the full client profile still opens in a new tab, never in this window
    assert "'_blank'" in js_function("openClientsTab")


def test_double_tap_opens_the_panel_but_not_from_the_name_note_or_buttons():
    out = json.loads(run_js("""
      const el=sel=>({closest:q=>q.split(',').map(x=>x.trim()).includes(sel) ? {} : null});
    """ + js_function("cardTapIgnored") + """
      console.log(JSON.stringify(['button','.crewnm','.shnote','textarea','div'].map(s=>cardTapIgnored(el(s)))));
    """))
    assert out == [True, True, True, True, False]
    assert "isDoubleTap(cardTap" in TEMPLATE and "openShiftDetail(key)" in TEMPLATE


def test_open_day_jumps_to_that_crew_on_the_days_view():
    src = js_function("openDayInSchedule")
    assert "selDate=d.date" in src and "focusDayId=d.id" in src and "setView('days')" in src
    assert "data-openday" in js_function("shiftCardHTML")
    assert "openDayInSchedule(" in js_function("sdDraw")
    assert 'role="button"' in TEMPLATE[TEMPLATE.index('class="stfshift" data-goday'):][:120]
    for fn in ("timelineRows", "sdTimelineHTML", "sdDraw", "shiftCardHTML"):
        assert "—" not in js_function(fn)
