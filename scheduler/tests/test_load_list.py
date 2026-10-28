"""Trailer load lists (review_template.html).

The user (2026-10-28): a "load list" for Dallas by trailer, "in reverse
order of installation ... the first stop of the night will be loaded last so
its at the front of the trailer", drawn as an outline of the real trailers
("they all look the same on the inside. 1 is just shorter"). Then: only the
first Dallas night goes in the three Spartans; the rest ride in a 50 ft
truck parked at the hotel, pulled from the doors night by night, trailer by
trailer, each trailer's set in its Spartan's loading order.

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
        "sumBoxes", "leadCrewStops", "nightTrailerLoads", "loadZones", "truckZones",
        "zoneSizes", "buildLoadPlan", "loadEsc", "wrapWords", "boxesTxt",
        "trailerTitle", "nightTag", "truckBlocks", "spartanGeom", "trailerOutlineSVG", "trailerSideSVG", "truckSideSVG",
        "truckOutlineSVG", "loadSpartanHTML", "loadTruckHTML", "loadCoverHTML", "loadListHTML"]


def trailers_const():
    m = re.search(r"^const TRAILERS=\[.*?^\];\nconst TRUCK50=.*?$", TEMPLATE, re.M | re.S)
    assert m
    return m.group(0) + "\n"


def run(body):
    src = trailers_const() + "\n".join(js_function(n) for n in PURE) + "\n" + body
    return json.loads(run_js(src))


def stop(row, boxes, name=None):
    return {"row": row, "name": name or f"Test Stop {row}", "city": "Testville", "boxes": boxes}


def crew(i, stops, trailer=None, title=None):
    return {"id": f"d|Crew {i}", "title": title or f"Crew {i}", "pos": i, "lead": [],
            "trailerId": trailer or ["bs24", "wb24", "ab20"][i - 1], "stops": stops}


# A four-night Dallas run: crew 1 and crew 2 share stop 20 (joint) on night 2.
NIGHTS = [
    {"night": 1, "date": "2026-11-02", "label": "Mon 11/02/2026", "kind": "install", "crews": [
        crew(1, [stop(1, 9), stop(2, 4), stop(3, 11)]),
        crew(2, [stop(4, 6), stop(5, 5)]),
        crew(3, [stop(6, 3), stop(7, 4)])]},
    {"night": 2, "date": "2026-11-03", "label": "Tue 11/03/2026", "kind": "install", "crews": [
        crew(1, [stop(20, 39), stop(21, 12)]),
        crew(2, [stop(20, 39), stop(22, 15)]),
        crew(3, [stop(23, 5), stop(24, 6)])]},
    {"night": 3, "date": "2026-11-04", "label": "Wed 11/04/2026", "kind": "install", "crews": [
        crew(1, [stop(30, 4)]),
        crew(2, [stop(31, None)]),
        crew(3, [stop(32, 2), stop(33, 4)])]},
]


@needs_node
def test_a_spartan_loads_in_reverse_install_order():
    out = run("""
      const z=loadZones([{row:1},{row:2},{row:3}], 'install');
      const t=loadZones([{row:1},{row:2},{row:3}], 'takedown');
      console.log(JSON.stringify({inst:z.map(x=>[x.load,x.row]), td:t.map(x=>[x.load,x.row])}));
    """)
    # Load #1 goes in first, against the nose: the night's LAST stop. The
    # first stop goes in last, at the rear door.
    assert out["inst"] == [[1, 3], [2, 2], [3, 1]]
    # A takedown fills as it goes: the first stop is at the nose.
    assert out["td"] == [[1, 1], [2, 2], [3, 3]]


@needs_node
def test_each_stop_rides_in_one_trailer_the_lead_crews():
    out = run(f"""
      const g=nightTrailerLoads({json.dumps(NIGHTS[1]["crews"])});
      console.log(JSON.stringify(g.map(x=>({{t:x.trailerId, rows:x.stops.map(s=>s.row),
        inst:x.stops.map(s=>s.inst+'/'+s.of), shared:x.stops.map(s=>s.sharedWith)}}))));
    """)
    # The joint stop (row 20) is all in Crew 1's trailer, never Crew 2's.
    assert out[0] == {"t": "bs24", "rows": [20, 21], "inst": ["1/2", "2/2"],
                      "shared": [["Crew 2"], []]}
    assert out[1]["rows"] == [22]
    rows = [r for g in out for r in g["rows"]]
    assert len(rows) == len(set(rows)) == 5


@needs_node
def test_crews_on_one_trailer_share_it_and_empty_trailers_drop():
    out = run("""
      const c=[{id:'a',title:'Crew 3',lead:['Lead A'],trailerId:'ab20',stops:[{row:1,boxes:9}]},
               {id:'b',title:'Crew 3',lead:[],trailerId:'ab20',stops:[{row:2,boxes:3},{row:3,boxes:4}]},
               {id:'c',title:'Crew 4',lead:[],trailerId:'wb24',stops:[{row:1,boxes:9}]}];
      const g=nightTrailerLoads(c);
      console.log(JSON.stringify(g.map(x=>[x.trailerId, x.crews, x.leads, x.stops.map(s=>s.row+':'+s.inst)])));
    """)
    assert out == [["ab20", ["Crew 3"], ["Lead A"], ["1:1", "2:2", "3:3"]]]


@needs_node
def test_dallas_plan_night_one_in_spartans_rest_in_the_truck():
    out = run(f"""
      const p=buildLoadPlan({json.dumps(NIGHTS)}, {{dallas:true}});
      console.log(JSON.stringify({{
        spartans:p.spartans.map(x=>[x.night, x.trailerId, x.source, x.total]),
        transfers:p.transfers.map(x=>[x.night, x.trailerId, x.source, x.zones.map(z=>z.row)]),
        truck:p.truck.zones.slice().sort((a,b)=>a.seq-b.seq).map(z=>[z.seq, z.load, z.night, z.trailerNum, z.row]),
        truckTotal:p.truck.total, nightTotals:p.truck.nights.map(n=>[n.night,n.total]),
        grand:p.grand, stops:p.stops, missing:p.missing}}));
    """)
    assert out["spartans"] == [[1, "bs24", "shop", 24], [1, "wb24", "shop", 11],
                               [1, "ab20", "shop", 7]]
    # Order off the Big Truck at the Doors: night 2 first; Trailer 1's set, then
    # 2's, then 3's; each set in its Spartan's loading order (last stop first).
    assert out["truck"] == [
        [1, 9, 2, 1, 21], [2, 8, 2, 1, 20],
        [3, 7, 2, 2, 22],
        [4, 6, 2, 3, 24], [5, 5, 2, 3, 23],
        [6, 4, 3, 1, 30],
        [7, 3, 3, 2, 31],
        [8, 2, 3, 3, 33], [9, 1, 3, 3, 32],
    ]
    # The truck is loaded in exactly the reverse: load #1 (the last night's
    # Trailer 3 first stop) goes against the nose.
    # The transfer pages are each Spartan's own load for that night, and what
    # comes off the truck for a trailer is already in that loading order.
    assert out["transfers"][0] == [2, "bs24", "truck", [21, 20]]
    assert [t[:2] for t in out["transfers"]] == [[2, "bs24"], [2, "wb24"], [2, "ab20"],
                                                 [3, "bs24"], [3, "wb24"], [3, "ab20"]]
    # Box totals: the joint stop is counted once, a blank count adds nothing
    # and is listed as missing.
    assert out["truckTotal"] == 39 + 12 + 15 + 5 + 6 + 4 + 2 + 4
    assert out["nightTotals"] == [[2, 77], [3, 10]]
    assert out["grand"] == 24 + 11 + 7 + out["truckTotal"]
    assert out["stops"] == 7 + 9
    assert out["missing"] == [{"name": "Test Stop 31", "label": "Wed 11/04/2026"}]


@needs_node
def test_takedown_and_non_dallas_nights_use_spartans_only():
    td = [dict(n, kind="takedown") for n in NIGHTS]
    out = run(f"""
      const a=buildLoadPlan({json.dumps(td)}, {{dallas:true}});
      const b=buildLoadPlan({json.dumps(NIGHTS[:1])}, {{dallas:false}});
      const c=buildLoadPlan({json.dumps(NIGHTS)}, {{dallas:false}});
      console.log(JSON.stringify({{a:[!!a.truck, a.spartans.length, a.transfers.length, a.spartans[0].source,
          a.spartans[0].zones.map(z=>z.row)], b:[!!b.truck, b.spartans.length], c:[!!c.truck, c.transfers.length]}}));
    """)
    assert out["a"] == [False, 9, 0, "takedown", [1, 2, 3]]
    assert out["b"] == [False, 3]
    assert out["c"] == [False, 0]


@needs_node
def test_zone_sizes_follow_boxes_with_a_floor():
    out = run("""console.log(JSON.stringify([zoneSizes([10,30],400,100), zoneSizes([1,1,1],90,50), zoneSizes([null,5],200,20)]));""")
    assert out[0] == [150, 250]
    assert out[1] == [30, 30, 30]
    assert abs(sum(out[2]) - 200) < 1e-9 and out[2][0] < out[2][1]


@needs_node
def test_the_20_ft_outline_is_shorter_than_the_24s_in_both_views():
    out = run("""
      const z=loadZones([{row:1,name:'Test A',boxes:3,inst:1,of:2},{row:2,name:'Test B',boxes:5,inst:2,of:2}],'install');
      const box=svg=>+/<rect x="[\\d.]+" y="24" width="([\\d.]+)" height="212" fill="none"/.exec(svg)[1];
      const body=svg=>{ const m=/M([\\d.]+) 168 L[\\d.]+ [\\d.]+ Q[\\d.]+ [\\d.]+ [\\d.]+ [\\d.]+ L([\\d.]+) /.exec(svg); return +m[2]-(+m[1]); };
      const t20=trailerOutlineSVG(trailerById('ab20'), z), t24=trailerOutlineSVG(trailerById('bs24'), z);
      const s20=trailerSideSVG(trailerById('ab20'), z), s24=trailerSideSVG(trailerById('bs24'), z);
      const xs=svg=>[...svg.matchAll(/<g class="(?:zone|panel)" data-stop="(\\d)"[^>]*><rect x="([\\d.]+)" y="[\\d.]+" width="([\\d.]+)"/g)].map(m=>[+m[1], Math.round(+m[2]), Math.round(+m[3])]);
      console.log(JSON.stringify({w20:box(t20), w24:box(t24), b20:body(s20), b24:body(s24),
        top:xs(t24), side:xs(s24), words:['NOSE','DOORS','Stop 2','Stop 1','5 boxes'].map(t=>t24.includes(t)||s24.includes(t)).concat([s24.includes('Test A'), !t24.includes('Test A')])}));
    """)
    assert out["w20"] == 500 and out["w24"] == 600   # 25 px a foot
    assert out["b20"] == 500 and out["b24"] == 600
    assert all(out["words"])
    # Stop 2 (the last stop) is at the Nose, Stop 1 at the Doors, in both
    # views; panels line up and are sized by boxes (5 vs 3).
    assert [x[0] for x in out["top"]] == [2, 1]
    assert [[a[0], a[1] + 4, a[2] - 8] for a in out["top"]] == out["side"]
    assert out["top"][0][2] > out["top"][1][2]


@needs_node
def test_big_truck_side_view_nights_and_trailers():
    out = run(f"""
      const p=buildLoadPlan({json.dumps(NIGHTS)}, {{dallas:true}});
      const s=truckSideSVG(p.truck);
      const blocks=[...s.matchAll(/class="tblock" data-night="(\\d)" data-trailer="(\\d)" data-row="(\\d+)" x="([\\d.]+)" y="\\d+" width="([\\d.]+)"/g)]
        .map(m=>({{n:+m[1], t:+m[2], r:+m[3], w:+m[5]}}));
      console.log(JSON.stringify({{order:blocks.map(b=>[b.n,b.t,b.r]), w20:blocks.find(b=>b.r===20).w, w32:blocks.find(b=>b.r===32).w,
        brackets:[...s.matchAll(/>Night (\\d) · ([^<]+)</g)].map(m=>m[1]+' '+m[2]), doors:s.includes('DOORS: unload this end first')}}));
    """)
    # Nose (left) to Doors (right): Night 3 then Night 2; within a night
    # Trailer 3, 2, 1; Trailer 1 of Night 2 is last, its Stop 1 (row 20) in
    # front of its Stop 2 (row 21).
    assert out["order"] == [[3, 3, 32], [3, 3, 33], [3, 2, 31], [3, 1, 30],
                            [2, 3, 23], [2, 3, 24], [2, 2, 22], [2, 1, 20], [2, 1, 21]]
    assert out["w20"] > out["w32"]          # 39 boxes vs 2
    assert out["brackets"] == ["3 Wed 11/04", "2 Tue 11/03"] and out["doors"]


@needs_node
def test_big_truck_top_view_matches_the_side_view():
    out = run(f"""
      const p=buildLoadPlan({json.dumps(NIGHTS)}, {{dallas:true}});
      const t=truckOutlineSVG(p.truck), sd=truckSideSVG(p.truck);
      const blocks=svg=>[...svg.matchAll(/class="tblock" data-night="(\\d)" data-trailer="(\\d)"/g)].map(m=>m[1]+'/'+m[2]);
      console.log(JSON.stringify({{brackets:[...t.matchAll(/>(Night \\d)<\/text><text[^>]*>([^<]+)</g)].map(m=>m[1]+' · '+m[2]),
        sideBrackets:[...sd.matchAll(/>(Night \\d · [^<]+)</g)].map(m=>m[1]),
        bars:(t.match(/class="nbar"/g)||[]).length, top:[...new Set(blocks(t))], side:[...new Set(blocks(sd))],
        tag:t.includes('>Trailer 1 · Stop 1<'), noNightTag:!/Night \\d · Trailer/.test(t), noHeaderBar:!t.includes('NIGHT 2')}}));
    """)
    # One bracket per night, labelled the same in both views; two thin bars
    # sandwich each night; the same trailer blocks in the same order.
    assert out["brackets"] == out["sideBrackets"] == ["Night 3 · Wed 11/04", "Night 2 · Tue 11/03"]
    assert out["bars"] == 4
    assert out["top"] == out["side"] == ["3/3", "3/2", "3/1", "2/3", "2/2", "2/1"]
    assert out["tag"] and out["noNightTag"] and out["noHeaderBar"]


@needs_node
def test_printed_pages_cover_spartans_truck_and_transfers():
    out = run(f"""
      const p=buildLoadPlan({json.dumps(NIGHTS)}, {{dallas:true}});
      const h=loadListHTML(p, 'Dallas load list', 'Printed now');
      console.log(JSON.stringify({{sections:[...h.matchAll(/<section class="lpage ([a-z0-9]+)"/g)].map(m=>m[1]), h}}));
    """)
    assert out["sections"] == ["cover", "spartan", "spartan", "spartan", "truck",
                               "spartan", "spartan", "spartan", "spartan", "spartan", "spartan"]
    h = out["h"]
    assert "Trailer 1 · Black &amp; Silver (24 ft)" in h
    assert "Trailer 3 · All Black (20 ft)" in h
    assert "Big Truck" in h and "from the Big Truck" in h
    assert "Load Stop 3 first, at the Nose. Stop 1 goes in last, at the Doors." in h
    assert "Trailer 1 · Stop 1" in h
    assert "<th>Stop</th><th>Restaurant</th><th class=\"c\">Expected</th><th class=\"c\">Loaded</th>" in h
    assert "Loaded by" in h and "Checked by" in h
    # One vocabulary: none of the old or competing words.
    for word in ("Pull", "PULL", "pull ", "load #", "LOAD #", "50 ft", "ramp door", "RAMP",
                 "front wall", "install order", "Install order", "warehouse", "Spartan", "—"):
        assert word not in h, word


@needs_node
def test_saved_trailer_picks_are_normalized():
    out = run("""
      const keys=new Set(['a','b']);
      console.log(JSON.stringify([normTrailers({a:'ab20', b:'nope', c:'bs24'}, keys), normTrailers(['x']),
        withTrailer({a:'ab20'}, 'a', ''), withTrailer({}, 'b', 'wb24'),
        [1,2,3,4].map(defaultTrailerId), parseBoxes(''), parseBoxes('7'), parseBoxes(null)]));
    """)
    assert out == [{"a": "ab20"}, {}, {}, {"b": "wb24"}, ["bs24", "wb24", "ab20", "bs24"], None, 7, None]


def test_trailers_are_shared_state_like_the_other_shift_fields():
    assert "'trailers'" in re.search(r"const SHARED_MAP_KEYS=.*", TEMPLATE).group(0)
    assert "trailers, shiftNotes, roster" in js_function("snapshot")
    assert "trailers, shiftNotes, roster" in js_function("stateBlob")
    assert "trailers = normTrailers(s.trailers, trailerKeys())" in js_function("restoreBlob")
    assert "trailers = normTrailers(trailers, trailerKeys())" in js_function("render")
    # Declared before the boot code reads saved state (a `let` read early
    # throws, and the boot's try/catch would drop everything saved).
    assert TEMPLATE.index("let trailers={};") < TEMPLATE.index("trailers = normTrailers(s.trailers")


def test_buttons_print_the_load_list():
    card = js_function("buildDayCard")
    assert "loadbtn" in card and "printLoadList(d.date)" in card
    assert "stfTrailerHTML(sh)" in js_function("drawStaffDlg")
