#!/usr/bin/env python3
"""Schuster's of Texas — full catalog (OpenCart 2.x, HTML-only).

~438 distinct products. No sitemap/API/ld+json; enumerate product_ids from the
143 category paths, then fetch each product page. Prices are gated behind a trade
login (OpenCart customer-group pricing): guests see no price. This runner logs in
if SCHUSTERS_USERNAME/PASSWORD authenticate, and captures the real price; if the
login is rejected it still ships the full catalog metadata (name, SKU, images,
description, availability) with price flagged as login-gated.

Bare domain root serves an unrelated GoDaddy page — always enter via ?route=.
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
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import pandas as pd
import requests
from bs4 import BeautifulSoup

B = "https://www.schustersoftexas.com/index.php"
ORIGIN = "https://www.schustersoftexas.com"
SUPPLIER = "Schusters of Texas"
SEASON = "2026"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
DELAY = 0.4
OUT_DIR = ROOT / "outputs" / "schusters-full"
IDS_PATH = OUT_DIR / "product_ids.json"
DETAILS_PATH = OUT_DIR / "details.ndjson"
_PRICE_RE = re.compile(r"\$[\d,]+\.\d{2}")


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    return s


def login(session: requests.Session) -> bool:
    user = os.environ.get("SCHUSTERS_USERNAME", "").strip()
    pw = os.environ.get("SCHUSTERS_PASSWORD", "").strip()
    if not user or not pw:
        return False
    session.get(f"{B}?route=account/login", timeout=40)
    r = session.post(f"{B}?route=account/login", data={"email": user, "password": pw},
                     headers={"Referer": f"{B}?route=account/login", "Origin": ORIGIN},
                     timeout=40, allow_redirects=True)
    if "No match for E-Mail" in r.text or "route=account/login" in r.url:
        return False
    acct = session.get(f"{B}?route=account/account", timeout=40).text
    return "route=account/logout" in acct


def discover_ids(session: requests.Session) -> list[str]:
    home = session.get(f"{B}?route=common/home", timeout=40).text
    paths = sorted(set(re.findall(r"route=product/category&(?:amp;)?path=([\d_]+)", home)))
    log(f"discover: {len(paths)} category paths")
    ids: set[str] = set()
    for i, p in enumerate(paths, 1):
        page = 1
        while True:
            url = f"{B}?route=product/category&path={p}&limit=100&page={page}"
            html = session.get(url, timeout=40).text
            found = set(re.findall(r"product_id=(\d+)", html))
            new = found - ids
            ids |= found
            # stop when no product tiles or no "next" pagination link
            if not found or f"page={page + 1}" not in html:
                break
            page += 1
            time.sleep(DELAY)
        if i % 20 == 0:
            log(f"  {i}/{len(paths)} paths, {len(ids)} unique ids")
        time.sleep(DELAY)
    return sorted(ids, key=int)


def _price(soup: BeautifulSoup) -> str:
    # OpenCart product price lives in the product-info column, not the cart widget.
    info = soup.select_one("#content .product-info, #content") or soup
    for m in _PRICE_RE.finditer(info.get_text(" ", strip=True)):
        val = m.group(0)
        if val != "$0.00":
            return val
    return ""


def parse_product(pid: str, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.select_one("#content h1, h1")
    name = h1.get_text(strip=True) if h1 else ""
    text = soup.get_text(" ", strip=True)
    sku = ""
    m = re.search(r"Product Code:\s*([^\s<][^\n<]*?)\s{2,}", text) or re.search(r"Product Code:\s*(\S+)", text)
    if m:
        sku = m.group(1).strip()
    avail = ""
    m = re.search(r"Availability:\s*([A-Za-z0-9 ,'-]+?)\s{2,}", text)
    if m:
        avail = m.group(1).strip()
    desc = ""
    tab = soup.select_one("#tab-description")
    if tab:
        desc = re.sub(r"\s+", " ", tab.get_text(" ", strip=True)).strip()
    images: list[str] = []
    for a in soup.select("#content a.thumbnail, #content a[href*='image/']"):
        href = a.get("href")
        if href and "image/" in href:
            images.append(href)
    for im in soup.select("#content img[src*='image/']"):
        src = im.get("src")
        if src and "image/" in src:
            images.append(src)
    # normalise (encode spaces) + dedupe, prefer full-size (drop -NNxNN cache dims)
    norm, seen = [], set()
    for u in images:
        if u.startswith("/"):
            u = ORIGIN + u
        u = quote(u, safe=":/?&=%")
        key = re.sub(r"-\d+x\d+", "", u)
        if key not in seen:
            seen.add(key)
            norm.append(u)
    return {"product_id": pid, "name": name, "sku": sku, "availability": avail,
            "description": desc, "price": _price(soup), "images": norm}


def run_details(session: requests.Session, ids: list[str], limit: int | None) -> dict:
    done: set[str] = set()
    if DETAILS_PATH.exists():
        for line in DETAILS_PATH.open(encoding="utf-8"):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("ok") is not None:
                done.add(str(row["product_id"]))
    pending = [i for i in ids if i not in done]
    if limit:
        pending = pending[:limit]
    log(f"details: {len(done)} done, {len(pending)} to fetch")
    counts = {"ok": 0, "err": 0, "priced": 0}
    with DETAILS_PATH.open("a", encoding="utf-8") as out:
        for i, pid in enumerate(pending, 1):
            rec: dict = {"product_id": pid}
            try:
                r = session.get(f"{B}?route=product/product&product_id={pid}", timeout=40)
                if r.status_code == 200 and ("product" in r.text.lower()):
                    rec.update(ok=True, **parse_product(pid, r.text))
                    counts["ok"] += 1
                    if rec.get("price"):
                        counts["priced"] += 1
                else:
                    rec.update(ok=False, error=f"HTTP {r.status_code}")
                    counts["err"] += 1
            except requests.RequestException as exc:
                rec.update(ok=False, error=repr(exc))
                counts["err"] += 1
            rec["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if i % 50 == 0:
                log(f"  {i}/{len(pending)} (ok={counts['ok']} priced={counts['priced']} err={counts['err']})")
            time.sleep(DELAY)
    return counts


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "product_name", "description", "price",
    "source_price_label", "availability", "image_url", "image_url_2",
    "image_url_3", "image_url_4", "image_url_5", "image_count", "product_url",
    "source_url", "needs_review", "extracted_at", "run_id", "product_id",
]


def export(run_id: str, authed: bool) -> None:
    rows: dict[str, dict] = {}
    errors = 0
    for line in DETAILS_PATH.open(encoding="utf-8"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not rec.get("ok"):
            errors += 1
            continue
        images = rec.get("images") or []
        primary = images[0] if images else ""
        extras = images[1:5]
        price = rec.get("price") or ""
        missing = []
        if not price:
            missing.append("price (login-gated)" if not authed else "price")
        if not primary:
            missing.append("image")
        if not rec.get("sku"):
            missing.append("sku")
        row = {
            "supplier": SUPPLIER, "season": SEASON,
            "sku": rec.get("sku") or "",
            "product_name": rec.get("name") or "",
            "description": rec.get("description") or "",
            "price": price,
            "source_price_label": ("dealer_login_price" if (price and authed)
                                   else ("public_site_price" if price else "")),
            "availability": rec.get("availability") or "",
            "image_url": primary,
            **{f"image_url_{n}": (extras[n - 2] if n - 2 < len(extras) else "") for n in range(2, 6)},
            "image_count": len(images),
            "product_url": f"{B}?route=product/product&product_id={rec['product_id']}",
            "source_url": f"{ORIGIN}",
            "needs_review": "; ".join(missing),
            "extracted_at": rec.get("fetched_at", ""),
            "run_id": run_id,
            "product_id": str(rec["product_id"]),
        }
        rows[str(rec["product_id"])] = row

    ordered = sorted(rows.values(), key=lambda r: (r["product_name"] or "zzz"))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    frame["sku"] = frame["sku"].fillna("").astype(str)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="schusters-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    (tmp / "products.json").write_text(json.dumps(ordered, indent=1, ensure_ascii=False), encoding="utf-8")
    for n in ("products.xlsx", "products.csv", "products.json"):
        shutil.move(str(tmp / n), str(OUT_DIR / n))
    shutil.rmtree(tmp, ignore_errors=True)

    priced = int((frame["price"].astype(str).str.strip() != "").sum())
    imaged = int((frame["image_url"].astype(str).str.strip() != "").sum())
    report = {
        "supplier": SUPPLIER, "season": SEASON, "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authenticated": authed, "rows_exported": len(frame),
        "with_price": priced, "with_image": imaged, "fetch_errors": errors,
        "needs_review_count": int((frame["needs_review"] != "").sum()),
        "pricing_note": ("Real dealer prices captured via trade login." if authed else
                         "Prices are login-gated and the trade credentials were REJECTED; "
                         "metadata+images+descriptions captured anonymously. Re-run after "
                         "fixing SCHUSTERS_USERNAME/PASSWORD to fill prices."),
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} rows -> {OUT_DIR/'products.xlsx'} "
        f"(authed={authed}, priced={priced}, imaged={imaged}, errors={errors})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["discover", "details", "export", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    session = make_session()
    authed = login(session)
    log(f"login: {'AUTHENTICATED' if authed else 'anonymous (creds rejected/absent)'}")

    if args.stage in ("discover", "all") and (args.stage == "discover" or not IDS_PATH.exists()):
        ids = discover_ids(session)
        IDS_PATH.write_text(json.dumps(ids, indent=0), encoding="utf-8")
        log(f"discover: {len(ids)} product ids -> {IDS_PATH}")
    if args.stage in ("details", "all"):
        ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
        counts = run_details(session, ids, args.limit)
        log(f"details: done (ok={counts['ok']} priced={counts['priced']} err={counts['err']})")
    if args.stage in ("export", "all"):
        export(run_id, authed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
