"""The toolbar "Find a client" dropdown also matches street, city and ZIP
(Comments #29, 11/6: "I can't remember the name of the client but the
address is Crawford; would like to be able to search for address only").
searchClientRows() is the pure part. FAKE clients only."""
import json
import shutil
import time

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

CLIENTS = [
    {"row": 1, "name": "Fakeman, Alex", "street": "1234 Maplewood St", "city": "Houston", "zip": "77001"},
    {"row": 2, "name": "Maplewood Pediatrics", "street": "9 Oak Ln", "city": "Katy", "zip": "77494"},
    {"row": 3, "name": "Sample, Jo", "street": "55  Birchmaple Ct", "city": "Spring", "zip": "77380"},
    {"row": 4, "name": "Testcase Cafe", "street": "", "city": "Sugar Land", "zip": "77479"},
    {"row": 5, "name": "Q Demo Club", "street": "8 Lake Dr", "city": "Houston", "zip": "77002"},
    {"row": 6, "name": "Nobody Home", "street": None, "city": None, "zip": None},
]


def search(q, clients=CLIENTS, limit=10):
    src = js_function("searchClientRows") + "\n"
    src += f"console.log(JSON.stringify(searchClientRows({json.dumps(q)}, {json.dumps(clients)}, {limit})));"
    return json.loads(run_js(src))


def names(res):
    return [r["name"] for r in res]


def test_address_only_partial_word():
    res = search("maplew")
    # the name match first, then the street match
    assert names(res) == ["Maplewood Pediatrics", "Fakeman, Alex"]
    assert [r["by"] for r in res] == ["name", "address"]
    addr = res[1]
    assert addr["addr"] == "1234 Maplewood St, Houston 77001"
    s, e = addr["addrRanges"][0]
    assert addr["addr"][s:e] == "Maplew"
    assert res[0]["nameRanges"] == [[0, 6]] and res[0]["addrRanges"] == []


def test_mid_word_street_and_case():
    res = search("MAPLE")
    assert names(res) == ["Maplewood Pediatrics", "Fakeman, Alex", "Sample, Jo"]
    jo = res[2]
    s, e = jo["addrRanges"][0]
    assert jo["addr"][s:e] == "maple"          # mid-word in "Birchmaple", after word-start hits
    assert jo["addr"] == "55 Birchmaple Ct, Spring 77380"   # double space collapsed


def test_city_zip_and_house_number():
    assert names(search("sugar land")) == ["Testcase Cafe"]
    assert names(search("77380")) == ["Sample, Jo"]
    assert names(search("1234 maple")) == ["Fakeman, Alex"]
    assert search("77380")[0]["addr"] == "55 Birchmaple Ct, Spring 77380"


def test_words_split_between_name_and_address():
    res = search("alex houston")
    assert names(res) == ["Fakeman, Alex"]
    r = res[0]
    assert r["by"] == "address"
    assert r["name"][r["nameRanges"][0][0]:r["nameRanges"][0][1]] == "Alex"
    assert r["addr"][r["addrRanges"][0][0]:r["addrRanges"][0][1]] == "Houston"


def test_name_words_out_of_order_rank_before_address():
    res = search("jo sample")
    assert names(res) == ["Sample, Jo"] and res[0]["by"] == "name"
    # "houston": two address matches, no name ones
    assert [r["by"] for r in search("houston")] == ["address", "address"]


def test_one_letter_words_only_at_word_start():
    assert names(search("q demo")) == ["Q Demo Club"]
    assert search("q fakeman") == []


def test_no_match_blank_and_missing_fields():
    assert search("crawfish") == []
    assert search("   ") == []
    assert search("nobody")[0]["addr"] == ""


def test_limit_keeps_name_matches_first():
    clients = [{"row": i, "name": f"Client {i:03d}", "street": f"{i} Pine St", "city": "Houston", "zip": "77001"}
               for i in range(1, 300)]
    clients.append({"row": 999, "name": "Pine Hollow HOA", "street": "1 Elm", "city": "Katy", "zip": "77494"})
    res = search("pine", clients, 10)
    assert len(res) == 10 and res[0]["name"] == "Pine Hollow HOA"
    assert all(r["by"] == "address" for r in res[1:])


def test_fast_on_300_clients():
    clients = [{"row": i, "name": f"Client {i:03d}", "street": f"{i} Pine St", "city": "Houston", "zip": "77001"}
               for i in range(1, 301)]
    src = js_function("searchClientRows") + "\n"
    src += f"const L={json.dumps(clients)};const t=Date.now();"
    src += "for(let k=0;k<100;k++) searchClientRows('pine', L, 10);"
    src += "console.log(Date.now()-t);"
    ms_per_search = int(run_js(src)) / 100
    assert ms_per_search < 20


def test_dropdown_wiring():
    sc = js_function("searchClients")
    assert "searchClientRows(q" in sc and "searchAddrFor(" in sc
    rs = js_function("renderSearch")
    assert "markRanges(r.addr, r.addrRanges, esc)" in rs and 'class="sraddr"' in rs
    assert "r.by==='address'" in rs
    assert "No client name or address matches" in rs
    assert "addrParts(C[row])" in js_function("searchAddrFor")
    assert "#searchresults mark{" in TEMPLATE and ".sraddr{" in TEMPLATE
    for chunk in (rs, js_function("searchClientRows")):
        assert "—" not in chunk
