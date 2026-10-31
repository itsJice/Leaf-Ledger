"""A client's Google Drive links (migrations/026): validation, the PUT
route, the install schedule's read of them, who may change them, and the
CSV importer's dry-run plan. No database."""
import asyncio

import pytest
from fastapi import HTTPException

from app.apis import clients, install_schedule
from app.libs import drive_links
from app.libs.drive_links import DriveLinkError, clean_drive_url
from scripts import import_drive_folders as imp

FOLDER = "https://drive.google.com/drive/folders/1AbC_def-123"
PHOTOS = "https://drive.google.com/drive/folders/9ZyX"


def run(coro):
    return asyncio.run(coro)


# ─── validation ──────────────────────────────────────────────────────────────


def test_clean_drive_url_trims_and_blanks_clear():
    assert clean_drive_url(f"  {FOLDER}\n") == FOLDER
    assert clean_drive_url("https://drive.google.com/drive/u/0/folders/abc?usp=sharing") \
        == "https://drive.google.com/drive/u/0/folders/abc?usp=sharing"
    assert clean_drive_url("HTTPS://Drive.Google.com/drive/folders/x") == "HTTPS://Drive.Google.com/drive/folders/x"
    assert clean_drive_url("") is None
    assert clean_drive_url("   ") is None
    assert clean_drive_url(None) is None


@pytest.mark.parametrize("bad", [
    "http://drive.google.com/drive/folders/x",       # not https
    "https://docs.google.com/document/d/x",          # another Google host
    "https://drive.google.com.evil.com/folders/x",   # look-alike host
    "https://evil.com/?https://drive.google.com/",   # Drive only in the query
    "https://user@drive.google.com/drive/folders/x",
    "https://drive.google.com:8443/drive/folders/x",
    "https://drive.google.com/",                     # no folder
    "https://drive.google.com",
    "javascript:alert(1)",
    "drive.google.com/drive/folders/x",              # no scheme
    "https://drive.google.com/drive/folders/x y",    # two things pasted
    "https://drive.google.com/" + "x" * 2000,
])
def test_clean_drive_url_rejects_anything_else(bad):
    with pytest.raises(DriveLinkError):
        clean_drive_url(bad, "Drive folder")


def test_error_names_the_field():
    with pytest.raises(DriveLinkError, match="Photos folder must start with https://drive.google.com/"):
        clean_drive_url("https://example.com/x", "Photos folder")


# ─── schema ──────────────────────────────────────────────────────────────────


def test_list_adds_the_drive_columns_once_and_reads_them(fake_db, fake_request):
    fake_db.on_fetch("FROM clients", [])
    run(clients.list_clients(fake_request()))
    run(clients.list_clients(fake_request()))
    alters = fake_db.calls("ADD COLUMN IF NOT EXISTS drive_folder_url")
    assert len(alters) == 1 and "ADD COLUMN IF NOT EXISTS drive_photos_url text" in alters[0][0]
    assert fake_db.seen("drive_folder_url, drive_photos_url FROM clients")
    assert set(drive_links.DRIVE_LINK_COLUMNS) <= set(clients.ENSURED_COLUMNS)


def test_client_out_carries_the_links():
    out = clients.ClientOut(name="Smith", drive_folder_url=FOLDER)
    assert out.drive_folder_url == FOLDER and out.drive_photos_url is None


# ─── PUT /clients/{id}/drive-links ───────────────────────────────────────────


def test_set_both_links(fake_db):
    fake_db.on_fetchrow("UPDATE clients SET drive_folder_url",
                        {"id": 7, "drive_folder_url": FOLDER, "drive_photos_url": PHOTOS})
    out = run(clients.set_drive_links(7, clients.DriveLinksIn(
        drive_folder_url=f" {FOLDER} ", drive_photos_url=PHOTOS)))
    assert out == {"id": 7, "drive_folder_url": FOLDER, "drive_photos_url": PHOTOS}
    ((sql, args),) = fake_db.calls("UPDATE clients SET drive_folder_url")
    assert args == (7, True, FOLDER, True, PHOTOS)
    assert "RETURNING id, drive_folder_url, drive_photos_url" in sql


