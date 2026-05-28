"""Scraper API - trigger supplier catalog scrapes and track job progress."""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import asyncpg
import asyncio
import threading
import os
import json
import databutton as db
from datetime import datetime
from urllib.parse import unquote

router = APIRouter(prefix="/scraper", tags=["scraper"])
DATABASE_URL = os.environ.get("DATABASE_URL")


async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


def _resolve_scraper_key(supplier_name: str, scraper_key: Optional[str]) -> str:
    """Prefer the configured scraper_key, with a name-based fallback for older rows."""
    key = (scraper_key or "").lower().strip()
    if key:
        return "accent_decor" if key == "accent" else key
    name = (supplier_name or "").lower()
    if "allstate" in name:
        return "allstate"
    if "accent" in name:
        return "accent_decor"
    return ""


# Models

class ScrapeJobOut(BaseModel):
    id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    status: str  # pending | running | done | failed
    phase: Optional[str] = None  # discovering | scraping | ready | importing | done | failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    products_found: int = 0
    products_imported: int = 0
    products_importing: int = 0  # live counter during import phase
    total_expected: Optional[int] = None
    progress_message: Optional[str] = None
    error_message: Optional[str] = None
    result_key: Optional[str] = None
    created_at: datetime
    # Structured milestone roadmap — populated live as the scraper runs
    milestone_log: Optional[dict] = None


class ScrapedProductOut(BaseModel):
    sku: str
    name: str
    base_price: Optional[float] = None
    uom: Optional[str] = None
    min_qty: Optional[int] = None
    avail_qty: Optional[str] = None
    upc: Optional[str] = None
    description: Optional[str] = None
    photo_url: Optional[str] = None
    category: Optional[str] = None
    color_group: Optional[str] = None
    country_of_origin: Optional[str] = None
    raw: dict = {}
    case_qty: Optional[int] = None
    box_qty: Optional[int] = None
    availability_note: Optional[str] = None
    length_in: Optional[float] = None
    weight_lb: Optional[float] = None
    material: Optional[str] = None


class StartScrapeRequest(BaseModel):
    supplier_id: int
    max_products: Optional[int] = None  # None = all; set small number for test runs


class ImportScrapedRequest(BaseModel):
    job_id: int
    supplier_id: int
    selected_skus: Optional[List[str]] = None  # None = import all


class SupplierEnrichmentStatusOut(BaseModel):
    supplier_id: int
    total_active: int = 0
    detail_stored: int = 0
    detail_pending: int = 0
    detail_failed: int = 0
    images_stored: int = 0
    images_external: int = 0
    images_with_reference: int = 0
    images_pending: int = 0
    images_failed: int = 0
    images_missing: int = 0
    last_backfill: Optional[dict] = None


# Background worker

