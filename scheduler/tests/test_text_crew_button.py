"""Text crew button on the Install Schedule's Staffing shift cards.

10/25/2026: "add a button on here that lets you text crew on a specific
shift." Each Staffing card's footer reads Edit crew, Open day, Text crew,
Details. Text crew opens the shift reminder send flow for just that crew
(the same path as "Text this crew"), starting from the reminder template;
step 2 stays editable and has "Write my own message", a one-off that clears
both boxes and is not remembered. Every send is still an sms: link the user
presses Send on (see test_shift_reminders.py). No real names or numbers.
"""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_shift_reminders import const_block

NODE = shutil.which("node")


def test_card_footer_order_and_text_crew_wiring():
    src = js_function("shiftCardHTML")
    foot = src[src.index('<div class="shcfoot">'):]
    order = [foot.index(s) for s in ("data-staff=", "data-openday=", "Text crew</span>", "data-shdetail=")]
    assert order == sorted(order)                       # Edit crew · Open day · Text crew · Details
    # Just that crew: the reminder flow's date + shift key, wired by
    # wireRemButtons like every other Text reminders button.
    assert 'data-remind="${esc(sh.date)}" data-remkeys="${esc(sh.key)}"' in foot
    assert "${IC.msg}<span>Text crew</span>" in foot
    assert "wireRemButtons(wrap)" in js_function("renderStaffing")
    assert "openReminderDlg(b.dataset.remind, b.dataset.remkeys ? b.dataset.remkeys.split(',') : null)" \
        in js_function("wireRemButtons")


def test_text_crew_is_left_out_for_read_only_and_empty_crews():
    foot = js_function("shiftCardHTML")
    assert "${READONLY || !cv.who.length ? '' : `<button type=\"button\" class=\"shcopen shctext\" data-remind=" in foot
    # and CSS hides every data-remind button for read-only and viewer logins
    assert "body.readonly [data-remind],body.viewonly [data-remind]" in TEMPLATE
    assert "roBlocked()" in js_function("openReminderDlg")


def test_footer_wraps_on_narrow_cards():
    m = re.search(r"^\.shcfoot\{([^}]*)\}", TEMPLATE, re.M)
    assert m and "flex-wrap:wrap" in m.group(1)


def test_days_view_crew_card_already_has_the_equivalent():
    card = js_function("buildDayCard")
    assert "remcardbtn" in card and 'data-remkeys="${esc(sh.key)}"' in card


def test_write_my_own_and_change_message_links_are_wired():
    assert "data-remown" in js_function("remWriteHTML")
    assert "remWriteOwn()" in js_function("remWireWrite")
    assert "data-remedit" in js_function("remSendHTML")
    assert "txt.step=2" in js_function("remWireSend")
    assert "if(rem.own) remLoadTpl();" in js_function("openReminderDlg")
    for name in ("shiftCardHTML", "remWriteHTML", "remWriteOwn", "remLoadTpl", "remSendHTML"):
        assert "—" not in js_function(name) and "–" not in js_function(name)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_own_message_is_one_off_and_the_template_comes_back():
    src = (
        "const store={};\n"
        "const localStorage={getItem:k=>k in store?store[k]:null, setItem:(k,v)=>{store[k]=String(v);}};\n"
        "let txt={mode:'remind', en:'', es:''};\n"
        + const_block("REM_TPL_KEY") + const_block("REM_DEFAULT")
        + re.search(r"^let rem=\(\(\)=>\{.*?\}\)\(\);\n", TEMPLATE, re.M | re.S).group(0)
        + "\n".join(js_function(n) for n in ("remLoadTpl", "remWriteOwn", "remSaveTpl", "txtSetDraft"))
        + """
        txtSetDraft('en', 'Saved {{first}} template');          // an edited template is remembered
        const saved=JSON.parse(store[REM_TPL_KEY]).en;
        remWriteOwn();
        const cleared=[rem.en, rem.es, rem.own];
        txtSetDraft('en', 'Truck is at the side gate today');  // a one-off: not remembered
        const after=JSON.parse(store[REM_TPL_KEY]).en, typed=rem.en;
        remLoadTpl();                                          // what openReminderDlg does next time
        console.log(JSON.stringify({saved, cleared, after, typed, back:rem.en, es:rem.es===REM_DEFAULT.es, own:rem.own}));
        """
    )
    out = json.loads(run_js(src))
    assert out["saved"] == "Saved {{first}} template"
    assert out["cleared"] == ["", "", True]
    assert out["typed"] == "Truck is at the side gate today"
    assert out["after"] == "Saved {{first}} template"
    assert out["back"] == "Saved {{first}} template" and out["es"] is True and out["own"] is False
