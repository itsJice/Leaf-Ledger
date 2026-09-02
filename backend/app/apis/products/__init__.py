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
    """Sidebar filter vocabulary, served from the facet baseline cache.

    This used to run seven full-table JSONB aggregates per call (16-19s EACH on
    this instance). The Catalog Search page calls it on every mount, so a few
    concurrent users saturated the instance's IO and every other query - search
    included - queued behind it: the app looked completely down. The facet
    baseline computes the same numbers in one pass and is cached in memory and
    on disk; suppliers/countries are cheap small-table reads."""
    conn = await get_conn()
    try:
        if not _facets_fresh():
            await _build_unfiltered_facets(conn)
        facets = (_FACET_CACHE["facets"] or {}) if _facets_fresh() else {}
        def opts(dim):
            return [FilterOption(value=str(e["value"]), count=int(e["count"]),
                                 id=e.get("id")) for e in facets.get(dim, [])]
        suppliers = opts("suppliers")
        if not suppliers:
            rows = await conn.fetch("""SELECT s.id, s.name AS value, COUNT(f.product_id)::int AS count
                FROM suppliers s LEFT JOIN product_facets f ON f.supplier_id = s.id
                GROUP BY s.id, s.name ORDER BY count DESC""")
            suppliers = [FilterOption(value=r["value"], count=r["count"], id=r["id"]) for r in rows]
        countries = await conn.fetch("""SELECT COALESCE(NULLIF(country_of_origin,''),'Unknown') AS value,
                COUNT(*)::int AS count FROM products WHERE is_active
                GROUP BY 1 ORDER BY count DESC LIMIT 40""")
        return ProductFilterMetadata(
            generated_at=datetime.utcnow().isoformat() + "Z",
            categories=opts("categories"), suppliers=suppliers,
            product_types=opts("product_types"),
            countries=[FilterOption(value=r["value"], count=r["count"]) for r in countries],
            colors=opts("colors"), availability=opts("availability"),
            finishes=opts("finishes"), sizes=opts("sizes"),
        )
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

# ─── Catalog search (SQL) ─────────────────────────────────────────────────────
# Served by _search_products_db over product_facets + trigram indexes. The old
# in-memory index (~892 MB resident, OOM-killed the web service, re-read the
# catalog on every restart) was deleted after the SQL path matched it on the
# parity matrix (20 queries x 2 paths, 0 defects). These caches hold the cheap
# leftovers: the unfiltered facet baseline and the typo-correction vocabulary.
# The catalog only changes when someone runs an import.
_SEARCH_TTL = int(os.environ.get("SEARCH_INDEX_TTL", 24 * 3600))

# Facet baseline + vocabulary persist here so a restart re-reads nothing. Point
# SEARCH_INDEX_CACHE_DIR at a persistent volume in production.
_SEARCH_DISK_CACHE = os.environ.get("SEARCH_INDEX_CACHE_DIR") or os.path.join(
    tempfile.gettempdir(), "leaf-ledger-index"
)

# Warm-up fallback only: how far we will count before reporting "N+".
_DB_COUNT_CAP = 5000

# The in-memory index takes ~30s to build (longer on a small CPU). Until it's
# ready — on a fresh boot or right after a deploy — search falls back to the
# database so the catalog is never empty. These coordinate a single background
# build: concurrent builds would each hold the whole index in memory at once and
# risk an out-of-memory kill, so only one ever runs.
import asyncio as _asyncio



























_VOCAB_CACHE: dict = {"ts": -1.0, "vocab": None}




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
# 15s covers the measured worst case for the pf-only baseline on cold shared
# buffers (9.3s); after the very first boot the disk cache answers instead. One
# bounded wait on the first-ever browse beats guaranteeing it an empty sidebar.
_FACET_COLD_WAIT = float(os.environ.get("SEARCH_FACET_COLD_WAIT", 15))
# Exact hits below this make a query look like a typo and unlock fuzzy matching.
_FUZZY_MIN_HITS = int(os.environ.get("SEARCH_FUZZY_MIN_HITS", 5))
# Typo-correction vocabulary, built by the database (see _load_sql_vocab).
_SQL_VOCAB_CACHE: dict = {"ts": 0.0, "vocab": None}

