from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Any
import asyncpg
import asyncio
import time
import io
import os
import re
import uuid
import json
import databutton as db
from datetime import datetime
from app.libs.catalog_importer import CatalogRow, parse_catalog_file
from app.libs.supplier_identity import resolve_scraper_key

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

DATABASE_URL = os.environ.get("DATABASE_URL")

async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


def _infer_scraper_key(name: Optional[str], scraper_key: Optional[str] = None) -> Optional[str]:
    """Normalize the configured scraper key, falling back to supplier name."""
    return resolve_scraper_key(name, scraper_key)


def _json_list(value: Any) -> list:
    """Decode a json/jsonb array returned by asyncpg into a Python list."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return list(value)


def _catalog_import_index_key(supplier_id: int) -> str:
    return f"catalog-imports/{supplier_id}/index.json"


def _catalog_import_record_key(import_id: int) -> str:
    return f"catalog-imports/by-id/{import_id}.json"


def _storage_json_get(key: str, default: Any):
    try:
        raw = db.storage.text.get(key, default=None)
        if raw is None:
            return default
        return json.loads(raw)
    except Exception:
        return default


def _storage_json_put(key: str, value: Any):
    db.storage.text.put(key, json.dumps(value, default=str))


def _catalog_now() -> str:
    return datetime.utcnow().isoformat()


def _catalog_import_id() -> int:
    return uuid.uuid4().int % 1_000_000_000_000


def _catalog_image_storage_key(supplier_id: int, sku: str, import_id: int) -> str:
    safe_sku = re.sub(r"[^a-zA-Z0-9._-]", "-", sku.strip()) or "product"
    return f"catalog-product-images/{supplier_id}/{safe_sku}-{import_id}-v2.png"


def _catalog_internal_image_url(storage_key: str) -> str:
    return f"/api/products/image-proxy?key={storage_key}"


def _attach_pdf_crop_images(
    data: bytes,
    parsed_rows: list[CatalogRow],
    *,
    supplier_id: int,
    import_id: int,
) -> int:
    rows_with_boxes = [
        row for row in parsed_rows
        if isinstance(row.raw_data, dict)
        and isinstance(row.raw_data.get("pdf_image_bbox"), list)
        and row.source_page
    ]
    if not rows_with_boxes:
        return 0
    try:
        import pypdfium2 as pdfium
        from PIL import Image, ImageChops
    except Exception:
        return 0

    stored = 0
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception:
        return 0

    rendered_pages: dict[int, Any] = {}
    try:
        for row in rows_with_boxes:
            try:
                page_number = int(row.source_page or 0)
                page_index = page_number - 1
                if page_index < 0:
                    continue
                if page_index not in rendered_pages:
                    page = pdf[page_index]
                    bitmap = page.render(scale=2)
                    rendered_pages[page_index] = (page, bitmap.to_pil().convert("RGB"))
                page, image = rendered_pages[page_index]
                bbox = [float(value) for value in row.raw_data["pdf_image_bbox"][:4]]
                x0, y0, x1, y1 = bbox
                scale_x = image.width / float(page.get_width())
                scale_y = image.height / float(page.get_height())
                crop_box = (
                    max(0, int(x0 * scale_x)),
                    max(0, int(y0 * scale_y)),
                    min(image.width, int(x1 * scale_x)),
                    min(image.height, int(y1 * scale_y)),
                )
                if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
                    continue
                crop = image.crop(crop_box).convert("RGB")
                if crop.width < 40 or crop.height < 40:
                    continue
                diff = ImageChops.difference(crop, Image.new("RGB", crop.size, "white"))
                content_box = diff.getbbox()
                if content_box:
                    padding = 8
                    content_box = (
                        max(0, content_box[0] - padding),
                        max(0, content_box[1] - padding),
                        min(crop.width, content_box[2] + padding),
                        min(crop.height, content_box[3] + padding),
                    )
                    crop = crop.crop(content_box)
                canvas = Image.new("RGB", (crop.width + 24, crop.height + 24), "white")
                canvas.paste(crop, (12, 12))
                buffer = io.BytesIO()
                canvas.save(buffer, format="PNG", optimize=True)
                storage_key = _catalog_image_storage_key(supplier_id, row.supplier_sku, import_id)
                db.storage.binary.put(storage_key, buffer.getvalue())
                image_url = _catalog_internal_image_url(storage_key)
                row.raw_data["source_photo_url"] = image_url
                row.raw_data["image_urls"] = [image_url]
                row.raw_data["image_status"] = "stored"
                row.raw_data["image_source"] = "pdf_crop"
                row.raw_data["image_storage_key"] = storage_key
                stored += 1
            except Exception:
                row.raw_data["image_status"] = row.raw_data.get("image_status") or "failed"
                continue
    finally:
        try:
            pdf.close()
        except Exception:
            pass
    return stored


def _save_catalog_import_record(record: dict):
    import_id = int(record["id"])
    supplier_id = int(record["supplier_id"])
    _storage_json_put(_catalog_import_record_key(import_id), record)
    index_key = _catalog_import_index_key(supplier_id)
    index = _storage_json_get(index_key, [])
    index = [item for item in index if int(item.get("id", -1)) != import_id]
    meta = {k: v for k, v in record.items() if k != "rows"}
    index.insert(0, meta)
    _storage_json_put(index_key, index[:50])


def _catalog_row_dict(
    import_id: int,
    supplier_id: int,
    row_index: int,
    product: CatalogRow,
    status: str,
    raw: dict,
    error_message: Optional[str] = None,
) -> dict:
    timestamp = _catalog_now()
    return {
        "id": row_index,
        "import_id": import_id,
        "supplier_id": supplier_id,
        "row_index": row_index,
        "supplier_sku": product.supplier_sku,
        "name": product.name,
        "description": product.description,
        "upc": product.upc,
        "current_price": product.current_price,
        "unit": product.unit,
        "category": product.category,
        "moq": product.moq,
        "box_qty": product.box_qty,
        "case_qty": product.case_qty,
        "cubic_ft": product.cubic_ft,
        "source_page": product.source_page,
        "source_section": product.source_section,
        "status": status,
        "product_id": None,
        "raw_data": raw,
        "error_message": error_message,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


async def ensure_catalog_import_schema(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS supplier_catalog_imports (
            id SERIAL PRIMARY KEY,
            supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL DEFAULT 'catalog_file',
            parser_key TEXT,
            catalog_name TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            storage_key TEXT,
            status TEXT NOT NULL DEFAULT 'staged',
            row_count INTEGER NOT NULL DEFAULT 0,
            staged_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            inserted_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            committed_at TIMESTAMPTZ
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS supplier_catalog_import_rows (
            id SERIAL PRIMARY KEY,
            import_id INTEGER NOT NULL REFERENCES supplier_catalog_imports(id) ON DELETE CASCADE,
            supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            row_index INTEGER NOT NULL,
            supplier_sku TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            upc TEXT,
            current_price NUMERIC,
            unit TEXT NOT NULL DEFAULT 'each',
            category TEXT NOT NULL DEFAULT 'other',
            moq INTEGER,
            box_qty INTEGER,
            case_qty INTEGER,
            cubic_ft NUMERIC,
            source_page INTEGER,
            source_section TEXT,
            status TEXT NOT NULL DEFAULT 'staged',
            product_id INTEGER,
            raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS supplier_catalog_import_rows_import_idx
        ON supplier_catalog_import_rows(import_id, row_index)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS supplier_catalog_import_rows_supplier_sku_idx
        ON supplier_catalog_import_rows(supplier_id, supplier_sku)
    """)


