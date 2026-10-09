"""Stop order inside a day: the lock rules behind the drag handle, the
arrows and "Shortest route" on the Install Schedule page.

orderViolations / lockConflicts / checkOrderMove in review_template.html are
pure, so they're pulled out of the template and run in node:

- Firsts fill the top of the day (several may trade places), Lasts the
  bottom, and a Middle never opens or closes the day.
- A move is allowed when it breaks no lock the old order kept.
- Several Firsts (or Lasts) form a first (last) block: allowed, no chip.
- A day whose locks can't all be met says why (a Middle on a 1-2 stop day,
  or too few middle slots).
"""
import json
import os
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = open(os.path.join(HERE, "review_template.html"), encoding="utf-8").read()
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


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


def run(expr, pins, extra=""):
    src = "\n".join([
        js_line("const PIN_SHORT="),
        js_function("orderViolations"),
        js_function("lockConflicts"),
        js_function("checkOrderMove"),
        extra,
        f"const PINS={json.dumps(pins)};",
        "const pin=r=>PINS[r]||null, name=r=>r;",
        f"console.log(JSON.stringify({expr}));",
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(src)
    try:
        out = subprocess.run([NODE, f.name], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)
    finally:
        os.unlink(f.name)


DAY_PINS = {"Ana": "first", "Bo": "first", "Mid1": "middle", "Mid2": "middle", "Zed": "last"}
DAY = ["Ana", "Bo", "Cy", "Mid1", "Mid2", "Zed"]


def violations(order, pins=DAY_PINS):
    return [v["row"] for v in run(f"orderViolations({json.dumps(order)}, pin)", pins)]


def move(before, after, pins=DAY_PINS, source=None):
    extra = f"const SRC={json.dumps(source or {})};"
    return run(f"checkOrderMove({json.dumps(before)}, {json.dumps(after)}, pin, name, r=>SRC[r]||null)",
               pins, extra)


def conflicts(rows, pins):
    return run(f"lockConflicts({json.dumps(rows)}, pin, name)", pins)


def test_valid_day_has_no_violations():
    assert violations(DAY) == []


def test_two_firsts_may_trade_places():
    assert violations(["Bo", "Ana", "Cy", "Mid1", "Mid2", "Zed"]) == []
    assert move(DAY, ["Bo", "Ana", "Cy", "Mid1", "Mid2", "Zed"]) == {"ok": True}


def test_middles_may_move_among_middle_slots():
    assert move(DAY, ["Ana", "Bo", "Mid1", "Cy", "Mid2", "Zed"]) == {"ok": True}
    assert move(DAY, ["Ana", "Bo", "Mid2", "Mid1", "Cy", "Zed"]) == {"ok": True}


def test_unlocked_stop_can_move_anywhere_between_the_locks():
    assert move(DAY, ["Ana", "Bo", "Mid1", "Mid2", "Cy", "Zed"]) == {"ok": True}


def test_moving_below_a_last_is_blocked_with_the_lasts_name():
    r = move(DAY, ["Ana", "Bo", "Mid1", "Mid2", "Zed", "Cy"])
    assert r["ok"] is False and r["row"] == "Zed"
    assert r["reason"] == "Zed is locked Last"


def test_moving_above_a_first_is_blocked():
    r = move(DAY, ["Cy", "Ana", "Bo", "Mid1", "Mid2", "Zed"])
    assert r["ok"] is False and r["reason"] == "Bo is locked First"


def test_a_planner_first_says_so():
    r = move(DAY, ["Ana", "Cy", "Bo", "Mid1", "Mid2", "Zed"], source={"Bo": "planner"})
    assert r["ok"] is False and r["reason"] == "Bo goes first (planner)"


def test_middle_cannot_open_or_close_the_day():
    pins = {"M": "middle"}
    assert violations(["M", "a", "b"], pins) == ["M"]
    assert violations(["a", "b", "M"], pins) == ["M"]
    assert violations(["a", "M", "b"], pins) == []
    r = move(["a", "M", "b"], ["a", "b", "M"], pins)
    assert r["ok"] is False and "can't start or end the day" in r["reason"]


def test_middle_next_to_firsts_and_lasts_is_fine():
    pins = {"F": "first", "M": "middle", "L": "last"}
    assert violations(["F", "M", "L"], pins) == []


def test_no_locks_any_order_is_fine():
    assert violations(["c", "a", "b"], {}) == []
    assert move(["a", "b", "c"], ["c", "b", "a"], {}) == {"ok": True}


def test_a_day_already_breaking_a_lock_can_still_be_shuffled():
    # A Middle on a 2-stop day can't be met; swapping the two stops breaks
    # nothing new, so it is allowed.
    pins = {"M": "middle"}
    assert move(["M", "x"], ["x", "M"], pins) == {"ok": True}
    # ...but a move that breaks a lock the old order kept is still refused.
    pins = {"M": "middle", "L": "last"}
    r = move(["M", "a", "L"], ["M", "L", "a"], pins)
    assert r["ok"] is False and r["row"] == "L"


def test_several_lasts_are_a_last_block_not_a_conflict():
    assert conflicts(["a", "b", "L1", "L2"], {"L1": "last", "L2": "last"}) == []
    pins = {"L1": "last", "L2": "last"}
    assert violations(["a", "b", "L2", "L1"], pins) == []
    assert move(["a", "b", "L1", "L2"], ["a", "b", "L2", "L1"], pins) == {"ok": True}


def test_several_firsts_are_a_first_block_not_a_conflict():
    assert conflicts(["F1", "F2", "a"], {"F1": "first", "F2": "first"}) == []
    assert conflicts(["F1", "F2", "F3"], {"F1": "first", "F2": "first", "F3": "first"}) == []


def test_planner_first_plus_locked_first_is_allowed():
    """A planner "goes first" stop and a Locked First share the first block:
    no chip, and either may lead."""
    extra = "\n".join([
        js_function("isPlannerFirst"),
        js_function("pinOf"),
        "const SPEC={forceFirst:{p:true}}; let stopPin={f:'first'};",
    ])
    out = run("[lockConflicts(['p','f','a'], r=>pinOf(r,{}), name),"
              " orderViolations(['f','p','a'], r=>pinOf(r,{})),"
              " checkOrderMove(['p','f','a'], ['f','p','a'], r=>pinOf(r,{}), name)]", {}, extra)
    assert out == [[], [], {"ok": True}]


def test_a_stop_cannot_split_the_first_block():
    pins = {"F1": "first", "F2": "first"}
    r = move(["F1", "F2", "a", "b"], ["F1", "a", "F2", "b"], pins)
    assert r["ok"] is False and r["reason"] == "F2 is locked First"


def test_conflicts_middle_on_short_day():
    assert conflicts(["M", "x"], {"M": "middle"}) == [
        "M is locked Middle, but the day has only 2 stops."]
    assert conflicts(["M"], {"M": "middle"}) == [
        "M is locked Middle, but the day has only 1 stop."]


def test_conflicts_middle_squeezed_out_by_first_and_last():
    pins = {"F": "first", "M": "middle", "L": "last"}
    assert conflicts(["F", "M", "L"], pins) == []
    pins = {"M1": "middle", "M2": "middle", "M3": "middle"}
    assert conflicts(["M1", "M2", "M3"], pins) == ["Not enough middle slots for M1, M2 and M3."]
    # First + two Lasts + a Middle on a 3-stop day: no slot left for it.
    pins = {"F": "first", "M": "middle", "L1": "last", "L2": "last"}
    assert conflicts(["F", "M", "L1"], {"F": "first", "M": "middle", "L1": "last"}) == []
    assert conflicts(["F", "M", "L1", "L2"], pins) == []
    assert conflicts(["F1", "F2", "M", "L"], {"F1": "first", "F2": "first", "M": "middle", "L": "last"}) == []
    assert conflicts(["F", "M", "L"], {"F": "first", "M": "middle", "L": "last"}) == []


def test_no_conflicts_on_a_normal_day():
    assert conflicts(["F", "a", "M", "b", "L"], {"F": "first", "M": "middle", "L": "last"}) == []
    assert conflicts(["a", "b"], {}) == []


def test_apply_pins_puts_a_planner_first_on_top():
    """applyPins now reads pinOf, so a planner "goes first" stop (forceFirst
    or the day's startRow) is pulled to the top like a First lock, and the
    client's own lock still wins over it."""
    extra = "\n".join([
        js_function("isPlannerFirst"),
        js_function("pinOf"),
        js_function("applyPins"),
        "const SPEC={forceFirst:{p:true}}; let stopPin={L:'last', q:'last'};",
    ])
    out = run("[applyPins(['a','p','L','b'], {startRow:null}), applyPins(['a','b','s'], {startRow:'s'}),"
              " applyPins(['q','a'], {startRow:'q'})]", {}, extra)
    assert out == [["p", "a", "b", "L"], ["s", "a", "b"], ["a", "q"]]


def test_shortest_route_keeps_locks_and_beats_any_valid_order():
    """bestLockedOrder ("Shortest route" on a day of 8 or fewer stops):
    Firsts on top, Lasts at the bottom, Middles off the ends, and the drive
    is the shortest of every order that does that."""
    import itertools
    import random
    random.seed(3)
    n = 6
    D = [[0 if i == j else random.randint(5, 60) for j in range(n + 1)] for i in range(n + 1)]
    rows = [1, 2, 3, 4, 5, 6]
    pins = {"1": "middle", "4": "first", "6": "last", "2": "first"}
    extra = "\n".join([
        js_function("isPlannerFirst"),
        js_function("pinOf"),
        js_function("bestLockedOrder"),
        f"const D={json.dumps(D)}; const N={{1:1,2:2,3:3,4:4,5:5,6:6}};",
        "function leg(a,b){ return D[a][b]; } function prefRank(){ return 1; }",
        f"const SPEC={{forceFirst:{{}}}}; let stopPin={json.dumps(pins)};",
    ])
    out = run(f"bestLockedOrder({{stops:{json.dumps(rows)}, anchored:true, startRow:null}})", {}, extra)
    order = out["order"]

    def ok(o):
        F = [r for r in o if pins.get(str(r)) == "first"]
        L = [r for r in o if pins.get(str(r)) == "last"]
        return (set(o[:len(F)]) == set(F) and set(o[len(o) - len(L):]) == set(L)
                and pins.get(str(o[0])) != "middle" and pins.get(str(o[-1])) != "middle")

    def drive(o):
        seq = [0, *o, 0]
        return sum(D[a][b] for a, b in zip(seq, seq[1:]))

    assert ok(order)
    assert drive(order) == min(drive(list(p)) for p in itertools.permutations(rows) if ok(list(p)))
    assert out["path"] == [0, *order, 0]


def test_day_card_has_no_reorder_hint_text():
    # No hint text on the schedule (user, 2026-10-08): the grip and its
    # tooltip say it.
    assert "locks stay put" not in TEMPLATE
    assert "cordernote quiet" not in TEMPLATE


def order_bar(manual, day_id="d1"):
    src = "\n".join([
        f"const manualOrder={json.dumps(manual)};",
        js_function("orderBarHTML"),
        f"console.log(JSON.stringify(orderBarHTML({{id:{json.dumps(day_id)}, stops:[1,2,3,4]}})));",
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(src)
    try:
        out = subprocess.run([NODE, f.name], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)
    finally:
        os.unlink(f.name)


def test_shortest_route_only_on_a_hand_ordered_day():
    # (user, 2026-10-09) A planner-ordered day, even with 3+ stops, shows no
    # bar and no "Shortest route" button.
    assert order_bar({}) == ""
    assert order_bar({"d2": [3, 1, 2]}) == ""
    # A hand-ordered day: one bar with the text and the button together.
    html = order_bar({"d1": [3, 1, 2, 4]})
    assert html.count('class="cordernote"') == 1
    assert "Stop order set by hand" in html
    assert html.count('class="cautoorder"') == 1 and ">Shortest route</button>" in html
    # The day card builds its bar only from this helper.
    assert "${orderBarHTML(d)}" in js_function("buildDayCard")
    assert js_function("buildDayCard").count("cautoorder\"") == 0


def test_no_per_stop_manual_order_tag():
    # (user, 2026-10-09) After a hand reorder only the single bar says so;
    # the stops themselves carry no "manual order" tag.
    assert "manual order</span>" not in TEMPLATE
    assert "badge order" not in TEMPLATE
    assert "manual order" not in js_function("buildDayCard")
