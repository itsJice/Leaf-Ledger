"""Quote calculator: what one Christmas job costs us, and what it should sell
for at each profit level. Pure -- the install-quote API loads the cost card
(``app.libs.install_costs``) and calls ``quote``.

A job is two trips, install and takedown (takedown can be left out). Each
trip is costed like a slice of a crew-day:

* **Paid hours** are depot to depot (1099, hourly, everything paid): before
  the trip, the longer of the 30-minute early arrival and the warehouse
  loading (boxes x minutes a box + prep a job) when the job is stored with
  us, else just the 30 minutes; then the drive out and back and the on-site
  time. Crew pay = the crew's combined hourly rate x paid hours.
* **The crew-day's van, trailer and extras** (van, trailer, rental
  insurance per vehicle, ancillary, tolls, parking) are charged per day, so
  a trip carries a share of them: paid hours / 10, at most one whole day.
* **Gas and wear** are per van on the round trip.

Takedown TIME is install on-site time x the card's takedown factor unless
given; the takedown PRICE is always the install price, so the ``price``
passed in is the job's whole price for the work quoted.

Profit levels: at profit ``p`` the job may cost ``price x (1 - overhead - p)``
and needs a price of ``job_cost / (1 - overhead - p)`` (None when overhead
plus profit reach 100%).
"""
from __future__ import annotations

from typing import Any, Optional

from app.libs import install_costs as ic

#: Profit levels the calculator always shows, in percent.
LEVELS = (0, 10, 15, 20, 25, 30, 35, 40, 50)

ARRIVE_MIN = 30       # the crew's early arrival before roll-out (crew_day_profit.ARRIVE_MIN)
DAY_HOURS = 10.0      # a full crew-day, for sharing the daily van/trailer/extras
LUNCH_MIN = 40        # the crew's paid lunch on a full day (the scheduler's LUNCH)
AVG_MPH = 27.0        # the scheduler's average speed, for miles from drive time
DEFAULT_DRIVE_MIN = 30.0


def _f(v: Any, default: Optional[float] = None) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _r(x: Optional[float], n: int = 2) -> Optional[float]:
    return None if x is None else round(x + 0.0, n)


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def crew_rate(card: dict, crew: dict) -> tuple[float, int, list[str], list[dict]]:
    """``(combined hourly rate, people, missing, seats)`` for ``{slug: count}``.
    A class the card does not have, or one with no rate, is named in
    ``missing`` and left out of the rate."""
    classes = {c["slug"]: c for c in card["classes"]}
    rate, people, missing, seats = 0.0, 0, [], []
    for slug, n in (crew or {}).items():
        count = int(_f(n, 0) or 0)
        if count <= 0:
            continue
        people += count
        cls = classes.get(slug)
        r = cls["rate"] if cls else None
        if r is None:
            missing.append(ic.PAY_PREFIX + slug)
        else:
            rate += count * r
        seats.append({"slug": slug, "label": cls["label"] if cls else slug, "count": count, "rate": r})
    return rate, people, missing, seats


def _trip(name: str, card: dict, rate: float, onsite_h: float, drive_min: float, miles: float,
          boxes: float, stored: bool, missing: list[str], lunch_min: float = LUNCH_MIN) -> dict:
    load_min = ic.value(card, "load_min_per_box") or 0
    prep_min = ic.value(card, "prep_min_per_job") or 0
    pretrip = max(ARRIVE_MIN, boxes * load_min + prep_min) if stored else ARRIVE_MIN
    work_h = (pretrip + 2 * drive_min + onsite_h * 60) / 60
    share = min(1.0, work_h / DAY_HOURS)
    # Lunch is paid, like on the crew-day page; a job that is part of a day
    # carries the same share of the lunch as of the van and trailer.
    paid_h = work_h + lunch_min / 60 * share

    def daily(key: str, count_key: Optional[str] = None) -> float:
        v = ic.value(card, key)
        if v is None:
            if key not in missing:
                missing.append(key)
            return 0.0
        n = ic.value(card, count_key) if count_key else 1
        return v * (n or 0)

    vans = ic.value(card, "vans_per_crew") or 0
    trailers = ic.value(card, "trailers_per_crew") or 0
    van = daily("van_day", "vans_per_crew") * share
    trailer = daily("trailer_day", "trailers_per_crew") * share
    insurance = (ic.value(card, "rental_insurance_day") or 0) * (vans + trailers) * share
    ancillary = (ic.value(card, "ancillary_day") or 0) * share
    tolls = (ic.value(card, "tolls_day") or 0) * share
    parking = (ic.value(card, "parking_day") or 0) * share

    gpm = ic.derived(card)["gas_per_mile"]
    if gpm is None and "gas" not in missing:
        missing.append("gas")
    round_trip = 2 * miles
    gas = round_trip * vans * (gpm or 0)
    wear = round_trip * vans * (ic.value(card, "wear_per_mile") or 0)

    crew_pay = rate * paid_h
    day_share_cost = van + trailer + insurance + ancillary + tolls + parking
    other = day_share_cost + gas + wear
    return {
        "trip": name, "onsite_h": _r(onsite_h), "pretrip_min": _r(pretrip, 1),
        "drive_min_each_way": _r(drive_min, 1), "miles_round_trip": _r(round_trip, 1),
        "paid_h": _r(paid_h, 3), "day_share": _r(share, 4),
        "crew_pay": _r(crew_pay), "van": _r(van), "trailer": _r(trailer), "insurance": _r(insurance),
        "ancillary": _r(ancillary), "tolls": _r(tolls), "parking": _r(parking),
        "day_share_cost": _r(day_share_cost), "gas": _r(gas), "wear": _r(wear),
        "other": _r(other), "total": _r(crew_pay + other),
        # unrounded, for the totals
        "_paid_h": paid_h, "_crew_pay": crew_pay, "_other": other,
    }


