#!/usr/bin/env python3
"""Point Allstate (supplier_id=1) product images at their permanent GitHub URLs.

The 4,668 Allstate images live in the public repo itsJice/L-Limages
(pushed from outputs/allstate-full/images/, verified serving image/jpeg).
This sets photo_url + image_urls to
    https://raw.githubusercontent.com/itsJice/L-Limages/main/allstate/<SKU>.jpg
matching on supplier_sku, additively stamping raw_data. Touches nothing else.

    ../backend/.venv/bin/python scripts/point_allstate_to_github.py [--commit]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / "backend"
MANIFEST = ROOT / "outputs" / "allstate-full" / "images_manifest.json"
RAW = "https://raw.githubusercontent.com/itsJice/L-Limages/main/allstate"
SUPPLIER_ID = 1

import dotenv
dotenv.load_dotenv(BACKEND / ".env")
dotenv.load_dotenv(BACKEND / ".env.dev", override=True)
import asyncpg

SQL = """
UPDATE products SET photo_url=$1, image_urls=$2::text[],
  raw_data = jsonb_set(jsonb_set(coalesce(raw_data,'{}'::jsonb),
      '{image_reacquired_at}', to_jsonb($3::text), true),
      '{image_source}', to_jsonb('github_llimages'::text), true),
  updated_at=NOW()
WHERE supplier_id=$4 AND supplier_sku=$5
"""


async def main() -> int:
    commit = "--commit" in sys.argv
    m = json.loads(MANIFEST.read_text())
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        db = {r["supplier_sku"] for r in await c.fetch(
            "SELECT supplier_sku FROM products WHERE supplier_id=$1 AND supplier_sku IS NOT NULL",
            SUPPLIER_ID)}
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = [(f"{RAW}/{sku}.jpg", [f"{RAW}/{sku}.jpg"], now, SUPPLIER_ID, sku)
                for sku in m if sku in db]
        print(f"images in repo: {len(m):,} | DB Allstate SKUs: {len(db):,} | will update: {len(rows):,}")
        if not commit:
            print("DRY RUN — re-run with --commit to write.")
            return 0
        async with c.transaction():
            for i in range(0, len(rows), 1000):
                await c.executemany(SQL, rows[i:i + 1000])
        n = await c.fetchval(
            "SELECT COUNT(*) FROM products WHERE supplier_id=$1 "
            "AND photo_url LIKE 'https://raw.githubusercontent.com/%'", SUPPLIER_ID)
        chk = await c.fetchrow(
            "SELECT COUNT(*) t, COUNT(current_price) p, COUNT(name) nm "
            "FROM products WHERE supplier_id=$1", SUPPLIER_ID)
        print(f"COMMITTED. repointed: {n:,}")
        print(f"integrity: products={chk['t']:,} priced={chk['p']:,} named={chk['nm']:,}")
        return 0
    finally:
        await c.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
