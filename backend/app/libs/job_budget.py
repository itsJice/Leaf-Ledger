"""Job budgets: what each install JOB can afford to spend, in crew-hours.

Pure, no database -- the job-budgets API loads the board, the client
directory, the cost card and the pay assignments, runs
``crew_day_profit.crew_days`` and hands its output here.

A job is one schedule row. It can be worked over several crew-days (or by
two crews), so every stop on every crew-day is grouped by its row.

Rules (owner, 2026-09-29):

* **Price** is the job's whole season price: the Clients tab season total
  (or the sum of its install, takedown and storage fees when there is no
  total), falling back to the fees the schedule was built with. A no-charge
  job is priced at $0; a job with none of these is UNPRICED.
* **Install** cost is the sum of the job's slices of its crew-days: the
  crew's paid hours (depot to depot, shared out by on-site time), crew pay,
  and everything else the day costs (van, trailer, gas, extras).
* **Takedown** is not scheduled yet, so it is estimated from the install:
  the takedown PRICE always equals the install price, but its TIME is the
  install time x the card's ``takedown_time_factor`` (0.6 by default). Same
  crew, same trip shape, so its vans, gas and extras are taken as the
  install trip's.
* **Net** = price - install - takedown - overhead (the card's overhead % of
  the price). Status is the crew-day page's: on target, under target,
  losing money, no price.
* **Hour budget** is the headline: how many crew-hours (hours the whole crew
  is on the clock, install + takedown, drives included) the job can take
  before it drops below the target profit, and before it loses money:

      budget_target_h    = (price x (1 - overhead - target) - vehicles) / crew rate
      budget_breakeven_h = (price x (1 - overhead) - vehicles) / crew rate

  where crew rate is the sum of the crew's hourly pay and vehicles is the
  install + takedown non-pay cost. Planned hours are the install paid hours
  plus the takedown estimate.
* **Materials** are not tracked per job yet: reported as None, never guessed.
"""
from __future__ import annotations

from typing import Optional

from app.libs import install_costs as ic
from app.libs.crew_day_profit import _num, _status, norm_name
from app.libs.schedule_board import Board


def _r(x: Optional[float], n: int = 2) -> Optional[float]:
    return None if x is None else round(x + 0.0, n)


def job_price(sched_client: dict, entry: Optional[dict]) -> dict:
    """The job's season price and its parts.

    ``{total, install, takedown, storage, price_source, basis}``; source is
    ``clients`` | ``schedule`` | ``no_charge`` | ``unpriced``."""
    basis = (entry or {}).get("basis") or sched_client.get("basis")
    if entry and any(entry.get(k) is not None for k in ("total", "install", "takedown", "storage")):
        parts = {k: entry.get(k) for k in ("install", "takedown", "storage")}
        total = entry.get("total")
        if total is None:
            total = sum(v for v in parts.values() if v is not None)
        return {"total": total, **parts, "price_source": "clients", "basis": basis}
    parts = {
        "install": _num(sched_client.get("installFee")),
        "takedown": _num(sched_client.get("takedownFee")),
        "storage": _num(sched_client.get("storageFee")),
    }
    if any(v is not None for v in parts.values()):
        total = sum(v for v in parts.values() if v is not None)
        return {"total": total, **parts, "price_source": "schedule", "basis": basis}
    if sched_client.get("noCharge"):
        return {"total": 0.0, "install": 0.0, "takedown": 0.0, "storage": 0.0,
                "price_source": "no_charge", "basis": basis}
    return {"total": None, "install": None, "takedown": None, "storage": None,
            "price_source": "unpriced", "basis": basis}


def _crew_basis(day: dict) -> str:
    if not day.get("estimated_count"):
        return "staffed" if day.get("staffed_count") else "none"
    return day.get("crew_basis") or "none"


