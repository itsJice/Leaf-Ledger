"""One person, many titles as the standard (user, 2026-11-25: combine
Cynthia's two roster entries "and this should be the standard so do this for
all"). Adding an installer whose full name is already on the roster offers to
add the title to that person instead of creating a second record; the seed
import folds same-name, same-contact entries. FAKE people only."""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

PRELUDE = "\n".join([
    "const TITLES=['Lead','Lead Assist','Designer','General Installer'];",
    *(js_function(n) for n in (
        "personTitles", "titlesText", "personNameKey", "sameNamePerson",
        "titlesWith", "sameNameAsk", "foldIntoPerson", "foldSameNamePeople")),
])


def run(body):
    return json.loads(run_js(PRELUDE + "\n" + body))


ROSTER = """const R=[
  {id:'p1', first:'Jane', last:'Sample', name:'Jane Sample', title:'Designer', titles:['Designer'],
   phone:'(555) 010-0001', email:'', dates:['2026-11-02'], notes:'Front office', active:true},
  {id:'p2', first:'Jose', last:'Example', name:'Jose Example', title:'Lead', titles:['Lead','General Installer'],
   phone:'', email:'', dates:[], notes:'', active:true},
];"""


@needs_node
def test_same_name_found_ignoring_case_and_spaces():
    out = run(ROSTER + """console.log(JSON.stringify([
      (sameNamePerson(R,'  jane ','SAMPLE ')||{}).id,
      sameNamePerson(R,'Jane','Samples'),
      sameNamePerson(R,'Janet','Sample'),
      sameNamePerson(R,'Jane','Sample','p1'),
      sameNamePerson(R,'',''),
    ]))""")
    assert out == ["p1", None, None, None, None]


@needs_node
def test_prompt_text_names_the_new_title():
    out = run(ROSTER + """console.log(JSON.stringify([
      sameNameAsk(R[0], ['General Installer']),
      sameNameAsk(R[1], ['General Installer']),
    ]))""")
    assert out[0]["msg"] == ("Jane Sample is already on the roster. "
                             "Add General Installer as another title instead?")
    assert out[0]["yes"] == "Add General Installer to Jane"
    assert out[1]["fresh"] == []
    assert "already on the roster as Lead, General Installer" in out[1]["msg"]


@needs_node
def test_fold_adds_title_keeps_main_and_existing_details():
    out = run(ROSTER + """console.log(JSON.stringify(foldIntoPerson(R[0], {
      title:'General Installer', titles:['General Installer','Lead Assist'],
      phone:'(555) 999-9999', email:'jane@example.com', notes:'Night crew',
      dates:['2026-11-03','2026-11-02']})))""")
    assert out["id"] == "p1"
    assert out["title"] == "Designer"
    assert out["titles"] == ["Designer", "Lead Assist", "General Installer"]
    assert out["phone"] == "(555) 010-0001"          # never overwritten
    assert out["email"] == "jane@example.com"        # blank filled
    assert out["dates"] == ["2026-11-02", "2026-11-03"]
    assert out["notes"] == "Front office | Night crew"
    assert out["active"] is True


@needs_node
def test_seed_folds_same_person_but_not_family():
    out = run("""console.log(JSON.stringify(foldSameNamePeople([
      {id:'p1', first:'Jane', last:'Sample', title:'General Installer', titles:['General Installer'],
       phone:'5550100001', email:'', dates:['2026-11-02'], notes:'', active:true},
      {id:'p2', first:'Jane', last:'Sample', title:'Designer', titles:['Designer'],
       phone:'(555) 010-0001', email:'', dates:['2026-11-05'], notes:'', active:true},
      {id:'p3', first:'Ann', last:'Example', title:'General Installer', titles:['General Installer'],
       phone:'5550100002', email:'', dates:[], notes:'', active:true},
      {id:'p4', first:'Anne', last:'Example', title:'General Installer', titles:['General Installer'],
       phone:'5550100002', email:'', dates:[], notes:'', active:true},
      {id:'p5', first:'Sam', last:'Twin', title:'Lead', titles:['Lead'],
       phone:'5550100003', email:'', dates:[], notes:'', active:true},
      {id:'p6', first:'Sam', last:'Twin', title:'General Installer', titles:['General Installer'],
       phone:'5550100004', email:'', dates:[], notes:'', active:true},
    ]).map(p=>[p.id, p.title, p.titles, p.dates])))""")
    ids = [r[0] for r in out]
    assert ids == ["p1", "p3", "p4", "p5", "p6"]       # family + different phones kept apart
    assert out[0][1:] == ["Designer", ["Designer", "General Installer"],
                          ["2026-11-02", "2026-11-05"]]


def test_add_dialog_asks_before_a_second_record():
    """The Save handler checks for a same-name person before pushing a new
    record, and the prompt has both answers."""
    i = TEMPLATE.index("document.getElementById('pergo').onclick")
    body = TEMPLATE[i:TEMPLATE.index("function togglePersonActive", i)]
    assert body.index("sameNamePerson(roster") < body.index("roster.push(")
    assert 'id="persameyes"' in TEMPLATE
    assert "It's a different person</button>" in TEMPLATE
    assert re.search(r"foldSameNamePeople\(normRoster\(SPEC\.rosterSeed", TEMPLATE)
