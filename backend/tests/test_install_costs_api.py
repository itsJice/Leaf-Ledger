"""The install cost card API: read with inheritance, validated writes, crew pay.

The shared ``fake_db`` harness stands in for asyncpg. The whole router is
admin-only through its module ``MIN_ROLE``, applied by main.py; that is a
route dependency, so calling the handlers directly exercises validation and
SQL, not the gate -- the gate is pinned below by reading MIN_ROLE.
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.apis import install_costs as api
from app.apis.install_costs import CardIn, ClassIn, PersonPayIn
from app.libs import schedule_board


def run(coro):
    return asyncio.run(coro)


def rows():
    return [
        {"season": "2026", "key": "pay:lead", "amount": 18, "label": "Lead"},
        {"season": "2026", "key": "pay:general", "amount": 15, "label": "General Installer"},
        {"season": "2026", "key": "van_day", "amount": 225, "label": None},
        {"season": "2026", "key": "mpg", "amount": 10, "label": None},
        {"season": "2026", "key": "gas_per_gallon", "amount": 4, "label": None},
    ]


def test_router_is_admin_only():
    assert api.MIN_ROLE == "admin"


def test_get_card_inherits_and_reports_missing(fake_db):
    fake_db.on_fetch("FROM ll_app.install_cost_rates", rows())
    out = run(api.get_card("2027"))
    assert out["own"] == [] and out["seasons"] == ["2026"]
    assert out["costs"]["van_day"] == 225
    assert {"trailer_day", "overhead_pct", "target_profit_pct"} <= set(out["missing"])
    assert out["derived"]["gas_per_mile"] == 0.4


def test_get_card_rejects_bad_season(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(api.get_card("26"))
    assert exc.value.status_code == 400


@pytest.mark.parametrize("body,why", [
    (CardIn(season="2026", costs={"tip": 5}), "tip"),
    (CardIn(season="2026", costs={"van_day": -1}), "zero or more"),
    (CardIn(season="2026", costs={"mpg": 0}), "MPG"),
    (CardIn(season="2026", costs={"overhead_pct": 100}), "under 100"),
    (CardIn(season="2026", classes=[ClassIn(label="  ")]), "name"),
    (CardIn(season="2026", classes=[ClassIn(label="Lead", rate=-2)]), "zero or more"),
])
def test_put_card_validates(fake_db, fake_user, body, why):
    with pytest.raises(HTTPException) as exc:
        run(api.put_card(body, fake_user))
    assert exc.value.status_code == 400 and why in exc.value.detail
    assert not fake_db.seen("INSERT INTO ll_app.install_cost_rates (season, key, amount, label, updated_by, updated_at)")


def test_put_card_writes_costs_classes_and_removals(fake_db, fake_user):
    fake_db.on_fetch("FROM ll_app.install_cost_rates", rows())
    run(api.put_card(CardIn(
        season="2026",
        costs={"trailer_day": 125, "van_day": None},
        classes=[ClassIn(label="Night Lead", rate=19), ClassIn(slug="lead", label="Lead", rate=18.5)],
        remove_classes=["general"],
    ), fake_user))
    writes = sorted(args for _, args in fake_db.calls("VALUES ($1, $2, $3, $4, $5, now())"))
    assert writes == sorted([
        ("2026", "trailer_day", 125.0, None, "user-1"),
        ("2026", "van_day", None, None, "user-1"),
        ("2026", "pay:night_lead", 19.0, "Night Lead", "user-1"),
        ("2026", "pay:lead", 18.5, "Lead", "user-1"),
        ("2026", "pay:general", None, None, "user-1"),
    ])


def test_put_card_copies_inherited(fake_db, fake_user):
    fake_db.on_fetch("FROM ll_app.install_cost_rates", rows())
    run(api.put_card(CardIn(season="2027", copy_from_inherited=True), fake_user))
    keys = sorted(args[1] for _, args in fake_db.calls("VALUES ($1, $2, $3, $4, $5, now())"))
    assert keys == ["gas_per_gallon", "mpg", "pay:general", "pay:lead", "van_day"]


def test_get_people_pays_by_assignment_title_or_override(fake_db, monkeypatch):
    board = schedule_board.Board(season="2026", version="v1", roster=[
        {"id": "a", "name": "Ana Lead", "title": "Lead"},
        {"id": "b", "name": "Bo Gen", "title": "General Installer"},
        {"id": "c", "name": "Cy Gen", "title": "General Installer"},
    ])

    async def fake_load(season=None, **_):
        return board
    monkeypatch.setattr(schedule_board, "load_board", fake_load)
    fake_db.on_fetch("FROM ll_app.install_cost_rates", rows())
    fake_db.on_fetch("FROM ll_app.install_pay_assignments", [
        {"person_id": "b", "person_name": "Bo Gen", "pay_class": "lead", "rate_override": None},
        {"person_id": "c", "person_name": "Cy Gen", "pay_class": None, "rate_override": 16.25},
    ])
    out = run(api.get_people("2026"))
    got = {p["person_id"]: (p["pay_class"], p["assigned"], p["rate"], p["source"]) for p in out["people"]}
    assert got == {
        "a": ("lead", False, 18, "title"),
        "b": ("lead", True, 18, "class"),
        "c": ("general", False, 16.25, "override"),
    }


def test_put_person_validates_and_upserts(fake_db, fake_user):
    with pytest.raises(HTTPException):
        run(api.put_person("p1", PersonPayIn(pay_class="Not A Slug"), fake_user))
    with pytest.raises(HTTPException):
        run(api.put_person("p1", PersonPayIn(rate_override=-1), fake_user))
    run(api.put_person("p1", PersonPayIn(name="Ana", pay_class="junior"), fake_user))
    (_, args), = fake_db.calls("INSERT INTO ll_app.install_pay_assignments")
    assert args == ("p1", "Ana", "junior", None, "user-1")
