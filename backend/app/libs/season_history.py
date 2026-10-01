"""A past season's install AND takedown crew-days, rebuilt from what really
happened: the real start and end time at every job, the real crews, and the
real invoices. Pure -- the install-costs API loads the inputs.

Where each fact comes from (user, 2026-10-01: "use real start stop times; all
crews arrived at 8 am; if there was real data for crews and number of people
on them default to that, if there is not, rely on the estimate"):

* **Jobs, dates, real times, invoices** -- the season row on the Clients tab
  (``install_date``, ``real_start``/``real_end``, ``crew``, ``crew_size``,
  ``takedown_date``, ``takedown_order``, ``invoice_total``, ``boxes``,
  ``storing``).
* **Who and how many** -- ``app/data/crew_history_<season>.json``, pulled from
  the client workbook by ``scheduler/extract_crew_history.py``: each job's full
  crew cell (the Clients tab keeps only its first line), the day-by-day crew
  lists from the crew schedule tabs (about three weeks), and takedown times
  that were typed as notes.
* **Drive times and miles** -- the current install board's road matrix and
  map points, matched by client name.

A crew-day's paid time runs from **8:00 am at the warehouse** to the crew's
return: loading, the drive out, every job from its real start to its real
end, the drives between, lunch, and the drive back. A job with no real times
takes its estimate and is placed after the crew's last timed job. Takedown
time is the job's real takedown time where one was written down, otherwise
its real install time x the card's takedown factor (0.6).

The crew, most specific first:
1. the names in the job's crew cell ("Lesly Crew / Alberto / Evlyn ..."),
2. the day's crew list from the crew schedule tabs, shared between that
   date's crews by on-site time ("CHRIS CREW" and "Kenneth Team" are their own
   crews),
3. a head count ("Crew A (6)", ``crew_size``) as one Lead and the rest General,
4. the estimate: the job's role needs.

Revenue (user): each job's (2025 invoice - storage) / 2 for the install and
the same again for the takedown; storage is boxes x the storage rate and pays
for the warehouse, which is overhead.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any, Optional

from app.libs import install_costs as ic
from app.libs.crew_day_profit import _haversine_mi, _num, _pt, _r, _status, norm_name, totals
from app.libs.install_calendar import ROAD_FUDGE, leg_seconds
from app.libs.schedule_board import Board

DAY_START = 8 * 60          # every crew arrives at the warehouse at 8:00
ARRIVE_MIN = 30             # before the first drive: at least this, or the loading
LUNCH_MIN = 40              # paid lunch on a day with no real clock times
DEFAULT_DRIVE_MIN = 30      # a leg the road matrix does not cover
DEFAULT_JOB_H = 2.0         # a job with no real time and no estimate at all
STORAGE_RATE = 75.0         # $ / box, the 2025 Rates tab

#: Leads (user, 2026-10-01), paid as Leads even before they are on the
#: roster. Someone on the roster is paid by their Settings pay class.
LEADS = {"lesly", "alberto", "chris", "justice", "karol", "reyna", "laura"}
#: Spellings in the sheets -> one first name.
ALIASES = {
    "nolbia": "nolvia", "nuirka": "niurka", "niurkita": "niurka", "evlyn": "evlynn",
    "reynita": "reinita", "erika": "ericka", "erica": "ericka", "daniella": "daniela",
    "gelibys": "gleibys", "julie": "julissa", "pilar": "pilar", "veronica": "merlin", "reina": "reyna",
}
#: Lines in a crew cell that are places or notes, not people.
NOT_PEOPLE = re.compile(r"woodlands|carlton|club|cc$|crew [a-z]$|^crew$|^\(|takedown|install", re.I)
WEEKDAY = re.compile(r"\s*-\s*(mon|tues|wednes|thurs|fri|satur|sun)day\b.*$", re.I)


# ---------------------------------------------------------------- helpers ----

def _hhmm(v: Any) -> Optional[int]:
    if not isinstance(v, str):
        return None
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*", v)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def daytime(start: int, end: int) -> tuple[int, int]:
    """A typed start/end as a working day (the sheet's time cells carry no
    am/pm): before 7 am is afternoon, an end before its start is later that
    day. Same rule as scheduler/extract_crew_history.py."""
    if start < 7 * 60:
        start += 12 * 60
    if end < 7 * 60:
        end += 12 * 60
    if end < start:
        end += 12 * 60
    if end - start > 12 * 60:
        end -= 12 * 60
    return start, end


def _date(v: Any) -> Optional[str]:
    """ISO date, or the first date of a range typed like "1/2-1/3, 2026"."""
    if not v:
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s[:10]):
        return s[:10]
    m = re.match(r"(\d{1,2})/(\d{1,2})\D.*?(\d{4})", s)
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            return None
    return None


def first_name(raw: str) -> str:
    n = re.sub(r"\(.*?\)", "", raw or "").strip().split(" ")[0].lower().strip(".,")
    return ALIASES.get(n, n)


def crew_label(lines: list[str], fallback: Optional[str]) -> tuple[str, list[str], Optional[int]]:
    """``(label, people named, head count)`` from a job's crew cell.

    "Lesly Crew / Alberto / Evlyn" -> ("Lesly", [Lesly, Alberto, Evlyn], None);
    "Crew A (6)" -> ("Crew A", [], 6); "Chris -Monday / Woodlands CC / Alberto"
    -> ("Chris", [Chris, Alberto], None)."""
    lines = [ln for ln in (lines or []) if ln.strip()] or ([fallback] if fallback else [])
    if not lines:
        return "", [], None
    head = lines[0]
    m = re.search(r"\((\d+)\)", head)
    count = int(m.group(1)) if m else None
    base = WEEKDAY.sub("", re.sub(r"\(.*?\)", "", head)).strip()
    people: list[str] = []
    led = re.match(r"^(\w+)\s*(crew)?$", base, re.I)
    if re.fullmatch(r"crew\s+[a-z]", base, re.I):
        label = base.title()
    elif led:
        label = led.group(1).title()
        people.append(label)
    else:                       # "Chris Wenz", "Justice Crew"
        label = base.split(" ")[0].title()
        people.append(base)
    for ln in lines[1:]:
        name = WEEKDAY.sub("", ln).strip()
        if name and not NOT_PEOPLE.search(name):
            people.append(name)
    return label, people, count


# ------------------------------------------------------------------ crews ----

class Payroll:
    """Who someone is paid as: the roster (with Settings pay classes) when the
    name is on it, a Lead for the crew leaders, otherwise a General Installer."""

    def __init__(self, card: dict, roster: list[dict], assignments: dict[str, dict]):
        self.card = card
        self.classes = {c["slug"]: c for c in card["classes"]}
        self.by_first: dict[str, dict] = {}
        for p in roster:
            k = first_name(p.get("name") or "")
            self.by_first.setdefault(k, p)
        self.assignments = assignments

    def seat(self, name: Optional[str], half: bool = False, temp: bool = False,
             slug: Optional[str] = None) -> dict:
        if name:
            p = self.by_first.get(first_name(name))
            if p:
                pr = ic.person_rate(p, self.assignments.get(p["id"]), self.card)
                return {"name": p["name"], "label": pr["label"], "rate": pr["rate"], "half": half,
                        "temp": temp, "on_roster": True}
            slug = "lead" if first_name(name) in LEADS else "general"
        cls = self.classes.get(slug or "general")
        return {"name": name, "label": (cls or {}).get("label", slug), "rate": (cls or {}).get("rate"),
                "half": half, "temp": temp, "on_roster": False}

    def count(self, n: int) -> list[dict]:
        """A head count with no names: one Lead, the rest General."""
        return [self.seat(None, slug="lead" if i == 0 else "general") for i in range(max(0, n))]


# --------------------------------------------------------------- the build ----

def _board_index(board: Optional[Board]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r, c in (board.clients if board else {}).items():
        for n in (c.get("name"), c.get("sheetName")):
            k = norm_name(n)
            if k and k not in out:
                out[k] = r
    return out


def _leg_min(board: Optional[Board], a: Optional[int], b: Optional[int], known: bool) -> float:
    if board is None or not known:
        return DEFAULT_DRIVE_MIN
    s = leg_seconds(board, a, b)
    return s / 60 if s else DEFAULT_DRIVE_MIN


def _miles(board: Optional[Board], rows: list[Optional[int]], anchored: bool) -> float:
    if board is None:
        return 0.0
    pts = [_pt(board.clients.get(r) or {}) if r is not None else None for r in rows]
    if anchored:
        pts = [_pt(board.depot)] + pts + [_pt(board.depot)]
    pts = [p for p in pts if p]
    return sum(_haversine_mi(a, b) for a, b in zip(pts, pts[1:])) * ROAD_FUDGE


def season_jobs(clients: list[dict], season: str, history: dict, board: Optional[Board]) -> list[dict]:
    """Every job of ``season`` with what the crew-days need, joined across the
    Clients tab, the workbook extract and the board."""
    extra = {}
    for j in history.get("jobs") or []:
        extra.setdefault(norm_name(j["name"]), j)
    bidx = _board_index(board)
    jobs = []
    for c in clients:
        row = next((a for a in c.get("activity") or []
                    if a.get("kind") == "christmas_install" and str(a.get("season")) == str(season)), None)
        if not row:
            continue
        d = row.get("detail") or {}
        if d.get("cancelled") or d.get("not_installing"):
            continue
        names = [c.get("name"), c.get("sheet_name"), *(c.get("former_names") or [])]
        x = next((extra[norm_name(n)] for n in names if norm_name(n) in extra), {})
        brow = next((bidx[norm_name(n)] for n in names if norm_name(n) in bidx), None)
        bc = (board.clients.get(brow) if board and brow is not None else None) or {}
        s, e = _hhmm(d.get("real_start")), _hhmm(d.get("real_end"))
        zip_ = str(d.get("zip") or c.get("zip") or "").strip()
        # Dallas-Fort Worth ZIPs start 75/76; those jobs ran as night shifts
        # from a hotel, not 8 am days from the Houston warehouse.
        dallas = zip_[:2] in ("75", "76") or bool(x.get("dallas_crew"))
        if s is not None and e is not None and not dallas:
            s, e = daytime(s, e)
        elif s is not None and dallas:
            # Night shift: a time before noon is after midnight.
            s = s + 24 * 60 if s < 12 * 60 else s
            if e is not None:
                e = e + 24 * 60 if e < 12 * 60 else e
                if e < s:
                    e += 24 * 60
        inv = _num(d.get("invoice_total"))
        boxes = int(_num(d.get("boxes")) or 0)
        storing = d.get("storing") is not False
        storage = boxes * STORAGE_RATE if storing else 0.0
        half = None if inv is None else max(0.0, inv - storage) / 2
        est_h = x.get("est_hours") or _num(bc.get("h26")) or _num(d.get("real_hours"))
        jobs.append({
            "client_id": c.get("id"), "name": c.get("name"), "row": brow, "geo": brow is not None,
            "install_date": _date(d.get("install_date")), "takedown_date": _date(d.get("takedown_date")),
            "takedown_order": _num(d.get("takedown_order")),
            "real_start": s, "real_end": e if s is not None else None,
            "real_h": ((e - s) / 60) if s is not None and e is not None else None,
            "est_h": est_h, "boxes": boxes, "storing": storing,
            "invoice": inv, "storage": storage, "half": half,
            "crew_lines": x.get("crew_lines") or ([d["crew"]] if d.get("crew") else []),
            "crew_size": _num(d.get("crew_size")),
            "role_need": x.get("role_need") or bc.get("roleNeed") or {},
            "takedown_real": x.get("takedown_real"), "dallas": dallas,
            "dallas_crew": x.get("dallas_crew") or [],
        })
    return jobs


def _timeline(board: Optional[Board], stops: list[dict], anchored: bool, card: dict,
              boxes: int, kind: str) -> dict:
    """Clock the crew's day: ``stops`` are ``{job, start, end}`` with real
    minutes where known (None otherwise) and ``dur`` minutes for estimates."""
    load_min = ic.value(card, "load_min_per_box") or 0
    timed = sorted((s for s in stops if s["start"] is not None), key=lambda s: s["start"])
    untimed = [s for s in stops if s["start"] is None]
    order = timed + untimed
    warehouse = boxes * load_min
    # Before the first drive: the 30-minute arrival or loading the trailer
    # (install); a takedown unloads at the end of the day instead.
    pre = max(ARRIVE_MIN, warehouse) if kind == "install" else ARRIVE_MIN
    post = warehouse if kind == "takedown" else 0
    t = None
    prev: Optional[dict] = None          # None = still at the warehouse
    drive_min = 0.0
    for s in order:
        j = s["job"]
        if prev is None and not anchored:
            leg = 0.0                     # away from the branch: the day starts at the first job
        else:
            known = j["geo"] and (prev is None or prev["geo"])
            leg = _leg_min(board, prev["row"] if prev else None, j["row"], known)
        if s["start"] is None:
            begin = (DAY_START + pre if t is None else t) + leg
            s["start"], s["end"] = begin, begin + s["dur"]
        elif s["end"] is None:          # a real start with no end written down
            s["end"] = s["start"] + s["dur"]
        drive_min += leg
        t = s["end"] if t is None else max(t, s["end"])
        prev = j
    prev_row = prev["row"] if prev else None
    back = _leg_min(board, prev_row, None, bool(prev and prev["geo"])) if anchored and order else 0.0
    if anchored:
        start = DAY_START
        end = t + back + post
        clocked = any(s["job"]["real_start"] is not None for s in order) if kind == "install" else \
            any(s.get("real") for s in order)
        # Real clock times already contain the lunch break; a day built from
        # estimates adds it.
        lunch = 0 if clocked else LUNCH_MIN
        # The clock from 8:00 to the return. Two jobs clocked over the same
        # hours (the crew split up) are inside that span once, not twice.
        paid = end - start + lunch
    else:
        start = order[0]["start"]
        end = t
        lunch = 0
        paid = end - start
    return {"order": order, "start": start, "end": end, "paid_min": paid, "drive_min": drive_min + back,
            "lunch_min": lunch, "pretrip_min": pre if anchored else 0}


def _estimate(pay: "Payroll", jobs: list[dict]) -> list[dict]:
    """The biggest job's role needs as seats (the whole crew rides together)."""
    best = max(jobs, key=lambda j: sum(int(v or 0) for v in (j["role_need"] or {}).values()))
    rn = best["role_need"] or {}
    return [pay.seat(None, slug=s) for k, s in (("leads", "lead"), ("specialty", "lead_assist"),
                                                 ("designer", "designer"), ("general", "general"))
            for _ in range(int(rn.get(k) or 0))]


