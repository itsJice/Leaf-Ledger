"""A client group's own read-only view of the install board.

A client share link (``ll_app.client_share_links``, app/apis/client_share)
lets one client group -- M Crowd, Mi Cocina's restaurant group, to start --
subscribe to its own installs without signing in. The feed is built from the
same resolved board the office calendar reads (``schedule_board.load_board``)
and the same stop arithmetic (``install_calendar.day_timeline``, the server
twin of the tool's ``stopTimes()``), so the client sees the times staff see.

What leaves the building is deliberately tiny. For each matching location and
visit: the location's name, its street address, the date, the arrive/finish
window and whether it is an install or a takedown. Nothing else -- no other
client, no price, crew, staff, phone, email, note, board row or client id.
``visits()`` is the only place board data is read, and it copies out just
those fields; the ICS and CSV writers only ever see its output.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from app.libs import install_calendar as cal
from app.libs.schedule_board import Board

COMPANY = "The Branch Design Group (TBDG)"
DESCRIPTION = {
    "Install": f"After-hours install by {COMPANY}. Times are estimates.",
    "Takedown": f"After-hours takedown by {COMPANY}. Times are estimates.",
}
#: A stop with no hours on the board still gets a visible block.
MIN_EVENT_MIN = 30


@dataclass(frozen=True)
class Rule:
    """Which board clients a share link shows, and how it names them.

    ``name_prefix`` matches board client names case-insensitively
    ("M Crowd " matches "M Crowd Lakewood"); ``client_names`` holds every
    spelling (name, sheet name, former names) of the clients picked by id.
    ``strip_prefix`` is removed from the front of the shown name."""
    name_prefix: str = ""
    client_names: frozenset = frozenset()
    strip_prefix: str = ""


@dataclass(frozen=True)
class Visit:
    location: str
    address: str
    date: str          # the board date (a night shift runs into the next morning)
    start: float       # minutes after midnight of ``date``
    end: float
    kind: str          # "Install" | "Takedown"
    uid: str


def _fold(s: str) -> str:
    return " ".join(str(s or "").split()).casefold()


def matches(rule: Rule, *names: Optional[str]) -> bool:
    prefix = _fold(rule.name_prefix)
    for n in names:
        if not n:
            continue
        if prefix and _fold(n).startswith(prefix):
            return True
        if cal.norm_name(n) in rule.client_names:
            return True
    return False


def display_name(rule: Rule, name: str) -> str:
    name = " ".join(str(name or "").split())
    strip = " ".join(rule.strip_prefix.split())
    if strip and name.casefold().startswith(strip.casefold()):
        rest = name[len(strip):].strip()
        if rest:
            return rest
    return name


def is_takedown(day_iso: str, visit_type: Optional[str]) -> bool:
    """"if its before christmas its an install oct-dec 25 if its after dec25
    - feb its a take down" (the user); a Takedown visit type wins."""
    if str(visit_type or "").strip().lower() == "takedown":
        return True
    d = date.fromisoformat(day_iso)
    return d.month <= 2 or (d.month == 12 and d.day >= 26)


def _uid(location: str, kind: str, n: int) -> str:
    """Stable per location + visit kind + nth visit, so a moved date updates
    the same calendar event. Hashed: no board row or client id leaks."""
    h = hashlib.sha256(f"{cal.norm_name(location)}|{kind}|{n}".encode()).hexdigest()[:20]
    return f"tbdg-share-{h}@leaf-and-ledger"


def visits(board: Board, rule: Rule, names: Optional[dict] = None) -> list[Visit]:
    """Every visit to a matching location, one per location per date. A
    joint stop (two crews at one location the same night) is ONE visit from
    the earlier crew's arrival to the later crew's finish. ``names`` maps a
    board row to its current name when renamed since the board was built."""
    names = names or {}
    spans: dict[tuple, list] = {}
    for day in board.days.values():
        rows = [r for r in day["stops"]
                if matches(rule, (board.clients.get(r) or {}).get("name"), names.get(r))]
        if not rows:
            continue
        tl = cal.day_timeline(board, day)
        for s in tl["stops"]:
            if s["row"] not in rows:
                continue
            key = (s["row"], day["date"])
            cur = spans.get(key)
            spans[key] = [min(cur[0], s["start"]), max(cur[1], s["end"])] if cur else [s["start"], s["end"]]

    out, seen = [], {}
    for (row, day_iso), (start, end) in sorted(spans.items(), key=lambda kv: (kv[0][1], kv[1][0])):
        c = board.clients.get(row) or {}
        location = display_name(rule, names.get(row) or c.get("name") or "")
        kind = "Takedown" if is_takedown(day_iso, c.get("visitType")) else "Install"
        n = seen[(location, kind)] = seen.get((location, kind), 0) + 1
        out.append(Visit(location=location, address=cal._address(c), date=day_iso,
                         start=start, end=max(end, start + MIN_EVENT_MIN), kind=kind,
                         uid=_uid(location, kind, n)))
    return out


# ---------- iCalendar ----------

def build_ics(label: str, vs: Iterable[Visit], now: Optional[datetime] = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    name = f"TBDG Christmas Installs – {label}"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Leaf & Ledger//Client Schedule//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{cal._esc(name)}",
             f"NAME:{cal._esc(name)}", f"X-WR-TIMEZONE:{cal.TZID}",
             "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    lines += cal.VTIMEZONE
    for v in vs:
        lines += ["BEGIN:VEVENT", f"UID:{v.uid}", f"DTSTAMP:{stamp}",
                  f"DTSTART;TZID={cal.TZID}:{cal._local(v.date, v.start)}",
                  f"DTEND;TZID={cal.TZID}:{cal._local(v.date, v.end)}",
                  f"SUMMARY:{cal._esc(f'{v.location} – TBDG Christmas {v.kind.lower()}')}"]
        if v.address:
            lines.append(f"LOCATION:{cal._esc(v.address)}")
        lines += [f"DESCRIPTION:{cal._esc(DESCRIPTION[v.kind])}", "TRANSP:OPAQUE", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(f for line in lines for f in cal._fold(line)) + "\r\n"


# ---------- CSV ----------

CSV_COLUMNS = ("Night", "Location", "Address", "Arrive", "Finish", "Type")


def clock(day_iso: str, minutes: float) -> str:
    """12-hour Central clock time, e.g. "11:00 PM"."""
    d = date.fromisoformat(day_iso)
    t = datetime(d.year, d.month, d.day) + timedelta(minutes=round(minutes))
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def night_label(day_iso: str) -> str:
    d = date.fromisoformat(day_iso)
    return f"{d.strftime('%a')} {d.month}/{d.day}/{d.year}"


def _cell(v: str) -> str:
    """Spreadsheet-formula guard: a cell never starts with = + - @."""
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def csv_rows(vs: list[Visit]) -> list[tuple]:
    rows = [(night_label(v.date), v.location, v.address, clock(v.date, v.start),
             clock(v.date, v.end), v.kind) for v in vs]
    # Already in date-then-arrival order (visits()); takedowns not yet on the
    # board get one TBD line per location.
    with_takedown = {v.location for v in vs if v.kind == "Takedown"}
    addr = {}
    for v in vs:
        addr.setdefault(v.location, v.address)
    for loc in sorted(addr, key=str.casefold):
        if loc not in with_takedown:
            rows.append(("TBD", loc, addr[loc], "TBD", "TBD", "Takedown – TBD"))
    return rows


def build_csv(vs: list[Visit]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_COLUMNS)
    for r in csv_rows(vs):
        w.writerow([_cell(str(x)) for x in r])
    return buf.getvalue()
