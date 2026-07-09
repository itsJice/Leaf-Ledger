"""Crawl every Vickerman top-nav header's listings via the DoSearch endpoint.

Purpose: coverage verification and header mapping. Every product visible
under any header/subcategory listing is recorded with the header it was
listed under, so the export can prove that all listed products are
represented and tag each SKU with where it appears on the site.

Listings are fetched with ``availableFilter=all`` (superset of what the
site shows by default); the default "Available" total is also recorded per
subcategory so on-site numbers can be reconciled.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from catalog_extraction.vickerman_http import BASE, login, make_session

# Top-nav headers in on-site order -> landing page for each header.
HEADERS = [
    ("Christmas Trees", "/productselector/christmas-trees/quick-lit"),
    ("Silk Trees and Florals", "/productselector/everyday/boxwood-trees-topiaries"),
    ("Natural", "/productselector/natural-botanicals/all"),
    ("Accent Pieces", "/productselector/accent-pieces/candle-holders"),
    ("Lights", "/productselector/lights/decorative"),
    ("Wreaths", "/productselector/wreaths/berry-wreaths"),
    ("Garlands", "/productselector/garland/berry-garlands"),
    ("Ornaments", "/productselector/ornament/all-ornaments"),
    ("Topiaries", "/productselector/topiary/topiary"),
    ("Stems", "/productselector/sprays/everyday-stems"),
    ("Commercial Décor", "/productselector/commercial-decor/bows"),
    ("New Items", "/productselector/new/all-new"),
    ("Textiles", "/productselector/textiles/pillows"),
    ("Pre-Decorated", "/productselector/pre-decorated/pre-decorated"),
    ("Containers", "/productselector/containers/containers"),
    ("Sale Items", "/productselector/sale-items/all-items"),
    ("Categories", "/productselector/categories/all-categories"),
    ("Seasons", "/productselector/seasons/easter"),
]

DOSEARCH = f"{BASE}/April.Vickerman.Commerce/ProductSelector/DoSearch"
PRODUCT_TYPE_RE = re.compile(r'name="product_type"[^>]*value="([^"]*)"')
TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')
ITEM_RE = re.compile(r"details\?item=([A-Za-z0-9\-\.]+)")
TOTAL_RE = re.compile(r"Total items found:\s*([\d,]+)")
PAGES_RE = re.compile(r"page \d+ of (\d+)")

REQUEST_DELAY_SECONDS = 0.2


def _subcategories_for_header(html: str, section: str) -> list[str]:
    """All /productselector/<section>/<sub> paths linked from a header page."""
    paths = []
    seen = set()
    for path in re.findall(rf'href="(/productselector/{re.escape(section)}/[a-z0-9\-]+)["?]', html):
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _do_search(session: requests.Session, referer: str, product_type: str,
               token: str, page_indx: int, available_filter: str) -> str:
    response = session.post(
        DOSEARCH,
        data={
            "product_type": product_type,
            "page_indx": str(page_indx),
            "sort": "",
            "search_box": "",
            "availableFilter": available_filter,
            "__RequestVerificationToken": token,
        },
        headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"},
        timeout=45,
    )
    response.raise_for_status()
    return response.text


def crawl_subcategory(session: requests.Session, path: str, log=print) -> dict:
    url = BASE + path
    page = session.get(url, timeout=45)
    product_type = (PRODUCT_TYPE_RE.search(page.text) or [None, ""])[1]
    token_match = TOKEN_RE.search(page.text)
    if not token_match:
        return {"path": path, "error": "no token/form", "skus": []}
    token = token_match.group(1)

    # default-filter total for reconciliation with on-site numbers
    first_available = _do_search(session, url, product_type, token, 1, "available")
    total_available = (TOTAL_RE.search(first_available) or [None, "0"])[1]

    skus: list[str] = []
    seen: set[str] = set()
    first = _do_search(session, url, product_type, token, 1, "all")
    total_all = (TOTAL_RE.search(first) or [None, "0"])[1]
    page_count = int((PAGES_RE.search(first) or [None, "1"])[1])
    for sku in ITEM_RE.findall(first):
        if sku not in seen:
            seen.add(sku)
            skus.append(sku)

    for page_indx in range(2, page_count + 1):
        time.sleep(REQUEST_DELAY_SECONDS)
        html = _do_search(session, url, product_type, token, page_indx, "all")
        for sku in ITEM_RE.findall(html):
            if sku not in seen:
                seen.add(sku)
                skus.append(sku)

    return {
        "path": path,
        "product_type": product_type,
        "total_available": int(total_available.replace(",", "")),
        "total_all": int(total_all.replace(",", "")),
        "pages": page_count,
        "skus": skus,
    }


def crawl_all_headers(output_path: Path, log=print) -> dict:
    session = make_session()
    login(session)

    results: dict = {"headers": [], "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    existing: dict[str, dict] = {}
    if output_path.exists():
        for header in json.loads(output_path.read_text(encoding="utf-8")).get("headers", []):
            for sub in header.get("subcategories", []):
                if sub.get("skus") and not sub.get("error"):
                    existing[sub["path"]] = sub

    for header_name, landing in HEADERS:
        section = landing.split("/")[2]
        page = session.get(BASE + landing, timeout=45)
        subs = _subcategories_for_header(page.text, section)
        if landing.split("?")[0] not in subs:
            subs.insert(0, landing)
        header_record = {"header": header_name, "section": section, "subcategories": []}
        for path in subs:
            if path in existing:
                record = existing[path]
            else:
                try:
                    record = crawl_subcategory(session, path, log=log)
                except requests.RequestException as exc:
                    record = {"path": path, "error": repr(exc), "skus": []}
                log(
                    f"{header_name} :: {path} -> "
                    f"available={record.get('total_available', '?')} "
                    f"all={record.get('total_all', '?')} skus={len(record['skus'])}"
                )
            header_record["subcategories"].append(record)
            output_path.write_text(
                json.dumps({**results, "headers": results["headers"] + [header_record]},
                           ensure_ascii=False),
                encoding="utf-8",
            )
        results["headers"].append(header_record)

    output_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    return results
