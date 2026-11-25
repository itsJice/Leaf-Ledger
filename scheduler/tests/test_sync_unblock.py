"""Comments #39 (11/16/2026): a tab locked for good on a duplicate added client.

A staff member's browser kept its own copy of the schedule (localStorage)
holding a client it had added itself ("Laborde, Christine") at a row number
the server had since used for a different client, and the same client was
already on the server at another row. syncBlockedBy stopped every save and
asked for a reload, and the reload restored the same copy: a permanent lock.
Now settleLocalAdds folds a duplicate into the server's row, moves a really
different client to a fresh row, and only what is left (nothing, normally)
still blocks, with a "Use the live schedule" button. A device copy that
breaks start-up is put aside and the live schedule loads on a plain reload.
All names here are FAKE.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_stale_tab_merge import CONSTS

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

LIB = CONSTS + "\nconst TEXT_LOG_MAX=5;\n" + "\n".join(js_function(n) for n in (
    "sharedDocOf", "stableJSON", "sameNewClient", "mergeShared", "normName", "sameLocalClient",
    "collidingNewClients", "remapLocalRows", "settleLocalAdds", "syncBlockedBy")) + """
const ROW_MAP_KEYS=['placement','stopPin','lastScheduledFrom','loadStops','hoursOverride'];
const ROW_SET_KEYS=['confirmed','notInstalling','hold'];
const clone=x=>JSON.parse(JSON.stringify(x));
let C={}, N={}, nextSyntheticRow=900001, syncBlocked=false, clientDirectory=null, sharedBase=null;
const banners=[];
function showSyncBanner(o){ banners.push(o); }
// Server: Smith at 900037 (the client), Lee at 900038 (someone else's).
const SMITH={row:900037, name:'Smith, Jo', street:'5 Elm St', visitType:'Standard', hours:2};
const LEE={row:900038, name:'Lee, Kim', street:'9 Oak Ln', visitType:'Reinstall', hours:3};
const OLD={row:900036, name:'Old, Al', street:'1 First St', visitType:'Standard', hours:1};
const BASE={placement:{'1':['2026-11-13|Crew 1|0'], '900036':['2026-11-14|Crew 1|0']},
            approved:[], confirmed:[], moves:[], comments:{}, newClients:[OLD]};
const THEIRS={...clone(BASE), placement:{...BASE.placement, '900037':['2026-11-20|Crew 1|0']},
              newClients:[OLD, SMITH, LEE], confirmed:[900037]};