# ---------- Models ----------

# ---------- Catalog filter models ----------

class CatalogFilters(BaseModel):
    """Saved catalog selection for a supplier — which sections/DDCODEs to scrape."""
    sections: List[str] = []   # e.g. ["Holiday & Fall", "Spring & Summer"]
    categories: List[str] = []  # e.g. ["HZ0001", "HZ0042"]
    updated_at: Optional[datetime] = None

class CatalogFiltersUpdate(BaseModel):
    sections: List[str] = []
    categories: List[str] = []

class CatalogSection(BaseModel):
    """A top-level section from live discovery."""
    name: str
    subcategories: List[dict] = []  # [{ddcode, label, item_count}]

class DiscoverCatalogResponse(BaseModel):
    sections: List[CatalogSection]
    total_subcategories: int
    total_products: int
    from_cache: bool
    section_listing_total: int = 0
    catalog_summary: Optional[dict] = None

# ---------- Supplier models ----------

class SupplierCreate(BaseModel):
    name: str
    scraper_key: Optional[str] = None
    login_url: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    categories: List[str] = []

class SupplierOut(BaseModel):
    id: int
    name: str
    scraper_key: Optional[str] = None
    login_url: Optional[str]
    login_username: Optional[str] = None
    has_credentials: bool = False  # True if login_username + login_password are stored
    credential_status: Optional[str] = None
    contact_name: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    notes: Optional[str]
    categories: List[str] = []
    created_at: datetime
    updated_at: datetime
    product_count: int = 0
    last_price_synced_at: Optional[datetime] = None
    last_full_sync_at: Optional[datetime] = None

class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    scraper_key: Optional[str] = None
    login_url: Optional[str] = None
    login_username: Optional[str] = None
    login_password: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    categories: Optional[List[str]] = None

class SupplierCredentialsOut(BaseModel):
    login_username: Optional[str] = None
    login_password: Optional[str] = None

class CatalogImportOut(BaseModel):
    id: int
    supplier_id: int
    source_type: str
    parser_key: Optional[str] = None
    catalog_name: str
    original_filename: str
    status: str
    row_count: int = 0
    staged_count: int = 0
    duplicate_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    error_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    committed_at: Optional[datetime] = None

class CatalogImportRowOut(BaseModel):
    id: int
    import_id: int
    supplier_id: int
    row_index: int
    supplier_sku: str
    name: str
    description: Optional[str] = None
    upc: Optional[str] = None
    current_price: Optional[float] = None
    unit: str
    category: str
    moq: Optional[int] = None
    box_qty: Optional[int] = None
    case_qty: Optional[int] = None
    cubic_ft: Optional[float] = None
    source_page: Optional[int] = None
    source_section: Optional[str] = None
    status: str
    product_id: Optional[int] = None
    raw_data: dict = {}
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class CatalogImportRowsPage(BaseModel):
    items: List[CatalogImportRowOut]
    total: int
    limit: int
    offset: int

