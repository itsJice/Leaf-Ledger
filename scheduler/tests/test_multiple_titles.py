"""Several titles per installer (Comments #36, joybells 2026-11-16: "multiple
titles can be added to the same installer, rather than having to add the same
installer multiple times"), and Comments #32/#33: Chris and Alberto (Leads)
also put on crews as General Installers.

`titles` is every title, primary first; `title` stays the primary so older
pages, pay class and logins keep reading one title.

Option 1 (the user, 2026-11-17): who LEADS a crew is decided exactly as
before -- by the primary title Lead. Extra titles only change counts (role
needs), title filters/groups and text groups. FAKE people only."""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _const(name):
    m = re.search(rf"^const {name}\s*=.*?\];", TEMPLATE, re.M | re.S)
    assert m, name
    return m.group(0)


PRELUDE = "\n".join([
    "const TITLES=['Lead','Lead Assist','Designer','General Installer'];",
    "const LANGS=['English','Spanish','Both']; let nextPersonId=1;",
    "const TITLE_CLS={'Lead':'lead','Lead Assist':'assist','Designer':'designer','General Installer':'gen'};",
    "const TITLE_ABBR={'Lead':'Lead','Lead Assist':'Assist','Designer':'Designer','General Installer':'General'};",
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
    *(js_function(n) for n in (
        "personTitles", "hasTitle", "extraTitles", "titlesText",
        "coverageCounts", "dayNeed", "dayCoverage", "titlePillHTML", "mainTitlePillHTML", "extraTitlePillsHTML",
        "perTitles", "perAlsoHTML")),
])


def run(body):
    return json.loads(run_js(PRELUDE + "\n" + body))


@needs_node
def test_norm_roster_derives_and_keeps_titles():
    out = run("""console.log(JSON.stringify(normRoster([
      {id:'p1', first:'Old', title:'Designer'},                                  // no titles yet
      {id:'p2', first:'Chris', title:'Lead', titles:['Lead','General Installer']},
      {id:'p3', first:'Moved', title:'Designer', titles:['Lead','General Installer']}, // title edited elsewhere
      {id:'p4', first:'Odd', title:'Boss', titles:['Boss','Designer','Designer','Nope']},
      {id:'p5', first:'Order', title:'General Installer', titles:['Designer','General Installer','Lead']},
    ]).map(p=>[p.title, p.titles])))""")
    assert out[0] == ["Designer", ["Designer"]]
    assert out[1] == ["Lead", ["Lead", "General Installer"]]
    # `title` wins; the rest stay as extras.
    assert out[2] == ["Designer", ["Designer", "Lead", "General Installer"]]
    # Unknown titles dropped, duplicates collapsed, primary falls back as before.
    assert out[3] == ["General Installer", ["General Installer", "Designer"]]
    # Primary first, extras in TITLES order.
    assert out[4] == ["General Installer", ["General Installer", "Lead", "Designer"]]


@needs_node
def test_one_title_people_count_exactly_as_before():
    """coverageCounts must match the old count-by-title for everyone who has
    one title, so no crew's chip changes until someone gets an extra title."""
    out = run("""
      const people=normRoster([
        {id:'p1',first:'A',title:'Lead'},{id:'p2',first:'B',title:'Lead Assist'},
        {id:'p3',first:'C',title:'Designer'},{id:'p4',first:'D',title:'General Installer'},
        {id:'p5',first:'E',title:'General Installer'}]);
      const old=w=>({lead:w.filter(p=>p.title==='Lead').length,
        assist:w.filter(p=>p.title==='Lead Assist'||p.title==='Designer').length,
        gen:w.filter(p=>p.title==='General Installer').length});
      console.log(JSON.stringify([coverageCounts(people), old(people)]));""")
    assert out[0] == out[1] == {"lead": 1, "assist": 2, "gen": 2}


