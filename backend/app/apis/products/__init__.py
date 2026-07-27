from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Response
from pydantic import BaseModel
from typing import Any, Optional, List
from collections import Counter
import asyncpg
import os
import re
import uuid
import json
import hashlib
import requests as http_requests
import databutton as db
from datetime import datetime
from app.auth import AuthorizedUser
from app.apis.user_context import extract_user_id, get_request_user_id

router = APIRouter(prefix="/products", tags=["products"])

# ─── Image proxy ──────────────────────────────────────────────────────────────
# Supplier sites block hotlinking via Referer checks.
# We proxy images through the backend to serve them without that restriction.
def _sniff_image_ct(data: bytes) -> Optional[str]:
    """Content-type from magic bytes, or None if the bytes aren't a known image."""
    if not data:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    # "RIFF" here is the Resource Interchange File Format container magic that
    # every .webp starts with — nothing to do with the old Riff/Databutton
    # branding. Do not rename it.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    if data[:2] == b"BM":
        return "image/bmp"
    return None


@router.get("/image-proxy")
def image_proxy(url: Optional[str] = None, key: Optional[str] = None) -> Response:
    """Serve a product image — from Databutton storage (key=) or by proxying an
    external URL (url=). External fetches are validated (must be a real image,
    not a 404/HTML page) and cached locally so each image is fetched once and a
    dead URL fails cleanly with a 404 → the frontend then falls back to the next
    candidate image or a placeholder instead of showing a broken tile."""
    # ── Serve from internal storage (production stored images) ─────────────────
    if key:
        try:
            data = db.storage.binary.get(key)
            if not data:
                raise HTTPException(status_code=404, detail="Image not in storage")
            return Response(
                content=data,
                media_type=_sniff_image_ct(data) or "image/jpeg",
                headers={"Cache-Control": "public, max-age=604800"},  # 7 days
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Storage error: {e}")

    # ── Proxy external URL ────────────────────────────────────────────────────
    if not url or not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Provide url= or key= parameter")

    cache_key = f"imgcache/{hashlib.sha256(url.encode('utf-8')).hexdigest()}"
    # Serve from cache if we've fetched this image before.
    try:
        cached = db.storage.binary.get(cache_key)
        if cached:
            return Response(
                content=cached, media_type=_sniff_image_ct(cached) or "image/jpeg",
                headers={"Cache-Control": "public, max-age=604800"},
            )
    except Exception:
        pass  # cache miss / storage unavailable → fetch live

    try:
        domain = "/".join(url.split("/")[:3]) + "/"
        resp = http_requests.get(
            url,
            timeout=10,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                "Referer": domain,
            },
        )
    except Exception:
        # Unreachable host → 404 so the frontend advances to the next candidate.
        raise HTTPException(status_code=404, detail="Image source unreachable")

    ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    sniffed = _sniff_image_ct(resp.content)
    # Reject dead URLs that answer 200 with an HTML/error body (e.g. Allstate,
    # Melrose) — without this they'd be served as a broken "image".
    if resp.status_code != 200 or not (ct.startswith("image/") or sniffed):
        raise HTTPException(status_code=404, detail="Not an image")

    data = resp.content
    try:
        db.storage.binary.put(cache_key, data)  # lazily cache for next time
    except Exception:
        pass
    return Response(
        content=data,
        media_type=ct if ct.startswith("image/") else (sniffed or "image/jpeg"),
        headers={"Cache-Control": "public, max-age=604800"},
    )

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

# The in-memory index takes ~30s to build (longer on a small CPU). Until it's
# ready — on a fresh boot or right after a deploy — search falls back to the
# database so the catalog is never empty. These coordinate a single background
# build: concurrent builds would each hold the whole index in memory at once and
# risk an out-of-memory kill, so only one ever runs.
import asyncio as _asyncio

_INDEX_BUILD_LOCK = _asyncio.Lock()
_index_build_task = None  # the in-flight background build, if any


