"""The board's "done look" (review_template.html): each stop shows planned,
on site, done or times needed from saved Install Times only, the crew card
gets a "Day: ..." line, and the date list marks done days and days missing
times. These run the template's own pure functions in node.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

FNS = ["addDaysISO", "actualMinutes", "fmtSpan", "centralTodayISO", "dayIsPast", "stopTimeState", "planDiff",
       "doneTimesText", "plannedLineText", "stopTimeTag", "dayTimesSummary", "dayTimesText", "dateTimesMark"]
STUBS = """
  const todayISO=()=>'2026-11-17';
  // Fri 11/12 Bergstrom (Crew 1): 10:00 AM to 12:50 PM CST.
  const BERG={arrive:'10:00 AM', depart:'12:50 PM', arriveAt:'2026-11-12T16:00:00+00:00', departAt:'2026-11-12T18:50:00+00:00'};
  const ONSITE={arrive:'8:55 AM', depart:'', arriveAt:'2026-11-17T14:55:00+00:00', departAt:null};
  // A Dallas night: 11:10 PM to 2:25 AM the next morning.
  const NIGHT={arrive:'11:10 PM', depart:'2:25 AM', arriveAt:'2026-11-17T05:10:00+00:00', departAt:'2026-11-17T08:25:00+00:00'};
