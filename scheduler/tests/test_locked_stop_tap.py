"""A locked (date confirmed) stop must open on a tap, on a phone too, so its
address shows and can be tapped for maps without unlocking it (Comments #34).

The cause was on iOS Safari: a stop that can be dragged is unselectable
(WebKit gives draggable=true elements user-select:none), but a locked stop is
draggable=false, so its text was selectable and Safari read each tap as the
start of a text selection and never sent the click. The rows now opt out of
text selection themselves. Locking still blocks dragging and moving.
"""
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = open(os.path.join(HERE, "review_template.html"), encoding="utf-8").read()
STYLE = re.sub(r"/\*.*?\*/", "", TEMPLATE[:TEMPLATE.index("</style>")], flags=re.S)


def css_rules(selector_part):
    """Every top-level-ish CSS rule whose selector list names selector_part."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", STYLE):
        sels = [s.strip() for s in m.group(1).split(",")]
        if selector_part in sels:
            out.append(m.group(2))
    return out


def test_stop_rows_are_not_text_selectable():
    for sel in (".stop", ".calev", ".agrow"):
        body = " ".join(css_rules(sel))
        assert "-webkit-user-select:none" in body, sel
        assert re.search(r"(^|[;\s])user-select:none", body), sel


def stop_row_builder():
    i = TEMPLATE.index("const isConfirmed=confirmed.has(r);")
    return TEMPLATE[i:TEMPLATE.index("card.appendChild(el);", i)]


def test_tapping_a_locked_row_opens_its_card():
    src = stop_row_builder()
    click = src[src.index("el.onclick=()=>{"):src.index("el.querySelector('.ordbtn.up')")]
    assert "openStopPeek(r, d.id)" in click
    assert "isConfirmed" not in click and "confirmed" not in click


def test_locking_still_blocks_dragging_and_moving():
    src = stop_row_builder()
    assert "el.draggable=!READONLY && !isConfirmed;" in src
    assert "if(isConfirmed){ e.preventDefault(); return; }" in src
    assert "if(!isConfirmed) openSlotFinder(r);" in src
    assert "mv.disabled = confirmed.has(row);" in TEMPLATE


def test_address_link_does_not_depend_on_the_lock():
    i = TEMPLATE.index("function contactViewHTML(row, editable){")
    body = TEMPLATE[i:TEMPLATE.index("\n}\n", i)]
    assert "ln(mapsHref(addr), IC.pin, peekEsc(addr))" in body
    assert "confirmed" not in body
