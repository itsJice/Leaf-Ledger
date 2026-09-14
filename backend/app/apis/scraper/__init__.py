"""Scraper API - trigger supplier catalog scrapes and track job progress."""
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import asyncpg
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





















# Background worker



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






# Endpoints













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






# ── Image backfill ─────────────────────────────────────────────────────────────
# Downloads all existing product images to Databutton storage.
# Progress is tracked in a JSON file so the UI can poll it.

BACKFILL_PROGRESS_KEY = "backfill_images_progress.json"
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




@router.get("/backfill-images/status", response_model=BackfillStatusOut)
async def get_backfill_status():
    """Poll the progress of the image backfill background job."""
    raw = db.storage.json.get(BACKFILL_PROGRESS_KEY, default={})
    if not raw:
        return BackfillStatusOut(
            status="idle", total=0, done=0, stored=0, skipped=0, failed=0
        )
    return BackfillStatusOut(**_backfill_status_payload(_reconcile_image_backfill_progress(raw)))






