def _crews_for_date(groups: dict[str, list[dict]], roster_days: list[dict], pay: "Payroll") -> dict[str, tuple[list, str]]:
    """Seats for every crew-day on one date: ``{label: (seats, source)}``.

    Most specific first: names in the jobs' crew cells; then the job's own
    head count ("Crew A (6)"), filled with people from the day's crew list
    who are not already on a named crew; then the day's crew list shared
    between the remaining crews by on-site time; then the estimate."""
    out: dict[str, tuple[list, str]] = {}
    used: set[str] = set()
    counts: dict[str, int] = {}
    for label, jobs in groups.items():
        named: list[str] = []
        count = 0
        for j in jobs:
            _, people, n = crew_label(j["crew_lines"], None)
            people = people + list(j.get("dallas_crew") or [])
            named += [p for p in people if first_name(p) not in {first_name(x) for x in named}]
            count = max(count, n or 0, int(j["crew_size"] or 0))
        if len(named) >= 2:
            out[label] = ([pay.seat(n) for n in named], "crew list")
            used |= {first_name(n) for n in named}
        elif count:
            counts[label] = count

    roster = [p for d in roster_days for p in d["people"]]
    by_group: dict[str, list[dict]] = {}
    for p in roster:
        by_group.setdefault(p.get("group") or "main", []).append(p)
    # A second crew named on the day's list ("CHRIS CREW") goes to the crew it leads.
    for g, people in list(by_group.items()):
        if g == "main":
            continue
        lead = g.split(" ")[0].title()
        target = next((lb for lb in groups if lb not in out and lb.lower().startswith(lead.lower())), None)
        if target:
            out[target] = ([pay.seat(lead)] + [pay.seat(p["name"], p["half"], p["temp"]) for p in people],
                           "crew schedule")
            used |= {first_name(p["name"]) for p in people} | {first_name(lead)}
            counts.pop(target, None)
        del by_group[g]
    pool = [p for ps in by_group.values() for p in ps if first_name(p["name"]) not in used]

    # Head counts: the right number of people, named from the day's list where it has them.
    for label, n in counts.items():
        take, pool = pool[:n], pool[n:]
        seats = [pay.seat(p["name"], p["half"], p["temp"]) for p in take]
        if len(seats) < n:
            seats += pay.count(n - len(seats)) if not seats else [pay.seat(None) for _ in range(n - len(seats))]
        out[label] = (seats, f"head count {n}" + (" + crew schedule" if take else ""))

    # Whoever is left on the day's list is shared by the crews still without anyone.
    open_labels = [lb for lb in groups if lb not in out]
    if open_labels and pool:
        hours = {lb: sum(j["_onsite"] for j in groups[lb]) or 1.0 for lb in open_labels}
        total = sum(hours.values())
        i = 0
        for k, lb in enumerate(open_labels):
            n = len(pool) - i if k == len(open_labels) - 1 else max(1, round(len(pool) * hours[lb] / total))
            share = pool[i:i + n]
            i += n
            if share:
                out[lb] = ([pay.seat(p["name"], p["half"], p["temp"]) for p in share], "crew schedule")

    for label, jobs in groups.items():
        if label not in out:
            seats = _estimate(pay, jobs)
            out[label] = (seats, "estimate" if seats else "unknown")
    return out


