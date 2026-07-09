"""Generic sitemap + per-product schema.org ld+json extractor.

Reusable runner for suppliers that (a) publish a product sitemap and (b) embed
a schema.org `Product` block (`application/ld+json`) plus a `BreadcrumbList` in
each product page's server-rendered HTML. Covers BigCommerce, nopCommerce, and
similar server-rendered stores.

A supplier is described by a SupplierConfig; the runner handles discovery,
threaded fetching with checkpoints, ld+json parsing (both breadcrumb shapes —
name direct, or nested under `item.name`), price gating, and row mapping.
"""

from __future__ import annotations

import html as html_lib
import json
import random
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_LDJSON_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S)
_LOC_RE = re.compile(r"<loc>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</loc>", re.S)
_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class SupplierConfig:
    supplier: str
    season: str
    base_url: str
    sitemap_url: str
    workers: int = 4
    delay: float = 0.25
    title_must_contain: str = ""          # skip pages whose <title> lacks this
    description_urldecode: bool = False   # BigCommerce URL-encodes descriptions
    category_from_url_fallback: bool = True  # derive category from URL path when no breadcrumb
    price_gated_note: str = "price (login-gated)"


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    # Some stores (e.g. PrestaShop/secondflor) return a truncated body — and thus a
    # WRONG ld+json block — unless the client advertises compression.
    session.headers["Accept-Encoding"] = "gzip, deflate"
    return session


def _blocks(html: str) -> list:
    out = []
    for raw in _LDJSON_RE.findall(html):
        try:
            # strict=False tolerates literal newlines/tabs inside string values
            # (e.g. PrestaShop/secondflor embed raw control chars in description).
            data = json.loads(raw.strip(), strict=False)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "@graph" in data:
            out.extend(data["@graph"])
        elif isinstance(data, list):
            out.extend(data)
        else:
            out.append(data)
    # Unwrap SFCC/schema.org page wrappers (ItemPage/WebPage) whose real product
    # sits under mainEntity — surface it so _typed(..., "Product") finds it.
    for b in list(out):
        if isinstance(b, dict) and isinstance(b.get("mainEntity"), dict):
            out.append(b["mainEntity"])
    return out


def _typed(blocks: list, wanted: str) -> dict | None:
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("@type")
        if t == wanted or (isinstance(t, list) and wanted in t):
            return b
    return None


def _breadcrumb_names(blocks: list) -> list[str]:
    bc = _typed(blocks, "BreadcrumbList")
    if not bc:
        return []
    names = []
    for el in bc.get("itemListElement", []):
        name = el.get("name")
        if not name and isinstance(el.get("item"), dict):
            name = el["item"].get("name")
        if name and name.lower() not in ("home",):
            names.append(str(name).strip())
    return names


def fetch_sitemap_urls(session: requests.Session, sitemap_url: str, log=print) -> list[str]:
    """Return product URLs from a sitemap or sitemap index."""
    resp = session.get(sitemap_url, timeout=120)
    resp.raise_for_status()
    locs = [u.strip() for u in _LOC_RE.findall(resp.text)]
    # sitemap index -> recurse into product sub-sitemaps only
    if locs and all(l.endswith(".xml") or "sitemap" in l.lower() or "xmlsitemap" in l.lower() for l in locs[:3]):
        product_maps = [l for l in locs if "product" in l.lower()]
        if product_maps:
            urls: list[str] = []
            for m in product_maps:
                sub = session.get(m, timeout=120)
                urls.extend(u.strip() for u in _LOC_RE.findall(sub.text))
            return list(dict.fromkeys(urls))
    return list(dict.fromkeys(locs))


def fetch_detail(session: requests.Session, url: str, cfg: SupplierConfig) -> dict:
    record: dict = {"url": url}
    resp = session.get(url, timeout=45)
    if resp.status_code != 200:
        record.update(ok=False, error=f"HTTP {resp.status_code}")
        return record
    if cfg.title_must_contain:
        title = _TITLE_RE.search(resp.text)
        if not title or cfg.title_must_contain.lower() not in title.group(1).lower():
            record.update(ok=False, error="TITLE_MISMATCH")
            return record
    blocks = _blocks(resp.text)
    product = _typed(blocks, "Product")
    if not product:
        record.update(ok=False, error="NO_PRODUCT")
        return record
    record.update(ok=True, product=product, breadcrumb=_breadcrumb_names(blocks))
    return record


def _worker(url: str, local: threading.local, cfg: SupplierConfig) -> dict:
    session = getattr(local, "session", None)
    if session is None:
        session = make_session()
        local.session = session
    last: dict = {}
    for attempt in range(3):
        time.sleep(cfg.delay + random.uniform(0, 0.15) + attempt * 2)
        try:
            return fetch_detail(session, url, cfg)
        except requests.RequestException as exc:
            last = {"url": url, "ok": False, "error": repr(exc)}
    return last


