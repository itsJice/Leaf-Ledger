#!/usr/bin/env python3
"""HR Casabella — catalog via the WooCommerce Store API.

Wholesale stone-container supplier (~621 products). The Store API lists/paginates
publicly, but PRICES are B2B-gated (all 0 for guests; product pages show no price)
and there is no trade account. So this captures the public metadata — SKU,
category, size/dimensions, image — with price left blank and flagged
account-gated. Names are just the item numbers (the supplier's convention).
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import requests

BASE = "https://www.hrcasabella.com"
API = f"{BASE}/wp-json/wc/store/v1/products"
SUPPLIER = "HR Casabella"
SEASON = "2026"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT_DIR = ROOT / "outputs" / "hrcasabella-full"
RAW_PATH = OUT_DIR / "products_raw.json"
_TAG_RE = re.compile(r"<[^>]+>")


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def fetch_all() -> list[dict]:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "gzip, deflate"})
    out, page = [], 1
    while True:
        r = s.get(API, params={"per_page": 100, "page": page}, timeout=45)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        log(f"page {page}: +{len(batch)} (total {len(out)})")
        total_pages = int(r.headers.get("X-WP-TotalPages", 0) or 0)
        if total_pages and page >= (len(out) // 100 + (1 if len(out) % 100 else 0)) and len(batch) < 100:
            break
        if len(batch) < 100:
            break
        page += 1
        time.sleep(0.3)
    return out


def _strip(t: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", t or ""))).strip()


def _price(p: dict):
    pr = (p.get("prices") or {}).get("price")
    try:
        v = int(pr) / (10 ** int((p.get("prices") or {}).get("currency_minor_unit", 2)))
        return v if v > 0 else ""
    except (TypeError, ValueError):
        return ""


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name", "category", "dimensions",
    "description", "price", "source_price_label", "availability", "image_url",
    "image_url_2", "image_url_3", "image_count", "product_url", "source_url",
    "needs_review", "extracted_at", "run_id",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["fetch", "export", "all"], default="all")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.stage in ("fetch", "all") and (args.stage == "fetch" or not RAW_PATH.exists()):
        products = fetch_all()
        RAW_PATH.write_text(json.dumps(products, ensure_ascii=False), encoding="utf-8")
        log(f"fetch: {len(products)} products -> {RAW_PATH}")

    if args.stage in ("export", "all"):
        products = json.loads(RAW_PATH.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = []
        for p in products:
            imgs = [i.get("src") for i in p.get("images", []) if i.get("src")]
            dims = "; ".join(
                t.get("name", "") for a in p.get("attributes", [])
                if "size" in (a.get("name", "").lower()) for t in a.get("terms", []))
            cats = "; ".join(c.get("name", "") for c in p.get("categories", []))
            price = _price(p)
            missing = ["price (account-gated)"] if price == "" else []
            if not imgs:
                missing.append("image")
            rows.append({
                "supplier": SUPPLIER, "season": SEASON,
                "sku": p.get("sku") or str(p.get("id") or ""),
                "product_name": _strip(p.get("name")),
                "category": cats,
                "dimensions": dims,
                "description": _strip(p.get("description")),
                "price": price,
                "source_price_label": "public_site_price" if price != "" else "",
                "availability": "in_stock" if p.get("is_in_stock") else "unavailable",
                "image_url": imgs[0] if imgs else "",
                "image_url_2": imgs[1] if len(imgs) > 1 else "",
                "image_url_3": imgs[2] if len(imgs) > 2 else "",
                "image_count": len(imgs),
                "product_url": p.get("permalink") or "",
                "source_url": API,
                "needs_review": "; ".join(missing),
                "extracted_at": now, "run_id": run_id,
            })
        rows.sort(key=lambda r: (r["category"], r["sku"]))
        frame = pd.DataFrame(rows, columns=EXPORT_COLUMNS)
        frame["sku"] = frame["sku"].fillna("").astype(str)

        import shutil, tempfile
        tmp = Path(tempfile.mkdtemp(prefix="hrc-export-"))
        frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
        frame.to_csv(tmp / "products.csv", index=False)
        for n in ("products.xlsx", "products.csv"):
            shutil.move(str(tmp / n), str(OUT_DIR / n))
        shutil.rmtree(tmp, ignore_errors=True)

        priced = int((frame["price"].astype(str).str.strip() != "").sum())
        imaged = int((frame["image_url"].astype(str).str.strip() != "").sum())
        report = {
            "supplier": SUPPLIER, "season": SEASON, "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rows_exported": len(frame), "with_price": priced, "with_image": imaged,
            "pricing_note": "Prices are B2B/wholesale-gated (0 for guests) and there is no "
                            "trade account; SKU + category + dimensions + image captured. "
                            "Add prices later via a trade login if an account is opened.",
        }
        (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        log(f"export: {len(frame)} products -> {OUT_DIR/'products.xlsx'} (priced={priced}, imaged={imaged})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
