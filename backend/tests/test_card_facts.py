"""The client card's job facts on the Install Schedule (Comment #28).

GET /api/install-schedule/card-facts lists, per client, the boxes, est.
install hours and headcounts a person edited on the season card (stamped in
detail.app_edits), with the names the page matches stops on. The schedule
lays those over its build. Reset hands a fact back to the sheet: the sheet's
value goes back on the card and the stamp is dropped. No database.
"""
import asyncio
import json

import pytest
from fastapi import HTTPException

from app.apis import clients, install_schedule
from app.libs import client_season as cs
from app.libs import roles


def run(coro):
    return asyncio.run(coro)


STACEY = {
    "id": 175, "name": "Bourque, Stacey", "sheet_name": "Bourque, Stacey", "former_names": None,
    "detail": json.dumps({
        "boxes": 29, "est_hours": 5.0, "notes": "x",
        "role_need": {"leads": 1, "specialty": 1, "designer": 0, "general": 7},
        "app_edits": {"est_hours": "2026-11-04T18:50:40+00:00", "role_need": "2026-11-04T18:50:40+00:00",
                      "notes": "2026-11-04T18:34:39+00:00"},
    }),
}


# ─── the pure shaping ────────────────────────────────────────────────────────


def test_only_app_edited_facts_are_listed():
    rows = [
        STACEY,
        # boxes stamped, hours from the sheet: only boxes
        {"id": 2, "name": "Tenaris", "sheet_name": None, "former_names": ["Tenaris USA"],
         "detail": {"boxes": 12, "est_hours": 6, "app_edits": {"boxes": "t"}}},
        # only notes edited: not a job fact, not listed
        {"id": 3, "name": "Smith, Ann", "sheet_name": "Smith Ann", "former_names": [],
         "detail": {"boxes": 4, "est_hours": 2, "app_edits": {"notes": "t"}}},
        # stamped but cleared: nothing to show
        {"id": 4, "name": "Cleared", "sheet_name": None, "former_names": [],
         "detail": {"app_edits": {"boxes": "t"}}},
        # junk detail never breaks the list
        {"id": 5, "name": "Junk", "sheet_name": None, "former_names": [], "detail": "not json"},
        {"id": 6, "name": "List", "sheet_name": None, "former_names": [], "detail": "[1]"},
    ]
    out = install_schedule.card_facts_from(rows)
    assert out == [
        {"id": 175, "name": "Bourque, Stacey", "sheet_name": "Bourque, Stacey", "former_names": [],
         "est_hours": 5.0, "role_need": {"leads": 1, "specialty": 1, "designer": 0, "general": 7},
         "edited": {"est_hours": "2026-11-04T18:50:40+00:00", "role_need": "2026-11-04T18:50:40+00:00"}},
        {"id": 2, "name": "Tenaris", "sheet_name": None, "former_names": ["Tenaris USA"],
         "boxes": 12, "edited": {"boxes": "t"}},
    ]
    # Never anything but the facts and the names: this router is readable by the TV.
    assert all(set(r) <= {"id", "name", "sheet_name", "former_names", "boxes", "est_hours",
                          "role_need", "edited"} for r in out)


# ─── the route ───────────────────────────────────────────────────────────────


def test_route_reads_one_season_of_stamped_rows(fake_db):
    fake_db.on_fetch("FROM client_activity a JOIN clients c", [STACEY])
    out = run(install_schedule.card_facts(season="2026"))
    assert [r["name"] for r in out] == ["Bourque, Stacey"]
    ((sql, args),) = fake_db.calls("FROM client_activity a JOIN clients c")
    assert args == ("2026",)
    assert "a.kind = 'christmas_install' AND a.season = $1" in sql
    assert "a.detail ? 'app_edits'" in sql
    for col in ("email", "phone", "street", "notes", "secondary_contacts"):
        assert col not in sql.split("FROM")[0]


def test_route_defaults_to_the_current_season_and_rejects_junk(fake_db, monkeypatch):
    monkeypatch.setattr(install_schedule, "season_for", lambda: 2026)
    fake_db.on_fetch("FROM client_activity a JOIN clients c", [])
    assert run(install_schedule.card_facts()) == []
    ((_, args),) = fake_db.calls("FROM client_activity a JOIN clients c")
    assert args == ("2026",)
    with pytest.raises(HTTPException) as exc:
        run(install_schedule.card_facts(season="26; drop"))
    assert exc.value.status_code == 400


@pytest.mark.parametrize("role, ok", [
    ("viewer", True), ("staff", True), ("admin", True), ("super_admin", True),
    ("crew", False), ("lead", False), ("production", False),
])
def test_who_may_read_card_facts(role, ok):
    """The shop TV shows the same numbers as the office; crew, leads and
    production don't read the card's hours and headcounts (price inputs)."""
    path = "/api/install-schedule/card-facts"
    assert install_schedule.VIEWER_READ is True
    assert roles.allowed(role, "staff", "GET", True, path) is ok
    # Saving a fact stays staff and up, through the Clients season route.
    put = "/api/clients/{client_id}/seasons/{season}"
    assert roles.allowed("viewer", "staff", "PUT", True, put) is False
    assert roles.allowed("production", "staff", "PUT", True, put) is False
    assert roles.allowed("staff", "staff", "PUT", True, put) is True


