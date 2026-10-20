"""The Install Schedule's stop-card editor, saved over real HTTP.

The editor (scheduler/review_template.html, "Edit client" on a stop card)
runs inside a srcDoc iframe and saves with the bearer token the app posted
into it, in two calls:

1. PUT /api/clients/update/{id}      the client card fields
2. PUT /api/clients/{id}/seasons/{yr} only the season notes that changed

These go through main.app (auth + role dependencies included) against the
shared fake DB, with a client shaped like the one in the 10/19 report
(Last, First; phone pasted with Unicode bidi marks; a 2026 season row with no
notes yet; an old season with no date). They pin:

* the exact save the editor sends succeeds with a fresh token, notes with a
  newline and the "(8)" parentheses included;
* a token minted an hour earlier (Supabase's access-token lifetime) is a 401
  "session has expired" -- what the editor hit on 10/19, since the page held
  on to the token the app posted in when it loaded;
* a season with no row yet is created by the same PUT (no separate create).
"""

import contextlib
import io
import json
import time
from datetime import datetime, timezone

import jwt
import pytest

SECRET = "test-secret-for-hs256-tokens-only-32b"
SUPA = "https://example.supabase.co"
T0 = datetime(2026, 9, 26, 5, 51, tzinfo=timezone.utc)

NOTE = "Install requires (8) longer extension cords.\nCSW Please pack in Kit"


def token(email="justice@wenzdays.com", age_s=0, ttl_s=3600):
    now = int(time.time()) - age_s
    return jwt.encode(
        {"sub": "u-1", "email": email, "aud": "authenticated", "iss": f"{SUPA}/auth/v1",
         "iat": now, "exp": now + ttl_s, "role": "authenticated"},
        SECRET, algorithm="HS256")


@pytest.fixture
def client(fake_db, monkeypatch):
    # main loads backend/.env on import, so it goes first and the test's
    # issuer and secret are set after it.
    with contextlib.redirect_stdout(io.StringIO()):
        import main
    monkeypatch.setenv("SUPABASE_URL", SUPA)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    from app.auth import supabase_auth
    monkeypatch.setattr(supabase_auth, "_decode_with_jwks", lambda t: None)
    from fastapi.testclient import TestClient
    if main.AUTH_DISABLED:
        pytest.skip("AUTH_DISABLED is set in this shell")
    return TestClient(main.app)


def client_row(**over):
    row = {
        "id": 195, "name": "Doe, Jane", "email": "jane@example.com",
        "phone": "‭+1 (713) 555-0100‬", "notes": None,
        "street": "1 Fake Ct", "city": "Pearland", "state": "TX", "zip": "77584",
        "time_preference": None, "former_names": [], "sheet_name": "Doe, Jane",
        "secondary_contacts": "[]", "created_at": T0, "updated_at": T0,
        "staff_alert": None, "staff_alert_by": None, "staff_alert_at": None,
        "first_name": "Jane", "last_name": "Doe", "company": None, "site": None,
        "area": None, "zone": None,
    }
    row.update(over)
    return row


def activity_rows(with_2026=True):
    rows = [
        {"client_id": 195, "id": 81, "kind": "christmas_install", "season": "2022",
         "summary": "2022 install", "occurred_at": None, "created_at": T0,
         "detail": json.dumps({"install_date": None, "total": 900, "notes": "old"})},
        {"client_id": 195, "id": 524, "kind": "christmas_install", "season": "2025",
         "summary": "Installed 11/03/2025", "occurred_at": datetime(2025, 11, 3).date(),
         "created_at": T0, "detail": json.dumps({"install_date": "2025-11-03", "production_notes": "x"})},
    ]
    if with_2026:
        rows.append({
            "client_id": 195, "id": 724, "kind": "christmas_install", "season": "2026",
            "summary": "Scheduled 11/10/2026", "occurred_at": datetime(2026, 11, 10).date(),
            "created_at": T0,
            "detail": json.dumps({"install_date": "2026-11-10", "boxes": None, "total": 1963.5,
                                  "phone": "‭+1 (713) 555-0100‬"})})
    return rows