def test_only_sent_keys_change_and_blank_clears(fake_db):
    fake_db.on_fetchrow("UPDATE clients SET drive_folder_url",
                        {"id": 7, "drive_folder_url": FOLDER, "drive_photos_url": None})
    run(clients.set_drive_links(7, clients.DriveLinksIn(drive_photos_url="")))
    ((_, args),) = fake_db.calls("UPDATE clients SET drive_folder_url")
    # folder untouched (False), photos cleared (True, None)
    assert args == (7, False, None, True, None)


def test_bad_link_is_a_400_and_writes_nothing(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(clients.set_drive_links(7, clients.DriveLinksIn(drive_folder_url="https://evil.com/x")))
    assert exc.value.status_code == 400
    assert "Drive folder must start with https://drive.google.com/" in exc.value.detail
    assert not fake_db.seen("UPDATE clients")


def test_empty_body_is_a_400(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(clients.set_drive_links(7, clients.DriveLinksIn()))
    assert exc.value.status_code == 400


def test_unknown_client_is_a_404(fake_db):
    fake_db.on_fetchrow("UPDATE clients SET drive_folder_url", None)
    with pytest.raises(HTTPException) as exc:
        run(clients.set_drive_links(404, clients.DriveLinksIn(drive_folder_url=FOLDER)))
    assert exc.value.status_code == 404


@pytest.mark.parametrize("role, ok", [
    ("crew", False), ("viewer", False), ("production", False), ("lead", False),
    ("staff", True), ("admin", True), ("super_admin", True),
])
def test_changing_links_needs_staff(role, ok):
    """Same people who edit the rest of the card. The shop TV and production
    can open the folder but not change the link."""
    from app.libs import roles

    path = "/api/clients/{client_id}/drive-links"
    assert roles.allowed(role, "staff", "PUT", False, path) is ok


def test_route_declares_the_staff_dependency():
    route = next(r for r in clients.router.routes if r.path.endswith("/drive-links"))
    assert route.methods == {"PUT"}
    assert route.dependencies, "drive-links must carry require_role('staff')"


# ─── GET /install-schedule/client-links ──────────────────────────────────────


def test_schedule_reads_only_clients_with_a_link(fake_db):
    fake_db.on_fetch("FROM clients", [
        {"id": 3, "name": "Smith, Ann", "sheet_name": "Smith Ann", "former_names": None,
         "drive_folder_url": FOLDER, "drive_photos_url": None},
    ])
    out = run(install_schedule.client_links())
    assert out == [{"id": 3, "name": "Smith, Ann", "sheet_name": "Smith Ann", "former_names": [],
                    "drive_folder_url": FOLDER, "drive_photos_url": None}]
    ((sql, _),) = fake_db.calls("FROM clients")
    assert "WHERE drive_folder_url IS NOT NULL OR drive_photos_url IS NOT NULL" in sql


@pytest.mark.parametrize("role, ok", [
    ("viewer", True), ("production", True), ("staff", True), ("admin", True),
    ("crew", False), ("lead", False),
])
def test_schedule_links_readable_by_the_tv_and_production(role, ok):
    """Viewers open the folder from the stop popup; the read is on the
    install-schedule router (VIEWER_READ), not the staff-only Clients list."""
    from app.libs import roles

    assert install_schedule.VIEWER_READ is True
    path = "/api/install-schedule/client-links"
    assert roles.allowed(role, "staff", "GET", True, path) is ok
    # ...and nobody but staff+ can write through that router
    assert roles.allowed("viewer", "staff", "PUT", True, "/api/clients/{client_id}/drive-links") is False


# ─── scripts/import_drive_folders.py ─────────────────────────────────────────


CLIENTS = [
    {"id": 1, "name": "Beaver, Austin", "sheet_name": None, "former_names": [],
     "drive_folder_url": None, "drive_photos_url": None},
    {"id": 2, "name": "Hug Away", "sheet_name": "A Hug Away", "former_names": ["Hug-Away LLC"],
     "drive_folder_url": "https://drive.google.com/drive/folders/OLD", "drive_photos_url": PHOTOS},
    {"id": 3, "name": "Woodlands CC - North", "sheet_name": "Woodlands CC", "former_names": [],
     "drive_folder_url": None, "drive_photos_url": None},
    {"id": 4, "name": "Woodlands CC - South", "sheet_name": "Woodlands CC", "former_names": [],
     "drive_folder_url": None, "drive_photos_url": None},
]


def row(name, folder="", photos="", r=""):
    return {"client_name": name, "folder_url": folder, "photos_folder_url": photos, "row": r, "_line": 9}


def by_status(report, status):
    return [(r["client_id"], r["field"]) for r in report if r["status"] == status]


def test_plan_matches_names_loosely_and_never_clears():
    report = imp.plan([row("beaver austin", FOLDER, "", r="12")], CLIENTS)
    assert by_status(report, "set") == [(1, "drive_folder_url")]
    assert by_status(report, "blank") == [(1, "drive_photos_url")]
    assert report[0]["csv_row"] == "12"
    assert imp.writes_from(report) == {1: {"drive_folder_url": FOLDER}}


def test_plan_matches_sheet_and_former_names_and_keeps_existing_links():
    new = "https://drive.google.com/drive/folders/NEW"
    report = imp.plan([row("Hug-Away LLC", new, PHOTOS)], CLIENTS)
    assert by_status(report, "differs") == [(2, "drive_folder_url")]
    assert by_status(report, "same") == [(2, "drive_photos_url")]
    assert imp.writes_from(report) == {}
    over = imp.plan([row("a hug away", new, PHOTOS)], CLIENTS, overwrite=True)
    assert imp.writes_from(over) == {2: {"drive_folder_url": new}}


def test_plan_skips_unknown_ambiguous_bad_and_duplicate_rows():
    report = imp.plan([
        row("Nobody Here", FOLDER),
        row("Woodlands CC", FOLDER),                       # two clients share the sheet name
        row("Beaver Austin", "https://docs.google.com/x"),
        row("Beaver, Austin", FOLDER),
        row("BEAVER AUSTIN", "https://drive.google.com/drive/folders/other"),
        row("", FOLDER),
    ], CLIENTS)
    statuses = [r["status"] for r in report if r["field"] != "drive_photos_url"]
    assert statuses == ["no_match", "ambiguous", "bad_url", "set", "duplicate", "no_match"]
    assert "#3" in report[1]["note"] and "#4" in report[1]["note"]
    assert imp.writes_from(report) == {1: {"drive_folder_url": FOLDER}}
    assert imp.summary(report)["set"] == 1


def test_read_csv_needs_the_columns(tmp_path):
    good = tmp_path / "ok.csv"
    good.write_text("﻿client_name,row,folder_url,photos_folder_url,confidence\n"
                    f"Beaver Austin,4, {FOLDER} ,,high\n")
    rows = imp.read_csv(str(good))
    assert rows == [{"client_name": "Beaver Austin", "row": "4", "folder_url": FOLDER,
                     "photos_folder_url": "", "confidence": "high", "_line": 2}]
    bad = tmp_path / "bad.csv"
    bad.write_text("name,url\nx,y\n")
    with pytest.raises(SystemExit):
        imp.read_csv(str(bad))


def test_apply_goes_through_the_api_writer(fake_db):
    fake_db.on_fetchrow("UPDATE clients SET drive_folder_url",
                        {"id": 1, "drive_folder_url": FOLDER, "drive_photos_url": None})
    conn = run(clients.get_conn())
    run(imp.apply(conn, {1: {"drive_folder_url": FOLDER}}))
    ((_, args),) = fake_db.calls("UPDATE clients SET drive_folder_url")
    assert args == (1, True, FOLDER, False, None)


@pytest.mark.parametrize("have, expect_sql", [
    (2, "SELECT id, name, sheet_name, former_names, drive_folder_url, drive_photos_url FROM clients"),
    (0, "NULL::text AS drive_folder_url, NULL::text AS drive_photos_url FROM clients"),
])
def test_dry_run_reads_without_ddl(fake_db, have, expect_sql):
    fake_db.on_fetchval("information_schema.columns", have)
    fake_db.on_fetch("FROM clients", [])
    conn = run(clients.get_conn())
    assert run(imp.read_clients(conn)) == []
    assert fake_db.seen(expect_sql)
    assert not fake_db.seen("ALTER TABLE")
