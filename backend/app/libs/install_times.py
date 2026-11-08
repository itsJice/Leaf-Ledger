"""Install Times: the pure rules behind the tracker (no database, no board).

How long each install really took, every year, so estimates improve. The
office (and crew leads, for their own crew-days) type the crew's Arrive and
Leave times; Claude types them from crew sheets. Everything here is a pure
function so the rules are pinned by value tests
(``tests/test_install_times.py``) and the frontend twin
(``frontend/src/utils/installTimes.ts``) can follow the same spec:

* **Fast typing.** ``"10:15p"``, ``"1:30a"``, ``"1030pm"``, ``"10:15 PM"``,
  ``"22:15"``, ``"10p"``, ``"noon"`` and ``"midnight"`` all parse. A time with
  no am/pm is read the way the shift runs: on a **day** shift 7 to 11 is
  morning and 12 to 6 is afternoon; on a **night** shift (Dallas) 6 to 11 is
  evening, 12 is midnight and 1 to 5 is early morning. 24-hour times
  (``"22:15"``, ``"0015"``) are taken as written.
* **Dates.** A crew-day's date is the date the shift STARTS (a night shift
  that runs 11/2 to 11/3 is the 11/2 crew-day). On a night shift an arrival
  before noon is the next calendar morning. A Leave time earlier than the
  Arrive time is the next day: 10:15 PM to 1:30 AM is 3 h 15 min, not
  minus 20 h.
* All wall-clock times are Central (``America/Chicago``); timestamps are
  stored timezone-aware.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")

KINDS = ("install", "takedown")
SOURCES = ("office", "lead", "claude", "imported_sheet", "comment_parsed")
#: What the reports group by (see job_type_of).
JOB_TYPES = ("residential", "commercial", "restaurant")

PEOPLE_MAX = 40
NOTE_MAX = 2000
#: A visit longer than this is almost surely a typo (wrong am/pm).
LONG_VISIT_H = 16.0

_SUFFIX = re.compile(r"(a\.?m?\.?|p\.?m?\.?)$")


class TimeParseError(ValueError):
    """A typed time we could not read. The message is safe to show staff."""


def parse_clock(text: str, *, night: bool = False) -> Optional[int]:
    """Minutes after midnight (0..1439) for a typed clock time, or None for
    blank. Raises TimeParseError for anything unreadable."""
    s = re.sub(r"\s+", "", str(text or "").lower())
    if not s:
        return None
    if s in ("noon", "12n"):
        return 12 * 60
    if s in ("midnight", "12m"):
        return 0
    bad = TimeParseError(f'Can\'t read "{str(text).strip()}" as a time. Try 10:15p or 1:30a.')
    ap = ""
    m = _SUFFIX.search(s)
    if m:
        ap, s = m.group(1)[:1], s[: m.start()]
    if re.fullmatch(r"\d{1,2}[:.]\d{2}", s):
        hs, ms = re.split(r"[:.]", s)
    elif re.fullmatch(r"\d{1,4}", s):
        hs, ms = (s, "0") if len(s) <= 2 else (s[:-2], s[-2:])
    else:
        raise bad
    h, mi = int(hs), int(ms)
    if mi > 59:
        raise TimeParseError(f'"{str(text).strip()}": minutes must be 00 to 59.')
    if ap:
        if not 1 <= h <= 12:
            raise TimeParseError(f'"{str(text).strip()}": with am/pm the hour must be 1 to 12.')
        return ((h % 12) + (12 if ap == "p" else 0)) * 60 + mi
    if h > 23:
        raise TimeParseError(f'"{str(text).strip()}": the hour must be 0 to 23.')
    # Written as 24-hour ("22:15", "0015", "09:30") -- take it as written.
    if h == 0 or h >= 13 or (len(hs) == 2 and hs.startswith("0")):
        return h * 60 + mi
    # 1..12 with no am/pm: read it the way the shift runs.
    if night:
        if 6 <= h <= 11:
            h += 12  # evening
        elif h == 12:
            h = 0  # midnight
        # 1..5 stay early morning
    elif 1 <= h <= 6:
        h += 12  # afternoon; 7..11 morning, 12 noon
    return h * 60 + mi


def fmt_clock(minutes: Optional[int]) -> str:
    """Minutes after midnight as 12-hour text: 1335 -> "10:15 PM"."""
    if minutes is None:
        return ""
    h, mi = divmod(int(minutes) % (24 * 60), 60)
    ap = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12}:{mi:02d} {ap}"


def visit_times(day: str, arrive_min: Optional[int], depart_min: Optional[int], *,
                night: bool = False) -> tuple[Optional[datetime], Optional[datetime]]:
    """Central timestamps for a visit on crew-day ``day`` (ISO date).

    Night shift: an arrival before noon is the next morning. A Leave earlier
    than (or equal to) the Arrive is the next day. With no Arrive, a Leave is
    placed like an arrival would be."""
    d = date.fromisoformat(day)

    def at(minutes: int, base: date) -> datetime:
        return datetime(base.year, base.month, base.day, tzinfo=TZ) + timedelta(minutes=minutes)

    def first_on(minutes: int) -> datetime:
        base = d + timedelta(days=1) if night and minutes < 12 * 60 else d
        return at(minutes, base)

    arrive = first_on(arrive_min) if arrive_min is not None else None
    depart = None
    if depart_min is not None:
        if arrive is None:
            depart = first_on(depart_min)
        else:
            depart = at(depart_min, arrive.date())
            if depart <= arrive:
                depart += timedelta(days=1)
    return arrive, depart


def on_site_hours(arrive: Optional[datetime], depart: Optional[datetime]) -> Optional[float]:
    if arrive is None or depart is None:
        return None
    # Through UTC: two datetimes sharing a tzinfo subtract as wall clocks,
    # which would lose (or gain) the DST hour on the first November night.
    span = depart.astimezone(timezone.utc) - arrive.astimezone(timezone.utc)
    return round(span.total_seconds() / 3600, 2)


def clock_of(ts: Optional[datetime]) -> Optional[int]:
    """A timestamp's Central wall-clock minutes (the inverse of visit_times)."""
    if ts is None:
        return None
    local = ts.astimezone(TZ)
    return local.hour * 60 + local.minute


