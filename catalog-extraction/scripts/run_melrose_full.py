#!/usr/bin/env python3
"""Melrose International — full catalog via the SoloVue B2B portal API.

melroseintl.com is only marketing; the wholesale catalog lives on the SoloVue
portal (melrose.solovue.com) — an ASP.NET + Vue SPA backed by a JSON API. Login
is trade-only (MELROSE_USERNAME/PASSWORD). After a genuine browser sign-in (the
Vue login needs input events + a button click, and sets .ASPXAUTH + UserToken/
AccessToken), the catalog comes from:
  /api/soloweb/GetCategories/?UserToken=..&AccessToken=..
  /api/soloweb/GetProductList/?ProductCategoryId=<id>&PageNumber=N&ReturnAllImages=true&..
GetProductList returns real quantity-tier WHOLESALE prices, images, and full
descriptions. We drive headless SeleniumBase (real login, same IP) and make the
API calls from the authenticated page context via fetch.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass

import pandas as pd
from seleniumbase import SB

PORTAL = "https://melrose.solovue.com"
SUPPLIER = "Melrose International"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "melrose-full"
PROD_PATH = OUT_DIR / "products.ndjson"

_SET_FIELDS = """
  function s(el,v){if(!el)return;el.focus();el.value=v;
    el.dispatchEvent(new Event('input',{bubbles:true}));
    el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();}
  s(document.querySelector('input[name=LogonEmail]'),arguments[0]);
  s(document.querySelector('input[name=LogonPassword]'),arguments[1]);
"""

# fetch a GetProductList page in the authed context; returns {Products, IsMoreProducts, TotalItems}
_FETCH_PAGE = r"""
var done=arguments[arguments.length-1];
var catId=arguments[0], page=arguments[1];
var u0=performance.getEntriesByType('resource').map(r=>r.name).find(u=>/UserToken=/.test(u));
if(!u0){ done(JSON.stringify({__noTokens:true})); return; }
var q=new URLSearchParams(new URL(u0).search);
var tok='UserToken='+encodeURIComponent(q.get('UserToken'))+'&AccessToken='+encodeURIComponent(q.get('AccessToken'));
var url='https://melrose.solovue.com/api/soloweb/GetProductList/?ProductCategoryId='+catId+
  '&DisplayOrder=Default&DisplayDescending=false&PageNumber='+page+
  '&SortModifier=ALL&ReturnAllImages=true&'+tok+'&ShoppingCartToken=&_='+Date.now();
fetch(url,{credentials:'include'}).then(r=>r.json()).then(function(d){
  done(JSON.stringify({Products:d.Products||[], IsMoreProducts:!!d.IsMoreProducts,
    TotalItems:d.TotalItems, TokenExpired:!!d.TokenExpired}));
}).catch(e=>done(JSON.stringify({__err:String(e)})));
"""

_FETCH_CATS = r"""
var done=arguments[arguments.length-1];
var u0=performance.getEntriesByType('resource').map(r=>r.name).find(u=>/UserToken=/.test(u));
if(!u0){ done(JSON.stringify({__noTokens:true})); return; }
var q=new URLSearchParams(new URL(u0).search);
var tok='UserToken='+encodeURIComponent(q.get('UserToken'))+'&AccessToken='+encodeURIComponent(q.get('AccessToken'));
fetch('https://melrose.solovue.com/api/soloweb/GetCategories/?'+tok+'&_='+Date.now(),{credentials:'include'})
 .then(r=>r.json()).then(d=>done(JSON.stringify(d))).catch(e=>done(JSON.stringify({__err:String(e)})));
"""


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def login(sb) -> bool:
    sb.open(f"{PORTAL}/home/index?ReturnUrl=%2fproduct"); sb.sleep(5)
    sb.execute_script(_SET_FIELDS, os.environ["MELROSE_USERNAME"], os.environ["MELROSE_PASSWORD"])
    sb.sleep(1)
    sb.execute_script("var b=Array.from(document.querySelectorAll('button,input,a'))"
                      ".find(x=>/log ?in/i.test((x.textContent||x.value||'')));if(b)b.click();")
    for _ in range(20):
        sb.sleep(1)
        if any(c["name"] == ".ASPXAUTH" for c in sb.get_cookies()):
            return True
    return False


def _collect_cat_ids(node, out):
    """Recursively collect every category Id from the GetCategories tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("Id", "CategoryId", "ProductCategoryId") and isinstance(v, int):
                out.add(v)
            else:
                _collect_cat_ids(v, out)
    elif isinstance(node, list):
        for it in node:
            _collect_cat_ids(it, out)


