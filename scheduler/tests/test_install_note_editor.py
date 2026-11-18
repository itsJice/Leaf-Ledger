"""Comment #38: install notes can be added, edited and cleared after the
install exists, right on the stop card.

The card's "Install notes" box only drew when a note was already there, and
the only way to change one was the client editor's "This season" field, so
staff couldn't see how to add one. An added stop (a callback, "Part B") kept
the note typed into the "add a client" dialog with no way to change it. Now
"This job" shows the note with Edit, or "Add install note" when there is
none, and saves to the same place the note is read from.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def run(names, body, prelude=""):
    src = prelude + "\n" + "\n".join(js_function(n) for n in names) + "\n" + body
    return json.loads(run_js(src))


@needs_node
def test_the_change_sent_is_trimmed_text_null_to_clear_or_nothing():
    out = run(["installNoteChange"], """
      console.log(JSON.stringify({
        added: installNoteChange('', '  Bring cords  '),
        same: installNoteChange('Bring cords', 'Bring cords ')===undefined,
        cleared: installNoteChange('Bring cords', '   ')===null,
        emptyStaysEmpty: installNoteChange('', '')===undefined,
      }));
    """)
    assert out == {"added": "Bring cords", "same": True, "cleared": True, "emptyStaysEmpty": True}


TARGET_STUBS = """
const C={1:{name:'District 121'}, 2:{name:'District 121', synthetic:true, advice:'Part B'},
         3:{name:'No card'}, 4:{name:'Callback', synthetic:true, advice:''}};
const notes={1:null, 2:{text:'Part B', live:false, own:true}, 3:{text:'Sheet', live:false}, 4:null, 5:{text:'Card', live:true}};
C[5]={name:'Callback, no own note', synthetic:true, advice:''};
function installNoteFor(r){ return notes[r]; }
function appClientFor(r){ return r===3 ? null : {id:266}; }
"""


@needs_node
def test_a_note_is_edited_where_it_is_read_from():
    out = run(["installNoteTarget"], """
      console.log(JSON.stringify([1,2,3,4,5].map(installNoteTarget)));
    """, TARGET_STUBS)
    # 1: card stop with no note -> season card; 2: added stop's own note;
    # 3: no client record, nowhere to save; 4: added stop, empty -> its own;
    # 5: an added stop with no note of its own shows the card's: edit that.
    assert out == ["card", "stop", None, "stop", "card"]


PEEK_STUBS = TARGET_STUBS + """
const IC={clip:'<i></i>'}; const SEASON=['2026-10-01'];
function peekEsc(s){ return String(s); }
let pkEditingInst=false, staff=true;
function canEditClientCard(){ return staff; }
function canEditHours(){ return staff; }
"""


@needs_node
def test_the_box_shows_add_or_edit_for_staff_and_stays_hidden_for_viewers():
    out = run(["installNoteTarget", "canEditInstallNote", "peekInstallNoteHTML"], """
      const r={};
      r.emptyStaff=peekInstallNoteHTML(1);
      r.noteStaff=peekInstallNoteHTML(2);
      staff=false;
      r.emptyViewer=peekInstallNoteHTML(1);
      r.noteViewer=peekInstallNoteHTML(2);
      staff=true; pkEditingInst=true;
      r.editingCard=peekInstallNoteHTML(1);
      r.editingStop=peekInstallNoteHTML(2);
      console.log(JSON.stringify(r));
    """, PEEK_STUBS)
    assert "Add install note" in out["emptyStaff"] and 'id="pkinstedit"' in out["emptyStaff"]
    assert "Part B" in out["noteStaff"] and ">Edit</button>" in out["noteStaff"]
    assert "· this stop" in out["noteStaff"]
    assert out["emptyViewer"] == ""
    assert "Part B" in out["noteViewer"] and "pkinstedit" not in out["noteViewer"]
    assert '<textarea id="pkinstin"' in out["editingCard"] and "season card" in out["editingCard"]
    assert ">Part B</textarea>" in out["editingStop"] and "this stop only" in out["editingStop"]


def test_the_card_wires_the_editor_and_a_refresh_never_clobbers_typing():
    i = TEMPLATE.index("function openStopPeek(")
    assert "pkEditingInst=false;" in TEMPLATE[i:i + 600]
    assert "wirePeekInstallNote(row);" in js_function("openStopPeek")
    refresh = js_function("refreshPeekLive")
    assert "if(ib && !pkEditingInst){ ib.innerHTML=peekInstallNoteHTML(row); wirePeekInstallNote(row); }" in refresh


def test_saves_go_to_the_season_card_or_the_stop_and_redraw_the_board():
    wire = js_function("wirePeekInstallNote")
    assert "putCardFacts(row, {fields:{notes:change}})" in wire
    assert "C[row].advice=change||'';" in wire and "persist();" in wire
    assert "render();" in wire


def test_another_tabs_note_edit_on_an_added_stop_comes_through():
    restore = js_function("restoreSyntheticClients")
    assert "C[def.row].advice = def.notes" in restore


def test_no_em_dashes_in_the_new_on_screen_text():
    for name in ("peekInstallNoteHTML", "installNoteErrorMessage"):
        assert "—" not in js_function(name)


@needs_node
def test_an_added_stop_shows_its_own_note_before_the_cards():
    out = run(["installNoteFor"], """
      const SEASON=['2026-10-01'];
      const C={60:{advice:''}, 61:{advice:'sheet'}, 900042:{advice:'PART B', synthetic:true}, 900043:{advice:'', synthetic:true}};
      const card={activity:[{kind:'christmas_install', season:'2026', detail:{notes:'PART A'}}]};
      function appClientFor(){ return card; }
      console.log(JSON.stringify([60,61,900042,900043].map(r=>installNoteFor(r).text)));
    """)
    assert out == ["PART A", "PART A", "PART B", "PART A"]