def wire(fake_db, with_2026=True):
    """The fake DB for client 195: the role row, the client, its activity
    and an upsert that echoes what was written."""
    fake_db.on_fetchval("SELECT role FROM ll_app.user_roles", None)
    fake_db.on_fetchval("SELECT name FROM clients WHERE id = $1", "Doe, Jane")
    fake_db.on_fetchval("SELECT 1 FROM clients WHERE id = $1", 1)
    fake_db.on_fetchrow("UPDATE clients SET", client_row())
    fake_db.on_fetch("FROM client_activity", activity_rows(with_2026))
    cur = next((r for r in activity_rows(with_2026) if r["season"] == "2026"), None)
    fake_db.on_fetchrow("FOR UPDATE", {"id": 724, "detail": cur["detail"]} if cur else None)
    fake_db.on("INSERT INTO client_activity",
               lambda sql, cid, season, summary, detail, occurred: {
                   "id": 724, "kind": "christmas_install", "season": season, "summary": summary,
                   "detail": detail, "occurred_at": occurred, "created_at": T0}, method="fetchrow")


#: Exactly what the editor's clientCardBody() sends when only the install
#: notes were typed: every contact field as-is, no name parts.
EDITOR_BODY = {
    "street": "1 Fake Ct", "city": "Pearland", "state": "TX", "zip": "77584",
    "phone": "‭+1 (713) 555-0100‬", "email": "jane@example.com", "notes": "",
    "time_preference": "", "secondary_contacts": [],
}


def test_editor_save_succeeds_with_a_fresh_token(client, fake_db):
    wire(fake_db)
    h = {"Authorization": f"Bearer {token()}"}
    r = client.put("/api/clients/update/195", json=EDITOR_BODY, headers=h)
    assert r.status_code == 200, r.text
    r2 = client.put("/api/clients/195/seasons/2026", json={"fields": {"notes": NOTE}}, headers=h)
    assert r2.status_code == 200, r2.text
    saved = r2.json()
    assert saved["detail"]["notes"] == NOTE
    assert "notes" in saved["detail"]["app_edits"]
    # the rest of the card is untouched
    assert saved["detail"]["install_date"] == "2026-11-10" and saved["detail"]["total"] == 1963.5


def test_a_token_from_an_hour_ago_is_refused_as_expired(client, fake_db):
    """The 10/19 failure: the page had been open past the token's hour."""
    wire(fake_db)
    h = {"Authorization": f"Bearer {token(age_s=3700)}"}
    r = client.put("/api/clients/update/195", json=EDITOR_BODY, headers=h)
    assert r.status_code == 401
    assert "expired" in r.json()["detail"]
    # nothing was written
    assert not fake_db.seen("UPDATE clients SET")
    r2 = client.put("/api/clients/195/seasons/2026", json={"fields": {"notes": NOTE}}, headers=h)
    assert r2.status_code == 401 and not fake_db.seen("INSERT INTO client_activity")


def test_season_without_a_row_is_created_by_the_same_put(client, fake_db):
    wire(fake_db, with_2026=False)
    h = {"Authorization": f"Bearer {token()}"}
    r = client.put("/api/clients/195/seasons/2026", json={"fields": {"notes": NOTE}}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["detail"] == {"notes": NOTE, "app_edits": {"notes": r.json()["detail"]["app_edits"]["notes"]}}


@pytest.mark.parametrize("email, ok", [
    ("justice@wenzdays.com", True),      # super_admin
])
def test_super_admin_may_save(client, fake_db, email, ok):
    wire(fake_db)
    r = client.put("/api/clients/195/seasons/2026", json={"fields": {"notes": NOTE}},
                   headers={"Authorization": f"Bearer {token(email=email)}"})
    assert (r.status_code == 200) is ok


def test_long_note_saves(client, fake_db):
    wire(fake_db)
    long_note = ("Bring (8) longer extension cords. " * 60).strip()
    r = client.put("/api/clients/195/seasons/2026", json={"fields": {"notes": long_note}},
                   headers={"Authorization": f"Bearer {token()}"})
    assert r.status_code == 200 and r.json()["detail"]["notes"] == long_note
