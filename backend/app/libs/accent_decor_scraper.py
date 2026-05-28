"""Accent Decor full-catalog scraper — production-ready.

Accent Decor (accentdecor.com) is a Magento Cloud wholesale site.
Login requires: Account Number + Billing Zip Code.

Flow:
  1. Log in with stored account number (username) and billing zip (password)
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
from typing import AsyncGenerator, Optional, Callable
from bs4 import BeautifulSoup
from app.libs.scraper_base import (
    ScrapedProduct, parse_price, polite_delay,
    parse_dimension, parse_availability, with_retry,
    load_category_index, save_category_index, verify_category_index,
)

BASE_URL = "https://www.accentdecor.com"
LOGIN_URL = "https://www.accentdecor.com/customer/account/login"
REQUEST_DELAY = 2.0   # Magento has rate limiting
MAX_PRODUCTS = 50000  # safety cap

# Accent Decor category slugs to crawl (avoids search pagination issues)
CATEGORY_SLUGS = [
    "all-products",
    "floral-and-botanical",
    "vases-and-planters",
    "baskets-and-boxes",
    "candles-and-lanterns",
    "seasonal",
    "wreaths-and-garlands",
    "home-accents",
    "decorative-accessories",
    "trays-and-books",
    "moss-and-bark",
    "ribbon-and-wire",
    "containers",
]


def _is_login_page(html: str) -> bool:
    """Detect redirect to login."""
    lower = html.lower()
    return (
        "customer/account/login" in lower
        or 'id="email"' in lower
        or "please sign in" in lower
        or "account number" in lower
    )


def _parse_product_listing(html: str) -> list[str]:
    """Extract product detail URLs from a Magento listing page."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    # Primary: Magento product link class
    for a in soup.find_all("a", class_="product-item-link"):
        href = a.get("href", "")
        if href:
            urls.append(href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/"))

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


def _get_next_page_url(html: str) -> Optional[str]:
    """Find the next page URL in Magento pagination."""
    soup = BeautifulSoup(html, "html.parser")

    # Magento standard: <link rel="next"> in <head>
    nxt = soup.find("link", rel="next")
    if nxt and nxt.get("href"):
        return nxt["href"]

    # Fallback: <a class="next">
    nxt_a = soup.find("a", class_="next")
    if nxt_a and nxt_a.get("href"):
        href = nxt_a["href"]
        return href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")

    return None


def _parse_product_detail(html: str, page_url: str) -> Optional[ScrapedProduct]:
    """Parse a single Accent Decor product page into a ScrapedProduct."""
    soup = BeautifulSoup(html, "html.parser")
    raw: dict = {}

    # --- Name ---
    name_el = (
        soup.find("h1", class_="page-title")
        or soup.find("h1", itemprop="name")
        or soup.find("h1")
    )
    name = name_el.get_text(strip=True) if name_el else ""

    # --- SKU ---
    sku = ""
    # Method 1: itemprop
    sku_el = soup.find(attrs={"itemprop": "sku"})
    if sku_el:
        sku = sku_el.get_text(strip=True)
    # Method 2: product-info-sku div
    if not sku:
        sku_block = soup.find("div", class_="product-info-sku") or soup.find(class_="product.attribute.sku")
        if sku_block:
            val = sku_block.find(class_="value")
            sku = (val or sku_block).get_text(strip=True)
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
    price_el = (
        soup.find("span", class_="price")
        or soup.find(attrs={"itemprop": "price"})
    )
    if price_el:
        price = parse_price(price_el.get_text(strip=True))

    # --- All product images ---
    image_urls: list[str] = []
    # Primary gallery: data-src or src on .gallery-placeholder or fotorama
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if not src:
            continue
        if any(skip in src.lower() for skip in ["logo", "placeholder", "spacer", "icon", "/icon"]):
            continue
        if any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            full = src if src.startswith("http") else BASE_URL + "/" + src.lstrip("/")
            # Filter out Magento thumbnails vs full-size (prefer cache/full images)
            if full not in image_urls:
                image_urls.append(full)
    # Also check data-gallery-role elements
    for el in soup.find_all(attrs={"data-src": True}):
        src = el.get("data-src", "")
        if src and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png"]):
            full = src if src.startswith("http") else BASE_URL + "/" + src.lstrip("/")
            if full not in image_urls:
                image_urls.append(full)

    # --- Description ---
    desc_el = (
        soup.find("div", class_="product.attribute.description")
        or soup.find("div", class_="product-info-description")
        or soup.find(attrs={"itemprop": "description"})
    )
    description = desc_el.get_text(" ", strip=True) if desc_el else None

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
    if price:
        raw["price"] = str(price)

    # --- Dimensions ---
    height = parse_dimension(raw.get("Height") or raw.get("H") or "")
    width = parse_dimension(raw.get("Width") or raw.get("W") or "")
    diameter = parse_dimension(raw.get("Diameter") or raw.get("D") or "")
    length = parse_dimension(raw.get("Length") or raw.get("L") or "")

    # --- Category from breadcrumb ---
    category = None
    breadcrumb = soup.find("ul", class_="items") or soup.find(class_="breadcrumb")
    if breadcrumb:
        crumbs = [li.get_text(strip=True) for li in breadcrumb.find_all("li")]
        if len(crumbs) >= 2:
            category = crumbs[-2]  # second-to-last is the category

    # --- Availability ---
    avail_el = (
        soup.find(class_="stock")
        or soup.find(attrs={"itemprop": "availability"})
    )
    avail_raw = avail_el.get_text(strip=True) if avail_el else raw.get("Availability", "")
    avail_status, avail_note = parse_availability(avail_raw)

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
    """Perform login on the Accent Decor login page."""
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

    # Account number field
    for selector in [
        "input[name='login[username]']",
        "input[id='email']",
        "input[name='email']",
        "input[type='email']",
        "input[type='text']",
    ]:
        el = await page.query_selector(selector)
        if el:
            await el.fill(username)
            break

    # Billing zip / password field
    pw_el = await page.query_selector("input[type='password'], input[name='login[password]']")
    if pw_el:
        await pw_el.fill(password)

    submit = await page.query_selector(".action.login, button[type='submit']")
    if submit:
        await submit.click()
    # Use load state with a short networkidle best-effort — domcontentloaded is the baseline
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)

    html = await page.content()
    if _is_login_page(html):
        raise ValueError(
            "Accent Decor login failed — check the account number and billing zip in credentials."
        )
    print("[accent_decor] Logged in successfully.")