def last_year_index(clients, season: str) -> dict[str, dict]:
    """normalised name -> the previous season's real numbers from the
    Clients tab (``real_hours``, ``crew_size``, ``takedown_real_hours``),
    indexed by every spelling like ``price_index``. The published schedule
    only carries the crew size, so the hours come from here."""
    prev = str(int(season) - 1)
    idx: dict[str, dict] = {}
    for c in clients:
        row = next((a for a in c.get("activity") or []
                    if a.get("kind") == "christmas_install" and str(a.get("season")) == prev), None)
        d = (row or {}).get("detail") or {}
        entry = {"hours": _num(d.get("real_hours")), "crew_size": _num(d.get("crew_size")),
                 "takedown_hours": _num(d.get("takedown_real_hours"))}
        if not any(v is not None for v in entry.values()):
            continue
        for n in [c.get("name"), c.get("sheet_name"), *(c.get("former_names") or [])]:
            k = norm_name(n)
            if k and k not in idx:
                idx[k] = entry
    return idx


def job_budgets(crew_days_out: dict, prices: dict[str, dict], board: Board, card: dict,
                last_year: Optional[dict[str, dict]] = None) -> dict:
    """Every job on the board with its price, install and takedown cost, net,
    and hour budget, worst net % first. See the module docstring."""
    overhead = crew_days_out.get("overhead_pct")
    if overhead is None:
        overhead = ic.value(card, "overhead_pct")
    target = crew_days_out.get("target_profit_pct")
    if target is None:
        target = ic.value(card, "target_profit_pct")
    factor = ic.value(card, "takedown_time_factor")
    factor = 0.6 if factor is None else factor

    # Group every stop by its schedule row, in day order.
    groups: dict[int, dict] = {}
    for d in crew_days_out.get("days") or []:
        for s in d.get("stops") or []:
            g = groups.setdefault(s["row"], {"stops": [], "days": []})
            g["stops"].append(s)
            g["days"].append(d)

    jobs = []
    for row, g in groups.items():
        c = board.clients.get(row) or {}
        entry = prices.get(norm_name(c.get("name")))
        first = g["stops"][0]
        price = job_price(c, entry)
        total = price["total"]

        onsite_h = sum(s.get("onsite_h") or 0 for s in g["stops"])
        paid_h = sum(s.get("paid_h") or 0 for s in g["stops"])
        labor = sum(s.get("labor_cost") or 0 for s in g["stops"])
        other = sum(s.get("other_cost") or 0 for s in g["stops"])

        # Crew rate: each day's whole-crew hourly pay, weighted by the hours
        # the job takes of that day.
        weighted = sum((d.get("crew_rate") or 0) * (s.get("paid_h") or 0) for s, d in zip(g["stops"], g["days"]))
        crew_rate = weighted / paid_h if paid_h else None
        if not crew_rate:
            rates = [d.get("crew_rate") for d in g["days"] if d.get("crew_rate")]
            crew_rate = max(rates) if rates else None
        biggest = max(g["days"], key=lambda d: len(d.get("crew_people") or []))
        crew_size = len(biggest.get("crew_people") or [])

        # One entry per crew-day (a job visited twice on one day is one day).
        seen, days = set(), []
        for d in g["days"]:
            if d["id"] not in seen:
                seen.add(d["id"])
                days.append({"id": d["id"], "date": d["date"], "crew": d["crew"]})
        missing = sorted({m for d in g["days"] for m in (d.get("cost") or {}).get("missing") or []})

        td_paid = paid_h * factor
        td_labor = labor * factor
        td_other = other
        job_cost = labor + other + td_labor + td_other
        oh = total * overhead / 100 if total is not None and overhead is not None else None
        net = total - job_cost - (oh or 0) if total is not None else None
        net_pct = net / total * 100 if net is not None and total else None
        status = "losing" if total == 0 and job_cost > 0 else _status(net_pct, target)

        vehicle = other + td_other
        planned = paid_h + td_paid
        b_target = b_even = over = None
        if total is not None and crew_rate:
            if overhead is not None:
                b_even = (total * (1 - overhead / 100) - vehicle) / crew_rate
                if target is not None:
                    b_target = (total * (1 - overhead / 100 - target / 100) - vehicle) / crew_rate
                    over = planned - b_target

        ly = (last_year or {}).get(norm_name(c.get("name"))) or {}
        real25 = _num(c.get("real25")) or ly.get("hours")
        size25 = _num(c.get("size25")) or ly.get("crew_size")
        vs = None
        if real25 and onsite_h:
            vs = {"plan_onsite_h": _r(onsite_h), "real25_h": _r(real25),
                  "diff_h": _r(onsite_h - real25), "ratio": _r(onsite_h / real25, 3)}

        jobs.append({
            "row": row,
            "name": (entry or {}).get("name") or first.get("name") or c.get("name"),
            "client_id": (entry or {}).get("client_id") or first.get("client_id"),
            "days": days,
            "price": {**price, **{k: _r(price[k]) for k in ("total", "install", "takedown", "storage")}},
            "install": {
                "onsite_h": _r(onsite_h), "paid_h": _r(paid_h), "labor_cost": _r(labor),
                "other_cost": _r(other), "cost": _r(labor + other),
                "crew_rate": _r(crew_rate), "crew_size": crew_size, "crew_basis": _crew_basis(biggest),
            },
            "takedown": {
                "factor": factor, "paid_h": _r(td_paid), "labor_cost": _r(td_labor),
                "other_cost": _r(td_other), "cost": _r(td_labor + td_other),
            },
            "materials": None,
            "job_cost": _r(job_cost), "overhead": _r(oh), "net": _r(net), "net_pct": _r(net_pct, 1),
            "status": status,
            "budget": {
                "vehicle": _r(vehicle), "crew_rate": _r(crew_rate),
                "budget_target_h": _r(b_target, 1), "budget_breakeven_h": _r(b_even, 1),
                "planned_h": _r(planned, 1), "over_target_h": _r(over, 1),
            },
            "last_year": {"hours": real25, "crew_size": int(size25) if size25 else None,
                          "takedown_hours": ly.get("takedown_hours")},
            "last_year_vs_plan": vs,
            "missing": missing,
            "placeholder": bool(missing) or overhead is None,
        })

    # Worst net % first; $0-priced losers ahead of the rest; unpriced last.
    def key(j: dict) -> tuple:
        if j["status"] == "unpriced":
            return (2, 0.0, j["name"] or "")
        if j["net_pct"] is None:
            return (0, float("-inf"), j["name"] or "")
        return (1, j["net_pct"], j["name"] or "")
    jobs.sort(key=key)

    priced = [j for j in jobs if j["price"]["total"] is not None]
    revenue = sum(j["price"]["total"] for j in priced)
    cost = sum(j["job_cost"] for j in priced)
    oh_total = sum(j["overhead"] or 0 for j in priced)
    net_total = revenue - cost - oh_total
    counts: dict[str, int] = {}
    for j in jobs:
        counts[j["status"]] = counts.get(j["status"], 0) + 1
    over_jobs = [j for j in jobs if (j["budget"]["over_target_h"] or 0) > 0]
    return {
        "season": crew_days_out.get("season") or board.season,
        "overhead_pct": overhead, "target_profit_pct": target, "takedown_time_factor": factor,
        "summary": {
            "jobs": len(jobs), "priced_jobs": len(priced),
            "revenue": _r(revenue), "cost": _r(cost), "overhead": _r(oh_total), "net": _r(net_total),
            "net_pct": _r(net_total / revenue * 100, 1) if revenue else None,
            "unpriced_cost": _r(sum(j["job_cost"] for j in jobs if j["price"]["total"] is None)),
            "planned_h": _r(sum(j["budget"]["planned_h"] or 0 for j in jobs), 1),
            "counts": counts,
            "over_budget": len(over_jobs),
            "over_budget_h": _r(sum(j["budget"]["over_target_h"] for j in over_jobs), 1),
        },
        "jobs": jobs,
    }

