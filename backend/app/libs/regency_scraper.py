"""Regency International scraper.

Regency (regency-rib.com) is a wholesale catalog site with classic Storefront
style pages. Pricing is visible after login. The important supplier-specific
details are tier pricing, UOM, box/carton quantities, minimum order multiples,
and style-level current/future inventory.
"""
import asyncio
import re
from html import unescape
from typing import AsyncGenerator, Callable, Optional
from urllib.parse import parse_qsl, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.libs.scraper_base import (
    ScrapedProduct,
    load_catalog_filters,
    load_category_index,
    parse_availability,
    parse_price,
    polite_delay,
    save_category_index,
    verify_category_index,
    with_retry,
)

BASE_URL = "https://www.regency-rib.com"
LOGIN_URL = f"{BASE_URL}/cgi-regency-rib/sb/order.cgi?func=2&storeid=*1a040546d0ab4bbe18c1723fd84a17&html_reg=html"
ACCOUNT_URL = f"{BASE_URL}/cgi-regency-rib/sb/order.cgi?func=3"
REQUEST_DELAY = 0.35
MAX_PRODUCTS = 50000
SCRAPER_KEY = "regency"
SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


CURATED_CATEGORY_HINTS: list[tuple[str, str, str]] = [
    ("Christmas", "Christmas Collection", "christmas-collection.html"),
    ("Christmas", "Christmas 2026 Themes", "2026-holiday-themes.html"),
    ("Home & Garden", "Home Decor", "home-decor.html"),
    ("Flowers & Foliage", "Flower Collection", "flower-collection.html"),
    ("Flowers & Foliage", "Foliage Collection", "foliage-collection.html"),
    ("Easter", "Easter Collection", "easter-collection.html"),
    ("Fall & Halloween", "Fall Collection", "fall-collection.html"),
    ("Fall & Halloween", "Halloween Collection", "halloween-collection.html"),
    ("Clearance", "Clearance", "clearance.html"),
]

NON_CATALOG_SLUG_PARTS = {
    "about",
    "account",
    "cart",
    "catalog",
    "claims",
    "contact",
    "events",
    "faq",
    "locate",
    "privacy",
    "request",
    "return",
    "sales-representative",
    "showroom",
    "tariff",
    "terms",
}


def _absolute_url(value: str) -> str:
    href = unescape((value or "").strip())
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(BASE_URL + "/", href.lstrip("/"))


def _category_slug(value: str) -> str:
    url = _absolute_url(value)
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.netloc and "regency-rib.com" not in parsed.netloc:
        return ""
    path = parsed.path.lstrip("/")
    if parsed.query:
        return f"{path}?{parsed.query}"
    return path


def _category_url(slug_or_url: str) -> str:
    value = (slug_or_url or "").strip()
    if not value:
        return BASE_URL
    return _absolute_url(value)


def _clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_login_page(html: str) -> bool:
    lower = html.lower()
    if _is_logged_in(html):
        return False
    return (
        "email address" in lower
        and "password" in lower
        and ("sign in" in lower or "existing customers" in lower)
    ) or "sign in / register" in lower


def _is_logged_in(html: str) -> bool:
    lower = html.lower()
    return "my account" in lower and "sign in / register" not in lower


def _looks_like_product_url(href: str) -> bool:
    slug = _category_slug(href)
    if not slug or not slug.endswith(".html"):
        return False
    lower = slug.lower()
    if any(skip in lower for skip in [
        "index.html",
        "collection.html",
        "collections.html",
        "catalog",
        "about",
        "faq",
        "showroom",
        "rep",
        "themes",
        "clearance",
        "promotion",
    ]):
        return False
    stem = lower.rsplit("/", 1)[-1].replace(".html", "")
    if "_" in stem or "-" in stem:
        return False
    return bool(re.match(r"^[a-z]{1,8}\d{2,}[a-z0-9]*$", stem))


