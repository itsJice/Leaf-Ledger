"""Job budgets: each install job's price against its install and estimated
takedown cost, and the crew-hours it can take before it misses the target
profit or loses money (app.libs.job_budget). Admin-only: it shows pay.

The inputs are the crew-day profit page's (the published board, the client
directory's season prices, the install cost card, pay assignments), so the
two pages always agree; this groups the crew-days' stops into jobs.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.apis.install_costs import _clean_season, ensure_schema, load_assignments, load_card_rows
from app.libs import crew_day_profit, job_budget, schedule_board
from app.libs import install_costs as ic
from app.libs.db import get_conn

router = APIRouter(prefix="/job-budgets", tags=["job-budgets"])

#: Pay is private: job budgets are built from every installer's rate.
MIN_ROLE = "admin"


@router.get("")
async def get_job_budgets(season: Optional[str] = None):
    """Every job on the season's install board, worst net % first."""
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
    prices = crew_day_profit.price_index(clients, season)
    days = crew_day_profit.crew_days(board, prices, card, assignments)
    out = job_budget.job_budgets(days, prices, board, card, job_budget.last_year_index(clients, season))
    out["missing_card"] = card["missing"]
    return out
