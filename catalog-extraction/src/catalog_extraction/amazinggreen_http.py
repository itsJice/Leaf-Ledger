"""Amazing Green (amazinggreen.com) full-catalog extraction over HTTP.

Shopify store, crawling allowed. The public JSON surfaces provide the whole
catalog without a browser:

- ``/products.json?limit=250&page=N`` — every published product with title,
  body_html, handle, vendor, product_type, tags, variants (sku, price,
  grams, options, availability), images, and option definitions.
- ``/products/{handle}.js`` — per-product detail incl. variant ``barcode``
  (UPC) when the store fills it.
- ``/collections.json`` + ``/collections/{handle}/products.json`` — category
  membership for ``listed_under`` and coverage verification.

Wholesale prices are NOT published online (confirmed via a logged-in
session 2026-07-04: a B2B lock app hides prices and the store's online
price fields are 0). Price cells are left blank and flagged
``price (login-gated)``; real pricing comes from the supplier rep and can
be merged later by SKU.
"""

from __future__ import annotations

import html as html_lib
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE = "https://www.amazinggreen.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
WORKERS = 6
REQUEST_DELAY_SECONDS = 0.1
GRAMS_PER_LB = 453.59237


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def fetch_all_products(session: requests.Session, log=print) -> list[dict]:
    """Full catalog via the bulk endpoint (250/page)."""
    products: list[dict] = []
    page = 1
    while True:
        response = session.get(f"{BASE}/products.json", params={"limit": 250, "page": page}, timeout=60)
        response.raise_for_status()
        batch = response.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        log(f"discover: page {page} -> {len(batch)} products (total {len(products)})")
        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)
    return products


def fetch_product_js(session: requests.Session, handle: str) -> dict:
    """Per-product endpoint that includes variant barcodes."""
    record: dict = {"handle": handle}
    response = session.get(f"{BASE}/products/{handle}.js", timeout=45)
    if response.status_code != 200:
        record.update(ok=False, error=f"HTTP {response.status_code}")
        return record
    try:
        record.update(ok=True, product=response.json())
    except json.JSONDecodeError:
        record.update(ok=False, error="BAD_JSON")
    return record


def _worker_fetch(handle: str, local: threading.local) -> dict:
    session = getattr(local, "session", None)
    if session is None:
        session = make_session()
        local.session = session
    last: dict = {}
    for attempt in range(3):
        time.sleep(REQUEST_DELAY_SECONDS + random.uniform(0, 0.1) + attempt * 2)
        try:
            return fetch_product_js(session, handle)
        except requests.RequestException as exc:
            last = {"handle": handle, "ok": False, "error": repr(exc)}
    return last


