"""Text shift reminders on the Install Schedule (review_template.html).

10/25/2026: "need a way in the scheduling and staffing tab to text remind
install crew of their shifts upcoming likely sent out the night before".

It is the Send mass text window in a reminder mode: the send list is
preloaded with everyone staffed on a date (or one crew), each person's text
is filled in from a template (first name, day/date, crew and lead, meet time
and place), every Send is an sms: link the user presses Send on, and what
went out is logged on the person as {kind:'reminder', for:date}. These run
the template's own functions in node, like test_shift_notes.py. No real
names or numbers.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_dallas_nights import BOARD, fns

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def const_block(name):
    """A top-level `const NAME=...;` that may span lines (ends at `;` + newline)."""
    m = re.search(rf"^const {name}\s*=.*?;\n", TEMPLATE, re.M | re.S)
    assert m, name
    return m.group(0)


REM = BOARD + "\n".join(const_block(n) for n in (
    "TEXT_LOG_MAX", "REMINDER_LOG_MAX", "BRANCH_ADDR", "REM_DEFAULT", "DOW_ES", "TXT_FIELDS",
)) + """
const ARRIVE_MIN = 8*60, DEPART_MIN = 8*60+30;
let staffing = {}, roster = [], crewNames = {};
const crewName = d => crewNames[d.id] || '';
const crewNameKey = d => d.id;
""" + fns(
    "isReminderText", "capTexts", "normTexts", "fmtReminderLog", "smsNumber", "fmtClock",
    "txtFill", "remMD", "remDateLabel", "remDaysAway", "remWhen", "remMeet", "remPeople",
    "remLead", "remVals", "remReason", "remSentFor", "remStatus", "withReminderLog",
    "withoutReminderLog", "remShiftInfos", "remRows", "shiftStart", "jointShiftGroups",
) + """
// The page's buildShifts, cut down to what reminders read: joint pairs
// (the real jointShiftGroups) are one shift; every other crew-day its own.
function buildShifts(){
  const jg=jointShiftGroups(days), map=new Map();
  days.forEach(d=>{
    const k=jg[d.id]||d.id;
    if(!map.has(k)) map.set(k,{key:k, crew:d.crew, dallas:isDallasNight(d), training:!!d.training,
                               joint:!!jg[d.id], days:[]});
    map.get(k).days.push(d);
  });
  return [...map.values()].map(sh=>{
    sh.date=sh.days[0].date; sh.night=sh.days.some(x=>x.win===K.NIGHT);
    sh.members=sh.days.slice(0, sh.joint?sh.days.length:1)
      .map(x=>({key:x.id, pos:crewLabel(x), name:crewName(x)}));
    return sh;
  }).sort((a,b)=>a.date.localeCompare(b.date)||(a.crew<b.crew?-1:1));
}
const person=(id, first, last, title, lang, phone)=>({id, first, last, name:first+' '+last,
  title, lang, phone, texts:[], active:true});
