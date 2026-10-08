"""The schedule page inside the app (user, 2026-10-08).

The app's nav has Install Schedule / Calendar / Staffing / Roster entries
that all keep ONE copy of this page loaded and tell it which view to show
(frontend/src/utils/installViews.ts, pages/InstallSchedule.tsx). These pin
the page's side of that contract, the phone layout rules that go with it,
and that the page's script still parses (a syntax error, or a duplicate
`const`, kills the whole page while the server still answers 200).
"""
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(HERE)
TEMPLATE = open(os.path.join(HERE, "review_template.html"), encoding="utf-8").read()
VIEWS_TS = os.path.join(REPO, "frontend", "src", "utils", "installViews.ts")


def main_script():
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", TEMPLATE, re.S)
    return max(scripts, key=len)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_page_script_parses(tmp_path):
    js = tmp_path / "page.js"
    js.write_text(main_script(), encoding="utf-8")
    out = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_no_top_level_name_is_declared_twice():
    names = re.findall(r"^(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)", main_script(), re.M)
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, dupes


def test_view_names_match_the_app():
    """The app posts these names; the page must accept every one."""
    if not os.path.exists(VIEWS_TS):
        pytest.skip("frontend not checked out")
    ts = open(VIEWS_TS, encoding="utf-8").read()
    app_views = re.findall(r'\{ view: "(\w+)", path: "(/install-[\w-]+)"', ts)
    assert [v for v, _ in app_views] == ["days", "cal", "staff", "roster"]
    accepted = re.search(r"\[('days','cal','staff','roster')\]\.includes\(v\)", TEMPLATE)
    assert accepted, "applyHostView no longer accepts the app's four view names"


def test_hosted_protocol_both_ways():
    js = main_script()
    assert "window.TBDG_HOSTED" in js and "window.TBDG_VIEW" in js
    assert "type:'tbdg-view'" in js                      # we report our view
    assert "e.data.type!=='tbdg-view'" in js             # and take the host's
    assert "window.tbdgViews = true" in js               # the host checks this
    # setView and the Staffing sub-tabs both report, so the URL follows
    assert re.search(r"function setView\(v\)\{.*?reportView\(\);\n\}", js, re.S)
    assert re.search(r"function renderStaffing\(\)\{\s*syncSearchMode\(\);\s*reportView\(\);", js)


def test_hosted_hides_tab_rows_but_tv_and_standalone_keep_them():
    assert "body.hosted:not(.tv) .viewtog,body.hosted:not(.tv) .stfbar .stftab{display:none!important}" in TEMPLATE
    assert "if(HOSTED) document.body.classList.add('hosted');" in TEMPLATE
    # hosted only when really framed by the app
    assert "const HOSTED = !!window.TBDG_HOSTED && window.parent!==window;" in TEMPLATE


def phone_css():
    """Every rule inside the phone breakpoint blocks."""
    out, i = [], 0
    while True:
        i = TEMPLATE.find("@media (max-width:767px){", i)
        if i < 0:
            return "\n".join(out)
        depth, j = 0, TEMPLATE.index("{", i)
        for k in range(j, len(TEMPLATE)):
            depth += {"{": 1, "}": -1}.get(TEMPLATE[k], 0)
            if depth == 0:
                out.append(TEMPLATE[j:k])
                break
        i = k


def test_phone_header_is_one_line_without_stats():
    css = phone_css()
    assert "body.apple .daystats{display:none}" in css
    assert "body.apple #side > .printbtn.ovprintall{display:none}" in css
    # one printer on phones: the toolbar's (user, 10/8) -- the header line has none
    assert ".ovprint{" not in css and ".ovprint ." not in css
    assert "className='ovprint'" not in TEMPLATE
    # the first date sits right under the one-line header
    assert "body.apple #side .ovdate.ovfirst{margin-top:0}" in css
    # the stats box stays on tablets and desktops
    assert "body.apple .daystats{display:flex" in TEMPLATE
    assert "dh.className='ovdate'+(dt===dates[0]?' ovfirst':'')" in TEMPLATE


def test_phone_continuous_list_hooks_into_render():
    js = main_script()
    assert "phoneNormalize();" in js
    assert "phoneAfterRender(phPrevScope, phPrevTop); drawDate(phoneMapDate());" in js
    assert "side.addEventListener('scroll', phoneSpy" in js
    # overview headings carry their date for the list to scroll to
    assert "an.className='ovanchor'; an.dataset.date=dt;" in js
