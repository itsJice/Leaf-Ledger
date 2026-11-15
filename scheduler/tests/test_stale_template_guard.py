"""The Install Schedule's stale-template guard, page side (review_template.html).

11/1/2026, 4:09 PM CT: a tab opened before the 10/31 10:31 PM publish saved
its whole state. It kept loading the state, so its base was current and the
stale-tab guard (test_stale_tab_merge.py) let it through, but its older page
didn't know the newer keys: the save dropped hoursOverride (Lake Highlands
4h), every team's driverId, and put back a takedown's old hours.

Now the server stamps each served page with its publish (pageRev) and
refuses saves from any other publish (backend
tests/test_install_schedule_stale_template.py); the page stops saving and
asks for a reload. As a second line, a save carries through the keys and
fields of the last server document this page doesn't know (keepUnknown).
These run the template's own functions in node.
"""
import json
import re

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_stale_tab_merge import DATES, MERGE, NODE, SAVE_LOOP

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def const_block(name):
    """A top-level const, to the first line that ends in `;`."""
    m = re.search(rf"^const {name}=.*?;$", TEMPLATE, re.M | re.S)
    assert m, name
    return m.group(0)


KEEP = "\n".join(const_block(n) for n in ("ROSTER_OWN_KEYS", "KNOWN_FIELDS", "KNOWN_ID")) \
    + "\n" + js_function("keepUnknown")


def run(body):
    return json.loads(run_js(KEEP + "\n" + body))


# The server document after the 10/31 publish (FAKE clients and people).
NEWER = """
const clone=x=>JSON.parse(JSON.stringify(x));
const NEWER={season:'2026', placement:{'7':['2026-11-20|Crew 1|0']}, hoursOverride:{'7':4},
  futureKey:{a:1},
  teams:[{id:'t1', name:'Team Ana', season:2026, leadId:'p1', members:['p1','p2'], driverId:'p2',
          futureField:'x'}],
  roster:[{id:'p1', first:'Ana', last:'Test', name:'Ana Test', active:true, futurePersonField:3}],
  newClients:[{row:9001, name:'M Crowd Lakewood', visitType:'Takedown', hours:2.5, futureClientField:'y'}]};
"""


def test_an_older_save_keeps_what_it_does_not_know():
    out = run(NEWER + """
      // What a page that predates hoursOverride, driverId and the rest sends.
      const old={season:'2026', placement:{'7':['2026-11-21|Crew 1|0']},
        teams:[{id:'t1', name:'Team Ana', season:2026, leadId:'p1', members:['p1','p2']}],
        roster:[{id:'p1', first:'Ana', last:'Test', name:'Ana Test', active:true}],
        newClients:[{row:9001, name:'M Crowd Lakewood', visitType:'Takedown', hours:2.5}]};
      console.log(JSON.stringify(keepUnknown(NEWER, old)));
    """)
    assert out["placement"] == {"7": ["2026-11-21|Crew 1|0"]}      # its own change kept
    assert out["futureKey"] == {"a": 1}
    assert out["hoursOverride"] == {"7": 4}
    assert out["teams"][0]["futureField"] == "x"
    assert out["roster"][0]["futurePersonField"] == 3
    assert out["newClients"][0]["futureClientField"] == "y"


def test_known_fields_are_never_put_back():
    # This page knows driverId: a team saved without one had its Driver
    # cleared here, and that must stick.
    out = run(NEWER + """
      const mine={season:'2026', placement:NEWER.placement, hoursOverride:{},
        teams:[{id:'t1', name:'Team Ana', season:2026, leadId:'p1', members:['p1','p2']}],
        roster:[{id:'p1', first:'Ana', last:'Test', name:'Ana Test', active:false}],
        newClients:[]};
      console.log(JSON.stringify(keepUnknown(NEWER, mine)));
    """)
    assert "driverId" not in out["teams"][0]
    assert out["teams"][0]["futureField"] == "x"
    assert out["hoursOverride"] == {}                                # cleared stays cleared
    assert out["roster"][0]["active"] is False
    assert out["newClients"] == []                                   # a removed client stays removed


def test_nothing_to_keep_without_a_server_document():
    out = run("""const o={a:1, teams:[{id:'t1'}]};
      console.log(JSON.stringify([keepUnknown(null, o), keepUnknown(undefined, o)]));""")
    assert out == [{"a": 1, "teams": [{"id": "t1"}]}] * 2


