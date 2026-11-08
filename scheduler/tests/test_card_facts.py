"""The client card's boxes, hours and people on the schedule (Comment #28).

Joy, 11/04: Stacey Bourque's card says 29 boxes, 5h, 1 lead, 1 specialty and
7 general (9 people), but her 12/01 stop still showed the build's 14 people
(2/2/0/10) and 4.86h, and taking her second crew off left Crew 1 needing all
14. DATA can't change, so the page lays the card's app-edited values over the
build at runtime (GET /api/install-schedule/card-facts): card edit > the
board's hoursOverride > the build. These run the template's own functions in
node with small stubs, plus source pins for the wiring.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

PRELUDE = """
const CARD_ROLE_KEYS=['leads','specialty','designer','general'];
"""
FNS = ["normName", "validHours", "fmtHrs", "applyHoursOverrideTo", "normRoleNeed", "roleSum",
       "isTakedownVisit", "cardBoxes", "applyCardFactsTo", "ownHours", "ownPeople", "setOwnHours",
       "perCrewPeople", "peopleChipText", "cardFactsNote", "jointN", "effH", "dayNeed"]


def run(body, extra=()):
    src = PRELUDE + "\n".join(js_function(n) for n in [*FNS, *extra]) + "\n" + body
    return json.loads(run_js(src))


# Live-shaped rows: Stacey's install stop, an M Crowd install plus its added
# takedown visit (same name), and two added stops for one client.
BOARD = """
  const C={
    12:{row:12, name:'Bourque, Stacey', h26:4.86, basis:'2025 real', boxes:29, people:14,
        roleNeed:{leads:2, specialty:2, designer:0, general:10}},
    63:{row:63, name:'M Crowd Lake Highlands', h26:7.29, basis:'est x0.81', boxes:4, people:14,
        roleNeed:{leads:2, specialty:2, designer:0, general:10}},
    70:{row:70, name:'Ecklund, Michol', h26:3, basis:'2025 real', boxes:8, people:5,
        roleNeed:{leads:1, specialty:0, designer:0, general:4}},
    900006:{row:900006, name:'Crane Solutions', h26:1, synthetic:true, visitType:'Standard', boxes:'', people:null},
    900007:{row:900007, name:'Crane Solutions', h26:3.5, synthetic:true, visitType:'Standard', boxes:'', people:5},
    900015:{row:900015, name:'M Crowd Lake Highlands', h26:2, synthetic:true, visitType:'Takedown', boxes:'', people:14},
    900034:{row:900034, name:'Hollon, Melissa', h26:3, synthetic:true, visitType:'Standard', boxes:'', people:null},
  };
  const SHEET={};
  const STACEY={id:175, name:'Bourque, Stacey', sheet_name:'Bourque, Stacey', former_names:[],
    est_hours:5, role_need:{leads:1, specialty:1, designer:0, general:7}};
  const FACTS=[STACEY,
    {id:269, name:'M Crowd Lake Highlands', sheet_name:'M Crowd Lake Highlands', former_names:[], est_hours:4},
    {id:400, name:'Crane Solutions', sheet_name:null, former_names:[], est_hours:9},
    {id:401, name:'Hollon, Melissa', sheet_name:null, former_names:[], est_hours:3.5,
     role_need:{leads:1, general:3}},
  ];
  const pick=r=>({h26:C[r].h26, basis:C[r].basis, people:C[r].people, roleNeed:C[r].roleNeed,
                  boxes:C[r].boxes, edited:!!C[r].hoursEdited, card:C[r].card||null});
