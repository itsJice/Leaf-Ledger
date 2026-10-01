"""The rate-card API: read with inheritance, admin write, key validation.

The shared ``fake_db`` harness stands in for asyncpg. The role gate on the
PUT is a FastAPI dependency, so calling the handler directly exercises the
body validation and SQL, not the gate -- that is pinned by the route table
in ``test_openapi_snapshot.py`` and the shared ``require_role`` tests.
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.apis import pricing as api
from app.apis.pricing import RatesIn


def run(coro):
    return asyncio.run(coro)


def rows_2026():
    return [{"season": "2026", "key": k, "amount": a} for k, a in (
        ("crew_lead", 100), ("general", 75), ("storage_box", 75))]


def test_get_rates_inherits_and_lists_seasons(fake_db):
    fake_db.on_fetch("FROM ll_app.pricing_rates",
                     rows_2026() + [{"season": "2025", "key": "designer", "amount": 150}])
    out = run(api.get_rates("2027"))
    assert out == {"season": "2027",
                   "rates": {"crew_lead": 100.0, "general": 75.0, "storage_box": 75.0, "designer": 150.0},
                   "own": [], "seasons": ["2026", "2025"]}
    out = run(api.get_rates("2026"))
    assert out["own"] == ["crew_lead", "general", "storage_box"]
    assert fake_db.ddl_runs == 1  # the CREATE TABLE ran once


def test_get_rates_rejects_bad_season(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(api.get_rates("26"))
    assert exc.value.status_code == 400


def test_put_rates_validates_keys_and_amounts(fake_db, fake_user):
    with pytest.raises(HTTPException) as exc:
        run(api.put_rates(RatesIn(season="2026", rates={"crew_lead": 100, "tip": 5}), fake_user))
    assert exc.value.status_code == 400 and "tip" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        run(api.put_rates(RatesIn(season="2026", rates={"crew_lead": -1}), fake_user))
    assert exc.value.status_code == 400
    assert not fake_db.seen("INSERT")


def test_put_rates_upserts_and_can_copy_inherited(fake_db, fake_user):
    fake_db.on_fetch("FROM ll_app.pricing_rates", rows_2026())
    run(api.put_rates(RatesIn(season="2027", rates={"crew_lead": 110}), fake_user))
    writes = [args for _, args in fake_db.calls("INSERT INTO ll_app.pricing_rates")]
    assert writes == [("2027", "crew_lead", 110.0, "user-1")]

    fake_db.executed.clear()
    run(api.put_rates(RatesIn(season="2027", rates={"crew_lead": 110}, copy_from_inherited=True), fake_user))
    writes = sorted(args for _, args in fake_db.calls("INSERT INTO ll_app.pricing_rates"))
    # the explicit value wins; every inherited key is written down as 2027's own
    assert writes == [("2027", "crew_lead", 110.0, "user-1"), ("2027", "general", 75.0, "user-1"),
                      ("2027", "storage_box", 75.0, "user-1")]


def test_load_rate_rows_survives_missing_table(fake_db):
    class Undefined(Exception):
        pass
    Undefined.__name__ = "UndefinedTableError"

    def boom(sql, *args):
        raise Undefined()
    fake_db.on("FROM ll_app.pricing_rates", boom, method="fetch")
    conn = run(api.get_conn())
    assert run(api.load_rate_rows(conn)) == []
