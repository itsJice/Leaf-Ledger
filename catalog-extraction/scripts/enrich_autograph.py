#!/usr/bin/env python3
"""Enrich Autograph Foliages with real prices (BigCommerce trade login).

Product pages display "Call for pricing", but BigCommerce's
`/remote/v1/product-attributes/{product_id}` endpoint returns the real price
for a logged-in dealer. Flow per product: fetch page -> product_id -> price API.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass

import pandas as pd
import requests

BASE = "https://autographfoliages.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT = ROOT / "outputs" / "autograph-full"
PRICES = OUT / "prices.ndjson"
WORKERS = 6
PID_RE = re.compile(r'data-product-id="(\d+)"|"product_id"\s*:\s*"?(\d+)|productId["\':\s]+(\d+)')


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def login() -> requests.Session:
    s = requests.Session(); s.headers["User-Agent"] = UA
    lp = s.get(f"{BASE}/login.php", timeout=30)
    at = re.search(r'name="authenticity_token"[^>]*value="([^"]+)"', lp.text)
    s.post(f"{BASE}/login.php?action=check_login", data={
        "authenticity_token": at.group(1) if at else "",
        "login_email": os.environ["AUTOGRAPH_USERNAME"], "login_pass": os.environ["AUTOGRAPH_PASSWORD"]},
        timeout=30, allow_redirects=True)
    if "logout" not in s.get(f"{BASE}/account.php", timeout=30).text.lower():
        raise RuntimeError("Autograph login failed")
    return s


def fetch_price(session, url, retries=3):
    last = None
    for attempt in range(retries):
        try:
            html = session.get(url, timeout=40).text
            m = PID_RE.search(html)
            pid = next((g for g in (m.groups() if m else []) if g), None)
            if not pid:
                return {"url": url, "ok": True, "price": "", "note": "no product_id"}
            r = session.post(f"{BASE}/remote/v1/product-attributes/{pid}",
                             data={"action": "add", "product_id": pid},
                             headers={"X-Requested-With": "XMLHttpRequest"}, timeout=30)
            pobj = ((r.json().get("data") or {}).get("price") or {})
            def _v(key):
                return (pobj.get(key) or {}).get("value", "") if isinstance(pobj.get(key), dict) else ""
            # without_tax = dealer/wholesale (what we pay); rrp_without_tax = retail list price
            return {"url": url, "ok": True, "product_id": pid,
                    "price": _v("without_tax"),
                    "list_price": _v("rrp_without_tax") or _v("sale_price_without_tax"),
                    "saved": _v("saved")}
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(1.5 + attempt * 2)
    return {"url": url, "ok": False, "error": repr(last)}


def stage_fetch(limit):
    df = pd.read_excel(OUT / "products.xlsx")
    urls = df["product_url"].dropna().unique().tolist()
    if limit:
        urls = urls[:limit]
    done = set()
    if PRICES.exists():
        for line in PRICES.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("ok"):
                    done.add(r["url"])
            except json.JSONDecodeError:
                pass
    pending = [u for u in urls if u not in done]
    s = login()
    log(f"login OK; {len(done)} done, {len(pending)} to fetch")
    lock = threading.Lock(); counts = {"ok": 0, "err": 0, "priced": 0}
    with PRICES.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(fetch_price, s, u): u for u in pending}
            for i, f in enumerate(as_completed(futs), 1):
                r = f.result()
                counts["ok" if r.get("ok") else "err"] += 1
                if r.get("price") not in ("", None):
                    counts["priced"] += 1
                with lock:
                    out.write(json.dumps(r, ensure_ascii=False) + "\n"); out.flush()
                if i % 250 == 0:
                    log(f"{i}/{len(pending)} (priced={counts['priced']} err={counts['err']})")
    log(f"done (ok={counts['ok']} priced={counts['priced']} err={counts['err']})")


def stage_merge():
    prices, list_prices = {}, {}
    for line in PRICES.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("ok") and r.get("price") not in ("", None):
            prices[r["url"]] = r["price"]
        if r.get("ok") and r.get("list_price") not in ("", None):
            list_prices[r["url"]] = r["list_price"]
    df = pd.read_excel(OUT / "products.xlsx")
    df["price"] = df["product_url"].map(prices)                 # dealer / wholesale (what we pay)
    df["list_price"] = df["product_url"].map(list_prices)       # retail list price (RRP)
    df["source_price_label"] = df["price"].apply(lambda v: "dealer_login_price" if pd.notna(v) else "")
    df["list_price_label"] = df["list_price"].apply(lambda v: "retail_rrp" if pd.notna(v) else "")
    # margin the dealer gets off retail: (list - dealer) / list
    def _margin(row):
        d, l = row["price"], row["list_price"]
        if pd.notna(d) and pd.notna(l) and l:
            return round((l - d) / l * 100, 1)
        return ""
    df["margin_pct_off_retail"] = df.apply(_margin, axis=1)
    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp())
    df.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    df.to_csv(tmp / "products.csv", index=False)
    for n in ("products.xlsx", "products.csv"):
        shutil.move(str(tmp / n), str(OUT / n))
    shutil.rmtree(tmp, ignore_errors=True)
    filled = int(df["price"].notna().sum())
    listed = int(df["list_price"].notna().sum())
    log(f"merge: {filled}/{len(df)} priced, {listed}/{len(df)} with list price -> {OUT / 'products.xlsx'}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=["fetch", "merge", "all"], default="all")
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args()
    if a.stage in ("fetch", "all"):
        stage_fetch(a.limit)
    if a.stage in ("merge", "all"):
        stage_merge()


if __name__ == "__main__":
    main()
