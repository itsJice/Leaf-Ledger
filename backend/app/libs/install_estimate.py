"""Install estimates: next season's on-site hours for one client, from real
times first and per-item rates second. Pure functions, no database. Spec:
``install_estimate.md`` beside this file; value pins in
``tests/test_install_estimate.py``.

Order of preference (the user: "I can't send crews out on faulty
information", so nothing here invents hours):

1. **Last real on-site time.** The most recent season with a real time
   (Install Times, else the card's real hours). When both that season's and
   this season's inventory are on the card and they differ, the time is
   scaled by item-minutes now / item-minutes then (needs the rates for every
   item involved; without them it stays unscaled and says so).
2. **Per item.** Setup + minutes per tree (by height band), wreath, foot of
   garland, spray, swag, other piece and box; then the night, commercial and
   first-year factors.
3. **NEEDS INPUT.** Any rate (or size) the estimate needs that isn't set
   gives no hours and the list of what's missing.

Rates come from ``ll_app.estimate_rates`` (season, key, amount); see
RATE_KEYS for the keys and units.
"""
from __future__ import annotations

import math
import re
from typing import Iterable, Optional

#: Every rate key, its unit and what it means. Minutes are crew-minutes on
#: site for one crew (wall clock), like the schedule's hours.
RATE_KEYS: dict[str, tuple[str, str]] = {
    "setup": ("min / job", "Arrive, unload, walk-through and clean-up, once per visit"),
    "tree_small": ("min / tree", "Trees up to 7.5 ft"),
    "tree_medium": ("min / tree", "Trees 8 to 10 ft"),
    "tree_large": ("min / tree", "Trees 11 to 14 ft"),
    "tree_xl": ("min / tree", "Trees 15 ft and up"),
    "wreath": ("min / wreath", "Any size"),
    "garland_ft": ("min / ft", "Per foot of garland"),
    "spray": ("min / spray", ""),
    "swag": ("min / swag", ""),
    "other": ("min / piece", "Inventory lines typed Other"),
    "box": ("min / box", "Unpacking and repacking, per box on the card"),
    "factor_night": ("x", "Dallas night shift multiplier"),
    "factor_commercial": ("x", "Business (not residence) multiplier"),
    "factor_first_year": ("x", "First install for this client multiplier"),
}
ITEM_KEYS = ("setup", "tree_small", "tree_medium", "tree_large", "tree_xl", "wreath", "garland_ft",
             "spray", "swag", "other", "box")
FACTOR_KEYS = ("factor_night", "factor_commercial", "factor_first_year")

