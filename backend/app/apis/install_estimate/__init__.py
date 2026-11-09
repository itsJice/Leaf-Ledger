"""Install estimates: the per-item rates (Settings > Install Estimates) and a
client's suggested hours for a season (the client card's "Suggested 2027").

The math is pure, in ``app.libs.install_estimate`` (spec beside it). This
router only gathers the inputs: the client's season cards (inventory, boxes,
real hours, ZIP), their Install Times (``ll_app.install_actuals_latest``),
the board's Business/Residence flag, and the rates.

Rates live in ``ll_app.estimate_rates`` (migrations/029): one row per
(season, key). A season uses its own amount for a key, else the latest
earlier season's (like Christmas Rates). A key nobody set is NEEDS INPUT.

Roles: office staff and up read (the router's MIN_ROLE); admins change the
rates. Nothing here writes a client's card: Accept on the card goes through
the normal season save (PUT /clients/{id}/seasons/{season}).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import AuthorizedUser
from app.libs import install_estimate as E
from app.libs import schedule_board
from app.libs.db import ensure_schema_once, get_conn
from app.libs.roles import require_role

router = APIRouter(prefix="/install-estimate", tags=["install-estimate"])

MIN_ROLE = "staff"

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.estimate_rates (
    season     text NOT NULL,
    key        text NOT NULL,
    amount     numeric(10, 3) NOT NULL CHECK (amount >= 0),
    note       text,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (season, key)
);
"""


async def ensure_schema(conn) -> None:
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("estimate_rates", _ddl)


def _season(s: Optional[str]) -> str:
    s = str(s or "").strip()
    if not re.fullmatch(r"\d{4}", s):
        raise HTTPException(status_code=400, detail="season must be a year")
    return s


def resolve_rates(rows: list[dict], season: str) -> dict[str, dict]:
    """{key: {amount, fromSeason, own}} for ``season``: its own row, else
    the latest earlier season's. Keys with nothing are amount None."""
    out = {k: {"amount": None, "fromSeason": None, "own": False} for k in E.RATE_KEYS}
    for r in sorted(rows, key=lambda r: str(r["season"])):
        if str(r["season"]) <= season and r["key"] in out:
            out[r["key"]] = {"amount": float(r["amount"]), "fromSeason": str(r["season"]),
                             "own": str(r["season"]) == season}
    return out


async def _rate_rows(conn) -> list[dict]:
    await ensure_schema(conn)
    return [dict(r) for r in await conn.fetch("SELECT season, key, amount FROM ll_app.estimate_rates")]


@router.get("/rates")
async def get_rates(season: str) -> dict:
    s = _season(season)
    conn = await get_conn()
    try:
        rows = await _rate_rows(conn)
    finally:
        await conn.close()
    return {
        "season": s,
        "rates": resolve_rates(rows, s),
        "keys": [{"key": k, "unit": u, "help": h} for k, (u, h) in E.RATE_KEYS.items()],
        "seasons": sorted({str(r["season"]) for r in rows}),
    }


class RatesIn(BaseModel):
    season: str
    #: {key: amount}; null removes this season's own amount for that key.
    rates: dict[str, Optional[float]]


