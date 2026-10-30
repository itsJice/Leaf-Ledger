"""Calendar subscribe popup: three links on the one office feed.

10/30/2026: "it needs to be just all dallas, all houston, all everything."
Each row has a Subscribe (webcal://) link and a Copy link (https) button;
Everything is the original feed URL, unchanged. The rows come from the pure
calSubRowsHTML(), rendered here in node. Fake token only.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
PATH = "/api/install-calendar/feed.ics?token=FAKE"
ORIGIN = "https://leaf-ledger.onrender.com"


def const_src(name):
    start = TEMPLATE.index(f"const {name}=")
    end = TEMPLATE.index("];\n", start) + 2
    return TEMPLATE[start:end]


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_popup_renders_three_rows_with_subscribe_and_copy():
    src = "\n".join([js_function("esc"), const_src("CAL_FEEDS"), js_function("calSubRowsHTML"),
                     f"console.log(JSON.stringify(calSubRowsHTML({json.dumps(ORIGIN)}, {json.dumps(PATH)})));"])
    html = json.loads(run_js(src))
    rows = re.findall(r'<div class="calsubrow"><b>(.*?)</b><a [^>]*href="(.*?)"[^>]*>Subscribe</a>'
                      r'<button [^>]*data-url="(.*?)">Copy link</button></div>', html)
    amp = lambda s: s.replace("&", "&amp;")
    host = ORIGIN.replace("https://", "")
    assert rows == [
        ("All Dallas", amp(f"webcal://{host}{PATH}&region=dallas"), amp(f"{ORIGIN}{PATH}&region=dallas")),
        ("All Houston", amp(f"webcal://{host}{PATH}&region=houston"), amp(f"{ORIGIN}{PATH}&region=houston")),
        ("Everything", amp(f"webcal://{host}{PATH}"), amp(f"{ORIGIN}{PATH}")),
    ]
    assert "kind=" not in html


def test_popup_markup_has_list_and_short_how_to():
    pop = TEMPLATE[TEMPLATE.index('<div id="calsubpop"'):]
    pop = pop[:pop.index("</div>\n    </div>")]
    assert '<div id="calsublist"></div>' in pop
    assert "<b>iPhone:</b> tap Subscribe." in pop and "From URL" in pop
    assert "&mdash;" not in pop and "—" not in pop
    # the old single-link buttons are gone
    assert "calsubgoogle" not in TEMPLATE and "calsubapple" not in TEMPLATE


def test_copy_is_delegated_since_rows_are_built_later():
    assert "calSubRowsHTML(origin, j.path)" in js_function("loadCalSub")
    assert "e.target.closest('.calsubcopy')" in TEMPLATE
    assert "document.execCommand('copy')" in TEMPLATE
