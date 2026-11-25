"""WhatsApp sends on the Install Schedule (Comments #56, Cynthia 2026-11-25:
"We also need crew confirmations through Whats APP").

Wherever a mass text or a shift reminder can go out as a text (an sms: link),
there is a WhatsApp button next to it: a wa.me link that opens WhatsApp with
the same message filled in, in the person's language. The user presses Send
in WhatsApp; nothing is sent from the page. What went out is logged on the
person with via:'whatsapp', and the "Reminders sent X/Y" count reads it the
same as a text. A per-person "Prefers WhatsApp" switch on the roster card
makes WhatsApp the solid button for them. FAKE people and numbers only.
"""
import json
import shutil
from urllib.parse import unquote

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_shift_reminders import REM

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

WA = REM + "\n".join(js_function(n) for n in (
    "waNumber", "smsHref", "waHref", "txtViaFor", "sendLinks", "esc",
)) + """
const EN={key:'en', label:'English'}, ES={key:'es', label:'Spanish'};
"""


def run(body):
    return json.loads(run_js(WA + body))


def test_wa_number_is_country_code_plus_ten_digits():
    out = run("""console.log(JSON.stringify([
      waNumber('(713) 555-0101'), waNumber('713.555.0101'), waNumber('+1 713 555 0101'),
      waNumber('555-0101'), waNumber(''), waNumber(null), waNumber('44 20 7946 0000')]))""")
    assert out == ["17135550101", "17135550101", "17135550101", None, None, None, None]


def test_wa_link_carries_the_same_message_url_encoded():
    out = run("""console.log(JSON.stringify([
      waHref('(713) 555-0101', '¡Hola Ana! Equipo 1 & 2\\nGracias'),
      smsHref('(713) 555-0101', 'Hi Ana'), waHref('nope', 'x')]))""")
    wa, sms, bad = out
    assert wa.startswith("https://wa.me/17135550101?text=")
    assert unquote(wa.split("?text=", 1)[1]) == "¡Hola Ana! Equipo 1 & 2\nGracias"
    assert "&" not in wa.split("?text=", 1)[1]          # the & inside the message is encoded
    assert sms == "sms:+17135550101&body=Hi%20Ana"
    assert bad == ""


def test_default_person_gets_solid_sms_in_their_language_and_whatsapp_next_to_it():
    out = run("""
      const p=person('p1','Ana','Test','General Installer','Spanish','(713) 555-0101');
      const links=sendLinks(p, [{l:EN, body:'Hi Ana'}, {l:ES, body:'Hola Ana'}], 'es');
      console.log(JSON.stringify(links.map(s=>[s.via, s.l.key, s.label, s.primary])));
    """)
    assert out == [
        ["sms", "en", "Send English", False],
        ["sms", "es", "Send Spanish", True],
        ["whatsapp", "en", "WhatsApp English", False],
        ["whatsapp", "es", "WhatsApp Spanish", False],
    ]


def test_prefers_whatsapp_makes_whatsapp_first_and_solid():
    out = run("""
      const p={...person('p1','Ana','Test','General Installer','English','(713) 555-0101'), prefersWhatsApp:true};
      const links=sendLinks(p, [{l:EN, body:'Hi Ana'}, {l:ES, body:'Hola Ana'}], 'en');
      console.log(JSON.stringify(links.map(s=>[s.via, s.l.key, s.primary, s.href.slice(0,22)])));
    """)
    assert out == [
        ["whatsapp", "en", True, "https://wa.me/17135550"],
        ["whatsapp", "es", False, "https://wa.me/17135550"],
        ["sms", "en", False, "sms:+17135550101&body="],
        ["sms", "es", False, "sms:+17135550101&body="],
    ]


def test_one_language_written_is_solid_whatever_their_language():
    out = run("""
      const p=person('p1','Ana','Test','General Installer','Spanish','(713) 555-0101');
      console.log(JSON.stringify(sendLinks(p, [{l:EN, body:'Hi'}], 'es').map(s=>[s.via, s.primary])));
    """)
    assert out == [["sms", True], ["whatsapp", False]]


