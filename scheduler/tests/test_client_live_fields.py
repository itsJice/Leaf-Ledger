"""The schedule shows the client card's name, city and area (Comments #24, #27).

A stop's name, city and area line were baked into the build's DATA, so a fix
on the client card ("Chappell Hill", not the sheet's "Chapel Hill") never
reached the board, and a stop added later (Hanover Rice Village) had no area
line at all. DATA can't change -- its hash keys every saved board -- so the
page lays the card's values over the build's at runtime: from the Clients
list for staff, else /api/install-schedule/client-links (TV, production).
These run the template's own functions in node with small stubs, plus source
pins for the wiring.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

NORM = "const normName=s=>String(s||'').trim().toLowerCase().replace(/[,.]/g,'').replace(/\\s+/g,' ');\n"
FNS = ["ambiguousSpellings", "liveRecordIn", "liveClientRecord", "overlayClientFields", "applyLiveClientFields"]


def run(body, names=FNS):
    src = NORM + "\n".join(js_function(n) for n in names) + "\n" + body
    return json.loads(run_js(src))


INDEX = """
  function index(rows){ const m=new Map(); rows.forEach(c=>[c.name,c.sheet_name,...(c.former_names||[])]
    .forEach(n=>{ const k=normName(n); if(k && !m.has(k)) m.set(k,c); })); return m; }
"""

STOPS = """
  const C={
    14:{row:14, name:'Byers, Merlene (Bellville)', city:'Bellville', zone:'Bellville/Sealy', area:'Far West'},
    15:{row:15, name:'Byers, Merlene (Chapel Hill)', city:'Chapel Hill', zone:'Brenham/Chappell Hill', area:'Far West'},
    36:{row:36, name:'Ecklund, Michol', city:'Houston', zone:'West University/Rice', area:'Central'},
    900005:{row:900005, name:'Hanover Rice Village', street:'2455 Dunstan Rd, Houston, TX 77005', city:'', zone:'', area:'', synthetic:true},
    50:{row:50, name:'Woodlands CC', city:'The Woodlands', zone:'The Woodlands', area:'North'},
    60:{row:60, name:'Smith, Ann', city:'12 Oak St, Houston', zone:'Heights/Near Northside', area:'Central'},
  };
  const ROWS=[
    {id:256, name:'Byler, Merlene - Bellville', sheet_name:'Byers, Merlene (Bellville)', former_names:['Byers, Merlene (Bellville)'], city:'Bellville', area:null, zone:null},
    {id:257, name:'Byler, Merlene - Chappell Hill', sheet_name:'Byers, Merlene (Chapel Hill)',
     former_names:['Byers, Merlene (Chapel Hill)','Byler, Merlene - Chapel Hill'], city:'Chappell Hill', area:null, zone:null},
    {id:208, name:'Ecklund, Michol', sheet_name:'Ecklund, Michol', former_names:[], city:'Houston', area:null, zone:null},
    {id:302, name:'Hanover Rice Village', sheet_name:'Hanover Rice Village', former_names:[], city:'Houston', area:'Central', zone:'West University/Rice'},
    {id:1, name:'Woodlands CC - North', sheet_name:'Woodlands CC', former_names:[], city:'Spring', area:null, zone:'Nope'},
    {id:2, name:'Woodlands CC - South', sheet_name:'Woodlands CC', former_names:[], city:'Spring', area:null, zone:'Nope'},
    {id:9, name:'Smith, Ann', sheet_name:null, former_names:[], city:'Houston', area:null, zone:null},
  ];
