"""The install cost card and who is paid as which class. Admin-only.

The card is one row per (season, key) in ``ll_app.install_cost_rates``
(migrations/019), read with the same season inheritance as the billing rate
card: a season with no rows of its own reads as the latest earlier season.
The arithmetic is ``app.libs.install_costs``; this module stores and serves.

Pay assignments (``ll_app.install_pay_assignments``) map a roster person id
to a pay class and an optional personal rate. They live here rather than on
the roster in the schedule state because that document is readable by the
warehouse display and by crew leads, and pay is not.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import AuthorizedUser
from app.libs import crew_day_profit
from app.libs import install_costs as ic
from app.libs import schedule_board
from app.libs.db import ensure_schema_once, get_conn
from app.libs.season import season_for

router = APIRouter(prefix="/install-costs", tags=["install-costs"])

#: Pay is private: reading the card or anyone's rate is admin-only.
MIN_ROLE = "admin"

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.install_cost_rates (
    season      text        NOT NULL,
    key         text        NOT NULL,
    amount      numeric(10,4),
    label       text,
    updated_by  text,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (season, key)
);

CREATE TABLE IF NOT EXISTS ll_app.install_pay_assignments (
    person_id     text        PRIMARY KEY,
    person_name   text,
    pay_class     text,
    rate_override numeric(10,2),
    updated_by    text,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

INSERT INTO ll_app.install_cost_rates (season, key, amount, label, updated_by) VALUES
    ('2026', 'pay:lead',              18.00, 'Lead',              'migration 019'),
    ('2026', 'pay:lead_assist',       17.00, 'Lead Assist',       'migration 019'),
    ('2026', 'pay:general',           15.00, 'General Installer', 'migration 019'),
    ('2026', 'pay:junior',            12.00, 'Junior Installer',  'migration 019'),
    ('2026', 'pay:designer',          16.50, 'Designer',          'migration 019'),
    ('2026', 'van_day',              225,    NULL,                'migration 019'),
    ('2026', 'trailer_day',          125,    NULL,                'migration 019'),
    ('2026', 'vans_per_crew',          1,    NULL,                'migration 019'),
    ('2026', 'trailers_per_crew',      1,    NULL,                'migration 019'),
    ('2026', 'mpg',                   10,    NULL,                'migration 019'),
    ('2026', 'gas_per_gallon',         4,    NULL,                'migration 019'),
    ('2026', 'ancillary_day',         20,    NULL,                'migration 019'),
    ('2026', 'load_min_per_box',       2,    NULL,                'migration 019'),
    ('2026', 'overhead_pct',          19.4,  NULL,                'migration 019'),
    ('2026', 'target_profit_pct',     16,    NULL,                'migration 019')
ON CONFLICT (season, key) DO NOTHING;
"""


async def ensure_schema(conn):
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("install_costs", _ddl)


async def load_card_rows(conn) -> List[dict]:
    """Every card row. A database without the table reads as an empty card
    (everything NEEDS INPUT) rather than a 500."""
    try:
        rows = await conn.fetch("SELECT season, key, amount, label FROM ll_app.install_cost_rates")
    except Exception as exc:  # asyncpg.UndefinedTableError, or a stub conn
        if type(exc).__name__ not in ("UndefinedTableError", "InvalidSchemaNameError"):
            raise
        return []
    return [dict(r) for r in rows]


async def load_assignments(conn) -> Dict[str, dict]:
    try:
        rows = await conn.fetch(
            "SELECT person_id, person_name, pay_class, rate_override FROM ll_app.install_pay_assignments")
    except Exception as exc:
        if type(exc).__name__ not in ("UndefinedTableError", "InvalidSchemaNameError"):
            raise
        return {}
    return {str(r["person_id"]): dict(r) for r in rows}


def _clean_season(season: Optional[str]) -> str:
    s = (season or "").strip() or str(season_for())
    if len(s) != 4 or not s.isdigit():
        raise HTTPException(status_code=400, detail="Bad season")
    return s


class PayClass(BaseModel):
    slug: str
    label: str
    rate: Optional[float] = None