def difference(est_h: Optional[float], actual_h: Optional[float]) -> dict:
    """Actual minus estimate, in hours and as a percent of the estimate.
    Missing either side gives Nones (shown as "not entered"), never zero."""
    if est_h is None or actual_h is None:
        return {"diffHours": None, "diffPct": None}
    diff = round(actual_h - est_h, 2)
    pct = round(diff / est_h * 100, 1) if est_h else None
    return {"diffHours": diff, "diffPct": pct}


def kind_for_date(day: str, season: str) -> str:
    """Takedown runs Dec 26 onward (the board's hard TAKEDOWN divider)."""
    return "takedown" if day > f"{season}-12-25" else "install"


def job_type_of(client: dict) -> Optional[str]:
    """Report bucket for a board client: M Crowd stops are restaurants, then
    the board's Business/Residence flag. None when the board doesn't say."""
    if str(client.get("cat") or "") == "M Crowd" or str(client.get("name") or "").startswith("M Crowd"):
        return "restaurant"
    bus = str(client.get("bus") or "").lower()
    if bus.startswith("bus"):
        return "commercial"
    if bus.startswith("res"):
        return "residential"
    return None


@dataclass
class Entry:
    """A typed visit, validated: what goes into one install_actuals row."""
    arrive_at: Optional[datetime]
    depart_at: Optional[datetime]
    hours: Optional[float]
    warnings: list[str]


def build_entry(day: str, arrive_text: str, depart_text: str, *, night: bool) -> Entry:
    """Parse both typed times for crew-day ``day`` and place them in time.
    Raises TimeParseError for unreadable text; soft problems (a very long
    visit, past the 8 AM Dallas stop) come back as warnings, never blocks."""
    a = parse_clock(arrive_text, night=night)
    d = parse_clock(depart_text, night=night)
    arrive, depart = visit_times(day, a, d, night=night)
    hours = on_site_hours(arrive, depart)
    warnings = []
    if hours is not None and hours > LONG_VISIT_H:
        warnings.append(f"{hours:g} h on site looks too long. Check am/pm.")
    if night and depart is not None and depart.date() > date.fromisoformat(day) and clock_of(depart) > 8 * 60:
        warnings.append("Left after 8 AM, past the Dallas hard stop.")
    return Entry(arrive, depart, hours, warnings)


# ─── reports ─────────────────────────────────────────────────────────────────


def _avg(xs: list[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 2) if xs else None


def _group(rows: Iterable[dict], key) -> dict:
    out: dict = {}
    for r in rows:
        k = key(r)
        if k is None or k == "":
            continue
        out.setdefault(k, []).append(r)
    return out


def summarize(rows: list[dict]) -> dict:
    """Report rollups from latest-actual rows (each with season, kind,
    clientName, clientId, crewLead, jobType, night, estHours, actualHours).
    A group's totals count only visits with BOTH an estimate and an actual
    time, so a missing time never reads as zero; ``missing`` says how many
    were left out."""

    def roll(rs: list[dict]) -> dict:
        both = [r for r in rs if r.get("estHours") is not None and r.get("actualHours") is not None]
        est = round(sum(r["estHours"] for r in both), 2) if both else None
        act = round(sum(r["actualHours"] for r in both), 2) if both else None
        return {
            "visits": len(rs),
            "compared": len(both),
            "missing": len(rs) - len(both),
            "estHours": est,
            "actualHours": act,
            "avgActualHours": _avg([r["actualHours"] for r in rs if r.get("actualHours") is not None]),
            **difference(est, act),
        }

    by_lead = [{"crewLead": k, **roll(v)} for k, v in sorted(_group(rows, lambda r: r.get("crewLead")).items())]
    types = {
        "residential": [r for r in rows if r.get("jobType") == "residential" and not r.get("night")],
        "commercial": [r for r in rows if r.get("jobType") == "commercial" and not r.get("night")],
        "restaurant": [r for r in rows if r.get("jobType") == "restaurant"],
        "dallas_night": [r for r in rows if r.get("night")],
    }
    by_type = [{"type": k, **roll(v)} for k, v in types.items()]

    clients: dict = {}
    for r in rows:
        if r.get("kind") != "install":
            continue
        key = r.get("clientId") or r.get("clientName")
        if not key:
            continue
        c = clients.setdefault(key, {"clientId": r.get("clientId"), "clientName": r.get("clientName"), "seasons": {}})
        s = c["seasons"].setdefault(str(r["season"]), {"estHours": None, "actualHours": None, "visits": 0, "missing": 0})
        s["visits"] += 1
        if r.get("actualHours") is None:
            s["missing"] += 1
        else:
            s["actualHours"] = round((s["actualHours"] or 0) + r["actualHours"], 2)
        if r.get("estHours") is not None:
            s["estHours"] = round((s["estHours"] or 0) + r["estHours"], 2)
    by_client = sorted(clients.values(), key=lambda c: str(c["clientName"] or "").lower())
    return {"byLead": by_lead, "byType": by_type, "byClient": by_client}
