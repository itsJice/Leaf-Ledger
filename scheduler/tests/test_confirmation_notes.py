"""Comment #44: the client's confirmation notes on the Install Schedule.

The season card's "Confirmation notes" (Clients tab, detail.confirmation_notes)
show on the stop card just above the Notes fold, with Edit for staff that saves
through the same season endpoint, and print on the crew sheet as a short
"Confirmation:" line. A return trip shows its client's note.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def run(names, body, prelude=""):
    src = prelude + "\n" + "\n".join(js_function(n) for n in names) + "\n" + body
    return json.loads(run_js(src))


STUBS = """
const SEASON=['2026-10-01']; const PAGE_SEASON='2026';
const card=(season, detail)=>({kind:'christmas_install', season, detail});
const CARDS={
  1:{id:1, activity:[card('2026', {confirmation_notes:'  11/15/26 - CSW sent email w/Install Date: 11/16/2026 '})]},
  2:{id:2, activity:[card('2025', {confirmation_notes:'last year'})]},
  3:{id:3, activity:[card('2026', {confirmation_notes:'', app_edits:{confirmation_notes:'x'}})]},
  4:{id:4, activity:[card('2026', {notes:'Bring cords'})]},
};
const C={1:{name:'A'}, 2:{name:'B'}, 3:{name:'C'}, 4:{name:'D'}, 5:{name:'No card'}, 6:{name:'A - Callback', of:1}};
function appClientFor(r){ if(C[r] && C[r].of!=null) return appClientFor(C[r].of); return CARDS[r]||null; }
"""


@needs_node
def test_reads_this_seasons_confirmation_note_from_the_card():
    out = run(["cardSeason", "confirmationNoteFor"], """
      console.log(JSON.stringify([1,2,3,4,5,6].map(confirmationNoteFor)));
    """, STUBS)
    note = {"text": "11/15/26 - CSW sent email w/Install Date: 11/16/2026", "season": "2026"}
    # 1: this season's note, trimmed; 2: only last season's -> none;
    # 3: cleared stays cleared; 4: no confirmation note; 5: no card;
    # 6: a return trip shows its client's note.
    assert out == [note, None, None, None, None, note]


PEEK_STUBS = STUBS + """
const IC={check:'<i></i>'};
function peekEsc(s){ return String(s); }
let pkEditingConf=false, staff=true;
function canEditClientCard(){ return staff; }
"""


@needs_node
def test_card_callout_with_edit_for_staff_only():
    out = run(["cardSeason", "confirmationNoteFor", "canEditConfirmationNote", "peekConfirmationHTML"], """
      const r={};
      r.noteStaff=peekConfirmationHTML(1);
      r.emptyStaff=peekConfirmationHTML(4);
      r.noCard=peekConfirmationHTML(5);
      staff=false;
      r.noteViewer=peekConfirmationHTML(1);
      r.emptyViewer=peekConfirmationHTML(4);
      staff=true; pkEditingConf=true;
      r.editing=peekConfirmationHTML(1);
      console.log(JSON.stringify(r));
    """, PEEK_STUBS)
    assert "Confirmation 2026" in out["noteStaff"] and 'id="pkconfedit"' in out["noteStaff"]
    assert "CSW sent email" in out["noteStaff"]
    assert "Add confirmation note" in out["emptyStaff"]
    assert out["noCard"] == ""          # nowhere to save it
    assert "CSW sent email" in out["noteViewer"] and "pkconfedit" not in out["noteViewer"]
    assert out["emptyViewer"] == ""
    assert 'id="pkconfin"' in out["editing"] and "Leave it empty to clear it" in out["editing"]


def test_callout_sits_just_above_the_notes_fold():
    i = TEMPLATE.index('<div id="pkconfbox">${peekConfirmationHTML(row)}</div>')
    j = TEMPLATE.index('<div class="pknotes" id="pknotes">')
    assert 0 < j - i < 120


def test_save_goes_through_the_season_card_and_clears_with_null():
    src = js_function("wirePeekConfirmation")
    assert "putCardFacts(row, {fields:{confirmation_notes:change}})" in src
    # installNoteChange gives null for an emptied box (the clear).
    assert "installNoteChange(" in src


def test_crew_sheet_prints_a_confirmation_line():
    src = js_function("manifestHTML")
    assert "conf=confirmationNoteFor(r)" in src
    assert re.search(r'<div class="cf"><b>Confirmation:</b> \$\{esc\(conf\.text\)\}</div>', src)


def test_no_em_dashes_in_the_new_text():
    for name in ("peekConfirmationHTML", "confirmationNoteFor", "wirePeekConfirmation"):
        assert "—" not in js_function(name)
