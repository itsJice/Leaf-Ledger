#!/usr/bin/env python3
"""Full Amazing Green catalog pull in bounded, resumable stages."""
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

from catalog_extraction.amazinggreen_http import (
    EXPORT_COLUMNS,
    fetch_all_products,
    fetch_collections,
    make_session,
    product_to_rows,
    run_details_stage,
)

SUPPLIER = "Amazing Green"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "amazinggreen-full"
BULK_PATH = OUT_DIR / "products_bulk.json"
DETAILS_PATH = OUT_DIR / "details.ndjson"
COLLECTIONS_PATH = OUT_DIR / "collections.json"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def stage_discover() -> list[dict]:
    products = fetch_all_products(make_session(), log=log)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BULK_PATH.write_text(json.dumps(products, ensure_ascii=False), encoding="utf-8")
    log(f"discover: {len(products)} products -> {BULK_PATH}")
    return products


def stage_collections() -> None:
    results = fetch_collections(make_session(), log=log)
    COLLECTIONS_PATH.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    log(f"collections: {len(results)} -> {COLLECTIONS_PATH}")


def stage_details(limit: int | None) -> None:
    if not BULK_PATH.exists():
        stage_discover()
    products = json.loads(BULK_PATH.read_text(encoding="utf-8"))
    handles = [p["handle"] for p in products if p.get("handle")]
    counts = run_details_stage(handles, DETAILS_PATH, limit=limit, log=log)
    log(f"details: done (ok={counts['ok']} err={counts['error']})")


def stage_export(run_id: str) -> None:
    products = json.loads(BULK_PATH.read_text(encoding="utf-8"))

    js_by_handle: dict[str, dict] = {}
    fetched_at_by_handle: dict[str, str] = {}
    if DETAILS_PATH.exists():
        with DETAILS_PATH.open(encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("ok"):
                    js_by_handle[record["handle"]] = record["product"]
                    fetched_at_by_handle[record["handle"]] = record.get("fetched_at", "")

    collections_by_handle: dict[str, list[str]] = {}
    coverage = []
    all_listed: set[str] = set()
    if COLLECTIONS_PATH.exists():
        for col in json.loads(COLLECTIONS_PATH.read_text(encoding="utf-8")):
            if col["handle"] in ("all", "frontpage"):
                continue
            for handle in col.get("product_handles", []):
                collections_by_handle.setdefault(handle, []).append(col["title"])
                all_listed.add(handle)
            coverage.append({"collection": col["title"], "site_count": col.get("products_count"),
                             "collected": len(col.get("product_handles", []))})

    rows: dict[str, dict] = {}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for bulk in products:
        handle = bulk.get("handle", "")
        for row in product_to_rows(
            bulk, js_by_handle.get(handle), collections_by_handle.get(handle, []),
            supplier=SUPPLIER, season=SEASON, run_id=run_id,
            fetched_at=fetched_at_by_handle.get(handle, now),
        ):
            key = row["sku"] if not row["variant"] else f'{row["sku"]}|{row["variant"]}'
            rows[key] = row

    bulk_handles = {p.get("handle") for p in products}
    listed_missing = sorted(all_listed - bulk_handles)

    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["product_name"], r["variant"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    for col in ("sku", "upc", "product_id"):
        frame[col] = frame[col].fillna("").astype(str)

    import shutil
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix="amazinggreen-export-"))
    frame.to_excel(tmp_dir / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp_dir / "products.csv", index=False)
    (tmp_dir / "products.json").write_text(
        json.dumps(ordered, indent=1, ensure_ascii=False), encoding="utf-8")
    for name in ("products.xlsx", "products.csv", "products.json"):
        shutil.move(str(tmp_dir / name), str(OUT_DIR / name))
    shutil.rmtree(tmp_dir, ignore_errors=True)

    needs_review = frame[frame["needs_review"] != ""]
    report = {
        "supplier": SUPPLIER,
        "season": SEASON,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "products": len(products),
        "rows_exported": len(frame),
        "needs_review_count": int(len(needs_review)),
        "needs_review_breakdown": {
            flag: int(frame["needs_review"].str.contains(flag, regex=False).sum())
            for flag in ("price (login-gated)", "sku", "image", "description")
        },
        "pricing_note": "Wholesale prices are not published online (B2B lock app; "
                        "confirmed via logged-in session 2026-07-04). Merge rep price "
                        "list by SKU when received.",
        "collection_coverage": coverage,
        "listed_products_missing_from_export": len(listed_missing),
        "listed_missing_sample": listed_missing[:50],
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    log(f"export: {len(frame)} rows ({len(products)} products) -> {OUT_DIR / 'products.xlsx'}")
    log(f"export: needs_review={len(needs_review)}, listed_missing={len(listed_missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Full Amazing Green catalog extraction.")
    parser.add_argument("--stage", choices=["discover", "collections", "details", "export", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.stage in ("discover", "all") and (args.stage == "discover" or not BULK_PATH.exists()):
        stage_discover()
    if args.stage in ("collections", "all") and (args.stage == "collections" or not COLLECTIONS_PATH.exists()):
        stage_collections()
    if args.stage in ("details", "all"):
        stage_details(args.limit)
    if args.stage in ("export", "all"):
        stage_export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
