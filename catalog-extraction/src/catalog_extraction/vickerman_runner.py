"""Vickerman-specific extraction.

Vickerman (vickerman.com, Orchard CMS) cannot use the generic selector runner:
- Listing pages load product tiles via an AJAX POST after page load.
- Pagination is a click on `a[data-cmd='paginator']`, not an href.
- Product detail pages are Vue-rendered from JSON after load.
- Pricing is only rendered for logged-in reseller accounts; logged out the
  price area reads "Sign In For Pricing" and we export an empty price.
"""

from __future__ import annotations

import os
import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from seleniumbase import Driver

from catalog_extraction.schema import ProductExportRow
from catalog_extraction.seleniumbase_runner import ExtractionResult, _clean

LISTING_TILE_SELECTOR = "#psPage .product a[href*='products/details?item=']"
NEXT_PAGE_SELECTOR = "a[data-cmd='paginator'][data-pageindx]"
RENDER_POLL_SECONDS = 0.5
RENDER_TIMEOUT_SECONDS = 20

_STOCK_RE = re.compile(r"Available Stock:\s*\|?\s*([\d,]+)")
_CASE_RE = re.compile(r"Packs Per Case:\s*\|?\s*([\d,]+)")
_DIMENSIONS_RE = re.compile(r"""L\d+(?:\.\d+)?["']?\s*W\d+(?:\.\d+)?["']?\s*H\d+(?:\.\d+)?["']?""")


def _wait_for(driver: Driver, predicate, timeout: float = RENDER_TIMEOUT_SECONDS) -> str:
    html = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        html = driver.page_source
        if predicate(html):
            return html
        time.sleep(RENDER_POLL_SECONDS)
    return html


def _login(driver: Driver, config: dict) -> bool:
    login = config.get("login") or {}
    username = os.getenv(login.get("username_env", "VICKERMAN_USERNAME"), "")
    password = os.getenv(login.get("password_env", "VICKERMAN_PASSWORD"), "")
    if not (login.get("url") and username and password):
        return False

    driver.get(login["url"])
    _wait_for(driver, lambda html: "userNameOrEmail" in html)
    driver.find_element("css selector", login["username_selector"]).send_keys(username)
    driver.find_element("css selector", login["password_selector"]).send_keys(password)
    driver.find_element("css selector", login["submit_selector"]).click()
    time.sleep(float(login.get("post_login_wait_seconds", 4)))
    return "/Users/Account/LogOff" in driver.page_source


