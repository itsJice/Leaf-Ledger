"""Shift reminders say "takedown crew" in January (review_template.html).

The user (2026-10-27): "make the reminder text say takedown crew in
January". The reminder's {{job}} fill-in is the shift's dayKind (the same
rule as the day cards and the printed crew sheet, PR #131): after Christmas
it is a takedown unless every stop is explicitly Install/Reinstall. A
template saved in a browser before {{job}} existed still has "install crew"
typed in, and on a takedown day that reads as the takedown wording. These
run the template's own functions in node. No real names or numbers.
"""
import json
import shutil

import pytest

from test_shift_reminders import REM, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def run(body):
    return json.loads(run_js(REM + body))


SETUP = """
  days=[day('2027-01-02|Crew 1|0',[5,6]), day('2026-12-01|Crew 1|0',[7])];
  crewNames={'2027-01-02|Crew 1|0':'Test Crew', '2026-12-01|Crew 1|0':'Test Crew'};
  roster=[person('p1','Alex','Lead','Lead','English','7135550101'),
          person('p2','Bea','Helper','General Installer','Spanish','7135550102')];
  staffing={'2027-01-02|Crew 1|0':['p1','p2'], '2026-12-01|Crew 1|0':['p1','p2']};
"""


def test_a_january_reminder_says_takedown_crew_in_english_and_spanish():
    out = run(SETUP + """
      const r=remRows('2027-01-02')[1];
      console.log(JSON.stringify({kind:r.info.kind, en:fill(r,'en','2027-01-01'), es:fill(r,'es','2027-01-01')}));
    """)
    assert out["kind"] == "takedown"
    assert out["en"].startswith(
        "Hi Bea! This is The Branch Design Group (TBDG) with a reminder: you are on the takedown crew"
        " tomorrow, Sat 01/02.\n")
    assert out["es"].startswith(
        "¡Hola Bea! Te escribe The Branch Design Group (TBDG) para recordarte que estás en el equipo de"
        " desmontaje mañana, sábado 01/02.\n")
    assert "install" not in out["en"].lower() and "instalación" not in out["es"]


def test_a_december_reminder_still_says_install_crew():
    out = run(SETUP + """
      const r=remRows('2026-12-01')[1];
      console.log(JSON.stringify({kind:r.info.kind, en:fill(r,'en','2026-11-30'), es:fill(r,'es','2026-11-30')}));
    """)
    assert out["kind"] == "install"
    assert "you are on the install crew tomorrow, Tue 12/01." in out["en"]
    assert "estás en el equipo de instalación mañana, martes 12/01." in out["es"]
    assert "takedown" not in out["en"].lower() and "desmontaje" not in out["es"]


def test_an_all_install_day_in_january_stays_install():
    out = run(SETUP + """
      C={5:{visitType:'Install'}, 6:{visitType:'Reinstall'}};
      const r=remRows('2027-01-02')[0];
      console.log(JSON.stringify([r.info.kind, fill(r,'en','2027-01-01')]));
    """)
    assert out[0] == "install"
    assert "you are on the install crew tomorrow" in out[1]


def test_an_old_saved_template_with_install_crew_reads_takedown_in_january():
    # Saved in this browser before {{job}}: the install words are typed in.
    out = run(SETUP + """
      const oldEn='Hey {{first}}, you are on the Install crew {{when}}. Install crew lead: {{lead}}.';
      const oldEs='Hola {{first}}, estás en el equipo de instalación {{when}}.';
      const jan=remRows('2027-01-02')[1], dec=remRows('2026-12-01')[1];
      console.log(JSON.stringify({
        janEn:remBody(oldEn, jan, 'en', '2027-01-01'), janEs:remBody(oldEs, jan, 'es', '2027-01-01'),
        decEn:remBody(oldEn, dec, 'en', '2026-11-30'), decEs:remBody(oldEs, dec, 'es', '2026-11-30')}));
    """)
    assert out["janEn"] == ("Hey Bea, you are on the Takedown crew tomorrow, Sat 01/02."
                            " Takedown crew lead: Alex Lead.")
    assert out["janEs"] == "Hola Bea, estás en el equipo de desmontaje mañana, sábado 01/02."
    assert out["decEn"] == "Hey Bea, you are on the Install crew tomorrow, Tue 12/01. Install crew lead: Alex Lead."
    assert out["decEs"] == "Hola Bea, estás en el equipo de instalación mañana, martes 12/01."


def test_job_fill_in_words():
    out = run("""console.log(JSON.stringify([remJob('install','en'), remJob('takedown','en'),
      remJob('install','es'), remJob('takedown','es'), remTplFor('the installation crew', 'takedown')]));""")
    assert out == ["install crew", "takedown crew", "equipo de instalación", "equipo de desmontaje",
                   "the takedown crew"]
