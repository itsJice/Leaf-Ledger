"""What a Christmas install COSTS us to run, as opposed to what we charge.

The billing side is ``app.libs.pricing`` (the Christmas rate card). This is
the other side of the ledger: the install cost card, one set of numbers per
season, and the arithmetic that turns a crew-day into dollars. Pure, no
database -- the install-costs API stores the card, this module reads it.

Rules (user, 2026-09-29):

* Installers are 1099 contractors paid hourly for the whole shift. No
  overtime, no labor burden, no night extra, no minimum hours. Lunch, drive
  time and warehouse loading are all paid, so a person's paid hours for a
  crew-day are simply depot-to-depot.
* Pay is by **class**, not by person: the card holds a rate per class
  (Lead, Lead Assist, General Installer, Junior Installer, Designer, and any
  class added later) and each installer on the roster is assigned a class.
  An installer with no class assigned falls back to the class matching
  their roster title. A per-person rate override exists for the exception,
  and wins over the class rate.
* Vehicles cost per crew per day (van rental, trailer rental, rental
  insurance), gas is ``miles / mpg x price per gallon`` from the day's real
  route miles, plus optional wear per mile. Every crew-day also carries a
  flat ancillary amount (the things that just come up), plus tolls and
  parking.
* Overhead is a percentage of revenue (what is left of Brooke's operating
  expenses once crew and vans are charged to jobs). Break-even job cost is
  ``100 - overhead``; the target is ``100 - overhead - target profit``.

A key the card has no value for is **missing**, never a silent zero: a
required key (the rentals) makes every figure built on it a placeholder, and
the UI says NEEDS INPUT. Optional keys (tolls, parking, wear) read as zero.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

#: Prefix for a pay-class key: ``pay:lead`` -> the Lead hourly rate.
PAY_PREFIX = "pay:"

#: The five classes the card starts with, in display order.
DEFAULT_CLASSES = (
    ("lead", "Lead"),
    ("lead_assist", "Lead Assist"),
    ("general", "General Installer"),
    ("junior", "Junior Installer"),
    ("designer", "Designer"),
)

#: Roster title -> the class an unassigned installer is paid as.
TITLE_CLASS = {"Lead": "lead", "Lead Assist": "lead_assist", "Designer": "designer",
               "General Installer": "general"}

#: Every non-pay key the card holds. ``required`` keys have no safe default.
COST_KEYS: dict[str, dict[str, Any]] = {
    "van_day":              {"required": True},
    "trailer_day":          {"required": True},
    "vans_per_crew":        {"required": False, "default": 1},
    "trailers_per_crew":    {"required": False, "default": 1},
    "rental_insurance_day": {"required": False, "default": 0},
    "mpg":                  {"required": True},
    "gas_per_gallon":       {"required": True},
    "wear_per_mile":        {"required": False, "default": 0},
    "ancillary_day":        {"required": False, "default": 0},
    "tolls_day":            {"required": False, "default": 0},
    "parking_day":          {"required": False, "default": 0},
    "load_min_per_box":     {"required": False, "default": 0},
    "prep_min_per_job":     {"required": False, "default": 0},
    # Takedown crew time as a share of install crew time -- the client
    # sheet's own estimate ("takedown hours = 0.6 x install"). Only a time
    # estimate: the takedown PRICE always equals the install price.
    "takedown_time_factor": {"required": False, "default": 0.6},
    "overhead_pct":         {"required": True},
    "target_profit_pct":    {"required": True},
}


def _num(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def valid_key(key: str) -> bool:
    if key in COST_KEYS:
        return True
    return key.startswith(PAY_PREFIX) and slug_ok(key[len(PAY_PREFIX):])


def slug_ok(slug: str) -> bool:
    return bool(slug) and len(slug) <= 40 and all(c.islower() or c.isdigit() or c == "_" for c in slug)


def slugify(label: str) -> str:
    out, last_us = [], False
    for ch in (label or "").strip().lower():
        if ch.isalnum() and ch.isascii():
            out.append(ch)
            last_us = False
        elif not last_us and out:
            out.append("_")
            last_us = True
    return "".join(out).strip("_")[:40]


def resolve_card(rows: Iterable[dict], season: str) -> dict:
    """The card in force for ``season`` from ``(season, key, amount, label)``
    rows: each key takes its value from the latest season <= the one asked
    for, like the rate card. A row whose amount is NULL is a deliberate
    removal in that season (a class dropped, a value cleared), so an older
    season's value does not come back through inheritance.

    Returns ``{costs, classes, missing}``: ``costs`` holds every non-pay key
    that has a value, ``classes`` the pay classes in display order
    ``[{slug, label, rate}]``, and ``missing`` the required keys (and classes
    with no rate) nobody has filled in yet."""
    want = str(season)
    best: dict[str, tuple[str, Optional[float], Optional[str]]] = {}
    for r in rows:
        s, k = str(r.get("season") or ""), r.get("key")
        if not k or not s or s > want:
            continue
        if k not in best or s > best[k][0]:
            best[k] = (s, _num(r.get("amount")), r.get("label"))

    costs = {k: v for k, (_, v, _l) in best.items() if k in COST_KEYS and v is not None}
    order = {slug: i for i, (slug, _) in enumerate(DEFAULT_CLASSES)}
    default_label = dict(DEFAULT_CLASSES)
    classes = []
    for k, (_, v, label) in best.items():
        if not k.startswith(PAY_PREFIX):
            continue
        slug = k[len(PAY_PREFIX):]
        # A NULL amount with no label is a removal; a label with no amount is
        # a class that exists but has no rate yet.
        if v is None and not label:
            continue
        classes.append({"slug": slug, "label": label or default_label.get(slug, slug), "rate": v})
    classes.sort(key=lambda c: (order.get(c["slug"], 99), c["label"].lower()))

    missing = [k for k, meta in COST_KEYS.items() if meta["required"] and k not in costs]
    missing += [PAY_PREFIX + c["slug"] for c in classes if c["rate"] is None]
    return {"costs": costs, "classes": classes, "missing": missing}


def value(card: dict, key: str) -> Optional[float]:
    """A cost key's value, falling back to its optional default. None for a
    required key with nothing on the card."""
    v = card["costs"].get(key)
    if v is not None:
        return v
    return COST_KEYS[key].get("default")


def derived(card: dict) -> dict:
    """The numbers the card implies: gas per mile, break-even and target job
    cost as a share of the price."""
    mpg, gal = value(card, "mpg"), value(card, "gas_per_gallon")
    oh, profit = value(card, "overhead_pct"), value(card, "target_profit_pct")
    return {
        "gas_per_mile": round(gal / mpg, 4) if mpg and gal is not None else None,
        "break_even_pct": round(100 - oh, 2) if oh is not None else None,
        "target_spend_pct": round(100 - oh - profit, 2) if oh is not None and profit is not None else None,
    }


def person_rate(person: dict, assignment: Optional[dict], card: dict) -> dict:
    """What one installer is paid per hour, and why.

    ``assignment`` is their row from the pay-assignment table (``pay_class``,
    ``rate_override``), or None. Returns ``{pay_class, label, rate, source}``
    where source is ``override`` | ``class`` | ``title`` (no class assigned,
    paid as their roster title) | ``missing`` (the class has no rate)."""
    classes = {c["slug"]: c for c in card["classes"]}
    a = assignment or {}
    slug = a.get("pay_class") if a.get("pay_class") in classes else None
    source = "class"
    if not slug:
        slug = TITLE_CLASS.get(person.get("title") or "", "general")
        source = "title"
    cls = classes.get(slug)
    label = cls["label"] if cls else slug
    override = _num(a.get("rate_override"))
    if override is not None:
        return {"pay_class": slug, "label": label, "rate": override, "source": "override"}
    rate = cls["rate"] if cls else None
    return {"pay_class": slug, "label": label, "rate": rate, "source": source if rate is not None else "missing"}


def _r2(x: float) -> float:
    return round(x + 0.0, 2)


def crew_day_cost(rates: list[Optional[float]], paid_hours: float, miles: float, card: dict) -> dict:
    """The cost of one crew for one day.

    ``rates`` is each person's hourly pay (None when unknown), ``paid_hours``
    the shift depot-to-depot (lunch, drive and loading are paid), ``miles``
    the day's route miles. Returns every line, the total, and ``missing``:
    anything unknown is left out of the total AND named, so a total with a
    non-empty ``missing`` is a placeholder, never a real number."""
    missing: list[str] = []
    known = [r for r in rates if r is not None]
    if len(known) < len(rates):
        missing.append("pay rate")
    labor = sum(known) * paid_hours

    def per_day(key: str, count_key: Optional[str] = None) -> float:
        v = value(card, key)
        if v is None:
            missing.append(key)
            return 0.0
        n = value(card, count_key) if count_key else 1
        return v * (n or 0)

    van = per_day("van_day", "vans_per_crew")
    trailer = per_day("trailer_day", "trailers_per_crew")
    vehicles = (value(card, "vans_per_crew") or 0) + (value(card, "trailers_per_crew") or 0)
    insurance = (value(card, "rental_insurance_day") or 0) * vehicles
    gpm = derived(card)["gas_per_mile"]
    if gpm is None:
        missing.append("gas")
    # Gas and wear are per van: two vans on one crew drive the route twice.
    vans = value(card, "vans_per_crew") or 0
    gas = (gpm or 0) * miles * vans
    wear = (value(card, "wear_per_mile") or 0) * miles * vans
    ancillary = value(card, "ancillary_day") or 0
    tolls = value(card, "tolls_day") or 0
    parking = value(card, "parking_day") or 0

    lines = {
        "labor": _r2(labor), "van": _r2(van), "trailer": _r2(trailer), "insurance": _r2(insurance),
        "gas": _r2(gas), "wear": _r2(wear), "ancillary": _r2(ancillary), "tolls": _r2(tolls),
        "parking": _r2(parking),
    }
    return {**lines, "total": _r2(sum(lines.values())), "missing": missing}