"""


@needs_node
def test_card_wins_over_the_board_edit_which_wins_over_the_build():
    out = run(BOARD + """
      const a={};
      applyHoursOverrideTo(C, SHEET, {'12':5}); applyCardFactsTo(C, []);
      a.override=pick(12);
      applyHoursOverrideTo(C, SHEET, {'12':5}); applyCardFactsTo(C, FACTS);
      a.card=pick(12);
      // The card's hours are cleared later: the board's 5h edit is back.
      const noHours=[{...STACEY, est_hours:undefined}];
      applyHoursOverrideTo(C, SHEET, {'12':5}); applyCardFactsTo(C, noHours);
      a.cardPeopleOnly=pick(12);
      // ...and with no board edit either: the build's 4.86h.
      applyHoursOverrideTo(C, SHEET, {}); applyCardFactsTo(C, []);
      a.build=pick(12);
      console.log(JSON.stringify(a));
    """)
    assert out["override"]["h26"] == 5 and out["override"]["edited"] is True
    assert out["override"]["people"] == 14
    card = out["card"]
    assert (card["h26"], card["basis"], card["people"], card["edited"]) == (5, "client card", 9, False)
    assert card["roleNeed"] == {"leads": 1, "specialty": 1, "designer": 0, "general": 7}
    assert card["boxes"] == 29                         # boxes not edited on the card: the build's
    assert card["card"]["source"] == "client card"
    assert card["card"]["fields"] == ["est_hours", "role_need"]
    assert card["card"]["was"]["h26"] == 5 and card["card"]["was"]["people"] == 14
    assert out["cardPeopleOnly"]["h26"] == 5 and out["cardPeopleOnly"]["edited"] is True
    assert out["cardPeopleOnly"]["people"] == 9
    assert out["build"] == {"h26": 4.86, "basis": "2025 real", "people": 14, "boxes": 29, "edited": False,
                            "roleNeed": {"leads": 2, "specialty": 2, "designer": 0, "general": 10},
                            "card": None}


@needs_node
def test_card_boxes_and_repeat_applies_are_idempotent():
    out = run(BOARD + """
      const F=[{id:208, name:'Ecklund, Michol', sheet_name:'Ecklund, Michol', former_names:[], boxes:11}];
      applyHoursOverrideTo(C, SHEET, {}); applyCardFactsTo(C, F);
      const once=pick(70);
      applyCardFactsTo(C, F); applyCardFactsTo(C, F);       // a refetch with nothing new
      const thrice=pick(70);
      applyHoursOverrideTo(C, SHEET, {}); applyCardFactsTo(C, F);
      console.log(JSON.stringify([once, thrice, pick(70)]));
    """)
    once, thrice, again = out
    assert once["boxes"] == 11 and once["h26"] == 3 and once["people"] == 5
    assert once == thrice == again


@needs_node
def test_takedown_visits_and_shared_cards_keep_their_own_numbers():
    out = run(BOARD + """
      applyHoursOverrideTo(C, SHEET, {}); applyCardFactsTo(C, FACTS);
      console.log(JSON.stringify({lh:pick(63), td:pick(900015), crane:[pick(900006), pick(900007)],
                                  hollon:pick(900034)}));
    """)
    # The install stop takes the card's 4h; its takedown visit keeps 2h.
    assert out["lh"]["h26"] == 4 and out["lh"]["basis"] == "client card"
    assert out["td"]["h26"] == 2 and out["td"]["card"] is None and out["td"]["people"] == 14
    # Two added stops match one card (two visits): neither takes it.
    assert [c["h26"] for c in out["crane"]] == [1, 3.5]
    assert all(c["card"] is None for c in out["crane"])
    # An added stop that is the card's only stop does.
    assert out["hollon"]["h26"] == 3.5 and out["hollon"]["people"] == 4


@needs_node
def test_a_spelling_two_cards_share_matches_neither():
    out = run(BOARD + """
      const F=[{id:1, name:'Ecklund, Michol', sheet_name:null, former_names:[], est_hours:9},
               {id:2, name:'Ecklund Michol', sheet_name:null, former_names:[], est_hours:8}];
      applyHoursOverrideTo(C, SHEET, {}); applyCardFactsTo(C, F);
      console.log(JSON.stringify(pick(70)));
    """)
    assert out["h26"] == 3 and out["card"] is None


@needs_node
def test_added_stops_save_their_own_hours_and_people_not_the_cards():
    out = run(BOARD + """
      applyHoursOverrideTo(C, SHEET, {}); applyCardFactsTo(C, FACTS);
      const c=C[900034];
      const shown=[c.h26, c.people], own=[ownHours(c), ownPeople(c)];
      // An undo / shared document restores the stop's own 2.5h under the card.
      setOwnHours(c, 2.5);
      const under=[c.h26, ownHours(c)];
      // The card's facts go away: the stop's own hours, people come back.
      applyHoursOverrideTo(C, SHEET, {}); applyCardFactsTo(C, []);
      console.log(JSON.stringify({shown, own, under, after:[c.h26, c.people, c.card||null, ownHours(c)]}));
    """)
    assert out["shown"] == [3.5, 4] and out["own"] == [3, None]
    assert out["under"] == [3.5, 2.5]
    assert out["after"] == [2.5, None, None, 2.5]


@needs_node
def test_without_card_facts_the_board_is_unchanged():
    """No login (or crew / production / offline): no facts, the page is
    exactly the build plus the board's own hours edits, key for key."""
    out = run(BOARD + """
      applyHoursOverrideTo(C, SHEET, {'63':4});
      const before=JSON.stringify(C);
      applyCardFactsTo(C, []); applyCardFactsTo(C, null);
      const same=JSON.stringify(C)===before;
      // Facts arrive, then go away: back to exactly what it was.
      applyHoursOverrideTo(C, SHEET, {'63':4}); applyCardFactsTo(C, FACTS);
      const changed=JSON.stringify(C)!==before;
      applyHoursOverrideTo(C, SHEET, {'63':4}); applyCardFactsTo(C, []);
      console.log(JSON.stringify([same, changed, JSON.stringify(C)===before]));
    """)
    assert out == [True, True, True]


