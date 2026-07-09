"""Accent Decor (accentdecor.com) full-catalog extraction over HTTP.

Accent Decor is a trade-only Magento 2 site: the storefront catalog and prices
are fully gated behind a dealer login, and Magento's own product-listing GraphQL
resolver is broken server-side (every product query throws "Internal server
error"). The product grid is actually rendered by **Klevu** (a third-party
search service), whose JSON search API is the real data channel — and it is
public with the store's Klevu API key (no Magento login needed for the data).

Discovery (done once, recorded here):
- Platform = Magento 2; grid powered by Klevu (js.klevu.com in the page).
- Klevu API key `klevu-166375275531315628` is embedded in the page HTML.
- Klevu shards stores by region; the correct host was captured from the
  browser's own request: `https://eucs30v2.ksearchnet.com/cs/v2/search`.
- A `term:"*"` SEARCH over `KLEVU_PRODUCT` returns the whole catalog
  (`totalResultsFound` = 2,274), 100 records/page via offset.

Each record: `sku` is a composite `{realSKU};;;;{internal}` — the real Magento
SKU is the part before `;;;;` (verified against the product page's ld+json).
Also: name, price (regular), salePrice (current), currency, inStock, url,
imageUrl (one; more images live on the product page), category (";;"-joined
list), weight, itemGroupId (variant grouping).
"""

from __future__ import annotations

import html as html_lib
import json
import re
import time
from pathlib import Path

import requests

BASE = "https://www.accentdecor.com"
KLEVU_KEY = "klevu-166375275531315628"
KLEVU_HOST = "https://eucs30v2.ksearchnet.com/cs/v2/search"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
PAGE_SIZE = 100
REQUEST_DELAY_SECONDS = 0.2
GENERIC_CATS = {"NEW", "VIEW ALL", "SHOP ALL", "ALL FLOWER", "ALL PLANT",
                "NEW TO SALE", "SALE", "IN STOCK", "IN STOCK NEW", "BEST SELLERS"}


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT, "Content-Type": "application/json",
        "Origin": BASE, "Referer": BASE + "/",
    })
    return session


# ---- Enrichment: logged-in product pages (authoritative price + images + desc) ----

import os

_FORMKEY_RE = re.compile(r'name="form_key"\s+value="([^"]+)"')
_FINALPRICE_RE = re.compile(r'"finalPrice"\s*:\s*\{\s*"amount"\s*:\s*"?([\d.]+)')
_LDJSON_RE = re.compile(r'<script type="application/ld\+json">\s*(\{(?:[^<]|<(?!/script))*?"@type"\s*:\s*"Product".*?)</script>', re.S)


class LoginError(RuntimeError):
    pass


def login_web(session: requests.Session) -> bool:
    """Magento customer web-session login (needed so pages show dealer prices)."""
    u = os.environ.get("ACCENTDECOR_USERNAME", "")
    p = os.environ.get("ACCENTDECOR_PASSWORD", "")
    if not (u and p):
        raise LoginError("ACCENTDECOR_USERNAME / ACCENTDECOR_PASSWORD not set in .env")
    # this session posts form data, not JSON
    web = session
    lp = web.get(f"{BASE}/customer/account/login/", timeout=30,
                 headers={"Content-Type": None})
    fk = _FORMKEY_RE.search(lp.text)
    web.post(f"{BASE}/customer/account/loginPost/",
             data={"form_key": fk.group(1) if fk else "",
                   "login[username]": u, "login[password]": p, "send": ""},
             headers={"Referer": lp.url, "Content-Type": "application/x-www-form-urlencoded"},
             timeout=30)
    ok = "customer/account/logout" in web.get(f"{BASE}/customer/account/", timeout=30).text
    if not ok:
        raise LoginError("Accent Decor web login failed")
    return ok


