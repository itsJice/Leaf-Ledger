"""Email week schedules on the Install Schedule (review_template.html).

Comments #37, 11/16/2026: "Cynthia requested to be able to email installers
their entire schedule for the week rather than having to email for each
individual install."

Built on the shift reminders: the same shifts, crews, leads and meet times,
one message per installer for the whole Sunday-Saturday week, English or
Spanish. Every Email is a mailto: link (every Text an sms: link) that the
staff member's own Mail or Messages opens filled in; nothing sends from the
page. These run the template's own functions in node. Fake names only.
"""
import json
import re
import shutil
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from test_client_name_editor import TEMPLATE
from test_dallas_nights import fns
from test_shift_reminders import REM, const_block

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

WK = REM + const_block("DOW3") + const_block("WK_TXT") + fns(
    "fmtMDYYYY", "weekOf", "wkDates", "wkDay", "wkPeople", "wkShiftLines", "wkMessage",
    "wkEmail", "wkMailto", "wkDefault",
) + """
// A fake stop list per shift, standing in for wkExtra (which reads the
// board's drive times): two stops a day, the end time given per day id.
const STOPS={}, ENDS={};
const extraOf=info=>({stops:STOPS[info.dayIds[0]]||[], end:ENDS[info.dayIds[0]]??null});
function weekFor(sun){
  const dates=wkDates(sun), by={};
  dates.forEach(iso=>{ by[iso]=remShiftInfos(iso); });
  return wkPeople(dates, by, staffing, roster, extraOf);
}
"""


def run(body):
    from test_client_name_editor import run_js
    return json.loads(run_js(WK + body))


SETUP = """
  days=[day('2026-11-16|Crew 1|0',[5,6]), day('2026-11-18|Crew 2|0',[7]),
        day('2026-11-23|Crew 1|0',[8])];
  crewNames={'2026-11-16|Crew 1|0':'Test Crew'};
  roster=[person('p1','Alex','Lead','Lead','English','(713) 555-0101'),
          person('p2','Bea','Helper','General Installer','Spanish','713-555-0102'),
          person('p3','Cy','Nomail','General Installer','English','')];
  roster[0].email='alex@example.com'; roster[1].email=' bea@example.com ';
  staffing={'2026-11-16|Crew 1|0':['p2','p1'], '2026-11-18|Crew 2|0':['p2','p3'],
            '2026-11-23|Crew 1|0':['p1']};
  STOPS['2026-11-16|Crew 1|0']=[{name:'Fake Bistro', zone:'Heights'}, {name:'Sample Residence', zone:''}];
  STOPS['2026-11-18|Crew 2|0']=[{name:'Pretend Plaza', zone:'Memorial', hold:true}];
  ENDS['2026-11-16|Crew 1|0']=16*60+45; ENDS['2026-11-18|Crew 2|0']=15*60;
"""


def test_one_message_per_person_with_every_day_they_work_that_week():
    out = run(SETUP + """
      const wk=weekFor('2026-11-15');
      console.log(JSON.stringify({ids:wk.map(e=>e.p.id), days:wk.map(e=>e.shifts.map(s=>s.info.date)),
        bea:wkMessage(wk[1], '2026-11-15', 'en'), beaEs:wkMessage(wk[1], '2026-11-15', 'es'),
        alex:wkMessage(wk[0], '2026-11-15', 'en').body}));
    """)
    # Alex's 11/23 shift is next week; Cy only has 11/18.
    assert out["ids"] == ["p1", "p2", "p3"]
    assert out["days"] == [["2026-11-16"], ["2026-11-16", "2026-11-18"], ["2026-11-18"]]
    assert out["bea"]["subject"] == "Your TBDG schedule for the week of 11/15/2026"
    assert out["bea"]["body"] == (
        "Hi Bea!\n\n"
        "This is The Branch Design Group (TBDG). Here is your schedule for the week of 11/15/2026 to 11/21/2026:\n\n"
        "Mon 11/16/2026, install crew\n"
        "Crew: Test Crew (Crew 1) (lead: Alex Lead)\n"
        "Meet: 8:00 AM at the branch (2860 Antoine Dr), we roll out at 8:30 AM\n"
        "Back at the branch about 4:45 PM\n"
        "Stops:\n- Fake Bistro (Heights)\n- Sample Residence\n\n"
        "Wed 11/18/2026, install crew\n"
        "Crew: Crew 1 (lead: to be confirmed)\n"
        "Meet: 8:00 AM at the branch (2860 Antoine Dr), we roll out at 8:30 AM\n"
        "Back at the branch about 3:00 PM\n"
        "Stops:\n- Pretend Plaza (Memorial) [on hold]\n\n"
        "If anything has changed or you can't make a day, please let me know. Thank you!")
    es = out["beaEs"]
    assert es["subject"] == "Tu horario de TBDG para la semana del 11/15/2026"
    assert es["body"].startswith("¡Hola Bea!\n\nTe escribe The Branch Design Group (TBDG).")
    assert "lunes 11/16/2026, equipo de instalación" in es["body"]
    assert "Equipo: Test Crew (Crew 1) (líder: Alex Lead)" in es["body"]
    assert "Regreso a la bodega aprox. 4:45 PM" in es["body"]
    assert "Paradas:" in es["body"] and "[en espera]" in es["body"]
    assert "(lead: you)" in out["alex"]


