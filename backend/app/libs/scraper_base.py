"""Shared scraper framework for all Leaf & Ledger supplier scrapers.

All supplier scrapers inherit from this module. It provides:
- Universal ScrapedProduct dataclass (matches the full products schema)
- Retry logic with exponential backoff
- Polite request delays
- Sync log management (inserts / updates scrape_sync_logs)
- Category normalization
- Price parsing helpers
- Progress callback protocol
"""
import asyncio
import re
import os
import requests
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from datetime import datetime
import asyncpg
import databutton as db
import json

DATABASE_URL = os.environ.get("DATABASE_URL")


# ─────────────────────────────────────────────
# Universal product dataclass
# ─────────────────────────────────────────────

@dataclass
class ScrapedProduct:
    """Normalized product row returned by any scraper.
    
    Every field maps 1:1 to the products table column.
    Scrapers fill in as many fields as the supplier exposes.
    """
    # Required
    sku: str                              # maps to supplier_sku
    name: str

    # Categorization
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: list = field(default_factory=list)

    # Pricing
    base_price: Optional[float] = None
    currency: str = "USD"

    # Physical dimensions
    height_in: Optional[float] = None
    width_in: Optional[float] = None
    diameter_in: Optional[float] = None
    length_in: Optional[float] = None
    weight_lb: Optional[float] = None

    # Material / style
    material: Optional[str] = None
    finish: Optional[str] = None
    color: Optional[str] = None
    style: Optional[str] = None

    # Purchasing
    uom: Optional[str] = None             # EA, stem, bunch, etc.
    moq: Optional[int] = None             # minimum order qty
    box_qty: Optional[int] = None
    case_qty: Optional[int] = None
    lead_time_days: Optional[int] = None

    # Availability
    availability: Optional[str] = None    # in_stock | out_of_stock | eta | unknown
    availability_note: Optional[str] = None

    # Images
    photo_url: Optional[str] = None       # primary image
    image_urls: list = field(default_factory=list)

    # Supplier IDs
    supplier_product_id: Optional[str] = None
    upc: Optional[str] = None

    # Content
    description: Optional[str] = None
    country_of_origin: Optional[str] = None

    # Raw key-value dump from page (for debugging)
    raw: dict = field(default_factory=dict)


# ─────────────────────────────────────────────
# Category normalization
# ─────────────────────────────────────────────

CATEGORY_MAP: dict[str, str] = {
    "artificial plants": "plant",
    "artificial trees": "trees",
    "silk plants": "plant",
    "silk trees": "trees",
    "real touch": "plant",
    "succulents": "succulents",
    "topiaries": "topiaries",
    "foliage": "foliage",
    "greenery": "greenery",
    "ferns": "foliage",
    "ivies": "foliage",
    "palms": "trees",
    "flowers": "florals",
    "florals": "florals",
    "stems": "stems",
    "botanicals": "botanicals",
    "dried": "botanicals",
    "preserved": "preserved",
    "containers": "containers",
    "pots": "containers",
    "planters": "containers",
    "vases": "vases",
    "baskets": "baskets",
    "urns": "containers",
    "bowls": "containers",
    "moss": "moss",
    "branches": "branches",
    "filler": "filler",
    "accents": "accent",
    "decorative": "accent",
    "wreaths": "wreaths",
    "seasonal": "seasonal",
    "christmas": "seasonal",
    "holiday": "seasonal",
    "fall": "seasonal",
    "spring": "seasonal",
    "risers": "risers",
    "pedestals": "pedestals",
    "liners": "liners",
    "wood": "wood",
}

VALID_CATEGORIES = {
    'containers', 'wood', 'greenery', 'florals', 'trees', 'plant',
    'container', 'filler', 'accent', 'other',
    'moss', 'branches', 'botanicals', 'preserved', 'seasonal',
    'stems', 'foliage', 'succulents', 'topiaries', 'wreaths',
    'baskets', 'vases', 'risers', 'pedestals', 'liners'
}

VALID_UNITS = {
    'stem', 'pot', 'flat', 'bunch', 'each',
    'box', 'case', 'bag', 'roll', 'yard', 'foot', 'piece', 'set', 'pair'
}


