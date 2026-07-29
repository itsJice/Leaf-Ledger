#!/usr/bin/env python3
"""Re-acquire Melrose (supplier_id=29) product images.

The original scrape built the wrong image path (/images/product/<name> -> 404).
The real SoloVue images are PUBLIC (no login) at:
    https://melrose.solovue.com/images/products/detail/desktop/<ImageName>   (high-res)
    https://melrose.solovue.com/images/products/list/desktop/<ImageName>     (thumb)
Image filenames come from the raw scrape (Images[].ImageName / MainImageName),
keyed by Pnumber (= products.supplier_sku). Writes image_urls + photo_url only,
additively stamps raw_data.image_reacquired_at, and changes nothing else.

    python reacquire_melrose_images.py [--commit]
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
NDJSON = ROOT / "outputs" / "melrose-full" / "products.ndjson"
IMG = "https://melrose.solovue.com/images/products"
SUPPLIER_ID = 29

import dotenv
dotenv.load_dotenv(BACKEND / ".env")
dotenv.load_dotenv(BACKEND / ".env.dev", override=True)
import asyncpg


def build_map() -> dict[str, list[str]]:
    """Pnumber -> [detail URLs...] + a list-thumb fallback."""
    out: dict[str, list[str]] = {}
    for line in NDJSON.open(encoding="utf-8"):
        for p in json.loads(line).get("products", []):
            sku = str(p.get("Pnumber") or "").strip()
            if not sku:
                continue
            names = [im.get("ImageName") for im in (p.get("Images") or []) if im.get("ImageName")]
            if not names and p.get("MainImageName"):
                names = [p["MainImageName"]]
            names = list(dict.fromkeys(names))
            if not names:
                continue
            urls = [f"{IMG}/detail/desktop/{n}" for n in names]
            urls.append(f"{IMG}/list/desktop/{names[0]}")  # lightweight fallback
            out[sku] = list(dict.fromkeys(urls))
    return out


UPDATE = """
UPDATE products
   SET image_urls = $1::text[], photo_url = $2,
       raw_data = jsonb_set(
           jsonb_set(coalesce(raw_data,'{}'::jsonb), '{image_reacquired_at}', to_jsonb($3::text), true),
           '{image_source}', to_jsonb('melrose_solovue'::text), true),
       updated_at = NOW()
 WHERE supplier_id = $4 AND supplier_sku = $5
"""


async def main() -> int:
    commit = "--commit" in sys.argv
    m = build_map()
    print(f"built image URLs for {len(m)} Melrose SKUs")
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        db_skus = {r["supplier_sku"] for r in await c.fetch(
            "SELECT supplier_sku FROM products WHERE supplier_id=$1 AND supplier_sku IS NOT NULL", SUPPLIER_ID)}
        matched = {sku: urls for sku, urls in m.items() if sku in db_skus}
        print(f"DB Melrose SKUs: {len(db_skus)} | will update: {len(matched)} | "
              f"in-file-not-in-db: {len(m) - len(matched)}")
        if not commit:
            print("\nDRY RUN — re-run with --commit to write.")
            return 0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = [(urls, urls[0], now, SUPPLIER_ID, sku) for sku, urls in matched.items()]
        async with c.transaction():
            for i in range(0, len(rows), 1000):
                await c.executemany(UPDATE, rows[i:i + 1000])
        imaged = await c.fetchval(
            "SELECT COUNT(*) FROM products WHERE supplier_id=$1 AND photo_url ILIKE '%products/detail%'", SUPPLIER_ID)
        print(f"\nCOMMITTED. Melrose products now with a re-acquired image: {imaged}")
        return 0
    finally:
        await c.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