async def _run_scrape_job(
    job_id: int,
    supplier_id: int,
    supplier_name: str,
    scraper_key: str,
    username: str,
    password: str,
    max_products: Optional[int],
):
    """Background task: 3-phase scrape.

    Phase 1 (discovering): Walk all subcategories, count every product so we know the exact total.
    Phase 2 (scraping):    Scrape product data using the pre-built subcategory list.
    Status becomes 'ready' when done — user then clicks Import to write to the product library.
    """

    # Track whether the job has reached a terminal state so callbacks can't overwrite it
    _terminal: dict = {"reached": False}

    async def update_status(**kwargs):
        # Never let a callback overwrite a terminal done/ready/failed state
        if _terminal["reached"] and "status" not in kwargs:
            return
        if kwargs.get("status") in ("done", "failed") or kwargs.get("phase") in ("ready", "failed"):
            _terminal["reached"] = True
        try:
            c = await get_conn()
            sets = ", ".join(f"{k}=${i+1}" for i, k in enumerate(kwargs))
            vals = list(kwargs.values()) + [job_id]
            await c.execute(f"UPDATE scrape_jobs SET {sets} WHERE id=${len(vals)}", *vals)
            await c.close()
        except Exception as ex:
            print(f"[job {job_id}] status update error: {ex}")

    # milestone_log state — mutated in-place and written to DB on each change
    milestones: dict = {
        "logged_in": False,
        "pages_accessible": False,
        "categories_discovered": False,
        "categories": [],  # [{name, slug, total, collected, done}]
    }

    async def update_milestones():
        """Write current milestone_log state to the scrape_jobs row."""
        if _terminal["reached"]:
            return  # don't let milestone writes race with the final status
        try:
            c = await get_conn()
            await c.execute(
                "UPDATE scrape_jobs SET milestone_log=$1 WHERE id=$2",
                json.dumps(milestones),  # asyncpg needs a JSON string for jsonb columns
                job_id,
            )
            await c.close()
        except Exception as ex:
            print(f"[job {job_id}] milestone update error: {ex}")

    await update_status(status="running", phase="discovering", started_at=datetime.utcnow())

    try:
        scraper_key = _resolve_scraper_key(supplier_name, scraper_key)

        # ── Phase 1: Discover ──────────────────────────────────────────────────
        subcategories: list[dict] = []
        total_products = 0

        if scraper_key == "allstate":
            from app.libs.allstate_scraper import discover_allstate_catalog

            async def on_discover(cats_done, cats_total, msg, *, milestone_event=None, category_info=None):
                """Called during discovery phase with optional structured events."""
                print(f"[job {job_id}] discover: {msg}")

                # Handle structured milestone events from the scraper
                if milestone_event == "logged_in":
                    milestones["logged_in"] = True
                    milestones["pages_accessible"] = True
                    await update_milestones()

                elif milestone_event == "category_found" and category_info:
                    # A new category was discovered — add it to the list
                    milestones["categories"].append({
                        "name": category_info["name"],
                        "slug": category_info.get("slug", ""),
                        "section": category_info.get("section", ""),
                        "total": category_info.get("total", 0),
                        "collected": 0,
                        "done": False,
                    })
                    if cats_done >= cats_total and cats_total > 0:
                        milestones["categories_discovered"] = True
                    await update_milestones()

                elif milestone_event == "categories_done":
                    milestones["categories_discovered"] = True
                    await update_milestones()

                await update_status(
                    phase="discovering",
                    products_found=cats_done,
                    total_expected=cats_total,
                    progress_message=msg,
                )

            catalog = await discover_allstate_catalog(username, password, on_discover, supplier_id=supplier_id)
            subcategories = catalog["subcategories"]
            total_products = catalog["total_products"]

            # Ensure categories_discovered is set
            milestones["categories_discovered"] = True
            # Rebuild categories list from full discovery result (has accurate totals)
            milestones["categories"] = [
                {
                    # label can be an empty string — fall back to ddcode so
                    # the UI always has something to display
                    "name": s.get("label") or s.get("ddcode", ""),
                    "slug": s.get("ddcode", ""),
                    "section": s.get("section", ""),
                    "total": s.get("item_count", 0),
                    "collected": 0,
                    "done": False,
                }
                for s in subcategories
            ]
            await update_milestones()

        elif scraper_key in ("accent", "accent_decor"):
            from app.libs.accent_decor_scraper import discover_accent_decor_catalog

            async def on_accent_discover(cats_done, cats_total, msg, *, milestone_event=None, category_info=None):
                print(f"[job {job_id}] accent discover: {msg}")
                if milestone_event == "logged_in":
                    milestones["logged_in"] = True
                    milestones["pages_accessible"] = True
                    await update_milestones()
                elif milestone_event == "category_found" and category_info:
                    milestones["categories"].append({
                        "name": category_info["name"],
                        "slug": category_info.get("slug", ""),
                        "section": category_info.get("section", ""),
                        "total": category_info.get("total", 0),
                        "collected": 0,
                        "done": False,
                    })
                    await update_milestones()
                elif milestone_event == "categories_done":
                    milestones["categories_discovered"] = True
                    await update_milestones()
                await update_status(
                    phase="discovering",
                    products_found=cats_done,
                    total_expected=cats_total,
                    progress_message=msg,
                )

            catalog = await discover_accent_decor_catalog(username, password, on_accent_discover, supplier_id=supplier_id)
            subcategories = catalog["subcategories"]
            total_products = catalog["total_products"]
            milestones["categories_discovered"] = True
            milestones["categories"] = [
                {
                    "name": s.get("label", s.get("slug", "")),
                    "slug": s.get("slug", ""),
                    "section": "",
                    "total": s.get("item_count", 0),
                    "collected": 0,
                    "done": False,
                }
                for s in subcategories
            ]
            await update_milestones()
        else:
            raise ValueError(f"No scraper configured for '{supplier_name}' (scraper_key='{scraper_key}').")

        # Cap total to max_products if set
        capped_total = min(total_products, max_products) if max_products else total_products
        print(f"[job {job_id}] Discovery complete: {total_products:,} products in {len(subcategories)} subcategories")
        await update_status(
            phase="scraping",
            products_found=0,
            total_expected=capped_total,
            progress_message=f"Found {total_products:,} products across {len(subcategories)} categories. Scraping now...",
        )

        # ── Phase 2: Scrape ─────────────────────────────────────────────────────────────────
        products: list[dict] = []
        # Build a fast lookup: slug -> index in milestones["categories"]
        cat_index: dict[str, int] = {
            c["slug"]: i for i, c in enumerate(milestones["categories"])
        }
        current_cat_slug: dict = {"v": ""}  # mutable container for current category

        async def hydrate_milestone_categories():
            """Ensure cached-discovery runs still have category rows for progress."""
            if milestones["categories"]:
                return
            built: list[dict] = []
            for s in subcategories:
                slug = s.get("ddcode") or s.get("slug") or ""
                built.append({
                    "name": s.get("label") or s.get("category_name") or slug,
                    "slug": slug,
                    "section": s.get("section", ""),
                    "total": s.get("item_count", 0),
                    "collected": 0,
                    "done": False,
                })
            milestones["categories"] = built
            cat_index.clear()
            cat_index.update({c["slug"]: i for i, c in enumerate(milestones["categories"])})
            await update_milestones()

        async def on_scrape(done, total, msg, *, category_slug=None, category_collected=None):
            print(f"[job {job_id}] scrape: {msg}")
            milestone_dirty = False

            if category_slug and not milestones["categories"]:
                await hydrate_milestone_categories()

            # If scraper tells us which category it just finished or is working on
            if category_slug and category_slug != current_cat_slug["v"]:
                # Mark previous category done
                if current_cat_slug["v"] and current_cat_slug["v"] in cat_index:
                    idx = cat_index[current_cat_slug["v"]]
                    milestones["categories"][idx]["done"] = True
                    milestone_dirty = True
                current_cat_slug["v"] = category_slug

            if category_slug and category_slug in cat_index and category_collected is not None:
                idx = cat_index[category_slug]
                milestones["categories"][idx]["collected"] = category_collected
                milestone_dirty = True

            if milestone_dirty:
                await update_milestones()

            await update_status(
                phase="scraping",
                products_found=done,
                total_expected=total,
                progress_message=msg,
            )

        if scraper_key == "allstate":
            from app.libs.allstate_scraper import scrape_allstate
            async for product in scrape_allstate(
                username, password, max_products, on_scrape, subcategories=subcategories, supplier_id=supplier_id
            ):
                products.append({
                    "sku": product.sku,
                    "name": product.name,
                    "base_price": product.base_price,
                    "uom": product.uom,
                    "min_qty": product.moq,
                    "box_qty": product.box_qty,
                    "case_qty": product.case_qty,
                    "avail_qty": product.availability,
                    "availability_note": product.availability_note,
                    "upc": product.upc,
                    "description": product.description,
                    "photo_url": product.photo_url,
                    "category": product.category,
                    "color_group": product.color,
                    "country_of_origin": product.country_of_origin,
                    "length_in": product.length_in,
                    "weight_lb": product.weight_lb,
                    "material": product.material,
                    "raw": product.raw,
                })
        elif scraper_key in ("accent", "accent_decor"):
            from app.libs.accent_decor_scraper import scrape_accent_decor
            async for product in scrape_accent_decor(
                username, password, max_products, on_scrape, subcategories=subcategories, supplier_id=supplier_id
            ):
                products.append({
                    "sku": product.sku,
                    "name": product.name,
                    "base_price": product.base_price,
                    "uom": product.uom,
                    "min_qty": product.moq,
                    "box_qty": product.box_qty,
                    "case_qty": product.case_qty,
                    "avail_qty": product.availability,
                    "availability_note": product.availability_note,
                    "upc": product.upc,
                    "description": product.description,
                    "photo_url": product.photo_url,
                    "category": product.category,
                    "color_group": product.color,
                    "country_of_origin": product.country_of_origin,
                    "length_in": product.length_in,
                    "weight_lb": product.weight_lb,
                    "material": product.material,
                    "raw": product.raw,
                })

        # Cache to storage for the import step
        result_key = f"scrape_job_{job_id}.json"
        db.storage.text.put(result_key, json.dumps(products))

        # Mark all categories as done and set data_saved milestone
        for cat in milestones["categories"]:
            cat["done"] = True
        milestones["data_saved"] = True
        await update_milestones()

        await update_status(
            status="done",
            phase="ready",
            completed_at=datetime.utcnow(),
            products_found=len(products),
            total_expected=len(products),
            result_key=result_key,
            progress_message=f"Ready to import — {len(products):,} products collected.",
        )
        print(f"[job {job_id}] Scrape complete: {len(products):,} products ready to import.")

    except Exception as e:
        print(f"[job {job_id}] FAILED: {e}")
        await update_status(
            status="failed",
            phase="failed",
            completed_at=datetime.utcnow(),
            error_message=str(e)[:500],
        )


# ── Price-only sync background worker ──────────────────────────────────────

async def _run_price_sync(supplier_id: int, supplier_name: str, scraper_key: str, username: str, password: str):
    """Scrape all products for a supplier but only update prices on existing records.
    Much faster than a full catalog import — skips photos, descriptions, etc."""
    print(f"[price-sync] Starting for supplier {supplier_id} ({supplier_name})")
    conn = await get_conn()
    try:
        await conn.execute(
            "UPDATE suppliers SET last_price_synced_at = NOW() WHERE id = $1", supplier_id
        )
    finally:
        await conn.close()

    try:
        scraped: list[dict] = []
        scraper_key = (scraper_key or "").lower().strip()

        async def noop_progress(done, total, msg, *args, **kwargs):
            print(f"[price-sync] {msg}")

        if scraper_key == "allstate":
            from app.libs.allstate_scraper import discover_allstate_catalog, scrape_allstate
            catalog = await discover_allstate_catalog(username, password, noop_progress, supplier_id=supplier_id)
            async for product in scrape_allstate(
                username, password, None, noop_progress,
                subcategories=catalog["subcategories"], supplier_id=supplier_id
            ):
                scraped.append({"sku": product.sku, "base_price": product.base_price})
        elif scraper_key in ("accent", "accent_decor"):
            from app.libs.accent_decor_scraper import discover_accent_decor_catalog, scrape_accent_decor
            catalog = await discover_accent_decor_catalog(username, password, noop_progress, supplier_id=supplier_id)
            async for product in scrape_accent_decor(
                username, password, None, noop_progress,
                subcategories=catalog["subcategories"], supplier_id=supplier_id
            ):
                scraped.append({"sku": product.sku, "base_price": product.base_price})
        else:
            print(f"[price-sync] No scraper for '{supplier_name}' — skipping")
            return

        if not scraped:
            print(f"[price-sync] No products returned for {supplier_name}")
            return

        # Update prices in DB, recording history for any changes
        conn = await get_conn()
        try:
            updated = 0
            changes = 0
            for item in scraped:
                sku = item["sku"]
                new_price = item["base_price"]
                if new_price is None:
                    continue

                row = await conn.fetchrow(
                    "SELECT id, current_price FROM products WHERE supplier_id=$1 AND supplier_sku=$2 AND is_active=TRUE",
                    supplier_id, sku
                )
                if not row:
                    continue  # Don't add new products during price-only sync

                old_price = float(row["current_price"]) if row["current_price"] is not None else None
                product_id = row["id"]

                # Always update price_updated_at; only log history if price actually changed
                await conn.execute(
                    "UPDATE products SET current_price=$1, price_updated_at=NOW(), updated_at=NOW() WHERE id=$2",
                    new_price, product_id
                )
                updated += 1

                if old_price != new_price:
                    await conn.execute(
                        """INSERT INTO product_price_history (product_id, old_price, new_price, source)
                           VALUES ($1, $2, $3, 'scrape')""",
                        product_id, old_price, new_price
                    )
                    changes += 1

            # Stamp final sync time on supplier
            await conn.execute(
                "UPDATE suppliers SET last_price_synced_at=NOW() WHERE id=$1", supplier_id
            )
            print(f"[price-sync] Done: {updated} prices updated, {changes} price changes detected")
        finally:
            await conn.close()

    except Exception as e:
        print(f"[price-sync] FAILED for supplier {supplier_id}: {e}")


