#!/usr/bin/env python3
"""Full Winward Silks catalog pull (authenticated B2B Direct/RepZio API)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import pandas as pd

from catalog_extraction.winward_http import (
    EXPORT_COLUMNS,
    fetch_all_products,
    login,
    make_session,
    product_to_row,
)

SUPPLIER = "Winward"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "winward-full"
CHECKPOINT = OUT_DIR / "products.ndjson"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def stage_fetch(limit: int | None) -> None:
    session = make_session()
    meta = login(session)
    log(f"login OK — ShowPricing={meta.get('ShowPricing')} PriceLevel={meta.get('PriceLevel')}")
    n = fetch_all_products(session, CHECKPOINT, limit=limit, log=log)
    log(f"fetch: {n} products in checkpoint")


def stage_export(run_id: str) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows: dict[str, dict] = {}
    raw_by_sku: dict[str, dict] = {}
    with CHECKPOINT.open(encoding="utf-8") as f:
        for line in f:
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            row = product_to_row(p, supplier=SUPPLIER, season=SEASON, run_id=run_id, fetched_at=now)
            rows[row["sku"]] = row
            raw_by_sku[row["sku"]] = p

    ordered = sorted(rows.values(), key=lambda r: (r["product_name"], r["sku"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)

    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="winward-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    (tmp / "products.json").write_text(
        json.dumps([{**r, "raw_data": raw_by_sku[r["sku"]]} for r in ordered], indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    for name in ("products.xlsx", "products.csv", "products.json"):
        shutil.move(str(tmp / name), str(OUT_DIR / name))
    shutil.rmtree(tmp, ignore_errors=True)

    needs = frame[frame["needs_review"] != ""]
    priced = int((frame["price"].astype(str).str.strip() != "").sum())
    report = {
        "supplier": SUPPLIER, "season": SEASON, "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_exported": len(frame),
        "with_price": priced,
        "with_image": int((frame["image_url"].astype(str).str.strip() != "").sum()),
        "with_upc": int((frame["upc"].astype(str).str.strip() != "").sum()),
        "needs_review_count": int(len(needs)),
        "needs_review_breakdown": {
            flag: int(frame["needs_review"].str.contains(flag, regex=False).sum())
            for flag in ("price", "image", "sku", "description")
        },
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"export: {len(frame)} rows, {priced} priced -> {OUT_DIR / 'products.xlsx'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Full Winward Silks catalog extraction.")
    parser.add_argument("--stage", choices=["fetch", "export", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.stage in ("fetch", "all"):
        stage_fetch(args.limit)
    if args.stage in ("export", "all"):
        stage_export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
