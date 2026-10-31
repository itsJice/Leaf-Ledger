"""The global "mousedown outside an open dialog closes it" handler must not
treat a click on an element that a handler just removed from the page as a
click outside. Picking a New client address suggestion re-renders the list,
which detached the clicked row, and the dialog closed and lost the typed name
(staff video, 2026-10-30). Runs the template's real handler in node against
minimal fake DOM objects.
"""
import json
import os
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = open(os.path.join(HERE, "review_template.html"), encoding="utf-8").read()
NODE = shutil.which("node")


def dialog_mousedown_handler():
    """The document mousedown listener that walks dialog[open]."""
    mark = "document.addEventListener('mousedown', e=>{\n"
    i = TEMPLATE.index(mark)
    while "dialog[open]" not in TEMPLATE[i:i + 600]:
        i = TEMPLATE.index(mark, i + 1)
    return TEMPLATE[i:TEMPLATE.index("\n});\n", i) + len("\n});\n")]


def closed_after(target):
    src = """
let handler=null;
const document={
  addEventListener:(type, fn)=>{ if(type==='mousedown') handler=fn; },
  querySelectorAll:()=>[dlg],
};
const inside={isConnected:true, closest:()=>null};
const detached={isConnected:false, closest:()=>null};
const outside={isConnected:true, closest:()=>null};
const dlg={id:'ncdlg', closed:false, classList:{contains:()=>false},
  contains:t=>t===inside, close(){ this.closed=true; }};
%s
handler({target:{inside, detached, outside}[%s]});
console.log(JSON.stringify(dlg.closed));
""" % (dialog_mousedown_handler(), json.dumps(target))
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(src)
    try:
        out = subprocess.run([NODE, f.name], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)
    finally:
        os.unlink(f.name)


@pytest.mark.skipif(not NODE, reason="node not installed")
@pytest.mark.parametrize("target, closes", [
    ("inside", False),
    ("detached", False),   # re-rendered suggestion row: not "outside"
    ("outside", True),
])
def test_dialog_outside_click(target, closes):
    assert closed_after(target) is closes
