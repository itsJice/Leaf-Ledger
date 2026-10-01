"""Freeze a season's prices from the billing export that went to clients.

The scheduler's review page used to COMPUTE the price in browser JavaScript
("last year's invoice + 5%") and export it; nothing stored the result. For
2026 that export is what clients received and some have already paid, so
those numbers are the season's price, full stop -- they are loaded here as
the season's ``install_fee`` / ``takedown_fee`` / ``storage_fee`` / ``total``
and never recomputed. From here on the app is the record: the ideal price
is computed from the client's Christmas card (app.libs.pricing) and the
charged price is what this script, or a person on the Clients tab, set.

Every value is written through ``client_season.apply_edits`` so it is
stamped in ``detail.app_edits`` and the spreadsheet sync never overwrites
it. A stamped value can only be changed by clearing it in the season editor
(or re-running this with a corrected file -- the load is idempotent).

Usage (from scheduler/)::

    python load_prices.py --file ~/Downloads/tbdg-2026-billing-all.xlsx --season 2026 --dry-run
    python load_prices.py --file ~/Downloads/tbdg-2026-billing-all.xlsx --season 2026

The workbook is the review page's own xlsx export: one sheet, a header row
matched by TEXT (column order is whatever the exporter chose that day), one
row per client with "Bill-to name/company", the four money columns and
"Pricing basis", a blank spacer, then a "TOTAL — N clients" footer. Names are
matched to ``clients`` exactly the way the sync matches the spreadsheet
(``sync_clients.find_client_by_name``: sheet spelling, current name, or a
former name). Any name that matches nothing aborts the run before a single
write, because a silently skipped client would be an unpriced job nobody
noticed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Optional

import asyncpg
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import current_season, load_env  # noqa: E402
import season as _season_bridge  # noqa: E402,F401  (puts backend/ on sys.path)
from app.libs import client_season  # noqa: E402
from sync_clients import ENV_FILE, find_client_by_name, money, to_date  # noqa: E402

#: Export header -> season detail key. The "<season>" in a header is the
#: season the file was exported for; the loader accepts any four digits there.
MONEY_COLUMNS = (
    ("install price", "install_fee"),
    ("takedown price", "takedown_fee"),
    ("storage price", "storage_fee"),
    ("TOTAL invoice", "total"),
)
NAME_HEADER = "Bill-to name/company"
BASIS_HEADER = "Pricing basis"
FOOTER_PREFIX = "TOTAL"


def _norm_header(h: Any) -> str:
    return " ".join(str(h or "").split()).lower()


def find_columns(header_row) -> dict:
    """{detail key: column index} from the export's header row, or raise."""
    cols = {}
    normed = [_norm_header(h) for h in header_row]
    for i, h in enumerate(normed):
        if h == NAME_HEADER.lower():
            cols["name"] = i
        elif h == BASIS_HEADER.lower():
            cols["price_basis"] = i
        else:
            for tail, key in MONEY_COLUMNS:
                # "2026 install price" -> any four-digit season + the tail
                if h.endswith(tail.lower()) and h[:4].isdigit() and h[4:5] == " ":
                    cols[key] = i
    missing = [k for k in ("name", "price_basis", *[k for _, k in MONEY_COLUMNS]) if k not in cols]
    if missing:
        raise SystemExit(f"export is missing column(s): {', '.join(missing)}; "
                         f"headers seen: {[str(h) for h in header_row if h]}")
    return cols


def parse_export(rows) -> list[dict]:
    """[{name, fields: {install_fee, takedown_fee, storage_fee, total, price_basis}}]
    from the export's rows (header first). Nulls stay null: a row the exporter
    left unpriced is loaded as unpriced with its basis text, not as $0."""
    rows = list(rows)
    if not rows:
        raise SystemExit("export is empty")
    cols = find_columns(rows[0])
    out = []
    for r in rows[1:]:
        name = str(r[cols["name"]] or "").strip() if cols["name"] < len(r) else ""
        if not name or name.startswith(FOOTER_PREFIX):
            continue
        fields: dict = {}
        for _, key in MONEY_COLUMNS:
            v = r[cols[key]] if cols[key] < len(r) else None
            fields[key] = money(v)
        basis = r[cols["price_basis"]] if cols["price_basis"] < len(r) else None
        basis = " ".join(str(basis).split()) if basis not in (None, "") else None
        fields["price_basis"] = basis
        out.append({"name": name, "fields": fields})
    return out


def is_priced(fields: dict) -> bool:
    """Did the exporter put ANY money on this row? A storage-only row is
    still a number the client may have seen, so it counts."""
    return any(fields.get(k) is not None for _, k in MONEY_COLUMNS)


