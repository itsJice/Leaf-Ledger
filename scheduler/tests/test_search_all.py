"""The toolbar search's "See all search results (N)" row and the results panel
it opens (user, 2026-10-25: "When I search in the search bar, I want an option
at the very end to say see all search results."). searchAllResults() is the
pure part: every match, grouped, with why it matched. FAKE clients and people
only."""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

CLIENTS = [
    {"row": 1, "name": "Q Party Allen", "street": "1 Main St", "city": "Allen", "zip": "75013",
     "zone": "Allen/McKinney", "phone": "(214) 555-0101", "email": "allen@example.com"},
    {"row": 2, "name": "Q Party Uptown", "street": "2 Elm St", "city": "Dallas", "zip": "75201",
     "zone": "Uptown", "phone": "", "email": ""},
    {"row": 3, "name": "Smith, Jo", "street": "9 Woodlands Pkwy", "city": "Spring", "zip": "77380",
     "zone": "The Woodlands", "phone": "(281) 555-0199", "email": "",
     "contacts": [{"label": "Assistant phone", "text": "(832) 555-7777", "phone": True}]},
    {"row": 4, "name": "Woodlands Club", "street": "5 Oak Rd", "city": "Woodlands", "zip": "77381",
     "zone": "The Woodlands", "phone": "", "email": ""},
    {"row": 5, "name": "Q Party Rockwall", "street": "8 Lake Dr", "city": "Rockwall", "zip": "75087",
     "zone": "Rockwall", "phone": "", "email": ""},
    {"row": 6, "name": "Q Party Teardown", "street": "1 Main St", "city": "Allen", "zip": "75013",
     "zone": "Allen/McKinney", "visitType": "Takedown"},
    {"row": 7, "name": "Q Party Hold", "street": "3 Pine", "city": "Plano", "zip": "75024", "zone": "Plano"},
]
DAYS = [
    {"id": "2026-11-03|Crew 1|0", "date": "2026-11-03", "crew": "Crew 1", "crewKey": "Crew 1", "stops": [2, 7]},
    {"id": "2026-11-02|Crew 2|0", "date": "2026-11-02", "crew": "Crew 2", "crewKey": "Crew 2", "stops": [1]},
    {"id": "2026-11-10|Crew 1|0", "date": "2026-11-10", "crew": "Crew 1", "crewKey": "Crew 1", "stops": [4]},
    {"id": "2026-12-28|Crew 1|0", "date": "2026-12-28", "crew": "Crew 1", "crewKey": "Crew 1", "stops": [1, 6]},
    {"id": "2026-11-20|Crew 3|0", "date": "2026-11-20", "crew": "Crew 3", "crewKey": "Crew 3", "stops": [], "training": True},
]
SRC = {"clients": CLIENTS, "days": DAYS, "cutoff": "2026-12-24", "season": "2026",
       "out": [5], "hold": [7],
       "extraOut": [{"name": "Q Party Gone", "street": "", "city": "Frisco", "zip": "", "phone": "",
                     "reason": "NO INSTALL 2026 (client note)", "row": None}]}
PEOPLE = [
    {"id": "p1", "name": "Ana Fake", "phone": "7135550101", "phoneText": "(713) 555-0101", "email": "ana@example.com",
     "title": "Lead", "lang": "Both", "notes": "friend of alberto", "active": True,
     "legalName": "Ana Q Fake", "street": "1 Secret Ln", "city": "Katy", "zip": "77494"},
    {"id": "p2", "name": "Luis Sample", "phone": "", "email": "", "title": "General Installer",
     "lang": "Spanish", "notes": "", "active": False},
]


def search(q, src):
    src_js = js_function("searchAllResults") + "\n" + js_function("markRanges") + "\n"
    src_js += f"console.log(JSON.stringify(searchAllResults({json.dumps(q)}, {json.dumps(src)})));"
    return json.loads(run_js(src_js))


def by_key(res):
    return {g["key"]: g for g in res["groups"]}


def test_every_match_grouped_and_counted():
    res = search("q party", SRC)
    g = by_key(res)
    assert [x["key"] for x in res["groups"]] == ["stops", "takedown", "hold", "out"]
    # scheduled stops in date order, with the day, crew and colour key to jump to
    assert [(i["name"], i["date"], i["dayId"]) for i in g["stops"]["items"]] == [
        ("Q Party Allen", "2026-11-02", "2026-11-02|Crew 2|0"),
        ("Q Party Hold", "2026-11-03", "2026-11-03|Crew 1|0"),
        ("Q Party Uptown", "2026-11-03", "2026-11-03|Crew 1|0"),
    ]
    assert g["stops"]["items"][1]["note"] == "On hold"
    # after the cutoff, or a Takedown visit type, is a takedown visit
    assert [(i["name"], i["date"]) for i in g["takedown"]["items"]] == [
        ("Q Party Allen", "2026-12-28"), ("Q Party Teardown", "2026-12-28")]
    assert g["hold"]["items"][0]["dayId"] == "2026-11-03|Crew 1|0"
    assert g["out"]["label"] == "Not installing 2026"
    assert [(i["name"], i["row"], i["note"]) for i in g["out"]["items"]] == [
        ("Q Party Gone", None, "NO INSTALL 2026 (client note)"),
        ("Q Party Rockwall", 5, "Taken out by staff")]
    assert res["total"] == sum(len(x["items"]) for x in res["groups"]) == 8