# migrations/006 adds `product_facets`: a narrow, trigger-maintained projection
# of the facet values (52 MB against the 500 MB products table). Reading a colour
# or a category from it costs an index lookup instead of detoasting raw_data for
# 166k rows. The JSONB expressions below stay correct if it is absent, so this
# file works on either schema and just gets faster when the migration lands.
_FACET_SOURCE: dict = {"probed": False, "has_pf": False, "has_blob": False,
                       "has_ident": False}
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

    Also records whether ident_norm is present (migrations/011) — read through
    `_has_ident()` rather than returned, so every existing caller is unchanged.

    `search_blob` is the flattened raw_data text the in-memory index searches.
    Until it exists the SQL path can only match name/description/sku, which is
    the one real recall gap between the two paths; the moment the column and its
    trigram index land, this picks it up with no further code change.
    """
    if _FACET_SOURCE["probed"]:
        return _FACET_SOURCE["has_pf"], _FACET_SOURCE["has_blob"]
    has = blob = ident = False
    try:
        row = await conn.fetchrow("""
            SELECT to_regclass('public.product_facets') AS t,
                   EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = 'product_facets'
                              AND column_name = 'search_blob') AS blob,
                   EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = 'product_facets'
                              AND column_name = 'ident_norm') AS ident""")
        has = bool(row and row["t"])
        blob = has and bool(row["blob"])
        ident = has and bool(row["ident"])
    except Exception as e:  # noqa: BLE001 — a failed probe just means "use raw_data"
        print(f"facet source probe failed, using raw_data paths: {e}")
        ident = False
    _FACET_SOURCE.update(probed=True, has_pf=has, has_blob=blob, has_ident=ident)
    print(f"facets reading from {'product_facets' if has else 'products.raw_data'}"
          f"{'; keyword search includes search_blob' if blob else ''}"
          f"{'; style numbers matched punctuation-blind' if ident else ''}")
    return has, blob


def _has_ident() -> bool:
    """Whether product_facets.ident_norm is available (migrations/011)."""
    return bool(_FACET_SOURCE.get("has_ident"))


def _facet_exprs(has_pf: bool, has_new_cols: bool = False) -> dict:
    """SQL for each faceted value, keyed by the short name used everywhere below.

    These must agree value-for-value with what the retired in-memory index
    used to serve, since the UI contract was pinned against it. Note `categories` reads
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
        "sid": "p.supplier_id",
    })
    exprs["pf_dims"] = _PF_DIMS
    if has_pf and has_new_cols:
        # migrations/007 precomputes product_type into product_facets.
        # PRODUCT_TYPE_SQL falls through to raw_data on the 82% of rows where
        # style is empty, and that single expression was why the unfiltered
        # baseline cost ~59s: it detoasted the whole catalog. Reading the
        # precomputed column keeps the baseline inside the cold-start wait,
        # which is what makes the first browse of a fresh process show a
        # sidebar instead of an empty one.
        exprs.update({
            "ptype": "NULLIF(pf.product_type, '')",
            "avail": f"({_availability_bucket_sql('btrim(pf.availability)')})",
            # These two now read pf.*, so any query filtering on them must join.
            "pf_dims": _PF_DIMS + ("product_types", "availability"),
        })
    else:
        exprs.update({
            "ptype": f"NULLIF({PRODUCT_TYPE_SQL}, '')",
            "avail": f"({_availability_bucket_sql('btrim(p.availability)')})",
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

    # Whenever product_facets is joined, its supplier_id is the same value as
    # products' — reading it from pf is what lets a pass whose every column
    # lives in the projection skip the 660 MB products heap altogether.
    exprs = dict(exprs, sid="pf.supplier_id") if exprs["join"] else exprs

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
        pf_only = bool(exprs["join"]) and dim in exprs.get("pf_dims", _PF_DIMS)
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

    # The unfiltered baseline (and any pass whose dimensions all live in the
    # projection) never reads a products column once sid comes from pf. Scanning
    # the 52 MB projection instead of joining the 660 MB heap took the cold
    # baseline from ~30s to inside the cold-start wait — which is the difference
    # between the first browse of a fresh process having a sidebar and not.
    fragments = " ".join([*select_cols, where_sql, lateral])
    if exprs["join"] and not _re.search(r"\bp\.", fragments):
        from_sql = "FROM pf_sel pf" if pf_cte else "FROM product_facets pf"
    else:
        from_sql = f"FROM products p {join_sql}"

    sql = f"""
        WITH {pf_cte}base AS MATERIALIZED (
            SELECT {', '.join(select_cols)}
            {from_sql}
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


# A Postgres advisory lock key, so the guard holds DB-wide rather than only
# within one Python process. asyncio.Lock only ever coordinated one process:
# if Render runs (or scales to) more than one instance, each boots with its own
# empty local disk cache — an ephemeral filesystem, not shared — and every one
# of them independently decided the baseline was cold and launched its own
# ~15-50s aggregate at once. Ten of those piling up on one small instance
# queued out every other query behind them, including plain browsing, which is
# what "catalog search isn't working, nothing populates" looks like from a
# user's chair.
_FACET_LOCK_KEY = int.from_bytes(hashlib.sha1(b"ll_facet_baseline").digest()[:8], "big", signed=True)


async def _build_unfiltered_facets(conn) -> Optional[dict]:
    """The no-search, nothing-selected counts. The one pass nothing can narrow
    (~15 s, more under contention), so it is computed once and cached hard —
    memory plus disk — and guarded DB-wide so only one process anywhere ever
    runs it at a time. A process that loses the race does not fall back to
    running its own copy: it returns None immediately, at the cost of one
    request seeing an empty sidebar rather than adding a second expensive query
    on top of the one already running.
    """
    got_lock = await conn.fetchval("SELECT pg_try_advisory_lock($1)", _FACET_LOCK_KEY)
    if not got_lock:
        print("unfiltered facet build already running elsewhere — skipping")
        return None
    try:
        if _facets_fresh():  # someone else finished while we waited for the lock
            return _FACET_CACHE["facets"]
        has_pf, has_blob = await _facet_source_probe(conn)
        exprs = _facet_exprs(has_pf, has_blob)
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
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", _FACET_LOCK_KEY)


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


# The other side of that coin. An identifier stays exact in *spelling*, but its
# punctuation is not part of its identity: vendors write B1670-BU, ROT.20.TA and
# X1923/75, and nobody quoting one from an invoice reproduces the separators
# reliably. Stripping them from both sides matches the same product without ever
# matching a different one — unlike an edit-distance correction, which turns
# N592522DCV into N592522DA, a different colour of the same item.
_IDENT_STRIP_RE = re.compile(r"[^a-z0-9]+")


def _ident_norm(term: str) -> str:
    """Lowercase, alphanumerics only — mirrors public.product_facets_ident()."""
    return _IDENT_STRIP_RE.sub("", term.lower())


def _looks_like_identifier(term: str) -> bool:
    """Whether a term is worth checking against the identifier column.

    Any digit makes it a candidate: style numbers are alphanumeric (B1670-BU,
    4611386, N592522DCV) while product words are not. Two characters is too
    short to be a useful identifier probe and would match most of the catalog.
    """
    n = _ident_norm(term)
    return len(n) >= 3 and any(ch.isdigit() for ch in n)


# How close a style number has to be before it is worth offering. 0.4 keeps
# N592522DCX -> N592522DCV (0.69) while dropping the long tail that shares a
# couple of trigrams and nothing else.
_SIMILAR_MIN = float(os.environ.get("SEARCH_SIMILAR_MIN", 0.4))

# Words use a looser trigram gate, because trigrams punish the commonest typo
# there is. Swapping two letters ("ornamnet") wrecks four trigrams at once, and
# so scores "ornament" at 0.385 -- below a 0.4 cut, while the vendor typo
# "ornamanet" sails through at 0.58. The gate only collects candidates cheaply
# off the index; the pick is made by edit distance below, where a swap is one
# edit like any other.
_WORD_SIMILAR_MIN = float(os.environ.get("SEARCH_WORD_SIMILAR_MIN", 0.3))
_WORD_CANDIDATES = 15
# A word the catalog uses is spelled fine -- unless it is a vendor's own typo of
# something far more common. "garlnd" appears 83 times and "garland" 3,949; the
# person who typed "garlnd" wanted garland. Below this ratio the word stands.
_KNOWN_RATIO = int(os.environ.get("SEARCH_KNOWN_RATIO", 20))
_MAX_EDITS = 2


def _edit_distance(a: str, b: str) -> int:
    """Optimal string alignment distance: insert, delete, substitute, or swap
    two adjacent letters. Plain Levenshtein charges a swap as two edits, which
    is how "ornamnet" ended up nearer "ornamanet" than "ornament"."""
    la, lb = len(a), len(b)
    prev2: list[int] = []
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[lb]


def _rank_corrections(term: str, candidates: list[tuple[str, int]],
                      self_freq: Optional[int], *, skip_known: bool,
                      keep: int = 4) -> list[str]:
    """Order near spellings of `term`: fewest edits first, then the spelling the
    catalog uses most. Frequency breaks ties rather than leading, so a common
    word never displaces a closer rare one, and a vendor's one-off typo never
    beats the real word it is one edit away from.

    `candidates` are (word, freq) from the trigram pass; `self_freq` is how
    often `term` itself appears in product names, or None if never.
    """
    max_edits = _MAX_EDITS if len(term) > 5 else 1  # two edits on a short word is a different word
    scored = []
    for word, freq in candidates:
        if word == term:
            continue
        d = _edit_distance(term, word)
        if d <= max_edits:
            scored.append((d, -freq, word))
    if not scored:
        return []
    if skip_known and self_freq is not None:
        best_freq = max(-f for _, f, _ in scored)
        if best_freq < _KNOWN_RATIO * self_freq:
            return []
    scored.sort()
    return [w for _, _, w in scored[:keep]]


async def _correct_terms(conn, terms: list[str], *, skip_known: bool = True) -> dict:
    """Near spellings for each term, from search_vocab. One round trip.

    Corrections come from the 18k-row dictionary, never from the product table:
    matching a typo against 166k product names measured 3.4-3.9 s cold, against
    the dictionary ~110 ms. Terms that are already real words are left alone, and
    identifiers are skipped entirely — see _WORD_RE for why an edit-distance
    correction is the wrong tool for a style number.

    skip_known controls what "worth correcting" means. True leaves a term the
    catalog already uses alone -- unless it is a vendor's own typo of something
    far more common (see _KNOWN_RATIO), which is the case a buyer actually hits:
    "ribon" is in two product names, "ribbon" in six thousand. False corrects
    everything it can, and is only for callers that want every neighbour.

    The trigram pass is a cheap, index-driven way to collect candidates; the
    pick among them is _rank_corrections, by edit distance. Trigrams alone chose
    badly in both directions: "ornamnet" -> "ornamanet" (a vendor typo) and
    "burlap" -> "burl" (a real word, replaced by a shorter one).
    """
    words = [t for t in terms if _WORD_RE.match(t)]
    if not words:
        return {}
    try:
        rows = await conn.fetch(
            """
            SELECT t.term, v.word, v.freq
              FROM unnest($1::text[]) AS t(term)
              JOIN LATERAL (
                   SELECT word, freq
                     FROM search_vocab
                    WHERE word %% t.term
                      AND similarity(word, t.term) >= $2
                    ORDER BY similarity(word, t.term) DESC, freq DESC
                    LIMIT $3
              ) v ON TRUE
            """.replace("%%", "%"),
            words, _WORD_SIMILAR_MIN, _WORD_CANDIDATES,
        )
    except Exception as e:  # noqa: BLE001 — suggestions are a bonus, not a gate
        print(f"search_vocab unavailable, approximate matching off: {e}")
        return {}
    cands: dict[str, list[tuple[str, int]]] = {}
    self_freq: dict[str, int] = {}
    for r in rows:
        if r["word"] == r["term"]:
            self_freq[r["term"]] = r["freq"]  # the term is itself a catalog word
        else:
            cands.setdefault(r["term"], []).append((r["word"], r["freq"]))
    out: dict = {}
    for term, near in cands.items():
        ranked = _rank_corrections(term, near, self_freq.get(term), skip_known=skip_known)
        if ranked:
            out[term] = ranked
    return out


async def _similar_identifiers(conn, terms: list[str], limit: int = 6) -> list:
    """Style numbers close to a typed one — as suggestions, never substitutions.

    Deliberately separate from the word path. N592522DCV and N592522DA are
    different colours of the same item and score 0.692 against 0.615, so nothing
    here is safe to fold silently into results; the caller shows these with the
    identifier visible so a person decides.
    """
    idents = [t for t in terms if _looks_like_identifier(t)]
    if not idents or not _has_ident():
        return []
    try:
        # LATERAL with the LIMIT *inside* it. The obvious shape -- join, then
        # DISTINCT ON (supplier_sku) ORDER BY sim -- has to materialise and sort
        # every trigram candidate before it can discard any: 39.5 s measured.
        # Bounding each term's scan lets idx_products_sku_trgm drive it instead:
        # 0.24 s on the same query.
        rows = await conn.fetch(
            """
            SELECT v.id, v.supplier_sku, v.name, v.sim
              FROM unnest($1::text[]) AS t(term)
              JOIN LATERAL (
                   SELECT p.id, p.supplier_sku, p.name,
                          similarity(p.supplier_sku, t.term) AS sim
                     FROM products p
                    WHERE p.is_active
                      AND p.supplier_sku %% t.term
                      AND similarity(p.supplier_sku, t.term) >= $3
                    ORDER BY similarity(p.supplier_sku, t.term) DESC
                    LIMIT $2
              ) v ON TRUE
            """.replace("%%", "%"),
            idents, limit, _SIMILAR_MIN,
        )
    except Exception as e:  # noqa: BLE001
        print(f"identifier suggestions unavailable: {e}")
        return []
    return [{"id": r["id"], "supplier_sku": r["supplier_sku"],
             "name": r["name"], "similarity": round(float(r["sim"]), 3)}
            for r in sorted(rows, key=lambda r: -r["sim"])]


async def _expand_terms(conn, terms: list[str]) -> tuple[list[tuple[str, list[str]]], bool]:
    """Map each query term to the spellings worth matching.

    Returns (term, variants) pairs — variants always lead with the term itself —
    and whether anything was actually corrected. Only the minimal-edit group is
    taken, so "wreathe" corrects to "wreath" and not also to "weather".
    """
    words = [t for t in terms if _WORD_RE.match(t)]
    if not words:
        return [(t, [t]) for t in terms], False

    # Corrections come from search_vocab, which carries an occurrence count and
    # so can prefer the spelling people actually use. Edit distance alone could
    # not: "wreathe" is one edit from both "wreath" and "wreathx" — the latter a
    # typo sitting in one vendor's own product name — and with nothing to break
    # the tie the junk word won, so a search for "wreathe" reported itself as a
    # search for "wreathx". Frequency settles it.
    corrections = await _correct_terms(conn, terms)
    if not corrections:
        return [(t, [t]) for t in terms], False

    expanded = False
    out: list[tuple[str, list[str]]] = []
    for t in terms:
        variants = [t]
        near = corrections.get(t)
        if near:
            variants += near[:8]  # a huge correction set would be noise, not recall
            expanded = True
        out.append((t, variants))
    return out, expanded


async def _search_products_db(conn, *, search, price_min, price_max,
                              supplier_ids, ids, limit, offset, build_facets,
                              categories=None, colors=None, sizes=None, finishes=None,
                              availability=None, product_types=None,
                              exclude_ids=None):
    """Answer a faceted catalog search from Postgres.

    This is a full replacement for the in-memory index, not just a warm-up
    fallback: it applies every filter the sidebar can set, returns the same
    drill-down facets, and tolerates typos. It exists because the index holds
    ~892 MB resident and OOM-kills the web service.
    """
    lim = max(1, min(limit, 500))
    off = max(0, offset)
    terms = [w for w in (search or "").lower().split() if w]
    # Spellings the caller has already shown. Used by the approximate pass so
    # its band contains only products the exact pass did not already return.
    # Rows the caller has already put on screen. An id list, deliberately: the
    # first attempt at this negated the original query as a predicate, which
    # cost 6.6 s against 760 ms for the same search without it, because NOT
    # (blob ILIKE ...) cannot use the trigram index and forces a scan. It also
    # over-excluded — "wreath" subsumes "wreaths" under substring matching, so
    # the band came back empty. A bounded array of ids the client actually
    # rendered is both cheap and exactly the question being asked.
    ex_ids = [int(x) for x in _csv_list(exclude_ids) if str(x).lstrip("-").isdigit()] \
        if exclude_ids else []

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
    exprs = _facet_exprs(has_pf, has_blob)
    item_ref = {"cat": exprs["cat"], "cfam": exprs["cfam"], "szn": exprs["szn"],
                "fin": exprs["fin"], "avail": exprs["avail"], "ptype": exprs["ptype"],
                "sid": exprs["sid"], "cfam_kind": exprs["cfam_kind"]}
    # Only reach for product_facets when a dimension it covers is being filtered
    # on, or when the keyword has to search its blob. On a plain browse the extra
    # join would only get in the way of the index-ordered scan.
    blob_search = bool(has_blob and terms)
    # Identifier terms are matched against product_facets.ident_norm, so they
    # need the same join even in the (unlikely) case that search_blob is absent.
    ident_search = bool(has_pf and _has_ident()
                        and any(_looks_like_identifier(t) for t in terms))
    item_join = (exprs["join"]
                 if (has_pf and (set(sel) & set(exprs.get("pf_dims", _PF_DIMS))
                                 or blob_search or ident_search))
                 else "")
    # When product_facets is in play it is the *driving* table: the candidate
    # set is found, filtered and sorted there, and products is joined only for
    # the page that comes out (see _page). Everything in the WHERE therefore
    # names pf columns, so the inner query never touches products at all.
    # The one exception is a price bound, which only products carries.
    pf_first = bool(item_join)
    id_col = "pf.product_id" if pf_first else "p.id"
    if pf_first:
        item_ref["sid"] = "pf.supplier_id"
    needs_products = (not pf_first) or price_min is not None or price_max is not None

    def _build(term_variants, extra_ex=None):
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
                if blob_search:
                    # search_blob is built from name + supplier_sku + description
                    # + supplier name + the flattened raw_data values (see the
                    # product_facets_blob trigger), so it is a strict superset of
                    # matching those three columns separately - keeping the
                    # per-column OR alongside it forced Postgres to evaluate the
                    # filter across BOTH products and product_facets post-join,
                    # which no index can satisfy: a plain keyword query fell back
                    # to a parallel seq scan of both tables (289 MB+ read, spilling
                    # to disk) instead of the trigram index, 18.5s measured for one
                    # word. search_blob alone lets the planner use the GIN index:
                    # 1.9s measured on the same query.
                    cols = [f"pf.search_blob ILIKE {ph}"]
                else:
                    cols = [f"p.name ILIKE {ph}", f"p.description ILIKE {ph}",
                            f"p.supplier_sku ILIKE {ph}"]
                alts.append("(" + " OR ".join(cols) + ")")

            parts = list(alts)
            if ident_search and _looks_like_identifier(term):
                # Same identifier, different punctuation. OR'd in, so this only
                # ever adds recall — a spelling that already matched still does.
                n = _ident_norm(term)
                ph_ident = add('%' + n + '%')
                parts.append(f"pf.ident_norm LIKE {ph_ident}")
                # And rank it: the product whose style number IS the query comes
                # before one that merely contains it (B1670 inside B1670703),
                # and both come before an incidental keyword hit. Only identifier
                # queries add a score, and those match few rows, so the cost of
                # sorting on it instead of the name index stays negligible.
                #
                # The score reuses ph_ident rather than binding its own copy:
                # `scores` is spliced into the SELECT while the count query is
                # built from `base` alone, so a placeholder that appears only in
                # a score would leave the count with more arguments than its SQL
                # references. The regex is inlined instead of bound for the same
                # reason, and is injection-safe because _ident_norm() has already
                # reduced the term to [a-z0-9].
                scores.append(
                    f"(CASE WHEN pf.ident_norm ~ '(^| ){n}( |$)' THEN 8 "
                    f"WHEN pf.ident_norm LIKE {ph_ident} THEN 4 ELSE 0 END)")
            base.append(f"({' OR '.join(parts)})")
            if len(alts) > 1:
                # alts[0] is the literal spelling. COALESCE matters: a NULL
                # description or sku makes the OR-group NULL, not false, and
                # ORDER BY rank DESC puts NULLs FIRST - every NULL-description
                # row jumped ahead of correctly-ranked ones, which is exactly
                # the page swap the parity gate caught on the typo query.
                scores.append(f"COALESCE(({alts[0]})::int, 0)")
        ex = [*ex_ids, *(extra_ex or [])]
        if ex:
            base.append(f"{id_col} <> ALL({add(ex)}::int[])")
        if price_min is not None:
            base.append(f"p.current_price >= {add(price_min)}")
        if price_max is not None:
            base.append(f"p.current_price <= {add(price_max)}")
        if id_list is not None:
            base.append(f"{id_col} = ANY({add(id_list)}::int[])")

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

    async def _page(term_variants, *, lim_=None, off_=None, extra_ex=None):
        l, o = (lim if lim_ is None else lim_), (off if off_ is None else off_)
        conds, base_args, dim_where, args, scores = _build(term_variants, extra_ex)
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
        if pf_first:
            # Find, filter and sort in product_facets alone -- its rows are a
            # tenth the width of products' -- and fetch the wide product rows
            # for the page only. Sorting 22k "ornament" matches by name used
            # to mean 22k random reads into the 355 MB products heap just to
            # learn each name; pg_stat_statements put that at 631 MB read per
            # call and a 42 s mean on this database, whose cache is 224 MB.
            # pf.name is trigger-maintained from products.name (0 mismatches
            # across 166k rows when this was written), so the order is the
            # same. The id tie-break makes paging deterministic among equal
            # names, which the previous shape left to the plan.
            frm = ("product_facets pf JOIN products p ON p.id = pf.product_id"
                   if needs_products else "product_facets pf")
            order = (f"{rank} DESC, {name_key('pf')}, pf.product_id" if rank
                     else f"{name_key('pf')}, pf.product_id")
            inner = (f"SELECT pf.product_id AS id{(', ' + rank + ' AS _rank') if rank else ''} "
                     f"FROM {frm} WHERE {wsql} ORDER BY {order} LIMIT {l} OFFSET {o}")
            sql = f"""SELECT p.id, p.name, s.name AS supplier_name, p.supplier_sku,
                       p.current_price, p.image_urls, p.photo_url, p.raw_data
                  FROM ({inner}) t
                  JOIN products p ON p.id = t.id
                  LEFT JOIN suppliers s ON s.id = p.supplier_id
                  ORDER BY {'t._rank DESC, ' if rank else ''}{name_key('p')}, p.id"""
            rows = await conn.fetch(sql, *args)
            return rows, wsql, args, base_where, base_args
        select = f"""SELECT p.id, p.name, s.name AS supplier_name, p.supplier_sku,
                   p.current_price, p.image_urls, p.photo_url, p.raw_data
                   {(', ' + rank + ' AS _rank') if rank else ''}
            FROM products p {item_join} LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE {wsql}"""
        if fenced:
            order = (f"ORDER BY t._rank DESC, {name_key('t')}" if rank
                     else f"ORDER BY {name_key('t')}")
            sql = f"SELECT * FROM ({select} OFFSET 0) t {order} LIMIT {l} OFFSET {o}"
        else:
            order = (f"ORDER BY {rank} DESC, {name_key('p')}" if rank
                     else f"ORDER BY {name_key('p')}")
            sql = f"{select} {order} LIMIT {l} OFFSET {o}"
        rows = await conn.fetch(sql, *args)
        return rows, wsql, args, base_where, base_args

    async def _count(wsql, args) -> tuple[int, bool]:
        # COUNT(*) OVER() used to ride along with the page, but it forces the
        # planner to materialise every matching row just to number them - 13s+
        # once the catalog passed 166k rows. Counted separately with a cap, so an
        # unfiltered browse never pays for a full scan.
        count_from = (("product_facets pf JOIN products p ON p.id = pf.product_id"
                       if needs_products else "product_facets pf")
                      if pf_first else f"products p {item_join}")
        capped = int(await conn.fetchval(f"""
            SELECT COUNT(*) FROM (
                SELECT 1 FROM {count_from} WHERE {wsql} LIMIT {_DB_COUNT_CAP + 1}
            ) x
        """, *args) or 0)
        return (_DB_COUNT_CAP, True) if capped > _DB_COUNT_CAP else (capped, False)

    term_variants = [(t, [t]) for t in terms]
    rows, wsql, args, base_where, base_args = await _page(term_variants)

    # Typo tolerance, second attempt only. A correctly spelled query fills its
    # page and stops here, paying nothing at all for this; only a query that came
    # back nearly empty goes looking for near spellings, and even then only for
    # terms that are words.
    #
    # The result is the exact-spelling rows (fewer than _FUZZY_MIN_HITS of them,
    # by construction) followed by the corrected query in name order, and the
    # two are joined here rather than in SQL. The earlier shape -- one query
    # OR'ing the typed word with four corrections, ORDER BY "typed spelling
    # first" -- measured 6.4 s warm and 15 s cold for "ornamnet": five OR'd
    # patterns made the planner give up the trigram index for a sequential scan
    # of all 166k facet rows, and the rank sort then spilled every one of the
    # 22k matches to disk before the first 48 could be returned. One pattern per
    # term keeps the index and lets ORDER BY name stop at the page: 0.35 s warm,
    # the same as a correctly spelled query.
    #
    # Paging counts the exact rows as the head of the list, so page two of a
    # corrected search continues where page one left off. (It used to return
    # nothing: the "is the exact set small?" test was made against the page
    # offset, which is never small on page two.)
    searched_for = None
    n_exact = 0
    if terms and len(rows) < lim:
        if off == 0:
            exact = list(rows)                      # a short first page is the whole set
        elif not rows:
            exact = list((await _page(term_variants, lim_=_FUZZY_MIN_HITS, off_=0))[0])
        else:
            exact = None                            # a later page with rows: the set is big
        if exact is not None and len(exact) < _FUZZY_MIN_HITS:
            expanded_variants, expanded = await _expand_terms(conn, terms)
            if expanded:
                # variants always lead with the term as typed; the best
                # correction is the next one. Only that one is searched.
                corrected = [(t, [v[1]] if len(v) > 1 else [t]) for t, v in expanded_variants]
                n_exact = len(exact)
                head = exact[off:off + lim]
                c_rows, wsql, args, base_where, base_args = await _page(
                    corrected, lim_=lim - len(head), off_=max(0, off - n_exact),
                    extra_ex=[r["id"] for r in exact] or None)
                rows = head + list(c_rows)
                # Report what was actually matched, so the caller can say so
                # instead of showing results for a word the user did not type.
                searched_for = " ".join(v[0] for _, v in corrected)

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
    if n_exact:
        total = (total or 0) + n_exact  # the exact rows lead the list; count them in

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
            # This IS the search, not a warm-up window; a permanent
            # "still loading" hint would be a lie.
            "warming": False, "total_is_capped": total_is_capped}
    if searched_for and searched_for != (search or "").lower().strip():
        resp["searched_for"] = searched_for
        resp["corrected"] = True
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
    """Faceted catalog search, served from Postgres.

    Alongside the page of results it returns `facets` — the values still
    available *within the current query*, each with a live count and computed
    with drill-down: a facet is counted ignoring its OWN selection, so picking
    one Color doesn't collapse the Color list. Facets are only built on a fresh
    load (offset == 0); infinite-scroll pages skip the extra pass.

    This used to be answered from an in-memory index of the whole catalog
    (~892 MB resident, ~1.3 GB peak while building). At 166k products it
    OOM-killed the web service, and every crash-restart re-read the catalog —
    the loop that exhausted the org's bandwidth quota. It also served data up
    to a day stale. The SQL path was proven identical first (parity gate:
    20 queries x 2 paths, 0 defects) and the index then deleted; the parity
    harness went with it, since there is no longer a reference to diff against.
    """
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


@router.get("/similar")
async def search_similar(
    search: str,
    colors: Optional[str] = None,
    categories: Optional[str] = None,
    sizes: Optional[str] = None,
    finishes: Optional[str] = None,
    product_types: Optional[str] = None,
    supplier_ids: Optional[str] = None,
    availability: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    exclude_ids: Optional[str] = None,
    limit: int = 24,
    offset: int = 0,
):
    """Near matches, for after the exact results have been shown or exhausted.

    Deliberately a second request rather than part of /search. The exact page
    is what the user is waiting on, and it must not pay for this: a correctly
    spelled query never calls here at all, and when it is called the work is a
    ~110 ms dictionary lookup plus one ordinary keyword search, not a fuzzy scan
    of the catalog.

    Pass `exclude_ids` — the ids already on screen — to keep the band from
    repeating them. That is an id array rather than a re-statement of the
    original query as a NOT: the predicate form measured 6.6 s against 760 ms,
    because NOT (blob ILIKE ...) cannot use the trigram index, and it also
    over-excluded, since "wreath" subsumes "wreaths" under substring matching
    and left the band empty.

    `corrections` says what was reinterpreted, so the UI can be honest about it
    ("showing results for wreath"), and `identifier_suggestions` carries near
    style numbers, which are offered for a person to pick rather than folded
    into the results. N592522DCV and N592522DA are different colours of one
    item; nothing here decides that on the buyer's behalf.
    """
    terms = [w for w in (search or "").lower().split() if w]
    if not terms:
        return {"items": [], "total": 0, "limit": limit, "offset": offset,
                "corrections": {}, "identifier_suggestions": []}

    conn = await get_conn()
    try:
        await _facet_source_probe(conn)
        # skip_known=True here too: a word the catalog really uses is kept as
        # typed, so "burlap ribon" becomes "burlap ribbon", not "burl ribbon".
        # Vendor typos of common words still correct (see _KNOWN_RATIO), which
        # is the reach this band exists for.
        corrections = await _correct_terms(conn, terms, skip_known=True)
        idents = await _similar_identifiers(conn, terms)

        if not corrections:
            return {"items": [], "total": 0, "limit": limit, "offset": offset,
                    "corrections": {}, "identifier_suggestions": idents}

        # One corrected spelling per term -- the best the dictionary offered.
        # Searching every combination would multiply the term set out for very
        # little extra recall.
        corrected = " ".join(corrections.get(t, [t])[0] for t in terms)
        result = await _search_products_db(
            conn, search=corrected, price_min=price_min, price_max=price_max,
            supplier_ids=supplier_ids, ids=None, limit=limit, offset=offset,
            build_facets=False,
            categories=categories, colors=colors, sizes=sizes, finishes=finishes,
            availability=availability, product_types=product_types,
            exclude_ids=exclude_ids,
        )
        result["corrections"] = corrections
        result["identifier_suggestions"] = idents
        result["searched_for"] = corrected
        return result
    finally:
        await conn.close()


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
