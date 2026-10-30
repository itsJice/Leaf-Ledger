"""The Trailer Loader view (review_template.html, user 2026-10-29).

"a trailer loader view tab. where you select your days which ones and how
many and it shows you the load order ... the output should be this": the
approved load sheets (PR #133), built from the board in the page. These run
the template's pure functions in node. Every name is invented.
"""
import json
import re

from test_client_name_editor import TEMPLATE, js_function
from test_load_list import NIGHTS, PURE, consts, crew, night, needs_node, run, stop  # noqa: F401

MORE = ["tripKey", "normLoadTrips", "loadAdvice", "loadCopyText", "loadPageText", "loadReconcile",
        "shortRange", "dateRuns", "isoOf", "dateOf"]


def run2(body):
    months = re.search(r"^const MONTHS=\[.*?\];", TEMPLATE, re.M | re.S).group(0)
    return run(months + "\n" + "\n".join(js_function(n) for n in MORE) + "\n" + body)


def plan(prefs=None, nights=None, **opts):
    o = {"dallas": True, "prefs": prefs or {}, **opts}
    return f"const p=buildLoadPlan({json.dumps(nights or NIGHTS)}, {json.dumps(o)});"


@needs_node
def test_a_stop_moved_to_another_trailer_rides_there_by_its_stop_number():
    # Crew 3's Night 2 Stop 2 (row 24, 6 boxes) moved into Trailer 2.
    out = run2(plan({"24": {"trailer": "wb24"}}) + """
      const [t1,t2,t3]=p.weeks;
      console.log(JSON.stringify({t2:t2.zones.map(z=>[z.night, z.inst, z.row, z.boxes, z.movedFrom||null]),
        t3:t3.zones.map(z=>[z.row, z.boxes, z.movedTo||null, z.movedNum||null]), totals:p.weeks.map(w=>w.total), grand:p.grand,
        svg3:weekTopSVG(trailerById('ab20'), t3.zones, t3.total).includes('Test Stop 24 · In Trailer 2'),
        svg2:weekTopSVG(trailerById('wb24'), t2.zones, t2.total).includes('Night 2 · Crew 3 · Stop 2'),
        cover:loadCoverHTML(p, 'T', '').includes('<i>Test Stop 24: Trailer 2</i>')}));
    """)
    # Loading order on Trailer 2, Night 2: Stop 2s (its own 22 and the moved 24), then Stop 1.
    assert out["t2"][2:5] == [[2, 2, 24, 6, "Crew 3"], [2, 2, 22, 15, None], [2, 1, 20, 20, None]]
    assert [24, 6, "wb24", 2] in out["t3"]
    assert out["totals"] == [61, 48 + 6, 20 - 6] and out["grand"] == 61 + 48 + 20
    assert out["svg3"] and out["svg2"] and out["cover"]


@needs_node
def test_in_production_wins_over_a_move_and_unknown_trailers_are_ignored():
    out = run2(plan({"24": {"trailer": "wb24", "notReady": True}, "23": {"trailer": "t-gone"}}) + """
      console.log(JSON.stringify({moved:p.weeks.flatMap(w=>w.zones).filter(z=>z.movedTo||z.movedFrom).length,
        late:p.late.zones.map(z=>z.row)}));
    """)
    assert out == {"moved": 0, "late": [24]}


@needs_node
def test_a_crew_with_no_trailer_is_listed_until_its_stops_move():
    nights = [night(1, "2026-11-02", "Mon 11/02/2026", [
        crew(1, [stop(1, 9)]), crew(2, [stop(2, 5), stop(3, 4)], trailer="none")])]
    out = run2(plan({"3": {"trailer": "bs24"}}, nights, mode="trip") + """
      console.log(JSON.stringify({pages:p.weeks.map(w=>[w.trailerId, w.total]), none:p.noTrailer.map(s=>[s.row, s.boxes]),
        note:loadCoverHTML(p,'T','').includes('No trailer yet')}));
    """)
    assert out["pages"] == [["bs24", 13]]
    assert out["none"] == [[2, 5]]
    assert out["note"]


