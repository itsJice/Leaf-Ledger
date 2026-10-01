"""Quote calculator: what one job costs us and what it should sell for at
each profit level. Admin-only (it reads pay rates).

The arithmetic is ``app.libs.quote``; the cost card is the one the
install-costs API stores. ``/jobs`` lists the season's scheduled jobs so a
quote can start from a real one.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.apis.install_costs import _clean_season, ensure_schema, load_card_rows
from app.libs import crew_day_profit as cdp
from app.libs import install_costs as ic
from app.libs import quote as q
from app.libs import schedule_board
from app.libs.db import get_conn
from app.libs.install_calendar import ROAD_FUDGE, leg_seconds

router = APIRouter(prefix="/install-quote", tags=["install-quote"])

#: Pay rates are private: the calculator is admin-only.
MIN_ROLE = "admin"


class QuoteIn(BaseModel):
    season: Optional[str] = None
    #: pay class slug -> how many of them on the crew
    crew: Dict[str, int] = Field(default_factory=dict)
    install_onsite_h: float = Field(0, ge=0, le=200)
    #: None: install hours x the card's takedown factor
    takedown_onsite_h: Optional[float] = Field(None, ge=0, le=200)
    include_takedown: bool = True
    drive_min_each_way: Optional[float] = Field(None, ge=0, le=600)
    #: None: from the drive time at the scheduler's 27 mph
    miles_each_way: Optional[float] = Field(None, ge=0, le=1000)
    boxes: int = Field(0, ge=0, le=5000)
    stored_with_us: bool = True
    designer_hours: float = Field(0, ge=0, le=1000)
    materials: float = Field(0, ge=0, le=1_000_000)
    price: Optional[float] = Field(None, ge=0, le=10_000_000)

    @field_validator("crew")
    @classmethod
    def _crew_ok(cls, v: Dict[str, int]) -> Dict[str, int]:
        if len(v) > 40:
            raise ValueError("Too many crew classes")
        for slug, n in v.items():
            if not ic.slug_ok(slug):
                raise ValueError(f"Bad pay class {slug!r}")
            if n < 0 or n > 100:
                raise ValueError(f"{slug}: crew count must be 0 to 100")
        return v


def _calc(rows: List[dict], body: QuoteIn) -> dict:
    season = _clean_season(body.season)
    card = ic.resolve_card(rows, season)
    inputs = body.model_dump(exclude={"season"})
    out = q.quote(card, inputs)
    missing = list(card["missing"])
    missing += [m for m in out["missing"] if m not in missing]
    return {
        **out, "season": season,
        "overhead_pct": ic.value(card, "overhead_pct"),
        "target_profit_pct": ic.value(card, "target_profit_pct"),
        "classes": card["classes"],
        "missing": missing,
    }


@router.post("/calc")
async def post_calc(body: QuoteIn):
    """Cost one job against the season's cost card, with the price needed
    (and, given a price, the room left) at each profit level."""
    _clean_season(body.season)
    conn = await get_conn()
    try:
        await ensure_schema(conn)
        rows = await load_card_rows(conn)
    finally:
        await conn.close()
    return _calc(rows, body)


def _num(v) -> Optional[float]:
    return cdp._num(v)


def job_entries(board: schedule_board.Board, prices: Dict[str, dict]) -> List[dict]:
    """Every job on the board's crew-days, with what a quote needs to start
    from it: price, hours, boxes, drive from the branch and a crew."""
    scheduled = {r for d in board.days.values() for r in d.get("stops") or []}
    out = []
    for row in scheduled:
        c = board.clients.get(row)
        if not c:
            continue
        entry = prices.get(cdp.norm_name(c.get("name"))) or {}

        def fee(key: str, board_key: str) -> Optional[float]:
            v = entry.get(key)
            return v if v is not None else _num(c.get(board_key))

        install, takedown, storage = fee("install", "installFee"), fee("takedown", "takedownFee"), fee("storage", "storageFee")
        total = entry.get("total")
        if total is None and any(v is not None for v in (install, takedown, storage)):
            total = sum(v or 0 for v in (install, takedown, storage))

        secs = leg_seconds(board, None, row)
        dep, here = board.depot or {}, c
        miles = None
        if None not in (_num(dep.get("lat")), _num(dep.get("lon")), _num(here.get("lat")), _num(here.get("lon"))):
            miles = cdp._haversine_mi((_num(dep["lat"]), _num(dep["lon"])), (_num(here["lat"]), _num(here["lon"]))) * ROAD_FUDGE

        slugs, basis = cdp.estimated_crew(board, [row])
        crew: Dict[str, int] = {}
        for s in slugs:
            crew[s] = crew.get(s, 0) + 1

        size25 = _num(c.get("size25"))
        out.append({
            "row": row,
            "name": entry.get("name") or c.get("name"),
            "sheet_name": c.get("name"),
            "price": {
                "total": total, "install": install, "takedown": takedown, "storage": storage,
                "source": "clients" if entry.get("install") is not None else (
                    "schedule" if _num(c.get("installFee")) is not None else (
                        "no_charge" if c.get("noCharge") else "unpriced")),
            },
            "h26": _num(c.get("h26")),
            "boxes": int(_num(c.get("boxes")) or 0),
            "size25": int(size25) if size25 else None,
            "real25": _num(c.get("real25")),
            # The sheet's storage column: "YES" / "NO" / "NO — client stores it" /
            # blank or "Ask". Only a no means the boxes are not on our shelves.
            "stored_with_us": not (c.get("storage") is False or str(c.get("storage") or "").strip().upper().startswith("NO")),
            "drive_min_each_way": round(secs / 60) if secs else None,
            "miles_each_way": round(miles, 1) if miles is not None else None,
            "crew": crew,
            "crew_basis": basis,
        })
    out.sort(key=lambda j: (str(j["name"] or "").lower(), j["row"]))
    return out


@router.get("/jobs")
async def get_jobs(season: Optional[str] = None):
    """The season's scheduled jobs, for starting a quote from a real one."""
    season = _clean_season(season)
    board = await schedule_board.load_board(season)
    if not board:
        return {"season": season, "jobs": []}
    # Deferred: the clients API pulls in the whole directory machinery.
    from app.apis.clients import build_client_list

    conn = await get_conn()
    try:
        clients = await build_client_list(conn)
    finally:
        await conn.close()
    return {"season": season, "jobs": job_entries(board, cdp.price_index(clients, season))}