def run_details_stage(urls: list[str], checkpoint_path: Path, cfg: SupplierConfig, *,
                      limit: int | None = None, progress_every: int = 250, log=print) -> dict:
    done: set[str] = set()
    if checkpoint_path.exists():
        with checkpoint_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("ok") is not None:
                    done.add(row["url"])

    pending = [u for u in urls if u not in done]
    if limit:
        pending = pending[:limit]
    log(f"details: {len(done)} already done, {len(pending)} to fetch")

    local = threading.local()
    lock = threading.Lock()
    counts = {"ok": 0, "skip": 0, "error": 0}
    started = time.monotonic()

    with checkpoint_path.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
            futures = {pool.submit(_worker, u, local, cfg): u for u in pending}
            for i, fut in enumerate(as_completed(futures), 1):
                url = futures[fut]
                try:
                    rec = fut.result()
                except Exception as exc:
                    rec = {"url": url, "ok": False, "error": repr(exc)}
                rec["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if rec.get("ok"):
                    counts["ok"] += 1
                elif rec.get("error") in ("NO_PRODUCT", "TITLE_MISMATCH"):
                    counts["skip"] += 1
                else:
                    counts["error"] += 1
                with lock:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                if i % progress_every == 0:
                    rate = i / max(1e-9, time.monotonic() - started)
                    left = (len(pending) - i) / max(rate, 1e-9)
                    log(f"details: {i}/{len(pending)} (ok={counts['ok']} skip={counts['skip']} "
                        f"err={counts['error']}, {rate:.1f}/s, ~{left/60:.0f}m left)")
    return counts


def _text(value) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", str(value or "")))).strip()


def _images(product: dict) -> list[str]:
    img = product.get("image")
    if isinstance(img, list):
        return [str(u) for u in img if u]
    return [str(img)] if img else []


def ldjson_to_row(record: dict, cfg: SupplierConfig, *, run_id: str) -> dict:
    p = record["product"]
    crumbs = record.get("breadcrumb") or []
    # last breadcrumb is usually the product itself; category/subcategory precede it
    cats = crumbs[:-1] if len(crumbs) > 1 else crumbs
    if not cats and cfg.category_from_url_fallback:
        # derive from URL path segments, dropping the final product slug
        segs = [s for s in urlparse(record.get("url", "")).path.split("/") if s]
        cats = [s.replace("-", " ").title() for s in segs[:-1]] if len(segs) > 1 else []
    category = cats[0] if cats else ""
    subcategory = cats[1] if len(cats) > 1 else ""

    brand = p.get("brand")
    brand = brand.get("name") if isinstance(brand, dict) else (brand or "")

    offers = p.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    raw_price = offers.get("price")
    try:
        price = float(raw_price) if raw_price not in (None, "", "Call for pricing") and float(raw_price) > 0 else ""
    except (ValueError, TypeError):
        price = ""

    desc = p.get("description") or ""
    if cfg.description_urldecode:
        desc = unquote(str(desc))
    desc = _text(desc)

    images = _images(p)
    primary = images[0] if images else ""
    extras = images[1:10]

    missing = []
    if price == "":
        missing.append(cfg.price_gated_note)
    if not primary:
        missing.append("image")
    if not desc:
        missing.append("description")
    sku = _text(p.get("sku")).split(" - ")[0].strip()  # strip "  - See All Options" noise
    if not sku:
        missing.append("sku")

    availability = ""
    avail = offers.get("availability") or ""
    if avail:
        availability = str(avail).rsplit("/", 1)[-1]  # InStock / OutOfStock

    return {
        "supplier": cfg.supplier,
        "season": cfg.season,
        "sku": sku,
        "upc": _text(p.get("gtin") or p.get("gtin13") or ""),
        "product_name": _text(p.get("name")),
        "brand": _text(brand),
        "category": category,
        "subcategory": subcategory,
        "breadcrumb": " > ".join(crumbs),
        "description": desc,
        "price": price,
        "source_price_label": "public_site_price" if price != "" else "",
        "availability": availability,
        "image_url": primary,
        **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 8)},
        "image_count": len(images),
        "product_url": record.get("url", ""),
        "source_url": cfg.sitemap_url,
        "needs_review": "; ".join(missing),
        "extracted_at": record.get("fetched_at", ""),
        "run_id": run_id,
    }


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "upc", "product_name", "brand",
    "category", "subcategory", "breadcrumb", "description",
    "price", "source_price_label", "availability",
    "image_url", "image_url_2", "image_url_3", "image_url_4",
    "image_url_5", "image_url_6", "image_url_7", "image_count",
    "product_url", "source_url", "needs_review", "extracted_at", "run_id",
]