class CardOut(BaseModel):
    season: str
    costs: Dict[str, float]
    classes: List[PayClass]
    #: Keys that are the season's OWN rows (the rest are inherited).
    own: List[str]
    #: Every season with at least one row, newest first.
    seasons: List[str]
    #: Required keys and classes with nothing filled in yet.
    missing: List[str]
    derived: Dict[str, Optional[float]]


class ClassIn(BaseModel):
    #: Omit (or leave blank) for a new class: it is made from the label.
    slug: Optional[str] = None
    label: str
    rate: Optional[float] = None


class CardIn(BaseModel):
    season: str
    #: key -> amount; None clears the value for this season (NEEDS INPUT).
    costs: Dict[str, Optional[float]] = {}
    #: Classes to add or change.
    classes: List[ClassIn] = []
    #: Class slugs to drop from this season on.
    remove_classes: List[str] = []
    #: Write the season's full inherited card down first, then apply the rest.
    copy_from_inherited: bool = False


def _shape(rows: List[dict], season: str) -> dict:
    card = ic.resolve_card(rows, season)
    own = sorted({r["key"] for r in rows if str(r["season"]) == season})
    seasons = sorted({str(r["season"]) for r in rows}, reverse=True)
    return {"season": season, **card, "own": own, "seasons": seasons, "derived": ic.derived(card)}


@router.get("/card", response_model=CardOut)
async def get_card(season: Optional[str] = None):
    season = _clean_season(season)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        return _shape(await load_card_rows(conn), season)
    finally:
        await conn.close()


def _planned_writes(body: CardIn, rows: List[dict], season: str) -> Dict[str, tuple]:
    """key -> (amount, label) to upsert, validated. Raises 400 on anything
    the card cannot hold."""
    writes: Dict[str, tuple] = {}
    if body.copy_from_inherited:
        card = ic.resolve_card(rows, season)
        for k, v in card["costs"].items():
            writes[k] = (v, None)
        for c in card["classes"]:
            writes[ic.PAY_PREFIX + c["slug"]] = (c["rate"], c["label"])

    bad = sorted(k for k in body.costs if k not in ic.COST_KEYS)
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown cost key(s): {', '.join(bad)}")
    for k, v in body.costs.items():
        if v is not None and v < 0:
            raise HTTPException(status_code=400, detail=f"{k} must be zero or more")
        if k in ("mpg",) and v is not None and v <= 0:
            raise HTTPException(status_code=400, detail="MPG must be more than zero")
        if k in ("overhead_pct", "target_profit_pct") and v is not None and v >= 100:
            raise HTTPException(status_code=400, detail=f"{k} must be under 100%")
        writes[k] = (v, None)

    for c in body.classes:
        label = (c.label or "").strip()
        if not label:
            raise HTTPException(status_code=400, detail="A pay class needs a name")
        slug = (c.slug or "").strip() or ic.slugify(label)
        if not ic.slug_ok(slug):
            raise HTTPException(status_code=400, detail=f"Can't make a class id from {label!r}")
        if c.rate is not None and c.rate < 0:
            raise HTTPException(status_code=400, detail=f"{label} rate must be zero or more")
        writes[ic.PAY_PREFIX + slug] = (c.rate, label[:60])

    for slug in body.remove_classes:
        if not ic.slug_ok(slug):
            raise HTTPException(status_code=400, detail=f"Bad class id {slug!r}")
        writes[ic.PAY_PREFIX + slug] = (None, None)
    return writes


@router.put("/card", response_model=CardOut)
async def put_card(body: CardIn, user: AuthorizedUser):
    season = _clean_season(body.season)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await load_card_rows(conn)
        writes = _planned_writes(body, rows, season)
        async with conn.transaction():
            for k, (amount, label) in writes.items():
                await conn.execute(
                    "INSERT INTO ll_app.install_cost_rates (season, key, amount, label, updated_by, updated_at) "
                    "VALUES ($1, $2, $3, $4, $5, now()) "
                    "ON CONFLICT (season, key) DO UPDATE SET amount = EXCLUDED.amount, "
                    "label = EXCLUDED.label, updated_by = EXCLUDED.updated_by, updated_at = now()",
                    season, k, None if amount is None else round(float(amount), 4), label, user.sub,
                )
        return _shape(await load_card_rows(conn), season)
    finally:
        await conn.close()


