"""Net profit per install crew-day: what the day's jobs bring in against what
the day costs to run. Pure -- the install-costs API loads the board, the
client directory, the cost card and the pay assignments, then calls
``crew_days``.

For each crew-day on the board:

* **Revenue** is the install price of the day's stops (takedown is earned on
  the takedown trip, storage pays for the warehouse, which is overhead). A
  job worked over several crew-days is split across them by on-site time.
  The price comes from the client's season on the Clients tab, falling back
  to the fee the schedule was built with; a job with neither is UNPRICED.
* **Paid hours** are depot to depot, everything paid (1099, hourly): before
  the trip, the longer of the 30-minute early arrival and the warehouse
  loading (boxes x minutes a box, plus prep a job); then the drive out,
  on-site time, drives between stops, the drive back, and lunch. A night
  shift away from the branch (the Dallas week) starts at the first stop and
  has no warehouse time.
* **Crew** is who is staffed on the day, each at their own pay. Until the
  day is fully staffed, the rest of the crew is estimated from last year's
  real crew on those jobs (the largest 2025 crew among the day's stops: one
  Lead, the rest General Installers), falling back to the stops' role needs
  for jobs with no 2025 crew on record. Estimated seats are paid at the
  class rate and marked as estimates.
* **Day cost** is ``install_costs.crew_day_cost``: pay, van, trailer, gas
  from route miles (straight-line x the scheduler's road factor), wear,
  ancillary, tolls, parking.
* **Net** = revenue - day cost - overhead (the card's overhead % of the
  revenue). Net % = net / revenue.

The day cost is shared out to its stops by on-site time so a day with an
unpriced stop still gives an honest net % for the stops that are priced; the
cost of the unpriced ones is reported, not hidden.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Optional

from app.libs import install_costs as ic
from app.libs.install_calendar import ROAD_FUDGE, day_timeline
from app.libs.schedule_board import Board

ARRIVE_MIN = 30  # crew arrives 8:00 for the 8:30 roll-out (the tool's ARRIVE/DEPART)

#: role_need key -> pay class slug, for a day nobody is staffed on yet. The
#: scheduler counts specialty as Lead Assist coverage; pay follows that.
ROLE_CLASS = (("leads", "lead"), ("specialty", "lead_assist"), ("designer", "designer"), ("general", "general"))


def norm_name(s: Any) -> str:
    """The schedule tool's normName(): how a schedule row finds its client."""
    out = str(s or "").strip().lower().replace(",", "").replace(".", "")
    return " ".join(out.split())


def _num(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        n = float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def price_index(clients: Iterable[dict], season: str) -> dict[str, dict]:
    """normalised name -> that client's ``season`` prices, indexed by every
    spelling the app knows (name, sheet name, former names), first wins --
    the same lookup the schedule's billing export uses."""
    idx: dict[str, dict] = {}
    for c in clients:
        season_row = next((a for a in c.get("activity") or []
                           if a.get("kind") == "christmas_install" and str(a.get("season")) == str(season)), None)
        d = (season_row or {}).get("detail") or {}
        entry = {
            "client_id": c.get("id"), "name": c.get("name"), "has_season": season_row is not None,
            "install": _num(d.get("install_fee")), "takedown": _num(d.get("takedown_fee")),
            "storage": _num(d.get("storage_fee")), "total": _num(d.get("total")),
            "basis": d.get("price_basis") or ((season_row or {}).get("pricing") or {}).get("basis"),
            "not_installing": bool(d.get("not_installing")),
        }
        for n in [c.get("name"), c.get("sheet_name"), *(c.get("former_names") or [])]:
            k = norm_name(n)
            if k and k not in idx:
                idx[k] = entry
    return idx


def install_price(sched_client: dict, entry: Optional[dict]) -> tuple[Optional[float], str, Optional[str]]:
    """``(install price, source, basis)`` for one schedule row. Source is
    ``clients`` (the Clients tab season), ``schedule`` (the fee the board was
    built with), ``no_charge`` or ``unpriced``."""
    basis = (entry or {}).get("basis") or sched_client.get("basis")
    if entry and entry.get("install") is not None:
        return entry["install"], "clients", basis
    fee = _num(sched_client.get("installFee"))
    if fee is not None:
        return fee, "schedule", basis
    if sched_client.get("noCharge"):
        return 0.0, "no_charge", basis
    return None, "unpriced", basis


def _haversine_mi(a: tuple, b: tuple) -> float:
    r, rad = 3958.8, math.radians
    dlat, dlon = rad(b[0] - a[0]), rad(b[1] - a[1])
    s = math.sin(dlat / 2) ** 2 + math.cos(rad(a[0])) * math.cos(rad(b[0])) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(s))