def test_more_than_the_dropdown_shows():
    clients = [{"row": i, "name": f"Q Party {i:02d}", "city": "Dallas"} for i in range(1, 26)]
    days = [{"id": "2026-11-02|Crew 1|0", "date": "2026-11-02", "crew": "Crew 1", "stops": list(range(1, 26))}]
    res = search("Q Party", {"clients": clients, "days": days})
    assert res["total"] == 25 and len(res["groups"][0]["items"]) == 25


def test_why_each_matched_with_ranges():
    g = by_key(search("woodlands", SRC))
    smith = g["unplaced"]["items"][0] if "unplaced" in g else None
    stop = g["stops"]["items"][0]
    assert stop["name"] == "Woodlands Club"
    labels = [h["label"] for h in stop["hits"]]
    assert labels == ["Name", "City", "Area"]
    name = stop["hits"][0]
    assert name["ranges"] == [[0, 9]]
    area = stop["hits"][2]
    assert area["text"][area["ranges"][0][0]:area["ranges"][0][1]] == "Woodlands"
    # Smith isn't on a day: an unplaced client, matched on address and area
    assert smith["name"] == "Smith, Jo" and smith["dayId"] is None
    assert [h["label"] for h in smith["hits"]] == ["Address", "Area"]


def test_unplaced_excludes_not_installing_and_training_days():
    g = by_key(search("q party", SRC))
    assert "unplaced" not in g                     # Rockwall is out, Hold is on a day
    g = by_key(search("smith", SRC))
    assert list(g) == ["unplaced"] and g["unplaced"]["items"][0]["note"] == "Not on a day yet"


def test_phone_digits_and_secondary_contacts():
    g = by_key(search("832-555", SRC))
    hit = g["unplaced"]["items"][0]["hits"][0]
    assert hit["label"] == "Assistant phone"
    assert hit["text"][hit["ranges"][0][0]:hit["ranges"][0][1]] == "832) 555"
    g = by_key(search("2145550101", SRC))
    assert g["stops"]["items"][0]["hits"][0]["label"] == "Phone"


def test_multi_word_across_fields_and_one_letter_words():
    g = by_key(search("party dallas", SRC))
    item = g["stops"]["items"][0]
    assert item["name"] == "Q Party Uptown"
    assert {h["label"] for h in item["hits"]} == {"Name", "City"}
    # "q" only counts at the start of a word
    assert search("q smith", SRC)["total"] == 0


def test_name_hits_rank_first():
    g = by_key(search("allen", {"clients": CLIENTS, "days": [], "cutoff": "2026-12-24"}))
    names = [i["name"] for i in g["unplaced"]["items"]]
    assert names[0] == "Q Party Allen"          # name hit before city-only hits
    assert set(names) == {"Q Party Allen", "Q Party Teardown"}


def test_people_on_the_roster():
    res = search("alberto", {"people": PEOPLE, "contractor": False})
    assert [(g["key"], g["label"]) for g in res["groups"]] == [("people", "People")]
    p = res["groups"][0]["items"][0]
    assert (p["kind"], p["id"], p["note"]) == ("person", "p1", "Lead")
    assert p["hits"][0]["label"] == "Notes"
    assert search("luis", {"people": PEOPLE})["groups"][0]["items"][0]["note"] == "General Installer · Inactive"
    assert search("713 555", {"people": PEOPLE})["total"] == 1
    # contractor fields only for those allowed to see them
    assert search("secret", {"people": PEOPLE, "contractor": False})["total"] == 0
    assert search("secret", {"people": PEOPLE, "contractor": True})["total"] == 1


def test_empty_query():
    assert search("   ", SRC) == {"q": "", "total": 0, "groups": []}


def test_mark_ranges_escapes_and_wraps():
    src = js_function("markRanges") + "\n"
    src += "const e=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
    src += "console.log(JSON.stringify([markRanges('A & <b> Woodlands', [[8,17]], e), markRanges('abc', [], e),"
    src += " markRanges('aaaa', [[0,2],[1,3]], e)]));"
    assert json.loads(run_js(src)) == ["A &amp; &lt;b> <mark>Woodlands</mark>", "abc", "<mark>aa</mark><mark>a</mark>a"]


def test_dropdown_ends_with_see_all_and_panel_wiring():
    rs = js_function("renderSearch")
    assert "+ searchAllRowHTML(q)" in rs and "searchAllRowHTML(q)" in rs.split("const results")[0]
    row = js_function("searchAllRowHTML")
    assert "See all search results (${n})" in row and 'id="sr-all"' in row
    assert "openSearchAll(searchBox.value)" in js_function("wireSearchRows")
    kd = TEMPLATE[TEMPLATE.index("searchBox.addEventListener('keydown'"):][:900]
    assert "ArrowDown" in kd and "cur.click()" in kd
    assert '<dialog id="sxdlg"' in TEMPLATE and "jumpToClient(it.row, it.dayId)" in js_function("sxOpenItem")
    assert "openStopPeek(it.row, null)" in js_function("sxOpenItem")
    assert "openPersonDlg(pn)" in js_function("sxOpenItem")
    css = TEMPLATE[TEMPLATE.index('/* "See all search results" panel'):][:6000]
    assert "prefers-reduced-motion" in css and "max-width:767px" in css
    # user-facing text: no em dashes
    for chunk in (row, js_function("drawSearchAll"), js_function("sxItemHTML"), css):
        assert "—" not in chunk


def test_jump_to_client_takes_a_day():
    j = js_function("jumpToClient")
    assert "x.id===dayId && x.stops.includes(row)" in j
