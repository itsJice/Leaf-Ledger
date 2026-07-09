#!/usr/bin/env python3
"""Full Vickerman catalog pull in bounded, resumable stages.

Usage:
    python scripts/run_vickerman_full.py                # all stages
    python scripts/run_vickerman_full.py --stage details
    python scripts/run_vickerman_full.py --limit 25     # smoke run

Interrupt at any time; re-running resumes from the details checkpoint.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import pandas as pd

from catalog_extraction.vickerman_http import (
    EXPORT_COLUMNS,
    fetch_product_urls,
    login,
    make_session,
    model_to_row,
    run_details_stage,
)

SUPPLIER = "Vickerman"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "vickerman-full"
ITEMS_PATH = OUT_DIR / "items.json"
DETAILS_PATH = OUT_DIR / "details.ndjson"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def stage_discover() -> list[str]:
    session = make_session()
    urls = fetch_product_urls(session)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ITEMS_PATH.write_text(json.dumps(urls, indent=0), encoding="utf-8")
    log(f"discover: {len(urls)} unique product URLs -> {ITEMS_PATH}")
    return urls


def stage_details(limit: int | None) -> None:
    if not ITEMS_PATH.exists():
        stage_discover()
    urls = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    # include anything seen in header listings that the sitemap missed
    sku_headers, _ = load_listings()
    known = {u.rsplit("item=", 1)[-1] for u in urls}
    extra = [f"https://www.vickerman.com/products/details?item={sku}"
             for sku in sku_headers if sku not in known]
    if extra:
        log(f"details: adding {len(extra)} SKUs found in listings but not in sitemap")
        urls = urls + extra
    counts = run_details_stage(urls, DETAILS_PATH, limit=limit, log=log)
    log(f"details: done (ok={counts['ok']} err={counts['error']})")


LISTINGS_PATH = OUT_DIR / "listings.json"


def load_listings() -> tuple[dict[str, list[str]], list[dict]]:
    """Returns (sku -> [headers it appears under], per-header summary)."""
    if not LISTINGS_PATH.exists():
        return {}, []
    data = json.loads(LISTINGS_PATH.read_text(encoding="utf-8"))
    sku_headers: dict[str, list[str]] = {}
    summary: list[dict] = []
    for header in data.get("headers", []):
        name = header["header"]
        header_skus: set[str] = set()
        rows_available = rows_all = 0
        for sub in header.get("subcategories", []):
            rows_available += sub.get("total_available", 0) or 0
            rows_all += sub.get("total_all", 0) or 0
            for sku in sub.get("skus", []):
                header_skus.add(sku)
                headers_for_sku = sku_headers.setdefault(sku, [])
                if name not in headers_for_sku:
                    headers_for_sku.append(name)
        summary.append(
            {
                "header": name,
                "listing_rows_available_filter": rows_available,
                "listing_rows_all_filter": rows_all,
                "unique_skus": len(header_skus),
            }
        )
    return sku_headers, summary


def stage_export(run_id: str) -> None:
    sku_headers, header_summary = load_listings()
    rows: dict[str, dict] = {}
    errors: list[dict] = []
    total_lines = 0
    with DETAILS_PATH.open(encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            total_lines += 1
            if not record.get("ok"):
                errors.append({"sku": record.get("sku"), "error": record.get("error")})
                continue
            row = model_to_row(record, supplier=SUPPLIER, season=SEASON, run_id=run_id)
            row["listed_under"] = "; ".join(sku_headers.get(row["sku"], []))
            # dedupe on supplier+sku: last fetch wins (records are append-ordered)
            rows[row["sku"]] = {**row, "_raw": record["model"]}

    # errors only count if the SKU never succeeded on a later (resumed) attempt
    errors = [e for e in errors if e["sku"] not in rows]

    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["subcategory"], r["sku"]))
    raw_by_sku = {r["sku"]: r.pop("_raw") for r in ordered}

    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    xlsx_path = OUT_DIR / "products.xlsx"
    csv_path = OUT_DIR / "products.csv"
    json_path = OUT_DIR / "products.json"
    report_path = OUT_DIR / "run_report.json"

    # Write to a local temp dir first, then move into place — the output dir
    # may be under iCloud sync, which can time out large in-place writes.
    import shutil
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix="vickerman-export-"))
    frame.to_excel(tmp_dir / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp_dir / "products.csv", index=False)
    (tmp_dir / "products.json").write_text(
        json.dumps(
            [{**row, "raw_data": raw_by_sku[row["sku"]]} for row in ordered],
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for name, target in (("products.xlsx", xlsx_path), ("products.csv", csv_path), ("products.json", json_path)):
        shutil.move(str(tmp_dir / name), str(target))
    shutil.rmtree(tmp_dir, ignore_errors=True)

    listed_skus = set(sku_headers)
    exported_skus = set(rows)
    listed_missing = sorted(listed_skus - exported_skus)

    needs_review = frame[frame["needs_review"] != ""]
    report = {
        "supplier": SUPPLIER,
        "season": SEASON,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sitemap_urls": total_lines,
        "products_exported": len(frame),
        "fetch_errors": len(errors),
        "needs_review_count": int(len(needs_review)),
        "needs_review_breakdown": {
            flag: int(frame["needs_review"].str.contains(flag).sum())
            for flag in ("price", "image", "upc", "dimensions", "description")
        },
        "header_coverage": header_summary,
        "listed_skus_total": len(listed_skus),
        "listed_skus_missing_from_export": len(listed_missing),
        "listed_missing_sample": listed_missing[:50],
        "errors_sample": errors[:50],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    log(f"export: {len(frame)} products -> {xlsx_path}")
    log(f"export: needs_review={len(needs_review)}, fetch_errors={len(errors)}")
    log(f"export: report -> {report_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Full Vickerman catalog extraction.")
    parser.add_argument("--stage", choices=["discover", "details", "export", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None, help="Max products (smoke runs).")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.stage in ("discover", "all") and (args.stage == "discover" or not ITEMS_PATH.exists()):
        stage_discover()
    if args.stage in ("details", "all"):
        stage_details(args.limit)
    if args.stage in ("export", "all"):
        stage_export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
