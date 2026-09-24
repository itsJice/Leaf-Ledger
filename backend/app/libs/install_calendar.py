"""The install board as an iCalendar (.ics) feed the office subscribes to.

Every crew-day becomes a run of timed events, the same day shape the review
tool's run sheet prints:

    arrive at the branch (30 min before roll-out)
    drive to stop 1 -> install stop 1 -> drive to stop 2 -> ... -> drive back

The times are estimates. When the tool has saved its own stop times for a day
(``state.timeline``, written by ``snapshot()`` in review_template.html) those
are used verbatim, so the calendar matches what staff see on screen. Otherwise
they are rebuilt here with the tool's arithmetic -- ``shiftStart()`` and
``stopTimes()`` -- over the stop order resolved by ``schedule_board``. If
either side's arithmetic changes, change both.

It is one feed for every crew. A subscribed Google calendar gets a single
colour, so crews are told apart by the emoji leading each event's title.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional
from urllib.parse import quote_plus

from app.libs.schedule_board import Board

TZID = "America/Chicago"
ARRIVE_LEAD_MIN = 30              # arrive 8:00 for the 8:30 roll-out
DEPART_MIN = 8 * 60 + 30          # DEPART_MIN in the tool
DAYTIME_WINDOW = 480              # the 9-5 corporate install (shiftStart)
ROAD_FUDGE, EST_AVG_MPH = 1.35, 27  # the tool's estSeconds() fallback
CREW_EMOJI = {"Crew 1": "🔴", "Crew 2": "🟢", "Crew 3": "⚪️"}

# Static zone definition: US Central, current (2007+) DST rules. Shipped
# inline so the feed needs no tz database in the container.
VTIMEZONE = (
    "BEGIN:VTIMEZONE", f"TZID:{TZID}", f"X-LIC-LOCATION:{TZID}",
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0600", "TZOFFSETTO:-0500", "TZNAME:CDT",
    "DTSTART:19700308T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:-0500", "TZOFFSETTO:-0600", "TZNAME:CST",
    "DTSTART:19701101T020000", "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD",
    "END:VTIMEZONE",
)


# ---------- drive times ----------

def _haversine_mi(a: tuple, b: tuple) -> float:
    r, rad = 3958.8, math.radians
    dlat, dlon = rad(b[0] - a[0]), rad(b[1] - a[1])
    s = math.sin(dlat / 2) ** 2 + math.cos(rad(a[0])) * math.cos(rad(b[0])) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(s))


def _latlon(board: Board, row: Optional[int]) -> Optional[tuple]:
    c = board.depot if row is None else board.clients.get(row) or {}
    lat, lon = c.get("lat"), c.get("lon")
    return (lat, lon) if lat is not None and lon is not None else None


def leg_seconds(board: Board, a: Optional[int], b: Optional[int]) -> float:
    """Drive seconds from row ``a`` to row ``b`` (``None`` = the branch).

    Real clients read the OSRM matrix. A client added in the tool has no node
    but carries its own OSRM row/column against the real nodes (outRow/inCol);
    anything else falls back to the tool's straight-line estimate.
    """
    D = board.durs
    na = 0 if a is None else board.node.get(a)
    nb = 0 if b is None else board.node.get(b)
    if na is not None and nb is not None and na < len(D) and nb < len(D[na]):
        return D[na][nb] or 0
    ca = {} if a is None else board.clients.get(a) or {}
    cb = {} if b is None else board.clients.get(b) or {}
    if na is None and nb is not None and nb < len(ca.get("outRow") or []):
        return ca["outRow"][nb] or 0
    if nb is None and na is not None and na < len(cb.get("inCol") or []):
        return cb["inCol"][na] or 0
    pa, pb = _latlon(board, a), _latlon(board, b)
    if pa and pb:
        return round(_haversine_mi(pa, pb) * ROAD_FUDGE / EST_AVG_MPH * 3600)
    return 0


# ---------- one crew-day's timeline ----------

def shift_start(meta: dict, const: dict) -> int:
    """Minutes after midnight the crew rolls out -- the tool's shiftStart()."""
    win = meta.get("win")
    if const.get("NIGHT") is not None and win == const["NIGHT"]:
        return 23 * 60
    if win == DAYTIME_WINDOW:
        return 9 * 60
    return DEPART_MIN