@router.put("/rates", dependencies=[Depends(require_role("admin"))])
async def put_rates(body: RatesIn, user: AuthorizedUser) -> dict:
    s = _season(body.season)
    bad = [k for k in body.rates if k not in E.RATE_KEYS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown rate: {', '.join(bad)}")
    if any(v is not None and (v < 0 or v > 10000) for v in body.rates.values()):
        raise HTTPException(status_code=400, detail="Rates must be between 0 and 10000")
    who = user.email
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        async with conn.transaction():
            for k, v in body.rates.items():
                if v is None:
                    await conn.execute("DELETE FROM ll_app.estimate_rates WHERE season = $1 AND key = $2", s, k)
                else:
                    await conn.execute(
                        "INSERT INTO ll_app.estimate_rates (season, key, amount, updated_by) VALUES ($1,$2,$3,$4) "
                        "ON CONFLICT (season, key) DO UPDATE SET amount = EXCLUDED.amount, "
                        "updated_by = EXCLUDED.updated_by, updated_at = now()", s, k, v, who)
    finally:
        await conn.close()
    return await get_rates(s)


# ─── a client's suggestion ───────────────────────────────────────────────────


def _detail(v) -> dict:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return {}
    return v if isinstance(v, dict) else {}


def _num(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def gather(season: str, cards: list[dict], actuals: list[dict]) -> dict:
    """The estimate inputs for ``season`` from a client's season cards
    (``{season, detail}``) and Install Times rows (``{season, kind,
    actualHours}``). Pure, so it's tested without a database."""
    by_season = {str(c["season"]): _detail(c["detail"]) for c in cards}
    real_times: dict[str, Optional[float]] = {}
    for a in actuals:
        if a.get("kind") != "install":
            continue
        s = str(a["season"])
        h = a.get("actualHours")
        if h is None:
            real_times[s] = real_times.get(s)  # keep "seen", not a number
            continue
        real_times[s] = round((real_times.get(s) or 0) + float(h), 2)
    history = []
    for s in sorted(set(by_season) | set(real_times)):
        if s >= season:
            continue
        d = by_season.get(s, {})
        if d.get("cancelled") or d.get("not_installing"):
            continue
        hours, source = real_times.get(s), "install_times"
        if hours is None:
            hours, source = _num(d.get("real_hours")), "card"
        history.append({"season": s, "hours": hours, "source": source if hours else None,
                        "inventory": d.get("inventory") or [], "boxes": d.get("boxes")})
    # This season's stuff: its own card, else the latest earlier card with an
    # inventory (the client's things rarely change year to year).
    target = by_season.get(season, {})
    inv, boxes, from_season = target.get("inventory"), target.get("boxes"), season if target.get("inventory") else None
    if not inv:
        for s in sorted(by_season, reverse=True):
            if s < season and by_season[s].get("inventory"):
                inv, from_season = by_season[s]["inventory"], s
                boxes = boxes or by_season[s].get("boxes")
                break
    if boxes is None:
        boxes = next((by_season[s].get("boxes") for s in sorted(by_season, reverse=True)
                      if s <= season and by_season[s].get("boxes")), None)
    zips = [str(d.get("zip") or "") for d in by_season.values()]
    return {"history": history, "inventory": inv or [], "boxes": boxes, "inventoryFrom": from_season,
            "night": any(z[:2] in ("75", "76") for z in zips if z),
            "currentEst": _num(target.get("est_hours"))}


@router.get("/client/{client_id}")
async def client_suggestion(client_id: int, season: str) -> dict:
    """Suggested on-site hours for ``season`` (normally next season)."""
    from app.apis import install_actuals as IA
    from app.apis.lead import norm_name

    s = _season(season)
    conn = await get_conn()
    try:
        client = await conn.fetchrow(
            "SELECT id, name, sheet_name, former_names, zip FROM clients WHERE id = $1", client_id)
        if not client:
            raise HTTPException(status_code=404, detail="No client with that id")
        cards = [dict(r) for r in await conn.fetch(
            "SELECT season, detail FROM client_activity WHERE client_id = $1 AND kind = 'christmas_install'",
            client_id)]
        await IA.ensure_schema(conn)
        actuals = [{"season": r["season"], "kind": r["kind"],
                    "actualHours": IA.T.on_site_hours(r["arrive_at"], r["depart_at"])}
                   for r in await conn.fetch(
                       "SELECT season, kind, arrive_at, depart_at FROM ll_app.install_actuals_latest "
                       "WHERE client_id = $1", client_id)]
        rates = {k: v["amount"] for k, v in resolve_rates(await _rate_rows(conn), s).items()}
    finally:
        await conn.close()

    g = gather(s, cards, actuals)
    commercial = False
    try:
        board = await schedule_board.load_board()
    except Exception:  # noqa: BLE001 - the suggestion still works without the board
        board = None
    if board:
        names = {norm_name(n) for n in [client["name"], client["sheet_name"], *(client["former_names"] or [])] if n}
        bc = next((c for c in board.clients.values() if norm_name(c.get("name")) in names), None)
        commercial = bool(bc) and IA.T.job_type_of(bc) in ("commercial", "restaurant")
    night = g["night"] or str(client["zip"] or "")[:2] in ("75", "76")
    out = E.estimate(inventory=g["inventory"], boxes=g["boxes"], history=g["history"], rates=rates,
                     night=night, commercial=commercial)
    return {"clientId": client_id, "season": s, **out, "currentEst": g["currentEst"],
            "inventoryFrom": g["inventoryFrom"], "night": night, "commercial": commercial,
            "history": [{"season": h["season"], "hours": h["hours"], "source": h["source"]} for h in g["history"]]}