@needs_node
def test_the_trip_mode_overrides_the_usual_rule():
    td = [dict(n, kind="takedown") for n in NIGHTS]
    out = run2(f"""
      const a=buildLoadPlan({json.dumps(NIGHTS)}, {{dallas:true, mode:'night'}});
      const b=buildLoadPlan({json.dumps(td)}, {{dallas:true, mode:'trip'}});
      const c=buildLoadPlan({json.dumps(NIGHTS[:1])}, {{dallas:false, mode:'trip'}});
      console.log(JSON.stringify({{a:[a.week, a.spartans.length, !!a.late],
        b:[b.week, b.weeks[0].kind, b.weeks[0].zones.map(z=>z.row)], bh:loadWeekHTML(b.weeks[0]),
        c:[c.week, c.weeks.length], ch:loadWeekHTML(c.weeks[0])}}));
    """)
    assert out["a"] == [False, 9, False]
    # A takedown trip fills as it goes: Night 1 Stop 1 at the Nose.
    assert out["b"][:2] == [True, "takedown"] and out["b"][2] == [1, 2, 3, 20, 21, 30, 31]
    assert "Takedown: load as you go. Load 1st goes in at the Nose." in out["bh"]
    assert out["c"] == [True, 3] and "Crew 1 · Night 1<" in out["ch"]


@needs_node
def test_fleet_capacity_and_custom_trailers():
    out = run2("""
      const f=normFleet({bs24:{cap:'80', name:'x'}, ab20:{cap:0}, 't-rental':{name:'  Rental  (16 ft) ', len:'16'},
        't-bad':{name:'', len:10}, 'evil':{name:'Y', len:10}, 't-long':{name:'Z', len:90}, late:{cap:50}});
      const l=fleetList(f);
      console.log(JSON.stringify({f, l:l.map(t=>[t.id, t.cap, t.custom]), d:[defaultCap(24), defaultCap(20)],
        n:normTrailers({a:'t-rental', b:'none', c:'t-x'}, null, new Set([...l.map(t=>t.id), 'none']))}));
    """)
    assert out["f"] == {"bs24": {"cap": 80}, "late": {"cap": 50}, "t-rental": {"name": "Rental (16 ft)", "len": 16}}
    assert out["l"] == [["bs24", 80, False], ["wb24", 72, False], ["ab20", 60, False], ["t-rental", 48, True]]
    assert out["d"] == [72, 60]
    assert out["n"] == {"a": "t-rental", "b": "none"}


@needs_node
def test_box_overrides_and_moves_are_saved_per_stop():
    out = run2("""
      console.log(JSON.stringify([normLoadStops({'5':{boxes:'12', trailer:'wb24'}, '6':{boxes:-1, trailer:'<x>'}, '7':{boxes:0}}),
        withLoadStop({'5':{boxes:12}}, '5', {boxes:null}),
        normLoadTrips({'2026-11-02|2026-11-05':'night', 'x':'trip', '2026-11-02|2026-11-03':'week'})]));
    """)
    assert out == [{"5": {"boxes": 12, "trailer": "wb24"}, "7": {"boxes": 0}}, {}, {"2026-11-02|2026-11-05": "night"}]


@needs_node
def test_over_capacity_suggests_the_smallest_stop_that_fits_elsewhere():
    out = run2("""
      const z=(row,b,extra)=>({row, name:'Test Stop '+row, boxes:b, ...(extra||{})});
      const pages=[
        {trailerId:'bs24', num:1, cap:20, total:26, zones:[z(1,3), z(2,7), z(3,9), z(4,7,{shared:true})]},
        {trailerId:'wb24', num:2, cap:20, total:19, zones:[]},
        {trailerId:'ab20', num:3, cap:20, total:10, zones:[]}];
      const near=[{trailerId:'bs24', num:1, cap:20, total:18, zones:[]}];
      console.log(JSON.stringify([loadAdvice(pages), loadAdvice(near)]));
    """)
    over = out[0][0]
    assert over["kind"] == "over" and over["over"] == 6
    assert over["move"]["row"] == 2 and over["move"]["to"] == "ab20" and over["move"]["room"] == 10
    assert out[1] == [{"kind": "near", "trailerId": "bs24", "num": 1, "total": 18, "cap": 20}]


