#!/usr/bin/env python3
"""Pull the 2025 season's real crew lists out of the client workbook into
``backend/app/data/crew_history_2025.json`` for the install & takedown profit
view (backend ``app.libs.season_history``).

Two tabs hold who actually worked, day by day (user: "about 3 weeks of real
data on who and how many"):

* "2025 Christmas Install Crew Sch" -- three blocks of day columns, each with
  a "# PPL Needed" row, then one name per row, then an INSTALLS list:
    - cols B-E: a four-day block whose weekday/date headers were left over
      from another sheet ("Saturday ... Tuesday", Jan 10-13). The jobs listed
      under it date it: Lynell Wright 11/19, Byler 11/20, Akinola/Hug Away/
      Semple/Hensley/Eilers 11/21, Sikkel 11/22. So it is Nov 19-22.
    - cols K-Q: Mon Nov 24 - Sun Nov 30.
    - cols X-AD: Mon Dec 1 - Sun Dec 7.
* "2025 Christmas Takedown Crew Sc" -- Crew "A" Jan 10-13 (cols B-E) and
  Crew "B" Jan 10-16 (cols K-Q). The INSTALLS lists and the right-hand block
  on this tab are copies of the install tab, so they are ignored.

A day's names run down its column from the first name row to the first blank
cell. A day's list is everyone working that date, across however many crews went
out. Cells that are notes rather than people ("RELIGHT", "CHRIS CREW",
"Start Crane by 2pm", "(Banks)") are kept as notes; "Laura/Reyna" style cells
are split; "(1/2 day)" counts as half a person-day; "(EXC)" marks a temp from
Xclusive Staffing.

Run from scheduler/:  python3 extract_crew_history.py [--file workbook.xlsx]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "CHRISTMAS CLIENTS - Storage - Delivery - Install +Takedown.xlsx")
OUT = os.path.join(HERE, "..", "backend", "app", "data", "crew_history_2025.json")

INSTALL_TAB = "2025 Christmas Install Crew Sch"
TAKEDOWN_TAB = "2025 Christmas Takedown Crew Sc"

#: (tab, kind, crew, {column: date}, first name row, "# PPL Needed" row)
BLOCKS = [
    (INSTALL_TAB, "install", None,
     {1: "2025-11-19", 2: "2025-11-20", 3: "2025-11-21", 4: "2025-11-22"}, 5, 4),
    (INSTALL_TAB, "install", None,
     {10 + i: (dt.date(2025, 11, 24) + dt.timedelta(days=i)).isoformat() for i in range(7)}, 4, 3),
    (INSTALL_TAB, "install", None,
     {23 + i: (dt.date(2025, 12, 1) + dt.timedelta(days=i)).isoformat() for i in range(7)}, 4, 3),
    (TAKEDOWN_TAB, "takedown", "A",
     {1 + i: (dt.date(2026, 1, 10) + dt.timedelta(days=i)).isoformat() for i in range(4)}, 5, 4),
    (TAKEDOWN_TAB, "takedown", "B",
     {10 + i: (dt.date(2026, 1, 10) + dt.timedelta(days=i)).isoformat() for i in range(7)}, 5, 4),
]

NOTE_RE = re.compile(r"^(relight|\(banks\)|start crane.*)$", re.I)
#: A label that starts a second crew on the same date.
CREW_RE = re.compile(r"^(chris crew|kenneth team)$", re.I)
STOP_RE = re.compile(r"^installs?$", re.I)


def clean_person(raw: str) -> list[dict]:
    """One cell -> the people in it: [{name, half, temp, note}]."""
    out = []
    # Split "Laura/Reyna" on the slash, but never inside "(1/2 day)".
    for part in re.split(r"\s*/\s*(?![^(]*\))", raw.strip()):
        if not part:
            continue
        half = bool(re.search(r"1/2 day", part, re.I))
        temp = bool(re.search(r"\(exc\)", part, re.I))
        tag = re.findall(r"\(([^)]*)\)", part)
        name = re.sub(r"\(.*?\)", "", part).strip(" .")
        if name:
            out.append({"name": name.title() if name.isupper() else name, "half": half, "temp": temp,
                        "tags": [t for t in tag if t.lower() not in ("1/2 day", "exc")]})
    return out


CLIENT_TAB = "2025 Christmas"
#: 2025 tab columns (0-based), by header.
JOB_COLS = {
    "name": "TBDG CLIENT", "dallas": "Dallas Crew", "leads": "# CREW LEADS NEEDED",
    "specialty": "# SPECIALTY LABOR (SCAFFOLDING EXTRA TALL LADDER)", "designer": "# DESIGNER / ART DIRECTOR",
    "general": "# GENERAL INSTALLERS NEEDED", "est_hours": "ESTIMATED TOTAL HOURS FOR INSTALL",
    "crew": "Crew Name", "td_est": "ESTIMATED TOTAL HOURS FOR Takedown",
    "td_hours": "2026 Real Hours For Takedown", "td_start": "2026 Real Start", "td_end": "2026 Real End",
}
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)?", re.I)


def _num(v):
    try:
        return float(str(v).strip()) if v not in (None, "") else None
    except ValueError:
        return None


def _minutes(t) -> int | None:
    if isinstance(t, dt.datetime):
        t = t.time()
    if isinstance(t, dt.time):
        return t.hour * 60 + t.minute
    return None


def note_times(text: str) -> tuple[int, int] | None:
    """First and last clock time in a typed note ("Arrived 8:45 am ...
    Finished 9:45 am", "12:50- 1:20"), as minutes after midnight. A time with
    no am/pm before 7 is taken as afternoon -- crews do not start at 1 am."""
    found = []
    for h, m, ap in TIME_RE.findall(text or ""):
        h, m = int(h), int(m)
        ap = ap.lower()
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        elif not ap and h < 7:
            h += 12
        found.append(h * 60 + m)
    if len(found) < 2:
        return None
    return found[0], found[-1]


def daytime(start: int, end: int) -> tuple[int, int]:
    """Make a typed start/end pair read as a working day: anything before
    7 am is afternoon (the sheet's time cells carry no am/pm, so "02:15" is
    2:15 pm), an end before its start is later that day, and an end more
    than 12 hours after its start had a stray "pm" ("Finished 11:50 pm" on a
    job that started at 11:15)."""
    if start < 7 * 60:
        start += 12 * 60
    if end < 7 * 60:
        end += 12 * 60
    if end < start:
        end += 12 * 60
    if end - start > 12 * 60:
        end -= 12 * 60
    return start, end


def extract_jobs(wb) -> list[dict]:
    """Per job, what the database does not keep: the full crew cell (the
    database stores only its first line), the install estimate and role
    needs, and takedown times that were typed as notes."""
    rows = [list(r) for r in wb[CLIENT_TAB].iter_rows(values_only=True)]
    hdr = rows[0]
    idx = {k: next((i for i, h in enumerate(hdr) if h == v), None) for k, v in JOB_COLS.items()}
    out = []
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        g = lambda k: r[idx[k]] if idx[k] is not None and idx[k] < len(r) else None
        crew = str(g("crew") or "").strip()
        td = None
        s, e = _minutes(g("td_start")), _minutes(g("td_end"))
        if s is not None and e is not None:
            s, e = daytime(s, e)
            td = {"start": s, "end": e, "source": "times"}
        else:
            for k in ("td_start", "td_hours", "td_est"):
                v = g(k)
                if isinstance(v, str) and (t := note_times(v)):
                    a, b = daytime(*t)
                    td = {"start": a, "end": b, "source": "note", "note": " ".join(v.split())}
                    break
        out.append({
            "name": str(r[0]).strip(),
            "crew_lines": [ln.strip() for ln in crew.splitlines() if ln.strip()],
            "dallas_crew": [ln.strip() for ln in str(g("dallas") or "").splitlines() if ln.strip()],
            "est_hours": _num(g("est_hours")),
            "role_need": {k: int(_num(g(k)) or 0) for k in ("leads", "specialty", "designer", "general")},
            "takedown_real": td,
        })
    return out


def extract(path: str) -> dict:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    days = []
    for tab, kind, crew, cols, first_row, ppl_row in BLOCKS:
        rows = [list(r) for r in wb[tab].iter_rows(values_only=True)]
        for col, date in cols.items():
            ppl = rows[ppl_row][col] if col < len(rows[ppl_row]) else None
            try:
                ppl = int(float(ppl)) if ppl not in (None, "") else None
            except (TypeError, ValueError):
                ppl = None
            people, notes = [], []
            # Install tab: names run down to the INSTALLS row; a blank row may
            # separate a second crew working the same date ("CHRIS CREW",
            # "Kenneth Team"), whose people follow its label. Takedown tab:
            # names stop at the first blank -- below it are leftovers copied
            # from the install tab.
            group = "main"
            for r in rows[first_row:]:
                lo, hi = min(cols) - 1, max(cols)
                if any(STOP_RE.match(str(c).strip()) for c in r[lo:hi + 1] if c is not None):
                    break
                v = r[col] if col < len(r) else None
                if v is None or str(v).strip() == "":
                    if kind == "takedown":
                        break
                    continue
                s_ = str(v).strip()
                if CREW_RE.match(s_):
                    group = s_.title()
                    notes.append(s_)
                    continue
                if NOTE_RE.match(s_):
                    notes.append(s_)
                    continue
                for p_ in clean_person(s_):
                    p_["group"] = group
                    people.append(p_)
            if people or ppl:
                days.append({"date": date, "kind": kind, "crew": crew, "ppl_needed": ppl,
                             "people": people, "notes": notes})
    return {"source": os.path.basename(path), "tabs": [INSTALL_TAB, TAKEDOWN_TAB, CLIENT_TAB],
            "days": days, "jobs": extract_jobs(wb)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=SRC)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    data = extract(a.file)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print(f"{len(data['days'])} crew-days, {len(data['jobs'])} jobs -> {a.out}")
    for j in data["jobs"]:
        if j["takedown_real"]:
            t = j["takedown_real"]
            print(f"  takedown {j['name'][:34]:34s} {t['start']//60:02d}:{t['start']%60:02d}-{t['end']//60:02d}:{t['end']%60:02d} ({t['source']})")
    for d in data["days"]:
        who = ", ".join(p["name"] + (" (1/2)" if p["half"] else "") + (" [EXC]" if p["temp"] else "")
                        + (f" <{p['group']}>" if p.get("group", "main") != "main" else "") for p in d["people"])
        print(f"  {d['date']} {d['kind']:8s} {d['crew'] or '-'}  need {d['ppl_needed']!s:>4}  have {len(d['people']):2d}: {who}"
              + (f"  | notes: {d['notes']}" if d["notes"] else ""))


if __name__ == "__main__":
    main()
