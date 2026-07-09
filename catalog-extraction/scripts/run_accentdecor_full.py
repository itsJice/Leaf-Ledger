#!/usr/bin/env python3
"""Full Accent Decor catalog pull (Klevu search API)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass

import pandas as pd

from catalog_extraction.accentdecor_http import (
    EXPORT_COLUMNS,
    fetch_all,
    fetch_detail,
    login_web,
    make_session,
    make_web_session,
    record_to_row,
)

SUPPLIER = "Accent Decor"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "accentdecor-full"
CHECKPOINT = OUT_DIR / "records.ndjson"
DETAILS = OUT_DIR / "details.ndjson"
DETAIL_WORKERS = 6


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def stage_fetch(limit):
    n = fetch_all(make_session(), CHECKPOINT, limit=limit, log=log)
    log(f"fetch: {n} records in checkpoint")


def stage_details(limit):
    """Enrich each product from its logged-in page: real price, images, description."""
    urls = []
    with CHECKPOINT.open(encoding="utf-8") as f:
        for line in f:
            try:
                u = json.loads(line).get("url")
            except json.JSONDecodeError:
                continue
            if u:
                urls.append(u)
    if limit:
        urls = urls[:limit]

    done = set()
    if DETAILS.exists():
        with DETAILS.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if row.get("ok"):
                        done.add(row["url"])
                except json.JSONDecodeError:
                    continue
    pending = [u for u in urls if u not in done]

    web = make_web_session()
    login_web(web)  # assert dealer session so pages show real prices
    log(f"details: login OK; {len(done)} enriched, {len(pending)} to fetch")

    lock = threading.Lock()
    counts = {"ok": 0, "err": 0}
    with DETAILS.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
            futs = {pool.submit(fetch_detail, web, u): u for u in pending}
            for i, fut in enumerate(as_completed(futs), 1):
                d = fut.result()
                counts["ok" if d.get("ok") else "err"] += 1
                with lock:
                    out.write(json.dumps(d, ensure_ascii=False) + "\n"); out.flush()
                if i % 250 == 0:
                    log(f"details: {i}/{len(pending)} (ok={counts['ok']} err={counts['err']})")
    log(f"details: done (ok={counts['ok']} err={counts['err']})")


def _load_details():
    by_url = {}
    if DETAILS.exists():
        with DETAILS.open(encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("ok"):
                    by_url[d["url"]] = d
    return by_url


def stage_export(run_id):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    details = _load_details()
    rows, raw = {}, {}
    with CHECKPOINT.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            row = record_to_row(rec, details.get(rec.get("url")),
                                supplier=SUPPLIER, season=SEASON, run_id=run_id, fetched_at=now)
            rows[row["sku"]] = row
            raw[row["sku"]] = rec
    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["product_name"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="accentdecor-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    (tmp / "products.json").write_text(
        json.dumps([{**r, "raw_data": raw[r["sku"]]} for r in ordered], indent=1, ensure_ascii=False), encoding="utf-8")
    for name in ("products.xlsx", "products.csv", "products.json"):
        shutil.move(str(tmp / name), str(OUT_DIR / name))
    shutil.rmtree(tmp, ignore_errors=True)

    needs = frame[frame["needs_review"] != ""]
    price_diff = frame[(frame["price"].astype(str).str.strip() != "") & (frame["klevu_price"].astype(str).str.strip() != "")]
    report = {
        "supplier": SUPPLIER, "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_exported": len(frame),
        "with_dealer_price": int((frame["price"].astype(str).str.strip() != "").sum()),
        "with_image": int((frame["image_url"].astype(str).str.strip() != "").sum()),
        "avg_images_per_product": round(float(frame["image_count"].mean()), 2),
        "needs_review_count": int(len(needs)),
        "note": "price = authoritative logged-in Magento DEALER price (min variant); "
                "klevu_price = Klevu index price (differs — do NOT treat as dealer cost). "
                "magento_price_min/max span variant prices. Images + full description from "
                "the logged-in product page.",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"export: {len(frame)} rows, {report['with_dealer_price']} dealer-priced, avg {report['avg_images_per_product']} imgs -> {OUT_DIR / 'products.xlsx'}")


def main():
    p = argparse.ArgumentParser(description="Full Accent Decor catalog extraction.")
    p.add_argument("--stage", choices=["fetch", "details", "export", "all"], default="all")
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if a.stage in ("fetch", "all"):
        stage_fetch(a.limit)
    if a.stage in ("details", "all"):
        stage_details(a.limit)
    if a.stage in ("export", "all"):
        stage_export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
