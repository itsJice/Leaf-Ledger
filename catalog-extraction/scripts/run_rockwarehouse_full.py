#!/usr/bin/env python3
"""The Rock Warehouse — full catalog from the static per-category Source.html files.

Custom Dreamweaver static site. The sitemap lists 31 `/{Category}/General.html`
shells that client-side-include `/{Category}/Source.html` — the real payload:
`div.tb_layer3` blocks laid out as [image] [name + SKU] [retail price] [volume
tiers] per product. RETAIL prices are PUBLIC (with quantity breaks); the wholesale
tier is login-gated (not captured — no account). ~700-1000 products across 31
categories. Products aren't individually addressable; SKU is the id.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://therockwarehouse.com"
SUPPLIER = "The Rock Warehouse"
SEASON = "2026"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT_DIR = ROOT / "outputs" / "rockwarehouse-full"
_SKU_RE = re.compile(r"\b([A-Z]{2,3})\s?(\d{3,4})\b")
_PRICE_RE = re.compile(r"\$\s?([\d,]+\.\d{2})")


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    return s


def categories(s: requests.Session) -> list[tuple[str, str]]:
    r = s.get(f"{BASE}/sitemap.xml", timeout=45)
    cats = []
    for loc in re.findall(r"<loc>([^<]+/General\.html)</loc>", r.text):
        cat = loc.replace("https://therockwarehouse.com/", "").split("/")[0]
        src = loc.replace("General.html", "Source.html")
        cats.append((cat.replace("_", " "), src))
    return cats


def parse_source(cat: str, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    blocks = soup.select("div.tb_layer3")
    products, cur = [], None
    for b in blocks:
        a_img = b.find("img")
        link = b.find("a", href=re.compile(r"assets/.+\.(jpg|png)", re.I))
        text = re.sub(r"\s+", " ", b.get_text(" ", strip=True))
        if a_img is not None:  # image block starts a new product
            if cur:
                products.append(cur)
            full = link.get("href") if link else (a_img.get("src") or "")
            cur = {"category": cat, "image": full, "alt": a_img.get("alt", ""),
                   "name": "", "sku": "", "price": "", "tiers": "", "stock": ""}
        elif cur is not None and text:
            sku_m = _SKU_RE.search(text)
            prices = _PRICE_RE.findall(text)
            if sku_m and not cur["sku"]:
                cur["sku"] = f"{sku_m.group(1)} {sku_m.group(2)}"
                cur["name"] = text[:sku_m.start()].strip(" ,-") or cur["alt"]
                if re.search(r"out of stock", text, re.I):
                    cur["stock"] = "Out of Stock"
            elif prices and not cur["price"]:
                cur["price"] = prices[0]
                if "out of stock" in text.lower():
                    cur["stock"] = "Out of Stock"
            elif prices and cur["price"]:
                cur["tiers"] = (cur["tiers"] + " | " + text).strip(" |")
    if cur:
        products.append(cur)
    # keep only rows that have a SKU
    return [p for p in products if p["sku"]]


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name", "category", "price", "currency",
    "price_tiers", "source_price_label", "availability", "image_url", "product_url",
    "source_url", "needs_review", "extracted_at", "run_id",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["all"], default="all")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    s = make_session()
    cats = categories(s)
    if args.limit:
        cats = cats[: args.limit]
    log(f"categories: {len(cats)}")
    rows: dict[str, dict] = {}
    for i, (cat, src) in enumerate(cats, 1):
        try:
            r = s.get(src, timeout=45)
            prods = parse_source(cat, r.text) if r.status_code == 200 else []
        except requests.RequestException as e:
            prods = []; log(f"  {cat} error {e!r}")
        for p in prods:
            img = urljoin(src, p["image"]) if p["image"] else ""
            price = float(p["price"].replace(",", "")) if p["price"] else ""
            key = f'{p["sku"]}|{cat}'
            if key in rows:
                continue
            missing = []
            if price == "":
                missing.append("price")
            if not img:
                missing.append("image")
            rows[key] = {
                "supplier": SUPPLIER, "season": SEASON,
                "sku": p["sku"], "product_name": p["name"] or p["alt"],
                "category": cat, "price": price, "currency": "USD",
                "price_tiers": p["tiers"],
                "source_price_label": "public_retail_price" if price != "" else "",
                "availability": p["stock"] or "in_stock",
                "image_url": img, "product_url": f"{BASE}/{src.split('/')[-2]}/General.html",
                "source_url": src, "needs_review": "; ".join(missing),
                "extracted_at": now, "run_id": run_id,
            }
        log(f"  [{i}/{len(cats)}] {cat}: {len(prods)} products")
        time.sleep(0.3)

    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["sku"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    frame["sku"] = frame["sku"].fillna("").astype(str)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="rw-export-"))
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
        "pricing_note": "Public RETAIL prices + volume tiers from static Source.html. "
                        "Wholesale tier is login-gated (no account) — not captured.",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} products -> {OUT_DIR/'products.xlsx'} (priced={priced}, imaged={imaged})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
