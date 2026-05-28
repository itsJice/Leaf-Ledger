"""Admin dashboard API — supplier sync health, product stats, and price change logs."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import asyncpg
import os
from datetime import datetime
from app.libs.scraper_base import rebuild_category_index, get_category_index_summary

router = APIRouter(prefix="/admin", tags=["admin"])
DATABASE_URL = os.environ.get("DATABASE_URL")


# ─── Category Index Models & Endpoints ───────────────────────────────────────────

class CategoryIndexRow(BaseModel):
    id: int
    category_name: str
    category_slug_or_url: str
    product_count: Optional[int]
    is_active: bool
    last_verified_at: Optional[datetime]
    created_at: Optional[datetime]


class SupplierCategoryIndex(BaseModel):
    supplier_id: int
    supplier_name: str
    scraper_key: Optional[str]
    total_categories: int
    active_categories: int
    total_cached_products: int
    oldest_verified_at: Optional[datetime]
    categories: list[CategoryIndexRow]


class CategoryIndexResponse(BaseModel):
    suppliers: list[SupplierCategoryIndex]


class RebuildIndexResponse(BaseModel):
    supplier_id: int
    scraper_key: str
    rows_deleted: int
    message: str


@router.get("/category-index", response_model=CategoryIndexResponse)
async def get_category_index():
    """Return the full category index for all suppliers that have a scraper."""
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        suppliers = await conn.fetch("""
            SELECT id, name, scraper_key
            FROM suppliers
            WHERE scraper_key IS NOT NULL
            ORDER BY name
        """)

        result: list[SupplierCategoryIndex] = []
        for sup in suppliers:
            rows = await get_category_index_summary(sup["id"], sup["scraper_key"])
            active = [r for r in rows if r["is_active"]]
            total_products = sum(r["product_count"] or 0 for r in active)

            verified_dates = [
                datetime.fromisoformat(r["last_verified_at"])
                for r in active
                if r["last_verified_at"]
            ]
            oldest = min(verified_dates) if verified_dates else None

            result.append(SupplierCategoryIndex(
                supplier_id=sup["id"],
                supplier_name=sup["name"],
                scraper_key=sup["scraper_key"],
                total_categories=len(rows),
                active_categories=len(active),
                total_cached_products=total_products,
                oldest_verified_at=oldest,
                categories=[
                    CategoryIndexRow(
                        id=r["id"],
                        category_name=r["category_name"],
                        category_slug_or_url=r["category_slug_or_url"],
                        product_count=r["product_count"],
                        is_active=r["is_active"],
                        last_verified_at=datetime.fromisoformat(r["last_verified_at"]) if r["last_verified_at"] else None,
                        created_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else None,
                    )
                    for r in rows
                ],
            ))

        return CategoryIndexResponse(suppliers=result)
    finally:
        await conn.close()


@router.post("/category-index/{supplier_id}/rebuild", response_model=RebuildIndexResponse)
async def rebuild_supplier_category_index(supplier_id: int):
    """Wipe the category index so the next scrape does a full re-discovery."""
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        row = await conn.fetchrow(
            "SELECT scraper_key FROM suppliers WHERE id = $1", supplier_id
        )
        if not row or not row["scraper_key"]:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Supplier not found or has no scraper key")
        scraper_key = row["scraper_key"]
    finally:
        await conn.close()

    deleted = await rebuild_category_index(supplier_id, scraper_key)
    return RebuildIndexResponse(
        supplier_id=supplier_id,
        scraper_key=scraper_key,
        rows_deleted=deleted,
        message=f"Index cleared ({deleted} rows deleted). Next scrape will do a full re-discovery.",
    )


# ─── Existing models below ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

class SupplierHealth(BaseModel):
    id: int
    name: str
    scraper_key: Optional[str]
    scraper_enabled: bool
    credential_status: str          # 'ok'/'verified' | 'untested' | 'missing' | 'error'
    last_full_sync_at: Optional[datetime]
    last_price_synced_at: Optional[datetime]
    product_count: int
    missing_images: int
    missing_prices: int
    sync_frequency_hours: Optional[int]
    # Last sync run stats
    last_sync_status: Optional[str]
    last_sync_inserted: Optional[int]
    last_sync_updated: Optional[int]
    last_sync_failed: Optional[int]
    last_sync_price_changes: Optional[int]
    last_sync_error: Optional[str]
    last_sync_duration_s: Optional[float]


class SyncLogEntry(BaseModel):
    id: int
    supplier_id: int
    supplier_name: str
    sync_type: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    products_found: Optional[int]
    products_inserted: Optional[int]
    products_updated: Optional[int]
    products_skipped: Optional[int]
    products_failed: Optional[int]
    price_changes: Optional[int]
    error_message: Optional[str]
    duration_s: Optional[float]


class PriceChangeEntry(BaseModel):
    id: int
    product_id: int
    product_name: str
    supplier_name: str
    old_price: Optional[float]
    new_price: Optional[float]
    change_pct: Optional[float]
    source: str
    changed_at: datetime


class DashboardSummary(BaseModel):
    total_suppliers: int
    suppliers_with_scraper: int
    suppliers_with_credentials: int
    suppliers_synced_this_week: int
    total_products: int
    products_missing_images: int
    products_missing_prices: int
    price_changes_this_week: int
    failed_syncs_this_week: int


class AdminDashboardResponse(BaseModel):
    summary: DashboardSummary
    supplier_health: list[SupplierHealth]
    recent_syncs: list[SyncLogEntry]
    recent_price_changes: list[PriceChangeEntry]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=AdminDashboardResponse)
async def get_admin_dashboard():
    """Return full admin dashboard: supplier health, sync history, and price changes."""
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        # ── Per-supplier health rows ──────────────────────────────────────────
        health_rows = await conn.fetch("""
            SELECT
                s.id,
                s.name,
                s.scraper_key,
                COALESCE(s.scraper_enabled, false) AS scraper_enabled,
                COALESCE(s.credential_status, 'missing') AS credential_status,
                s.last_full_sync_at,
                s.last_price_synced_at,
                COALESCE(s.sync_frequency_hours, 168) AS sync_frequency_hours,
                COUNT(p.id) FILTER (WHERE p.is_active)                   AS product_count,
                COUNT(p.id) FILTER (WHERE p.is_active AND p.photo_url IS NULL) AS missing_images,
                COUNT(p.id) FILTER (WHERE p.is_active AND p.current_price IS NULL) AS missing_prices,
                -- Last sync log for this supplier
                (
                    SELECT l.status FROM scrape_sync_logs l
                    WHERE l.supplier_id = s.id ORDER BY l.started_at DESC LIMIT 1
                ) AS last_sync_status,
                (
                    SELECT l.products_inserted FROM scrape_sync_logs l
                    WHERE l.supplier_id = s.id ORDER BY l.started_at DESC LIMIT 1
                ) AS last_sync_inserted,
                (
                    SELECT l.products_updated FROM scrape_sync_logs l
                    WHERE l.supplier_id = s.id ORDER BY l.started_at DESC LIMIT 1
                ) AS last_sync_updated,
                (
                    SELECT l.products_failed FROM scrape_sync_logs l
                    WHERE l.supplier_id = s.id ORDER BY l.started_at DESC LIMIT 1
                ) AS last_sync_failed,
                (
                    SELECT l.price_changes FROM scrape_sync_logs l
                    WHERE l.supplier_id = s.id ORDER BY l.started_at DESC LIMIT 1
                ) AS last_sync_price_changes,
                (
                    SELECT l.error_message FROM scrape_sync_logs l
                    WHERE l.supplier_id = s.id ORDER BY l.started_at DESC LIMIT 1
                ) AS last_sync_error,
                (
                    SELECT EXTRACT(EPOCH FROM (l.completed_at - l.started_at))
                    FROM scrape_sync_logs l
                    WHERE l.supplier_id = s.id ORDER BY l.started_at DESC LIMIT 1
                ) AS last_sync_duration_s
            FROM suppliers s
            LEFT JOIN products p ON p.supplier_id = s.id
            GROUP BY s.id, s.name, s.scraper_key, s.scraper_enabled,
                     s.credential_status, s.last_full_sync_at, s.last_price_synced_at,
                     s.sync_frequency_hours
            ORDER BY s.name
        """)

        # ── Recent sync logs ──────────────────────────────────────────────────
        sync_rows = await conn.fetch("""
            SELECT
                l.id, l.supplier_id, s.name AS supplier_name,
                l.sync_type, l.status, l.started_at, l.completed_at,
                l.products_found, l.products_inserted, l.products_updated,
                l.products_skipped, l.products_failed, l.price_changes,
                l.error_message,
                EXTRACT(EPOCH FROM (COALESCE(l.completed_at, now()) - l.started_at)) AS duration_s
            FROM scrape_sync_logs l
            JOIN suppliers s ON s.id = l.supplier_id
            ORDER BY l.started_at DESC
            LIMIT 50
        """)

        # ── Recent price changes (last 7 days) ────────────────────────────────
        price_rows = await conn.fetch("""
            SELECT
                ph.id, ph.product_id,
                p.name AS product_name,
                s.name AS supplier_name,
                ph.old_price, ph.new_price,
                CASE
                    WHEN ph.old_price IS NOT NULL AND ph.old_price != 0
                    THEN ROUND(((ph.new_price - ph.old_price) / ph.old_price * 100)::numeric, 1)
                    ELSE NULL
                END AS change_pct,
                ph.source,
                ph.changed_at
            FROM product_price_history ph
            JOIN products p ON p.id = ph.product_id
            JOIN suppliers s ON s.id = p.supplier_id
            WHERE ph.changed_at >= now() - interval '7 days'
            ORDER BY ph.changed_at DESC
            LIMIT 100
        """)

        # ── Summary counts ────────────────────────────────────────────────────
        summary_row = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM suppliers) AS total_suppliers,
                (SELECT COUNT(*) FROM suppliers WHERE scraper_key IS NOT NULL) AS suppliers_with_scraper,
                (SELECT COUNT(*) FROM suppliers
                 WHERE login_username IS NOT NULL AND login_username != ''
                   AND login_password IS NOT NULL AND login_password != '') AS suppliers_with_credentials,
                (SELECT COUNT(*) FROM suppliers
                 WHERE last_full_sync_at >= now() - interval '7 days'
                    OR last_price_synced_at >= now() - interval '7 days') AS suppliers_synced_this_week,
                (SELECT COUNT(*) FROM products WHERE is_active) AS total_products,
                (SELECT COUNT(*) FROM products WHERE is_active AND photo_url IS NULL) AS products_missing_images,
                (SELECT COUNT(*) FROM products WHERE is_active AND current_price IS NULL) AS products_missing_prices,
                (SELECT COUNT(*) FROM product_price_history WHERE changed_at >= now() - interval '7 days') AS price_changes_this_week,
                (SELECT COUNT(*) FROM scrape_sync_logs WHERE status = 'error' AND started_at >= now() - interval '7 days') AS failed_syncs_this_week
        """)

        return AdminDashboardResponse(
            summary=DashboardSummary(**dict(summary_row)),
            supplier_health=[
                SupplierHealth(**dict(r)) for r in health_rows
            ],
            recent_syncs=[
                SyncLogEntry(**dict(r)) for r in sync_rows
            ],
            recent_price_changes=[
                PriceChangeEntry(**dict(r)) for r in price_rows
            ],
        )
    finally:
        await conn.close()


@router.post("/toggle-scraper/{supplier_id}")
async def toggle_scraper(supplier_id: int, enabled: bool):
    """Enable or disable the automated scraper for a supplier."""
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        await conn.execute(
            "UPDATE suppliers SET scraper_enabled = $2, updated_at = now() WHERE id = $1",
            supplier_id, enabled,
        )
        return {"ok": True, "scraper_enabled": enabled}
    finally:
        await conn.close()