def day_timeline(board: Board, day: dict) -> dict:
    """``{start, anchored, stops: [{row, start, end}], back}`` in minutes
    after midnight of the day's date (a night shift runs past 1440)."""
    meta = board.day_meta.get(day["id"]) or {}
    anchored = meta.get("anchored") is not False
    saved = board.timeline.get(day["id"])
    if isinstance(saved, dict) and sorted(s.get("row") for s in saved.get("stops") or []) == sorted(day["stops"]):
        return {"start": saved.get("start", shift_start(meta, board.const)), "anchored": anchored,
                "stops": [{"row": int(s["row"]), "start": float(s["start"]), "end": float(s["end"])}
                          for s in saved["stops"]],
                "back": saved.get("back")}

    stacked = meta.get("stacked") or 1
    half = set(meta.get("half") or [])
    start = shift_start(meta, board.const)
    order = day["stops"]
    t = float(start)
    if anchored and order:
        t += leg_seconds(board, None, order[0]) / 60
    stops = []
    for i, row in enumerate(order):
        c = board.clients.get(row) or {}
        # A client added in the tool saves its estimate as "hours", not "h26".
        hours = float(c.get("h26") or c.get("hours") or 0)
        dur = (hours / 2 if row in half else hours) * 60 / stacked
        stops.append({"row": row, "start": t, "end": t + dur})
        t += dur
        if i + 1 < len(order):
            t += leg_seconds(board, row, order[i + 1]) / 60
    back = leg_seconds(board, order[-1], None) / 60 if anchored and order else None
    return {"start": start, "anchored": anchored, "stops": stops, "back": back}


# ---------- iCalendar ----------

def _esc(text: str) -> str:
    return (str(text).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> Iterable[str]:
    """RFC 5545 3.1: lines over 75 octets continue on a line starting with a space."""
    out, cur = [], b""
    for ch in line:
        enc = ch.encode("utf-8")
        if len(cur) + len(enc) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += enc
    out.append(cur.decode("utf-8"))
    return [out[0]] + [" " + x for x in out[1:]]


def _local(day_iso: str, minutes: float) -> str:
    d = date.fromisoformat(day_iso)
    dt = datetime(d.year, d.month, d.day) + timedelta(minutes=round(minutes))
    return dt.strftime("%Y%m%dT%H%M%S")


def _dur(minutes: float) -> str:
    m = round(minutes)
    if m < 60:
        return f"{m} min"
    h, r = divmod(m, 60)
    return f"{h} hr" if not r else f"{h} hr {r} min"


def _address(c: dict) -> str:
    return ", ".join(x for x in (c.get("street"), c.get("city"),
                                 " ".join(y for y in (c.get("st"), c.get("zip")) if y)) if x)


def _maps(c: dict) -> str:
    """Directions to the stop -- same link the lead pages use (lead.maps_url)."""
    addr = _address(c)
    if addr:
        return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(addr)}"
    if c.get("lat") is not None and c.get("lon") is not None:
        return f"https://www.google.com/maps/dir/?api=1&destination={c['lat']},{c['lon']}"
    return ""


def _crew_line(board: Board, day_id: str) -> str:
    people = [board.person(pid) for pid in board.staffing.get(day_id, [])]
    names = [p["name"] + (" (lead)" if p["title"] == "Lead" else "") for p in people if p]
    return ", ".join(names) or "Nobody assigned yet"


