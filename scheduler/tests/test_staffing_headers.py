"""Staffing groups its shifts like the Days date list (review_template.html).

10/24/2026, the user, showing the Days date list beside Staffing: "this visual
theme and headers needs to be consistent through the staffing ui".

Both views now group dates with one helper, monthWeeks(): month headings,
then Sunday-start "Week N" bars (split at a month boundary and at the install
cutoff), then the days, with the hard Takedown line before the first
takedown week. These run the template's own functions in node. No real names.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

CUTOFF = "2026-12-25"
HELPERS = "\n".join(js_function(n) for n in ("dateOf", "weekOf", "weekOfMonth", "monthWeeks"))


def weeks(dates, cutoff=CUTOFF):
    return json.loads(run_js(HELPERS + f"\nconsole.log(JSON.stringify(monthWeeks({json.dumps(dates)}, '{cutoff}')));"))


def test_weeks_run_sunday_to_saturday_and_are_numbered_by_calendar_row():
    # Nov 1 2026 is a Sunday: Nov 1-7 is Week 1, Nov 8-14 is Week 2.
    out = weeks(["2026-11-02", "2026-11-05", "2026-11-07", "2026-11-08", "2026-11-10"])
    assert [(w["num"], w["dates"]) for w in out] == [
        (1, ["2026-11-02", "2026-11-05", "2026-11-07"]),
        (2, ["2026-11-08", "2026-11-10"]),
    ]
    assert [w["newMonth"] for w in out] == [True, False]
    assert not any(w["takedownStart"] for w in out)


def test_october_numbers_count_the_partial_first_row():
    # Oct 1 2026 is a Thursday, so Fri Oct 23 sits on row 4 and Mon Oct 26 on row 5.
    out = weeks(["2026-10-23", "2026-10-26"])
    assert [(w["mo"], w["num"]) for w in out] == [("2026-10", 4), ("2026-10", 5)]


def test_a_week_that_crosses_into_the_next_month_is_split():
    # Sun Nov 29 - Sat Dec 5 is one calendar week; each month gets its own part.
    out = weeks(["2026-11-30", "2026-12-01", "2026-12-03"])
    assert [(w["mo"], w["num"], w["dates"], w["newMonth"]) for w in out] == [
        ("2026-11", 5, ["2026-11-30"], True),
        ("2026-12", 1, ["2026-12-01", "2026-12-03"], True),
    ]


def test_takedown_line_goes_before_the_first_week_after_the_cutoff_only():
    # Dec 20-26 is one week; the cutoff splits it, and the line marks Dec 26.
    out = weeks(["2026-12-22", "2026-12-24", "2026-12-26", "2027-01-02", "2027-01-04"])
    assert [(w["dates"], w["takedownStart"], w["newMonth"]) for w in out] == [
        (["2026-12-22", "2026-12-24"], False, True),
        (["2026-12-26"], True, False),
        (["2027-01-02"], False, True),     # Dec 27 - Jan 2, January's part
        (["2027-01-04"], False, False),
    ]


def test_takedown_line_when_the_first_takedown_date_is_in_january():
    # Staffing lists only dates with shifts: Dec 23 then the Jan 2 Dallas week.
    out = weeks(["2026-12-23", "2027-01-02", "2027-01-03"])
    assert [(w["dates"], w["takedownStart"], w["newMonth"]) for w in out] == [
        (["2026-12-23"], False, True),
        (["2027-01-02"], True, True),
        (["2027-01-03"], False, False),
    ]


def test_no_takedown_line_when_only_takedown_dates_are_listed():
    out = weeks(["2027-01-02", "2027-01-09"])
    assert not any(w["takedownStart"] for w in out)


def test_input_order_and_repeats_do_not_matter():
    assert weeks(["2026-11-10", "2026-11-02", "2026-11-10", "2026-11-02"]) == \
        weeks(["2026-11-02", "2026-11-10"])


def test_staffing_day_row_reads_like_the_date_list():
    src = """
      const SPEC={calendar:[{date:'2026-11-02',dow:'Mon'},{date:'2026-11-07',dow:'Sat',label:'Event - big one'}]};
      const days=[{date:'2026-11-02',stops:[1,2,3]},{date:'2026-11-02',stops:[4]}];
      const MON3=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    """ + "\n".join(js_function(n) for n in ("dowOf", "listDate", "esc", "shiftDayRowHTML")) + """
      console.log(JSON.stringify([shiftDayRowHTML('2026-11-02'), shiftDayRowHTML('2026-11-07')]));
    """
    mon, sat = json.loads(run_js(src))
    assert 'class="dchip stfday"' in mon and ">Mon, Nov 2<" in mon
    assert '<span class="dcount" title="4 stops · 2 crews">4</span>' in mon
    assert 'class="dchip stfday wknd tagged"' in sat and ">Sat, Nov 7<" in sat
    assert '<span class="dtag" title="Event - big one">Event</span>' in sat


def test_both_views_use_the_same_grouping_and_header_builders():
    strip, staff = js_function("renderStrip"), js_function("shiftsHTML")
    for fn in (strip, staff):
        assert "monthWeeks(" in fn and "TAKEDOWN_CUTOFF" in fn
    assert "foldMonths(strip, STRIP_SHUT_KEY)" in strip
    for builder in ("dateMonthHead(", "dateWeekBar(", "takedownLine("):
        assert builder in staff
    assert "foldMonths(grp, STAFF_SHUT_KEY" in js_function("renderStaffing")
    # Folding Staffing doesn't fold the Days list (and the reverse).
    assert "const STAFF_SHUT_KEY='tbdg-staff-shut';" in TEMPLATE
    assert "const STRIP_SHUT_KEY='tbdg-strip-shut';" in TEMPLATE
    # The old Georgia date headings are gone from the shift list.
    assert 'class="shiftdate"' not in staff


def test_phone_staffing_keeps_the_headers_the_date_sheet_shows():
    # Under 768px the date strip hides .dsec/.dmon; Staffing shares the date
    # sheet's rules to show them as a vertical list.
    assert "body.apple.datesheet .dsec,body.apple .stfgroups .dsec{display:flex}" in TEMPLATE
    assert "body.apple.datesheet .dmon,body.apple .stfgroups .dmon{display:flex}" in TEMPLATE
    assert "body.apple .stfgroups .dgrp.shut{display:none}" in TEMPLATE


def test_a_folded_month_does_not_mount_its_maps():
    assert "if(el.closest('.dgrp.shut')) return;" in js_function("shiftMapInit")