class CatalogImportCommitOut(BaseModel):
    import_id: int
    inserted: int
    updated: int
    skipped: int
    errors: int

# ---------- Endpoints ----------

# Counting products per supplier means walking all ~166k active rows, which on
# this instance costs 16-29s and made the Suppliers page look broken. The
# catalog only changes on import, so the counts are cached and refreshed in the
# background; the supplier list itself (32 rows) is always fetched fresh.
_SUPPLIER_COUNT_CACHE: dict = {"ts": 0.0, "counts": None}
_SUPPLIER_COUNT_TTL = 900  # 15 minutes
_SUPPLIER_COUNT_LOCK = asyncio.Lock()


async def _fetch_supplier_counts(conn) -> dict:
    rows = await conn.fetch(
        """SELECT supplier_id, COUNT(*) AS n FROM products
            WHERE is_active = TRUE GROUP BY supplier_id"""
    )
    return {r["supplier_id"]: r["n"] for r in rows}


async def _refresh_supplier_counts() -> None:
    """Rebuild the count cache on its own connection, one refresh at a time."""
    if _SUPPLIER_COUNT_LOCK.locked():
        return
    async with _SUPPLIER_COUNT_LOCK:
        conn = await get_conn()
        try:
            counts = await _fetch_supplier_counts(conn)
            _SUPPLIER_COUNT_CACHE.update(ts=time.time(), counts=counts)
        except Exception:
            pass
        finally:
            await conn.close()


@router.get("/list", response_model=List[SupplierOut])
async def list_suppliers():
    conn = await get_conn()
    try:
        rows = await conn.fetch("""
            SELECT s.*,
                   (s.login_username IS NOT NULL AND s.login_username != '' AND s.login_password IS NOT NULL AND s.login_password != '') as has_credentials
            FROM suppliers s
            ORDER BY s.name
        """)
        cached = _SUPPLIER_COUNT_CACHE.get("counts")
        fresh = cached is not None and (time.time() - _SUPPLIER_COUNT_CACHE["ts"]) < _SUPPLIER_COUNT_TTL
        if not fresh:
            if cached is None:
                # Nothing cached yet: pay for it once so the first load is correct.
                try:
                    cached = await _fetch_supplier_counts(conn)
                    _SUPPLIER_COUNT_CACHE.update(ts=time.time(), counts=cached)
                except Exception:
                    cached = {}
            else:
                # Stale but usable - serve it now, refresh behind the request.
                asyncio.create_task(_refresh_supplier_counts())
        counts = cached or {}
        return [dict(r, product_count=counts.get(r["id"], 0)) for r in rows]
    finally:
        await conn.close()

@router.post("/create", response_model=SupplierOut)
async def create_supplier(body: SupplierCreate):
    conn = await get_conn()
    try:
        scraper_key = _infer_scraper_key(body.name, body.scraper_key)
        row = await conn.fetchrow("""
            INSERT INTO suppliers (name, scraper_key, scraper_enabled, login_url, contact_name, contact_email, contact_phone, notes, categories)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *, 0 as product_count, FALSE as has_credentials
        """, body.name, scraper_key, scraper_key is not None, body.login_url, body.contact_name, body.contact_email, body.contact_phone, body.notes, body.categories)
        return dict(row)
    finally:
        await conn.close()