def _index_ready() -> bool:
    rows = _SEARCH_CACHE.get("rows")
    return rows is not None and (_time.time() - _SEARCH_CACHE["ts"]) < _SEARCH_TTL


def _ensure_index_building() -> None:
    """Start the background index build if it isn't ready and none is running.

    Non-blocking: it schedules the work and returns immediately so the caller can
    serve from the database meanwhile. The lock inside _load_search_index keeps
    this from ever building a second copy concurrently.
    """
    global _index_build_task
    if _index_ready():
        return
    if _index_build_task is not None and not _index_build_task.done():
        return

    async def _bg():
        conn = await get_conn()
        try:
            await _load_search_index(conn)
        finally:
            await conn.close()

    _index_build_task = _asyncio.create_task(_bg())


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


def _searchable_values(value, out: list) -> None:
    """Collect the human-meaningful values out of a raw_data blob.

    Keeping the raw JSON *text* in the search blob cost ~1.7 KB per product
    (~179 MB across the catalogue) — most of it braces, quotes, key names and
    image URLs that nobody searches for. Walking the values instead keeps every
    searchable term (material, finish, collection, UPC …) for about a third of
    the memory.
    """
    if isinstance(value, str):
        # Long prose and URLs add weight without adding search terms.
        if value and len(value) < 200 and not value.startswith("http"):
            out.append(value)
    elif isinstance(value, (int, float)):
        out.append(str(value))
    elif isinstance(value, dict):
        for v in value.values():
            _searchable_values(v, out)
    elif isinstance(value, list):
        for v in value:
            _searchable_values(v, out)


def _build_blob(*parts: str) -> str:
    """Lowercased keyword blob with duplicate words removed."""
    seen: set[str] = set()
    words: list[str] = []
    for word in " ".join(p for p in parts if p).lower().split():
        if word not in seen:
            seen.add(word)
            words.append(word)
    return " ".join(words)


async def _load_search_index(conn):
    if _index_ready():
        return _SEARCH_CACHE["rows"]

    # Single-flight: if another caller is already building, wait for it and use
    # its result rather than building a second copy (which would double memory).
    async with _INDEX_BUILD_LOCK:
        if _index_ready():
            return _SEARCH_CACHE["rows"]
        return await _build_search_index(conn)


async def _build_search_index(conn):
    now = _time.time()

    query = f"""
        SELECT p.id, p.name, s.name AS supplier_name, p.supplier_id, p.supplier_sku,
               p.current_price, p.image_urls, p.photo_url, p.availability, p.description,
               {PRODUCT_TYPE_SQL} AS product_type,
               p.raw_data
        FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id
        WHERE p.is_active = TRUE
    """

    idx = []
    # Streamed with a server-side cursor rather than one big fetch(). Pulling
    # ~95k rows (each carrying its raw_data) in a single round trip both spiked
    # peak memory to roughly double the finished index and got the connection
    # torn down by Supabase's transaction pooler mid-read.
    async with conn.transaction():
        async for r in conn.cursor(query, prefetch=1000):
            raw_text = r["raw_data"]  # asyncpg returns jsonb as its JSON text
            try:
                raw = json.loads(raw_text) if isinstance(raw_text, str) else (raw_text or {})
            except json.JSONDecodeError:
                raw = {}
            if not isinstance(raw, dict):
                raw = {}
            norm = raw.get("normalized") or {}
            cf = [c for c in (raw.get("color_families") or []) if isinstance(c, str)]
            # All candidate images (deduped) so the card can fall back URL→URL when
            # one 404s, instead of showing a broken/empty tile.
            images: list[str] = []
            for u in list(r["image_urls"] or []) + [r["photo_url"], raw.get("source_photo_url")]:
                if u and u not in images:
                    images.append(u)
            image = images[0] if images else None
            size = norm.get("size_in")
            try: size = float(size) if size is not None else None
            except (TypeError, ValueError): size = None
            color, finish = norm.get("color"), norm.get("finish")
            # full-breadth keyword blob: name + sku + description + every
            # searchable value captured in raw_data (see _searchable_values).
            raw_values: list[str] = []
            _searchable_values(raw, raw_values)
            blob = _build_blob(r["name"], r["supplier_sku"], r["description"],
                               r["supplier_name"], " ".join(raw_values))
            idx.append({
                "id": r["id"], "name": r["name"], "supplier_name": r["supplier_name"],
                "supplier_id": r["supplier_id"], "supplier_sku": r["supplier_sku"],
                "price": float(r["current_price"]) if r["current_price"] is not None else None,
                "image": image, "images": images[:6], "class": norm.get("class"), "color": color, "finish": finish,
                "size": size, "size_bucket": (f"{round(size * 2) / 2:g}" if size is not None else None),
                "product_type": r["product_type"], "color_families": cf,
                "category": raw.get("category_group"),
                "avail": _avail_bucket_py(r["availability"]),
                "blob": blob,
            })
    _SEARCH_CACHE.update(ts=now, rows=idx)
    return idx


