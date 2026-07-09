#!/usr/bin/env python3
"""Regency International — full catalog via authenticated headless browser.

ShopSite Pro + custom PHP/AJAX. Prices are Customer-Group-#0 dealer prices that
ONLY render client-side (JS function Y() reads ss_field27 after an ss_reg login
cookie is present). Pure-HTTP replication fails (the server won't populate the
price-bearing quickview for curl, and the session isn't portable), so we drive a
real headless Chrome on this machine: log in with REGENCY_* creds (which sets
ss_reg + window.group="Customer Group #0"), then read the rendered prices.

Flow: login -> enumerate category .html pages from the nav -> per category,
load-more to the end -> read name/SKU/price/image/url from the DOM -> dedupe by
SKU -> export. Checkpointed to NDJSON per category so it resumes.
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

BASE = "https://www.regency-rib.com"
SUPPLIER = "Regency International"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "regency-full"
CATS_PATH = OUT_DIR / "categories.json"
PROD_PATH = OUT_DIR / "products.ndjson"   # one line per (category) scrape result

_SKU_RE = re.compile(r"SKU:\s*(\S+)")
_PRICE_RE = re.compile(r"\$[\d,]+\.\d{2}")


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def login(sb) -> bool:
    sb.open(f"{BASE}/login.html")
    sb.sleep(3)
    user = os.environ["REGENCY_USERNAME"]
    pw = os.environ["REGENCY_PASSWORD"]
    sb.execute_script(
        "var pw=document.querySelector('input[name=text1]');var f=pw.closest('form');"
        "f.querySelector('input[name=email1]').value=arguments[0];pw.value=arguments[1];"
        "f.requestSubmit?f.requestSubmit():f.submit();", user, pw)
    sb.sleep(6)
    group = sb.execute_script("return (window.group||'')+''")
    log(f"login: window.group={group!r}")
    return "customer group" in group.lower()


def enumerate_categories(sb) -> list[str]:
    sb.open(f"{BASE}/"); sb.sleep(5)
    hrefs = sb.execute_script(r"""
      var out=[];
      document.querySelectorAll('a[href]').forEach(function(a){
        var h=a.getAttribute('href')||'';
        if(/\.html$/.test(h) && !/login|account|faq|privacy|cart|register|contact|rep|about|policy|shipping|terms|catalog/i.test(h)){
          out.push(h.indexOf('http')===0?h:('""" + BASE + r"""/'+h.replace(/^\//,'')));
        }
      });
      return JSON.stringify(Array.from(new Set(out)));
    """)
    return json.loads(hrefs)


# One authenticated fetch of a skip-page; decode each tile's quickview and pull
# name / SKU / "as low as" price / quantity tiers / image / url. Runs in the page
# context (credentials:'include') so the server returns the priced quickview.
_BATCH_JS = r"""
var pageId=arguments[0], skip=arguments[1], done=arguments[2];
fetch('/get_products.php?init=1&skip='+skip+'&pageType=products&pageId='+pageId,{credentials:'include'})
 .then(function(r){return r.text();})
 .then(function(t){
   var out=[]; var host=document.createElement('div'); host.innerHTML=t;
   host.querySelectorAll('li[id^=product_]').forEach(function(li){
     var name=(li.querySelector('.name')||{}).textContent||'';
     if(!name.trim()) return;
     var txt=li.textContent||'';
     var sku=(txt.match(/SKU:\s*(\S+)/)||[])[1]||'';
     var a=li.querySelector('a[href*=".html"]'); var url=a?a.getAttribute('href'):'';
     var img=li.querySelector('img'); var src=img?(img.getAttribute('src')||img.getAttribute('data-src')||''):'';
     var qv=li.getAttribute('quickview')||'';
     var price='', tiers='';
     if(qv.length>10){
       var d=document.createElement('div');
       d.innerHTML=qv.replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&#39;/g,String.fromCharCode(39)).replace(/&lt;/g,'<').replace(/&gt;/g,'>');
       price=((d.querySelector('.price')||{}).textContent||'').trim();
       tiers=((d.querySelector('.qntyprice')||{}).textContent||'').trim();
       if(!src){var qi=d.querySelector('img'); if(qi) src=qi.getAttribute('src')||'';}
     }
     out.push({name:name.trim(), sku:sku.trim(), price:price, tiers:tiers, url:url, image:src});
   });
   done(JSON.stringify(out));
 })
 .catch(function(e){done(JSON.stringify({__err:String(e)}));});
"""


def scrape_category(sb, url: str) -> dict:
    sb.open(url); sb.sleep(3)
    meta = json.loads(sb.execute_script(
        "return JSON.stringify({total:(window.totalProducts||0)|0, pageId:(window.pageId||'')+''});"))
    total, page_id = meta.get("total", 0), meta.get("pageId", "")
    if not page_id:
        return {"url": url, "total": total, "products": [], "error": "no pageId"}
    sb.driver.set_script_timeout(45)
    collected: dict[str, dict] = {}
    skip = 0
    for _ in range(140):  # up to ~140 pages
        raw = sb.driver.execute_async_script(_BATCH_JS, page_id, skip)
        batch = json.loads(raw)
        if isinstance(batch, dict) and batch.get("__err"):
            break
        if not batch:
            break
        for p in batch:
            key = p.get("sku") or p.get("url") or p.get("name")
            collected.setdefault(key, p)
        skip += len(batch)
        if total and skip >= total:
            break
        if len(batch) < 40:  # last (short) page
            break
        time.sleep(0.3)
    return {"url": url, "total": total, "pageId": page_id, "products": list(collected.values())}


def stage_scrape(limit_categories: int | None) -> None:
    with SB(headless=True, browser="chrome") as sb:
        if not login(sb):
            raise RuntimeError("Regency login failed (window.group not set)")
        if CATS_PATH.exists():
            cats = json.loads(CATS_PATH.read_text())
        else:
            cats = enumerate_categories(sb)
            CATS_PATH.write_text(json.dumps(cats, indent=0))
        log(f"categories: {len(cats)}")
        done = set()
        if PROD_PATH.exists():
            for line in PROD_PATH.open(encoding="utf-8"):
                try:
                    done.add(json.loads(line)["url"])
                except (json.JSONDecodeError, KeyError):
                    pass
        pending = [c for c in cats if c not in done]
        if limit_categories:
            pending = pending[:limit_categories]
        log(f"scrape: {len(done)} categories done, {len(pending)} to go")
        with PROD_PATH.open("a", encoding="utf-8") as out:
            for i, url in enumerate(pending, 1):
                try:
                    rec = scrape_category(sb, url)
                except Exception as exc:  # noqa: BLE001
                    rec = {"url": url, "error": repr(exc), "products": []}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
                log(f"  [{i}/{len(pending)}] {url.rsplit('/',1)[-1]}: "
                    f"{len(rec.get('products', []))} products (total~{rec.get('total','?')})")


def _price_num(text: str):
    m = _PRICE_RE.findall(text or "")
    return float(m[0].replace("$", "").replace(",", "")) if m else ""


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name", "price", "price_label",
    "price_tiers", "source_price_label", "category_count", "image_url",
    "product_url", "source_url", "needs_review", "extracted_at", "run_id",
]


def stage_export(run_id: str) -> None:
    by_sku: dict[str, dict] = {}
    cat_count: dict[str, int] = {}
    for line in PROD_PATH.open(encoding="utf-8"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        for p in rec.get("products", []):
            sku = p.get("sku") or p.get("url") or p.get("name")
            if not sku:
                continue
            cat_count[sku] = cat_count.get(sku, 0) + 1
            if sku in by_sku:
                continue
            price = _price_num(p.get("price"))
            url = p.get("url") or ""
            if url and not url.startswith("http"):
                url = f"{BASE}/{url.lstrip('/')}"
            img = p.get("image") or ""
            if img and not img.startswith("http"):
                img = f"{BASE}/{img.lstrip('/')}"
            missing = []
            if price == "":
                missing.append("price")
            if not img:
                missing.append("image")
            by_sku[sku] = {
                "supplier": SUPPLIER, "season": SEASON,
                "sku": p.get("sku") or "",
                "product_name": p.get("name") or "",
                "price": price,
                "price_label": p.get("price") or "",
                "price_tiers": p.get("tiers") or "",
                "source_price_label": "dealer_login_price (Customer Group #0)" if price != "" else "",
                "category_count": 0,
                "image_url": img,
                "product_url": url,
                "source_url": BASE,
                "needs_review": "; ".join(missing),
                "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "run_id": run_id,
            }
    for sku, row in by_sku.items():
        row["category_count"] = cat_count.get(sku, 1)
    ordered = sorted(by_sku.values(), key=lambda r: (r["product_name"] or "zzz"))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    frame["sku"] = frame["sku"].fillna("").astype(str)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="regency-export-"))
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
        "needs_review_count": int((frame["needs_review"] != "").sum()),
        "pricing_note": "Customer Group #0 dealer prices, rendered via authenticated "
                        "headless browser (ss_field27). 'As low as' = starting/tier price.",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} unique products -> {OUT_DIR/'products.xlsx'} (priced={priced}, imaged={imaged})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["scrape", "export", "all"], default="all")
    ap.add_argument("--limit-categories", type=int, default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.stage in ("scrape", "all"):
        stage_scrape(args.limit_categories)
    if args.stage in ("export", "all"):
        stage_export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