class PriceSyncResponse(BaseModel):
    ok: bool
    message: str


@router.post("/sync-prices/{supplier_id}", response_model=PriceSyncResponse)
async def sync_prices(
    supplier_id: int,
    background_tasks: BackgroundTasks,
):
    """Trigger a price-only sync for a supplier. Updates existing product prices fast."""
    conn = await get_conn()
    async def ensure_conn():
        nonlocal conn
        if conn.is_closed():
            conn = await get_conn()
        return conn

    async def refresh_conn():
        nonlocal conn
        try:
            if not conn.is_closed():
                await conn.close()
        except Exception:
            pass
        conn = await get_conn()
        return conn

    try:
        supplier = await conn.fetchrow(
            "SELECT id, name, scraper_key, login_username, login_password FROM suppliers WHERE id=$1",
            supplier_id,
        )
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        if not supplier["login_username"] or not supplier["login_password"]:
            raise HTTPException(
                status_code=400,
                detail="No credentials saved for this supplier.",
            )
        background_tasks.add_task(
            _run_price_sync,
            supplier["id"],
            supplier["name"],
            _resolve_scraper_key(supplier["name"], supplier["scraper_key"]),
            supplier["login_username"],
            supplier["login_password"],
        )
        # Stamp started time immediately so UI can reflect it
        await conn.execute(
            "UPDATE suppliers SET last_price_synced_at=NOW() WHERE id=$1", supplier_id
        )
        return PriceSyncResponse(ok=True, message=f"Price sync started for {supplier['name']}")
    finally:
        await conn.close()


class BulkPriceSyncRequest(BaseModel):
    supplier_ids: Optional[List[int]] = None  # None = all suppliers with credentials


