"""The stop card's Google Drive buttons (review_template.html).

A client's Drive folder / photos folder live on the client record
(migrations/026) and are read at runtime from
GET /api/install-schedule/client-links -- never baked into DATA, so a link
change can't touch the build's version hash. "Drive folder" opens the
folder in a new tab, "Photos" shows only when set, staff get "Add folder"
when there's none, and view-only logins never get an edit control. These
run the template's own functions in node with small stubs.
"""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

FOLDER = "https://drive.google.com/drive/folders/1AbC"
PHOTOS = "https://drive.google.com/drive/folders/9ZyX"


def run(names, body):
    src = "\n".join(js_function(n) for n in names) + "\n" + body
    return json.loads(run_js(src))


@needs_node
def test_only_drive_links_count():
    out = run(["isDriveUrl"], """
      console.log(JSON.stringify([
        'https://drive.google.com/drive/folders/1AbC', ' https://drive.google.com/drive/u/0/folders/x?usp=sharing ',
        'http://drive.google.com/drive/folders/x', 'https://docs.google.com/x', 'https://drive.google.com.evil.com/x',
        'https://user@drive.google.com/x', 'https://drive.google.com/', 'javascript:alert(1)', 'https://drive.google.com/a b', '',
      ].map(isDriveUrl)));
    """)
    assert out == [True, True, False, False, False, False, False, False, False, False]


STUBS = f"""
  const IC={{folder:'F', folderplus:'FP', image:'I', pencil:'E'}};
  const normName=s=>String(s||'').trim().toLowerCase().replace(/[,.]/g,'').replace(/\\s+/g,' ');
  let AUTH='Bearer x', READONLY=false, clientDirectory=new Map(), CAN_EDIT=true;
  const canEditClientCard=()=>CAN_EDIT;
  const C={{1:{{name:'Smith, Ann'}}, 2:{{name:'Nobody'}}, 3:{{name:'Jones', sheetName:'Jones Bob'}}}};
  let AC=null; const appClientFor=()=>AC;
  let driveLinkMap=new Map([
    ['smith ann', {{id:7, drive_folder_url:'{FOLDER}', drive_photos_url:null}}],
    ['jones bob', {{id:8, drive_folder_url:'{FOLDER}', drive_photos_url:'{PHOTOS}'}}],
  ]);
"""
FNS = ["isDriveUrl", "driveLinksFor", "peekEsc", "attrEsc", "peekDriveHTML"]


@needs_node
def test_buttons_open_in_a_new_tab_and_photos_only_when_set():
    out = run(FNS, STUBS + """
      console.log(JSON.stringify([peekDriveHTML(1), peekDriveHTML(3)]));
    """)
    folder_only, both = out
    assert f'href="{FOLDER}"' in folder_only and 'target="_blank"' in folder_only
    assert 'rel="noopener noreferrer"' in folder_only
    assert "Drive folder" in folder_only and "Photos" not in folder_only
    # matched through the sheet's spelling
    assert f'href="{PHOTOS}"' in both and both.count('target="_blank"') == 2
    assert 'id="pkdriveedit"' in both and "Add folder" not in both


@needs_node
def test_add_folder_for_staff_and_nothing_for_view_only():
    out = run(FNS, STUBS + """
      const staff=peekDriveHTML(2);
      CAN_EDIT=false; const viewer=peekDriveHTML(2), viewerWithLink=peekDriveHTML(1);
      CAN_EDIT=true; READONLY=true; const archived=peekDriveHTML(2);
      console.log(JSON.stringify([staff, viewer, viewerWithLink, archived]));
    """)
    staff, viewer, viewer_with_link, archived = out
    assert 'id="pkdriveadd"' in staff and "Add folder" in staff and "href" not in staff
    assert viewer == "" and archived == ""
    assert f'href="{FOLDER}"' in viewer_with_link and "pkdriveedit" not in viewer_with_link


@needs_node
def test_live_client_record_wins_and_bad_links_never_render():
    out = run(FNS, STUBS + """
      AC={drive_folder_url:'https://evil.com/x', drive_photos_url:null};
      console.log(JSON.stringify(peekDriveHTML(1)));
    """)
    assert "evil.com" not in out and "Add folder" in out


@needs_node
def test_editor_sends_only_changed_links_and_checks_them_first():
    out = run(["isDriveUrl", "driveLinkChanges", "driveLinksProblem"], f"""
      const was={{drive:'{FOLDER}', photos:''}};
      console.log(JSON.stringify([
        driveLinkChanges({{drive:' {FOLDER} ', photos:'', drive_was:was}}),
        driveLinkChanges({{drive:'{FOLDER}', photos:'{PHOTOS}', drive_was:was}}),
        driveLinkChanges({{drive:'', photos:'', drive_was:was}}),
        driveLinksProblem({{drive:'https://evil.com', photos:''}}),
        driveLinksProblem({{drive:'', photos:'nope'}}),
        driveLinksProblem({{drive:'', photos:''}}),
      ]));
    """)
    assert out[0] is None
    assert out[1] == {"drive_photos_url": PHOTOS}
    assert out[2] == {"drive_folder_url": ""}
    assert "Drive folder" in out[3] and "Photos folder" in out[4] and out[5] == ""


def test_links_come_from_the_api_not_data():
    """Read at runtime from the viewer-readable route; saved through the
    staff-only PUT; never part of the baked DATA (which would change the
    version hash and wipe the board)."""
    assert "authFetch('/api/install-schedule/client-links'" in TEMPLATE
    assert "`/api/clients/${entry.id}/drive-links`, 'PUT'" in TEMPLATE
    assert "DATA.drive" not in TEMPLATE and "drive_folder_url" not in js_function("manifestHTML")
    stop_card = js_function("openStopPeek")
    assert '<div id="pkdrive">${peekDriveHTML(row)}</div>' in stop_card
    assert "wirePeekDrive(row)" in stop_card
    assert "pkf-drive" in js_function("contactEditHTML") and "pkf-photos" in js_function("contactEditHTML")
