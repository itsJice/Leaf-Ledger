"""Comment #58: the crew card's Reorder window.

"there should be a thing on the crews that you could click reorder and
quickly have a window that has a drag and drop of the order instead of
having to click all 8 one by one each move" (Justice).

The window's rules are pure and pulled out of review_template.html into
node, next to the lock rules they reuse (orderViolations / checkOrderMove):

- a step that keeps the locks moves the stop; one that breaks a lock is
  refused with the same reason the card's arrows give
- a lone First on top (or Last at the bottom) is fixed in place
- the change-log line reads "Reordered Crew 1, Fri 11/27"

Plus the wiring: the button on the crew card, the dialog, Save as ONE undo
step and one log entry, the read-only guard, and the per-stop link.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = open(os.path.join(HERE, "review_template.html"), encoding="utf-8").read()
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def js_function(name):
    start = TEMPLATE.index(f"function {name}(")
    depth, i = 0, TEMPLATE.index("{", start)
    while True:
        ch = TEMPLATE[i]
        depth += ch == "{"
        depth -= ch == "}"
        i += 1
        if depth == 0:
            return TEMPLATE[start:i]


def js_line(prefix):
    start = TEMPLATE.index(prefix)
    return TEMPLATE[start:TEMPLATE.index("\n", start)]


def run(expr, pins=None, source=None):
    src = "\n".join([
        js_line("const PIN_SHORT="),
        *(js_function(n) for n in ("orderViolations", "checkOrderMove", "moveInOrder",
                                   "tryReorder", "reorderFixed", "reorderLabel")),
        f"const PINS={json.dumps(pins or {})}, SRC={json.dumps(source or {})};",
        "const pin=r=>PINS[r]||null, name=r=>r, src=r=>SRC[r]||null;",
        f"console.log(JSON.stringify({expr}));",
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(src)
    try:
        out = subprocess.run([NODE, f.name], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)
    finally:
        os.unlink(f.name)


EIGHT = ["A", "B", "C", "D", "E", "F", "G", "H"]


@needs_node
def test_move_in_order_moves_one_stop_anywhere():
    assert run(f"moveInOrder({json.dumps(EIGHT)}, 7, 0)") == ["H", "A", "B", "C", "D", "E", "F", "G"]
    assert run(f"moveInOrder({json.dumps(EIGHT)}, 0, 7)") == ["B", "C", "D", "E", "F", "G", "H", "A"]
    assert run(f"moveInOrder({json.dumps(EIGHT)}, 2, 99)")[-1] == "C"
    assert run(f"moveInOrder({json.dumps(EIGHT)}, 9, 0)") == EIGHT


@needs_node
def test_one_drag_does_what_seven_arrow_clicks_did():
    r = run(f"tryReorder({json.dumps(EIGHT)}, 7, 0, pin, name, src)")
    assert r == {"ok": True, "order": ["H", "A", "B", "C", "D", "E", "F", "G"]}


@needs_node
def test_no_move_is_ok_and_same():
    r = run(f"tryReorder({json.dumps(EIGHT)}, 3, 3, pin, name, src)")
    assert r["ok"] is True and r["same"] is True and r["order"] == EIGHT


@needs_node
def test_a_move_past_a_locked_last_is_refused_with_the_arrows_reason():
    r = run(f"tryReorder({json.dumps(EIGHT)}, 2, 7, pin, name, src)", pins={"H": "last"})
    assert r["ok"] is False and r["reason"] == "H is locked Last" and r["order"] == EIGHT


@needs_node
def test_a_move_above_a_planner_first_says_planner():
    r = run(f"tryReorder({json.dumps(EIGHT)}, 4, 0, pin, name, src)",
            pins={"A": "first"}, source={"A": "planner"})
    assert r["ok"] is False and r["reason"] == "A goes first (planner)"


@needs_node
def test_two_firsts_may_still_trade_in_the_window():
    r = run(f"tryReorder({json.dumps(EIGHT)}, 1, 0, pin, name, src)", pins={"A": "first", "B": "first"})
    assert r["ok"] is True and r["order"][:2] == ["B", "A"]


@needs_node
def test_lone_first_and_last_are_fixed_others_are_not():
    pins = {"A": "first", "H": "last"}
    fixed = run(f"{json.dumps(EIGHT)}.map((_,i)=>reorderFixed({json.dumps(EIGHT)}, i, pin, name, src))", pins=pins)
    assert fixed == [True, False, False, False, False, False, False, True]


@needs_node
def test_a_middle_lock_can_move_among_the_middle():
    pins = {"D": "middle"}
    assert run(f"reorderFixed({json.dumps(EIGHT)}, 3, pin, name, src)", pins=pins) is False
    r = run(f"tryReorder({json.dumps(EIGHT)}, 3, 0, pin, name, src)", pins=pins)
    assert r["ok"] is False and "locked Middle" in r["reason"]


@needs_node
def test_reorder_label():
    assert run("reorderLabel('Crew 1', 'Fri', '2026-11-27')") == "Reordered Crew 1, Fri 11/27"
    assert run("reorderLabel('Crew 2', '', '2026-12-03')") == "Reordered Crew 2, 12/3"


def test_crew_card_has_a_reorder_button_for_days_with_two_or_more_stops():
    card = js_function("buildDayCard")
    assert "orderbtn" in card and "Reorder" in card
    assert "!READONLY && d.stops.length>1" in card
    assert "openReorderDlg(d.id)" in card


def test_dialog_markup_has_cancel_and_save_order():
    dlg = TEMPLATE[TEMPLATE.index('<dialog id="orddlg"'):]
    dlg = dlg[:dlg.index("</dialog>")]
    assert 'id="ordcancel">Cancel<' in dlg and ">Save order<" in dlg
    assert 'id="ordlist"' in dlg and 'role="status"' in dlg


def test_save_is_one_undo_step_one_log_line_and_checks_locks():
    fn = js_function("saveDayOrder")
    assert fn.count("pushUndo()") == 1 and fn.count("persist()") == 1
    assert "checkDayOrder(d, order)" in fn
    assert "manualOrder[d.id]=[...order]" in fn
    assert "reorderLabel(" in fn and "to:'ORDER'" in fn
    assert "roBlocked()" in fn


def test_session_log_reads_the_reorder_line_plainly():
    log = js_function("renderLog")
    assert "m.to==='ORDER'" in log


def test_legacy_move_replay_skips_rowless_entries():
    assert "if(!m || m.row==null) return; try{ applyMove(m.row, m.to, false)" in TEMPLATE


def test_preview_does_not_leave_a_hand_order_behind():
    fn = js_function("reorderPreview")
    assert "finally" in fn and "delete manualOrder[d.id]" in fn


def test_keyboard_touch_and_arrow_controls():
    row = js_function("wireOrdRow")
    assert "ArrowUp" in row and "ArrowDown" in row
    assert "touchstart" in row and "pointerdown" in row
    drag = js_function("ordDragStart")
    assert "setPointerCapture" in drag and "tryReorder(" in drag


def test_position_fold_links_to_the_window():
    assert "Reorder the whole day" in js_function("peekPositionHTML")
    assert "openReorderDlg(id)" in TEMPLATE


def test_no_em_dashes_in_the_new_window():
    dlg = TEMPLATE[TEMPLATE.index('<dialog id="orddlg"'):]
    dlg = dlg[:dlg.index("</dialog>")]
    body = TEMPLATE[TEMPLATE.index("// ---------- Reorder window (comment #58)"):TEMPLATE.index("orddlg.addEventListener('close'")]
    assert "—" not in dlg and "—" not in re.sub(r"//.*", "", body)
