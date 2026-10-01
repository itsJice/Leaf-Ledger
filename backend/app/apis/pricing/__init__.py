"""The Christmas install rate card, per season.

One row per (season, key) in ``ll_app.pricing_rates`` (migrations/018). The
ideal price of a job is ``app.libs.pricing`` applied to these and the
client's Christmas card; this module only stores and serves the rates.
Reading is open to anyone signed in, because every price on the Clients tab
depends on them; changing them is admin-only, like the product markup.

A season with no rows of its own reads as the latest earlier season, so the
first look at a new year is never blank. ``copy_from`` on a PUT writes that
inherited set down as real rows for the new season in one go.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import AuthorizedUser
from app.libs.db import ensure_schema_once, get_conn
from app.libs.pricing import RATE_KEYS, resolve_rates
from app.libs.roles import require_role
from app.libs.season import season_for

router = APIRouter(prefix="/pricing", tags=["pricing"])

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.pricing_rates (
    season      text        NOT NULL,
    key         text        NOT NULL,
    amount      numeric(10,2) NOT NULL,
    updated_by  text,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (season, key)
);
"""


async def ensure_schema(conn):
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("pricing_rates", _ddl)


async def load_rate_rows(conn) -> List[dict]:
    """Every (season, key, amount) row. A database the migration has not
    reached yet reads as no rates rather than a 500 -- the clients list
    must keep working, it just prices nothing."""
    try:
        rows = await conn.fetch("SELECT season, key, amount FROM ll_app.pricing_rates")
    except Exception as exc:  # asyncpg.UndefinedTableError, or a stub conn
        if type(exc).__name__ not in ("UndefinedTableError", "InvalidSchemaNameError"):
            raise
        return []
    return [dict(r) for r in rows]


def _clean_season(season: Optional[str]) -> str:
    s = (season or "").strip() or str(season_for())
    if len(s) != 4 or not s.isdigit():
        raise HTTPException(status_code=400, detail="Bad season")
    return s


class RatesOut(BaseModel):
    season: str
    #: key -> amount in force for that season (own rows plus inherited).
    rates: Dict[str, float]
    #: Which keys are the season's OWN rows (the rest are inherited).
    own: List[str]
    #: Every season that has at least one row, newest first.
    seasons: List[str]


class RatesIn(BaseModel):
    season: str
    rates: Dict[str, float]
    #: Write the season's full inherited set down first, then apply ``rates``.
    copy_from_inherited: bool = False


def _shape(rows: List[dict], season: str) -> dict:
    own = sorted({r["key"] for r in rows if str(r["season"]) == season})
    seasons = sorted({str(r["season"]) for r in rows}, reverse=True)
    return {"season": season, "rates": resolve_rates(rows, season), "own": own, "seasons": seasons}


@router.get("/rates", response_model=RatesOut)
async def get_rates(season: Optional[str] = None):
    season = _clean_season(season)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        return _shape(await load_rate_rows(conn), season)
    finally:
        await conn.close()


@router.put("/rates", response_model=RatesOut, dependencies=[Depends(require_role("admin"))])
async def put_rates(body: RatesIn, user: AuthorizedUser):
    season = _clean_season(body.season)
    bad = sorted(k for k in body.rates if k not in RATE_KEYS)
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown rate key(s): {', '.join(bad)}")
    for k, v in body.rates.items():
        if v is None or v < 0:
            raise HTTPException(status_code=400, detail=f"{k} must be zero or more")
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await load_rate_rows(conn)
        writes = dict(body.rates)
        if body.copy_from_inherited:
            inherited = resolve_rates(rows, season)
            for k, v in inherited.items():
                writes.setdefault(k, v)
        async with conn.transaction():
            for k, v in writes.items():
                await conn.execute(
                    "INSERT INTO ll_app.pricing_rates (season, key, amount, updated_by, updated_at) "
                    "VALUES ($1, $2, $3, $4, now()) "
                    "ON CONFLICT (season, key) DO UPDATE SET amount = EXCLUDED.amount, "
                    "updated_by = EXCLUDED.updated_by, updated_at = now()",
                    season, k, round(float(v), 2), user.sub,
                )
        return _shape(await load_rate_rows(conn), season)
    finally:
        await conn.close()
