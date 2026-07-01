"""Accent Decor full-catalog scraper — production-ready.

Accent Decor (accentdecor.com) is a Magento Cloud wholesale site.
Login requires the activated customer email + password.
Current customers can first activate online access with account number + billing zip.

Flow:
  1. Log in with stored customer email/password
  2. Iterate all category pages to collect product URLs
  3. For each product page: parse name, SKU, price, description,
     dimensions, material, color, all images
  4. Yield ScrapedProduct objects with every available field

Production features:
  - Exponential backoff retry on page loads (3 attempts)
  - Session expiration detection + re-login
  - Polite request delays (configurable)
  - Category-driven pagination (more reliable than search)
  - All image URLs collected, not just first
"""
import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from html import unescape
from typing import AsyncGenerator, Optional, Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup
from app.libs.scraper_base import (
    ScrapedProduct, parse_price, polite_delay,
    parse_dimension, parse_availability, with_retry,
    load_category_index, save_category_index, verify_category_index,
)

BASE_URL = "https://www.accentdecor.com"
LOGIN_URL = "https://www.accentdecor.com/customer/account/login"
ACCOUNT_URL = "https://www.accentdecor.com/customer/account/"
REQUEST_DELAY = 2.0   # Magento has rate limiting
MAX_PRODUCTS = 50000  # safety cap
CDN_BASE_URL = "https://cdn-lg.accentdecor.com"
KLEVU_SEARCH_URL = "https://eucs30v2.ksearchnet.com/cs/v2/search"
KLEVU_API_KEY = "klevu-166375275531315628"
KLEVU_BATCH_SIZE = 100
KLEVU_REQUEST_DELAY = 0.12

# Accent's product-listing UI is driven by Klevu. Querying these top-level
# paths and deduping by product URL gives the real catalog total rather than
# the inflated sum of every overlapping menu category.
KLEVU_TOP_LEVEL_CATEGORIES: list[tuple[str, str, str]] = [
    ("New", "NEW", "new"),
    ("In-Stock", "IN-STOCK", "in-stock"),
    ("Flower + Event", "FLOWER + EVENT", "flower"),
    ("Plant + Garden", "PLANT + GARDEN", "plant"),
    ("Home + Gift", "HOME + GIFT", "home"),
    ("Seasonal", "SEASONAL", "seasonal"),
    ("Eric + Eloise", "ERIC + ELOISE", "eric-eloise"),
    ("Sale", "SALE", "sale"),
]