_VOCAB_CACHE: dict = {"ts": -1.0, "vocab": None}


def _get_search_vocab(idx) -> set:
    """≥4-letter words from product names — the vocabulary a misspelled query
    word is matched back against. Rebuilt only when the search index reloads."""
    if _VOCAB_CACHE["vocab"] is not None and _VOCAB_CACHE["ts"] == _SEARCH_CACHE["ts"]:
        return _VOCAB_CACHE["vocab"]
    vocab: set = set()
    for it in idx:
        for w in re.findall(r"[a-z]{4,}", (it["name"] or "").lower()):
            vocab.add(w)
    _VOCAB_CACHE.update(ts=_SEARCH_CACHE["ts"], vocab=vocab)
    return vocab


def _bounded_distance(a: str, b: str, maxd: int) -> Optional[int]:
    """Damerau-Levenshtein (optimal string alignment) distance if ≤ maxd, else
    None. Counts an adjacent transposition as one edit, so "ornamnet" is 1 away
    from "ornament" — the most common real-world typo."""
    la, lb = len(a), len(b)
    if abs(la - lb) > maxd:
        return None
    prevprev = [0] * (lb + 1)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        row_best = i
        ai = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ai == b[j - 1] else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and ai == b[j - 2] and a[i - 2] == b[j - 1]:
                v = min(v, prevprev[j - 2] + 1)  # adjacent transposition
            cur[j] = v
            if v < row_best:
                row_best = v
        if row_best > maxd:
            return None
        prevprev, prev = prev, cur
    return prev[lb] if prev[lb] <= maxd else None


def _fuzzy_variants(term: str, vocab: set, maxd: int) -> list:
    """Closest vocabulary words to a misspelled term. Only the minimal-edit
    group is returned — so "wreathe" corrects to "wreath" (1 edit) and does NOT
    also pull in "weather" (2 edits). Same first letter + similar length keeps
    the scan fast."""
    first, lt = term[0], len(term)
    best = maxd + 1
    hits: list = []
    for w in vocab:
        if w[0] != first or abs(len(w) - lt) > maxd:
            continue
        d = _bounded_distance(term, w, maxd)
        if d is None:
            continue
        if d < best:
            best, hits = d, [w]
        elif d == best:
            hits.append(w)
    return hits