"""


def run(body):
    src = "\n".join(js_function(n) for n in FNS) + "\n" + STUBS + body
    return json.loads(run_js(src))


def test_functions_exist_and_wired():
    for name in FNS + ["stopTimeInfo", "stopHoursHTML", "dayTimesLineHTML", "dateTimesMarkOf", "dateTimesMarkHTML"]:
        assert f"function {name}(" in TEMPLATE, name
    assert "stopHoursHTML(d, r, [" in TEMPLATE
    assert "${dayTimesLineHTML(d)}" in TEMPLATE
    assert "tmark:dateTimesMarkOf(dt)" in TEMPLATE
    assert "dateTimesMarkHTML(dateTimesMarkOf(iso))" in TEMPLATE


def test_on_screen_text_has_no_em_dash():
    start = TEMPLATE.index("// ---------- planned, on site, done, times needed")
    end = TEMPLATE.index("/** Office staff enter and fix times here", start)
    assert "—" not in TEMPLATE[start:end]


@needs_node
def test_four_states():
    out = run("""
      console.log(JSON.stringify([
        stopTimeState(null, false, false),          // a coming day
        stopTimeState(ONSITE, false, false),        // arrival only, today
        stopTimeState(BERG, true, false),           // both times
        stopTimeState(null, true, false),           // past day, nothing saved
        stopTimeState(null, true, true),            // past training day
        stopTimeState(ONSITE, true, false),         // past, never got a leave
        stopTimeState({arrive:'', depart:''}, true, false),
        stopTimeTag('onsite', ONSITE), stopTimeTag('needed', null), stopTimeTag('needed', ONSITE),
        stopTimeTag('needed', {arrive:'', depart:'1:00 PM'}), stopTimeTag('planned', null), stopTimeTag('done', BERG)]));
    """)
    assert out[:7] == ["planned", "onsite", "done", "needed", "planned", "needed", "needed"]
    assert out[7] == {"cls": "onsite", "text": "On site since 8:55 AM"}
    assert out[8] == {"cls": "need", "text": "Times needed"}
    assert out[9]["text"] == "Leave time needed"
    assert out[10]["text"] == "Arrival time needed"
    assert out[11] is None and out[12] is None


@needs_node
def test_done_text_and_plan_compare():
    out = run("""
      console.log(JSON.stringify([
        doneTimesText(BERG), doneTimesText(ONSITE), doneTimesText(NIGHT),
        plannedLineText(170, 146), plannedLineText(136, 146), plannedLineText(149, 146), plannedLineText(141, 146),
        planDiff(177, 146), planDiff(176, 146), planDiff(100, 146), planDiff(151, 146), planDiff(152, 146),
        planDiff(null, 146)]));
    """)
    assert out[0] == "10:00 AM to 12:50 PM · 2h 50m"
    assert out[1] == ""
    assert out[2] == "11:10 PM to 2:25 AM · 3h 15m"            # across midnight
    assert out[3] == "Planned 2h 26m · 24m over"
    assert out[4] == "Planned 2h 26m · 10m under"
    assert out[5] == "Planned 2h 26m · on time"
    assert out[6] == "Planned 2h 26m · on time"                # 5 min under
    assert out[7]["cls"] == "overbig" and out[7]["text"] == "31m over"
    assert out[8]["cls"] == "over"                             # exactly 30 min over: not amber
    assert out[9] == {"text": "46m under", "cls": "under", "diff": -46}
    assert out[10]["cls"] == "ontime" and out[11]["cls"] == "over"
    assert out[12] is None


@needs_node
def test_past_day_in_central_and_nights():
    out = run("""
      console.log(JSON.stringify([
        dayIsPast('2026-11-16', '2026-11-17', false), dayIsPast('2026-11-17', '2026-11-17', false),
        dayIsPast('2026-11-16', '2026-11-17', true), dayIsPast('2026-11-15', '2026-11-17', true),
        dayIsPast('', '2026-11-17', false),
        // 12:30 AM Eastern on 11/18 is still 11:30 PM on 11/17 in Central.
        centralTodayISO(new Date('2026-11-18T05:30:00Z')), centralTodayISO(new Date('2026-11-18T06:30:00Z'))]));
    """)
    assert out[:5] == [True, False, False, True, False]
    assert out[5:] == ["2026-11-17", "2026-11-18"]


@needs_node
def test_crew_day_summary():
    out = run("""
      const A={arrive:'9:10 AM', depart:'11:40 AM', arriveAt:'2026-11-10T15:10:00Z', departAt:'2026-11-10T17:40:00Z'};
      const B={arrive:'12:05 PM', depart:'4:00 PM', arriveAt:'2026-11-10T18:05:00Z', departAt:'2026-11-10T22:00:00Z'};
      const Cc={arrive:'4:30 PM', depart:'7:46 PM', arriveAt:'2026-11-10T22:30:00Z', departAt:'2026-11-11T01:46:00Z'};
      const full=dayTimesSummary([{a:A, plannedMins:120}, {a:B, plannedMins:180}, {a:Cc, plannedMins:126}]);
      const part=dayTimesSummary([{a:A, plannedMins:120}, {a:{...B, depart:'', departAt:null}, plannedMins:180}, {a:null, plannedMins:126}]);
      const none=dayTimesSummary([{a:null, plannedMins:120}]);
      const night=dayTimesSummary([{a:NIGHT, plannedMins:180},
        {a:{arrive:'2:40 AM', depart:'4:05 AM', arriveAt:'2026-11-17T08:40:00Z', departAt:'2026-11-17T10:05:00Z'}, plannedMins:90}]);
      console.log(JSON.stringify([dayTimesText(full), full.onMins, full.planMins, dayTimesText(part), dayTimesText(none),
        dayTimesText(night)]));
    """)
    full, on, plan, part, none, night = out
    # 2h 30m + 3h 55m + 3h 16m = 9h 41m on site; planned 7h 6m.
    assert full == "Day: 9:10 AM to 7:46 PM · on site 9h 41m (planned 7h 6m)"
    assert (on, plan) == (581, 426)
    # Still on site at the second stop: no end yet, only the done stop counts.
    assert part == "Day: from 9:10 AM · on site 2h 30m (planned 2h)"
    assert none == ""
    # Night shift: starts 11:10 PM, ends 4:05 AM the next morning.
    assert night == "Day: 11:10 PM to 4:05 AM · on site 4h 40m (planned 4h 30m)"


@needs_node
def test_date_marks():
    out = run("""
      console.log(JSON.stringify([dateTimesMark(['done','done']), dateTimesMark(['done','planned']),
        dateTimesMark(['done','needed']), dateTimesMark([]), dateTimesMark(['planned']), dateTimesMark(['onsite','done'])]));
    """)
    assert out == ["done", "", "need", "", "", ""]
