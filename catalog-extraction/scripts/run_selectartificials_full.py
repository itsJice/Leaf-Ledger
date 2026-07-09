#!/usr/bin/env python3
"""Full Select Artificials catalog pull (open Emun JSON API)."""
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

from catalog_extraction.selectartificials_http import (
    EXPORT_COLUMNS,
    fetch_all_products,
    login,
    make_session,
    product_to_row,
)

SUPPLIER = "Select Artificials"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "selectartificials-full"
RAW_PATH = OUT_DIR / "products_raw.json"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Full Select Artificials catalog extraction.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    session = make_session()
    if login(session):
        log("login: retailer session active (base prices unlocked)")
    else:
        log("login: none — capturing public tier prices only")

    products = fetch_all_products(session, limit=args.limit, log=log)
    RAW_PATH.write_text(json.dumps(products, ensure_ascii=False), encoding="utf-8")
    log(f"discover: {len(products)} products -> {RAW_PATH}")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows: dict[str, dict] = {}
    raw_by_sku: dict[str, dict] = {}
    for p in products:
        row = product_to_row(p, supplier=SUPPLIER, season=SEASON, run_id=run_id, fetched_at=now)
        if row["sku"]:
            rows[row["sku"]] = row
            raw_by_sku[row["sku"]] = p

    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["subcategory"], r["sku"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    for col in ("sku", "upc"):
        frame[col] = frame[col].fillna("").astype(str)

    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="selectartificials-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    (tmp / "products.json").write_text(
        json.dumps([{**r, "raw_data": raw_by_sku[r["sku"]]} for r in ordered], indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    for name in ("products.xlsx", "products.csv", "products.json"):
        shutil.move(str(tmp / name), str(OUT_DIR / name))
    shutil.rmtree(tmp, ignore_errors=True)

    needs_review = frame[frame["needs_review"].str.replace("image (url needs auth/browser pass)", "", regex=False).str.strip("; ") != ""]
    with_tier = int(((frame["tier2_price"].astype(str) != "") | (frame["tier3_price"].astype(str) != "")).sum())
    report = {
        "supplier": SUPPLIER, "season": SEASON, "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "products": len(products), "rows_exported": len(frame),
        "with_public_tier_price": with_tier,
        "with_base_price": int((frame["price"].astype(str) != "").sum()),
        "rows_needing_review_excl_images": int(len(needs_review)),
        "pricing_note": "Volume-tier prices (tier2/tier3) are public. Base wholesale/list "
                        "price requires SELECT_ARTIFICIALS_* retailer login. Image URLs need "
                        "an authenticated/browser pass (raw productImages positions kept in raw_data).",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"export: {len(frame)} rows -> {OUT_DIR / 'products.xlsx'} (tier-priced={with_tier})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
