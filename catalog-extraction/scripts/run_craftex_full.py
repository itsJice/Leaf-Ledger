#!/usr/bin/env python3
"""Full Craftex catalog pull in bounded, resumable stages.

Usage:
    python scripts/run_craftex_full.py                 # all stages
    python scripts/run_craftex_full.py --stage details
    python scripts/run_craftex_full.py --limit 25      # smoke run
"""
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

from catalog_extraction.craftex_http import (
    EXPORT_COLUMNS,
    crawl_all_categories,
    fetch_product_urls,
    make_session,
    product_to_rows,
    run_details_stage,
)

SUPPLIER = "Craftex"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "craftex-full"
ITEMS_PATH = OUT_DIR / "items.json"
DETAILS_PATH = OUT_DIR / "details.ndjson"
CATEGORIES_PATH = OUT_DIR / "categories.json"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def stage_discover() -> list[str]:
    urls = fetch_product_urls(make_session())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ITEMS_PATH.write_text(json.dumps(urls, indent=0), encoding="utf-8")
    log(f"discover: {len(urls)} product URLs -> {ITEMS_PATH}")
    return urls


def stage_details(limit: int | None) -> None:
    if not ITEMS_PATH.exists():
        stage_discover()
    urls = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    if CATEGORIES_PATH.exists():
        known = {u.rstrip("/").rsplit("/", 1)[-1] for u in urls}
        extra = []
        for cat in json.loads(CATEGORIES_PATH.read_text(encoding="utf-8")):
            for product in cat.get("products", []):
                slug = product.get("urlPart") or ""
                if slug and slug not in known:
                    known.add(slug)
                    extra.append(f"https://www.craftex.com/product-page/{slug}")
        if extra:
            log(f"details: adding {len(extra)} products from category listings not in sitemap")
            urls = urls + extra
    counts = run_details_stage(urls, DETAILS_PATH, limit=limit, log=log)
    log(f"details: done (ok={counts['ok']} err={counts['error']})")


def stage_categories() -> None:
    results = crawl_all_categories(log=log)
    CATEGORIES_PATH.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    log(f"categories: {len(results)} sections -> {CATEGORIES_PATH}")


# Top-nav store sections (site header order). Collection names are matched
# after normalization because "Décor" appears with inconsistent encodings.
SECTIONS = [
    ("ribbon", "All Ribbons"),
    ("christmas store", "Christmas Store"),
    ("seasons and decor", "Seasons and Decor"),
    ("floral store", "Floral Store"),
]


def _norm(name: str) -> str:
    return (name.lower().replace("é", "e").replace("�", "e").strip())


def _section_for(collection_name: str) -> str | None:
    normalized = _norm(collection_name)
    for key, section in SECTIONS:
        if normalized == key:
            return section
    return None


def stage_export(run_id: str) -> None:
    category_products: dict[str, list[str]] = {}
    category_summary: list[dict] = []
    if CATEGORIES_PATH.exists():
        for cat in json.loads(CATEGORIES_PATH.read_text(encoding="utf-8")):
            slugs = {p["urlPart"] for p in cat.get("products", []) if p.get("urlPart")}
            for slug in slugs:
                category_products.setdefault(slug, []).append(cat["name"])
            category_summary.append({
                "section": cat.get("name"),
                "path": cat.get("path"),
                "site_total": cat.get("total_count"),
                "collected": cat.get("collected"),
            })

    rows: dict[str, dict] = {}
    raw_by_product: dict[str, dict] = {}
    errors: list[dict] = []
    fetched_slugs: set[str] = set()
    with DETAILS_PATH.open(encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not record.get("ok"):
                errors.append({"slug": record.get("slug"), "error": record.get("error")})
                continue
            fetched_slugs.add(record["slug"])
            for row in product_to_rows(record, supplier=SUPPLIER, season=SEASON, run_id=run_id):
                collections = [c for c in category_products.get(record["slug"], []) if c and c != "All Products"]
                main_sections = list(dict.fromkeys(
                    s for s in (_section_for(c) for c in collections) if s
                ))
                sub_collections = [c for c in collections if not _section_for(c)]
                if not row["category"]:
                    row["category"] = main_sections[0] if main_sections else (sub_collections[0] if sub_collections else "")
                if not row["subcategory"] and sub_collections:
                    row["subcategory"] = sub_collections[0]
                merged = main_sections + sub_collections
                if merged:
                    row["listed_under"] = "; ".join(
                        dict.fromkeys((row["listed_under"].split("; ") if row["listed_under"] else []) + merged)
                    ).strip("; ")
                rows[row["sku"] if row["variant"] == "" else f'{row["sku"]}|{row["variant"]}'] = row
            raw_by_product[record["slug"]] = record["product"]

    errors = [e for e in errors if e["slug"] not in fetched_slugs]
    listed_missing = sorted(s for s in category_products if s not in fetched_slugs)

    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["subcategory"], r["product_name"], r["variant"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    for col in ("sku", "upc"):
        frame[col] = frame[col].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)

    import shutil
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix="craftex-export-"))
    frame.to_excel(tmp_dir / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp_dir / "products.csv", index=False)
    (tmp_dir / "products.json").write_text(
        json.dumps(
            [{**row, "raw_data": raw_by_product.get(row["product_url"].rsplit("/", 1)[-1], {})}
             for row in ordered],
            indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    for name in ("products.xlsx", "products.csv", "products.json"):
        shutil.move(str(tmp_dir / name), str(OUT_DIR / name))
    shutil.rmtree(tmp_dir, ignore_errors=True)

    needs_review = frame[frame["needs_review"] != ""]
    report = {
        "supplier": SUPPLIER,
        "season": SEASON,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "products_fetched": len(fetched_slugs),
        "rows_exported": len(frame),
        "fetch_errors": len(errors),
        "needs_review_count": int(len(needs_review)),
        "needs_review_breakdown": {
            flag: int(frame["needs_review"].str.contains(flag).sum())
            for flag in ("price", "image", "sku", "description")
        },
        "category_coverage": category_summary,
        "listed_products_missing_from_export": len(listed_missing),
        "listed_missing_sample": listed_missing[:50],
        "errors_sample": errors[:50],
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    log(f"export: {len(frame)} rows ({len(fetched_slugs)} products) -> {OUT_DIR / 'products.xlsx'}")
    log(f"export: needs_review={len(needs_review)}, fetch_errors={len(errors)}, "
        f"listed_missing={len(listed_missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Full Craftex catalog extraction.")
    parser.add_argument("--stage", choices=["discover", "categories", "details", "export", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.stage in ("discover", "all") and (args.stage == "discover" or not ITEMS_PATH.exists()):
        stage_discover()
    if args.stage in ("categories", "all") and (args.stage == "categories" or not CATEGORIES_PATH.exists()):
        stage_categories()
    if args.stage in ("details", "all"):
        stage_details(args.limit)
    if args.stage in ("export", "all"):
        stage_export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