def run_details_stage(handles: list[str], checkpoint_path: Path, *,
                      limit: int | None = None, log=print) -> dict:
    done: set[str] = set()
    if checkpoint_path.exists():
        with checkpoint_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("ok"):
                    done.add(row["handle"])

    pending = [h for h in handles if h not in done]
    if limit:
        pending = pending[: max(0, limit - len(done))]
    log(f"details: {len(done)} already fetched, {len(pending)} to fetch")

    local = threading.local()
    write_lock = threading.Lock()
    counts = {"ok": 0, "error": 0}

    with checkpoint_path.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(_worker_fetch, h, local): h for h in pending}
            for future in as_completed(futures):
                handle = futures[future]
                try:
                    record = future.result()
                except Exception as exc:
                    record = {"handle": handle, "ok": False, "error": repr(exc)}
                record["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                counts["ok" if record.get("ok") else "error"] += 1
                with write_lock:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out.flush()
    return counts


def fetch_collections(session: requests.Session, log=print) -> list[dict]:
    """All collections and their product handles (for listed_under/coverage)."""
    collections: list[dict] = []
    page = 1
    while True:
        response = session.get(f"{BASE}/collections.json", params={"limit": 250, "page": page}, timeout=60)
        response.raise_for_status()
        batch = response.json().get("collections", [])
        if not batch:
            break
        collections.extend(batch)
        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    results = []
    for collection in collections:
        handle = collection.get("handle")
        handles: list[str] = []
        page = 1
        while True:
            response = session.get(
                f"{BASE}/collections/{handle}/products.json",
                params={"limit": 250, "page": page}, timeout=60,
            )
            if response.status_code != 200:
                break
            batch = response.json().get("products", [])
            if not batch:
                break
            handles.extend(p.get("handle") for p in batch if p.get("handle"))
            page += 1
            time.sleep(REQUEST_DELAY_SECONDS)
        results.append({
            "handle": handle,
            "title": collection.get("title") or handle,
            "products_count": collection.get("products_count"),
            "product_handles": handles,
        })
        log(f"collection {collection.get('title')}: {len(handles)} products (site says {collection.get('products_count')})")
    return results


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def _https(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def product_to_rows(bulk: dict, js: dict | None, collections_for_handle: list[str], *,
                    supplier: str, season: str, run_id: str, fetched_at: str) -> list[dict]:
    handle = bulk.get("handle", "")
    images = [_https(i.get("src", "")) for i in bulk.get("images", []) if i.get("src")]
    primary = images[0] if images else ""
    extras = images[1:10]
    description = _strip_html(bulk.get("body_html") or "")
    option_names = [o.get("name") for o in bulk.get("options", []) if o.get("name")]

    # barcode lookup from the .js endpoint (variant id -> barcode)
    barcodes: dict[int, str] = {}
    if js:
        for variant in js.get("variants", []):
            if variant.get("barcode"):
                barcodes[variant["id"]] = str(variant["barcode"])

    rows = []
    for variant in bulk.get("variants", []):
        opts = [variant.get(f"option{i}") for i in (1, 2, 3)]
        variant_desc = " / ".join(
            f"{n}: {v}" for n, v in zip(option_names, opts)
            if v and v != "Default Title"
        )
        sku = (variant.get("sku") or "").strip()
        barcode = barcodes.get(variant.get("id"), "")
        price = float(variant.get("price") or 0)
        grams = variant.get("grams") or 0

        missing = []
        if price <= 0:
            missing.append("price (login-gated)")
        if not sku:
            missing.append("sku")
        if not primary:
            missing.append("image")
        if not description:
            missing.append("description")

        rows.append({
            "supplier": supplier,
            "season": season,
            "sku": sku or f"{handle}#{variant.get('id')}",
            "upc": barcode if barcode.isdigit() and len(barcode) in (12, 13) else "",
            "product_name": bulk.get("title") or "",
            "variant": variant_desc,
            "category": collections_for_handle[0] if collections_for_handle else "",
            "subcategory": "",
            "listed_under": "; ".join(collections_for_handle),
            "product_type": bulk.get("product_type") or "",
            "description": description,
            "price": price if price > 0 else "",
            "list_price": float(variant["compare_at_price"]) if variant.get("compare_at_price") else "",
            "source_price_label": "public_site_price" if price > 0 else "",
            "uom": "",
            "moq": "",
            "box_quantity": "",
            "case_quantity": "",
            "availability": "in_stock" if variant.get("available") else "unavailable",
            "qty_in_stock": "",
            "weight_lbs": round(grams / GRAMS_PER_LB, 2) if grams else "",
            "tags": "; ".join(bulk.get("tags") or []),
            "vendor": bulk.get("vendor") or "",
            "image_url": primary,
            **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 11)},
            "image_count": len(images),
            "product_url": f"{BASE}/products/{handle}",
            "source_url": f"{BASE}/products.json",
            "needs_review": "; ".join(missing),
            "extracted_at": fetched_at,
            "run_id": run_id,
            "product_id": str(bulk.get("id") or ""),
        })
    return rows


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "upc", "product_name", "variant",
    "category", "subcategory", "listed_under", "product_type", "description",
    "price", "list_price", "source_price_label", "uom", "moq",
    "box_quantity", "case_quantity",
    "availability", "qty_in_stock", "weight_lbs", "tags", "vendor",
    "image_url",
    "image_url_2", "image_url_3", "image_url_4", "image_url_5", "image_url_6",
    "image_url_7", "image_url_8", "image_url_9", "image_url_10",
    "image_count", "product_url", "source_url",
    "needs_review", "extracted_at", "run_id", "product_id",
]
