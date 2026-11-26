"""Recorded on-site times on the Install Schedule (review_template.html).

Install Times (ll_app.install_actuals) is the one source of truth for when a
crew was at a stop. The board reads GET /api/install-times/schedule and saves
through POST /api/install-times/actuals; a time is never written into the
board's own state (state.comments / PUT /state). These run the template's own
functions in node with small stubs.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

FNS = ["peekEsc", "attrEsc", "actualsMap", "actualFor", "dayHasHappened", "actualMinutes", "fmtSpan",
       "onSiteText", "doneTimesText", "canEditActuals", "timesShown", "timesToday", "centralTodayISO",
       "timesByText", "crewSizeText", "timesStaffCount", "peekTimesHTML"]
STUBS = """
  const IC={clock:'@', alert:'!'};
  let AUTH='t', READONLY=false, VIEWONLY=false, TVMODE=false, ME_ROLE='staff';
  const ALERT_EDIT_ROLES=new Set(['staff','admin','super_admin']);
  let ACTUALS=null, actualsToday='2026-11-16', actualsReady=true, pkTimesEdit=false, pkTimesMsg='';
  const todayISO=()=>'2026-11-16';
  let pkShortDraft=null;
  const staffing={'2026-11-04|Crew 2|0':['p1','p4'], '2026-11-04|Crew 3|0':['p1','p4','p5'], '2026-11-09|Crew 2|0':['p1','p2','p3','p4','p5']};
  const shiftOfDay=d=>d.id.startsWith('2026-11-04|') ? {days:[{id:'2026-11-04|Crew 2|0'},{id:'2026-11-04|Crew 3|0'}]} : null;
  const isDallasNight=d=>d.night===true;
  const SERENITY={id:4, row:105, dayId:'2026-11-09|Crew 2|0', dayIds:['2026-11-09|Crew 2|0'],
    arrive:'3:44 PM', depart:'6:27 PM', arriveAt:'2026-11-09T21:44:00+00:00', departAt:'2026-11-10T00:27:00+00:00',
    actualHours:2.72, source:'claude', enteredBy:'c@x'};
  const JOINT={id:9, row:69, dayId:'2026-11-04|Crew 2|0', dayIds:['2026-11-04|Crew 2|0','2026-11-04|Crew 3|0'],
    arrive:'11:00 PM', depart:'', arriveAt:'2026-11-05T05:00:00+00:00', departAt:null, actualHours:null};