const fill=(row, lang, today)=>txtFill(REM_DEFAULT[lang], row.p, remVals(row, lang, today));
"""


def run(body):
    return json.loads(run_js(REM + body))


def test_houston_day_message_fills_every_field_in_english_and_spanish():
    out = run("""
      days=[day('2026-11-10|Crew 1|0',[5,6,7])];
      crewNames={'2026-11-10|Crew 1|0':'Test Crew'};
      roster=[person('p1','Alex','Lead','Lead','English','(713) 555-0101'),
              person('p2','Bea','Helper','General Installer','Spanish','713-555-0102')];
      staffing={'2026-11-10|Crew 1|0':['p2','p1']};
      const rows=remRows('2026-11-10');
      console.log(JSON.stringify({ids:rows.map(r=>r.p.id),
        en:fill(rows[1],'en','2026-11-09'), es:fill(rows[1],'es','2026-11-09'),
        leadEn:fill(rows[0],'en','2026-11-09'), leadEs:remLead(rows[0],'es')}));
    """)
    assert out["ids"] == ["p1", "p2"]          # the lead first
    assert out["en"] == (
        "Hi Bea! This is The Branch Design Group (TBDG) with a reminder: you are on the install crew"
        " tomorrow, Tue 11/10.\n"
        "Crew: Test Crew (Crew 1) (lead: Alex Lead)\n"
        "Meet: 8:00 AM at the branch (2860 Antoine Dr), we roll out at 8:30 AM\n"
        "If anything has changed, please let me know. Thank you, see you then!")
    assert out["es"] == (
        "¡Hola Bea! Te escribe The Branch Design Group (TBDG) para recordarte que estás en el equipo de"
        " instalación mañana, martes 11/10.\n"
        "Equipo: Test Crew (Crew 1) (líder: Alex Lead)\n"
        "Hora y lugar: 8:00 AM en la bodega (2860 Antoine Dr), salimos a las 8:30 AM\n"
        "Si algo cambió, avísame por favor. ¡Gracias, nos vemos!")
    assert "(lead: you)" in out["leadEn"]
    assert out["leadEs"] == "tú"


def test_message_has_no_stops_notes_em_dashes_or_24_hour_times():
    # User, 10/25: only first name, day/date, crew and lead, meet time and
    # place, and a closing line. No stop names, addresses, counts or notes.
    for lang in ("en", "es"):
        tpl = run(f"console.log(JSON.stringify(REM_DEFAULT.{lang}))")
        assert set(re.findall(r"\{\{(\w+)\}\}", tpl)) == {"first", "when", "crew", "lead", "meet"}
        assert "—" not in tpl and "–" not in tpl
    assert re.search(r"usted", run("console.log(JSON.stringify(REM_DEFAULT.es))"), re.I) is None
    fields = re.search(r"const REM_FIELDS=\[(.*?)\];", TEMPLATE, re.S).group(1)
    assert re.findall(r"key:'(\w+)'", fields) == ["first", "when", "crew", "lead", "meet"]


def test_when_reads_tomorrow_today_or_the_date():
    out = run("""
      console.log(JSON.stringify([
        remWhen('2026-11-10','2026-11-09',false,'en'), remWhen('2026-11-10','2026-11-09',true,'en'),
        remWhen('2026-11-10','2026-11-10',false,'en'), remWhen('2026-11-10','2026-11-10',true,'en'),
        remWhen('2026-11-10','2026-11-05',false,'en'), remWhen('2026-11-10','2026-11-05',true,'en'),
        remWhen('2026-11-10','2026-11-09',true,'es'), remWhen('2026-11-02','2026-10-25',false,'es'),
        remWhen('2026-11-01','2026-10-31',false,'en')]));
    """)
    assert out == ["tomorrow, Tue 11/10", "tomorrow night, Tue 11/10", "today, Tue 11/10",
                   "tonight, Tue 11/10", "on Tue 11/10", "the night of Tue 11/10",
                   "mañana en la noche, martes 11/10", "el lunes 11/02",
                   "tomorrow, Sun 11/01"]          # across the month and the DST change


def test_dallas_night_is_the_11_pm_start_not_the_branch():
    out = run("""
      days=[day('2026-11-03|Crew 2|0',[8,9]), day('2026-12-01|Crew 1|0',[5])];
      roster=[person('p1','Cam','Night','General Installer','English','7135550103')];
      staffing={'2026-11-03|Crew 2|0':['p1']};
      const info=remShiftInfos('2026-11-03')[0];
      const rows=remRows('2026-11-03');
      console.log(JSON.stringify({info, en:fill(rows[0],'en','2026-11-02'), es:fill(rows[0],'es','2026-11-02'),
        nine:remMeet({night:false, anchored:false, start:540}, 'en'),
        day:remShiftInfos('2026-12-01')[0]}));
    """)
    i = out["info"]
    assert (i["night"], i["dallas"], i["anchored"], i["start"], i["arrive"]) == (True, True, False, 1380, None)
    assert "tomorrow night, Tue 11/03" in out["en"]
    assert "Meet: 11:00 PM start (Dallas night shift)" in out["en"]
    assert "lead: to be confirmed" in out["en"]
    assert "branch" not in out["en"]
    assert "Hora y lugar: empezamos a las 11:00 PM (turno de noche en Dallas)" in out["es"]
    assert out["nine"] == "9:00 AM start"
    d = out["day"]
    assert (d["night"], d["anchored"], d["start"], d["arrive"]) == (False, True, 510, 480)


def test_joint_pair_is_one_text_and_two_crews_the_same_day_is_flagged():
    out = run("""
      days=[day('2026-11-10|Crew 1|0',[5,6]), day('2026-11-10|Crew 2|0',[5,6]),
            day('2026-11-10|Crew 3|0',[7])];
      roster=[person('a','Ann','One','Lead','English','7135550111'),
              person('b','Ben','Two','Lead','Both','7135550112'),
              person('c','Cy','Three','General Installer','English','7135550113')];
      // a joint pair: the same people written to both crew-days
      staffing={'2026-11-10|Crew 1|0':['a','b','c'], '2026-11-10|Crew 2|0':['a','b','c'],
                '2026-11-10|Crew 3|0':['c']};
      const infos=remShiftInfos('2026-11-10'), rows=remRows('2026-11-10');
      console.log(JSON.stringify({crews:infos.map(i=>i.crew),
        rows:rows.map(r=>[r.p.id, r.info.crew, r.also]),
        leadA:remLead(rows.find(r=>r.p.id==='a'),'en'), leadC:remLead(rows.find(r=>r.p.id==='c'),'es'),
        crewOnly:remRows('2026-11-10',[infos[1].key]).map(r=>r.p.id)}));
    """)
    assert out["crews"] == ["Crew 1 + Crew 2", "Crew 3"]
    # one row per person; Cy is on the pair AND Crew 3, so one text and a flag
    assert out["rows"] == [["a", "Crew 1 + Crew 2", []], ["b", "Crew 1 + Crew 2", []],
                           ["c", "Crew 1 + Crew 2", ["Crew 3"]]]
    assert out["leadA"] == "you and Ben Two"
    assert out["leadC"] == "Ann One y Ben Two"
    assert out["crewOnly"] == ["c"]             # Text this crew: only that crew


def test_people_without_a_textable_phone_are_blocked_with_the_reason():
    out = run("""
      console.log(JSON.stringify([
        remReason({phone:'(713) 555-0101'}), remReason({phone:''}), remReason({}),
        remReason({phone:'555-0101'}), remReason({phone:'713 555 0101 ext 4'})]));
    """)
    assert out[0] == "" and out[1] == out[2] == "No phone number on file"
    assert out[3] == "Phone number can't take a text (555-0101)"
    assert out[4].startswith("Phone number can't take a text")


def test_tracking_logs_one_reminder_per_date_and_keeps_the_mass_texts():
    out = run("""
      const p=person('p1','Dee','Four','General Installer','English','7135550104');
      p.texts=[1,2,3,4,5].map(i=>({at:`2026-10-0${i}T12:00:00.000Z`, lang:'en', body:'mass '+i}));
      p.texts=withReminderLog(p.texts, {at:'2026-11-10T01:42:00.000Z', lang:'en', body:'r1', kind:'reminder', for:'2026-11-10'});
      p.texts=withReminderLog(p.texts, {at:'2026-11-10T01:50:00.000Z', lang:'es', body:'r2', kind:'reminder', for:'2026-11-10'});
      const once=p.texts.filter(isReminderText).length;
      for(let i=11;i<=25;i++) p.texts=withReminderLog(p.texts, {at:`2026-11-${i}T01:00:00.000Z`, lang:'en', body:'r', kind:'reminder', for:`2026-11-${i+1}`});
      const kept=normTexts(JSON.parse(JSON.stringify(p.texts)));
      const rows=[{p}, {p:person('p2','Eve','Five','General Installer','English','7135550105')},
                  {p:person('p3','Fay','Six','General Installer','English','')}];
      rows[1].p.texts=withReminderLog([], {at:'2026-11-09T23:00:00.000Z', lang:'en', body:'x', kind:'reminder', for:'2026-11-10'});
      const status=remStatus(rows, '2026-11-26');
      const status10=remStatus(rows, '2026-11-10');
      console.log(JSON.stringify({once, mass:kept.filter(t=>!isReminderText(t)).length,
        rem:kept.filter(isReminderText).length, newest:kept[0].for,
        junk:normTexts([{at:'x', body:'y', kind:'reminder', for:'nope'}])[0],
        status, status10, gone:withoutReminderLog(rows[1].p.texts,'2026-11-10').length,
        sent:!!remSentFor(rows[1].p,'2026-11-10'), notSent:remSentFor(rows[1].p,'2026-11-11')}));
    """)
    assert out["once"] == 1                     # sending again replaces, never stacks
    assert out["mass"] == 5 and out["rem"] == 10   # reminders never push the mass texts out
    assert out["newest"] == "2026-11-26"
    assert out["junk"] == {"at": "x", "lang": "en", "body": "y"}   # a bad tag is dropped, the text kept
    assert out["status"] == {"total": 2, "sent": 1}       # Fay has no phone: not counted
    assert out["status10"] == {"total": 2, "sent": 1}
    assert out["gone"] == 0 and out["sent"] is True and out["notSent"] is None


def test_the_log_line_reads_reminder_date_sent_date_and_12_hour_time():
    out = run("""
      const at=new Date(2026,10,9,19,42).toISOString();
      const am=new Date(2026,10,9,9,5).toISOString();
      console.log(JSON.stringify([fmtReminderLog({at, for:'2026-11-10'}), fmtReminderLog({at:am, for:'2026-11-10'})]));
    """)
    assert out == ["Reminder 11/10 sent 11/09 7:42 PM", "Reminder 11/10 sent 11/09 9:05 AM"]


def test_sends_are_sms_links_and_nothing_is_automated():
    # The user never gives Claude (or the page) access to Messages: every
    # send is an sms: link he presses Send on.
    src = js_function("remSendHTML") + js_function("remWireSend")
    assert "`sms:${num}&body=${encodeURIComponent(body)}`" in src
    for bad in ("osascript", "AppleScript", "window.open(", "location.href", ".click()"):
        assert bad not in src
    # read-only users can't send: no buttons, no log, and the dialog won't open
    assert "if(READONLY) return;" in js_function("remLog")
    assert "if(READONLY) return;" in js_function("remUnlog")
    assert "roBlocked()" in js_function("openReminderDlg")
    assert "!READONLY" in js_function("remHeadHTML")


def test_entry_points_are_wired():
    assert "shiftDayRowHTML(dt, remHeadHTML(dt, null, shifts))" in js_function("shiftsHTML")   # Staffing day heading
    assert "nextReminderDate()" in js_function("renderStaffing")        # Text tomorrow's crews
    assert "Text tomorrow's crews" in js_function("renderStaffing")
    assert "remcardbtn" in js_function("buildDayCard")                  # Days view crew card
    assert "remHeadHTML(selDate)" in TEMPLATE                           # Days view selected date
    assert "Text this crew" in js_function("sdDraw")                    # shift detail panel
    assert "openReminderDlg(sh.date, [sh.key])" in js_function("drawStaffDlg")   # Edit crew
    assert 'id="stfremind"' in TEMPLATE