def _cost_day(seats: list[dict], paid_h: float, miles: float, card: dict) -> dict:
    rates = [None if s["rate"] is None else s["rate"] * (0.5 if s["half"] else 1) for s in seats]
    cost = ic.crew_day_cost(rates, paid_h, miles, card)
    if not seats:
        cost["missing"].append("crew")
    return cost


def season_days(clients: list[dict], season: str, history: dict, board: Optional[Board],
                card: dict, roster: list[dict], assignments: dict[str, dict]) -> dict:
    """Every install and takedown crew-day of a past season, with cost,
    revenue and net -- the same day shape as ``crew_day_profit.crew_days``
    plus ``kind``, ``times`` (how much was clocked) and ``crew_source``."""
    overhead = ic.value(card, "overhead_pct")
    target = ic.value(card, "target_profit_pct")
    factor = ic.value(card, "takedown_time_factor") or 0.6
    pay = Payroll(card, roster, assignments)
    jobs = season_jobs(clients, season, history, board)
    rosters: dict[tuple[str, str], list[dict]] = {}
    for d in history.get("days") or []:
        rosters.setdefault((d["kind"], d["date"]), []).append(d)

    days = []
    # ---- installs: one crew-day per (date, crew) ----
    by_date: dict[str, dict[str, list[dict]]] = {}
    for j in jobs:
        if not j["install_date"]:
            continue
        label, _, _ = crew_label(j["crew_lines"], None)
        label = "Dallas" if j["dallas"] else (label or "Crew ?")
        j["_onsite"] = (j["real_h"] or j["est_h"] or DEFAULT_JOB_H)
        by_date.setdefault(j["install_date"], {}).setdefault(label, []).append(j)
    for date, groups in sorted(by_date.items()):
        crews = _crews_for_date(groups, rosters.get(("install", date), []), pay)
        for label, gj in sorted(groups.items()):
            stops = [{"job": j, "start": j["real_start"], "end": j["real_end"],
                      "dur": (j["est_h"] or DEFAULT_JOB_H) * 60} for j in gj]
            days.append(_build_day("install", date, label, stops, crews.get(label, ([], "unknown")),
                                   board, card, overhead, target))

    # ---- takedowns: per date, split into crews where the order restarts ----
    td_by_date: dict[str, list[dict]] = {}
    for j in jobs:
        if j["takedown_date"]:
            td_by_date.setdefault(j["takedown_date"], []).append(j)
    for date, tj in sorted(td_by_date.items()):
        crews_td = []
        for label, seq in takedown_crews(tj):
            if label == "Dallas" and not all(j["takedown_real"] for j in seq):
                nights = dallas_nights(seq, factor)
                crews_td += [(f"Dallas night {n + 1}" if len(nights) > 1 else "Dallas", night)
                             for n, night in enumerate(nights)]
            else:
                crews_td.append((label, seq))
        roster_days = rosters.get(("takedown", date), [])
        named = {d["crew"]: d for d in roster_days if d["people"]}
        for i, (label, seq) in enumerate(crews_td):
            stops = []
            for j in seq:
                tr = j["takedown_real"]
                base_h = j["real_h"] or j["est_h"] or DEFAULT_JOB_H
                stops.append({"job": j, "start": tr["start"] if tr else None, "end": tr["end"] if tr else None,
                              "dur": base_h * factor * 60, "real": bool(tr)})
            letter = label[-1] if label.startswith("Crew ") else None
            if letter and named.get(letter):
                ppl = named[letter]["people"]
                seats, src = [pay.seat(p["name"], p["half"], p["temp"]) for p in ppl], "crew schedule"
            elif letter == "A" and len(crews_td) == 1 and named:
                ppl = [p for d in named.values() for p in d["people"]]
                seats, src = [pay.seat(p["name"], p["half"], p["temp"]) for p in ppl], "crew schedule"
            else:
                # Nobody wrote down the takedown crew: the size of the crew
                # that installed these jobs.
                n = 0
                names: list[str] = []
                for j in seq:
                    _, people, cnt = crew_label(j["crew_lines"], None)
                    people = people + list(j.get("dallas_crew") or [])
                    if len(people) > len(names):
                        names = people
                    n = max(n, cnt or 0, int(j["crew_size"] or 0))
                if len(names) >= 2:
                    seats, src = [pay.seat(x) for x in names], "install crew"
                elif n:
                    seats, src = pay.count(n), "install crew size"
                else:
                    seats = _estimate(pay, seq)
                    src = "estimate" if seats else "unknown"
            days.append(_build_day("takedown", date, label, stops, (seats, src),
                                   board, card, overhead, target))

    return _summarise(days, season, overhead, target)