def quote(card: dict, inputs: dict) -> dict:
    """Cost one job from ``inputs`` (see the module docstring and the API's
    ``QuoteIn``) against the resolved cost ``card``. Every figure built on a
    missing card value is a placeholder, and the value is named in
    ``missing``."""
    rate, people, missing, seats = crew_rate(card, inputs.get("crew") or {})

    factor = ic.value(card, "takedown_time_factor")
    factor = 0.6 if factor is None else factor
    install_h = max(0.0, _f(inputs.get("install_onsite_h"), 0.0) or 0.0)
    takedown_h = _f(inputs.get("takedown_onsite_h"))
    takedown_auto = takedown_h is None
    if takedown_h is None:
        takedown_h = install_h * factor
    include_takedown = inputs.get("include_takedown", True) is not False
    drive = _f(inputs.get("drive_min_each_way"))
    drive = DEFAULT_DRIVE_MIN if drive is None else max(0.0, drive)
    miles = _f(inputs.get("miles_each_way"))
    miles_auto = miles is None
    if miles is None:
        miles = drive / 60 * AVG_MPH
    boxes = max(0.0, _f(inputs.get("boxes"), 0.0) or 0.0)
    stored = inputs.get("stored_with_us", True) is not False
    designer_h = max(0.0, _f(inputs.get("designer_hours"), 0.0) or 0.0)
    materials = max(0.0, _f(inputs.get("materials"), 0.0) or 0.0)
    lunch = max(0.0, _f(inputs.get("lunch_min"), LUNCH_MIN) or 0.0)
    price = _f(inputs.get("price"))

    trips = [_trip("install", card, rate, install_h, drive, miles, boxes, stored, missing, lunch)]
    if include_takedown:
        trips.append(_trip("takedown", card, rate, takedown_h, drive, miles, boxes, stored, missing, lunch))

    designer_rate = next((c["rate"] for c in card["classes"] if c["slug"] == "designer"), None)
    if designer_h > 0 and designer_rate is None and ic.PAY_PREFIX + "designer" not in missing:
        missing.append(ic.PAY_PREFIX + "designer")
    designer_cost = designer_h * (designer_rate or 0)

    labor = sum(t["_crew_pay"] for t in trips)
    other = sum(t["_other"] for t in trips)
    crew_hours = sum(t["_paid_h"] for t in trips)
    job_cost = labor + other + designer_cost + materials
    for t in trips:
        for k in ("_paid_h", "_crew_pay", "_other"):
            t.pop(k)

    oh_v = ic.value(card, "overhead_pct")
    if oh_v is None:
        missing.append("overhead_pct")
    target = ic.value(card, "target_profit_pct")
    oh = (oh_v or 0) / 100

    pcts = sorted(set(LEVELS) | ({target} if target is not None else set()))
    levels = []
    for p in pcts:
        keep = 1 - oh - p / 100
        lv: dict[str, Any] = {
            "profit_pct": p, "break_even": p == 0, "target": target is not None and p == target,
            "cost_share_pct": _r(keep * 100),
            "price_needed": _r(job_cost / keep) if keep > 0 else None,
        }
        if price is not None:
            max_cost = price * keep
            lv.update({
                "max_job_cost": _r(max_cost),
                "headroom": _r(max_cost - job_cost),
                # Crew-hours: hours of this whole crew on the clock, both trips.
                "max_crew_hours": _r(_div(max_cost - other - designer_cost - materials, rate if rate > 0 else None)),
                "max_materials": _r(max_cost - (job_cost - materials)),
                "max_designer_hours": _r(_div(max_cost - (job_cost - designer_cost), designer_rate or None)),
            })
        levels.append(lv)

    overhead = price * oh if price is not None else None
    profit = price - job_cost - overhead if price is not None and overhead is not None else None
    return {
        "crew_rate": _r(rate), "crew_size": people, "crew": seats,
        "takedown_time_factor": factor,
        "inputs": {
            "install_onsite_h": _r(install_h), "takedown_onsite_h": _r(takedown_h), "takedown_auto": takedown_auto,
            "include_takedown": include_takedown, "drive_min_each_way": _r(drive, 1),
            "miles_each_way": _r(miles, 1), "miles_auto": miles_auto, "boxes": boxes, "stored_with_us": stored,
            "designer_hours": _r(designer_h), "materials": _r(materials), "price": _r(price),
        },
        "trips": trips,
        "designer": {"hours": _r(designer_h), "rate": designer_rate, "cost": _r(designer_cost)},
        "materials": _r(materials),
        "crew_pay": _r(labor), "other": _r(other), "crew_hours": _r(crew_hours, 2),
        "job_cost": _r(job_cost),
        "overhead_pct": oh_v, "target_profit_pct": target,
        "price": _r(price), "overhead": _r(overhead), "profit": _r(profit),
        "profit_pct": _r(profit / price * 100, 1) if profit is not None and price else None,
        "levels": levels,
        "missing": missing,
    }