@needs_node
def test_day_need_on_the_joint_stop_and_after_a_crew_comes_off():
    """Stacey's 12/01 stop, two crews: the build's 14 people (2/2/0/10) is 7
    per crew; one crew left needs all 14. With the card's 9 (1/1/0/7) the
    last crew needs 9, and two crews would need 6 each."""
    out = run(BOARD + """
      const joint={id:'2026-12-01|Crew 1|0', stops:[12], half:[12]};
      const alone={id:'2026-12-01|Crew 1|0', stops:[12], half:[]};
      const a=[dayNeed(joint), dayNeed(alone), peopleChipText(C[12], 2), peopleChipText(C[12], 1)];
      applyHoursOverrideTo(C, SHEET, {'12':5}); applyCardFactsTo(C, FACTS);
      a.push(dayNeed(joint), dayNeed(alone), peopleChipText(C[12], 2), peopleChipText(C[12], 1),
             +effH(joint, 12).toFixed(2));
      console.log(JSON.stringify(a));
    """)
    assert out[0] == {"lead": 1, "assist": 1, "gen": 5, "total": 7}
    assert out[1] == {"lead": 2, "assist": 2, "gen": 10, "total": 14}
    assert out[2:4] == ["14 people (7 per crew)", "14 people"]
    assert out[4] == {"lead": 1, "assist": 1, "gen": 4, "total": 6}
    assert out[5] == {"lead": 1, "assist": 1, "gen": 7, "total": 9}
    assert out[6:8] == ["9 people (6 per crew)", "9 people"]
    assert out[8] == 2.5


@needs_node
def test_remove_crew_confirm_states_the_new_need():
    out = run(BOARD + """
      const a=[removeCrewNeedLine(C[12], ['Crew 1'], 2), removeCrewNeedLine(C[12], ['Crew 1','Crew 3'], 3),
               removeCrewNeedLine({people:0}, ['Crew 1'], 2)];
      applyHoursOverrideTo(C, SHEET, {}); applyCardFactsTo(C, FACTS);
      a.push(removeCrewNeedLine(C[12], ['Crew 1'], 2));
      console.log(JSON.stringify(a));
    """, extra=("removeCrewNeedLine",))
    assert out[0] == "\nThis job needs 14 people, so Crew 1 needs all 14 (it was 7 per crew)."
    assert out[1] == "\nThis job needs 14 people, so each crew needs 7 (it was 6 per crew)."
    assert out[2] == ""
    assert out[3] == "\nThis job needs 9 people, so Crew 1 needs all 9 (it was 6 per crew)."
    for line in out:
        assert "—" not in line


@needs_node
def test_the_card_note_says_what_came_from_the_card():
    out = run(BOARD + """
      applyHoursOverrideTo(C, SHEET, {'12':5});
      applyCardFactsTo(C, [{...STACEY, boxes:30}]);
      console.log(JSON.stringify([cardFactsNote(C[12]), cardFactsNote(C[70])]));
    """)
    assert out == ["From the client card: 5h, 9 people (was 14), 30 boxes (was 29)", ""]


@needs_node
def test_the_card_note_says_was_when_the_card_moved_the_hours():
    out = run(BOARD + """
      applyHoursOverrideTo(C, SHEET, {}); applyCardFactsTo(C, FACTS);
      console.log(JSON.stringify(cardFactsNote(C[12])));
    """)
    assert out == "From the client card: 5h (was 4.86h), 9 people (was 14)"