async def _search_products_db(conn, *, search, price_min, price_max,
                              supplier_ids, ids, limit, offset, build_facets):
    """Warm-up fallback: answer a search straight from the database.

    Used only while the in-memory index is still building. It covers the
    column-backed filters (keyword, price, supplier, ids) so the catalog shows
    real products immediately; the richer facet filters (colour/size/finish…)
    live in the index and are simply not applied during this brief window, which
    only ever widens results, never hides the catalog. `warming` lets the client
    show a "still loading" hint if it wants. Once the index is ready every
    request returns to the fast in-memory path automatically.
    """
    where = ["p.is_active = TRUE"]
    args: list = []

    for t in [w for w in (search or "").split() if w]:
        args.append(f"%{t}%")
        i = len(args)
        where.append(f"(p.name ILIKE ${i} OR p.description ILIKE ${i} OR p.supplier_sku ILIKE ${i})")
    if price_min is not None:
        args.append(price_min); where.append(f"p.current_price >= ${len(args)}")
    if price_max is not None:
        args.append(price_max); where.append(f"p.current_price <= ${len(args)}")
    sup = [int(x) for x in _csv_list(supplier_ids) if x.isdigit()]
    if sup:
        args.append(sup); where.append(f"p.supplier_id = ANY(${len(args)}::int[])")
    id_list = [int(x) for x in _csv_list(ids) if x.lstrip("-").isdigit()] if ids is not None else None
    if id_list is not None:
        args.append(id_list); where.append(f"p.id = ANY(${len(args)}::int[])")

    wsql = " AND ".join(where)
    lim = max(1, min(limit, 500))
    off = max(0, offset)

    # One scan, not two: COUNT(*) OVER() rides along with the page so the total
    # doesn't cost a second full-table scan during the warm-up window.
    rows = await conn.fetch(f"""
        SELECT p.id, p.name, s.name AS supplier_name, p.supplier_sku, p.current_price,
               p.image_urls, p.photo_url, p.raw_data,
               COUNT(*) OVER() AS _total
        FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id
        WHERE {wsql}
        ORDER BY p.name
        LIMIT {lim} OFFSET {off}
    """, *args)
    total = rows[0]["_total"] if rows else 0

    items = []
    for r in rows:
        raw = r["raw_data"]
        if isinstance(raw, str):
            try: raw = json.loads(raw)
            except json.JSONDecodeError: raw = {}
        raw = raw if isinstance(raw, dict) else {}
        norm = raw.get("normalized") or {}
        imgs: list[str] = []
        for u in list(r["image_urls"] or []) + [r["photo_url"], raw.get("source_photo_url")]:
            if u and u not in imgs:
                imgs.append(u)
        items.append({
            "id": r["id"], "name": r["name"], "supplier_name": r["supplier_name"],
            "supplier_sku": r["supplier_sku"],
            "current_price": float(r["current_price"]) if r["current_price"] is not None else None,
            "image_urls": imgs,
            "raw_data": {"normalized": {"color": norm.get("color"), "finish": norm.get("finish"),
                                        "size_in": norm.get("size_in"), "class": norm.get("class")}},
        })

    resp = {"items": items, "total": total or 0, "limit": limit, "offset": offset, "warming": True}
    if build_facets:
        resp["facets"] = {"categories": [], "colors": [], "sizes": [], "finishes": [],
                          "availability": [], "product_types": [], "suppliers": []}
    return resp


