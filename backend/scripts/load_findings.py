#!/usr/bin/env python3
"""Load a standardized supplier catalog export ("THE FINDINGS") into the
Leaf & Ledger products table.

Dry-run by default (no writes). Pass --commit to upsert.

    python scripts/load_findings.py --supplier Vickerman \
        --file "/path/THE FINDINGS/Vickerman_Catalog_2026.xlsx" [--commit] [--limit N]

Non-destructive: upserts on (supplier_id, supplier_sku), keeping existing
product IDs (so project/favorite references stay intact). raw_data is replaced
per row with the fresh full detail; image_urls updated when present.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import dotenv

dotenv.load_dotenv(BACKEND / ".env")
dotenv.load_dotenv(BACKEND / ".env.dev", override=True)

import asyncpg  # noqa: E402

from app.libs.findings_intake import parse_findings_xlsx  # noqa: E402

# Dual-price columns (list_price/margin/tiers) are OPTIONAL: they're written as
# first-class columns when they exist in the DB, otherwise skipped. Either way
# they're always preserved inside raw_data, so the data is never lost — this just
# controls whether they're promoted to their own sortable columns. (They require
# an owner-only ALTER TABLE — see migrations/002_dual_pricing.sql.)
_EXTRA_COLS = "list_price, list_price_label, margin_pct_off_retail, price_tiers,\n   "
_EXTRA_VALS = "$29::numeric,$30,$31::numeric,$32,\n   "
_EXTRA_UPD = ("list_price=EXCLUDED.list_price, list_price_label=EXCLUDED.list_price_label,\n"
              "   margin_pct_off_retail=EXCLUDED.margin_pct_off_retail, price_tiers=EXCLUDED.price_tiers,\n   ")


def build_upsert(ext: bool) -> str:
    cols, vals, upd = (_EXTRA_COLS, _EXTRA_VALS, _EXTRA_UPD) if ext else ("", "", "")
    return f"""
INSERT INTO products
  (supplier_id, supplier_sku, name, description, category, unit, current_price, price_updated_at,
   subcategory, uom, moq, case_qty, availability, availability_note,
   height_in, width_in, length_in, diameter_in, weight_lb, material, color, finish, style,
   country_of_origin, supplier_product_id, currency, photo_url, image_urls, raw_data,
   {cols}is_active, last_scraped_at, created_at, updated_at)
VALUES
  ($1,$2,$3,$4,$5,$6,$7::numeric,
   CASE WHEN $7::numeric IS NOT NULL THEN NOW() ELSE NULL END,
   $8,$9,$10::int,$11::int,$12,$13,
   $14::numeric,$15::numeric,$16::numeric,$17::numeric,$18::numeric,$19,$20,$21,$22,
   $23,$24,$25,$26,$27::text[],$28::jsonb,
   {vals}TRUE, NOW(), NOW(), NOW())
ON CONFLICT (supplier_id, supplier_sku) DO UPDATE SET
   name=EXCLUDED.name, description=EXCLUDED.description, category=EXCLUDED.category, unit=EXCLUDED.unit,
   current_price=EXCLUDED.current_price,
   price_updated_at=CASE
        WHEN EXCLUDED.current_price IS NOT NULL AND EXCLUDED.current_price IS DISTINCT FROM products.current_price
        THEN NOW() ELSE products.price_updated_at END,
   subcategory=EXCLUDED.subcategory, uom=EXCLUDED.uom, moq=EXCLUDED.moq, case_qty=EXCLUDED.case_qty,
   availability=EXCLUDED.availability, availability_note=EXCLUDED.availability_note,
   height_in=EXCLUDED.height_in, width_in=EXCLUDED.width_in, length_in=EXCLUDED.length_in,
   diameter_in=EXCLUDED.diameter_in, weight_lb=EXCLUDED.weight_lb, material=EXCLUDED.material,
   color=EXCLUDED.color, finish=EXCLUDED.finish, style=EXCLUDED.style,
   country_of_origin=EXCLUDED.country_of_origin, supplier_product_id=EXCLUDED.supplier_product_id,
   currency=EXCLUDED.currency, photo_url=EXCLUDED.photo_url,
   image_urls=CASE WHEN array_length(EXCLUDED.image_urls,1) > 0 THEN EXCLUDED.image_urls ELSE products.image_urls END,
   raw_data=EXCLUDED.raw_data,
   {upd}is_active=TRUE, last_scraped_at=NOW(), updated_at=NOW()
"""


# Default (extended) — used directly where the columns are known to exist.
UPSERT_SQL = build_upsert(True)


async def dual_price_columns_exist(conn) -> bool:
    n = await conn.fetchval(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='products' "
        "AND column_name IN ('list_price','list_price_label','margin_pct_off_retail','price_tiers')")
    return n == 4


def _values(sid, p, ext: bool = True):
    base = (
        sid, p.supplier_sku, p.name, p.description, p.category, p.unit, p.current_price,
        p.subcategory, p.uom, p.moq, p.case_qty, p.availability, p.availability_note,
        p.height_in, p.width_in, p.length_in, p.diameter_in, p.weight_lb, p.material, p.color,
        p.finish, p.style, p.country_of_origin, p.supplier_product_id, p.currency,
        p.photo_url, p.image_urls, json.dumps(p.raw_data),
    )
    return base + (p.list_price, p.list_price_label, p.margin_pct_off_retail, p.price_tiers) if ext else base


async def run(supplier: str, path: str, commit: bool, limit: int | None) -> int:
    rows, rep = parse_findings_xlsx(path)
    if limit:
        rows = rows[:limit]
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        sup = await conn.fetchrow(
            "SELECT id, name FROM suppliers WHERE name ILIKE $1 ORDER BY id LIMIT 1", supplier
        )
        if not sup:
            print(f"ERROR: no supplier matching {supplier!r}")
            return 2
        sid = sup["id"]
        before = await conn.fetchval("SELECT COUNT(*) FROM products WHERE supplier_id=$1", sid)
        existing = {
            r["supplier_sku"]
            for r in await conn.fetch(
                "SELECT supplier_sku FROM products WHERE supplier_id=$1 AND supplier_sku IS NOT NULL", sid
            )
        }
        will_insert = sum(1 for p in rows if p.supplier_sku not in existing)
        will_update = len(rows) - will_insert
        flagged = sum(1 for p in rows if p.needs_review)
        print(f"supplier={sup['name']} (id={sid})  existing_products={before}")
        print(f"file rows_ok={rep['rows_ok']} dropped={rep['dropped_missing_sku_or_name']}  "
              f"loading={len(rows)}  -> insert={will_insert} update={will_update}  needs_review={flagged}")
        if not commit:
            print("\nDRY RUN — no writes. Re-run with --commit to apply.")
            return 0
        ext = await dual_price_columns_exist(conn)
        print(f"dual-price columns present: {ext} (list_price/margin stored "
              f"{'as columns' if ext else 'in raw_data only'})")
        sql = build_upsert(ext)
        values = [_values(sid, p, ext) for p in rows]
        CHUNK = 1000
        async with conn.transaction():
            for i in range(0, len(values), CHUNK):
                await conn.executemany(sql, values[i:i + CHUNK])
        after = await conn.fetchval("SELECT COUNT(*) FROM products WHERE supplier_id=$1", sid)
        print(f"\nCOMMITTED. products for supplier {sid}: {before} -> {after} (+{after - before})")
        return 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--supplier", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    return asyncio.run(run(a.supplier, a.file, a.commit, a.limit))


if __name__ == "__main__":
    raise SystemExit(main())
