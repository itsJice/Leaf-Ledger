"""Scraper API - trigger supplier catalog scrapes and track job progress."""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import asyncpg
import asyncio
import importlib
import threading
import os
import json
import re
import databutton as db
from datetime import datetime
from urllib.parse import unquote
from app.libs.supplier_identity import resolve_scraper_key

router = APIRouter(prefix="/scraper", tags=["scraper"])
DATABASE_URL = os.environ.get("DATABASE_URL")


async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


def _resolve_scraper_key(supplier_name: str, scraper_key: Optional[str]) -> str:
    """Prefer the configured scraper_key, with a name-based fallback for older rows."""
    return resolve_scraper_key(supplier_name, scraper_key) or ""


def _credential_validation_message(scraper_key: str, credential_status: Optional[str]) -> Optional[str]:
    """Return a user-facing block message when credentials need validation first."""
    status = (credential_status or "untested").lower()
    if scraper_key not in ("allstate", "accent_decor", "regency", "select_artificial", "vickerman") or status not in ("failed", "error", "untested"):
        return None
    if status == "untested":
        if scraper_key == "accent_decor":
            return "Run Configure Catalog to test the Accent email/password before syncing products."
        if scraper_key == "select_artificial":
            return "Run Configure Catalog to test the Select customer number/billing zip before syncing products."
        if scraper_key == "vickerman":
            return "Run Configure Catalog to test the Vickerman email/password before syncing products."
        return "Run Configure Catalog to test these credentials before syncing products."
    if scraper_key == "accent_decor":
        return "Update the Accent email/password, then run Configure Catalog again."
    if scraper_key == "select_artificial":
        return "Update the Select customer number/billing zip, then run Configure Catalog again."
    if scraper_key == "vickerman":
        return "Update the Vickerman email/password, then run Configure Catalog again."
    return "Update the login credentials, then run Configure Catalog again."


def _credential_step_detail(supplier_label: str, scraper_key: str, has_credentials: bool, credential_status: str) -> str:
    """Describe credential readiness using the supplier's actual credential fields."""
    if not has_credentials:
        if scraper_key == "accent_decor":
            return f"{supplier_label} email/password are missing."
        if scraper_key == "select_artificial":
            return f"{supplier_label} customer number/billing zip are missing."
        if scraper_key == "vickerman":
            return f"{supplier_label} email/password are missing."
        return f"{supplier_label} login username and password are missing."
    if credential_status in ("failed", "error"):
        if scraper_key == "accent_decor":
            return f"{supplier_label} rejected the saved email/password during catalog discovery."
        if scraper_key == "select_artificial":
            return f"{supplier_label} rejected the saved customer number/billing zip during catalog discovery."
        if scraper_key == "vickerman":
            return f"{supplier_label} rejected the saved email/password during catalog discovery."
        return f"{supplier_label} rejected the saved credentials during catalog discovery."
    if credential_status == "untested":
        if scraper_key == "accent_decor":
            return f"{supplier_label} email/password are saved but have not passed catalog discovery yet."
        if scraper_key == "select_artificial":
            return f"{supplier_label} customer number/billing zip are saved but have not passed catalog discovery yet."
        if scraper_key == "vickerman":
            return f"{supplier_label} email/password are saved but have not passed catalog discovery yet."
        return f"{supplier_label} credentials are saved but have not passed catalog discovery yet."
    return "Saved in the app/database."


def _credential_step_action(scraper_key: str, has_credentials: bool, credential_status: str) -> Optional[str]:
    """Return the next credential action for the supplier readiness checklist."""
    if credential_status in ("failed", "error"):
        if scraper_key == "accent_decor":
            return "Edit this supplier and update the Accent email/password."
        if scraper_key == "select_artificial":
            return "Edit this supplier and update the Select customer number/billing zip."
        if scraper_key == "vickerman":
            return "Edit this supplier and update the Vickerman email/password."
        return "Edit this supplier and update the login credentials."
    if credential_status == "untested":
        if scraper_key == "accent_decor":
            return "Run Configure Catalog to test the Accent email/password."
        if scraper_key == "select_artificial":
            return "Run Configure Catalog to test the Select customer number/billing zip."
        if scraper_key == "vickerman":
            return "Run Configure Catalog to test the Vickerman email/password."
        return "Run Configure Catalog to test these credentials."
    if has_credentials:
        return None
    if scraper_key == "accent_decor":
        return "Edit this supplier and add the Accent email/password."
    if scraper_key == "select_artificial":
        return "Edit this supplier and add the Select customer number/billing zip."
    if scraper_key == "vickerman":
        return "Edit this supplier and add the Vickerman email/password."
    return "Edit this supplier and add credentials."


def _catalog_selection_detail(
    selected_category_mode: str,
    selected_category_count: int,
    overlapping_listing_count: int,
    unique_product_count: int,
) -> str:
    """Describe selected catalog size without confusing overlapping category listings with unique products."""
    if selected_category_mode not in ("selected", "all"):
        return "No categories selected because discovery has not completed."

    category_text = (
        f"All {selected_category_count:,} cached categories selected"
        if selected_category_mode == "all"
        else f"{selected_category_count:,} selected categories"
    )
    if unique_product_count > 0:
        detail = f"{category_text}; {unique_product_count:,} unique products imported."
        if overlapping_listing_count > unique_product_count:
            detail += f" Category pages list them {overlapping_listing_count:,} times because products can appear in multiple categories."
        return detail
    return f"{category_text}, about {overlapping_listing_count:,} category listings before dedupe."


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
    image_urls: List[str] = []
    source_photo_url: Optional[str] = None
    detail_url: Optional[str] = None
    source_url: Optional[str] = None
    height_in: Optional[float] = None
    width_in: Optional[float] = None
    diameter_in: Optional[float] = None
    length_in: Optional[float] = None
    weight_lb: Optional[float] = None
    material: Optional[str] = None
    finish: Optional[str] = None
    style: Optional[str] = None


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
    images_no_supplier_image: int = 0
    images_resolved: int = 0
    images_pending: int = 0
    images_failed: int = 0
    images_missing: int = 0
    last_backfill: Optional[dict] = None


class SupplierReadinessStep(BaseModel):
    key: str
    label: str
    status: str
    detail: str
    action: Optional[str] = None


class SupplierImageProblem(BaseModel):
    product_id: int
    supplier_sku: str
    name: str
    photo_url: Optional[str] = None
    source_photo_url: Optional[str] = None
    image_status: Optional[str] = None
    problem_type: str = "retryable"


class AllstateReadinessOut(BaseModel):
    supplier_id: int
    supplier_name: str
    scraper_key: str
    has_credentials: bool = False
    credential_status: Optional[str] = None
    category_index_count: int = 0
    selected_category_count: int = 0
    selected_category_mode: str = "none"
    estimated_selected_products: int = 0
    product_count: int = 0
    standardized_count: int = 0
    photo_ready_count: int = 0
    internal_photo_count: int = 0
    supplier_hosted_photo_count: int = 0
    photo_problem_count: int = 0
    placeholder_image_count: int = 0
    no_supplier_image_count: int = 0
    retryable_image_problem_count: int = 0
    detail_ready_count: int = 0
    fully_ready_count: int = 0
    builder_item_count: int = 0
    ready_percent: int = 0
    storage_percent: int = 0
    image_problem_samples: List[SupplierImageProblem] = []
    next_action: str
    steps: List[SupplierReadinessStep]


class PlaceholderImageReviewOut(BaseModel):
    supplier_id: int
    reviewed_count: int
    message: str


