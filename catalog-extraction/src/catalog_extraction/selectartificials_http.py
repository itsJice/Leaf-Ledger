"""Select Artificials (selectartificials.com) full-catalog extraction over HTTP.

Emun B2B commerce platform (AngularJS SPA over a ServiceStack JSON API).
The entire catalog is exposed through an open, unauthenticated JSON endpoint:

    GET /service/QueryProducts.json?Take=250&Skip=N   ->  {offset,total,results[]}

Per product: id, manufacturerNumber, upcCode, short/longDescription, stock
(unitsInStock/availableQty/incomingQty/availableOn), minimumOrderQty,
purchaseIncrement, caseQty, uom, dimensions (height/width/length/weight),
a structured `tags` object (Category/SubCategory/Collection/Color/Group), and
pricing. Public prices are the volume-tier breaks (tier2Qty/tier2Price,
tier3Qty/tier3Price); base list/wholesale/case prices are 0 anonymously and
require a retailer login (optional — see login()).

Take is capped near 1000 by a downstream SQL parameter limit; use 250.

Images: product image URLs are built client-side from an S3 bucket keyed by a
store clientId not exposed anonymously, so the raw `productImages` array
(productId + position) is preserved in raw_data and image_url is flagged for a
later authenticated/browser pass rather than blocking the catalog pull.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

BASE = "https://www.selectartificials.com"
API = f"{BASE}/service/QueryProducts.json"
LOGIN_URL = f"{BASE}/service/Authenticate.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
PAGE = 250
REQUEST_DELAY_SECONDS = 0.6


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.get(BASE, timeout=30)  # seed ServiceStack session cookies
    return session


def login(session: requests.Session) -> bool:
    """Optional retailer login to unlock base list/wholesale prices."""
    username = os.environ.get("SELECT_ARTIFICIALS_USERNAME", "")
    password = os.environ.get("SELECT_ARTIFICIALS_PASSWORD", "")
    if not (username and password):
        return False
    try:
        r = session.post(
            LOGIN_URL,
            json={"provider": "credentials", "UserName": username, "Password": password},
            timeout=30,
        )
        return r.status_code == 200 and "SessionId" in r.text
    except requests.RequestException:
        return False


def fetch_all_products(session: requests.Session, *, limit: int | None = None, log=print) -> list[dict]:
    products: list[dict] = []
    skip = 0
    total = None
    while total is None or skip < total:
        for attempt in range(3):
            try:
                r = session.get(API, params={"Take": PAGE, "Skip": skip}, timeout=60)
                r.raise_for_status()
                payload = r.json()
                break
            except requests.RequestException as exc:
                if attempt == 2:
                    raise
                time.sleep(2 + attempt * 2)
        batch = payload.get("results", [])
        total = payload.get("total", 0)
        if not batch:
            break
        products.extend(batch)
        log(f"discover: {len(products)}/{total}")
        skip += len(batch)
        if limit and len(products) >= limit:
            return products[:limit]
        time.sleep(REQUEST_DELAY_SECONDS)
    return products


def _clean(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _tag(tags: dict, key: str) -> str:
    vals = (tags or {}).get(key) or []
    return "; ".join(str(v) for v in vals) if isinstance(vals, list) else str(vals)


def _num(value):
    return value if isinstance(value, (int, float)) and value not in (0, None) else ""


def product_to_row(p: dict, *, supplier: str, season: str, run_id: str, fetched_at: str) -> dict:
    tags = p.get("tags") or {}
    sku = _clean(p.get("id") or p.get("manufacturerNumber"))
    base_price = _num(p.get("wholesalePrice")) or _num(p.get("listPrice"))
    tier2 = _num(p.get("tier2Price"))
    tier3 = _num(p.get("tier3Price"))

    missing = []
    if base_price == "" and tier2 == "" and tier3 == "":
        missing.append("price (login-gated)")
    elif base_price == "":
        missing.append("base_price (login-gated; tier prices present)")
    missing.append("image (url needs auth/browser pass)")
    desc = _clean(p.get("longDescription") or p.get("shortDescription"))
    if not desc:
        missing.append("description")

    return {
        "supplier": supplier,
        "season": season,
        "sku": sku,
        "upc": _clean(p.get("upcCode")),
        "product_name": _clean(p.get("shortDescription")),
        "category": _tag(tags, "Category") or _clean(p.get("categoryId")),
        "subcategory": _tag(tags, "SubCategory") or _clean(p.get("subCategory")),
        "collection": _tag(tags, "Collection"),
        "group": _tag(tags, "Group"),
        "description": desc,
        "price": base_price,
        "tier2_qty": _num(p.get("tier2Qty")),
        "tier2_price": tier2,
        "tier3_qty": _num(p.get("tier3Qty")),
        "tier3_price": tier3,
        "source_price_label": "base_wholesale" if base_price != "" else ("volume_tier_public" if (tier2 or tier3) else ""),
        "uom": _clean(p.get("uom")),
        "moq": _num(p.get("minimumOrderQty")),
        "purchase_increment": _num(p.get("purchaseIncrement")),
        "case_quantity": _num(p.get("caseQty")),
        "availability": p.get("availableQty") if p.get("availableQty") is not None else "",
        "units_in_stock": p.get("unitsInStock") if p.get("unitsInStock") is not None else "",
        "incoming_qty": p.get("incomingQty") if p.get("incomingQty") is not None else "",
        "available_on": _clean(p.get("availableOn")),
        "color": _tag(tags, "Color"),
        "height_in": _num(p.get("height")),
        "width_in": _num(p.get("width")),
        "length_in": _num(p.get("length")),
        "weight_lbs": _num(p.get("weight")),
        "image_count": len(p.get("productImages") or []),
        "image_url": "",  # reconstructed in a later pass; raw positions kept in raw_data
        "product_url": f"{BASE}/shop/product/{sku}",
        "source_url": API,
        "needs_review": "; ".join(missing),
        "extracted_at": fetched_at,
        "run_id": run_id,
    }


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "upc", "product_name",
    "category", "subcategory", "collection", "group", "description",
    "price", "tier2_qty", "tier2_price", "tier3_qty", "tier3_price", "source_price_label",
    "uom", "moq", "purchase_increment", "case_quantity",
    "availability", "units_in_stock", "incoming_qty", "available_on",
    "color", "height_in", "width_in", "length_in", "weight_lbs",
    "image_count", "image_url", "product_url", "source_url",
    "needs_review", "extracted_at", "run_id",
]
