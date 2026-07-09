#!/usr/bin/env python3
"""PMJC Inc — image + SKU harvest from the static HTML brochure site.

PMJC (pmjcinc.com) is a hand-coded static-HTML brochure, not an ecommerce store:
no platform, no JSON, no prices anywhere ("Contact us today for our price lists!").
Product identity lives in the image filenames (base SKU + color/finish suffix).
So this harvests, per category page, the product images and derives the SKU from
the filename. No prices/descriptions exist to capture (flagged).
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

BASE = "https://www.pmjcinc.com"
SUPPLIER = "PMJC Inc"
SEASON = "2026"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT_DIR = ROOT / "outputs" / "pmjc-full"
# nice category labels for the page slugs
CATEGORY_LABELS = {
    "AHnewwood": "Wood Containers", "BallFeetContainers": "Ball-Feet Containers",
    "Ceramiccontainer": "Ceramic Containers", "Plasticcontainers": "Plastic Containers",
    "antiques": "Antiques", "fiberglass": "Fiberglass", "fiberglassplanter": "Fiberglass Planters",
    "fiberstoneplanterurn": "Fiberstone Planters/Urns", "fiberstoneplanterurn1": "Fiberstone Planters/Urns",
    "fishbowl": "Fish Bowls", "flowers": "Artificial Flowers", "lamps": "Lamps", "trays": "Trays",
    "accessory": "Accessories", "floralfoam": "Floral Foam",
    "T1008": "Tole Containers", "T1015": "Tole Containers", "T1158": "Tole Containers",
    "page1": "Containers", "page2": "Containers", "page3": "Containers", "page4": "Containers",
}
_SKU_RE = re.compile(r"^([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)$")


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    return s


def discover_pages(s: requests.Session) -> list[str]:
    r = s.get(f"{BASE}/", timeout=45)
    pages = set()
    for m in re.findall(r'href="([^"]+\.html)"', r.text, re.I):
        slug = m.rsplit("/", 1)[-1]
        base = slug[:-5]
        if base.lower() in ("index", "contact", "about", "home") or "catalog" in base.lower():
            continue
        pages.add(f"{BASE}/{slug}")
    return sorted(pages)


def scrape_page(s: requests.Session, url: str) -> list[dict]:
    r = s.get(url, timeout=45)
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    slug = url.rsplit("/", 1)[-1][:-5]
    category = CATEGORY_LABELS.get(slug, slug.replace("_", " ").title())
    out, seen = [], set()
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if not src:
            continue
        fname = src.rsplit("/", 1)[-1]
        stem, ext = (fname.rsplit(".", 1) + [""])[:2]
        if ext.lower() not in ("jpg", "jpeg", "png", "gif"):
            continue
        # skip layout/spacer images
        if re.search(r"(logo|banner|button|spacer|header|footer|bg|nav|arrow|title|line)", stem, re.I):
            continue
        if not _SKU_RE.match(stem) or len(stem) < 3 or stem.isalpha():
            continue
        sku = stem.upper()
        if sku in seen:
            continue
        seen.add(sku)
        base_sku = sku.split("-")[0]
        out.append({
            "sku": sku, "base_sku": base_sku,
            "color": "-".join(sku.split("-")[1:]) if "-" in sku else "",
            "category": category,
            "image": urljoin(BASE + "/", src).replace("http://", "https://"),
            "alt": (img.get("alt") or "").strip(),
        })
    return out


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "base_sku", "color", "product_name", "category",
    "price", "source_price_label", "image_url", "source_url", "needs_review",
    "extracted_at", "run_id",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["all"], default="all")
    ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    s = make_session()
    pages = discover_pages(s)
    log(f"discover: {len(pages)} category pages")
    rows: dict[str, dict] = {}
    for i, url in enumerate(pages, 1):
        for p in scrape_page(s, url):
            if p["sku"] in rows:
                continue
            rows[p["sku"]] = {
                "supplier": SUPPLIER, "season": SEASON,
                "sku": p["sku"], "base_sku": p["base_sku"], "color": p["color"],
                "product_name": p["alt"] or p["category"],
                "category": p["category"],
                "price": "", "source_price_label": "",
                "image_url": p["image"],
                "source_url": url,
                "needs_review": "price (contact for wholesale price list); description",
                "extracted_at": now, "run_id": run_id,
            }
        log(f"  [{i}/{len(pages)}] {url.rsplit('/',1)[-1]}: {len(rows)} SKUs total")
        time.sleep(0.4)

    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["sku"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="pmjc-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    for n in ("products.xlsx", "products.csv"):
        shutil.move(str(tmp / n), str(OUT_DIR / n))
    shutil.rmtree(tmp, ignore_errors=True)

    imaged = int((frame["image_url"].astype(str).str.strip() != "").sum())
    report = {
        "supplier": SUPPLIER, "season": SEASON, "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_exported": len(frame), "with_price": 0, "with_image": imaged,
        "pricing_note": "Static brochure site — NO online prices ('contact us for price lists') "
                        "and no descriptions. Image + SKU (from filename) harvest only.",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} SKUs -> {OUT_DIR/'products.xlsx'} (imaged={imaged}, priced=0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