def normalize_category(raw_category: Optional[str]) -> str:
    if not raw_category:
        return "other"
    lower = raw_category.lower().strip()
    if lower in VALID_CATEGORIES:
        return lower
    for key, val in CATEGORY_MAP.items():
        if key in lower:
            return val
    return "other"


def normalize_unit(raw_unit: Optional[str]) -> str:
    if not raw_unit:
        return "each"
    lower = raw_unit.lower().strip()
    if lower in VALID_UNITS:
        return lower
    if any(w in lower for w in ["ea", "each"]):
        return "each"
    if "stem" in lower:
        return "stem"
    if any(w in lower for w in ["bunch", "bundle"]):
        return "bunch"
    if "case" in lower:
        return "case"
    if "box" in lower:
        return "box"
    return "each"


# ─────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────

def parse_price(raw: str) -> Optional[float]:
    """Extract a float from strings like '$29.10' or '29.10'."""
    if not raw:
        return None
    cleaned = str(raw).replace(",", "").replace("$", "").strip()
    m = re.search(r"\d+\.?\d*", cleaned)
    return float(m.group()) if m else None


def safe_int(raw: Any) -> Optional[int]:
    try:
        return int(str(raw).strip())
    except (ValueError, AttributeError, TypeError):
        return None


def parse_dimension(raw: str) -> Optional[float]:
    """Parse a dimension like '18\"' or '18 in' or '18.5\"' to float inches."""
    if not raw:
        return None
    m = re.search(r"([\d.]+)", str(raw))
    return float(m.group(1)) if m else None


def parse_availability(raw: str) -> tuple[str, Optional[str]]:
    """Return (availability_status, note) from a raw availability string."""
    if not raw or raw.strip() == "":
        return ("unknown", None)
    lower = raw.lower().strip()
    if any(w in lower for w in ["in stock", "available", "yes"]):
        return ("in_stock", raw)
    if any(w in lower for w in ["out of stock", "unavailable", "no"]):
        return ("out_of_stock", raw)
    if "eta" in lower or "expected" in lower:
        return ("eta", raw)
    if re.match(r"^\d+$", raw.strip()):
        qty = int(raw.strip())
        if qty > 0:
            return ("in_stock", f"{qty} in stock")
        return ("out_of_stock", "0 in stock")
    return ("unknown", raw)


# ─────────────────────────────────────────────
# Retry logic
# ─────────────────────────────────────────────

