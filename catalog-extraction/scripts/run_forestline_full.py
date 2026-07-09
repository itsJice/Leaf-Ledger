#!/usr/bin/env python3
"""Forest Line Products — full catalog via the mysimplestore JSON API.

The site is a GoDaddy front over a SimpleStore (mysimplestore.com) storefront.
Product pages are a client-rendered SPA (no data in the HTML), but the store's
public API returns the whole catalog in one call:
  https://<storeUUID>.mysimplestore.com/api/v3/products?per_page=100
Prices are PUBLIC. ~77 products (live-edge/epoxy furniture, cutting boards, etc.).
"""
from __future__ import annotations

import argparse
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

STORE = "https://7c01b86f-b4a7-47dc-bd3d-0040f50ab98d.mysimplestore.com"
SITE = "https://forestlineproducts.com"
SUPPLIER = "Forest Line Products"
SEASON = "2026"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT_DIR = ROOT / "outputs" / "forestline-full"
RAW_PATH = OUT_DIR / "products_raw.json"


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def fetch_all() -> list[dict]:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    products, page = [], 1
    while True:
        r = s.get(f"{STORE}/api/v3/products", params={"per_page": 100, "page": page}, timeout=45)
        r.raise_for_status()
        data = r.json()
        batch = data.get("products", [])
        products.extend(batch)
        if page >= data.get("pages", 1) or not batch:
            break
        page += 1
        time.sleep(0.3)
    return products


def _desc(raw: str) -> str:
    """description_raw is Draft.js JSON ({blocks:[{text:...}]}) — join the text."""
    if not raw:
        return ""
    try:
        blocks = json.loads(raw).get("blocks", [])
        return re.sub(r"\s+", " ", " ".join(b.get("text", "") for b in blocks)).strip()
    except (json.JSONDecodeError, AttributeError):
        return re.sub(r"<[^>]+>", " ", raw).strip()


def _images(p: dict) -> list[str]:
    out = []
    for a in (p.get("assets") or p.get("image_list") or []):
        url = a.get("url") if isinstance(a, dict) else a
        if url:
            out.append(url if url.startswith("http") else "https:" + url)
    return out


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name", "product_type", "description",
    "price", "sale_price", "currency", "source_price_label", "colors",
    "variant_count", "availability", "in_stock_qty", "image_url", "image_url_2",
    "image_url_3", "image_url_4", "image_url_5", "image_count", "product_url",
    "source_url", "needs_review", "extracted_at", "run_id",
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
            price = (p.get("price") or {}).get("numeric")
            sale = (p.get("sale_price") or {}).get("numeric")
            imgs = _images(p)
            colors = p.get("colors") or []
            colors = "; ".join(c.get("name", "") if isinstance(c, dict) else str(c) for c in colors) if isinstance(colors, list) else str(colors)
            url = p.get("relative_url") or f"/ols/products/{p.get('slug')}"
            missing = []
            if not price:
                missing.append("price")
            if not imgs:
                missing.append("image")
            rows.append({
                "supplier": SUPPLIER, "season": SEASON,
                "sku": p.get("sku") or str(p.get("id") or ""),
                "product_name": p.get("name") or "",
                "product_type": p.get("product_type") or "",
                "description": _desc(p.get("description_raw")),
                "price": price if price else "",
                "sale_price": sale if sale else "",
                "currency": (p.get("price") or {}).get("currency") or "USD",
                "source_price_label": "public_site_price" if price else "",
                "colors": colors,
                "variant_count": p.get("variant_count") or "",
                "availability": "in_stock" if p.get("in_stock") else "out_of_stock",
                "in_stock_qty": p.get("total_on_hand") if p.get("total_on_hand") is not None else "",
                "image_url": imgs[0] if imgs else "",
                **{f"image_url_{n}": (imgs[n - 1] if n - 1 < len(imgs) else "") for n in range(2, 6)},
                "image_count": len(imgs),
                "product_url": url if url.startswith("http") else SITE + url,
                "source_url": f"{STORE}/api/v3/products",
                "needs_review": "; ".join(missing),
                "extracted_at": now, "run_id": run_id,
            })
        rows.sort(key=lambda r: r["product_name"])
        frame = pd.DataFrame(rows, columns=EXPORT_COLUMNS)
        frame["sku"] = frame["sku"].fillna("").astype(str)

        import shutil, tempfile
        tmp = Path(tempfile.mkdtemp(prefix="fl-export-"))
        frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
        frame.to_csv(tmp / "products.csv", index=False)
        (tmp / "products.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
        for n in ("products.xlsx", "products.csv", "products.json"):
            shutil.move(str(tmp / n), str(OUT_DIR / n))
        shutil.rmtree(tmp, ignore_errors=True)

        priced = int((frame["price"].astype(str).str.strip() != "").sum())
        imaged = int((frame["image_url"].astype(str).str.strip() != "").sum())
        report = {
            "supplier": SUPPLIER, "season": SEASON, "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rows_exported": len(frame), "with_price": priced, "with_image": imaged,
            "pricing_note": "Public prices from the SimpleStore API (mysimplestore.com).",
        }
        (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        log(f"export: {len(frame)} products -> {OUT_DIR/'products.xlsx'} (priced={priced}, imaged={imaged})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
