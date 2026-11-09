"""Scheduling restrictions and the last contact on the Install Schedule
(Comments #23, review_template.html).

A client's restrictions ("no Fridays") live on the client record
(clients.schedule_restrictions, migrations/027) and are read at runtime --
from the Clients list for staff, else /api/install-schedule/client-links for
the TV and production -- never baked into DATA, so editing them can't change
the build's version hash. They show as a badge on the stop next to the time
preference and as a line in the popup. The popup's "Last contact" line is the
season card's contact log, for office staff only. These run the template's
own functions in node with small stubs.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def run(names, body):
    src = "\n".join(js_function(n) for n in names) + "\n" + body
    return json.loads(run_js(src))


STUBS = """
  const IC={alert:'!', aphone:'P'};
  const normName=s=>String(s||'').trim().toLowerCase().replace(/[,.]/g,'').replace(/\\s+/g,' ');
  const SEASON=['2026-10-01','2027-01-31'];
  const ALERT_EDIT_ROLES=new Set(['staff','admin','super_admin']);
  let ME_ROLE='staff';
  const CONTACT_METHOD_LABEL={call:'Call', voicemail:'Voicemail', text:'Text', email:'Email', in_person:'In person'};
  const fmtMDYYYY=iso=>{ const [y,m,d]=iso.split('-'); return `${m}/${d}/${y}`; };
  const C={1:{name:'Allums, Jennifer'}, 2:{name:'Smith, Ann'}, 3:{name:'Nobody'}, 4:{name:'Shared'}};
  let DIR=new Map();
  const appClientFor=row=>DIR.get(row)||null;
  let driveLinkMap=new Map([
    ['smith ann', {id:8, schedule_restrictions:'  Gate closes\\n at 3 PM '}],
    ['shared', {id:9, schedule_restrictions:'Should not show'}],
  ]);
  let driveLinkAmbig=new Set(['shared']);
"""
FNS = ["peekEsc", "attrEsc", "liveRecordIn", "restrictionsOf", "anyRestrictions", "restrictBadge",
       "newestContact", "lastContactOf", "peekSchedHTML"]
JEN = """{id:1, name:'Allums, Jennifer', schedule_restrictions:'No Fridays <b>', activity:[
  {kind:'christmas_install', season:'2026', detail:{contact_log:[
    {date:'2026-11-02', method:'voicemail', note:'', by:'Amy', at:'a'},
    {date:'2026-11-05', method:'call', note:'confirmed 11/19, prefers morning', by:'Cynthia', at:'c'},
    {date:'2026-11-05', method:'text', note:'earlier same day', by:'Cynthia', at:'b'},
    'junk']}},
  {kind:'christmas_install', season:'2025', detail:{contact_log:[{date:'2025-12-01', method:'email', at:'z'}]}}]}"""


@needs_node
def test_badge_reads_the_client_record_then_client_links():
    out = run(FNS, STUBS + f"""
      DIR.set(1, {JEN});
      console.log(JSON.stringify([restrictionsOf(1), restrictionsOf(2), restrictionsOf(3), restrictionsOf(4),
        restrictBadge(1), restrictBadge(3), anyRestrictions()]));
    """)
    jen, ann, nobody, shared, badge, none, anyr = out
    assert jen == "No Fridays <b>"
    assert ann == "Gate closes at 3 PM"  # TV / production: from client-links, whitespace collapsed
    assert nobody == "" and shared == ""  # a spelling two records share never matches
    assert 'class="badge restrict"' in badge and "No Fridays &lt;b&gt;" in badge
    assert 'title="Scheduling restrictions: No Fridays &lt;b&gt;"' in badge
    assert none == "" and anyr is True


@needs_node
def test_record_without_restrictions_beats_client_links():
    """A staff directory entry that has the field (even empty) wins, so
    clearing restrictions on the card clears the badge right away."""
    out = run(FNS, STUBS + """
      DIR.set(2, {id:8, name:'Smith, Ann', schedule_restrictions:null});
      console.log(JSON.stringify([restrictionsOf(2)]));
    """)
    assert out == [""]


@needs_node
def test_last_contact_is_newest_and_staff_only():
    out = run(FNS, STUBS + f"""
      DIR.set(1, {JEN});
      const staff=peekSchedHTML(1);
      ME_ROLE='production'; const prod=peekSchedHTML(1), prodLast=lastContactOf(1);
      ME_ROLE='lead'; const lead=lastContactOf(1);
      ME_ROLE=''; const unknown=lastContactOf(1);
      ME_ROLE='viewer'; const tv=peekSchedHTML(2);
      console.log(JSON.stringify([staff, prod, prodLast, lead, unknown, tv, peekSchedHTML(3)]));
    """)
    staff, prod, prod_last, lead, unknown, tv, nothing = out
    assert "Scheduling restrictions:</b> No Fridays &lt;b&gt;" in staff
    assert "Last contact:</b> Call, 11/05/2026, Cynthia: confirmed 11/19, prefers morning" in staff
    assert "Last contact" not in prod and "No Fridays" in prod
    assert prod_last is None and lead is None and unknown is None
    assert "Gate closes at 3 PM" in tv and "Last contact" not in tv
    assert nothing == ""


@needs_node
def test_newest_contact_handles_empty_and_junk():
    out = run(["newestContact"], """
      console.log(JSON.stringify([newestContact(null), newestContact({}), newestContact({contact_log:'x'}),
        newestContact({contact_log:[null, 'x']}), newestContact({contact_log:[{date:'2026-11-01', method:'call'}]})]));
    """)
    assert out == [None, None, None, None, {"date": "2026-11-01", "method": "call"}]


def test_restrictions_are_wired_into_card_popup_and_editor():
    t = TEMPLATE
    # The badge sits next to the time preference on every stop card variant.
    assert t.count("${prefBadge(r)}${restrictBadge(r)}") == 1
    assert t.count("${prefBadge(row)}${restrictBadge(row)}") == 2
    # The popup line, refreshed when the directory lands.
    assert '<div id="pksched">${peekSchedHTML(row)}</div>' in t
    assert "const sc=document.getElementById('pksched'); if(sc) sc.innerHTML=peekSchedHTML(row);" in t
    # The card editor's field, buffered and saved with the client card.
    assert "pkField('pkf-restrict','Scheduling restrictions'" in t
    assert "['restrictions','pkf-restrict']" in t
    assert "schedule_restrictions:t(f.restrictions)" in t
    assert "const CONTACT_METHOD_LABEL={call:'Call', voicemail:'Voicemail', text:'Text', email:'Email', in_person:'In person'};" in t
    # Never baked into DATA.
    assert "schedule_restrictions" not in t.split("const DATA = ")[0][-200:]


def test_no_em_dashes_in_the_new_ui_text():
    t = TEMPLATE
    start = t.index("// ---------- scheduling restrictions + last contact (Comments #23)")
    end = t.index("async function pullShared()")
    assert "—" not in t[start:end]
    assert "—" not in t[t.index("pkField('pkf-restrict'"):t.index("pkField('pkf-restrict'") + 200]
