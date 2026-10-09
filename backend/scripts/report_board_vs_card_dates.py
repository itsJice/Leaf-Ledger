#!/usr/bin/env python3
"""
READ-ONLY report: where the Install Schedule board and the client cards
disagree about a client's date (Comments #14-17).

The board owns install dates (user, 2026-10-06). Since board-date-sync, a stop
moved on the board writes its new date onto that client's season card -- but
only for moves made from then on. Cards that already disagreed are listed here
for a person to review; nothing here writes, and the board is never changed.

The board is read the way the tool shows it: the published page's DATA plus
the shared state's placement (app.libs.schedule_board.resolve). Per client:
the earliest install-visit date (an event teardown is not an install) and, if
there is one, the earliest stop after the Dec 25 cutoff as the takedown --
the same rule the page uses when it sends a move (boardDatesByClient()).

Usage (from backend/; reads DATABASE_URL, else backend/.env.supabase):

    .venv/bin/python scripts/report_board_vs_card_dates.py --report out.csv [--season 2026]

The connection is opened read-only (default_transaction_read_only). Fixing a
row means updating the card to the board's date through the app
(PUT /clients/{id}/seasons/{season}) with the user's OK -- see ll-client-cards.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.libs.schedule_board import Board, extract_payload, resolve  # noqa: E402
from app.libs.season import season_for  # noqa: E402
from split_client_names import load_database_url  # noqa: E402

REPORT_COLUMNS = ["client", "client_id", "kind", "board_date", "board_crew", "card_date",
                  "card_summary", "problem", "matched_by"]


def fold(s) -> str:
    """normName() in the page: case, commas, periods and spacing don't count."""
    out = str(s or "").strip().lower().replace(",", "").replace(".", "")
    return " ".join(out.split())


def board_dates(board: Board, cutoff: str) -> dict[str, dict]:
    """{folded board name: {name, install?, takedown?, install_crew?, takedown_crew?}}."""
    out: dict[str, dict] = {}
    for d in board.days.values():
        for r in d["stops"]:
            c = board.clients.get(r) or {}
            name = c.get("name")
            if not name:
                continue
            if d["date"] > cutoff:
                kind = "takedown"
            elif "takedown" in str(c.get("visitType") or "").lower():
                continue
            else:
                kind = "install"
            o = out.setdefault(fold(name), {"name": name})
            if not o.get(kind) or d["date"] < o[kind]:
                o[kind] = d["date"]
                o[f"{kind}_crew"] = board.crew_label(d)
    return out


def compare(board: dict[str, dict], cards: list[dict], season: str) -> list[dict]:
    """One row per board client + kind whose card does not show the board's date.

    ``cards`` are clients with their ``detail`` for this season (None when the
    client has no season row). Matching uses every spelling the app keeps
    (name, sheet_name, former_names), then a word-order-free fallback
    ("Jinks, Amy" vs "Amy Jinks"), which the report labels.
    """
    exact: dict[str, list[dict]] = {}
    loose: dict[str, list[dict]] = {}
    for c in cards:
        for s in {c.get("name"), c.get("sheet_name"), *(c.get("former_names") or [])}:
            k = fold(s)
            if k:
                exact.setdefault(k, []).append(c)
                loose.setdefault(" ".join(sorted(k.split())), []).append(c)
    rows = []
    for key, b in sorted(board.items(), key=lambda kv: (kv[1].get("install") or kv[1].get("takedown") or "", kv[0])):
        hits = {c["id"]: c for c in exact.get(key, [])}
        how = "name"
        if not hits:
            hits = {c["id"]: c for c in loose.get(" ".join(sorted(key.split())), [])}
            how = "same words, different order"
        card = next(iter(hits.values())) if len(hits) == 1 else None
        for kind, field in (("install", "install_date"), ("takedown", "takedown_date")):
            bd = b.get(kind)
            if not bd:
                continue
            base = {"client": b["name"], "kind": kind, "board_date": bd,
                    "board_crew": b.get(f"{kind}_crew", "")}
            if len(hits) > 1:
                rows.append({**base, "client_id": "", "card_date": "", "card_summary": "",
                             "problem": "several clients match this name: " + ", ".join(
                                 f'#{c["id"]} {c["name"]}' for c in hits.values()),
                             "matched_by": how})
                continue
            if card is None:
                rows.append({**base, "client_id": "", "card_date": "", "card_summary": "",
                             "problem": "no matching client on the Clients tab", "matched_by": ""})
                continue
            detail = card.get("detail")
            if detail is None:
                rows.append({**base, "client_id": card["id"], "card_date": "", "card_summary": "",
                             "problem": f"no {season} season card", "matched_by": how})
                continue
            cd = detail.get(field) or ""
            if detail.get("not_installing"):
                problem = "card says not installing"
            elif not cd:
                problem = "card has no date"
            elif cd != bd:
                problem = "different date"
            else:
                continue
            rows.append({**base, "client_id": card["id"], "card_date": cd,
                         "card_summary": card.get("summary") or "", "problem": problem,
                         "matched_by": how})
    return rows


async def read_live(conn, season: str) -> tuple[Board, list[dict]]:
    """Every read this report makes. SELECTs only -- no ensure_schema()."""
    page = await conn.fetchrow(
        "SELECT html FROM ll_app.install_schedule_pages WHERE season = $1 AND name = 'index.html'",
        season)
    if not page:
        sys.exit(f"No {season} Install Schedule page published")
    payload = extract_payload(page["html"])
    version = (payload.get("spec") or {}).get("version")
    srow = await conn.fetchrow(
        "SELECT state FROM ll_app.install_schedule_state WHERE version = $1", version)
    state = srow["state"] if srow else None
    state = json.loads(state) if isinstance(state, str) else state
    board = resolve(season, payload, state)
    rows = await conn.fetch(
        "SELECT cl.id, cl.name, cl.sheet_name, cl.former_names, ca.detail, ca.summary "
        "  FROM clients cl LEFT JOIN client_activity ca "
        "    ON ca.client_id = cl.id AND ca.kind = 'christmas_install' AND ca.season = $1",
        season)
    cards = []
    for r in rows:
        d = r["detail"]
        d = json.loads(d) if isinstance(d, str) else d
        cards.append({**dict(r), "detail": d if isinstance(d, dict) else (None if d is None else {})})
    return board, cards


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, help="CSV path to write")
    ap.add_argument("--season", default=str(season_for()))
    args = ap.parse_args()

    import asyncpg

    conn = await asyncpg.connect(load_database_url(), statement_cache_size=0,
                                 server_settings={"default_transaction_read_only": "on"})
    try:
        board, cards = await read_live(conn, args.season)
    finally:
        await conn.close()

    dates = board_dates(board, f"{args.season}-12-25")
    report = compare(dates, cards, args.season)
    with open(args.report, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_COLUMNS)
        w.writeheader()
        w.writerows(report)
    counts: dict[str, int] = {}
    for r in report:
        k = r["problem"].split(":")[0]
        counts[k] = counts.get(k, 0) + 1
    print(f"{args.season}: {len(dates)} clients on the board, {len(report)} board/card mismatches "
          f"({', '.join(f'{n} {k}' for k, n in sorted(counts.items())) or 'none'}). Wrote {args.report}")


if __name__ == "__main__":
    asyncio.run(main())