# Accent Decor catalog taxonomy from the live mega-menu. Keep this explicit:
# it gives the app a stable configuration surface while still crawling real
# Accent category/filter URLs.
CATEGORY_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("New", [
        ("Shop All New", "new"),
        ("Flower + Event", "new/new-flower"),
        ("Plant + Garden", "new/new-plant"),
        ("Home + Gift", "new/new-home"),
        ("Seasonal", "new/seasonal"),
        ("Halloween", "new/seasonal/halloween"),
        (
            "New Vases + Vessels",
            "flower/new?Filters=ad_product_type%3AVASES%252CBUDVASES%252CBOWLS%252CCOMPOTES%252CURNS%252CCENTERPIECE%2520VASES",
        ),
        (
            "New Pots + Planters",
            "plant/new?Filters=ad_product_type%3APOTS%252CPOTS%2520W%252F%2520SAUCER%252CPLANTERS",
        ),
        (
            "New Room Decor",
            "home/new?kdsjhf=&Filters=ad_product_type%3AVASES%252CBOWLS%252CLARGE-SCALE%2520VASES%252CPLANTERS%252CTABLETOP%2520BOWLS%252CDECORATIVE%2520OBJECTS",
        ),
    ]),
    ("In-Stock", [
        ("Shop All In-Stock", "in-stock"),
        ("New In-Stock", "in-stock/in-stock-new"),
        ("Flower", "flower/in-stock"),
        ("Plant", "plant/in-stock"),
        ("Home", "home/in-stock"),
        ("Seasonal", "seasonal/in-stock"),
        ("In Stock Floral Essentials", "flower/floral-essentials?Filters=label_in_stock%3AIN%2520STOCK"),
        ("In Stock Planters & Pots", "plant/planters/planters-pots?Filters=label_in_stock%3AIN%2520STOCK"),
        ("In Stock Room Decor", "home/room-decor?Filters=label_in_stock%3AIN%2520STOCK"),
        ("In Stock Eric + Eloise", "home/eric-eloise?Filters=label_in_stock%3AIN%2520STOCK"),
    ]),
    ("Flower + Event", [
        ("Shop All Flower + Event", "flower"),
        ("New", "flower/new"),
        ("Floral Bestsellers", "flower/floral-bestsellers"),
        ("In Stock", "flower/in-stock"),
        ("Vases & Vessels", "flower/vases-vessels"),
        ("Vases & Vessels / Vases", "flower/vases-vessels/vases"),
        ("Vases & Vessels / Budvases", "flower/vases-vessels/budvases"),
        ("Vases & Vessels / Compotes & Urns", "flower/vases-vessels/compotes-urns"),
        ("Vases & Vessels / Troughs & Boats", "flower/vases-vessels/troughs-boats"),
        ("Vases & Vessels / Bowls", "flower/vases-vessels/bowls"),
        ("Vase Fillers", "flower/vase-fillers"),
        ("Dried & Preserved", "flower/dried-preserved"),
        ("Wedding & Event", "flower/wedding-event"),
        ("Wedding & Event / Structures & Arches", "flower/wedding-event/structures-arches"),
        ("Wedding & Event / Columns & Stands", "flower/wedding-event/columns-stands"),
        ("Wedding & Event / Compotes & Urns", "flower/wedding-event/compotes-urns"),
        ("Wedding & Event / Lanterns & Votives", "flower/wedding-event/lanterns-votives"),
        ("Wedding & Event / Candelabras & Candlesticks", "flower/wedding-event/candelabras-candlesticks"),
        ("Wedding & Event / Event Vases & Vessels", "flower/wedding-event/event-vases-vessels"),
        ("Wedding & Event / Drinkware", "flower/wedding-event/drinkware"),
        ("Floral Essentials", "flower/floral-essentials"),
        ("Sustainable Floristry Vessels", "sustainable-floristry-vessels"),
        ("Glass Centerpiece Vessels", "glass-vessels"),
        ("Trending Now", "trending-flower"),
    ]),
    ("Plant + Garden", [
        ("Shop All Plant + Garden", "plant"),
        ("New", "plant/new"),
        ("Garden Center", "plant/garden-center"),
        ("In Stock", "plant/in-stock"),
        ("Planters", "plant/planters"),
        ("Planters / Planters & Pots", "plant/planters/planters-pots"),
        ("Planters / Bowls", "plant/planters/bowls"),
        ("Planters / Troughs & Boats", "plant/planters/troughs-boats"),
        ("Planters / Terrariums", "plant/planters/terrariums"),
        ("Planters / Baskets", "plant/planters/baskets"),
        ("Planters / Outdoor Planters", "plant/planters/outdoor-planters"),
        ("Plant Accessories", "plant/plant-accessories"),
        ("Plant Accessories / Plant Stands", "plant/plant-accessories/plant-stands"),
        ("Plant Accessories / Plant Accessories", "plant/plant-accessories/plant-accessories"),
        ("Plant Accessories / Watering", "plant/plant-accessories/watering"),
        ("Plant Accessories / Propagation Stands", "plant/plant-accessories/propagation-stands"),
        ("Plant Accessories / Saucers", "plant/plant-accessories/saucers"),
        ("Plant Accessories / Fillers & Potting Stones", "plant/plant-accessories/fillers-potting-stones"),
        ("Core Pot Collection", "plant/core-pots"),
        ("Pots with Drainage", "plant/planters?Filters=drainage_hole%3AYes"),
        (
            "Drop In Pots",
            "plant/planters/planters-pots?Filters=enable_grower_pot_size%3A6%2522%2520Standard%252C4.5%2522%2520Orchid%252C3%2522%252C8%2522%252C10%2522%252C4.5%2522%2520Standard%252C4%2522%252C4%2522%2520Standard%252C3.5%2522%252C2.5%2522",
        ),
        ("Trending Now", "trending-plant"),
    ]),
    ("Home + Gift", [
        ("Shop All Home + Gift", "home"),
        ("New", "home/new"),
        ("Home & Gift Bestsellers", "home/home-gift-bestsellers"),
        ("In Stock", "home/in-stock"),
        ("Room Decor", "home/room-decor"),
        ("Room Decor / Wall Decor", "home/room-decor/wall-decor"),
        ("Room Decor / Decorative Objects", "home/room-decor/decorative-objects"),
        ("Room Decor / Decorative Bowls & Trays", "home/room-decor/decorative-bowls-trays"),
        ("Room Decor / Vases & Vessels", "home/room-decor/vases-vessels"),
        ("Room Decor / Display Stands", "home/room-decor/display-stands"),
        ("Room Decor / Baskets", "home/room-decor/baskets"),
        ("Room Decor / Pillows", "home/room-decor/pillows"),
        ("Room Decor / Mirrors", "home/room-decor/mirrors"),
        ("Eric + Eloise", "home/eric-eloise"),
        ("Accent Tables & Stands", "home/accent-tables-stands"),
        ("Candleholders & Lighting", "home/candleholders-lighting"),
        ("Candleholders & Lighting / Candleholders", "home/candleholders-lighting/candleholders"),
        ("Candleholders & Lighting / Lanterns & Light Shades", "home/candleholders-lighting/lanterns-light-shades"),
        ("Candleholders & Lighting / Candles", "home/candleholders-lighting/candles"),
        ("Tabletop", "home/tabletop"),
        ("Tabletop / Dinnerware", "home/tabletop/dinnerware"),
        ("Tabletop / Drinkware", "home/tabletop/drinkware"),
        ("Tabletop / Serveware & Accessories", "home/tabletop/serveware-accessories"),
        ("Outdoor", "home/outdoor"),
        ("Outdoor / Outdoor Living", "home/outdoor/outdoor-living"),
        ("Outdoor / Outdoor Planters", "home/outdoor/outdoor-planters"),
        ("Gifts Collection", "home/gifts"),
        ("Textures Collection", "textures"),
        ("Trending Now", "trending-home"),
        ("Cast Aluminum Collection", "eric-eloise/cast-aluminum"),
    ]),
    ("Seasonal", [
        ("Shop All Seasonal", "seasonal"),
        ("New", "seasonal/new"),
        ("In-Stock", "seasonal/in-stock"),
        ("Halloween", "seasonal/halloween"),
        ("Fall & Harvest", "seasonal/harvest"),
        ("Christmas", "seasonal/christmas"),
        ("Christmas / Decorative Objects", "seasonal/christmas/decorative-objects"),
        ("Christmas / Ornaments", "seasonal/christmas/ornaments"),
        ("Christmas / Stockings & Stocking Holders", "seasonal/christmas/stockings-stocking-holders"),
        ("Christmas / Wreaths & Garlands", "seasonal/christmas/wreaths-garlands"),
        ("Christmas / Decorative Trees", "seasonal/christmas/decorative-trees"),
        ("Christmas / Deer", "seasonal/christmas/deer-1"),
        ("Christmas / Vases & Pots", "seasonal/christmas/vases-pots"),
        ("Christmas / Tabletop", "seasonal/christmas/tabletop"),
        ("Mother's Day", "seasonal/mother-s-day"),
        ("Spring & Easter", "seasonal/easter"),
        ("Valentine's Day", "seasonal/valentine-s-day"),
        ("Hanukkah", "seasonal/hanukkah"),
        ("Iconic Christmas Collection", "seasonal/christmas/iconic-christmas"),
        ("Vintage Christmas Collection", "seasonal/christmas/vintage-christmas"),
    ]),
    ("Eric + Eloise", [
        ("Shop All Eric + Eloise", "eric-eloise"),
        ("Wall Mounts", "eric-eloise/wall-mounts"),
        ("Room Decor", "eric-eloise/decor"),
        ("Christmas", "eric-eloise/seasonal"),
        ("Meet Eric", "eric-eloise/eric"),
        ("Eric the Hare", "eric-eloise/eric"),
        ("Eloise the Fox", "eric-eloise/eloise"),
        ("Emerson the Pheasant", "eric-eloise/emerson"),
        ("Frankie the Buck", "eric-eloise/frankie"),
        ("Louie the Mouse", "eric-eloise/louie-the-mouse"),
        ("Eugene the Moose", "eric-eloise/eugene-the-moose"),
        ("Margie the Doe", "eric-eloise/margie-the-doe"),
        ("Beatrice the Bear", "eric-eloise/beatrice-the-bear"),
        ("Charlie the Duck", "eric-eloise/charlie-the-duck"),
        ("Our Story", "eric-eloise/our-story"),
    ]),
    ("Sale", [
        ("Shop All Sale", "sale"),
        ("New To Sale", "sale/new-to-sale"),
        ("Flower Sale", "sale/flower"),
        ("Flower Sale / Vases & Vessels", "sale/flower/vases-vessels"),
        ("Flower Sale / Dried & Preserved", "sale/flower/dried-preserved"),
        ("Flower Sale / Wedding & Event", "sale/flower/wedding-event"),
        ("Plant Sale", "sale/plant"),
        ("Plant Sale / Planters", "sale/plant/planters"),
        ("Plant Sale / Plant Accessories", "sale/plant/plant-accessories"),
        ("Home Sale", "sale/home"),
        ("Home Sale / Room Decor", "sale/home/room-decor"),
        ("Home Sale / Tabletop", "sale/home/tabletop"),
        ("Home Sale / Accent Tables & Stands", "sale/home/accent-tables-stands"),
        ("Home Sale / Candleholders & Lighting", "sale/home/candleholders-lighting"),
        ("Home Sale / Outdoor", "sale/home/outdoor"),
        ("Seasonal Sale", "sale/seasonal"),
        ("Seasonal Sale / Christmas", "sale/seasonal/christmas"),
        ("Seasonal Sale / Fall & Harvest", "sale/seasonal/harvest"),
        ("Seasonal Sale / Halloween", "sale/seasonal/halloween"),
        ("Seasonal Sale / Valentine's Day", "sale/seasonal/valentine-s-day"),
        ("Seasonal Sale / Spring & Easter", "sale/seasonal/easter"),
        ("Seasonal Sale / Mother's Day", "sale/seasonal/mother-s-day"),
        ("Seasonal Sale / Spring Celebrations", "sale/seasonal/spring-celebrations"),
        ("Product Under $10", "sale/under-10"),
    ]),
]


def _category_slug_from_url(value: str) -> str:
    """Convert an Accent URL or path into the stored category code."""
    href = unescape((value or "").strip())
    if href.startswith(BASE_URL):
        href = href[len(BASE_URL):]
    if href.startswith("/"):
        href = href[1:]
    return href


def _category_url(slug_or_url: str) -> str:
    """Turn a stored category code back into a crawlable Accent URL."""
    value = unescape((slug_or_url or "").strip())
    if not value:
        return BASE_URL
    if value.startswith("javascript:") or value.startswith("#"):
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return urljoin(BASE_URL + "/", value.lstrip("/"))


