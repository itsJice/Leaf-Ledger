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
    # categories: multi param, or the legacy single `category`
    category_list = _csv_list(categories) or ([category] if category else [])
    if category_list:
        conditions.append(
            f"""(
                p.category = ANY(${idx}::text[])
                OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(COALESCE(p.raw_data->'category_tags', '[]'::jsonb)) AS category_tag(value)
                    WHERE category_tag.value = ANY(${idx}::text[])
                )
            )"""
        )
        params.append(category_list)
        idx += 1
    product_type_list = _csv_list(product_types)
    if product_type_list:
        conditions.append(f"{PRODUCT_TYPE_SQL} = ANY(${idx}::text[])")
        params.append(product_type_list)
        idx += 1
    color_list = _csv_list(colors)
    if color_list:
        conditions.append(f"p.color = ANY(${idx}::text[])")
        params.append(color_list)
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
        SELECT value, COUNT(DISTINCT id)::int AS count
        FROM (
            SELECT id, COALESCE(NULLIF(category, ''), 'other') AS value
            FROM products
            WHERE is_active = TRUE

            UNION ALL

            SELECT p.id, category_tag.value
            FROM products p
            CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(p.raw_data->'category_tags', '[]'::jsonb)) AS category_tag(value)
            WHERE p.is_active = TRUE
              AND NULLIF(BTRIM(category_tag.value), '') IS NOT NULL
        ) AS category_options
        GROUP BY value
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
        SELECT COALESCE(
            NULLIF(color, ''),
            NULLIF(raw_data->>'ColorGrp', ''),
            NULLIF(raw_data->>'Color', ''),
            NULLIF(raw_data->>'Primary Color', '')
        ) AS value,
        COUNT(*)::int AS count
        FROM products
        WHERE is_active = TRUE
        GROUP BY 1
        ORDER BY count DESC, value ASC
        LIMIT 300
    """)
    product_type_rows = await conn.fetch("""
        SELECT COALESCE(NULLIF(style, ''), raw_data->>'product_type') AS value,
               COUNT(*)::int AS count
        FROM products
        WHERE is_active = TRUE
        GROUP BY 1
        ORDER BY count DESC, value ASC
        LIMIT 300
    """)
    availability_rows = await conn.fetch(f"""
        SELECT ({_availability_bucket_sql('availability')}) AS value, COUNT(*)::int AS count
        FROM products
        WHERE is_active = TRUE
        GROUP BY 1
    """)
    availability_counts = {row["value"]: row["count"] for row in availability_rows if row["value"]}
    availability_order = ["In stock", "Out of stock"]
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "categories": _option_rows(category_rows),
        "suppliers": _option_rows(supplier_rows),
        "product_types": _option_rows(product_type_rows),
        "countries": _option_rows(country_rows),
        "colors": _option_rows(color_rows),
        "availability": [
            {"value": label, "count": availability_counts[label]}
            for label in availability_order
            if availability_counts.get(label)
        ],
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
