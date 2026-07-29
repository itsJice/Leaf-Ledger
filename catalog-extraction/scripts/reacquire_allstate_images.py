#!/usr/bin/env python3
"""Re-acquire Allstate (supplier_id=1) product images.

Allstate exposes ONLY ephemeral ColdFusion `/CFFileServlet/_cf_image/_cfimg-<rand>.jpg`
URLs — they 200 while fresh (public, no cookie) but expire, which is why the
originally-scraped URLs now 404. Fix: re-scrape the CURRENT fresh URLs so the app's
image-caching layer can download the bytes before they expire.

Two stages (different venvs):
  --stage scrape : SeleniumBase browser (catalog-extraction venv) -> writes
                   outputs/allstate-full/reacquired_images.json  {item: [urls]}
  --stage load   : asyncpg (backend venv) -> UPDATE products image_urls/photo_url

    .venv/bin/python scripts/reacquire_allstate_images.py --stage scrape
    ../backend/.venv/bin/python scripts/reacquire_allstate_images.py --stage load [--commit]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / "backend"
BASE = "https://www.allstatefloral.com"
OUT = ROOT / "outputs" / "allstate-full"
IMGMAP = OUT / "reacquired_images.json"
CKPT = OUT / "reacquired_progress.ndjson"   # per-DDCODE checkpoint
SUPPLIER_ID = 1


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def stage_scrape():
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_allstate_full import login, scrape_ddcode, DD_PATH  # reuse proven flow
    from seleniumbase import SB

    dd = json.loads(DD_PATH.read_text()) if DD_PATH.exists() else []
    done = {}
    if CKPT.exists():
        for line in CKPT.open(encoding="utf-8"):
            try:
                r = json.loads(line); done[r["ddcode"]] = r["items"]
            except (json.JSONDecodeError, KeyError):
                pass
    pending = [d for d in dd if d not in done]
    log(f"DDCODEs: {len(dd)} total, {len(done)} done, {len(pending)} to scrape")
    with SB(headless=True, browser="chrome") as sb:
        if not login(sb):
            raise RuntimeError("Allstate login failed")
        log("login OK")
        with CKPT.open("a", encoding="utf-8") as ck:
            for i, code in enumerate(pending, 1):
                try:
                    prods = scrape_ddcode(sb, code)
                except Exception as exc:  # noqa: BLE001
                    prods = []; log(f"  {code} error: {exc!r}")
                items = {}
                for p in prods:
                    item = (p.get("item") or "").strip()
                    img = p.get("img") or ""
                    if item and "_cf_image" in img:
                        items.setdefault(item, [])
                        if img not in items[item]:
                            items[item].append(img)
                ck.write(json.dumps({"ddcode": code, "items": items}) + "\n"); ck.flush()
                log(f"  [{i}/{len(pending)}] {code}: {len(items)} items with images")
    # collapse checkpoint -> {item: [urls]}
    merged = {}
    for line in CKPT.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        for item, urls in r.get("items", {}).items():
            merged.setdefault(item, [])
            for u in urls:
                if u not in merged[item]:
                    merged[item].append(u)
    IMGMAP.write_text(json.dumps(merged), encoding="utf-8")
    log(f"scrape: {len(merged)} items with fresh image URLs -> {IMGMAP}")


def stage_load(commit: bool):
    import asyncio, os
    import dotenv
    dotenv.load_dotenv(BACKEND / ".env"); dotenv.load_dotenv(BACKEND / ".env.dev", override=True)
    import asyncpg

    m = json.loads(IMGMAP.read_text(encoding="utf-8"))
    UPDATE = """
    UPDATE products
       SET image_urls = $1::text[], photo_url = $2,
           raw_data = jsonb_set(
               jsonb_set(coalesce(raw_data,'{}'::jsonb), '{image_reacquired_at}', to_jsonb($3::text), true),
               '{image_source}', to_jsonb('allstate_cffileservlet_fresh'::text), true),
           updated_at = NOW()
     WHERE supplier_id = $4 AND supplier_sku = $5
    """

    async def run():
        c = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            db = {r["supplier_sku"] for r in await c.fetch(
                "SELECT supplier_sku FROM products WHERE supplier_id=$1 AND supplier_sku IS NOT NULL", SUPPLIER_ID)}
            matched = {k: v for k, v in m.items() if k in db and v}
            log(f"scraped items: {len(m)} | DB Allstate SKUs: {len(db)} | will update: {len(matched)}")
            if not commit:
                log("DRY RUN — re-run with --commit to write."); return
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            rows = [(urls, urls[0], now, SUPPLIER_ID, sku) for sku, urls in matched.items()]
            async with c.transaction():
                for i in range(0, len(rows), 1000):
                    await c.executemany(UPDATE, rows[i:i + 1000])
            n = await c.fetchval(
                "SELECT COUNT(*) FROM products WHERE supplier_id=$1 AND photo_url ILIKE '%_cf_image%'", SUPPLIER_ID)
            log(f"COMMITTED. Allstate products now with a fresh image URL: {n}")
        finally:
            await c.close()
    asyncio.run(run())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["scrape", "load"], required=True)
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.stage == "scrape":
        stage_scrape()
    else:
        stage_load(a.commit)


if __name__ == "__main__":
    raise SystemExit(main())
