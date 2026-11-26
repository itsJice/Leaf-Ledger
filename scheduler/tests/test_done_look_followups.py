"""Follow-ups to the Install Schedule's done look (PRs #166 and #170).

* A fetch that started before a save never puts the old times back, and a
  forced fetch while one is in flight runs again after it.
* Logins without Install Times (viewer iPad, production, crew) ask once at
  most, and never see "No times entered yet".
* Times saved before a stop moved to another crew-day show there, labelled
  "saved under Crew N" (the server's savedUnder).
* Training-day stops never offer "Enter times".
* The label says "Install Times · entered by Claude".
* "Has this day happened" uses Central time.
These run the template's own functions in node with small stubs.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

ROLES = re.search(r"^const ACTUALS_ROLES=.*$", TEMPLATE, re.M).group(0)
FNS = ["peekEsc", "attrEsc", "actualsMap", "actualsAllowed", "loadActuals", "actualFor", "dayHasHappened",
       "centralTodayISO", "timesToday", "timesShown", "actualMinutes", "fmtSpan", "onSiteText", "canEditActuals",
       "timesByText", "crewSizeText", "timesStaffCount", "peekTimesHTML"]
STUBS = ROLES + """
  const IC={clock:'@', alert:'!'};
  let AUTH='t', READONLY=false, VIEWONLY=false, TVMODE=false, ME_ROLE='staff';
  const ALERT_EDIT_ROLES=new Set(['staff','admin','super_admin']);
  let ACTUALS=null, actualsAt=0, actualsBusy=null, actualsNext=null, actualsGen=0, actualsDenied=false,
      actualsToday='', actualsReady=false, actualsOffice=false, pkTimesEdit=false, pkTimesMsg='';
  const todayISO=()=>'2099-01-01';          // the device's own clock: never used for "today"
  const isDallasNight=d=>d.night===true;
  let pkShortDraft=null;
  const staffing={}, shiftOfDay=()=>null;
  // authFetch: each call waits until the test answers it.
  const calls=[];
  function authFetch(url){ return new Promise(res=>calls.push({url, answer:(status, body)=>res(
    {status, ok:status>=200 && status<300, json:()=>Promise.resolve(body)})})); }
  const tick=()=>new Promise(r=>setTimeout(r, 0));
  const DAY='2026-11-16|Crew 1|0';
  const act=(id, arrive, depart, extra)=>({id, row:10, dayId:DAY, dayIds:[DAY], arrive, depart,
    arriveAt:'2026-11-16T15:00:00Z', departAt:depart?'2026-11-16T17:00:00Z':null, enteredBy:'o@x', ...(extra||{})});
