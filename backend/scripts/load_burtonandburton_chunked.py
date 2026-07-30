#!/usr/bin/env python3
"""Import BurtonAndBurton_Catalog_2026.xlsx with per-chunk transactions and a
fresh connection per chunk, so a single Supabase pooler drop doesn't roll back
everything already committed. Upserts are idempotent (ON CONFLICT supplier_id,
supplier_sku) so this is safe to just re-run if it stops partway.

    set -a && . ./.env.supabase && set +a
    .venv/bin/python scripts/load_burtonandburton_chunked.py [--commit]
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import asyncpg  # noqa: E402
from app.libs.findings_intake import parse_findings_xlsx  # noqa: E402
from load_findings import build_upsert, dual_price_columns_exist, _values  # noqa: E402

FILE = ("/Users/justice/Projects/leaf-and-ledger/catalog-findings/"
        "THE FINDINGS/BurtonAndBurton_Catalog_2026.xlsx")
SUPPLIER_NAME = "Burton + Burton"
CHUNK = 250


async def main() -> int:
    commit = "--commit" in sys.argv
    rows, rep = parse_findings_xlsx(FILE)
    print(f"rows_ok={rep['rows_ok']} dropped={rep.get('dropped_missing_sku_or_name')} "
         f"total={len(rows)}")

    c = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    sid = await c.fetchval("SELECT id FROM suppliers WHERE name=$1", SUPPLIER_NAME)
    if sid is None:
        sid = await c.fetchval(
            "INSERT INTO suppliers (name, credential_status, notes) VALUES ($1,'n/a',$2) RETURNING id",
            SUPPLIER_NAME, "auto-created by load_burtonandburton_chunked")
        print(f"created supplier id={sid}")
    ext = await dual_price_columns_exist(c)
    await c.close()
    sql = build_upsert(ext)
    print(f"supplier id={sid} | dual-price columns: {ext}")

    if not commit:
        print("DRY RUN — re-run with --commit to write.")
        return 0

    values = [_values(sid, p, ext) for p in rows]
    n_chunks = (len(values) + CHUNK - 1) // CHUNK
    done = 0
    for i in range(0, len(values), CHUNK):
        chunk = values[i:i + CHUNK]
        for attempt in range(3):
            try:
                cc = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
                try:
                    async with cc.transaction():
                        await cc.executemany(sql, chunk)
                finally:
                    await cc.close()
                break
            except (asyncpg.exceptions.InterfaceError, asyncpg.exceptions.ConnectionDoesNotExistError,
                    OSError) as e:
                if attempt == 2:
                    print(f"chunk {i // CHUNK + 1}/{n_chunks} FAILED after retries: {e}")
                    raise
                time.sleep(2 * (attempt + 1))
        done += len(chunk)
        if (i // CHUNK + 1) % 10 == 0 or i + CHUNK >= len(values):
            print(f"  {done}/{len(values)} committed ({i // CHUNK + 1}/{n_chunks} chunks)")

    cc = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    total = await cc.fetchval("SELECT COUNT(*) FROM products WHERE supplier_id=$1", sid)
    await cc.close()
    print(f"\nCOMMITTED. products for supplier {sid}: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
