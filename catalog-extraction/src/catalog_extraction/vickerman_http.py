"""Vickerman full-catalog extraction over HTTP.

Product detail pages embed a complete JSON model (``var model = {...}``)
containing SKU, UPC, descriptions, product type, prices (when logged in),
quantities, stock, product and package dimensions, material, warranty, and
all image URLs. That means the full catalog can be pulled with a logged-in
requests session — no browser per product page.

Discovery uses the official product sitemap (https://vickerman.com/
sitemap-products.xml, ~22k items; robots.txt allows crawling). Category and
subcategory come from each item's own ``Category`` field, so listing pages
never need to be paginated.

Per the Vickerman onboarding notes, the run is split into bounded,
idempotent, checkpointed stages:

1. discover  -> outputs/vickerman-full/items.json (all product URLs)
2. details   -> outputs/vickerman-full/details.ndjson (one line per item,
                appended as fetched; already-fetched SKUs are skipped, so
                the stage is resumable after any interruption)
3. export    -> products.xlsx / products.csv / products.json / run_report.json
                (raw model preserved in products.json and details.ndjson;
                spreadsheet columns follow SUPPLIER_CONNECTOR_CONTRACT.md)
"""

from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

BASE = "https://www.vickerman.com"
SITEMAP_PRODUCTS = "https://vickerman.com/sitemap-products.xml"
LOGIN_URL = f"{BASE}/Users/Account/LogOn"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

WORKERS = 6
REQUEST_DELAY_SECONDS = 0.15
MODEL_RE = re.compile(r"var model = (\{.*?\});\s*\n", re.S)
TOKEN_RE = re.compile(
    r'<form action="/Users/Account/LogOn".*?name="__RequestVerificationToken"[^>]*value="([^"]+)"',
    re.S,
)


class LoginError(RuntimeError):
    pass


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def login(session: requests.Session) -> None:
    username = os.environ.get("VICKERMAN_USERNAME", "")
    password = os.environ.get("VICKERMAN_PASSWORD", "")
    if not (username and password):
        raise LoginError("VICKERMAN_USERNAME / VICKERMAN_PASSWORD not set")

    page = session.get(LOGIN_URL, timeout=30)
    token = TOKEN_RE.search(page.text)
    if not token:
        raise LoginError("could not find login verification token")
    result = session.post(
        LOGIN_URL,
        data={
            "userNameOrEmail": username,
            "password": password,
            "rememberMe": "false",
            "__RequestVerificationToken": token.group(1),
        },
        timeout=30,
    )
    if "/Users/Account/LogOff" not in result.text:
        raise LoginError("login failed — check credentials")


def fetch_product_urls(session: requests.Session) -> list[str]:
    response = session.get(SITEMAP_PRODUCTS, timeout=120)
    response.raise_for_status()
    urls: list[str] = []
    seen: set[str] = set()
    for loc in re.findall(r"<loc>([^<]+)</loc>", response.text):
        loc = loc.strip()
        item = (parse_qs(urlparse(loc).query).get("item") or [""])[0]
        if item and item.upper() != "INVALIDSKU" and item not in seen:
            seen.add(item)
            urls.append(f"{BASE}/products/details?item={item}")
    return urls


