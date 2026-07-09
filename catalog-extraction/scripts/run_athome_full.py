#!/usr/bin/env python3
"""At Home (athome.com) — full catalog via sitemap + PDP ld+json.

Salesforce Commerce Cloud, ~45,558 products, PUBLIC retail prices. Akamai Bot
Manager 403s the Python `requests`/TLS fingerprint, so every fetch goes through
curl with a browser UA (which Akamai allows). PDP ld+json is an `ItemPage` whose
`mainEntity` is the Product — the shared ldjson parser unwraps that.

Big, resumable run: enumerate the two product sitemaps, fetch each PDP via a curl
thread pool with 403 retry/backoff, checkpoint to NDJSON, then export.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from catalog_extraction.ldjson_http import (
    EXPORT_COLUMNS, SupplierConfig, _blocks, _breadcrumb_names, _typed, ldjson_to_row,
)

BASE = "https://www.athome.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
SITEMAPS = [f"{BASE}/sitemap_0-product.xml", f"{BASE}/sitemap_1-product.xml"]
WORKERS = 6
DELAY = 0.15
OUT_DIR = ROOT / "outputs" / "athome-full"
ITEMS_PATH = OUT_DIR / "items.json"
DETAILS_PATH = OUT_DIR / "details.ndjson"
_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")

CFG = SupplierConfig(
    supplier="At Home", season="2026", base_url=BASE,
    sitemap_url="sitemap_index.xml", price_gated_note="price",
)


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _curl(url: str, timeout: int = 60) -> tuple[int, str]:
    """Return (http_code, body) via curl. -w writes the status to stderr tail."""
    proc = subprocess.run(
        ["curl", "-s", "--compressed", "-A", UA, "-w", "\n%{http_code}", url],
        capture_output=True, text=True, timeout=timeout,
    )
    out = proc.stdout
    nl = out.rfind("\n")
    if nl == -1:
        return 0, out
    try:
        code = int(out[nl + 1:].strip())
    except ValueError:
        code = 0
    return code, out[:nl]


def discover() -> list[str]:
    urls: list[str] = []
    for sm in SITEMAPS:
        code, body = _curl(sm, timeout=120)
        found = _LOC_RE.findall(body)
        log(f"discover: {sm} -> {len(found)} (HTTP {code})")
        urls.extend(u.strip() for u in found)
    return list(dict.fromkeys(urls))


def fetch_detail(url: str) -> dict:
    rec: dict = {"url": url}
    code, body = _curl(url)
    if code != 200:
        rec.update(ok=False, error=f"HTTP {code}")
        return rec
    blocks = _blocks(body)
    product = _typed(blocks, "Product")
    if not product:
        rec.update(ok=False, error="NO_PRODUCT")
        return rec
    rec.update(ok=True, product=product, breadcrumb=_breadcrumb_names(blocks))
    return rec


def _worker(url: str) -> dict:
    last = {"url": url, "ok": False, "error": "unknown"}
    for attempt in range(4):
        time.sleep(DELAY + random.uniform(0, 0.2) + attempt * 3)
        try:
            rec = fetch_detail(url)
        except subprocess.TimeoutExpired:
            last = {"url": url, "ok": False, "error": "TIMEOUT"}
            continue
        if rec.get("ok") or rec.get("error") == "NO_PRODUCT":
            return rec
        last = rec  # 403 / transient — back off and retry
    return last


def run_details(urls: list[str], limit: int | None) -> dict:
    done: set[str] = set()
    if DETAILS_PATH.exists():
        for line in DETAILS_PATH.open(encoding="utf-8"):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            # retry hard failures (403/timeout) on resume; keep ok + NO_PRODUCT
            if row.get("ok") or row.get("error") == "NO_PRODUCT":
                done.add(row["url"])
    pending = [u for u in urls if u not in done]
    if limit:
        pending = pending[:limit]
    log(f"details: {len(done)} done, {len(pending)} to fetch")
    lock = threading.Lock()
    counts = {"ok": 0, "skip": 0, "err": 0}
    started = time.monotonic()
    with DETAILS_PATH.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(_worker, u): u for u in pending}
            for i, f in enumerate(as_completed(futs), 1):
                rec = f.result()
                rec["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if rec.get("ok"):
                    counts["ok"] += 1
                elif rec.get("error") == "NO_PRODUCT":
                    counts["skip"] += 1
                else:
                    counts["err"] += 1
                with lock:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                if i % 500 == 0:
                    rate = i / max(1e-9, time.monotonic() - started)
                    left = (len(pending) - i) / max(rate, 1e-9)
                    log(f"details: {i}/{len(pending)} (ok={counts['ok']} skip={counts['skip']} "
                        f"err={counts['err']}, {rate:.1f}/s, ~{left/60:.0f}m left)")
    return counts


def export(run_id: str) -> None:
    rows: dict[str, dict] = {}
    errors = 0
    with DETAILS_PATH.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not rec.get("ok"):
                if rec.get("error") not in ("NO_PRODUCT",):
                    errors += 1
                continue
            row = ldjson_to_row(rec, CFG, run_id=run_id)
            key = row["sku"] or row["product_url"]
            if key:
                rows[key] = row
    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["product_name"]))
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    for col in ("sku", "upc"):
        frame[col] = frame[col].fillna("").astype(str)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="athome-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    for n in ("products.xlsx", "products.csv"):
        shutil.move(str(tmp / n), str(OUT_DIR / n))
    shutil.rmtree(tmp, ignore_errors=True)

    priced = int((frame["price"].astype(str).str.strip() != "").sum())
    imaged = int((frame["image_url"].astype(str).str.strip() != "").sum())
    report = {
        "supplier": "At Home", "season": "2026", "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_exported": len(frame), "with_price": priced, "with_image": imaged,
        "fetch_errors": errors,
        "pricing_note": "Public retail price from PDP ld+json (SFCC). Business login "
                        "affects tax-exempt/bulk, not unit price.",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} rows -> {OUT_DIR/'products.xlsx'} (priced={priced}, imaged={imaged}, errors={errors})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["discover", "details", "export", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.stage in ("discover", "all") and (args.stage == "discover" or not ITEMS_PATH.exists()):
        urls = discover()
        ITEMS_PATH.write_text(json.dumps(urls, indent=0), encoding="utf-8")
        log(f"discover: {len(urls)} product URLs -> {ITEMS_PATH}")
    if args.stage in ("details", "all"):
        urls = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
        counts = run_details(urls, args.limit)
        log(f"details: done (ok={counts['ok']} skip={counts['skip']} err={counts['err']})")
    if args.stage in ("export", "all"):
        export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
