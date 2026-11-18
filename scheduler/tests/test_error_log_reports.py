"""The Install Schedule's reports to the app's error log (review_template.html,
"telling the app's error log what happened").

The page tells the app when the board loaded but shows nothing (Comments
#39's blank schedule) or never finished starting up, and why a save was
refused or held back. These check the blank-screen rule in node, that the
report never leaves a standalone page and never throws, and that each save
path that blocks a save also reports it.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

BOOTED = dict(booted=True, view="days", daysInData=40, stopsInData=120, visibleChars=900,
              visibleChildren=30, hostingSeason=False, tv=False)


def blank_reason(**over):
    facts = {**BOOTED, **over}
    return json.loads(run_js(js_function("llBlankReason") + f"\nconsole.log(JSON.stringify(llBlankReason({json.dumps(facts)})));"))


@needs_node
def test_a_normal_board_is_not_blank():
    assert blank_reason() is None


@needs_node
@pytest.mark.parametrize("over,why", [
    ({"booted": False}, "The schedule never finished starting up"),
    ({"daysInData": 0}, "The schedule loaded with no days in it"),
    ({"visibleChars": 0, "visibleChildren": 0}, "The schedule loaded but the screen is empty (days view)"),
    ({"visibleChars": 2, "visibleChildren": 1, "view": "calendar"}, "The schedule loaded but the screen is empty (calendar view)"),
])
def test_blank_reasons(over, why):
    assert blank_reason(**over) == why


@needs_node
@pytest.mark.parametrize("over", [
    {"hostingSeason": True, "visibleChars": 0, "visibleChildren": 0},   # an older season is open
    {"tv": True, "visibleChars": 0, "visibleChildren": 0},              # the wall display
    {"visibleChars": 0, "visibleChildren": 5},                          # icons/cards with no text
])
def test_not_blank_when_something_else_owns_the_screen(over):
    assert blank_reason(**over) is None


@needs_node
def test_report_is_silent_standalone_and_never_throws():
    src = (
        "const LL_EVENT='ll-frame-event';\n" + js_function("llReport") + """
const sent=[];
// Standalone: the page is its own parent.
globalThis.window={}; window.parent=window; window.postMessage=m=>sent.push(m);
llReport('blank','x',{a:1});
// Hosted: posts once, small.
const parent={postMessage:(m,o)=>sent.push([m,o])}; globalThis.window={parent};
llReport('save_blocked','Save refused',{pageRev:'abc'});
// A detail that is too big, and one that can't be serialised.
const big={s:'x'.repeat(5000)}; llReport('error','big',big);
const loop={}; loop.self=loop; llReport('error','loop',loop);
// A parent that throws.
globalThis.window={parent:{postMessage(){ throw new Error('nope'); }}}; llReport('error','x',{});
console.log(JSON.stringify(sent));
""")
    sent = json.loads(run_js(src))
    assert len(sent) == 3
    (m, origin), (big, _), (loop, _) = sent
    assert m == {"type": "ll-frame-event", "kind": "save_blocked", "message": "Save refused", "detail": {"pageRev": "abc"}}
    assert origin == "*"
    assert big["detail"] == {"trimmed": True}
    assert loop["detail"] == {}


@pytest.mark.parametrize("fn,kind", [
    ("showPageOutdated", "save_blocked"),
    ("syncBlockedBy", "save_blocked"),
    ("putShared", "save_blocked"),
    ("showMergedBanner", "save_conflict"),
])
def test_every_blocked_save_reports(fn, kind):
    assert f"llReport('{kind}'" in js_function(fn)


def test_put_shared_reports_both_give_up_and_failure():
    src = js_function("putShared")
    assert "the schedule kept changing" in src and "'Save failed: '" in src


def test_device_copy_drop_is_reported_on_the_next_load():
    i = TEMPLATE.index("sessionStorage.removeItem(DEVICE_COPY_DROPPED);")
    assert "llReport('error', 'The copy of the schedule on this device could not be opened" in TEMPLATE[i:i + 400]


def test_health_checks_run_after_start_up():
    assert "setTimeout(()=>llCheckHealth('10s'), 10000);" in TEMPLATE
    assert "setTimeout(()=>llCheckHealth('30s'), 30000);" in TEMPLATE


def test_reports_carry_no_client_details():
    """Counts and reasons only: no names, addresses or notes go to the log."""
    block = TEMPLATE[TEMPLATE.index("// ---------- telling the app's error log"):TEMPLATE.index("// ---------- which season this page IS")]
    calls = re.findall(r"llReport\([^;]*\);", TEMPLATE)
    assert len(calls) >= 7
    for call in calls:
        # (`e.name` is an error's type, like "TypeError".)
        assert not re.search(r"(?<!\be)\.(name|street|notes|phone|email)\b", call), call
    assert ".name" not in js_function("llScreenFacts")
    assert "innerText||'').trim().length" in block   # length only, never the text