function board(mine){                     // what bootstrap restores from the device copy
  C={}; N={};
  (mine.newClients||[]).forEach(d=>{ C[d.row]={...d, synthetic:true}; N[d.row]=d.row-899000; });
  C[1]={row:1, name:'Sheet Client'};
  nextSyntheticRow=Math.max(900001, ...Object.keys(C).map(r=>+r+1));
}
"""


def run(body):
    return json.loads(run_js(LIB + "\n" + body))


def test_duplicate_at_a_colliding_row_merges_into_the_server_row():
    out = run("""
      // This computer added Smith itself at 900038 (the server's Lee) and placed them.
      const mine={...clone(BASE), newClients:[OLD, {...SMITH, row:900038}],
        placement:{...BASE.placement, '900038':['2026-11-19|Crew 2|0']},
        comments:{'900038':[{at:5, text:'gate code'}]}, confirmed:[900038],
        moves:[{row:900038, name:'Smith, Jo', from:null, to:'2026-11-19|Crew 2|0'}]};
      board(mine); sharedBase={at:'t0', state:clone(BASE)};
      const j={state:clone(THEIRS), updatedAt:'t1'};
      const s=settleLocalAdds(j, clone(mine), true);
      const blocked=syncBlockedBy(j);
      const r=mergeShared(BASE, s.mine, sharedDocOf(j.state));
      console.log(JSON.stringify({blocked, banners:banners.length, merged:s.merged, renumbered:s.renumbered,
        local900038:!!C[900038], names:r.state.newClients.map(c=>c.row+':'+c.name),
        place:r.state.placement, comments:r.state.comments, hard:r.hard, confirmed:r.state.confirmed,
        moveRows:r.state.moves.map(m=>m.row)}));
    """)
    assert out["blocked"] is False and out["banners"] == 0
    assert out["merged"] == ["Smith, Jo"] and out["renumbered"] == []
    assert out["local900038"] is False            # the server's Lee goes there on applySharedDoc
    assert out["names"] == ["900036:Old, Al", "900037:Smith, Jo", "900038:Lee, Kim"]   # one Smith
    # The server already had Smith's day: the server wins.
    assert out["place"]["900037"] == ["2026-11-20|Crew 1|0"] and "900038" not in out["place"]
    assert out["comments"] == {"900037": [{"at": 5, "text": "gate code"}]}   # nothing lost
    assert out["confirmed"] == [900037] and out["hard"] == []
    assert out["moveRows"] == [900037]


def test_a_different_client_at_a_colliding_row_is_renumbered_and_kept():
    out = run("""
      const ZED={row:900038, name:'Zed, Pat', street:'7 Pine Rd', visitType:'Standard', hours:2};
      const mine={...clone(BASE), newClients:[OLD, ZED],
        placement:{...BASE.placement, '900038':['2026-11-19|Crew 2|0']}, hoursOverride:{}};
      board(mine); sharedBase={at:'t0', state:clone(BASE)};
      const j={state:clone(THEIRS), updatedAt:'t1'};
      const s=settleLocalAdds(j, clone(mine), true);
      const blocked=syncBlockedBy(j);
      const r=mergeShared(BASE, s.mine, sharedDocOf(j.state));
      console.log(JSON.stringify({blocked, renumbered:s.renumbered, next:nextSyntheticRow,
        Crow:Object.keys(C).filter(k=>C[k].name==='Zed, Pat'), node:N[900039],
        names:r.state.newClients.map(c=>c.row+':'+c.name), place:r.state.placement, hard:r.hard}));
    """)
    assert out["blocked"] is False and out["renumbered"] == ["Zed, Pat"]
    assert out["Crow"] == ["900039"] and out["node"] == 1038 and out["next"] == 900040
    assert out["names"] == ["900036:Old, Al", "900037:Smith, Jo", "900038:Lee, Kim", "900039:Zed, Pat"]
    assert out["place"]["900039"] == ["2026-11-19|Crew 2|0"] and "900038" not in out["place"]
    assert out["hard"] == []


def test_two_local_copies_of_one_client_both_fold_in():
    out = run("""
      const mine={...clone(BASE), newClients:[OLD, {...SMITH, row:900038}, {...SMITH, row:900039}],
        placement:{...BASE.placement, '900038':['2026-11-19|Crew 2|0'], '900039':['2026-11-21|Crew 1|0']}};
      board(mine); sharedBase={at:'t0', state:clone(BASE)};
      const th=clone(THEIRS); th.newClients.push({row:900039, name:'Ng, Ty', street:'3 Bay St', visitType:'Standard'});
      const j={state:th, updatedAt:'t1'};
      const s=settleLocalAdds(j, clone(mine), true);
      const blocked=syncBlockedBy(j);
      const r=mergeShared(BASE, s.mine, sharedDocOf(j.state));
      console.log(JSON.stringify({blocked, names:r.state.newClients.map(c=>c.row+':'+c.name).sort(), hard:r.hard}));
    """)
    assert out["blocked"] is False and out["hard"] == []
    assert out["names"] == ["900036:Old, Al", "900037:Smith, Jo", "900038:Lee, Kim", "900039:Ng, Ty"]


def test_without_a_base_colliding_local_rows_are_dropped_not_renumbered():
    out = run("""
      const ZED={row:900038, name:'Zed, Pat', street:'7 Pine Rd', visitType:'Standard'};
      const mine={...clone(BASE), newClients:[OLD, ZED]};
      board(mine); sharedBase=null;
      const j={state:clone(THEIRS)};
      const s=settleLocalAdds(j, clone(mine), false);
      console.log(JSON.stringify({blocked:syncBlockedBy(j), C:Object.keys(C), nc:s.mine.newClients.map(c=>c.row)}));
    """)
    assert out["blocked"] is False and "900038" not in out["C"] and out["nc"] == [900036]


def test_nothing_colliding_changes_nothing():
    out = run("""
      const mine={...clone(BASE), newClients:[OLD]};
      board(mine); sharedBase={at:'t0', state:clone(BASE)};
      const m=clone(mine), s=settleLocalAdds({state:clone(THEIRS)}, m, true);
      console.log(JSON.stringify({same:s.mine===m, C:Object.keys(C).length}));
    """)
    assert out == {"same": True, "C": 2}


def test_whatever_still_blocks_offers_the_live_schedule():
    sub = js_function("syncBlockedBy")
    assert "useLive:true" in sub and "If it keeps coming back, use the live schedule." in sub
    banner = js_function("showSyncBanner")
    assert 'class="sblive">Use the live schedule</button>' in banner
    assert "useLiveSchedule()" in banner


def test_use_the_live_schedule_clears_this_computers_copy_and_reloads():
    out = json.loads(run_js("const LS_KEY='tbdg2026review';\n" + js_function("useLiveSchedule") + """
      const store={tbdg2026review:'{"x":1}', other:'keep'}, asked=[]; let reloads=0;
      global.localStorage={removeItem:k=>{ delete store[k]; }};
      global.window={top:{location:{reload:()=>{ reloads++; }}}};
      global.confirm=m=>{ asked.push(m); return true; };
      const ok=useLiveSchedule();
      global.confirm=m=>false; store.tbdg2026review='y'; const no=useLiveSchedule();
      console.log(JSON.stringify({ok, no, store, asked, reloads}));
    """))
    assert out["ok"] is True and out["no"] is False
    assert out["asked"] == ["Throw away the copy on this computer and load the live schedule?"]
    assert out["store"] == {"other": "keep", "tbdg2026review": "y"} and out["reloads"] == 1


def test_save_and_load_settle_before_they_block():
    pull = js_function("pullSharedNow")
    assert pull.index("settleLocalAdds(j,") < pull.index("syncBlockedBy(j)") < pull.index("rebaseOnto(j, base, mine)")
    put = js_function("putShared")
    assert put.index("settleLocalAdds(j,") < put.index("syncBlockedBy(j)") < put.index("rebaseOnto(j,")


EARLY = TEMPLATE[TEMPLATE.index("const DEVICE_COPY_KEY="):TEMPLATE.index("// ---------- which season this page IS")]


def test_a_broken_device_copy_is_put_aside_and_the_page_reloads_once():
    out = json.loads(run_js("""
      const ls={}, ss={}; let reloads=0; const listeners={};
      const store=o=>({getItem:k=>(k in o?o[k]:null), setItem:(k,v)=>{o[k]=String(v);}, removeItem:k=>{delete o[k];}});
      global.localStorage=new Proxy(store(ls), {ownKeys:()=>Object.keys(ls),
        getOwnPropertyDescriptor:(t,k)=>({enumerable:true, configurable:true, value:ls[k]})});
      global.sessionStorage=store(ss);
      global.console.warn=()=>{};
      global.window={top:{location:{reload:()=>{ reloads++; }}}, addEventListener:(t,f)=>{ listeners[t]=f; }};
      // The start-up health checks (10 s and 30 s) are only noted, never
      // waited for: node would otherwise sit 30 s before exiting.
      const timers=[]; global.setTimeout=(fn, ms)=>{ timers.push(ms); return timers.length; };
      ls['tbdg2026review']='{"broken":';
      """ + EARLY.replace("tbdg__SEASON__review", "tbdg2026review") + """
      // An error thrown while starting up, with a device copy in place:
      let prevented=false;
      listeners.error({error:new TypeError('x is undefined'), preventDefault:()=>{ prevented=true; }});
      const after=Object.keys(ls).sort();
      // Read the set-aside copy now: the second drop below replaces it (a new
      // key unless it lands in the same millisecond), which made this flaky.
      const stash=ls[after[0]];
      // Broken again within a minute (the copy came back somehow): no second reload.
      ls['tbdg2026review']='{"again":1}'; deviceCopyRecovering=false;
      const again=recoverFromDeviceCopy(new Error('y'), 'restore');
      const kept=Object.keys(ls).filter(k=>k.includes('-broken-'));
      console.log(JSON.stringify({after, reloads, prevented, again, stash, timers,
        kept:kept.length, keptValue:ls[kept[0]], live:ls['tbdg2026review']===undefined,
        flag:!!ss['tbdg-device-copy-dropped']}));
    """))
    assert out["after"][0].startswith("tbdg2026review-broken-") and len(out["after"]) == 1
    assert out["stash"] == '{"broken":'
    assert out["reloads"] == 1 and out["prevented"] is True and out["again"] is False
    assert out["flag"] is True
    # The second broken copy was put aside too, replacing the first (only the
    # newest is kept), and the live key is gone.
    assert out["kept"] == 1 and out["keptValue"] == '{"again":1}' and out["live"] is True
    assert sorted(out["timers"]) == [10000, 30000]


def test_start_up_recovery_is_wired_in():
    assert "}catch(e){ recoverFromDeviceCopy(e, 'restore'); }" in TEMPLATE
    assert "if(loaded) recoverFromDeviceCopy(e, 'merge');" in js_function("pullSharedNow")
    tail = TEMPLATE[TEMPLATE.rindex("\nreportView();"):]
    assert tail.index("pageBooted = true;") < tail.index("couldn\\'t be opened, so the live schedule is shown.")
    assert "const LS_KEY = DEVICE_COPY_KEY;" in TEMPLATE
    # The add-a-client dialog won't add on a tab that can't save.
    assert "This tab can\\'t save right now." in TEMPLATE


def test_no_em_dashes_in_the_new_words():
    for fn in ("syncBlockedBy", "useLiveSchedule", "settleLocalAdds", "dropBrokenDeviceCopy"):
        assert "—" not in js_function(fn)


def test_a_removed_added_client_takes_its_placement_with_it():
    out = run("""
      const base={...clone(BASE), newClients:[OLD], manualOrder:{'2026-11-14|Crew 1|0':[900036, 1]},
                  stopPin:{'900036':'first'}};
      const mine={...clone(base), newClients:[]};   // this tab removed Old
      const r=mergeShared(base, mine, clone(base));
      console.log(JSON.stringify({nc:r.state.newClients, place:r.state.placement, mo:r.state.manualOrder, pin:r.state.stopPin}));
    """)
    assert out["nc"] == [] and "900036" not in out["place"]
    assert out["mo"] == {"2026-11-14|Crew 1|0": [1]} and out["pin"] == {}


def test_a_placement_row_with_no_client_is_left_off_the_board():
    # The blank board's throw: a device copy's placement held a row with no
    # client (no map point), and routing it threw in the first render.
    fn = js_function("applyPlacement")
    assert "if(!C[+r] || N[+r]===undefined || !Array.isArray(ids)){ missing++; placementGhosts.push(String(r)); return; }" in fn
    assert "const c=C[r]; if(!c) return 0;" in js_function("effH")
    assert "const row=D[a]; return (row && row[b])||0;" in js_function("leg")
    assert "try{ render(); }catch(e){ if(!recoverFromDeviceCopy(e, 'first draw')) throw e; }" in TEMPLATE


def test_a_ghost_row_from_a_broken_copy_is_not_saved_as_a_removal():
    # A device copy with the client's placement but not the client: the row is
    # left off the board, and the save must not unschedule it on the server.
    out = json.loads(run_js(js_function("keepGhostRows") + """
      const base={placement:{'900037':['2026-11-20|Crew 1|0'], '1':['d1']}, newClients:[{row:900037, name:'Smith, Jo'}]};
      const mine={placement:{'1':['d2']}, newClients:[]};
      const out=keepGhostRows(mine, base, ['900037', '900099']);
      console.log(JSON.stringify(out));
    """))
    assert out == {"placement": {"1": ["d2"], "900037": ["2026-11-20|Crew 1|0"]},
                   "newClients": [{"row": 900037, "name": "Smith, Jo"}]}
    pull = js_function("pullSharedNow")
    assert pull.index("keepGhostRows(mine, base.state, deviceGhostRows)") < pull.index("settleLocalAdds(j,")
    assert "deviceGhostRows = placementGhosts.slice();" in TEMPLATE
