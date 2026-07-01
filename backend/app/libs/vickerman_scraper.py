"""Vickerman supplier scraper.

Vickerman exposes static navigation plus an HTML product-selector endpoint.
Product details include an embedded JSON model with SKU, descriptions, images,
stock, package data, and account-specific price fields after login.
"""

import json
import re
import time
from html import unescape
from typing import AsyncGenerator, Callable, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.libs.scraper_base import (
    ScrapedProduct,
    load_category_index,
    parse_price,
    polite_delay,
    save_category_index,
    verify_category_index,
)

BASE_URL = "https://www.vickerman.com"
LOGIN_URL = f"{BASE_URL}/Users/Account/LogOn"
SELECTOR_URL = f"{BASE_URL}/April.Vickerman.Commerce/ProductSelector/DoSearch"
SCRAPER_KEY = "vickerman"
REQUEST_DELAY = 0.25
REQUEST_RETRIES = 3
REQUEST_BACKOFF_SECONDS = 1.5
VICKERMAN_PRODUCT_SELECTOR_SEEDS = [
    "/productselector/christmas-trees/alpine-trees",
    "/productselector/christmas-trees/quick-lit",
    "/productselector/everyday/boxwood-trees-topiaries",
    "/productselector/natural-botanicals/all",
    "/productselector/accent-pieces/candle-holders",
    "/productselector/lights/decorative",
    "/productselector/wreaths/berry-wreaths",
    "/productselector/garland/berry-garlands",
    "/productselector/ornament/all-ornaments",
    "/productselector/topiary/topiary",
    "/productselector/sprays/everyday-stems",
    "/productselector/commercial-decor/bows",
    "/productselector/new/all-new",
    "/productselector/textiles/pillows",
    "/productselector/pre-decorated/pre-decorated",
    "/productselector/containers/containers",
    "/productselector/sale-items/all-items",
    "/productselector/categories/all-categories",
    "/productselector/seasons/spring",
    "/productselector/seasons/easter",
]

SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _absolute_url(value: str) -> str:
    href = unescape((value or "").strip())
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    return urljoin(BASE_URL + "/", href)


def _item_number_from_detail_url(detail_url: str) -> str:
    values = parse_qs(urlparse(detail_url or "").query).get("item") or []
    return _clean_text(values[0] if values else "")


def _same_site(url: str) -> bool:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host in ("", "vickerman.com")


def _category_url(value: str) -> str:
    url = _absolute_url(value)
    parsed = urlparse(url)
    if not _same_site(url):
        return ""
    if not parsed.path.lower().startswith("/productselector/"):
        return ""
    return f"{parsed.scheme or 'https'}://{parsed.netloc or 'www.vickerman.com'}{parsed.path}".split("#", 1)[0]


def _category_from_url(url: str, label: str = "") -> dict:
    category_url = _category_url(url)
    label = _clean_text(label) or _label_from_category_url(category_url)
    return {
        "section": _section_from_category_url(category_url),
        "label": label,
        "slug": category_url,
        "ddcode": category_url,
        "item_count": 0,
        "product_type": _product_type_from_category(category_url, label),
    }


def _section_from_category_url(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) >= 2 and parts[0].lower() == "productselector":
        return parts[1].replace("-", " ").title()
    return "General"


def _label_from_category_url(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) >= 3:
        return parts[-1].replace("-", " ").title()
    return _section_from_category_url(url)


def _product_type_from_category(url: str, fallback: str = "") -> str:
    label = fallback or _label_from_category_url(url)
    return _clean_text(label)