"""


def run(body):
    src = "\n".join(js_function(n) for n in FNS) + "\n" + STUBS + body
    return json.loads(run_js(src))


@needs_node
def test_serenity_reads_like_the_stop_note():
    out = run("""
      ACTUALS=actualsMap([SERENITY, JOINT, null, {row:null}]);
      const past={id:'2026-11-09|Crew 2|0', date:'2026-11-09'};
      console.log(JSON.stringify([onSiteText(actualFor(105, past.id)), doneTimesText(actualFor(105, past.id)),
        onSiteText(actualFor(69, '2026-11-04|Crew 3|0')), actualFor(69, '2026-11-04|Crew 1|0'), ACTUALS.size]));
    """)
    text, sub, joint, other, size = out
    assert text == "On site 3:44 PM to 6:27 PM (2h 43m)"
    assert sub == "3:44 PM to 6:27 PM · 2h 43m"
    # A joint shift's visit shows on both crew-days, never on another crew's.
    assert joint == "Arrived 11:00 PM, no leave time yet"
    assert other is None and size == 3


@needs_node
def test_future_days_show_nothing_and_only_office_can_edit():
    out = run("""
      ACTUALS=actualsMap([SERENITY]);
      const past={id:'2026-11-09|Crew 2|0', date:'2026-11-09'};
      const future={id:'2026-11-20|Crew 1|0', date:'2026-11-20'};
      const staff=peekTimesHTML(105, past);
      const fut=peekTimesHTML(105, future);
      ME_ROLE='lead'; const lead=peekTimesHTML(105, past);
      ME_ROLE='staff'; READONLY=true; const archived=peekTimesHTML(105, past);
      READONLY=false; ACTUALS=null; const loading=peekTimesHTML(105, past);
      ACTUALS=new Map(); const none=peekTimesHTML(105, past);
      console.log(JSON.stringify([staff, fut, lead, archived, loading, none, fmtSpan(45), fmtSpan(180)]));
    """)
    staff, fut, lead, archived, loading, none, m45, h3 = out
    assert "On site 3:44 PM to 6:27 PM (2h 43m)" in staff and 'id="pktimesedit"' in staff and "Fix times" in staff
    assert "Install Times · entered by Claude" in staff and "from the stop note" not in staff
    assert fut == "" and loading == ""
    assert "pktimesedit" not in lead and "pktimesedit" not in archived
    assert "No times entered yet" in none and "Enter times" in none
    assert (m45, h3) == ("45m", "3h")


@needs_node
def test_edit_form_has_16px_inputs_and_night_hint():
    out = run("""
      ACTUALS=actualsMap([JOINT]); pkTimesEdit=true;
      console.log(JSON.stringify([peekTimesHTML(69, {id:'2026-11-04|Crew 3|0', date:'2026-11-04', night:true})]));
    """)[0]
    assert 'id="pkarrive"' in out and 'value="11:00 PM"' in out and 'id="pkdepart"' in out
    assert "Night shift" in out and 'placeholder="1:30"' in out
    assert "—" not in out


def test_times_never_go_into_board_state():
    """The save goes to Install Times only: the block never touches comments,
    persist() or the /state endpoint."""
    src = TEMPLATE
    start = src.index("// ---------- recorded on-site times (Install Times) ----------")
    end = src.index("// dayId === null means the client is on the roster", start)
    block = src[start:end]
    assert "/api/install-times/actuals" in block and "/api/install-times/schedule" in block
    assert "supersedesId:cur?cur.id:null" in block
    for banned in ("comments[", "persist(", "/api/install-schedule/state", "pushUndo("):
        assert banned not in block, banned
    assert "—" not in block
    assert "syncQueued(openPendingStop);" in src


# ─── crew size: people, ladders, full or short (migrations/031) ──────────────


@needs_node
def test_crew_size_reads_in_plain_words_on_the_card():
    out = run("""
      const saved={...SERENITY, peopleCount:4, ladders:2, shortCrew:true};
      ACTUALS=actualsMap([saved]);
      const past={id:'2026-11-09|Crew 2|0', date:'2026-11-09'};
      console.log(JSON.stringify([peekTimesHTML(105, past), crewSizeText({peopleCount:1, ladders:1, shortCrew:false}),
        crewSizeText({peopleCount:6}), crewSizeText(null)]));
    """)
    card, one, six, none = out
    assert "4 people · 2 ladders · " in card and '<span class="short">Short crew</span>' in card
    assert one == "1 person · 1 ladder · Full crew"
    assert six == "6 people" and none == ""


@needs_node
def test_edit_form_prefills_people_from_staffing_until_saved():
    out = run("""
      pkTimesEdit=true;
      ACTUALS=actualsMap([JOINT]);
      const joint=peekTimesHTML(69, {id:'2026-11-04|Crew 3|0', date:'2026-11-04', night:true});
      ACTUALS=actualsMap([{...SERENITY, peopleCount:3, ladders:1}]); pkShortDraft=true;
      const saved=peekTimesHTML(105, {id:'2026-11-09|Crew 2|0', date:'2026-11-09'});
      console.log(JSON.stringify([joint, saved, timesStaffCount({id:'2026-11-20|Crew 9|0'})]));
    """)
    joint, saved, nobody = out
    # A joint shift counts everyone staffed on either crew-day, once.
    assert re.search(r'id="pkpeople"[^>]*value="3"', joint)
    assert "People starts at the crew-day's staffing." in joint
    assert re.search(r'id="pkpeople"[^>]*value="3"', saved) and re.search(r'id="pkladders"[^>]*value="1"', saved)
    assert 'data-short="1" aria-pressed="true"' in saved and 'data-short="0" aria-pressed="false"' in saved
    assert "starts at the crew-day" not in saved
    assert nobody is None
    for html in (joint, saved):
        assert "—" not in html


def test_board_save_sends_people_ladders_and_short_crew():
    src = TEMPLATE
    start = src.index("// ---------- recorded on-site times (Install Times) ----------")
    end = src.index("// dayId === null means the client is on the roster", start)
    block = src[start:end]
    assert "peopleCount:countOf(pi, 40), ladders:countOf(li, 20), shortCrew:pkShortDraft" in block