def _catalog_categories() -> list[dict]:
    """Flatten the curated menu taxonomy into scraper category records."""
    categories: list[dict] = []
    seen: set[str] = set()
    for section, entries in CATEGORY_SECTIONS:
        for label, href in entries:
            slug = _category_slug_from_url(href)
            if not slug or slug in seen:
                continue
            seen.add(slug)
            categories.append({
                "section": section,
                "label": label,
                "slug": slug,
                "ddcode": slug,
            })
    return categories


# Backwards-compatible list for code/tests that still need the raw crawl codes.
CATEGORY_SLUGS = [cat["slug"] for cat in _catalog_categories()]


def _normalize_klevu_product_url(url: str) -> str:
    """Normalize a Klevu product URL for deduping across catalog sections."""
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        parsed = urlparse(urljoin(BASE_URL + "/", value.lstrip("/")))
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))


def _clean_klevu_sku(value: str) -> str:
    """Klevu group records expose values like `kendallpot;;;;97521.01`."""
    text = (value or "").strip()
    if ";;;;" in text:
        text = text.split(";;;;", 1)[0]
    return text.strip()


def _coerce_klevu_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _add_unique_url(urls: list[str], value: str) -> None:
    url = (value or "").strip()
    if not url:
        return
    if url.startswith("//"):
        url = f"https:{url}"
    elif url.startswith("/"):
        url = urljoin(BASE_URL, url)
    if url.startswith("http") and url not in urls:
        urls.append(url)


def _selected_klevu_sections(subcategories: Optional[list]) -> list[tuple[str, str, str]]:
    """Map selected Accent categories to top-level Klevu paths.

    When all categories are selected this returns all top-level sections. For
    smaller selections it keeps any top-level section represented by the chosen
    slugs. If the selection is too narrow to map confidently, callers can fall
    back to the page crawler.
    """
    if not subcategories:
        return KLEVU_TOP_LEVEL_CATEGORIES

    selected_slugs = {
        str(s.get("slug") or s.get("ddcode") or s.get("category_slug_or_url") or "").strip()
        for s in subcategories
        if isinstance(s, dict)
    }
    selected_slugs.discard("")
    if not selected_slugs:
        return KLEVU_TOP_LEVEL_CATEGORIES

    # A full Accent discovery has 100+ category rows. That means the user has
    # not made a narrow section choice, so import across every top-level Klevu
    # path and dedupe products globally.
    if len(selected_slugs) > 20:
        return KLEVU_TOP_LEVEL_CATEGORIES

    sections: list[tuple[str, str, str]] = []
    for section_name, category_path, top_slug in KLEVU_TOP_LEVEL_CATEGORIES:
        if any(slug == top_slug or slug.startswith(f"{top_slug}/") for slug in selected_slugs):
            sections.append((section_name, category_path, top_slug))

    return sections


