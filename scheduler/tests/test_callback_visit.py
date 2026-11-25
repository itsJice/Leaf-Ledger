"""Return trips are added to the client, not as a new client (11/2026).

Nicole (office): "every time I add a new install for a callback, it is adding
an entirely new client. Is that right?" It was: "+ New client" was the only
way, so a client's callback became a client called "Jane Sample" next to
the real "Sample, Jane", and editing it made a duplicate client card. Now
the stop card, the find box and "+ New client" (when the name matches) add a
return trip FOR the client: an added stop under the client's own name,
visit type Callback, `of` = the client's row, `returnReason` = why (callback,
bought more, fix, unfinished, other). These run the template's own
functions in node with small stubs, plus source pins for the wiring.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

HELPERS = ["normName", "isTakedownVisit", "isCallbackVisit", "isExtraVisit", "normReturnReason", "visitSuffix",
           "matchExistingClients", "legsFromRow", "fullAddressOf", "extraVisitRow"]


def run(body, extra=(), prelude=""):
    src = (prelude + "\nconst RETURN_REASONS={callback:'Callback', bought_more:'Bought more', fix:'Fix', unfinished:'Unfinished', other:'Other'};"
           + "\nconst VISIT_WORDS=new Set(['callback','call','back','reinstall','install','takedown','teardown','part','fix','visit','b']);\n"
           + "\n".join(js_function(n) for n in [*HELPERS, *extra]) + "\n" + body)
    return json.loads(run_js(src))


ROWS = """
const C={
  36:{row:36, name:'Sample, Jane', street:'100 Example St', city:'Houston', st:'TX', zip:'77005', lat:29.71, lon:-95.41},
  12:{row:12, name:'Bourque, Stacey', street:'1 Main St', city:'Houston', st:'TX', zip:'77001', lat:29.7, lon:-95.4},
  13:{row:13, name:'No Address, Client', lat:null, lon:null},
  900015:{row:900015, name:'M Crowd Lake Highlands', synthetic:true, visitType:'Takedown', lat:1, lon:1},
  900039:{row:900039, name:'Jane Sample', synthetic:true, visitType:'Callback', street:'100 Example St, Houston, TX 77005', lat:29.71, lon:-95.41},
  900050:{row:900050, name:'Sample, Jane', synthetic:true, visitType:'Callback', of:36, returnReason:'fix', lat:29.71, lon:-95.41},
};
"""


@needs_node
def test_a_typed_name_finds_the_client_in_any_order():
    out = run("""
      const m=q=>matchExistingClients(q, C, 3);
      console.log(JSON.stringify({
        flipped: m('Jane Sample'), sheet: m('Sample, Jane'), suffix: m('Jane Sample - Callback'),
        callbackWord: m('callback sample'), partial: m('Sampl'), nobody: m('Zed Zulu'),
        tooShort: m('ec'), noAddress: m('No Address'), onlyVisitWords: m('callback'),
      }));
    """, prelude=ROWS)
    # One row per client, its main stop (not the callback rows).
    assert out["flipped"] == [36] and out["sheet"] == [36] and out["suffix"] == [36]
    assert out["callbackWord"] == [36] and out["partial"] == [36]
    assert out["nobody"] == [] and out["tooShort"] == [] and out["onlyVisitWords"] == []
    assert out["noAddress"] == []   # nothing to drive to


@needs_node
def test_a_callback_is_titled_and_counted_as_an_extra_visit():
    out = run("""
      console.log(JSON.stringify({
        title: C[900050].name+visitSuffix(C[900050]),
        oldTyped: C[900039].name+visitSuffix(C[900039]),
        main: visitSuffix(C[36]), takedown: visitSuffix(C[900015]),
        already: visitSuffix({name:'Sample, Jane - Callback', visitType:'Callback'}),
        noReason: visitSuffix({name:'Sample, Jane', visitType:'Callback', of:36}),
        bought: visitSuffix({name:'Sample, Jane', visitType:'Callback', of:36, returnReason:'bought_more'}),
        extra: [36, 900050, 900039, 900015].map(r=>extraVisitRow(r, C)),
      }));
    """, prelude=ROWS)
    assert out["title"] == "Sample, Jane - Return trip (Fix)"
    assert out["noReason"] == " - Return trip (Callback)" and out["bought"] == " - Return trip (Bought more)"
    assert out["oldTyped"] == "Jane Sample - Callback"
    assert out["main"] == "" and out["takedown"] == "" and out["already"] == ""
    # The linked callback is an extra visit (its hold / not-installing don't
    # write to the card, its billing line folds into the client's); the old
    # typed-as-new one has no twin under its name, so it works as before.
    assert out["extra"] == [False, True, False, False]


@needs_node
def test_the_callback_reuses_the_clients_drive_legs():
    out = run("""
      const D=[[0,10,20],[11,0,30],[21,31,0]];
      console.log(JSON.stringify({
        built: legsFromRow({row:1}, 1, D, 3),
        added: legsFromRow({outRow:[1,2], inCol:[3,4]}, 5, D, 3),
        none: legsFromRow({row:9}, null, D, 3),
        addr: [fullAddressOf(C[36]), fullAddressOf(C[900039])],
      }));
    """, prelude=ROWS)
    assert out["built"] == {"outRow": [11, 0, 30], "inCol": [10, 0, 31]}
    assert out["added"] == {"outRow": [1, 2], "inCol": [3, 4]}
    assert out["none"] == {"outRow": None, "inCol": None}
    assert out["addr"] == ["100 Example St, Houston, TX 77005", "100 Example St, Houston, TX 77005"]


@needs_node
def test_a_callback_never_moves_the_cards_install_date():
    out = json.loads(run_js(js_function("boardDatesByClient") + """
      const info=r=>({36:{key:'sample jane', name:'Sample, Jane', id:7, visitType:'Standard'},
                      900050:{key:'sample jane', name:'Sample, Jane', id:7, visitType:'Callback'}})[r];
      const days=[{date:'2026-11-18', stops:[900050]}, {date:'2026-11-10', stops:[36]},
                  {date:'2026-12-28', stops:[900050]}];
      console.log(JSON.stringify([boardDatesByClient(days, '2026-12-25', info),
        boardDatesByClient([{date:'2026-11-05', stops:[900050]}], '2026-12-25', info)]));
    """))
    assert out[0] == {"sample jane": {"name": "Sample, Jane", "id": 7, "install": "2026-11-10"}}
    assert out[1] == {}


@needs_node
def test_the_client_keeps_its_card_facts_with_a_callback_on_the_board():
    out = json.loads(run_js("const CARD_ROLE_KEYS=['leads','specialty','designer','general'];\n" + "\n".join(
        js_function(n) for n in ["normName", "validHours", "normRoleNeed", "roleSum", "isTakedownVisit",
                                 "isCallbackVisit", "isExtraVisit", "cardBoxes", "applyCardFactsTo"]) + """
      const C={36:{row:36, name:'Sample, Jane', h26:1.62, basis:'est', boxes:10, people:6},
               900050:{row:900050, name:'Sample, Jane', h26:1, synthetic:true, visitType:'Callback', of:36, boxes:'', people:null}};
      applyCardFactsTo(C, [{id:7, name:'Sample, Jane', sheet_name:'Sample, Jane', former_names:[], est_hours:2, boxes:12}]);
      console.log(JSON.stringify([C[36].h26, C[36].boxes, C[900050].h26, C[900050].boxes]));
    """))
    # Before, the two same-name rows made the card match neither.
    assert out == [2, 12, 1, ""]


def test_the_link_is_saved_and_restored():
    assert "'outRow','inCol','of','returnReason']" in TEMPLATE   # known fields, kept on merges
    assert TEMPLATE.count("outRow:c.outRow, inCol:c.inCol, ...(c.of!=null ? {of:c.of} : {}),\n     ...(c.returnReason ? {returnReason:c.returnReason} : {})}));") == 3   # snapshot, undo steps, notebook
    i = TEMPLATE.index("function addSyntheticClientSync(")
    add = TEMPLATE[i:i + 2600]
    assert "of, business, returnReason}" in add and "C[r].returnReason = String(returnReason);" in add and "if(of!=null && of!=='' && Number.isFinite(+of)) C[r].of = +of;" in add
    assert "phone:(base&&base.phone)||''" in add and "bus:(base&&base.bus)||classifyBusiness(name)" in add


def test_three_ways_in_add_a_return_trip_for_the_client():
    # 1. the stop card's chip, 2. the find box's "+ Return trip", 3. "+ New client" offering it.
    peek = js_function("openStopPeek")
    assert 'id="pkcallback"' in peek and "<span>Return trip</span>" in peek
    assert "openCallbackDialog(row)" in peek
    assert 'class="srcb" data-cb=' in js_function("renderSearch") and "+ Return trip</button>" in js_function("renderSearch")
    assert "openCallbackDialog(+b.dataset.cb)" in js_function("wireSearchRows")
    assert "document.getElementById('ncname').addEventListener('input', ncRenderMatches);" in TEMPLATE
    m = js_function("ncRenderMatches")
    assert "Add a return trip for ${esc(C[r].name)}" in m and "ncSetCallback(+b.dataset.cbfor)" in m
    # The dialog adds it to the client: no address lookup, the client's row.
    assert "const row=addCallbackVisit(ncCallbackOf, {hours, people, notes, reason:document.getElementById('ncreason').value});" in TEMPLATE
    for v, label in (("callback", "Callback"), ("bought_more", "Bought more"), ("fix", "Fix / repair"), ("unfinished", "Unfinished")):
        assert f'<option value="{v}">{label}</option>' in TEMPLATE
    i = TEMPLATE.index("function addCallbackVisit(")
    cb = TEMPLATE[i:i + 1000]
    assert "name:b.sheetName||b.name, of:b.row" in cb and "visitType:'Callback'" in cb
    assert "returnReason:normReturnReason(reason)" in cb
    # Every "+ New client" opening starts as a new client again.
    assert "ncSetCallback(null);" in js_function("openPutBackDialog")


def test_the_board_card_sheet_and_log_title_it_as_a_callback():
    assert "${peekEsc(stopName(r))}${alertIconHTML(r)}" in TEMPLATE      # board stop row
    assert "<h3>${esc(stopName(row))}" in js_function("openStopPeek")    # stop card
    assert "${esc(stopName(r))}${stopPin[r]?" in TEMPLATE                # crew sheet
    assert "moves.push({row, name:C[row].name" not in TEMPLATE           # history / Install Changes
    assert "name:stopName(row)" in TEMPLATE


def test_no_em_dashes_in_the_new_on_screen_text():
    for name in ("ncSetCallback", "ncRenderMatches", "openCallbackDialog"):
        assert "—" not in js_function(name)


@needs_node
def test_a_callback_does_not_borrow_the_install_box_count():
    out = json.loads(run_js("\n".join(js_function(n) for n in ["parseBoxes", "isCallbackVisit", "cardBoxesFor"]) + """
      const C={36:{name:'Sample, Jane', boxes:10}, 900050:{name:'Sample, Jane', boxes:'', visitType:'Callback'},
               900015:{name:'Sample, Jane', boxes:'', visitType:'Takedown'}};
      console.log(JSON.stringify([cardBoxesFor(900050).boxes, cardBoxesFor(900015).boxes]));
    """))
    assert out == [None, 10]   # a takedown still takes the install's boxes back


@needs_node
def test_a_return_trip_and_a_reordered_spelling_find_the_clients_card():
    """The duplicate cards: editing an added stop with no exact-name card
    created a new card. Now a return trip finds its client's card through
    `of`, and an older stop typed as "Jane Sample" finds "Sample, Jane"."""
    out = json.loads(run_js("\n".join(js_function(n) for n in ["normName", "nameTokensKey", "appClientFor"]) + """
      let _tokIdx=null, _tokIdxOf=null, _tokIdxN=-1;
    """ + js_function("tokenClientIndex") + """
      const jane={id:7, name:'Sample, Jane'}, twinA={id:8, name:'Lee, Pat'}, twinB={id:9, name:'Pat Lee'};
      const clientDirectory=new Map([['sample jane', jane], ['lee pat', twinA], ['pat lee', twinB]]);
      const C={36:{name:'Sample, Jane'}, 900050:{name:'Renamed Since', synthetic:true, visitType:'Callback', of:36},
               900039:{name:'Jane Sample', synthetic:true, visitType:'Callback'},
               900060:{name:'Jane Sample - Callback', synthetic:true},
               900070:{name:'Lee Pat Junior', synthetic:true}, 50:{name:'Jane Sample'}};
      console.log(JSON.stringify([36, 900050, 900039, 900060, 900070, 50].map(r=>(appClientFor(r)||{}).id||null)));
    """))
    # Built rows still need an exact name (50); two cards with the same words
    # (Lee, Pat / Pat Lee) match neither.
    assert out == [7, 7, 7, 7, None, None]


def test_a_visit_never_creates_a_client_card_of_its_own():
    i = TEMPLATE.index("// A return trip or takedown row is a visit, never a client of its")
    assert "if(isExtraVisit(C[row])) throw" in TEMPLATE[i:i + 400]
    assert TEMPLATE.index("if(isExtraVisit(C[row])) throw") < TEMPLATE.index("`/api/clients/create`")