async def with_retry(
    fn: Callable,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    label: str = "",
) -> Any:
    """Run an async callable with exponential backoff retry."""
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                print(f"[retry] {label} attempt {attempt}/{max_attempts} failed: {exc}. Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                print(f"[retry] {label} all {max_attempts} attempts failed: {exc}")
    raise last_exc


async def polite_delay(seconds: float = 1.5):
    """Polite pause between requests."""
    await asyncio.sleep(seconds)


# ─────────────────────────────────────────────
# Image storage helpers
# ─────────────────────────────────────────────

IMAGE_KEY_PREFIX = "product-img-"


def _storage_key(supplier_sku: str) -> str:
    """Return a safe storage key for a product image."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "-", supplier_sku)
    return f"{IMAGE_KEY_PREFIX}{safe}"


def _internal_image_url(storage_key: str) -> str:
    """Return the internal proxy URL for a stored image."""
    return f"/api/products/image-proxy?key={storage_key}"


def download_and_store_image(
    url: str,
    supplier_sku: str,
    session_headers: Optional[dict] = None,
    timeout: int = 15,
) -> Optional[str]:
    """Download an image from url and store it in Databutton storage.

    Args:
        url: The image URL to download.
        supplier_sku: Used to generate a stable storage key.
        session_headers: Optional headers (e.g. cookies) for authenticated requests.
        timeout: Request timeout in seconds.

    Returns:
        Internal proxy URL if stored successfully, None on failure.
    """
    if not url:
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        ),
    }
    if session_headers:
        headers.update(session_headers)

    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            print(f"[img] download failed {resp.status_code}: {url[:80]}")
            return None
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type and "octet" not in content_type:
            print(f"[img] unexpected content-type '{content_type}': {url[:80]}")
            return None
        data = resp.content
        if len(data) < 500:  # suspiciously small — probably an error page
            print(f"[img] too small ({len(data)} bytes), skipping: {url[:80]}")
            return None

        key = _storage_key(supplier_sku)
        db.storage.binary.put(key, data)
        return _internal_image_url(key)
    except Exception as e:
        print(f"[img] error downloading {url[:80]}: {e}")
        return None


def delete_supplier_images(supplier_sku_list: list[str]) -> int:
    """Delete all stored images for the given SKUs. Returns number deleted."""
    deleted = 0
    for sku in supplier_sku_list:
        key = _storage_key(sku)
        try:
            existing = db.storage.binary.list()
            if any(f.name == key for f in existing):
                db.storage.binary.delete(key)
                deleted += 1
        except Exception as e:
            print(f"[img] could not delete {key}: {e}")
    return deleted


def delete_all_supplier_images_by_prefix(supplier_id: int) -> int:
    """List all product-img-* keys and delete ones matching stored SKUs for a supplier.
    Call before re-importing to keep storage lean. Returns number deleted."""
    deleted = 0
    try:
        files = db.storage.binary.list()
        for f in files:
            if f.name.startswith(IMAGE_KEY_PREFIX):
                try:
                    db.storage.binary.delete(f.name)
                    deleted += 1
                except Exception as e:
                    print(f"[img] could not delete {f.name}: {e}")
    except Exception as e:
        print(f"[img] error listing storage: {e}")
    return deleted


# ─────────────────────────────────────────────
# Sync log management
# ─────────────────────────────────────────────

async def create_sync_log(
    supplier_id: int,
    scrape_job_id: Optional[int] = None,
    sync_type: str = "full",
) -> int:
    """Insert a new sync log row and return its id."""
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        row = await conn.fetchrow("""
            INSERT INTO scrape_sync_logs
                (supplier_id, scrape_job_id, sync_type, status, started_at)
            VALUES ($1, $2, $3, 'running', now())
            RETURNING id
        """, supplier_id, scrape_job_id, sync_type)
        return row["id"]
    finally:
        await conn.close()


async def update_sync_log(log_id: int, **kwargs):
    """Patch arbitrary columns on a sync log row."""
    if not kwargs:
        return
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
        vals = [log_id] + list(kwargs.values())
        await conn.execute(f"UPDATE scrape_sync_logs SET {sets} WHERE id = $1", *vals)
    finally:
        await conn.close()


async def finish_sync_log(
    log_id: int,
    status: str,
    inserted: int = 0,
    updated: int = 0,
    skipped: int = 0,
    failed: int = 0,
    price_changes: int = 0,
    error_message: Optional[str] = None,
):
    """Mark a sync log as completed with final stats."""
    await update_sync_log(
        log_id,
        status=status,
        completed_at=datetime.utcnow(),
        products_inserted=inserted,
        products_updated=updated,
        products_skipped=skipped,
        products_failed=failed,
        price_changes=price_changes,
        error_message=error_message,
    )


# ─────────────────────────────────────────────
# Product upsert (shared import logic)
# ─────────────────────────────────────────────

async def upsert_product(
    conn: asyncpg.Connection,
    supplier_id: int,
    product: ScrapedProduct,
) -> tuple[str, bool]:
    """Insert or update a product from a ScrapedProduct.
    
    Returns:
        (action, price_changed): action is 'inserted' | 'updated' | 'skipped'
    """
    if not product.sku or not product.name:
        return ("skipped", False)

    category = normalize_category(product.category)
    unit = normalize_unit(product.uom)
    avail_status, avail_note = parse_availability(str(product.availability or ""))
    image_urls = list(product.image_urls) if product.image_urls else []
    if product.photo_url and product.photo_url not in image_urls:
        image_urls.insert(0, product.photo_url)
    photo_url = image_urls[0] if image_urls else None

    # Check for existing record
    existing = await conn.fetchrow("""
        SELECT id, current_price FROM products
        WHERE supplier_id = $1 AND supplier_sku = $2
    """, supplier_id, product.sku)

    price_changed = False

    if existing:
        old_price = existing["current_price"]
        new_price = product.base_price
        price_changed = new_price is not None and old_price != new_price

        await conn.execute("""
            UPDATE products SET
                name = $3,
                description = COALESCE($4, description),
                category = $5,
                unit = $6,
                current_price = COALESCE($7, current_price),
                price_updated_at = CASE WHEN $7 IS NOT NULL THEN now() ELSE price_updated_at END,
                last_price_change_at = CASE WHEN $8 THEN now() ELSE last_price_change_at END,
                photo_url = COALESCE($9, photo_url),
                image_urls = CASE WHEN array_length($10::text[], 1) > 0 THEN $10::text[] ELSE image_urls END,
                height_in = COALESCE($11, height_in),
                width_in = COALESCE($12, width_in),
                diameter_in = COALESCE($13, diameter_in),
                length_in = COALESCE($14, length_in),
                weight_lb = COALESCE($15, weight_lb),
                material = COALESCE($16, material),
                finish = COALESCE($17, finish),
                color = COALESCE($18, color),
                style = COALESCE($19, style),
                moq = COALESCE($20, moq),
                case_qty = COALESCE($21, case_qty),
                uom = COALESCE($22, uom),
                availability = $23,
                availability_note = $24,
                currency = $25,
                country_of_origin = COALESCE($26, country_of_origin),
                last_scraped_at = now(),
                updated_at = now(),
                raw_data = $27
            WHERE supplier_id = $1 AND supplier_sku = $2
        """,
            supplier_id, product.sku,
            product.name, product.description, category, unit,
            new_price, price_changed,
            photo_url, image_urls,
            product.height_in, product.width_in, product.diameter_in,
            product.length_in, product.weight_lb,
            product.material, product.finish, product.color, product.style,
            product.moq, product.case_qty, unit,
            avail_status, avail_note, product.currency,
            product.country_of_origin, product.raw,
        )

        if price_changed:
            await conn.execute("""
                INSERT INTO product_price_history
                    (product_id, old_price, new_price, source, changed_at)
                VALUES ($1, $2, $3, 'scrape', now())
            """, existing["id"], old_price, new_price)

        return ("updated", price_changed)

    else:
        await conn.execute("""
            INSERT INTO products (
                supplier_id, supplier_sku, name, description,
                category, unit, current_price, price_updated_at,
                photo_url, image_urls,
                height_in, width_in, diameter_in, length_in, weight_lb,
                material, finish, color, style,
                moq, case_qty, uom, availability, availability_note,
                currency, country_of_origin, last_scraped_at,
                raw_data, is_active
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, CASE WHEN $7 IS NOT NULL THEN now() END,
                $8, $9::text[],
                $10, $11, $12, $13, $14,
                $15, $16, $17, $18,
                $19, $20, $21, $22, $23, $24, $25,
                now(), $26, true
            )
        """,
            supplier_id, product.sku, product.name, product.description,
            category, unit, product.base_price,
            photo_url, image_urls,
            product.height_in, product.width_in, product.diameter_in,
            product.length_in, product.weight_lb,
            product.material, product.finish, product.color, product.style,
            product.moq, product.case_qty, unit,
            avail_status, avail_note, product.currency,
            product.country_of_origin, product.raw,
        )
        return ("inserted", False)


# ─────────────────────────────────────────────
# Category index cache helpers
# ─────────────────────────────────────────────

from datetime import timedelta

CATEGORY_INDEX_FRESH_DAYS = 7   # index is "fresh" if verified within this many days


async def load_category_index(
    supplier_id: int,
    scraper_key: str,
    max_age_days: int = CATEGORY_INDEX_FRESH_DAYS,
) -> Optional[list[dict]]:
    """Return cached categories for a supplier if the index exists and is fresh.

    Each entry is a dict with keys:
        category_name, category_slug_or_url, product_count, last_verified_at

    Returns None if the index is empty or all rows are stale (triggers full discovery).
    """
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        rows = await conn.fetch("""
            SELECT category_name, category_slug_or_url, product_count, last_verified_at
            FROM supplier_category_index
            WHERE supplier_id = $1
              AND scraper_key  = $2
              AND is_active    = true
            ORDER BY category_name
        """, supplier_id, scraper_key)

        if not rows:
            print(f"[cat-index] No index found for {scraper_key} supplier_id={supplier_id}")
            return None

        # Treat the index as stale if ANY row hasn't been verified recently.
        # Older migrations may have rows with NULL last_verified_at; force a
        # rediscovery instead of crashing while trying to use the cache.
        verified_at = [r["last_verified_at"] for r in rows if r["last_verified_at"]]
        if len(verified_at) != len(rows):
            print(f"[cat-index] Index has unverified rows — will re-discover")
            return None
        oldest = min(dt.replace(tzinfo=None) for dt in verified_at)
        if oldest < cutoff:
            age_days = (datetime.utcnow() - oldest).days
            print(f"[cat-index] Index stale ({age_days}d old, max={max_age_days}d) — will re-discover")
            return None

        result = [
            {
                "category_name": r["category_name"],
                "category_slug_or_url": r["category_slug_or_url"],
                "product_count": r["product_count"],
                "last_verified_at": r["last_verified_at"].isoformat(),
            }
            for r in rows
        ]
        print(f"[cat-index] Loaded {len(result)} cached categories for {scraper_key}")
        return result
    finally:
        await conn.close()


async def save_category_index(
    supplier_id: int,
    scraper_key: str,
    categories: list[dict],
) -> int:
    """Upsert a list of categories into the index. Returns number of rows upserted.

    Each dict must have:
        category_name       str
        category_slug_or_url str
        product_count       int | None

    Marks all supplied slugs as active=true. Does NOT deactivate missing ones
    (call verify_category_index for that).
    """
    if not categories:
        return 0
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        count = 0
        for cat in categories:
            await conn.execute("""
                INSERT INTO supplier_category_index
                    (supplier_id, scraper_key, category_name, category_slug_or_url,
                     product_count, is_active, last_verified_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, true, now(), now())
                ON CONFLICT (supplier_id, category_slug_or_url)
                DO UPDATE SET
                    category_name      = EXCLUDED.category_name,
                    product_count      = COALESCE(EXCLUDED.product_count, supplier_category_index.product_count),
                    is_active          = true,
                    last_verified_at   = now(),
                    updated_at         = now()
            """,
                supplier_id,
                scraper_key,
                cat["category_name"],
                cat["category_slug_or_url"],
                cat.get("product_count"),
            )
            count += 1
        # Stamp supplier.category_index_rebuilt_at
        await conn.execute("""
            UPDATE suppliers SET category_index_rebuilt_at = now() WHERE id = $1
        """, supplier_id)
        print(f"[cat-index] Saved {count} categories for {scraper_key}")
        return count
    finally:
        await conn.close()


async def verify_category_index(
    supplier_id: int,
    scraper_key: str,
    live_slugs: list[str],
) -> dict:
    """Compare live_slugs from a fresh top-level crawl against the stored index.

    - New slugs (in live but not in DB) → inserted as active
    - Removed slugs (in DB but not in live) → marked is_active=false
    - Existing slugs → last_verified_at refreshed

    Returns {"added": int, "removed": int, "refreshed": int}
    """
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        existing_rows = await conn.fetch("""
            SELECT category_slug_or_url, is_active
            FROM supplier_category_index
            WHERE supplier_id = $1 AND scraper_key = $2
        """, supplier_id, scraper_key)
        existing_slugs = {r["category_slug_or_url"] for r in existing_rows}
        live_set = set(live_slugs)

        added = refreshed = removed = 0

        # Refresh or add
        for slug in live_set:
            if slug in existing_slugs:
                await conn.execute("""
                    UPDATE supplier_category_index
                    SET is_active=true, last_verified_at=now(), updated_at=now()
                    WHERE supplier_id=$1 AND scraper_key=$2 AND category_slug_or_url=$3
                """, supplier_id, scraper_key, slug)
                refreshed += 1
            else:
                # New category appeared in catalog — insert with placeholder name
                await conn.execute("""
                    INSERT INTO supplier_category_index
                        (supplier_id, scraper_key, category_name, category_slug_or_url,
                         is_active, last_verified_at, updated_at)
                    VALUES ($1, $2, $3, $4, true, now(), now())
                    ON CONFLICT DO NOTHING
                """, supplier_id, scraper_key, slug, slug)
                added += 1

        # Mark removed
        for slug in existing_slugs - live_set:
            await conn.execute("""
                UPDATE supplier_category_index
                SET is_active=false, updated_at=now()
                WHERE supplier_id=$1 AND scraper_key=$2 AND category_slug_or_url=$3
            """, supplier_id, scraper_key, slug)
            removed += 1

        print(f"[cat-index] verify {scraper_key}: +{added} new, -{removed} removed, ~{refreshed} refreshed")
        return {"added": added, "removed": removed, "refreshed": refreshed}
    finally:
        await conn.close()


async def rebuild_category_index(
    supplier_id: int,
    scraper_key: str,
) -> int:
    """Wipe the category index for this supplier so the next scrape does a full re-discovery.

    Returns number of rows deleted.
    """
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        result = await conn.execute("""
            DELETE FROM supplier_category_index
            WHERE supplier_id = $1 AND scraper_key = $2
        """, supplier_id, scraper_key)
        # Parse 'DELETE N' response
        deleted = int(result.split()[-1]) if result else 0
        # Clear rebuilt timestamp so the next scrape knows it needs full discovery
        await conn.execute("""
            UPDATE suppliers SET category_index_rebuilt_at = NULL WHERE id = $1
        """, supplier_id)
        print(f"[cat-index] Rebuilt (wiped) index for {scraper_key}: {deleted} rows deleted")
        return deleted
    finally:
        await conn.close()


async def get_category_index_summary(
    supplier_id: int,
    scraper_key: str,
) -> list[dict]:
    """Return all index rows for a supplier (active + inactive) for admin display."""
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        rows = await conn.fetch("""
            SELECT
                id,
                category_name,
                category_slug_or_url,
                product_count,
                is_active,
                last_verified_at,
                created_at
            FROM supplier_category_index
            WHERE supplier_id = $1 AND scraper_key = $2
            ORDER BY is_active DESC, category_name
        """, supplier_id, scraper_key)
        return [
            {
                "id": r["id"],
                "category_name": r["category_name"],
                "category_slug_or_url": r["category_slug_or_url"],
                "product_count": r["product_count"],
                "is_active": r["is_active"],
                "last_verified_at": r["last_verified_at"].isoformat() if r["last_verified_at"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    finally:
        await conn.close()


async def load_catalog_filters(
    supplier_id: int,
) -> Optional[set[str]]:
    """Load the user's saved DDCODE allow-list for a supplier.

    Returns:
        - A set of DDCODE strings if selections exist (scraper should filter to these)
        - None if no selections saved, meaning scrape everything (safe default)

    Usage in scrapers::

        allowed = await load_catalog_filters(supplier_id)
        subcategories = [s for s in all_subs if allowed is None or s["ddcode"] in allowed]
    """
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        row = await conn.fetchrow(
            "SELECT categories FROM supplier_catalog_filters WHERE supplier_id = $1",
            supplier_id,
        )
        if not row or not row["categories"]:
            return None  # No filter saved — scrape everything
        raw_categories = row["categories"]
        if isinstance(raw_categories, str):
            try:
                cats = json.loads(raw_categories)
            except Exception:
                cats = []
        else:
            cats = list(raw_categories)
        if not cats:
            return None  # Empty list — still means scrape everything
        return set(cats)
    finally:
        await conn.close()


async def bulk_upsert_products(
    supplier_id: int,
    products: list[ScrapedProduct],
    sync_log_id: Optional[int] = None,
    on_progress: Optional[Callable] = None,
) -> dict:
    """Bulk upsert a list of ScrapedProducts for a supplier.
    
    Returns stats dict: inserted, updated, skipped, failed, price_changes
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0, "price_changes": 0}
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    total = len(products)

    try:
        for i, product in enumerate(products):
            try:
                action, price_changed = await upsert_product(conn, supplier_id, product)
                stats[action] += 1
                if price_changed:
                    stats["price_changes"] += 1
            except Exception as e:
                stats["failed"] += 1
                print(f"[upsert] product #{i} '{product.name}' SKU='{product.sku}' failed: {e}")

            if on_progress and i % 25 == 0:
                await on_progress(i + 1, total, f"Importing {i + 1}/{total}...")
            if sync_log_id and i % 50 == 0:
                await update_sync_log(
                    sync_log_id,
                    products_found=total,
                    products_inserted=stats["inserted"],
                    products_updated=stats["updated"],
                    products_failed=stats["failed"],
                )

        # Update supplier-level stats
        total_active = await conn.fetchval(
            "SELECT COUNT(*) FROM products WHERE supplier_id = $1 AND is_active = true",
            supplier_id
        )
        await conn.execute("""
            UPDATE suppliers
            SET last_full_sync_at = now(),
                total_products_count = $2,
                credential_status = 'ok'
            WHERE id = $1
        """, supplier_id, total_active)

    finally:
        await conn.close()

    print(f"[upsert] Done: {stats}")
    return stats