def scrape(limit_categories: int | None) -> None:
    with SB(headless=True, browser="chrome") as sb:
        if not login(sb):
            raise RuntimeError("Melrose SoloVue login failed (.ASPXAUTH not set)")
        log("login OK")
        sb.open(f"{PORTAL}/product"); sb.sleep(9)  # fires GetCategories → seeds tokens
        sb.driver.set_script_timeout(60)

        cats_raw = json.loads(sb.driver.execute_async_script(_FETCH_CATS))
        cat_ids: set[int] = set()
        _collect_cat_ids(cats_raw, cat_ids)
        cat_ids = sorted(cat_ids)
        log(f"categories: {len(cat_ids)} ids")
        if limit_categories:
            cat_ids = cat_ids[:limit_categories]

        done = set()
        if PROD_PATH.exists():
            for line in PROD_PATH.open(encoding="utf-8"):
                try:
                    done.add(json.loads(line)["cat"])
                except (json.JSONDecodeError, KeyError):
                    pass

        with PROD_PATH.open("a", encoding="utf-8") as out:
            for i, cid in enumerate(cat_ids, 1):
                if cid in done:
                    continue
                products, page = {}, 1
                while page <= 400:
                    raw = sb.driver.execute_async_script(_FETCH_PAGE, cid, page)
                    d = json.loads(raw)
                    if d.get("__noTokens") or d.get("__err") or d.get("TokenExpired"):
                        log(f"  cat {cid} page {page}: {d}")
                        break
                    for p in d.get("Products", []):
                        if p.get("Id") is not None:
                            products[p["Id"]] = p
                    if not d.get("IsMoreProducts"):
                        break
                    page += 1
                    time.sleep(0.2)
                out.write(json.dumps({"cat": cid, "products": list(products.values())}, ensure_ascii=False) + "\n")
                out.flush()
                if products:
                    log(f"  [{i}/{len(cat_ids)}] cat {cid}: {len(products)} products ({page} pages)")


def _price(p: dict):
    """Lowest tier wholesale price (real buyer price)."""
    prices = [x.get("Price") for x in (p.get("Prices") or []) if isinstance(x.get("Price"), (int, float)) and x.get("Price") > 0]
    return min(prices) if prices else ""


def _tiers(p: dict) -> str:
    return " | ".join(f"{x.get('Quantity')}{x.get('UnitDescription','')}: ${x.get('Price')}"
                      for x in (p.get("Prices") or []) if x.get("Price"))


def _images(p: dict) -> list[str]:
    out = []
    for im in (p.get("Images") or []):
        name = im.get("Filename") or im.get("Name") or im.get("Url") if isinstance(im, dict) else im
        if name:
            out.append(name if str(name).startswith("http") else f"{PORTAL}/images/product/{name}")
    if not out and p.get("MainImageName"):
        out.append(f"{PORTAL}/images/product/{p['MainImageName']}")
    return list(dict.fromkeys(out))


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "color", "product_name", "description",
    "price", "price_tiers", "list_price", "currency", "source_price_label",
    "available_qty", "availability", "image_url", "image_url_2", "image_url_3",
    "image_url_4", "image_count", "product_url", "source_url", "needs_review",
    "extracted_at", "run_id",
]


def export(run_id: str) -> None:
    by_id: dict = {}
    for line in PROD_PATH.open(encoding="utf-8"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        for p in rec.get("products", []):
            pid = p.get("Id")
            if pid is None or pid in by_id:
                continue
            imgs = _images(p)
            price = _price(p)
            sku = (str(p.get("Pnumber") or "").strip() or str(p.get("Id")))
            missing = []
            if price == "":
                missing.append("price")
            if not imgs:
                missing.append("image")
            by_id[pid] = {
                "supplier": SUPPLIER, "season": SEASON,
                "sku": sku, "color": (p.get("Detail") or "").strip(),
                "product_name": (p.get("Item") or p.get("Item2") or "").strip(),
                "description": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p.get("LongDescription") or "")).strip(),
                "price": price, "price_tiers": _tiers(p),
                "list_price": p.get("OriginalPrice1Amount") or "",
                "currency": "USD",
                "source_price_label": "dealer_login_price (wholesale, tiered)" if price != "" else "",
                "available_qty": p.get("AvailableQuantity") if p.get("AvailableQuantity") is not None else "",
                "availability": "discontinued" if p.get("IsDiscontinued") else ("inactive" if p.get("IsInactive") else "active"),
                "image_url": imgs[0] if imgs else "",
                **{f"image_url_{n}": (imgs[n - 1] if n - 1 < len(imgs) else "") for n in range(2, 5)},
                "image_count": len(imgs),
                "product_url": f"{PORTAL}/product",
                "source_url": f"{PORTAL}/api/soloweb/GetProductList",
                "needs_review": "; ".join(missing),
                "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "run_id": run_id,
            }
    ordered = sorted(by_id.values(), key=lambda r: (r["product_name"] or "zzz"))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    frame["sku"] = frame["sku"].fillna("").astype(str)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="melrose-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    for n in ("products.xlsx", "products.csv"):
        shutil.move(str(tmp / n), str(OUT_DIR / n))
    shutil.rmtree(tmp, ignore_errors=True)

    priced = int((frame["price"].astype(str).str.strip() != "").sum())
    imaged = int((frame["image_url"].astype(str).str.strip() != "").sum())
    report = {
        "supplier": SUPPLIER, "season": SEASON, "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_exported": len(frame), "with_price": priced, "with_image": imaged,
        "pricing_note": "Wholesale dealer prices (quantity-tiered) from the SoloVue "
                        "GetProductList API via authenticated headless browser.",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} products -> {OUT_DIR/'products.xlsx'} (priced={priced}, imaged={imaged})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["scrape", "export", "all"], default="all")
    ap.add_argument("--limit-categories", type=int, default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.stage in ("scrape", "all"):
        scrape(args.limit_categories)
    if args.stage in ("export", "all"):
        export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
