"""Allstate Floral scraper — category-grid approach.

Allstate Floral (allstatefloral.com) is a trade-account site with two browsing
systems:

  OLD: /pro_i/  — product search, 50/page, requires visiting each detail page
  NEW: /design/ — category grid, 50/page, shows SKU + price + photo + desc inline

We use the /design/ category grid for the fast bulk import (Option C):
  Phase 1  —  Walk all catalog sections → subcategories → listing pages
              Extract SKU, price, UOM, description, image from each grid cell
              ~20 min for all 20k+ products
  Phase 2  —  Background detail enrichment (dimensions, UPC, colour, origin)
              Fetches /Productitemdetail.cfm for individual products on demand

Category URL structure (verified May 2025):
  Top sections:   /design/index.cfm?CL=1&CLCD={X|E|W|M}
  Sub-sections:   /design/index.cfm?CL=1&CLCD={H|W|L|I}&SubCodeIMG=y&NewDN=Y
  Sub-categories: /design/?DDCODE={HZ0001..}&classlist=y&page=N

Auth:
  Login field: input[name='UserCode'] (NOT custno)
  Password field: input[type='password']
"""
import re
import asyncio
from typing import AsyncGenerator, Optional, Callable
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse
from bs4 import BeautifulSoup
from app.libs.scraper_base import (
    ScrapedProduct, parse_price, safe_int, polite_delay,
    parse_dimension, parse_availability, with_retry,
    load_category_index, save_category_index, verify_category_index,
)

LOGIN_URL = "https://www.allstatefloral.com/?login"
DESIGN_BASE = "https://www.allstatefloral.com/design/"
DESIGN_INDEX = "https://www.allstatefloral.com/design/index.cfm"
DETAIL_BASE_URL = "https://www.allstatefloral.com/Productitemdetail.cfm"
BASE_URL = "https://www.allstatefloral.com"
REQUEST_DELAY = 1.0   # seconds between requests
MAX_PRODUCTS = 30000  # safety cap

# All known top-level catalog sections and the URL that shows their sub-categories
# Format: (section_name, CLCD, subcategory_index_url)
CATALOG_SECTIONS = [
    ("Holiday & Fall",   "X", f"{DESIGN_INDEX}?CL=1&CLCD=H&SubCodeIMG=y&NewDN=Y"),
    ("Spring & Summer",  "E", f"{DESIGN_INDEX}?CL=1&CLCD=W&SubCodeIMG=y&NewDN=Y"),
    ("Allstate Living",  "W", f"{DESIGN_INDEX}?CL=1&CLCD=L&SubCodeIMG=y&NewDN=Y"),
    ("Inspired Living",  "M", f"{DESIGN_INDEX}?CL=1&CLCD=I&SubCodeIMG=y&NewDN=Y"),
]

DDCODE_LABELS: dict[str, str] = {
    "HZ0001": "CHRISTMAS TREES",
    "HZ0002": "ORNAMENTS",
    "HZ0003": "HOLIDAY ACCESSORIES",
    "HZ0004": "WREATHS & GARLANDS",
    "HZ0005": "HOLIDAY FLORAL",
    "HZ0006": "STOCKINGS & PILLOWS",
    "HZ0007": "OUTDOOR HOLIDAY",
    "HZ0008": "FALL",
    "HZ0009": "HALLOWEEN",
    "HZ0010": "PVC COLLECTION",
    "HZ0011": "CHRISTMAS LIGHTS",
    "EZ6EA": "Easter",
    "EZ6GD": "Garden",
    "EZ6SP": "Spring",
    "EZ6SU": "Summer",
    "EZ6TR": "Tropical",
    "EZ6WD": "Wedding",
    "EZ6VA": "Valentine",
    "WW0001": "New",
    "WW0002": "Tropical",
    "WW0003": "Greenery",
    "WW0004": "Orchids",
    "WW0005": "Limited Quantity",
    "MM0001": "New",
    "MM0002": "Sale",
}

REQUIRED_ALLSTATE_PARENT_DDCODES = {
    "HZ0001", "HZ0002", "HZ0003", "HZ0004", "HZ0005", "HZ0006",
    "HZ0007", "HZ0008", "HZ0009", "HZ0010", "HZ0011",
}

# Known subcategory labels matched to our internal categories
CATEGORY_MAP: dict[str, str] = {
    "christmas tree": "trees", "tree": "trees",
    "ornament": "accents", "holiday accessori": "accents",
    "wreath": "accents", "garland": "accents",
    "floral": "florals", "flower": "florals", "bloom": "florals",
    "green": "greenery", "foliage": "greenery", "fern": "greenery",
    "bush": "greenery", "ivy": "greenery", "moss": "greenery",
    "container": "containers", "vase": "containers", "pot": "containers",
    "basket": "containers", "planter": "containers",
    "wood": "wood", "twig": "wood", "branch": "wood", "driftwood": "wood",
    "stocking": "accents", "pillow": "accents", "ribbon": "accents",
    "fruit": "accents", "berry": "accents", "pumpkin": "accents",
    "outdoor": "outdoor", "topiar": "trees", "palm": "trees",
    "succulent": "greenery", "cactus": "greenery",
    "spring": "florals", "summer": "florals", "fall": "accents",
    "holiday": "accents", "halloween": "accents",
    "light": "accents", "string light": "accents",
}


def _is_login_page(html: str) -> bool:
    """Detect if the browser has been redirected back to the login page."""
    lower = html.lower()
    return 'name="usercode"' in lower or 'name="custno"' in lower or "please log in" in lower


