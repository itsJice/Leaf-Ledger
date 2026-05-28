from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Any
import asyncpg
import asyncio
import os
import uuid
import json
import databutton as db
from datetime import datetime

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

DATABASE_URL = os.environ.get("DATABASE_URL")

async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


def _infer_scraper_key(name: Optional[str], scraper_key: Optional[str] = None) -> Optional[str]:
    """Normalize the configured scraper key, falling back to supplier name."""
    key = (scraper_key or "").strip().lower()
    if key:
        return "accent_decor" if key == "accent" else key
    lower = (name or "").lower()
    if "allstate" in lower:
        return "allstate"
    if "accent" in lower:
        return "accent_decor"
    return None


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
    has_credentials: bool = False  # True if login_username + login_password are stored
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

# ---------- Endpoints ----------

@router.get("/list", response_model=List[SupplierOut])
async def list_suppliers():
    conn = await get_conn()
    try:
        rows = await conn.fetch("""
            SELECT s.*, COUNT(p.id) as product_count,
                   (s.login_username IS NOT NULL AND s.login_username != '' AND s.login_password IS NOT NULL AND s.login_password != '') as has_credentials
            FROM suppliers s
            LEFT JOIN products p ON p.supplier_id = s.id AND p.is_active = TRUE
            GROUP BY s.id
            ORDER BY s.name
        """)
        return [dict(r) for r in rows]
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

    if scraper_key not in ("allstate", "accent_decor"):
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
            sections_map: dict[str, list] = {}
            total_products = 0
            for entry in cached:
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
                total_products += count

            catalog_sections = [
                CatalogSection(name=name, subcategories=subs)
                for name, subs in sections_map.items()
            ]
            return DiscoverCatalogResponse(
                sections=catalog_sections,
                total_subcategories=sum(len(s.subcategories) for s in catalog_sections),
                total_products=total_products,
                from_cache=True,
            )

    # ── Live crawl path (cache stale or force_refresh=True) ───────────────────
    print(f"[discover-catalog] Live crawl for supplier {supplier_id} (force={force_refresh}, stale={not cache_is_fresh})")
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
    else:
        from app.libs.accent_decor_scraper import discover_accent_decor_catalog
        result = await discover_accent_decor_catalog(
            username=username,
            password=password,
            progress_callback=None,
            supplier_id=supplier_id,
        )
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
    )