@router.post("/sync-prices-bulk", response_model=PriceSyncResponse)
async def sync_prices_bulk(
    body: BulkPriceSyncRequest,
    background_tasks: BackgroundTasks,
):
    """Sync prices for multiple suppliers at once. Used for auto-sync on arrangement/invoice open."""
    conn = await get_conn()
    try:
        if body.supplier_ids:
            rows = await conn.fetch(
                """SELECT id, name, scraper_key, login_username, login_password FROM suppliers
                   WHERE id = ANY($1) AND login_username IS NOT NULL AND login_password IS NOT NULL""",
                body.supplier_ids,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, name, scraper_key, login_username, login_password FROM suppliers
                   WHERE login_username IS NOT NULL AND login_password IS NOT NULL
                   AND (last_price_synced_at IS NULL OR last_price_synced_at < NOW() - INTERVAL '23 hours')"""
            )

        count = 0
        for row in rows:
            background_tasks.add_task(
                _run_price_sync,
                row["id"],
                row["name"],
                _resolve_scraper_key(row["name"], row["scraper_key"]),
                row["login_username"],
                row["login_password"],
            )
            count += 1

        return PriceSyncResponse(ok=True, message=f"Price sync started for {count} supplier(s)")
    finally:
        await conn.close()


# Price history endpoint
class PriceHistoryEntry(BaseModel):
    id: int
    product_id: int
    old_price: Optional[float] = None
    new_price: float
    source: str
    changed_at: datetime


@router.get("/price-history/{product_id}", response_model=List[PriceHistoryEntry])
async def get_price_history(product_id: int):
    """Get price change history for a product."""
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """SELECT * FROM product_price_history WHERE product_id=$1 ORDER BY changed_at DESC LIMIT 50""",
            product_id,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# Endpoints

def _parse_job_row(row) -> dict:
    """Convert an asyncpg Record to a dict, decoding the milestone_log JSONB field."""
    d = dict(row)
    ml = d.get("milestone_log")
    if isinstance(ml, str):
        try:
            d["milestone_log"] = json.loads(ml)
        except Exception:
            d["milestone_log"] = {}
    return d


@router.post("/start", response_model=ScrapeJobOut)
async def start_scrape(
    body: StartScrapeRequest,
    background_tasks: BackgroundTasks,
):
    """Kick off a catalog scrape for a supplier. Credentials must be saved on the supplier record first."""
    conn = await get_conn()
    async def ensure_conn():
        nonlocal conn
        if conn.is_closed():
            conn = await get_conn()
        return conn

    async def refresh_conn():
        nonlocal conn
        try:
            if not conn.is_closed():
                await conn.close()
        except Exception:
            pass
        conn = await get_conn()
        return conn

    try:
        supplier = await conn.fetchrow(
            "SELECT id, name, scraper_key, login_username, login_password FROM suppliers WHERE id=$1",
            body.supplier_id,
        )
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        if not supplier["login_username"] or not supplier["login_password"]:
            raise HTTPException(
                status_code=400,
                detail="No login credentials stored for this supplier. Add them in the Suppliers page first.",
            )

        await conn.execute(
            """
            UPDATE scrape_jobs
            SET
                status='failed',
                phase='failed',
                completed_at=NOW(),
                error_message=COALESCE(error_message, 'Marked stale before starting a new scrape')
            WHERE supplier_id=$1
              AND status IN ('pending', 'running')
              AND completed_at IS NULL
              AND created_at < NOW() - INTERVAL '30 minutes'
            """,
            body.supplier_id,
        )

        running = await conn.fetchrow(
            """
            SELECT id
            FROM scrape_jobs
            WHERE supplier_id=$1
              AND status IN ('pending', 'running')
              AND (phase IS NULL OR phase IN ('discovering', 'scraping', 'importing'))
            """,
            body.supplier_id,
        )
        if running:
            raise HTTPException(status_code=409, detail="A scrape is already running for this supplier.")

        row = await conn.fetchrow(
            "INSERT INTO scrape_jobs (supplier_id, status) VALUES ($1, 'pending') RETURNING *",
            body.supplier_id,
        )
        job = _parse_job_row(row)
        job["supplier_name"] = supplier["name"]

        # Run the scraper in a dedicated thread so Playwright's heavy browser I/O
        # doesn't block FastAPI's event loop and starve other requests.
        def _run_in_thread():
            asyncio.run(_run_scrape_job(
                job["id"],
                body.supplier_id,
                supplier["name"],
                _resolve_scraper_key(supplier["name"], supplier["scraper_key"]),
                supplier["login_username"],
                supplier["login_password"],
                body.max_products,
            ))

        thread = threading.Thread(target=_run_in_thread, daemon=True)
        thread.start()
        return job
    finally:
        await conn.close()


@router.get("/jobs/{supplier_id}", response_model=List[ScrapeJobOut])
async def list_scrape_jobs(supplier_id: int):
    """List all scrape jobs for a supplier, newest first."""
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """SELECT j.*, s.name as supplier_name
               FROM scrape_jobs j JOIN suppliers s ON s.id=j.supplier_id
               WHERE j.supplier_id=$1 ORDER BY j.created_at DESC LIMIT 20""",
            supplier_id,
        )
        return [_parse_job_row(r) for r in rows]
    finally:
        await conn.close()


@router.get("/job/{job_id}", response_model=ScrapeJobOut)
async def get_scrape_job(job_id: int):
    """Poll current status of a scrape job."""
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            """SELECT j.*, s.name as supplier_name
               FROM scrape_jobs j JOIN suppliers s ON s.id=j.supplier_id
               WHERE j.id=$1""",
            job_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        return _parse_job_row(row)
    finally:
        await conn.close()


@router.get("/preview/{job_id}", response_model=List[ScrapedProductOut])
async def preview_scraped_products(job_id: int, limit: int = 50):
    """Return the first N scraped products for review before committing to the database."""
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT status, result_key, error_message FROM scrape_jobs WHERE id=$1", job_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        if not row["result_key"]:
            raise HTTPException(status_code=400, detail=f"Job has no cached preview data (status: {row['status']})")
        raw_json = db.storage.text.get(row["result_key"], default="[]")
        return json.loads(raw_json)[:limit]
    finally:
        await conn.close()


# All values must be in the products_category_check constraint
_VALID_CATEGORIES = {
    "containers", "wood", "greenery", "florals", "trees", "plant", "container",
    "filler", "accent", "accents", "other", "moss", "branches", "botanicals",
    "preserved", "seasonal", "stems", "foliage", "succulents", "topiaries",
    "wreaths", "baskets", "vases", "risers", "pedestals", "liners", "supplies",
}

def _map_category(cat_raw: str) -> str:
    """Map a raw scraped category string to a valid internal category."""
    c = (cat_raw or "").lower()
    # If the raw value is already a valid category, use it directly
    if c in _VALID_CATEGORIES:
        return c
    if any(w in c for w in ["flower", "floral", "bloom", "rose", "lily", "botanical"]):
        return "florals"
    if any(w in c for w in ["wreath", "garland", "swag"]):
        return "wreaths"
    if any(w in c for w in ["green", "fern", "leaf", "foliage", "ivy"]):
        return "greenery"
    if "moss" in c:
        return "moss"
    if any(w in c for w in ["tree", "topiar", "palm", "christmas"]):
        return "trees"
    if "succulent" in c:
        return "succulents"
    if any(w in c for w in ["container", "planter", "urn", "liner"]):
        return "containers"
    if "vase" in c:
        return "vases"
    if "basket" in c:
        return "baskets"
    if any(w in c for w in ["pedestal", "riser"]):
        return "pedestals"
    if any(w in c for w in ["wood", "twig", "branch", "bark", "driftwood"]):
        return "branches"
    if any(w in c for w in ["ribbon", "bow", "wire", "tape", "supply", "tool"]):
        return "supplies"
    if "preserved" in c:
        return "preserved"
    if any(w in c for w in ["seasonal", "holiday", "ornament", "stocking", "pillow", "decor", "accent"]):
        return "seasonal"
    if "stem" in c:
        return "stems"
    return "other"


def _map_unit(uom_raw: str) -> str:
    """Normalise a UOM string to internal unit values."""
    u = (uom_raw or "each").strip().lower()
    return {"ea": "each", "each": "each", "stem": "stem", "st": "stem",
            "pot": "pot", "flat": "flat", "bunch": "bunch", "bx": "box",
            "box": "box", "cs": "case", "case": "case"}.get(u, "each")


async def _run_import(job_id: int, supplier_id: int, selected_skus):
    """Background worker: upsert scraped products into the products table.
    Imports core rows quickly. Images/details are enriched by separate backfill jobs.
    """
    print(f"[import] Starting import for job {job_id}, supplier {supplier_id}")
    conn = await get_conn()
    async def ensure_conn():
        nonlocal conn
        if conn.is_closed():
            conn = await get_conn()
    async def refresh_conn():
        nonlocal conn
        try:
            if not conn.is_closed():
                await conn.close()
        except Exception:
            pass
        conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT result_key FROM scrape_jobs WHERE id=$1", job_id)
        if not row or not row["result_key"]:
            print(f"[import] No result_key for job {job_id}, aborting")
            return

        supplier = await conn.fetchrow(
            "SELECT name, scraper_key, login_username, login_password FROM suppliers WHERE id=$1",
            supplier_id,
        )
        scraper_key = _resolve_scraper_key(
            supplier["name"] if supplier else "",
            supplier["scraper_key"] if supplier else None,
        )

        all_products = json.loads(db.storage.text.get(row["result_key"], default="[]"))
        if selected_skus:
            sku_set = set(selected_skus)
            all_products = [p for p in all_products
                            if p.get("sku") in sku_set or p.get("supplier_sku") in sku_set]

        total = len(all_products)
        print(f"[import] Processing {total} products")
        inserted = 0
        updated = 0
        PROGRESS_EVERY = 25  # Update frequently so UI counter stays smooth

        start_at = await conn.fetchval(
            "SELECT COALESCE(products_importing, 0) FROM scrape_jobs WHERE id=$1",
            job_id,
        ) or 0
        if start_at > 0:
            print(f"[import] Resuming job {job_id} after {start_at}/{total}")

        for i, p in enumerate(all_products, start=1):
            if i <= start_at:
                continue
            if i % 100 == 1:
                await refresh_conn()
            await ensure_conn()
            sku = unquote((p.get("sku") or p.get("supplier_sku") or "").strip())
            name = (p.get("name") or sku or "Unknown").strip()
            description = p.get("description") or None
            raw_photo = p.get("photo_url") or None
            # Do not download supplier images during core import. Long image downloads
            # make imports fragile; detail/image backfill stores them afterward.
            photo_url = raw_photo if raw_photo and not raw_photo.startswith("http") else None
            # base_price may be float or None — cast explicitly to avoid asyncpg type inference issue
            raw_price = p.get("base_price")
            price: float | None = float(raw_price) if raw_price is not None else None
            category = _map_category(p.get("category") or "")
            unit = _map_unit(p.get("uom") or "")
            country = p.get("country_of_origin") or None
            color = p.get("color_group") or None
            raw_data = p.get("raw") or {}
            if raw_photo:
                raw_data = {
                    **raw_data,
                    "source_photo_url": raw_photo,
                    "image_status": "pending" if raw_photo.startswith("http") else "stored",
                    "detail_status": raw_data.get("detail_status") or "pending",
                    "scraper_key": scraper_key,
                }
            min_qty = p.get("min_qty")
            case_qty = p.get("case_qty")
            length_in = p.get("length_in")
            weight_lb = p.get("weight_lb")
            material = p.get("material") or raw_data.get("Material Breakdown")
            availability = p.get("avail_qty") or None
            availability_note = p.get("availability_note") or raw_data.get("Avail. Qty") or None

            # Use an UPSERT so we don't need a separate SELECT per row.
            # Also returns the old price so we can log history if it changed.
            result = await conn.fetchrow(
                """
                WITH old_row AS (
                    -- Snapshot the existing price BEFORE the upsert touches it
                    SELECT id, current_price
                    FROM products
                    WHERE supplier_id = $1 AND supplier_sku = $2
                )
                INSERT INTO products
                    (supplier_id, supplier_sku, name, description, category, unit,
                     current_price, photo_url, price_updated_at, last_scraped_at,
                     country_of_origin, color, moq, case_qty, length_in, weight_lb,
                     material, availability, availability_note, raw_data,
                     is_active, created_at, updated_at)
                VALUES
                    ($1, $2, $3, $4, $5, $6,
                     $7::numeric, $8,
                     CASE WHEN $7::numeric IS NOT NULL THEN NOW() ELSE NULL END,
                     NOW(), $9, $10, $11::integer, $12::integer, $13::numeric, $14::numeric,
                     $15, $16, $17, $18::jsonb,
                     TRUE, NOW(), NOW())
                ON CONFLICT (supplier_id, supplier_sku)
                DO UPDATE SET
                    name             = EXCLUDED.name,
                    description      = COALESCE(EXCLUDED.description, products.description),
                    photo_url        = COALESCE(EXCLUDED.photo_url, products.photo_url),
                    current_price    = COALESCE(EXCLUDED.current_price, products.current_price),
                    price_updated_at = CASE
                                         WHEN EXCLUDED.current_price IS NOT NULL
                                              AND EXCLUDED.current_price IS DISTINCT FROM products.current_price
                                         THEN NOW()
                                         ELSE products.price_updated_at
                                       END,
                    category         = EXCLUDED.category,
                    unit             = EXCLUDED.unit,
                    country_of_origin = COALESCE(EXCLUDED.country_of_origin, products.country_of_origin),
                    color            = COALESCE(EXCLUDED.color, products.color),
                    moq              = COALESCE(EXCLUDED.moq, products.moq),
                    case_qty         = COALESCE(EXCLUDED.case_qty, products.case_qty),
                    length_in        = COALESCE(EXCLUDED.length_in, products.length_in),
                    weight_lb        = COALESCE(EXCLUDED.weight_lb, products.weight_lb),
                    material         = COALESCE(EXCLUDED.material, products.material),
                    availability     = COALESCE(EXCLUDED.availability, products.availability),
                    availability_note = COALESCE(EXCLUDED.availability_note, products.availability_note),
                    raw_data         = COALESCE(products.raw_data, '{}'::jsonb) || COALESCE(EXCLUDED.raw_data, '{}'::jsonb),
                    last_scraped_at  = NOW(),
                    updated_at       = NOW()
                RETURNING
                    id,
                    (xmax = 0) AS is_insert,
                    -- Pull the pre-upsert price from the CTE snapshot
                    (SELECT current_price FROM old_row) AS old_price
                """,
                supplier_id, sku, name, description, category, unit,
                price, photo_url, country, color, min_qty, case_qty, length_in, weight_lb,
                material, availability, availability_note, json.dumps(raw_data),
            )
            if result and result["is_insert"]:
                inserted += 1
            else:
                updated += 1
                # Log price history if the price actually changed
                if price is not None and result and result["old_price"] is not None:
                    old_price = float(result["old_price"])
                    if abs(old_price - price) > 0.001:
                        await conn.execute(
                            """INSERT INTO product_price_history
                                   (product_id, old_price, new_price, source)
                               VALUES ($1, $2, $3, 'import')""",
                            result["id"], old_price, price,
                        )

            if i % PROGRESS_EVERY == 0:
                await ensure_conn()
                await conn.execute(
                    "UPDATE scrape_jobs SET products_importing=$1 WHERE id=$2",
                    i, job_id,
                )
                print(f"[import] Progress {i}/{total} — {inserted} new, {updated} updated")

        # Final — stamp supplier and job counts, then mark done.
        await ensure_conn()
        total_active = await conn.fetchval(
            "SELECT COUNT(*) FROM products WHERE supplier_id=$1 AND is_active=TRUE",
            supplier_id,
        )
        await conn.execute(
            """
            UPDATE suppliers
               SET last_full_sync_at = NOW(),
                   total_products_count = $2,
                   credential_status = 'ok',
                   updated_at = NOW()
             WHERE id = $1
            """,
            supplier_id, total_active,
        )
        await conn.execute(
            """
            UPDATE scrape_jobs
               SET products_imported  = $1,
                   products_importing = $2,
                   milestone_log      = COALESCE(milestone_log, '{}'::jsonb) || '{"import_complete": true}'::jsonb,
                   phase              = 'done',
                   status             = 'done',
                   completed_at       = NOW()
             WHERE id = $3
            """,
            total, total, job_id,
        )
        print(f"[import] Finished job {job_id}: {inserted} inserted, {updated} updated")

    except Exception as e:
        print(f"[import] FAILED for job {job_id}: {e}")
        try:
            await ensure_conn()
            await conn.execute(
                "UPDATE scrape_jobs SET phase='failed', status='failed', error_message=$1 WHERE id=$2",
                str(e)[:2000], job_id,
            )
        except Exception as inner:
            print(f"[import] Could not mark job as failed: {inner}")
    finally:
        await conn.close()


@router.post("/import")
async def import_scraped_products(body: ImportScrapedRequest, background_tasks: BackgroundTasks):
    """Kick off a background import of scraped products into the products table.
    Returns immediately — poll GET /scraper/job/{id} for phase='done' to know when it finishes.
    """
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT result_key, products_importing FROM scrape_jobs WHERE id=$1", body.job_id
        )
        if not row or not row["result_key"]:
            raise HTTPException(status_code=404, detail="Job results not found")

        # Load total so we can set it upfront for the progress bar
        all_products = json.loads(db.storage.text.get(row["result_key"], default="[]"))
        if body.selected_skus:
            sku_set = set(body.selected_skus)
            all_products = [p for p in all_products if p.get("sku") in sku_set]
        total = len(all_products)

        # Mark importing immediately so the UI sees it right away
        current_progress = int(row["products_importing"] or 0)
        await conn.execute(
            """
            UPDATE scrape_jobs
               SET phase='importing',
                   status='done',
                   error_message=NULL,
                   products_importing=$1,
                   total_expected=$2
             WHERE id=$3
            """,
            current_progress, total, body.job_id,
        )
    finally:
        await conn.close()

    # Kick off the real work in the background so this request returns instantly
    background_tasks.add_task(_run_import, body.job_id, body.supplier_id, body.selected_skus)
    return {"started": True, "total": total}


# ── Image backfill ─────────────────────────────────────────────────────────────
# Downloads all existing product images to Databutton storage.
# Progress is tracked in a JSON file so the UI can poll it.

BACKFILL_PROGRESS_KEY = "backfill_images_progress.json"
ALLSTATE_DETAIL_BACKFILL_KEY = "allstate_detail_backfill_progress.json"
ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY = "allstate_detail_backfill_autorun_progress.json"


async def _run_image_backfill():
    """Background task: download every active product's supplier image and store it.
    Skips products that already have an internal URL (/routes/products/image-proxy?key=).
    Uses raw_data.source_photo_url when import stored the source URL as image pending.
    """
    from app.libs.scraper_base import download_and_store_image as _dl_img

    print("[backfill] Starting image backfill")
    db.storage.json.put(BACKFILL_PROGRESS_KEY, {
        "status": "running",
        "total": 0,
        "done": 0,
        "stored": 0,
        "skipped": 0,
        "failed": 0,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": None,
    })

    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT id, supplier_sku, photo_url, raw_data
            FROM products
            WHERE is_active = TRUE
              AND (
                (photo_url IS NOT NULL AND photo_url != '')
                OR (raw_data->>'source_photo_url') IS NOT NULL
              )
            ORDER BY id
            """
        )
        total = len(rows)
        print(f"[backfill] Found {total} products with photo_url")
        db.storage.json.put(BACKFILL_PROGRESS_KEY, {
            "status": "running",
            "total": total,
            "done": 0,
            "stored": 0,
            "skipped": 0,
            "failed": 0,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        })

        done = 0
        stored = 0
        skipped = 0
        failed = 0

        for row in rows:
            product_id = row["id"]
            sku = row["supplier_sku"]
            photo_url = row["photo_url"]
            raw_data = dict(row["raw_data"] or {})
            source_photo_url = raw_data.get("source_photo_url")
            download_url = photo_url if photo_url and photo_url.startswith("http") else source_photo_url

            # Skip products already using the internal image-proxy storage URL
            if photo_url and "image-proxy?key=" in photo_url:
                if raw_data.get("image_status") != "stored":
                    raw_data["image_status"] = "stored"
                    await conn.execute(
                        "UPDATE products SET raw_data=$1::jsonb, updated_at=NOW() WHERE id=$2",
                        json.dumps(raw_data), product_id,
                    )
                skipped += 1
                done += 1
            elif download_url and str(download_url).startswith("http"):
                raw_data["source_photo_url"] = download_url
                internal_url = _dl_img(download_url, sku)
                if internal_url:
                    try:
                        raw_data["image_status"] = "stored"
                        await conn.execute(
                            "UPDATE products SET photo_url=$1, raw_data=$2::jsonb, updated_at=NOW() WHERE id=$3",
                            internal_url, json.dumps(raw_data), product_id,
                        )
                        stored += 1
                    except Exception as e:
                        print(f"[backfill] DB update failed for product {product_id}: {e}")
                        failed += 1
                else:
                    raw_data["image_status"] = "failed"
                    await conn.execute(
                        "UPDATE products SET raw_data=$1::jsonb, updated_at=NOW() WHERE id=$2",
                        json.dumps(raw_data), product_id,
                    )
                    failed += 1
                done += 1
            else:
                raw_data["image_status"] = raw_data.get("image_status") or "pending"
                await conn.execute(
                    "UPDATE products SET raw_data=$1::jsonb, updated_at=NOW() WHERE id=$2",
                    json.dumps(raw_data), product_id,
                )
                skipped += 1
                done += 1

            # Write progress every 25 products
            if done % 25 == 0:
                db.storage.json.put(BACKFILL_PROGRESS_KEY, {
                    "status": "running",
                    "total": total,
                    "done": done,
                    "stored": stored,
                    "skipped": skipped,
                    "failed": failed,
                    "started_at": datetime.utcnow().isoformat(),
                    "completed_at": None,
                })

        db.storage.json.put(BACKFILL_PROGRESS_KEY, {
            "status": "done",
            "total": total,
            "done": done,
            "stored": stored,
            "skipped": skipped,
            "failed": failed,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
        })
        print(f"[backfill] Complete: {stored} stored, {skipped} skipped, {failed} failed")

    except Exception as e:
        print(f"[backfill] FAILED: {e}")
        db.storage.json.put(BACKFILL_PROGRESS_KEY, {
            "status": "failed",
            "error": str(e)[:500],
            "total": 0,
            "done": 0,
            "stored": 0,
            "skipped": 0,
            "failed": 0,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
        })
    finally:
        await conn.close()


