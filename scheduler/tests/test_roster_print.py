"""Print roster dialog (user, 2026-10-22: "I need options on the print roster
button ... choose what information I want to print ... make a check-in sheet
for training ... I want verticle orientation"). The pure helpers that pick
the people, columns and layout. FAKE people only."""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

HELPERS = ["rosterPrintColumns", "rosterPrintPreset", "normRosterPrintOpts", "rosterPrintKey",
           "rosterPrintSort", "rosterPrintPeople", "rosterPrintCell", "rosterPrintLayout",
           "rosterPrintDateLine", "rosterPrintBody", "rosterPrintCSS", "fmtFreeDays", "esc"]

PRELUDE = """
const TITLES=['Lead','Lead Assist','Designer','General Installer'];
const LANGS=['English','Spanish','Both'];
const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
function fmtPhone(p){ return '('+p.slice(0,3)+') '+p.slice(3,6)+'-'+p.slice(6); }
function fmtTextDay(iso){ return 'Oct 5'; }
const PEOPLE=[
  {id:'p1', first:'Érica', last:'Zeta', name:'Érica Zeta', title:'General Installer', lang:'Spanish',
   gender:'Female', phone:'7135550101', dates:['2026-10-26'], active:true, legalName:'Erica Q Zeta',
   street:'1 Main St', city:'Houston', state:'TX', zip:'77002'},
  {id:'p2', first:'Erin', last:'Adams', name:'Erin Adams', title:'Lead', lang:'English',
   gender:'Female', phone:'', dates:[], active:true},
  {id:'p3', first:'Arely', last:'', name:'Arely', title:'Designer', lang:'Both',
   gender:'Female', phone:'7135550102', dates:['2026-10-26','2026-11-02'], active:true,
   texts:[{at:'2026-10-05T15:00:00Z', body:'hi'}]},
  {id:'p4', first:'Bob', last:'Moe', name:'Bob Moe', title:'Lead Assist', lang:'English',
   gender:'Male', phone:'7135550103', dates:['2026-10-26'], active:false},
];
"""


def js(body):
    src = PRELUDE + "\n".join(js_function(h) for h in HELPERS) + "\n" + body
    return json.loads(run_js(src))


def test_training_preset_is_the_check_in_sheet():
    o = js("console.log(JSON.stringify(normRosterPrintOpts(rosterPrintPreset('training'), false, '10/23/2026')))")
    assert o["cols"] == ["name", "phone", "w9", "dd", "availrec", "checkin"]   # no Signature
    assert o["sort"] == "first" and o["orient"] == "portrait"
    assert o["nums"] is True and o["fill"] is True and o["walkins"] == 10
    assert o["title"] == "Installer Training Check-in" and o["date"] == "10/23/2026"
    assert o["who"] == "active" and o["inactive"] is False


def test_layout_order_checked_in_last_and_custom_before_it():
    cols = js("""const o=normRosterPrintOpts({cols:['checkin','phone','w9','sign'], custom:['Shirt size',' Shirt  size ','']}, false, '');
      console.log(JSON.stringify(rosterPrintLayout(o).map(c=>c.label)))""")
    assert cols == ["Name", "Phone", "W-9", "Signature", "Shirt size", "Checked in"]


@pytest.mark.parametrize("admin", [True, False])
def test_contractor_columns_admin_only(admin):
    o = js(f"console.log(JSON.stringify(normRosterPrintOpts({{cols:['legal','address','email','bogus']}}, {str(admin).lower()}, '')))")
    if admin:
        assert o["cols"] == ["name", "email", "address", "legal"]
    else:
        assert o["cols"] == ["name", "email"]


def test_defaults_and_bounds():
    o = js("console.log(JSON.stringify(normRosterPrintOpts({who:'x', sort:'y', orient:'z', walkins:999, nums:false}, false, '10/22/2026')))")
    assert o["who"] == "active" and o["sort"] == "first" and o["orient"] == "portrait"
    assert o["walkins"] == 60 and o["nums"] is False and o["cols"] == ["name"] and o["date"] == "10/22/2026"
    assert js("console.log(JSON.stringify(normRosterPrintOpts({walkins:-3}, false, '').walkins))") == 0


def test_sorts_fold_accents_and_last_name_option():
    names = js("""const f=s=>rosterPrintSort(PEOPLE, s).map(p=>p.name);
      console.log(JSON.stringify([f('first'), f('last'), f('title')]))""")
    first, last, title = names
    assert first == ["Arely", "Bob Moe", "Érica Zeta", "Erin Adams"]   # Érica with the E's
    assert last == ["Erin Adams", "Arely", "Bob Moe", "Érica Zeta"]    # one-name Arely by "Arely"
    assert title == ["Erin Adams", "Bob Moe", "Arely", "Érica Zeta"]