def make_web_session() -> requests.Session:
    """Plain session (form headers) for storefront page fetches."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def fetch_detail(session: requests.Session, url: str, retries: int = 3) -> dict:
    """Fetch a product page (logged in); return authoritative price, images, description."""
    last = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=40)
            html = r.text
            # all distinct catalog product images on the page (full-size)
            imgs = []
            seen = set()
            for m in re.findall(r'https://cdn[^"\']*accentdecor\.com/media/catalog/product/[^"\'\s]+?\.(?:jpg|jpeg|png)', html):
                base = m.split("/cache/")[0] + "/" + m.split("/")[-1] if "/cache/" in m else m
                key = m.split("/")[-1]
                if key not in seen:
                    seen.add(key)
                    imgs.append(m)
            # authoritative dealer price(s) from the Magento price config
            finals = sorted({round(float(x), 2) for x in _FINALPRICE_RE.findall(html)})
            # full description from ld+json
            desc = ""
            ld = _LDJSON_RE.search(html)
            if ld:
                try:
                    desc = json.loads(ld.group(1)).get("description", "") or ""
                except json.JSONDecodeError:
                    pass
            return {"url": url, "ok": True,
                    "magento_price_min": finals[0] if finals else "",
                    "magento_price_max": finals[-1] if finals else "",
                    "images": imgs[:10],
                    "full_description": desc}
        except requests.RequestException as exc:
            last = exc
            time.sleep(1.5 + attempt * 2)
    return {"url": url, "ok": False, "error": repr(last)}


def _search(session: requests.Session, offset: int, retries: int = 4) -> dict:
    payload = {"context": {"apiKeys": [KLEVU_KEY]},
               "recordQueries": [{"id": "productList", "typeOfRequest": "SEARCH",
                                  "settings": {"query": {"term": "*"},
                                               "typeOfRecords": ["KLEVU_PRODUCT"],
                                               "limit": PAGE_SIZE, "offset": offset}}]}
    last = None
    for attempt in range(retries):
        try:
            r = session.post(KLEVU_HOST, json=payload, timeout=45)
            r.raise_for_status()
            return r.json()["queryResults"][0]
        except (requests.RequestException, KeyError, IndexError) as exc:
            last = exc
            time.sleep(1.5 + attempt * 2)
    raise last


def fetch_all(session: requests.Session, checkpoint_path: Path, *,
              limit: int | None = None, log=print) -> int:
    first = _search(session, 0)
    total = int(first.get("meta", {}).get("totalResultsFound", 0))
    target = min(total, limit) if limit else total
    log(f"fetch: {total} products total, fetching {target}")

    done: set[str] = set()
    if checkpoint_path.exists():
        with checkpoint_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue

    written = len(done)
    with checkpoint_path.open("a", encoding="utf-8") as out:
        offset = 0
        while offset < target:
            page = first if offset == 0 else _search(session, offset)
            records = page.get("records", [])
            if not records:
                break
            for rec in records:
                rid = rec.get("id")
                if not rid or rid in done:
                    continue
                done.add(rid)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
                if limit and written >= limit:
                    out.flush()
                    return written
            out.flush()
            offset += len(records)
            log(f"fetch: {min(offset, target)}/{target}")
            time.sleep(REQUEST_DELAY_SECONDS)
    return written


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _money(v) -> str:
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return ""


def _categories(raw: str) -> list[str]:
    seen, out = set(), []
    for c in (raw or "").split(";;"):
        c = c.strip()
        if c and c.upper() not in GENERIC_CATS and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def record_to_row(rec: dict, detail: dict | None, *, supplier: str, season: str,
                  run_id: str, fetched_at: str) -> dict:
    real_sku = (rec.get("sku") or "").split(";;;;")[0].strip()
    cats = _categories(rec.get("category", ""))
    klevu_reg = _money(rec.get("price"))
    klevu_sale = _money(rec.get("salePrice"))

    detail = detail or {}
    enriched = bool(detail.get("ok"))
    mag_min = detail.get("magento_price_min", "")
    mag_max = detail.get("magento_price_max", "")
    # authoritative price = logged-in Magento dealer price when we have it
    price = mag_min if enriched and mag_min != "" else ""

    images = detail.get("images") or []
    if not images and (rec.get("imageUrl") or rec.get("image")):
        images = [rec.get("imageUrl") or rec.get("image")]
    primary = images[0] if images else ""
    extras = images[1:10]
    description = _clean(detail.get("full_description") or rec.get("shortDesc") or "")

    missing = []
    if price == "":
        missing.append("price (enrich to resolve)" if not enriched else "price")
    if not primary:
        missing.append("image")
    if not real_sku:
        missing.append("sku")
    if not description:
        missing.append("description")

    return {
        "supplier": supplier,
        "season": season,
        "sku": real_sku or rec.get("id", ""),
        "product_name": _clean(rec.get("name") or ""),
        "category": cats[0] if cats else "",
        "listed_under": "; ".join(cats),
        "description": description,
        "price": price,
        "magento_price_min": mag_min,
        "magento_price_max": mag_max,
        "klevu_price": klevu_sale if klevu_sale != "" else klevu_reg,
        "klevu_regular_price": klevu_reg,
        "currency": rec.get("currency") or "USD",
        "source_price_label": "magento_dealer_price" if price != "" else "unverified",
        "availability": "in_stock" if str(rec.get("inStock")).lower() == "yes" else "out_of_stock",
        "weight_lbs": _money(rec.get("weight")) if rec.get("weight") else "",
        "item_group_id": rec.get("itemGroupId") or "",
        "image_url": primary,
        **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 11)},
        "image_count": len(images),
        "product_url": rec.get("url") or "",
        "source_url": rec.get("url") or KLEVU_HOST,
        "needs_review": "; ".join(missing),
        "extracted_at": fetched_at,
        "run_id": run_id,
        "klevu_id": rec.get("id", ""),
    }


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name",
    "category", "listed_under", "description",
    "price", "magento_price_min", "magento_price_max",
    "klevu_price", "klevu_regular_price", "currency", "source_price_label",
    "availability", "weight_lbs", "item_group_id",
    "image_url",
    "image_url_2", "image_url_3", "image_url_4", "image_url_5", "image_url_6",
    "image_url_7", "image_url_8", "image_url_9", "image_url_10",
    "image_count", "product_url", "source_url",
    "needs_review", "extracted_at", "run_id", "klevu_id",
]
