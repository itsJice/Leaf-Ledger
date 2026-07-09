#!/usr/bin/env python3
"""Allstate Floral & Craft — full catalog via authenticated headless browser.

Legacy ColdFusion, trade-only. No sitemap / product IDs / structured feed; the
catalog is query-string-routed HTML behind a login. Structure discovered:
  /design/                                  -> category codes  (index.cfm?CL=1&CLCD=<E|X|W|M|...>)
  /design/index.cfm?CL=1&CLCD=<c>           -> subcategory codes (index.cfm?piclist=Y&DDCODE=<code>)
  /design/index.cfm?piclist=Y&DDCODE=<d>    -> product cells (item#, List Price, unit, desc, image), paginated

Login sets a ColdFusion session that persists in the app section (/design/, /pro/ ...)
even though the public "/" splash always shows a login link. Prices shown are the
trade "List Price" (the buyer's wholesale price for a logged-in dealer).

Runs a real headless Chrome locally (Bash tool -> user's machine) so the login is
genuine and the pages render. Checkpointed by DDCODE.
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

BASE = "https://www.allstatefloral.com"
DESIGN = f"{BASE}/design/index.cfm"
SUPPLIER = "Allstate Floral & Craft"
SEASON = "2026"
OUT_DIR = ROOT / "outputs" / "allstate-full"
DD_PATH = OUT_DIR / "ddcodes.json"
PROD_PATH = OUT_DIR / "products.ndjson"


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def login(sb) -> bool:
    sb.open(f"{BASE}/?login"); sb.sleep(3)
    u = os.environ["ALLSTATE_USERNAME"]; p = os.environ["ALLSTATE_PASSWORD"]
    sb.execute_script(
        "var u=document.querySelector('input[name=UserCode],input[name=usercode]');"
        "var p=document.querySelector('input[type=password]');"
        "if(u)u.value=arguments[0]; if(p)p.value=arguments[1];"
        "var f=p?p.closest('form'):null; if(f) f.submit();", u, p)
    sb.sleep(5)
    return "logout" in (sb.execute_script("return document.body.innerText")).lower()


def enumerate_ddcodes(sb) -> list[str]:
    # category codes from /design/ landing
    sb.open(f"{BASE}/design/"); sb.sleep(3)
    clcds = sb.execute_script(r"""
      var s=new Set(); Array.from(document.querySelectorAll('a[href*="CLCD="]')).forEach(function(a){
        var m=(a.getAttribute('href')||'').match(/CLCD=([^&]+)/); if(m) s.add(m[1]);
      }); return JSON.stringify(Array.from(s));
    """)
    clcds = json.loads(clcds)
    log(f"category codes: {len(clcds)} ({','.join(clcds)})")
    dd: list[str] = []
    for c in clcds:
        sb.open(f"{DESIGN}?CL=1&CLCD={c}"); sb.sleep(2.5)
        codes = json.loads(sb.execute_script(r"""
          var s=new Set(); Array.from(document.querySelectorAll('a[href*="DDCODE="]')).forEach(function(a){
            var m=(a.getAttribute('href')||'').match(/DDCODE=([^&]+)/); if(m) s.add(m[1]);
          }); return JSON.stringify(Array.from(s));
        """))
        dd.extend(codes)
        log(f"  CLCD={c}: {len(codes)} DDCODEs")
    return list(dict.fromkeys(dd))


_EXTRACT_JS = r"""
var out=[]; var seen={};
document.querySelectorAll('td,div,li').forEach(function(el){
  var t=el.innerText||'';
  if(t.length>200) return;
  var im=t.match(/\b([A-Z]{1,4}\d{3,6})(?:-([A-Z0-9\/]+))?\b/);
  var pm=t.match(/List Price:\s*\$([\d,]+\.\d{2})/i) || t.match(/\$([\d,]+\.\d{2})/);
  if(!im||!pm) return;
  var item=im[1]; if(seen[item]) return;
  var img=el.querySelector('img');
  var unit=(t.match(/\((EA|BX|ST|CS|PK|DZ|SET)\b/)||[])[1]||'';
  var desc=t.replace(/\s+/g,' ').replace(/.*List Price:\s*\$[\d,.]+/i,'').replace(/^\s*\(?(EA|BX|ST|CS|PK|DZ|SET)?\s*/,'').trim();
  seen[item]=1;
  out.push({item:item, color:(im[2]||''), price:pm[1].replace(/,/g,''), unit:unit,
            desc:desc.slice(0,140), img:img?img.src:''});
});
return JSON.stringify(out);
"""


def scrape_ddcode(sb, code: str) -> list[dict]:
    collected: dict[str, dict] = {}
    seen_pages: set[str] = set()
    to_visit = [f"{DESIGN}?piclist=Y&DDCODE={code}"]
    while to_visit:
        url = to_visit.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        sb.open(url); sb.sleep(4)
        batch = json.loads(sb.execute_script(_EXTRACT_JS))
        if not batch:  # image-heavy CF page may not be ready — wait + retry once
            sb.sleep(3.5)
            batch = json.loads(sb.execute_script(_EXTRACT_JS))
        for p in batch:
            collected.setdefault(p["item"], p)
        # follow pagination links for THIS DDCODE only
        more = json.loads(sb.execute_script(r"""
          var code=arguments[0]; var s=new Set();
          Array.from(document.querySelectorAll('a[href*="piclist"]')).forEach(function(a){
            var h=a.getAttribute('href')||'';
            if(h.indexOf('DDCODE='+code)>-1 && /PG=|STARTROW=|page=|start=|ROW=/i.test(h)) s.add(h);
          }); return JSON.stringify(Array.from(s));
        """, code))
        for h in more:
            full = h if h.startswith("http") else f"{BASE}/design/{h.lstrip('/')}"
            if full not in seen_pages:
                to_visit.append(full)
        if len(seen_pages) > 40:  # safety
            break
    return list(collected.values())


def stage_scrape(limit: int | None) -> None:
    with SB(headless=True, browser="chrome") as sb:
        if not login(sb):
            raise RuntimeError("Allstate login failed")
        log("login OK")
        if DD_PATH.exists():
            dd = json.loads(DD_PATH.read_text())
        else:
            dd = enumerate_ddcodes(sb)
            DD_PATH.write_text(json.dumps(dd, indent=0))
        log(f"DDCODEs: {len(dd)}")
        done = set()
        if PROD_PATH.exists():
            for line in PROD_PATH.open(encoding="utf-8"):
                try:
                    done.add(json.loads(line)["ddcode"])
                except (json.JSONDecodeError, KeyError):
                    pass
        pending = [d for d in dd if d not in done]
        if limit:
            pending = pending[:limit]
        log(f"scrape: {len(done)} done, {len(pending)} DDCODEs to go")
        with PROD_PATH.open("a", encoding="utf-8") as out:
            for i, code in enumerate(pending, 1):
                try:
                    prods = scrape_ddcode(sb, code)
                except Exception as exc:  # noqa: BLE001
                    prods = []; log(f"  {code} error: {exc!r}")
                out.write(json.dumps({"ddcode": code, "products": prods}, ensure_ascii=False) + "\n"); out.flush()
                if i % 10 == 0 or len(prods) > 40:
                    log(f"  [{i}/{len(pending)}] {code}: {len(prods)} products")


EXPORT_COLUMNS = [
    "supplier", "season", "sku", "color", "product_name", "unit", "price",
    "source_price_label", "image_url", "product_url", "source_url",
    "needs_review", "extracted_at", "run_id",
]


def stage_export(run_id: str) -> None:
    by_item: dict[str, dict] = {}
    for line in PROD_PATH.open(encoding="utf-8"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        dd = rec.get("ddcode", "")
        for p in rec.get("products", []):
            item = p.get("item")
            if not item or item in by_item:
                continue
            try:
                price = float(p.get("price")) if p.get("price") else ""
            except ValueError:
                price = ""
            missing = []
            if price == "":
                missing.append("price")
            if not p.get("img"):
                missing.append("image")
            by_item[item] = {
                "supplier": SUPPLIER, "season": SEASON,
                "sku": item, "color": p.get("color") or "",
                "product_name": p.get("desc") or "",
                "unit": p.get("unit") or "",
                "price": price,
                "source_price_label": "trade_list_price (login)" if price != "" else "",
                "image_url": p.get("img") or "",
                "product_url": f"{DESIGN}?piclist=Y&DDCODE={dd}",
                "source_url": f"{BASE}/design/",
                "needs_review": "; ".join(missing),
                "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "run_id": run_id,
            }
    ordered = sorted(by_item.values(), key=lambda r: r["sku"])
    frame = pd.DataFrame(ordered, columns=EXPORT_COLUMNS)
    frame["sku"] = frame["sku"].fillna("").astype(str)

    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="allstate-export-"))
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
        "pricing_note": "Trade 'List Price' from the logged-in ColdFusion catalog "
                        "(the dealer's wholesale price; site is trade-only).",
    }
    (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"export: {len(frame)} unique products -> {OUT_DIR/'products.xlsx'} (priced={priced}, imaged={imaged})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["scrape", "export", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.stage in ("scrape", "all"):
        stage_scrape(args.limit)
    if args.stage in ("export", "all"):
        stage_export(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
