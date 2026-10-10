"""Board dates -> client cards, and the export's notes column (review_template.html).

Comments #14-17: a stop moved on the Install Schedule board did not move the
date on the client's season card, and the Excel export's "Repairs & install
notes" column still read the spreadsheet's old note. The board owns dates
(user, 2026-10-06), so every save now sends `dateMoves` -- the clients whose
board date changed since the last save that landed -- and the export reads
the client record's notes. These run the template's own functions in node.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

DATE_FNS = ["boardDatesByClient", "boardDateMoves", "placementDayList"]


def run(names, body):
    src = "\n".join(js_function(n) for n in names) + "\n" + body
    return json.loads(run_js(src))


INFO = """
  const C={1:{name:'Jinks, Amy'},2:{name:'Crane Worldwide'},3:{name:'Crane Worldwide'},
           4:{name:'Gala Hall', visitType:'Takedown'},5:{name:'Gala Hall'}};
  const info=r=>C[r] ? {key:C[r].name.toLowerCase(), name:C[r].name, id:r===1?41:null,
                        visitType:C[r].visitType} : null;
  const CUT='2026-12-25';
"""


@needs_node
def test_dates_per_client_earliest_visit_and_kinds():
    out = run(DATE_FNS, INFO + """
      const days=[
        {date:'2026-11-13', stops:[1]},
        {date:'2026-11-20', stops:[3]}, {date:'2026-11-18', stops:[2]},   // two install visits
        {date:'2026-11-21', stops:[4]}, {date:'2026-11-20', stops:[5]},   // event + its teardown
        {date:'2027-01-06', stops:[1]},                                   // Christmas takedown
        {date:'2026-11-14', training:true, stops:[1]},                    // training: ignored
      ];
      console.log(JSON.stringify(boardDatesByClient(days, CUT, info)));
    """)
    assert out == {
        "jinks, amy": {"name": "Jinks, Amy", "id": 41, "install": "2026-11-13", "takedown": "2027-01-06"},
        "crane worldwide": {"name": "Crane Worldwide", "id": None, "install": "2026-11-18"},
        # the event teardown never overwrites the install date
        "gala hall": {"name": "Gala Hall", "id": None, "install": "2026-11-20"},
    }


@needs_node
def test_moves_only_what_changed_and_undo_sends_the_old_date_back():
    out = run(DATE_FNS, INFO + """
      const at=(d1)=>boardDatesByClient([{date:d1, stops:[1]}, {date:'2026-11-18', stops:[2]}], CUT, info);
      const loaded=at('2026-11-13');
      const moved=at('2026-11-16');
      console.log(JSON.stringify([
        boardDateMoves(loaded, loaded),          // nothing moved: nothing sent
        boardDateMoves(moved, loaded),           // drag Amy to the 16th
        boardDateMoves(loaded, moved),           // undo: the 13th goes back to the card
        boardDateMoves(at('2026-11-13'), {}),    // newly placed: no "from"
        boardDateMoves({}, loaded),              // taken off the board: not this path
      ]));
    """)
    same, move, undo, placed, removed = out
    assert same == [] and removed == []
    assert move == [{"name": "Jinks, Amy", "id": 41, "kind": "install",
                     "date": "2026-11-16", "from": "2026-11-13"}]
    assert undo == [{"name": "Jinks, Amy", "id": 41, "kind": "install",
                     "date": "2026-11-13", "from": "2026-11-16"}]
    assert {m["name"] for m in placed} == {"Jinks, Amy", "Crane Worldwide"}
    assert all(m["from"] is None for m in placed)


@needs_node
def test_saved_placement_reads_dates_off_day_ids():
    out = run(DATE_FNS, INFO + """
      const place={'1':['2026-11-13|A|0'], '2':['2026-11-18|B|0','2026-11-18|C|0'], '3':['bogus']};
      console.log(JSON.stringify(boardDatesByClient(placementDayList(place), CUT, info)));
    """)
    assert out == {"jinks, amy": {"name": "Jinks, Amy", "id": 41, "install": "2026-11-13"},
                   "crane worldwide": {"name": "Crane Worldwide", "id": None, "install": "2026-11-18"}}


def test_every_save_carries_date_moves_and_baselines_are_set():
    """Every board change goes through persist() -> pushShared -> sharedSnapshot,
    so one hook there covers drags, the move dialog, moveWholeDay, the slot
    finder, undo/redo and history restore."""
    shared = js_function("sharedSnapshot")
    assert "boardDateMoves(cur, syncedBoardDates)" in shared
    assert "dateMoves}" in shared
    push = js_function("pushSharedNow")
    assert "if(r.ok && sent) syncedBoardDates=sent;" in push
    assert "if(!AUTH || READONLY) return false;" in push      # archived / viewer never send
    pull = js_function("pullShared")
    assert pull.count("syncedBoardDates =") == 3
    # never the other way: nothing reads a card's date onto the board
    assert "install_date" not in js_function("applyPlacement")
    for fn in ("moveWholeDay", "undo", "redo"):
        assert "persist()" in js_function(fn)


# ─── the export's notes column ───────────────────────────────────────────────

NOTE_FNS = ["installNoteFor", "productionNoteFor", "exportNotesFor"]


@needs_node
def test_export_notes_use_the_client_record_then_fall_back():
    out = run(NOTE_FNS, """
      const SEASON=['2026-10-01'];
      const C={1:{name:'A', repairNotes:'OLD sheet note', advice:'sheet install'},
               2:{name:'B', repairNotes:'OLD sheet note'},
               3:{name:'C', repairNotes:''}};
      const dir={
        1:{activity:[{kind:'christmas_install', season:'2025', detail:{production_notes:'Rewire garland'}},
                     {kind:'christmas_install', season:'2026', detail:{notes:'Gate code 1234'}}]},
        2:{activity:[]},
      };
      const appClientFor=r=>dir[r]||null;
      console.log(JSON.stringify([exportNotesFor(1), exportNotesFor(2), exportNotesFor(3)]));
    """)
    assert out == ["Rewire garland | Gate code 1234", "OLD sheet note", ""]


def test_export_column_reads_the_live_notes():
    assert "{key:'notes',   label:'Repairs & install notes',     width:34, get:x=>exportNotesFor(x.r)}" in TEMPLATE
    assert "x.c.repairNotes" not in TEMPLATE
    assert "const x = {c, a, p, date, r};" in js_function("buildBillingRows")