def _map_category(label: str, section: str) -> str:
    """Map a subcategory label to our internal category enum."""
    combined = (label + " " + section).lower()
    for keyword, cat in CATEGORY_MAP.items():
        if keyword in combined:
            return cat
    return "other"


def _has_required_allstate_cache_rows(cached: list[dict]) -> bool:
    """Avoid trusting old partial Allstate indexes that skipped visible categories."""
    parent_slugs = {
        str(row.get("category_slug_or_url", "")).split("|", 1)[0]
        for row in cached
    }
    missing = REQUIRED_ALLSTATE_PARENT_DDCODES - parent_slugs
    if missing:
        print(f"[allstate-discover] Cached index missing required DDCODEs {sorted(missing)} — live discovery required")
        return False
    return True


def _parse_design_listing_page(html: str, section: str, subcategory_label: str) -> list[dict]:
    """Parse the /design/?DDCODE=XX&classlist=y listing grid.

    Each product occupies a <td height="225"> containing a nested table with:
      Row 1: product image (<img src="/CFFileServlet/...">) linked to detail page
      Row 2: SKU (bold link) + "List Price: $X.XX (UOM" + description text

    Returns a list of dicts with raw product data ready to become ScrapedProduct.
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen_skus: set[str] = set()

    price_pattern = re.compile(r"List Price:\s*\$([\d,]+\.?\d*)", re.I)
    uom_pattern = re.compile(r"List Price:[^(]+\(\s*([A-Z]{1,4})\s*", re.I)
    category = _map_category(subcategory_label, section)

    # Each product is in a <td height="225"> — this is the reliable container selector
    for td in soup.find_all("td", attrs={"height": "225"}):
        text = td.get_text()
        if "List Price" not in text:
            continue

        # Photo: first CFFileServlet image inside this cell
        photo_url = None
        fallback_photo_url = None
        for img in td.find_all("img"):
            src = img.get("src", "")
            if src and not fallback_photo_url and not any(skip in src.lower() for skip in ("spacer", "logo", "icon")):
                fallback_photo_url = src if src.startswith("http") else urljoin(BASE_URL + "/", src)
            if "CFFileServlet" in src:
                photo_url = src if src.startswith("http") else BASE_URL + src
                break
        if not photo_url:
            photo_url = fallback_photo_url

        # SKU: from the ItemNumber query param in the detail link
        sku = None
        for a in td.find_all("a", href=True):
            m = re.search(r"ItemNumber=([^&]+)", a.get("href", ""), re.I)
            if m:
                sku = unquote(m.group(1)).strip()
                break

        if not sku or sku in seen_skus:
            continue
        seen_skus.add(sku)

        # Price
        pm = price_pattern.search(text)
        price = float(pm.group(1).replace(",", "")) if pm else None

        # UOM — inside the parens after "List Price: $X (UOM"
        um = uom_pattern.search(text)
        uom = um.group(1).strip() if um else "EA"

        # Description: the last non-empty line of text in the cell
        # Layout: "\nSKU \n\xa0\n\nList Price: $X.XX\xa0 (UOM\n\nDESCRIPTION TEXT\n\n"
        lines = [l.strip() for l in text.replace("\xa0", " ").splitlines()]
        lines = [l for l in lines if l and l != sku and "List Price" not in l]
        description = lines[-1].strip() if lines else sku

        products.append({
            "sku": sku,
            "name": description or sku,
            "base_price": price,
            "uom": uom,
            "photo_url": photo_url,
            "category": category,
            "allstate_subcategory": subcategory_label,
            "allstate_section": section,
        })

    return products


def _clean_detail_label(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").replace("\xa0", " ")).strip().rstrip(":").strip()


def _build_cookie_header(cookies: list[dict]) -> dict[str, str]:
    """Convert Playwright cookies to a requests-friendly Cookie header."""
    cookie_pairs: list[str] = []
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value is not None:
            cookie_pairs.append(f"{name}={value}")
    if not cookie_pairs:
        return {}
    return {"Cookie": "; ".join(cookie_pairs)}


def _parse_allstate_detail_page(html: str) -> dict:
    """Parse the Allstate Product Item Detail table into normalized fields.

    The detail page exposes the exact attributes the product library needs
    (MinQty, BoxQty, CaseQty, dimensions, weights, UPC, material breakdown,
    etc.) in a two-column/two-pair table. Keep the original labels in raw_data
    so the expanded UI can mirror Allstate's own structure.
    """
    soup = BeautifulSoup(html, "html.parser")
    raw: dict[str, str] = {}
    photo_url: Optional[str] = None

    # The detail page has a main product image plus a handful of utility icons.
    # Capture the first plausible product image so downstream image downloads can
    # fall back to a detail-page URL when the listing thumbnail is stale.
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            continue
        src_l = src.lower()
        alt_l = (img.get("alt") or "").lower()
        if any(skip in src_l or skip in alt_l for skip in ("logo", "spacer", "icon", "cart", "banner", "arrow")):
            continue
        if "cfFileservlet".lower() in src_l or "product" in src_l or "image" in src_l:
            photo_url = src if src.startswith("http") else urljoin(BASE_URL + "/", src)
            break
        if not photo_url:
            photo_url = src if src.startswith("http") else urljoin(BASE_URL + "/", src)

    # Header fields.
    header_text = soup.get_text(" ", strip=True)
    sold_out = bool(re.search(r"\bSOLD\s+OUT\b", header_text, re.I))
    item_match = re.search(r"Item No:\s*([^\s]+)", header_text, re.I)
    desc_match = re.search(r"Description:\s*(.+?)(?:\s+SOLD\s+OUT|\s+Uom:|\s*$)", header_text, re.I)
    if item_match:
        raw["Item No"] = item_match.group(1).strip()
    if desc_match:
        raw["Description"] = desc_match.group(1).strip()

    # Detail grid labels and values.
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        i = 0
        while i < len(cells) - 1:
            label = _clean_detail_label(cells[i].get_text(" ", strip=True))
            value = _clean_detail_label(cells[i + 1].get_text(" ", strip=True))
            if label and value and len(label) <= 40:
                raw[label] = value
                i += 2
            else:
                i += 1

    # Material Breakdown is rendered as a heading row followed by a value row.
    material_header = soup.find(string=re.compile(r"Material\s+Breakdown", re.I))
    if material_header:
        header_row = material_header.find_parent("tr")
        value_row = header_row.find_next_sibling("tr") if header_row else None
        if value_row:
            material = _clean_detail_label(value_row.get_text(" ", strip=True))
            if material and "Location in Showroom" not in material:
                raw["Material Breakdown"] = material

    avail_note = raw.get("Avail. Qty") or raw.get("Avail Qty") or ("SOLD OUT" if sold_out else None)
    avail_status = "out_of_stock" if sold_out or (avail_note and "sold out" in avail_note.lower()) else None
    if not avail_status and avail_note:
        avail_status, _ = parse_availability(avail_note)

    return {
        "sku": raw.get("Item No"),
        "description": raw.get("Description"),
        "uom": raw.get("Uom") or raw.get("UOM"),
        "moq": safe_int(raw.get("MinQty") or raw.get("Min Qty")),
        "box_qty": safe_int(raw.get("BoxQty") or raw.get("Box Qty")),
        "case_qty": safe_int(raw.get("CaseQty") or raw.get("Case Qty")),
        "base_price": parse_price(raw.get("BasePrice") or raw.get("Base Price") or ""),
        "availability": avail_status,
        "availability_note": avail_note,
        "length_in": parse_dimension(raw.get("ProdLength") or raw.get("Prod Length") or ""),
        "weight_lb": parse_dimension(raw.get("ProdWeight") or raw.get("Prod Weight") or ""),
        "upc": raw.get("UPC"),
        "case_cube": raw.get("CaseCube"),
        "suggested_retail": parse_price(raw.get("SugRetail") or raw.get("Suggested Retail") or ""),
        "product_class": raw.get("Class"),
        "color": raw.get("ColorGrp") or raw.get("Color Group") or raw.get("Color"),
        "season": raw.get("Season"),
        "oversize": raw.get("Oversize"),
        "country_of_origin": raw.get("Country of Origin"),
        "material": raw.get("Material Breakdown"),
        "photo_url": photo_url,
        "raw": raw,
    }


async def _fetch_detail_for_listing_product(page, username: str, password: str, sku: str) -> dict:
    detail_url = f"{DETAIL_BASE_URL}?ItemNumber={quote(sku, safe='')}&Banner=1"
    html = await _safe_goto(page, detail_url, username, password)
    detail = _parse_allstate_detail_page(html)
    detail.setdefault("raw", {})
    detail["raw"]["detail_url"] = detail_url
    return detail


def _parse_item_count(html: str) -> int:
    """Extract item count from a category listing page.

    Allstate renders the number as markup like "item count: <b>1654</b>",
    so parse both the raw HTML and the flattened text.
    """
    normalized = html.replace("\xa0", " ")
    m = re.search(r"item\s*count:\s*(?:<[^>]+>\s*)*([\d,]+)", normalized, re.I)
    if not m:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        m = re.search(r"item\s*count:\s*([\d,]+)", text, re.I)
    return int(m.group(1).replace(",", "")) if m else 0


def _append_page_param(url: str, page_num: int) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}page={page_num}"


def _listing_url_from_subcategory(sub: dict) -> str:
    if sub.get("url"):
        return sub["url"]

    ddcode = sub["ddcode"]
    parts = ddcode.split("|")
    if len(parts) == 3:
        parent_ddcode, cid, category_id = parts
        return f"{BASE_URL}/collect/?cid={cid}&DDCODE={parent_ddcode}&CategoryID={category_id}"

    return f"{DESIGN_BASE}?DDCODE={ddcode}&classlist=y"


def _extract_collection_children(html: str, parent_subcategory: dict) -> list[dict]:
    """Extract child product groups from /collect/ landing pages.

    Examples from Allstate:
      /collect/?cid=PVC&DDCODE=HZ0010 -> CategoryID=ICE, CEDAR, ...
      /collect/?cid=STLIGHT&DDCODE=HZ0011 -> CategoryID=CW, WW, MX
    """
    parent_url = parent_subcategory.get("url") or ""
    if "/collect/" not in parent_url:
        return []

    parsed = urlparse(parent_url)
    query = parse_qs(parsed.query)
    cid = (query.get("cid") or [""])[0]
    ddcode = (query.get("DDCODE") or [parent_subcategory.get("ddcode", "")])[0]
    if not cid or not ddcode:
        return []

    soup = BeautifulSoup(html, "html.parser")
    children: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        child_query = parse_qs(urlparse(a.get("href", "")).query)
        category_id = (child_query.get("CategoryID") or [""])[0]
        if not category_id or category_id in seen:
            continue
        seen.add(category_id)
        label = a.get_text(" ", strip=True) or category_id
        child_url = f"{BASE_URL}{parsed.path}?cid={cid}&DDCODE={ddcode}&CategoryID={category_id}"
        children.append({
            "ddcode": f"{ddcode}|{cid}|{category_id}",
            "label": f"{parent_subcategory.get('label', ddcode)} › {label}",
            "section": parent_subcategory.get("section", ""),
            "url": child_url,
            "parent_ddcode": ddcode,
        })
    return children


def _parse_max_page(html: str) -> int:
    """Extract the maximum page number from pagination links.

    Allstate only renders a window of pagination links (e.g. 1-5 of 9),
    so we CANNOT rely on this for the true last page.
    Use _calc_max_pages(item_count) instead wherever item_count is known.
    Kept as a fallback when item_count is 0.
    """
    soup = BeautifulSoup(html, "html.parser")
    pages: set[int] = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"[&?]page=(\d+)", a.get("href", ""), re.I)
        if m:
            pages.add(int(m.group(1)))
    return max(pages) if pages else 1


def _calc_max_pages(item_count: int, per_page: int = 50) -> int:
    """Calculate true page count from item_count (ceiling division)."""
    if item_count <= 0:
        return 1
    return (item_count + per_page - 1) // per_page


def _parse_category_label(html: str) -> str:
    """Extract the human-readable category name from a classlist/product listing page.

    Allstate renders the category heading as a short bold/td text element that
    appears immediately before 'item count:' on listing pages.  For sections
    (Holiday, Everyday, etc.) that use image tiles whose labels are baked into
    image files, this is the ONLY way to get the real text name.

    Returns an empty string if no label can be found.
    """
    soup = BeautifulSoup(html, "html.parser")
    skip_phrases = {
        "sale", "n= new item", "item count", "page", "sorry", "no data",
        "available today", "available within",
    }
    texts: list[str] = []
    seen: set[str] = set()
    for el in soup.find_all(["b", "strong", "td", "font"]):
        t = el.get_text(strip=True)
        if not t or t in seen or len(t) > 50:
            continue
        seen.add(t)
        tl = t.lower()
        if any(s in tl for s in skip_phrases):
            continue
        # Stop collecting once we hit the first item SKU (uppercase + digits pattern)
        if re.match(r'^[A-Z]{2}\d', t):
            break
        texts.append(t)

    # Return the first meaningful text — it's always the category heading
    return texts[0] if texts else ""


async def _count_listing_products(
    page,
    base_url: str,
    section: str,
    label: str,
    username: str,
    password: str,
    first_page_html: Optional[str] = None,
) -> tuple[int, int]:
    """Count unique product SKUs in a category by walking listing pages.

    Allstate's displayed "item count" is capped for several categories, so the
    only reliable count is the number of unique product tiles across pages.
    """
    seen_skus: set[str] = set()
    page_no = 1
    max_pages_seen = 0
    html = first_page_html

    while True:
        if html is None:
            html = await _safe_goto(page, _append_page_param(base_url, page_no), username, password)
            await polite_delay(REQUEST_DELAY)

        page_products = _parse_design_listing_page(html, section, label)
        if not page_products:
            break

        for product in page_products:
            sku = product.get("sku")
            if sku:
                seen_skus.add(sku)

        max_pages_seen = page_no
        if len(page_products) < 50:
            break

        page_no += 1
        html = None

    return len(seen_skus), max(max_pages_seen, 1 if seen_skus else 0)


def _extract_subcategories(html: str) -> list[dict]:
    """Extract subcategory DDCODE + label from a section index page.

    Each subcategory is structured as two <tr> rows inside a containing table:
      <tr><td><a href="./?DDCODE=HZ0001&classlist=y"><img .../></a></td></tr>
      <tr><td class="font_view"><b>CHRISTMAS TREES</b></td></tr>  ← label here
    """
    soup = BeautifulSoup(html, "html.parser")
    subs: list[dict] = []
    seen: set[str] = set()
    ddcode_re = re.compile(r"DDCODE=([A-Z0-9]+)", re.I)

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        m = ddcode_re.search(href)
        if not m:
            continue
        ddcode = m.group(1)
        if ddcode in seen:
            continue
        seen.add(ddcode)

        # Strategy 1: label is in the <tr> immediately after the <tr> containing this link
        label = ""
        row = a.find_parent("tr")
        if row:
            next_row = row.find_next_sibling("tr")
            if next_row:
                label = next_row.get_text(strip=True)

        # Strategy 2: look for a <td class="font_view"> or <b> near the link
        if not label:
            td = a.find_parent("td")
            if td:
                # Check sibling tds in same row
                for sibling in td.find_next_siblings("td"):
                    t = sibling.get_text(strip=True)
                    if t:
                        label = t
                        break

        # Strategy 3: look for nearest font_view class element after this anchor
        if not label:
            for el in a.find_all_next(class_="font_view", limit=3):
                t = el.get_text(strip=True)
                if t and len(t) < 60:  # avoid grabbing big blocks of text
                    label = t
                    break

        # Strategy 4: alt text of the image inside the link
        if not label:
            img = a.find("img")
            if img and img.get("alt", "").strip():
                label = img["alt"].strip()

        # Final fallback: use ddcode so UI always shows something
        if not label:
            label = ddcode

        label = DDCODE_LABELS.get(ddcode, label)

        # Build the classlist URL
        if "collect" in href:
            full_url = BASE_URL + href if href.startswith("/") else BASE_URL + "/design/" + href
        else:
            full_url = f"{DESIGN_BASE}?DDCODE={ddcode}&classlist=y"

        subs.append({"ddcode": ddcode, "label": label.strip(), "url": full_url})
    return subs


async def _do_login(page, username: str, password: str) -> None:
    """Perform login on the Allstate login page."""
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    html = await page.content()
    if "usercode" not in html.lower() and "custno" not in html.lower():
        print("[allstate] Already logged in or on unexpected page")
        return

    filled = False
    for selector in ["input[name='UserCode']", "input[name='custno']", "input[name='username']", "input[type='text']"]:
        el = await page.query_selector(selector)
        if el:
            await el.fill(username)
            filled = True
            print(f"[allstate] Filled username with selector: {selector}")
            break

    if not filled:
        raise ValueError("[allstate] Could not find username input field on login page")

    pw_el = await page.query_selector("input[type='password']")
    if pw_el:
        await pw_el.fill(password)
    else:
        raise ValueError("[allstate] Could not find password field on login page")

    for submit_sel in ["input[name='Submit']", "input[type='submit']", "button[type='submit']"]:
        submit = await page.query_selector(submit_sel)
        if submit:
            await submit.click()
            break

    # Best-effort networkidle after login submit — fall back to domcontentloaded
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
    html = await page.content()
    if _is_login_page(html):
        raise ValueError(
            "Login failed — check the username/password stored for this supplier. "
            "Allstate username is your customer/account number (e.g. 713FLV)."
        )
    print("[allstate] Logged in successfully.")


async def _safe_goto(page, url: str, username: str, password: str, timeout: int = 45000) -> str:
    """Go to URL, detect session expiry, re-login if needed, return HTML.

    Uses 'domcontentloaded' instead of 'networkidle' to avoid stalling on
    pages that keep firing background requests (ads, analytics, session pings)
    which can block networkidle indefinitely.
    A hard asyncio timeout is also applied as a safety ceiling.
    """
    import asyncio
    timeout_s = timeout / 1000

    async def _goto_once():
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        # Give dynamic content a brief moment to settle after DOM loads
        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass  # networkidle is best-effort; DOM content is sufficient
        return await page.content()

    try:
        html = await asyncio.wait_for(_goto_once(), timeout=timeout_s)
    except asyncio.TimeoutError:
        print(f"[allstate] Hard timeout ({timeout_s}s) on {url} — using whatever loaded")
        html = await page.content()

    if _is_login_page(html):
        print(f"[allstate] Session expired — re-logging in...")
        await _do_login(page, username, password)
        try:
            html = await asyncio.wait_for(_goto_once(), timeout=timeout_s)
        except asyncio.TimeoutError:
            print(f"[allstate] Hard timeout after re-login on {url}")
            html = await page.content()
    return html


async def discover_allstate_catalog(
    username: str,
    password: str,
    progress_callback: Optional[Callable] = None,
    supplier_id: Optional[int] = None,
    use_cache: bool = True,
    apply_filters: bool = True,
) -> dict:
    """Phase 1: Login, walk all sections/subcategories, count every product listing.

    If supplier_id is provided and a fresh category index exists in the DB,
    the full section crawl is skipped and the cached subcategories are returned
    directly (fast mode). A lightweight verify pass still runs to detect new
    categories after scraping.

    Returns:
        {
          "subcategories": [{ddcode, label, section, item_count, max_pages}],
          "total_products": int,
          "from_cache": bool,
        }
    Does NOT yield products — this is purely a counting/discovery pass.
    """
    from playwright.async_api import async_playwright

    SCRAPER_KEY = "allstate"

    # ── Fast mode: check category index cache ─────────────────────────────────
    if supplier_id is not None and use_cache:
        cached = await load_category_index(supplier_id, SCRAPER_KEY)
        if cached and _has_required_allstate_cache_rows(cached):
            # Reconstruct subcategory dicts from cached index rows.
            # Apply catalog filter allow-list (DDCODEs the user selected).
            from app.libs.scraper_base import load_catalog_filters
            allowed_ddcodes = await load_catalog_filters(supplier_id) if apply_filters and supplier_id is not None else None

            result_subcategories = []
            total_products = 0
            for row in cached:
                slug = row["category_slug_or_url"]
                # Skip DDCODEs not in the user's selection (if any selection saved)
                if allowed_ddcodes is not None and slug not in allowed_ddcodes:
                    continue
                count = row["product_count"] if row["product_count"] is not None else 0
                max_pg = _calc_max_pages(count)
                result_subcategories.append({
                    "ddcode": slug,
                    "label": row["category_name"],
                    "section": "",           # section info folded into label at save time
                    "item_count": count,
                    "max_pages": max_pg,
                })
                total_products += count

            filter_note = f" (filtered to {len(result_subcategories)} selected)" if allowed_ddcodes else ""
            print(f"[allstate-discover] ✅ Fast mode: {len(result_subcategories)} categories from cache{filter_note}")
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
            print("[allstate-discover] Logging in...")
            await _do_login(page, username, password)

            # ✅ Milestone: logged in
            if progress_callback:
                await progress_callback(
                    0, 1, "Logged in to Allstate Floral.",
                    milestone_event="logged_in"
                )

            # Walk each top-level section and collect subcategory metadata
            all_subcategories: list[dict] = []
            for section_name, clcd, section_url in CATALOG_SECTIONS:
                print(f"[allstate-discover] Section: {section_name}")
                try:
                    html = await _safe_goto(page, section_url, username, password)
                    subs = _extract_subcategories(html)
                    if not subs:
                        alt_url = f"{DESIGN_INDEX}?CL=1&CLCD={clcd}&SubCodeIMG=y"
                        html = await _safe_goto(page, alt_url, username, password)
                        subs = _extract_subcategories(html)
                    for s in subs:
                        s["section"] = section_name
                    all_subcategories.extend(subs)
                    await polite_delay(REQUEST_DELAY)
                except Exception as e:
                    print(f"[allstate-discover] Failed section {section_name}: {e}")

            print(f"[allstate-discover] {len(all_subcategories)} subcategories found")

            expanded_subcategories: list[dict] = []
            for sub in all_subcategories:
                sub_url = sub.get("url", "")
                if "/collect/" not in sub_url:
                    expanded_subcategories.append(sub)
                    continue
                try:
                    html = await _safe_goto(page, sub_url, username, password)
                    children = _extract_collection_children(html, sub)
                    if children:
                        expanded_subcategories.extend(children)
                        print(f"[allstate-discover] Expanded {sub.get('label', sub.get('ddcode'))}: {len(children)} child groups")
                    else:
                        expanded_subcategories.append(sub)
                    await polite_delay(REQUEST_DELAY)
                except Exception as e:
                    print(f"[allstate-discover] Failed expanding collection {sub.get('ddcode')}: {e}")
                    expanded_subcategories.append(sub)
            all_subcategories = expanded_subcategories
            print(f"[allstate-discover] {len(all_subcategories)} scrapeable categories after collection expansion")

            # Apply saved catalog filter before counting/scraping when this
            # discovery is part of a scrape. Catalog Wizard live refreshes
            # deliberately bypass filters so the full index can be rebuilt.
            from app.libs.scraper_base import load_catalog_filters
            allowed_ddcodes = await load_catalog_filters(supplier_id) if apply_filters and supplier_id is not None else None
            if allowed_ddcodes is not None:
                before = len(all_subcategories)
                all_subcategories = [
                    sub for sub in all_subcategories
                    if sub.get("ddcode") in allowed_ddcodes
                    or sub.get("parent_ddcode") in allowed_ddcodes
                    or str(sub.get("ddcode", "")).split("|", 1)[0] in allowed_ddcodes
                ]
                print(f"[allstate-discover] Catalog filter applied: {len(all_subcategories)}/{before} categories selected")

            if progress_callback:
                await progress_callback(
                    0, len(all_subcategories),
                    f"Found {len(all_subcategories)} categories — counting products..."
                )

            # Visit first page of each subcategory just to read item_count
            for idx, sub in enumerate(all_subcategories):
                ddcode = sub["ddcode"]
                label = sub.get("label", ddcode)
                section = sub.get("section", "")
                base_url = _listing_url_from_subcategory(sub)
                try:
                    html = await _safe_goto(page, _append_page_param(base_url, 1), username, password)
                    await polite_delay(REQUEST_DELAY)
                    item_count = _parse_item_count(html)
                    if item_count > 0:
                        max_pg = _calc_max_pages(item_count)
                    else:
                        # Check if there are paginated results even without a count header
                        max_pg = _parse_max_page(html)
                        if max_pg > 1:
                            # Has multiple pages but no count text — estimate conservatively
                            item_count = max_pg * 50
                        else:
                            # No count and no extra pages — truly empty category
                            item_count = 0
                            max_pg = 0
                    total_products += item_count

                    # For image-tile sections the index page yields no text label —
                    # read the real name from the product listing page header instead.
                    if label == ddcode or not label:
                        real_label = _parse_category_label(html)
                        if real_label:
                            label = real_label
                            print(f"[allstate-discover] Resolved label for {ddcode}: {real_label}")

                    result_subcategories.append({
                        "ddcode": ddcode,
                        "label": label,
                        "section": section,
                        "item_count": item_count,
                        "max_pages": max_pg,
                    })
                    print(f"[allstate-discover] [{idx+1}/{len(all_subcategories)}] {section} > {label}: {item_count} items")
                    if progress_callback:
                        await progress_callback(
                            idx + 1, len(all_subcategories),
                            f"Counted {section} › {label} — {item_count:,} products",
                            milestone_event="category_found",
                            category_info={
                                "name": f"{section} › {label}" if section else label,
                                "slug": ddcode,
                                "section": section,
                                "total": item_count,
                            },
                        )
                except Exception as e:
                    print(f"[allstate-discover] Error on {ddcode}: {e}")

            # ✅ Milestone: all categories counted
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
                "category_name": f"{s['section']} › {s['label']}" if s.get('section') else s['label'],
                "category_slug_or_url": s["ddcode"],
                "product_count": s.get("item_count"),
            }
            for s in result_subcategories
        ]
        await save_category_index(supplier_id, SCRAPER_KEY, index_entries)
        print(f"[allstate-discover] Category index saved ({len(index_entries)} rows)")

    print(f"[allstate-discover] Done. {total_products:,} total products across {len(result_subcategories)} subcategories")
    return {"subcategories": result_subcategories, "total_products": total_products, "from_cache": False}


async def scrape_allstate(
    username: str,
    password: str,
    max_products: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
    subcategories: Optional[list] = None,
    supplier_id: Optional[int] = None,
) -> AsyncGenerator[ScrapedProduct, None]:
    """Phase 2: Log in to Allstate Floral and yield ScrapedProduct objects.

    If subcategories list is provided (from discover pass), skips the
    discovery step and uses those directly.

    Uses the /design/ category grid to extract SKU, price, UOM, photo, and
    description from listing pages — no individual detail page visits needed.
    Estimated runtime: ~20 minutes for all 20k+ products.

    Args:
        username: Allstate trade account number (e.g. 713FLV)
        password: Allstate account password
        max_products: Stop after this many products (None = all)
        progress_callback: async callable(done, total, message, *, category_slug, category_collected)
        subcategories: Pre-discovered list from discover_allstate_catalog
        supplier_id: Used for category index verification after scrape
    """
    from playwright.async_api import async_playwright

    cap = max_products or MAX_PRODUCTS
    total_yielded = 0
    seen_skus: set[str] = set()

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
            print("[allstate] Logging in...")
            await _do_login(page, username, password)

            # Use pre-discovered subcategories if provided, else discover now
            all_subcategories: list[dict] = []
            if subcategories:
                def _has_known_products(sub: dict) -> bool:
                    raw_count = sub.get("item_count", sub.get("total"))
                    if raw_count is None:
                        return True
                    try:
                        return int(raw_count) > 0
                    except (TypeError, ValueError):
                        return True

                all_subcategories = [sub for sub in subcategories if _has_known_products(sub)]
                skipped = len(subcategories) - len(all_subcategories)
                skip_note = f" ({skipped} zero-count skipped)" if skipped else ""
                print(f"[allstate] Using {len(all_subcategories)} pre-discovered subcategories{skip_note}")
            else:
                for section_name, clcd, section_url in CATALOG_SECTIONS:
                    print(f"[allstate] Discovering subcategories: {section_name}")
                    try:
                        html = await _safe_goto(page, section_url, username, password)
                        subs = _extract_subcategories(html)
                        if not subs:
                            alt_url = f"{DESIGN_INDEX}?CL=1&CLCD={clcd}&SubCodeIMG=y"
                            html = await _safe_goto(page, alt_url, username, password)
                            subs = _extract_subcategories(html)
                        for s in subs:
                            s["section"] = section_name
                        all_subcategories.extend(subs)
                        print(f"[allstate]   {section_name}: {len(subs)} subcategories")
                        await polite_delay(REQUEST_DELAY)
                    except Exception as e:
                        print(f"[allstate] Failed to load section {section_name}: {e}")

                print(f"[allstate] Total subcategories discovered: {len(all_subcategories)}")
                if progress_callback:
                    await progress_callback(0, cap, f"Found {len(all_subcategories)} subcategories. Starting product scrape...")

            # Walk each subcategory and yield products
            for sub_idx, sub in enumerate(all_subcategories):
                if total_yielded >= cap:
                    break

                ddcode = sub["ddcode"]
                label = sub.get("label", ddcode)
                section = sub.get("section", "")
                base_url = _listing_url_from_subcategory(sub)

                print(f"[allstate] [{sub_idx+1}/{len(all_subcategories)}] {section} > {label or ddcode}")

                try:
                    # Load first page — item_count from HTML is capped at 200/250
                    # by Allstate and cannot be trusted for pagination.
                    # We paginate until a page returns 0 products instead.
                    html = await _safe_goto(page, _append_page_param(base_url, 1), username, password)
                    await polite_delay(REQUEST_DELAY)

                    # Use displayed count only as a rough UI estimate
                    item_count = _parse_item_count(html)
                    print(f"[allstate]   ~{item_count} items displayed (may be capped) — paginating until empty")

                    cat_yielded = 0  # products collected for this subcategory
                    pg = 0
                    while True:
                        pg += 1
                        if total_yielded >= cap:
                            break

                        if pg > 1:
                            html = await _safe_goto(page, _append_page_param(base_url, pg), username, password)
                            await polite_delay(REQUEST_DELAY)

                        page_products = _parse_design_listing_page(html, section, label)

                        # Stop when the page comes back empty — true end of category
                        if not page_products:
                            print(f"[allstate]   Page {pg} empty — category done ({cat_yielded} collected)")
                            break
                        for p in page_products:
                            if total_yielded >= cap:
                                break
                            if p["sku"] in seen_skus:
                                continue
                            seen_skus.add(p["sku"])
                            total_yielded += 1
                            cat_yielded += 1
                            detail: dict = {}
                            try:
                                detail = await _fetch_detail_for_listing_product(page, username, password, p["sku"])
                                await polite_delay(REQUEST_DELAY)
                            except Exception as detail_err:
                                print(f"[allstate]   Detail fetch failed for {p['sku']}: {detail_err}")
                                detail = {"raw": {"detail_error": str(detail_err)}}

                            raw_data = {
                                **(detail.get("raw") or {}),
                                "allstate_ddcode": ddcode,
                                "allstate_section": section,
                                "allstate_subcategory": label,
                                "listing_url": _append_page_param(base_url, pg),
                            }

                            yield ScrapedProduct(
                                sku=p["sku"],
                                name=detail.get("description") or p["name"],
                                base_price=detail.get("base_price") if detail.get("base_price") is not None else p.get("base_price"),
                                uom=detail.get("uom") or p.get("uom", "EA"),
                                photo_url=p.get("photo_url"),
                                category=p.get("category", "other"),
                                description=detail.get("description") or p.get("name", ""),
                                moq=detail.get("moq"),
                                box_qty=detail.get("box_qty"),
                                case_qty=detail.get("case_qty"),
                                availability=detail.get("availability"),
                                availability_note=detail.get("availability_note"),
                                upc=detail.get("upc"),
                                length_in=detail.get("length_in"),
                                weight_lb=detail.get("weight_lb"),
                                material=detail.get("material"),
                                color=detail.get("color"),
                                country_of_origin=detail.get("country_of_origin"),
                                raw=raw_data,
                            )

                            if progress_callback and (cat_yielded % 25 == 0):
                                pct_subs = (sub_idx + 1) / max(len(all_subcategories), 1)
                                estimated_total = min(int(total_yielded / max(pct_subs, 0.01)), cap)
                                await progress_callback(
                                    total_yielded, estimated_total,
                                    f"{section} › {label} — {total_yielded:,} products so far (page {pg})",
                                    category_slug=ddcode,
                                    category_collected=cat_yielded,
                                )

                    # Done with this subcategory — send final count
                    if progress_callback and cat_yielded > 0:
                        pct_subs = (sub_idx + 1) / max(len(all_subcategories), 1)
                        estimated_total = min(int(total_yielded / max(pct_subs, 0.01)), cap)
                        await progress_callback(
                            total_yielded, estimated_total,
                            f"{section} › {label} — done ({cat_yielded:,} collected)",
                            category_slug=ddcode,
                            category_collected=cat_yielded,
                        )

                except Exception as e:
                    print(f"[allstate] Error on subcategory {ddcode}: {e}")
                    continue

        finally:
            await browser.close()
            print(f"[allstate] Browser closed. Total products yielded: {total_yielded}")

    # ── Post-scrape: verify index against live top-level sections ──────────────
    # Runs a quick section crawl to detect new/removed categories added since
    # the index was built, then updates last_verified_at for existing slugs.
    if supplier_id is not None and all_subcategories and subcategories is None:
        live_slugs = [s["ddcode"] for s in all_subcategories]
        try:
            verify_result = await verify_category_index(supplier_id, "allstate", live_slugs)
            print(f"[allstate] Category index verified: {verify_result}")
        except Exception as ve:
            print(f"[allstate] Category index verify failed (non-fatal): {ve}")


async def enrich_product_detail(
    username: str,
    password: str,
    sku: str,
) -> Optional[dict]:
    """Fetch and parse the detail page for a single product SKU.

    Returns a dict of extra fields: dimensions, UPC, color, country_of_origin, etc.
    Used for Phase 2 (background detail enrichment).
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await _do_login(page, username, password)
            url = f"{DETAIL_BASE_URL}?ItemNumber={sku}&Banner=1"
            html = await _safe_goto(page, url, username, password)

            soup = BeautifulSoup(html, "html.parser")
            raw: dict = {}
            for row in soup.find_all("tr"):
                cells = row.find_all(["td", "th"])
                i = 0
                while i < len(cells) - 1:
                    label = cells[i].get_text(strip=True).rstrip(":").strip()
                    value = cells[i + 1].get_text(strip=True)
                    if label and len(label) < 40:
                        raw[label] = value
                        i += 2
                    else:
                        i += 1

            # Parse dimensions
            height = parse_dimension(raw.get("ProdHeight") or raw.get("Height") or "")
            width = parse_dimension(raw.get("ProdWidth") or raw.get("Width") or "")
            length = parse_dimension(raw.get("ProdLength") or raw.get("Length") or "")
            weight = parse_dimension(raw.get("ProdWeight") or raw.get("Weight") or "")
            diameter = parse_dimension(raw.get("Diameter") or "")

            return {
                "upc": raw.get("UPC"),
                "color": raw.get("ColorGrp") or raw.get("Color Group") or raw.get("Color"),
                "country_of_origin": raw.get("Country of Origin"),
                "height_in": height,
                "width_in": width,
                "length_in": length,
                "weight_lb": weight,
                "diameter_in": diameter,
                "moq": safe_int(raw.get("MinQty") or raw.get("Min Qty")),
                "raw": raw,
            }
        finally:
            await browser.close()


async def enrich_allstate_details(
    username: str,
    password: str,
    skus: list[str],
    progress_callback: Optional[Callable] = None,
) -> AsyncGenerator[tuple[str, dict], None]:
    """Fetch Allstate detail pages for many SKUs in one browser session."""
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
            await _do_login(page, username, password)
            cookie_headers = _build_cookie_header(await context.cookies())
            total = len(skus)
            for idx, sku in enumerate(skus, start=1):
                try:
                    detail = await _fetch_detail_for_listing_product(page, username, password, sku)
                except Exception as exc:
                    print(f"[allstate-detail] Failed for {sku}: {exc}")
                    detail = {"raw": {"detail_error": str(exc)}}
                if cookie_headers:
                    detail["download_headers"] = cookie_headers
                if progress_callback:
                    await progress_callback(idx, total, f"Fetched details for {idx:,}/{total:,} ({sku})")
                yield sku, detail
                await polite_delay(REQUEST_DELAY)
        finally:
            await browser.close()


async def build_allstate_session_headers(username: str, password: str) -> dict[str, str]:
    """Log in once and return authenticated request headers for image downloads."""
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
            await _do_login(page, username, password)
            return _build_cookie_header(await context.cookies())
        finally:
            await browser.close()
