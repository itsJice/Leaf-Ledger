"""Trailer load lists (review_template.html).

The user (2026-10-28): a "load list" for Dallas by trailer, "in reverse
order of installation ... the first stop of the night will be loaded last so
its at the front of the trailer", drawn as an outline of the real trailers
("they all look the same on the inside. 1 is just shorter"). Settled on
paper with Katrina: "We are going to try and fit everything into the 3
trailers": each crew's whole Dallas week in its own trailer, the last
night's last stop at the Nose, Night 1 Stop 1 at the Doors. A restaurant two
crews share is split between their trailers (39 -> 19 + 20) unless staff set
it; restaurants still in production ride in a Late Trailer driven up later.

These run the template's own pure functions in node. Every name is invented.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

PURE = ["trailerById", "defaultTrailerId", "normTrailers", "withTrailer", "parseBoxes",
        "sumBoxes", "normLoadStops", "withLoadStop", "stopShares", "nightTrailerLoads",
        "loadZones", "weekZones", "lateZones", "zoneSizes", "buildLoadPlan", "loadStopName",
        "nightTag", "nightRuns", "loadEsc", "wrapWords", "boxesTxt", "trailerTitle",
        "spartanGeom", "trailerOutlineSVG", "trailerSideSVG", "weekSideSVG", "weekTopSVG",
        "loadSpartanHTML", "loadWeekHTML", "loadLateHTML", "loadCoverHTML", "loadListHTML"]


def consts():
    m = re.search(r"^const TRAILERS=\[.*?^\];$", TEMPLATE, re.M | re.S)
    assert m
    late = re.search(r"^const LATE_TRAILER=.*$", TEMPLATE, re.M).group(0)
    words = re.search(r"^const LATE_WORDS=.*$", TEMPLATE, re.M).group(0)
    return "\n".join([m.group(0), late, words]) + "\n"


def run(body):
    src = consts() + "\n".join(js_function(n) for n in PURE) + "\n" + body
    return json.loads(run_js(src))


def stop(row, boxes, name=None):
    return {"row": row, "name": name or f"Test Stop {row}", "city": "Testville", "boxes": boxes}


def crew(i, stops, trailer=None):
    return {"id": f"n|Crew {i}", "title": f"Crew {i}", "pos": i, "lead": [],
            "trailerId": trailer or ["bs24", "wb24", "ab20"][i - 1], "stops": stops}


def night(n, date, label, crews, kind="install"):
    # crew-day ids are per night, like the board's
    cs = [dict(c, id=c["id"].replace("n|", f"{date}|")) for c in crews]
    return {"night": n, "date": date, "label": label, "kind": kind, "crews": cs}


# A three-night Dallas week. Crews 1 and 2 share row 20 (39 boxes) on night 2
# and row 30 (4 boxes) on night 3.
NIGHTS = [
    night(1, "2026-11-02", "Mon 11/02/2026", [
        crew(1, [stop(1, 9), stop(2, 4), stop(3, 11)]),
        crew(2, [stop(4, 6), stop(5, 5)]),
        crew(3, [stop(6, 3), stop(7, 4)])]),
    night(2, "2026-11-03", "Tue 11/03/2026", [
        crew(1, [stop(20, 39), stop(21, 12)]),
        crew(2, [stop(20, 39), stop(22, 15)]),
        crew(3, [stop(23, 5), stop(24, 6)])]),
    night(3, "2026-11-04", "Wed 11/04/2026", [
        crew(1, [stop(30, 4), stop(31, 4)]),
        crew(2, [stop(30, 4), stop(32, None)]),
        crew(3, [stop(33, 2)])]),
]


def plan_js(prefs="{}", nights=None, dallas=True):
    return f"const p=buildLoadPlan({json.dumps(nights or NIGHTS)}, {{dallas:{str(dallas).lower()}, prefs:{prefs}}});"


@needs_node
def test_a_night_loads_in_reverse_install_order():
    out = run("""
      const z=loadZones([{row:1},{row:2},{row:3}], 'install');
      const t=loadZones([{row:1},{row:2},{row:3}], 'takedown');
      console.log(JSON.stringify({inst:z.map(x=>x.row), td:t.map(x=>x.row)}));
    """)
    assert out["inst"] == [3, 2, 1]   # the last stop at the Nose, Stop 1 at the Doors
    assert out["td"] == [1, 2, 3]     # a takedown fills as it goes


@needs_node
def test_a_dallas_week_is_one_trailer_per_crew_in_reverse_across_the_week():
    out = run(plan_js() + """
      console.log(JSON.stringify({week:p.week, pages:p.weeks.map(w=>[w.trailerId, w.num,
        w.zones.map(z=>[z.night, z.inst, z.row, z.boxes]), w.total]), spartans:p.spartans.length, late:p.late}));
    """)
    assert out["week"] and out["spartans"] == 0 and out["late"] is None
    t1, t2, t3 = out["pages"]
    # Nose to Doors: the last night's last stop first ... Night 1 Stop 1 last.
    assert t1[:2] == ["bs24", 1]
    assert t1[2] == [[3, 2, 31, 4], [3, 1, 30, 2], [2, 2, 21, 12], [2, 1, 20, 19],
                     [1, 3, 3, 11], [1, 2, 2, 4], [1, 1, 1, 9]]
    # Shared stops split evenly, the lower crew taking the smaller half.
    assert t2[2] == [[3, 2, 32, None], [3, 1, 30, 2], [2, 2, 22, 15], [2, 1, 20, 20],
                     [1, 2, 5, 5], [1, 1, 4, 6]]
    assert t3[2] == [[3, 1, 33, 2], [2, 2, 24, 6], [2, 1, 23, 5], [1, 2, 7, 4], [1, 1, 6, 3]]
    assert [p[3] for p in out["pages"]] == [61, 48, 20]


@needs_node
def test_a_shared_stop_can_ride_entirely_in_the_other_crews_trailer():
    prefs = json.dumps({"30": {"split": {"2026-11-04|Crew 1": 0}},
                        "20": {"split": {"2026-11-03|Crew 1": 25}}})
    out = run(plan_js(prefs) + """
      console.log(JSON.stringify(p.weeks.map(w=>w.zones.filter(z=>z.row===30||z.row===20).map(z=>[z.row, z.boxes, z.full]))));
    """)
    assert out[0] == [[20, 25, 39]]                 # row 30 is not in Trailer 1 at all
    assert out[1] == [[30, 4, 4], [20, 14, 39]]


@needs_node
def test_stop_shares():
    out = run("""console.log(JSON.stringify([stopShares(['a','b'],39,{}), stopShares(['a','b'],4,{a:0}),
      stopShares(['a','b','c'],10,{}), stopShares(['a'],7,{}), stopShares(['a','b'],null,{}), stopShares(['a','b'],5,{a:9})]));""")
    assert out == [{"a": 19, "b": 20}, {"a": 0, "b": 4}, {"a": 3, "b": 3, "c": 4}, {"a": 7},
                   {"a": None, "b": 0}, {"a": 5, "b": 0}]


@needs_node
def test_in_production_stops_go_in_the_late_trailer():
    prefs = json.dumps({"2": {"notReady": True}, "22": {"notReady": True}, "30": {"notReady": True}})
    out = run(plan_js(prefs) + """
      const h=loadListHTML(p, 'Dallas load list', '');
      console.log(JSON.stringify({totals:p.weeks.map(w=>w.total), t1:p.weeks[0].zones.map(z=>[z.row, z.notReady]),
        late:p.late.zones.map(z=>[z.night, z.row, z.boxes, z.crews]), lateTotal:p.late.total, grand:p.grand,
        sections:[...h.matchAll(/<section class="lpage ([a-z ]+)"/g)].map(m=>m[1]),
        dashed:(h.match(/In the Late Trailer/g)||[]).length, cover:h.includes('All 4 trailers')}));
    """)
    # Still on the crew's sheet, in its place, with no boxes ...
    assert [2, True] in out["t1"]
    assert out["totals"] == [61 - 4 - 2, 48 - 15 - 2, 20]
    # ... and once on the Late Trailer with all its boxes, latest needed at
    # the Nose, the earliest (Night 1) at the Doors.
    assert out["late"] == [[3, 30, 4, ["Crew 1", "Crew 2"]], [2, 22, 15, ["Crew 2"]], [1, 2, 4, ["Crew 1"]]]
    assert out["lateTotal"] == 23
    assert out["grand"] == 61 + 48 + 20     # every box is on some trailer
    assert out["sections"] == ["cover", "week", "week", "week", "week late"]
    assert out["dashed"] == 4 and out["cover"]


@needs_node
def test_takedown_and_other_nights_print_one_page_per_trailer_per_night():
    td = [dict(n, kind="takedown") for n in NIGHTS]
    out = run(f"""
      const a=buildLoadPlan({json.dumps(td)}, {{dallas:true}});
      const b=buildLoadPlan({json.dumps(NIGHTS[:1])}, {{dallas:true}});
      console.log(JSON.stringify({{a:[a.week, a.spartans.length, a.spartans[0].zones.map(z=>z.row)], b:[b.week, b.spartans.length]}}));
    """)
    assert out["a"] == [False, 9, [1, 2, 3]]
    assert out["b"] == [False, 3]


@needs_node
def test_zone_sizes_follow_boxes_with_a_floor():
    out = run("""console.log(JSON.stringify([zoneSizes([10,30],400,100), zoneSizes([1,1,1],90,50), zoneSizes([null,5],200,20)]));""")
    assert out[0] == [150, 250]
    assert out[1] == [30, 30, 30]
    assert abs(sum(out[2]) - 200) < 1e-9 and out[2][0] < out[2][1]


@needs_node
def test_week_views_scale_by_boxes_and_the_20_ft_is_shorter():
    out = run(plan_js(json.dumps({"2": {"notReady": True}})) + """
      const w1=p.weeks[0], w3=p.weeks[2];
      const side=weekSideSVG(trailerById('bs24'), w1.zones), top=weekTopSVG(trailerById('bs24'), w1.zones, w1.total);
      const top20=weekTopSVG(trailerById('ab20'), w3.zones, w3.total), top24=weekTopSVG(trailerById('bs24'), w3.zones, w3.total);
      const body=svg=>{ const m=/<rect x="150" y="58" width="70" height="([\\d.]+)" fill="none"/.exec(svg); return +m[1]; };
      const panels=[...side.matchAll(/class="wpanel" data-night="(\\d)" data-stop="(\\d)" data-row="(\\d+)"><rect x="([\\d.]+)" y="\\d+" width="([\\d.]+)"/g)]
        .map(m=>({n:+m[1], r:+m[3], w:+m[5]}));
      console.log(JSON.stringify({rows:panels.map(x=>x.r), w20:panels.find(x=>x.r===20).w, w31:panels.find(x=>x.r===31).w,
        sideBr:[...side.matchAll(/>Night (\\d)</g)].map(m=>+m[1]), topBr:[...top.matchAll(/>Night (\\d)</g)].map(m=>+m[1]),
        bars:(top.match(/class="nbar"/g)||[]).length, h20:body(top20), h24:body(top24),
        late:/Test Stop 2 · In the Late Trailer/.test(top), split:top.includes('Test Stop 20: 19 of 39')}));
    """)
    assert out["rows"] == [31, 30, 21, 20, 3, 1]          # in-production row 2 takes no floor
    assert out["w20"] > out["w31"]
    assert out["sideBr"] == out["topBr"] == [3, 2, 1]
    assert out["bars"] == 6
    assert out["h20"] < out["h24"]
    assert out["late"] and out["split"]


@needs_node
def test_printed_words():
    out = run(plan_js(json.dumps({"22": {"notReady": True}})) + """
      console.log(JSON.stringify(loadListHTML(p, 'Dallas load list', 'Printed now')));
    """)
    h = out
    assert "Trailer 1 · Black &amp; Silver (24 ft)" in h and "Trailer 3 · All Black (20 ft)" in h
    assert "Late Trailer (drive-up)" in h
    assert "Load Night 3 first, at the Nose. Night 1 Stop 1 goes in last, at the Doors." in h
    assert "EXPECTED" in h and "LOADED" in h and "Loaded by" in h and "Checked by" in h
    assert "Night 2 · Crew 2 · Stop 2" in h
    for word in ("Pull", "PULL", "load #", "LOAD #", "50 ft", "Big Truck", "ramp door", "RAMP",
                 "front wall", "install order", "warehouse", "Spartan", "coming separately", "—"):
        assert word not in h, word


@needs_node
def test_saved_settings_are_normalized():
    out = run("""
      const keys=new Set(['a','b']);
      console.log(JSON.stringify([normTrailers({a:'ab20', b:'nope', c:'bs24'}, keys), normTrailers(['x']),
        withTrailer({a:'ab20'}, 'a', ''), withTrailer({}, 'b', 'wb24'),
        [1,2,3,4].map(defaultTrailerId), parseBoxes(''), parseBoxes('7'), parseBoxes(null),
        normLoadStops({'5':{notReady:true, split:{x:'19', y:-1}}, '6':{notReady:'yes'}, '7':{notReady:true}}, new Set(['5','6'])),
        withLoadStop({'5':{notReady:true}}, '5', {notReady:null}), withLoadStop({}, '5', {split:{d:0}})]));
    """)
    assert out == [{"a": "ab20"}, {}, {}, {"b": "wb24"}, ["bs24", "wb24", "ab20", "bs24"], None, 7, None,
                   {"5": {"notReady": True, "split": {"x": 19}}}, {}, {"5": {"split": {"d": 0}}}]


def test_load_settings_are_shared_state_like_the_other_shift_fields():
    keys = re.search(r"const SHARED_MAP_KEYS=.*", TEMPLATE).group(0)
    assert "'trailers'" in keys and "'loadStops'" in keys
    assert "trailers, loadStops, shiftNotes, roster" in js_function("snapshot")
    assert "trailers, loadStops, shiftNotes, roster" in js_function("stateBlob")
    rb = js_function("restoreBlob")
    assert "trailers = normTrailers(s.trailers, trailerKeys())" in rb
    assert "loadStops = normLoadStops(s.loadStops" in rb
    assert "loadStops = normLoadStops(loadStops" in js_function("render")
    # Declared before the boot code reads saved state (a `let` read early
    # throws, and the boot's try/catch would drop everything saved).
    assert TEMPLATE.index("let loadStops={};") < TEMPLATE.index("loadStops = normLoadStops(s.loadStops")
    import board_state
    assert "loadStops" in board_state.ROW_KEYED_MAPS   # a rebuild re-keys it by client


def test_buttons_and_controls():
    card = js_function("buildDayCard")
    assert "loadbtn" in card and "printLoadList(d.date)" in card
    assert "stfTrailerHTML(sh)" in js_function("drawStaffDlg")
    stf = js_function("stfTrailerHTML")
    assert "data-nr-row" in stf and "data-split-row" in stf and "LATE_WORDS" in stf