def _scraped_product_to_import_dict(product) -> dict:
    return {
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
        "image_urls": product.image_urls,
        "category": product.category,
        "color_group": product.color,
        "country_of_origin": product.country_of_origin,
        "source_photo_url": product.raw.get("source_photo_url"),
        "detail_url": product.raw.get("detail_url"),
        "source_url": product.raw.get("source_url"),
        "height_in": product.height_in,
        "width_in": product.width_in,
        "diameter_in": product.diameter_in,
        "length_in": product.length_in,
        "weight_lb": product.weight_lb,
        "material": product.material,
        "finish": product.finish,
        "style": product.style,
        "raw": product.raw,
    }


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
            from app.libs import accent_decor_scraper as accent_decor_module
            accent_decor_module = importlib.reload(accent_decor_module)

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

            catalog = await accent_decor_module.discover_accent_decor_catalog(
                username, password, on_accent_discover, supplier_id=supplier_id
            )
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
        elif scraper_key == "regency":
            from app.libs.regency_scraper import discover_regency_catalog

            async def on_regency_discover(cats_done, cats_total, msg, *, milestone_event=None, category_info=None):
                print(f"[job {job_id}] regency discover: {msg}")
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

            catalog = await discover_regency_catalog(username, password, on_regency_discover, supplier_id=supplier_id)
            subcategories = catalog["subcategories"]
            total_products = catalog["total_products"]
            milestones["categories_discovered"] = True
            milestones["categories"] = [
                {
                    "name": s.get("label", s.get("slug", "")),
                    "slug": s.get("slug", ""),
                    "section": s.get("section", ""),
                    "total": s.get("item_count", 0),
                    "collected": 0,
                    "done": False,
                }
                for s in subcategories
            ]
            await update_milestones()
        elif scraper_key == "select_artificial":
            from app.libs.select_artificial_scraper import discover_select_artificial_catalog

            async def on_select_discover(cats_done, cats_total, msg, *, milestone_event=None, category_info=None):
                print(f"[job {job_id}] select discover: {msg}")
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

            catalog = await discover_select_artificial_catalog(username, password, on_select_discover, supplier_id=supplier_id)
            subcategories = catalog["subcategories"]
            total_products = catalog["total_products"]
            milestones["categories_discovered"] = True
            milestones["categories"] = [
                {
                    "name": s.get("label", s.get("slug", "")),
                    "slug": s.get("slug", ""),
                    "section": s.get("section", ""),
                    "total": s.get("item_count", 0),
                    "collected": 0,
                    "done": False,
                }
                for s in subcategories
            ]
            await update_milestones()
        elif scraper_key == "vickerman":
            from app.libs.vickerman_scraper import discover_vickerman_catalog

            async def on_vickerman_discover(cats_done, cats_total, msg, *, milestone_event=None, category_info=None):
                print(f"[job {job_id}] vickerman discover: {msg}")
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

            catalog = await discover_vickerman_catalog(username, password, on_vickerman_discover, supplier_id=supplier_id)
            subcategories = catalog["subcategories"]
            total_products = catalog["total_products"]
            milestones["categories_discovered"] = True
            milestones["categories"] = [
                {
                    "name": s.get("label", s.get("slug", "")),
                    "slug": s.get("slug", ""),
                    "section": s.get("section", ""),
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
                    "image_urls": product.image_urls,
                    "category": product.category,
                    "color_group": product.color,
                    "country_of_origin": product.country_of_origin,
                    "source_photo_url": product.raw.get("source_photo_url"),
                    "detail_url": product.raw.get("detail_url"),
                    "source_url": product.raw.get("source_url"),
                    "height_in": product.height_in,
                    "width_in": product.width_in,
                    "diameter_in": product.diameter_in,
                    "length_in": product.length_in,
                    "weight_lb": product.weight_lb,
                    "material": product.material,
                    "finish": product.finish,
                    "style": product.style,
                    "raw": product.raw,
                })
        elif scraper_key in ("accent", "accent_decor"):
            from app.libs import accent_decor_scraper as accent_decor_module
            accent_decor_module = importlib.reload(accent_decor_module)
            async for product in accent_decor_module.scrape_accent_decor(
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
                    "image_urls": product.image_urls,
                    "category": product.category,
                    "color_group": product.color,
                    "country_of_origin": product.country_of_origin,
                    "source_photo_url": product.raw.get("source_photo_url"),
                    "detail_url": product.raw.get("detail_url"),
                    "source_url": product.raw.get("source_url"),
                    "height_in": product.height_in,
                    "width_in": product.width_in,
                    "diameter_in": product.diameter_in,
                    "length_in": product.length_in,
                    "weight_lb": product.weight_lb,
                    "material": product.material,
                    "finish": product.finish,
                    "style": product.style,
                    "raw": product.raw,
                })
        elif scraper_key == "regency":
            from app.libs import regency_scraper as regency_module
            regency_module = importlib.reload(regency_module)
            async for product in regency_module.scrape_regency(
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
                    "image_urls": product.image_urls,
                    "category": product.category,
                    "color_group": product.color,
                    "country_of_origin": product.country_of_origin,
                    "source_photo_url": product.raw.get("source_photo_url"),
                    "detail_url": product.raw.get("detail_url"),
                    "source_url": product.raw.get("source_url"),
                    "height_in": product.height_in,
                    "width_in": product.width_in,
                    "diameter_in": product.diameter_in,
                    "length_in": product.length_in,
                    "weight_lb": product.weight_lb,
                    "material": product.material,
                    "finish": product.finish,
                    "style": product.style,
                    "raw": product.raw,
                })
        elif scraper_key == "select_artificial":
            from app.libs import select_artificial_scraper as select_module
            select_module = importlib.reload(select_module)
            async for product in select_module.scrape_select_artificial(
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
                    "image_urls": product.image_urls,
                    "category": product.category,
                    "color_group": product.color,
                    "country_of_origin": product.country_of_origin,
                    "source_photo_url": product.raw.get("source_photo_url"),
                    "detail_url": product.raw.get("detail_url"),
                    "source_url": product.raw.get("source_url"),
                    "height_in": product.height_in,
                    "width_in": product.width_in,
                    "diameter_in": product.diameter_in,
                    "length_in": product.length_in,
                    "weight_lb": product.weight_lb,
                    "material": product.material,
                    "finish": product.finish,
                    "style": product.style,
                    "raw": product.raw,
                })
        elif scraper_key == "vickerman":
            from app.libs import vickerman_scraper as vickerman_module
            vickerman_module = importlib.reload(vickerman_module)
            async for product in vickerman_module.scrape_vickerman(
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
                    "image_urls": product.image_urls,
                    "category": product.category,
                    "color_group": product.color,
                    "country_of_origin": product.country_of_origin,
                    "source_photo_url": product.raw.get("source_photo_url"),
                    "detail_url": product.raw.get("detail_url"),
                    "source_url": product.raw.get("source_url"),
                    "height_in": product.height_in,
                    "width_in": product.width_in,
                    "diameter_in": product.diameter_in,
                    "length_in": product.length_in,
                    "weight_lb": product.weight_lb,
                    "material": product.material,
                    "finish": product.finish,
                    "style": product.style,
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
        elif scraper_key == "regency":
            from app.libs.regency_scraper import discover_regency_catalog, scrape_regency
            catalog = await discover_regency_catalog(username, password, noop_progress, supplier_id=supplier_id)
            async for product in scrape_regency(
                username, password, None, noop_progress,
                subcategories=catalog["subcategories"], supplier_id=supplier_id
            ):
                scraped.append({"sku": product.sku, "base_price": product.base_price})
        elif scraper_key == "select_artificial":
            print("[price-sync] Select Artificial price sync waits on authenticated product route capture")
            return
        elif scraper_key == "vickerman":
            from app.libs.vickerman_scraper import discover_vickerman_catalog, scrape_vickerman
            catalog = await discover_vickerman_catalog(username, password, noop_progress, supplier_id=supplier_id)
            async for product in scrape_vickerman(
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
            "SELECT id, name, scraper_key, login_username, login_password, credential_status FROM suppliers WHERE id=$1",
            supplier_id,
        )
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        if not supplier["login_username"] or not supplier["login_password"]:
            raise HTTPException(
                status_code=400,
                detail="No credentials saved for this supplier.",
            )
        resolved_scraper_key = _resolve_scraper_key(supplier["name"], supplier["scraper_key"])
        credential_message = _credential_validation_message(resolved_scraper_key, supplier["credential_status"])
        if credential_message:
            raise HTTPException(status_code=400, detail=credential_message)
        background_tasks.add_task(
            _run_price_sync,
            supplier["id"],
            supplier["name"],
            resolved_scraper_key,
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
                """SELECT id, name, scraper_key, login_username, login_password, credential_status FROM suppliers
                   WHERE id = ANY($1) AND login_username IS NOT NULL AND login_password IS NOT NULL""",
                body.supplier_ids,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, name, scraper_key, login_username, login_password, credential_status FROM suppliers
                   WHERE login_username IS NOT NULL AND login_password IS NOT NULL
                   AND (last_price_synced_at IS NULL OR last_price_synced_at < NOW() - INTERVAL '23 hours')"""
            )

        count = 0
        for row in rows:
            resolved_scraper_key = _resolve_scraper_key(row["name"], row["scraper_key"])
            if _credential_validation_message(resolved_scraper_key, row["credential_status"]):
                continue
            background_tasks.add_task(
                _run_price_sync,
                row["id"],
                row["name"],
                resolved_scraper_key,
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
            "SELECT id, name, scraper_key, login_username, login_password, credential_status FROM suppliers WHERE id=$1",
            body.supplier_id,
        )
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        if not supplier["login_username"] or not supplier["login_password"]:
            raise HTTPException(
                status_code=400,
                detail="No login credentials stored for this supplier. Add them in the Suppliers page first.",
            )
        resolved_scraper_key = _resolve_scraper_key(supplier["name"], supplier["scraper_key"])
        credential_message = _credential_validation_message(resolved_scraper_key, supplier["credential_status"])
        if credential_message:
            raise HTTPException(status_code=400, detail=credential_message)

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
                resolved_scraper_key,
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


@router.post("/job/{job_id}/cancel", response_model=ScrapeJobOut)
async def cancel_scrape_job(job_id: int):
    """Mark a pending/running scrape job as failed so a corrected sync can start."""
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
        ready_without_import = (
            row["status"] == "done"
            and row["phase"] == "ready"
            and int(row["products_imported"] or 0) == 0
        )
        if row["status"] not in ("pending", "running") and not ready_without_import:
            return _parse_job_row(row)

        updated = await conn.fetchrow(
            """
            UPDATE scrape_jobs
            SET status='failed',
                phase='failed',
                completed_at=NOW(),
                error_message=COALESCE(error_message, 'Cancelled before starting a corrected scrape')
            WHERE id=$1
            RETURNING *
            """,
            job_id,
        )
        job = _parse_job_row(updated)
        job["supplier_name"] = row["supplier_name"]
        return job
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


def _clean_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def _coerce_int(value) -> Optional[int]:
    number = _coerce_float(value)
    return int(number) if number is not None else None


def _string_list(value) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    cleaned: list[str] = []
    for item in values:
        text = _clean_text(item)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _first_http_image_url(photo_url=None, image_urls=None, raw_data=None) -> Optional[str]:
    """Choose the best supplier-hosted image URL for image storage/backfill."""
    return next(iter(_http_image_url_candidates(photo_url, image_urls, raw_data)), None)


def _http_image_url_candidates(photo_url=None, image_urls=None, raw_data=None) -> list[str]:
    """Return supplier-hosted image URLs in priority order for storage/backfill."""
    raw = raw_data if isinstance(raw_data, dict) else {}
    candidates = [
        photo_url,
        raw.get("source_photo_url"),
        *_string_list(image_urls),
        *_string_list(raw.get("image_urls")),
    ]
    urls: list[str] = []
    for url in candidates:
        text = _clean_text(url) or ""
        if text.startswith("http") and text not in urls:
            urls.append(text)
    return urls


def _json_object(value) -> dict:
    """Return a JSON object dict from decoded DB jsonb or string storage variants."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except Exception:
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}


def _normalize_sku_value(value) -> str:
    return unquote(_clean_text(value) or "")


def _selected_sku_set(selected_skus) -> set[str]:
    sku_set: set[str] = set()
    for sku in selected_skus or []:
        raw = _clean_text(sku)
        normalized = _normalize_sku_value(sku)
        if raw:
            sku_set.add(raw)
        if normalized:
            sku_set.add(normalized)
    return sku_set


def _product_matches_selected_skus(p: dict, sku_set: set[str]) -> bool:
    if not sku_set:
        return True
    if not isinstance(p, dict):
        return False
    for value in (p.get("sku"), p.get("supplier_sku")):
        raw = _clean_text(value)
        normalized = _normalize_sku_value(value)
        if raw in sku_set or normalized in sku_set:
            return True
    return False


def _category_tag_values(p: dict, raw_data: dict, normalized_category: str) -> list[str]:
    """Collect supplier category aliases so duplicate SKU imports keep every browse path."""
    tags: list[str] = []
    for value in (
        normalized_category,
        p.get("category"),
        p.get("subcategory"),
        raw_data.get("Category"),
        raw_data.get("Subcategory"),
        raw_data.get("source_category"),
        raw_data.get("source_section"),
        raw_data.get("source_category_path"),
        raw_data.get("category_path"),
        raw_data.get("product_type"),
        raw_data.get("ProductType"),
    ):
        tags.extend(_string_list(value))
    tags.extend(_string_list(p.get("tags")))
    tags.extend(_string_list(raw_data.get("category_tags")))

    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        text = _clean_text(tag)
        if not text:
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned


def _normalize_product_for_import(p: dict, scraper_key: str) -> dict:
    """Normalize cached scraper output into the products-table import contract."""
    if not isinstance(p, dict):
        p = {}

    raw_input = p.get("raw") or {}
    raw_data = dict(raw_input) if isinstance(raw_input, dict) else {}

    sku = _normalize_sku_value(p.get("sku") or p.get("supplier_sku"))
    source_photo_url = _clean_text(
        p.get("photo_url") or p.get("source_photo_url") or raw_data.get("source_photo_url")
    )
    image_urls = _string_list(p.get("image_urls") or raw_data.get("image_urls"))
    if not source_photo_url and image_urls:
        source_photo_url = image_urls[0]
    if source_photo_url and source_photo_url not in image_urls:
        image_urls.insert(0, source_photo_url)

    for key in ("detail_url", "source_url", "source_photo_url"):
        value = _clean_text(p.get(key) or raw_data.get(key))
        if value and not raw_data.get(key):
            raw_data[key] = value
    if source_photo_url and not raw_data.get("source_photo_url"):
        raw_data["source_photo_url"] = source_photo_url
    if image_urls and not raw_data.get("image_urls"):
        raw_data["image_urls"] = image_urls

    if source_photo_url:
        default_image_status = "pending" if source_photo_url.startswith("http") else "stored"
    else:
        default_image_status = "pending"
    raw_data["detail_status"] = raw_data.get("detail_status") or ("stored" if raw_data.get("detail_url") else "pending")
    raw_data["image_status"] = raw_data.get("image_status") or default_image_status
    raw_data["scraper_key"] = scraper_key

    price_source = p.get("base_price")
    if price_source is None:
        price_source = raw_data.get("price") or raw_data.get("Price")

    normalized_category = _map_category(p.get("category") or raw_data.get("Category") or "")
    raw_data["category_tags"] = _category_tag_values(p, raw_data, normalized_category)

    return {
        "sku": sku,
        "name": _clean_text(p.get("name")) or sku or "Unknown",
        "description": _clean_text(p.get("description")),
        # Keep remote supplier images out of photo_url; image backfill stores them later.
        "photo_url": source_photo_url if source_photo_url and not source_photo_url.startswith("http") else None,
        "image_urls": image_urls,
        "price": _coerce_float(price_source),
        "category": normalized_category,
        "unit": _map_unit(p.get("uom") or raw_data.get("Unit of Measure") or raw_data.get("Unit") or raw_data.get("UOM") or ""),
        "country": _clean_text(p.get("country_of_origin") or raw_data.get("Country of Origin") or raw_data.get("Country")),
        "color": _clean_text(p.get("color_group") or p.get("color") or raw_data.get("ColorGrp") or raw_data.get("Color") or raw_data.get("Primary Color")),
        "min_qty": _coerce_int(p.get("min_qty") or raw_data.get("Min Qty") or raw_data.get("MOQ")),
        "case_qty": _coerce_int(p.get("case_qty") or raw_data.get("Case Qty") or raw_data.get("Case Quantity")),
        "height_in": _coerce_float(p.get("height_in") or raw_data.get("Height")),
        "width_in": _coerce_float(p.get("width_in") or raw_data.get("Width")),
        "diameter_in": _coerce_float(p.get("diameter_in") or raw_data.get("Diameter")),
        "length_in": _coerce_float(p.get("length_in") or raw_data.get("Length")),
        "weight_lb": _coerce_float(p.get("weight_lb") or raw_data.get("Weight")),
        "material": _clean_text(p.get("material") or raw_data.get("Material Breakdown") or raw_data.get("Material") or raw_data.get("Materials")),
        "finish": _clean_text(p.get("finish") or raw_data.get("Finish")),
        "style": _clean_text(p.get("style") or raw_data.get("Style")),
        "availability": _clean_text(p.get("avail_qty") or p.get("availability") or raw_data.get("Availability")),
        "availability_note": _clean_text(p.get("availability_note") or raw_data.get("Avail. Qty") or raw_data.get("Avail. Qty: *") or raw_data.get("Availability")),
        "raw_data": raw_data,
    }


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
            sku_set = _selected_sku_set(selected_skus)
            all_products = [p for p in all_products if _product_matches_selected_skus(p, sku_set)]

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
            normalized = _normalize_product_for_import(p, scraper_key)
            sku = normalized["sku"]
            name = normalized["name"]
            description = normalized["description"]
            photo_url = normalized["photo_url"]
            image_urls = normalized["image_urls"]
            price = normalized["price"]
            category = normalized["category"]
            unit = normalized["unit"]
            country = normalized["country"]
            color = normalized["color"]
            min_qty = normalized["min_qty"]
            case_qty = normalized["case_qty"]
            height_in = normalized["height_in"]
            width_in = normalized["width_in"]
            diameter_in = normalized["diameter_in"]
            length_in = normalized["length_in"]
            weight_lb = normalized["weight_lb"]
            material = normalized["material"]
            finish = normalized["finish"]
            style = normalized["style"]
            availability = normalized["availability"]
            availability_note = normalized["availability_note"]
            raw_data = normalized["raw_data"]

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
                     current_price, photo_url, image_urls, price_updated_at, last_scraped_at,
                     country_of_origin, color, moq, case_qty,
                     height_in, width_in, diameter_in, length_in, weight_lb,
                     material, finish, style, availability, availability_note, raw_data,
                     is_active, created_at, updated_at)
                VALUES
                    ($1, $2, $3, $4, $5, $6,
                     $7::numeric, $8, $9::text[],
                     CASE WHEN $7::numeric IS NOT NULL THEN NOW() ELSE NULL END,
                     NOW(), $10, $11, $12::integer, $13::integer,
                     $14::numeric, $15::numeric, $16::numeric, $17::numeric, $18::numeric,
                     $19, $20, $21, $22, $23, $24::jsonb,
                     TRUE, NOW(), NOW())
                ON CONFLICT (supplier_id, supplier_sku)
                DO UPDATE SET
                    name             = EXCLUDED.name,
                    description      = COALESCE(EXCLUDED.description, products.description),
                    photo_url        = COALESCE(EXCLUDED.photo_url, products.photo_url),
                    image_urls       = CASE
                                         WHEN array_length(EXCLUDED.image_urls, 1) > 0
                                         THEN EXCLUDED.image_urls
                                         ELSE products.image_urls
                                       END,
                    current_price    = COALESCE(EXCLUDED.current_price, products.current_price),
                    price_updated_at = CASE
                                         WHEN EXCLUDED.current_price IS NOT NULL
                                              AND EXCLUDED.current_price IS DISTINCT FROM products.current_price
                                         THEN NOW()
                                         ELSE products.price_updated_at
                                       END,
                    category         = COALESCE(EXCLUDED.category, products.category),
                    unit             = EXCLUDED.unit,
                    country_of_origin = COALESCE(EXCLUDED.country_of_origin, products.country_of_origin),
                    color            = COALESCE(EXCLUDED.color, products.color),
                    moq              = COALESCE(EXCLUDED.moq, products.moq),
                    case_qty         = COALESCE(EXCLUDED.case_qty, products.case_qty),
                    height_in        = COALESCE(EXCLUDED.height_in, products.height_in),
                    width_in         = COALESCE(EXCLUDED.width_in, products.width_in),
                    diameter_in      = COALESCE(EXCLUDED.diameter_in, products.diameter_in),
                    length_in        = COALESCE(EXCLUDED.length_in, products.length_in),
                    weight_lb        = COALESCE(EXCLUDED.weight_lb, products.weight_lb),
                    material         = COALESCE(EXCLUDED.material, products.material),
                    finish           = COALESCE(EXCLUDED.finish, products.finish),
                    style            = COALESCE(EXCLUDED.style, products.style),
                    availability     = COALESCE(EXCLUDED.availability, products.availability),
                    availability_note = COALESCE(EXCLUDED.availability_note, products.availability_note),
                    raw_data         =
                        COALESCE(products.raw_data, '{}'::jsonb)
                        || COALESCE(EXCLUDED.raw_data, '{}'::jsonb)
                        || jsonb_build_object(
                            'category_tags',
                            COALESCE(
                                (
                                    SELECT jsonb_agg(tag ORDER BY tag)
                                    FROM (
                                        SELECT DISTINCT tag
                                        FROM jsonb_array_elements_text(
                                            COALESCE(products.raw_data->'category_tags', '[]'::jsonb)
                                            || COALESCE(EXCLUDED.raw_data->'category_tags', '[]'::jsonb)
                                        ) AS merged(tag)
                                        WHERE NULLIF(BTRIM(tag), '') IS NOT NULL
                                    ) AS deduped_tags
                                ),
                                '[]'::jsonb
                            )
                        ),
                    last_scraped_at  = NOW(),
                    updated_at       = NOW()
                RETURNING
                    id,
                    (xmax = 0) AS is_insert,
                    -- Pull the pre-upsert price from the CTE snapshot
                    (SELECT current_price FROM old_row) AS old_price
                """,
                supplier_id, sku, name, description, category, unit,
                price, photo_url, image_urls, country, color, min_qty, case_qty,
                height_in, width_in, diameter_in, length_in, weight_lb,
                material, finish, style, availability, availability_note, json.dumps(raw_data),
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
            sku_set = _selected_sku_set(body.selected_skus)
            all_products = [p for p in all_products if _product_matches_selected_skus(p, sku_set)]
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
VICKERMAN_FULL_SYNC_AUTORUN_KEY = "vickerman_full_sync_autorun_progress.json"
BACKFILL_ZERO_START_STALE_SECONDS = 30
BACKFILL_PROGRESS_STALE_SECONDS = 300


def _int_progress_value(progress: dict, key: str) -> int:
    try:
        return int(progress.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _parse_progress_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _backfill_status_payload(progress: Optional[dict]) -> dict:
    return {
        **{"total": 0, "done": 0, "stored": 0, "skipped": 0, "failed": 0},
        **(progress or {}),
    }


def _reconcile_image_backfill_progress(progress: dict) -> dict:
    """Clear stale running markers left behind by dev-server reloads."""
    if not progress or progress.get("status") != "running":
        return progress

    last_write = _parse_progress_timestamp(progress.get("started_at"))
    if not last_write:
        return progress

    age_seconds = (datetime.utcnow() - last_write).total_seconds()
    zero_work = all(
        _int_progress_value(progress, key) == 0
        for key in ("total", "done", "stored", "skipped", "failed")
    )
    stale_after = BACKFILL_ZERO_START_STALE_SECONDS if zero_work else BACKFILL_PROGRESS_STALE_SECONDS
    if age_seconds <= stale_after:
        return progress

    reconciled = {
        **_backfill_status_payload(progress),
        "status": "failed",
        "completed_at": datetime.utcnow().isoformat(),
        "error": progress.get("error")
        or "Image storage stalled or was interrupted; start it again to resume remaining photos.",
    }
    db.storage.json.put(BACKFILL_PROGRESS_KEY, reconciled)
    return reconciled


async def _run_image_backfill(supplier_id: Optional[int] = None):
    """Background task: download every active product's supplier image and store it.
    Skips products that already have an internal URL (/routes/products/image-proxy?key=).
    Uses raw_data.source_photo_url or product image_urls when import stored the source URL as image pending.
    """
    from app.libs.scraper_base import download_and_store_image as _dl_img

    scope_label = f" for supplier {supplier_id}" if supplier_id else ""
    print(f"[backfill] Starting image backfill{scope_label}")
    db.storage.json.put(BACKFILL_PROGRESS_KEY, {
        "status": "running",
        "supplier_id": supplier_id,
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
            SELECT id, supplier_sku, photo_url, image_urls, raw_data
            FROM products
            WHERE is_active = TRUE
              AND ($1::int IS NULL OR supplier_id = $1)
              AND COALESCE(raw_data->>'image_status', '') != 'no_supplier_image'
              AND (
                (photo_url IS NOT NULL AND photo_url != '')
                OR NULLIF(image_urls[1], '') IS NOT NULL
                OR (raw_data->>'source_photo_url') IS NOT NULL
              )
            ORDER BY id
            """,
            supplier_id,
        )
        total = len(rows)
        print(f"[backfill] Found {total} products with photo_url{scope_label}")
        db.storage.json.put(BACKFILL_PROGRESS_KEY, {
            "status": "running",
            "supplier_id": supplier_id,
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
            typed_image_urls = _string_list(row["image_urls"])
            raw_data = _json_object(row["raw_data"])
            if typed_image_urls and not raw_data.get("image_urls"):
                raw_data["image_urls"] = typed_image_urls
            download_urls = _http_image_url_candidates(photo_url, typed_image_urls, raw_data)
            download_url = download_urls[0] if download_urls else None

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
                internal_url = None
                successful_url = download_url
                for candidate_url in download_urls:
                    successful_url = candidate_url
                    internal_url = _dl_img(candidate_url, sku)
                    if internal_url:
                        break
                if internal_url:
                    try:
                        raw_data["image_status"] = "stored"
                        raw_data["source_photo_url"] = successful_url
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
                    "supplier_id": supplier_id,
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
            "supplier_id": supplier_id,
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
            "supplier_id": supplier_id,
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
            if raw.get("image_status") == "no_supplier_image":
                return False
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
    supplier_id: Optional[int] = None
    total: int
    done: int
    stored: int
    skipped: int
    failed: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


def _running_image_backfill_conflict(progress: dict, supplier_id: Optional[int]) -> Optional[str]:
    """Return a clear conflict message when a different image job is already running."""
    if not progress or progress.get("status") != "running":
        return None
    running_supplier_id = progress.get("supplier_id")
    if supplier_id is None or running_supplier_id is None or running_supplier_id == supplier_id:
        return None
    return (
        f"Image storage is already running for supplier {running_supplier_id}. "
        "Wait for that job to finish before starting this supplier."
    )


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


class VickermanFullSyncStatusOut(BaseModel):
    status: str          # idle | running | done | failed | stopping
    supplier_id: Optional[int] = None
    batch_limit: int = 500
    max_batches: Optional[int] = None
    max_products: Optional[int] = None
    batches_run: int = 0
    total_scraped: int = 0
    total_imported: int = 0
    total_active: Optional[int] = None
    current_job_id: Optional[int] = None
    current_batch: Optional[dict] = None
    last_backfill: Optional[dict] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    stop_requested: bool = False


async def _get_scrape_supplier(supplier_id: int):
    conn = await get_conn()
    try:
        return await conn.fetchrow(
            "SELECT id, name, scraper_key, login_username, login_password, credential_status FROM suppliers WHERE id=$1",
            supplier_id,
        )
    finally:
        await conn.close()


async def _count_supplier_active_products(supplier_id: int) -> int:
    conn = await get_conn()
    try:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM products WHERE supplier_id=$1 AND is_active=TRUE",
            supplier_id,
        ) or 0
    finally:
        await conn.close()


async def _imported_supplier_skus(supplier_id: int) -> set[str]:
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT supplier_sku
            FROM products
            WHERE supplier_id=$1
              AND is_active=TRUE
              AND NULLIF(BTRIM(supplier_sku), '') IS NOT NULL
            """,
            supplier_id,
        )
        return {str(row["supplier_sku"]).strip().upper() for row in rows if row["supplier_sku"]}
    finally:
        await conn.close()


async def _create_import_ready_scrape_job(supplier_id: int, products: list[dict], message: str) -> int:
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO scrape_jobs
                (supplier_id, status, phase, started_at, completed_at,
                 products_found, total_expected, progress_message, milestone_log)
            VALUES
                ($1, 'done', 'ready', NOW(), NOW(), $2, $2, $3, $4::jsonb)
            RETURNING id
            """,
            supplier_id,
            len(products),
            message,
            json.dumps({"logged_in": True, "data_saved": True, "batch_mode": "vickerman_full_sync"}),
        )
        job_id = int(row["id"])
        result_key = f"scrape_job_{job_id}.json"
        db.storage.text.put(result_key, json.dumps(products))
        await conn.execute(
            "UPDATE scrape_jobs SET result_key=$1 WHERE id=$2",
            result_key,
            job_id,
        )
        return job_id
    finally:
        await conn.close()


