#!/usr/bin/env python3
"""Promote dual-pricing values from raw_data into their real columns.

Context: migration 002 (list_price / list_price_label / margin_pct_off_retail /
price_tiers) could not be applied while the app role was DML-only on Neon, so
every importer preserved these values inside raw_data instead — losslessly, but
not sortable/filterable. Now that the DB is Supabase-owned, 002 is applied and
this promotes the already-captured values into the columns.

Reads ONLY from raw_data (no re-import), so it cannot disturb photo_url,
image_urls, or any re-acquired supplier images.

Source keys, in priority order:
  list_price            <- 'list_price', 'retail price'
  list_price_label      <- 'list_price_label', 'list price label'
  margin_pct_off_retail <- 'margin_pct_off_retail', else computed from
                           (list_price - current_price) / list_price * 100
  price_tiers           <- 'price_tiers'

    set -a && . ./.env.supabase && set +a
    .venv/bin/python scripts/backfill_dual_pricing.py [--commit]
"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg

# Strip currency symbols/commas, then accept only a clean number.
_NUM = r"""
NULLIF(regexp_replace(COALESCE({expr}, ''), '[^0-9.\-]', '', 'g'), '')
"""


def _num(expr: str) -> str:
    """SQL: text -> numeric, or NULL when it isn't a plain number."""
    cleaned = _NUM.format(expr=expr).strip()
    return (f"CASE WHEN ({cleaned}) ~ '^-?[0-9]+(\\.[0-9]+)?$' "
            f"THEN ({cleaned})::numeric ELSE NULL END")


LIST_PRICE = _num("COALESCE(raw_data->>'list_price', raw_data->>'retail price')")
TIERS = "NULLIF(raw_data->>'price_tiers', '')"
LABEL = ("NULLIF(COALESCE(raw_data->>'list_price_label', "
         "raw_data->>'list price label'), '')")
MARGIN_RAW = _num("raw_data->>'margin_pct_off_retail'")

UPDATE = f"""
UPDATE products SET
  list_price = COALESCE({LIST_PRICE}, list_price),
  list_price_label = COALESCE({LABEL}, list_price_label),
  price_tiers = COALESCE({TIERS}, price_tiers),
  margin_pct_off_retail = COALESCE(
      {MARGIN_RAW},
      CASE WHEN {LIST_PRICE} > 0 AND current_price IS NOT NULL
                AND {LIST_PRICE} >= current_price
           THEN round((({LIST_PRICE} - current_price) / {LIST_PRICE} * 100)::numeric, 1)
      END,
      margin_pct_off_retail),
  updated_at = NOW()
WHERE raw_data ?| ARRAY['list_price','retail price','list_price_label',
                        'list price label','margin_pct_off_retail','price_tiers']
"""


async def main() -> int:
    commit = "--commit" in sys.argv
    c = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    try:
        eligible = await c.fetchval(
            "SELECT COUNT(*) FROM products WHERE raw_data ?| ARRAY['list_price',"
            "'retail price','list_price_label','list price label',"
            "'margin_pct_off_retail','price_tiers']")
        print(f"rows carrying dual-price data in raw_data: {eligible:,}")
        before = await c.fetchrow(
            "SELECT COUNT(list_price) lp, COUNT(margin_pct_off_retail) mg, "
            "COUNT(price_tiers) pt FROM products")
        print(f"before -> list_price={before['lp']:,} margin={before['mg']:,} tiers={before['pt']:,}")
        if not commit:
            print("\nDRY RUN — re-run with --commit to write.")
            return 0
        async with c.transaction():
            await c.execute(UPDATE)
        after = await c.fetchrow(
            "SELECT COUNT(list_price) lp, COUNT(margin_pct_off_retail) mg, "
            "COUNT(price_tiers) pt FROM products")
        print(f"after  -> list_price={after['lp']:,} margin={after['mg']:,} tiers={after['pt']:,}")
        print("\nper-supplier dual pricing now visible:")
        for r in await c.fetch("""
                SELECT s.name, COUNT(p.list_price) lp,
                       round(avg(p.margin_pct_off_retail), 1) avg_margin,
                       COUNT(p.price_tiers) pt
                  FROM products p JOIN suppliers s ON s.id = p.supplier_id
                 GROUP BY s.name HAVING COUNT(p.list_price) > 0 OR COUNT(p.price_tiers) > 0
                 ORDER BY COUNT(p.list_price) DESC"""):
            print(f"   {r['name'][:26]:28s} list_price={r['lp']:>7,}  "
                  f"avg_margin={str(r['avg_margin'] or '—'):>6}%  tiers={r['pt']:>7,}")
        # sanity: no row should claim a margin without a list price
        bad = await c.fetchval("SELECT COUNT(*) FROM products WHERE margin_pct_off_retail "
                               "IS NOT NULL AND list_price IS NULL")
        print(f"\nsanity — margin without list_price: {bad:,}")
        return 0
    finally:
        await c.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