def _pt(c: dict) -> Optional[tuple]:
    lat, lon = _num(c.get("lat")), _num(c.get("lon"))
    return (lat, lon) if lat is not None and lon is not None else None


def route_miles(board: Board, rows: list[int], anchored: bool) -> float:
    """Road miles for the day: straight line between consecutive points times
    the scheduler's road factor. Depot legs only when the day starts and ends
    at the branch."""
    pts = [_pt(board.clients.get(r) or {}) for r in rows]
    if anchored:
        pts = [_pt(board.depot)] + pts + [_pt(board.depot)]
    pts = [p for p in pts if p]
    return sum(_haversine_mi(a, b) for a, b in zip(pts, pts[1:])) * ROAD_FUDGE


def role_need_crew(board: Board, rows: list[int]) -> list[str]:
    """Pay-class slugs from the stops' role needs: the crew of the single
    stop that needs the most people. That whole crew rides out together and
    works every stop on the day, so the biggest job sets the crew size (taking
    the most of each role across different stops would invent a crew bigger
    than any one job needs). Empty when no stop says."""
    best: list[str] = []
    for r in rows:
        rn = (board.clients.get(r) or {}).get("roleNeed") or {}
        seats = [slug for k, slug in ROLE_CLASS for _ in range(int(_num(rn.get(k)) or 0))]
        if len(seats) > len(best):
            best = seats
    return best


def estimated_crew(board: Board, rows: list[int]) -> tuple[list[str], Optional[str]]:
    """``(pay-class slugs, basis)`` for the seats nobody is staffed in yet.

    Rule (user, 2026-09-29): size the crew by last year's real crew on those
    jobs -- the largest 2025 crew among the day's stops -- as one Lead and
    the rest General Installers. The stops' role needs run far larger than
    the crews actually sent (a 14-person need on a job done by 6), so they
    are only the fallback for a day none of whose jobs has a 2025 crew size.
    Basis is ``2025 crew`` | ``role needs`` | None (nothing to go on)."""
    sizes = [int(n) for n in (_num((board.clients.get(r) or {}).get("size25")) for r in rows) if n and n > 0]
    if sizes:
        size = max(sizes)
        return ["lead"] + ["general"] * (size - 1), "2025 crew"
    needed = role_need_crew(board, rows)
    return (needed, "role needs") if needed else ([], None)


def _status(net_pct: Optional[float], target: Optional[float]) -> str:
    if net_pct is None:
        return "unpriced"
    if net_pct < 0:
        return "losing"
    if target is not None and net_pct < target:
        return "tight"
    return "healthy"


def _r(x: Optional[float], n: int = 2) -> Optional[float]:
    return None if x is None else round(x + 0.0, n)


