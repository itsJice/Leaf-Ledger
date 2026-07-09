#!/usr/bin/env python3
"""Jay Scotts — full catalog over the WooCommerce Store API.

Commercial fiberglass planters (~68 products, mostly variable → several hundred
SKUs). The Store API is enabled and returns real prices anonymously, BUT the
listing endpoint is crippled (catalog_visibility=hidden → X-WP-Total:1), so we
enumerate product slugs from product-sitemap.xml and fetch each individually.

Prices come back in MINOR units (currency_minor_unit=2 → divide by 100), USD.
Variable products expose only a price RANGE on the parent; real per-SKU prices
require a per-parent variation call. Anonymous prices are retail/MSRP; the
wholesale dashboard likely lowers them (flagged, not captured here).

Cloudflare fronts the site, so API calls go through curl (browser UA).
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

BASE = "https://jayscotts.com"
API = f"{BASE}/wp-json/wc/store/v1"
SUPPLIER = "Jay Scotts"
SEASON = "2026"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT_DIR = ROOT / "outputs" / "jayscotts-full"
RAW_PATH = OUT_DIR / "products_raw.json"
_TAG_RE = re.compile(r"<[^>]+>")
_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _curl(url: str):
    for attempt in range(5):
        proc = subprocess.run(["curl", "-s", "--compressed", "-A", UA, url],
                              capture_output=True, text=True, timeout=90)
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"could not fetch {url}")


def _strip(t: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", t or ""))).strip()


def discover_slugs() -> list[str]:
    proc = subprocess.run(["curl", "-s", "--compressed", "-A", UA, f"{BASE}/product-sitemap.xml"],
                          capture_output=True, text=True, timeout=60)
    slugs = []
    for loc in _LOC_RE.findall(proc.stdout):
        m = re.search(r"/product/([^/]+)/?$", loc)
        if m:
            slugs.append(m.group(1))
    return list(dict.fromkeys(slugs))


def fetch_catalog() -> list[dict]:
    slugs = discover_slugs()
    log(f"discover: {len(slugs)} product slugs")
    out = []
    for i, slug in enumerate(slugs, 1):
        data = _curl(f"{API}/products?slug={slug}")
        if not isinstance(data, list) or not data:
            log(f"  no record for slug {slug}")
            continue
        parent = data[0]
        record = {"slug": slug, "parent": parent, "variations": []}
        if parent.get("type") == "variable" or parent.get("has_options"):
            pid = parent.get("id")
            variations = _curl(f"{API}/products?type=variation&parent={pid}&per_page=100")
            if isinstance(variations, list):
                record["variations"] = variations
        out.append(record)
        if i % 10 == 0:
            log(f"  {i}/{len(slugs)} products")
        time.sleep(0.5)
    return out


def _price(minor, minor_unit=2):
    try:
        return round(int(minor) / (10 ** int(minor_unit)), 2)
    except (TypeError, ValueError):
        return ""


def _images(p: dict) -> list[str]:
    return [img.get("src") for img in p.get("images", []) if img.get("src")]


def _categories(p: dict) -> str:
    return "; ".join(_strip(c.get("name")) for c in p.get("categories", []) if c.get("name"))


def record_to_rows(rec: dict, run_id: str, now: str) -> list[dict]:
    p = rec["parent"]
    prices = p.get("prices") or {}
    minor_unit = prices.get("currency_minor_unit", 2)
    images = _images(p)
    primary = images[0] if images else ""
    extras = images[1:10]
    description = _strip(p.get("description"))
    short_desc = _strip(p.get("short_description"))
    category = _categories(p)
    base = {
        "supplier": SUPPLIER, "season": SEASON,
        "product_name": _strip(p.get("name")),
        "category": category,
        "description": description or short_desc,
        "currency": prices.get("currency_code") or "USD",
        "vendor": SUPPLIER,
        "image_url": primary,
        **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 11)},
        "image_count": len(images),
        "product_url": p.get("permalink") or f"{BASE}/product/{rec['slug']}/",
        "source_url": f"{API}/products?slug={rec['slug']}",
        "extracted_at": now, "run_id": run_id,
        "product_id": str(p.get("id") or ""),
    }
    rows = []
    variations = rec.get("variations") or []
    if variations:
        for v in variations:
            vp = v.get("prices") or {}
            vprice = _price(vp.get("price"), vp.get("currency_minor_unit", minor_unit))
            attrs = "; ".join(f'{a.get("name")}: {a.get("value")}' for a in v.get("attributes", []))
            sku = (v.get("sku") or "").strip()
            missing = []
            if vprice == "":
                missing.append("price")
            if not sku:
                missing.append("sku")
            if not primary:
                missing.append("image")
            rows.append({
                **base,
                "sku": sku or f'{base["product_id"]}.{v.get("id")}',
                "variant": attrs,
                "price": vprice,
                "source_price_label": "public_retail_price" if vprice != "" else "",
                "availability": "in_stock" if v.get("is_in_stock", True) else "unavailable",
                "variation_id": str(v.get("id") or ""),
                "needs_review": "; ".join(missing),
            })
    else:
        price = _price(prices.get("price"), minor_unit)
        sku = (p.get("sku") or "").strip()
        missing = []
        if price == "":
            missing.append("price")
        if not sku:
            missing.append("sku")
        if not primary:
            missing.append("image")
        rows.append({
            **base,
            "sku": sku or base["product_id"],
            "variant": "",
            "price": price,
            "source_price_label": "public_retail_price" if price != "" else "",
            "availability": "in_stock" if p.get("is_in_stock", True) else "unavailable",
            "variation_id": "",
            "needs_review": "; ".join(missing),
        })
    return rows


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name", "variant", "category",
    "description", "price", "currency", "source_price_label", "availability",
    "vendor", "image_url", "image_url_2", "image_url_3", "image_url_4",
    "image_url_5", "image_url_6", "image_url_7", "image_url_8", "image_url_9",
    "image_url_10", "image_count", "product_url", "source_url", "needs_review",
    "extracted_at", "run_id", "product_id", "variation_id",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["fetch", "export", "all"], default="all")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.stage in ("fetch", "all") and (args.stage == "fetch" or not RAW_PATH.exists()):
        catalog = fetch_catalog()
        RAW_PATH.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        log(f"fetch: {len(catalog)} products -> {RAW_PATH}")

    if args.stage in ("export", "all"):
        catalog = json.loads(RAW_PATH.read_text(encoding="utf-8"))
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rows: dict[str, dict] = {}
        for rec in catalog:
            for row in record_to_rows(rec, run_id, now):
                key = f'{row["sku"]}|{row["variant"]}'
                rows[key] = row
        ordered = sorted(rows.values(), key=lambda r: (r["category"], r["product_name"], r["variant"]))
        frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
        for col in ("sku", "product_id", "variation_id"):
            frame[col] = frame[col].fillna("").astype(str)

        import shutil, tempfile
        tmp = Path(tempfile.mkdtemp(prefix="js-export-"))
        frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
        frame.to_csv(tmp / "products.csv", index=False)
        (tmp / "products.json").write_text(json.dumps(ordered, indent=1, ensure_ascii=False), encoding="utf-8")
        for n in ("products.xlsx", "products.csv", "products.json"):
            shutil.move(str(tmp / n), str(OUT_DIR / n))
        shutil.rmtree(tmp, ignore_errors=True)

        priced = int((frame["price"].astype(str).str.strip() != "").sum())
        imaged = int((frame["image_url"].astype(str).str.strip() != "").sum())
        report = {
            "supplier": SUPPLIER, "season": SEASON, "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "products": len(catalog), "rows_exported": len(frame),
            "with_price": priced, "with_image": imaged,
            "needs_review_count": int((frame["needs_review"] != "").sum()),
            "pricing_note": "Public WooCommerce Store API price (retail/MSRP, minor units /100). "
                            "Wholesale-dashboard login likely lowers prices — enrichment TBD.",
        }
        (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        log(f"export: {len(frame)} rows ({len(catalog)} products) -> {OUT_DIR/'products.xlsx'} "
            f"(priced={priced}, imaged={imaged})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