def takedown_crews(jobs: list[dict]) -> list[tuple[str, list[dict]]]:
    """Split one date's takedowns into crews.

    "Take Down Order by Day" numbers each crew's stops 1, 2, 3...: the first
    job numbered 1 is crew A's first stop, the second job numbered 1 is crew
    B's, and so on, so a job's crew is its rank among the jobs sharing its
    number. Jobs with no number are grouped by the crew that installed them.
    Dallas jobs are their own crew."""
    dallas = [j for j in jobs if j["dallas"]]
    rest = [j for j in jobs if not j["dallas"]]
    ordered = sorted((j for j in rest if j["takedown_order"] is not None),
                     key=lambda j: (j["takedown_order"], crew_label(j["crew_lines"], None)[0]))
    crews: list[list[dict]] = []
    seen: dict[float, int] = {}
    for j in ordered:
        k = seen.get(j["takedown_order"], 0)
        seen[j["takedown_order"]] = k + 1
        while len(crews) <= k:
            crews.append([])
        crews[k].append(j)
    unordered: dict[str, list[dict]] = {}
    for j in rest:
        if j["takedown_order"] is None:
            unordered.setdefault(crew_label(j["crew_lines"], None)[0] or "?", []).append(j)
    crews += list(unordered.values())
    out = [(f"Crew {chr(65 + i)}", sorted(c, key=lambda j: j["takedown_order"] or 0)) for i, c in enumerate(crews)]
    if dallas:
        out.append(("Dallas", dallas))
    return out


