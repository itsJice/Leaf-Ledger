from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from seleniumbase import Driver

from catalog_extraction.schema import ProductExportRow


@dataclass
class ExtractionResult:
    rows: list[ProductExportRow]
    report: dict


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _first_text(soup: BeautifulSoup, selector: str | None) -> str:
    if not selector:
        return ""
    for option in selector.split(","):
        node = soup.select_one(option.strip())
        if node:
            value = node.get("content") or node.get("data-sku") or node.get_text(" ", strip=True)
            cleaned = _clean(value)
            if cleaned:
                return cleaned
    return ""


def _first_image(soup: BeautifulSoup, selector: str | None, base_url: str) -> str:
    if not selector:
        return ""
    for option in selector.split(","):
        for node in soup.select(option.strip()):
            src = node.get("src") or node.get("data-src") or node.get("data-zoom-image")
            if not src:
                continue
            if any(skip in src.lower() for skip in ("logo", "placeholder", "spacer", "icon")):
                continue
            return urljoin(base_url, src)
    return ""


def _same_site(url: str, candidate: str) -> bool:
    return urlparse(url).netloc == urlparse(candidate).netloc


def _collect_links(html: str, base_url: str, selector: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()
    for option in selector.split(","):
        for node in soup.select(option.strip()):
            href = node.get("href")
            if not href:
                continue
            url = urljoin(base_url, href)
            if url not in seen and _same_site(base_url, url):
                seen.add(url)
                links.append(url)
    return links


def _next_page(html: str, base_url: str, selector: str | None) -> str:
    if not selector:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for option in selector.split(","):
        node = soup.select_one(option.strip())
        if node and node.get("href"):
            return urljoin(base_url, node["href"])
    return ""


def _login(driver: Driver, config: dict) -> None:
    login = config.get("login") or {}
    login_url = login.get("url")
    if not login_url:
        return

    username = os.getenv(login.get("username_env", "SUPPLIER_USERNAME"), "")
    password = os.getenv(login.get("password_env", "SUPPLIER_PASSWORD"), "")
    if not username or not password:
        return

    driver.get(login_url)
    driver.wait_for_ready_state_complete()
    driver.type(login["username_selector"], username, timeout=15)
    driver.type(login["password_selector"], password, timeout=15)
    driver.click(login["submit_selector"], timeout=15)
    time.sleep(float(login.get("post_login_wait_seconds", 3)))


def _parse_product(config: dict, html: str, url: str, source_category_url: str) -> ProductExportRow:
    soup = BeautifulSoup(html, "lxml")
    product = config.get("product") or {}
    raw = {field: _first_text(soup, selector) for field, selector in product.items() if field != "image"}
    image_url = _first_image(soup, product.get("image"), url)

    return ProductExportRow(
        supplier_key=config["supplier_key"],
        supplier_name=config["supplier_name"],
        season=str(config.get("season", "")),
        sku=raw.get("sku", ""),
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        category=raw.get("category", ""),
        price=raw.get("price", ""),
        uom=raw.get("uom", ""),
        moq=raw.get("moq", ""),
        box_qty=raw.get("box_qty", ""),
        case_qty=raw.get("case_qty", ""),
        availability=raw.get("availability", ""),
        dimensions=raw.get("dimensions", ""),
        image_url=image_url,
        source_url=url,
        source_category_url=source_category_url,
        raw=raw,
    )


def run_selector_extraction(config: dict, *, limit: int | None = None, headed: bool = False) -> ExtractionResult:
    listing = config.get("listing") or {}
    product_link_selector = listing["product_link_selector"]
    next_selector = listing.get("next_selector")
    max_listing_pages = int(listing.get("max_listing_pages", 25))

    product_urls: list[tuple[str, str]] = []
    seen_products: set[str] = set()
    listing_pages_seen = 0
    errors: list[str] = []

    driver = Driver(browser="chrome", headless=not headed)
    try:
        _login(driver, config)

        for start_url in config.get("start_urls", []):
            current_url = start_url
            pages_for_start = 0

            while current_url and pages_for_start < max_listing_pages:
                driver.get(current_url)
                driver.wait_for_ready_state_complete()
                html = driver.get_page_source()
                listing_pages_seen += 1
                pages_for_start += 1

                for product_url in _collect_links(html, current_url, product_link_selector):
                    if product_url in seen_products:
                        continue
                    seen_products.add(product_url)
                    product_urls.append((product_url, current_url))
                    if limit and len(product_urls) >= limit:
                        break

                if limit and len(product_urls) >= limit:
                    break

                next_url = _next_page(html, current_url, next_selector)
                current_url = next_url if next_url and next_url != current_url else ""

            if limit and len(product_urls) >= limit:
                break

        rows: list[ProductExportRow] = []
        for product_url, source_category_url in product_urls:
            try:
                driver.get(product_url)
                driver.wait_for_ready_state_complete()
                rows.append(_parse_product(config, driver.get_page_source(), product_url, source_category_url))
            except Exception as exc:
                errors.append(f"{product_url}: {exc}")

    finally:
        driver.quit()

    report = {
        "supplier_key": config["supplier_key"],
        "supplier_name": config["supplier_name"],
        "listing_pages_seen": listing_pages_seen,
        "product_urls_found": len(product_urls),
        "rows_exported": len(rows),
        "errors": errors,
    }
    return ExtractionResult(rows=rows, report=report)
