"""Teams builder: pan the board sideways from anywhere over it.

User, 2026-10-30: "with my cursor anywhere in this pane i should be able to
pan right or left". Sideways swipes only worked over the column headers: each
team's list (.tblist) was overflow-y:auto, which makes overflow-x auto too,
with overscroll-behavior:contain on both axes, so a swipe over a card or an
empty column was swallowed by the list instead of reaching the board.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")


def css_rule(selector):
    m = re.search(r"^" + re.escape(selector) + r"\{([^}]*)\}", TEMPLATE, re.M)
    assert m, selector
    return m.group(1)


def test_team_lists_hand_sideways_scroll_to_the_board():
    rule = css_rule(".tblist")
    assert "overflow-x:hidden" in rule and "overflow-y:auto" in rule
    assert "overscroll-behavior-x:auto" in rule and "overscroll-behavior-y:contain" in rule
    assert "overscroll-behavior:contain" not in rule
    # the board itself still keeps a swipe from going Back
    assert "overscroll-behavior:contain" in css_rule(".tbboard")


def test_wheel_handler_is_not_passive_and_skips_menus_and_phones():
    i = TEMPLATE.index("teamdlg.addEventListener('wheel'")
    block = TEMPLATE[i:TEMPLATE.index("}, {passive:false});", i)]
    assert "tbBoardPans(board)" in block           # stacked phone columns: nothing to pan
    assert ".tbmenu,select" in block
    assert "e.ctrlKey" in block                     # pinch zoom is left alone
    assert "e.shiftKey" in block
    assert "tbCanScrollY(" in block                 # a list that can scroll keeps the wheel
    assert "tbColsStacked()" in js_function("tbBoardPans")


def test_grab_to_pan_never_starts_on_cards_grips_buttons_or_fields():
    skip = re.search(r"^const TB_PAN_SKIP='([^']*)';", TEMPLATE, re.M).group(1).split(",")
    for sel in (".tbc", ".tbcolgrip", "[data-colgrip]", "button", "input", "select", "textarea", ".tbmenu"):
        assert sel in skip
    down = js_function("tbPanDown")
    assert "!=='mouse'" in down                      # touch keeps native scrolling
    assert "tb.drag" in down and "tb.pend" in down   # never during a person or column drag
    assert "preventDefault" not in down              # a press still blurs a rename / focuses
    assert "tbPanDown" in js_function("tbWire")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_wheel_px_converts_lines_and_pages():
    out = json.loads(run_js(js_function("tbWheelPx") + """
      console.log(JSON.stringify([tbWheelPx(120,0,900), tbWheelPx(3,1,900), tbWheelPx(1,2,900), tbWheelPx(1,2,0)]));
    """))
    assert out == [120, 48, 900, 800]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_can_scroll_y_looks_up_to_the_board_only():
    out = json.loads(run_js(js_function("tbCanScrollY") + """
      globalThis.getComputedStyle=el=>({overflowY:el.oy||'visible'});
      const board={nodeType:1};
      const list={nodeType:1, oy:'auto', scrollHeight:500, clientHeight:200, scrollTop:0, parentElement:board};
      const card={nodeType:1, scrollHeight:30, clientHeight:30, parentElement:list};
      const head={nodeType:1, scrollHeight:30, clientHeight:30, parentElement:board};
      const r={};
      r.downTop=tbCanScrollY(card, board, 100);
      r.upTop=tbCanScrollY(card, board, -100);
      list.scrollTop=300;
      r.downBottom=tbCanScrollY(card, board, 100);
      r.upBottom=tbCanScrollY(card, board, -100);
      r.header=tbCanScrollY(head, board, 100);
      console.log(JSON.stringify(r));
    """))
    assert out == {"downTop": True, "upTop": False, "downBottom": False, "upBottom": True, "header": False}
