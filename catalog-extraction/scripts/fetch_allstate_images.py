#!/usr/bin/env python3
"""Download Allstate (supplier_id=1) product images to local files.

WHY THIS EXISTS (important):
Allstate serves product images ONLY as ColdFusion `<cfimage>` temp files at
`/CFFileServlet/_cf_image/_cfimg<random>.jpg`. Verified behaviour:
  * they need no cookie while alive, BUT
  * they are destroyed within minutes of the generating session — measured:
    the first DDCODE's URLs were already 404 while the last DDCODE's still 200.
  * neither the piclist page nor `Productitemdetail.cfm` exposes any stable path.
So storing image URLs in the DB CANNOT work for this supplier. The only durable
fix is to grab the BYTES while the session is alive — hence: scrape a DDCODE,
immediately download that batch, move on.

Output:
  outputs/allstate-full/images/<sku>.jpg      the image bytes
  outputs/allstate-full/images_manifest.json  {sku: {"file","bytes","sha256"}}
  outputs/allstate-full/images_progress.ndjson  per-DDCODE checkpoint (resumable)

The app's image-caching layer (owned by the main session) ingests from the
manifest; this script does NOT touch the proxy, frontend, or product URLs.

    .venv/bin/python scripts/fetch_allstate_images.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "outputs" / "allstate-full"
IMGDIR = OUT / "images"
MANIFEST = OUT / "images_manifest.json"
CKPT = OUT / "images_progress.ndjson"
BASE = "https://www.allstatefloral.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Referer": f"{BASE}/"}


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def safe(sku: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", sku)


def download(job):
    """(sku, url) -> record. Runs immediately after the URL is minted."""
    sku, url = job
    path = IMGDIR / f"{safe(sku)}.jpg"
    if path.exists() and path.stat().st_size > 1024:
        return sku, {"file": path.name, "bytes": path.stat().st_size, "cached": True}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HDRS, timeout=30)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") \
                    and len(r.content) > 1024:
                path.write_bytes(r.content)
                return sku, {"file": path.name, "bytes": len(r.content),
                             "sha256": hashlib.sha256(r.content).hexdigest()[:16]}
            if r.status_code == 404:
                return sku, {"error": "expired_404"}
        except requests.RequestException as e:
            if attempt == 2:
                return sku, {"error": type(e).__name__}
        time.sleep(0.5)
    return sku, {"error": "failed"}


def main() -> int:
    from run_allstate_full import login, scrape_ddcode, DD_PATH
    from seleniumbase import SB

    IMGDIR.mkdir(parents=True, exist_ok=True)
    dd = json.loads(DD_PATH.read_text())
    done = set()
    if CKPT.exists():
        for line in CKPT.open(encoding="utf-8"):
            try:
                done.add(json.loads(line)["ddcode"])
            except (json.JSONDecodeError, KeyError):
                pass
    pending = [d for d in dd if d not in done]
    log(f"DDCODEs: {len(dd)} total, {len(done)} done, {len(pending)} to fetch")

    with SB(headless=True, browser="chrome") as sb:
        if not login(sb):
            raise RuntimeError("Allstate login failed")
        log("login OK")
        with CKPT.open("a", encoding="utf-8") as ck:
            for i, code in enumerate(pending, 1):
                t0 = time.time()
                try:
                    prods = scrape_ddcode(sb, code)
                except Exception as exc:  # noqa: BLE001
                    prods = []
                    log(f"  {code} scrape error: {exc!r}")
                jobs = []
                seen = set()
                for p in prods:
                    sku = (p.get("item") or "").strip()
                    img = p.get("img") or ""
                    if sku and "_cf_image" in img and sku not in seen:
                        seen.add(sku)
                        jobs.append((sku, img))
                # download IMMEDIATELY — these URLs die within minutes
                recs = {}
                with ThreadPoolExecutor(max_workers=8) as ex:
                    for sku, rec in ex.map(download, jobs):
                        recs[sku] = rec
                ok = sum(1 for r in recs.values() if "file" in r)
                ck.write(json.dumps({"ddcode": code, "records": recs}) + "\n"); ck.flush()
                log(f"  [{i}/{len(pending)}] {code}: {len(jobs)} urls -> {ok} images "
                    f"({time.time() - t0:.0f}s)")

    merged = {}
    for line in CKPT.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        for sku, rec in r.get("records", {}).items():
            if "file" in rec:
                merged[sku] = rec
    MANIFEST.write_text(json.dumps(merged, indent=0), encoding="utf-8")
    tot = sum(r["bytes"] for r in merged.values())
    log(f"DONE: {len(merged)} images, {tot/1e6:.0f} MB -> {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