_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def feet(size: Optional[str]) -> Optional[float]:
    """A typed size in feet: "12 ft", "7.5'", "9ft", "12", "36 in" (3 ft),
    "6' 6\"" (6.5). None when there's no number."""
    s = str(size or "").strip().lower()
    if not s:
        return None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(?:'|ft|feet|foot)\s*(\d+(?:\.\d+)?)\s*(?:\"|in|inch|inches)\s*$", s)
    if m:
        return round(float(m.group(1)) + float(m.group(2)) / 12, 2)
    n = _NUM.search(s)
    if not n:
        return None
    v = float(n.group(1))
    if re.search(r"\d\s*(\"|in\b|inch)", s):
        return round(v / 12, 2)
    return v


def tree_band(ft: float) -> str:
    if ft <= 7.5:
        return "tree_small"
    if ft <= 10:
        return "tree_medium"
    if ft <= 14:
        return "tree_large"
    return "tree_xl"


def item_counts(inventory: Iterable[dict], boxes: Optional[int]) -> tuple[dict[str, float], list[str]]:
    """{rate key: count} for an inventory (trees by band, garland in feet)
    plus boxes, and what's missing to count it (a tree or garland with no
    size)."""
    counts: dict[str, float] = {}
    missing: list[str] = []
    for line in inventory or []:
        t = str(line.get("type") or "").lower()
        q = float(line.get("qty") or 1)
        if t == "tree":
            ft = feet(line.get("size"))
            if ft is None:
                missing.append("tree size")
                continue
            k = tree_band(ft)
            counts[k] = counts.get(k, 0) + q
        elif t == "garland":
            ft = feet(line.get("size"))
            if ft is None:
                missing.append("garland length")
                continue
            counts["garland_ft"] = counts.get("garland_ft", 0) + q * ft
        elif t in ("wreath", "spray", "swag", "other"):
            counts[t] = counts.get(t, 0) + q
    if boxes:
        counts["box"] = float(boxes)
    return counts, sorted(set(missing))


def item_minutes(inventory: Iterable[dict], boxes: Optional[int], rates: dict) -> tuple[Optional[float], list[str]]:
    """Setup + item minutes, or (None, what's missing)."""
    counts, missing = item_counts(inventory, boxes)
    need = ["setup", *counts.keys()]
    missing += [k for k in need if rates.get(k) is None]
    if missing:
        return None, sorted(set(missing))
    return float(rates["setup"]) + sum(float(rates[k]) * n for k, n in counts.items()), []


def _round_q(h: float) -> float:
    """To the nearest quarter hour, never below a quarter."""
    return max(0.25, math.floor(h * 4 + 0.5) / 4)


def same_inventory(a: Iterable[dict], b: Iterable[dict]) -> bool:
    def norm(inv):
        return sorted((str(x.get("type") or "").lower(), str(feet(x.get("size")) or x.get("size") or ""),
                       int(x.get("qty") or 1)) for x in inv or [])
    return norm(a) == norm(b)


def estimate(*, inventory: Optional[list], boxes: Optional[int], history: list[dict], rates: dict,
             night: bool = False, commercial: bool = False) -> dict:
    """Next season's hours for one client.

    ``history``: past seasons, each ``{season, hours, inventory, boxes,
    source}`` (hours = real on-site hours, or None). ``rates``: {key: amount
    or None}. Returns ``{hours, basis, basisText, confidence, needsInput,
    detail}``; hours is None with NEEDS INPUT."""
    real = sorted((h for h in history if h.get("hours")), key=lambda h: str(h["season"]))
    first_year = not history
    if real:
        last = real[-1]
        base = float(last["hours"])
        then_inv, now_inv = last.get("inventory") or [], inventory or []
        detail = {"lastSeason": str(last["season"]), "lastHours": round(base, 2), "source": last.get("source")}
        if then_inv and now_inv and not same_inventory(then_inv, now_inv):
            m_now, miss_now = item_minutes(now_inv, boxes, rates)
            m_then, miss_then = item_minutes(then_inv, last.get("boxes"), rates)
            if m_now is not None and m_then:
                ratio = m_now / m_then
                return {
                    "hours": _round_q(base * ratio), "basis": "last_real_scaled", "confidence": "medium",
                    "basisText": f"{last['season']} real {base:g} h, scaled {ratio:.2f}x for this year's inventory",
                    "needsInput": [], "detail": {**detail, "scale": round(ratio, 3)},
                }
            return {
                "hours": _round_q(base), "basis": "last_real", "confidence": "medium",
                "basisText": f"{last['season']} real {base:g} h; inventory changed but item rates are missing, so not scaled",
                "needsInput": sorted(set(miss_now + miss_then)), "detail": detail,
            }
        same = bool(then_inv and now_inv)
        return {
            "hours": _round_q(base), "basis": "last_real", "confidence": "high" if same else "medium",
            "basisText": f"{last['season']} real {base:g} h" + ("" if same else " (inventory not on both cards)"),
            "needsInput": [], "detail": detail,
        }

    minutes, missing = item_minutes(inventory or [], boxes, rates)
    factors = [k for k, on in (("factor_night", night), ("factor_commercial", commercial),
                               ("factor_first_year", first_year)) if on]
    missing += [k for k in factors if rates.get(k) is None]
    if not inventory:
        missing.append("inventory")
    if missing:
        return {"hours": None, "basis": "needs_input", "confidence": None,
                "basisText": "NEEDS INPUT: " + ", ".join(sorted(set(missing))),
                "needsInput": sorted(set(missing)), "detail": {}}
    mult = 1.0
    for k in factors:
        mult *= float(rates[k])
    return {
        "hours": _round_q(minutes * mult / 60), "basis": "per_item", "confidence": "low",
        "basisText": f"Per item: {minutes:g} min" + (f" x {mult:g} ({', '.join(f.replace('factor_', '').replace('_', ' ') for f in factors)})" if factors else ""),
        "needsInput": [], "detail": {"minutes": minutes, "factor": mult},
    }


# ─── fitting the rates from real jobs ────────────────────────────────────────


def fit_rates(jobs: list[dict], keys: Iterable[str] = ITEM_KEYS, *, min_jobs_per_key: int = 3,
              iterations: int = 5000) -> dict:
    """Least-squares minutes per item key from real jobs (``{inventory, boxes,
    hours}``), non-negative. A key gets a value only if at least
    ``min_jobs_per_key`` jobs have it; the rest stay None (NEEDS INPUT).
    Returns ``{rates: {key: minutes|None}, jobs, rmseMin}``."""
    keys = list(keys)
    rows, ys = [], []
    for j in jobs:
        if not j.get("hours"):
            continue
        counts, missing = item_counts(j.get("inventory") or [], j.get("boxes"))
        if missing or not counts:
            continue
        rows.append([1.0 if k == "setup" else float(counts.get(k, 0)) for k in keys])
        ys.append(float(j["hours"]) * 60)
    support = {k: sum(1 for r in rows if r[i]) for i, k in enumerate(keys)}
    use = [i for i, k in enumerate(keys) if support[k] >= min_jobs_per_key]
    if not rows or not use:
        return {"rates": {k: None for k in keys}, "jobs": len(rows), "rmseMin": None}
    X = [[r[i] for i in use] for r in rows]
    n = len(use)
    # Projected gradient descent on 0.5*|Xb - y|^2 with b >= 0 (no numpy here).
    xtx = [[sum(X[r][a] * X[r][b] for r in range(len(X))) for b in range(n)] for a in range(n)]
    xty = [sum(X[r][a] * ys[r] for r in range(len(X))) for a in range(n)]
    lip = max(sum(abs(v) for v in row) for row in xtx) or 1.0
    beta = [0.0] * n
    for _ in range(iterations):
        grad = [sum(xtx[a][b] * beta[b] for b in range(n)) - xty[a] for a in range(n)]
        beta = [max(0.0, beta[a] - grad[a] / lip) for a in range(n)]
    pred = [sum(X[r][a] * beta[a] for a in range(n)) for r in range(len(X))]
    rmse = math.sqrt(sum((p - y) ** 2 for p, y in zip(pred, ys)) / len(ys))
    rates = {k: None for k in keys}
    for a, i in enumerate(use):
        rates[keys[i]] = round(beta[a], 2)
    return {"rates": rates, "jobs": len(rows), "rmseMin": round(rmse, 1)}