async def _run_vickerman_full_sync_until_complete(
    supplier_id: int,
    batch_limit: int = 500,
    max_batches: Optional[int] = None,
    max_products: Optional[int] = None,
):
    started_at = datetime.utcnow().isoformat()
    batch_limit = max(1, min(batch_limit or 500, 1000))
    if max_products is not None:
        max_products = max(1, max_products)

    status = {
        "status": "running",
        "supplier_id": supplier_id,
        "batch_limit": batch_limit,
        "max_batches": max_batches,
        "max_products": max_products,
        "batches_run": 0,
        "total_scraped": 0,
        "total_imported": 0,
        "total_active": None,
        "current_job_id": None,
        "current_batch": None,
        "last_backfill": None,
        "started_at": started_at,
        "completed_at": None,
        "message": "Starting Vickerman checkpointed full sync",
        "error": None,
        "stop_requested": False,
    }
    db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, status)

    batches_run = 0
    total_scraped = 0
    total_imported = 0
    try:
        supplier = await _get_scrape_supplier(supplier_id)
        if not supplier:
            raise RuntimeError("Supplier not found")
        resolved_scraper_key = _resolve_scraper_key(supplier["name"], supplier["scraper_key"])
        if resolved_scraper_key != "vickerman":
            raise RuntimeError("This checkpoint runner is only for Vickerman")
        if not supplier["login_username"] or not supplier["login_password"]:
            raise RuntimeError("No Vickerman credentials are saved for this supplier")
        credential_message = _credential_validation_message(resolved_scraper_key, supplier["credential_status"])
        if credential_message:
            raise RuntimeError(credential_message)

        from app.libs import vickerman_scraper as vickerman_module
        vickerman_module = importlib.reload(vickerman_module)

        async def progress(done, total, msg, *args, **kwargs):
            current = db.storage.json.get(VICKERMAN_FULL_SYNC_AUTORUN_KEY, default={})
            current_batch = current.get("current_batch") or {}
            next_batch = {
                **current_batch,
                "queued_or_scraped": done,
                "target": total,
            }
            if "category_index" in kwargs:
                next_batch["category_index"] = kwargs.get("category_index")
            if "category_total" in kwargs:
                next_batch["category_total"] = kwargs.get("category_total")
            if "category_label" in kwargs:
                next_batch["category_label"] = kwargs.get("category_label")
            if "category_collected" in kwargs:
                next_batch["category_collected"] = kwargs.get("category_collected")
            if "category_failures" in kwargs:
                next_batch["category_failures"] = kwargs.get("category_failures")
            if "last_category_error" in kwargs:
                next_batch["last_category_error"] = kwargs.get("last_category_error")
            if "last_product_error" in kwargs:
                next_batch["last_product_error"] = kwargs.get("last_product_error")
            db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
                **current,
                "message": msg,
                "current_batch": next_batch,
            })

        catalog = await vickerman_module.discover_vickerman_catalog(
            supplier["login_username"],
            supplier["login_password"],
            progress,
            supplier_id=supplier_id,
            use_cache=True,
        )
        subcategories = catalog["subcategories"]

        while True:
            current = db.storage.json.get(VICKERMAN_FULL_SYNC_AUTORUN_KEY, default={})
            if current.get("stop_requested"):
                db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
                    **current,
                    "status": "stopping",
                    "completed_at": datetime.utcnow().isoformat(),
                    "message": "Stopped after the last completed checkpoint",
                })
                return
            if max_batches is not None and batches_run >= max_batches:
                total_active = await _count_supplier_active_products(supplier_id)
                db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
                    **current,
                    "status": "done",
                    "batches_run": batches_run,
                    "total_scraped": total_scraped,
                    "total_imported": total_imported,
                    "total_active": total_active,
                    "completed_at": datetime.utcnow().isoformat(),
                    "message": f"Stopped after {batches_run} batch(es); run again to continue",
                    "stop_requested": False,
                })
                return
            if max_products is not None and total_imported >= max_products:
                total_active = await _count_supplier_active_products(supplier_id)
                db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
                    **current,
                    "status": "done",
                    "batches_run": batches_run,
                    "total_scraped": total_scraped,
                    "total_imported": total_imported,
                    "total_active": total_active,
                    "completed_at": datetime.utcnow().isoformat(),
                    "message": f"Reached requested cap of {max_products:,} imported products",
                    "stop_requested": False,
                })
                return

            imported_skus = await _imported_supplier_skus(supplier_id)
            remaining_cap = None if max_products is None else max_products - total_imported
            this_batch_limit = min(batch_limit, remaining_cap) if remaining_cap else batch_limit
            batch_number = batches_run + 1
            db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
                **current,
                "status": "running",
                "batches_run": batches_run,
                "total_scraped": total_scraped,
                "total_imported": total_imported,
                "current_batch": {
                    "batch_number": batch_number,
                    "excluded_skus": len(imported_skus),
                    "limit": this_batch_limit,
                    "scraped": 0,
                },
                "message": f"Running Vickerman batch {batch_number}; skipping {len(imported_skus):,} already-imported SKUs",
                "stop_requested": False,
            })

            products: list[dict] = []
            async for product in vickerman_module.scrape_vickerman(
                supplier["login_username"],
                supplier["login_password"],
                this_batch_limit,
                progress,
                subcategories=subcategories,
                supplier_id=supplier_id,
                excluded_item_numbers=imported_skus,
            ):
                products.append(_scraped_product_to_import_dict(product))

            if not products:
                total_active = await _count_supplier_active_products(supplier_id)
                done_status = db.storage.json.get(VICKERMAN_FULL_SYNC_AUTORUN_KEY, default={})
                db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
                    **done_status,
                    "status": "done",
                    "batches_run": batches_run,
                    "total_scraped": total_scraped,
                    "total_imported": total_imported,
                    "total_active": total_active,
                    "completed_at": datetime.utcnow().isoformat(),
                    "message": "No new Vickerman products were found; catalog checkpoint is complete",
                    "stop_requested": False,
                })
                return

            job_id = await _create_import_ready_scrape_job(
                supplier_id,
                products,
                f"Vickerman checkpoint batch {batch_number}: {len(products):,} products ready to import",
            )
            total_scraped += len(products)
            batch_status = db.storage.json.get(VICKERMAN_FULL_SYNC_AUTORUN_KEY, default={})
            db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
                **batch_status,
                "current_job_id": job_id,
                "current_batch": {
                    **(batch_status.get("current_batch") or {}),
                    "job_id": job_id,
                    "scraped": len(products),
                    "phase": "importing",
                },
                "message": f"Importing Vickerman batch {batch_number} ({len(products):,} products)",
            })
            await _run_import(job_id, supplier_id, None)

            conn = await get_conn()
            try:
                job_row = await conn.fetchrow(
                    "SELECT status, phase, error_message, products_imported FROM scrape_jobs WHERE id=$1",
                    job_id,
                )
            finally:
                await conn.close()
            if job_row and job_row["status"] == "failed":
                raise RuntimeError(job_row["error_message"] or f"Vickerman import job {job_id} failed")
            imported_count = int(job_row["products_imported"] or len(products)) if job_row else len(products)
            total_imported += imported_count

            batch_status = db.storage.json.get(VICKERMAN_FULL_SYNC_AUTORUN_KEY, default={})
            db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
                **batch_status,
                "current_batch": {
                    **(batch_status.get("current_batch") or {}),
                    "phase": "image_backfill",
                    "imported": imported_count,
                },
                "message": f"Storing Vickerman images for batch {batch_number}",
            })
            await _run_image_backfill(supplier_id)
            backfill = db.storage.json.get(BACKFILL_PROGRESS_KEY, default={})

            batches_run += 1
            total_active = await _count_supplier_active_products(supplier_id)
            db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
                "status": "running",
                "supplier_id": supplier_id,
                "batch_limit": batch_limit,
                "max_batches": max_batches,
                "max_products": max_products,
                "batches_run": batches_run,
                "total_scraped": total_scraped,
                "total_imported": total_imported,
                "total_active": total_active,
                "current_job_id": job_id,
                "current_batch": {
                    "batch_number": batch_number,
                    "job_id": job_id,
                    "scraped": len(products),
                    "imported": imported_count,
                    "phase": "checkpointed",
                },
                "last_backfill": backfill,
                "started_at": started_at,
                "completed_at": None,
                "message": f"Finished Vickerman batch {batch_number}; {total_active:,} active products now stored",
                "error": None,
                "stop_requested": False,
            })
            await asyncio.sleep(2)
    except Exception as exc:
        current = db.storage.json.get(VICKERMAN_FULL_SYNC_AUTORUN_KEY, default={})
        db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, {
            **status,
            **current,
            "status": "failed",
            "batches_run": batches_run,
            "total_scraped": total_scraped,
            "total_imported": total_imported,
            "completed_at": datetime.utcnow().isoformat(),
            "message": "Vickerman checkpointed full sync stopped with an error",
            "error": str(exc)[:500],
            "stop_requested": False,
        })


