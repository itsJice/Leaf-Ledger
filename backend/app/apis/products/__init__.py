from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Response
from pydantic import BaseModel
from typing import Any, Optional, List
import asyncpg
import os
import uuid
import json
import requests as http_requests
import databutton as db
from datetime import datetime
from app.auth import AuthorizedUser
from app.apis.user_context import extract_user_id, get_request_user_id

router = APIRouter(prefix="/products", tags=["products"])

# ─── Image proxy ──────────────────────────────────────────────────────────────
# Supplier sites block hotlinking via Referer checks.
# We proxy images through the backend to serve them without that restriction.
@router.get("/image-proxy")
def image_proxy(url: Optional[str] = None, key: Optional[str] = None) -> Response:
    """Serve a product image — either from Databutton storage (key=) or by proxying an external URL (url=)."""
    # ── Serve from internal storage ────────────────────────────────────────────
    if key:
        try:
            data = db.storage.binary.get(key)
            if not data:
                raise HTTPException(status_code=404, detail="Image not in storage")
            # Sniff content-type from magic bytes
            ct = "image/jpeg"
            if data[:4] == b"\x89PNG":
                ct = "image/png"
            elif data[:4] == b"RIFF" or data[:4] == b"WEBP":
                ct = "image/webp"
            elif data[:3] == b"GIF":
                ct = "image/gif"
            return Response(
                content=data,
                media_type=ct,
                headers={"Cache-Control": "public, max-age=604800"},  # 7 days
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Storage error: {e}")

    # ── Proxy external URL ────────────────────────────────────────────────────
    if not url or not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Provide url= or key= parameter")
    try:
        domain = "/".join(url.split("/")[:3]) + "/"
        resp = http_requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                "Referer": domain,
            },
        )
        content_type = resp.headers.get("content-type", "image/jpeg")
        return Response(
            content=resp.content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")

DATABASE_URL = os.environ.get("DATABASE_URL")

async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

# ---------- Models ----------

class ProductCreate(BaseModel):
    supplier_id: int
    name: str
    description: Optional[str] = None
    category: str  # plant, container, filler, accent, other
    unit: str      # stem, pot, flat, bunch, each
    current_price: Optional[float] = None
    photo_url: Optional[str] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    current_price: Optional[float] = None
    photo_url: Optional[str] = None
    supplier_id: Optional[int] = None

class ProductPriceUpdate(BaseModel):
    current_price: float

class ProductOut(BaseModel):
    id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    supplier_sku: Optional[str] = None
    name: str
    description: Optional[str]
    category: str
    unit: str
    current_price: Optional[float]
    price_updated_at: Optional[datetime]
    photo_url: Optional[str]
    moq: Optional[int] = None
    box_qty: Optional[int] = None
    case_qty: Optional[int] = None
    availability: Optional[str] = None
    availability_note: Optional[str] = None
    upc: Optional[str] = None
    image_urls: Optional[List[str]] = None
    height_in: Optional[float] = None
    width_in: Optional[float] = None
    diameter_in: Optional[float] = None
    length_in: Optional[float] = None
    weight_lb: Optional[float] = None
    material: Optional[str] = None
    finish: Optional[str] = None
    color: Optional[str] = None
    style: Optional[str] = None
    country_of_origin: Optional[str] = None
    raw_data: Optional[dict] = None
    is_active: bool
    is_favorited: bool = False
    created_at: datetime
    updated_at: datetime

class ProductListPage(BaseModel):
    items: List[ProductOut]
    total: int
    limit: int
    offset: int

class FilterOption(BaseModel):
    value: str
    count: int
    id: Optional[int] = None

class ProductFilterMetadata(BaseModel):
    generated_at: str
    categories: List[FilterOption]
    suppliers: List[FilterOption]
    product_types: List[FilterOption] = []
    countries: List[FilterOption]
    colors: List[FilterOption]
    availability: List[FilterOption]
    finishes: List[FilterOption] = []
    sizes: List[FilterOption] = []

# ---------- Endpoints ----------

def _normalize_product_row(row) -> dict:
    product = dict(row)
    raw = product.get("raw_data") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
        product["raw_data"] = raw
    # Surface the rich display category (constrained column stays a safe slug)
    if raw.get("category_group"):
        product["category"] = raw["category_group"]
    product["upc"] = product.get("upc") or raw.get("UPC")
    if product.get("box_qty") is None:
        try:
            product["box_qty"] = int(str(raw.get("BoxQty", "")).strip())
        except (TypeError, ValueError):
            product["box_qty"] = None
    return product

def _csv_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _availability_bucket_sql(col: str) -> str:
    """Bucket a raw availability value (numeric qty or status text) into
    'In stock' / 'Out of stock'. Same expression used for filtering + options."""
    return f"""CASE
        WHEN {col} ~ '^[0-9]+(\\.[0-9]+)?$'
            THEN CASE WHEN {col}::numeric > 0 THEN 'In stock' ELSE 'Out of stock' END
        WHEN lower(coalesce({col}, '')) IN ('in_stock', 'available', 'in stock', 'today', 'yes')
            THEN 'In stock'
        WHEN lower(coalesce({col}, '')) IN ('out_of_stock', 'sold out', 'unavailable', 'no')
            THEN 'Out of stock'
        ELSE NULL
    END"""


# style column carries the supplier "product type"
PRODUCT_TYPE_SQL = "COALESCE(NULLIF(p.style, ''), p.raw_data->>'product_type')"


def _product_filters(
    user_id: Optional[str],
    supplier_id: Optional[int],
    supplier_ids: Optional[str],
    category: Optional[str],
    favorites_only: Optional[bool],
    search: Optional[str],
    categories: Optional[str] = None,
    product_types: Optional[str] = None,
    colors: Optional[str] = None,
    availability: Optional[str] = None,
    finishes: Optional[str] = None,
    sizes: Optional[str] = None,
    size_min: Optional[float] = None,
    size_max: Optional[float] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
) -> tuple[list[str], list, int]:
    conditions = ["p.is_active = TRUE"]
    effective_user_id = user_id or "__no_user__"
    params: list = [effective_user_id]
    idx = 2
    if supplier_id:
        conditions.append(f"p.supplier_id = ${idx}")
        params.append(supplier_id)
        idx += 1
    elif supplier_ids:
        parsed_supplier_ids = [
            int(value)
            for value in str(supplier_ids).split(",")
            if value.strip().isdigit()
        ]
        if parsed_supplier_ids:
            conditions.append(f"p.supplier_id = ANY(${idx}::int[])")
            params.append(parsed_supplier_ids)
            idx += 1
    # categories: match on the rich category_group (falls back to the column)
    category_list = _csv_list(categories) or ([category] if category else [])
    if category_list:
        conditions.append(f"COALESCE(p.raw_data->>'category_group', p.category) = ANY(${idx}::text[])")
        params.append(category_list)
        idx += 1
    product_type_list = _csv_list(product_types)
    if product_type_list:
        conditions.append(f"p.raw_data->>'type_family' = ANY(${idx}::text[])")
        params.append(product_type_list)
        idx += 1
    color_list = _csv_list(colors)
    if color_list:
        # match if the product's color_families overlaps any selected family
        conditions.append(f"p.raw_data->'color_families' ?| ${idx}::text[]")
        params.append(color_list)
        idx += 1
    # normalized facets (Phase 3): finish + size range from the normalization layer.
    # Reads raw_data->'normalized' (works today); swaps to indexed norm_* columns
    # once migrations/001_normalized_columns.sql is run by the DB owner.
    finish_list = _csv_list(finishes)
    if finish_list:
        conditions.append(f"p.raw_data->'normalized'->>'finish' = ANY(${idx}::text[])")
        params.append(finish_list)
        idx += 1
    # discrete size buckets (match filter-metadata's rounded 0.5" buckets)
    size_list = _csv_list(sizes)
    if size_list:
        conditions.append(
            "trim(trailing '.' from trim(trailing '0' from "
            f"(round((NULLIF(p.raw_data->'normalized'->>'size_in','')::numeric) * 2) / 2)::text)) "
            f"= ANY(${idx}::text[])"
        )
        params.append(size_list)
        idx += 1
    if size_min is not None:
        conditions.append(f"NULLIF(p.raw_data->'normalized'->>'size_in','')::numeric >= ${idx}")
        params.append(size_min)
        idx += 1
    if size_max is not None:
        conditions.append(f"NULLIF(p.raw_data->'normalized'->>'size_in','')::numeric <= ${idx}")
        params.append(size_max)
        idx += 1
    if price_min is not None:
        conditions.append(f"p.current_price >= ${idx}")
        params.append(price_min)
        idx += 1
    if price_max is not None:
        conditions.append(f"p.current_price <= ${idx}")
        params.append(price_max)
        idx += 1
    availability_list = _csv_list(availability)
    if availability_list:
        conditions.append(f"({_availability_bucket_sql('p.availability')}) = ANY(${idx}::text[])")
        params.append(availability_list)
        idx += 1
    if favorites_only and user_id:
        conditions.append("EXISTS (SELECT 1 FROM product_favorites pf WHERE pf.product_id = p.id AND pf.user_id = $1)")
    if search:
        conditions.append(
            f"""(
                p.name ILIKE ${idx}
                OR p.description ILIKE ${idx}
                OR p.supplier_sku ILIKE ${idx}
                OR p.raw_data::text ILIKE ${idx}
            )"""
        )
        params.append(f"%{search}%")
        idx += 1
    return conditions, params, idx

def _others_last(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep 'Other' at the bottom of a grouped option list."""
    return [o for o in options if o.get("value") != "Other"] + [o for o in options if o.get("value") == "Other"]


def _option_rows(rows) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        value = data.get("value")
        if value is None or not str(value).strip():
            continue
        option = {"value": str(value).strip(), "count": int(data.get("count") or 0)}
        if data.get("id") is not None:
            option["id"] = data["id"]
        options.append(option)
    return options

def _availability_bucket(value: Any) -> Optional[str]:
    text = str(value or "").lower()
    if not text:
        return None
    if "within 1" in text or "1-4 month" in text or "1 4 month" in text:
        return "Within 1-4 months"
    if "available today" in text or "in stock" in text or "instock" in text or text.strip() in {"in_stock", "today", "available"}:
        return "Available today"
    if "sold out" in text or "out of stock" in text or "unavailable" in text or text.strip() == "out_of_stock":
        return "Sold out / unavailable"
    if "eta" in text or "expected" in text or "future" in text:
        return "Future ETA"
    if "over 4" in text:
        return "Over 4 months"
    return None

async def _build_product_filter_metadata(conn) -> dict[str, Any]:
    category_rows = await conn.fetch("""
        SELECT COALESCE(NULLIF(raw_data->>'category_group', ''), NULLIF(category, ''), 'Home Décor') AS value,
               COUNT(*)::int AS count
        FROM products
        WHERE is_active = TRUE
        GROUP BY 1
        ORDER BY count DESC, value ASC
    """)
    supplier_rows = await conn.fetch("""
        SELECT s.id, s.name AS value, COUNT(p.id)::int AS count
        FROM suppliers s
        LEFT JOIN products p ON p.supplier_id = s.id AND p.is_active = TRUE
        GROUP BY s.id, s.name
        ORDER BY s.name ASC
    """)
    country_rows = await conn.fetch("""
        SELECT COALESCE(
            NULLIF(country_of_origin, ''),
            NULLIF(raw_data->>'Country of Origin', ''),
            NULLIF(raw_data->>'Country', '')
        ) AS value,
        COUNT(*)::int AS count
        FROM products
        WHERE is_active = TRUE
        GROUP BY 1
        ORDER BY count DESC, value ASC
    """)
    color_rows = await conn.fetch("""
        SELECT fam AS value, COUNT(*)::int AS count
        FROM products p,
             LATERAL jsonb_array_elements_text(p.raw_data->'color_families') AS fam
        WHERE p.is_active = TRUE AND p.raw_data ? 'color_families'
        GROUP BY fam
        ORDER BY count DESC, value ASC
    """)
    product_type_rows = await conn.fetch("""
        SELECT raw_data->>'type_family' AS value, COUNT(*)::int AS count
        FROM products
        WHERE is_active = TRUE AND raw_data->>'type_family' IS NOT NULL
        GROUP BY 1
        ORDER BY count DESC, value ASC
    """)
    availability_rows = await conn.fetch(f"""
        SELECT ({_availability_bucket_sql('availability')}) AS value, COUNT(*)::int AS count
        FROM products
        WHERE is_active = TRUE
        GROUP BY 1
    """)
    availability_counts = {row["value"]: row["count"] for row in availability_rows if row["value"]}
    availability_order = ["In stock", "Out of stock"]
    # Phase 3 normalized facets: finish + size (from the normalization layer)
    finish_rows = await conn.fetch("""
        SELECT raw_data->'normalized'->>'finish' AS value, COUNT(*)::int AS count
        FROM products
        WHERE is_active = TRUE AND NULLIF(raw_data->'normalized'->>'finish','') IS NOT NULL
        GROUP BY 1 ORDER BY count DESC, value ASC
    """)
    size_rows = await conn.fetch("""
        SELECT trim(trailing '.' from trim(trailing '0' from value::text)) AS value,
               COUNT(*)::int AS count
        FROM (
            SELECT round((NULLIF(raw_data->'normalized'->>'size_in','')::numeric) * 2) / 2 AS value
            FROM products
            WHERE is_active = TRUE
              AND NULLIF(raw_data->'normalized'->>'size_in','') IS NOT NULL
              AND (raw_data->'normalized'->>'size_in')::numeric BETWEEN 0.5 AND 40
        ) t
        GROUP BY value ORDER BY value ASC
    """)
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "categories": _option_rows(category_rows),
        "suppliers": _option_rows(supplier_rows),
        "product_types": _others_last(_option_rows(product_type_rows)),
        "countries": _option_rows(country_rows),
        "colors": _others_last(_option_rows(color_rows)),
        "availability": [
            {"value": label, "count": availability_counts[label]}
            for label in availability_order
            if availability_counts.get(label)
        ],
        "finishes": _option_rows(finish_rows),
        "sizes": _option_rows(size_rows),
    }

@router.get("/filter-metadata", response_model=ProductFilterMetadata)
async def get_product_filter_metadata():
    conn = await get_conn()
    try:
        return await _build_product_filter_metadata(conn)
    finally:
        await conn.close()

@router.get("/list", response_model=List[ProductOut])
async def list_products(
    request: Request,
    supplier_id: Optional[int] = None,
    supplier_ids: Optional[str] = None,
    category: Optional[str] = None,
    categories: Optional[str] = None,
    product_types: Optional[str] = None,
    colors: Optional[str] = None,
    availability: Optional[str] = None,
    finishes: Optional[str] = None,
    sizes: Optional[str] = None,
    size_min: Optional[float] = None,
    size_max: Optional[float] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    favorites_only: Optional[bool] = None,
    search: Optional[str] = None,
):
    # Resolve user ID from auth token if present, but don't require it
    user_id: Optional[str] = extract_user_id(request)
    if favorites_only and not user_id:
        return []

    conn = await get_conn()
    try:
        conditions, params, _ = _product_filters(
            user_id, supplier_id, supplier_ids, category, favorites_only, search,
            categories=categories, product_types=product_types, colors=colors, availability=availability,
            finishes=finishes, sizes=sizes, size_min=size_min, size_max=size_max,
            price_min=price_min, price_max=price_max,
        )
        where = " AND ".join(conditions)
        rows = await conn.fetch(f"""
            SELECT p.*, s.name as supplier_name,
                   EXISTS (SELECT 1 FROM product_favorites pf WHERE pf.product_id = p.id AND pf.user_id = $1) as is_favorited
            FROM products p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE {where}
            ORDER BY is_favorited DESC, p.name ASC
        """, *params)
        return [_normalize_product_row(row) for row in rows]
    finally:
        await conn.close()

@router.get("/page", response_model=ProductListPage)
async def page_products(
    request: Request,
    supplier_id: Optional[int] = None,
    supplier_ids: Optional[str] = None,
    category: Optional[str] = None,
    categories: Optional[str] = None,
    product_types: Optional[str] = None,
    colors: Optional[str] = None,
    availability: Optional[str] = None,
    finishes: Optional[str] = None,
    sizes: Optional[str] = None,
    size_min: Optional[float] = None,
    size_max: Optional[float] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    favorites_only: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = 96,
    offset: int = 0,
):
    user_id: Optional[str] = extract_user_id(request)
    if favorites_only and not user_id:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    safe_limit = max(1, min(limit, 2000))
    safe_offset = max(0, offset)
    conn = await get_conn()
    try:
        conditions, params, idx = _product_filters(
            user_id, supplier_id, supplier_ids, category, favorites_only, search,
            categories=categories, product_types=product_types, colors=colors, availability=availability,
            finishes=finishes, sizes=sizes, size_min=size_min, size_max=size_max,
            price_min=price_min, price_max=price_max,
        )
        where = " AND ".join(conditions)
        total = await conn.fetchval(f"""
            SELECT COUNT(*)
            FROM products p
            WHERE {where}
              AND ($1::text IS NULL OR TRUE)
        """, *params)
        page_params = [*params, safe_limit, safe_offset]
        rows = await conn.fetch(f"""
            SELECT p.*, s.name as supplier_name,
                   EXISTS (SELECT 1 FROM product_favorites pf WHERE pf.product_id = p.id AND pf.user_id = $1) as is_favorited
            FROM products p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE {where}
            ORDER BY is_favorited DESC, p.name ASC
            LIMIT ${idx} OFFSET ${idx + 1}
        """, *page_params)
        return {
            "items": [_normalize_product_row(row) for row in rows],
            "total": int(total or 0),
            "limit": safe_limit,
            "offset": safe_offset,
        }
    finally:
        await conn.close()

# ─── Fast in-memory catalog search ────────────────────────────────────────────
# Filtering the raw_data JSONB in SQL scans 88k rows per request (~2-8s). Since
# the app DB role can't create indexes, we instead load a lightweight index of
# the catalog into memory ONCE (cached with a TTL) and filter it in Python —
# instant after the first load. Same pattern as the ornament matcher above.
_SEARCH_CACHE: dict = {"ts": 0.0, "rows": None}
_SEARCH_TTL = 3600  # 1 hour — catalog is static between imports


def _avail_bucket_py(v) -> Optional[str]:
    t = str(v or "").strip().lower()
    if not t:
        return None
    if t.replace(".", "", 1).isdigit():
        return "In stock" if float(t) > 0 else "Out of stock"
    if t in ("in_stock", "available", "in stock", "today", "yes"):
        return "In stock"
    if t in ("out_of_stock", "sold out", "unavailable", "no"):
        return "Out of stock"
    return None


async def _load_search_index(conn):
    now = _time.time()
    cached = _SEARCH_CACHE.get("rows")
    if cached is not None and (now - _SEARCH_CACHE["ts"]) < _SEARCH_TTL:
        return cached
    # Pull the full record once; the raw_data JSON text drives full-breadth
    # keyword search (parity with the old search over name/desc/sku/raw_data).
    rows = await conn.fetch(f"""
        SELECT p.id, p.name, s.name AS supplier_name, p.supplier_id, p.supplier_sku,
               p.current_price, p.image_urls, p.availability, p.description,
               {PRODUCT_TYPE_SQL} AS product_type,
               p.raw_data
        FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id
        WHERE p.is_active = TRUE
    """)
    idx = []
    for r in rows:
        raw_text = r["raw_data"]  # asyncpg returns jsonb as its JSON text
        if not isinstance(raw_text, str):
            raw_text = json.dumps(raw_text) if raw_text else ""
        try:
            raw = json.loads(raw_text) if raw_text else {}
        except json.JSONDecodeError:
            raw = {}
        norm = raw.get("normalized") or {}
        cf = [c for c in (raw.get("color_families") or []) if isinstance(c, str)]
        imgs = r["image_urls"] or []
        image = imgs[0] if isinstance(imgs, (list, tuple)) and imgs else None
        size = norm.get("size_in")
        try: size = float(size) if size is not None else None
        except (TypeError, ValueError): size = None
        color, finish = norm.get("color"), norm.get("finish")
        # full-breadth keyword blob: name + sku + description + all raw fields
        blob = " ".join(filter(None, [r["name"], r["supplier_sku"], r["description"],
                                      r["supplier_name"], raw_text])).lower()
        idx.append({
            "id": r["id"], "name": r["name"], "supplier_name": r["supplier_name"],
            "supplier_id": r["supplier_id"], "supplier_sku": r["supplier_sku"],
            "price": float(r["current_price"]) if r["current_price"] is not None else None,
            "image": image, "class": norm.get("class"), "color": color, "finish": finish,
            "size": size, "size_bucket": (f"{round(size * 2) / 2:g}" if size is not None else None),
            "product_type": r["product_type"], "color_families": cf,
            "category": raw.get("category_group"),
            "avail": _avail_bucket_py(r["availability"]),
            "blob": blob,
        })
    _SEARCH_CACHE.update(ts=now, rows=idx)
    return idx


@router.get("/search")
async def search_products(
    colors: Optional[str] = None,
    categories: Optional[str] = None,
    sizes: Optional[str] = None,
    finishes: Optional[str] = None,
    product_types: Optional[str] = None,
    supplier_ids: Optional[str] = None,
    availability: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    search: Optional[str] = None,
    limit: int = 48,
    offset: int = 0,
):
    """Fast faceted search served from the in-memory catalog index."""
    # Only touch the database when the cache is cold — a warm request opens no
    # connection at all, so it isn't paying the ~1s Neon handshake to Europe.
    cached = _SEARCH_CACHE.get("rows")
    if cached is not None and (_time.time() - _SEARCH_CACHE["ts"]) < _SEARCH_TTL:
        idx = cached
    else:
        conn = await get_conn()
        try:
            idx = await _load_search_index(conn)
        finally:
            await conn.close()

    col = set(_csv_list(colors)); sz = set(_csv_list(sizes)); fin = set(_csv_list(finishes))
    pt = set(_csv_list(product_types)); avail = set(_csv_list(availability))
    cat = set(_csv_list(categories))
    sup = {int(x) for x in _csv_list(supplier_ids) if x.isdigit()}
    terms = [w for w in (search or "").lower().split() if w]

    out = []
    for it in idx:
        if col and not (col & set(it["color_families"])): continue
        if cat and it["category"] not in cat: continue
        if fin and it["finish"] not in fin: continue
        if sz and it["size_bucket"] not in sz: continue
        if pt and it["product_type"] not in pt: continue
        if avail and it["avail"] not in avail: continue
        if sup and it["supplier_id"] not in sup: continue
        if price_min is not None and (it["price"] is None or it["price"] < price_min): continue
        if price_max is not None and (it["price"] is None or it["price"] > price_max): continue
        if terms and not all(t in it["blob"] for t in terms): continue
        out.append(it)

    out.sort(key=lambda x: (x["name"] or "").lower())
    total = len(out)
    page = out[max(0, offset): max(0, offset) + max(1, min(limit, 500))]
    items = [{
        "id": it["id"], "name": it["name"], "supplier_name": it["supplier_name"],
        "supplier_sku": it["supplier_sku"], "current_price": it["price"],
        "image_urls": [it["image"]] if it["image"] else [],
        "raw_data": {"normalized": {"color": it["color"], "finish": it["finish"],
                                    "size_in": it["size"], "class": it["class"]}},
    } for it in page]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/detail/{product_id}", response_model=ProductOut)
async def get_product_detail(request: Request, product_id: int):
    """Full product record for the detail modal — one row, fetched on demand so
    the fast /search index can stay slim."""
    user_id: Optional[str] = extract_user_id(request)
    conn = await get_conn()
    try:
        row = await conn.fetchrow("""
            SELECT p.*, s.name as supplier_name,
                   EXISTS (SELECT 1 FROM product_favorites pf WHERE pf.product_id = p.id AND pf.user_id = $2) as is_favorited
            FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.id = $1
        """, product_id, user_id or "__no_user__")
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
        return _normalize_product_row(row)
    finally:
        await conn.close()


@router.get("/by-ids", response_model=List[ProductOut])
async def get_products_by_ids(request: Request, ids: Optional[str] = None):
    """Full product records for a set of ids — powers the Favorites view so a
    product favorited anywhere (Catalog Search, Library) can be shown."""
    user_id: Optional[str] = extract_user_id(request)
    id_list = [int(x) for x in _csv_list(ids) if x.lstrip("-").isdigit()]
    if not id_list:
        return []
    conn = await get_conn()
    try:
        rows = await conn.fetch("""
            SELECT p.*, s.name as supplier_name,
                   EXISTS (SELECT 1 FROM product_favorites pf WHERE pf.product_id = p.id AND pf.user_id = $2) as is_favorited
            FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.id = ANY($1::int[])
        """, id_list, user_id or "__no_user__")
        return [_normalize_product_row(row) for row in rows]
    finally:
        await conn.close()


@router.post("/create", response_model=ProductOut)
async def create_product(body: ProductCreate, user: AuthorizedUser):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("""
            INSERT INTO products (supplier_id, name, description, category, unit, current_price, photo_url, price_updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, CASE WHEN $6 IS NOT NULL THEN NOW() ELSE NULL END)
            RETURNING *
        """, body.supplier_id, body.name, body.description, body.category, body.unit, body.current_price, body.photo_url)
        supplier = await conn.fetchrow("SELECT name FROM suppliers WHERE id = $1", body.supplier_id)
        result = dict(row)
        result["supplier_name"] = supplier["name"] if supplier else None
        result["is_favorited"] = False
        return result
    finally:
        await conn.close()

@router.put("/update/{product_id}", response_model=ProductOut)
async def update_product(product_id: int, body: ProductUpdate, user: AuthorizedUser):
    conn = await get_conn()
    try:
        existing = await conn.fetchrow("SELECT * FROM products WHERE id = $1", product_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Product not found")
        price_ts = "price_updated_at"
        price_val = body.current_price if body.current_price is not None else existing["current_price"]
        updated = await conn.fetchrow("""
            UPDATE products SET
                name = COALESCE($1, name),
                description = COALESCE($2, description),
                category = COALESCE($3, category),
                unit = COALESCE($4, unit),
                current_price = COALESCE($5, current_price),
                photo_url = COALESCE($6, photo_url),
                supplier_id = COALESCE($7, supplier_id),
                price_updated_at = CASE WHEN $5 IS NOT NULL THEN NOW() ELSE price_updated_at END,
                updated_at = NOW()
            WHERE id = $8
            RETURNING *
        """, body.name, body.description, body.category, body.unit, body.current_price, body.photo_url, body.supplier_id, product_id)
        supplier = await conn.fetchrow("SELECT name FROM suppliers WHERE id = $1", updated["supplier_id"])
        fav = await conn.fetchrow("SELECT id FROM product_favorites WHERE product_id = $1 AND user_id = $2", product_id, user.sub)
        result = dict(updated)
        result["supplier_name"] = supplier["name"] if supplier else None
        result["is_favorited"] = fav is not None
        return result
    finally:
        await conn.close()

@router.delete("/delete/{product_id}")
async def delete_product(product_id: int, user: AuthorizedUser):
    conn = await get_conn()
    try:
        await conn.execute("UPDATE products SET is_active = FALSE WHERE id = $1", product_id)
        return {"ok": True}
    finally:
        await conn.close()

@router.post("/upload-photo/{product_id}")
async def upload_product_photo(product_id: int, file: UploadFile = File(...)):
    contents = await file.read()
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    key = f"product-photos/product-{product_id}-{uuid.uuid4().hex[:8]}.{ext}"
    db.storage.binary.put(key, contents)
    # Build public URL
    photo_url = f"/api/products/photo/{key.replace('/', '_')}"
    conn = await get_conn()
    try:
        await conn.execute("UPDATE products SET photo_url = $1, updated_at = NOW() WHERE id = $2", photo_url, product_id)
        return {"photo_url": photo_url, "key": key}
    finally:
        await conn.close()

@router.post("/upload-photo-new")
async def upload_product_photo_new(file: UploadFile = File(...)):
    """Upload a photo before product is created (returns temp URL)"""
    contents = await file.read()
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    key = f"product-photos/temp-{uuid.uuid4().hex}.{ext}"
    db.storage.binary.put(key, contents)
    return {"photo_url": f"https://static.riff.new/public/huge-complex-baritone-zbyo/{key}", "key": key}

@router.post("/favorite/{product_id}")
async def toggle_favorite(product_id: int, request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        existing = await conn.fetchrow(
            "SELECT id FROM product_favorites WHERE product_id = $1 AND user_id = $2",
            product_id, user_id
        )
        if existing:
            await conn.execute("DELETE FROM product_favorites WHERE product_id = $1 AND user_id = $2", product_id, user_id)
            return {"favorited": False}
        else:
            await conn.execute("INSERT INTO product_favorites (product_id, user_id) VALUES ($1, $2)", product_id, user_id)
            return {"favorited": True}
    finally:
        await conn.close()

@router.post("/sync-price/{product_id}", response_model=ProductOut)
async def sync_prices2(product_id: int, body: ProductPriceUpdate):
    """Manually update a product's price and record the change in price history."""
    conn = await get_conn()
    try:
        existing = await conn.fetchrow(
            "SELECT * FROM products WHERE id = $1 AND is_active = TRUE", product_id
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Product not found")

        old_price = float(existing["current_price"]) if existing["current_price"] is not None else None
        new_price = body.current_price

        updated = await conn.fetchrow(
            """UPDATE products SET current_price=$1, price_updated_at=NOW(), updated_at=NOW()
               WHERE id=$2 RETURNING *""",
            new_price, product_id
        )

        # Log to history if price changed
        if old_price != new_price:
            await conn.execute(
                """INSERT INTO product_price_history (product_id, old_price, new_price, source)
                   VALUES ($1, $2, $3, 'manual')""",
                product_id, old_price, new_price
            )

        supplier = await conn.fetchrow("SELECT name FROM suppliers WHERE id=$1", updated["supplier_id"])
        fav = await conn.fetchrow(
            "SELECT id FROM product_favorites WHERE product_id=$1", product_id
        )
        result = dict(updated)
        result["supplier_name"] = supplier["name"] if supplier else None
        result["is_favorited"] = fav is not None
        return result
    finally:
        await conn.close()


@router.get("/stats")
async def get_product_stats(request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        total_products = await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_active = TRUE")
        total_suppliers = await conn.fetchval("SELECT COUNT(*) FROM suppliers")
        total_favorites = await conn.fetchval("SELECT COUNT(*) FROM product_favorites WHERE user_id = $1", user_id)
        total_arrangements = await conn.fetchval("SELECT COUNT(*) FROM arrangements WHERE created_by = $1", user_id)
        return {
            "total_products": total_products,
            "total_suppliers": total_suppliers,
            "total_favorites": total_favorites,
            "total_arrangements": total_arrangements,
        }
    finally:
        await conn.close()


# ─── Ornament catalog matcher ───────────────────────────────────────────────
# Turns an Ornament-Calculator recipe (sizes + quantities, optional color) into
# REAL orderable products across the whole catalog — any supplier, and any
# future supplier we upload — since it matches by size/color instead of relying
# on Vickerman-style composable SKUs (which only Vickerman has). Sizes are read
# from dimension columns or parsed from the product name (mm/cm converted to in).
import time as _time
import re as _re

_BALL_CACHE: dict = {"ts": 0.0, "rows": None}
_BALL_TTL = 600  # seconds; short so freshly-uploaded catalogs appear
_SIZE_RE = _re.compile(r'(\d+(?:\.\d+)?)\s*(mm|cm|"|inch\b|inches\b|in\b)', _re.I)
# names that contain "ball" but are not round ball ornaments
_BALL_EXCLUDE = ("spray", "garland", "lamp", "wreath", "spike", "pick",
                 "boxwood", "topiary", "stem", "bush", "tree", "candle")


def _parse_size_in(name, diameter_in, width_in, height_in):
    for v in (diameter_in, width_in, height_in):
        try:
            if v is not None and float(v) > 0:
                return round(float(v), 2)
        except (TypeError, ValueError):
            pass
    if name:
        m = _SIZE_RE.search(name)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if unit == "mm":
                return round(val / 25.4, 2)
            if unit == "cm":
                return round(val / 2.54, 2)
            return round(val, 2)
    return None


async def _load_ball_index(conn):
    now = _time.time()
    cached = _BALL_CACHE.get("rows")
    if cached is not None and (now - _BALL_CACHE["ts"]) < _BALL_TTL:
        return cached
    exclude_sql = " ".join(f"AND p.name NOT ILIKE '%{w}%'" for w in _BALL_EXCLUDE)
    # Fast name/type filter in WHERE (indexed-friendly text scan); the normalized
    # profile (learned SKU grammar + parsing) is read only for matched rows, to
    # enrich color/finish/size. Filtering on the JSONB class would force a slow
    # full-catalog scan (no index available on the app DB role).
    rows = await conn.fetch(f"""
        SELECT p.id, s.name AS supplier, p.name, p.supplier_sku, p.color, p.finish,
               p.current_price, p.diameter_in, p.width_in, p.height_in,
               p.image_urls, p.case_qty, p.uom, {PRODUCT_TYPE_SQL} AS product_type,
               p.raw_data->'normalized' AS norm
        FROM products p JOIN suppliers s ON s.id = p.supplier_id
        WHERE p.is_active = TRUE
          AND (p.name ILIKE '%ball%' OR {PRODUCT_TYPE_SQL} ILIKE '%ball ornament%')
          {exclude_sql}
    """)
    index = []
    for r in rows:
        norm = r["norm"]
        if isinstance(norm, str):
            try:
                norm = json.loads(norm)
            except json.JSONDecodeError:
                norm = None
        norm = norm or {}
        # size: prefer normalized (may derive from SKU/columns), else live parse
        size = norm.get("size_in")
        if size is None:
            size = _parse_size_in(r["name"], r["diameter_in"], r["width_in"], r["height_in"])
        try:
            size = float(size) if size is not None else None
        except (TypeError, ValueError):
            size = None
        if size is None or size <= 0 or size > 40:
            continue
        imgs = r["image_urls"] or []
        image = imgs[0] if isinstance(imgs, (list, tuple)) and imgs else None
        # canonical color/finish fold in the learned SKU grammar — recover
        # attributes the product name never stated.
        norm_color = norm.get("color") or r["color"]
        norm_finish = norm.get("finish") or r["finish"]
        index.append({
            "id": r["id"],
            "supplier": r["supplier"],
            "name": r["name"],
            "sku": r["supplier_sku"],
            "color": norm_color,
            "finish": norm_finish,
            "price": float(r["current_price"]) if r["current_price"] is not None else None,
            "size": size,
            "image": image,
            "case_qty": r["case_qty"],
            "canonical_key": norm.get("canonical_key"),
            # search text now includes decoded color+finish, so SKU-only colors match
            "search": " ".join(filter(None, [
                r["name"], r["color"], norm_color, norm_finish,
            ])).lower(),
        })
    _BALL_CACHE.update(ts=now, rows=index)
    return index


class OrnamentMatchLine(BaseModel):
    size: float
    quantity: Optional[int] = None
    color: Optional[str] = None
    finish: Optional[str] = None


class OrnamentMatchRequest(BaseModel):
    lines: List[OrnamentMatchLine]
    suppliers: Optional[List[str]] = None  # optional supplier-name allowlist
    per_line: int = 6                       # max matches returned per line


@router.post("/ornament-match")
async def ornament_match(body: OrnamentMatchRequest):
    """For each recipe line (size + optional color), return real ball-ornament
    products from the catalog, ranked by size closeness then color match."""
    conn = await get_conn()
    try:
        index = await _load_ball_index(conn)
    finally:
        await conn.close()

    supplier_allow = set(s.lower() for s in body.suppliers) if body.suppliers else None
    results = []
    for line in body.lines:
        want_size = float(line.size)
        # tolerance scales with size; small balls need tighter absolute tolerance
        tol = max(0.35, want_size * 0.15)
        color = (line.color or "").strip().lower()
        color_words = [w for w in _re.split(r"[^a-z]+", color) if len(w) > 2]
        finish = (line.finish or "").strip().lower()

        scored = []
        for item in index:
            if supplier_allow and item["supplier"].lower() not in supplier_allow:
                continue
            dsize = abs(item["size"] - want_size)
            if dsize > tol:
                continue
            score = 100.0 - dsize * 10.0
            color_hit = bool(color_words) and all(w in item["search"] for w in color_words)
            if color_hit:
                score += 25.0
            finish_hit = bool(finish) and finish in item["search"]
            if finish_hit:
                score += 15.0
            if item["price"] is not None:
                score += 2.0
            if item["image"]:
                score += 1.0
            scored.append((score, dsize, item, color_hit, finish_hit))

        scored.sort(key=lambda x: (-x[0], x[1]))
        qty = line.quantity or 0
        matches = []
        for score, dsize, item, color_hit, finish_hit in scored[: max(1, body.per_line)]:
            case_qty = item["case_qty"] or 1
            try:
                case_qty = int(case_qty) or 1
            except (TypeError, ValueError):
                case_qty = 1
            packs_needed = (qty + case_qty - 1) // case_qty if qty else None
            matches.append({
                "product_id": item["id"],
                "supplier": item["supplier"],
                "name": item["name"],
                "sku": item["sku"],
                "price": item["price"],
                "image": item["image"],
                "size_in": item["size"],
                "color": item["color"],
                "finish": item["finish"],
                "case_qty": case_qty,
                "packs_needed": packs_needed,
                "color_match": color_hit,
                "finish_match": finish_hit,
                "canonical_key": item.get("canonical_key"),
                "size_delta": round(dsize, 2),
            })
        results.append({
            "size": want_size,
            "quantity": qty,
            "color": line.color,
            "finish": line.finish,
            "match_count": len(scored),
            "matches": matches,
        })

    return {"lines": results, "catalog_size": len(index)}
