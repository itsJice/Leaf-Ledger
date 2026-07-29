#!/usr/bin/env python3
"""Give Allstate (supplier_id=1) products PERMANENT public image URLs via the
Internet Archive's Wayback Machine.

WHY: Allstate serves product images only as ColdFusion temp URLs
(`/CFFileServlet/_cf_image/_cfimg<rand>.jpg`) that are destroyed minutes after
the generating session — the vendor hosts nothing durable (verified: dealer
portal, Productitemdetail.cfm, public site, 15 candidate stable paths → all
dead ends). Fix: while each temp URL is still alive, ask archive.org's
Save Page Now to capture it. The archived copy lives forever at
    https://web.archive.org/web/<ts>im_/<original-url>
which is a real public https URL — same pattern as the Rock Warehouse fix.

Flow per DDCODE (23 total): scrape fresh SKU→URL pairs (logged-in browser) →
IMMEDIATELY submit each URL to SPN with a small worker pool → verify the
archived copy actually serves image/* bytes → checkpoint. SKUs whose URL
expired before capture are re-scraped (fresh URLs) and re-saved in later
rounds — the process self-heals.

  --stage archive : browser + SPN (catalog-extraction venv). Resumable.
  --stage load    : write archived URLs to products (backend venv) [--commit]

    .venv/bin/python scripts/archive_allstate_images.py --stage archive
    ../backend/.venv/bin/python scripts/archive_allstate_images.py --stage load --commit
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / "backend"
OUT = ROOT / "outputs" / "allstate-full"
CKPT = OUT / "wayback_progress.ndjson"      # one line per SKU attempt
BASE = "https://www.allstatefloral.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
SUPPLIER_ID = 1
MAX_ROUNDS = 3
WORKERS = 2          # SPN rate-limits per IP — low & steady beats fast & throttled
BACKOFF_CODES = {429, 500, 502, 503, 520, 521, 522, 523, 524}


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def load_done() -> dict[str, dict]:
    """sku -> last successful record ({ts, orig})."""
    done = {}
    if CKPT.exists():
        for line in CKPT.open(encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ok"):
                done[r["sku"]] = r
    return done


# ─── stage: archive ──────────────────────────────────────────────────────────

class Throttled(Exception):
    pass


def stage_archive():
    import requests
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_allstate_full import login, scrape_ddcode, DD_PATH
    from seleniumbase import SB

    dd = json.loads(DD_PATH.read_text())
    done = load_done()
    log(f"already archived OK: {len(done)} SKUs")

    # global politeness/backoff shared by workers
    lock = threading.Lock()
    state = {"delay": 1.0, "pause_until": 0.0}

    def spn_save(job):
        """(sku, url) -> checkpoint record. Submits to Save Page Now + verifies."""
        sku, url = job
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        for attempt in range(6):
            with lock:
                wait = max(0.0, state["pause_until"] - time.time()) + state["delay"]
            time.sleep(wait)
            try:
                r = s.get(f"https://web.archive.org/save/{url}", timeout=180,
                          allow_redirects=True)
            except requests.RequestException as e:
                with lock:  # network trouble — everyone slow down a little
                    state["pause_until"] = max(state["pause_until"], time.time() + 20)
                if attempt == 5:
                    return {"sku": sku, "orig": url, "ok": False, "error": type(e).__name__}
                continue
            if r.status_code in BACKOFF_CODES:
                # archive.org overloaded / rate-limiting: global pause, growing delay
                with lock:
                    state["pause_until"] = max(state["pause_until"], time.time() + 60 + 30 * attempt)
                    state["delay"] = min(state["delay"] * 1.5, 10.0)
                continue
            m = (re.search(r"/web/(\d{14})", r.url)
                 or re.search(r"/web/(\d{14})", r.headers.get("content-location", ""))
                 or re.search(r'/web/(\d{14})/', r.text[:20000] if r.text else ""))
            if not m:
                if attempt == 5:
                    return {"sku": sku, "orig": url, "ok": False, "error": f"no_ts_http{r.status_code}"}
                continue
            ts = m.group(1)
            # verify the archived copy is a real image (not a captured 404 page)
            try:
                v = s.get(f"https://web.archive.org/web/{ts}im_/{url}", timeout=90, stream=True)
                head = next(v.iter_content(1024), b"")
                v.close()
            except requests.RequestException:
                head = b""
            if head[:3] == b"\xff\xd8\xff" or head[:4] == b"\x89PNG":
                with lock:  # success — gently relax the delay
                    state["delay"] = max(0.6, state["delay"] * 0.95)
                return {"sku": sku, "orig": url, "ts": ts, "ok": True}
            if attempt == 3:
                return {"sku": sku, "orig": url, "ok": False, "error": "captured_non_image"}
        return {"sku": sku, "orig": url, "ok": False, "error": "exhausted"}

    with SB(headless=True, browser="chrome") as sb:
        if not login(sb):
            raise RuntimeError("Allstate login failed")
        log("login OK")
        for rnd in range(1, MAX_ROUNDS + 1):
            done = load_done()
            log(f"── round {rnd}: {len(done)} archived so far")
            any_missing = False
            with CKPT.open("a", encoding="utf-8") as ck:
                for i, code in enumerate(dd, 1):
                    try:
                        prods = scrape_ddcode(sb, code)
                    except Exception as exc:  # noqa: BLE001
                        log(f"  {code} scrape error: {exc!r}")
                        continue
                    jobs, seen = [], set()
                    for p in prods:
                        sku = (p.get("item") or "").strip()
                        img = p.get("img") or ""
                        if sku and "_cf_image" in img and sku not in seen and sku not in done:
                            seen.add(sku)
                            jobs.append((sku, img))
                    if not jobs:
                        continue
                    any_missing = True
                    t0 = time.time()
                    ok = 0
                    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                        for rec in ex.map(spn_save, jobs):
                            ck.write(json.dumps(rec) + "\n"); ck.flush()
                            if rec["ok"]:
                                ok += 1; done[rec["sku"]] = rec
                    log(f"  [{i}/{len(dd)}] {code}: {len(jobs)} to save -> {ok} archived "
                        f"({time.time() - t0:.0f}s, delay {state['delay']:.1f}s)")
            if not any_missing:
                break
    done = load_done()
    log(f"DONE: {len(done)} SKUs permanently archived on web.archive.org")


# ─── stage: load ─────────────────────────────────────────────────────────────

def stage_load(commit: bool):
    import asyncio, os
    import dotenv
    dotenv.load_dotenv(BACKEND / ".env"); dotenv.load_dotenv(BACKEND / ".env.dev", override=True)
    import asyncpg
    from datetime import datetime, timezone

    done = load_done()
    SQL = """
    UPDATE products SET photo_url=$1, image_urls=$2::text[],
      raw_data = jsonb_set(jsonb_set(coalesce(raw_data,'{}'::jsonb),
          '{image_reacquired_at}', to_jsonb($3::text), true),
          '{image_source}', to_jsonb('wayback_archive'::text), true),
      updated_at=NOW()
    WHERE supplier_id=$4 AND supplier_sku=$5
    """

    async def run():
        c = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            db = {r["supplier_sku"] for r in await c.fetch(
                "SELECT supplier_sku FROM products WHERE supplier_id=$1 AND supplier_sku IS NOT NULL",
                SUPPLIER_ID)}
            rows = []
            for sku, rec in done.items():
                if sku in db:
                    url = f"https://web.archive.org/web/{rec['ts']}im_/{rec['orig']}"
                    rows.append((url, [url],
                                 datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 SUPPLIER_ID, sku))
            log(f"archived: {len(done)} | in DB: {len(rows)} | DB total: {len(db)}")
            if not commit:
                log("DRY RUN — re-run with --commit"); return
            async with c.transaction():
                for i in range(0, len(rows), 1000):
                    await c.executemany(SQL, rows[i:i + 1000])
            n = await c.fetchval(
                "SELECT COUNT(*) FROM products WHERE supplier_id=$1 AND photo_url LIKE 'https://web.archive.org/%'",
                SUPPLIER_ID)
            log(f"COMMITTED. Allstate products with permanent archive.org URLs: {n}")
        finally:
            await c.close()
    asyncio.run(run())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["archive", "load"], required=True)
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.stage == "archive":
        stage_archive()
    else:
        stage_load(a.commit)


if __name__ == "__main__":
    raise SystemExit(main())
