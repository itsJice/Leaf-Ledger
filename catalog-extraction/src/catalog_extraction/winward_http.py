"""Winward Silks (winwardsilks.com) full-catalog extraction over HTTP.

Winward runs on B2B Direct / RepZio — a wholesale portal with a Vue front-end
and `NoPublicBrowsing` (nothing is visible to anonymous visitors). But the
login is a standard ASP.NET anti-forgery form, and once authenticated the Vue
app reads products from a SAME-ORIGIN JSON endpoint:

    GET /categories/0/-/products/?page=N&pageSize=500   (category 0 = whole catalog)

authenticated purely by the session cookie (no RepZio API key). Each product
record is rich: ItemID (SKU), UPC, ItemName, RenderedDescription, Price + full
AllPrices tiers, Dimensions, Weight, OnHandQuantity, ImageURL + additional
images, color (Udf17), and more. So the whole catalog comes from one paged
endpoint — no per-product detail fetch.

Requires an APPROVED Winward dealer account. Credentials come from the
gitignored .env (WINWARD_USERNAME / WINWARD_PASSWORD).
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import time
from pathlib import Path

import requests

BASE = "https://www.winwardsilks.com"
LOGIN_URL = f"{BASE}/account/login"
PRODUCTS_URL = f"{BASE}/categories/0/-/products/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
PAGE_SIZE = 500
REQUEST_DELAY_SECONDS = 0.3
TOKEN_RE = re.compile(
    r'id="login-form".*?name="__RequestVerificationToken"[^>]*value="([^"]+)"', re.S
)
_TAG_RE = re.compile(r"<[^>]+>")


class LoginError(RuntimeError):
    pass


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _get(session: requests.Session, url: str, *, params=None, timeout=60, retries=4):
    """GET with retries — Winward can be slow to first-byte on cold requests."""
    last = None
    for attempt in range(retries):
        try:
            return session.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 + attempt * 3)
    raise last


def login(session: requests.Session) -> dict:
    """Scripted ASP.NET form login. Returns the first page's meta for sanity."""
    username = os.environ.get("WINWARD_USERNAME", "")
    password = os.environ.get("WINWARD_PASSWORD", "")
    if not (username and password):
        raise LoginError("WINWARD_USERNAME / WINWARD_PASSWORD not set in .env")

    page = _get(session, LOGIN_URL, timeout=45)
    token = TOKEN_RE.search(page.text)
    if not token:
        raise LoginError("could not parse login anti-forgery token")
    for attempt in range(4):
        try:
            session.post(
                f"{LOGIN_URL}?ReturnUrl=%2F",
                data={
                    "Username": username,
                    "Password": password,
                    "__RequestVerificationToken": token.group(1),
                    "RememberMe": "false",
                },
                headers={"Referer": page.url},
                timeout=45,
            )
            break
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 + attempt * 3)
    # switch to XHR/JSON headers for the API calls
    session.headers.update({"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
    probe = _get(session, PRODUCTS_URL, params={"page": 1, "pageSize": 1}, timeout=45)
    try:
        meta = probe.json()
    except json.JSONDecodeError:
        raise LoginError("login failed — products endpoint did not return JSON")
    if not meta.get("ShowPricing"):
        # not fatal, but flag it: prices may be hidden for this account
        meta.setdefault("_warning", "ShowPricing is false — prices may be blank")
    return meta


def fetch_all_products(session: requests.Session, checkpoint_path: Path, *,
                       limit: int | None = None, log=print) -> int:
    """Page through the whole catalog, appending raw product JSON to a checkpoint."""
    first = _get(session, PRODUCTS_URL, params={"page": 1, "pageSize": PAGE_SIZE}).json()
    total = first.get("TotalRecords", 0)
    target = min(total, limit) if limit else total
    pages = (target + PAGE_SIZE - 1) // PAGE_SIZE
    log(f"discover: {total} products total, fetching {target} across {pages} page(s) of {PAGE_SIZE}")

    seen: set[str] = set()
    if checkpoint_path.exists():
        with checkpoint_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["ItemID"])
                except (json.JSONDecodeError, KeyError):
                    continue
        log(f"discover: {len(seen)} already checkpointed")

    written = len(seen)
    with checkpoint_path.open("a", encoding="utf-8") as out:
        for page in range(1, pages + 1):
            data = first if page == 1 else _get(
                session, PRODUCTS_URL, params={"page": page, "pageSize": PAGE_SIZE}
            ).json()
            for product in data.get("Products", []):
                item_id = product.get("ItemID")
                if not item_id or item_id in seen:
                    continue
                seen.add(item_id)
                out.write(json.dumps(product, ensure_ascii=False) + "\n")
                written += 1
                if limit and written >= limit:
                    out.flush()
                    log(f"discover: reached limit {limit}")
                    return written
            out.flush()
            log(f"discover: page {page}/{pages} ({written} products)")
            time.sleep(REQUEST_DELAY_SECONDS)
    return written


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def _image(url: str) -> str:
    # image urls arrive like ".../cvas3165-mvgr_lg.jpg?width=" — drop the empty query
    return (url or "").split("?")[0]


def product_to_row(p: dict, *, supplier: str, season: str, run_id: str, fetched_at: str) -> dict:
    prices = p.get("AllPrices") or {}
    primary = _image(p.get("ImageURL", ""))
    extras = [_image(u) for u in (p.get("AdditionalImageList") or []) if _image(u)]
    description = _clean(p.get("RenderedDescription") or p.get("Description") or "")
    price = p.get("Price") or 0

    missing = []
    if not price:
        missing.append("price")
    if not primary:
        missing.append("image")
    if not p.get("ItemID"):
        missing.append("sku")
    if not description:
        missing.append("description")

    return {
        "supplier": supplier,
        "season": season,
        "sku": p.get("ItemID", ""),
        "upc": p.get("UPC") or "",
        "product_name": p.get("ItemName") or "",
        "description": description,
        "category": p.get("ReportCategory") or "",
        "manufacturer_id": p.get("ManufacturerID") or "",
        "price": price if price else "",
        "base_price": prices.get("BasePrice", ""),
        "price_level1": prices.get("Level1", ""),
        "price_level2": prices.get("Level2", ""),
        "price_level3": prices.get("Level3", ""),
        "special_price": p.get("SpecialPrice") or "",
        "source_price_label": "dealer_account_price",
        "uom": p.get("UnitOfMeasure") or "",
        "moq": p.get("OrderMinimumQuantity") if p.get("OrderMinimumQuantity") is not None else "",
        "order_multiple": p.get("OrderMultipleQuantity") if p.get("OrderMultipleQuantity") is not None else "",
        "container_min_qty": p.get("ContainerMinQty") if p.get("ContainerMinQty") is not None else "",
        "availability": p.get("InventoryStatus") or p.get("Udf16") or "",
        "qty_in_stock": p.get("OnHandQuantity") if not p.get("OnHandQuantityIsNull") else "",
        "discontinued": p.get("Discontinued", ""),
        "dimensions_in": p.get("Dimensions") or "",
        "weight_lbs": p.get("Weight") if p.get("Weight") is not None else "",
        "cubes": p.get("Cubes") if p.get("Cubes") is not None else "",
        "color": p.get("Udf17") or "",
        "image_url": primary,
        **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 11)},
        "image_count": (1 if primary else 0) + len(extras),
        "product_url": (BASE + p["ProductURL"]) if p.get("ProductURL") else "",
        "source_url": PRODUCTS_URL,
        "needs_review": "; ".join(missing),
        "extracted_at": fetched_at,
        "run_id": run_id,
    }


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "upc", "product_name", "description",
    "category", "manufacturer_id",
    "price", "base_price", "price_level1", "price_level2", "price_level3",
    "special_price", "source_price_label",
    "uom", "moq", "order_multiple", "container_min_qty",
    "availability", "qty_in_stock", "discontinued",
    "dimensions_in", "weight_lbs", "cubes", "color",
    "image_url",
    "image_url_2", "image_url_3", "image_url_4", "image_url_5", "image_url_6",
    "image_url_7", "image_url_8", "image_url_9", "image_url_10",
    "image_count", "product_url", "source_url",
    "needs_review", "extracted_at", "run_id",
]
