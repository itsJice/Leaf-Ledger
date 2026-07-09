"""Craftex (craftex.com) full-catalog extraction over HTTP.

Craftex is a Wix Stores site. No login is required — prices are public.
Two embedded-data sources make this browserless:

- ``store-products-sitemap.xml`` enumerates every product URL (~4.6k).
- Every product page embeds the full Wix catalog model in the
  ``wix-warmup-data`` script tag: name, SKU, prices, inventory quantity,
  weight, all media, categories/breadcrumbs, options, and per-variant
  ``productItems`` (each with its own SKU, price, and inventory).

Category listing pages ("infinite scroll") accept a cumulative ``?page=N``
parameter — one request at the last page returns the complete product list
for a category, which we use for coverage verification.

Rows are emitted per purchasable variant (product item) when a product has
options; single-variant products emit one row. Dedupe key: supplier + SKU
(falling back to product id + variant id when a SKU is absent).
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

BASE = "https://www.craftex.com"
SITEMAP_PRODUCTS = f"{BASE}/store-products-sitemap.xml"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

WORKERS = 6
REQUEST_DELAY_SECONDS = 0.1
WARMUP_RE = re.compile(r'id="wix-warmup-data"[^>]*>(.*?)</script>', re.S)

# Store sections seen in site navigation (recording 2026-07-02). Extend as
# nav changes; unknown paths simply return no category warmup and are skipped.
CATEGORY_PATHS = [
    "/ribbon",
    "/christmas",
    "/seasonal-holidays",
    "/floral",
    "/shop",
]


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def fetch_product_urls(session: requests.Session) -> list[str]:
    response = session.get(SITEMAP_PRODUCTS, timeout=120)
    response.raise_for_status()
    urls: list[str] = []
    seen: set[str] = set()
    for loc in re.findall(r"<loc>([^<]+)</loc>", response.text):
        loc = loc.strip()
        if "/product-page/" in loc and loc not in seen:
            seen.add(loc)
            urls.append(loc)
    return urls


def _warmup(html: str) -> dict:
    match = WARMUP_RE.search(html)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def _find_product(warmup: dict) -> dict | None:
    for app in (warmup.get("appsWarmupData") or {}).values():
        if not isinstance(app, dict):
            continue
        for value in app.values():
            if isinstance(value, dict):
                product = (value.get("catalog") or {}).get("product")
                if product and product.get("id"):
                    return product
    return None


def _find_category(warmup: dict) -> dict | None:
    for app in (warmup.get("appsWarmupData") or {}).values():
        if not isinstance(app, dict):
            continue
        for value in app.values():
            if isinstance(value, dict):
                category = (value.get("catalog") or {}).get("category")
                if category and category.get("productsWithMetaData"):
                    return category
    return None


PRODUCT_BY_SLUG_QUERY = """query getProductBySlug($slug: String!) {
  catalog {
    product(slug: $slug) {
      id name sku price discountedPrice formattedPrice comparePrice
      description urlPart productType isVisible isInStock weight
      inventory { quantity status }
      media { url fullUrl altText }
      options { title selections { id description } }
      productItems { id sku price discountedPrice optionsSelections isVisible inventory { quantity status } }
    }
  }
}"""

_token_lock = threading.Lock()
_token_cache: dict[str, str] = {}


def _cached_instance(session: requests.Session) -> str:
    with _token_lock:
        if "instance" not in _token_cache:
            _token_cache["instance"] = get_instance_token(session)
        return _token_cache["instance"]


def _product_by_slug_api(session: requests.Session, slug: str) -> dict | None:
    """Fallback for pages whose server-rendered warmup comes back empty."""
    response = session.post(
        GRAPHQL_URL,
        json={"query": PRODUCT_BY_SLUG_QUERY, "variables": {"slug": slug}},
        headers={"Authorization": _cached_instance(session), "Content-Type": "application/json"},
        timeout=60,
    )
    if response.status_code != 200:
        return None
    return ((response.json().get("data") or {}).get("catalog") or {}).get("product")


def fetch_detail(session: requests.Session, url: str) -> dict:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    record: dict = {"slug": slug, "url": url}
    response = session.get(url, timeout=45)
    if response.status_code != 200:
        record.update(ok=False, error=f"HTTP {response.status_code}")
        return record
    product = _find_product(_warmup(response.text))
    if not product:
        product = _product_by_slug_api(session, slug)
        if product:
            record.update(ok=True, product=product, source="storefront_api")
            return record
        record.update(ok=False, error="NO_PRODUCT_MODEL")
        return record
    record.update(ok=True, product=product)
    return record


def _worker_fetch(url: str, local: threading.local) -> dict:
    session = getattr(local, "session", None)
    if session is None:
        session = make_session()
        local.session = session
    last: dict = {}
    for attempt in range(3):
        time.sleep(REQUEST_DELAY_SECONDS + random.uniform(0, 0.1) + attempt * 2)
        try:
            return fetch_detail(session, url)
        except requests.RequestException as exc:
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            last = {"slug": slug, "url": url, "ok": False, "error": repr(exc)}
    return last


def run_details_stage(urls: list[str], checkpoint_path: Path, *,
                      limit: int | None = None, progress_every: int = 250,
                      log=print) -> dict:
    done: set[str] = set()
    if checkpoint_path.exists():
        with checkpoint_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("ok"):
                    done.add(row["slug"])

    pending = [u for u in urls if u.rstrip("/").rsplit("/", 1)[-1] not in done]
    if limit:
        pending = pending[: max(0, limit - len(done))]
    log(f"details: {len(done)} already fetched, {len(pending)} to fetch")

    local = threading.local()
    write_lock = threading.Lock()
    counts = {"ok": 0, "error": 0}
    started = time.monotonic()

    with checkpoint_path.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(_worker_fetch, url, local): url for url in pending}
            for index, future in enumerate(as_completed(futures), 1):
                url = futures[future]
                try:
                    record = future.result()
                except Exception as exc:
                    slug = url.rstrip("/").rsplit("/", 1)[-1]
                    record = {"slug": slug, "url": url, "ok": False, "error": repr(exc)}
                record["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                counts["ok" if record.get("ok") else "error"] += 1
                with write_lock:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out.flush()
                if index % progress_every == 0:
                    rate = index / max(1e-9, time.monotonic() - started)
                    remaining = (len(pending) - index) / max(rate, 1e-9)
                    log(f"details: {index}/{len(pending)} "
                        f"(ok={counts['ok']} err={counts['error']}, "
                        f"{rate:.1f}/s, ~{remaining / 60:.0f}m left)")
    return counts


GRAPHQL_URL = f"{BASE}/_api/wix-ecommerce-storefront-web/api"
STORES_APP_ID = "1380b703-ce81-ff05-f115-39571d94dfcd"
CATEGORY_QUERY = """query getFilteredProducts($mainCollectionId: String!, $offset: Int, $limit: Int) {
  catalog {
    category(categoryId: $mainCollectionId) {
      numOfProducts
      productsWithMetaData(limit: $limit, offset: $offset, onlyVisible: true) {
        totalCount
        list { id name sku urlPart }
      }
    }
  }
}"""


def get_instance_token(session: requests.Session) -> str:
    tokens = session.get(f"{BASE}/_api/v1/access-tokens", timeout=30).json()
    return tokens["apps"][STORES_APP_ID]["instance"]


def _category_products_api(session: requests.Session, instance: str, category_id: str) -> list[dict]:
    """Page through the storefront API — no cap, unlike the embedded warmup."""
    products: list[dict] = []
    offset, total = 0, None
    while total is None or offset < total:
        response = session.post(
            GRAPHQL_URL,
            json={"query": CATEGORY_QUERY,
                  "variables": {"mainCollectionId": category_id, "offset": offset, "limit": 100}},
            headers={"Authorization": instance, "Content-Type": "application/json"},
            timeout=60,
        )
        response.raise_for_status()
        payload = (((response.json().get("data") or {}).get("catalog") or {})
                   .get("category") or {}).get("productsWithMetaData") or {}
        batch = payload.get("list") or []
        total = payload.get("totalCount") or 0
        products.extend(batch)
        if not batch:
            break
        offset += len(batch)
        time.sleep(REQUEST_DELAY_SECONDS)
    return products


def crawl_category(session: requests.Session, path: str, instance: str) -> dict | None:
    """Full category product list via the storefront API (id from the page)."""
    first = session.get(f"{BASE}{path}", timeout=45)
    category = _find_category(_warmup(first.text))
    if not category:
        return None
    total = category["productsWithMetaData"].get("totalCount") or 0
    product_list = _category_products_api(session, instance, category["id"])
    if len(product_list) < len(category["productsWithMetaData"]["list"]):
        product_list = category["productsWithMetaData"]["list"]
    return {
        "path": path,
        "id": category.get("id"),
        "name": category.get("name") or path,
        "total_count": total,
        "collected": len(product_list),
        "products": [
            {"id": p.get("id"), "sku": p.get("sku") or "", "urlPart": p.get("urlPart") or ""}
            for p in product_list
        ],
    }


def _all_collections(session: requests.Session) -> list[dict]:
    """Union of categoryId filter values across all section pages, plus each
    section page's own collection (filter lists are page-specific)."""
    collections: list[dict] = []
    seen: set[str] = set()

    def add(cid: str | None, name: str | None) -> None:
        if cid and name and cid not in seen:
            seen.add(cid)
            collections.append({"id": cid, "name": name})

    for path in CATEGORY_PATHS:
        try:
            page = session.get(f"{BASE}{path}", timeout=45)
        except requests.RequestException:
            continue
        warmup = _warmup(page.text)
        category = _find_category(warmup)
        if category:
            add(category.get("id"), category.get("name"))
        for app in (warmup.get("appsWarmupData") or {}).values():
            if not isinstance(app, dict):
                continue
            for key, value in app.items():
                if not key.startswith("filters") or not isinstance(value, list):
                    continue
                for filt in value:
                    if filt.get("name") != "categoryId":
                        continue
                    for entry in filt.get("values") or []:
                        add(entry.get("key"), entry.get("value"))
    return collections


