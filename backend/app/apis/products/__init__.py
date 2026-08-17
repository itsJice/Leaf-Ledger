from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Response
from pydantic import BaseModel
from typing import Any, Optional, List
from collections import Counter
from decimal import Decimal, InvalidOperation
import asyncpg
import os
import re
import uuid
import json
import tempfile
import gzip
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
# The catalog only changes when someone runs an import, so an hour was needlessly
# short: every expiry re-reads the whole catalog out of Supabase. Egress is the
# binding constraint (a single rebuild moves tens of MB), not staleness.
_SEARCH_TTL = int(os.environ.get("SEARCH_INDEX_TTL", 24 * 3600))

# Rebuilding the index on every process start is the single largest source of
# database egress: each build streams the whole catalog. Persisting it means a
# restart reloads from local disk and reads nothing. Set SEARCH_INDEX_CACHE_DIR
# to a persistent volume in production; on an ephemeral filesystem this still
# covers in-place restarts, just not brand-new containers.
_SEARCH_DISK_CACHE = os.environ.get("SEARCH_INDEX_CACHE_DIR") or os.path.join(
    tempfile.gettempdir(), "leaf-ledger-index"
)
_SEARCH_DISK_VERSION = 2  # bump whenever the row shape below changes
# Rows pulled per cursor round trip. At 1,000 a 166k-row catalog needed 166
# round trips, which dominates the build wherever latency to the database is
# non-trivial (a laptop, or a host in a different region). Larger batches trade
# a little peak memory for far fewer trips.
_INDEX_PREFETCH = int(os.environ.get("SEARCH_INDEX_PREFETCH", 10000))

# Escape hatch. The in-memory index buys instant filtering and the colour/size/
# finish facets, but building it reads the whole catalog, which is expensive in
# both time and egress. Since the trigram indexes landed, the database path is
# fast enough to serve search on its own - it just can't do those extra facets
# yet. Set SEARCH_INDEX_ENABLED=0 to skip the build entirely and stay on SQL.
_INDEX_ENABLED = os.environ.get("SEARCH_INDEX_ENABLED", "1").lower() not in ("0", "false", "no")
# Warm-up fallback only: how far we will count before reporting "N+".
_DB_COUNT_CAP = 5000

# The in-memory index takes ~30s to build (longer on a small CPU). Until it's
# ready — on a fresh boot or right after a deploy — search falls back to the
# database so the catalog is never empty. These coordinate a single background
# build: concurrent builds would each hold the whole index in memory at once and
# risk an out-of-memory kill, so only one ever runs.
import asyncio as _asyncio

_INDEX_BUILD_LOCK = _asyncio.Lock()
_index_build_task = None  # the in-flight background build, if any


def _index_ready() -> bool:
    if not _INDEX_ENABLED:
        return False
    rows = _SEARCH_CACHE.get("rows")
    return rows is not None and (_time.time() - _SEARCH_CACHE["ts"]) < _SEARCH_TTL


def _ensure_index_building() -> None:
    """Start the background index build if it isn't ready and none is running.

    Non-blocking: it schedules the work and returns immediately so the caller can
    serve from the database meanwhile. The lock inside _load_search_index keeps
    this from ever building a second copy concurrently.
    """
    global _index_build_task
    if not _INDEX_ENABLED:
        return  # SQL-only mode: never read the whole catalog
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
        # Prefer a warm index left on disk by an earlier run: reading it costs
        # nothing from the database, where a rebuild streams the whole catalog.
        cached = _load_index_from_disk()
        if cached:
            _SEARCH_CACHE.update(ts=_time.time(), rows=cached)
            return cached
        return await _build_search_index(conn)