class PersonPay(BaseModel):
    person_id: str
    name: str
    title: str
    #: The class they are paid as (assigned, or taken from their title).
    pay_class: str
    pay_label: str
    #: True when a class was picked for them; False when it follows the title.
    assigned: bool
    rate_override: Optional[float] = None
    #: What they are actually paid per hour (None: the class has no rate).
    rate: Optional[float] = None
    source: str


class PeopleOut(BaseModel):
    season: str
    people: List[PersonPay]
    classes: List[PayClass]


def _people(roster: List[dict], assignments: Dict[str, dict], card: dict) -> List[dict]:
    out = []
    for p in roster:
        a = assignments.get(p["id"])
        pr = ic.person_rate(p, a, card)
        out.append({
            "person_id": p["id"], "name": p["name"], "title": p.get("title") or "General Installer",
            "pay_class": pr["pay_class"], "pay_label": pr["label"],
            "assigned": bool(a and a.get("pay_class") in {c["slug"] for c in card["classes"]}),
            "rate_override": ic._num((a or {}).get("rate_override")),
            "rate": pr["rate"], "source": pr["source"],
        })
    return out


@router.get("/people", response_model=PeopleOut)
async def get_people(season: Optional[str] = None):
    """Everyone on the roster with the class and rate they are paid at."""
    season = _clean_season(season)
    board = await schedule_board.load_board(season)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        card = ic.resolve_card(await load_card_rows(conn), season)
        people = _people(board.roster if board else [], await load_assignments(conn), card)
        return {"season": season, "people": people, "classes": card["classes"]}
    finally:
        await conn.close()


class PersonPayIn(BaseModel):
    #: Name, kept so the row still reads sensibly if they leave the roster.
    name: Optional[str] = None
    #: A class slug, or None to go back to paying them by roster title.
    pay_class: Optional[str] = None
    #: A personal hourly rate that beats the class rate, or None for none.
    rate_override: Optional[float] = None


@router.put("/people/{person_id}")
async def put_person(person_id: str, body: PersonPayIn, user: AuthorizedUser):
    pid = (person_id or "").strip()
    if not pid or len(pid) > 80:
        raise HTTPException(status_code=400, detail="Bad person id")
    if body.pay_class is not None and not ic.slug_ok(body.pay_class):
        raise HTTPException(status_code=400, detail="Bad pay class")
    if body.rate_override is not None and body.rate_override < 0:
        raise HTTPException(status_code=400, detail="Rate must be zero or more")
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        await conn.execute(
            "INSERT INTO ll_app.install_pay_assignments "
            "(person_id, person_name, pay_class, rate_override, updated_by, updated_at) "
            "VALUES ($1, $2, $3, $4, $5, now()) "
            "ON CONFLICT (person_id) DO UPDATE SET person_name = COALESCE(EXCLUDED.person_name, "
            "ll_app.install_pay_assignments.person_name), pay_class = EXCLUDED.pay_class, "
            "rate_override = EXCLUDED.rate_override, updated_by = EXCLUDED.updated_by, updated_at = now()",
            pid, (body.name or "").strip() or None, body.pay_class, body.rate_override, user.sub,
        )
        return {"person_id": pid, "pay_class": body.pay_class, "rate_override": body.rate_override}
    finally:
        await conn.close()


@router.get("/crew-days")
async def get_crew_days(season: Optional[str] = None):
    """Net profit for every install crew-day on the board: the day's install
    revenue against its crew, vans, gas and overhead (app.libs.crew_day_profit)."""
    season = _clean_season(season)
    board = await schedule_board.load_board(season)
    if not board:
        raise HTTPException(status_code=404, detail=f"No {season} install schedule has been published")
    # Deferred: the clients API pulls in the whole directory machinery.
    from app.apis.clients import build_client_list

    conn = await get_conn()
    try:
        await ensure_schema(conn)
        card = ic.resolve_card(await load_card_rows(conn), season)
        assignments = await load_assignments(conn)
        clients = await build_client_list(conn)
    finally:
        await conn.close()
    out = crew_day_profit.crew_days(board, crew_day_profit.price_index(clients, season), card, assignments)
    out["missing_card"] = card["missing"]
    return out
