"""Install notes on the morning of, and the stop card's save after an hour.

10/19: a super_admin typed "Install requires (8) longer extension cords..."
into a stop card's Install notes 2026 and Save said "Couldn't save that
change". Nothing reached the database: the page held the one token the app
posted in when it loaded, Supabase tokens last an hour, and every call after
that was a 401 the editor reported as a generic failure. These pin the fix
(authFetch asks the app for a fresh token and retries once; a refresh token
doesn't reload the board; the message names what failed) and where the
season card's install notes now show: the stop row's chip, the date
heading's count, the card's quick reference and the crew sheet's pack list.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


ASYNC = {"authFetch"}


def run(names, body, prelude=""):
    src = prelude + "\n" + "\n".join(("async " if n in ASYNC else "") + js_function(n) for n in names) + "\n" + body
    return json.loads(run_js(src))


# ─── the token ───────────────────────────────────────────────────────────────

TOKEN_STUBS = """
let AUTH='Bearer old';
const tokenWaiters=[]; let tokenAsk=null; const posted=[]; const calls=[];
const window={parent:{postMessage:(m)=>{ posted.push(m.type);
  // the app answers with a refreshed token, as InstallSchedule.tsx does
  setTimeout(()=>{ AUTH='Bearer new'; tokenWaiters.splice(0).forEach(fn=>fn(AUTH)); }, 5); }}};
