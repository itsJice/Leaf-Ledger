#!/usr/bin/env python3
"""Unlimited Container Inc — full catalog over the public Shopify JSON API.

Shopify store (~488 products). Prices are PUBLIC wholesale (no login): the real
number lives in `variants[].price`. Rich detail (per-SKU item numbers, physical
dimensions, case-pack quantity) is embedded in the `body_html` pricing table and
variant titles, so we capture both the structured fields and the parsed HTML.

Stages: discover (bulk products.json) -> export. One resumable artifact.
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

BASE = "https://www.unlimitedcontainers.com"
SUPPLIER = "Unlimited Container"
SEASON = "2026"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
GRAMS_PER_LB = 453.59237
OUT_DIR = ROOT / "outputs" / "unlimited_container-full"
BULK_PATH = OUT_DIR / "products_bulk.json"

_TAG_RE = re.compile(r"<[^>]+>")
_DIM_RE = re.compile(r'([HDWL])\s*[-:]\s*([\d.]+)\s*"', re.I)
_CASE_RE = re.compile(r'(\d+)\s*pc\(?s?\)?\s*/\s*case', re.I)


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _curl_json(url: str) -> dict:
    """Fetch JSON via curl. Cloudflare fingerprints and 429s the Python `requests`
    client here, but lets curl through with a browser UA."""
    for attempt in range(5):
        proc = subprocess.run(
            ["curl", "-s", "--compressed", "-A", UA, url],
            capture_output=True, text=True, timeout=90,
        )
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            wait = 4 * (attempt + 1)
            log(f"  bad body for {url} (len={len(proc.stdout)}) — retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"could not fetch {url}")


def fetch_all_products() -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        data = _curl_json(f"{BASE}/products.json?limit=250&page={page}")
        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        log(f"discover: page {page} -> {len(batch)} (total {len(products)})")
        page += 1
        time.sleep(1.0)
    return products


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def _https(u: str) -> str:
    return "https:" + u if u.startswith("//") else u


def _dims(text: str) -> str:
    found = _DIM_RE.findall(text or "")
    seen: dict[str, str] = {}
    for axis, val in found:
        seen.setdefault(axis.upper(), val)
    order = [a for a in ("H", "D", "W", "L") if a in seen]
    return ", ".join(f"{a}-{seen[a]}\"" for a in order)


def product_to_rows(p: dict, run_id: str, now: str) -> list[dict]:
    images = [_https(i.get("src", "")) for i in p.get("images", []) if i.get("src")]
    primary = images[0] if images else ""
    extras = images[1:10]
    body = p.get("body_html") or ""
    description = _strip(body)
    case_qty = ""
    m = _CASE_RE.search(body)
    if m:
        case_qty = m.group(1)
    option_names = [o.get("name") for o in p.get("options", []) if o.get("name")]

    rows = []
    for v in p.get("variants", []):
        opts = [v.get(f"option{i}") for i in (1, 2, 3)]
        variant_desc = " / ".join(
            f"{n}: {val}" for n, val in zip(option_names, opts)
            if val and val != "Default Title"
        )
        title_dims = _dims(v.get("title") or "")
        price = float(v.get("price") or 0)
        grams = v.get("grams") or 0
        sku = (v.get("sku") or "").strip()
        missing = []
        if price <= 0:
            missing.append("price")
        if not sku:
            missing.append("sku")
        if not primary:
            missing.append("image")
        rows.append({
            "supplier": SUPPLIER,
            "season": SEASON,
            "sku": sku or f'{p.get("handle")}#{v.get("id")}',
            "upc": (str(v.get("barcode")) if v.get("barcode") else ""),
            "product_name": p.get("title") or "",
            "variant": variant_desc,
            "category": p.get("product_type") or "",
            "dimensions": title_dims,
            "description": description,
            "price": price if price > 0 else "",
            "list_price": float(v["compare_at_price"]) if v.get("compare_at_price") else "",
            "source_price_label": "public_wholesale_price" if price > 0 else "",
            "case_quantity": case_qty,
            "availability": "in_stock" if v.get("available") else "unavailable",
            "weight_lbs": round(grams / GRAMS_PER_LB, 2) if grams else "",
            "vendor": p.get("vendor") or "",
            "tags": "; ".join(p.get("tags") or []) if isinstance(p.get("tags"), list) else (p.get("tags") or ""),
            "image_url": primary,
            **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 11)},
            "image_count": len(images),
            "product_url": f"{BASE}/products/{p.get('handle')}",
            "source_url": f"{BASE}/products.json",
            "needs_review": "; ".join(missing),
            "extracted_at": now,
            "run_id": run_id,
            "product_id": str(p.get("id") or ""),
        })
    return rows


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "upc", "product_name", "variant", "category",
    "dimensions", "description", "price", "list_price", "source_price_label",
    "case_quantity", "availability", "weight_lbs", "vendor", "tags",
    "image_url", "image_url_2", "image_url_3", "image_url_4", "image_url_5",
    "image_url_6", "image_url_7", "image_url_8", "image_url_9", "image_url_10",
    "image_count", "product_url", "source_url", "needs_review", "extracted_at",
    "run_id", "product_id",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["discover", "export", "all"], default="all")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.stage in ("discover", "all") and (args.stage == "discover" or not BULK_PATH.exists()):
        products = fetch_all_products()
        BULK_PATH.write_text(json.dumps(products, ensure_ascii=False), encoding="utf-8")
        log(f"discover: {len(products)} products -> {BULK_PATH}")

    if args.stage in ("export", "all"):
        products = json.loads(BULK_PATH.read_text(encoding="utf-8"))
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rows: dict[str, dict] = {}
        for p in products:
            for row in product_to_rows(p, run_id, now):
                key = f'{row["sku"]}|{row["variant"]}'
                rows[key] = row
        ordered = sorted(rows.values(), key=lambda r: (r["category"], r["product_name"], r["variant"]))
        frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
        for col in ("sku", "upc", "product_id"):
            frame[col] = frame[col].fillna("").astype(str)

        import shutil, tempfile
        tmp = Path(tempfile.mkdtemp(prefix="uc-export-"))
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
            "products": len(products), "rows_exported": len(frame),
            "with_price": priced, "with_image": imaged,
            "needs_review_count": int((frame["needs_review"] != "").sum()),
            "pricing_note": "Public Shopify wholesale price (variants[].price); no login required.",
        }
        (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        log(f"export: {len(frame)} rows ({len(products)} products) -> {OUT_DIR/'products.xlsx'} "
            f"(priced={priced}, imaged={imaged})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