def test_real_snapshot_carries_unknown_keys_through():
    src = js_function("sharedSnapshot")
    assert "keepUnknown(sharedRaw," in src
    # Every server document a tab takes on becomes what it carries through.
    assert "sharedRaw=j.state;" in js_function("rebaseOnto")
    assert js_function("putShared").count("sharedRaw = st;") == 1


# ─── the save loop against a server that checks pageRev ──────────────────────

STAMPED = MERGE + "\n" + DATES + "\n" + KEEP + """
const P=(id,first)=>({id, first, last:'Test', name:first+' Test', active:true});
const clone=x=>JSON.parse(JSON.stringify(x));
""" + SAVE_LOOP.replace("let sharedRaw=null, PAGE_REV=null;", "let sharedRaw=null, PAGE_REV=PAGE_STAMP;") + """
// The template's sharedSnapshot ends in keepUnknown too.
const _snap=sharedSnapshot;
sharedSnapshot=function(){ return keepUnknown(sharedRaw, _snap()); };
// The server also checks the page's stamp (install_schedule.is_stale_page).
const PUBLISHED='2026-11-01T03:31:00.000001+00:00';    // 10/31 10:31 PM CT
const _fetch=fetch;
fetch=async function(url, init){
  const b=JSON.parse(init.body);
  if(!('pageRev' in b) || (b.pageRev!==null && b.pageRev!==PUBLISHED)){
    server.log.push({status:409, stale:true});
    return {status:409, ok:false, json:async()=>({conflict:true, staleTemplate:true, pageRev:PUBLISHED})};
  }
  return _fetch(url, init);
};
"""


def run_loop(stamp, body):
    return json.loads(run_js(f"const PAGE_STAMP={json.dumps(stamp)};\n" + STAMPED + body))


LOOP = """
      (async()=>{
        server.doc={season:'2026', placement:{'1':['2026-11-13|Crew 1|0']}, approved:[], moves:[],
          hoursOverride:{'1':4}, teams:[{id:'t1', name:'Team Ana', season:2026, leadId:'p1',
          members:['p1','p2'], driverId:'p2'}], roster:[P('p1','Ana'), P('p2','Luis')], futureKey:[1]};
        load();
        DOC.approved=['1'];                          // the edit it saves
        const ok=await putShared();
        console.log(JSON.stringify({ok, log:server.log, doc:server.doc, banners, blocked:syncBlocked}));
      })();
"""


def test_a_page_from_an_older_publish_is_refused_and_asks_for_a_reload():
    out = run_loop("2026-10-31T20:00:00+00:00", LOOP)
    assert out["ok"] is False
    assert out["log"] == [{"status": 409, "stale": True}]           # nothing written
    assert out["doc"]["hoursOverride"] == {"1": 4}
    assert out["doc"]["teams"][0]["driverId"] == "p2"
    assert out["blocked"] is True
    assert out["banners"] == [{"title": "This schedule was updated."}]


def test_the_current_publish_saves_and_carries_unknown_keys():
    out = run_loop("2026-11-01T03:31:00.000001+00:00", LOOP)
    assert out["ok"] is True and [x["status"] for x in out["log"]] == [200]
    assert out["doc"]["approved"] == ["1"]
    assert out["doc"]["futureKey"] == [1]
    assert out["doc"]["teams"][0]["driverId"] == "p2"
    assert out["banners"] == [] and out["blocked"] is False


def test_once_blocked_it_stops_saving():
    out = run_loop("2026-10-31T20:00:00+00:00", LOOP.replace(
        "const ok=await putShared();", "await putShared(); const ok=await putShared();"))
    assert out["ok"] is False and len(out["log"]) == 1


def test_outdated_check():
    js = js_function("pageOutdated")
    out = json.loads(run_js("let PAGE_REV='A';\n" + js + """
      const a=[pageOutdated({pageRev:'A'}), pageOutdated({pageRev:'B'}), pageOutdated({}), pageOutdated(null)];
      PAGE_REV=null; a.push(pageOutdated({pageRev:'B'}));
      console.log(JSON.stringify(a));"""))
    assert out == [False, True, False, False, False]


def test_page_reads_its_stamp_and_sends_it():
    assert 'meta[name="tbdg-page-rev"]' in TEMPLATE
    assert TEMPLATE.count("pageRev:PAGE_REV") == 2                   # putShared and tbdgFlush
    assert "if(j && j.staleTemplate){ showPageOutdated(); break; }" in js_function("putShared")
    assert "pageOutdated(j)" in js_function("pullSharedNow")


def test_banner_text_has_no_em_dashes():
    src = js_function("showPageOutdated")
    assert "This schedule was updated." in src and "—" not in src