@router.get("/search")
async def search_products(
    colors: Optional[str] = None,
    categories: Optional[str] = None,
    sizes: Optional[str] = None,
    finishes: Optional[str] = None,
    product_types: Optional[str] = None,
    supplier_ids: Optional[str] = None,
    availability: Optional[str] = None,
    ids: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    search: Optional[str] = None,
    limit: int = 48,
    offset: int = 0,
):
    """Fast faceted search served from the in-memory catalog index.

    Alongside the page of results it returns `facets` — the values still
    available *within the current query* (search + price + favorites + the other
    filters), each with a live count. Every facet is computed with drill-down: a
    facet is counted ignoring its OWN selection, so picking one Color doesn't
    collapse the Color list — you can still add a second. This is what makes the
    sidebar responsive to whatever was searched (e.g. "ornaments" surfaces the
    ornament sizes/colors/finishes actually present). Facets are only built on a
    fresh load (offset == 0); infinite-scroll pages skip the extra pass.
    """
    # A warm request opens no connection at all — it filters the in-memory index,
    # so it isn't paying the DB round trip. Until that index is ready (fresh boot
    # or just after a deploy) we answer from the database instead of blocking this
    # request for the whole ~30s build, so the catalog is never empty.
    if not _index_ready():
        _ensure_index_building()
        conn = await get_conn()
        try:
            return await _search_products_db(
                conn, search=search, price_min=price_min, price_max=price_max,
                supplier_ids=supplier_ids, ids=ids, limit=limit, offset=offset,
                build_facets=offset <= 0,
            )
        finally:
            await conn.close()
    idx = _SEARCH_CACHE["rows"]

    col = set(_csv_list(colors)); sz = set(_csv_list(sizes)); fin = set(_csv_list(finishes))
    pt = set(_csv_list(product_types)); avail = set(_csv_list(availability))
    cat = set(_csv_list(categories))
    sup = {int(x) for x in _csv_list(supplier_ids) if x.isdigit()}
    id_filter = {int(x) for x in _csv_list(ids) if x.lstrip("-").isdigit()} if ids is not None else None
    terms = [w for w in (search or "").lower().split() if w]

    # Typo tolerance: a query word not in the catalog vocabulary is expanded to
    # near-spellings (edit distance 1, or 2 for long words) so "blossum" still
    # finds "blossom". Correctly-spelled words skip this entirely (no slowdown),
    # and exact matches rank ahead of fuzzy ones.
    term_variants: list[tuple[str, set]] = []
    if terms:
        vocab = _get_search_vocab(idx)
        for t in terms:
            variants = {t}
            if len(t) >= 4 and t not in vocab:
                variants |= set(_fuzzy_variants(t, vocab, 2 if len(t) >= 7 else 1))
            term_variants.append((t, variants))

    # Base set: the always-on filters (favorites ids, price, keyword). Facets and
    # results are both derived from here, so the sidebar reflects the search.
    match_score: dict = {}
    base = []
    for it in idx:
        if id_filter is not None and it["id"] not in id_filter: continue
        if price_min is not None and (it["price"] is None or it["price"] < price_min): continue
        if price_max is not None and (it["price"] is None or it["price"] > price_max): continue
        if term_variants:
            blob = it["blob"]; exact = 0; ok = True
            for t, variants in term_variants:
                if t in blob:
                    exact += 1
                elif not any(v in blob for v in variants):
                    ok = False; break
            if not ok: continue
            match_score[it["id"]] = exact
        base.append(it)

    # Faceted dimensions: (key, current selection, value-extractor). An item
    # "passes" a dimension when its selection is empty OR intersects the item's
    # values (colors are multi-valued; the rest single).
    def _one(v):
        return [v] if v else []
    dim_defs = [
        ("categories",   cat,   lambda it: _one(it["category"])),
        ("colors",       col,   lambda it: it["color_families"]),
        ("sizes",        sz,    lambda it: _one(it["size_bucket"])),
        ("finishes",     fin,   lambda it: _one(it["finish"])),
        ("availability", avail, lambda it: _one(it["avail"])),
        ("suppliers",    sup,   lambda it: [it["supplier_id"]] if it["supplier_id"] is not None else []),
        ("product_types", pt,   lambda it: _one(it["product_type"])),
    ]
    build_facets = offset <= 0
    counters = {key: Counter() for key, _, _ in dim_defs} if build_facets else None
    sup_names: dict = {}

    out = []
    for it in base:
        vals = [get(it) for _, _, get in dim_defs]
        fails = []
        for j, (_, selset, _get) in enumerate(dim_defs):
            if selset and not (selset & set(vals[j])):
                fails.append(j)
                if len(fails) > 1:
                    break
        nfail = len(fails)
        if nfail == 0:
            out.append(it)
        if not build_facets:
            continue
        # Count each facet over items that pass every OTHER facet (drill-down):
        # nfail==0 counts everywhere; nfail==1 counts only its single failing dim.
        if nfail == 0:
            for (key, _s, _g), v in zip(dim_defs, vals):
                for x in v:
                    counters[key][x] += 1
        elif nfail == 1:
            key = dim_defs[fails[0]][0]
            for x in vals[fails[0]]:
                counters[key][x] += 1
        if it["supplier_id"] is not None:
            sup_names[it["supplier_id"]] = it["supplier_name"]

    # Exact keyword matches first (fuzzy-only matches after), then by name.
    out.sort(key=lambda x: (-match_score.get(x["id"], 0), (x["name"] or "").lower()))
    total = len(out)
    page = out[max(0, offset): max(0, offset) + max(1, min(limit, 500))]
    items = [{
        "id": it["id"], "name": it["name"], "supplier_name": it["supplier_name"],
        "supplier_sku": it["supplier_sku"], "current_price": it["price"],
        "image_urls": it.get("images") or ([it["image"]] if it["image"] else []),
        "raw_data": {"normalized": {"color": it["color"], "finish": it["finish"],
                                    "size_in": it["size"], "class": it["class"]}},
    } for it in page]

    resp = {"items": items, "total": total, "limit": limit, "offset": offset}
    if build_facets:
        def _by_count(c):
            return [{"value": v, "count": n} for v, n in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0]).lower()))[:80]]
        # sizes read as numbers so 10" sorts after 9", not after 1"
        def _by_size(c):
            def num(v):
                try: return float(v)
                except (TypeError, ValueError): return 1e9
            items_ = [(v, n) for v, n in c.items() if num(v) > 0]  # drop the 0" noise bucket
            return [{"value": v, "count": n} for v, n in sorted(items_, key=lambda kv: num(kv[0]))[:80]]
        resp["facets"] = {
            "categories": _by_count(counters["categories"]),
            "colors": _by_count(counters["colors"]),
            "sizes": _by_size(counters["sizes"]),
            "finishes": _by_count(counters["finishes"]),
            "availability": _by_count(counters["availability"]),
            "product_types": _by_count(counters["product_types"]),
            "suppliers": [
                {"value": sup_names.get(sid, str(sid)), "id": sid, "count": n}
                for sid, n in counters["suppliers"].most_common(80)
            ],
        }
    return resp


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
    # Serve it from our own image route, the same way upload-photo above does.
    # This used to return a static.riff.new URL pointing at the old platform's
    # CDN — a link that never resolved, because the bytes are written to our own
    # storage one line up, not theirs.
    return {"photo_url": f"/api/products/photo/{key.replace('/', '_')}", "key": key}

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
        # Favourites are personal; projects are team-wide.
        total_favorites = await conn.fetchval("SELECT COUNT(*) FROM product_favorites WHERE user_id = $1", user_id)
        total_arrangements = await conn.fetchval("SELECT COUNT(*) FROM arrangements")
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
                 "boxwood", "topiary", "stem", "bush", "tree", "candle",
                 "stick", "swag", "cluster", "wand", "on stem",
                 # non-ornament items that merely contain "ball" as a substring
                 "moss", "rope", "vase", "highball", "disco", "bud vase",
                 "basket", "mesh", "nut", "pomander", "succulent", "topiaries")


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
        # exclude non-loose-ball items (ball on a stick/pick/spray, etc.) even
        # when they're classed as ball ornaments — applies to every row.
        nm = (r["name"] or "").lower()
        if any(w in nm for w in _BALL_EXCLUDE):
            continue
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
        # When a color is requested, only count/show ornaments of that color, so
        # the "in catalog" total reflects size + color (not just size).
        eligible = [t for t in scored if t[3]] if color_words else scored  # t[3]=color_hit
        # Vendor-diverse: surface the best match(es) from EVERY vendor that has a
        # qualifying ornament, so all suppliers are represented instead of the
        # largest one (Vickerman) crowding out the rest. Round-robin by vendor:
        # round 0 = best per vendor (all vendors), later rounds add depth.
        by_vendor: dict = {}
        for tup in eligible:
            by_vendor.setdefault(tup[2]["supplier"], []).append(tup)
        chosen = []
        for round_i in range(max(1, body.per_line)):
            for lst in by_vendor.values():
                if round_i < len(lst):
                    chosen.append(lst[round_i])
        qty = line.quantity or 0
        matches = []
        for score, dsize, item, color_hit, finish_hit in chosen:
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
            "match_count": len(eligible),
            "matches": matches,
        })

    return {"lines": results, "catalog_size": len(index)}