def crawl_all_categories(paths: list[str] | None = None, log=print) -> list[dict]:
    session = make_session()
    instance = get_instance_token(session)
    results = []
    for collection in _all_collections(session):
        try:
            products = _category_products_api(session, instance, collection["id"])
            record = {
                "path": "",
                "id": collection["id"],
                "name": collection["name"],
                "total_count": len(products),
                "collected": len(products),
                "products": [
                    {"id": p.get("id"), "sku": p.get("sku") or "", "urlPart": p.get("urlPart") or ""}
                    for p in products
                ],
            }
        except requests.RequestException as exc:
            record = {"id": collection["id"], "name": collection["name"],
                      "error": repr(exc), "products": []}
        log(f"collection {record['name']}: {len(record['products'])} products")
        results.append(record)
    return results


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return html_lib.unescape(_TAG_RE.sub(" ", text or "")).replace("\xa0", " ").strip()


def _clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _original_image(media_item: dict) -> str:
    media_id = media_item.get("url") or media_item.get("id") or ""
    if media_id and "/" not in media_id:
        return f"https://static.wixstatic.com/media/{media_id}"
    return media_item.get("fullUrl") or ""


def _option_lookup(product: dict) -> dict[str, tuple[str, str]]:
    """selection id -> (option title, selection description)."""
    lookup: dict[str, tuple[str, str]] = {}
    for option in product.get("options") or []:
        title = option.get("title") or ""
        for selection in option.get("selections") or []:
            lookup[str(selection.get("id"))] = (title, selection.get("description") or "")
    return lookup


