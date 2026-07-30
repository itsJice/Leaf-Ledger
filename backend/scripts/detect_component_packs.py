#!/usr/bin/env python3
"""Per-line pack-vs-piece detection for the historical recipe components.

``historical_recipe_components.quantity`` is ambiguous: some designers logged the
number of *multi-packs* they bought, others logged individual *pieces*. This
script decides, line by line, which reading the row's ``first_cost`` implies, and
records the verdict additively in ``formulas.pack_analysis``. Nothing else is
touched -- in particular no pricing column is ever written, because the sheet
totals are the business record and must keep reconciling.

    python scripts/detect_component_packs.py            # dry run (default)
    python scripts/detect_component_packs.py --commit    # write
    python scripts/detect_component_packs.py --commit --era-factor 0.70


How a line is decided
=====================

1. **Catalog match.** ``upper(trim(supplier_sku))`` against ``products``. No
   match (or no ``current_price``, or no usable ``first_cost``) -> ``unknown``.

2. **Pack size.** Parsed from ``products.name``: ``3/Pk``, ``6/pk``, ``2/Bx``,
   ``12/Bag``, ``4/Box``, ``3/Bundle``, ``Set of 4``, ``Box of 12`` and the
   glass-trade ``12 p/c`` ("pieces per carton"). ``products.case_qty`` is the
   *shipping* case, not the retail pack, so it is never used as a pack size --
   only as weak corroboration (see below). Recipe-line descriptions are parsed
   too (``3.9" Smooth Foam Ball 6bag``) but a description-derived pack size can
   never by itself produce a ``pack`` verdict, since there is no catalog price to
   test it against.

   ``X#`` in a name (``Phalaenopsis x7 33.5"``, ``27" Yucca Spray X60``) means
   parts-per-plant -- blooms, leaves, fronds -- **not** a pack. Those SKUs carry
   ``uom = 'EA'`` in the catalog. ``X#`` is recorded in the evidence as
   deliberately ignored and never contributes to ``pack_size``. Dimension strings
   (``Zinc 20"X12"X12"``, ``Hard Mapple 1-2"X 6'``) are excluded by requiring the
   ``x`` to follow whitespace rather than a quote mark.

3. **Cost-basis test.** Recipes are 2020-23; the catalog is priced today. The
   measured era factor is the median of ``first_cost / current_price`` over the
   catalog-matched lines whose product name carries **no** pack pattern:

       ERA_FACTOR = 0.64   (measured 0.636, n = 126)

   Two candidate readings are scored, each as a ratio to its era-adjusted
   expectation (1.0 == a perfect fit):

       z_pack  = first_cost / (current_price * ERA_FACTOR)
       z_piece = first_cost / (current_price / pack_size * ERA_FACTOR)
                 (note z_piece == z_pack * pack_size)

   Each reading gets a log-normal likelihood ``exp(-ln(z)^2 / 2*SIGMA^2)`` with

       SIGMA = 0.35        # log-space spread of the era ratio

   and ``confidence`` is the normalised posterior of the winner, i.e. a real
   probability in [0.5, 1.0].

   SIGMA is deliberately wider than the robust spread of the measured era ratio
   (MAD-derived sigma was 0.15) because era drift, vendor discounts and one-off
   negotiated costs all inflate the real dispersion: only 71% of non-pack lines
   sit within a factor of 1.5 of the era expectation, 79% within a factor of 2.

4. **Thresholds.** A verdict is only issued when all of these hold:

       MIN_CONFIDENCE = 0.70          posterior of the winning reading
       MAX_ABS_LOG    = ln(3.0)       winner within a factor of 3 of era expectation
       integral quantity              required for a ``pack`` verdict

   otherwise the line is ``ambiguous``. The absolute-fit gate is deliberately
   loose and the decision is driven by the *relative* fit, because the era factor
   is a median over a wide distribution -- ``4" Green Succulent Stem 6/pk`` at
   ``first_cost 12.34`` vs a pack price of ``11.14`` is 1.74x the era
   expectation, yet still unmistakably a pack because the piece reading is 10x
   off.

   A non-integral ``quantity`` (0.25, 0.5, 0.05, ...) blocks a ``pack`` verdict:
   nobody buys a quarter of a 3-pack, so ``quantity * pack_size`` would be a
   fictional piece count. Those lines stay ``ambiguous`` and keep quantity as
   written. 58 rows in the corpus are fractional; most are consumables ("Palm
   Fiber 0.034", "Natural lichen moss 0.05") measured as a fraction of a bag.

5. **Bad catalog matches.** ``supplier_sku`` is not globally unique across
   suppliers, so the join produces real collisions (a Melrose "Bird House
   Ornament" answering to the SKU a designer used for a "Marta Pot"). A match is
   *rejected* -- back to ``unknown``, and listed in the report -- when either:

       best |ln z| > ln(5.0)                        no reading is credible at all
       zero name-token overlap AND |ln z| > ln(2.0) neither name nor price agrees

   Name overlap alone is never enough to reject, because the corpus is full of
   hand-typed misspellings; overlap is therefore fuzzy (``difflib`` ratio >= 0.85,
   which accepts "Echeverria"/"Echeveria" and "Mapple"/"Maple" while still keeping
   "planter"/"plate" apart). The zero-overlap rule is also suppressed when the
   catalog name literally contains the SKU (``CBR1444WT - White Glossy Long Flat
   Rectangle``), since that corroborates the join on its own.

6. **case_qty.** Never a pack size. In this catalog the retail pack is always
   written into the name and ``case_qty`` is always the shipping case: the
   pack-named products carry ``case_qty`` 6/12/18/24/48/72, none of which is the
   pack. So ``case_qty`` gets two narrow jobs only:

   * when a name pack size exists, ``case_qty`` being an exact multiple of it is
     recorded as corroboration;
   * when no name pack size exists, ``case_qty`` is in 2..12, **and** the
     single-unit reading has already failed the factor-3 sanity band, the line is
     downgraded to ``ambiguous`` with a note.

   It can never promote a line to ``pack``. The second rule is deliberately gated
   on the single-unit reading failing first, because on price alone almost any
   well-matched single unit "could" be a small case -- a $49.78 potted palm bought
   one at a time included.

``pieces_used`` is ``quantity * pack_size`` for ``pack`` and ``quantity`` for
``piece`` / ``ambiguous`` / ``unknown`` (i.e. as written).


Safety
======
* Dry run by default. ``--commit`` writes.
* Writes are ``formulas = coalesce(formulas,'{}') || {"pack_analysis": ...}`` --
  a JSONB merge, so the existing ``extended_total`` / ``landed_cost`` /
  ``retail`` / ``anomalies`` / ``flat_priced`` / ``merged_from_row`` keys survive
  untouched. The project's additive-only rule for this data is enforced by a
  post-condition, not just by convention.
* Idempotent: a row is only updated when the recomputed block differs from what
  is already stored, so a second run reports zero changes.
* All writes happen in one transaction which is rolled back unless every
  post-condition passes:
    - row count unchanged
    - md5 over (quantity, first_cost, landed_cost, retail, extended_total)
      unchanged
    - md5 over ``formulas - 'pack_analysis'`` unchanged (nothing dropped or
      rewritten)
    - all 223 recipes still reconcile: SUM(component extended_total) ==
      ``pricing_summary.component_extended_sum``
* No DDL. The ``app`` role does not own the public schema, which is exactly why
  the verdict lives in the existing ``formulas`` JSONB column.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

BACKEND = Path(__file__).resolve().parents[1]

VERSION = 1
ANALYSIS_KEY = "pack_analysis"

# ── tuning constants (see the module docstring for the derivation) ────────────

ERA_FACTOR = 0.64          # measured median first_cost / current_price, n=126
SIGMA = 0.35               # log-space spread used for the likelihoods
MIN_CONFIDENCE = 0.70      # posterior needed to issue a pack/piece verdict
MAX_ABS_LOG = math.log(3.0)        # winner must be within a factor of 3
REJECT_ABS_LOG = math.log(5.0)     # beyond this the catalog match is unusable
REJECT_NO_OVERLAP_LOG = math.log(2.0)  # with zero name overlap, be stricter
CASE_QTY_PACK_MAX = 12     # above this a case_qty is certainly a shipping case
CASE_QTY_PACK_MIN = 2

BASIS_PACK = "pack"
BASIS_PIECE = "piece"
BASIS_AMBIGUOUS = "ambiguous"
BASIS_UNKNOWN = "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# Pack-size parsing
# ══════════════════════════════════════════════════════════════════════════════

# Unit tokens that mean "a retail pack of N". Kept deliberately tight.
PACK_UNITS = (
    "pk", "pks", "pkg", "pkgs", "pack", "packs",
    "bx", "bxs", "box", "boxes",
    "bag", "bags", "bg", "bgs",
    "set", "sets", "st",
    "bundle", "bundles", "bndle", "bnd",
    "bunch", "bunches",
    "tray", "trays",
)

# Tokens that look like a pack but are NOT a retail pack. Listed so the
# exclusion is explicit and testable rather than an accident of the accept list.
#   cs/case/carton/bulk -> the shipping case
#   ast/asst/assort(ed) -> how many *designs* are assorted, not how many ship
#   ea/each/pc          -> explicitly a single unit
NON_PACK_UNITS = (
    "cs", "case", "cases", "carton", "cartons", "bulk",
    "ast", "asst", "assort", "assorted", "assrtd", "ass", "as",
    "ea", "each", "pc", "pcs", "pvc",
)

# "6/pk", "12 / Bag", "3/Bundle" -- the leading number must not continue a
# decimal or another number, which keeps dimensions and fractions out.
_SLASH_PACK = re.compile(
    r"(?<![\d.])(\d{1,3})\s*/\s*(" + "|".join(sorted(PACK_UNITS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# "Set of 4", "Box of 12", "Pack of 3", "(Set of 2)"
_WORD_OF_PACK = re.compile(
    r"\b(?:set|box|bag|pack|pkg|bundle)\s+of\s+(\d{1,3})\b", re.IGNORECASE)

# Glass-trade "12 p/c" == pieces per carton; current_price is then the carton.
_PER_CARTON = re.compile(r"(?<![\d.])(\d{1,3})\s*p\s*/\s*c\b", re.IGNORECASE)

# A pack size written into a recipe line description: "Smooth Foam Ball 6bag".
_BARE_PACK = re.compile(
    r"(?<![\d.])(\d{1,3})\s*(" + "|".join(sorted(PACK_UNITS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# "X7", "X60", "x 15" -- parts per plant, never a pack. The x must follow
# whitespace (or start of string) so that dimension strings such as
# `20"X12"X12"` and `1-2"X 6'` cannot match, and the digits must not run into a
# decimal or a quote mark so that `15"L x 9.5"W` cannot match either.
_X_PATTERN = re.compile(r"(?:(?<=\s)|(?<=^))(x\s?\d{1,4})(?![\d.])(?!\s*[\"'’”])",
                        re.IGNORECASE)

MAX_PACK_SIZE = 500


def _valid_pack(size: int) -> bool:
    return 1 <= size <= MAX_PACK_SIZE


def parse_pack_size(name: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """Retail pack size stated in *name*, as ``(size, matched_text)``.

    Returns ``(None, None)`` when the name states no pack size. A stated size of
    1 (``8" Ball 1/Bx``) is returned as 1 -- an explicit single unit.
    """
    if not name:
        return None, None
    for pattern in (_PER_CARTON, _SLASH_PACK, _WORD_OF_PACK):
        for match in pattern.finditer(name):
            size = int(match.group(1))
            if _valid_pack(size):
                return size, match.group(0).strip()
    return None, None


def parse_pack_size_loose(text: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """As :func:`parse_pack_size` but also accepts the bare ``6bag`` form.

    Only used on recipe-line descriptions, which are hand-typed and drop the
    slash. Never used on catalog names, where the bare form would collide with
    dimensions and colour codes.
    """
    size, matched = parse_pack_size(text)
    if size is not None:
        return size, matched
    if not text:
        return None, None
    for match in _BARE_PACK.finditer(text):
        value = int(match.group(1))
        if _valid_pack(value) and value > 1:
            return value, match.group(0).strip()
    return None, None


def find_x_pattern(name: Optional[str]) -> Optional[str]:
    """The ``X#`` parts-per-plant marker in *name*, for the evidence trail only."""
    if not name:
        return None
    match = _X_PATTERN.search(name)
    return match.group(1).upper().replace(" ", "") if match else None


def case_qty_pack_hint(case_qty: Optional[int]) -> Optional[int]:
    """A ``case_qty`` small enough that it *might* also be the retail pack.

    Weak signal only: it can downgrade a verdict to ``ambiguous``, never promote
    one to ``pack``. 32/36/48/80 and friends are shipping cases and are rejected.
    """
    if case_qty is None:
        return None
    try:
        value = int(case_qty)
    except (TypeError, ValueError):
        return None
    return value if CASE_QTY_PACK_MIN <= value <= CASE_QTY_PACK_MAX else None


# ══════════════════════════════════════════════════════════════════════════════
# Name-overlap scoring (used to catch supplier_sku collisions)
# ══════════════════════════════════════════════════════════════════════════════

_STOPWORDS = {
    "the", "and", "with", "for", "inch", "inches", "regular", "asst", "assorted",
    "large", "small", "mini", "tall", "real", "touch", "faux", "artificial",
    "green", "white", "black", "brown", "grey", "gray", "silver", "gold", "red",
    "blue", "pink", "purple", "yellow", "orange", "natural", "nat", "each",
}



# The corpus is full of hand-typed misspellings -- "Echeverria" for Echeveria,
# "Thilandsia" for Tillandsia, "Mapple" for Maple, "Vicerman" for Vickerman --
# so exact token equality would throw away good matches. 0.85 accepts those and
# ordinary plurals while still separating planter/plate (0.83) and vase/case (0.75).
_FUZZY_CUTOFF = 0.85


def _tokens(text: Optional[str]) -> set[str]:
    if not text:
        return set()
    raw = re.findall(r"[a-z]{3,}", text.lower())
    return {t for t in raw if t not in _STOPWORDS}


def name_overlap(description: Optional[str], catalog_name: Optional[str]) -> float:
    """Fraction of the recipe line's significant words the catalog name also has."""
    from difflib import SequenceMatcher

    left, right = _tokens(description), _tokens(catalog_name)
    if not left or not right:
        return 0.0
    hits = 0
    for token in left:
        if token in right or any(
                SequenceMatcher(None, token, other).ratio() >= _FUZZY_CUTOFF
                for other in right):
            hits += 1
    return round(hits / len(left), 3)


def _squash(text: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def sku_in_name(supplier_sku: Optional[str], catalog_name: Optional[str]) -> bool:
    """Does the catalog name literally contain the SKU?

    Some vendors bake the SKU into the product name (``CBR1444WT - White Glossy
    Long Flat Rectangle``). That is corroboration the join is right even when no
    descriptive word is shared, so it suppresses the zero-overlap rejection rule.
    """
    sku = _squash(supplier_sku)
    return len(sku) >= 4 and sku in _squash(catalog_name)


# ══════════════════════════════════════════════════════════════════════════════
# Classification
# ══════════════════════════════════════════════════════════════════════════════

def _fit(z: float) -> float:
    """Log-normal likelihood that an era-adjusted ratio of *z* is the truth."""
    if z <= 0:
        return 0.0
    return math.exp(-(math.log(z) ** 2) / (2.0 * SIGMA * SIGMA))


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_integral(value: Optional[float]) -> bool:
    return value is not None and abs(value - round(value)) < 1e-9


def _round(value: Optional[float], places: int = 4) -> Optional[float]:
    """Fixed-precision rounding, so a re-run produces byte-identical JSON."""
    return None if value is None else round(value + 0.0, places)


def classify_line(
    *,
    quantity: Any = None,
    first_cost: Any = None,
    description: Optional[str] = None,
    catalog_sku: Optional[str] = None,
    catalog_name: Optional[str] = None,
    catalog_price: Any = None,
    catalog_supplier: Optional[str] = None,
    case_qty: Optional[int] = None,
    vendor: Optional[str] = None,
    era_factor: float = ERA_FACTOR,
) -> dict[str, Any]:
    """Decide the cost basis of one component line.

    Pure: no database, no I/O. Returns the ``formulas.pack_analysis`` block.
    """
    qty = _f(quantity)
    cost = _f(first_cost)
    price = _f(catalog_price)
    notes: list[str] = []

    catalog_pack, catalog_pack_text = parse_pack_size(catalog_name)
    line_pack, line_pack_text = parse_pack_size_loose(description)
    x_pattern = find_x_pattern(catalog_name) or find_x_pattern(description)
    if x_pattern:
        notes.append(f"{x_pattern} in name is parts-per-unit, not a pack; ignored")

    if catalog_pack is not None:
        pack_size: Optional[int] = catalog_pack
        pack_source: Optional[str] = "catalog_name"
        pack_text = catalog_pack_text
    elif line_pack is not None:
        pack_size, pack_source, pack_text = line_pack, "line_description", line_pack_text
        notes.append("pack size read from the recipe line, not the catalog; "
                     "cannot support a pack verdict on its own")
    else:
        pack_size, pack_source, pack_text = None, None, None

    hint = case_qty_pack_hint(case_qty)
    if pack_size is not None and case_qty is not None:
        try:
            if pack_size > 1 and int(case_qty) % pack_size == 0:
                notes.append(f"case_qty {case_qty} is a multiple of pack size "
                             f"{pack_size} (corroborates)")
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    result: dict[str, Any] = {
        "version": VERSION,
        "basis": BASIS_UNKNOWN,
        "pack_size": pack_size,
        "pack_size_source": pack_source,
        "pieces_used": _round(qty, 6),
        "confidence": 0.0,
        "quantity": _round(qty, 6),
        "catalog_sku": catalog_sku,
        "catalog_name": catalog_name,
        "catalog_price": _round(price, 4),
        "catalog_supplier": catalog_supplier,
        "era_factor": round(era_factor, 4),
        "evidence": {
            "reason": "",
            "pack_text": pack_text,
            "x_pattern": x_pattern,
            "case_qty": int(case_qty) if case_qty is not None else None,
            "vendor": vendor,
            "name_overlap": name_overlap(description, catalog_name),
            "sku_in_name": sku_in_name(catalog_sku, catalog_name),
            "pack_ratio": None,
            "piece_ratio": None,
            "posterior_pack": None,
            "notes": notes,
        },
    }
    ev = result["evidence"]

    # ── no basis for any comparison ──────────────────────────────────────────
    if catalog_name is None and price is None:
        ev["reason"] = "no catalog match on supplier_sku"
        return result
    if price is None or price <= 0:
        ev["reason"] = "catalog match has no usable current_price"
        return result
    if cost is None or cost <= 0:
        ev["reason"] = "line has no usable first_cost"
        return result

    era_price = price * era_factor
    z_pack = cost / era_price
    ev["pack_ratio"] = _round(z_pack)

    # ── no pack size: the distinction is moot, quantity IS pieces ────────────
    if pack_size is None or pack_size == 1 or pack_source == "line_description":
        best_log = abs(math.log(z_pack)) if z_pack > 0 else float("inf")
        if _reject_match(best_log, ev["name_overlap"], ev["sku_in_name"]):
            ev["reason"] = _reject_reason(best_log, z_pack, None)
            ev["notes"].append("catalog match rejected; quantity kept as written")
            return result
        result["basis"] = BASIS_PIECE
        result["confidence"] = 0.9 if best_log <= MAX_ABS_LOG else 0.75
        result["pieces_used"] = _round(qty, 6)
        if pack_source == "line_description":
            ev["reason"] = (f"catalog name states no pack size; the recipe line's "
                            f"{pack_text!r} is unverifiable against the catalog price")
        elif pack_size == 1:
            ev["reason"] = f"catalog name states a single unit ({pack_text})"
        else:
            ev["reason"] = "catalog name states no pack size; priced as a single unit"

        # Weak secondary signal. A small case_qty *might* also be the retail pack,
        # but in this catalog the retail pack is always written into the name and
        # case_qty is always the shipping case -- so acting on it would invent
        # doubt about ordinary single units (a $49.78 potted palm bought one at a
        # time reads as "could be a case of 6" on price alone). It is therefore
        # only allowed to speak when the single-unit reading has ALREADY failed
        # the sanity band, i.e. when we have no good explanation either way.
        if pack_size is None and hint is not None and best_log > MAX_ABS_LOG:
            hint_piece = z_pack * hint
            fit_a, fit_b = _fit(z_pack), _fit(hint_piece)
            if fit_a > fit_b:
                result["basis"] = BASIS_AMBIGUOUS
                ev["notes"].append(
                    f"the single-unit reading is {z_pack:.2f}x the era expectation, and "
                    f"case_qty {case_qty} is small enough that first_cost could instead be "
                    f"a case price ({hint_piece:.2f}x per piece). case_qty is the shipping "
                    f"case in this catalog, so no pack verdict is issued")
                ev["reason"] = ("catalog name states no pack size and the single-unit price "
                                "does not fit; case_qty leaves the basis in doubt")
        return result

    # ── two readings to choose between ───────────────────────────────────────
    z_piece = z_pack * pack_size
    ev["piece_ratio"] = _round(z_piece)
    fit_pack, fit_piece = _fit(z_pack), _fit(z_piece)
    total = fit_pack + fit_piece
    posterior_pack = 0.5 if total <= 0 else fit_pack / total
    ev["posterior_pack"] = _round(posterior_pack, 4)

    if posterior_pack >= 0.5:
        winner, z_win, confidence = BASIS_PACK, z_pack, posterior_pack
    else:
        winner, z_win, confidence = BASIS_PIECE, z_piece, 1.0 - posterior_pack
    best_log = abs(math.log(z_win)) if z_win > 0 else float("inf")
    result["confidence"] = _round(confidence, 4)

    if _reject_match(best_log, ev["name_overlap"], ev["sku_in_name"]):
        result["basis"] = BASIS_UNKNOWN
        result["confidence"] = 0.0
        result["pieces_used"] = _round(qty, 6)
        ev["reason"] = _reject_reason(best_log, z_pack, z_piece)
        ev["notes"].append("catalog match rejected; quantity kept as written")
        return result

    if confidence < MIN_CONFIDENCE:
        result["basis"] = BASIS_AMBIGUOUS
        result["pieces_used"] = _round(qty, 6)
        ev["reason"] = (f"pack reading {z_pack:.2f}x and piece reading {z_piece:.2f}x the "
                        f"era expectation are too close to separate "
                        f"(confidence {confidence:.2f} < {MIN_CONFIDENCE})")
        return result

    if best_log > MAX_ABS_LOG:
        result["basis"] = BASIS_AMBIGUOUS
        result["pieces_used"] = _round(qty, 6)
        ev["reason"] = (f"best reading ({winner}) is {z_win:.2f}x the era expectation, "
                        f"outside the factor-3 sanity band")
        return result

    if winner == BASIS_PACK and not _is_integral(qty):
        result["basis"] = BASIS_AMBIGUOUS
        result["pieces_used"] = _round(qty, 6)
        ev["reason"] = (f"cost matches the pack price ({z_pack:.2f}x era expectation) but "
                        f"quantity {qty} is not a whole number of packs")
        return result

    result["basis"] = winner
    if winner == BASIS_PACK:
        result["pieces_used"] = _round((qty * pack_size) if qty is not None else None, 6)
        ev["reason"] = (f"first_cost {cost:.2f} tracks the {pack_size}-pack price "
                        f"({z_pack:.2f}x era expectation vs {z_piece:.2f}x for a single piece)")
    else:
        result["pieces_used"] = _round(qty, 6)
        ev["reason"] = (f"first_cost {cost:.2f} tracks the single-piece price "
                        f"({z_piece:.2f}x era expectation vs {z_pack:.2f}x for the "
                        f"{pack_size}-pack)")
    return result


def _reject_match(best_log: float, overlap: float, sku_embedded: bool = False) -> bool:
    """Is the catalog match too implausible to reason from at all?"""
    if best_log > REJECT_ABS_LOG:
        return True
    if sku_embedded:
        # the name carries the SKU verbatim, so the join is corroborated
        return False
    return overlap <= 0.0 and best_log > REJECT_NO_OVERLAP_LOG


def _reject_reason(best_log: float, z_pack: float, z_piece: Optional[float]) -> str:
    readings = f"pack {z_pack:.2f}x" + (f", piece {z_piece:.2f}x" if z_piece else "")
    if best_log > REJECT_ABS_LOG:
        return (f"catalog price is irreconcilable with first_cost ({readings} the era "
                f"expectation) -- suspected supplier_sku collision")
    return (f"catalog name shares no words with the line description and the price "
            f"does not agree either ({readings}) -- suspected supplier_sku collision")


# ══════════════════════════════════════════════════════════════════════════════
# Database
# ══════════════════════════════════════════════════════════════════════════════

SELECT_SQL = """
SELECT c.id, c.recipe_id, c.line_order, c.component_label, c.vendor,
       c.supplier_sku, c.description, c.quantity, c.first_cost,
       coalesce(c.formulas, '{}'::jsonb) AS formulas,
       r.item_code, r.description AS recipe_description,
       p.supplier_sku AS catalog_sku, p.name AS catalog_name,
       p.current_price, p.case_qty, p.uom, s.name AS catalog_supplier
FROM historical_recipe_components c
JOIN historical_recipes r ON r.id = c.recipe_id
LEFT JOIN LATERAL (
    SELECT pp.* FROM products pp
    WHERE c.supplier_sku IS NOT NULL AND trim(c.supplier_sku) <> ''
      AND upper(trim(pp.supplier_sku)) = upper(trim(c.supplier_sku))
    ORDER BY pp.id
    LIMIT 1
) p ON true
LEFT JOIN suppliers s ON s.id = p.supplier_id
ORDER BY c.recipe_id, c.line_order, c.id
"""

UPDATE_SQL = f"""
UPDATE historical_recipe_components
SET formulas = coalesce(formulas, '{{}}'::jsonb)
               || jsonb_build_object('{ANALYSIS_KEY}', $2::jsonb)
WHERE id = $1
"""

PRICING_CHECKSUM_SQL = """
SELECT md5(coalesce(string_agg(
    id::text || '|' || coalesce(quantity::text,'') || '|' || coalesce(first_cost::text,'')
    || '|' || coalesce(landed_cost::text,'') || '|' || coalesce(retail::text,'')
    || '|' || coalesce(extended_total::text,''), E'\\n' ORDER BY id), ''))
FROM historical_recipe_components
"""

OTHER_FORMULAS_CHECKSUM_SQL = f"""
SELECT md5(coalesce(string_agg(
    id::text || '|' || ((coalesce(formulas,'{{}}'::jsonb)) - '{ANALYSIS_KEY}')::text,
    E'\\n' ORDER BY id), ''))
FROM historical_recipe_components
"""

RECONCILE_SQL = """
SELECT r.id, r.item_code,
       coalesce((SELECT SUM(c.extended_total) FROM historical_recipe_components c
                 WHERE c.recipe_id = r.id), 0) AS component_sum,
       (r.pricing_summary->>'component_extended_sum')::numeric AS sheet_sum
FROM historical_recipes r
ORDER BY r.id
"""


class PostconditionError(RuntimeError):
    """Raised inside the write transaction to force a rollback."""


def _canonical(block: dict[str, Any]) -> str:
    return json.dumps(block, sort_keys=True, ensure_ascii=False, default=str)


async def _snapshot(conn) -> dict[str, Any]:
    return {
        "rows": await conn.fetchval("SELECT COUNT(*) FROM historical_recipe_components"),
        "pricing": await conn.fetchval(PRICING_CHECKSUM_SQL),
        "other_formulas": await conn.fetchval(OTHER_FORMULAS_CHECKSUM_SQL),
    }


async def _reconcile(conn) -> list[tuple[int, str, float, Optional[float]]]:
    """Recipes whose component extended_total no longer matches the sheet total."""
    bad = []
    for row in await conn.fetch(RECONCILE_SQL):
        got = float(row["component_sum"] or 0)
        want = row["sheet_sum"]
        if want is None or abs(got - float(want)) > 0.01:
            bad.append((row["id"], row["item_code"], got,
                        None if want is None else float(want)))
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════

def _money(value: Any) -> str:
    f = _f(value)
    return "-" if f is None else f"{f:,.2f}"


def _qty(value: Any) -> str:
    f = _f(value)
    return "-" if f is None else (f"{f:g}")


def _cell(text: Any, width: int = 44) -> str:
    s = "" if text is None else str(text).replace("|", "/").replace("\n", " ").strip()
    return (s[: width - 1] + "…") if len(s) > width else (s or "-")


def build_report(rows: list[dict[str, Any]], *, era_factor: float,
                 measured_era: Optional[float], committed: bool) -> str:
    by_basis: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_basis.setdefault(row["analysis"]["basis"], []).append(row)

    ambiguous = by_basis.get(BASIS_AMBIGUOUS, [])
    rejected = [r for r in rows
                if "suspected supplier_sku collision" in r["analysis"]["evidence"]["reason"]]

    # SKUs whose lines disagree about their cost basis -- the Cactus case.
    per_sku: dict[str, set[str]] = {}
    for row in rows:
        a = row["analysis"]
        if a["catalog_sku"] and a["basis"] in (BASIS_PACK, BASIS_PIECE, BASIS_AMBIGUOUS):
            per_sku.setdefault(a["catalog_sku"].upper(), set()).add(a["basis"])
    conflict_skus = {sku for sku, bases in per_sku.items() if len(bases) > 1}
    conflicts = [r for r in rows
                 if (r["analysis"]["catalog_sku"] or "").upper() in conflict_skus
                 and r["analysis"]["basis"] != BASIS_UNKNOWN]
    conflicts.sort(key=lambda r: ((r["analysis"]["catalog_sku"] or "").upper(),
                                  r["analysis"]["basis"]))

    matched = sum(1 for r in rows if r["analysis"]["catalog_name"])
    out: list[str] = []
    w = out.append

    w("# Pack-vs-piece detection — lines needing a human")
    w("")
    w(f"Generated by `scripts/detect_component_packs.py` "
      f"({'committed' if committed else 'dry run'}), analysis version {VERSION}.")
    w("")
    w("## Thresholds in force")
    w("")
    w(f"| setting | value | meaning |")
    w(f"| --- | --- | --- |")
    w(f"| `ERA_FACTOR` | {era_factor} | historical `first_cost` runs at this share of "
      f"today's catalog price |")
    if measured_era is not None:
        w(f"| measured era factor | {measured_era} | median over this run's non-pack "
          f"catalog-matched lines (cross-check) |")
    w(f"| `SIGMA` | {SIGMA} | log-space spread of the era ratio |")
    w(f"| `MIN_CONFIDENCE` | {MIN_CONFIDENCE} | posterior needed for a pack/piece verdict |")
    w(f"| `MAX_ABS_LOG` | ln(3.0) | winning reading must be within a factor of 3 |")
    w(f"| `REJECT_ABS_LOG` | ln(5.0) | beyond this the catalog match is discarded |")
    w(f"| `REJECT_NO_OVERLAP_LOG` | ln(2.0) | stricter when the names share no words |")
    w("")
    w("`pack` verdicts additionally require a whole-number `quantity`. Nothing in this "
      "report changes a price: `quantity`, `first_cost`, `landed_cost`, `retail` and "
      "`extended_total` are read-only to this script.")
    w("")
    w("## Counts")
    w("")
    w("| bucket | lines |")
    w("| --- | --- |")
    w(f"| total | {len(rows)} |")
    w(f"| catalog match on `supplier_sku` | {matched} |")
    for basis in (BASIS_PACK, BASIS_PIECE, BASIS_AMBIGUOUS, BASIS_UNKNOWN):
        w(f"| {basis} | {len(by_basis.get(basis, []))} |")
    w(f"| rejected catalog match (sku collision) | {len(rejected)} |")
    w(f"| SKUs read inconsistently across recipes | {len(conflict_skus)} |")
    w("")

    def table(entries: Iterable[dict[str, Any]]) -> None:
        w("| line | recipe | description | qty | FC | catalog match | pack | "
          "pack reading | piece reading | verdict | conf | why |")
        w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in entries:
            a = row["analysis"]
            ev = a["evidence"]
            cat = (f"{a['catalog_sku'] or '-'} · {_cell(a['catalog_name'], 40)} "
                   f"@ {_money(a['catalog_price'])}") if a["catalog_name"] else "-"
            pack_read = ("-" if ev["pack_ratio"] is None
                         else f"{_money(_f(a['catalog_price']))} ×{ev['pack_ratio']}")
            piece_read = ("-" if ev["piece_ratio"] is None else
                          f"{_money((_f(a['catalog_price']) or 0) / (a['pack_size'] or 1))}"
                          f" ×{ev['piece_ratio']}")
            w(f"| {row['id']} | {_cell(row['item_code'], 18)} | "
              f"{_cell(row['description'], 34)} | {_qty(row['quantity'])} | "
              f"{_money(row['first_cost'])} | {cat} | "
              f"{a['pack_size'] or '-'} | {pack_read} | {piece_read} | "
              f"**{a['basis']}** | {a['confidence']} | {_cell(ev['reason'], 150)} |")
        w("")

    packs = sorted(by_basis.get(BASIS_PACK, []), key=lambda r: r["id"])
    w(f"## Every `pack` verdict ({len(packs)})")
    w("")
    w("These are the only lines whose `pieces_used` differs from `quantity`, so they are "
      "the whole of this run's behavioural change. Worth eyeballing all of them: a "
      "`quantity` of 1 against a multi-pack means the line bought a whole pack, which is "
      "occasionally a designer typing the case price against a single item instead.")
    w("")
    if packs:
        table(packs)
    else:
        w("_None._")
        w("")

    w(f"## Ambiguous lines ({len(ambiguous)})")
    w("")
    w("The cost basis could not be separated. `pieces_used` is left equal to `quantity` "
      "as written, which is the safe reading.")
    w("")
    if ambiguous:
        table(sorted(ambiguous, key=lambda r: (-(r["analysis"]["confidence"] or 0), r["id"])))
    else:
        w("_None._")
        w("")

    w(f"## Suspected `supplier_sku` collisions ({len(rejected)})")
    w("")
    w("`supplier_sku` is not unique across suppliers, so these joins landed on the wrong "
      "product. They were forced back to `unknown` rather than analysed. Fixing them "
      "needs a supplier-aware match, not a threshold change.")
    w("")
    if rejected:
        table(sorted(rejected, key=lambda r: r["id"]))
    else:
        w("_None._")
        w("")

    w(f"## SKUs read inconsistently ({len(conflict_skus)} SKUs, {len(conflicts)} lines)")
    w("")
    w("The same catalog product appears on different recipe lines with costs that imply "
      "different bases — the designers were not consistent. Each line's own verdict is "
      "the best available reading; listed together so a human can confirm.")
    w("")
    if conflicts:
        table(conflicts)
    else:
        w("_None._")
        w("")

    w("## Not in this report")
    w("")
    w(f"- `{len(by_basis.get(BASIS_UNKNOWN, []))}` lines are `unknown`, almost all because "
      f"their `supplier_sku` has no catalog row (or is blank, as mechanics lines usually "
      f"are). They keep `quantity` as written and need no decision.")
    w(f"- `{len(by_basis.get(BASIS_PIECE, []))}` `piece` verdicts cleared every threshold. "
      f"They leave `pieces_used == quantity`, so nothing about them changes how a recipe "
      f"reads; they are not listed individually.")
    w("")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def _load_env() -> None:
    import dotenv

    for name in (".env", ".env.dev", ".env.supabase"):
        path = BACKEND / name
        if path.exists():
            dotenv.load_dotenv(path, override=True)


def _measured_era_factor(rows: list[dict[str, Any]]) -> Optional[float]:
    """Median first_cost/current_price over catalog-matched lines with no pack size.

    Printed as a cross-check on ``ERA_FACTOR``; never used to classify, so the
    verdicts do not silently move when the catalog is repriced.
    """
    import statistics

    ratios = []
    for row in rows:
        a = row["analysis"]
        price, cost = _f(a["catalog_price"]), _f(row["first_cost"])
        if a["catalog_name"] and a["pack_size"] is None and price and cost and price > 0:
            ratios.append(cost / price)
    return round(statistics.median(ratios), 4) if len(ratios) >= 20 else None


async def run(args: argparse.Namespace) -> int:
    _load_env()
    import asyncpg

    era = args.era_factor
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    try:
        raw = await conn.fetch(SELECT_SQL)
        rows: list[dict[str, Any]] = []
        for record in raw:
            row = dict(record)
            existing = row["formulas"]
            if isinstance(existing, str):
                existing = json.loads(existing)
            row["formulas"] = existing or {}
            row["analysis"] = classify_line(
                quantity=row["quantity"],
                first_cost=row["first_cost"],
                description=row["description"],
                catalog_sku=row["catalog_sku"],
                catalog_name=row["catalog_name"],
                catalog_price=row["current_price"],
                catalog_supplier=row["catalog_supplier"],
                case_qty=row["case_qty"],
                vendor=row["vendor"],
                era_factor=era,
            )
            rows.append(row)

        measured = _measured_era_factor(rows)

        changed = [r for r in rows
                   if _canonical(r["formulas"].get(ANALYSIS_KEY) or {})
                   != _canonical(r["analysis"])]

        # ── summary ──────────────────────────────────────────────────────────
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["analysis"]["basis"]] = counts.get(row["analysis"]["basis"], 0) + 1
        matched = sum(1 for r in rows if r["analysis"]["catalog_name"])
        rejected = sum(1 for r in rows
                       if "supplier_sku collision" in r["analysis"]["evidence"]["reason"])
        with_pack = sum(1 for r in rows if r["analysis"]["pack_size"])

        mode = "COMMIT" if args.commit else "DRY RUN"
        print(f"{mode} — pack-vs-piece detection v{VERSION}")
        print(f"  era factor in use   {era}"
              + (f"   (measured this run: {measured})" if measured else ""))
        print(f"  sigma / min conf    {SIGMA} / {MIN_CONFIDENCE}")
        print()
        print(f"  {'component lines':34s} {len(rows):6d}")
        print(f"  {'catalog match on supplier_sku':34s} {matched:6d}")
        print(f"  {'  ... rejected as sku collision':34s} {rejected:6d}")
        print(f"  {'pack size resolved':34s} {with_pack:6d}")
        print()
        print("  classification:")
        for basis in (BASIS_PACK, BASIS_PIECE, BASIS_AMBIGUOUS, BASIS_UNKNOWN):
            n = counts.get(basis, 0)
            print(f"    {basis:12s} {n:6d}  {n / max(len(rows), 1):6.1%}")
        print()
        print("  pack size sources:")
        src: dict[str, int] = {}
        for row in rows:
            key = row["analysis"]["pack_size_source"] or "(none)"
            src[key] = src.get(key, 0) + 1
        for key, n in sorted(src.items(), key=lambda kv: -kv[1]):
            print(f"    {key:20s} {n:6d}")
        print()
        print(f"  rows whose pack_analysis differs from stored: {len(changed)}")

        # ── report ───────────────────────────────────────────────────────────
        report_path = Path(args.report)
        report_path.write_text(
            build_report(rows, era_factor=era, measured_era=measured,
                         committed=args.commit),
            encoding="utf-8")
        print(f"  report written: {report_path}")

        # ── write ────────────────────────────────────────────────────────────
        before = await _snapshot(conn)
        pre_bad = await _reconcile(conn)
        print()
        print(f"  pricing invariant BEFORE: "
              f"{len(pre_bad)} of 223 recipes off  ->  "
              f"{'OK' if not pre_bad else 'ALREADY BROKEN'}")

        if not args.commit:
            print()
            print("  DRY RUN — nothing written. Re-run with --commit.")
            return 0

        if not changed:
            print()
            print("  nothing to write — already up to date (idempotent no-op).")
            return 0

        try:
            async with conn.transaction():
                await conn.executemany(
                    UPDATE_SQL,
                    [(r["id"], json.dumps(r["analysis"], ensure_ascii=False, default=str))
                     for r in changed])

                after = await _snapshot(conn)
                problems: list[str] = []
                if after["rows"] != before["rows"]:
                    problems.append(f"row count changed {before['rows']} -> {after['rows']}")
                if after["pricing"] != before["pricing"]:
                    problems.append("a pricing column changed (quantity/first_cost/"
                                    "landed_cost/retail/extended_total checksum moved)")
                if after["other_formulas"] != before["other_formulas"]:
                    problems.append(f"pre-existing formulas keys changed — the merge was "
                                    f"not additive")
                post_bad = await _reconcile(conn)
                if len(post_bad) != len(pre_bad):
                    problems.append(f"{len(post_bad)} recipes no longer reconcile with "
                                    f"their sheet total")
                stored = await conn.fetchval(
                    f"SELECT COUNT(*) FROM historical_recipe_components "
                    f"WHERE formulas ? '{ANALYSIS_KEY}'")
                if stored != len(rows):
                    problems.append(f"only {stored} of {len(rows)} rows carry "
                                    f"{ANALYSIS_KEY}")
                if problems:
                    raise PostconditionError("; ".join(problems))

                print()
                print(f"  wrote {len(changed)} rows")
                print(f"  post-conditions:")
                print(f"    row count unchanged                  OK ({after['rows']})")
                print(f"    pricing columns unchanged            OK")
                print(f"    pre-existing formulas keys intact    OK")
                print(f"    all {223 - len(post_bad)}/223 recipes reconcile          OK")
                print(f"    every row carries {ANALYSIS_KEY}        OK ({stored})")
        except PostconditionError as exc:
            print()
            print(f"  ROLLED BACK — post-condition failed: {exc}", file=sys.stderr)
            return 1

        print()
        print("  COMMITTED")
        return 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", action="store_true",
                    help="write to the database (default is a dry run)")
    ap.add_argument("--era-factor", type=float, default=ERA_FACTOR,
                    help=f"historical cost as a share of today's catalog price "
                         f"(default {ERA_FACTOR})")
    ap.add_argument("--report", default=str(Path(__file__).with_name("pack_detection_report.md")),
                    help="where to write the manual-review report")
    args = ap.parse_args()
    if not 0 < args.era_factor <= 5:
        print("--era-factor must be in (0, 5]", file=sys.stderr)
        return 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