def test_who():
    who = js("""const run=o=>rosterPrintPeople(PEOPLE, [PEOPLE[2], PEOPLE[3]],
        normRosterPrintOpts(o, false, '')).map(p=>p.id);
      console.log(JSON.stringify({
        active: run({who:'active'}), inactive: run({who:'active', inactive:true}),
        ready: run({who:'ready'}), needs: run({who:'needs'}),
        filters: run({who:'filters'}), filtersInactive: run({who:'filters', inactive:true}),
        title: run({who:'title', whoTitle:'Lead'}), lang: run({who:'lang', whoLang:'Spanish'})}))""")
    assert who["active"] == ["p3", "p1", "p2"]
    assert who["inactive"] == ["p3", "p4", "p1", "p2"]
    assert who["ready"] == ["p3", "p1"] and who["needs"] == ["p2"]
    assert who["filters"] == ["p3"] and who["filtersInactive"] == ["p3", "p4"]
    assert who["title"] == ["p2"] and who["lang"] == ["p1"]


def test_cells():
    c = js("""const p=PEOPLE[0], q=PEOPLE[2];
      console.log(JSON.stringify([rosterPrintCell(p,'phone'), rosterPrintCell(p,'address'),
        rosterPrintCell(p,'legal'), rosterPrintCell(PEOPLE[1],'avail'), rosterPrintCell(q,'avail'),
        rosterPrintCell(q,'texted'), rosterPrintCell(PEOPLE[3],'gender'), rosterPrintCell(p,'w9')]))""")
    assert c == ["(713) 555-0101", "1 Main St, Houston, TX 77002", "Erica Q Zeta", "None marked",
                 "2 · Oct 26 · Nov 2", "Oct 5", "M", ""]


def test_body_blank_cells_walk_ins_and_numbers():
    h = js("""const o=normRosterPrintOpts({...rosterPrintPreset('training'), walkins:2, fill:true, details:'1:00 to 5:00 PM'}, false, '10/23/2026');
      const people=rosterPrintPeople(PEOPLE, [], o);
      console.log(JSON.stringify(rosterPrintBody(people, o, 'Printed X')))""")
    assert "<h1>Installer Training Check-in</h1>" in h
    assert "Friday 10/23/2026 · 1:00 to 5:00 PM · 3 people, blank rows for walk-ins at the end" in h
    assert "<th class=\"n\">#</th><th>Name</th><th>Phone</th><th class=\"c\">W-9</th>" in h
    assert h.index("Direct deposit") < h.index("Availability") < h.index("Checked in")
    assert "Signature" not in h
    assert '<td class="n">1</td><td class="nm">Arely</td><td class="nw">(713) 555-0102</td><td></td>' in h
    assert '<td class="n">5</td><td></td><td></td>' in h          # walk-in rows numbered on
    assert '<td class="n">6</td>' not in h                         # only 2 fixed walk-in rows
    assert '<template id="rpblank"><tr><td class="n"></td>' in h  # fill-the-page row
    assert "—" not in h and "–" not in h


def test_css_orientation_and_repeating_header():
    css = js("console.log(JSON.stringify([rosterPrintCSS({orient:'portrait'}), rosterPrintCSS({orient:'landscape'})]))")
    assert "size:letter portrait" in css[0] and "size:letter landscape" in css[1]
    assert "counter(pages)" in css[0] and "background:#1f3d2b" in css[0] and "height:24px" in css[0]
    assert "thead{display:table-header-group}" in TEMPLATE and "tr{break-inside:avoid}" in TEMPLATE


def test_print_button_opens_the_dialog_and_remembers_choices():
    pr = TEMPLATE[TEMPLATE.index("document.getElementById('tbprint').onclick"):][:300]
    assert "openRosterPrintDlg()" in pr
    s = js_function("saveRpOpts")
    assert "try{" in s and "localStorage.setItem(RP_KEY" in s and "date, ...keep" in s
    assert "try{ saved=JSON.parse(localStorage.getItem(RP_KEY)" in js_function("openRosterPrintDlg")
    assert '<dialog id="rpdlg"' in TEMPLATE
    assert "rosterPrintFill.toString()" in js_function("printRosterSheet")


def test_sort_key_folds_accents_and_punctuation():
    keys = js("console.log(JSON.stringify(['Érica Gonzales', '(Fuentes)', 'Ana  María'].map(rosterPrintKey)))")
    assert keys == ["erica gonzales", "fuentes", "ana maria"]