def crew_days(board: Board, prices: dict[str, dict], card: dict, assignments: dict[str, dict]) -> dict:
    """Every crew-day on the board with its cost, revenue and net, plus the
    season totals. See the module docstring for the arithmetic."""
    overhead = ic.value(card, "overhead_pct")
    target = ic.value(card, "target_profit_pct")
    load_min = ic.value(card, "load_min_per_box") or 0
    prep_min = ic.value(card, "prep_min_per_job") or 0
    classes = {c["slug"]: c for c in card["classes"]}
    lunch_default = _num(board.const.get("LUNCH")) or 0

    # Pass 1: every day's timeline, and each job's on-site minutes across all
    # of its days (a job split over days shares its price by time).
    lines = {}
    onsite_total: dict[int, float] = {}
    for d in board.days.values():
        if not d["stops"]:
            continue
        tl = day_timeline(board, d)
        lines[d["id"]] = tl
        for s in tl["stops"]:
            onsite_total[s["row"]] = onsite_total.get(s["row"], 0.0) + max(0.0, s["end"] - s["start"])

    out_days = []
    for d in sorted(board.days.values(), key=lambda x: (x["date"], x["crew"], x["id"])):
        tl = lines.get(d["id"])
        if not tl or not tl["stops"]:
            continue
        meta = board.day_meta.get(d["id"]) or {}
        anchored = tl["anchored"]
        night = board.const.get("NIGHT") is not None and meta.get("win") == board.const.get("NIGHT")
        rows = [s["row"] for s in tl["stops"]]
        notes: list[str] = []

        # ---- crew ----
        # Staffed people at their own pay; anyone the role needs call for
        # beyond them is filled in as an estimate at the class rate, so a day
        # with only its lead assigned so far is not costed as a crew of one.
        staffed_ids = board.staffing.get(d["id"]) or []
        crew: list[dict] = []
        needed, crew_basis = estimated_crew(board, rows)
        for pid in staffed_ids:
            p = board.person(pid) or {"id": pid, "name": pid, "title": "General Installer"}
            pr = ic.person_rate(p, assignments.get(pid), card)
            crew.append({"name": p["name"], "pay_class": pr["pay_class"], "label": pr["label"], "rate": pr["rate"]})
            # This person covers one needed seat: their own class if the
            # stops call for one, otherwise a general installer's.
            for slug in (pr["pay_class"], "general", *needed):
                if slug in needed:
                    needed.remove(slug)
                    break
        for slug in needed:
            cls = classes.get(slug)
            crew.append({"name": None, "pay_class": slug, "label": cls["label"] if cls else slug,
                         "rate": cls["rate"] if cls else None})
        estimated = sum(1 for c in crew if c["name"] is None)
        if not crew:
            notes.append("No crew staffed and no role needs on these stops")

        # ---- paid time ----
        first, last = tl["stops"][0], tl["stops"][-1]
        begin = tl["start"] if anchored else first["start"]
        span = (last["end"] + (tl["back"] or 0)) - begin
        boxes = sum(int(_num((board.clients.get(r) or {}).get("boxes")) or 0) for r in rows)
        warehouse = boxes * load_min + len(rows) * prep_min
        pretrip = max(ARRIVE_MIN, warehouse) if anchored else 0.0
        lunch = _num(meta.get("lunchMin"))
        lunch = lunch_default if lunch is None else lunch
        paid_min = pretrip + span + lunch
        if not anchored:
            notes.append("Away from the branch: no warehouse time or drive to the first stop")

        miles = route_miles(board, rows, anchored)
        cost = ic.crew_day_cost([c["rate"] for c in crew], paid_min / 60, miles, card)
        if not crew:
            cost["missing"].append("crew")

        # ---- stops: revenue and a share of the day's cost ----
        onsite_day = sum(max(0.0, s["end"] - s["start"]) for s in tl["stops"]) or 1.0
        stops = []
        for s in tl["stops"]:
            c = board.clients.get(s["row"]) or {}
            entry = prices.get(norm_name(c.get("name")))
            price, source, basis = install_price(c, entry)
            mins = max(0.0, s["end"] - s["start"])
            share = mins / (onsite_total.get(s["row"]) or mins or 1.0)
            revenue = None if price is None else price * share
            part = mins / onsite_day
            stop_cost = cost["total"] * part
            stops.append({
                "row": s["row"], "name": (entry or {}).get("name") or c.get("name"),
                "client_id": (entry or {}).get("client_id"),
                "onsite_h": _r(mins / 60), "share": _r(share, 3), "boxes": int(_num(c.get("boxes")) or 0),
                "price": price, "revenue": _r(revenue), "source": source, "basis": basis,
                "cost": _r(stop_cost),
                # This stop's slice of the day, for job budgets: paid crew
                # hours (depot to depot, by on-site share), and its cost split
                # into crew pay and everything else (vehicles, gas, extras).
                "paid_h": _r(paid_min / 60 * part, 3),
                "labor_cost": _r(cost["labor"] * part),
                "other_cost": _r((cost["total"] - cost["labor"]) * part),
            })

        priced = [s for s in stops if s["revenue"] is not None]
        revenue = sum(s["revenue"] for s in priced) if priced else None
        priced_cost = sum(s["cost"] for s in priced)
        unpriced_cost = sum(s["cost"] for s in stops if s["revenue"] is None)
        oh = revenue * overhead / 100 if revenue is not None and overhead is not None else None
        net = revenue - priced_cost - (oh or 0) if revenue is not None else None
        net_pct = net / revenue * 100 if net is not None and revenue else None
        # Priced at $0 (no charge, donation): all cost, no percentage to show.
        status = "losing" if revenue == 0 and priced_cost > 0 else _status(net_pct, target)
        for s in stops:
            if s["revenue"] is not None:
                s_oh = s["revenue"] * (overhead or 0) / 100
                s["net"] = _r(s["revenue"] - s["cost"] - s_oh)
                s["net_pct"] = _r((s["net"] / s["revenue"] * 100) if s["revenue"] else None, 1)
            else:
                s["net"] = s["net_pct"] = None
        if len(priced) < len(stops):
            notes.append(f"{len(stops) - len(priced)} of {len(stops)} stops have no price yet")
        placeholder = bool(cost["missing"]) or overhead is None

        out_days.append({
            "id": d["id"], "date": d["date"], "crew": board.crew_label(d), "night": night, "anchored": anchored,
            "staffed": bool(staffed_ids), "staffed_count": len(staffed_ids), "estimated_count": estimated,
            "crew_basis": crew_basis if estimated else None,
            "crew_people": crew,
            "paid_hours": _r(paid_min / 60),
            "crew_rate": _r(sum(c["rate"] or 0 for c in crew)), "pretrip_min": _r(pretrip, 0), "lunch_min": _r(lunch, 0),
            "boxes": boxes, "miles": _r(miles, 1),
            "cost": cost, "revenue": _r(revenue), "overhead": _r(oh),
            "net": _r(net), "net_pct": _r(net_pct, 1),
            "priced_cost": _r(priced_cost), "unpriced_cost": _r(unpriced_cost),
            "status": status, "placeholder": placeholder,
            "stops": stops, "notes": notes,
        })

    rev = sum(d["revenue"] or 0 for d in out_days)
    cost_priced = sum(d["priced_cost"] or 0 for d in out_days)
    oh_total = sum(d["overhead"] or 0 for d in out_days)
    net_total = rev - cost_priced - oh_total
    counts: dict[str, int] = {}
    for d in out_days:
        counts[d["status"]] = counts.get(d["status"], 0) + 1
    return {
        "season": board.season,
        "overhead_pct": overhead, "target_profit_pct": target,
        "summary": {
            "days": len(out_days), "staffed_days": sum(1 for d in out_days if d["staffed"]),
            "revenue": _r(rev), "cost": _r(sum(d["cost"]["total"] for d in out_days)),
            "priced_cost": _r(cost_priced), "unpriced_cost": _r(sum(d["unpriced_cost"] or 0 for d in out_days)),
            "overhead": _r(oh_total), "net": _r(net_total),
            "net_pct": _r(net_total / rev * 100, 1) if rev else None,
            "counts": counts,
            "missing": sorted({m for d in out_days for m in d["cost"]["missing"]}),
        },
        "days": out_days,
    }