def day_events(board: Board, day: dict) -> list[dict]:
    """The crew-day as ``{uid, start, end, summary, location, description}``
    dicts (start/end in minutes after midnight of ``day['date']``)."""
    label = board.crew_label(day)
    label = f"{CREW_EMOJI[label]} {label}" if label in CREW_EMOJI else label
    tl = day_timeline(board, day)
    if not tl["stops"]:
        return []
    crew = _crew_line(board, day["id"])
    note = board.day_notes.get(day["id"], "")
    base = f"Crew: {crew}" + (f"\nDay note: {note}" if note else "")
    uid = re.sub(r"[^A-Za-z0-9-]+", "-", day["id"])
    events = []

    def add(kind: str, start: float, end: float, summary: str, **extra):
        if end - start >= 1:
            events.append({"uid": f"{uid}-{kind}@leaf-and-ledger", "start": start, "end": end,
                           "summary": f"{label} · {summary}", "location": "",
                           "description": base, **extra})

    first = board.clients.get(tl["stops"][0]["row"]) or {}
    if tl["anchored"]:
        add("arrive", tl["start"] - ARRIVE_LEAD_MIN, tl["start"], "Arrive at branch")
        add("drive-0", tl["start"], tl["stops"][0]["start"],
            f"Drive to {first.get('name', 'first stop')} "
            f"({_dur(tl['stops'][0]['start'] - tl['start'])})")

    for i, s in enumerate(tl["stops"]):
        c = board.clients.get(s["row"]) or {}
        name = c.get("name") or f"Row {s['row']}"
        lines = [f"Stop {i + 1} of {len(tl['stops'])} · est. {_dur(s['end'] - s['start'])}"]
        lines += [x for x in (_address(c), c.get("phone"), _maps(c)) if x]
        lines += [x for x in (c.get("advice"), c.get("repairNotes")) if x]
        add(f"stop-{s['row']}", s["start"], s["end"], f"{name} ({_dur(s['end'] - s['start'])})",
            location=_address(c), description="\n".join(lines) + "\n\n" + base)
        if i + 1 < len(tl["stops"]):
            nxt = tl["stops"][i + 1]
            nname = (board.clients.get(nxt["row"]) or {}).get("name") or f"Row {nxt['row']}"
            add(f"drive-{s['row']}", s["end"], nxt["start"],
                f"Drive to {nname} ({_dur(nxt['start'] - s['end'])})")

    if tl["anchored"] and tl.get("back"):
        end = tl["stops"][-1]["end"]
        add("return", end, end + tl["back"], f"Drive back to branch ({_dur(tl['back'])})")
    return events


def build_ics(board: Board, now: Optional[datetime] = None) -> str:
    """The whole season's board, every crew, as one VCALENDAR."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    name = f"L&L Installs {board.season}"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Leaf & Ledger//Install Schedule//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_esc(name)}",
             f"NAME:{_esc(name)}", f"X-WR-TIMEZONE:{TZID}",
             # Honoured by Apple/Outlook; Google refreshes on its own schedule.
             "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    lines += VTIMEZONE

    for day in sorted(board.days.values(), key=lambda d: (d["date"], board.crew_label(d))):
        for ev in day_events(board, day):
            lines += ["BEGIN:VEVENT", f"UID:{ev['uid']}", f"DTSTAMP:{stamp}",
                      f"DTSTART;TZID={TZID}:{_local(day['date'], ev['start'])}",
                      f"DTEND;TZID={TZID}:{_local(day['date'], ev['end'])}",
                      f"SUMMARY:{_esc(ev['summary'])}"]
            if ev["location"]:
                lines.append(f"LOCATION:{_esc(ev['location'])}")
            lines += [f"DESCRIPTION:{_esc(ev['description'])}", "TRANSP:OPAQUE", "END:VEVENT"]

    lines.append("END:VCALENDAR")
    return "\r\n".join(folded for line in lines for folded in _fold(line)) + "\r\n"