@needs_node
def test_copy_list_is_restaurant_comma_boxes_by_trailer():
    out = run2(plan({"2": {"notReady": True}}) + "console.log(JSON.stringify(loadCopyText(p)));")
    lines = out.split("\n")
    assert lines[0] == "Trailer 1 · Black & Silver (24 ft): Crew 1"
    assert lines[1] == "Test Stop 31, 4"                      # Load 1st first
    assert "Test Stop 20: Boxes 1–19 of 39, 19" in lines
    assert "Test Stop 2, 4" not in lines[:9]                  # in production: on the Late Trailer list
    assert "Late Trailer (drive-up)" in lines and lines[-1] == "All trailers, 129"
    assert "—" not in out


@needs_node
def test_reconcile_explains_the_gap_to_the_board():
    out = run2(plan({"2": {"notReady": True}, "30": {"split": {"2026-11-04|Crew 1": 0}}}) + f"""
      console.log(JSON.stringify(loadReconcile({json.dumps(NIGHTS)}, p.weeks[0])));
    """)
    assert out["board"] == 9 + 4 + 11 + 39 + 12 + 4 + 4
    assert out["loaded"] == 9 + 11 + 19 + 12 + 4
    text = " | ".join(out["lines"])
    assert "In production (Late Trailer): Test Stop 2 4" in text
    assert "Split: Test Stop 20 19 of 39 here" in text
    assert "In the other crew's trailer: Test Stop 30 4" in text


@needs_node
def test_quick_picks_find_back_to_back_runs():
    out = run2("""console.log(JSON.stringify([dateRuns(['2026-11-02','2026-11-03','2026-11-05','2026-12-31','2027-01-01']),
      shortRange('2026-11-02','2026-11-05'), shortRange('2026-12-30','2027-01-02'), shortRange('2026-11-03','2026-11-03')]));""")
    assert out[0] == [["2026-11-02", "2026-11-03"], ["2026-11-05"], ["2026-12-31", "2027-01-01"]]
    assert out[1:] == ["Nov 2–5", "Dec 30–Jan 2", "Nov 3"]


def test_the_view_is_wired_like_the_others():
    assert '<div id="loadwrap" style="display:none"></div>' in TEMPLATE
    assert '<button id="viewload" type="button">Trailers</button>' in TEMPLATE
    sv = js_function("setView")
    assert "v==='load'" in sv and "'loadwrap'" in sv
    assert "else if(viewMode==='load'){ renderLoader(); }" in js_function("render")
    assert "else if(v==='load') printLoader();" in TEMPLATE
    # Every edit goes through the read-only gate, undo and the shared save.
    cl = js_function("commitLoader")
    assert "roBlocked()" in cl and "pushUndo();" in cl and "persist(); render();" in cl
    # Shared like the other shift fields, merged key by key on a stale tab.
    keys = re.search(r"const SHARED_MAP_KEYS=.*", TEMPLATE).group(0)
    assert "'trailerFleet'" in keys and "'loadTrips'" in keys
    # Declared before the boot code reads saved state.
    assert TEMPLATE.index("let trailerFleet={};") < TEMPLATE.index("trailerFleet = normFleet(s.trailerFleet)")
    assert TEMPLATE.index("const TRAILER_NONE=") < TEMPLATE.index("trailers = normTrailers(s.trailers")
    # Texting the lead is an sms: link the user sends; hidden when read-only.
    rl = js_function("renderLoader")
    assert 'href="sms:${smsNumber(p.phone)}&body=' in rl and "!ro ? pageLeads(sel)" in rl
    assert "—" not in rl