@needs_node
def test_extra_titles_count_toward_role_needs_but_never_make_a_lead():
    """Comments #32/#33 under option 1: Chris (Lead + General Installer) on
    Lesly's crew fills a general seat (a spare lead fills down); an extra
    Designer title fills an assist seat; an extra Lead title on a General
    Installer does NOT count as a lead -- only a primary Lead leads."""
    out = run("""
      const roster=normRoster([
        {id:'p1',first:'Lesly',title:'Lead'},
        {id:'p2',first:'Chris',title:'Lead',titles:['Lead','General Installer']},
        {id:'p3',first:'Gen',title:'General Installer'},
        {id:'p4',first:'Desi',title:'General Installer',titles:['General Installer','Designer']},
        {id:'p5',first:'Xtra',title:'General Installer',titles:['General Installer','Lead']}]);
      const personById=id=>roster.find(p=>p.id===id);
      const C={1:{roleNeed:{leads:1, general:2, designer:1}}};
      let staffing={'d1':['p2','p1','p3','p4'], 'd2':['p2','p3'], 'd3':['p5','p3','p4']};
      const day=id=>({id, stops:[1], half:[]});
      const r=id=>{ const c=dayCoverage(day(id)); return [c.lead, c.assist, c.gen, c.shortLead, c.short, c.state]; };
      console.log(JSON.stringify({d1:r('d1'), d2:r('d2'), d3:r('d3')}));""")
    # Need 1 lead + 1 assist + 2 general = 4. Two primary Leads (the spare one
    # fills a general seat), Desi counts as assist through her extra Designer.
    assert out["d1"] == [2, 1, 1, 0, 0, "ok"]
    # Chris alone is still a lead (his primary title), as before.
    assert out["d2"][0] == 1 and out["d2"][3] == 0
    # Xtra's extra Lead title doesn't cover the lead need: still NO LEAD.
    assert out["d3"] == [0, 1, 2, 1, 1, "bad"]


@needs_node
def test_pills_and_dialog_titles():
    out = run("""
      const [p]=normRoster([{id:'p1',first:'Chris',title:'Lead',titles:['Lead','General Installer']}]);
      console.log(JSON.stringify([titlePillHTML(p), titlePillHTML(p,true), titlesText(p),
        perTitles('Lead',['Designer','Lead','General Installer']), perTitles('Nope',[]),
        perAlsoHTML('Lead',['General Installer'])]));""")
    assert out[0].startswith('<span class="pill lead">Lead</span><span class="pill ttx gen"')
    assert ">+General</span>" in out[0]
    assert '<span class="pill lead">Lead</span>' in out[1]
    assert out[2] == "Lead, General Installer"
    assert out[3] == ["Lead", "Designer", "General Installer"]
    assert out[4] == ["General Installer"]
    assert 'data-also="Lead"' not in out[5]
    assert 'data-also="General Installer" checked' in out[5]
    assert 'data-also="Designer">' in out[5]


def test_readers_match_any_title():
    """Roster filter, text groups, the Teams filter and the staffing picker's
    title groups match any title."""
    assert "hasTitle(p,f.title)" in js_function("rosterLists")
    assert "test:p=>txtActive(p)&&hasTitle(p,t)" in TEMPLATE
    assert "hasTitle(p, f.slice(2))" in TEMPLATE
    dlg = js_function("drawStaffDlg")
    assert "avail.filter(p=>hasTitle(p,t))" in dlg
    # The edit dialog saves both, primary first.
    go = TEMPLATE[TEMPLATE.index("document.getElementById('pergo').onclick"):]
    assert "title:titles[0], titles," in go[:2000]
    assert 'id="peralsoopts"' in TEMPLATE
    # Pay and logins are not decided here; training bypass stays primary-Lead only.
    assert "return p.title==='Lead' || attendedTraining" in js_function("staffPickable")


def test_who_leads_is_decided_by_the_primary_title_only():
    """Option 1: no crewLeads()/crew_leads -- every place that names a crew's
    lead reads the primary title, exactly as before several titles."""
    assert "crewLeads" not in TEMPLATE and "crewRoleTag" not in TEMPLATE
    checks = {
        "shiftCrewHTML": "pn.title==='Lead'?' · lead'",
        "remPeople": "const leads=who.filter(p=>p.title==='Lead');",
        "manifestHTML": "pn.title==='Lead'?' (lead)'",
        "pageLeads": "x.title==='Lead' && smsNumber(x.phone)",
        "loaderCrews": "filter(p=>p && p.title==='Lead')",
        "loadNights": "filter(p=>p && p.title==='Lead')",
        "sdDraw": "cv.who.filter(p=>p.title==='Lead')",
        "coverageCounts": "if(p.title==='Lead') lead++;",
    }
    for name, needle in checks.items():
        assert needle in js_function(name), name


@needs_node
def test_picker_lists_a_person_under_each_title():
    out = run("""
      const [p]=normRoster([{id:'p1',first:'Chris',title:'Lead',titles:['Lead','General Installer']}]);
      console.log(JSON.stringify([TITLES.filter(t=>hasTitle(p,t)), mainTitlePillHTML(p)]));""")
    assert out[0] == ["Lead", "General Installer"]
    assert 'title="Main title: Lead"' in out[1] and ">Lead</span>" in out[1]
    dlg = js_function("drawStaffDlg")
    assert "p.title===t ? extraTitlePillsHTML(p) : mainTitlePillHTML(p)" in dlg