"""


@needs_node
def test_card_name_city_and_area_show_on_the_stop():
    out = run(INDEX + """
      let clientDirectory=null, clientDirectoryAmbig=new Set(), driveLinkMap=null, driveLinkAmbig=new Set();
    """ + STOPS + """
      clientDirectory=index(ROWS); clientDirectoryAmbig=ambiguousSpellings(ROWS);
      const changed=applyLiveClientFields();
      console.log(JSON.stringify({changed, C}));
    """)
    C = out["C"]
    assert out["changed"] is True
    # #24: Merlene's Chappell Hill stop follows the card, the sheet spelling kept.
    assert (C["15"]["name"], C["15"]["city"]) == ("Byler, Merlene - Chappell Hill", "Chappell Hill")
    assert C["15"]["sheetName"] == "Byers, Merlene (Chapel Hill)"
    assert C["15"]["zone"] == "Brenham/Chappell Hill"   # blank on the card: the build's stands
    assert (C["14"]["name"], C["14"]["city"]) == ("Byler, Merlene - Bellville", "Bellville")
    # #27: the added stop gets the card's area line; Ecklund keeps the build's.
    assert (C["900005"]["zone"], C["900005"]["area"], C["900005"]["city"]) == (
        "West University/Rice", "Central", "Houston")
    assert C["36"]["zone"] == "West University/Rice"
    # A spelling two records share never overlays anything.
    assert C["50"] == {"row": 50, "name": "Woodlands CC", "city": "The Woodlands", "zone": "The Woodlands",
                       "area": "North"}
    # The sheet's street-in-the-city-cell quirk is left for addrParts.
    assert C["60"]["city"] == "12 Oak St, Houston"


@needs_node
def test_falls_back_to_client_links_then_the_build_and_clearing_restores_it():
    out = run(INDEX + """
      let clientDirectory=null, clientDirectoryAmbig=new Set(), driveLinkMap=null, driveLinkAmbig=new Set();
    """ + STOPS + """
      // TV / production: no Clients list, the client-links rows instead.
      driveLinkMap=index(ROWS); driveLinkAmbig=ambiguousSpellings(ROWS);
      applyLiveClientFields();
      const tv={name:C[15].name, city:C[15].city, zone:C[900005].zone};
      // The card's area is cleared later: the build's value comes back.
      ROWS[3].zone=null; ROWS[3].area=null;
      const again=applyLiveClientFields();
      // Crew / lead / offline: nothing loaded, nothing changes.
      driveLinkMap=null;
      const none=applyLiveClientFields();
      console.log(JSON.stringify({tv, again, zone:C[900005].zone, none}));
    """)
    assert out["tv"] == {"name": "Byler, Merlene - Chappell Hill", "city": "Chappell Hill",
                         "zone": "West University/Rice"}
    assert out["again"] is True and out["zone"] == ""
    assert out["none"] is False


@needs_node
def test_area_box_saves_only_a_change_with_its_broad_area():
    out = run("""
      const ZA={'West University/Rice':'Central', 'Bellville/Sealy':'Far West'};
      console.log(JSON.stringify([
        zoneChanges({zone:'West University/Rice', zone_was:'West University/Rice'}, ZA),
        zoneChanges({zone:' west university/rice ', zone_was:''}, ZA),
        zoneChanges({zone:'Brand New Place', zone_was:''}, ZA),
        zoneChanges({zone:'', zone_was:'Bellville/Sealy'}, ZA),
        zoneChanges({street:'x'}, ZA),
      ]));
    """, names=["zoneChanges"])
    assert out == [{}, {"zone": "West University/Rice", "area": "Central"}, {"zone": "Brand New Place"},
                   {"zone": "", "area": ""}, {}]


def test_wiring():
    # Loaded for everyone with a token, not just when a stop popup opens.
    assert "loadDriveLinks().then(()=>{ if(applyLiveClientFields() || anyRestrictions()) render(); });" in TEMPLATE
    assert "applyLiveClientFields();" in js_function("loadClientDirectory")
    assert "driveLinkAmbig=ambiguousSpellings(rows);" in js_function("loadDriveLinks")
    # Added stops come with the shared state, often after the records landed.
    assert "if(added){ try{ applyLiveClientFields(); }catch(e){} }" in js_function("restoreSyntheticClients")
    assert "clientDirectoryAmbig = ambiguousSpellings(rows);" in js_function("loadClientDirectory")
    # The editor has the Area box, saves it with the card and redraws the board.
    assert "pkField('pkf-zone','Area'" in js_function("contactEditHTML")
    assert "['zone','pkf-zone']" in js_function("syncContactBuffer")
    assert "...zoneChanges(f, ZONE_AREA)" in js_function("clientCardBody")
    assert "if(applyLiveClientFields()) fieldsChanged=true;" in TEMPLATE
    assert "seasonSaved || fieldsChanged)) render();" in TEMPLATE
    # The saved board never carries the overlay: added stops save their own
    # name and street, not city/zone/area.
    snap = js_function("snapshot")
    new_clients = snap[snap.index("const newClients"):snap.index("notInstallingNames")]
    assert not re.search(r"\b(zone|area|city)\s*:", new_clients)