def _extract_token(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    token = soup.find("input", {"name": "__RequestVerificationToken"})
    return (token.get("value") if token else "") or ""


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(SESSION_HEADERS)
    return session


def _is_logged_in(html: str) -> bool:
    lower = (html or "").lower()
    return "log out" in lower or "order history" in lower or "account settings" in lower


def _login(session: requests.Session, username: str, password: str) -> str:
    response = session.get(LOGIN_URL, timeout=30)
    response.raise_for_status()
    token = _extract_token(response.text)
    payload = {
        "userNameOrEmail": username,
        "password": password,
        "rememberMe": "false",
    }
    if token:
        payload["__RequestVerificationToken"] = token
    login_response = session.post(LOGIN_URL, data=payload, timeout=30, allow_redirects=True)
    login_response.raise_for_status()
    html = login_response.text
    if not _is_logged_in(html):
        # Some deployments redirect to the home page after successful login.
        home = session.get(BASE_URL, timeout=30)
        home.raise_for_status()
        html = home.text
    if not _is_logged_in(html):
        raise ValueError("Vickerman rejected the saved login credentials.")
    return html


def _discover_category_links(html: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    categories: list[dict] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        url = _category_url(link.get("href") or "")
        if not url or url in seen:
            continue
        label = _clean_text(link.get_text(" ", strip=True)) or _label_from_category_url(url)
        if not label:
            continue
        lowered = url.lower()
        if "/productselector/cancel" in lowered:
            continue
        seen.add(url)
        categories.append(_category_from_url(url, label))
    return categories


def _seed_categories() -> list[dict]:
    seen: set[str] = set()
    categories: list[dict] = []
    for seed in VICKERMAN_PRODUCT_SELECTOR_SEEDS:
        url = _category_url(seed)
        if not url or url in seen:
            continue
        seen.add(url)
        categories.append(_category_from_url(url))
    return categories


def _merge_categories(*groups: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for group in groups:
        for category in group:
            url = category.get("slug") or category.get("ddcode") or ""
            url = _category_url(url)
            if not url or url in seen:
                continue
            seen.add(url)
            category["slug"] = url
            category["ddcode"] = url
            merged.append(category)
    return merged


def _selector_payload(category: dict, page_index: int, token: str = "") -> dict:
    payload = {
        "product_type": category.get("product_type") or category.get("label") or _label_from_category_url(category.get("slug", "")),
        "page_indx": str(page_index),
        "sort": "",
        "search_box": "",
        "availableFilter": "available",
    }
    if token:
        payload["__RequestVerificationToken"] = token
    return payload


def _selector_payload_for_product_type(category: dict, page_index: int, product_type: str, token: str = "") -> dict:
    payload = _selector_payload(category, page_index, token)
    payload["product_type"] = product_type
    return payload


def _fetch_selector_page(
    session: requests.Session,
    category: dict,
    page_index: int,
    token: str = "",
    product_type: str = "",
) -> str:
    headers = {
        "Referer": category.get("slug") or BASE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    payload = (
        _selector_payload_for_product_type(category, page_index, product_type, token)
        if product_type
        else _selector_payload(category, page_index, token)
    )
    response = _request_with_retries(
        session,
        "post",
        SELECTOR_URL,
        data=payload,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def _fetch_category_page(session: requests.Session, category: dict) -> tuple[str, str]:
    response = _request_with_retries(session, "get", category["slug"], timeout=30)
    response.raise_for_status()
    return response.text, _extract_token(response.text)


def _request_with_retries(
    session: requests.Session,
    method: str,
    url: str,
    attempts: int = REQUEST_RETRIES,
    backoff_seconds: float = REQUEST_BACKOFF_SECONDS,
    **kwargs,
) -> requests.Response:
    """Retry transient supplier disconnects without losing the whole batch."""

    last_exc: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            response = getattr(session, method.lower())(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            time.sleep(backoff_seconds * attempt)
    assert last_exc is not None
    raise last_exc


def _count_category_items(session: requests.Session, category: dict, page_html: str = "", token: str = "") -> int:
    if not page_html:
        page_html, token = _fetch_category_page(session, category)
    for product_type in _product_type_candidates(category):
        ajax_html = _fetch_selector_page(session, category, 1, token, product_type)
        ajax_count = _parse_total_items(ajax_html)
        if ajax_count:
            category["product_type"] = product_type
            return ajax_count
    return _parse_total_items(page_html)


def _product_type_candidates(category: dict) -> list[str]:
    candidates = [
        category.get("product_type"),
        category.get("label"),
        _label_from_category_url(category.get("slug") or category.get("ddcode") or ""),
    ]
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = _clean_text(candidate)
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return result


def _append_new_categories(categories: list[dict], candidates: list[dict], seen_urls: set[str]) -> int:
    added = 0
    for candidate in candidates:
        url = _category_url(candidate.get("slug") or candidate.get("ddcode") or "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        candidate["slug"] = url
        candidate["ddcode"] = url
        categories.append(candidate)
        added += 1
    return added


def _seed_url_set() -> set[str]:
    return {_category_url(seed) for seed in VICKERMAN_PRODUCT_SELECTOR_SEEDS if _category_url(seed)}


def _catalog_totals(categories: list[dict]) -> dict:
    seed_urls = _seed_url_set()
    discovered_listing_total = sum(int(category.get("item_count") or 0) for category in categories)
    seed_listing_total = sum(
        int(category.get("item_count") or 0)
        for category in categories
        if _category_url(category.get("slug") or category.get("ddcode") or "") in seed_urls
    )
    return {
        "total_products": seed_listing_total or discovered_listing_total,
        "section_listing_total": discovered_listing_total,
        "catalog_summary": {
            "seed_listing_total": seed_listing_total,
            "seed_category_count": len(seed_urls),
            "discovered_listing_total": discovered_listing_total,
            "discovered_category_count": len(categories),
        },
    }


def _is_rollup_category(category: dict) -> bool:
    section = _clean_text(category.get("section")).lower()
    label = _clean_text(category.get("label") or category.get("product_type")).lower()
    slug = _category_url(category.get("slug") or category.get("ddcode") or "").lower()
    item_count = int(category.get("item_count") or 0)
    if section == "categories":
        return True
    if label in {"all categories", "all items", "new items", "sale items", "seasons / holidays"}:
        return True
    if label.startswith("all "):
        return True
    if slug.endswith("/all") or slug.endswith("/all-categories") or slug.endswith("/all-items"):
        return True
    return item_count >= 1000


def _validation_category_order(categories: list[dict]) -> list[dict]:
    """Prefer specific categories for capped validation scrapes.

    Rollup categories are useful for full coverage and category tag merging, but
    they are expensive early in small proof runs because they contain thousands
    of duplicate listing appearances.
    """

    def sort_key(category: dict) -> tuple:
        item_count = int(category.get("item_count") or 0)
        return (
            _is_rollup_category(category),
            item_count == 0,
            item_count or 999_999,
            _clean_text(category.get("section")),
            _clean_text(category.get("label") or category.get("product_type")),
        )

    return sorted(categories, key=sort_key)


def _parse_total_items(html: str) -> int:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    match = re.search(r"Total items found:\s*([0-9,]+)", text, flags=re.I)
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def _parse_page_count(html: str) -> int:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    match = re.search(r"page\s+\d+\s+of\s+([0-9,]+)", text, flags=re.I)
    if not match:
        return 1
    return max(1, int(match.group(1).replace(",", "")))


def _parse_product_links(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        url = _absolute_url(link.get("href") or "")
        if "/products/details" not in urlparse(url).path.lower():
            continue
        item = (parse_qs(urlparse(url).query).get("item") or [""])[0]
        if not item:
            continue
        normalized = f"{BASE_URL}/products/details?item={item}"
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def _image_url(value: str) -> str:
    value = _clean_text(value)
    if not value:
        return ""
    value = re.sub(r"(?i)(?<!\.)(jpe?g|png|webp)$", r".\1", value)
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://images.vickerman.com/{value.lstrip('/')}"


def _add_silhouette_variant_image_fallbacks(item: dict, image_urls: list[str]) -> None:
    """Add Vickerman's T-variant image fallback for silhouette SKUs with broken primary images."""
    item_number = _clean_text(item.get("ItemNumber"))
    product_type = _clean_text(item.get("ProductType")).lower()
    if not item_number or item_number.endswith("T"):
        return
    if not item_number.startswith("X23S") and "silhouette" not in product_type:
        return
    fallback = _image_url(f"{item_number}T_1000.jpg")
    if fallback and fallback not in image_urls:
        image_urls.append(fallback)


def _extract_model(html: str) -> dict:
    match = re.search(r"var\s+model\s*=\s*(\{.*?\});\s*\r?\n\s*if\s*\(model\.CurrentItem\)", html or "", flags=re.S)
    if not match:
        return {}
    return json.loads(match.group(1))


def _coerce_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        parsed = parse_price(str(value))
        return parsed


def _coerce_positive_float(value) -> Optional[float]:
    parsed = _coerce_float(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _coerce_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _category_tags(category: dict) -> list[str]:
    source_section = _clean_text(category.get("section"))
    source_category = _clean_text(category.get("label") or category.get("product_type"))
    source_category_path = " > ".join(
        part for part in [source_section, source_category] if part
    )

    tags: list[str] = []
    seen: set[str] = set()
    for tag in category.get("category_tags") or [
        source_section,
        source_category,
        source_category_path,
    ]:
        text = _clean_text(tag)
        if not text:
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            tags.append(text)
    return tags


def _merge_category_tags(target: dict, category: dict) -> None:
    existing = _category_tags(target)
    seen = {tag.lower() for tag in existing}
    for tag in _category_tags(category):
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            existing.append(tag)
    target["category_tags"] = existing


def _first_price(item: dict) -> Optional[float]:
    for key in ("SalePrice", "Price", "PricePerPiece"):
        price = _coerce_float(item.get(key))
        if price and price > 0:
            return price
    return None


def _parse_detail_page(html: str, detail_url: str, category: Optional[dict] = None) -> ScrapedProduct:
    model = _extract_model(html)
    item = model.get("CurrentItem") or {}
    if not item:
        raise ValueError(f"Could not find Vickerman product model at {detail_url}")

    image_urls = []
    for key in ["ImageUrl"] + [f"Image{i}Url" for i in range(1, 10)]:
        url = _image_url(item.get(key))
        if url and url not in image_urls:
            image_urls.append(url)
    if not image_urls:
        for key in ["Image"] + [f"Image{i}" for i in range(1, 10)]:
            url = _image_url(item.get(key))
            if url and url not in image_urls:
                image_urls.append(url)
    _add_silhouette_variant_image_fallbacks(item, image_urls)

    category = category or {}
    source_section = _clean_text(category.get("section"))
    source_category = _clean_text(category.get("label") or category.get("product_type"))
    source_category_path = " > ".join(
        part for part in [source_section, source_category] if part
    )
    category_tags = _category_tags(category)
    raw = {
        "source_url": detail_url,
        "detail_url": detail_url,
        "source_photo_url": image_urls[0] if image_urls else "",
        "image_urls": image_urls,
        "source_section": source_section,
        "source_category": source_category,
        "source_category_path": source_category_path,
        "category_tags": category_tags,
        "vickerman_model": model,
    }

    future_stock = _coerce_int(item.get("FutureStock")) or 0
    qty_in_stock = _coerce_int(item.get("QtyInStock")) or 0
    availability_note = f"In stock: {qty_in_stock}"
    if future_stock:
        availability_note += f"; future stock: {future_stock}"

    return ScrapedProduct(
        sku=_clean_text(item.get("ItemNumber")),
        name=_clean_text(item.get("Description")) or _clean_text(item.get("WebDescriptionSummary")),
        base_price=_first_price(item),
        uom="PC",
        moq=_coerce_int(item.get("QtyMin")),
        box_qty=_coerce_int(item.get("InnerPackQty")),
        case_qty=_coerce_int(item.get("QtyPerPack")),
        availability=str(qty_in_stock),
        availability_note=availability_note,
        upc=_clean_text(item.get("Upc")),
        description=_clean_text(item.get("WebDescription")),
        photo_url=image_urls[0] if image_urls else "",
        image_urls=image_urls,
        category=source_section or _clean_text(item.get("ProductType")) or "General",
        color=_clean_text(item.get("ColorMatch")),
        country_of_origin="",
        height_in=_coerce_float(item.get("Height")),
        width_in=_coerce_float(item.get("Width")),
        diameter_in=None,
        length_in=_coerce_float(item.get("Length")),
        weight_lb=_coerce_positive_float(item.get("Weight")),
        material=_clean_text(item.get("PrimaryMaterial")),
        finish="",
        style=_clean_text(item.get("ProductType")),
        raw=raw,
    )


async def discover_vickerman_catalog(
    username: str,
    password: str,
    progress_callback: Optional[Callable] = None,
    supplier_id: Optional[int] = None,
    use_cache: bool = True,
) -> dict:
    if use_cache and supplier_id:
        cached = await load_category_index(supplier_id, SCRAPER_KEY)
        if cached:
            categories = [
                {
                    "section": (row.get("category_name") or "General").split(" › ", 1)[0],
                    "label": (row.get("category_name") or row.get("category_slug_or_url") or "").split(" › ", 1)[-1],
                    "slug": row.get("category_slug_or_url"),
                    "ddcode": row.get("category_slug_or_url"),
                    "item_count": row.get("product_count") or 0,
                    "product_type": (row.get("category_name") or "").split(" › ", 1)[-1],
                }
                for row in cached
            ]
            totals = _catalog_totals(categories)
            return {
                "subcategories": categories,
                "total_products": totals["total_products"],
                "section_listing_total": totals["section_listing_total"],
                "catalog_summary": totals["catalog_summary"],
            }

    session = _new_session()
    homepage_html = _login(session, username, password)
    if progress_callback:
        await progress_callback(0, 0, "Logged in to Vickerman", milestone_event="logged_in")

    homepage_categories = _discover_category_links(homepage_html)
    if not homepage_categories:
        response = session.get(BASE_URL, timeout=30)
        response.raise_for_status()
        homepage_categories = _discover_category_links(response.text)
    categories = _merge_categories(_seed_categories(), homepage_categories)

    total_products = 0
    seen_category_urls = {
        category.get("slug") or category.get("ddcode") or ""
        for category in categories
    }
    idx = 0
    while idx < len(categories):
        category = categories[idx]
        idx += 1
        try:
            category_page_html, token = _fetch_category_page(session, category)
            _append_new_categories(
                categories,
                _discover_category_links(category_page_html),
                seen_category_urls,
            )
            item_count = _count_category_items(session, category, category_page_html, token)
            category["item_count"] = item_count
            total_products += item_count
        except Exception as exc:
            category["item_count"] = 0
            category["error"] = str(exc)[:180]
        if progress_callback:
            await progress_callback(
                idx,
                len(categories),
                f"Discovered {category['label']}: {category.get('item_count', 0)} items",
                milestone_event="category_found",
                category_info={
                    "name": category["label"],
                    "slug": category["slug"],
                    "section": category["section"],
                    "total": category.get("item_count", 0),
                },
            )
        await polite_delay(REQUEST_DELAY)

    if supplier_id:
        await save_category_index(
            supplier_id,
            SCRAPER_KEY,
            [
                {
                    "category_name": f"{cat['section']} › {cat['label']}",
                    "category_slug_or_url": cat["slug"],
                    "product_count": cat.get("item_count", 0),
                    "sample_product_urls": [],
                    "metadata": {"product_type": cat.get("product_type")},
                }
                for cat in categories
            ],
        )
        await verify_category_index(
            supplier_id,
            SCRAPER_KEY,
            [cat["slug"] for cat in categories if cat.get("slug")],
        )
    if progress_callback:
        await progress_callback(len(categories), len(categories), "Vickerman catalog discovery complete", milestone_event="categories_done")
    totals = _catalog_totals(categories)
    return {
        "subcategories": categories,
        "total_products": totals["total_products"],
        "section_listing_total": totals["section_listing_total"],
        "catalog_summary": totals["catalog_summary"],
    }


async def scrape_vickerman(
    username: str,
    password: str,
    max_products: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
    subcategories: Optional[list[dict]] = None,
    supplier_id: Optional[int] = None,
    excluded_item_numbers: Optional[set[str]] = None,
) -> AsyncGenerator[ScrapedProduct, None]:
    session = _new_session()
    _login(session, username, password)
    excluded_items = {
        _clean_text(item).upper()
        for item in (excluded_item_numbers or set())
        if _clean_text(item)
    }
    if subcategories is None:
        catalog = await discover_vickerman_catalog(username, password, None, supplier_id=supplier_id, use_cache=True)
        subcategories = catalog["subcategories"]
    if max_products:
        subcategories = _validation_category_order(subcategories)

    detail_categories: dict[str, dict] = {}
    detail_order: list[str] = []
    categories_seen = 0
    category_failures = 0
    for category_index, category in enumerate(subcategories, start=1):
        if max_products and len(detail_order) >= max_products:
            break
        slug = category.get("slug") or category.get("ddcode")
        if not slug:
            continue
        categories_seen += 1
        category_label = category.get("label") or category.get("product_type") or slug
        try:
            if progress_callback:
                await progress_callback(
                    len(detail_order),
                    max_products or 0,
                    f"Scanning Vickerman category {category_index:,}/{len(subcategories):,}: {category_label}",
                    category_slug=slug,
                    category_label=category_label,
                    category_index=category_index,
                    category_total=len(subcategories),
                    category_failures=category_failures,
                )
            category_page = _request_with_retries(session, "get", slug, timeout=30)
            token = _extract_token(category_page.text)
            first_page = _fetch_selector_page(session, category, 1, token)
            page_count = _parse_page_count(first_page)
            pages = [first_page]
            for page_index in range(2, page_count + 1):
                if max_products and len(detail_order) >= max_products:
                    break
                pages.append(_fetch_selector_page(session, category, page_index, token))
                await polite_delay(REQUEST_DELAY)

            category_collected = 0
            for listing_html in pages:
                for detail_url in _parse_product_links(listing_html):
                    item_number = _item_number_from_detail_url(detail_url).upper()
                    if item_number and item_number in excluded_items:
                        continue
                    if detail_url in detail_categories:
                        _merge_category_tags(detail_categories[detail_url], category)
                        continue
                    detail_category = dict(category)
                    detail_category["category_tags"] = _category_tags(category)
                    detail_categories[detail_url] = detail_category
                    detail_order.append(detail_url)
                    category_collected += 1
                    if progress_callback:
                        await progress_callback(
                            len(detail_order),
                            max_products or 0,
                            f"Queued {len(detail_order):,} unique Vickerman products",
                            category_slug=slug,
                            category_label=category_label,
                            category_index=category_index,
                            category_total=len(subcategories),
                            category_collected=category_collected,
                            category_failures=category_failures,
                        )
                    if max_products and len(detail_order) >= max_products:
                        break
                if max_products and len(detail_order) >= max_products:
                    break
        except Exception as exc:
            category_failures += 1
            if progress_callback:
                await progress_callback(
                    len(detail_order),
                    max_products or 0,
                    f"Skipped Vickerman category after retries: {category_label}: {exc}",
                    category_slug=slug,
                    category_label=category_label,
                    category_index=category_index,
                    category_total=len(subcategories),
                    category_failures=category_failures,
                    last_category_error=str(exc)[:300],
                )
            continue

    yielded = 0
    total_to_fetch = len(detail_order)
    for detail_url in detail_order:
        try:
            detail_response = _request_with_retries(session, "get", detail_url, timeout=30)
            product = _parse_detail_page(detail_response.text, detail_url, detail_categories[detail_url])
            yielded += 1
            if progress_callback:
                await progress_callback(
                    yielded,
                    total_to_fetch,
                    f"Scraped {product.sku} from Vickerman",
                    category_failures=category_failures,
                )
            yield product
            await polite_delay(REQUEST_DELAY)
        except Exception as exc:
            if progress_callback:
                await progress_callback(
                    yielded,
                    total_to_fetch,
                    f"Vickerman product failed: {detail_url}: {exc}",
                    category_failures=category_failures,
                    last_product_error=str(exc)[:300],
                )
            continue

    if supplier_id:
        try:
            await verify_category_index(supplier_id, SCRAPER_KEY, [c.get("slug") or c.get("ddcode") for c in subcategories if c.get("slug") or c.get("ddcode")])
        except Exception as exc:
            print(f"[vickerman] Category index verify failed (non-fatal): {exc}")