def extract_model(html: str) -> dict | None:
    match = MODEL_RE.search(html) or re.search(r"var model = (\{.*\});", html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def fetch_detail(session: requests.Session, url: str) -> dict:
    """Fetch one product page; returns a checkpoint record."""
    item = (parse_qs(urlparse(url).query).get("item") or [""])[0]
    record: dict = {"sku": item, "url": url}
    response = session.get(url, timeout=45)
    if response.status_code != 200:
        record.update(ok=False, error=f"HTTP {response.status_code}")
        return record
    if "/Users/Account/LogOff" not in response.text:
        record.update(ok=False, error="SESSION_EXPIRED")
        return record
    model = extract_model(response.text)
    current = (model or {}).get("CurrentItem")
    if not current or not current.get("ItemNumber"):
        record.update(ok=False, error="NO_MODEL")
        return record
    record.update(ok=True, model=model)
    return record


class _SharedAuth:
    """One login shared by all workers; re-login is serialized."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.generation = 0
        self.cookies: dict[str, str] = {}

    def ensure(self, known_generation: int) -> int:
        with self.lock:
            if self.generation == known_generation:
                session = make_session()
                login(session)
                self.cookies = session.cookies.get_dict()
                self.generation += 1
            return self.generation


def _worker_fetch(url: str, local: threading.local, auth: _SharedAuth) -> dict:
    session = getattr(local, "session", None)
    if session is None:
        session = make_session()
        local.session = session
        local.generation = 0
    if getattr(local, "generation", 0) != auth.generation:
        with auth.lock:
            session.cookies.update(auth.cookies)
            local.generation = auth.generation

    last_error: dict = {}
    for attempt in range(3):
        time.sleep(REQUEST_DELAY_SECONDS + random.uniform(0, 0.1) + attempt * 2)
        try:
            record = fetch_detail(session, url)
        except requests.RequestException as exc:
            last_error = {
                "sku": (parse_qs(urlparse(url).query).get("item") or [""])[0],
                "url": url,
                "ok": False,
                "error": repr(exc),
            }
            continue
        if record.get("error") == "SESSION_EXPIRED":
            local.generation = auth.ensure(local.generation)
            with auth.lock:
                session.cookies.update(auth.cookies)
            last_error = record
            continue
        return record
    return last_error


def run_details_stage(
    urls: list[str],
    checkpoint_path: Path,
    *,
    limit: int | None = None,
    progress_every: int = 250,
    log=print,
) -> dict:
    """Fetch details for every URL not already in the checkpoint (resumable)."""
    done: set[str] = set()
    if checkpoint_path.exists():
        with checkpoint_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("ok"):
                    done.add(row["sku"])

    pending = [u for u in urls if (parse_qs(urlparse(u).query).get("item") or [""])[0] not in done]
    if limit:
        pending = pending[: max(0, limit - len(done))]
    log(f"details: {len(done)} already fetched, {len(pending)} to fetch")

    local = threading.local()
    auth = _SharedAuth()
    auth.ensure(0)  # single login up front, shared by all workers
    write_lock = threading.Lock()
    counts = {"ok": 0, "error": 0}
    started = time.monotonic()

    with checkpoint_path.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(_worker_fetch, url, local, auth): url for url in pending}
            for index, future in enumerate(as_completed(futures), 1):
                url = futures[future]
                try:
                    record = future.result()
                except Exception as exc:
                    item = (parse_qs(urlparse(url).query).get("item") or [""])[0]
                    record = {"sku": item, "url": url, "ok": False, "error": repr(exc)}
                record["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                counts["ok" if record.get("ok") else "error"] += 1
                with write_lock:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out.flush()
                if index % progress_every == 0:
                    rate = index / max(1e-9, time.monotonic() - started)
                    remaining = (len(pending) - index) / max(rate, 1e-9)
                    log(
                        f"details: {index}/{len(pending)} "
                        f"(ok={counts['ok']} err={counts['error']}, "
                        f"{rate:.1f}/s, ~{remaining / 60:.0f}m left)"
                    )
    return counts


def _image_urls(current: dict) -> tuple[str, list[str]]:
    primary = current.get("ImageUrl") or ""
    extra = [
        current[key]
        for key in (f"Image{n}Url" for n in range(1, 10))
        if current.get(key)
    ]
    return primary, extra


def _dimensions(current: dict) -> str:
    parts = []
    for label, key in (("L", "Length"), ("W", "Width"), ("H", "Height")):
        value = current.get(key)
        if value:
            parts.append(f'{label}{value:g}"')
    return " ".join(parts)


def _package_info(current: dict) -> tuple[str, str]:
    packages = current.get("Packages") or []
    dims, weights = [], []
    for pkg in packages:
        piece = []
        for label, key in (("L", "Length"), ("W", "Width"), ("H", "Height")):
            if pkg.get(key):
                piece.append(f'{label}{pkg[key]:g}"')
        if piece:
            dims.append(" ".join(piece))
        if pkg.get("Weight"):
            weights.append(f"{pkg['Weight']:g} lbs")
    return "; ".join(dims), "; ".join(weights)


def model_to_row(record: dict, *, supplier: str, season: str, run_id: str) -> dict:
    model = record["model"]
    current = model["CurrentItem"]

    category_full = current.get("Category") or ""
    category, _, subcategory = category_full.partition("/")

    price = current.get("Price")
    sale_price = current.get("SalePrice")
    if sale_price:
        current_price, price_label = sale_price, "portal_sale_price"
    elif price:
        current_price, price_label = price, "portal_price"
    else:
        current_price, price_label = "", ""

    primary_image, extra_images = _image_urls(current)
    box_dimensions, box_weight = _package_info(current)

    missing = []
    if current_price == "":
        missing.append("price")
    if not primary_image:
        missing.append("image")
    if not current.get("Upc"):
        missing.append("upc")
    if not _dimensions(current):
        missing.append("dimensions")
    if not (current.get("WebDescription") or current.get("Description")):
        missing.append("description")

    return {
        "supplier": supplier,
        "season": season,
        "sku": current.get("ItemNumber", ""),
        "upc": current.get("Upc") or "",
        "product_name": current.get("Description") or "",
        "web_name": current.get("WebDescriptionSummary") or "",
        "category": category.strip(),
        "subcategory": subcategory.strip(),
        "listed_under": "",  # filled at export time from the listings crawl
        "product_type": current.get("ProductType") or "",
        "description": current.get("WebDescription") or "",
        "price": current_price,
        "list_price": price if (sale_price and price) else "",
        "source_price_label": price_label,
        "uom": "",
        "moq": current.get("QtyMin") if current.get("QtyMin") is not None else "",
        "box_quantity": current.get("InnerPackQty") if current.get("InnerPackQty") is not None else "",
        "case_quantity": current.get("QtyPerPack") if current.get("QtyPerPack") is not None else "",
        "piece_count": current.get("PieceCount") if current.get("PieceCount") is not None else "",
        "availability": current.get("QtyAvailable") if current.get("QtyAvailable") is not None else "",
        "qty_in_stock": current.get("QtyInStock") if current.get("QtyInStock") is not None else "",
        "dimensions_in": _dimensions(current),
        "height_in": current.get("Height") if current.get("Height") is not None else "",
        "width_in": current.get("Width") if current.get("Width") is not None else "",
        "length_in": current.get("Length") if current.get("Length") is not None else "",
        "weight_lbs": current.get("Weight") if current.get("Weight") is not None else "",
        "box_dimensions_in": box_dimensions,
        "box_weight_lbs": box_weight,
        "color": current.get("Color") or current.get("LightColor") or "",
        "material": current.get("PrimaryMaterial") or "",
        "finish_style": current.get("VariationValue") or "",
        "country_of_origin": current.get("CountryOfOrigin") or "",
        "warranty": current.get("Warranty") or "",
        "image_url": primary_image,
        # one URL per column so each cell is individually clickable in Excel
        **{
            f"image_url_{n}": (extra_images[n - 2] if n - 2 < len(extra_images) else "")
            for n in range(2, 11)
        },
        "image_count": (1 if primary_image else 0) + len(extra_images),
        "video_url": current.get("Video") or "",
        "product_url": record.get("url", ""),
        "source_url": SITEMAP_PRODUCTS,
        "needs_review": "; ".join(missing),
        "extracted_at": record.get("fetched_at", ""),
        "run_id": run_id,
    }


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "upc", "product_name", "web_name",
    "category", "subcategory", "listed_under", "product_type", "description",
    "price", "list_price", "source_price_label", "uom", "moq",
    "box_quantity", "case_quantity", "piece_count",
    "availability", "qty_in_stock",
    "dimensions_in", "height_in", "width_in", "length_in", "weight_lbs",
    "box_dimensions_in", "box_weight_lbs",
    "color", "material", "finish_style", "country_of_origin", "warranty",
    "image_url",
    "image_url_2", "image_url_3", "image_url_4", "image_url_5", "image_url_6",
    "image_url_7", "image_url_8", "image_url_9", "image_url_10",
    "image_count", "video_url",
    "product_url", "source_url", "needs_review", "extracted_at", "run_id",
]