def test_whatsapp_log_survives_normalising_and_old_entries_stay_texts():
    out = run("""
      console.log(JSON.stringify(normTexts([
        {at:'2026-11-24T01:00:00.000Z', lang:'es', body:'Hola', via:'whatsapp'},
        {at:'2026-11-23T01:00:00.000Z', lang:'en', body:'Hi'},
        {at:'2026-11-22T01:00:00.000Z', lang:'en', body:'Hi', via:'carrier pigeon'},
        {at:'2026-11-21T01:00:00.000Z', lang:'en', body:'R', kind:'reminder', for:'2026-11-22', via:'whatsapp'},
      ])));
    """)
    assert out[0] == {"at": "2026-11-24T01:00:00.000Z", "lang": "es", "body": "Hola", "via": "whatsapp"}
    assert "via" not in out[1] and "via" not in out[2]
    assert out[3]["kind"] == "reminder" and out[3]["via"] == "whatsapp"


def test_reminders_sent_counter_counts_whatsapp_sends():
    out = run("""
      const iso='2026-11-26';
      const a=person('p1','Ana','Test','Lead','Spanish','(713) 555-0101');
      const b=person('p2','Ben','Test','General Installer','English','(713) 555-0102');
      const c=person('p3','Cy','Test','General Installer','English','(713) 555-0103');
      a.texts=withReminderLog([], {at:'2026-11-25T23:00:00.000Z', lang:'es', body:'x', kind:'reminder', for:iso, via:'whatsapp'});
      b.texts=withReminderLog([], {at:'2026-11-25T23:01:00.000Z', lang:'en', body:'x', kind:'reminder', for:iso});
      const rows=[a,b,c].map(p=>({p}));
      console.log(JSON.stringify(remStatus(rows, iso)));
    """)
    assert out == {"sent": 2, "total": 3}


def test_send_screens_use_the_shared_buttons_and_log_the_channel():
    for fn in ("txtSendHTML", "remSendHTML"):
        assert "sendLinksHTML(sendLinks(p, sends," in js_function(fn), fn
    for fn in ("txtWireSend", "remWireSend"):
        src = js_function(fn)
        assert "a.dataset.via" in src, fn
        assert "txtViaFor(p)" in src, fn                 # ticked by hand: their usual app
    assert "entry.via='whatsapp'" in js_function("txtLog")
    assert "entry.via='whatsapp'" in js_function("remLog")
    # WhatsApp opens in a new tab (wa.me hands off to the app); nothing is automated.
    html = js_function("sendLinksHTML")
    assert 'target="_blank" rel="noopener"' in html
    for src in (js_function("sendLinks"), html, js_function("waHref")):
        for bad in ("osascript", "window.open(", "location.href", ".click()", "fetch("):
            assert bad not in src


def test_roster_card_has_the_prefers_whatsapp_switch_and_it_saves():
    detail = js_function("personDetailHTML")
    assert "data-prefwa" in detail and "Prefers WhatsApp" in detail
    staff = js_function("renderStaffing")
    assert "pn.prefersWhatsApp=cb.checked; persist();" in staff
    assert "roBlocked()" in staff
    assert "'prefersWhatsApp'" in TEMPLATE.split("const ROSTER_OWN_KEYS=", 1)[1].split("];", 1)[0]
    assert "prefersWhatsApp: p.prefersWhatsApp===true" in js_function("normRoster")


def test_text_history_marks_whatsapp():
    assert "WhatsApp</span>" in js_function("textLogHTML")
    assert "on WhatsApp" in js_function("remRowFlags")


def test_no_em_dashes_in_new_on_screen_text():
    for fn in ("sendLinksHTML", "sendLinks", "textLogHTML", "remRowFlags"):
        assert "—" not in js_function(fn), fn
