#!/usr/bin/env python3
"""Jackson Pottery Inc — catalog via the nopCommerce (FocusPoint) portal.

Wholesale pottery/planters on a white-labeled nopCommerce portal
(jacksonpotteryb2c.focuspointportal.com). Server-rendered HTML; ~605 products
enumerated from the sitemap (631 URLs = products + ~24 categories + home/contact).
PRICES are login-gated ("Login for pricing" / $0.00 placeholder) and there is no
trade account, so this captures the public metadata: product name (h1), vendor SKU
(id="sku-*"), description, category, and any real image. Prices flagged gated.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://jacksonpotteryb2c.focuspointportal.com"
SUPPLIER = "Jackson Pottery Inc"
SEASON = "2026"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
WORKERS = 6
OUT_DIR = ROOT / "outputs" / "jacksonpottery-full"
ITEMS_PATH = OUT_DIR / "items.json"
DETAILS_PATH = OUT_DIR / "details.ndjson"
_SKU_RE = re.compile(r'id="sku-\d+"[^>]*>([^<]+)')


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    return s


def discover(s: requests.Session) -> list[str]:
    # FocusPoint occasionally serves another tenant's cached sitemap — retry until
    # we get Jackson's (validate host + size).
    for _ in range(4):
        r = s.get(f"{BASE}/sitemap.xml", timeout=60)
        locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
        jackson = [u for u in locs if "focuspointportal.com" in u]
        if len(jackson) > 100:
            return list(dict.fromkeys(jackson))
        time.sleep(1.5)
    return list(dict.fromkeys(locs))


def _text(x: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", x or ""))).strip()


def fetch_detail(s: requests.Session, url: str) -> dict:
    rec = {"url": url}
    try:
        r = s.get(url, timeout=40)
    except requests.RequestException as e:
        return {**rec, "ok": False, "error": repr(e)}
    if r.status_code != 200:
        return {**rec, "ok": False, "error": f"HTTP {r.status_code}"}
    html = r.text
    sku_m = _SKU_RE.search(html)
    if not sku_m:
        return {**rec, "ok": False, "error": "NOT_PRODUCT"}  # category/home page
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.select_one("h1")
    desc_el = soup.select_one(".full-description, #product-details-form .full-description")
    # real product images (skip default placeholder / logos)
    imgs = []
    for im in soup.select(".gallery img, .picture img, [id*=main-product-img] img, img"):
        src = im.get("src") or im.get("data-src") or ""
        if "/images/" in src and "default-image" not in src and "logo" not in src.lower():
            full = src if src.startswith("http") else BASE + "/" + src.lstrip("/")
            imgs.append(full)
    cats = [a.get_text(strip=True) for a in soup.select(".breadcrumb a")][1:]  # drop Home
    return {
        **rec, "ok": True,
        "name": h1.get_text(strip=True) if h1 else "",
        "sku": sku_m.group(1).strip(),
        "description": _text(str(desc_el)) if desc_el else "",
        "category": " > ".join(c for c in cats if c.lower() != "home"),
        "images": list(dict.fromkeys(imgs))[:5],
    }


def run_details(urls: list[str], limit: int | None) -> None:
    done = set()
    if DETAILS_PATH.exists():
        for line in DETAILS_PATH.open(encoding="utf-8"):
            try:
                done.add(json.loads(line)["url"])
            except (json.JSONDecodeError, KeyError):
                pass
    pending = [u for u in urls if u not in done]
    if limit:
        pending = pending[:limit]
    log(f"details: {len(done)} done, {len(pending)} to fetch")
    local = threading.local(); lock = threading.Lock()
    counts = {"ok": 0, "skip": 0, "err": 0}

    def worker(u):
        s = getattr(local, "s", None)
        if s is None:
            s = make_session(); local.s = s
        return fetch_detail(s, u)

    with DETAILS_PATH.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(worker, u): u for u in pending}
            for i, f in enumerate(as_completed(futs), 1):
                rec = f.result()
                rec["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                counts["ok" if rec.get("ok") else ("skip" if rec.get("error") == "NOT_PRODUCT" else "err")] += 1
                with lock:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
                if i % 100 == 0:
                    log(f"  {i}/{len(pending)} (ok={counts['ok']} skip={counts['skip']} err={counts['err']})")
    log(f"details: done (ok={counts['ok']} skip={counts['skip']} err={counts['err']})")


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name", "category", "description",
    "price", "source_price_label", "image_url", "image_url_2", "image_url_3",
    "image_count", "product_url", "source_url", "needs_review", "extracted_at", "run_id",
]


def export(run_id: str) -> None:
    rows: dict[str, dict] = {}
    for line in DETAILS_PATH.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not r.get("ok"):
            continue
        imgs = r.get("images") or []
        sku = r.get("sku") or r["url"]
        missing = ["price (account-gated)"]
        if not imgs:
            missing.append("image")
        rows[sku] = {
            "supplier": SUPPLIER, "season": SEASON,
            "sku": r.get("sku") or "", "product_name": r.get("name") or "",
            "category": r.get("category") or "", "description": r.get("description") or "",
            "price": "", "source_price_label": "",
            "image_url": imgs[0] if imgs else "",
            "image_url_2": imgs[1] if len(imgs) > 1 else "",
            "image_url_3": imgs[2] if len(imgs) > 2 else "",
            "image_count": len(imgs),
            "product_url": r["url"], "source_url": f"{BASE}/sitemap.xml",
            "needs_review": "; ".join(missing),
            "extracted_at": r.get("fetched_at", ""), "run_id": run_id,
        }
    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["product_name"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    frame["sku"] = frame["sku"].fillna("").astype(str)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="jp-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    for n in ("products.xlsx", "products.csv"):
        shutil.move(str(tmp / n), str(OUT_DIR / n))
    shutil.rmtree(tmp, ignore_errors=True)

    imaged = int((frame["image_url"].astype(str).str.strip() != "").sum())
    report = {
        "supplier": SUPPLIER, "season": SEASON, "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_exported": len(frame), "with_price": 0, "with_image": imaged,
        "pricing_note": "nopCommerce B2B portal — prices are login-gated ('Login for pricing') "
                        "and no trade account exists. Name + SKU + description + category captured.",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} products -> {OUT_DIR/'products.xlsx'} (imaged={imaged}, priced=0/gated)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["discover", "details", "export", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.stage in ("discover", "all") and (args.stage == "discover" or not ITEMS_PATH.exists()):
        urls = discover(make_session())
        ITEMS_PATH.write_text(json.dumps(urls, indent=0))
        log(f"discover: {len(urls)} URLs")
    if args.stage in ("details", "all"):
        run_details(json.loads(ITEMS_PATH.read_text()), args.limit)
    if args.stage in ("export", "all"):
        export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