"""


def run(body):
    src = "\n".join(js_function(n) for n in FNS) + "\n" + STUBS + "\n(async()=>{\n" + body + "\n})();"
    return json.loads(run_js(src))


@needs_node
def test_a_fetch_begun_before_a_save_never_puts_the_old_times_back():
    out = run("""
      const p1=loadActuals();                       // in flight with the old times
      // The card saves 9:00 to 11:00 (wirePeekTimes' success path):
      actualsGen++; ACTUALS=actualsMap([act(2, '9:00 AM', '11:00 AM')]);
      const p2=loadActuals(true);                   // the save's forced refresh
      calls[0].answer(200, {actuals:[act(1, '8:00 AM', '')], today:'2026-11-17', office:true});
      const r1=await p1; await tick();
      const afterStale=actualFor(10, DAY).arrive;
      const started=calls.length;                   // the forced one starts only now
      calls[1].answer(200, {actuals:[act(2, '9:00 AM', '11:00 AM')], today:'2026-11-17', office:true});
      const r2=await p2;
      console.log(JSON.stringify({r1, afterStale, started, r2, now:actualFor(10, DAY).arrive, n:calls.length}));
    """)
    assert out["r1"] is False and out["afterStale"] == "9:00 AM"
    assert out["started"] == 2 and out["r2"] is True and out["now"] == "9:00 AM" and out["n"] == 2


@needs_node
def test_forced_fetches_while_busy_share_one_fetch_after_it():
    out = run("""
      const p0=loadActuals(); const a=loadActuals(true), b=loadActuals(true), c=loadActuals();
      const same=(a===b), joined=(c===p0);
      calls[0].answer(200, {actuals:[]}); await p0; await tick();
      calls[1].answer(200, {actuals:[act(3, '7:00 AM', '8:00 AM')]});
      const [ra, rb]=await Promise.all([a, b]);
      console.log(JSON.stringify({same, joined, n:calls.length, ra, rb}));
    """)
    assert out == {"same": True, "joined": True, "n": 2, "ra": True, "rb": True}


@needs_node
def test_a_403_is_remembered_and_lower_roles_never_ask():
    out = run("""
      ME_ROLE='';                                   // role not known yet: asks once
      const p=loadActuals(); calls[0].answer(403, {detail:'no'}); const r=await p;
      const again=await loadActuals(true); const n403=calls.length;
      const card=peekTimesHTML(10, {id:DAY, date:'2026-11-16'});
      actualsDenied=false;
      const asked={};
      for(const role of ['viewer','production','crew','lead','staff','admin','super_admin']){
        ME_ROLE=role; const before=calls.length; loadActuals(true); asked[role]=calls.length>before;
        if(calls.length>before){ calls[calls.length-1].answer(200, {actuals:[]}); await tick(); await tick(); }
      }
      console.log(JSON.stringify({r, again, n403, card, denied:actualsDenied, asked}));
    """)
    assert out["r"] is False and out["again"] is False and out["n403"] == 1
    assert out["card"] == ""                         # never "No times entered yet"
    assert out["asked"] == {"viewer": False, "production": False, "crew": False,
                            "lead": True, "staff": True, "admin": True, "super_admin": True}


@needs_node
def test_an_error_waits_a_minute_before_asking_again():
    out = run("""
      const p=loadActuals(); calls[0].answer(500, {}); await p;
      await loadActuals(); await loadActuals();
      console.log(JSON.stringify({n:calls.length, denied:actualsDenied}));
    """)
    assert out == {"n": 1, "denied": False}


@needs_node
def test_labels_moved_times_and_training_days():
    out = run("""
      actualsReady=true; actualsToday='2026-11-17';
      ACTUALS=actualsMap([act(4, '9:00 AM', '11:00 AM', {source:'claude', savedUnder:'Crew 2'})]);
      const d={id:DAY, date:'2026-11-16'};
      const moved=peekTimesHTML(10, d);
      const train=peekTimesHTML(10, {...d, training:true});
      ACTUALS=new Map(); const none=peekTimesHTML(10, d);
      console.log(JSON.stringify({moved, train, none,
        office:timesByText({source:'office'}), claude:timesByText({source:'claude'}), empty:timesByText(null)}));
    """)
    assert "Install Times · entered by Claude · saved under Crew 2" in out["moved"]
    assert "Fix times" in out["moved"]
    assert out["train"] == ""
    assert "Enter times" in out["none"]
    assert (out["office"], out["claude"], out["empty"]) == ("Install Times", "Install Times · entered by Claude", "")
    for v in out.values():
        assert "—" not in v and "from the stop note" not in v


@needs_node
def test_day_has_happened_falls_back_to_central_time():
    out = run("""
      // 11:30 PM Monday in Central is already Tuesday in UTC.
      const late=new Date('2026-11-17T05:30:00Z');
      const RealDate=Date;
      global.Date=class extends RealDate{ constructor(...a){ super(...(a.length?a:[late])); } static now(){ return late.getTime(); } };
      const mon=dayHasHappened({date:'2026-11-16'}), tue=dayHasHappened({date:'2026-11-17'});
      actualsToday='2026-11-17'; const server=dayHasHappened({date:'2026-11-17'});
      global.Date=RealDate;
      console.log(JSON.stringify({mon, tue, server}));
    """)
    assert out == {"mon": True, "tue": False, "server": True}


def test_the_save_drops_stale_fetches_and_repaints_partner_crews():
    fn = js_function("wirePeekTimes")
    ok = fn.index("if(r && r.ok && j && j.actual){")
    assert fn.index("actualsGen++;", ok) < fn.index("ACTUALS.set(", ok)
    assert "loadActuals(true).then(ch=>{ if(ch) render(); });" in fn
    assert "if(gen!==actualsGen) return false;" in js_function("loadActuals")
    assert "if(r.status===403) actualsDenied=true;" in js_function("loadActuals")
    assert "timesShown()" in js_function("peekTimesHTML") and "d.training" in js_function("peekTimesHTML")
    assert "timesToday()" in js_function("dayHasHappened")