async def _run_allstate_detail_backfill(supplier_id: int, limit: Optional[int] = None):
    """Backfill existing Allstate products with detail-page fields and stored images."""
    from app.libs.allstate_scraper import enrich_allstate_details
    from app.libs.scraper_base import download_and_store_image as _dl_img

    print(f"[detail-backfill] Starting for supplier {supplier_id}")
    db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_KEY, {
        "status": "running",
        "total": 0,
        "done": 0,
        "updated": 0,
        "stored_images": 0,
        "skipped": 0,
        "failed": 0,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": None,
    })

    conn = await get_conn()
    async def ensure_conn():
        nonlocal conn
        if conn.is_closed():
            conn = await get_conn()
        return conn

    async def refresh_conn():
        nonlocal conn
        try:
            if not conn.is_closed():
                await conn.close()
        except Exception:
            pass
        conn = await get_conn()
        return conn

    try:
        supplier = await conn.fetchrow(
            "SELECT name, scraper_key, login_username, login_password FROM suppliers WHERE id=$1",
            supplier_id,
        )
        if not supplier:
            raise ValueError("Supplier not found")
        scraper_key = _resolve_scraper_key(supplier["name"], supplier["scraper_key"])
        if scraper_key != "allstate":
            raise ValueError(f"Detail backfill is only enabled for Allstate suppliers, not '{supplier['name']}'")
        if not supplier["login_username"] or not supplier["login_password"]:
            raise ValueError("Supplier credentials are missing")

        rows = await conn.fetch(
            """
            SELECT id, supplier_sku, photo_url, raw_data
            FROM products
            WHERE supplier_id = $1
              AND is_active = TRUE
            ORDER BY id
            """,
            supplier_id,
        )

        def _row_raw(row) -> dict:
            raw = row["raw_data"] or {}
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    return {}
            return raw if isinstance(raw, dict) else {}

        def _needs_detail_payload(row) -> bool:
            raw = _row_raw(row)
            return not raw.get("detail_url")

        def _needs_image_payload(row) -> bool:
            raw = _row_raw(row)
            photo_url = (row["photo_url"] or "").strip()
            # A supplier-hosted URL is still a usable catalog image. Keep trying
            # to store images when there is no image at all, but do not loop
            # forever on rows that already have a displayable supplier URL.
            return not photo_url

        # Only work rows that still need source detail fields or a stored image.
        rows = [r for r in rows if _needs_detail_payload(r) or _needs_image_payload(r)]

        # Prefer products that still lack detail-page payloads, then missing/stale images.
        rows = sorted(
            rows,
            key=lambda r: (
                0 if _needs_detail_payload(r) else 1,
                0 if _needs_image_payload(r) else 1,
                r["id"],
            ),
        )
        if limit and limit > 0:
            rows = rows[:limit]

        total = len(rows)
        db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_KEY, {
            "status": "running",
            "total": total,
            "done": 0,
            "updated": 0,
            "stored_images": 0,
            "skipped": 0,
            "failed": 0,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        })

        done = updated = stored_images = skipped = failed = 0
        if total == 0:
            db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_KEY, {
                "status": "done",
                "total": 0,
                "done": 0,
                "updated": 0,
                "stored_images": 0,
                "skipped": 0,
                "failed": 0,
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
            })
            return

        sku_rows = [str(r["supplier_sku"]) for r in rows if r["supplier_sku"]]
        progress_state = {"done": 0, "total": total}

        async def _progress(done_count: int, total_count: int, message: str):
            progress_state["done"] = done_count
            progress_state["total"] = total_count
            db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_KEY, {
                "status": "running",
                "total": total,
                "done": done_count,
                "updated": updated,
                "stored_images": stored_images,
                "skipped": skipped,
                "failed": failed,
                "started_at": db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={}).get("started_at"),
                "completed_at": None,
                "message": message,
            })

        async for sku, detail in enrich_allstate_details(
            supplier["login_username"],
            supplier["login_password"],
            sku_rows,
            progress_callback=_progress,
        ):
            row = next((r for r in rows if str(r["supplier_sku"]) == sku), None)
            if not row:
                skipped += 1
                done += 1
                continue

            raw_data = detail.get("raw") or {}
            photo_url = detail.get("photo_url") or row["photo_url"]
            session_headers = detail.get("download_headers") or None
            if photo_url and photo_url.startswith("http"):
                try:
                    stored_url = _dl_img(photo_url, sku, session_headers=session_headers)
                    if stored_url:
                        photo_url = stored_url
                        raw_data["source_photo_url"] = detail.get("photo_url")
                        raw_data["image_status"] = "stored"
                        stored_images += 1
                    else:
                        raw_data["source_photo_url"] = detail.get("photo_url")
                        raw_data["image_status"] = "failed"
                except Exception as exc:
                    raw_data["source_photo_url"] = detail.get("photo_url")
                    raw_data["image_status"] = "failed"
                    print(f"[detail-backfill] Image store failed for {sku}: {exc}")
            raw_data["detail_status"] = "stored"

            try:
                await ensure_conn()
                await conn.execute(
                    """
                    UPDATE products
                       SET photo_url = COALESCE($1, photo_url),
                           current_price = COALESCE($2, current_price),
                           price_updated_at = CASE WHEN $2 IS NOT NULL THEN NOW() ELSE price_updated_at END,
                           moq = COALESCE($3, moq),
                           case_qty = COALESCE($4, case_qty),
                           length_in = COALESCE($5, length_in),
                           weight_lb = COALESCE($6, weight_lb),
                           material = COALESCE($7, material),
                           availability = COALESCE($8, availability),
                           availability_note = COALESCE($9, availability_note),
                           country_of_origin = COALESCE($10, country_of_origin),
                           color = COALESCE($11, color),
                           raw_data = COALESCE(raw_data, '{}'::jsonb) || $12::jsonb,
                           last_scraped_at = NOW(),
                           updated_at = NOW()
                     WHERE id = $13
                    """,
                    photo_url,
                    detail.get("base_price"),
                    detail.get("moq"),
                    detail.get("case_qty"),
                    detail.get("length_in"),
                    detail.get("weight_lb"),
                    detail.get("material"),
                    detail.get("availability"),
                    detail.get("availability_note"),
                    detail.get("country_of_origin"),
                    detail.get("color"),
                    json.dumps(raw_data),
                    row["id"],
                )
                updated += 1
            except Exception as exc:
                try:
                    await refresh_conn()
                    await conn.execute(
                        """
                        UPDATE products
                           SET photo_url = COALESCE($1, photo_url),
                               current_price = COALESCE($2, current_price),
                               price_updated_at = CASE WHEN $2 IS NOT NULL THEN NOW() ELSE price_updated_at END,
                               moq = COALESCE($3, moq),
                               case_qty = COALESCE($4, case_qty),
                               length_in = COALESCE($5, length_in),
                               weight_lb = COALESCE($6, weight_lb),
                               material = COALESCE($7, material),
                               availability = COALESCE($8, availability),
                               availability_note = COALESCE($9, availability_note),
                               country_of_origin = COALESCE($10, country_of_origin),
                               color = COALESCE($11, color),
                               raw_data = COALESCE(raw_data, '{}'::jsonb) || $12::jsonb,
                               last_scraped_at = NOW(),
                               updated_at = NOW()
                         WHERE id = $13
                        """,
                        photo_url,
                        detail.get("base_price"),
                        detail.get("moq"),
                        detail.get("case_qty"),
                        detail.get("length_in"),
                        detail.get("weight_lb"),
                        detail.get("material"),
                        detail.get("availability"),
                        detail.get("availability_note"),
                        detail.get("country_of_origin"),
                        detail.get("color"),
                        json.dumps(raw_data),
                        row["id"],
                    )
                    updated += 1
                except Exception as retry_exc:
                    failed += 1
                    print(f"[detail-backfill] DB update failed for {sku}: {exc}; retry failed: {retry_exc}")

            done += 1
            if done % 50 == 0 and done < total:
                await refresh_conn()
            if done % 10 == 0 or done == total:
                db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_KEY, {
                    "status": "running",
                    "total": total,
                    "done": done,
                    "updated": updated,
                    "stored_images": stored_images,
                    "skipped": skipped,
                    "failed": failed,
                    "started_at": db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={}).get("started_at"),
                    "completed_at": None,
                    "message": f"Backfilled {done}/{total}",
                })

        db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_KEY, {
            "status": "done",
            "total": total,
            "done": done,
            "updated": updated,
            "stored_images": stored_images,
            "skipped": skipped,
            "failed": failed,
            "started_at": db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={}).get("started_at"),
            "completed_at": datetime.utcnow().isoformat(),
        })
        print(f"[detail-backfill] Complete: {done} processed, {updated} updated, {stored_images} images stored, {failed} failed")
    except Exception as e:
        print(f"[detail-backfill] FAILED: {e}")
        db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_KEY, {
            "status": "failed",
            "error": str(e)[:500],
            "total": 0,
            "done": 0,
            "updated": 0,
            "stored_images": 0,
            "skipped": 0,
            "failed": 0,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
        })
    finally:
        await conn.close()


