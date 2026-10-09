"""The expanded stop card and its client card editor (review_template.html).

The editor offers what the app's Edit Client dialog offers (Clients.tsx,
NewClientModal) and saves through the same endpoints: PUT
/api/clients/update/{id} for the client record (rename-everywhere included)
and PUT /api/clients/{id}/seasons/{season} for this season's notes, only
the fields that changed. These run the template's own functions in node
with small stubs, plus a few source pins for the gating and wiring.
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


@needs_node
def test_save_body_matches_the_app_edit_dialog():
    out = run(["clientCardBody"], """
      const f={street:' 1 Elm St ', city:'Houston', state:'tx', zip:'77010', phone:' 713 ',
        email:'a@example.test', notes:'  gate code  ', time_preference:'late',
        secondary:[{label:'Wife',phone:'',email:''},{label:'',phone:'',email:''}]};
      console.log(JSON.stringify([clientCardBody(f,null), clientCardBody({...f,time_preference:''},{first_name:'A',last_name:'B',company:'',site:''})]));
    """)
    plain, renamed = out
    assert plain == {"street": "1 Elm St", "city": "Houston", "state": "TX", "zip": "77010",
                     "phone": "713", "email": "a@example.test", "notes": "gate code",
                     "time_preference": "late",
                     "secondary_contacts": [{"label": "Wife", "phone": "", "email": ""}]}
    # "" clears the preference server-side; name parts ride along only when given.
    assert renamed["time_preference"] == ""
    assert renamed["first_name"] == "A" and "first_name" not in plain


@needs_node
def test_season_notes_send_only_what_changed():
    out = run(["seasonNotesChanges"], """
      const was={notes:'Park in back', production_notes:''};
      console.log(JSON.stringify([
        seasonNotesChanges({inst_notes:'Park in back', prod_notes:'', season_was:was}),
        seasonNotesChanges({inst_notes:'Park in back', prod_notes:'Fix wreath', season_was:was}),
        seasonNotesChanges({inst_notes:'', prod_notes:'', season_was:was}),
        seasonNotesChanges({inst_notes:'x'}),
      ]));
    """)
    assert out == [None, {"production_notes": "Fix wreath"}, {"notes": None}, None]


@needs_node
def test_last_years_repair_note_is_a_hint_not_the_value():
    out = run(["seasonNotesFor"], """
      const SEASON=['2026-10-01'];
      const ac={activity:[
        {kind:'christmas_install', season:'2025', detail:{production_notes:'Rebuild garland'}},
        {kind:'christmas_install', season:'2026', detail:{notes:'Dock entrance'}},
        {kind:'comment', season:'2026', detail:{}}]};
      console.log(JSON.stringify(seasonNotesFor(ac)));
    """)
    assert out["inst_notes"] == "Dock entrance"
    assert out["prod_notes"] == ""
    assert out["prod_prev"] == {"season": "2025", "text": "Rebuild garland"}


@needs_node
def test_contact_links_and_pencil_gating():
    out = run(["mapsHref", "telHref", "attrEsc", "peekEsc", "pkSection", "contactViewHTML"], """
      const IC={pin:'P',aphone:'T',amail:'M',ausers:'U',pencil:'E'};
      const fmtPhone=p=>p;
      const contactFieldsFor=()=>({street:'1 Elm St',city:'Houston',state:'TX',zip:'77010',
        phone:'(713) 555-1200',email:'a@example.test',secondary:[{label:'Wife',phone:'7135550000',email:''}]});
      console.log(JSON.stringify([contactViewHTML(1,true), contactViewHTML(1,false)]));
    """)
    staff, viewer = out
    assert 'href="https://maps.apple.com/?q=1%20Elm%20St%2C%20Houston%2C%20TX%2C%2077010"' in staff
    assert 'href="tel:+17135551200"' in staff and 'href="mailto:a@example.test"' in staff
    assert 'href="tel:+17135550000"' in staff
    assert 'id="pkcontactedit"' in staff and 'aria-label="Edit client"' in staff
    assert 'id="pkcontactedit"' not in viewer


FOLD = ["pkFold", "peekEsc"]
FOLD_STUBS = "const IC={chevD:'v'}; let pkOpen=new Set();"


@needs_node
def test_history_is_a_closed_fold_with_a_one_line_summary():
    out = run(["pkSection", "profileSectionHTML"] + FOLD, FOLD_STUBS + """
      const AUTH='x', clientDirectory=new Map(), SEASON=['2026-10-01'], notInstalling=new Set(), days=[{stops:[1]}];
      const appClientFor=()=>({activity:['2022','2023','2024','2025','2026'].map(s=>({kind:'christmas_install',season:s,summary:'Installed '+s}))});
      console.log(JSON.stringify(profileSectionHTML(1)));
    """)
    assert '<details class="pkfold" data-k="hist">' in out  # closed: no open attribute
    assert out.count('class="pkhrow"') == 5
    # Summary = the last season that already happened, not this one's plan.
    summary = out[out.index("<summary>"):out.index("</summary>")]
    assert "2025 · Installed 2025" in summary and '<span class="pkcount">5</span>' in summary


@needs_node
def test_notes_fold_counts_and_leads_with_production_notes():
    out = run(["peekNotesHTML"] + FOLD, FOLD_STUBS + """
      const installNoteFor=()=>({text:'Dock entrance', season:'2026', live:true});
      const productionNoteFor=()=>({text:'Rebuild garland', season:'2025', live:true});
      const appClientFor=()=>({notes:'Gate code'});
      console.log(JSON.stringify(peekNotesHTML(1)));
    """)
    summary = out[out.index("<summary>"):out.index("</summary>")]
    assert 'class="pkcount warn">3<' in summary and "Rebuild garland" in summary
    assert " open" not in out.split(">")[0]


@needs_node
def test_unknown_boxes_are_a_muted_chip_not_a_dash():
    out = run(["pkChip", "peekEsc", "peekFactsHTML"], """
      const IC={pkg:'B',aclock:'C',ausers:'U',sun:'S',box:'X'};
      const C={1:{boxes:'',people:4,h26:3}, 2:{boxes:5,people:0,h26:2}};
      let pkDayId=null; const days=[];
      const prefOf=r=>r===1?'late':''; const PREF_LABEL={late:'late'}; const storingWithUs=r=>r===1?true:null;
      console.log(JSON.stringify([peekFactsHTML(1), peekFactsHTML(2)]));
    """)
    unknown, known = out
    assert "boxes?" in unknown and "pkchip muted" in unknown and "—" not in unknown
    # Only the quick-reference facts sit up top; preference and storage live
    # in the closed Client profile fold.
    assert "Late installs" not in unknown and "Storing" not in unknown
    assert "5 boxes" in known and "people" not in known


def test_only_office_staff_on_the_live_season_get_the_editor():
    fn = js_function("canEditClientCard")
    for guard in ("!!AUTH", "!READONLY", "!VIEWONLY", "!TVMODE", "!clientEditDenied",
                  "ALERT_EDIT_ROLES.has(ME_ROLE)"):
        assert guard in fn
    assert "const editable=canEditClientCard();" in js_function("contactBlockHTML")
    # Viewer and archived pages also hide the controls by CSS, as a backstop.
    assert "body.viewonly .pkpencil,body.viewonly .pkchip-btn,body.viewonly .pkpos," in TEMPLATE
    assert "body.readonly .pkpencil,body.readonly .pkchip-btn,body.readonly .pkseg-b," in TEMPLATE


def test_save_goes_through_the_app_endpoints_and_redraws_without_reload():
    save = TEMPLATE[TEMPLATE.index("if(saveBtn) saveBtn.onclick=async()=>{"):]
    save = save[:save.index("\n  };\n}")]
    assert "/api/clients/update/${ac.id}" in save
    assert "/api/clients/${entry.id}/seasons/${encodeURIComponent(yr)}" in save
    assert "seasonNotesChanges(contactFieldsForEdit)" in save
    assert "applyClientRename(oldName, entry.name)" in save
    assert "refreshPeekLive(row)" in save
    assert "code==='403'" in save and "clientEditDenied=true" in save


def test_editor_has_the_app_fields():
    html = js_function("contactEditHTML")
    for field in ("pkf-email", "pkf-phone", "pkf-street", "pkf-suggest", "pkf-city", "pkf-state",
                  "pkf-zip", "pkf-pref", "pksecondary", "pkf-notes", "pkf-instnotes", "pkf-prodnotes"):
        assert field in html, field
    assert "nameBlockHTML(row)" in html


def test_suggestion_pick_cannot_fold_the_card():
    # Picking empties the list; without stopPropagation the page's outside-
    # click check sees a detached target and closes the stop card.
    assert "e.preventDefault(); e.stopPropagation(); pkPickSuggestion" in js_function("pkRenderSuggestions")


def test_card_has_no_emoji_clutter_left():
    body = TEMPLATE[TEMPLATE.index("function openStopPeek(row,dayId){"):]
    body = body[:body.index("wireContactBlock(row);")]
    for junk in ("📦", "⏱", "📞", "✉", "📍", "Edit contact info", "Edit on the Clients tab"):
        assert junk not in body, junk
    assert "Edit contact info" not in TEMPLATE and "Edit on the Clients tab" not in TEMPLATE


def test_quick_reference_first_everything_else_folded():
    body = TEMPLATE[TEMPLATE.index("function openStopPeek(row,dayId){"):]
    body = body[:body.index("wireContactBlock(row);")]
    order = [body.index(s) for s in ('class="pktop"', 'id="pkcontact"', 'id="pkfactsbox"', 'class="pkfolds"')]
    assert order == sorted(order)
    folds = body[body.index('class="pkfolds"'):]
    for piece in ("peekNotesHTML(row)", "peekPositionHTML(row)", "profileSectionHTML(row)",
                  "profileLinkHTML(row)", "pkFold('comm'"):
        assert piece in folds, piece
    assert "pkOpen=new Set();" in body  # every card opens short