async def _reconcile_vickerman_full_sync_status(raw: dict) -> dict:
    """Clear stale stopped/running state after a checkpoint job is recovered manually."""
    if not raw or raw.get("status") != "running" or not raw.get("stop_requested"):
        return raw or {}

    job_id = raw.get("current_job_id") or (raw.get("current_batch") or {}).get("job_id")
    if not job_id:
        updated = {
            **raw,
            "status": "stopped",
            "completed_at": raw.get("completed_at") or datetime.utcnow().isoformat(),
            "message": "Stopped before a checkpoint job was created; run again to continue",
            "stop_requested": False,
        }
        db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, updated)
        return updated

    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            """
            SELECT supplier_id, products_found, products_imported, status, phase
              FROM scrape_jobs
             WHERE id = $1
            """,
            int(job_id),
        )
    finally:
        await conn.close()

    if not row:
        return raw

    products_found = int(row["products_found"] or 0)
    products_imported = int(row["products_imported"] or 0)
    if row["status"] == "done" and row["phase"] == "done" and products_imported >= products_found:
        supplier_id = int(raw.get("supplier_id") or row["supplier_id"])
        total_active = await _count_supplier_active_products(supplier_id)
        updated = {
            **raw,
            "status": "stopped",
            "total_imported": max(int(raw.get("total_imported") or 0), products_imported),
            "total_active": total_active,
            "completed_at": raw.get("completed_at") or datetime.utcnow().isoformat(),
            "current_batch": {
                **(raw.get("current_batch") or {}),
                "job_id": int(job_id),
                "scraped": products_found,
                "imported": products_imported,
                "phase": "checkpointed_recovered",
            },
            "message": f"Stopped after recovered Vickerman checkpoint job {job_id}; run again to continue",
            "error": None,
            "stop_requested": False,
        }
        db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, updated)
        return updated

    return raw


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
                OR (
                  COALESCE(raw_data->>'image_status', '') != 'no_supplier_image'
                  AND (photo_url IS NULL OR photo_url = '')
                )
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
    progress = _reconcile_image_backfill_progress(db.storage.json.get(BACKFILL_PROGRESS_KEY, default={}))
    if progress.get("status") == "running":
        return BackfillStatusOut(**_backfill_status_payload(progress))

    background_tasks.add_task(_run_image_backfill)
    return BackfillStatusOut(
        status="running", total=0, done=0, stored=0, skipped=0, failed=0,
        started_at=datetime.utcnow().isoformat(),
    )


