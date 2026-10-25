"""Shift notes on the Install Schedule (review_template.html).

10/24/2026, on a Staffing shift card: "I need a way to make notes for the
install day on this page."

Shared state `shiftNotes` is {shiftKey: {text, by, at}}, keyed like
crewNames: a crew-day's own id, or a Dallas run's key so one note covers the
whole week. These run the template's own functions in node, like
test_crew_names.py. No real names.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_dallas_nights import BOARD, MERGE, fns

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

NOTES = BOARD + "\nconst SHIFT_NOTE_MAX=2000;\nlet shiftNotes={};\nlet roster=[];\n" + fns(
    "normShiftNoteText", "normShiftNote", "shiftNoteKey", "normShiftNotes", "withShiftNote",
    "shiftNoteOf", "shiftNoteStamp", "shiftNoteBy", "shiftNoteByline")


def run(body):
    return json.loads(run_js(NOTES + body))


def test_key_is_the_day_id_for_houston_and_the_run_for_a_dallas_week():
    out = run("""
      days=['2026-11-02|Crew 1|0','2026-11-05|Crew 1|0','2026-11-04|Crew 2|0','2026-12-01|Crew 3|0']
        .map(id=>day(id,[1]));
      days.push(hydrate({id:'2026-12-01|Training|0', date:'2026-12-01', crew:'Training', stops:[], training:true}));
      shiftNotes={'dallas|2026-11-02|Crew 1':{text:'Gate code at the office', by:'', at:''}};
      console.log(JSON.stringify({keys:days.map(shiftNoteKey),
        notes:days.map(d=>{ const n=shiftNoteOf(d); return n && n.text; })}));
    """)
    assert out["keys"] == ["dallas|2026-11-02|Crew 1", "dallas|2026-11-02|Crew 1", "dallas|2026-11-02|Crew 2",
                           "2026-12-01|Crew 3|0", "2026-12-01|Training|0"]
    # one note covers every night of that crew's Dallas week, and nobody else
    assert out["notes"] == ["Gate code at the office", "Gate code at the office", None, None, None]


def test_text_is_cleaned_and_capped():
    out = run("""
      console.log(JSON.stringify([
        normShiftNoteText('  Line one   \\r\\nLine two\\t\\n\\n\\n\\nLine three  '),
        normShiftNoteText('x'.repeat(2100)).length, normShiftNoteText(null), normShiftNoteText('  \\n ')]));
    """)
    assert out == ["Line one\nLine two\n\nLine three", 2000, "", ""]


def test_set_stamp_and_empty_removes():
    out = run("""
      let n=withShiftNote({}, 'k', ' Bring the tall ladder ', 'a@x.com', '2026-10-25T01:31:00.000Z');
      const a=JSON.parse(JSON.stringify(n));
      const same=withShiftNote(n, 'k', 'Bring the tall ladder', 'b@x.com', '2026-10-26T01:31:00.000Z');
      const gone=withShiftNote(n, 'k', '   ', 'b@x.com', 'later');
      console.log(JSON.stringify({a, same, gone}));
    """)
    assert out["a"] == {"k": {"text": "Bring the tall ladder", "by": "a@x.com", "at": "2026-10-25T01:31:00.000Z"}}
    assert out["same"] == out["a"]          # the same text keeps who really wrote it
    assert out["gone"] == {}


def test_saved_notes_are_normalized_and_dropped_for_shifts_that_are_gone():
    out = run("""
      days=['2026-12-01|Crew 1|0','2026-11-03|Crew 2|0'].map(id=>day(id,[1]));
      console.log(JSON.stringify([
        normShiftNotes({'2026-12-01|Crew 1|0':{text:' A ', by:7, at:'nope'},
                        'dallas|2026-11-02|Crew 2':'Plain text',
                        '2026-12-09|Crew 1|0':{text:'gone'}, x:{text:''}, y:5, z:['a']}),
        normShiftNotes(null), normShiftNotes(['a']),
        normShiftNotes({a:{text:'A', at:1793000000000}}, new Set(['a']))]));
    """)
    assert out[0] == {"2026-12-01|Crew 1|0": {"text": "A", "by": "", "at": ""},
                      "dallas|2026-11-02|Crew 2": {"text": "Plain text", "by": "", "at": ""}}
    assert out[1] == {} and out[2] == {}
    assert out[3]["a"]["at"].startswith("2026-")


def test_byline_is_12_hour_central_and_names_the_roster_person():
    out = run("""
      roster=[{id:'p1', name:'Lead A', email:'Lead.A@Example.com'}];
      console.log(JSON.stringify([
        shiftNoteStamp('2026-10-25T01:31:00.000Z'), shiftNoteStamp('2026-12-01T15:05:00.000Z'),
        shiftNoteStamp(''), shiftNoteStamp('junk'),
        shiftNoteByline({text:'t', by:'lead.a@example.com', at:'2026-10-25T01:31:00.000Z'}),
        shiftNoteByline({text:'t', by:'someone@example.com', at:''}),
        shiftNoteByline({text:'t', by:'', at:''}), shiftNoteByline(null)]));
    """)
    assert out == ["Edited 10/24/2026 8:31 PM", "Edited 12/01/2026 9:05 AM", "", "",
                   "Edited 10/24/2026 8:31 PM · Lead A", "someone@example.com", "", ""]


def test_shift_notes_merge_three_ways_on_a_stale_tab():
    out = json.loads(run_js(MERGE + """
      const N=(text,at)=>({text, by:'', at:at||''});
      const base={placement:{}, shiftNotes:{a:N('A'), b:N('B')}};
      const mine=clone(base), theirs=clone(base);
      mine.shiftNotes={a:N('A2','t2'), b:N('B'), c:N('C')};   // I edited a, wrote c
      theirs.shiftNotes={a:N('A'), d:N('D')};                // they cleared b, wrote d
      const r=mergeShared(base, mine, theirs);
      const both=mergeShared(base, {shiftNotes:{a:N('Mine')}}, {shiftNotes:{a:N('Theirs')}}, (k,x)=>x);
      // the same text with only a different stamp is not a conflict
      const stamp=mergeShared({shiftNotes:{a:N('A','t1')}}, {shiftNotes:{a:N('A','t2')}}, {shiftNotes:{a:N('A','t3')}});
      console.log(JSON.stringify({got:r.state.shiftNotes, conflicts:r.conflicts,
        both:[both.state.shiftNotes.a.text, both.conflicts], stamp:[stamp.state.shiftNotes.a.at, stamp.conflicts]}));
    """))
    assert out["got"] == {"a": {"text": "A2", "by": "", "at": "t2"}, "c": {"text": "C", "by": "", "at": ""},
                          "d": {"text": "D", "by": "", "at": ""}}
    assert out["conflicts"] == []
    assert out["both"] == ["Theirs", ["Note for a"]]
    assert out["stamp"] == ["t3", []]


def test_every_save_and_load_path_carries_shift_notes():
    assert "'shiftNotes'" in re.search(r"const SHARED_MAP_KEYS=.*", TEMPLATE).group(0)
    assert "shiftNotes, roster" in js_function("snapshot")
    assert "shiftNotes, roster" in js_function("stateBlob")
    for fn in ("restoreBlob", "restoreHistoryEntry"):
        src = js_function(fn)
        assert src.index("shiftNotes = normShiftNotes(") > src.index("applyPlacement(")
    boot = TEMPLATE[TEMPLATE.index("const s = JSON.parse(localStorage.getItem(LS_KEY)||'{}');"):]
    assert boot.index("shiftNotes = normShiftNotes(s.shiftNotes)") > boot.index("applyPlacement(s.placement)")
    assert "shiftNotes = normShiftNotes(shiftNotes)" in js_function("render")
    assert "ME_EMAIL=" in js_function("loadMeRole")


def test_notes_show_where_the_crew_sees_them_and_read_only_cant_edit():
    assert "shiftNoteCardHTML(sh)" in js_function("shiftCardHTML")
    assert "dayNoteLineHTML(d)" in js_function("buildDayCard")
    assert "shiftNoteOf(d)" in js_function("manifestHTML")
    assert 'id="stfnote"' in TEMPLATE and "stfNoteHTML(sh)" in js_function("drawStaffDlg")
    gate = js_function("canEditShiftNotes")
    for flag in ("READONLY", "VIEWONLY", "TVMODE", "ALERT_EDIT_ROLES"):
        assert flag in gate
    for fn in ("startShiftNoteEdit", "setShiftNote"):
        src = js_function(fn)
        assert "roBlocked()" in src and "canEditShiftNotes()" in src
    assert "canEditShiftNotes()" in js_function("shiftNoteCardHTML")
    # no em dashes in the new user-facing text
    for fn in ("shiftNoteCardHTML", "stfNoteHTML", "dayNoteLineHTML", "startShiftNoteEdit", "shiftNoteStamp"):
        assert "—" not in js_function(fn)
