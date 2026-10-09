"""Install Schedule page: touch taps, fold chevrons and the card's print icon
(user, 2026-10-09).

- iPhone Safari turns a tap into mouseover + click. If the hover changes what
  is on screen it keeps the hover and drops the click, so the stop row's hover
  styles only apply where a real pointer can hover, and the staff-alert card
  doesn't open from a tap's emulated mouseover.
- Every fold uses one chevron: right when closed, down when open.
- The stop card's "Print sheet" is a printer icon like the other print buttons.
"""
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = open(os.path.join(HERE, "review_template.html"), encoding="utf-8").read()
STYLE = TEMPLATE[TEMPLATE.index("<style"):TEMPLATE.index("</style>")]


def top_level_rules(css):
    """Rules outside any @media block, as (selector, body) pairs."""
    out, depth, buf, i = [], 0, "", 0
    sel = ""
    while i < len(css):
        ch = css[i]
        if ch == "{":
            if depth == 0:
                sel = buf.strip()
            depth += 1
            buf = ""
        elif ch == "}":
            depth -= 1
            if depth == 0:
                out.append((sel, buf))
            buf = "" if depth == 0 else buf
        else:
            buf += ch
        i += 1
    return out


def unguarded_hover_selectors():
    sels = []
    for sel, _ in top_level_rules(re.sub(r"/\*.*?\*/", "", STYLE, flags=re.S)):
        if sel.startswith("@"):
            continue
        sels += [s.strip() for s in sel.split(",") if ":hover" in s]
    return sels


def test_stop_row_hover_only_with_a_real_pointer():
    bad = [s for s in unguarded_hover_selectors()
           if re.search(r"\.(stop|ordbtn|ordgrip|mv|salert|cautoorder)\b", s)]
    assert bad == [], bad
    assert "@media (hover:hover){ .stop:hover{" in STYLE
    assert "@media (hover:hover){ body.apple .stop:hover{" in STYLE


def test_alert_card_ignores_a_taps_emulated_mouseover():
    i = TEMPLATE.index("document.addEventListener('mouseover', e=>{")
    assert "if(tapEmulatedHover()) return;" in TEMPLATE[i:i + 120]
    assert "salertPtrAt=Date.now()" in TEMPLATE


def test_every_fold_uses_one_chevron_right_closed_down_open():
    # Card folds: the plain down chevron, turned right while closed.
    assert '<span class="pkfold-c foldchev" aria-hidden="true">${IC.chev}</span>' in TEMPLATE
    assert ".pkfold:not([open])>summary .foldchev{transform:rotate(-90deg)}" in STYLE
    assert "rotate(180deg)" not in STYLE[STYLE.index(".pkfold-c"):STYLE.index(".pkfold-b")]
    # Date list (Overview / months): same chevron and class.
    assert "chev.className='dmonchev foldchev'; chev.setAttribute('aria-hidden','true'); chev.innerHTML=IC.chev;" in TEMPLATE
    assert "body.apple .dmon.shut .dmonchev{transform:rotate(-90deg)}" in STYLE
    # Staffing lists: the SVG chevron instead of a text triangle.
    assert '<summary><span class="foldchev" aria-hidden="true">${IC.chev}</span>' in TEMPLATE
    assert "\\25B8" not in STYLE
    # One animation for all of them.
    assert STYLE.count("transition:transform .22s cubic-bezier(0.23,1,0.32,1)}") >= 1
    assert re.search(r"\.foldchev\{[^}]*transition:transform \.22s", STYLE)
    assert "chevD" not in TEMPLATE


def test_card_print_sheet_is_a_printer_icon():
    assert '<button id="peekprint" class="picon" title="Print sheet" aria-label="Print sheet"></button>' in TEMPLATE
    assert ">Print sheet</button>" not in TEMPLATE
    assert "prBtn.innerHTML=IC.print" in TEMPLATE
    m = re.search(r"#peekprint\.picon\{([^}]*)\}", STYLE)
    assert m and "min-width:40px" in m.group(1) and "min-height:40px" in m.group(1)
