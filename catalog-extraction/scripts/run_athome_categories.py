#!/usr/bin/env python3
"""At Home — category-scoped extraction (user-selected categories only).

Instead of the full 45k catalog, this pulls just the categories the user chose.
At Home's human category pages 403 to scripts, but the SFCC grid AJAX endpoint
`Search-UpdateGrid?cgid=<slug>&start=N&sz=100` returns product tiles (data-pid +
PDP link). We resolve each requested category name to a real cgid slug (auto-
fixing misses against the site's 1,231-slug universe), paginate every category,
tag each product with the categories it appears under, then fetch each PDP's
ld+json for price/sku/images/description. PDP fetches reuse the cache in
athome-full/details.ndjson (curl — Akamai 403s the requests client).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from catalog_extraction.ldjson_http import (
    EXPORT_COLUMNS, SupplierConfig, _blocks, _breadcrumb_names, _typed, ldjson_to_row,
)

BASE = "https://www.athome.com"
GRID = (BASE + "/on/demandware.store/Sites-athome-sfra-Site/default/"
        "Search-UpdateGrid?cgid={cgid}&start={start}&sz=100")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT_DIR = ROOT / "outputs" / "athome-categories-full"
CACHE_DETAILS = ROOT / "outputs" / "athome-full" / "details.ndjson"  # reuse full-run cache
ITEMS_PATH = OUT_DIR / "items.json"          # {url: [categories]}
DETAILS_PATH = OUT_DIR / "details.ndjson"
UNIVERSE_PATH = OUT_DIR / "slug_universe.txt"

_PID_TILE_RE = re.compile(r'data-pid="(\d+)"')
_PDP_HREF_RE = re.compile(r'href="((?:https://www\.athome\.com)?/[^"]*?/\d{6,}\.html)"')

CFG = SupplierConfig(supplier="At Home", season="2026", base_url=BASE,
                     sitemap_url="Search-UpdateGrid", price_gated_note="price")

# The user's selected categories (label -> slug guess). The resolver corrects
# guesses that don't return products.
CATEGORIES: list[tuple[str, str]] = [
    ("Outdoor Pots & Planters", "outdoor-pots-planters"),
    ("Indoor Pots & Planters", "indoor-pots-planters"),
    ("Plant Stands & Trellises", "plant-stands-trellises"),
    ("Statues & Sculptures", "statues-sculptures"),
    ("Yard Stakes & Flags", "yard-stakes-flags"),
    ("Fountains & Wind Chimes", "fountains-wind-chimes"),
    ("Outdoor Wall Décor", "outdoor-wall-decor"),
    ("Vases", "vases"),
    ("Sculptures & Figurines", "sculptures-figurines"),
    ("Decorative Plates, Bowls & Trays", "decorative-plates-bowls-trays"),
    ("Candle Holders & Lanterns", "candle-holders-lanterns"),
    ("Decorative Boxes & Trunks", "decorative-boxes-trunks"),
    ("Floral Arrangements", "floral-arrangements"),
    ("Flowers, Stems & Sprays", "flowers-stems-sprays"),
    ("Trees, Plants & Topiaries", "trees-plants-topiaries"),
    ("Wreaths & Garland", "wreaths-garland"),
    ("Mirrors", "mirrors"),
    ("Plants & Trees", "plants-trees"),
    ("Floor Candle Holders", "floor-candle-holders"),
    ("Stands, Easels & Chalkboards", "stands-easels-chalkboards"),
    ("Scented Candles", "scented-candles"),
    ("Pillar Candles", "pillar-candles"),
    ("Flameless & LED Candles", "flameless-led-candles"),
    ("Citronella & Torches", "citronella-torches"),
    ("Seasonal Candles & Fragrance", "seasonal-candles-fragrance"),
    ("Cabinet & Pantry Organization", "cabinet-pantry-organization"),
    ("Kitchen Canisters & Jars", "kitchen-canisters-jars"),
    ("Food Storage Containers", "food-storage-containers"),
    ("Utensil Holders & Caddies", "utensil-holders-caddies"),
    ("Drawer Organizers", "drawer-organizers"),
    ("Table Lamps", "table-lamps"),
    ("Desk Lamps", "desk-lamps"),
    ("Floor Lamps", "floor-lamps"),
    ("Accent Lamps", "accent-lamps"),
    ("Lamp Shades", "lamp-shades"),
    ("Patio Lighting", "patio-lighting"),
    ("Bedroom Lighting", "bedroom-lighting"),
    ("Living Room Lighting", "living-room-lighting"),
    ("Uplighting", "uplighting"),
    ("Novelty Lights", "novelty-lights"),
    ("Finials, Harps & Light Bulbs", "finials-harps-light-bulbs"),
    ("Baskets", "baskets"),
    ("Bins", "bins"),
    ("Crates", "crates"),
    ("Trunks", "trunks"),
    ("Drawers & Carts", "drawers-carts"),
    ("Shoe Storage", "shoe-storage"),
    ("Closet & Drawer Organizers", "closet-drawer-organizers"),
    ("Closet Bins & Baskets", "closet-bins-baskets"),
    ("Hangers & Closet Accessories", "hangers-closet-accessories"),
    ("Jewelry Organizers & Stands", "jewelry-organizers-stands"),
    ("Garment Racks & Shelves", "garment-racks-shelves"),
    ("Laundry Hampers", "laundry-hampers"),
    ("Laundry Baskets", "laundry-baskets"),
    ("Ironing Boards & Clothing Care", "ironing-boards-clothing-care"),
    ("Clothes Drying Racks", "clothes-drying-racks"),
    ("Bathroom Counter & Makeup Organizers", "bathroom-counter-makeup-organizers"),
    ("Shower Caddies & Totes", "shower-caddies-totes"),
    ("Bathroom Shelves, Carts & Storage", "bathroom-shelves-carts-storage"),
    ("Toilet Paper Holders & Stands", "toilet-paper-holders-stands"),
    ("Office Organization", "office-organization"),
    ("Kitchen Organization", "kitchen-organization"),
    ("Cleaning Essentials", "cleaning-essentials"),
    ("Trash Cans", "trash-cans"),
    ("Outdoor Halloween Décor", "outdoor-halloween-decor"),
    ("Indoor Halloween Décor", "indoor-halloween-decor"),
    ("Skeletons & Skulls", "skeletons-skulls"),
    ("Halloween Pillows & Throws", "halloween-pillows-throws"),
    ("Halloween Kitchen & Entertaining", "halloween-kitchen-entertaining"),
    ("Liberty Way Collection", "liberty-way-collection"),
    ("Union Beach Collection", "union-beach-collection"),
    ("Patriotic Outdoor", "patriotic-outdoor"),
    ("Patriotic Indoor Décor", "patriotic-indoor-decor"),
    ("Gifts For Her", "gifts-for-her"),
    ("Gifts For Him", "gifts-for-him"),
    ("Dorm Bedding", "dorm-bedding"),
    ("Dorm Furniture", "dorm-furniture"),
    ("Dorm Wall Art & Frames", "dorm-wall-art-frames"),
    ("Dorm Rugs", "dorm-rugs"),
    ("Dorm Bath", "dorm-bath"),
]


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _curl(url: str, timeout: int = 60) -> tuple[int, str]:
    proc = subprocess.run(["curl", "-s", "--compressed", "-A", UA, "-w", "\n%{http_code}", url],
                          capture_output=True, text=True, timeout=timeout)
    out = proc.stdout
    nl = out.rfind("\n")
    if nl == -1:
        return 0, out
    try:
        code = int(out[nl + 1:].strip())
    except ValueError:
        code = 0
    return code, out[:nl]


def grid_pids(cgid: str, start: int) -> tuple[list[str], dict[str, str]]:
    code, body = _curl(GRID.format(cgid=cgid, start=start))
    if code != 200:
        return [], {}
    pids = list(dict.fromkeys(_PID_TILE_RE.findall(body)))
    urls: dict[str, str] = {}
    for href in _PDP_HREF_RE.findall(body):
        full = href if href.startswith("http") else BASE + href
        m = re.search(r"/(\d{6,})\.html", full)
        if m:
            urls[m.group(1)] = full
    return pids, urls


def resolve_slug(label: str, guess: str, universe: list[str]) -> str | None:
    pids, _ = grid_pids(guess, 0)
    if pids:
        return guess
    # keyword resolution: candidates whose slug contains the meaningful words
    words = [w for w in re.split(r"[^a-z0-9]+", guess) if len(w) > 2 and
             w not in ("and", "the", "with", "for")]
    cands = [s for s in universe if all(w in s for w in words[:2])] if words else []
    # prefer shorter / non-"shop-all" slugs
    cands.sort(key=lambda s: (("shop-all" in s), len(s)))
    for c in cands[:4]:
        pids, _ = grid_pids(c, 0)
        if pids:
            log(f"  resolved '{label}': {guess} -> {c}")
            return c
    return None


def stage_discover() -> None:
    universe = [l.strip() for l in UNIVERSE_PATH.read_text().splitlines() if l.strip()]
    by_url: dict[str, set] = {}
    resolved, unresolved = 0, []
    for label, guess in CATEGORIES:
        slug = resolve_slug(label, guess, universe)
        if not slug:
            unresolved.append(label)
            continue
        resolved += 1
        start, total = 0, 0
        seen_pid: set[str] = set()
        while True:
            pids, urls = grid_pids(slug, start)
            fresh = [p for p in pids if p not in seen_pid]
            if not fresh:
                break
            seen_pid.update(fresh)
            for pid in fresh:
                url = urls.get(pid)
                if url:
                    by_url.setdefault(url, set()).add(label)
            total += len(fresh)
            start += 100
            time.sleep(0.3)
            if start > 5000:  # safety
                break
        log(f"{label} [{slug}]: {total} products")
    items = {u: sorted(cats) for u, cats in by_url.items()}
    ITEMS_PATH.write_text(json.dumps(items, indent=0, ensure_ascii=False), encoding="utf-8")
    log(f"discover: {resolved}/{len(CATEGORIES)} categories resolved, "
        f"{len(items)} unique products -> {ITEMS_PATH}")
    if unresolved:
        log(f"UNRESOLVED categories ({len(unresolved)}): {', '.join(unresolved)}")


def _load_cache() -> dict[str, dict]:
    cache: dict[str, dict] = {}
    for path in (CACHE_DETAILS, DETAILS_PATH):
        if path.exists():
            for line in path.open(encoding="utf-8"):
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("ok") or r.get("error") == "NO_PRODUCT":
                    cache[r["url"]] = r
    return cache


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


def stage_details(limit: int | None) -> None:
    items = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    urls = list(items.keys())
    cache = _load_cache()
    reused = sum(1 for u in urls if u in cache and cache[u].get("ok"))
    log(f"details: {len(urls)} target products, {reused} already cached")
    pending = [u for u in urls if u not in cache]
    if limit:
        pending = pending[:limit]
    counts = {"ok": 0, "skip": 0, "err": 0}

    def worker(url: str) -> dict:
        for attempt in range(4):
            try:
                rec = fetch_detail(url)
            except subprocess.TimeoutExpired:
                rec = {"url": url, "ok": False, "error": "TIMEOUT"}
            if rec.get("ok") or rec.get("error") == "NO_PRODUCT":
                break
            time.sleep(2 + attempt * 3)
        rec["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return rec

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    lock = threading.Lock()
    with DETAILS_PATH.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=5) as pool:
            futs = {pool.submit(worker, u): u for u in pending}
            for i, f in enumerate(as_completed(futs), 1):
                rec = f.result()
                counts["ok" if rec.get("ok") else ("skip" if rec.get("error") == "NO_PRODUCT" else "err")] += 1
                with lock:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                if i % 300 == 0:
                    log(f"  {i}/{len(pending)} (ok={counts['ok']} skip={counts['skip']} err={counts['err']})")
    log(f"details: done (ok={counts['ok']} skip={counts['skip']} err={counts['err']})")


def stage_export(run_id: str) -> None:
    items = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    cache = _load_cache()
    rows: dict[str, dict] = {}
    for url, cats in items.items():
        rec = cache.get(url)
        if not rec or not rec.get("ok"):
            continue
        row = ldjson_to_row(rec, CFG, run_id=run_id)
        row["category"] = cats[0] if cats else row.get("category", "")
        row["listed_under"] = "; ".join(cats)
        key = row["sku"] or url
        rows[key] = row
    columns = EXPORT_COLUMNS + ["listed_under"]
    ordered = sorted(rows.values(), key=lambda r: (r["category"], r["product_name"]))
    frame = pd.DataFrame(ordered, columns=columns)
    for col in ("sku", "upc"):
        frame[col] = frame[col].fillna("").astype(str)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="ahcat-export-"))
    frame.to_excel(tmp / "products.xlsx", index=False, sheet_name="products")
    frame.to_csv(tmp / "products.csv", index=False)
    for n in ("products.xlsx", "products.csv"):
        shutil.move(str(tmp / n), str(OUT_DIR / n))
    shutil.rmtree(tmp, ignore_errors=True)

    priced = int((frame["price"].astype(str).str.strip() != "").sum())
    imaged = int((frame["image_url"].astype(str).str.strip() != "").sum())
    report = {
        "supplier": "At Home (selected categories)", "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_exported": len(frame), "with_price": priced, "with_image": imaged,
        "categories_requested": len(CATEGORIES),
        "pricing_note": "Public retail price from PDP ld+json; scoped to user-selected categories.",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} rows -> {OUT_DIR/'products.xlsx'} (priced={priced}, imaged={imaged})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["discover", "details", "export", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.stage in ("discover", "all") and (args.stage == "discover" or not ITEMS_PATH.exists()):
        stage_discover()
    if args.stage in ("details", "all"):
        stage_details(args.limit)
    if args.stage in ("export", "all"):
        stage_export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