async def discover_accent_decor_catalog(
    username: str,
    password: str,
    progress_callback: Optional[Callable] = None,
    supplier_id: Optional[int] = None,
) -> dict:
    """Phase 1: Login, walk all categories, count product URLs.

    If supplier_id is provided and a fresh category index exists in the DB,
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
    if supplier_id is not None:
        cached = await load_category_index(supplier_id, SCRAPER_KEY)
        if cached:
            from app.libs.scraper_base import load_catalog_filters
            allowed_slugs = await load_catalog_filters(supplier_id)
            result_subcategories = [
                {
                    "slug": row["category_slug_or_url"],
                    "label": row["category_name"],
                    "item_count": row["product_count"] or 50,
                }
                for row in cached
                if allowed_slugs is None or row["category_slug_or_url"] in allowed_slugs
            ]
            total_products = sum(s["item_count"] for s in result_subcategories)
            print(f"[accent-discover] ✅ Fast mode: {len(result_subcategories)} categories from cache")
            if progress_callback:
                await progress_callback(
                    len(result_subcategories), len(result_subcategories),
                    f"Using cached index — {len(result_subcategories)} categories, ~{total_products:,} products (skipping discovery crawl)",
                    milestone_event="logged_in",
                )
                await progress_callback(
                    len(result_subcategories), len(result_subcategories),
                    f"All {len(result_subcategories)} categories from cache.",
                    milestone_event="categories_done",
                )
            return {"subcategories": result_subcategories, "total_products": total_products, "from_cache": True}

    # ── Full discovery crawl ───────────────────────────────────────────────────
    result_subcategories: list[dict] = []
    total_products = 0

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
            crawl_slugs = [
                slug for slug in CATEGORY_SLUGS
                if allowed_slugs is None or slug in allowed_slugs
            ]

            # Walk each category slug and count product URLs on page 1
            for cat_idx, slug in enumerate(crawl_slugs):
                cat_url = f"{BASE_URL}/{slug}"
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

                    # Count all product URLs across all pages of this category
                    soup = BeautifulSoup(html, "html.parser")
                    # Try to get total count from Magento toolbar
                    item_count = 0
                    toolbar = soup.find(class_="toolbar-amount") or soup.find(class_="amount")
                    if toolbar:
                        import re as _re
                        m = _re.search(r"(\d[\d,]*)", toolbar.get_text())
                        if m:
                            item_count = int(m.group(1).replace(",", ""))

                    # Fall back: count product links on first page, multiply by page count
                    if not item_count:
                        links = _parse_product_listing(html)
                        max_pg_url = _get_next_page_url(html)
                        # Estimate: if there's a next page we have at least 2x first page
                        item_count = len(links) * (2 if max_pg_url else 1)

                    total_products += item_count
                    label = slug.replace("-", " ").title()
                    result_subcategories.append({
                        "slug": slug,
                        "label": label,
                        "item_count": item_count,
                    })
                    print(f"[accent-discover] [{cat_idx+1}/{len(crawl_slugs)}] {label}: ~{item_count} items")

                    if progress_callback:
                        await progress_callback(
                            cat_idx + 1, len(crawl_slugs),
                            f"Counted {label} \u2014 ~{item_count:,} products",
                            milestone_event="category_found",
                            category_info={
                                "name": label,
                                "slug": slug,
                                "section": "",
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

    # ── Persist discovered categories into the index ───────────────────────────
    if supplier_id is not None and result_subcategories:
        index_entries = [
            {
                "category_name": s["label"],
                "category_slug_or_url": s["slug"],
                "product_count": s.get("item_count"),
            }
            for s in result_subcategories
        ]
        await save_category_index(supplier_id, SCRAPER_KEY, index_entries)
        print(f"[accent-discover] Category index saved ({len(index_entries)} rows)")

    print(f"[accent-discover] Done. ~{total_products:,} products across {len(result_subcategories)} categories")
    return {"subcategories": result_subcategories, "total_products": total_products, "from_cache": False}


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
        username: Account number
        password: Billing zip code
        max_products: Stop after this many products (None = all)
        progress_callback: async callable(done, total, message, *, category_slug, category_collected)
        subcategories: Pre-discovered category list from discover_accent_decor_catalog
    """
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
            cap = min(max_products or MAX_PRODUCTS, MAX_PRODUCTS)

            crawl_slugs = (
                [s["slug"] for s in subcategories]
                if subcategories
                else ["all-products"]
            )

            for slug in crawl_slugs:
                if len(product_urls) >= cap:
                    break
                slug_start = len(product_urls)
                current_url: Optional[str] = f"{BASE_URL}/{slug}"
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
                    current_url = _get_next_page_url(html)

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
