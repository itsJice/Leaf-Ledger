#!/usr/bin/env python3
"""Full SuperMoss catalog pull (WooCommerce Store API)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from catalog_extraction.supermoss_http import (
    EXPORT_COLUMNS,
    fetch_all,
    make_session,
    record_to_row,
)

SUPPLIER = "SuperMoss"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "supermoss-full"
CHECKPOINT = OUT_DIR / "records.ndjson"


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def stage_fetch(limit):
    n = fetch_all(make_session(), CHECKPOINT, limit=limit, log=log)
    log(f"fetch: {n} rows in checkpoint")


def stage_export(run_id):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows, raw = {}, {}
    with CHECKPOINT.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            row = record_to_row(rec, supplier=SUPPLIER, season=SEASON, run_id=run_id, fetched_at=now)
            key = row["sku"] if not row["variant"] else f'{row["sku"]}|{row["variant"]}'
            rows[key] = row
            raw[key] = rec
    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["product_name"], r["variant"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="supermoss-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    (tmp / "products.json").write_text(json.dumps(ordered, indent=1, ensure_ascii=False), encoding="utf-8")
    for name in ("products.xlsx", "products.csv", "products.json"):
        shutil.move(str(tmp / name), str(OUT_DIR / name))
    shutil.rmtree(tmp, ignore_errors=True)

    needs = frame[frame["needs_review"] != ""]
    report = {
        "supplier": SUPPLIER, "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_exported": len(frame),
        "variant_rows": int((frame["variant"].astype(str) != "").sum()),
        "with_price": int((frame["price"].astype(str).str.strip() != "").sum()),
        "with_image": int((frame["image_url"].astype(str).str.strip() != "").sum()),
        "needs_review_count": int(len(needs)),
        "needs_review_breakdown": {
            flag: int(frame["needs_review"].str.contains(flag, regex=False).sum())
            for flag in ("price", "image", "sku", "description")
        },
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"export: {len(frame)} rows ({report['variant_rows']} variants), {report['with_price']} priced -> {OUT_DIR / 'products.xlsx'}")


def main():
    p = argparse.ArgumentParser(description="Full SuperMoss catalog extraction.")
    p.add_argument("--stage", choices=["fetch", "export", "all"], default="all")
    p.add_argument("--limit", type=int, default=None, help="Max BASE products (smoke runs).")
    a = p.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if a.stage in ("fetch", "all"):
        stage_fetch(a.limit)
    if a.stage in ("export", "all"):
        stage_export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
