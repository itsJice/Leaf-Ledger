#!/usr/bin/env python3
"""Backfill product_facets.ident_norm (migrations/011).

Batched deliberately: one UPDATE across 166k rows holds a single transaction
open long enough to bloat the table and its indexes. Re-runnable — it only
touches rows whose stored value differs from what the function now produces,
so a second run is a no-op and a partial run resumes cleanly.

    python scripts/backfill_ident_norm.py            # dry run, reports the gap
    python scripts/backfill_ident_norm.py --commit
"""
import asyncio
import os
import sys
import time

BATCH = 5000


async def main() -> None:
    import asyncpg

    commit = "--commit" in sys.argv
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set (source backend/.env.supabase)")

    conn = await asyncpg.connect(url, statement_cache_size=0, timeout=300)
    try:
        todo = await conn.fetchval("""
            SELECT count(*) FROM product_facets pf JOIN products p ON p.id = pf.product_id
            WHERE pf.ident_norm IS DISTINCT FROM public.product_facets_ident(p)
        """)
        total = await conn.fetchval("SELECT count(*) FROM product_facets")
        print(f"{todo:,} of {total:,} rows need ident_norm")
        if not commit:
            print("dry run — pass --commit to write")
            return
        if not todo:
            print("nothing to do")
            return

        # Walk the primary key in ranges rather than repeatedly asking "which
        # rows still differ?". That predicate has to compute the function over
        # products.raw_data to answer, so every batch re-scanned the rows the
        # previous ones had already filled — fine at the start, quadratic by the
        # end. A cursor over product_id touches each row exactly once and makes
        # the run resumable: re-running starts from the lowest id still unset.
        lo = await conn.fetchval("SELECT min(product_id) FROM product_facets") or 0
        hi = await conn.fetchval("SELECT max(product_id) FROM product_facets") or 0
        done, t0 = 0, time.time()
        while lo <= hi:
            top = lo + BATCH
            status = await conn.execute(
                """
                UPDATE product_facets f
                   SET ident_norm = public.product_facets_ident(p)
                  FROM products p
                 WHERE p.id = f.product_id
                   AND f.product_id >= $1 AND f.product_id < $2
                   AND f.ident_norm IS DISTINCT FROM public.product_facets_ident(p)
                """,
                lo, top,
            )
            done += int(status.split()[-1]) if status else 0
            lo = top
            pct = 100 * min(done, todo) / max(todo, 1)
            print(f"  {done:,}/{todo:,}  ({pct:.0f}%, {time.time()-t0:.0f}s)", flush=True)

        left = await conn.fetchval("""
            SELECT count(*) FROM product_facets pf JOIN products p ON p.id = pf.product_id
            WHERE pf.ident_norm IS DISTINCT FROM public.product_facets_ident(p)
        """)
        print(f"\ndone: {done:,} rows in {time.time()-t0:.0f}s, {left:,} remaining")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
