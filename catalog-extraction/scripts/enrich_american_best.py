#!/usr/bin/env python3
"""Enrich the American Best catalog with real prices (nopCommerce trade login).

The base scrape captured everything except prices (hidden from guests). This
logs in with the dealer account and pulls each product's price from its page,
then rewrites products.xlsx/csv with the price column filled.
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

BASE = "https://www.americanbest.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT = ROOT / "outputs" / "american_best-full"
PRICES = OUT / "prices.ndjson"
WORKERS = 6
# price lives in a `price-value-<id>` span; grab the $ number
PRICE_RE = re.compile(r'price-value-\d+"[^>]*>\s*\$?\s*([\d,]+\.\d{2})')
ANY_PRICE_RE = re.compile(r'itemprop="price"[^>]*content="([\d.]+)"')


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def login() -> requests.Session:
    s = requests.Session(); s.headers["User-Agent"] = UA
    lp = s.get(f"{BASE}/login", timeout=30)
    tok = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', lp.text)
    s.post(f"{BASE}/login", data={
        "Email": os.environ["AMERICAN_BEST_USERNAME"], "Password": os.environ["AMERICAN_BEST_PASSWORD"],
        "__RequestVerificationToken": tok.group(1) if tok else "", "RememberMe": "false"},
        timeout=30, allow_redirects=True)
    acct = s.get(f"{BASE}/customer/info", timeout=30).text
    if "logout" not in acct.lower():
        raise RuntimeError("American Best login failed")
    return s


def fetch_price(session, url, retries=3):
    for attempt in range(retries):
        try:
            html = session.get(url, timeout=40).text
            m = PRICE_RE.search(html) or ANY_PRICE_RE.search(html)
            price = float(m.group(1).replace(",", "")) if m else ""
            return {"url": url, "ok": True, "price": price}
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 + attempt * 2)
    return {"url": url, "ok": False, "error": repr(last)}


def stage_fetch(limit):
    df = pd.read_excel(OUT / "products.xlsx")
    urls = [u for u in df["product_url"].dropna().unique().tolist()]
    if limit:
        urls = urls[:limit]
    done = {}
    if PRICES.exists():
        for line in PRICES.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("ok"):
                    done[r["url"]] = r
            except json.JSONDecodeError:
                pass
    pending = [u for u in urls if u not in done]
    s = login()
    log(f"login OK; {len(done)} priced, {len(pending)} to fetch")
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
    prices = {}
    for line in PRICES.open(encoding="utf-8"):
        try:
            r = json.loads(line)
            if r.get("ok") and r.get("price") not in ("", None):
                prices[r["url"]] = r["price"]
        except json.JSONDecodeError:
            pass
    df = pd.read_excel(OUT / "products.xlsx")
    df["price"] = df["product_url"].map(prices).fillna(df.get("price"))
    df["source_price_label"] = df["price"].apply(lambda v: "dealer_login_price" if pd.notna(v) and str(v).strip() not in ("", "nan") else "")
    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp())
    df.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    df.to_csv(tmp / "products.csv", index=False)
    for n in ("products.xlsx", "products.csv"):
        shutil.move(str(tmp / n), str(OUT / n))
    shutil.rmtree(tmp, ignore_errors=True)
    filled = int((df["price"].astype(str).str.strip().replace("nan", "") != "").sum())
    log(f"merge: {filled}/{len(df)} rows now priced -> {OUT / 'products.xlsx'}")


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
