#!/usr/bin/env python3
"""Jay Scotts — enrich with real WHOLESALE (dealer) prices.

The public catalog (run_jayscotts_full.py) captured retail prices. Jay Scotts runs
a WooCommerce wholesale plugin whose prices aren't in the Store API or static HTML,
but the WooCommerce variation AJAX returns them for a logged-in wholesale account:
  POST /?wc-ajax=get_variation  {product_id, variation_id, attribute_pa_*=...}
  -> display_price = WHOLESALE (dealer), display_regular_price = RETAIL (list).
Attributes come from each variation's permalink query string. We log in with
JAY_SCOTTS_* and fetch per variation, then rewrite products.xlsx with
price=wholesale, list_price=retail, margin_pct_off_retail.
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
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass

import pandas as pd
import requests

B = "https://jayscotts.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT = ROOT / "outputs" / "jayscotts-full"
RAW = OUT / "products_raw.json"
PRICES = OUT / "wholesale_prices.ndjson"
WORKERS = 6


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def login() -> requests.Session:
    s = requests.Session(); s.headers["User-Agent"] = UA
    lp = s.get(f"{B}/my-account/", timeout=40).text
    nonce = re.search(r'name="woocommerce-login-nonce" value="([^"]+)"', lp)
    s.post(f"{B}/my-account/", data={
        "username": os.environ["JAY_SCOTTS_USERNAME"], "password": os.environ["JAY_SCOTTS_PASSWORD"],
        "woocommerce-login-nonce": nonce.group(1) if nonce else "",
        "_wp_http_referer": "/my-account/", "login": "Log in"}, timeout=40)
    if "customer-logout" not in s.get(f"{B}/my-account/", timeout=40).text.lower():
        raise RuntimeError("Jay Scotts login failed")
    return s


def _attrs(permalink: str) -> dict:
    q = parse_qs(urlparse(permalink).query)
    return {k: v[0] for k, v in q.items() if k.startswith("attribute_")}


def variations() -> list[dict]:
    out = []
    for rec in json.loads(RAW.read_text(encoding="utf-8")):
        pid = rec["parent"]["id"]
        for v in rec.get("variations", []):
            out.append({"pid": pid, "vid": v["id"], "attrs": _attrs(v.get("permalink", ""))})
        if not rec.get("variations"):  # simple product
            p = rec["parent"]
            out.append({"pid": p["id"], "vid": p["id"], "attrs": {}, "simple": True})
    return out


def fetch_one(session, item, retries=3):
    for a in range(retries):
        try:
            data = {"product_id": item["pid"], "variation_id": item["vid"], **item["attrs"]}
            r = session.post(f"{B}/?wc-ajax=get_variation", data=data,
                             headers={"X-Requested-With": "XMLHttpRequest"}, timeout=30)
            d = r.json()
            if d:
                return {"vid": item["vid"], "ok": True,
                        "wholesale": d.get("display_price"), "retail": d.get("display_regular_price")}
            return {"vid": item["vid"], "ok": True, "wholesale": "", "retail": ""}  # false = no match
        except (requests.RequestException, ValueError):
            time.sleep(1 + a * 2)
    return {"vid": item["vid"], "ok": False}


def stage_fetch(limit):
    items = variations()
    if limit:
        items = items[:limit]
    done = set()
    if PRICES.exists():
        for line in PRICES.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("ok"):
                    done.add(r["vid"])
            except json.JSONDecodeError:
                pass
    pending = [i for i in items if i["vid"] not in done]
    s = login()
    log(f"login OK; {len(done)} done, {len(pending)} variations to fetch")
    lock = threading.Lock(); c = {"ok": 0, "priced": 0, "err": 0}
    with PRICES.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(fetch_one, s, i): i for i in pending}
            for n, f in enumerate(as_completed(futs), 1):
                r = f.result()
                c["ok" if r.get("ok") else "err"] += 1
                if r.get("wholesale"):
                    c["priced"] += 1
                with lock:
                    out.write(json.dumps(r) + "\n"); out.flush()
                if n % 400 == 0:
                    log(f"  {n}/{len(pending)} (priced={c['priced']} err={c['err']})")
    log(f"fetch done (ok={c['ok']} priced={c['priced']} err={c['err']})")


def stage_merge():
    whole, retail = {}, {}
    for line in PRICES.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("ok") and r.get("wholesale") not in ("", None):
            whole[str(r["vid"])] = float(r["wholesale"])
            if r.get("retail") not in ("", None):
                retail[str(r["vid"])] = float(r["retail"])
    df = pd.read_excel(OUT / "products.xlsx")
    df["variation_id"] = df["variation_id"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    df["list_price"] = df["variation_id"].map(retail)          # retail (was the old 'price')
    df["price"] = df["variation_id"].map(whole)                # wholesale dealer price
    df["source_price_label"] = df["price"].apply(lambda v: "wholesale_dealer_price" if pd.notna(v) else "")
    df["list_price_label"] = df["list_price"].apply(lambda v: "retail" if pd.notna(v) else "")
    df["margin_pct_off_retail"] = df.apply(
        lambda r: round((r["list_price"] - r["price"]) / r["list_price"] * 100, 1)
        if pd.notna(r["price"]) and pd.notna(r["list_price"]) and r["list_price"] else "", axis=1)
    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp())
    df.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    df.to_csv(tmp / "products.csv", index=False)
    for n in ("products.xlsx", "products.csv"):
        shutil.move(str(tmp / n), str(OUT / n))
    shutil.rmtree(tmp, ignore_errors=True)
    w = int(df["price"].notna().sum()); l = int(df["list_price"].notna().sum())
    log(f"merge: {w}/{len(df)} wholesale-priced, {l} with retail list -> {OUT/'products.xlsx'}")


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
    raise SystemExit(main())
