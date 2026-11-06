"""T-shirt size on the installer roster (Comments #26, Joy 2026-10-26: "need
a location on each profile for t-shirt size"). The sizes are the Installer
Form's: S, M, L, XL, 2XL, 3XL. It has to survive normalisation and the
stale-tab merge, and show in the editor, the roster card, Download and Print.
Also: normRoster now carries keys it doesn't know, so a newer page's fields
survive an older page's save. FAKE people only."""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_stale_tab_merge import MERGE

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _const(name):
    m = re.search(rf"^const {name}\s*=.*?\];", TEMPLATE, re.M | re.S)
    assert m, name
    return m.group(0)


def _norm():
    return "\n".join([
        "const TITLES=['Lead','Lead Assist','Designer','General Installer'];",
        "const LANGS=['English','Spanish','Both']; let nextPersonId=1;",
        "function workDates(){ return ['2026-10-26','2026-10-27']; }",
        "function normRatings(o){ return o||{}; }",
        "function normTexts(t){ return t||[]; }",
        "function fmtPhone(v){ return String(v||''); }",
        _const("CONTRACTOR_TEXT"),
        js_function("contractorFields"),
        _const("SHIRT_SIZES"),
        _const("ROSTER_OWN_KEYS"),
        js_function("normShirt"),
        js_function("normRoster"),
        js_function("esc"),
        js_function("shirtOptionsHTML"),
    ])


def run(body):
    return json.loads(run_js(_norm() + "\n" + body))


@needs_node
def test_sizes_are_the_installer_forms():
    assert run("console.log(JSON.stringify(SHIRT_SIZES))") == ["S", "M", "L", "XL", "2XL", "3XL"]


@needs_node
def test_norm_shirt_maps_common_spellings():
    out = run("""console.log(JSON.stringify(['m',' M ','med','Medium','xl','X-Large','XXL','2x','xxxl',
      '3X','Small','lg','', null, undefined, '4XL'].map(normShirt)))""")
    assert out == ["M", "M", "M", "M", "XL", "XL", "2XL", "2XL", "3XL",
                   "3XL", "S", "L", "", "", "", "4XL"]


@needs_node
def test_norm_roster_keeps_shirt_and_unknown_keys():
    out = run("""console.log(JSON.stringify(normRoster([
      {id:'p1', first:'Ann', last:'A', shirt:'xxl', dates:[], futureField:{a:1}},
      {id:'p2', first:'Bo',  last:'B', title:'Boss'},
    ])))""")
    assert out[0]["shirt"] == "2XL"
    assert out[0]["futureField"] == {"a": 1}       # a newer page's field rides along
    assert out[1]["shirt"] == ""                   # always sent, so a clear is a clear
    # Known keys are still normalised, never taken raw.
    assert out[1]["title"] == "General Installer" and out[1]["name"] == "Bo B"


@needs_node
def test_norm_roster_contractor_fields_still_only_when_set():
    out = run("""console.log(JSON.stringify(normRoster([
      {id:'p1', first:'Ann', legalName:'  ', tax1099:false, street:'1 Main'}])))""")
    assert "legalName" not in out[0] and "tax1099" not in out[0]
    assert out[0]["street"] == "1 Main"


@needs_node
def test_picker_options_blank_sizes_and_a_kept_odd_value():
    h = run("console.log(JSON.stringify(shirtOptionsHTML('m')))")
    assert re.findall(r'value="([^"]*)"', h) == ["", "S", "M", "L", "XL", "2XL", "3XL"]
    assert '<option value="M" selected>M</option>' in h
    assert ">Not set<" in h
    h2 = run("console.log(JSON.stringify(shirtOptionsHTML('4XL')))")
    assert re.findall(r'value="([^"]*)"', h2)[-1] == "4XL" and 'value="4XL" selected' in h2


MERGE_SCENARIO = """
const P=(id,first,shirt)=>({id, first, last:'Test', name:first+' Test', title:'General Installer',
  lang:'Both', gender:'Female', email:'', phone:'', notes:'', shirt:shirt||'', ratings:{}, texts:[],
  times:['day','night'], dates:['2026-10-26'], active:true});
const clone=x=>JSON.parse(JSON.stringify(x));
const BASE={placement:{}, approved:[], moves:[], comments:{}, staffing:{}, newClients:[],
  roster:[P('p1','Ana','M'), P('p2','Luis','')]};
"""


@needs_node
def test_merge_keeps_a_size_set_here_and_changes_made_elsewhere():
    out = json.loads(run_js(MERGE + "\n" + MERGE_SCENARIO + """
      const mine=clone(BASE); mine.roster[1].shirt='XL';
      const theirs=clone(BASE); theirs.roster[1].notes='Has a truck'; theirs.roster[0].shirt='L';
      console.log(JSON.stringify(mergeShared(BASE, mine, theirs)));"""))
    assert out["conflicts"] == [] and out["hard"] == []
    roster = {p["id"]: p for p in out["state"]["roster"]}
    assert roster["p2"]["shirt"] == "XL" and roster["p2"]["notes"] == "Has a truck"
    assert roster["p1"]["shirt"] == "L"


def test_editor_saves_and_loads_the_size():
    assert 'id="pershirt"' in TEMPLATE and "T-shirt size" in TEMPLATE
    save = TEMPLATE[TEMPLATE.index("getElementById('pergo').onclick"):]
    save = save[:save.index("perdlg.close()")]
    assert "shirt:normShirt(document.getElementById('pershirt').value)" in save
    assert "shirtOptionsHTML(person ? person.shirt : '')" in js_function("openPersonDlg")


def test_roster_card_download_and_print_show_it():
    assert "Shirt ${esc(p.shirt)}" in js_function("personDetailHTML")
    rows = js_function("rosterRows")
    assert "'Shirt'" in rows and "p.shirt||''" in rows
    assert "key:'shirt'" in js_function("rosterPrintColumns")
    assert "case 'shirt': return p.shirt||'';" in js_function("rosterPrintCell")
    assert "Shirt:6" in js_function("downloadRoster")