@router.put("/update/{supplier_id}", response_model=SupplierOut)
async def update_supplier(supplier_id: int, body: SupplierUpdate):
    conn = await get_conn()
    try:
        existing = await conn.fetchrow("SELECT * FROM suppliers WHERE id = $1", supplier_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Supplier not found")
        next_name = body.name if body.name is not None else existing["name"]
        next_scraper_key = _infer_scraper_key(next_name, body.scraper_key if body.scraper_key is not None else existing["scraper_key"])
        next_username = body.login_username if body.login_username is not None else existing["login_username"]
        next_password = body.login_password if body.login_password is not None else existing["login_password"]
        creds_changed = body.login_username is not None or body.login_password is not None
        if not next_username or not next_password:
            next_credential_status = "missing"
        elif creds_changed:
            next_credential_status = "untested"
        else:
            next_credential_status = existing["credential_status"] or "untested"
        updated = await conn.fetchrow("""
            UPDATE suppliers SET
                name = COALESCE($1::text, name),
                scraper_key = $2::text,
                scraper_enabled = CASE WHEN $2::text IS NOT NULL THEN true ELSE scraper_enabled END,
                login_url = COALESCE($3::text, login_url),
                login_username = COALESCE($4::text, login_username),
                login_password = COALESCE($5::text, login_password),
                credential_status = $6::text,
                contact_name = COALESCE($7::text, contact_name),
                contact_email = COALESCE($8::text, contact_email),
                contact_phone = COALESCE($9::text, contact_phone),
                notes = COALESCE($10::text, notes),
                categories = COALESCE($11::text[], categories),
                updated_at = NOW()
            WHERE id = $12
            RETURNING *
        """, body.name, next_scraper_key, body.login_url, body.login_username, body.login_password, next_credential_status, body.contact_name, body.contact_email, body.contact_phone, body.notes, body.categories, supplier_id)
        count = await conn.fetchval("SELECT COUNT(*) FROM products WHERE supplier_id = $1 AND is_active = TRUE", supplier_id)
        result = dict(updated)
        result["product_count"] = count
        result["has_credentials"] = bool(result.get("login_username") and result.get("login_password"))
        return result
    finally:
        await conn.close()

@router.delete("/delete/{supplier_id}")
async def delete_supplier(supplier_id: int):
    conn = await get_conn()
    try:
        result = await conn.execute("DELETE FROM suppliers WHERE id = $1", supplier_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Supplier not found")
        return {"ok": True}
    finally:
        await conn.close()

@router.get("/get/{supplier_id}", response_model=SupplierOut)
async def get_supplier(supplier_id: int):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("""
            SELECT s.*, COUNT(p.id) as product_count,
                   (s.login_username IS NOT NULL AND s.login_username != '' AND s.login_password IS NOT NULL AND s.login_password != '') as has_credentials
            FROM suppliers s
            LEFT JOIN products p ON p.supplier_id = s.id AND p.is_active = TRUE
            WHERE s.id = $1
            GROUP BY s.id
        """, supplier_id)
        if not row:
            raise HTTPException(status_code=404, detail="Supplier not found")
        return dict(row)
    finally:
        await conn.close()

@router.get("/{supplier_id}/credentials", response_model=SupplierCredentialsOut)
async def get_supplier_credentials(supplier_id: int):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT login_username, login_password FROM suppliers WHERE id = $1",
            supplier_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Supplier not found")
        return dict(row)
    finally:
        await conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Supplier catalog file intake endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/{supplier_id}/catalog-imports", response_model=List[CatalogImportOut])
async def list_catalog_imports(supplier_id: int):
    return _storage_json_get(_catalog_import_index_key(supplier_id), [])


@router.post("/{supplier_id}/catalog-imports/upload", response_model=CatalogImportOut)
async def upload_catalog_import(
    supplier_id: int,
    file: UploadFile = File(...),
    catalog_name: Optional[str] = Form(None),
    parser_key: Optional[str] = Form(None),
):
    data = await file.read()
    filename = file.filename or "catalog"
    print(f"[catalog-import] supplier={supplier_id} filename={filename} bytes={len(data)} parser={parser_key or 'auto'}")
    if not data:
        raise HTTPException(status_code=400, detail="Catalog file is empty")

    conn = await get_conn()
    try:
        supplier = await conn.fetchrow("SELECT id, name FROM suppliers WHERE id = $1", supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        label = catalog_name or filename
        storage_key = f"catalog-imports/{supplier_id}/{uuid.uuid4()}-{filename}"
        try:
            db.storage.binary.put(storage_key, data)
        except Exception:
            storage_key = None

        import_id = _catalog_import_id()
        created_at = _catalog_now()

        try:
            parsed_rows = parse_catalog_file(data, filename, parser_hint=parser_key)
        except Exception as exc:
            failed = {
                "id": import_id,
                "supplier_id": supplier_id,
                "source_type": "catalog_file",
                "parser_key": parser_key,
                "catalog_name": label,
                "original_filename": filename,
                "storage_key": storage_key,
                "status": "failed",
                "row_count": 0,
                "staged_count": 0,
                "duplicate_count": 0,
                "inserted_count": 0,
                "updated_count": 0,
                "error_count": 1,
                "error_message": str(exc)[:500],
                "created_at": created_at,
                "updated_at": _catalog_now(),
                "committed_at": None,
                "rows": [],
            }
            _save_catalog_import_record(failed)
            return failed

        if not parsed_rows:
            failed = {
                "id": import_id,
                "supplier_id": supplier_id,
                "source_type": "catalog_file",
                "parser_key": parser_key,
                "catalog_name": label,
                "original_filename": filename,
                "storage_key": storage_key,
                "status": "failed",
                "row_count": 0,
                "staged_count": 0,
                "duplicate_count": 0,
                "inserted_count": 0,
                "updated_count": 0,
                "error_count": 1,
                "error_message": "No product rows could be parsed from this file.",
                "created_at": created_at,
                "updated_at": _catalog_now(),
                "committed_at": None,
                "rows": [],
            }
            _save_catalog_import_record(failed)
            return failed

        stored_image_count = _attach_pdf_crop_images(
            data,
            parsed_rows,
            supplier_id=supplier_id,
            import_id=import_id,
        )

        existing_skus = {
            str(row["supplier_sku"]).upper()
            for row in await conn.fetch(
                "SELECT supplier_sku FROM products WHERE supplier_id = $1 AND supplier_sku IS NOT NULL",
                supplier_id,
            )
        }
        seen: set[str] = set()
        staged = duplicate = errors = 0
        row_records: list[dict] = []
        for index, product in enumerate(parsed_rows, start=1):
            sku_key = product.supplier_sku.upper().strip()
            status = "duplicate" if sku_key in existing_skus or sku_key in seen else "staged"
            if status == "duplicate":
                duplicate += 1
            else:
                staged += 1
            seen.add(sku_key)
            raw = dict(product.raw_data or {})
            raw.update({
                "catalog_import_id": import_id,
                "catalog_name": label,
                "catalog_filename": filename,
                "catalog_source_type": raw.get("catalog_source_type") or "catalog_file",
                "source_page": product.source_page,
                "source_section": product.source_section,
                "UPC": product.upc,
                "BoxQty": product.box_qty,
                "CaseQty": product.case_qty,
                "CubicFt": product.cubic_ft,
            })
            row_records.append(_catalog_row_dict(import_id, supplier_id, index, product, status, raw))

        complete = {
            "id": import_id,
            "supplier_id": supplier_id,
            "source_type": "catalog_file",
            "parser_key": parser_key,
            "catalog_name": label,
            "original_filename": filename,
            "storage_key": storage_key,
            "status": "staged",
            "row_count": len(parsed_rows),
            "staged_count": staged,
            "duplicate_count": duplicate,
            "inserted_count": 0,
            "updated_count": 0,
            "error_count": errors,
            "error_message": None,
            "stored_image_count": stored_image_count,
            "created_at": created_at,
            "updated_at": _catalog_now(),
            "committed_at": None,
            "rows": row_records,
        }
        _save_catalog_import_record(complete)
        return complete
    finally:
        await conn.close()


@router.get("/catalog-imports/{import_id}/rows", response_model=CatalogImportRowsPage)
async def list_catalog_import_rows(import_id: int, limit: int = 50, offset: int = 0):
    record = _storage_json_get(_catalog_import_record_key(import_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="Catalog import not found")
    safe_limit = min(max(limit, 1), 200)
    safe_offset = max(offset, 0)
    rows = record.get("rows") or []
    return {
        "items": rows[safe_offset : safe_offset + safe_limit],
        "total": len(rows),
        "limit": safe_limit,
        "offset": safe_offset,
    }


@router.post("/catalog-imports/{import_id}/reprocess", response_model=CatalogImportOut)
async def reprocess_catalog_import(import_id: int):
    existing = _storage_json_get(_catalog_import_record_key(import_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Catalog import not found")
    storage_key = existing.get("storage_key")
    if not storage_key:
        raise HTTPException(status_code=400, detail="Catalog file was not stored for retry")
    try:
        data = db.storage.binary.get(storage_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Stored catalog file could not be read") from exc
    if not data:
        raise HTTPException(status_code=400, detail="Stored catalog file is empty")

    supplier_id = int(existing["supplier_id"])
    filename = existing.get("original_filename") or "catalog"
    label = existing.get("catalog_name") or filename
    parser_key = existing.get("parser_key")
    created_at = existing.get("created_at") or _catalog_now()

    conn = await get_conn()
    try:
        parsed_rows = parse_catalog_file(data, filename, parser_hint=parser_key)
        if not parsed_rows:
            failed = {
                **existing,
                "status": "failed",
                "row_count": 0,
                "staged_count": 0,
                "duplicate_count": 0,
                "inserted_count": 0,
                "updated_count": 0,
                "error_count": 1,
                "error_message": "No product rows could be parsed from this file.",
                "updated_at": _catalog_now(),
                "committed_at": None,
                "rows": [],
            }
            _save_catalog_import_record(failed)
            return failed

        stored_image_count = _attach_pdf_crop_images(
            data,
            parsed_rows,
            supplier_id=supplier_id,
            import_id=import_id,
        )

        existing_skus = {
            str(row["supplier_sku"]).upper()
            for row in await conn.fetch(
                "SELECT supplier_sku FROM products WHERE supplier_id = $1 AND supplier_sku IS NOT NULL",
                supplier_id,
            )
        }
        seen: set[str] = set()
        staged = duplicate = errors = 0
        row_records: list[dict] = []
        for index, product in enumerate(parsed_rows, start=1):
            sku_key = product.supplier_sku.upper().strip()
            status = "duplicate" if sku_key in existing_skus or sku_key in seen else "staged"
            if status == "duplicate":
                duplicate += 1
            else:
                staged += 1
            seen.add(sku_key)
            raw = dict(product.raw_data or {})
            raw.update({
                "catalog_import_id": import_id,
                "catalog_name": label,
                "catalog_filename": filename,
                "catalog_source_type": raw.get("catalog_source_type") or "catalog_file",
                "source_page": product.source_page,
                "source_section": product.source_section,
                "UPC": product.upc,
                "BoxQty": product.box_qty,
                "CaseQty": product.case_qty,
                "CubicFt": product.cubic_ft,
            })
            row_records.append(_catalog_row_dict(import_id, supplier_id, index, product, status, raw))

        complete = {
            **existing,
            "id": import_id,
            "supplier_id": supplier_id,
            "source_type": "catalog_file",
            "parser_key": parser_key,
            "catalog_name": label,
            "original_filename": filename,
            "storage_key": storage_key,
            "status": "staged",
            "row_count": len(parsed_rows),
            "staged_count": staged,
            "duplicate_count": duplicate,
            "inserted_count": 0,
            "updated_count": 0,
            "error_count": errors,
            "error_message": None,
            "stored_image_count": stored_image_count,
            "created_at": created_at,
            "updated_at": _catalog_now(),
            "committed_at": None,
            "rows": row_records,
        }
        _save_catalog_import_record(complete)
        return complete
    finally:
        await conn.close()


@router.post("/catalog-imports/{import_id}/commit", response_model=CatalogImportCommitOut)
async def commit_catalog_import(import_id: int, include_duplicates: bool = True):
    conn = await get_conn()
    try:
        catalog = _storage_json_get(_catalog_import_record_key(import_id), None)
        if not catalog:
            raise HTTPException(status_code=404, detail="Catalog import not found")
        if catalog["status"] == "committed":
            return {
                "import_id": import_id,
                "inserted": catalog["inserted_count"],
                "updated": catalog["updated_count"],
                "skipped": 0,
                "errors": catalog["error_count"],
            }

        rows = [
            row for row in (catalog.get("rows") or [])
            if row.get("status") in (["staged", "duplicate"] if include_duplicates else ["staged"])
        ]

        inserted = updated = skipped = errors = 0
        existing_skus = {
            str(row["supplier_sku"]).upper()
            for row in await conn.fetch(
                "SELECT supplier_sku FROM products WHERE supplier_id = $1 AND supplier_sku IS NOT NULL",
                catalog["supplier_id"],
            )
        }
        batch_values = []
        timestamp = _catalog_now()
        for row in rows:
            raw = dict(row["raw_data"] or {})
            raw["catalog_import_committed_at"] = datetime.utcnow().isoformat()
            raw["category_tags"] = list({
                tag for tag in (raw.get("category_tags") or [])
                if isinstance(tag, str) and tag.strip()
            })
            sku_key = str(row["supplier_sku"]).upper()
            if sku_key in existing_skus:
                updated += 1
            else:
                inserted += 1
                existing_skus.add(sku_key)
            batch_values.append((
                row["supplier_id"], row["supplier_sku"], row["name"], row["description"],
                row["category"], row["unit"], row["current_price"], row["moq"],
                row["case_qty"],
                raw.get("source_photo_url"),
                [value for value in (raw.get("image_urls") or []) if isinstance(value, str) and value.strip()],
                json.dumps(raw),
            ))
            row["status"] = "imported"
            row["updated_at"] = timestamp

        if batch_values:
            try:
                async with conn.transaction():
                    await conn.executemany("""
                        INSERT INTO products
                            (supplier_id, supplier_sku, name, description, category, unit,
                             current_price, price_updated_at, country_of_origin, color, moq, case_qty,
                             availability, availability_note, photo_url, image_urls, raw_data, is_active, created_at, updated_at)
                        VALUES
                            ($1, $2, $3, $4, $5, $6, $7::numeric,
                             CASE WHEN $7::numeric IS NOT NULL THEN NOW() ELSE NULL END,
                             NULL, NULL, $8::integer, $9::integer, NULL, NULL, $10, $11::text[], $12::jsonb,
                             TRUE, NOW(), NOW())
                        ON CONFLICT (supplier_id, supplier_sku)
                        DO UPDATE SET
                            name = COALESCE(EXCLUDED.name, products.name),
                            description = COALESCE(EXCLUDED.description, products.description),
                            category = COALESCE(EXCLUDED.category, products.category),
                            unit = COALESCE(EXCLUDED.unit, products.unit),
                            current_price = COALESCE(EXCLUDED.current_price, products.current_price),
                            price_updated_at = CASE
                                WHEN EXCLUDED.current_price IS NOT NULL
                                     AND EXCLUDED.current_price IS DISTINCT FROM products.current_price
                                THEN NOW()
                                ELSE products.price_updated_at
                            END,
                            moq = COALESCE(EXCLUDED.moq, products.moq),
                            case_qty = COALESCE(EXCLUDED.case_qty, products.case_qty),
                            photo_url = COALESCE(EXCLUDED.photo_url, products.photo_url),
                            image_urls = CASE
                                WHEN array_length(EXCLUDED.image_urls, 1) > 0
                                THEN EXCLUDED.image_urls
                                ELSE products.image_urls
                            END,
                            raw_data = COALESCE(products.raw_data, '{}'::jsonb) || COALESCE(EXCLUDED.raw_data, '{}'::jsonb),
                            is_active = TRUE,
                            updated_at = NOW()
                    """, batch_values)
            except Exception as exc:
                errors = len(rows)
                inserted = 0
                updated = 0
                for row in rows:
                    row["status"] = "error"
                    row["error_message"] = str(exc)[:500]
                    row["updated_at"] = timestamp

        catalog["status"] = "committed_with_errors" if errors > 0 else "committed"
        catalog["inserted_count"] = inserted
        catalog["updated_count"] = updated
        catalog["error_count"] = int(catalog.get("error_count") or 0) + errors
        catalog["committed_at"] = _catalog_now()
        catalog["updated_at"] = _catalog_now()
        _save_catalog_import_record(catalog)
        await conn.execute(
            "UPDATE suppliers SET last_full_sync_at = NOW(), updated_at = NOW() WHERE id = $1",
            catalog["supplier_id"],
        )
        return {"import_id": import_id, "inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors}
    finally:
        await conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Catalog filter endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/{supplier_id}/catalog-filters", response_model=CatalogFilters)
async def get_catalog_filters(supplier_id: int):
    """Return saved catalog filter selections for this supplier.
    Returns empty lists if none have been saved yet (meaning scrape everything).
    """
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT sections, categories, updated_at FROM supplier_catalog_filters WHERE supplier_id = $1",
            supplier_id,
        )
        if not row:
            return CatalogFilters(sections=[], categories=[])
        return CatalogFilters(
            sections=_json_list(row["sections"]),
            categories=_json_list(row["categories"]),
            updated_at=row["updated_at"],
        )
    finally:
        await conn.close()


@router.put("/{supplier_id}/catalog-filters", response_model=CatalogFilters)
async def save_catalog_filters(supplier_id: int, body: CatalogFiltersUpdate):
    """Save the user's catalog selections for this supplier.
    Empty lists = scrape everything (safe default).
    """
    conn = await get_conn()
    try:
        # Verify supplier exists
        exists = await conn.fetchval("SELECT id FROM suppliers WHERE id = $1", supplier_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Supplier not found")

        row = await conn.fetchrow(
            """
            INSERT INTO supplier_catalog_filters (supplier_id, sections, categories, updated_at)
            VALUES ($1, $2::jsonb, $3::jsonb, NOW())
            ON CONFLICT (supplier_id) DO UPDATE
              SET sections = EXCLUDED.sections,
                  categories = EXCLUDED.categories,
                  updated_at = NOW()
            RETURNING sections, categories, updated_at
            """,
            supplier_id,
            json.dumps(body.sections),
            json.dumps(body.categories),
        )
        return CatalogFilters(
            sections=_json_list(row["sections"]),
            categories=_json_list(row["categories"]),
            updated_at=row["updated_at"],
        )
    finally:
        await conn.close()


@router.delete("/{supplier_id}/catalog-filters")
async def delete_catalog_filters(supplier_id: int):
    """Clear all catalog filter selections for this supplier (resets to scrape-everything)."""
    conn = await get_conn()
    try:
        await conn.execute(
            "DELETE FROM supplier_catalog_filters WHERE supplier_id = $1", supplier_id
        )
        return {"ok": True}
    finally:
        await conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Discover catalog endpoint — logs in live and returns category tree
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/{supplier_id}/discover-catalog", response_model=DiscoverCatalogResponse)
async def discover_catalog(supplier_id: int, force_refresh: bool = False):
    """Return the live category tree for a supplier, grouped by section.

    Strategy (cache-first with 30-day TTL):
    - If the category index was built < 30 days ago AND force_refresh is False,
      return the cached index instantly (no browser session needed).
    - If the index is stale (> 30 days) OR force_refresh=True, log in live,
      crawl all sections, save a fresh index, and return results.

    Does NOT scrape products — this is a lightweight discovery pass only.
    Live crawl takes ~1-3 minutes. Cached response is instant.
    """
    from datetime import timezone

    CACHE_TTL_DAYS = 30  # refresh the live category tree once a month

    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT name, scraper_key, login_username, login_password, category_index_rebuilt_at FROM suppliers WHERE id = $1",
            supplier_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Supplier not found")
        supplier_name = row["name"] or ""
        scraper_key = _infer_scraper_key(supplier_name, row["scraper_key"])
        username = row["login_username"] or ""
        password = row["login_password"] or ""
        index_rebuilt_at = row["category_index_rebuilt_at"]  # may be None
    finally:
        await conn.close()

    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="Supplier has no saved credentials. Add login username and password first.",
        )

    if scraper_key not in ("allstate", "accent_decor", "regency", "select_artificial", "vickerman"):
        raise HTTPException(
            status_code=400,
            detail=f"Catalog discovery not yet supported for supplier '{supplier_name}'.",
        )

    from app.libs.scraper_base import load_category_index

    # ── Decide: use cache or do a live crawl ─────────────────────────────────
    now = datetime.now(timezone.utc)
    cache_is_fresh = (
        index_rebuilt_at is not None
        and (now - index_rebuilt_at.replace(tzinfo=timezone.utc)).days < CACHE_TTL_DAYS
    )
    use_cache = cache_is_fresh and not force_refresh

    if use_cache:
        # Fast path: load category index from DB
        print(f"[discover-catalog] Cache-hit for supplier {supplier_id} (age < {CACHE_TTL_DAYS} days)")
        cached = await load_category_index(supplier_id, scraper_key)
        if cached:
            entries = cached
            if scraper_key == "vickerman":
                from app.libs.vickerman_scraper import _catalog_totals, _category_url

                merged_entries: dict[str, dict] = {}
                for entry in cached:
                    url = _category_url(entry.get("category_slug_or_url") or "")
                    if not url:
                        continue
                    existing = merged_entries.get(url)
                    if not existing or int(entry.get("product_count") or 0) > int(existing.get("product_count") or 0):
                        merged_entries[url] = {**entry, "category_slug_or_url": url}
                entries = list(merged_entries.values())
                vickerman_categories = [
                    {
                        "slug": entry["category_slug_or_url"],
                        "ddcode": entry["category_slug_or_url"],
                        "item_count": entry.get("product_count") or 0,
                    }
                    for entry in entries
                ]
                vickerman_totals = _catalog_totals(vickerman_categories)
                total_products = int(vickerman_totals["total_products"])
                section_listing_total = int(vickerman_totals["section_listing_total"])
                catalog_summary: Optional[dict] = vickerman_totals["catalog_summary"]
            else:
                total_products = 0
                section_listing_total = 0
                catalog_summary = None

            sections_map: dict[str, list] = {}
            for entry in entries:
                # Category name stored as "Section › Subcategory" or just name
                full_name = entry["category_name"] or ""
                if " › " in full_name:
                    section, label = full_name.split(" › ", 1)
                else:
                    section, label = "General", full_name
                if section not in sections_map:
                    sections_map[section] = []
                count = entry.get("product_count") or 0
                sections_map[section].append({
                    "ddcode": entry["category_slug_or_url"],
                    "label": label,
                    "item_count": count,
                })
                if scraper_key != "vickerman":
                    total_products += count

            if scraper_key != "vickerman":
                section_listing_total = total_products
            if scraper_key == "accent_decor":
                try:
                    from app.libs.accent_decor_scraper import _discover_klevu_catalog_summary
                    catalog_summary = await asyncio.to_thread(_discover_klevu_catalog_summary)
                    live_unique_total = int(catalog_summary.get("unique_total") or 0)
                    if live_unique_total > 0:
                        total_products = live_unique_total
                    section_listing_total = int(
                        catalog_summary.get("section_listing_total") or section_listing_total
                    )
                    print(
                        "[discover-catalog] Accent live count from Klevu: "
                        f"{total_products:,} unique products across "
                        f"{section_listing_total:,} section listings"
                    )
                except Exception as exc:
                    print(f"[discover-catalog] Accent live count failed; using cached category sum: {exc}")

            catalog_sections = [
                CatalogSection(name=name, subcategories=subs)
                for name, subs in sections_map.items()
            ]
            return DiscoverCatalogResponse(
                sections=catalog_sections,
                total_subcategories=sum(len(s.subcategories) for s in catalog_sections),
                total_products=total_products,
                from_cache=True,
                section_listing_total=section_listing_total,
                catalog_summary=catalog_summary,
            )

    # ── Live crawl path (cache stale or force_refresh=True) ───────────────────
    print(f"[discover-catalog] Live crawl for supplier {supplier_id} (force={force_refresh}, stale={not cache_is_fresh})")
    try:
        if scraper_key == "allstate":
            from app.libs.allstate_scraper import discover_allstate_catalog
            result = await discover_allstate_catalog(
                username=username,
                password=password,
                progress_callback=None,
                supplier_id=supplier_id,  # saves fresh index to DB after crawl
                use_cache=not force_refresh,
                apply_filters=False,
            )
        elif scraper_key == "accent_decor":
            from app.libs.accent_decor_scraper import discover_accent_decor_catalog
            result = await discover_accent_decor_catalog(
                username=username,
                password=password,
                progress_callback=None,
                supplier_id=supplier_id,
                use_cache=False,
            )
        elif scraper_key == "regency":
            from app.libs.regency_scraper import discover_regency_catalog
            result = await discover_regency_catalog(
                username=username,
                password=password,
                progress_callback=None,
                supplier_id=supplier_id,
                use_cache=False,
            )
        elif scraper_key == "select_artificial":
            from app.libs.select_artificial_scraper import discover_select_artificial_catalog
            result = await discover_select_artificial_catalog(
                username=username,
                password=password,
                progress_callback=None,
                supplier_id=supplier_id,
                use_cache=False,
            )
        else:
            from app.libs.vickerman_scraper import discover_vickerman_catalog
            result = await discover_vickerman_catalog(
                username=username,
                password=password,
                progress_callback=None,
                supplier_id=supplier_id,
                use_cache=False,
            )
    except ValueError as exc:
        conn = await get_conn()
        try:
            await conn.execute(
                "UPDATE suppliers SET credential_status = 'failed', updated_at = NOW() WHERE id = $1",
                supplier_id,
            )
        finally:
            await conn.close()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Catalog discovery failed: {str(exc)[:300]}")
    conn = await get_conn()
    try:
        await conn.execute(
            "UPDATE suppliers SET credential_status = 'ok', updated_at = NOW() WHERE id = $1",
            supplier_id,
        )
    finally:
        await conn.close()
    subcategories = result["subcategories"]

    sections_map2: dict[str, list] = {}
    for sub in subcategories:
        section = sub.get("section") or "General"
        if section not in sections_map2:
            sections_map2[section] = []
        sections_map2[section].append({
            "ddcode": sub.get("ddcode") or sub.get("slug"),
            "label": sub.get("label") or sub.get("ddcode") or sub.get("slug"),
            "item_count": sub.get("item_count", 0),
        })

    catalog_sections2 = [
        CatalogSection(name=name, subcategories=subs)
        for name, subs in sections_map2.items()
    ]
    return DiscoverCatalogResponse(
        sections=catalog_sections2,
        total_subcategories=len(subcategories),
        total_products=result["total_products"],
        from_cache=False,
        section_listing_total=int(result.get("section_listing_total") or result["total_products"]),
        catalog_summary=result.get("catalog_summary"),
    )
