"""What a Christmas install SHOULD cost, and how far the charged price sits
from it.

One pure module, no database, used by the clients API (every season row it
returns carries a ``pricing`` block), and therefore by the Clients tab and
the scheduler's billing export, which both read that block. Nothing else
computes a price.

Rules (user, 2026-09-25):

* **Ideal** = on-site labour for install, the same again for takedown
  (takedown ALWAYS costs the same as install), storage per box, and a
  pickup & delivery fee.
* On-site labour = (leads x crew_lead + specialty x specialty
  + designer x designer + general x general) x estimated install hours.
  The headcounts are the season's ``role_need`` -- the same four numbers
  the spreadsheet has always carried per client.
* **Pickup & delivery** replaces the old flat $150 each way. The client is
  only charged from crew arrival to crew departure; the fee covers the
  unpaid rest of the two van trips a season. Install trip: pull the boxes
  off the shelf and load the trailer, drive out, (on-site time is already
  charged), drive back. Takedown trip: drive out, load the trailer, drive
  back, unload and shelve. So::

      loading_min = 2 x boxes x handling_min_per_box    (only if we store them)
      driving_min = 2 x (drive_min_out + drive_min_back) (everyone)
      fee         = (loading_min + driving_min) / 60 x van_crew_rate

  Boxes that stay at the client's house need no warehouse handling. A leg
  the scheduler has not mapped uses ``drive_min_default``.
* **Charged** is the stored fact, never derived: the season's ``total`` as
  sent to the client, or the real ``invoice_total`` once that is on record.
  It is deliberately NOT a sum of whatever fees happen to be filled in --
  a row with only a storage fee is an unpriced job, not a $75 one.
* **Discount** = 1 - charged / ideal, shown and never stored, so a fix to
  the ideal formula moves the discount, not anyone's price.
"""
from __future__ import annotations

from typing import Any, Iterable

#: Every rate the card needs, with what a missing one means for the ideal.
RATE_KEYS = (
    "crew_lead", "specialty", "designer", "general",
    "storage_box",
    "van_crew_rate", "handling_min_per_box", "drive_min_default",
)

#: role_need key -> rate key. The sheet's four headcount columns.
ROLE_RATES = (("leads", "crew_lead"), ("specialty", "specialty"),
              ("designer", "designer"), ("general", "general"))


def _num(v: Any) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def resolve_rates(rows: Iterable[dict], season: str) -> dict[str, float]:
    """The rate card in force for ``season`` from ``(season, key, amount)``
    rows: each key's value from the latest season <= the one asked for. So a
    2027 with no rows yet prices off 2026, and a 2027 with only
    ``van_crew_rate`` changed keeps every other 2026 rate."""
    want = str(season)
    best: dict[str, tuple[str, float]] = {}
    for r in rows:
        s, k = str(r.get("season") or ""), r.get("key")
        a = _num(r.get("amount"))
        if not k or a is None or not s or s > want:
            continue
        if k not in best or s > best[k][0]:
            best[k] = (s, a)
    return {k: v for k, (_, v) in best.items()}


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


def ideal(detail: dict | None, rates: dict[str, float]) -> dict:
    """The ideal price breakdown for one season row.

    Returns install, takedown, storage, pickup_delivery and total (each a
    float or None), plus ``missing``: the card fields or rates still needed
    before the number means anything. ``total`` is None whenever any part
    of it is."""
    d = detail or {}
    missing: list[str] = []
    role = d.get("role_need") if isinstance(d.get("role_need"), dict) else {}
    hours = _num(d.get("est_hours"))
    if hours is None:
        missing.append("est_hours")
    hourly = 0.0
    any_role = False
    for role_key, rate_key in ROLE_RATES:
        n = _num(role.get(role_key))
        if not n:
            continue
        any_role = True
        rate = rates.get(rate_key)
        if rate is None:
            missing.append(f"rate:{rate_key}")
            continue
        hourly += n * rate
    if not any_role:
        missing.append("role_need")
    install = _round2(hourly * hours) if hours is not None and any_role and not missing else None

    storing = bool(d.get("storing"))
    boxes = _num(d.get("boxes")) or 0.0
    storage: float | None = 0.0
    if storing:
        if rates.get("storage_box") is None:
            missing.append("rate:storage_box")
            storage = None
        else:
            storage = _round2(boxes * rates["storage_box"])

    pd: float | None = None
    van = rates.get("van_crew_rate")
    per_box = rates.get("handling_min_per_box")
    default_leg = rates.get("drive_min_default")
    out = _num(d.get("drive_min_out"))
    back = _num(d.get("drive_min_back"))
    if out is None:
        out = default_leg
    if back is None:
        back = default_leg
    if van is None or per_box is None or out is None or back is None:
        for k, v in (("van_crew_rate", van), ("handling_min_per_box", per_box),
                     ("drive_min_default", default_leg)):
            if v is None and f"rate:{k}" not in missing:
                missing.append(f"rate:{k}")
    else:
        loading = 2 * boxes * per_box if storing else 0.0
        driving = 2 * (out + back)
        pd = _round2((loading + driving) / 60.0 * van)

    total = None
    if install is not None and storage is not None and pd is not None:
        total = _round2(install * 2 + storage + pd)
    return {
        "install": install,
        "takedown": install,
        "storage": storage,
        "pickup_delivery": pd,
        "total": total,
        "missing": missing,
    }


def charged(detail: dict | None) -> float | None:
    """What the client was (or will be) billed: the real invoice once on
    record, else the total as sent. Never a sum of partial fees."""
    d = detail or {}
    inv = _num(d.get("invoice_total"))
    if inv is not None:
        return _round2(inv)
    tot = _num(d.get("total"))
    return _round2(tot) if tot is not None else None


def price_view(detail: dict | None, rates: dict[str, float]) -> dict:
    """The ``pricing`` block a season row carries out of the API."""
    d = detail or {}
    ide = ideal(d, rates)
    chg = charged(d)
    discount = None
    if chg is not None and ide["total"]:
        discount = round((1 - chg / ide["total"]) * 100, 1)
    return {
        "ideal": ide,
        "charged": chg,
        "charged_source": ("invoice" if _num(d.get("invoice_total")) is not None
                           else "total" if chg is not None else None),
        "discount_pct": discount,
        "basis": d.get("price_basis") or None,
    }