@router.post("/backfill-images/{supplier_id}", response_model=BackfillStatusOut)
async def start_supplier_backfill_images(supplier_id: int, background_tasks: BackgroundTasks):
    """Download supplier image URLs for one supplier into internal storage."""
    progress = _reconcile_image_backfill_progress(db.storage.json.get(BACKFILL_PROGRESS_KEY, default={}))
    conflict = _running_image_backfill_conflict(progress, supplier_id)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    if progress.get("status") == "running":
        return BackfillStatusOut(**_backfill_status_payload(progress))

    background_tasks.add_task(_run_image_backfill, supplier_id)
    return BackfillStatusOut(
        status="running", supplier_id=supplier_id, total=0, done=0, stored=0, skipped=0, failed=0,
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
    return BackfillStatusOut(**_backfill_status_payload(_reconcile_image_backfill_progress(raw)))


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


@router.post("/vickerman/{supplier_id}/run-until-complete", response_model=VickermanFullSyncStatusOut)
async def start_vickerman_full_sync_until_complete(
    supplier_id: int,
    batch_limit: int = 500,
    max_batches: Optional[int] = None,
    max_products: Optional[int] = None,
):
    """Run checkpointed Vickerman scrape/import/image batches until stopped or complete."""
    autorun = await _reconcile_vickerman_full_sync_status(
        db.storage.json.get(VICKERMAN_FULL_SYNC_AUTORUN_KEY, default={})
    )
    if autorun.get("status") == "running":
        return VickermanFullSyncStatusOut(**{
            "status": "running",
            **autorun,
        })
    image_progress = _reconcile_image_backfill_progress(db.storage.json.get(BACKFILL_PROGRESS_KEY, default={}))
    conflict = _running_image_backfill_conflict(image_progress, supplier_id)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    safe_limit = max(1, min(batch_limit or 500, 1000))

    def _run_in_thread():
        asyncio.run(_run_vickerman_full_sync_until_complete(
            supplier_id,
            safe_limit,
            max_batches,
            max_products,
        ))

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()
    return VickermanFullSyncStatusOut(
        status="running",
        supplier_id=supplier_id,
        batch_limit=safe_limit,
        max_batches=max_batches,
        max_products=max_products,
        started_at=datetime.utcnow().isoformat(),
        message="Vickerman checkpointed full sync started",
    )


@router.post("/vickerman/run-until-complete/stop", response_model=VickermanFullSyncStatusOut)
async def stop_vickerman_full_sync_until_complete():
    autorun = await _reconcile_vickerman_full_sync_status(
        db.storage.json.get(VICKERMAN_FULL_SYNC_AUTORUN_KEY, default={})
    )
    if not autorun:
        return VickermanFullSyncStatusOut(status="idle", message="No Vickerman checkpointed sync exists")
    if autorun.get("status") != "running":
        return VickermanFullSyncStatusOut(**{
            "status": autorun.get("status", "idle"),
            **autorun,
        })
    updated = {**autorun, "stop_requested": True, "message": "Stop requested; finishing the current checkpoint"}
    db.storage.json.put(VICKERMAN_FULL_SYNC_AUTORUN_KEY, updated)
    return VickermanFullSyncStatusOut(**updated)


@router.get("/vickerman/run-until-complete/status", response_model=VickermanFullSyncStatusOut)
async def get_vickerman_full_sync_until_complete_status():
    raw = await _reconcile_vickerman_full_sync_status(
        db.storage.json.get(VICKERMAN_FULL_SYNC_AUTORUN_KEY, default={})
    )
    if not raw:
        return VickermanFullSyncStatusOut(status="idle")
    return VickermanFullSyncStatusOut(**{
        "status": "idle",
        **raw,
    })


@router.post("/allstate-placeholder-images/{supplier_id}/mark-reviewed", response_model=PlaceholderImageReviewOut)
async def mark_allstate_placeholder_images_reviewed(supplier_id: int):
    """Mark known Allstate placeholder images as reviewed no-image products.

    Allstate sometimes returns /images/price_update.gif as the product image.
    That is not a real product photo, so it should stop being treated as a
    retryable image-storage failure.
    """
    conn = await get_conn()
    try:
        supplier = await conn.fetchrow(
            "SELECT id, name, scraper_key FROM suppliers WHERE id = $1",
            supplier_id,
        )
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        scraper_key = _resolve_scraper_key(supplier["name"], supplier["scraper_key"])
        if scraper_key != "allstate":
            raise HTTPException(status_code=400, detail="Placeholder review is currently only available for Allstate.")

        rows = await conn.fetch(
            """
            SELECT id, raw_data
            FROM products
            WHERE supplier_id = $1
              AND is_active = TRUE
              AND COALESCE(raw_data->>'image_status', '') != 'no_supplier_image'
              AND (
                LOWER(COALESCE(photo_url, '')) LIKE '%price_update.gif%'
                OR LOWER(COALESCE(raw_data->>'source_photo_url', '')) LIKE '%price_update.gif%'
              )
            """,
            supplier_id,
        )

        reviewed_at = datetime.utcnow().isoformat()
        reviewed_count = 0
        for row in rows:
            raw_data = dict(row["raw_data"] or {})
            raw_data["image_status"] = "no_supplier_image"
            raw_data["image_problem_type"] = "supplier_placeholder"
            raw_data["placeholder_reviewed_at"] = reviewed_at
            raw_data["placeholder_review_note"] = "Allstate returned price_update.gif instead of a product photo."
            await conn.execute(
                """
                UPDATE products
                   SET photo_url = NULL,
                       raw_data = COALESCE(raw_data, '{}'::jsonb) || $1::jsonb,
                       updated_at = NOW()
                 WHERE id = $2
                """,
                json.dumps(raw_data),
                row["id"],
            )
            reviewed_count += 1

        return PlaceholderImageReviewOut(
            supplier_id=supplier_id,
            reviewed_count=reviewed_count,
            message=(
                f"Marked {reviewed_count:,} Allstate placeholder image"
                f"{'' if reviewed_count == 1 else 's'} as no supplier image."
            ),
        )
    finally:
        await conn.close()


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
                      AND LOWER(COALESCE(photo_url, '')) NOT LIKE '%price_update.gif%'
                      AND LOWER(COALESCE(raw_data->>'source_photo_url', '')) NOT LIKE '%price_update.gif%'
                ) AS images_stored,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND display_photo_url LIKE 'http%'
                      AND COALESCE(raw_data->>'image_status', '') != 'no_supplier_image'
                      AND LOWER(COALESCE(display_photo_url, '')) NOT LIKE '%price_update.gif%'
                      AND LOWER(COALESCE(raw_data->>'source_photo_url', '')) NOT LIKE '%price_update.gif%'
                ) AS images_external,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND display_photo_url IS NOT NULL
                      AND display_photo_url != ''
                      AND LOWER(COALESCE(display_photo_url, '')) NOT LIKE '%price_update.gif%'
                      AND LOWER(COALESCE(raw_data->>'source_photo_url', '')) NOT LIKE '%price_update.gif%'
                ) AS images_with_reference,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND raw_data->>'image_status' = 'no_supplier_image'
                ) AS images_no_supplier_image,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND (
                        (
                          display_photo_url IS NOT NULL
                          AND display_photo_url != ''
                          AND LOWER(COALESCE(display_photo_url, '')) NOT LIKE '%price_update.gif%'
                          AND LOWER(COALESCE(raw_data->>'source_photo_url', '')) NOT LIKE '%price_update.gif%'
                        )
                        OR raw_data->>'image_status' = 'no_supplier_image'
                      )
                ) AS images_resolved,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND COALESCE(raw_data->>'image_status', 'pending') = 'pending'
                ) AS images_pending,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND raw_data->>'image_status' = 'failed'
                      AND LOWER(COALESCE(display_photo_url, '')) NOT LIKE '%price_update.gif%'
                      AND LOWER(COALESCE(raw_data->>'source_photo_url', '')) NOT LIKE '%price_update.gif%'
                ) AS images_failed,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND COALESCE(raw_data->>'image_status', '') != 'no_supplier_image'
                      AND (display_photo_url IS NULL OR display_photo_url = '')
                ) AS images_missing
            FROM (
                SELECT *,
                       COALESCE(
                           NULLIF(photo_url, ''),
                           NULLIF(image_urls[1], ''),
                           NULLIF(raw_data->>'source_photo_url', '')
                       ) AS display_photo_url
                FROM products
                WHERE supplier_id = $1
            ) products
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
            images_no_supplier_image=row["images_no_supplier_image"] or 0,
            images_resolved=row["images_resolved"] or 0,
            images_pending=row["images_pending"] or 0,
            images_failed=row["images_failed"] or 0,
            images_missing=row["images_missing"] or 0,
            last_backfill=progress or None,
        )
    finally:
        await conn.close()


