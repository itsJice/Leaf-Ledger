"""The roster's double-click popup (Edit installer, #perdlg) has a
"Mark inactive" / "Mark active" button with an in-page confirm.

User, 2026-10-30: "mark as inactive needs to be on the pop up window on the
roster when you double click someones name."

It does exactly what the roster panel's existing button does
(togglePersonActive), never uses the browser's confirm(), and keeps the
popup open so unsaved edits in the form survive. FAKE people only.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def popup_block():
    """drawPerActive() plus the three button handlers that follow it."""
    start = TEMPLATE.index("function drawPerActive(")
    end = TEMPLATE.index("document.getElementById('peractyes').onclick")
    end = TEMPLATE.index("\n};", end) + 3
    return TEMPLATE[start:end]


DOM = """
const els={};
const el=id=>els[id]||(els[id]={id, hidden:false, textContent:'', onclick:null,
  _cls:new Set(), classList:{toggle(c,on){ on?els[id]._cls.add(c):els[id]._cls.delete(c); }}});
const document={getElementById:el};
let confirmCalls=0; globalThis.confirm=()=>{ confirmCalls++; return true; };
let undos=0, saves=0, renders=0;
const roBlocked=()=>false, pushUndo=()=>undos++, persist=()=>saves++, render=()=>renders++;
const shiftsFor=id=>id==='p1'?[{},{}]:[];
let editingPerson=null;
const snap=()=>({btn:el('peractive').textContent, hidden:el('peractive').hidden,
  red:el('peractive')._cls.has('off'), confirm:!el('peractconfirm').hidden,
  msg:el('peractmsg').textContent, yes:el('peractyes').textContent});
"""


def run(body):
    src = DOM + js_function("togglePersonActive") + "\n" + js_function("perActiveLabels") \
        + "\n" + popup_block() + "\n" + body
    return json.loads(run_js(src))


def test_button_is_in_the_double_click_popup():
    dlg = TEMPLATE[TEMPLATE.index('<dialog id="perdlg">'):]
    dlg = dlg[:dlg.index("</dialog>")]
    for i in ("peractive", "peractconfirm", "peractyes", "peractno"):
        assert f'id="{i}"' in dlg
    # opening the popup draws the button for that person
    assert "drawPerActive();" in js_function("openPersonDlg")


def test_mark_inactive_then_active_with_in_page_confirm():
    out = run("""
      const p={id:'p1', name:'Fake Person', active:true};
      editingPerson=p; drawPerActive();
      const s0=snap();
      el('peractive').onclick();               // ask
      const s1=snap(), still=p.active;
      el('peractno').onclick();                // back out: nothing changes
      const s2=snap(), afterNo=[p.active, undos, saves];
      el('peractive').onclick(); el('peractyes').onclick();   // confirm
      const s3=snap(), afterYes=[p.active, undos, saves, renders];
      el('peractive').onclick(); const s4=snap(); el('peractyes').onclick();
      console.log(JSON.stringify({s0, s1, still, s2, afterNo, s3, afterYes, s4,
        back:p.active, undos, confirmCalls}));
    """)
    assert out["s0"] == {"btn": "Mark inactive", "hidden": False, "red": True,
                         "confirm": False, "msg": "", "yes": ""}
    assert out["s1"]["confirm"] is True
    assert out["s1"]["msg"] == "Mark Fake Person inactive? They are still on 2 shifts."
    assert out["s1"]["yes"] == "Yes, mark inactive"
    assert out["still"] is True                       # asking alone changes nothing
    assert out["s2"]["confirm"] is False and out["afterNo"] == [True, 0, 0]
    assert out["afterYes"] == [False, 1, 1, 1]        # same path as the panel button
    assert out["s3"]["btn"] == "Mark active" and out["s3"]["red"] is False
    assert out["s3"]["confirm"] is False and out["s3"]["hidden"] is False
    assert out["s4"]["msg"] == "Mark Fake Person active again?"
    assert out["s4"]["yes"] == "Yes, mark active"
    assert out["back"] is True and out["undos"] == 2
    assert out["confirmCalls"] == 0                   # never the browser's confirm()


def test_hidden_when_adding_a_new_person():
    out = run("editingPerson=null; drawPerActive(); console.log(JSON.stringify(snap()))")
    assert out["hidden"] is True and out["confirm"] is False


def test_no_browser_confirm_in_the_popup_code():
    assert not re.search(r"\bconfirm\(", popup_block() + js_function("perActiveLabels"))