def _loads_obj(value) -> dict:
    """asyncpg hands back jsonb as text; tolerate either, never raise."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _loads_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _disk_cache_path() -> str:
    return os.path.join(_SEARCH_DISK_CACHE, f"search-index-v{_SEARCH_DISK_VERSION}.json.gz")


def _load_index_from_disk():
    """Return a cached index if one is on disk and still within its TTL."""
    path = _disk_cache_path()
    try:
        if not os.path.exists(path):
            return None
        age = _time.time() - os.path.getmtime(path)
        if age >= _SEARCH_TTL:
            return None
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            payload = json.load(fh)
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            return None
        print(f"search index loaded from disk ({len(rows)} rows, {age/60:.0f} min old) — no catalog read")
        return rows
    except Exception as e:  # noqa: BLE001 — a bad cache must never block startup
        print(f"search index disk cache unreadable, rebuilding: {e}")
        return None


def _save_index_to_disk(rows) -> None:
    path = _disk_cache_path()
    try:
        os.makedirs(_SEARCH_DISK_CACHE, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump({"rows": rows}, fh)
        os.replace(tmp, path)  # atomic: readers never see a half-written file
    except Exception as e:  # noqa: BLE001 — caching is an optimisation, not a requirement
        print(f"could not persist search index: {e}")


async def _build_search_index(conn):
    now = _time.time()

    # Only the pieces of raw_data the index actually uses are pulled, and the
    # searchable text is flattened server-side. Shipping whole raw_data
    # documents for 166k rows meant transferring 237 MB (compressed on disk,
    # more on the wire) and the warm-up ran for over nine minutes; extracting
    # here costs ~400 chars a row instead. The WHERE clauses mirror
    # _searchable_values(): no URLs, nothing longer than prose.
    query = f"""
        SELECT p.id, p.name, s.name AS supplier_name, p.supplier_id, p.supplier_sku,
               p.current_price, p.image_urls, p.photo_url, p.availability, p.description,
               {PRODUCT_TYPE_SQL} AS product_type,
               p.raw_data->'normalized'       AS norm_json,
               p.raw_data->'color_families'   AS color_families_json,
               p.raw_data->>'category_group'  AS category_group,
               p.raw_data->>'source_photo_url' AS source_photo_url,
               (SELECT string_agg(v.value, ' ')
                  FROM jsonb_each_text(CASE WHEN jsonb_typeof(p.raw_data) = 'object'
                                            THEN p.raw_data ELSE '{{}}'::jsonb END) AS v(key, value)
                 WHERE v.value <> '' AND length(v.value) < 200
                   AND v.value NOT LIKE 'http%%') AS raw_blob
        FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id
        WHERE p.is_active = TRUE
    """

    idx = []
    # Streamed with a server-side cursor rather than one big fetch(). Pulling
    # ~95k rows (each carrying its raw_data) in a single round trip both spiked
    # peak memory to roughly double the finished index and got the connection
    # torn down by Supabase's transaction pooler mid-read.
    async with conn.transaction():
        async for r in conn.cursor(query, prefetch=_INDEX_PREFETCH):
            norm = _loads_obj(r["norm_json"])
            cf = [c for c in (_loads_list(r["color_families_json"])) if isinstance(c, str)]
            # All candidate images (deduped) so the card can fall back URL→URL when
            # one 404s, instead of showing a broken/empty tile.
            images: list[str] = []
            for u in list(r["image_urls"] or []) + [r["photo_url"], r["source_photo_url"]]:
                if u and u not in images:
                    images.append(u)
            image = images[0] if images else None
            size = norm.get("size_in")
            try: size = float(size) if size is not None else None
            except (TypeError, ValueError): size = None
            color, finish = norm.get("color"), norm.get("finish")
            # full-breadth keyword blob: name + sku + description + every
            # searchable value captured in raw_data (see _searchable_values).
            blob = _build_blob(r["name"], r["supplier_sku"], r["description"],
                               r["supplier_name"], r["raw_blob"] or "")
            idx.append({
                "id": r["id"], "name": r["name"], "supplier_name": r["supplier_name"],
                "supplier_id": r["supplier_id"], "supplier_sku": r["supplier_sku"],
                "price": float(r["current_price"]) if r["current_price"] is not None else None,
                "image": image, "images": images[:6], "class": norm.get("class"), "color": color, "finish": finish,
                "size": size, "size_bucket": (f"{round(size * 2) / 2:g}" if size is not None else None),
                "product_type": r["product_type"], "color_families": cf,
                "category": r["category_group"],
                "avail": _avail_bucket_py(r["availability"]),
                "blob": blob,
            })
    _SEARCH_CACHE.update(ts=now, rows=idx)
    _save_index_to_disk(idx)
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


# ─── SQL-served facets ────────────────────────────────────────────────────────
# The sidebar is the last thing the in-memory index does that SQL did not, so it
# is the last thing standing between us and deleting ~892 MB of resident memory.
#
# Two measurements on the production instance shape the implementation:
#   * touching raw_data at all costs ~15 s for a full-catalog pass — 145 MB of
#     TOAST to fetch and parse for 166k rows. So a facet build must make at most
#     ONE pass, and must not make it when the answer is already known;
#   * as soon as any indexable predicate narrows the scan, that same pass drops
#     to ~0.2 s. Keyword, supplier and price all narrow.
#
# Hence the shape below: ONE materialised pass that extracts every dimension in a
# single scan and then aggregates seven times over the tuplestore (seven separate
# GROUP BYs would pay the 15 s seven times over), plus a cache for the unfiltered
# counts — the one case nothing can narrow, and the case most page loads ask for.
_FACET_DIMS = ("categories", "colors", "sizes", "finishes",
               "availability", "suppliers", "product_types")

_FACET_TTL = int(os.environ.get("SEARCH_FACET_TTL", _SEARCH_TTL))
# Unfiltered baseline: the counts for "no search, nothing selected". They only
# change when someone runs an import.
_FACET_CACHE: dict = {"ts": 0.0, "facets": None, "total": 0}
_FACET_BUILD_LOCK = _asyncio.Lock()
_facet_build_task = None
_FACET_DISK_VERSION = 1
# How long a cold request will wait for the baseline before giving up on it and
# serving a sidebar-less page. The build itself keeps running either way.
_FACET_COLD_WAIT = float(os.environ.get("SEARCH_FACET_COLD_WAIT", 8))
# Exact hits below this make a query look like a typo and unlock fuzzy matching.
_FUZZY_MIN_HITS = int(os.environ.get("SEARCH_FUZZY_MIN_HITS", 5))
# Typo-correction vocabulary, built by the database (see _load_sql_vocab).
_SQL_VOCAB_CACHE: dict = {"ts": 0.0, "vocab": None}

# migrations/006 adds `product_facets`: a narrow, trigger-maintained projection
# of the facet values (52 MB against the 500 MB products table). Reading a colour
# or a category from it costs an index lookup instead of detoasting raw_data for
# 166k rows. The JSONB expressions below stay correct if it is absent, so this
# file works on either schema and just gets faster when the migration lands.
_FACET_SOURCE: dict = {"probed": False, "has_pf": False, "has_blob": False}
# The dimensions product_facets actually covers. supplier_id and availability are
# plain products columns (no TOAST, already indexed) and product_type falls back
# to raw_data on 82% of rows, so none of those three gain anything from the join.
_PF_DIMS = ("categories", "colors", "sizes", "finishes")

# Sizes are grouped into half-inch buckets. Python's round() is half-to-even, so
# the index buckets 1.25" down to 1.0" where a naive SQL round() gives 1.5";
# reproduced here so the two paths agree on every bucket.
_SIZE_BUCKET_SQL = """CASE WHEN {v} IS NULL THEN NULL ELSE
    (CASE WHEN ({v} * 2) - floor({v} * 2) = 0.5 AND (floor({v} * 2))::bigint % 2 = 0
          THEN floor({v} * 2) ELSE round({v} * 2) END) / 2 END"""
# The bucket's label, formatted the way "%g" does it (20.0 -> "20", 2.5 -> "2.5").
# Applied to the ~80 grouped buckets, never to the 166k rows behind them.
_SIZE_LABEL_SQL = "rtrim(rtrim(to_char({v}, 'FM9999990.0'), '0'), '.')"


async def _facet_source_probe(conn) -> tuple[bool, bool]:
    """(product_facets exists, it carries search_blob). Probed once per process.

    `search_blob` is the flattened raw_data text the in-memory index searches.
    Until it exists the SQL path can only match name/description/sku, which is
    the one real recall gap between the two paths; the moment the column and its
    trigram index land, this picks it up with no further code change.
    """
    if _FACET_SOURCE["probed"]:
        return _FACET_SOURCE["has_pf"], _FACET_SOURCE["has_blob"]
    has = blob = False
    try:
        row = await conn.fetchrow("""
            SELECT to_regclass('public.product_facets') AS t,
                   EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = 'product_facets'
                              AND column_name = 'search_blob') AS blob""")
        has = bool(row and row["t"])
        blob = has and bool(row["blob"])
    except Exception as e:  # noqa: BLE001 — a failed probe just means "use raw_data"
        print(f"facet source probe failed, using raw_data paths: {e}")
    _FACET_SOURCE.update(probed=True, has_pf=has, has_blob=blob)
    print(f"facets reading from {'product_facets' if has else 'products.raw_data'}"
          f"{'; keyword search includes search_blob' if blob else ''}")
    return has, blob


def _facet_exprs(has_pf: bool) -> dict:
    """SQL for each faceted value, keyed by the short name used everywhere below.

    These must agree value-for-value with what _build_search_index puts in the
    in-memory rows, or the two paths disagree on counts. Note `categories` reads
    category_group with NO fallback to the (much sparser, slug-shaped) category
    column, and `colors` reads the multi-valued color_families — not
    normalized.color, which is a different, single-valued thing.

    `cfam_kind` exists because the two sources spell "many colours" differently:
    a jsonb array in raw_data, a text[] in product_facets. Overlap and unnest
    differ accordingly.
    """
    if has_pf:
        # product_facets stores size_in as text, so it has to be validated before
        # the cast — one bad row would otherwise error the whole sidebar. The
        # exponent branch matters because jsonb renders some numbers that way.
        size = ("CASE WHEN pf.norm_size_in ~ '^-?[0-9]+(\\.[0-9]+)?([eE][-+]?[0-9]+)?$' "
                "THEN pf.norm_size_in::numeric END")
        exprs = {
            "join": "JOIN product_facets pf ON pf.product_id = p.id",
            "cat": "NULLIF(pf.category_group, '')",
            "fin": "NULLIF(pf.norm_finish, '')",
            "cfam": "pf.color_families",
            "cfam_kind": "array",
            "size": size,
        }
    else:
        # size_in is stored as a JSON number on every row that has one, so the
        # type check answers for free; the regex is a guard against a future
        # importer writing it as text, and never actually runs today (a JSON null
        # makes ->> return SQL NULL, which the regex short-circuits on).
        size = ("CASE WHEN jsonb_typeof(p.raw_data->'normalized'->'size_in') = 'number' "
                "     THEN (p.raw_data->'normalized'->>'size_in')::numeric "
                "     WHEN p.raw_data->'normalized'->>'size_in' ~ '^-?[0-9]+(\\.[0-9]+)?$' "
                "     THEN (p.raw_data->'normalized'->>'size_in')::numeric END")
        exprs = {
            "join": "",
            "cat": "NULLIF(p.raw_data->>'category_group', '')",
            "fin": "NULLIF(p.raw_data->'normalized'->>'finish', '')",
            "cfam": ("CASE WHEN jsonb_typeof(p.raw_data->'color_families') = 'array' "
                     "THEN p.raw_data->'color_families' END"),
            "cfam_kind": "jsonb",
            "size": size,
        }
    exprs.update({
        "szn": _SIZE_BUCKET_SQL.format(v=f"({size})"),
        # Neither of these gains anything from product_facets: availability and
        # style are plain products columns, and product_type falls through to
        # raw_data on the 82% of rows where style is empty either way.
        "ptype": f"NULLIF({PRODUCT_TYPE_SQL}, '')",
        "avail": f"({_availability_bucket_sql('btrim(p.availability)')})",
        "sid": "p.supplier_id",
    })
    return exprs


def _dim_predicate(dim: str, ref: dict, placeholder: str) -> str:
    """"This row is inside the user's selection for `dim`" — over `ref`, which is
    either the raw p.*/pf.* expressions (items query) or CTE aliases (facets).

    COALESCE to false throughout: a NULL here would poison the drill-down
    arithmetic and silently drop the row from every facet.
    """
    if dim == "colors":
        if ref.get("cfam_kind") == "array":
            return f"COALESCE({ref['cfam']} && {placeholder}::text[], false)"
        return f"COALESCE({ref['cfam']} ?| {placeholder}::text[], false)"
    if dim == "suppliers":
        return f"COALESCE({ref['sid']} = ANY({placeholder}::int[]), false)"
    if dim == "sizes":
        # Compared as numbers, not as their labels — "2.5" and "2.50" are the
        # same bucket, and it saves formatting every row just to filter it.
        return f"COALESCE({ref['szn']} = ANY({placeholder}::numeric[]), false)"
    col = {"categories": "cat", "finishes": "fin",
           "availability": "avail", "product_types": "ptype"}[dim]
    return f"COALESCE({ref[col]} = ANY({placeholder}::text[]), false)"


def _facet_query(exprs: dict, base_where: str, base_args: list,
                 sel: dict, dims: tuple) -> tuple[str, list]:
    """One materialised pass, then one GROUP BY per requested dimension.

    Drill-down is arithmetic rather than seven differently-filtered queries: the
    CTE carries `nfail`, the number of *selected* dimensions this row fails. A
    row belongs in dimension d's counts when it fails nothing except possibly d
    itself — `nfail = (NOT passes_d)::int`, which collapses to `nfail = 0` for a
    dimension the user has not touched. That is exactly the in-memory rule
    (count where nfail==0, plus the single failing dimension when nfail==1), and
    it means every dimension is counted in the same scan.
    """
    args = list(base_args)

    def add(value) -> str:
        args.append(value)
        return f"${len(args)}"

    # Built against p.*/pf.* because a CTE cannot reference its own output aliases.
    raw_ref = {"cat": exprs["cat"], "cfam": exprs["cfam"], "szn": "sb.szn",
               "fin": exprs["fin"], "avail": exprs["avail"], "ptype": exprs["ptype"],
               "sid": exprs["sid"], "cfam_kind": exprs["cfam_kind"]}

    # Hard predicates that touch only product_facets can be applied before the
    # join. Sizes is spelled inline here rather than through the lateral so it
    # stays pf-only.
    pf_ref = dict(raw_ref, szn=_SIZE_BUCKET_SQL.format(v=f"({exprs['size']})"))

    pass_cols, nfail_terms = [], []
    pf_hard: list[str] = []       # applied to product_facets BEFORE the join
    hard: list[str] = []          # applied after it
    drill_cte, drill_pf = [], []  # the "at least one passes" term, both spellings
    drill_all_pf = True           # can that term be answered before the join?

    for dim in _FACET_DIMS:
        if not sel.get(dim):
            continue
        ph = add(sel[dim])
        pred = _dim_predicate(dim, raw_ref, ph)
        pf_only = bool(exprs["join"]) and dim in _PF_DIMS
        pf_pred = f"({_dim_predicate(dim, pf_ref, ph)})" if pf_only else None
        if dim in dims:
            pass_cols.append(f"({pred}) AS ps_{dim}")
            nfail_terms.append(f"(NOT ({pred}))::int")
            drill_cte.append(f"({pred})")
            drill_pf.append(pf_pred or f"({pred})")
            drill_all_pf = drill_all_pf and pf_only
        elif pf_only:
            pf_hard.append(pf_pred)
        else:
            # This dimension's own counts are coming from the cache, so no branch
            # here ever wants a row that fails it. Pushing the selection into the
            # scan instead of into `nfail` is the difference between a GIN lookup
            # over a few thousand rows and materialising all 166k — this is the
            # "user clicked one colour" path, so it is the one that matters.
            hard.append(f"({pred})")
    nfail = " + ".join(nfail_terms) or "0"

    # Every branch wants rows failing at most one selected dimension, so with two
    # or more of them at least one must pass. Weaker than nfail <= 1, but unlike
    # nfail it is a plain OR the planner can answer from indexes — and when every
    # drilled dimension lives in product_facets it can be answered before the join.
    if len(drill_cte) >= 2:
        if drill_all_pf:
            pf_hard.append("(" + " OR ".join(drill_pf) + ")")
        else:
            hard.append("(" + " OR ".join(drill_cte) + ")")

    # Filtering the 52 MB projection first and only then fetching the matching
    # product rows. Without this fence the planner sees two PK-ordered inputs and
    # picks a merge join, which walks products_pkey across 160k rows in random
    # heap order — measured at 39 s for a two-facet drill-down.
    # Only when there is something to filter on: fencing an unfiltered pass just
    # buys a 166k-row tuplestore (measured 58.7s either way — that pass is bound
    # by detoasting raw_data for product_type, not by the join), and a keyword
    # query is better served by the products-side trigram bitmap.
    join_sql, pf_cte = exprs["join"], ""
    if pf_hard:
        pf_cte = ("pf_sel AS MATERIALIZED (SELECT * FROM product_facets pf WHERE "
                  + " AND ".join(pf_hard) + "), ")
        join_sql = "JOIN pf_sel pf ON pf.product_id = p.id"

    where_sql = " AND ".join([base_where, *hard])

    def drill(dim: str) -> str:
        return f"b.nfail = (NOT b.ps_{dim})::int" if sel.get(dim) else "b.nfail = 0"

    branches = [
        # The exact total of the current selection, free of charge in this pass —
        # so a faceted request never has to fall back on the capped count.
        f"SELECT '__total__' AS dim, NULL::text AS val, NULL::int AS sid, "
        f"count(*)::int AS n FROM base b WHERE b.nfail = 0"
    ]
    branch_sql = {
        "categories": ("SELECT 'categories', b.cat, NULL::int, count(*)::int FROM base b "
                       f"WHERE {drill('categories')} AND b.cat IS NOT NULL GROUP BY b.cat"),
        "finishes": ("SELECT 'finishes', b.fin, NULL::int, count(*)::int FROM base b "
                     f"WHERE {drill('finishes')} AND b.fin IS NOT NULL GROUP BY b.fin"),
        "sizes": (f"SELECT 'sizes', {_SIZE_LABEL_SQL.format(v='b.szn')}, NULL::int, count(*)::int "
                  f"FROM base b WHERE {drill('sizes')} AND b.szn IS NOT NULL GROUP BY b.szn"),
        "availability": ("SELECT 'availability', b.av, NULL::int, count(*)::int FROM base b "
                         f"WHERE {drill('availability')} AND b.av IS NOT NULL GROUP BY b.av"),
        "product_types": ("SELECT 'product_types', b.ptype, NULL::int, count(*)::int FROM base b "
                          f"WHERE {drill('product_types')} AND b.ptype IS NOT NULL GROUP BY b.ptype"),
        "suppliers": ("SELECT 'suppliers', COALESCE(s.name, b.sid::text), b.sid, count(*)::int "
                      "FROM base b LEFT JOIN suppliers s ON s.id = b.sid "
                      f"WHERE {drill('suppliers')} AND b.sid IS NOT NULL GROUP BY b.sid, s.name"),
        # colors is the multi-valued dimension: one row can be Red AND Gold, so it
        # is counted through an unnest rather than a plain GROUP BY.
        "colors": ("SELECT 'colors', f, NULL::int, count(*)::int FROM base b, LATERAL "
                   + ("unnest(b.cfam) f" if exprs["cfam_kind"] == "array"
                      else "jsonb_array_elements_text(b.cfam) f")
                   + f" WHERE b.cfam IS NOT NULL AND {drill('colors')} GROUP BY f"),
    }
    branches += [branch_sql[d] for d in dims if d in branch_sql]

    # Only carry the dimensions some branch is actually going to count. This is
    # not tidiness: product_type falls back to raw_data on 82% of rows, so a
    # request whose product_types facet comes from the cache can avoid touching
    # TOAST at all and run entirely off product_facets.
    col_sql = {
        "categories": f"{exprs['cat']} AS cat",
        "colors": f"{exprs['cfam']} AS cfam",
        "finishes": f"{exprs['fin']} AS fin",
        "availability": f"{exprs['avail']} AS av",
        "product_types": f"{exprs['ptype']} AS ptype",
        "suppliers": f"{exprs['sid']} AS sid",
        "sizes": "sb.szn AS szn",
    }
    select_cols = [col_sql[d] for d in _FACET_DIMS if d in dims]
    select_cols += pass_cols
    select_cols.append(f"({nfail}) AS nfail")

    # The lateral exists so the size expression is pulled out of raw_data ONCE
    # per row instead of four times by the rounding arithmetic.
    lateral = ""
    if "sizes" in dims or sel.get("sizes"):
        lateral = f"""LEFT JOIN LATERAL (
                SELECT {_SIZE_BUCKET_SQL.format(v='sv.v')} AS szn
                FROM (SELECT {exprs['size']} AS v) sv
            ) sb ON TRUE"""

    sql = f"""
        WITH {pf_cte}base AS MATERIALIZED (
            SELECT {', '.join(select_cols)}
            FROM products p
            {join_sql}
            {lateral}
            WHERE {where_sql}
        )
        {' UNION ALL '.join(branches)}
    """
    return sql, args


def _shape_facets(rows, dims) -> tuple[dict, Optional[int]]:
    """Group the flat (dim, value, id, count) result into the sidebar payload.

    Ordering and truncation copy the in-memory path exactly: count descending
    then value, capped at 80 — except sizes, which sort numerically so 10" lands
    after 9" instead of after 1", and drop the 0" noise bucket.
    """
    buckets: dict = {d: [] for d in dims}
    total: Optional[int] = None
    for r in rows:
        dim = r["dim"]
        if dim == "__total__":
            total = int(r["n"] or 0)
            continue
        if dim not in buckets:
            continue
        value = r["val"]
        if value is None or not str(value).strip():
            continue
        entry = {"value": str(value), "count": int(r["n"] or 0)}
        if r["sid"] is not None:
            entry["id"] = int(r["sid"])
        buckets[dim].append(entry)

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 1e9

    out = {}
    for dim, entries in buckets.items():
        if dim == "sizes":
            entries = [e for e in entries if _num(e["value"]) > 0]
            entries.sort(key=lambda e: _num(e["value"]))
        else:
            entries.sort(key=lambda e: (-e["count"], str(e["value"]).lower()))
        out[dim] = entries[:80]
    return out, total


def _empty_facets() -> dict:
    return {d: [] for d in _FACET_DIMS}


def _facets_fresh() -> bool:
    return (_FACET_CACHE["facets"] is not None
            and (_time.time() - _FACET_CACHE["ts"]) < _FACET_TTL)


def _facet_disk_path() -> str:
    return os.path.join(_SEARCH_DISK_CACHE, f"facets-v{_FACET_DISK_VERSION}.json.gz")


def _load_facets_from_disk() -> bool:
    """Warm the unfiltered baseline from a previous run. Costs the database
    nothing, which is the entire point of this exercise."""
    path = _facet_disk_path()
    try:
        if not os.path.exists(path):
            return False
        age = _time.time() - os.path.getmtime(path)
        if age >= _FACET_TTL:
            return False
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            payload = json.load(fh)
        facets = payload.get("facets")
        if not isinstance(facets, dict) or not facets:
            return False
        _FACET_CACHE.update(ts=_time.time() - age, facets=facets,
                            total=int(payload.get("total") or 0))
        vocab = payload.get("vocab")
        if isinstance(vocab, list) and vocab:
            _SQL_VOCAB_CACHE.update(ts=_time.time() - age, vocab=set(vocab))
        return True
    except Exception as e:  # noqa: BLE001 — a bad cache must never block a request
        print(f"facet disk cache unreadable, rebuilding: {e}")
        return False


def _save_facets_to_disk() -> None:
    path = _facet_disk_path()
    try:
        os.makedirs(_SEARCH_DISK_CACHE, exist_ok=True)
        payload = {"facets": _FACET_CACHE["facets"], "total": _FACET_CACHE["total"],
                   "vocab": sorted(_SQL_VOCAB_CACHE["vocab"] or ())}
        tmp = f"{path}.{os.getpid()}.tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001 — caching is an optimisation
        print(f"could not persist facet cache: {e}")


async def _build_unfiltered_facets(conn) -> Optional[dict]:
    """The no-search, nothing-selected counts. The one pass nothing can narrow
    (~15 s), so it is computed once and cached hard — memory plus disk, the same
    way the search index is, so a restart does not re-read the catalog."""
    has_pf, _ = await _facet_source_probe(conn)
    exprs = _facet_exprs(has_pf)
    sql, args = _facet_query(exprs, "TRUE" if has_pf else "p.is_active = TRUE",
                             [], {}, _FACET_DIMS)
    started = _time.time()
    rows = await conn.fetch(sql, *args)
    if not rows:
        return None  # a stub or a failure — never cache an empty sidebar
    facets, total = _shape_facets(rows, _FACET_DIMS)
    _FACET_CACHE.update(ts=_time.time(), facets=facets, total=int(total or 0))
    _save_facets_to_disk()
    print(f"unfiltered facets built in {_time.time() - started:.1f}s ({total} products)")
    return facets


def _ensure_facets_building() -> None:
    """Kick off the baseline build without blocking this request.

    A cold process would otherwise hold the first browse for ~15 s. Serving an
    empty sidebar for one request and filling it on the next is the better trade,
    and with the disk cache only a brand-new container ever sees it.
    """
    global _facet_build_task
    if _facets_fresh():
        return
    if _facet_build_task is not None and not _facet_build_task.done():
        return
    if _load_facets_from_disk():
        return

    async def _bg():
        async with _FACET_BUILD_LOCK:
            if _facets_fresh():
                return
            conn = await get_conn()
            try:
                await _build_unfiltered_facets(conn)
            except Exception as e:  # noqa: BLE001 — never let this kill the loop
                print(f"unfiltered facet build failed: {e}")
            finally:
                await conn.close()

    try:
        _facet_build_task = _asyncio.create_task(_bg())
    except RuntimeError:
        pass  # no running loop (tests) — the next request will try again


async def _load_sql_vocab(conn) -> set:
    """The typo-correction vocabulary: ≥4-letter words from product names.

    Same definition as _get_search_vocab, but the DISTINCT happens in the
    database, so this moves ~117 KB of unique words instead of the catalog —
    17k words, ~2.3 s, cached for a day. Only ever built when a query already
    looks misspelt, so a correctly spelled search never pays for it.
    """
    cached = _SQL_VOCAB_CACHE["vocab"]
    if cached and (_time.time() - _SQL_VOCAB_CACHE["ts"]) < _FACET_TTL:
        return cached
    try:
        rows = await conn.fetch("""
            SELECT DISTINCT m[1] AS w
            FROM products p, LATERAL regexp_matches(lower(p.name), '[a-z]{4,}', 'g') m
            WHERE p.is_active = TRUE
        """)
        vocab = {r["w"] for r in rows}
    except Exception as e:  # noqa: BLE001 — typo tolerance is a bonus, not a feature gate
        print(f"search vocabulary unavailable, typo tolerance off: {e}")
        return set()
    if not vocab:
        return set()
    _SQL_VOCAB_CACHE.update(ts=_time.time(), vocab=vocab)
    if _FACET_CACHE["facets"]:
        _save_facets_to_disk()  # ride along, so a restart keeps the vocabulary too
    return vocab


# A term is only ever fuzzy-matched when it is a *word*. Item numbers are
# identifiers, not spellings: correcting N590321-2 by one edit hands the user a
# different product, so anything carrying a digit or a separator stays exact.
_WORD_RE = re.compile(r"^[a-z]{4,}$")


async def _expand_terms(conn, terms: list[str]) -> tuple[list[tuple[str, list[str]]], bool]:
    """Map each query term to the spellings worth matching.

    Returns (term, variants) pairs — variants always lead with the term itself —
    and whether anything was actually corrected. Only the minimal-edit group is
    taken, so "wreathe" corrects to "wreath" and not also to "weather".
    """
    words = [t for t in terms if _WORD_RE.match(t)]
    if not words:
        return [(t, [t]) for t in terms], False
    vocab = await _load_sql_vocab(conn)
    if not vocab:
        return [(t, [t]) for t in terms], False
    expanded = False
    out: list[tuple[str, list[str]]] = []
    for t in terms:
        variants = [t]
        if _WORD_RE.match(t) and t not in vocab:
            near = [w for w in _fuzzy_variants(t, vocab, 2 if len(t) >= 7 else 1) if w != t]
            if near:
                variants += near[:8]  # a huge correction set would be noise, not recall
                expanded = True
        out.append((t, variants))
    return out, expanded


async def _search_products_db(conn, *, search, price_min, price_max,
                              supplier_ids, ids, limit, offset, build_facets,
                              categories=None, colors=None, sizes=None, finishes=None,
                              availability=None, product_types=None):
    """Answer a faceted catalog search from Postgres.

    This is a full replacement for the in-memory index, not just a warm-up
    fallback: it applies every filter the sidebar can set, returns the same
    drill-down facets, and tolerates typos. It exists because the index holds
    ~892 MB resident and OOM-kills the web service.
    """
    lim = max(1, min(limit, 500))
    off = max(0, offset)
    terms = [w for w in (search or "").lower().split() if w]

    sel: dict = {}
    for dim, raw in (("categories", categories), ("colors", colors),
                     ("finishes", finishes), ("availability", availability),
                     ("product_types", product_types)):
        values = _csv_list(raw)
        if values:
            sel[dim] = values
    size_values = []
    for value in _csv_list(sizes):
        try:
            size_values.append(Decimal(value))
        except (InvalidOperation, ValueError):
            continue  # a label the catalog never produced — ignore, don't 500
    if size_values:
        sel["sizes"] = size_values
    sup = [int(x) for x in _csv_list(supplier_ids) if x.isdigit()]
    if sup:
        sel["suppliers"] = sup
    id_list = [int(x) for x in _csv_list(ids) if x.lstrip("-").isdigit()] if ids is not None else None

    has_pf, has_blob = (await _facet_source_probe(conn)
                        if (sel or build_facets or terms) else (False, False))
    exprs = _facet_exprs(has_pf)
    item_ref = {"cat": exprs["cat"], "cfam": exprs["cfam"], "szn": exprs["szn"],
                "fin": exprs["fin"], "avail": exprs["avail"], "ptype": exprs["ptype"],
                "sid": exprs["sid"], "cfam_kind": exprs["cfam_kind"]}
    # Only reach for product_facets when a dimension it covers is being filtered
    # on, or when the keyword has to search its blob. On a plain browse the extra
    # join would only get in the way of the index-ordered scan.
    blob_search = bool(has_blob and terms)
    item_join = (exprs["join"] if (has_pf and (set(sel) & set(_PF_DIMS) or blob_search))
                 else "")

    def _build(term_variants):
        """WHERE clauses + args for a given keyword expansion.

        `base` is everything that is not a facet dimension (it narrows the facet
        counts too); `dim_where` is the user's facet selections, which apply to
        the result rows but are held out of their own facet's count.
        """
        args: list = []

        def add(v):
            args.append(v)
            return f"${len(args)}"

        base: list[str] = []
        scores: list[str] = []
        for term, variants in term_variants:
            alts = []
            for v in variants:
                ph = add(f"%{v}%")
                cols = [f"p.name ILIKE {ph}", f"p.description ILIKE {ph}",
                        f"p.supplier_sku ILIKE {ph}"]
                if blob_search:
                    # The flattened raw_data values the index folds into its blob
                    # — material, collection, type, UPC and so on. Without this
                    # the SQL path loses ~30-70% of the rows on a keyword query.
                    cols.append(f"pf.search_blob ILIKE {ph}")
                alts.append("(" + " OR ".join(cols) + ")")
            base.append(f"({' OR '.join(alts)})")
            if len(alts) > 1:
                scores.append(f"({alts[0]})::int")  # alts[0] is the literal spelling
        if price_min is not None:
            base.append(f"p.current_price >= {add(price_min)}")
        if price_max is not None:
            base.append(f"p.current_price <= {add(price_max)}")
        if id_list is not None:
            base.append(f"p.id = ANY({add(id_list)}::int[])")

        base_args = list(args)
        dim_where = [_dim_predicate(d, item_ref, add(v)) for d, v in sel.items()]
        return base, base_args, dim_where, args, scores

    def _where(conds: list, scoped: bool) -> str:
        """AND the conditions, adding is_active only where it isn't implied.

        product_facets holds active products and nothing else, so once it is
        joined, repeating `p.is_active` only gives the planner a reason to start
        from products — measured as a merge join walking products_pkey over
        160k rows (13 s) instead of a bitmap scan of the 52 MB projection.
        """
        parts = (conds if scoped else ["p.is_active = TRUE", *conds])
        return " AND ".join(parts) if parts else "TRUE"

    # ORDER BY name LIMIT 48 is served by idx_products_active_name, which is what
    # makes a browse ~0.3 s instead of sorting 166k rows. But that plan walks the
    # catalog in name order until it has found 48 matches, so it collapses when
    # the filters are selective: "ornament" AND colour=Red matches 106 rows out
    # of 166k and the same query measured 44 s. Fetching the matches first and
    # sorting those (an OFFSET 0 optimisation fence) measured 5.4 s on the same
    # data — and the reverse on an unfiltered browse, where the fence would mean
    # materialising the whole catalog. Neither plan is right for both, and the
    # planner cannot tell them apart, so we choose: one filter is assumed
    # unselective enough for the index walk, two or more are not.
    narrowers = (bool(terms) + (price_min is not None or price_max is not None)
                 + (id_list is not None) + len(sel))
    fenced = narrowers >= 2

    async def _page(term_variants):
        conds, base_args, dim_where, args, scores = _build(term_variants)
        wsql = _where([*conds, *dim_where], scoped=bool(item_join))
        base_where = _where(conds, scoped=has_pf)
        # Exact spellings rank ahead of corrected ones. Only sorted by relevance
        # when something actually was corrected — otherwise every row scores the
        # same and the name ordering is all that matters.
        rank = f"({' + '.join(scores)})" if scores else None
        # The index sorts on Python's name.lower(), i.e. raw codepoints. This
        # database is en_US.UTF-8, whose collation ignores leading punctuation:
        # it puts '.25-.5" Green Putka Pods' where the index puts
        # '"Caroline\'s Treasures'. Two orders means offset pagination breaks
        # the moment the backend flips paths — duplicates and skipped rows — so
        # SQL has to reproduce the codepoint order exactly, NULL names included.
        name_key = lambda t: f"""lower(coalesce({t}.name, '')) COLLATE "C" """
        select = f"""SELECT p.id, p.name, s.name AS supplier_name, p.supplier_sku,
                   p.current_price, p.image_urls, p.photo_url, p.raw_data
                   {(', ' + rank + ' AS _rank') if rank else ''}
            FROM products p {item_join} LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE {wsql}"""
        if fenced:
            order = (f"ORDER BY t._rank DESC, {name_key('t')}" if rank
                     else f"ORDER BY {name_key('t')}")
            sql = f"SELECT * FROM ({select} OFFSET 0) t {order} LIMIT {lim} OFFSET {off}"
        else:
            order = (f"ORDER BY {rank} DESC, {name_key('p')}" if rank
                     else f"ORDER BY {name_key('p')}")
            sql = f"{select} {order} LIMIT {lim} OFFSET {off}"
        rows = await conn.fetch(sql, *args)
        return rows, wsql, args, base_where, base_args

    async def _count(wsql, args) -> tuple[int, bool]:
        # COUNT(*) OVER() used to ride along with the page, but it forces the
        # planner to materialise every matching row just to number them - 13s+
        # once the catalog passed 166k rows. Counted separately with a cap, so an
        # unfiltered browse never pays for a full scan.
        capped = int(await conn.fetchval(f"""
            SELECT COUNT(*) FROM (
                SELECT 1 FROM products p {item_join} WHERE {wsql} LIMIT {_DB_COUNT_CAP + 1}
            ) x
        """, *args) or 0)
        return (_DB_COUNT_CAP, True) if capped > _DB_COUNT_CAP else (capped, False)

    term_variants = [(t, [t]) for t in terms]
    rows, wsql, args, base_where, base_args = await _page(term_variants)

    # Typo tolerance, second attempt only. A correctly spelled query fills its
    # page and stops here, paying nothing at all for this; only a query that came
    # back nearly empty goes looking for near spellings, and even then only for
    # terms that are words. A short page is proof the match set is small, so this
    # decision costs no extra query.
    if terms and len(rows) < lim and off + len(rows) < _FUZZY_MIN_HITS:
        term_variants, expanded = await _expand_terms(conn, terms)
        if expanded:
            rows, wsql, args, base_where, base_args = await _page(term_variants)

    facets, exact_total = None, None
    if build_facets:
        facets, exact_total = await _facets_for(conn, exprs, base_where, base_args, sel,
                                                unfiltered=not (terms or price_min is not None
                                                                or price_max is not None
                                                                or id_list is not None))
    if exact_total is not None:
        # The facet pass already counted this exact result set, so the capped
        # count would be a second scan for a worse answer. Skipping it also
        # dodges a planner trap: LIMIT inside the count makes it favour a
        # cheap-startup merge join that walks the products PK index (32s
        # measured) instead of the index the page itself uses.
        total, total_is_capped = exact_total, False
    else:
        total, total_is_capped = await _count(wsql, args)

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
            "image_urls": imgs[:6],  # same cap the index applies, so the payloads match
            "raw_data": {"normalized": {"color": norm.get("color"), "finish": norm.get("finish"),
                                        "size_in": norm.get("size_in"), "class": norm.get("class")}},
        })

    resp = {"items": items, "total": total or 0, "limit": limit, "offset": offset,
            # Only a real warm-up when an index is coming. With SEARCH_INDEX_ENABLED=0
            # this IS the search, and a permanent "still loading" hint would be a lie.
            "warming": _INDEX_ENABLED, "total_is_capped": total_is_capped}
    if build_facets:
        resp["facets"] = facets if facets is not None else _empty_facets()
    return resp


async def _facets_for(conn, exprs, base_where, base_args, sel,
                      *, unfiltered: bool) -> tuple[dict, Optional[int]]:
    """The sidebar for this request, computed as cheaply as it can be.

    The trick that makes selection-only browsing affordable: a dimension is
    counted ignoring its OWN selection, so when there is no search/price/id
    filter and no OTHER dimension is selected, its counts are — by definition —
    the unfiltered baseline. Clicking one colour therefore reads the colour list
    straight from cache and only re-counts the other six, and an untouched
    browse opens no facet query at all.
    """
    baseline = _FACET_CACHE["facets"] if _facets_fresh() else None
    if baseline is None:
        _ensure_facets_building()
        # A cold process would otherwise serve one sidebar-less browse. Wait a
        # bounded moment for the build rather than either blocking on the full
        # pass or guaranteeing an empty first page; shielded, so timing out here
        # leaves the build running for the next request.
        task = _facet_build_task
        if task is not None and _FACET_COLD_WAIT > 0:
            try:
                await _asyncio.wait_for(_asyncio.shield(task), _FACET_COLD_WAIT)
            except Exception:  # noqa: BLE001 — timeout or a failed build; both fine
                pass
            if _facets_fresh():
                baseline = _FACET_CACHE["facets"]

    selected = {d for d in _FACET_DIMS if sel.get(d)}
    from_cache, need = [], []
    for dim in _FACET_DIMS:
        others = selected - {dim}
        if unfiltered and not others:
            from_cache.append(dim)
        else:
            need.append(dim)

    # A baseline dimension is served from cache or not at all — never by running
    # the full-catalog pass inline, which is the 15 s the background build exists
    # to keep off the request path. One browse with a thin sidebar beats a browse
    # that times out.
    facets = {d: (baseline[d] if baseline else []) for d in from_cache}
    exact_total: Optional[int] = None
    if not need:
        # Nothing selected and no search: the whole answer is the baseline. The
        # total deliberately still comes from the capped count — deriving it from
        # the cache instead would make the same request report 166,029 warm and
        # "5000+" cold, and a number that moves with cache state is worse than a
        # number that is honestly approximate.
        return facets, None
    sql, args = _facet_query(exprs, base_where, base_args, sel, tuple(need))
    try:
        rows = await conn.fetch(sql, *args)
    except Exception as e:  # noqa: BLE001 — a broken sidebar must not 500 the catalog
        print(f"facet query failed: {e}")
        rows = []
    computed, exact_total = _shape_facets(rows, tuple(need))
    facets.update(computed)
    for dim in _FACET_DIMS:
        facets.setdefault(dim, [])
    return facets, exact_total


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
                categories=categories, colors=colors, sizes=sizes, finishes=finishes,
                availability=availability, product_types=product_types,
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
            # most_common() leaves equal-count suppliers in arbitrary order, which
            # made this the one dimension whose ordering was not reproducible.
            # Tie-break on the name, like every other dimension does.
            "suppliers": [
                {"value": sup_names.get(sid, str(sid)), "id": sid, "count": n}
                for sid, n in sorted(
                    counters["suppliers"].items(),
                    key=lambda kv: (-kv[1], str(sup_names.get(kv[0], kv[0])).lower()))[:80]
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
