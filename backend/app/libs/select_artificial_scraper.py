"""Select Artificials scraper.

Select Artificials is an Angular/ServiceStack wholesale site. Public pages
expose category navigation, but product import must use a logged-in account
session because pricing is account-specific.
"""

import re
from typing import AsyncGenerator, Callable, Optional
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from app.libs.scraper_base import (
    ScrapedProduct,
    load_category_index,
    save_category_index,
    verify_category_index,
)

BASE_URL = "https://selectartificials.com"
SHOP_URL = f"{BASE_URL}/shop/"
SCRAPER_KEY = "select_artificial"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_category_url(value: str) -> str:
    return urljoin(BASE_URL + "/", (value or "").strip())


def _category_section(label: str, url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    category = (params.get("Category") or [""])[0]
    if category:
        return _clean_text(category).title()
    lowered = f"{label} {url}".lower()
    for section in [
        "foliages",
        "moss",
        "flowers",
        "twigs",
        "berries",
        "autumn",
        "christmas",
        "containers",
        "garden",
        "home",
        "halloween",
        "sale",
    ]:
        if section in lowered:
            return section.title()
    return "General"


def _parse_category_links(html: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    categories: list[dict] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = _normalize_category_url(link.get("href") or "")
        parsed = urlparse(href)
        if parsed.netloc and "selectartificials.com" not in parsed.netloc:
            continue
        if "/shop/" not in parsed.path:
            continue
        params = parse_qs(parsed.query)
        if not params.get("Category"):
            continue
        label = _clean_text(link.get_text(" ", strip=True))
        if not label:
            label = _clean_text((params.get("Group") or params.get("SubCategory") or params.get("Category") or [""])[0])
        if not label:
            continue
        if href in seen:
            continue
        seen.add(href)
        section = _category_section(label, href)
        categories.append({
            "section": section,
            "label": label,
            "slug": href,
            "ddcode": href,
            "item_count": 0,
        })

    return categories


async def _login_and_read_catalog_html(username: str, password: str) -> str:
    """Log in with Playwright and return authenticated homepage/shop HTML."""

    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    except Exception as exc:
        raise ValueError(f"Playwright is required for Select Artificial login: {exc}") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=45000)

            sign_in = page.get_by_text(re.compile(r"sign in|login", re.I)).first
            try:
                await sign_in.click(timeout=8000)
            except PlaywrightTimeoutError as exc:
                raise ValueError("Could not open Select Artificial sign-in modal.") from exc

            await page.locator("input[type='text'], input[name*='user' i], input[placeholder*='user' i]").first.fill(username)
            await page.locator("input[type='password'], input[name*='password' i], input[placeholder*='password' i]").first.fill(password)
            await page.get_by_role("button", name=re.compile(r"login|sign in", re.I)).first.click()
            await page.wait_for_load_state("networkidle", timeout=45000)

            content = await page.content()
            lowered = content.lower()
            if "sign in to your account" in lowered or "invalid" in lowered or "incorrect" in lowered:
                raise ValueError("Select Artificial rejected the saved customer number/billing zip credentials.")

            await page.goto(SHOP_URL, wait_until="networkidle", timeout=45000)
            return await page.content()
        finally:
            await browser.close()


async def discover_select_artificial_catalog(
    username: str,
    password: str,
    progress_callback: Optional[Callable] = None,
    supplier_id: Optional[int] = None,
    use_cache: bool = True,
) -> dict:
    """Log in and cache Select Artificial category links.

    Product counts are intentionally left at 0 until we confirm the authenticated
    ServiceStack product query route that returns preferred pricing.
    """

    if supplier_id and use_cache:
        cached = await load_category_index(supplier_id, SCRAPER_KEY)
        if cached:
            subcategories = [
                {
                    "section": (row.get("category_name") or "General").split(" › ", 1)[0],
                    "label": (row.get("category_name") or row.get("category_slug_or_url") or "").split(" › ", 1)[-1],
                    "slug": row.get("category_slug_or_url"),
                    "ddcode": row.get("category_slug_or_url"),
                    "item_count": row.get("product_count") or 0,
                }
                for row in cached
            ]
            return {
                "sections": [],
                "subcategories": subcategories,
                "total_products": sum(c.get("item_count", 0) for c in subcategories),
                "from_cache": True,
            }

    if progress_callback:
        await progress_callback(0, 1, "Logging in to Select Artificial...", milestone_event="logged_in")

    html = await _login_and_read_catalog_html(username, password)
    categories = _parse_category_links(html)
    if not categories:
        raise ValueError("Select Artificial login succeeded, but no shop categories were discovered.")

    if progress_callback:
        await progress_callback(
            len(categories),
            len(categories),
            f"Discovered {len(categories)} Select Artificial categories.",
            milestone_event="categories_done",
        )

    if supplier_id:
        index_entries = [
            {
                "category_name": f"{cat['section']} › {cat['label']}",
                "category_slug_or_url": cat["slug"],
                "product_count": cat.get("item_count", 0),
            }
            for cat in categories
        ]
        await save_category_index(supplier_id, SCRAPER_KEY, index_entries)
        await verify_category_index(supplier_id, SCRAPER_KEY, [cat["slug"] for cat in categories])

    return {
        "sections": [],
        "subcategories": categories,
        "total_products": sum(c.get("item_count", 0) for c in categories),
        "from_cache": False,
        "catalog_summary": {
            "requires_authenticated_product_route": True,
            "note": "Categories are cached. Product import waits on authenticated QueryProducts route capture.",
        },
    }


async def scrape_select_artificial(
    username: str,
    password: str,
    max_products: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
    subcategories: Optional[list[dict]] = None,
    supplier_id: Optional[int] = None,
) -> AsyncGenerator[ScrapedProduct, None]:
    """Placeholder until preferred-pricing product query route is verified."""

    raise ValueError(
        "Select Artificial product sync is not enabled yet. "
        "Run Configure Catalog, log in, then capture the authenticated product API route that returns preferred pricing."
    )
    yield  # pragma: no cover
