"""SuperMoss (supermoss.com) full-catalog extraction over HTTP.

SuperMoss runs on WooCommerce (WordPress). The WooCommerce Store API is public
and enabled, which is the whole catalog in one place:

    GET /wp-json/wc/store/v1/products?per_page=100&page=N   (X-WP-Total header = count)

Each record is rich: sku, name, description, prices (in MINOR units — divide by
10**currency_minor_unit), images[], categories, dimensions, weight, stock. Two
product shapes:
- ``type == "simple"``  -> one row, price from ``prices.price``.
- ``type == "variable"`` -> parent carries only a ``price_range`` and a
  ``variations: [{id, attributes:[{name,value}]}]`` list. Fetch each variation
  as its own product (``/products/{id}``) to get its SKU + price; the variant
  label (e.g. "Size: 2-cu-ft") comes from the parent's variations[].attributes.
  One row per variation.

Prices are whatever a guest sees. SuperMoss is a wholesale supplier; if a
logged-in wholesale tier differs, pass an authenticated session cookie to the
same Store API (WordPress login) and re-run — the Store API honors the session.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import time
from pathlib import Path

import requests

BASE = "https://www.supermoss.com"
PRODUCTS_API = f"{BASE}/wp-json/wc/store/v1/products"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
PER_PAGE = 100
REQUEST_DELAY_SECONDS = 0.15
_TAG_RE = re.compile(r"<[^>]+>")


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _get(session: requests.Session, url: str, *, params=None, retries=4):
    last = None
    for attempt in range(retries):
        try:
            return session.get(url, params=params, timeout=45)
        except requests.RequestException as exc:
            last = exc
            time.sleep(1.5 + attempt * 2)
    raise last


def fetch_all(session: requests.Session, checkpoint_path: Path, *,
              limit: int | None = None, log=print) -> int:
    """Page all base products; expand variable products into per-variant records.

    Appends one raw record per emitted row to the checkpoint (resumable by SKU/id).
    """
    done: set[str] = set()
    if checkpoint_path.exists():
        with checkpoint_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["_key"])
                except (json.JSONDecodeError, KeyError):
                    continue
        log(f"fetch: {len(done)} records already checkpointed")

    first = _get(session, PRODUCTS_API, params={"per_page": PER_PAGE, "page": 1})
    total = int(first.headers.get("X-WP-Total", 0))
    pages = int(first.headers.get("X-WP-TotalPages", 1))
    log(f"fetch: {total} base products across {pages} page(s)")

    written = len(done)
    with checkpoint_path.open("a", encoding="utf-8") as out:
        base_count = 0
        for page in range(1, pages + 1):
            products = first.json() if page == 1 else _get(
                session, PRODUCTS_API, params={"per_page": PER_PAGE, "page": page}
            ).json()
            for prod in products:
                base_count += 1
                if limit and base_count > limit:
                    break
                if prod.get("type") == "variable" and prod.get("variations"):
                    for v in prod["variations"]:
                        vid = v.get("id")
                        key = f"v{vid}"
                        if not vid or key in done:
                            continue
                        variation = _get(session, f"{PRODUCTS_API}/{vid}").json()
                        label = "; ".join(
                            f"{a.get('name')}: {a.get('value')}" for a in (v.get("attributes") or [])
                        )
                        rec = {"_key": key, "_parent": prod, "_variation": variation, "_label": label}
                        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        done.add(key)
                        written += 1
                        time.sleep(REQUEST_DELAY_SECONDS)
                else:
                    key = f"p{prod['id']}"
                    if key in done:
                        continue
                    rec = {"_key": key, "_simple": prod, "_label": ""}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    done.add(key)
                    written += 1
            out.flush()
            log(f"fetch: page {page}/{pages} ({written} rows)")
            if limit and base_count > limit:
                break
    return written


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def _name(text: str) -> str:
    return html_lib.unescape(text or "").strip()


def _money(prices: dict, field: str) -> str:
    raw = (prices or {}).get(field)
    if raw in (None, "", "null"):
        return ""
    try:
        minor = int((prices or {}).get("currency_minor_unit", 2))
        return round(int(raw) / (10 ** minor), 2)
    except (ValueError, TypeError):
        return ""


def _dims(product: dict) -> str:
    d = product.get("dimensions") or {}
    parts = [f"{lbl}{d[k]}" for lbl, k in (("L", "length"), ("W", "width"), ("H", "height")) if d.get(k)]
    return " ".join(parts)


def record_to_row(rec: dict, *, supplier: str, season: str, run_id: str, fetched_at: str) -> dict:
    if "_simple" in rec:
        prod = rec["_simple"]; priced = prod
    else:
        prod = rec["_parent"]; priced = rec["_variation"]
    prices = priced.get("prices") or {}

    images = [i.get("src") for i in (priced.get("images") or prod.get("images") or []) if i.get("src")]
    primary = images[0] if images else ""
    extras = images[1:10]
    cats = [c.get("name") for c in (prod.get("categories") or []) if c.get("name")]
    sku = priced.get("sku") or prod.get("sku") or ""
    price = _money(prices, "price")

    missing = []
    if price == "":
        missing.append("price")
    if not primary:
        missing.append("image")
    if not sku:
        missing.append("sku")
    if not (prod.get("description") or prod.get("short_description")):
        missing.append("description")

    return {
        "supplier": supplier,
        "season": season,
        "sku": sku or f"woo-{priced.get('id')}",
        "product_name": _name(prod.get("name") or ""),
        "variant": rec.get("_label", ""),
        "category": cats[0] if cats else "",
        "listed_under": "; ".join(cats),
        "description": _clean(prod.get("description") or prod.get("short_description") or ""),
        "price": price,
        "regular_price": _money(prices, "regular_price"),
        "sale_price": _money(prices, "sale_price"),
        "on_sale": priced.get("on_sale", prod.get("on_sale", "")),
        "source_price_label": "woocommerce_store_api",
        "availability": "in_stock" if priced.get("is_in_stock", prod.get("is_in_stock")) else "out_of_stock",
        "on_backorder": priced.get("is_on_backorder", ""),
        "low_stock_remaining": priced.get("low_stock_remaining") or "",
        "dimensions_in": _dims(priced) or _dims(prod),
        "weight": (priced.get("weight") or prod.get("weight") or ""),
        "image_url": primary,
        **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 11)},
        "image_count": len(images),
        "product_url": prod.get("permalink") or "",
        "source_url": PRODUCTS_API,
        "needs_review": "; ".join(missing),
        "extracted_at": fetched_at,
        "run_id": run_id,
        "product_id": str(priced.get("id") or prod.get("id") or ""),
    }


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name", "variant",
    "category", "listed_under", "description",
    "price", "regular_price", "sale_price", "on_sale", "source_price_label",
    "availability", "on_backorder", "low_stock_remaining",
    "dimensions_in", "weight",
    "image_url",
    "image_url_2", "image_url_3", "image_url_4", "image_url_5", "image_url_6",
    "image_url_7", "image_url_8", "image_url_9", "image_url_10",
    "image_count", "product_url", "source_url",
    "needs_review", "extracted_at", "run_id", "product_id",
]