def test_no_em_dashes_24_hour_times_or_usted():
    out = run(SETUP + """
      const wk=weekFor('2026-11-15');
      console.log(JSON.stringify(wk.flatMap(e=>['en','es'].map(l=>wkMessage(e,'2026-11-15',l).body))));
    """)
    for body in out:
        assert "—" not in body and "–" not in body
        assert not re.search(r"\b(1[3-9]|2[0-3]):\d\d\b", body)
        assert not re.search(r"usted", body, re.I)


def test_dallas_night_reads_start_and_next_morning_finish():
    out = run("""
      days=[day('2026-11-03|Crew 2|0',[8,9])];
      roster=[person('p1','Cam','Night','General Installer','English','7135550103')];
      staffing={'2026-11-03|Crew 2|0':['p1']};
      STOPS['2026-11-03|Crew 2|0']=[{name:'Fake Cantina', zone:'Uptown'}];
      ENDS['2026-11-03|Crew 2|0']=1440+5*60+30;
      const wk=weekFor('2026-11-01');
      console.log(JSON.stringify({en:wkMessage(wk[0],'2026-11-01','en').body, es:wkMessage(wk[0],'2026-11-01','es').body}));
    """)
    assert "Meet: 11:00 PM start (Dallas night shift)" in out["en"]
    assert "Last stop done about 5:30 AM (next morning)" in out["en"]
    assert "Última parada termina aprox. 5:30 AM (a la mañana siguiente)" in out["es"]


def test_mailto_is_one_person_with_subject_and_crlf_body():
    out = run(SETUP + """
      const wk=weekFor('2026-11-15');
      const m=wkMessage(wk[0],'2026-11-15','en');
      console.log(JSON.stringify({href:wkMailto(wkEmail(wk[0].p.email), m), body:m.body,
        emails:[wkEmail(' bea@example.com '), wkEmail(''), wkEmail('nope'), wkEmail('a@b.com, c@d.com')]}));
    """)
    u = urlparse(out["href"])
    assert u.scheme == "mailto" and unquote(u.path) == "alex@example.com"
    q = parse_qs(u.query)
    assert q["subject"] == ["Your TBDG schedule for the week of 11/15/2026"]
    assert q["body"][0] == out["body"].replace("\n", "\r\n")
    # One address, never a list: a pasted "a, b" is not used.
    assert out["emails"] == ["bea@example.com", "", "", ""]


def test_default_week_is_the_next_staffed_week():
    out = run("""
      console.log(JSON.stringify([
        wkDefault(['2026-11-10','2026-11-18'], '2026-11-16'),
        wkDefault(['2026-11-10','2026-11-25'], '2026-11-21'),
        wkDefault([], '2026-11-16'),
        wkDates('2026-11-15'), wkDay('2026-11-16','en'), wkDay('2026-11-16','es')]));
    """)
    assert out[0] == "2026-11-15"
    assert out[1] == "2026-11-22"
    assert out[2] == "2026-11-15"
    assert out[3] == ["2026-11-15", "2026-11-16", "2026-11-17", "2026-11-18",
                      "2026-11-19", "2026-11-20", "2026-11-21"]
    assert out[4:] == ["Mon 11/16/2026", "lunes 11/16/2026"]


def test_nothing_sends_from_the_page():
    block = TEMPLATE[TEMPLATE.index("// ---- Email week schedules (Staffing) ----"):]
    block = block[:block.index("let daysScrollKeep")]
    assert "fetch(" not in block and "apiFetch" not in block
    assert "persist()" not in block           # checkmarks stay in this browser
    assert "mailto:" in block and "sms:" in block
    # The Staffing bar has the entry point, wired to the window.
    assert 'id="wkmailbtn"' in TEMPLATE and "openWeekDlg()" in TEMPLATE
    assert '<dialog id="wkdlg"' in TEMPLATE