# ---------------------------------------------------------------------------
# The install & takedown view: every install crew-day plus its takedown.

def totals(days: list[dict]) -> dict:
    """Season totals over any set of crew-days (install, takedown or both)."""
    rev = sum(d["revenue"] or 0 for d in days)
    cost_all = sum(d["cost"]["total"] for d in days)
    priced = sum(d["priced_cost"] or 0 for d in days)
    oh = sum(d["overhead"] or 0 for d in days)
    counts: dict[str, int] = {}
    for d in days:
        counts[d["status"]] = counts.get(d["status"], 0) + 1
    net = rev - priced - oh
    return {
        "days": len(days), "staffed_days": sum(1 for d in days if d["staffed"]),
        "revenue": _r(rev), "cost": _r(cost_all), "priced_cost": _r(priced),
        "unpriced_cost": _r(cost_all - priced), "labor": _r(sum(d["cost"]["labor"] for d in days)),
        "person_hours": _r(sum(d["paid_hours"] * len(d["crew_people"]) for d in days), 1),
        "overhead": _r(oh), "net": _r(net), "net_pct": _r(net / rev * 100, 1) if rev else None,
        "counts": counts, "missing": sorted({m for d in days for m in d["cost"]["missing"]}),
    }


def takedown_price(sched_client: dict, entry: Optional[dict]) -> tuple[Optional[float], str]:
    """``(takedown price, source)``, like ``install_price``."""
    if entry and entry.get("takedown") is not None:
        return entry["takedown"], "clients"
    fee = _num(sched_client.get("takedownFee"))
    if fee is not None:
        return fee, "schedule"
    if sched_client.get("noCharge"):
        return 0.0, "no_charge"
    return None, "unpriced"