# ─── sheet values and Reset ──────────────────────────────────────────────────


def test_first_edit_keeps_the_sheet_value_and_reset_puts_it_back():
    sheet_row = {"boxes": 29, "est_hours": 6.0, "role_need": {"leads": 2, "general": 10}}
    d = cs.apply_edits(sheet_row, {"est_hours": 5, "role_need": {"leads": 1, "specialty": 1, "general": 7}}, when="T1")
    assert d["est_hours"] == 5 and d["app_edits"] == {"est_hours": "T1", "role_need": "T1"}
    assert d["sheet_values"] == {"est_hours": 6.0, "role_need": {"leads": 2, "general": 10}}
    # A second edit keeps the sheet's number, not the first edit's.
    d = cs.apply_edits(d, {"est_hours": 4.5}, when="T2")
    assert d["sheet_values"]["est_hours"] == 6.0
    # Reset hours: the sheet's 6h goes back and the stamp is dropped.
    d = cs.apply_edits(d, {}, reset=["est_hours"])
    assert d["est_hours"] == 6.0 and "est_hours" not in d["app_edits"]
    assert d["sheet_values"] == {"role_need": {"leads": 2, "general": 10}}
    d = cs.apply_edits(d, {}, reset=["role_need"])
    assert d["role_need"] == {"leads": 2, "general": 10}
    assert "sheet_values" not in d and "app_edits" not in d


def test_reset_without_a_known_sheet_value():
    # Edited before sheet values were kept (Stacey's card, 11/04).
    d = {"est_hours": 5.0, "boxes": 29, "role_need": {"leads": 1, "general": 7},
         "app_edits": {"est_hours": "t", "role_need": "t", "boxes": "t"}}
    # The schedule sends its build's headcounts as the fallback...
    out = cs.apply_edits(d, {"role_need": {"leads": 2, "specialty": 2, "designer": 0, "general": 10}},
                         reset=["role_need", "est_hours"])
    assert out["role_need"] == {"leads": 2, "specialty": 2, "designer": 0, "general": 10}
    # ...but no hours (its hours are calibrated, not the sheet's): the card
    # keeps 5h, unstamped, until the next sheet sync refreshes it.
    assert out["est_hours"] == 5.0
    assert out["app_edits"] == {"boxes": "t"}
    with pytest.raises(cs.FieldError):
        cs.apply_edits(d, {}, reset=["colour"])


def test_sheet_sync_keeps_the_sheet_value_fresh_while_an_edit_stands():
    prior = {"est_hours": 5.0, "boxes": 29, "app_edits": {"est_hours": "t"},
             "sheet_values": {"est_hours": 6.0}}
    out = cs.merge_sheet_detail(prior, {"est_hours": 6.5, "boxes": 30})
    assert out["est_hours"] == 5.0 and out["boxes"] == 30
    assert out["sheet_values"] == {"est_hours": 6.5}
    # Once the edit is gone (reset), the sync drops the kept value too.
    out = cs.merge_sheet_detail({"est_hours": 6.0, "sheet_values": {"est_hours": 6.0}}, {"est_hours": 6.5})
    assert out == {"est_hours": 6.5}


def test_put_season_with_reset(fake_db, fake_request, monkeypatch):
    monkeypatch.setattr(cs, "now_iso", lambda: "T")
    fake_db.on_fetchval("SELECT 1 FROM clients WHERE id = $1", 1)
    fake_db.on_fetchrow("FOR UPDATE", {"id": 9, "detail": {
        "boxes": 30, "est_hours": 5.0, "app_edits": {"boxes": "t0", "est_hours": "t0"},
        "sheet_values": {"boxes": 29}}})
    fake_db.on("INSERT INTO client_activity",
               lambda sql, cid, season, summary, detail, occurred: {
                   "id": 9, "kind": "christmas_install", "season": season, "summary": summary,
                   "detail": detail, "occurred_at": occurred, "created_at": None}, method="fetchrow")
    body = clients.SeasonFieldsIn(fields={"est_hours": 4}, reset=["boxes"])
    out = run(clients.update_client_season(175, "2026", body, fake_request()))
    assert out["detail"]["boxes"] == 29 and out["detail"]["est_hours"] == 4
    assert out["detail"]["app_edits"] == {"est_hours": "T"}
    assert "sheet_values" not in out["detail"]
    # Reset alone is a valid request; nothing at all is not.
    run(clients.update_client_season(175, "2026", clients.SeasonFieldsIn(reset=["est_hours"]), fake_request()))
    with pytest.raises(HTTPException) as exc:
        run(clients.update_client_season(175, "2026", clients.SeasonFieldsIn(), fake_request()))
    assert exc.value.status_code == 400
