"""The stop popup's contact editor can rename a client by parts
(first name, last name, business name, location), saving through
PUT /api/clients/update/{id}. These pin the parts of review_template.html
that matter: the JS composes names exactly like the backend
(backend/app/libs/client_names.py), only office staff get the fields, and a
saved rename is shown at once and keeps resolving after a reload.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = open(os.path.join(HERE, "review_template.html"), encoding="utf-8").read()
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backend"))

from app.libs.client_names import compose_name  # noqa: E402

NODE = shutil.which("node")


def js_function(name):
    """The source of one top-level `function name(...){...}` in the template."""
    start = TEMPLATE.index(f"function {name}(")
    depth, i = 0, TEMPLATE.index("{", start)
    while True:
        ch = TEMPLATE[i]
        depth += ch == "{"
        depth -= ch == "}"
        i += 1
        if depth == 0:
            return TEMPLATE[start:i]


def run_js(src):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(src)
    try:
        out = subprocess.run([NODE, f.name], capture_output=True, text=True, check=True)
        return out.stdout
    finally:
        os.unlink(f.name)


CASES = [
    ("Nataliya", "Scheib", None, None),
    ("  Nataliya ", " Scheib  ", None, None),
    ("", "Hellums", None, None),
    ("Kerri", "Byler", None, "House"),
    (None, None, "The Club at Carlton Woods", "Nicklaus Clubhouse"),
    (None, None, "A Hug Away", "Daycare"),
    (None, None, "Capital Bank - Baytown", None),
    (None, None, "Capital  Bank", "  "),
    ("Marissa", "Frazier", "A Hug Away", None),
    ("Marissa", "Frazier", "A Hug Away", "Residence"),
    (None, None, None, "Daycare"),
]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_js_composes_names_like_the_backend():
    src = js_function("squashName") + "\n" + js_function("composeClientName") + "\n"
    rows = [dict(zip(("first_name", "last_name", "company", "site"), c)) for c in CASES]
    src += f"console.log(JSON.stringify({json.dumps(rows)}.map(composeClientName)));"
    assert json.loads(run_js(src)) == [compose_name(*c) for c in CASES]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_whole_page_script_parses():
    """node --check on the page's script: a duplicate const kills the page
    while it still returns 200."""
    for block in re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", TEMPLATE, re.S):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(block)
        try:
            subprocess.run([NODE, "--check", f.name], capture_output=True, text=True, check=True)
        finally:
            os.unlink(f.name)


def test_only_office_staff_get_the_name_fields():
    fn = js_function("canRenameClients")
    assert "ALERT_EDIT_ROLES.has(ME_ROLE)" in fn
    for guard in ("!!AUTH", "!READONLY", "!VIEWONLY", "!TVMODE"):
        assert guard in fn
    assert "const ALERT_EDIT_ROLES=new Set(['staff','admin','super_admin']);" in TEMPLATE
    block = js_function("nameBlockHTML")
    assert "only office staff can rename" in block


def test_parts_are_sent_only_when_touched_and_through_the_clients_api():
    save = TEMPLATE[TEMPLATE.index("if(saveBtn) saveBtn.onclick=async()=>{"):]
    save = save[:save.index("\n  };\n}")]
    assert "pkNameEdit.touched && canRenameClients()" in save
    assert "clientCardBody(contactFieldsForEdit, nameBody)" in save
    assert "...(nameBody||{})" in js_function("clientCardBody")
    assert "/api/clients/update/${ac.id}" in save
    assert "'409'" in save  # a duplicate name says so


def test_a_saved_rename_shows_now_and_survives_reload():
    rename = js_function("applyClientRename")
    assert "c.sheetName=c.sheetName||c.name; c.name=newName;" in rename
    assert "render();" in rename
    directory = js_function("replaceDirectoryEntry")
    assert "entry.former_names" in directory
    # On reload the page's baked name is found again through former_names,
    # and loadClientDirectory swaps in the app's spelling.
    loader = js_function("loadClientDirectory")
    assert "...(c.former_names||[])" in loader and "c.name = ac.name;" in loader