NIGHT_MIN = 450   # a Dallas night shift (the scheduler's NIGHT)


def dallas_nights(jobs: list[dict], factor: float) -> list[list[dict]]:
    """A Dallas takedown typed as one date range ("1/2-1/3, 2026") is several
    night shifts: fill each night up to 7.5 hours of work, in order."""
    nights: list[list[dict]] = [[]]
    used = 0.0
    for j in jobs:
        mins = ((j["real_h"] or j["est_h"] or DEFAULT_JOB_H) * factor * 60)
        if nights[-1] and used + mins > NIGHT_MIN:
            nights.append([])
            used = 0.0
        nights[-1].append(j)
        used += mins
    return nights


def _build_day(kind: str, date: str, label: str, stops: list[dict], crew: tuple[list, str],
               board: Optional[Board], card: dict, overhead: Optional[float], target: Optional[float]) -> dict:
    seats, src = crew
    anchored = not label.startswith("Dallas")
    boxes = sum(s["job"]["boxes"] for s in stops if s["job"]["storing"])
    tl = _timeline(board, stops, anchored, card, boxes, kind)
    rows = [s["job"]["row"] for s in tl["order"]]
    miles = _miles(board, rows, anchored)
    paid_h = tl["paid_min"] / 60
    cost = _cost_day(seats, paid_h, miles, card)
    onsite_total = sum(s["end"] - s["start"] for s in tl["order"]) or 1.0
    out_stops = []
    for s in tl["order"]:
        j = s["job"]
        mins = s["end"] - s["start"]
        part = mins / onsite_total
        rev = j["half"]
        real = (j["real_start"] is not None) if kind == "install" else bool(s.get("real"))
        out_stops.append({
            "row": j["row"], "name": j["name"], "client_id": j["client_id"],
            "start": _r(s["start"], 0), "end": _r(s["end"], 0), "onsite_h": _r(mins / 60), "real_times": real,
            "boxes": j["boxes"], "invoice": j["invoice"], "storage": _r(j["storage"]),
            "price": rev, "revenue": _r(rev), "share": 1.0,
            "source": "invoice" if rev is not None else "unpriced", "basis": None,
            "cost": _r(cost["total"] * part), "labor_cost": _r(cost["labor"] * part),
            "other_cost": _r((cost["total"] - cost["labor"]) * part), "paid_h": _r(paid_h * part, 3),
        })
    priced = [s for s in out_stops if s["revenue"] is not None]
    revenue = sum(s["revenue"] for s in priced) if priced else None
    priced_cost = sum(s["cost"] for s in priced)
    unpriced_cost = sum(s["cost"] for s in out_stops if s["revenue"] is None)
    oh = revenue * overhead / 100 if revenue is not None and overhead is not None else None
    net = revenue - priced_cost - (oh or 0) if revenue is not None else None
    net_pct = net / revenue * 100 if net is not None and revenue else None
    for s in out_stops:
        if s["revenue"] is not None:
            s["net"] = _r(s["revenue"] - s["cost"] - s["revenue"] * (overhead or 0) / 100)
            s["net_pct"] = _r(s["net"] / s["revenue"] * 100, 1) if s["revenue"] else None
        else:
            s["net"] = s["net_pct"] = None
    clocked = sum(1 for s in out_stops if s["real_times"])
    notes = []
    if not anchored:
        notes.append("Dallas trip: the drive to Dallas and hotel nights are not in this cost")
    if len(priced) < len(out_stops):
        notes.append(f"{len(out_stops) - len(priced)} of {len(out_stops)} jobs have no 2025 invoice")
    status = "losing" if revenue == 0 and priced_cost > 0 else _status(net_pct, target)
    people = [s for s in seats]
    return {
        "id": f"{date}|{kind}|{label}", "date": date, "kind": kind, "crew": label, "night": not anchored,
        "anchored": anchored, "staffed": src in ("crew list", "crew schedule"),
        "staffed_count": sum(1 for p in people if p["name"]), "estimated_count": sum(1 for p in people if not p["name"]),
        "crew_basis": src, "crew_source": src,
        "crew_people": [{"name": p["name"], "pay_class": None, "label": p["label"], "rate": p["rate"],
                         "half": p["half"], "temp": p["temp"], "on_roster": p["on_roster"]} for p in people],
        "crew_rate": _r(sum((p["rate"] or 0) * (0.5 if p["half"] else 1) for p in people)),
        "clock_in": "8:00" if anchored else None, "clock_out_min": _r(tl["end"], 0) if anchored else None,
        "times": "real" if clocked == len(out_stops) else ("mixed" if clocked else "estimated"),
        "paid_hours": _r(paid_h), "pretrip_min": _r(tl["pretrip_min"], 0), "lunch_min": tl["lunch_min"],
        "drive_min": _r(tl["drive_min"], 0), "boxes": boxes, "miles": _r(miles, 1),
        "cost": cost, "revenue": _r(revenue), "overhead": _r(oh), "net": _r(net), "net_pct": _r(net_pct, 1),
        "priced_cost": _r(priced_cost), "unpriced_cost": _r(unpriced_cost),
        "status": status, "placeholder": bool(cost["missing"]) or overhead is None,
        "stops": out_stops, "notes": notes,
    }


def _summarise(days: list[dict], season: str, overhead, target) -> dict:
    days.sort(key=lambda d: (d["date"], d["kind"] != "install", d["crew"]))
    return {
        "season": season, "mode": "actual", "overhead_pct": overhead, "target_profit_pct": target,
        "summary": totals(days),
        "by_kind": {k: totals([d for d in days if d["kind"] == k]) for k in ("install", "takedown")},
        "days": days,
    }