def _looks_like_upc(sku: str) -> bool:
    return sku.isdigit() and len(sku) in (12, 13)


def product_to_rows(record: dict, *, supplier: str, season: str, run_id: str) -> list[dict]:
    product = record["product"]
    breadcrumbs = [c.get("name") for c in product.get("breadcrumbs") or [] if c.get("name")]
    categories = [c.get("name") for c in product.get("categories") or [] if c.get("name")]
    category = breadcrumbs[0] if breadcrumbs else (categories[0] if categories else "")
    subcategory = breadcrumbs[1] if len(breadcrumbs) > 1 else ""

    media = product.get("media") or []
    images = [_original_image(m) for m in media if _original_image(m)]
    primary = images[0] if images else ""
    extras = images[1:10]

    description = _clean_ws(_strip_html(product.get("description") or ""))
    option_lookup = _option_lookup(product)

    price = product.get("price")
    discounted = product.get("discountedPrice")
    compare = product.get("comparePrice") or 0

    base = {
        "supplier": supplier,
        "season": season,
        "product_name": _clean_ws(product.get("name") or ""),
        "category": category,
        "subcategory": subcategory,
        "listed_under": "; ".join(categories),
        "product_type": product.get("productType") or "",
        "description": description,
        "source_price_label": "public_site_price",
        "uom": "",
        "moq": "",
        "box_quantity": "",
        "case_quantity": "",
        "weight_lbs": product.get("weight") if product.get("weight") else "",
        "image_url": primary,
        **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 11)},
        "image_count": len(images),
        "product_url": record.get("url", ""),
        "source_url": SITEMAP_PRODUCTS,
        "extracted_at": record.get("fetched_at", ""),
        "run_id": run_id,
        "product_id": product.get("id") or "",
    }

    items = [i for i in (product.get("productItems") or []) if i.get("isVisible", True)]
    rows: list[dict] = []

    def finish(row: dict, sku: str, row_price, row_discounted, inventory: dict, variant: str) -> dict:
        current = row_discounted if row_discounted else row_price
        row["sku"] = sku or base["product_id"]
        row["upc"] = sku if _looks_like_upc(sku) else ""
        row["variant"] = variant
        row["price"] = current if current is not None else ""
        row["list_price"] = row_price if (row_discounted and row_price and row_discounted < row_price) else (compare or "")
        row["availability"] = (inventory or {}).get("status") or ("in_stock" if product.get("isInStock") else "")
        row["qty_in_stock"] = (inventory or {}).get("quantity", "")
        missing = []
        if row["price"] == "":
            missing.append("price")
        if not row["image_url"]:
            missing.append("image")
        if not row["sku"] or row["sku"] == base["product_id"]:
            missing.append("sku")
        if not description:
            missing.append("description")
        row["needs_review"] = "; ".join(missing)
        return row

    if len(items) > 1:
        for item in items:
            selections = [option_lookup.get(str(s)) for s in item.get("optionsSelections") or []]
            variant = " / ".join(f"{t}: {d}" for t, d in [s for s in selections if s])
            rows.append(finish(dict(base), item.get("sku") or "", item.get("price"),
                               item.get("discountedPrice") or item.get("price"),
                               item.get("inventory") or {}, variant))
    else:
        item = items[0] if items else {}
        inventory = item.get("inventory") or product.get("inventory") or {}
        sku = item.get("sku") or product.get("sku") or ""
        rows.append(finish(dict(base), sku, price, discounted, inventory, ""))
    return rows


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "upc", "product_name", "variant",
    "category", "subcategory", "listed_under", "product_type", "description",
    "price", "list_price", "source_price_label", "uom", "moq",
    "box_quantity", "case_quantity",
    "availability", "qty_in_stock", "weight_lbs",
    "image_url",
    "image_url_2", "image_url_3", "image_url_4", "image_url_5", "image_url_6",
    "image_url_7", "image_url_8", "image_url_9", "image_url_10",
    "image_count", "product_url", "source_url",
    "needs_review", "extracted_at", "run_id", "product_id",
]
