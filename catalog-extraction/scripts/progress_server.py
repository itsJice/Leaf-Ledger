#!/usr/bin/env python3
"""Live progress tracker for the Allstate image work.

Now tracks the PERMANENT-ARCHIVE phase: each fresh Allstate image URL is pushed
to archive.org's Save Page Now before it expires, giving every product a
permanent public https URL. Reads the running job's checkpoint/log read-only.

    python scripts/progress_server.py [--port 8351]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "allstate-full"
LOG = OUT / "wayback_archive.log"
CKPT = OUT / "wayback_progress.ndjson"

TARGET = 4668  # images that existed in the download pass

EXPECTED = {
    "EZ7EA": 308, "EZ7GD": 509, "EZ7SP": 184, "EZ7SU": 483, "EZ7TR": 328,
    "EZ7WD": 90, "EZ7VA": 76, "XZ6RE": 212, "XZ6WS": 348, "XZ6TD": 54,
    "XZ6SN": 555, "XZ6NA": 670, "XZ6JE": 109, "XZ6GO": 328, "XZ6FA": 280,
    "XZ6HA": 174, "WW0001": 33, "WW0002": 8, "WW0003": 7, "WW0004": 7,
    "WW0005": 6, "MM0001": 1, "MM0002": 5,
}
ORDER = list(EXPECTED)


def running() -> bool:
    return os.popen("pgrep -f archive_allstate_images").read().strip() != ""


def collect() -> dict:
    ok = fail = 0
    first_ts = last_ts = None
    if CKPT.exists():
        st = CKPT.stat()
        for line in CKPT.open(encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ok"):
                ok += 1
            else:
                fail += 1
        last_ts = st.st_mtime
    # per-DDCODE lines from the log:  [i/23] CODE: N to save -> M archived (Xs, delay Ys)
    rows, cur = {}, None
    if LOG.exists():
        txt = LOG.read_text(errors="replace")
        m0 = re.search(r"\[(\d\d:\d\d:\d\d)\] login OK", txt)
        if m0:
            first_ts = m0.group(1)
        for m in re.finditer(r"\[\d+/\d+\] (\w+): (\d+) to save -> (\d+) archived \((\d+)s", txt):
            rows[m.group(1)] = {"todo": int(m.group(2)), "ok": int(m.group(3)),
                                "secs": int(m.group(4))}
        ms = re.search(r"scrape.*?(\w+)\s*$", txt.strip().splitlines()[-1]) if txt.strip() else None
        done_codes = list(rows)
        cur = next((c for c in ORDER if c not in done_codes), None)
    total_done = ok
    # rate from measured per-DDCODE save throughput
    secs = sum(r["secs"] for r in rows.values())
    saved = sum(r["ok"] for r in rows.values())
    rate = (secs / saved) if saved else 2.5          # sec per image archived
    remaining = max(0, TARGET - total_done)
    eta_s = int(remaining * rate)
    return {"ok": ok, "fail": fail, "rows": rows, "cur": cur, "rate": rate,
            "eta_s": eta_s, "running": running(), "start": first_ts,
            "done_pct": 100 * total_done / TARGET if TARGET else 0}


def human(s: int) -> str:
    if s <= 0:
        return "—"
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def page() -> str:
    d = collect()
    eta_clock = (datetime.now() + timedelta(seconds=d["eta_s"])).strftime("%H:%M") if d["eta_s"] and d["running"] else "—"
    if not d["running"] and d["ok"] >= TARGET * 0.97:
        state, badge = "COMPLETE", "#16a34a"
    elif d["running"]:
        state, badge = "ARCHIVING", "#7c3aed"
    else:
        state, badge = "STOPPED", "#dc2626"

    bars = []
    for c in ORDER:
        exp = EXPECTED[c]
        r = d["rows"].get(c)
        if r:
            pct = 100 * r["ok"] / max(r["todo"], 1) if r["todo"] else 100
            cls = "ok" if r["ok"] >= r["todo"] else "err"
            label = f"{r['ok']}/{r['todo']} archived"
        elif c == d["cur"] and d["running"]:
            pct, cls, label = 45, "cur", "scraping + archiving…"
        else:
            pct, cls, label = 0, "wait", f"{exp} queued"
        bars.append(f"""<tr><td class=c>{c}</td><td class=b>
          <div class=track><div class="fill {cls}" style="width:{pct}%"></div></div></td>
          <td class=l>{label}</td></tr>""")

    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta http-equiv=refresh content=15><title>Allstate → archive.org</title><style>
:root{{--bg:#fff;--fg:#111827;--mut:#6b7280;--line:#e5e7eb;--track:#f3f4f6}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0b0f19;--fg:#e5e7eb;--mut:#9ca3af;--line:#1f2937;--track:#111827}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif;padding:24px}}
h1{{font-size:18px;margin:0 0 2px}}.sub{{color:var(--mut);font-size:13px;margin-bottom:18px}}
.badge{{display:inline-block;background:{badge};color:#fff;border-radius:999px;
padding:2px 10px;font-size:11px;font-weight:600;letter-spacing:.04em;vertical-align:2px;margin-left:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:22px}}
.card{{border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
.k{{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em}}
.v{{font-size:22px;font-weight:650;font-variant-numeric:tabular-nums;margin-top:2px}}
.big{{height:12px;border-radius:6px;background:var(--track);overflow:hidden;margin:6px 0 4px}}
.big>div{{height:100%;background:linear-gradient(90deg,#7c3aed,#22c55e);width:{d['done_pct']:.1f}%}}
table{{width:100%;border-collapse:collapse}}td{{padding:3px 6px;vertical-align:middle}}
td.c{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;width:78px;color:var(--mut)}}
td.l{{font-size:12px;color:var(--mut);width:170px;text-align:right;font-variant-numeric:tabular-nums}}
.track{{height:8px;background:var(--track);border-radius:4px;overflow:hidden}}
.fill{{height:100%;border-radius:4px}}.fill.ok{{background:#22c55e}}.fill.err{{background:#f59e0b}}
.fill.cur{{background:#7c3aed;animation:p 1.4s ease-in-out infinite}}.fill.wait{{background:transparent}}
@keyframes p{{0%,100%{{opacity:.45}}50%{{opacity:1}}}}
.foot{{color:var(--mut);font-size:12px;margin-top:18px;border-top:1px solid var(--line);padding-top:10px}}
</style></head><body>
<h1>Allstate → permanent archive.org image links<span class=badge>{state}</span></h1>
<div class=sub>Each image is captured by the Wayback Machine before Allstate's temp URL expires ·
started {d['start'] or '—'} · auto-refreshes every 15s</div>
<div class=big><div></div></div>
<div class=sub>{d['done_pct']:.1f}% · {d['ok']:,} of {TARGET:,} images permanently archived</div>
<div class=grid>
  <div class=card><div class=k>Archived OK</div><div class=v>{d['ok']:,}</div></div>
  <div class=card><div class=k>Failed (will retry)</div><div class=v>{d['fail']:,}</div></div>
  <div class=card><div class=k>Pace</div><div class=v>{d['rate']:.1f}s/img</div></div>
  <div class=card><div class=k>Time remaining</div><div class=v>{human(d['eta_s']) if d['running'] else '—'}</div></div>
  <div class=card><div class=k>Done at ~</div><div class=v>{eta_clock}</div></div>
</div>
<table>{''.join(bars)}</table>
<div class=foot>Archived copies live at web.archive.org and never expire · failed items are
re-scraped with fresh URLs in later rounds (up to 3) · job is resumable if interrupted</div>
</body></html>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = page().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8351)))
    port = ap.parse_args().port
    print(f"progress tracker on http://127.0.0.1:{port}", flush=True)
    HTTPServer(("127.0.0.1", port), H).serve_forever()
