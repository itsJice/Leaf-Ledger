"""Added stops on the Install Schedule: delete, change address, bring back,
and the Today button (Comments #49, #55, #57, 11/2026).

#49 (Nicole): "Can't get this fake Michol Ecklund callback to delete". There
was no way to delete an added stop or a return trip; Not installing only
parked it. Now the stop card has "Delete stop" for added stops (never a
spreadsheet client), and the delete is a durable list in shared state
(deletedStops) that every merge and restore honors, so a tab opened before
the delete can't save the stop back.

#57 (Nicole): she added The Green Room, needed to fix its address, marked it
Not installing and couldn't get it back with the right address. "+ New
client" offered a return trip for the not-installing stop (a second stop at
the OLD address), "Find a date" took it off the list before a date was
picked, and the Move dialog started on today, Crew 1. Now an added stop's
address is changed on its stop card, "+ New client" offers to bring the
not-installing stop back (with the new address), it stays on Not installing
until a date is picked, and the Move dialog starts on a sensible date.

#55 (Cynthia): "a button that says go to 'today'". The Days view toolbar has
Today: today when a crew works it, else the next date with work.

These run the template's own functions in node with small stubs, plus
source pins for the wiring. All names and rows are FAKE.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_stale_tab_merge import MERGE, SAVE_LOOP, SCENARIO, const_line, run as run_merge

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def run(body, names=(), prelude=""):
    src = prelude + "\n" + "\n".join(js_function(n) for n in names) + "\n" + body
    return json.loads(run_js(src))


# ─── #49: delete an added stop, and it stays deleted ──────────────────────────

STOP = {"row": 900038, "name": "Fake Callback, Test", "street": "1 Test St", "lat": 29.7, "lon": -95.4,
        "hours": 1, "visitType": "Callback"}
OTHER = {"row": 900040, "name": "Kept Stop, Test", "street": "2 Test St", "lat": 29.8, "lon": -95.5, "hours": 2}


def merge_case(body):
    return run_merge(f"const STOP={json.dumps(STOP)}, OTHER={json.dumps(OTHER)};\n"
                     "const clone=x=>JSON.parse(JSON.stringify(x));\n" + body)


@needs_node
def test_a_stale_tab_that_did_not_touch_the_stop_does_not_bring_it_back():
    out = merge_case("""
      const BASE={newClients:[clone(STOP), clone(OTHER)], placement:{'900038':['2026-11-18|Crew 1|0'], '900040':['2026-11-19|Crew 1|0']},
                  notInstalling:[], deletedStops:[]};
      // Another device deleted the stop.
      const THEIRS={newClients:[clone(OTHER)], placement:{'900040':['2026-11-19|Crew 1|0']}, notInstalling:[], deletedStops:[900038]};
      // This (stale) tab still holds it -- unchanged -- and moved OTHER.
      const MINE=clone(BASE); MINE.placement['900040']=['2026-11-20|Crew 2|0'];
      const r=mergeShared(BASE, MINE, THEIRS);
      console.log(JSON.stringify({rows:r.state.newClients.map(c=>c.row), placement:r.state.placement,
                                  deleted:r.state.deletedStops, hard:r.hard}));
    """)
    assert out["rows"] == [900040]
    assert out["placement"] == {"900040": ["2026-11-20|Crew 2|0"]}
    assert out["deleted"] == [900038]
    assert out["hard"] == []


@needs_node
def test_a_stale_tab_that_edited_the_stop_still_cannot_bring_it_back():
    out = merge_case("""
      const BASE={newClients:[clone(STOP)], placement:{'900038':['2026-11-18|Crew 1|0']},
                  notInstalling:[900038], hold:[900038], hoursOverride:{}, stopPin:{'900038':'first'}, deletedStops:[]};
      const THEIRS={newClients:[], placement:{}, notInstalling:[], hold:[], hoursOverride:{}, stopPin:{}, deletedStops:[900038]};
      const MINE=clone(BASE); MINE.newClients[0].hours=3; MINE.placement['900038']=['2026-11-21|Crew 1|0'];
      const r=mergeShared(BASE, MINE, THEIRS);
      console.log(JSON.stringify({nc:r.state.newClients, pl:r.state.placement, ni:r.state.notInstalling,
                                  hold:r.state.hold, pin:r.state.stopPin}));
    """)
    assert out == {"nc": [], "pl": {}, "ni": [], "hold": [], "pin": {}}


@needs_node
def test_a_delete_made_here_wins_over_the_servers_copy_and_tombstones_union():
    out = merge_case("""
      const BASE={newClients:[clone(STOP), clone(OTHER)], placement:{'900038':['2026-11-18|Crew 1|0']}, deletedStops:[]};
      // This tab deleted STOP; the server meanwhile deleted OTHER and edited STOP's notes.
      const MINE={newClients:[clone(OTHER)], placement:{}, deletedStops:[900038]};
      const THEIRS={newClients:[{...clone(STOP), notes:'edited elsewhere'}], placement:{'900038':['2026-11-18|Crew 1|0']},
                    deletedStops:[900040]};
      const r=mergeShared(BASE, MINE, THEIRS);
      console.log(JSON.stringify({nc:r.state.newClients.map(c=>c.row), pl:r.state.placement,
                                  del:[...r.state.deletedStops].sort()}));
    """)
    assert out == {"nc": [], "pl": {}, "del": [900038, 900040]}


@needs_node
def test_through_the_real_save_loop_a_stale_tab_does_not_save_the_deleted_stop_back():
    out = run_merge(SCENARIO + SAVE_LOOP + f"const STOP={json.dumps(STOP)};\n" + """
      (async()=>{
        server.doc={...clone(BASE), newClients:[clone(STOP)], placement:{...BASE.placement, '900038':['2026-11-18|Crew 1|0']}};
        load();                                     // the tab opens with the stop
        const gone=clone(server.doc);               // someone deletes it on another device
        gone.newClients=[]; delete gone.placement['900038']; gone.deletedStops=[900038];
        serverWrite(gone, 'nicole');
        DOC.newClients[0].hours=2;                  // the stale tab edits it, then saves
        const ok=await putShared();
        console.log(JSON.stringify({ok, nc:server.doc.newClients, pl:server.doc.placement['900038']||null,
                                    del:server.doc.deletedStops, statuses:server.log.map(x=>x.status)}));
      })();
    """)
    # Refused (stale), merged: its only change was to the deleted stop, so
    # there is nothing left to send and the server copy stands.
    assert out["ok"] is True and out["statuses"] == [409]
    assert out["nc"] == [] and out["pl"] is None and out["del"] == [900038]


RESTORE = """
const C={36:{row:36, name:'Sample, Jane', lat:29.71, lon:-95.41}};
const N={36:3};
let nextSyntheticRow=900001, clientDirectory=null;
let days=[{id:'2026-11-18|Crew 1|0', date:'2026-11-18', stops:[36, 900038]}];
let notInstalling=new Set([900038]), hold=new Set(), confirmed=new Set(), newDates=new Set();
let stopPin={900038:'first'}, lastScheduledFrom={900038:{date:'2026-11-18'}}, hoursOverride={}, comments={}, manualOrder={'2026-11-18|Crew 1|0':[900038, 36]};
const liveRouteCache=new Map([['D,36,900038,D', {}], ['D,36,D', {}]]);
const MATRIX=[];
function extendMatrix(lat, lon, o, i){ MATRIX.push([lat, lon, !!o]); return 100+MATRIX.length; }
function addSyntheticClientSync(d){ C[d.row]={...d, synthetic:true, h26:d.hours}; N[d.row]=1; return d.row; }
function normName(s){ return String(s||'').trim().toLowerCase(); }
function syncSyntheticName(c, n){ c.name=n; }
function applyLiveClientFields(){} function applyCardFactsTo(){} let cardFacts=null;
"""
RESTORE_FNS = ("normDeletedStops", "dropDeletedStops", "applySyntheticAddress", "restoreSyntheticClients")


@needs_node
def test_restore_drops_a_deleted_stop_everywhere_and_never_reuses_its_row():
    out = run("""
      restoreSyntheticClients([], []);
      C[900038]={row:900038, name:'Fake Callback, Test', synthetic:true, lat:29.7, lon:-95.4};
      restoreSyntheticClients([{row:900038, name:'Fake Callback, Test', lat:29.7, lon:-95.4},
                               {row:900041, name:'New One', lat:1, lon:2}], [900038, 900050, 12]);
      console.log(JSON.stringify({rows:Object.keys(C).map(Number), stops:days[0].stops, ni:[...notInstalling],
        pin:stopPin, was:lastScheduledFrom, order:manualOrder, next:nextSyntheticRow,
        norm:[...normDeletedStops([900038, '900039', 12, 'x', null])]}));
    """, RESTORE_FNS, RESTORE)
    assert out["rows"] == [36, 900041]            # deleted stop gone, the other restored
    assert out["stops"] == [36]
    assert out["ni"] == [] and out["pin"] == {} and out["was"] == {}
    assert out["order"] == {"2026-11-18|Crew 1|0": [36]}
    assert out["next"] == 900051                   # past every deleted row
    assert out["norm"] == [900038, 900039]         # only added-stop rows


@needs_node
def test_a_spreadsheet_client_is_never_deleted_or_moved():
    out = run("""
      restoreSyntheticClients([], [36]);
      console.log(JSON.stringify({kept:!!C[36], stops:days[0].stops,
        del:[canDeleteStop(C[36]), canDeleteStop({synthetic:true}), canDeleteStop(null)],
        addr:[canChangeAddress(C[36]), canChangeAddress({synthetic:true})]}));
    """, RESTORE_FNS + ("canDeleteStop", "canChangeAddress"), RESTORE)
    assert out["kept"] is True and out["stops"] == [36, 900038]
    assert out["del"] == [False, True, False]
    assert out["addr"] == [False, True]


def test_delete_wiring():
    fn = js_function("deleteAddedStop")
    assert "Delete this added stop? It comes off the schedule." in fn
    assert "canDeleteStop(c)" in fn and "pushUndo();" in fn and "deletedStops.add(+row);" in fn
    assert "to:'DELETED'" in fn and "persist(); render();" in fn
    assert "'deletedStops'" in const_line("SHARED_SET_KEYS")
    assert "deletedStops:[...deletedStops]" in js_function("snapshot")
    blob = js_function("stateBlob")
    assert "newClients:newClientDefs(), deletedStops:[...deletedStops]" in blob
    restore = js_function("restoreBlob")
    assert "deletedStops = normDeletedStops(s.deletedStops);" in restore
    assert "restoreSyntheticClients(s.newClients, s.deletedStops)" in restore
    assert "restoreSyntheticClients(st.newClients, st.deletedStops);" in js_function("applySharedDoc")
    peek = js_function("openStopPeek")
    assert 'id="pkdelete"' in peek and "canDeleteStop(c) && canEditHours()" in peek
    assert "if(deleteAddedStop(row)) peekdlg.close();" in peek
    assert "if(id==='DELETED') return 'deleted';" in js_function("renderLog")
    # No em dashes in what staff read.
    assert "—" not in fn


# ─── #57: change an added stop's address, bring a not-installing stop back ─────

@needs_node
def test_a_changed_address_is_applied_on_every_copy_with_new_drive_times():
    out = run("""
      C[900038]={row:900038, name:'Fake Club, Test', synthetic:true, street:'1 Old Rd', lat:30.19, lon:-95.55, outRow:[1], inCol:[1]};
      // The shared document says it moved (saved on another device).
      restoreSyntheticClients([{row:900038, name:'Fake Club, Test', street:'9 New Rd', lat:30.16, lon:-95.55, outRow:[5], inCol:[6]}], []);
      const c=C[900038];
      const same=applySyntheticAddress(c, {street:'9 New Rd', lat:30.16, lon:-95.55});
      console.log(JSON.stringify({street:c.street, lat:c.lat, node:N[900038], legs:[c.outRow, c.inCol], geo:c.geo,
        matrix:MATRIX, same, routes:[...liveRouteCache.keys()], edited:!!days[0].edited}));
    """, RESTORE_FNS, RESTORE)
    assert out["street"] == "9 New Rd" and out["lat"] == 30.16
    assert out["node"] == 101 and out["matrix"] == [[30.16, -95.55, True]]
    assert out["legs"] == [[5], [6]] and out["geo"] == "street"
    assert out["same"] is False                       # nothing to redo for the same spot
    assert out["routes"] == ["D,36,D"]                # its day's drawn route is redrawn
    assert out["edited"] is True


@needs_node
def test_new_client_offers_to_bring_back_a_not_installing_stop_not_a_return_trip():
    out = run("""
      const ni=new Set([900074]);
      const can=r=>r!==13;
      console.log(JSON.stringify([ncMatchOffers([900074, 36], ni, can), ncMatchOffers([13, 36], ni, can),
                                  ncMatchOffers([], ni, can)]));
    """, ("ncMatchOffers",))
    assert out[0] == {"back": [900074], "trip": [36]}
    assert out[1] == {"back": [], "trip": [36]}
    assert out[2] == {"back": [], "trip": []}


def test_address_and_bring_back_wiring():
    peek = js_function("openStopPeek")
    assert 'id="pkaddr"' in peek and "openAddressDialog(row)" in peek
    assert "notInstalling.has(row) ? 'Back on the schedule' : 'Find a date'" in peek
    change = js_function("changeStopAddress")
    assert "await fetchRealLegs(geo.lat, geo.lon)" in change and "pushUndo();" in change
    assert "applySyntheticAddress(c, def);" in change and "persist(); render();" in change
    go = TEMPLATE[TEMPLATE.index("document.getElementById('ncgo').onclick"):][:4000]
    assert "if(ncAddrFor!=null){" in go and "await geocodeAddress(addr)" in go
    assert "await changeStopAddress(row, {street:addr, lat:geo.lat, lon:geo.lon});" in go
    # Same name as a not-installing stop: that stop, not a second copy.
    assert "is on the Not installing list." in go and "await ncBringBack(outSame);" in go
    back = js_function("ncBringBack")
    assert "changeStopAddress(row" in back and "putBackOnSchedule(row);" in back
    render = js_function("ncRenderMatches")
    assert "ncMatchOffers(found, notInstalling, canAddCallback)" in render and "data-backfor" in render
    # Back on the schedule only once a date is picked: no stop on no list.
    put = js_function("putBackOnSchedule")
    assert "notInstalling.delete" not in put and "openSlotFinder(row);" in put
    move = js_function("applyMove")
    assert "if(notInstalling.has(row)) delete lastScheduledFrom[row];" in move
    assert "notInstalling.delete(row);" in move
    # The dialog's job-only fields hide in address mode.
    assert TEMPLATE.count('class="nclabel ncjob"') == 3 and 'id="ncnotes" class="ncjob"' in TEMPLATE


@needs_node
def test_the_move_dialog_never_defaults_to_today_crew_1_from_a_list():
    out = run("""
      console.log(JSON.stringify([
        moveDlgPreset('2026-12-01', 'NOINSTALL', null),
        moveDlgPreset(null, '2026-11-20', {date:'2026-12-01'}),
        moveDlgPreset(null, 'NOINSTALL', {date:'2026-12-01', crew:'Crew 2'}),
        moveDlgPreset(null, 'ALL-INSTALL', null),
        moveDlgPreset(undefined, 'HOLD', {}),
      ]));
    """, ("moveDlgPreset",))
    assert out == ["2026-12-01", "2026-11-20", "2026-12-01", "", ""]
    dlg = js_function("openMoveDlg")
    assert "moveDlgPreset(presetDate, selDate, lastScheduledFrom[row])" in dlg
    assert '<option value="" disabled>Pick a date</option>' in dlg
    # The old fallback to the first date that works (today, Crew 1) is gone.
    assert "findIndex(o=>!o.disabled)" not in dlg


# ─── #55: Today ────────────────────────────────────────────────────────────────

@needs_node
def test_today_goes_to_today_or_the_next_date_with_work():
    out = run("""
      const W=['2026-11-24','2026-11-24','2026-11-27','2026-12-01'];
      console.log(JSON.stringify([
        todayDateFor('2026-11-24', W, true, 'ALL'),     // a crew works today
        todayDateFor('2026-11-25', W, true, 'ALL'),     // nothing today: the next work date
        todayDateFor('2026-10-01', W, false, 'ALL'),    // before the season: its first date
        todayDateFor('2026-12-20', W, true, 'ALL'),     // after the last: today, if listed
        todayDateFor('2027-03-01', W, false, 'ALL'),    // season over: the overview
      ]));
    """, ("todayDateFor",))
    assert out == ["2026-11-24", "2026-11-27", "2026-11-24", "2026-12-20", "ALL"]


def test_today_button_wiring():
    # Beside the dates list's picker (the top toolbar had no room for it at
    # 1440 wide), rebuilt with the list on every render.
    strip = js_function("renderStrip")
    assert "tb.id='tbtoday';" in strip and "<span>Today</span>" in strip
    assert "tb.onclick=goToday;" in strip and "hdrow.appendChild(scope); hdrow.appendChild(tb);" in strip
    go = js_function("goToday")
    assert "const to=todayTarget();" in go and "selDate=to;" in go and "render();" in go
    # Phones use the day bar's Today (the same rule), so this one hides there.
    assert "document.getElementById('pbtoday').click();" in go
    assert "@media (max-width:767px){ body.apple #tbtoday{display:none!important} }" in TEMPLATE
    assert "todayDateFor(T, work, stripListsDate(T), stripAll())" in js_function("todayTarget")