class BackfillStatusOut(BaseModel):
    status: str          # idle | running | done | failed
    total: int
    done: int
    stored: int
    skipped: int
    failed: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class DetailBackfillStatusOut(BaseModel):
    status: str          # idle | running | done | failed
    total: int
    done: int
    updated: int
    stored_images: int
    skipped: int
    failed: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


class DetailBackfillAutoRunStatusOut(BaseModel):
    status: str          # idle | running | done | failed | stopping
    supplier_id: Optional[int] = None
    batch_limit: int = 250
    max_batches: Optional[int] = None
    batches_run: int = 0
    total_updated: int = 0
    total_stored_images: int = 0
    remaining_pending: Optional[int] = None
    current_batch: Optional[dict] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    stop_requested: bool = False


async def _count_allstate_detail_backfill_pending(supplier_id: int) -> int:
    conn = await get_conn()
    try:
        return await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM products
            WHERE supplier_id = $1
              AND is_active = TRUE
              AND (
                COALESCE(raw_data->>'detail_status', 'pending') != 'stored'
                OR photo_url IS NULL
                OR photo_url = ''
              )
            """,
            supplier_id,
        ) or 0
    finally:
        await conn.close()


async def _reconcile_allstate_autorun_status(raw: dict) -> dict:
    """Clear stale run-until-complete state when the catalog is effectively done.

    A product is complete when it has source details and a displayable photo URL.
    Locally storing the image is preferred, but a supplier-hosted image URL should
    not keep the user-facing run in an "almost done" loop forever.
    """
    if not raw:
        return raw
    supplier_id = raw.get("supplier_id")
    if not supplier_id:
        return raw
    if raw.get("status") not in {"running", "stopping", "failed"}:
        return raw

    remaining = await _count_allstate_detail_backfill_pending(int(supplier_id))
    if remaining > 0:
        return {**raw, "remaining_pending": remaining}

    completed_at = datetime.utcnow().isoformat()
    reconciled = {
        **raw,
        "status": "done",
        "remaining_pending": 0,
        "completed_at": raw.get("completed_at") or completed_at,
        "message": "All Allstate products have details and displayable photos",
        "error": None,
        "stop_requested": False,
    }

    current_batch = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={})
    if current_batch and current_batch.get("status") in {"running", "failed"}:
        done_batch = {
            **current_batch,
            "status": "done",
            "completed_at": current_batch.get("completed_at") or completed_at,
            "message": "Catalog complete; remaining photos are displayable supplier URLs",
            "error": None,
        }
        db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_KEY, done_batch)
        reconciled["current_batch"] = done_batch

    db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, reconciled)
    return reconciled


async def _run_allstate_detail_backfill_until_complete(
    supplier_id: int,
    batch_limit: int = 250,
    max_batches: Optional[int] = None,
):
    started_at = datetime.utcnow().isoformat()
    batch_limit = max(1, min(batch_limit or 250, 1000))
    db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, {
        "status": "running",
        "supplier_id": supplier_id,
        "batch_limit": batch_limit,
        "max_batches": max_batches,
        "batches_run": 0,
        "total_updated": 0,
        "total_stored_images": 0,
        "remaining_pending": None,
        "current_batch": None,
        "started_at": started_at,
        "completed_at": None,
        "message": "Checking remaining Allstate image/detail work",
        "stop_requested": False,
    })

    batches_run = total_updated = total_stored_images = 0
    try:
        while True:
            autorun = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, default={})
            if autorun.get("stop_requested"):
                db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, {
                    **autorun,
                    "status": "stopping",
                    "message": "Stopping after current checkpoint",
                    "completed_at": datetime.utcnow().isoformat(),
                })
                return

            remaining = await _count_allstate_detail_backfill_pending(supplier_id)
            if remaining <= 0:
                db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, {
                    **autorun,
                    "status": "done",
                    "batches_run": batches_run,
                    "total_updated": total_updated,
                    "total_stored_images": total_stored_images,
                    "remaining_pending": 0,
                    "completed_at": datetime.utcnow().isoformat(),
                    "message": "All selected Allstate products have details and displayable photos",
                    "stop_requested": False,
                })
                return
            if max_batches is not None and batches_run >= max_batches:
                db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, {
                    **autorun,
                    "status": "done",
                    "batches_run": batches_run,
                    "total_updated": total_updated,
                    "total_stored_images": total_stored_images,
                    "remaining_pending": remaining,
                    "completed_at": datetime.utcnow().isoformat(),
                    "message": f"Stopped after {batches_run} batch(es); {remaining} products still need work",
                    "stop_requested": False,
                })
                return

            db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, {
                **autorun,
                "status": "running",
                "batches_run": batches_run,
                "total_updated": total_updated,
                "total_stored_images": total_stored_images,
                "remaining_pending": remaining,
                "message": f"Running batch {batches_run + 1}; {remaining} products still need images/details",
                "stop_requested": False,
            })

            await _run_allstate_detail_backfill(supplier_id, batch_limit)
            batch = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={})
            if batch.get("status") == "failed":
                raise RuntimeError(batch.get("error") or "Allstate detail/image batch failed")

            batches_run += 1
            total_updated += int(batch.get("updated") or 0)
            total_stored_images += int(batch.get("stored_images") or 0)
            next_remaining = await _count_allstate_detail_backfill_pending(supplier_id)
            db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, {
                "status": "running",
                "supplier_id": supplier_id,
                "batch_limit": batch_limit,
                "max_batches": max_batches,
                "batches_run": batches_run,
                "total_updated": total_updated,
                "total_stored_images": total_stored_images,
                "remaining_pending": next_remaining,
                "current_batch": batch,
                "started_at": started_at,
                "completed_at": None,
                "message": f"Finished batch {batches_run}; {next_remaining} products still need work",
                "stop_requested": False,
            })

            if next_remaining >= remaining and int(batch.get("done") or 0) == 0:
                raise RuntimeError("No remaining progress was made; stopping so the run can be inspected")
            await asyncio.sleep(2)
    except Exception as exc:
        autorun = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, default={})
        db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, {
            **autorun,
            "status": "failed",
            "batches_run": batches_run,
            "total_updated": total_updated,
            "total_stored_images": total_stored_images,
            "completed_at": datetime.utcnow().isoformat(),
            "error": str(exc)[:500],
            "message": "Run until complete stopped with an error",
            "stop_requested": False,
        })


@router.post("/backfill-images", response_model=BackfillStatusOut)
async def start_backfill_images(background_tasks: BackgroundTasks):
    """Kick off a one-time background job that downloads all existing product images
    to Databutton storage so they never expire.
    Poll GET /scraper/backfill-images/status to track progress.
    """
    # Prevent double-run
    progress = db.storage.json.get(BACKFILL_PROGRESS_KEY, default={})
    if progress.get("status") == "running":
        return BackfillStatusOut(**{**{"total": 0, "done": 0, "stored": 0, "skipped": 0, "failed": 0}, **progress})

    background_tasks.add_task(_run_image_backfill)
    return BackfillStatusOut(
        status="running", total=0, done=0, stored=0, skipped=0, failed=0,
        started_at=datetime.utcnow().isoformat(),
    )


@router.get("/backfill-images/status", response_model=BackfillStatusOut)
async def get_backfill_status():
    """Poll the progress of the image backfill background job."""
    raw = db.storage.json.get(BACKFILL_PROGRESS_KEY, default={})
    if not raw:
        return BackfillStatusOut(
            status="idle", total=0, done=0, stored=0, skipped=0, failed=0
        )
    return BackfillStatusOut(**{**{"total": 0, "done": 0, "stored": 0, "skipped": 0, "failed": 0}, **raw})


@router.post("/backfill-allstate-details/{supplier_id}", response_model=DetailBackfillStatusOut)
async def start_allstate_detail_backfill(
    supplier_id: int,
    limit: Optional[int] = None,
    force: bool = False,
    background_tasks: BackgroundTasks = None,
):
    """Backfill existing Allstate products with detail-page fields and stored images."""
    progress = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={})
    if progress.get("status") == "running" and not force:
        return DetailBackfillStatusOut(**{
            "status": "running",
            "total": 0,
            "done": 0,
            "updated": 0,
            "stored_images": 0,
            "skipped": 0,
            "failed": 0,
            **progress,
        })
    if background_tasks is None:
        raise HTTPException(status_code=500, detail="Background task runner unavailable")
    background_tasks.add_task(_run_allstate_detail_backfill, supplier_id, limit)
    return DetailBackfillStatusOut(
        status="running",
        total=0,
        done=0,
        updated=0,
        stored_images=0,
        skipped=0,
        failed=0,
        started_at=datetime.utcnow().isoformat(),
    )


@router.get("/backfill-allstate-details/status", response_model=DetailBackfillStatusOut)
async def get_allstate_detail_backfill_status():
    raw = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={})
    if not raw:
        return DetailBackfillStatusOut(status="idle", total=0, done=0, updated=0, stored_images=0, skipped=0, failed=0)
    return DetailBackfillStatusOut(**{
        "status": "idle",
        "total": 0,
        "done": 0,
        "updated": 0,
        "stored_images": 0,
        "skipped": 0,
        "failed": 0,
        **raw,
    })


@router.post("/backfill-allstate-details/{supplier_id}/run-until-complete", response_model=DetailBackfillAutoRunStatusOut)
async def start_allstate_detail_backfill_until_complete(
    supplier_id: int,
    batch_limit: int = 250,
    max_batches: Optional[int] = None,
    background_tasks: BackgroundTasks = None,
):
    """Run safe Allstate detail/image backfill batches until no products are pending."""
    autorun = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, default={})
    autorun = await _reconcile_allstate_autorun_status(autorun)
    if autorun.get("status") == "running":
        return DetailBackfillAutoRunStatusOut(**{
            "status": "running",
            **autorun,
        })
    batch = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={})
    if batch.get("status") == "running":
        return DetailBackfillAutoRunStatusOut(
            status="running",
            supplier_id=supplier_id,
            batch_limit=max(1, min(batch_limit or 250, 1000)),
            max_batches=max_batches,
            current_batch=batch,
            message="A detail/image batch is already running",
        )
    if background_tasks is None:
        raise HTTPException(status_code=500, detail="Background task runner unavailable")
    safe_limit = max(1, min(batch_limit or 250, 1000))
    background_tasks.add_task(_run_allstate_detail_backfill_until_complete, supplier_id, safe_limit, max_batches)
    return DetailBackfillAutoRunStatusOut(
        status="running",
        supplier_id=supplier_id,
        batch_limit=safe_limit,
        max_batches=max_batches,
        started_at=datetime.utcnow().isoformat(),
        message="Run until complete started",
    )


@router.post("/backfill-allstate-details/run-until-complete/stop", response_model=DetailBackfillAutoRunStatusOut)
async def stop_allstate_detail_backfill_until_complete():
    autorun = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, default={})
    if not autorun:
        return DetailBackfillAutoRunStatusOut(status="idle", message="No run until complete job exists")
    if autorun.get("status") != "running":
        return DetailBackfillAutoRunStatusOut(**{
            "status": autorun.get("status", "idle"),
            **autorun,
        })
    updated = {**autorun, "stop_requested": True, "message": "Stop requested; finishing the current checkpoint"}
    db.storage.json.put(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, updated)
    return DetailBackfillAutoRunStatusOut(**updated)


@router.get("/backfill-allstate-details/run-until-complete/status", response_model=DetailBackfillAutoRunStatusOut)
async def get_allstate_detail_backfill_until_complete_status():
    raw = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_AUTORUN_KEY, default={})
    if not raw:
        return DetailBackfillAutoRunStatusOut(status="idle")
    raw = await _reconcile_allstate_autorun_status(raw)
    current_batch = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={})
    if current_batch:
        raw = {**raw, "current_batch": current_batch}
    return DetailBackfillAutoRunStatusOut(**{
        "status": "idle",
        **raw,
    })


@router.get("/supplier-enrichment-status/{supplier_id}", response_model=SupplierEnrichmentStatusOut)
async def get_supplier_enrichment_status(supplier_id: int):
    """Summarize image/detail coverage for supplier catalog UI."""
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE is_active = TRUE) AS total_active,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND raw_data->>'detail_status' = 'stored'
                ) AS detail_stored,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND COALESCE(raw_data->>'detail_status', 'pending') = 'pending'
                ) AS detail_pending,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND raw_data->>'detail_status' = 'failed'
                ) AS detail_failed,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND raw_data->>'image_status' = 'stored'
                      AND photo_url IS NOT NULL
                      AND photo_url != ''
                ) AS images_stored,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND photo_url LIKE 'http%'
                ) AS images_external,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND photo_url IS NOT NULL
                      AND photo_url != ''
                ) AS images_with_reference,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND COALESCE(raw_data->>'image_status', 'pending') = 'pending'
                ) AS images_pending,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND raw_data->>'image_status' = 'failed'
                ) AS images_failed,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND (photo_url IS NULL OR photo_url = '')
                ) AS images_missing
            FROM products
            WHERE supplier_id = $1
            """,
            supplier_id,
        )
        progress = db.storage.json.get(ALLSTATE_DETAIL_BACKFILL_KEY, default={})
        return SupplierEnrichmentStatusOut(
            supplier_id=supplier_id,
            total_active=row["total_active"] or 0,
            detail_stored=row["detail_stored"] or 0,
            detail_pending=row["detail_pending"] or 0,
            detail_failed=row["detail_failed"] or 0,
            images_stored=row["images_stored"] or 0,
            images_external=row["images_external"] or 0,
            images_with_reference=row["images_with_reference"] or 0,
            images_pending=row["images_pending"] or 0,
            images_failed=row["images_failed"] or 0,
            images_missing=row["images_missing"] or 0,
            last_backfill=progress or None,
        )
    finally:
        await conn.close()