def _tile_urls(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []
    for node in soup.select(LISTING_TILE_SELECTOR):
        href = node.get("href")
        if href:
            urls.append(urljoin(base_url, href))
    return urls


def _collect_category(driver: Driver, url: str, max_pages: int) -> list[str]:
    driver.get(url)
    html = _wait_for(driver, lambda h: len(_tile_urls(h, url)) > 0)
    urls = _tile_urls(html, url)
    pages_seen = 1

    while pages_seen < max_pages:
        soup = BeautifulSoup(driver.page_source, "lxml")
        next_link = None
        for node in soup.select(NEXT_PAGE_SELECTOR):
            if "next" in node.get_text(" ", strip=True).lower():
                next_link = node
                break
        if next_link is None:
            break

        page_indx = next_link.get("data-pageindx")
        previous_first = urls[0] if urls else ""
        try:
            driver.execute_script(
                "var links = document.querySelectorAll(arguments[0]);"
                "for (var i = 0; i < links.length; i++) {"
                "  if (links[i].getAttribute('data-pageindx') === arguments[1]) { links[i].click(); return; }"
                "}",
                NEXT_PAGE_SELECTOR,
                page_indx,
            )
        except Exception:
            break

        html = _wait_for(
            driver,
            lambda h: _tile_urls(h, url) and _tile_urls(h, url)[0] != previous_first,
            timeout=15,
        )
        page_urls = _tile_urls(html, url)
        if not page_urls or page_urls[0] == previous_first:
            break
        urls.extend(page_urls)
        pages_seen += 1

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in urls:
        if candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
    return deduped


def _category_from_url(category_url: str) -> str:
    parts = [p for p in urlparse(category_url).path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "productselector":
        return f"{parts[1].replace('-', ' ').title()} / {parts[2].replace('-', ' ').title()}"
    return ""


def _parse_detail(config: dict, html: str, url: str, source_category_url: str) -> ProductExportRow:
    soup = BeautifulSoup(html, "lxml")
    details = soup.select_one(".productDetails") or soup

    name_node = details.select_one("h1") or soup.select_one("h1")
    sku_node = details.select_one(".productNumber") or soup.select_one(".productNumber")
    image_node = soup.select_one("img.productImage")
    overview_node = soup.select_one(".tab-content")

    detail_table = soup.select_one("table.item-detail-table")
    table_text = detail_table.get_text(" | ", strip=True) if detail_table else ""
    details_text = details.get_text(" | ", strip=True)

    # Pricing renders only for logged-in reseller accounts. The main item's
    # price is the first price pair in document order: a strikethrough list
    # price (span.strike.item-price) and the current/sale price (span.sale-item).
    sale_node = soup.select_one("span.sale-item")
    list_node = soup.select_one("span.strike.item-price")
    price = _clean(sale_node.get_text()) if sale_node else ""
    list_price = _clean(list_node.get_text()) if list_node else ""

    stock_match = _STOCK_RE.search(table_text) or _STOCK_RE.search(details_text)
    case_match = _CASE_RE.search(table_text) or _CASE_RE.search(details_text)

    overview_text = _clean(overview_node.get_text(" ", strip=True)) if overview_node else ""
    dimensions_match = _DIMENSIONS_RE.search(overview_text)

    raw: dict[str, str] = {}
    for label_node in soup.select("#tabs-4 b, .tab-content b, .additionalDetails b"):
        label = _clean(label_node.get_text(" ", strip=True)).rstrip(":")
        value = _clean(label_node.next_sibling.get_text(" ", strip=True) if hasattr(label_node.next_sibling, "get_text") else str(label_node.next_sibling or ""))
        if label and value:
            raw[label] = value
    if list_price and list_price != price:
        raw["list_price"] = list_price
    if not price and "Sign In For Pricing" in details_text:
        raw["pricing"] = "login required"

    return ProductExportRow(
        supplier_key=config["supplier_key"],
        supplier_name=config["supplier_name"],
        season=str(config.get("season", "")),
        sku=_clean(sku_node.get_text(" ", strip=True)) if sku_node else "",
        name=_clean(name_node.get_text(" ", strip=True)) if name_node else "",
        description=overview_text.split("Product Weight & Dimensions")[0].strip(" |"),
        category=_category_from_url(source_category_url),
        price=price,
        case_qty=case_match.group(1) if case_match else "",
        availability=stock_match.group(1) if stock_match else "",
        dimensions=dimensions_match.group(0) if dimensions_match else "",
        image_url=image_node.get("src", "") if image_node else "",
        source_url=url,
        source_category_url=source_category_url,
        raw=raw,
    )


def run_vickerman_extraction(config: dict, *, limit: int | None = None, headed: bool = False) -> ExtractionResult:
    listing = config.get("listing") or {}
    max_listing_pages = int(listing.get("max_listing_pages", 40))

    product_urls: list[tuple[str, str]] = []
    seen: set[str] = set()
    errors: list[str] = []
    listing_pages_seen = 0
    logged_in = False

    driver = Driver(browser="chrome", headless=not headed)
    try:
        logged_in = _login(driver, config)

        for start_url in config.get("start_urls", []):
            if limit and len(product_urls) >= limit:
                break
            try:
                category_urls = _collect_category(driver, start_url, max_listing_pages)
            except Exception as exc:
                errors.append(f"{start_url}: {exc}")
                continue
            listing_pages_seen += 1
            for product_url in category_urls:
                if product_url in seen:
                    continue
                seen.add(product_url)
                product_urls.append((product_url, start_url))
                if limit and len(product_urls) >= limit:
                    break

        rows: list[ProductExportRow] = []
        for product_url, source_category_url in product_urls:
            try:
                driver.get(product_url)
                html = _wait_for(
                    driver,
                    lambda h: "productNumber" in h and "{{" not in h.split("</footer>")[0],
                )
                rows.append(_parse_detail(config, html, product_url, source_category_url))
            except Exception as exc:
                errors.append(f"{product_url}: {exc}")
    finally:
        driver.quit()

    report = {
        "supplier_key": config["supplier_key"],
        "supplier_name": config["supplier_name"],
        "logged_in": logged_in,
        "listing_pages_seen": listing_pages_seen,
        "product_urls_found": len(product_urls),
        "rows_exported": len(rows),
        "errors": errors,
    }
    return ExtractionResult(rows=rows, report=report)
