#!/usr/bin/env python3
"""DFW Glass and Vases — full catalog over server-rendered HTML (Fortune3 cart).

~515 products. No JSON API; each product page carries Open Graph product meta
(clean: price, currency, availability, SKU) plus schema.org microdata. Prices are
PUBLIC — the orderslogin.cgi is order-history only and does NOT gate pricing.

Gotchas handled: sitemap URLs are http:// and 301 to https (follow redirects);
inch-quotes in name/alt attributes break naive parsing (use bs4/lxml + OG meta);
category (Products-*) pages are excluded; relative image paths resolved to full-res.

Stages: discover (sitemap) -> details (checkpointed) -> export.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://www.dfwvases.com"
SUPPLIER = "DFW Glass and Vases"
SEASON = "2026"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
WORKERS = 5
DELAY = 0.25
OUT_DIR = ROOT / "outputs" / "dfw_vases-full"
ITEMS_PATH = OUT_DIR / "items.json"
DETAILS_PATH = OUT_DIR / "details.ndjson"

_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")
# dims like 4" x 8" and case pack "12 p/c" live in the product name
_DIM_RE = re.compile(r'([\d.]+)"\s*[xX]\s*([\d.]+)"')
_CASE_RE = re.compile(r'(\d+)\s*p/?c', re.I)


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    return s


_NAV = {"products.html", "specials.html", "ideas.html", "contact.html", "index.html",
        "about.html", "faq.html", "policies.html", "terms.html", "cart.html",
        "sitemap.html", "content.html"}


def discover(session: requests.Session) -> list[str]:
    """Enumerate from the LIVE category pages, not the sitemap.

    ~57% of the sitemap's product URLs are stale 404s; the category pages
    (Products-*.html) link only to currently-live products. Category pages
    render the full product set (no pagination).
    """
    r = session.get(f"{BASE}/sitemap.xml", timeout=60)
    r.raise_for_status()
    cats = []
    for loc in _LOC_RE.findall(r.text):
        tail = loc.rsplit("/", 1)[-1]
        if tail.startswith("Products-") and tail.endswith(".html"):
            cats.append(loc.replace("http://", "https://"))
    cats = list(dict.fromkeys(cats))
    log(f"discover: {len(cats)} category pages")

    products: list[str] = []
    for i, cat in enumerate(cats, 1):
        try:
            cr = session.get(cat, timeout=45, allow_redirects=True)
        except requests.RequestException as exc:
            log(f"  category fetch failed {cat}: {exc!r}")
            continue
        soup = BeautifulSoup(cr.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            tail = href.rsplit("/", 1)[-1]
            if (tail.endswith(".html") and "Products-" not in href
                    and not href.startswith("http") and tail.lower() not in _NAV
                    and "-" in tail):
                products.append(urljoin(BASE + "/", href))
        if i % 10 == 0:
            log(f"  {i}/{len(cats)} categories, {len(set(products))} products so far")
        time.sleep(DELAY)
    return list(dict.fromkeys(products))


def _og(soup: BeautifulSoup, prop: str) -> str:
    el = soup.find("meta", attrs={"property": prop})
    return (el.get("content") or "").strip() if el else ""


def parse_product(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    # name: itemprop=name span in the body (non-empty); fallback to <title> minus SKU
    name = ""
    for el in soup.find_all(attrs={"itemprop": "name"}):
        txt = el.get_text(strip=True)
        if txt:
            name = txt
            break
    if not name and soup.title and soup.title.string:
        name = re.sub(r"^\S+\s+", "", soup.title.string.split(" - ")[0]).strip()

    sku = _og(soup, "product:retailer_item_id")
    price_s = _og(soup, "product:price:amount")
    currency = _og(soup, "product:price:currency") or "USD"
    availability = _og(soup, "product:availability")
    try:
        price = float(price_s) if price_s else ""
    except ValueError:
        price = ""

    # description: itemprop=description body text (the <meta> description is stale)
    desc = ""
    d = soup.find(attrs={"itemprop": "description"})
    if d:
        desc = re.sub(r"\s+", " ", d.get_text(" ", strip=True)).strip()

    # gallery: full-res img-*.jpg (prefer data-magnify-src), resolved absolute
    images: list[str] = []
    for im in soup.find_all("img"):
        src = im.get("data-magnify-src") or im.get("src") or ""
        if re.search(r"(^|/)img-.+\.jpe?g$", src, re.I):
            images.append(urljoin(BASE + "/", src))
    if not images:
        og_img = _og(soup, "og:image")
        if og_img:
            images.append(og_img.replace("icon-img-", "img-"))
    images = list(dict.fromkeys(images))

    dims = ""
    m = _DIM_RE.search(name)
    if m:
        dims = f'{m.group(1)}" x {m.group(2)}"'
    case_pack = ""
    m = _CASE_RE.search(name)
    if m:
        case_pack = m.group(1)

    return {
        "sku": sku, "product_name": name, "price": price, "currency": currency,
        "availability": availability.replace("in stock", "InStock"),
        "description": desc, "dimensions": dims, "case_quantity": case_pack,
        "images": images,
    }


def fetch_detail(session: requests.Session, url: str) -> dict:
    rec: dict = {"url": url}
    r = session.get(url, timeout=45, allow_redirects=True)
    if r.status_code != 200:
        rec.update(ok=False, error=f"HTTP {r.status_code}")
        return rec
    try:
        rec.update(ok=True, **parse_product(url, r.text))
    except Exception as exc:  # noqa: BLE001 - record and continue
        rec.update(ok=False, error=repr(exc))
    return rec


def _worker(url: str, local: threading.local) -> dict:
    s = getattr(local, "session", None)
    if s is None:
        s = make_session()
        local.session = s
    last: dict = {"url": url, "ok": False, "error": "unknown"}
    for attempt in range(3):
        time.sleep(DELAY + random.uniform(0, 0.15) + attempt * 2)
        try:
            return fetch_detail(s, url)
        except requests.RequestException as exc:
            last = {"url": url, "ok": False, "error": repr(exc)}
    return last


def run_details(urls: list[str], limit: int | None) -> dict:
    done: set[str] = set()
    if DETAILS_PATH.exists():
        for line in DETAILS_PATH.open(encoding="utf-8"):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("ok") is not None:
                done.add(row["url"])
    pending = [u for u in urls if u not in done]
    if limit:
        pending = pending[:limit]
    log(f"details: {len(done)} done, {len(pending)} to fetch")
    local = threading.local()
    lock = threading.Lock()
    counts = {"ok": 0, "err": 0}
    with DETAILS_PATH.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(_worker, u, local): u for u in pending}
            for i, f in enumerate(as_completed(futs), 1):
                rec = f.result()
                rec["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                counts["ok" if rec.get("ok") else "err"] += 1
                with lock:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                if i % 100 == 0:
                    log(f"details: {i}/{len(pending)} (ok={counts['ok']} err={counts['err']})")
    return counts


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name", "category", "dimensions",
    "case_quantity", "description", "price", "currency", "source_price_label",
    "availability", "image_url", "image_url_2", "image_url_3", "image_url_4",
    "image_url_5", "image_count", "product_url", "source_url", "needs_review",
    "extracted_at", "run_id",
]


def _category_from_url(url: str) -> str:
    tail = url.rsplit("/", 1)[-1].removesuffix(".html")
    return tail.split("-", 1)[0].replace("_", " ") if "-" in tail else ""


def export(run_id: str) -> None:
    rows: dict[str, dict] = {}
    errors = 0
    for line in DETAILS_PATH.open(encoding="utf-8"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not rec.get("ok"):
            errors += 1
            continue
        images = rec.get("images") or []
        primary = images[0] if images else ""
        extras = images[1:5]
        price = rec.get("price", "")
        missing = []
        if price == "":
            missing.append("price")
        if not primary:
            missing.append("image")
        if not rec.get("sku"):
            missing.append("sku")
        row = {
            "supplier": SUPPLIER, "season": SEASON,
            "sku": rec.get("sku") or "",
            "product_name": rec.get("product_name") or "",
            "category": _category_from_url(rec["url"]),
            "dimensions": rec.get("dimensions") or "",
            "case_quantity": rec.get("case_quantity") or "",
            "description": rec.get("description") or "",
            "price": price,
            "currency": rec.get("currency") or "USD",
            "source_price_label": "public_site_price" if price != "" else "",
            "availability": rec.get("availability") or "",
            "image_url": primary,
            **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 6)},
            "image_count": len(images),
            "product_url": rec["url"],
            "source_url": f"{BASE}/sitemap.xml",
            "needs_review": "; ".join(missing),
            "extracted_at": rec.get("fetched_at", ""),
            "run_id": run_id,
        }
        key = row["sku"] or row["product_url"]
        rows[key] = row

    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["product_name"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    frame["sku"] = frame["sku"].fillna("").astype(str)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="dfw-export-"))
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
        "rows_exported": len(frame), "with_price": priced, "with_image": imaged,
        "fetch_errors": errors,
        "needs_review_count": int((frame["needs_review"] != "").sum()),
        "pricing_note": "Public Fortune3 storefront price (OG product:price:amount); no login required.",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} rows -> {OUT_DIR/'products.xlsx'} (priced={priced}, imaged={imaged}, errors={errors})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["discover", "details", "export", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.stage in ("discover", "all") and (args.stage == "discover" or not ITEMS_PATH.exists()):
        urls = discover(make_session())
        ITEMS_PATH.write_text(json.dumps(urls, indent=0), encoding="utf-8")
        log(f"discover: {len(urls)} product URLs -> {ITEMS_PATH}")
    if args.stage in ("details", "all"):
        urls = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
        counts = run_details(urls, args.limit)
        log(f"details: done (ok={counts['ok']} err={counts['err']})")
    if args.stage in ("export", "all"):
        export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