@needs_node
def test_editor_sends_only_changes_and_reset_hands_back_to_the_sheet():
    out = run(BOARD + """
      applyHoursOverrideTo(C, SHEET, {'12':5}); applyCardFactsTo(C, FACTS);
      const rn9={leads:1, specialty:1, designer:0, general:7};
      const a=[
        cardFactChanges(C[12], {h:5, boxes:29, rn:rn9}),                    // nothing changed
        cardFactChanges(C[12], {h:4.5, boxes:null, rn:rn9}),                // hours; blank boxes = no change
        cardFactChanges(C[12], {h:5, boxes:31, rn:{...rn9, general:6}}),
        cardResetBody(C[12].card),
        cardResetBody({fields:['boxes','est_hours'], was:{boxes:'', h26:3}}),
        cardFactFromDetail({id:175, name:'Bourque, Stacey', sheet_name:'Bourque, Stacey'},
          {boxes:29, est_hours:4.5, role_need:rn9, notes:'x', app_edits:{est_hours:'T', notes:'T'}}),
        cardFactFromDetail({id:175, name:'Bourque, Stacey'}, {boxes:29, app_edits:{notes:'T'}}),
      ];
      console.log(JSON.stringify(a));
    """, extra=("cardFactChanges", "cardResetBody", "cardFactFromDetail"))
    assert out[0] == {}
    assert out[1] == {"est_hours": 4.5}
    assert out[2] == {"boxes": 31, "role_need": {"leads": 1, "specialty": 1, "designer": 0, "general": 6}}
    # Reset: both facts back to the sheet; the build's 14 people is the
    # fallback, never its calibrated hours.
    assert out[3] == {"fields": {"role_need": {"leads": 2, "specialty": 2, "designer": 0, "general": 10}},
                      "reset": ["est_hours", "role_need"]}
    assert out[4] == {"fields": {}, "reset": ["boxes", "est_hours"]}
    assert out[5] == {"id": 175, "name": "Bourque, Stacey", "sheet_name": "Bourque, Stacey", "former_names": [],
                      "est_hours": 4.5, "edited": {"est_hours": "T"}}
    assert out[6] is None


def test_wiring():
    # Applied on every path that applies the board's hours, after them.
    assert "applyHoursOverrideTo(C, SHEET_HOURS, hoursOverride); applyCardFactsTo(C, cardFacts);" \
        in js_function("applyHoursOverride")
    assert "delete c.cardH;" in js_function("applyHoursOverrideTo")
    # Fetched on sign-in, after every pullShared, and on coming back to the tab.
    assert "/api/install-schedule/card-facts?season=" in js_function("loadCardFacts")
    assert "refreshCardFacts(true);" in js_function("pullShared")
    assert "refreshCardFacts(true);" in TEMPLATE.split("loadDriveLinks().then(()=>{ if(applyLiveClientFields()) render(); });")[1][:200]
    vis = TEMPLATE[TEMPLATE.index("document.addEventListener('visibilitychange'"):][:300]
    assert "else refreshCardFacts();" in vis
    # Added stops arriving with the shared state get the card too.
    assert "applyCardFactsTo(C, cardFacts);" in js_function("restoreSyntheticClients")
    # Never saved: shared state, undo and the notebook carry each stop's own values.
    snap = js_function("snapshot")
    assert "hours:ownHours(c)" in snap and "people:ownPeople(c)" in snap
    assert "hours:ownHours(c)" in js_function("exportNotebook")
    assert "[c.row, ownHours(c)]" in js_function("stateBlob")
    assert "setOwnHours(C[r], validHours(h))" in js_function("restoreBlob")
    assert "setOwnHours(c, h);" in js_function("setStopHours")
    # The people chip and the card note in This job.
    facts = js_function("peekFactsHTML")
    assert "peopleChipText(c, d ? jointN(d,row) : 1)" in facts and "cardFactsNote(c)" in facts
    # The editor saves to the card through the Clients season route, staff+ only.
    assert "/api/clients/${ac.id}/seasons/" in js_function("putCardFacts")
    gate = js_function("canEditCardFacts")
    assert "canEditHours()" in gate and "!isTakedownVisit(c)" in gate and "cardTwinRows(row).length===1" in gate
    hrs = js_function("peekHoursHTML")
    assert "if(cardEdit) return cardFactsFormHTML(row);" in hrs
    form = js_function("cardFactsFormHTML")
    for k in ("pkhrsin", "pkfbox", "pkfr-${k}"):
        assert k in form
    wire = js_function("wirePeekHours")
    assert "putCardFacts(row, cardResetBody(c.card))" in wire
    assert "putCardFacts(row, {fields})" in wire
    # Remove crew states the new need, then offers This job, no recount.
    crews = js_function("wirePeekCrews")
    assert "removeCrewNeedLine(C[row], rest.map(crewTitle), rest.length+1)" in crews
    assert "openJobEditor(row, keep.id)" in crews
    # No em dashes in what staff read.
    for fn in ("cardFactsFormHTML", "cardFactsNote", "cardFactsErrorMessage", "removeCrewNeedLine",
               "peopleChipText", "peekHoursHTML", "wirePeekHours"):
        assert "—" not in js_function(fn), fn