@router.get("/supplier-readiness/{supplier_id}", response_model=AllstateReadinessOut)
@router.get("/allstate-readiness/{supplier_id}", response_model=AllstateReadinessOut)
async def get_allstate_readiness(supplier_id: int):
    """Summarize the full supplier pipeline: config, import, enrichment, and builder use."""
    conn = await get_conn()
    try:
        supplier = await conn.fetchrow(
            """
            SELECT id, name, scraper_key,
                   COALESCE(credential_status, 'missing') AS credential_status,
                   (login_username IS NOT NULL AND login_username != ''
                    AND login_password IS NOT NULL AND login_password != '') AS has_credentials
            FROM suppliers
            WHERE id = $1
            """,
            supplier_id,
        )
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        scraper_key = _resolve_scraper_key(supplier["name"], supplier["scraper_key"])
        if scraper_key not in ("allstate", "accent_decor", "regency", "select_artificial", "vickerman"):
            raise HTTPException(status_code=400, detail="Readiness summary is currently available for Allstate, Accent Decor, Regency, Select Artificial, and Vickerman.")
        supplier_label = supplier["name"] or ("Accent Decor" if scraper_key == "accent_decor" else "Allstate")

        category_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE is_active = TRUE)::int AS active_categories,
                COALESCE(SUM(product_count) FILTER (WHERE is_active = TRUE), 0)::int AS estimated_products
            FROM supplier_category_index
            WHERE supplier_id = $1 AND scraper_key = $2
            """,
            supplier_id,
            scraper_key,
        )
        category_index_count = int(category_row["active_categories"] or 0)
        estimated_all_products = int(category_row["estimated_products"] or 0)

        filters = await conn.fetchrow(
            """
            SELECT categories
            FROM supplier_catalog_filters
            WHERE supplier_id = $1
            """,
            supplier_id,
        )
        selected_categories: list[str] = []
        if filters and filters["categories"] is not None:
            raw_categories = filters["categories"]
            if isinstance(raw_categories, str):
                try:
                    parsed = json.loads(raw_categories)
                    selected_categories = parsed if isinstance(parsed, list) else []
                except Exception:
                    selected_categories = []
            else:
                selected_categories = list(raw_categories)

        if selected_categories:
            selected_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int AS selected_count,
                    COALESCE(SUM(product_count), 0)::int AS selected_products
                FROM supplier_category_index
                WHERE supplier_id = $1
                  AND scraper_key = $2
                  AND is_active = TRUE
                  AND category_slug_or_url = ANY($3::text[])
                """,
                supplier_id,
                scraper_key,
                selected_categories,
            )
            selected_category_count = int(selected_row["selected_count"] or 0)
            estimated_selected_products = int(selected_row["selected_products"] or 0)
            selected_category_mode = "selected"
        elif category_index_count > 0:
            selected_category_count = category_index_count
            estimated_selected_products = estimated_all_products
            selected_category_mode = "all"
        else:
            selected_category_count = 0
            estimated_selected_products = 0
            selected_category_mode = "none"

        product_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE is_active = TRUE)::int AS total_active,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND supplier_sku IS NOT NULL AND supplier_sku != ''
                      AND name IS NOT NULL AND name != ''
                      AND category IS NOT NULL AND category != ''
                      AND current_price IS NOT NULL
                      AND unit IS NOT NULL AND unit != ''
                )::int AS standardized_count,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND display_photo_url IS NOT NULL
                      AND display_photo_url != ''
                      AND LOWER(COALESCE(display_photo_url, '')) NOT LIKE '%price_update.gif%'
                      AND LOWER(COALESCE(raw_data->>'source_photo_url', '')) NOT LIKE '%price_update.gif%'
                )::int AS photo_ready_count,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND photo_url LIKE '/api/products/image-proxy?key=%'
                )::int AS internal_photo_count,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND display_photo_url LIKE 'http%'
                      AND COALESCE(raw_data->>'image_status', '') != 'no_supplier_image'
                      AND LOWER(COALESCE(display_photo_url, '')) NOT LIKE '%price_update.gif%'
                      AND LOWER(COALESCE(raw_data->>'source_photo_url', '')) NOT LIKE '%price_update.gif%'
                )::int AS supplier_hosted_photo_count,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND raw_data->>'image_status' = 'failed'
                )::int AS photo_problem_count,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND COALESCE(raw_data->>'image_status', '') != 'no_supplier_image'
                      AND (
                        LOWER(COALESCE(display_photo_url, '')) LIKE '%price_update.gif%'
                        OR LOWER(COALESCE(raw_data->>'source_photo_url', '')) LIKE '%price_update.gif%'
                      )
                )::int AS placeholder_image_count,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND raw_data->>'image_status' = 'no_supplier_image'
                )::int AS no_supplier_image_count,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND (
                        raw_data->>'image_status' = 'failed'
                        OR display_photo_url LIKE 'http%'
                        OR display_photo_url IS NULL
                        OR display_photo_url = ''
                      )
                      AND COALESCE(raw_data->>'image_status', '') != 'no_supplier_image'
                      AND NOT (
                        LOWER(COALESCE(display_photo_url, '')) LIKE '%price_update.gif%'
                        OR LOWER(COALESCE(raw_data->>'source_photo_url', '')) LIKE '%price_update.gif%'
                      )
                )::int AS retryable_image_problem_count,
                COUNT(*) FILTER (
                    WHERE is_active = TRUE
                      AND raw_data->>'detail_status' = 'stored'
                )::int AS detail_ready_count
            FROM (
                SELECT *,
                       COALESCE(
                           NULLIF(photo_url, ''),
                           NULLIF(image_urls[1], ''),
                           NULLIF(raw_data->>'source_photo_url', '')
                       ) AS display_photo_url
                FROM products
                WHERE supplier_id = $1
            ) products
            """,
            supplier_id,
        )
        product_count = int(product_row["total_active"] or 0)
        standardized_count = int(product_row["standardized_count"] or 0)
        photo_ready_count = int(product_row["photo_ready_count"] or 0)
        internal_photo_count = int(product_row["internal_photo_count"] or 0)
        supplier_hosted_photo_count = int(product_row["supplier_hosted_photo_count"] or 0)
        photo_problem_count = int(product_row["photo_problem_count"] or 0)
        placeholder_image_count = int(product_row["placeholder_image_count"] or 0)
        no_supplier_image_count = int(product_row["no_supplier_image_count"] or 0)
        retryable_image_problem_count = int(product_row["retryable_image_problem_count"] or 0)
        detail_ready_count = int(product_row["detail_ready_count"] or 0)
        image_resolved_count = min(product_count, photo_ready_count + no_supplier_image_count)
        fully_ready_count = min(standardized_count, image_resolved_count, detail_ready_count)
        ready_percent = (
            100 if product_count > 0 and fully_ready_count == product_count
            else min(99, int((fully_ready_count / product_count) * 100)) if product_count else 0
        )
        storage_percent = (
            100 if product_count > 0 and internal_photo_count == product_count
            else min(99, int((internal_photo_count / product_count) * 100)) if product_count else 0
        )

        builder_item_count = int(await conn.fetchval(
            """
            SELECT COUNT(*)::int
            FROM container_items ci
            JOIN products p ON p.id = ci.product_id
            WHERE p.supplier_id = $1
              AND p.is_active = TRUE
            """,
            supplier_id,
        ) or 0)

        image_problem_rows = await conn.fetch(
            """
            SELECT
                id,
                supplier_sku,
                name,
                display_photo_url AS photo_url,
                raw_data->>'source_photo_url' AS source_photo_url,
                raw_data->>'image_status' AS image_status,
                CASE
                    WHEN LOWER(COALESCE(display_photo_url, '')) LIKE '%price_update.gif%'
                      OR LOWER(COALESCE(raw_data->>'source_photo_url', '')) LIKE '%price_update.gif%'
                    THEN 'placeholder'
                    ELSE 'retryable'
                END AS problem_type
            FROM (
                SELECT *,
                       COALESCE(
                           NULLIF(photo_url, ''),
                           NULLIF(image_urls[1], ''),
                           NULLIF(raw_data->>'source_photo_url', '')
                       ) AS display_photo_url
                FROM products
                WHERE supplier_id = $1
            ) products
            WHERE supplier_id = $1
              AND is_active = TRUE
              AND (
                raw_data->>'image_status' = 'failed'
                OR display_photo_url LIKE 'http%'
                OR display_photo_url IS NULL
                OR display_photo_url = ''
              )
              AND COALESCE(raw_data->>'image_status', '') != 'no_supplier_image'
            ORDER BY
              CASE
                WHEN LOWER(COALESCE(display_photo_url, '')) LIKE '%price_update.gif%'
                  OR LOWER(COALESCE(raw_data->>'source_photo_url', '')) LIKE '%price_update.gif%'
                THEN 0
                WHEN raw_data->>'image_status' = 'failed' THEN 1
                ELSE 2
              END,
              id
            LIMIT 5
            """,
            supplier_id,
        )
        image_problem_samples = [
            SupplierImageProblem(
                product_id=row["id"],
                supplier_sku=row["supplier_sku"] or "",
                name=row["name"] or "",
                photo_url=row["photo_url"],
                source_photo_url=row["source_photo_url"],
                image_status=row["image_status"],
                problem_type=row["problem_type"] or "retryable",
            )
            for row in image_problem_rows
        ]

        steps: list[SupplierReadinessStep] = []

        def add_step(key: str, label: str, status: str, detail: str, action: Optional[str] = None):
            steps.append(SupplierReadinessStep(
                key=key,
                label=label,
                status=status,
                detail=detail,
                action=action,
            ))

        has_credentials = bool(supplier["has_credentials"])
        credential_status = supplier["credential_status"] or ("untested" if has_credentials else "missing")
        credentials_failed = credential_status in ("failed", "error")
        credentials_untested = credential_status == "untested"
        add_step(
            "credentials",
            "Credentials",
            "missing" if not has_credentials else ("partial" if (credentials_failed or credentials_untested) else "done"),
            _credential_step_detail(supplier_label, scraper_key, has_credentials, credential_status),
            _credential_step_action(scraper_key, has_credentials, credential_status),
        )
        add_step(
            "configuration",
            "Catalog configuration",
            "done" if category_index_count > 0 else "missing",
            f"{category_index_count:,} active categories cached." if category_index_count > 0 else f"No remembered {supplier_label} category index yet.",
            None if category_index_count > 0 else "Open Configure Catalog and discover categories.",
        )
        selection_detail = _catalog_selection_detail(
            selected_category_mode,
            selected_category_count,
            estimated_selected_products,
            product_count,
        )
        add_step(
            "selection",
            "Selected catalog",
            "done" if selected_category_mode in ("selected", "all") else "missing",
            selection_detail,
            None if selected_category_mode in ("selected", "all") else "Choose or confirm catalog categories.",
        )
        add_step(
            "upload",
            "Product Library upload",
            "done" if product_count > 0 else "missing",
            f"{product_count:,} active {supplier_label} products are in Product Library." if product_count > 0 else f"No {supplier_label} products are imported yet.",
            None if product_count > 0 else "Run Sync Catalog, preview, then import.",
        )
        standardized_status = "done" if product_count > 0 and standardized_count == product_count else ("partial" if standardized_count > 0 else "missing")
        add_step(
            "standardized",
            "Standardized product data",
            standardized_status,
            f"{standardized_count:,} of {product_count:,} products have SKU, name, category, price, and UOM." if product_count > 0 else "No imported products to standardize yet.",
            None if standardized_status == "done" else ("Finish import/backfill and review product mapping." if product_count > 0 else "Import products first."),
        )
        media_status = "done" if product_count > 0 and fully_ready_count == product_count else ("partial" if fully_ready_count > 0 else "missing")
        media_action = None if media_status == "done" else ("Run Complete missing photos/details." if product_count > 0 else "Import products before running photo/detail enrichment.")
        if media_status != "done" and retryable_image_problem_count == 0 and placeholder_image_count > 0:
            media_action = "Review supplier placeholder images and mark them as no-image when appropriate."
        if product_count > 0 and no_supplier_image_count > 0:
            media_detail = (
                f"{fully_ready_count:,} of {product_count:,} products have standardized data, detail payloads, and resolved image status; "
                f"{no_supplier_image_count:,} are marked as no supplier image."
            )
        elif product_count > 0 and placeholder_image_count > 0:
            media_detail = (
                f"{fully_ready_count:,} of {product_count:,} products have standardized data, detail payloads, and real product photos; "
                f"{placeholder_image_count:,} still show supplier placeholders."
            )
        elif product_count > 0:
            media_detail = f"{fully_ready_count:,} of {product_count:,} products have standardized data, detail payloads, and displayable photos."
        else:
            media_detail = "No imported products to enrich yet."
        add_step(
            "media_details",
            "Photos and full details",
            media_status,
            media_detail,
            media_action,
        )
        storage_resolved_count = min(product_count, internal_photo_count + no_supplier_image_count)
        storage_status = "done" if product_count > 0 and storage_resolved_count == product_count else ("partial" if storage_resolved_count > 0 else "missing")
        storage_action = None if storage_status == "done" else ("Retry image problems so more photos are stored inside Leaf & Ledger." if product_count > 0 else "Import products before storing photos.")
        if storage_status != "done" and retryable_image_problem_count == 0 and placeholder_image_count > 0:
            storage_action = "Review supplier placeholder images and mark them as no-image when appropriate."

        if product_count > 0 and supplier_hosted_photo_count > 0:
            storage_parts = [
                f"{internal_photo_count:,} photos are stored internally",
                f"{supplier_hosted_photo_count:,} are still supplier-hosted fallbacks",
            ]
            if placeholder_image_count > 0:
                storage_parts.append(f"{placeholder_image_count:,} look like supplier placeholders")
            if retryable_image_problem_count > 0:
                storage_parts.append(f"{retryable_image_problem_count:,} still look retryable")
            storage_detail = "; ".join(storage_parts) + "."
        elif product_count > 0 and no_supplier_image_count > 0:
            storage_detail = (
                f"{internal_photo_count:,} photos are stored internally; "
                f"{no_supplier_image_count:,} products are marked as no supplier image."
            )
        elif product_count > 0 and placeholder_image_count > 0:
            storage_detail = (
                f"{internal_photo_count:,} photos are stored internally; "
                f"{placeholder_image_count:,} supplier placeholders need review."
            )
        elif product_count > 0:
            storage_detail = f"{internal_photo_count:,} of {product_count:,} photos are stored internally."
        else:
            storage_detail = "No imported products to store images for yet."
        add_step(
            "picture_storage",
            "Picture storage",
            storage_status,
            storage_detail,
            storage_action,
        )
        builder_status = "done" if product_count > 0 else "missing"
        add_step(
            "builder",
            "Builder connection",
            builder_status,
            f"{supplier_label} products are used in {builder_item_count:,} builder line items." if builder_item_count > 0 else (
                "Products are ready to add to project buckets." if product_count > 0 else "Builder use starts after products are imported."
            ),
            None if product_count > 0 else "Import products first.",
        )

        next_action = f"{supplier_label} catalog is fully ready for builder use."
        for step in steps:
            if step.status in ("missing", "partial"):
                next_action = step.action or step.detail
                break

        return AllstateReadinessOut(
            supplier_id=supplier_id,
            supplier_name=supplier["name"],
            scraper_key=scraper_key,
            has_credentials=has_credentials,
            credential_status=credential_status,
            category_index_count=category_index_count,
            selected_category_count=selected_category_count,
            selected_category_mode=selected_category_mode,
            estimated_selected_products=estimated_selected_products,
            product_count=product_count,
            standardized_count=standardized_count,
            photo_ready_count=photo_ready_count,
            internal_photo_count=internal_photo_count,
            supplier_hosted_photo_count=supplier_hosted_photo_count,
            photo_problem_count=photo_problem_count,
            placeholder_image_count=placeholder_image_count,
            no_supplier_image_count=no_supplier_image_count,
            retryable_image_problem_count=retryable_image_problem_count,
            detail_ready_count=detail_ready_count,
            fully_ready_count=fully_ready_count,
            builder_item_count=builder_item_count,
            ready_percent=ready_percent,
            storage_percent=storage_percent,
            image_problem_samples=image_problem_samples,
            next_action=next_action,
            steps=steps,
        )
    finally:
        await conn.close()