def _klevu_search(category_path: str, *, offset: int = 0, limit: int = KLEVU_BATCH_SIZE) -> dict:
    payload = {
        "context": {"apiKeys": [KLEVU_API_KEY]},
        "recordQueries": [
            {
                "id": "productList",
                "typeOfRequest": "CATNAV",
                "settings": {
                    "query": {"term": "*", "categoryPath": category_path},
                    "typeOfRecords": ["KLEVU_PRODUCT"],
                    "limit": str(limit),
                    "offset": str(offset),
                },
                "filters": {
                    "filtersToReturn": {
                        "enabled": True,
                        "options": {"limit": 20},
                        "rangeFilterSettings": [{"key": "klevu_price", "minMax": "true"}],
                    }
                },
            }
        ],
    }
    req = urllib.request.Request(
        KLEVU_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _klevu_query_result(data: dict) -> dict:
    query_results = data.get("queryResults") if isinstance(data, dict) else None
    if isinstance(query_results, list) and query_results:
        result = query_results[0]
        return result if isinstance(result, dict) else {}
    return {}


def _klevu_total(result: dict) -> int:
    meta = result.get("meta") if isinstance(result, dict) else None
    candidates = [
        result.get("totalResultsFound") if isinstance(result, dict) else None,
        meta.get("totalResultsFound") if isinstance(meta, dict) else None,
        meta.get("totalResults") if isinstance(meta, dict) else None,
    ]
    for value in candidates:
        try:
            return int(value)
        except Exception:
            continue
    return 0


def _collect_klevu_product_records(
    max_products: Optional[int] = None,
    sections: Optional[list[tuple[str, str, str]]] = None,
) -> tuple[list[dict], list[dict]]:
    """Return unique Accent product records from Klevu plus section stats."""
    chosen_sections = sections or KLEVU_TOP_LEVEL_CATEGORIES
    cap = min(max_products or MAX_PRODUCTS, MAX_PRODUCTS)
    records: list[dict] = []
    stats: list[dict] = []
    seen: set[str] = set()

    for section_name, category_path, top_slug in chosen_sections:
        if len(records) >= cap:
            break
        offset = 0
        listed_total = 0
        pages_checked = 0
        section_unique = 0

        while len(records) < cap:
            data = _klevu_search(category_path, offset=offset, limit=KLEVU_BATCH_SIZE)
            result = _klevu_query_result(data)
            page_records = result.get("records") if isinstance(result, dict) else []
            if not isinstance(page_records, list):
                page_records = []
            if pages_checked == 0:
                listed_total = _klevu_total(result) or len(page_records)
            pages_checked += 1

            if not page_records:
                break

            for record in page_records:
                if not isinstance(record, dict):
                    continue
                key = (
                    _normalize_klevu_product_url(str(record.get("url") or ""))
                    or str(record.get("itemGroupId") or record.get("id") or "").strip()
                )
                if not key or key in seen:
                    continue
                seen.add(key)
                enriched = dict(record)
                enriched["_accent_first_section"] = section_name
                enriched["_accent_section_slug"] = top_slug
                records.append(enriched)
                section_unique += 1
                if len(records) >= cap:
                    break

            previous_offset = offset
            offset += len(page_records)
            if offset <= previous_offset or offset >= listed_total:
                break
            time.sleep(KLEVU_REQUEST_DELAY)

        stats.append({
            "name": section_name,
            "slug": top_slug,
            "category_path": category_path,
            "listed_total": listed_total,
            "pages_checked": pages_checked,
            "unique_in_section": section_unique,
            "running_unique_total": len(records),
        })

    return records, stats


def _klevu_catalog_summary(records: list[dict], stats: list[dict]) -> dict:
    """Summarize Accent's live catalog counts without mixing overlap with unique products."""
    section_listing_total = sum(int(s.get("listed_total") or 0) for s in stats)
    return {
        "unique_total": len(records),
        "section_listing_total": section_listing_total,
        "sections": stats,
        "method": (
            "Klevu CATNAV top-level sections: read live totalResultsFound for "
            "section totals, then page records and dedupe by normalized product URL."
        ),
    }


def _discover_klevu_catalog_summary(
    max_products: Optional[int] = None,
    sections: Optional[list[tuple[str, str, str]]] = None,
) -> dict:
    records, stats = _collect_klevu_product_records(max_products=max_products, sections=sections)
    return _klevu_catalog_summary(records, stats)


def count_unique_accent_decor_products() -> dict:
    """Count unique Accent Decor product pages through the public Klevu catalog."""
    return _discover_klevu_catalog_summary()


def _klevu_record_category(record: dict) -> Optional[str]:
    product_type = str(record.get("ad_product_type") or "").strip()
    if product_type:
        return product_type.replace("_", " ").title()

    category = str(record.get("category") or "").strip()
    if category:
        parts = [part.strip() for part in category.split(";;") if part.strip()]
        for part in reversed(parts):
            if part.lower() not in {"shop all", "view all", "new products", "tariff impacted products"}:
                return part.title()

    klevu_category = str(record.get("klevu_category") or "").strip()
    if klevu_category:
        cleaned = klevu_category.split("@ku@kuCategory@ku@", 1)[0]
        parts = [part.strip() for part in cleaned.split(";;") if part.strip()]
        for part in reversed(parts):
            if part.upper() not in {"KLEVU_PRODUCT", "SHOP ALL", "VIEW ALL"}:
                return part.title()
    return record.get("_accent_first_section")


def _scraped_product_from_klevu_record(record: dict) -> ScrapedProduct:
    url = _normalize_klevu_product_url(str(record.get("url") or ""))
    sku = _clean_klevu_sku(str(record.get("sku") or "")) or str(record.get("itemGroupId") or record.get("id") or "").strip()
    name = str(record.get("name") or sku or "Unknown").strip()
    price = (
        _coerce_klevu_float(record.get("basePrice"))
        or _coerce_klevu_float(record.get("startPrice"))
        or _coerce_klevu_float(record.get("salePrice"))
        or _coerce_klevu_float(record.get("price"))
    )

    image_urls: list[str] = []
    for key in ("image", "imageUrl", "imageHover"):
        _add_unique_url(image_urls, str(record.get(key) or ""))

    availability_raw = (
        record.get("label_in_stock")
        or record.get("is_in_norcross_stock")
        or record.get("is_in_perris_stock")
        or ("In Stock" if str(record.get("inStock") or "").lower() == "yes" else "")
    )
    availability, availability_note = parse_availability(str(availability_raw or ""))
    if not availability_note and availability_raw:
        availability_note = str(availability_raw)

    raw = dict(record)
    raw["sku"] = sku
    raw["name"] = name
    raw["detail_url"] = url
    raw["source_url"] = url
    raw["source"] = "klevu_catalog"
    raw["detail_status"] = "stored"
    raw["image_status"] = "pending" if image_urls else "missing"
    raw["Category"] = _klevu_record_category(record) or record.get("_accent_first_section")
    raw["Unit of Measure"] = "Each"
    if image_urls:
        raw["source_photo_url"] = image_urls[0]
        raw["image_urls"] = image_urls
    if price is not None:
        raw["price"] = str(price)
    if availability_raw:
        raw["Availability"] = str(availability_raw)

    return ScrapedProduct(
        sku=sku,
        name=name,
        base_price=price,
        uom="Each",
        category=raw.get("Category"),
        description=str(record.get("shortDesc") or "").strip() or None,
        photo_url=image_urls[0] if image_urls else None,
        image_urls=image_urls,
        material=str(record.get("material") or "").strip() or None,
        color=str(record.get("color_chip") or record.get("color_scheme") or "").strip() or None,
        weight_lb=_coerce_klevu_float(record.get("weight")),
        availability=availability,
        availability_note=availability_note,
        supplier_product_id=str(record.get("itemGroupId") or record.get("id") or "").strip() or None,
        raw=raw,
    )


def _is_login_page(html: str) -> bool:
    """Detect redirect to login."""
    lower = html.lower()
    if _is_account_dashboard(html):
        return False
    return (
        (
            'id="email"' in lower
            and ("forgot password" in lower or 'id="pass"' in lower or "login[password]" in lower)
        )
        or (
            "sign in to accent decor" in lower
            and ("email address" in lower or "forgot password" in lower)
        )
        or (
            "customer login" in lower
            and ("email" in lower and "password" in lower)
        )
        or "please sign in" in lower
        or ("account number" in lower and "billing zip" in lower)
    )


def _is_account_dashboard(html: str) -> bool:
    """Detect authenticated Accent account pages."""
    lower = html.lower()
    return (
        "my account" in lower
        and (
            "account information" in lower
            or "account number:" in lower
            or "change password" in lower
            or "account info" in lower
        )
    )


def _is_email_login(username: str) -> bool:
    """Accent activated accounts log in with email/password."""
    return "@" in (username or "")


def _credential_label(username: str) -> str:
    return "email/password" if _is_email_login(username) else "account number/billing zip"


async def _fill_first_visible(page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        try:
            elements = await page.query_selector_all(selector)
        except Exception:
            continue
        for el in elements:
            try:
                if await el.is_visible() and await el.is_enabled():
                    await el.fill(value)
                    return True
            except Exception:
                continue
    return False


async def _click_first_visible(page, selectors: list[str]) -> bool:
    for selector in selectors:
        try:
            elements = await page.query_selector_all(selector)
        except Exception:
            continue
        for el in elements:
            try:
                if await el.is_visible() and await el.is_enabled():
                    await el.click()
                    return True
            except Exception:
                continue
    return False


async def _wait_for_login_navigation(page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass


async def _press_enter(page) -> bool:
    try:
        await page.keyboard.press("Enter")
        return True
    except Exception:
        return False


async def _confirm_logged_in(page) -> bool:
    """Load the account dashboard, which redirects to login when auth failed."""
    for _ in range(4):
        await _wait_for_login_navigation(page)
        try:
            await page.goto(ACCOUNT_URL, wait_until="domcontentloaded", timeout=30000)
            await _wait_for_login_navigation(page)
        except Exception:
            await asyncio.sleep(1)
            continue
        html = await page.content()
        if not _is_login_page(html):
            return True
        await asyncio.sleep(1)
    return False


async def _try_customer_login_page(page, username: str, password: str) -> bool:
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    username_filled = await _fill_first_visible(page, [
        "input[name='login[username]']",
        "input[id='email']",
        "input[name='email']",
        "input[type='email']",
        "input[placeholder*='Email']",
    ], username)
    if not username_filled:
        print("[accent_decor] Direct Customer Login page did not show a visible email field.")
        return False

    password_filled = await _fill_first_visible(page, [
        "input[name='login[password]']",
        "input[id='pass']",
        "input[type='password']",
    ], password)
    if not password_filled:
        print("[accent_decor] Direct Customer Login page did not show a visible password field.")
        return False

    clicked = await _click_first_visible(page, [
        ".action.login",
        "button.action.login",
        "button:has-text('Sign In')",
        "button:has-text('SIGN IN')",
        "input[value='Sign In']",
        "input[value='SIGN IN']",
        "input[type='submit']",
        "button[type='submit']",
    ])
    if not clicked:
        print("[accent_decor] Direct Customer Login page did not show a visible submit button; pressing Enter.")
        clicked = await _press_enter(page)
    if not clicked:
        return False
    logged_in = await _confirm_logged_in(page)
    if not logged_in:
        print("[accent_decor] Direct Customer Login did not confirm account dashboard access.")
    return logged_in


async def _try_homepage_drawer_login(page, username: str, password: str) -> bool:
    """Fallback for Accent's home-page sign-in drawer."""
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    trigger_clicked = await _click_first_visible(page, [
        "a:has-text('SIGN IN | REGISTER')",
        "button:has-text('SIGN IN | REGISTER')",
        "a:has-text('SIGN IN')",
        "button:has-text('SIGN IN')",
        "[href*='customer/account/login']",
    ])
    if not trigger_clicked:
        print("[accent_decor] Homepage sign-in drawer trigger was not visible.")
    else:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
    try:
        await page.wait_for_timeout(500)
    except Exception:
        pass

    username_filled = await _fill_first_visible(page, [
        "input[name='login[username]']",
        "input[id='email']",
        "input[name='email']",
        "input[type='email']",
        "input[placeholder*='Email address']",
        "input[placeholder*='Email']",
        "input[aria-label*='Email']",
    ], username)
    if not username_filled:
        print("[accent_decor] Homepage sign-in drawer did not show a visible email field.")
        return False

    password_filled = await _fill_first_visible(page, [
        "input[name='login[password]']",
        "input[id='pass']",
        "input[type='password']",
        "input[placeholder*='Password']",
        "input[aria-label*='Password']",
    ], password)
    if not password_filled:
        print("[accent_decor] Homepage sign-in drawer did not show a visible password field.")
        return False

    clicked = await _click_first_visible(page, [
        "button:has-text('Sign In')",
        "button:has-text('SIGN IN')",
        ".action.login",
        "button.action.login",
        "input[value='Sign In']",
        "input[value='SIGN IN']",
        "input[type='submit']",
        "button[type='submit']",
    ])
    if not clicked:
        print("[accent_decor] Homepage sign-in drawer did not show a visible submit button; pressing Enter.")
        clicked = await _press_enter(page)
    if not clicked:
        return False
    logged_in = await _confirm_logged_in(page)
    if not logged_in:
        print("[accent_decor] Homepage sign-in drawer did not confirm account dashboard access.")
    return logged_in


def _parse_product_listing(html: str) -> list[str]:
    """Extract product detail URLs from a Magento listing page."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    # Primary: Magento product link class
    for a in soup.find_all("a", class_="product-item-link"):
        href = a.get("href", "")
        if href:
            urls.append(href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/"))

    # Current Accent listing cards are rendered by Klevu without .html suffixes.
    for a in soup.select("a.product-name, a.klevuProductClick, a.kuTrackRecentView"):
        href = a.get("href", "")
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        if any(skip in href.lower() for skip in ["/customer", "/cart", "/account", "/checkout"]):
            continue
        full = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
        if full.startswith(BASE_URL) and full not in urls:
            urls.append(full)

    # Fallback: .html product links
    if not urls:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if (".html" in href
                    and "/customer" not in href
                    and "/cart" not in href
                    and "/account" not in href
                    and "/checkout" not in href):
                full = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
                if full not in urls:
                    urls.append(full)

    return list(dict.fromkeys(urls))  # deduplicate preserving order


def _parse_listing_count(html: str) -> int:
    """Extract Accent listing totals such as '744 item(s)' or 'Items 1-36 of 744'."""
    soup = BeautifulSoup(html, "html.parser")
    toolbar = soup.find(class_="toolbar-amount") or soup.find(class_="amount")
    texts = []
    if toolbar:
        texts.append(toolbar.get_text(" ", strip=True))
    body_text = soup.get_text(" ", strip=True)
    if body_text:
        texts.append(body_text)

    patterns = [
        r"(\d[\d,]*)\s+item\(s\)",
        r"of\s+(\d[\d,]*)\s+item",
        r"Items?\s+\d[\d,]*\s*-\s*\d[\d,]*\s+of\s+(\d[\d,]*)",
    ]
    for text in texts:
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if m:
                return int(m.group(1).replace(",", ""))

    if toolbar:
        m = re.search(r"(\d[\d,]*)", toolbar.get_text(" ", strip=True))
        if m:
            return int(m.group(1).replace(",", ""))
    return 0


def _page_number_from_url(url: Optional[str]) -> Optional[int]:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    params = parse_qs(parsed.query)
    for key, values in params.items():
        if key.lower() == "page" and values:
            try:
                return int(values[0])
            except Exception:
                return None
    return None


def _url_with_page(url: str, page_number: int) -> str:
    parsed = urlparse(_category_url(url))
    params = parse_qs(parsed.query, keep_blank_values=True)
    page_key = next((key for key in params if key.lower() == "page"), "Page")
    params[page_key] = [str(page_number)]
    query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=query))


def _get_next_page_url(html: str, current_url: Optional[str] = None) -> Optional[str]:
    """Find the next listing page URL, including Accent's '?Page=2' links."""
    soup = BeautifulSoup(html, "html.parser")

    # Magento standard: <link rel="next"> in <head>
    nxt = soup.find("link", rel="next")
    if nxt and nxt.get("href"):
        return _category_url(nxt["href"])

    # Fallback: <a class="next">
    nxt_a = soup.find("a", class_="next")
    if nxt_a and nxt_a.get("href"):
        url = _category_url(nxt_a["href"])
        if url:
            return url

    current_page = _page_number_from_url(current_url) or 1
    page_links: list[tuple[int, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "page=" not in href.lower():
            continue
        url = _category_url(href)
        page_number = _page_number_from_url(url)
        if page_number:
            page_links.append((page_number, url))

    if page_links:
        for page_number, url in sorted(page_links, key=lambda row: row[0]):
            if page_number > current_page:
                return url
        max_page = max(page_number for page_number, _ in page_links)
        if current_url and current_page < max_page:
            return _url_with_page(current_url, current_page + 1)

    return None


def _absolute_accent_url(src: str) -> str:
    """Normalize Accent/CDN image URLs without manufacturing bad hostnames."""
    value = (src or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("cdn-lg.accentdecor.com/"):
        return "https://" + value
    if value.startswith("/media/"):
        return BASE_URL + value
    if value.startswith("media/"):
        return BASE_URL + "/" + value
    return urljoin(BASE_URL + "/", value.lstrip("/"))


def _is_product_image_url(url: str) -> bool:
    """Keep product media, skip navigation, marketing, social, and malformed URLs."""
    lower = (url or "").lower()
    if not lower:
        return False
    if "www.accentdecor.com/cdn-lg.accentdecor.com" in lower:
        return False
    if "/media/catalog/product/" not in lower:
        return False
    return any(ext in lower for ext in [".jpg", ".jpeg", ".png", ".webp"])


def _add_product_image(image_urls: list[str], src: str) -> None:
    full = _absolute_accent_url(src)
    if _is_product_image_url(full) and full not in image_urls:
        image_urls.append(full)


def _json_objects(value) -> list[dict]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        result: list[dict] = []
        for item in value:
            result.extend(_json_objects(item))
        return result
    return []


def _parse_json_script(script_text: str):
    text = (script_text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _find_jsonld_product_and_breadcrumb(soup: BeautifulSoup) -> tuple[dict, Optional[str]]:
    product: dict = {}
    category: Optional[str] = None
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        parsed = _parse_json_script(script.string or script.get_text())
        for obj in _json_objects(parsed):
            obj_type = obj.get("@type")
            if isinstance(obj_type, list):
                types = obj_type
            else:
                types = [obj_type]
            if "Product" in types and not product:
                product = obj
            if "BreadcrumbList" in types:
                names: list[str] = []
                for entry in obj.get("itemListElement", []) or []:
                    item = entry.get("item", {}) if isinstance(entry, dict) else {}
                    name = item.get("name") if isinstance(item, dict) else None
                    if name:
                        names.append(str(name).strip())
                category_names = [n for n in names if n and n.lower() != "home"]
                if category_names:
                    category = category_names[-1]
    return product, category


def _extract_gallery_images(soup: BeautifulSoup) -> list[str]:
    image_urls: list[str] = []
    for script in soup.find_all("script", attrs={"type": "text/x-magento-init"}):
        parsed = _parse_json_script(script.string or script.get_text())
        if not isinstance(parsed, dict):
            continue
        for config in parsed.values():
            if not isinstance(config, dict):
                continue
            gallery = config.get("mage/gallery/gallery")
            if not isinstance(gallery, dict):
                continue
            for row in gallery.get("data", []) or []:
                if not isinstance(row, dict):
                    continue
                _add_product_image(image_urls, row.get("full") or row.get("img") or row.get("thumb") or "")

    gallery = soup.find(attrs={"data-gallery-role": "gallery-placeholder"})
    if gallery:
        for img in gallery.find_all("img"):
            _add_product_image(image_urls, img.get("data-src") or img.get("src") or "")

    og_image = soup.find("meta", property="og:image")
    if og_image:
        _add_product_image(image_urls, og_image.get("content") or "")

    return image_urls


def _offer_value(product_json: dict, key: str):
    offers = product_json.get("offers") if isinstance(product_json, dict) else None
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if isinstance(offers, dict):
        return offers.get(key)
    return None


def _parse_product_detail(html: str, page_url: str) -> Optional[ScrapedProduct]:
    """Parse a single Accent Decor product page into a ScrapedProduct."""
    soup = BeautifulSoup(html, "html.parser")
    raw: dict = {}
    product_json, jsonld_category = _find_jsonld_product_and_breadcrumb(soup)

    # --- Name ---
    name_el = (
        soup.find("h1", class_="page-title")
        or soup.find("h1", itemprop="name")
        or soup.find("h1")
    )
    name = str(product_json.get("name") or "").strip()
    if not name:
        name = name_el.get_text(strip=True) if name_el else ""

    # --- SKU ---
    sku = str(product_json.get("sku") or _offer_value(product_json, "sku") or "").strip()
    # Method 1: itemprop
    sku_el = soup.find(attrs={"itemprop": "sku"})
    if not sku and sku_el:
        sku = sku_el.get_text(strip=True)
    # Method 2: product-info-sku div
    if not sku:
        sku_block = (
            soup.find("div", class_="product-info-sku")
            or soup.select_one(".product.attribute.sku")
            or soup.select_one("[data-product-sku]")
        )
        if sku_block:
            val = sku_block.find(class_="value")
            sku = (val.get_text(strip=True) if val else sku_block.get("data-product-sku") or sku_block.get_text(strip=True))
    # Method 3: text scan for "SKU:"
    if not sku:
        for el in soup.find_all(["div", "span", "td"]):
            text = el.get_text(strip=True)
            if text.startswith(("SKU:", "Item #:", "Item:", "SKU ")):
                sku = text.split(":", 1)[-1].strip()
                if sku:
                    break
    # Method 4: URL slug
    if not sku:
        sku = page_url.rstrip("/").split("/")[-1].replace(".html", "")

    if not name:
        name = sku
    if not name or not sku:
        return None

    # --- Price ---
    price = None
    json_price = _offer_value(product_json, "price")
    if json_price is not None:
        price = parse_price(str(json_price))
    price_el = (
        soup.find("span", class_="price")
        or soup.find(attrs={"itemprop": "price"})
    )
    if price is None and price_el:
        price = parse_price(price_el.get("content") or price_el.get_text(strip=True))

    # --- All product images ---
    image_urls = _extract_gallery_images(soup)
    product_image = product_json.get("image") if isinstance(product_json, dict) else None
    if isinstance(product_image, list):
        for src in product_image:
            _add_product_image(image_urls, str(src))
    elif product_image:
        _add_product_image(image_urls, str(product_image))
    if not image_urls:
        for img in soup.find_all("img"):
            _add_product_image(image_urls, img.get("data-src") or img.get("src") or "")
        for el in soup.find_all(attrs={"data-src": True}):
            _add_product_image(image_urls, el.get("data-src", ""))

    # --- Description ---
    desc_el = (
        soup.find("div", class_="product.attribute.description")
        or soup.find("div", class_="product-info-description")
        or soup.find(attrs={"itemprop": "description"})
    )
    description = str(product_json.get("description") or "").strip() or (desc_el.get_text(" ", strip=True) if desc_el else None)
    if description:
        description = BeautifulSoup(unescape(description), "html.parser").get_text(" ", strip=True)

    # --- Spec table / additional attributes ---
    # Magento renders product specs in a table under #product-attribute-specs-table
    spec_table = soup.find(id="product-attribute-specs-table") or soup.find("table", class_="data")
    if spec_table:
        for row in spec_table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).rstrip(":")
                value = cells[1].get_text(strip=True)
                if label:
                    raw[label] = value

    # Additional info divs
    for div in soup.find_all("div", class_="additional-attributes-wrapper"):
        for row in div.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                raw[cells[0].get_text(strip=True).rstrip(":")] = cells[1].get_text(strip=True)

    raw["name"] = name
    raw["sku"] = sku
    raw["detail_url"] = page_url
    raw["source_url"] = page_url
    raw["detail_status"] = "stored"
    if price:
        raw["price"] = str(price)

    # --- Dimensions ---
    height = parse_dimension(raw.get("Height") or raw.get("H") or "")
    width = parse_dimension(raw.get("Width") or raw.get("W") or "")
    diameter = parse_dimension(raw.get("Diameter") or raw.get("D") or "")
    length = parse_dimension(raw.get("Length") or raw.get("L") or "")

    # --- Category from breadcrumb ---
    category = jsonld_category
    breadcrumb = soup.find("ul", class_="items") or soup.find(class_="breadcrumb")
    if not category and breadcrumb:
        crumbs = [li.get_text(strip=True) for li in breadcrumb.find_all("li")]
        if len(crumbs) >= 2:
            category = crumbs[-2]  # second-to-last is the category
    if category and not raw.get("Category"):
        raw["Category"] = category

    # --- Availability ---
    avail_el = (
        soup.find(class_="stock")
        or soup.find(attrs={"itemprop": "availability"})
    )
    avail_raw = (
        avail_el.get("content")
        or avail_el.get("href")
        or avail_el.get_text(strip=True)
        if avail_el
        else raw.get("Availability", "")
    )
    avail_status, avail_note = parse_availability(avail_raw)
    if avail_raw and not raw.get("Availability"):
        raw["Availability"] = avail_raw
    if image_urls:
        raw["source_photo_url"] = image_urls[0]
        raw["image_urls"] = image_urls
    raw["image_status"] = "pending"

    return ScrapedProduct(
        sku=sku,
        name=name,
        base_price=price,
        description=description,
        category=category or raw.get("Category"),
        uom=raw.get("Unit of Measure") or raw.get("UOM") or raw.get("Unit"),
        photo_url=image_urls[0] if image_urls else None,
        image_urls=image_urls,
        height_in=height,
        width_in=width,
        diameter_in=diameter,
        length_in=length,
        material=raw.get("Material") or raw.get("Materials"),
        finish=raw.get("Finish"),
        color=raw.get("Color") or raw.get("Primary Color"),
        style=raw.get("Style"),
        moq=None,  # Accent Decor doesn't show MOQ publicly
        availability=avail_status,
        availability_note=avail_note,
        country_of_origin=raw.get("Country of Origin") or raw.get("Country"),
        raw=raw,
    )


async def _do_login(page, username: str, password: str) -> None:
    """Perform login with the activated account flow or activation fallback."""
    if _is_email_login(username):
        logged_in = False
        try:
            print("[accent_decor] Trying direct Customer Login page.")
            logged_in = await _try_customer_login_page(page, username, password)
        except Exception as exc:
            print(f"[accent_decor] Direct Customer Login raised {type(exc).__name__}.")
            logged_in = False

        if not logged_in:
            try:
                print("[accent_decor] Trying homepage sign-in drawer.")
                logged_in = await _try_homepage_drawer_login(page, username, password)
            except Exception as exc:
                print(f"[accent_decor] Homepage sign-in drawer raised {type(exc).__name__}.")
                logged_in = False

        if logged_in:
            print("[accent_decor] Logged in successfully.")
            return
        raise ValueError(
            f"Accent Decor login failed — check the {_credential_label(username)} in credentials."
        )

    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    username_filled = await _fill_first_visible(page, [
        "input[name='account_number']",
        "input[name='accountNumber']",
        "input[id*='account']",
        "input[placeholder*='Account Number']",
        "input[aria-label*='Account Number']",
        "input[type='text']",
    ], username)
    if not username_filled:
        raise ValueError("Accent Decor activation form did not show a visible account number field.")

    password_filled = await _fill_first_visible(page, [
        "input[name='billing_zip']",
        "input[name='billingZip']",
        "input[id*='zip']",
        "input[placeholder*='Billing Zip']",
        "input[aria-label*='Billing Zip']",
    ], password)
    if not password_filled:
        raise ValueError("Accent Decor activation form did not show a visible billing zip field.")

    await _click_first_visible(page, [
        "button:has-text('Activate Account')",
        "button:has-text('ACTIVATE ACCOUNT')",
        "button[type='submit']",
    ])
    if not await _confirm_logged_in(page):
        raise ValueError(
            f"Accent Decor login failed — check the {_credential_label(username)} in credentials."
        )
    print("[accent_decor] Logged in successfully.")


async def discover_accent_decor_catalog(
    username: str,
    password: str,
    progress_callback: Optional[Callable] = None,
    supplier_id: Optional[int] = None,
    use_cache: bool = True,
) -> dict:
    """Phase 1: Login, walk all categories, count product URLs.

    If supplier_id is provided and use_cache is true and a category index exists in the DB,
    the full crawl is skipped and cached categories are returned directly.

    Returns:
        {
          "subcategories": [{slug, label, item_count}],
          "total_products": int,
          "from_cache": bool,
        }
    Does NOT yield products — purely a counting/discovery pass.
    """
    from playwright.async_api import async_playwright

    SCRAPER_KEY = "accent_decor"

    # ── Fast mode: check category index cache ─────────────────────────────────
    if supplier_id is not None and use_cache:
        cached = await load_category_index(supplier_id, SCRAPER_KEY)
        if cached:
            from app.libs.scraper_base import load_catalog_filters
            allowed_slugs = await load_catalog_filters(supplier_id)
            result_subcategories = [
                {
                    "slug": row["category_slug_or_url"],
                    "ddcode": row["category_slug_or_url"],
                    "label": (
                        row["category_name"].split(" › ", 1)[1]
                        if " › " in (row["category_name"] or "")
                        else row["category_name"]
                    ),
                    "section": (
                        row["category_name"].split(" › ", 1)[0]
                        if " › " in (row["category_name"] or "")
                        else "General"
                    ),
                    "item_count": row["product_count"] or 50,
                }
                for row in cached
                if allowed_slugs is None or row["category_slug_or_url"] in allowed_slugs
            ]
            category_listing_total = sum(s["item_count"] for s in result_subcategories)
            total_products = category_listing_total
            catalog_summary: dict = {}
            try:
                live_sections = _selected_klevu_sections(result_subcategories)
                catalog_summary = await asyncio.to_thread(
                    _discover_klevu_catalog_summary,
                    None,
                    live_sections,
                )
                if int(catalog_summary.get("unique_total") or 0) > 0:
                    total_products = int(catalog_summary["unique_total"])
            except Exception as exc:
                print(f"[accent-discover] Live Klevu count failed in cache mode; using cached category sum: {exc}")

            print(
                f"[accent-discover] ✅ Fast mode: {len(result_subcategories)} categories from cache; "
                f"{total_products:,} live unique products"
            )
            if progress_callback:
                if catalog_summary:
                    count_message = (
                        f"Using cached category setup; live Accent catalog has "
                        f"{total_products:,} unique products across "
                        f"{int(catalog_summary.get('section_listing_total') or 0):,} section listings."
                    )
                else:
                    count_message = (
                        f"Using cached index — {len(result_subcategories)} categories, "
                        f"~{total_products:,} category listings (live count unavailable)"
                    )
                await progress_callback(
                    len(result_subcategories), len(result_subcategories),
                    count_message,
                    milestone_event="logged_in",
                )
                await progress_callback(
                    len(result_subcategories), len(result_subcategories),
                    f"All {len(result_subcategories)} categories from cache.",
                    milestone_event="categories_done",
                )
            return {
                "subcategories": result_subcategories,
                "total_products": total_products,
                "section_listing_total": int(catalog_summary.get("section_listing_total") or category_listing_total),
                "catalog_summary": catalog_summary,
                "from_cache": True,
            }

    # ── Full discovery crawl ───────────────────────────────────────────────────
    result_subcategories: list[dict] = []
    total_products = 0
    catalog_summary: dict = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            print("[accent-discover] Logging in...")
            await _do_login(page, username, password)

            if progress_callback:
                await progress_callback(
                    0, 1, "Logged in to Accent Decor.",
                    milestone_event="logged_in"
                )

            from app.libs.scraper_base import load_catalog_filters
            allowed_slugs = await load_catalog_filters(supplier_id) if supplier_id is not None else None
            crawl_categories = [
                cat for cat in _catalog_categories()
                if allowed_slugs is None or cat["slug"] in allowed_slugs
            ]

            # Walk each category slug and count product URLs on page 1
            for cat_idx, category in enumerate(crawl_categories):
                slug = category["slug"]
                label = category["label"]
                section = category["section"]
                cat_url = _category_url(slug)
                if not cat_url:
                    continue
                try:
                    await page.goto(cat_url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        pass
                    html = await page.content()
                    if _is_login_page(html):
                        await _do_login(page, username, password)
                        await page.goto(cat_url, wait_until="domcontentloaded", timeout=30000)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=3000)
                        except Exception:
                            pass
                        html = await page.content()

                    # Count products from Accent's toolbar text when available.
                    item_count = _parse_listing_count(html)

                    # Fall back: count product links on first page, multiply by page count
                    if not item_count:
                        links = _parse_product_listing(html)
                        max_pg_url = _get_next_page_url(html, cat_url)
                        # Estimate: if there's a next page we have at least 2x first page
                        item_count = len(links) * (2 if max_pg_url else 1)

                    total_products += item_count
                    result_subcategories.append({
                        "slug": slug,
                        "ddcode": slug,
                        "label": label,
                        "section": section,
                        "item_count": item_count,
                    })
                    print(
                        f"[accent-discover] [{cat_idx+1}/{len(crawl_categories)}] "
                        f"{section} / {label}: ~{item_count} items"
                    )

                    if progress_callback:
                        await progress_callback(
                            cat_idx + 1, len(crawl_categories),
                            f"Counted {label} \u2014 ~{item_count:,} products",
                            milestone_event="category_found",
                            category_info={
                                "name": label,
                                "slug": slug,
                                "section": section,
                                "total": item_count,
                            },
                        )
                    await polite_delay(REQUEST_DELAY)

                except Exception as e:
                    print(f"[accent-discover] Error on {slug}: {e}")

            if progress_callback:
                await progress_callback(
                    len(result_subcategories), len(result_subcategories),
                    f"All {len(result_subcategories)} categories discovered.",
                    milestone_event="categories_done",
                )

        finally:
            await browser.close()

    category_listing_total = total_products
    try:
        live_sections = _selected_klevu_sections(result_subcategories)
        catalog_summary = await asyncio.to_thread(
            _discover_klevu_catalog_summary,
            None,
            live_sections,
        )
        if int(catalog_summary.get("unique_total") or 0) > 0:
            total_products = int(catalog_summary["unique_total"])
            print(
                "[accent-discover] Klevu live summary: "
                f"{total_products:,} unique products across "
                f"{int(catalog_summary.get('section_listing_total') or 0):,} section listings"
            )
    except Exception as exc:
        print(f"[accent-discover] Live Klevu summary failed; using category listing sum: {exc}")

    # ── Persist discovered categories into the index ───────────────────────────
    if supplier_id is not None and result_subcategories:
        index_entries = [
            {
                "category_name": f"{s.get('section') or 'General'} › {s['label']}",
                "category_slug_or_url": s["slug"],
                "product_count": s.get("item_count"),
            }
            for s in result_subcategories
        ]
        await save_category_index(supplier_id, SCRAPER_KEY, index_entries)
        live_slugs = [s["slug"] for s in result_subcategories]
        try:
            verify_result = await verify_category_index(supplier_id, SCRAPER_KEY, live_slugs)
            print(f"[accent-discover] Category index verified: {verify_result}")
        except Exception as ve:
            print(f"[accent-discover] Category index verify failed (non-fatal): {ve}")
        print(f"[accent-discover] Category index saved ({len(index_entries)} rows)")

    print(f"[accent-discover] Done. ~{total_products:,} products across {len(result_subcategories)} categories")
    return {
        "subcategories": result_subcategories,
        "total_products": total_products,
        "section_listing_total": int(catalog_summary.get("section_listing_total") or category_listing_total),
        "catalog_summary": catalog_summary,
        "from_cache": False,
    }


async def scrape_accent_decor(
    username: str,
    password: str,
    max_products: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
    subcategories: Optional[list] = None,
    supplier_id: Optional[int] = None,
) -> AsyncGenerator[ScrapedProduct, None]:
    """Log in to Accent Decor and yield ScrapedProduct objects.

    Args:
        username: Activated Accent customer email
        password: Activated Accent customer password
        max_products: Stop after this many products (None = all)
        progress_callback: async callable(done, total, message, *, category_slug, category_collected)
        subcategories: Pre-discovered category list from discover_accent_decor_catalog
    """
    cap = min(max_products or MAX_PRODUCTS, MAX_PRODUCTS)
    klevu_sections = _selected_klevu_sections(subcategories)
    if klevu_sections:
        try:
            klevu_records, section_stats = await asyncio.to_thread(
                _collect_klevu_product_records,
                cap,
                klevu_sections,
            )
            if klevu_records:
                total = min(len(klevu_records), cap)
                print(
                    "[accent_decor] Klevu catalog collected "
                    f"{total:,} unique products across {len(section_stats)} sections."
                )
                if progress_callback:
                    await progress_callback(
                        0,
                        total,
                        f"Found {total:,} unique Accent Decor products from catalog API. Importing core records...",
                    )

                section_counts: dict[str, int] = {}
                for i, record in enumerate(klevu_records[:total], start=1):
                    section_slug = str(record.get("_accent_section_slug") or "klevu-catalog")
                    section_counts[section_slug] = section_counts.get(section_slug, 0) + 1
                    yield _scraped_product_from_klevu_record(record)

                    if progress_callback and (i == 1 or i % 25 == 0 or i == total):
                        await progress_callback(
                            i,
                            total,
                            f"Prepared {i:,} of {total:,} Accent Decor products",
                            category_slug=section_slug,
                            category_collected=section_counts[section_slug],
                        )
                return
        except Exception as exc:
            print(f"[accent_decor] Klevu catalog import failed; falling back to page crawl: {exc}")

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            print("[accent_decor] Logging in...")
            await _do_login(page, username, password)

            # Collect all product URLs — prefer category-by-category when subcategories pre-known
            product_urls: list[str] = []
            cat_url_ranges: list[dict] = []  # [{slug, start_idx, end_idx}] for milestone tracking

            crawl_slugs = (
                [
                    s.get("slug") or s.get("ddcode") or s.get("category_slug_or_url")
                    for s in subcategories
                    if s.get("slug") or s.get("ddcode") or s.get("category_slug_or_url")
                ]
                if subcategories
                else ["all-products"]
            )

            for slug in crawl_slugs:
                if len(product_urls) >= cap:
                    break
                slug_start = len(product_urls)
                current_url: Optional[str] = _category_url(slug)
                page_num = 0

                while current_url and len(product_urls) < cap:
                    page_num += 1

                    async def fetch_page(u=current_url):
                        await page.goto(u, wait_until="domcontentloaded", timeout=30000)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=3000)
                        except Exception:
                            pass
                        html = await page.content()
                        if _is_login_page(html):
                            print("[accent_decor] Session expired — re-logging in...")
                            await _do_login(page, username, password)
                            await page.goto(u, wait_until="domcontentloaded", timeout=30000)
                            try:
                                await page.wait_for_load_state("networkidle", timeout=3000)
                            except Exception:
                                pass
                        return await page.content()

                    try:
                        html = await with_retry(fetch_page, max_attempts=3, base_delay=3.0,
                                               label=f"accent listing {slug} page {page_num}")
                    except Exception as e:
                        print(f"[accent_decor] Failed to load {current_url}: {e}")
                        break

                    await polite_delay(REQUEST_DELAY)
                    new_links = _parse_product_listing(html)
                    added = 0
                    for link in new_links:
                        if link not in product_urls:
                            product_urls.append(link)
                            added += 1

                    print(f"[accent_decor] {slug} page {page_num}: +{added} (total {len(product_urls)})")
                    if added == 0:
                        break
                    current_url = _get_next_page_url(html, current_url)

                cat_url_ranges.append({"slug": slug, "start": slug_start, "end": len(product_urls)})

            total = min(len(product_urls), cap)
            product_urls = product_urls[:total]
            print(f"[accent_decor] Collected {total} product URLs. Starting detail scrape...")

            if progress_callback:
                await progress_callback(0, total, f"Found {total} products. Scraping details...")

            # Build a slug -> range map for milestone tracking
            slug_range_map = {r["slug"]: (r["start"], r["end"]) for r in cat_url_ranges}

            # Scrape each product detail page with retry
            for i, url in enumerate(product_urls):
                # Determine which category this URL belongs to
                current_slug = "all-products"
                current_cat_collected = 1
                for slug, (start, end) in slug_range_map.items():
                    if start <= i < end:
                        current_slug = slug
                        current_cat_collected = i - start + 1
                        break

                try:
                    async def fetch_detail(u=url):
                        await page.goto(u, wait_until="domcontentloaded", timeout=25000)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=3000)
                        except Exception:
                            pass
                        html = await page.content()
                        if _is_login_page(html):
                            print("[accent_decor] Session expired mid-scrape — re-logging in...")
                            await _do_login(page, username, password)
                            await page.goto(u, wait_until="domcontentloaded", timeout=25000)
                            try:
                                await page.wait_for_load_state("networkidle", timeout=3000)
                            except Exception:
                                pass
                        return await page.content()

                    html = await with_retry(fetch_detail, max_attempts=3, base_delay=2.0,
                                           label=f"accent product {i+1}/{total}")
                    await polite_delay(REQUEST_DELAY)

                    product = _parse_product_detail(html, url)
                    if product:
                        yield product

                    if progress_callback and i % 10 == 0:
                        await progress_callback(
                            i + 1, total,
                            f"Scraped {i + 1} of {total}",
                            category_slug=current_slug,
                            category_collected=current_cat_collected,
                        )

                except Exception as e:
                    print(f"[accent_decor] Error on {url}: {e}")
                    continue

        finally:
            await browser.close()
            print("[accent_decor] Browser closed.")

    # ── Post-scrape: verify index against live category slugs ──────────────────
    if supplier_id is not None and subcategories:
        live_slugs = [s["slug"] for s in subcategories]
        try:
            verify_result = await verify_category_index(supplier_id, "accent_decor", live_slugs)
            print(f"[accent_decor] Category index verified: {verify_result}")
        except Exception as ve:
            print(f"[accent_decor] Category index verify failed (non-fatal): {ve}")
