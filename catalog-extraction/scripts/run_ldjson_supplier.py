#!/usr/bin/env python3
"""Run a sitemap + ld+json supplier extraction (Autograph Foliages, American Best, ...).

Usage:
    python scripts/run_ldjson_supplier.py autograph [--limit N] [--stage discover|details|export|all]
    python scripts/run_ldjson_supplier.py american_best [--limit N]
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

from catalog_extraction.ldjson_http import (
    EXPORT_COLUMNS,
    SupplierConfig,
    fetch_sitemap_urls,
    ldjson_to_row,
    make_session,
    run_details_stage,
)

CONFIGS = {
    "autograph": SupplierConfig(
        supplier="Autograph Foliages",
        season="2026",
        base_url="https://autographfoliages.com",
        sitemap_url="https://autographfoliages.com/xmlsitemap.php?type=products&page=1",
        workers=4,
        delay=0.3,
        description_urldecode=True,
        price_gated_note="price (login-gated: 'Call for pricing')",
    ),
    "american_best": SupplierConfig(
        supplier="American Best",
        season="2026",
        base_url="https://www.americanbest.com",
        sitemap_url="https://www.americanbest.com/sitemap.xml",
        workers=4,
        delay=0.3,
        title_must_contain="American Best",  # skip the stale misrouted BigCommerce slug
        price_gated_note="price (login-gated)",
    ),
    # WGV International — BigCommerce, ~1.1k products, PUBLIC ld+json prices.
    # Store hash s-vfwvf156mw. Descriptions are URL-encoded (BigCommerce).
    "wgv": SupplierConfig(
        supplier="WGV International",
        season="2026",
        base_url="https://wholesaleglassvasesint.com",
        sitemap_url="https://wholesaleglassvasesint.com/xmlsitemap.php?type=products&page=1",
        workers=3,          # robots Crawl-delay: 10 — be gentle
        delay=0.6,
        description_urldecode=True,
    ),
    # Second Flor — PrestaShop, ~294 products, PUBLIC ld+json prices (USD).
    # Sitemap is a flat urlset mixing category + product (.html) URLs; non-product
    # pages are skipped as NO_PRODUCT. Compression header (make_session) avoids the
    # truncated-body -> wrong-ld+json trap.
    "second_flor": SupplierConfig(
        supplier="Second Flor",
        season="2026",
        base_url="https://www.secondflor.us",
        sitemap_url="https://www.secondflor.us/1_en_0_sitemap.xml",
        workers=4,
        delay=0.3,
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("supplier", choices=list(CONFIGS))
    parser.add_argument("--stage", choices=["discover", "details", "export", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    cfg = CONFIGS[args.supplier]
    out_dir = ROOT / "outputs" / f"{args.supplier}-full"
    out_dir.mkdir(parents=True, exist_ok=True)
    items_path = out_dir / "items.json"
    details_path = out_dir / "details.ndjson"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def log(msg: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    if args.stage in ("discover", "all") and (args.stage == "discover" or not items_path.exists()):
        urls = fetch_sitemap_urls(make_session(), cfg.sitemap_url, log=log)
        items_path.write_text(json.dumps(urls, indent=0), encoding="utf-8")
        log(f"discover: {len(urls)} URLs -> {items_path}")

    if args.stage in ("details", "all"):
        urls = json.loads(items_path.read_text(encoding="utf-8"))
        counts = run_details_stage(urls, details_path, cfg, limit=args.limit, log=log)
        log(f"details: done (ok={counts['ok']} skip={counts['skip']} err={counts['error']})")

    if args.stage in ("export", "all"):
        rows: dict[str, dict] = {}
        raw_by_sku: dict[str, dict] = {}
        errors = 0
        with details_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not rec.get("ok"):
                    if rec.get("error") not in ("NO_PRODUCT", "TITLE_MISMATCH"):
                        errors += 1
                    continue
                row = ldjson_to_row(rec, cfg, run_id=run_id)
                if row["sku"]:
                    rows[row["sku"]] = row
                    raw_by_sku[row["sku"]] = rec["product"]

        ordered = sorted(rows.values(), key=lambda r: (r["category"], r["subcategory"], r["product_name"]))
        frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
        for col in ("sku", "upc"):
            frame[col] = frame[col].fillna("").astype(str)

        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix=f"{args.supplier}-export-"))
        frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
        frame.to_csv(tmp / "products.csv", index=False)
        (tmp / "products.json").write_text(
            json.dumps([{**r, "raw_data": raw_by_sku[r["sku"]]} for r in ordered], indent=1, ensure_ascii=False),
            encoding="utf-8",
        )
        for name in ("products.xlsx", "products.csv", "products.json"):
            shutil.move(str(tmp / name), str(out_dir / name))
        shutil.rmtree(tmp, ignore_errors=True)

        priced = int((frame["price"].astype(str) != "").sum())
        with_img = int((frame["image_url"].astype(str) != "").sum())
        report = {
            "supplier": cfg.supplier, "season": cfg.season, "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rows_exported": len(frame), "with_price": priced, "with_image": with_img,
            "fetch_errors": errors,
            "needs_review_count": int((frame["needs_review"] != "").sum()),
            "pricing_note": "Prices are login-gated; metadata + images captured anonymously.",
        }
        (out_dir / "run_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"export: {len(frame)} rows -> {out_dir / 'products.xlsx'} (priced={priced}, images={with_img}, errors={errors})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