def _parse_menu_categories(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    categories: list[dict] = []
    seen: set[str] = set()

    for section, label, slug in CURATED_CATEGORY_HINTS:
        categories.append({"section": section, "label": label, "slug": slug, "ddcode": slug, "item_count": 0})
        seen.add(slug)

    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        label = _clean_text(a.get_text(" ", strip=True))
        slug = _category_slug(href)
        lower = slug.lower()
        if not slug or slug in seen or not lower.endswith(".html"):
            continue
        if _looks_like_product_url(slug):
            continue
        if any(part in lower for part in NON_CATALOG_SLUG_PARTS):
            continue
        if any(skip in lower for skip in ["index.html", "about", "faq", "account", "registration", "cart", "order.cgi"]):
            continue
        if not label:
            label = slug.rsplit("/", 1)[-1].replace(".html", "").replace("-", " ").title()
        section = _infer_section(label, slug)
        categories.append({"section": section, "label": label, "slug": slug, "ddcode": slug, "item_count": 0})
        seen.add(slug)

    return categories


def _infer_section(label: str, slug: str) -> str:
    haystack = f"{label} {slug}".lower()
    if "christmas" in haystack or "holiday" in haystack:
        return "Christmas"
    if "home" in haystack or "garden" in haystack:
        return "Home & Garden"
    if "flower" in haystack or "foliage" in haystack:
        return "Flowers & Foliage"
    if "easter" in haystack:
        return "Easter"
    if "fall" in haystack or "halloween" in haystack:
        return "Fall & Halloween"
    if "clearance" in haystack or "promotion" in haystack:
        return "Clearance"
    return "General"


def _parse_listing_count(html: str) -> int:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    patterns = [
        r"Items?\s+\d[\d,]*\s*-\s*\d[\d,]*\s+of\s+(\d[\d,]*)",
        r"Showing\s+\d[\d,]*\s*-\s*\d[\d,]*\s+of\s+(\d[\d,]*)",
        r"(\d[\d,]*)\s+products?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return int(match.group(1).replace(",", ""))
    product_links = _parse_product_listing(html)
    return len(product_links)


def _parse_page_context(html: str) -> tuple[Optional[str], str]:
    page_id_match = re.search(r"var\s+pageId\s*=\s*[\"']([^\"']+)[\"']", html)
    page_type_match = re.search(r"var\s+pageType\s*=\s*[\"']([^\"']+)[\"']", html)
    page_id = page_id_match.group(1).strip() if page_id_match else None
    page_type = page_type_match.group(1).strip() if page_type_match else "products"
    return page_id, page_type


def _parse_product_listing(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        if not _looks_like_product_url(href):
            continue
        full = _absolute_url(href)
        if full and full not in urls:
            urls.append(full)
    return urls


def _fetch_product_grid_sync(
    session: requests.Session,
    page_id: str,
    page_type: str = "products",
    skip: int = 0,
    source_url: Optional[str] = None,
) -> str:
    params: dict[str, str | int] = {}
    if source_url:
        parsed = urlparse(source_url)
        params.update({k: v for k, v in parse_qsl(parsed.query) if k})
    params.update({"skip": skip, "pageType": page_type or "products", "pageId": page_id})
    response = session.get(f"{BASE_URL}/get_products.php", params=params, timeout=20, allow_redirects=True)
    response.raise_for_status()
    return response.text


async def _fetch_product_grid(
    session: requests.Session,
    page_id: str,
    page_type: str = "products",
    skip: int = 0,
    source_url: Optional[str] = None,
) -> str:
    return await asyncio.to_thread(_fetch_product_grid_sync, session, page_id, page_type, skip, source_url)


def _form_payload(form: BeautifulSoup) -> dict:
    payload: dict[str, str] = {}
    for field in form.find_all("input"):
        name = field.get("name")
        if name:
            payload[name] = field.get("value", "")
    return payload


def _http_login_sync(username: str, password: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(SESSION_HEADERS)

    response = session.get(LOGIN_URL, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    form = next(
        (
            f for f in soup.find_all("form")
            if f.find("input", {"name": "email1"}) and f.find("input", {"name": "text1"})
        ),
        None,
    )
    if not form:
        raise ValueError("Regency login form did not include expected email/password fields.")

    payload = _form_payload(form)
    payload["email1"] = username
    payload["text1"] = password
    payload["function"] = "Sign In"
    action_url = urljoin(response.url, form.get("action") or LOGIN_URL)
    login_response = session.post(action_url, data=payload, timeout=20, allow_redirects=True)
    login_response.raise_for_status()

    if _is_login_page(login_response.text):
        raise ValueError("Regency login failed — check the saved email/password.")
    return session


async def _http_login(username: str, password: str) -> requests.Session:
    return await asyncio.to_thread(_http_login_sync, username, password)


def _http_get_sync(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=20, allow_redirects=True)
    response.raise_for_status()
    return response.text


async def _http_get(session: requests.Session, url: str) -> str:
    return await asyncio.to_thread(_http_get_sync, session, url)


def _get_next_page_url(html: str, current_url: Optional[str] = None) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    for selector in ["a.next", "a[rel='next']"]:
        node = soup.select_one(selector)
        if node and node.get("href"):
            return _absolute_url(node["href"])
    for a in soup.find_all("a", href=True):
        text = _clean_text(a.get_text(" ", strip=True)).lower()
        if text in {"next", ">", ">>"}:
            return _absolute_url(a["href"])
    return None


def _is_product_image_url(url: str) -> bool:
    lower = (url or "").lower()
    if not lower or "regency-rib.com" not in lower:
        return False
    if any(skip in lower for skip in ["logo", "banner", "catalog", "button", "icon", "spacer", "pixel"]):
        return False
    return any(ext in lower for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"])


def _extract_images(soup: BeautifulSoup) -> list[str]:
    images: list[str] = []
    for img in soup.find_all("img"):
        for attr in ("data-src", "data-large", "data-zoom-image", "src"):
            src = img.get(attr)
            if not src:
                continue
            full = _absolute_url(src)
            if _is_product_image_url(full) and full not in images:
                images.append(full)
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        full = _absolute_url(og["content"])
        if _is_product_image_url(full) and full not in images:
            images.insert(0, full)
    return images


def _parse_label_value_blocks(text: str) -> dict:
    raw: dict = {}
    for label in ["UOM", "BOX", "CARTON"]:
        match = re.search(rf"\b{label}\s*:\s*([A-Z0-9./-]+)", text, re.I)
        if match:
            raw[label.upper()] = _clean_text(match.group(1))
    sku_match = re.search(r"\bSKU\s*:\s*([A-Z0-9._/-]+)", text, re.I)
    if sku_match:
        raw["SKU"] = _clean_text(sku_match.group(1))
    return raw


def _parse_tier_prices(soup: BeautifulSoup) -> list[dict]:
    tiers: list[dict] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        row_texts = [[_clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])] for row in rows]
        if len(row_texts) < 2:
            continue
        header = row_texts[0]
        price_row = next((row for row in row_texts[1:] if row and row[0].lower() == "price"), None)
        if not price_row or not header or header[0].lower() != "quantity":
            continue
        for qty_label, price_label in zip(header[1:], price_row[1:]):
            price = parse_price(price_label)
            if qty_label and price is not None:
                tiers.append({"quantity": qty_label, "price": price, "price_label": price_label})
    return tiers


def _parse_style_inventory(soup: BeautifulSoup) -> list[dict]:
    inventory: list[dict] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [_clean_text(c.get_text(" ", strip=True)).lower() for c in rows[0].find_all(["th", "td"])]
        if "style" not in headers or "qty" not in " ".join(headers):
            continue
        for row in rows[1:]:
            cells = [_clean_text(c.get_text(" ", strip=True)) for c in row.find_all(["th", "td"])]
            if len(cells) < len(headers):
                continue
            record = dict(zip(headers, cells))
            if not record.get("style"):
                continue
            row_text = " ".join(cells)
            date_match = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", row_text)
            inventory.append({
                "style": record.get("style"),
                "current_qty": record.get("current qty") or record.get("current"),
                "future_qty": record.get("future qty") or record.get("future"),
                "future_ship_date": date_match.group(0) if date_match else None,
            })
    return inventory


def _parse_minimums(text: str) -> tuple[Optional[int], Optional[int]]:
    moq = None
    multiple = None
    match = re.search(r"Minimum order amount:\s*(\d+)", text, re.I)
    if match:
        moq = int(match.group(1))
    match = re.search(r"multiples of:\s*(\d+)", text, re.I)
    if match:
        multiple = int(match.group(1))
    return moq, multiple


def _parse_product_detail(html: str, page_url: str) -> Optional[ScrapedProduct]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    compact_text = soup.get_text(" ", strip=True)
    if "SKU:" not in compact_text and not re.search(r"As low as:\s*\$?[\d,.]+", compact_text, re.I):
        return None

    sku_match = re.search(r"\bSKU:\s*([A-Z0-9._/-]+)", compact_text, re.I)
    sku = sku_match.group(1).strip() if sku_match else page_url.rstrip("/").rsplit("/", 1)[-1].replace(".html", "")
    sku = sku.upper()

    title_el = soup.find("h1") or soup.find("h2")
    name = _clean_text(title_el.get_text(" ", strip=True)) if title_el else ""
    if not name:
        lines = [_clean_text(line) for line in text.splitlines() if _clean_text(line)]
        for line in lines:
            if line.upper() != sku and not line.lower().startswith(("sku:", "as low as")):
                if len(line) > 8:
                    name = line
                    break
    if not name:
        name = sku

    price_tiers = _parse_tier_prices(soup)
    as_low_as_match = re.search(r"As low as:\s*(\$?[\d,.]+)", compact_text, re.I)
    base_price = parse_price(as_low_as_match.group(1)) if as_low_as_match else None
    if base_price is None and price_tiers:
        base_price = min(t["price"] for t in price_tiers if t.get("price") is not None)

    raw = _parse_label_value_blocks(compact_text)
    moq, order_multiple = _parse_minimums(compact_text)
    style_inventory = _parse_style_inventory(soup)
    image_urls = _extract_images(soup)

    availability_raw = ""
    first_inventory = style_inventory[0] if style_inventory else {}
    if first_inventory.get("current_qty") not in (None, ""):
        availability_raw = str(first_inventory["current_qty"])
    if first_inventory.get("future_ship_date"):
        availability_raw = f"future ship date {first_inventory['future_ship_date']}"
    availability, availability_note = parse_availability(availability_raw)
    if first_inventory.get("future_ship_date"):
        availability = "eta"
        availability_note = f"Future ship date {first_inventory['future_ship_date']}"

    raw.update({
        "name": name,
        "sku": sku,
        "detail_url": page_url,
        "source_url": page_url,
        "detail_status": "stored",
        "source_price_label": as_low_as_match.group(0) if as_low_as_match else None,
        "price_tiers": price_tiers,
        "style_inventory": style_inventory,
        "order_multiple": order_multiple,
        "scraper_key": SCRAPER_KEY,
    })
    if image_urls:
        raw["source_photo_url"] = image_urls[0]
        raw["image_urls"] = image_urls
    raw["image_status"] = "pending" if image_urls else "no_supplier_image"

    return ScrapedProduct(
        sku=sku,
        name=name,
        base_price=base_price,
        category=raw.get("Category"),
        uom=raw.get("UOM"),
        moq=moq,
        box_qty=_safe_int(raw.get("BOX")),
        case_qty=_safe_int(raw.get("CARTON")),
        availability=availability,
        availability_note=availability_note,
        photo_url=image_urls[0] if image_urls else None,
        image_urls=image_urls,
        style=first_inventory.get("style"),
        raw={k: v for k, v in raw.items() if v is not None},
    )


def _safe_int(value) -> Optional[int]:
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return None


async def _fill_first_visible(page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        try:
            elements = await page.query_selector_all(selector)
        except Exception:
            continue
        for element in elements:
            try:
                if await element.is_visible() and await element.is_enabled():
                    await element.fill(value)
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
        for element in elements:
            try:
                if await element.is_visible() and await element.is_enabled():
                    await element.click()
                    return True
            except Exception:
                continue
    return False


async def _wait_for_page(page) -> None:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass


async def _goto(page, url: str, timeout_ms: int = 15000) -> None:
    await asyncio.wait_for(
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms),
        timeout=(timeout_ms / 1000) + 5,
    )


async def _block_heavy_assets(route) -> None:
    if route.request.resource_type in {"image", "media", "font", "stylesheet"}:
        await route.abort()
    else:
        await route.continue_()


async def _do_login(page, username: str, password: str) -> None:
    await _goto(page, LOGIN_URL, timeout_ms=15000)
    await _wait_for_page(page)

    username_filled = await _fill_first_visible(page, [
        "input[name='email1']",
        "input[name='email']",
        "input[name='Email']",
        "input[type='email']",
        "input[name*='email' i]",
        "input[id*='email' i]",
        "input[type='text']",
    ], username)
    password_filled = await _fill_first_visible(page, [
        "input[name='text1']",
        "input[name='password']",
        "input[name='Password']",
        "input[type='password']",
        "input[name*='pass' i]",
        "input[id*='pass' i]",
    ], password)
    if not username_filled or not password_filled:
        raise ValueError("Regency login form did not show visible email/password fields.")

    clicked = await _click_first_visible(page, [
        "input[name='function'][value='Sign In']",
        "button:has-text('SIGN IN')",
        "button:has-text('Sign In')",
        "input[value='SIGN IN']",
        "input[value='Sign In']",
        "input[type='submit']",
        "button[type='submit']",
    ])
    if not clicked:
        await page.keyboard.press("Enter")
    await page.wait_for_timeout(1000)
    await _wait_for_page(page)

    html = await page.content()
    if _is_login_page(html) and not _is_logged_in(html):
        raise ValueError("Regency login failed — check the saved email/password.")


async def discover_regency_catalog(
    username: str,
    password: str,
    progress_callback: Optional[Callable] = None,
    supplier_id: Optional[int] = None,
    use_cache: bool = True,
) -> dict:
    if supplier_id is not None and use_cache:
        cached = await load_category_index(supplier_id, SCRAPER_KEY)
        if cached:
            allowed_slugs = await load_catalog_filters(supplier_id)
            subcategories = [
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
                    "item_count": row["product_count"] or 0,
                }
                for row in cached
                if allowed_slugs is None or row["category_slug_or_url"] in allowed_slugs
            ]
            total_products = sum(s["item_count"] for s in subcategories)
            if progress_callback:
                await progress_callback(len(subcategories), len(subcategories), "Using cached Regency category index.", milestone_event="logged_in")
                await progress_callback(len(subcategories), len(subcategories), "Regency categories loaded from cache.", milestone_event="categories_done")
            return {"subcategories": subcategories, "total_products": total_products, "from_cache": True}

    result_subcategories: list[dict] = []
    total_products = 0

    session = await _http_login(username, password)
    if progress_callback:
        await progress_callback(0, 1, "Logged in to Regency.", milestone_event="logged_in")

    homepage_html = await _http_get(session, f"{BASE_URL}/index.html")
    if _is_login_page(homepage_html):
        session = await _http_login(username, password)
        homepage_html = await _http_get(session, f"{BASE_URL}/index.html")
    categories = _parse_menu_categories(homepage_html)
    allowed_slugs = await load_catalog_filters(supplier_id) if supplier_id is not None else None
    categories = [c for c in categories if allowed_slugs is None or c["slug"] in allowed_slugs]

    for index, category in enumerate(categories, start=1):
        url = _category_url(category["slug"])
        try:
            html = await _http_get(session, url)
            if _is_login_page(html):
                session = await _http_login(username, password)
                html = await _http_get(session, url)
            count = _parse_listing_count(html)
            page_id, page_type = _parse_page_context(html)
            if page_id:
                grid_html = await _fetch_product_grid(session, page_id, page_type, 0, url)
                count = max(count, len(_parse_product_listing(grid_html)))
        except Exception as exc:
            print(f"[regency-discover] Error on {category['slug']}: {exc}")
            count = 0

        item = {**category, "item_count": count}
        result_subcategories.append(item)
        total_products += count
        if progress_callback:
            await progress_callback(
                index,
                len(categories),
                f"Counted {category['label']} — ~{count:,} products",
                milestone_event="category_found",
                category_info={
                    "name": category["label"],
                    "slug": category["slug"],
                    "section": category.get("section") or "General",
                    "total": count,
                },
            )
        await polite_delay(REQUEST_DELAY)

    if progress_callback:
        await progress_callback(len(result_subcategories), len(result_subcategories), "Regency category discovery complete.", milestone_event="categories_done")

    if supplier_id is not None and result_subcategories:
        await save_category_index(
            supplier_id,
            SCRAPER_KEY,
            [
                {
                    "category_name": f"{s.get('section') or 'General'} › {s['label']}",
                    "category_slug_or_url": s["slug"],
                    "product_count": s.get("item_count") or 0,
                }
                for s in result_subcategories
            ],
        )
        try:
            await verify_category_index(supplier_id, SCRAPER_KEY, [s["slug"] for s in result_subcategories])
        except Exception as exc:
            print(f"[regency-discover] Category index verify failed (non-fatal): {exc}")

    return {"subcategories": result_subcategories, "total_products": total_products, "from_cache": False}


async def scrape_regency(
    username: str,
    password: str,
    max_products: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
    subcategories: Optional[list] = None,
    supplier_id: Optional[int] = None,
) -> AsyncGenerator[ScrapedProduct, None]:
    session = await _http_login(username, password)
    cap = min(max_products or MAX_PRODUCTS, MAX_PRODUCTS)
    crawl_slugs = [
        s.get("slug") or s.get("ddcode") or s.get("category_slug_or_url")
        for s in (subcategories or [])
        if s.get("slug") or s.get("ddcode") or s.get("category_slug_or_url")
    ] or [slug for _, _, slug in CURATED_CATEGORY_HINTS]

    product_urls: list[str] = []
    cat_url_ranges: list[dict] = []
    for cat_index, slug in enumerate(crawl_slugs, start=1):
        if len(product_urls) >= cap:
            break
        start = len(product_urls)
        current_url: Optional[str] = _category_url(slug)
        page_num = 0
        while current_url and len(product_urls) < cap:
            page_num += 1

            async def fetch_page(u=current_url):
                html = await _http_get(session, u)
                if _is_login_page(html):
                    fresh = await _http_login(username, password)
                    session.cookies.update(fresh.cookies)
                    html = await _http_get(session, u)
                return html

            try:
                html = await with_retry(fetch_page, max_attempts=3, base_delay=2.0, label=f"regency listing {slug} page {page_num}")
            except Exception as exc:
                print(f"[regency] Failed listing {current_url}: {exc}")
                break
            added = 0
            page_id, page_type = _parse_page_context(html)
            if page_id:
                skip = 0
                while len(product_urls) < cap:
                    try:
                        grid_html = await with_retry(
                            lambda pid=page_id, ptype=page_type, s=skip, u=current_url: _fetch_product_grid(session, pid, ptype, s, u),
                            max_attempts=3,
                            base_delay=1.5,
                            label=f"regency product grid {slug} skip {skip}",
                        )
                    except Exception as exc:
                        print(f"[regency] Failed product grid {current_url} skip={skip}: {exc}")
                        break
                    page_links = _parse_product_listing(grid_html)
                    page_added = 0
                    for link in page_links:
                        if link not in product_urls:
                            product_urls.append(link)
                            page_added += 1
                    added += page_added
                    if len(page_links) == 0 or page_added == 0:
                        break
                    skip += len(page_links)
                    await polite_delay(REQUEST_DELAY)
            else:
                for link in _parse_product_listing(html):
                    if link not in product_urls:
                        product_urls.append(link)
                        added += 1
            if added == 0 and _parse_product_detail(html, current_url):
                if current_url not in product_urls:
                    product_urls.append(current_url)
                    added = 1
            if added == 0 or page_id:
                break
            current_url = _get_next_page_url(html, current_url)
            await polite_delay(REQUEST_DELAY)
        cat_url_ranges.append({"slug": slug, "start": start, "end": len(product_urls)})
        if progress_callback:
            await progress_callback(
                cat_index,
                len(crawl_slugs),
                f"Collected {len(product_urls) - start} Regency product links from {slug}",
                category_slug=slug,
                category_collected=len(product_urls) - start,
            )

    product_urls = product_urls[:cap]
    total = len(product_urls)
    if progress_callback:
        await progress_callback(0, total, f"Found {total} Regency products. Scraping details...")
    slug_ranges = {r["slug"]: (r["start"], r["end"]) for r in cat_url_ranges}

    for index, url in enumerate(product_urls):
        current_slug = crawl_slugs[0] if crawl_slugs else ""
        current_cat_collected = 1
        for slug, (start, end) in slug_ranges.items():
            if start <= index < end:
                current_slug = slug
                current_cat_collected = index - start + 1
                break

        async def fetch_detail(u=url):
            html = await _http_get(session, u)
            if _is_login_page(html):
                fresh = await _http_login(username, password)
                session.cookies.update(fresh.cookies)
                html = await _http_get(session, u)
            return html

        try:
            html = await with_retry(fetch_detail, max_attempts=3, base_delay=2.0, label=f"regency product {index + 1}/{total}")
            product = _parse_product_detail(html, url)
            if product:
                yield product
            if progress_callback and index % 10 == 0:
                await progress_callback(
                    index + 1,
                    total,
                    f"Scraped {index + 1} of {total}",
                    category_slug=current_slug,
                    category_collected=current_cat_collected,
                )
            await polite_delay(REQUEST_DELAY)
        except Exception as exc:
            print(f"[regency] Error on {url}: {exc}")
            continue

    if supplier_id is not None and subcategories:
        try:
            await verify_category_index(
                supplier_id,
                SCRAPER_KEY,
                [s.get("slug") or s.get("ddcode") for s in subcategories if s.get("slug") or s.get("ddcode")],
            )
        except Exception as exc:
            print(f"[regency] Category index verify failed (non-fatal): {exc}")
