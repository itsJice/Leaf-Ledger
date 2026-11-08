"""Install estimate API: rate inheritance, admin-only edits, gathering a
client's inputs, and the suggestion end to end on a fake database."""

import asyncio
import pathlib
import re
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.apis import install_estimate as IE
from app.auth.user import User
from app.libs import install_times as T
from app.libs import roles, schedule_board


def run(coro):
    return asyncio.run(coro)


def test_router_roles():
    assert IE.MIN_ROLE == "staff"
    assert not roles.allowed("lead", IE.MIN_ROLE, "GET")
    assert not roles.allowed("production", IE.MIN_ROLE, "GET", path="/api/install-estimate/client/1")
    put = next(r for r in IE.router.routes if r.path.endswith("/rates") and "PUT" in r.methods)
    assert put.dependencies, "PUT /rates must require admin"


def test_rates_inherit_the_latest_earlier_season():
    rows = [{"season": "2025", "key": "setup", "amount": 30}, {"season": "2026", "key": "setup", "amount": 35},
            {"season": "2025", "key": "box", "amount": 2.5}, {"season": "2028", "key": "box", "amount": 9}]
    r = IE.resolve_rates(rows, "2027")
    assert r["setup"] == {"amount": 35.0, "fromSeason": "2026", "own": False}
    assert r["box"] == {"amount": 2.5, "fromSeason": "2025", "own": False}
    assert r["wreath"] == {"amount": None, "fromSeason": None, "own": False}
    assert IE.resolve_rates(rows, "2026")["setup"]["own"] is True


def test_put_rates_rejects_unknown_keys_and_negative(fake_db):
    u = User(sub="a", user_id="a", email="admin@example.com", name="a")
    with pytest.raises(HTTPException) as exc:
        run(IE.put_rates(IE.RatesIn(season="2026", rates={"bogus": 1}), u))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException):
        run(IE.put_rates(IE.RatesIn(season="2026", rates={"setup": -1}), u))
    run(IE.put_rates(IE.RatesIn(season="2026", rates={"setup": 30, "box": None}), u))
    assert fake_db.calls("INSERT INTO ll_app.estimate_rates")[0][1] == ("2026", "setup", 30, "admin@example.com")
    assert fake_db.calls("DELETE FROM ll_app.estimate_rates")[0][1] == ("2026", "box")


def test_gather_prefers_install_times_then_card_hours_and_carries_inventory():
    inv = [{"type": "tree", "size": "9 ft", "qty": 1}]
    cards = [
        {"season": "2024", "detail": {"real_hours": 3.5}},
        {"season": "2025", "detail": {"real_hours": 2.0, "inventory": inv, "boxes": 6, "zip": "77005"}},
        {"season": "2026", "detail": '{"est_hours": 2.4}'},
    ]
    actuals = [{"season": "2025", "kind": "install", "actualHours": 1.5},
               {"season": "2025", "kind": "install", "actualHours": 1.0},
               {"season": "2025", "kind": "takedown", "actualHours": 0.7}]
    g = IE.gather("2027", cards, actuals)
    assert [(h["season"], h["hours"], h["source"]) for h in g["history"]] == [
        ("2024", 3.5, "card"), ("2025", 2.5, "install_times"), ("2026", None, None)]
    assert g["inventory"] == inv and g["inventoryFrom"] == "2025" and g["boxes"] == 6
    assert g["night"] is False and g["currentEst"] is None
    assert IE.gather("2026", cards, actuals)["currentEst"] == 2.4


def test_gather_skips_not_installing_seasons():
    cards = [{"season": "2025", "detail": {"real_hours": 2.0, "not_installing": True}}]
    assert IE.gather("2027", cards, [])["history"] == []


def test_client_suggestion_end_to_end(fake_db, monkeypatch):
    b = schedule_board.resolve("2026", {"spec": {}, "clients": {"5": {"name": "Smith, Ann", "bus": "Residence"}},
                                        "days": []}, {})

    async def fake_load(*_, **__):
        return b

    monkeypatch.setattr(schedule_board, "load_board", fake_load)
    fake_db.on_fetchrow("FROM clients WHERE id", {"id": 7, "name": "Smith, Ann", "sheet_name": None,
                                                  "former_names": [], "zip": "77005"})
    fake_db.on_fetch("FROM client_activity WHERE client_id", [
        {"season": "2025", "detail": {"real_hours": 2.0, "boxes": 6}}])
    fake_db.on_fetch("FROM ll_app.install_actuals_latest WHERE client_id", [
        {"season": "2025", "kind": "install", "arrive_at": datetime(2025, 11, 20, 9, 0, tzinfo=T.TZ),
         "depart_at": datetime(2025, 11, 20, 11, 40, tzinfo=T.TZ)}])
    out = run(IE.client_suggestion(7, season="2027"))
    assert (out["hours"], out["basis"], out["confidence"]) == (2.75, "last_real", "medium")
    assert out["basisText"].startswith("2025 real 2.67 h")
    assert out["commercial"] is False and out["night"] is False
    assert not fake_db.seen("INSERT INTO client_activity")
    assert not fake_db.seen("UPDATE client_activity")


def test_client_suggestion_needs_input_for_a_new_client(fake_db, monkeypatch):
    async def no_board(*_, **__):
        return None

    monkeypatch.setattr(schedule_board, "load_board", no_board)
    fake_db.on_fetchrow("FROM clients WHERE id", {"id": 8, "name": "New Co", "sheet_name": None,
                                                  "former_names": [], "zip": "75201"})
    out = run(IE.client_suggestion(8, season="2027"))
    assert out["hours"] is None and out["basis"] == "needs_input"
    assert "inventory" in out["needsInput"] and out["night"] is True


def test_bad_season_is_400(fake_db):
    with pytest.raises(HTTPException):
        run(IE.get_rates("27"))


def test_migration_matches_router_ddl():
    mig = (pathlib.Path(__file__).resolve().parent.parent / "migrations" / "029_estimate_rates.sql").read_text()

    def norm(sql):
        return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", sql)).strip()

    assert norm(IE.DDL) == norm(mig)