def _takedown_of(day: dict, board: Board, prices: dict[str, dict], card: dict,
                 overhead: Optional[float], target: Optional[float], factor: float) -> dict:
    """The takedown trip for one planned install crew-day: the same crew and
    route in January, on-site time x the takedown factor, everything else
    (warehouse time, drives, lunch) as on the install day; earning the
    takedown price."""
    onsite_h = sum(s["onsite_h"] for s in day["stops"])
    paid_h = max(0.0, day["paid_hours"] - onsite_h) + onsite_h * factor
    cost = ic.crew_day_cost([c["rate"] for c in day["crew_people"]], paid_h, day["miles"], card)
    if not day["crew_people"]:
        cost["missing"].append("crew")
    stops = []
    for s in day["stops"]:
        c = board.clients.get(s["row"]) or {}
        price, source = takedown_price(c, prices.get(norm_name(c.get("name"))))
        part = s["onsite_h"] / onsite_h if onsite_h else 1 / max(1, len(day["stops"]))
        revenue = None if price is None else price * s["share"]
        stop_cost = cost["total"] * part
        stops.append({**s, "onsite_h": _r(s["onsite_h"] * factor), "price": price, "revenue": _r(revenue),
                      "source": source, "cost": _r(stop_cost), "paid_h": _r(paid_h * part, 3),
                      "labor_cost": _r(cost["labor"] * part), "other_cost": _r((cost["total"] - cost["labor"]) * part)})
    priced = [s for s in stops if s["revenue"] is not None]
    revenue = sum(s["revenue"] for s in priced) if priced else None
    priced_cost = sum(s["cost"] for s in priced)
    oh = revenue * overhead / 100 if revenue is not None and overhead is not None else None
    net = revenue - priced_cost - (oh or 0) if revenue is not None else None
    net_pct = net / revenue * 100 if net is not None and revenue else None
    for s in stops:
        if s["revenue"] is not None:
            s["net"] = _r(s["revenue"] - s["cost"] - s["revenue"] * (overhead or 0) / 100)
            s["net_pct"] = _r(s["net"] / s["revenue"] * 100, 1) if s["revenue"] else None
        else:
            s["net"] = s["net_pct"] = None
    return {
        **day, "id": day["id"] + "|takedown", "kind": "takedown", "takedown_of": day["date"],
        "paid_hours": _r(paid_h), "cost": cost, "revenue": _r(revenue), "overhead": _r(oh),
        "net": _r(net), "net_pct": _r(net_pct, 1), "priced_cost": _r(priced_cost),
        "unpriced_cost": _r(sum(s["cost"] for s in stops if s["revenue"] is None)),
        "status": "losing" if revenue == 0 and priced_cost > 0 else _status(net_pct, target),
        "times": "estimated", "stops": stops,
        "notes": [f"Takedown estimate: the {day['date']} install crew and route, {factor:g} x the on-site time; "
                  "not on the calendar yet"] + [n for n in day["notes"] if "stops have no price" not in n],
    }


def plan_days(board: Board, prices: dict[str, dict], card: dict, assignments: dict[str, dict]) -> dict:
    """The season being planned, install AND takedown: every crew-day from
    ``crew_days`` plus the takedown trip each one implies."""
    out = crew_days(board, prices, card, assignments)
    factor = ic.value(card, "takedown_time_factor") or 0.6
    installs = [{**d, "kind": "install", "times": "planned"} for d in out["days"]]
    takedowns = [_takedown_of(d, board, prices, card, out["overhead_pct"], out["target_profit_pct"], factor)
                 for d in installs]
    days = installs + takedowns
    return {
        **out, "mode": "plan", "takedown_time_factor": factor,
        "summary": totals(days),
        "by_kind": {"install": totals(installs), "takedown": totals(takedowns)},
        "days": days,
    }