"""


@needs_node
def test_a_401_gets_a_fresh_token_and_one_retry():
    out = run(["requestFreshToken", "authFetch"], """
      async function fetch(url, init){
        calls.push(init.headers.Authorization);
        return {status: init.headers.Authorization==='Bearer new' ? 200 : 401, ok: init.headers.Authorization==='Bearer new'};
      }
      (async()=>{
        const r=await authFetch('/api/clients/update/195', {method:'PUT', headers:{'Content-Type':'application/json'}, body:'{}'});
        console.log(JSON.stringify({status:r.status, calls, posted}));
      })();
    """, TOKEN_STUBS)
    assert out == {"status": 200, "calls": ["Bearer old", "Bearer new"], "posted": ["tbdg-token-request"]}


@needs_node
def test_a_second_401_is_returned_not_looped():
    out = run(["requestFreshToken", "authFetch"], """
      async function fetch(url, init){ calls.push(init.headers.Authorization); return {status:401, ok:false}; }
      (async()=>{
        const r=await authFetch('/api/x', {});
        console.log(JSON.stringify({status:r.status, n:calls.length}));
      })();
    """, TOKEN_STUBS)
    assert out == {"status": 401, "n": 2}


def test_a_refreshed_token_is_swapped_in_without_reloading_the_board():
    i = TEMPLATE.index("if(e.data && e.data.type==='tbdg-auth' && typeof e.data.token==='string'){")
    handler = TEMPLATE[i:i + 900]
    assert "const first = !AUTH;" in handler
    assert handler.index("if(!first) return;") < handler.index("pullShared();")
    assert "tokenWaiters.splice(0).forEach(fn=>fn(AUTH));" in handler


def test_every_api_call_goes_through_authfetch():
    import re
    lo = TEMPLATE.index("/** fetch() with the current token")
    hi = TEMPLATE.index(js_function("authFetch")) + len(js_function("authFetch"))
    for m in re.finditer(r"(?<![A-Za-z.])fetch\(", TEMPLATE):
        if lo <= m.start() < hi:
            continue
        assert "Authorization:AUTH" not in TEMPLATE[m.start():m.start() + 300], TEMPLATE[m.start():m.start() + 120]
    assert TEMPLATE.count("authFetch(") >= 15


def test_the_app_answers_token_requests_and_refreshes():
    host = open(__file__.replace("scheduler/tests/test_install_notes_and_token.py",
                                 "frontend/src/pages/InstallSchedule.tsx")).read()
    assert 'type === "tbdg-token-request"' in host
    assert "auth.onTokenChange" in host


# ─── the save's message ──────────────────────────────────────────────────────


@needs_node
def test_save_errors_say_what_failed():
    out = run(["cardSaveErrorMessage"], """
      const duplicateNameMessage=()=>'dup';
      console.log(JSON.stringify({
        expired: cardSaveErrorMessage('client', 401, 'Your session has expired', null, '2026'),
        season: cardSaveErrorMessage('season', 500, '', null, '2026'),
        bad: cardSaveErrorMessage('season', 400, "unknown season field 'x'", null, '2026'),
        offline: cardSaveErrorMessage('client', 0, '', null, '2026'),
        dup: cardSaveErrorMessage('client', 409, '', {first_name:'A'}, '2026'),
        gone: cardSaveErrorMessage('client', 404, 'No client with that id', null, '2026'),
      }));
    """)
    assert out["expired"].startswith("Nothing was saved. Your sign-in has expired. Reload the page")
    assert out["season"].startswith("The client card saved, but the 2026 install notes didn't.")
    assert "error 500" in out["season"]
    assert "(unknown season field 'x')" in out["bad"]
    assert "Couldn't reach the server" in out["offline"] and "still here" in out["offline"]
    assert out["dup"] == "dup"
    assert "merged" in out["gone"]
    assert all("Couldn't save that change" not in v for v in out.values())


def test_a_redraw_hiccup_after_saving_never_reads_as_a_failed_save():
    save = TEMPLATE[TEMPLATE.index("if(saveBtn) saveBtn.onclick=async()=>{"):]
    save = save[:save.index("\n  };\n}")]
    # The alert lives only in the catch around the two calls; the redraw has
    # its own try that logs.
    # name-parts problem, a bad Drive link (both before anything is sent),
    # and the save error
    assert save.count("alert(") == 3
    assert "console.error('card redraw after save', e)" in save
    assert "Saved. ${yr} install notes updated." in save


# ─── where install notes show ────────────────────────────────────────────────

NOTE_STUBS = """
const IC={clip:'<i/>'};
function peekEsc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function attrEsc(s){ return peekEsc(s).replace(/"/g,'&quot;'); }
const NOTES={1:'Bring (8) longer extension cords. Pack in kit', 3:'Gate code 1234'};
const installNoteFor=r=>NOTES[r] ? {text:NOTES[r], season:'2026', live:true} : null;
"""


@needs_node
def test_row_chip_count_and_card_quick_reference():
    out = run(["installNoteChipHTML", "installNoteStops", "installNoteCountHTML", "peekInstallNoteHTML",
               "adviceLineHTML"], """
      const days=[{id:'a', stops:[1,2]}, {id:'b', stops:[3]}];
      console.log(JSON.stringify({
        chip1: installNoteChipHTML(1), chip2: installNoteChipHTML(2),
        stops: installNoteStops(days).map(x=>[x.row, x.day.id]),
        count: installNoteCountHTML(days), one: installNoteCountHTML([days[1]]), none: installNoteCountHTML([{stops:[2]}]),
        card: peekInstallNoteHTML(1), cardNone: peekInstallNoteHTML(2), line: adviceLineHTML(1),
      }));
    """, NOTE_STUBS)
    assert 'class="badge instnote"' in out["chip1"] and ">notes</span>" in out["chip1"]
    assert "extension cords" in out["chip1"] and out["chip2"] == ""
    assert out["stops"] == [[1, "a"], [3, "b"]]
    assert "2 stops have install notes" in out["count"] and "1 stop has install notes" in out["one"]
    assert out["none"] == ""
    assert "Install notes 2026" in out["card"] and "Bring (8) longer extension cords" in out["card"]
    assert out["cardNone"] == ""
    assert "<b>Install notes:</b>" in out["line"]


def test_card_shows_install_notes_open_in_this_job_not_in_a_fold():
    body = TEMPLATE[TEMPLATE.index("function openStopPeek(row,dayId){"):]
    body = body[:body.index("wireContactBlock(row);")]
    assert body.index('id="pkinstbox"') < body.index('class="pkfolds"')
    assert "peekInstallNoteHTML(row)" in js_function("refreshPeekLive")
    assert "installNoteFor" not in js_function("peekNotesHTML")


def test_rows_and_headings_carry_the_chip_and_count():
    assert TEMPLATE.count("${installNoteChipHTML(") >= 3      # day rows, not installing, on hold
    assert "installNoteCountHTML(onThisDate)" in TEMPLATE
    assert "installNoteCountHTML(ds)" in TEMPLATE


def test_crew_sheet_has_a_pack_list_and_labelled_lines():
    m = js_function("manifestHTML")
    assert "Pack list for this crew" in m
    assert "<b>Bring / install notes:</b>" in m
    assert "<b>Production &amp; repair:</b>" in m
    pm = TEMPLATE[TEMPLATE.index("function printManifests("):]
    assert ".pack{" in pm[:pm.index("</style>")]
    # one source: the season card's install notes (installNoteFor)
    assert "installNoteFor(r)" in m


def test_installnotefor_is_the_season_card_field():
    fn = js_function("installNoteFor")
    assert "a.kind==='christmas_install' && String(a.season)===yr" in fn
    assert "en.detail.notes" in fn
    # the editor writes that same key
    assert "notes:String(f.inst_notes||'').trim()" in js_function("seasonNotesChanges")


def test_the_app_can_open_a_date():
    assert "e.data.type!=='tbdg-date'" in TEMPLATE
    i = TEMPLATE.index("e.data.type!=='tbdg-date'")
    assert "phoneGo(dt);" in TEMPLATE[i:i + 500]
