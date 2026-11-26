"""A save that never reached the server heals itself (11/25: "Not saved to
the server · 363 changes" after PUT /api/install-schedule/state failed with
"Failed to fetch" and one PUT hung 236 s).

- the PUT gives up after 30 s (AbortController), so a hung save can't sit
- network errors, timeouts, 5xx, 408 and 429 retry after 5 s, 15 s, 30 s,
  then every 60 s; a 4xx the server meant does not
- coming back online, showing the tab, and clicking the red status ("Retry
  now") retry at once
- every retry is a step in the app's trail; the 409 merge is unchanged
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


def node(src):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(src)
    try:
        out = subprocess.run([NODE, f.name], capture_output=True, text=True, check=True)
        return json.loads(out.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(f.name)


@needs_node
def test_backoff_is_5_15_30_then_every_minute():
    src = "\n".join([js_line("const SAVE_RETRY_DELAYS"), js_line("const SAVE_RETRY_EVERY"),
                     js_function("saveRetryDelay"),
                     "console.log(JSON.stringify([0,1,2,3,4,10].map(saveRetryDelay)));"])
    assert node(src) == [5000, 15000, 30000, 60000, 60000, 60000]


@needs_node
def test_only_server_away_statuses_retry():
    src = "\n".join([js_function("saveRetryable"),
                     "console.log(JSON.stringify([0,408,429,500,502,503,504,400,401,403,404,409,422].map(saveRetryable)));"])
    assert node(src) == [True, True, True, True, True, True, True, False, False, False, False, False, False]


@needs_node
def test_a_failed_save_schedules_retries_and_a_success_stops_them():
    """Runs scheduleSaveRetry / runSaveRetry / saveRetryDone with fake
    timers and a fake save that fails twice, then lands."""
    src = "\n".join([
        "let AUTH='t', READONLY=false, syncBlocked=false, DRAFT=false, lastPushOk=false, pushWaiting=null;",
        "const steps=[], waits=[]; let timers=[];",
        "function llStep(a,l){ steps.push(l); }",
        "function syncToolbar(){}",
        "global.setTimeout=(fn,ms)=>{ waits.push(ms); timers.push(fn); return timers.length; };",
        "global.clearTimeout=()=>{};",
        "let calls=0;",
        "function pushSharedNow(){ calls++; if(calls<3){ lastPushOk=false; saveRetryTimer=null; scheduleSaveRetry('Failed to fetch'); return Promise.resolve(false);} lastPushOk=true; saveRetryDone(); return Promise.resolve(true); }",
        js_line("const SAVE_RETRY_DELAYS"), js_line("const SAVE_RETRY_EVERY"),
        "let saveRetryN = 0, saveRetryTimer = null, saveRetrying = false;",
        *(js_function(n) for n in ("saveRetryDelay", "scheduleSaveRetry", "runSaveRetry", "saveRetryDone")),
        "(async()=>{",
        "  scheduleSaveRetry('Failed to fetch');",
        "  for(let i=0;i<3;i++){ const fn=timers.shift(); if(fn){ fn(); await new Promise(r=>setImmediate(r)); } }",
        "  console.log(JSON.stringify({waits, steps, calls, n:saveRetryN, ok:lastPushOk}));",
        "})();",
    ])
    r = node(src)
    assert r["waits"][:3] == [5000, 15000, 30000]
    assert r["calls"] == 3 and r["ok"] is True and r["n"] == 0
    assert r["steps"][0] == "Save retry 1 in 5s (Failed to fetch)"
    assert r["steps"][-1] == "Saved after 3 retries"


def test_put_has_a_30_second_timeout():
    put = js_function("putShared")
    assert "AbortController" in put and "SAVE_TIMEOUT_MS" in put and "signal:ctl.signal" in put
    assert "const SAVE_TIMEOUT_MS=30000;" in TEMPLATE


def test_network_errors_and_5xx_schedule_a_retry_409_still_merges():
    put = js_function("putShared")
    assert "scheduleSaveRetry(why)" in put
    assert "saveRetryable(r.status)" in put
    assert "r.status===409" in put and "rebaseOnto(j" in put


def test_online_visibility_and_click_retry_now():
    assert "window.addEventListener('online', ()=>{ runSaveRetry('back online'); });" in TEMPLATE
    assert "document.visibilityState==='visible') runSaveRetry('tab shown')" in TEMPLATE
    tb = js_function("syncToolbar")
    assert "Retry now" in tb and "sv.classList.toggle('retry', retry)" in tb
    assert "runSaveRetry('Retry now')" in TEMPLATE
    assert "will retry with your next change" not in tb


def test_trail_steps_are_allowed_by_the_app():
    watch = open(os.path.join(HERE, "..", "frontend", "src", "utils", "scheduleFrameWatch.ts"), encoding="utf-8").read()
    assert '"save"' in watch[watch.index("ACTION_KINDS"):watch.index("ACTION_KINDS") + 300]
    assert "type:'ll-frame-step'" in js_function("llStep")