def summarize_parsed(recs: list[dict]) -> dict:
    priced = [r for r in recs if r["fields"].get("total") is not None]
    return {
        "rows": len(recs),
        "priced": len(priced),
        "install": round(sum(r["fields"].get("install_fee") or 0 for r in recs), 2),
        "takedown": round(sum(r["fields"].get("takedown_fee") or 0 for r in recs), 2),
        "storage": round(sum(r["fields"].get("storage_fee") or 0 for r in recs), 2),
        "total": round(sum(r["fields"].get("total") or 0 for r in priced), 2),
    }


async def load_season_row(conn, client_id: int, season: str) -> Optional[dict]:
    row = await conn.fetchrow(
        "SELECT detail FROM client_activity "
        " WHERE client_id = $1 AND kind = 'christmas_install' AND season = $2 FOR UPDATE",
        client_id, season,
    )
    if row is None:
        return None
    d = row["detail"]
    return json.loads(d) if isinstance(d, str) else (d or {})


async def write_prices(conn, client_id: int, season: str, fields: dict) -> bool:
    """Stamp the export's values onto the season row. Returns True if the
    row changed. A None value is sent as a clear, so a re-run with a
    corrected file can un-price a client too."""
    async with conn.transaction():
        prior = await load_season_row(conn, client_id, season) or {}
        detail = client_season.apply_edits(prior, fields)
        if detail == prior:
            return False
        await conn.execute(
            "INSERT INTO client_activity (client_id, kind, season, summary, detail, occurred_at) "
            "VALUES ($1, 'christmas_install', $2, $3, $4::jsonb, $5::date) "
            "ON CONFLICT (client_id, kind, season) WHERE kind <> 'comment' DO UPDATE SET "
            "summary=EXCLUDED.summary, detail=EXCLUDED.detail, occurred_at=EXCLUDED.occurred_at, "
            "updated_at=now()",
            client_id, season, client_season.summarize(detail), json.dumps(detail, default=str),
            to_date(detail.get("install_date")),
        )
    return True


async def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", required=True, help="The billing export xlsx that went to clients")
    ap.add_argument("--season", default=None, help="Four-digit season (default: the current one)")
    ap.add_argument("--dry-run", action="store_true", help="Match and report, write nothing")
    args = ap.parse_args()

    season = args.season or current_season()
    if len(season) != 4 or not season.isdigit():
        raise SystemExit(f"bad season {season!r}")

    wb = openpyxl.load_workbook(args.file, data_only=True)
    ws = wb[wb.sheetnames[0]]
    recs = parse_export(ws.iter_rows(values_only=True))
    s = summarize_parsed(recs)
    print(f"{args.file}: {s['rows']} clients, {s['priced']} priced; "
          f"install {s['install']:,.2f} + takedown {s['takedown']:,.2f} + storage {s['storage']:,.2f} "
          f"= total {s['total']:,.2f}")

    load_env(ENV_FILE)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit(f"DATABASE_URL not set (checked env and {ENV_FILE})")
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        matched, unmatched = [], []
        for rec in recs:
            row = await find_client_by_name(conn, rec["name"])
            if row is None:
                unmatched.append(rec)
            else:
                matched.append((row["id"], row["name"], rec))
        # A client added inside the scheduler (a teardown-only event, a
        # one-off) has no Clients-tab row and was never priced by the
        # exporter either: nothing to load, so say so and carry on. A name
        # that matches nothing but DID carry a price is a real gap -- a
        # priced job would silently go unrecorded -- so that aborts.
        skipped = [r for r in unmatched if not is_priced(r["fields"])]
        blocking = [r for r in unmatched if is_priced(r["fields"])]
        for r in skipped:
            print(f"  skip (unpriced, no client row): {r['name']!r}")
        if blocking:
            print(f"\n{len(blocking)} PRICED name(s) match no client -- nothing written:")
            for r in blocking:
                print(f"  - {r['name']!r}  total={r['fields'].get('total')!r}")
            raise SystemExit(2)
        print(f"{len(matched)} names matched a client, {len(skipped)} unpriced rows skipped")
        if args.dry_run:
            for cid, cname, rec in matched:
                f = rec["fields"]
                print(f"  {cname!r:50} total={f.get('total')!r:10} basis={f.get('price_basis')!r}")
            print("dry run: nothing written")
            return
        changed = 0
        for cid, cname, rec in matched:
            if await write_prices(conn, cid, season, rec["fields"]):
                changed += 1
        print(f"{season}: {changed} season row(s) updated, {len(matched) - changed} already matched")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
