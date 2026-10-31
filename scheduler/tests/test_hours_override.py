"""Staff-edited install hours on the live board (review_template.html).

A spreadsheet client's hours (C[r].h26) are baked into DATA, and a new DATA
is a new version (the board would look wiped). So an edit lives in shared
state, `hoursOverride: {row: hours}`, applied onto C at load and on every
restore, so every reader of h26 sees it. 10/30/2026: "M Crowd Lake
Highlands" takes about 4h, the sheet says 7.29h. An added (synthetic) stop
keeps editing its own stored hours (newClients[].hours).
These run the template's own functions in node, plus source pins for the
wiring (shared keys, undo blob, restore paths, gating).
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

HELPERS = "\n".join(js_function(n) for n in (
    "validHours", "normHoursOverride", "applyHoursOverrideTo", "fmtHrs"))


def run(body, extra=()):
    src = HELPERS + "\n" + "\n".join(js_function(n) for n in extra) + "\n" + body
    return json.loads(run_js(src))


@needs_node
def test_valid_hours_and_normalising_state():
    out = run("""
      console.log(JSON.stringify([
        [4, '4', 7.294, 0, -1, 25, 'x', null, undefined, ''].map(validHours),
        normHoursOverride({'63':4, '64':'2.5', '65':0, 'abc':3, '66':null, '67':30}),
        normHoursOverride(null), normHoursOverride([4]),
        [7.29, 4, 2.5, null].map(fmtHrs),
      ]));
    """)
    assert out[0] == [4, 4, 7.29, None, None, None, None, None, None, None]
    assert out[1] == {"63": 4, "64": 2.5}
    assert out[2] == {} and out[3] == {}
    assert out[4] == ["7.29", "4", "2.5", "—"]


@needs_node
def test_override_applies_and_resets_to_the_spreadsheet_value():
    out = run("""
      const C={63:{row:63,name:'M Crowd Lake Highlands',h26:7.29,basis:'est x0.81'},
               65:{row:65,name:'M Crowd Lakewood',h26:2.43,basis:'2025 real'},
               900015:{row:900015,name:'M Crowd Lake Highlands',h26:3.65,synthetic:true,visitType:'Takedown'}};
      const SHEET={};
      const snap=()=>[C[63].h26, C[63].basis, !!C[63].hoursEdited, C[65].h26, C[900015].h26];
      const a=[];
      applyHoursOverrideTo(C, SHEET, {});              a.push(snap());
      applyHoursOverrideTo(C, SHEET, {'63':4, '900015':1});  a.push(snap());
      applyHoursOverrideTo(C, SHEET, {'63':4});        a.push(snap());   // idempotent
      applyHoursOverrideTo(C, SHEET, {});              a.push(snap());   // reset / an older doc
      console.log(JSON.stringify([a, SHEET[63]]));
    """)
    steps, sheet = out
    assert steps[0] == [7.29, "est x0.81", False, 2.43, 3.65]
    # Staff value, marked staff-entered (not an estimate); an added stop is
    # never touched by the override map -- it keeps its own hours.
    assert steps[1] == [4, "staff entry", True, 2.43, 3.65]
    assert steps[2] == steps[1]
    # No override: the spreadsheet's own number, never a made-up one.
    assert steps[3] == steps[0]
    assert sheet == {"h": 7.29, "basis": "est x0.81"}


@needs_node
def test_lake_highlands_night_drops_by_the_difference():
    """effH / dayCalc read C, so the 11/04 Crew 1 night (Lake Highlands +
    Lakewood) drops by exactly 7.29 - 4 = 3.29h of install."""
    out = run("""
      const C={63:{h26:7.29}, 65:{h26:2.43}};
      const SHEET={};
      const d={half:[], stops:[63,65], stacked:1};
      const inst=()=>+d.stops.reduce((a,r)=>a+effH(d,r),0).toFixed(2);
      applyHoursOverrideTo(C, SHEET, {}); const before=inst();
      applyHoursOverrideTo(C, SHEET, {'63':4}); const after=inst();
      d.half=[63]; const half=effH(d,63);
      console.log(JSON.stringify([before, after, half]));
    """, extra=("effH",))
    assert out == [9.72, 6.43, 2]


def const_line(name):
    m = re.search(rf"^const {name}=.*$", TEMPLATE, re.M)
    assert m, name
    return m.group(0)


@needs_node
def test_shared_merge_keeps_both_tabs_edits():
    consts = "\n".join(const_line(n) for n in ("SHARED_SET_KEYS", "SHARED_MAP_KEYS", "SHARED_KEYS"))
    src = consts + "\nconst TEXT_LOG_MAX=5;\n" + "\n".join(
        js_function(n) for n in ("sharedDocOf", "stableJSON", "sameNewClient", "mergeShared")) + """
      const base={placement:{}};                       // an older document: no key at all
      const mine={placement:{}, hoursOverride:{'63':4}};
      const theirs={placement:{}, hoursOverride:{'70':2}};
      const both=mergeShared(base, mine, theirs, (k,r)=>'Row '+r);
      const clash=mergeShared({hoursOverride:{}}, {hoursOverride:{'63':4}}, {hoursOverride:{'63':5}}, (k,r)=>'Row '+r);
      const reset=mergeShared({hoursOverride:{'63':4}}, {hoursOverride:{}}, {hoursOverride:{'63':4}}, (k,r)=>'Row '+r);
      console.log(JSON.stringify([sharedDocOf({hoursOverride:{'63':4}, savedAt:1}), both.state.hoursOverride,
        clash.state.hoursOverride, clash.conflicts, reset.state.hoursOverride]));
    """
    shared, both, clash, conflicts, reset = json.loads(run_js(src))
    assert shared == {"hoursOverride": {"63": 4}}
    assert both == {"63": 4, "70": 2}
    assert clash == {"63": 5} and conflicts == ["Row 63: install time"]
    assert reset == {}


def test_wiring_is_in_place():
    """Saved, undoable, restored on every path, logged, and gated."""
    assert "'hoursOverride'];" in const_line("SHARED_MAP_KEYS")
    snap = js_function("snapshot")
    assert "hoursOverride," in snap
    blob = js_function("stateBlob")
    assert "hoursOverride" in blob and "synHours" in blob
    restore = js_function("restoreBlob")
    assert "hoursOverride = normHoursOverride(s.hoursOverride); applyHoursOverride();" in restore
    assert "s.synHours" in restore
    # The fresh-load path and the History restore apply it too.
    assert TEMPLATE.count("normHoursOverride(s.hoursOverride); applyHoursOverride();") == 2
    assert "hoursOverride = normHoursOverride(st.hoursOverride); applyHoursOverride();" in TEMPLATE
    # A shared document's own hours win for an added stop already on the board.
    assert "C[def.row].h26 = h;" in js_function("restoreSyntheticClients")
    setter = js_function("setStopHours")
    assert "roBlocked() || !canEditHours()" in setter
    assert "pushUndo();" in setter and "persist(); render();" in setter
    assert "from:`HOURS:" in setter
    assert "startsWith('HOURS:')" in js_function("renderLog")
    gate = js_function("canEditHours")
    assert "!READONLY" in gate and "!VIEWONLY" in gate and "ALERT_EDIT_ROLES" in gate


@needs_node
def test_popup_shows_edited_and_hides_buttons_from_viewers():
    out = run("""
      const peekEsc=s=>String(s);
      const C={63:{row:63,h26:4,hoursEdited:true}, 900015:{row:900015,h26:3.65,synthetic:true}};
      const sheetHoursOf=r=>C[r].synthetic?null:7.29;
      let pkEditingHours=false, canEdit=true;
      const canEditHours=()=>canEdit;
      const staff=peekHoursHTML(63), syn=peekHoursHTML(900015);
      pkEditingHours=true; const form=peekHoursHTML(63);
      canEdit=false; const viewer=peekHoursHTML(63);
      console.log(JSON.stringify([staff, syn, form, viewer]));
    """, extra=("peekHoursHTML",))
    staff, syn, form, viewer = out
    assert "edited (was 7.29h)" in staff and 'id="pkhrsedit"' in staff and 'id="pkhrsreset"' in staff
    assert "edited" not in syn and 'id="pkhrsedit"' in syn and "pkhrsreset" not in syn
    assert 'id="pkhrsin"' in form and 'value="4"' in form and "Spreadsheet: 7.29h" in form
    assert "edited (was 7.29h)" in viewer and "pkhrsedit" not in viewer and "pkhrsreset" not in viewer


def test_a_rebuild_carries_the_edit_by_client_name():
    """carry_state re-keys row-keyed state by NAME: a sheet row inserted
    above Lake Highlands renumbers it, and the 4h edit follows it."""
    import board_state as B
    old = {"spec": {"version": "a"}, "clients": {"63": {"name": "M Crowd Lake Highlands"},
                                                  "65": {"name": "M Crowd Lakewood"}},
           "days": [{"id": "2026-11-04|Crew 1|0", "stops": [63, 65]}]}
    new = {"spec": {"version": "b"}, "clients": {"64": {"name": "M Crowd Lake Highlands"},
                                                  "66": {"name": "M Crowd Lakewood"}},
           "days": [{"id": "2026-11-04|Crew 1|0", "stops": [64, 66]}]}
    state = {"placement": {"63": ["2026-11-04|Crew 1|0"], "65": ["2026-11-04|Crew 1|0"]},
             "hoursOverride": {"63": 4}}
    out, _ = B.carry_state(old, state, new)
    assert out["hoursOverride"] == {"64": 4}
