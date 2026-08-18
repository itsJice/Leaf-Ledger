#!/usr/bin/env python3
"""Prove the SQL search path answers the same questions as the in-memory index.

``/products/search`` has two implementations behind one signature:

* the **in-memory index** (``SEARCH_INDEX_ENABLED=1``, the default) — ~892 MB of
  RAM holding the whole catalog, filtered in Python. It is the *reference*: the
  answers it gives are the ones the UI has been shipping, so they are correct by
  definition;
* the **SQL path** (``SEARCH_INDEX_ENABLED=0``) — the same search answered out of
  Postgres, with a capped total.

The index has to go: it OOM-kills the web service, and every crash-restart
re-reads the whole catalog, which is what exhausted the org's egress quota. This
script is the gate on that removal — it runs a matrix of real queries through
BOTH paths against the live database and diffs everything the frontend consumes:
the total, the ordered list of product ids, the per-item payload, and every facet
dimension (values, counts and ordering).

    python scripts/check_search_parity.py                  # full matrix
    python scripts/check_search_parity.py --only browse,kw_moss
    python scripts/check_search_parity.py --json out.json  # machine-readable
    python scripts/check_search_parity.py --timing-repeat 5

Egress
======
Building the in-memory index streams the entire catalog. This script builds it
**at most once per run** and reuses that one index for every query in the matrix
— and it goes through ``products._load_search_index``, so a warm on-disk cache
from an earlier run costs nothing at all. The SQL side is cheap by comparison:
two round trips per query, a page of <=48 rows plus a capped ``COUNT``. Run
``--dry-run`` to print the matrix and the plan without touching the database.

Where the line between "acceptable" and "defect" is drawn
=========================================================
ACCEPTABLE — the two paths disagree, but the disagreement is a deliberate design
difference that the frontend already copes with:

* ``capped-total`` — the SQL path deliberately stops counting at
  ``_DB_COUNT_CAP`` and says so via ``total_is_capped``, rather than paying for a
  full scan. A reference count at or above the cap is therefore *expected* to
  come back as "cap+", and the UI renders it as "5000+". A capped total that is
  *below* the reference count, or a capped flag on a query the reference says has
  fewer rows than the cap, is NOT acceptable — that is over- or under-counting.
* ``tie-order`` — the same ids in a different order where the ordering key is
  genuinely tied (identical case-folded names). Neither order is more correct.
* ``undefined-tie-order`` — a facet reordering limited to equal counts in a
  dimension the *reference* leaves unordered (``suppliers``, built with
  ``Counter.most_common()``). There is no correct order to reproduce.

WARN — tolerable, but someone should know:

* ``ranking-order`` — same result set, different order, on a query with search
  terms *whose reference page is not plain alphabetical* — i.e. relevance really
  is what separates them. Fuzzy/relevance ranking is allowed to differ between
  implementations. If the reference page IS alphabetical, relevance is not in
  play and the difference is ``collation-order``, a defect: the frontend pages by
  offset, so a shifting order silently duplicates and skips products.
* ``payload-type`` — a field that compares equal numerically but ships a
  different JSON type (``10.5`` vs ``"10.5"``). Not wrong, but the client is
  typed and it will bite eventually.
* ``facet-truncation-boundary`` — a facet value that differs only at the 80-entry
  truncation floor, where both lists are full and the cut lands mid-tie.

DEFECT — everything else, and in particular:

* a different set of product ids (recall gap, or a filter that one path silently
  ignores);
* any facet value/count difference above the truncation floor — the sidebar is a
  promise about what is in the result set, and a wrong count is a wrong promise;
* a different browse order (breaks offset pagination), including ``collation-order``
  — Python's ``str.lower()`` sorts by codepoint, Postgres sorts under the database
  collation (``en_US.UTF-8``), which ignores leading punctuation, so the two
  disagree about where a product named ``3" Ball`` belongs;
* ``cold-start-empty-facets`` — an empty sidebar on the first request that fills
  in on the next. Separated from "facets unimplemented" so the two are not
  confused, but still a defect: it is what a user sees after every deploy;
* an exact-SKU query returning a *different* SKU. A SKU is an identifier, not a
  keyword: ``N590321-2`` must never surface ``N590321-20``.

The SKU invariant is checked on each path independently as well as compared,
because both paths currently match SKUs with a substring/``ILIKE`` test and a
substring test cannot express "this exact identifier".
"""

from __future__ import annotations

import argparse
import asyncio
from asyncio import sleep as _asyncio_sleep
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ─── Verdicts ────────────────────────────────────────────────────────────────

ACCEPTABLE = "ACCEPTABLE"
WARN = "WARN"
DEFECT = "DEFECT"

VERDICT_ORDER = {DEFECT: 0, WARN: 1, ACCEPTABLE: 2}

FACET_DIMS = (
    "categories", "colors", "sizes", "finishes",
    "availability", "suppliers", "product_types",
)

# The index truncates every facet dimension to its top 80 values.
FACET_LIMIT = 80

# Dimensions where the REFERENCE itself has no defined order for equal counts:
# search_products builds `suppliers` with Counter.most_common(), which leaves ties
# in arbitrary insertion order, while every other dimension sorts ties by value.
# Demanding the SQL path reproduce an arbitrary order would be demanding a bug.
UNORDERED_TIE_DIMS = ("suppliers",)

# Facet params the SQL path has to implement for parity; used only to explain a
# result-set difference ("this filter was ignored") in the report.
FACET_PARAMS = ("colors", "categories", "sizes", "finishes", "product_types", "availability")


@dataclass(frozen=True)
class Diff:
    """One actionable disagreement between the two paths."""
    query: str
    dimension: str
    verdict: str
    reason: str
    expected: Any = None      # what the in-memory index (reference) said
    actual: Any = None        # what the SQL path said
    note: str = ""

    def render(self) -> str:
        head = f"  [{self.verdict:10}] {self.dimension:28} {self.reason}"
        body = f"\n      expected (index): {_short(self.expected)}\n      actual   (sql)  : {_short(self.actual)}"
        tail = f"\n      → {self.note}" if self.note else ""
        return head + body + tail


def _short(value: Any, width: int = 220) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= width else text[: width - 3] + "..."


# ─── Comparison ──────────────────────────────────────────────────────────────


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _values_equal(a: Any, b: Any) -> tuple[bool, bool]:
    """(equal_by_value, same_json_type). ``10.5`` and ``"10.5"`` are equal but
    not the same type — a WARN, not a defect."""
    if a == b:
        return True, True
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None and na == nb:
        return True, False
    return False, type(a) is type(b)


def compare_total(query: str, ref: dict, cand: dict, *, cap: int) -> list[Diff]:
    ref_total = int(ref.get("total") or 0)
    cand_total = int(cand.get("total") or 0)
    capped = bool(cand.get("total_is_capped"))

    if not capped:
        if ref_total == cand_total:
            return []
        return [Diff(query, "total", DEFECT, "total-mismatch", ref_total, cand_total,
                     "Neither path reported a capped total, so these must be equal.")]

    # SQL reported a capped total.
    if ref_total < cap:
        return [Diff(query, "total", DEFECT, "capped-total-overstated", ref_total, f"{cand_total}+",
                     f"SQL says 'more than {cand_total}' but the reference has only {ref_total} "
                     f"rows — below the {cap} cap, so it should have returned an exact count.")]
    if cand_total == cap:
        return [Diff(query, "total", ACCEPTABLE, "capped-total", ref_total, f"{cand_total}+",
                     "Deliberate: SQL stops counting at the cap instead of scanning the catalog.")]
    return [Diff(query, "total", WARN, "capped-total-off-cap", ref_total, f"{cand_total}+",
                 f"Capped, and the reference is above the cap, but the cap reported ({cand_total}) "
                 f"is not _DB_COUNT_CAP ({cap}).")]


def compare_items(query: str, ref: dict, cand: dict, *, has_search: bool,
                  facet_params_used: tuple[str, ...] = (), offset: int = 0) -> list[Diff]:
    ref_items = list(ref.get("items") or [])
    cand_items = list(cand.get("items") or [])
    ref_ids = [it.get("id") for it in ref_items]
    cand_ids = [it.get("id") for it in cand_items]
    diffs: list[Diff] = []

    if ref_ids != cand_ids:
        ref_set, cand_set = set(ref_ids), set(cand_ids)
        if ref_set != cand_set:
            missing = [i for i in ref_ids if i not in cand_set]
            extra = [i for i in cand_ids if i not in ref_set]
            if extra and facet_params_used and not missing:
                reason = "filter-not-applied"
                note = ("SQL returned rows the index filtered out, and the query used "
                        f"{', '.join(facet_params_used)} — that filter looks unimplemented on the SQL path.")
            elif missing and not extra:
                reason = "recall-gap"
                note = ("SQL missed rows the index found. The index searches a flattened blob of "
                        "raw_data values; the SQL path only searches name/description/supplier_sku.")
            else:
                reason = "result-set-mismatch"
                note = "Both paths returned rows the other did not."
                # Equal-sized swaps on a page usually mean the two paths ORDER the
                # catalog differently rather than match different rows: the index
                # sorts on Python's str.lower() (codepoint order), Postgres sorts
                # under the database collation (en_US.UTF-8 ignores leading
                # punctuation), so the two disagree about which rows are on page N.
                if len(missing) == len(extra) and int(ref.get("total") or 0) >= len(ref_ids):
                    note += (" Same-sized swap: check the ORDER BY — Python str.lower() and the "
                             "database collation disagree about names starting with punctuation.")
            if offset:
                note += f" (offset={offset}: an upstream ordering difference alone can cause this.)"
            diffs.append(Diff(query, "items.ids", DEFECT, reason,
                              {"count": len(ref_ids), "missing_from_sql": missing[:8]},
                              {"count": len(cand_ids), "extra_in_sql": extra[:8]}, note))
        else:
            ref_names = [str(it.get("name") or "").lower() for it in ref_items]
            cand_names = [str(it.get("name") or "").lower() for it in cand_items]
            # Show the first position where the two orders part company — the
            # leading ids are usually identical, so a bare prefix says nothing.
            at = next(i for i, (a, b) in enumerate(zip(ref_ids, cand_ids)) if a != b)
            window = slice(at, at + 4)
            expected = {"first_differs_at": at,
                        "ids": ref_ids[window], "names": [it.get("name") for it in ref_items[window]]}
            actual = {"first_differs_at": at,
                      "ids": cand_ids[window], "names": [it.get("name") for it in cand_items[window]]}
            if ref_names == cand_names:
                diffs.append(Diff(query, "items.order", ACCEPTABLE, "tie-order", expected, actual,
                                  "Same products in the same name order; only ties between identically "
                                  "named products are broken differently."))
            elif ref_names == sorted(ref_names):
                # The reference page is in plain alphabetical order, so relevance
                # ranking is not reordering it — the two paths simply sort the same
                # names differently. That is not a tolerable ranking difference.
                diffs.append(Diff(query, "items.order", DEFECT, "collation-order", expected, actual,
                                  "The reference page is purely alphabetical, so relevance is not what "
                                  "separates these: the two paths disagree about name ORDER. The index "
                                  "sorts on Python's str.lower() (codepoint order); Postgres sorts under "
                                  "the database collation, which ignores leading punctuation — so a "
                                  "product named '3\" Ball' lands in a different place. Offset pagination "
                                  "is not stable across the two."))
            elif has_search:
                diffs.append(Diff(query, "items.order", WARN, "ranking-order", expected, actual,
                                  "Same result set, different relevance order on a keyword query. "
                                  "Tolerable, but it makes offset pagination unstable if a user pages "
                                  "while the backend flips paths."))
            else:
                diffs.append(Diff(query, "items.order", DEFECT, "browse-order", expected, actual,
                                  "Same result set, different order on an unsearched browse. The "
                                  "frontend pages by offset, so this duplicates and skips products."))

    # Payload comparison for the products both pages agree on.
    by_id = {it.get("id"): it for it in cand_items}
    scalar_bad: list[str] = []
    type_only: list[str] = []
    image_bad: list[str] = []
    for it in ref_items:
        other = by_id.get(it.get("id"))
        if other is None:
            continue
        for key in ("name", "supplier_name", "supplier_sku", "current_price"):
            equal, same_type = _values_equal(it.get(key), other.get(key))
            if not equal:
                scalar_bad.append(f"{it.get('id')}.{key}: {it.get(key)!r} != {other.get(key)!r}")
            elif not same_type:
                type_only.append(f"{it.get('id')}.{key}")
        ref_norm = ((it.get("raw_data") or {}).get("normalized") or {})
        cand_norm = ((other.get("raw_data") or {}).get("normalized") or {})
        for key in ("color", "finish", "size_in", "class"):
            equal, same_type = _values_equal(ref_norm.get(key), cand_norm.get(key))
            if not equal:
                scalar_bad.append(f"{it.get('id')}.normalized.{key}: "
                                  f"{ref_norm.get(key)!r} != {cand_norm.get(key)!r}")
            elif not same_type:
                type_only.append(f"{it.get('id')}.normalized.{key}")
        if list(it.get("image_urls") or []) != list(other.get("image_urls") or []):
            image_bad.append(str(it.get("id")))

    if scalar_bad:
        diffs.append(Diff(query, "items.payload", DEFECT, "payload-mismatch",
                          f"{len(scalar_bad)} field(s) differ", scalar_bad[:6],
                          "The same product ships different values from the two paths."))
    if type_only:
        diffs.append(Diff(query, "items.payload", WARN, "payload-type",
                          "same value", type_only[:6],
                          "Equal numerically but a different JSON type (e.g. 10.5 vs \"10.5\"). "
                          "The index coerces normalized sizes to float; the SQL path passes the "
                          "raw JSON through."))
    if image_bad:
        diffs.append(Diff(query, "items.image_urls", WARN, "image-list",
                          "index candidate list", image_bad[:6],
                          "Candidate image lists differ (order or depth). Cosmetic: the card falls "
                          "back URL→URL, but the first image is what the user sees."))
    return diffs


def _facet_pairs(entries) -> list[tuple[Any, int]]:
    return [(e.get("value"), int(e.get("count") or 0)) for e in (entries or [])]


def compare_facets(query: str, ref: dict, cand: dict) -> list[Diff]:
    ref_f, cand_f = ref.get("facets"), cand.get("facets")
    if ref_f is None and cand_f is None:
        return []
    if ref_f is not None and cand_f is None:
        return [Diff(query, "facets", DEFECT, "facets-absent", sorted(ref_f), None,
                     "The index built facets for this request and the SQL path returned none. "
                     "Facets are only built at offset<=0 — both paths must agree on that too.")]
    if ref_f is None and cand_f is not None:
        return [Diff(query, "facets", WARN, "facets-unexpected", None, sorted(cand_f),
                     "SQL built facets on a page the index skipped (offset>0). Harmless to the UI, "
                     "but it is paying for work the reference does not.")]

    diffs: list[Diff] = []
    for dim in FACET_DIMS:
        ref_list = _facet_pairs(ref_f.get(dim))
        cand_list = _facet_pairs(cand_f.get(dim))
        if ref_list == cand_list:
            continue
        ref_map, cand_map = dict(ref_list), dict(cand_list)

        if ref_list and not cand_list:
            diffs.append(Diff(query, f"facets.{dim}", DEFECT, "facet-not-implemented",
                              ref_list[:5], [],
                              f"The SQL path returns an empty {dim} facet. The sidebar would show "
                              f"no {dim} at all."))
            continue
        if cand_list and not ref_list:
            diffs.append(Diff(query, f"facets.{dim}", DEFECT, "facet-unexpected", [], cand_list[:5],
                              "SQL offered facet values the reference says are not in this result set."))
            continue

        # Both lists full → the 80-entry cut can legitimately land mid-tie.
        truncated = len(ref_list) >= FACET_LIMIT or len(cand_list) >= FACET_LIMIT
        floor = 0
        if truncated:
            floor = max(min(c for _, c in ref_list), min(c for _, c in cand_list))

        missing = [v for v, _ in ref_list if v not in cand_map]
        extra = [v for v, _ in cand_list if v not in ref_map]
        if missing or extra:
            at_floor = all(ref_map.get(v, cand_map.get(v, 0)) <= floor for v in missing + extra)
            verdict = WARN if (truncated and at_floor) else DEFECT
            reason = "facet-truncation-boundary" if verdict == WARN else "facet-values"
            note = ("Both lists are at the 80-value cap and the differing values sit on the "
                    "truncation floor — a tie broken differently, not a missing value."
                    if verdict == WARN else
                    "The sidebar offers a different set of values, so a user sees (or cannot see) "
                    "filters the other path has.")
            diffs.append(Diff(query, f"facets.{dim}", verdict, reason,
                              {"missing_from_sql": missing[:8]}, {"extra_in_sql": extra[:8]}, note))

        bad_counts = [
            f"{v}: {ref_map[v]} != {cand_map[v]}"
            for v, _ in ref_list if v in cand_map and ref_map[v] != cand_map[v]
        ]
        if bad_counts:
            diffs.append(Diff(query, f"facets.{dim}", DEFECT, "facet-counts",
                              f"{len(bad_counts)} value(s)", bad_counts[:6],
                              "A facet count is a promise about how many products the user gets if "
                              "they click it. Drill-down semantics: each dimension is counted "
                              "ignoring its OWN selection while every other filter applies."))

        if not missing and not extra and not bad_counts:
            ref_order = [v for v, _ in ref_list]
            cand_order = [v for v, _ in cand_list]
            if ref_order != cand_order:
                at = next(i for i, (a, b) in enumerate(zip(ref_order, cand_order)) if a != b)
                window = slice(at, at + 4)
                expected = {"first_differs_at": at, "values": ref_list[window]}
                actual = {"first_differs_at": at, "values": cand_list[window]}
                # Only equal-count entries swapped?
                ties_only = [c for _, c in ref_list] == [c for _, c in cand_list]
                if ties_only and dim in UNORDERED_TIE_DIMS:
                    diffs.append(Diff(query, f"facets.{dim}", ACCEPTABLE, "undefined-tie-order",
                                      expected, actual,
                                      "Equal counts, different order — but the REFERENCE has no "
                                      "tie-break here: it builds this dimension with "
                                      "Counter.most_common(), which leaves equal counts in arbitrary "
                                      "insertion order. There is nothing for the SQL path to match, "
                                      "and sorting by name (as it does) is the better behaviour. Not a "
                                      "blocker; worth giving the index a real tie-break if the two are "
                                      "ever meant to be byte-identical."))
                else:
                    diffs.append(Diff(query, f"facets.{dim}", DEFECT, "facet-order", expected, actual,
                                      "Same values and counts in a different order. Every other "
                                      "dimension breaks count ties with the value itself, so the order "
                                      "is fully determined — a difference reshuffles the sidebar."))
    return diffs


def compare_responses(query: str, ref: dict, cand: dict, *, cap: int, has_search: bool = False,
                      facet_params_used: tuple[str, ...] = (), offset: int = 0) -> list[Diff]:
    """Every actionable difference between the reference (index) and candidate (SQL)."""
    return [
        *compare_total(query, ref, cand, cap=cap),
        *compare_items(query, ref, cand, has_search=has_search,
                       facet_params_used=facet_params_used, offset=offset),
        *compare_facets(query, ref, cand),
    ]


# ─── SKU invariant ───────────────────────────────────────────────────────────


def sku_buckets(sku_query: str, resp: dict) -> dict[str, list[int]]:
    """Split a page of results for an exact-SKU query into three buckets.

    ``exact``       — supplier_sku *is* the queried identifier. The only rows a
                      SKU lookup should ever return.
    ``superstring`` — supplier_sku merely *contains* it (``N590321-20`` for a
                      search of ``N590321-2``). This is the failure the "a SKU
                      must never fuzzy-match a different SKU" rule forbids: both
                      paths match SKUs with a substring/ILIKE test, which cannot
                      express identity.
    ``other``       — matched on some other field (name, description, raw_data).
    """
    needle = (sku_query or "").strip().casefold()
    out: dict[str, list[int]] = {"exact": [], "superstring": [], "other": []}
    for item in resp.get("items") or []:
        sku = str(item.get("supplier_sku") or "").strip().casefold()
        if sku == needle:
            out["exact"].append(item.get("id"))
        elif needle and needle in sku:
            out["superstring"].append(item.get("id"))
        else:
            out["other"].append(item.get("id"))
    return out


def sku_invariant_diffs(query: str, sku: str, ref: dict, cand: dict) -> list[Diff]:
    diffs: list[Diff] = []
    ref_b, cand_b = sku_buckets(sku, ref), sku_buckets(sku, cand)
    for label, buckets in (("index", ref_b), ("sql", cand_b)):
        if buckets["superstring"]:
            diffs.append(Diff(query, f"sku.{label}", DEFECT, "sku-cross-match",
                              f"only SKUs equal to {sku!r}", buckets["superstring"][:8],
                              f"The {label} path returned products whose supplier_sku merely "
                              f"CONTAINS {sku!r}. A SKU lookup must be exact."))
    if ref_b != cand_b:
        diffs.append(Diff(query, "sku.buckets", DEFECT, "sku-parity",
                          {k: len(v) for k, v in ref_b.items()},
                          {k: len(v) for k, v in cand_b.items()},
                          "The two paths disagree about which products a SKU lookup returns."))
    return diffs


# ─── Query matrix ────────────────────────────────────────────────────────────


@dataclass
class Case:
    name: str
    params: dict = field(default_factory=dict)
    why: str = ""
    sku: Optional[str] = None          # set → also check the exact-SKU invariant

    @property
    def has_search(self) -> bool:
        return bool(self.params.get("search"))

    @property
    def facet_params_used(self) -> tuple[str, ...]:
        return tuple(p for p in FACET_PARAMS if self.params.get(p))


def build_matrix(sample: dict) -> list[Case]:
    """The matrix. ``sample`` carries real values (a supplier id, five product
    ids, a live colour/category) read out of the already-built index, so the
    filter cases exercise values that actually exist — at no extra DB cost."""
    ids_csv = ",".join(str(i) for i in sample["ids"])
    cases = [
        Case("browse", {}, "Unfiltered first page — the catalog landing view."),
        Case("browse_p2", {"offset": 48}, "Second page: pagination + the facet-skip rule (offset>0)."),
        Case("browse_deep", {"offset": 4800}, "Deep offset, near the SQL count cap."),
        Case("kw_moss", {"search": "moss"}, "Single common keyword."),
        Case("kw_fiddle", {"search": "fiddle"}, "Keyword that lives in product names."),
        Case("kw_green_wreath", {"search": "green wreath"}, "Two terms — must AND, not OR."),
        Case("sku_numeric", {"search": "124394892"}, "Exact numeric SKU.", sku="124394892"),
        Case("sku_alnum", {"search": "N590321-2"}, "Exact alphanumeric SKU with a suffix — the "
             "case where a substring match can bleed into N590321-20.", sku="N590321-2"),
        Case("price_band", {"price_min": 10, "price_max": 25}, "Price range only."),
        Case("supplier", {"supplier_ids": str(sample["supplier_id"])}, "Single supplier filter."),
        Case("ids_favorites", {"ids": ids_csv}, "Favourites-style id set."),
        Case("ids_empty", {"ids": ""}, "Empty id set: an explicit 'nothing selected', not 'no filter'."),
        Case("kw_price", {"search": "moss", "price_min": 5, "price_max": 40},
             "Keyword + price."),
        Case("kw_supplier", {"search": "wreath", "supplier_ids": str(sample["supplier_id"])},
             "Keyword + supplier."),
        Case("ids_price", {"ids": ids_csv, "price_min": 5}, "Id set + price."),
        Case("kw_moss_p2", {"search": "moss", "offset": 48}, "Keyword + pagination."),
        Case("no_match", {"search": "zzqqxnothingmatchesthis"}, "Matches nothing."),
        Case("typo", {"search": "ornamnet"}, "Misspelling — typo tolerance and its ranking."),
    ]
    if sample.get("color"):
        cases.append(Case("facet_color", {"colors": sample["color"]},
                          "Colour facet filter (index-only until the SQL path implements it)."))
    if sample.get("category"):
        cases.append(Case("facet_combo", {"categories": sample["category"], "price_max": 100},
                          "Category facet + price — drill-down counts must ignore the category "
                          "selection while still respecting the price filter."))
    return cases


# ─── Runner ──────────────────────────────────────────────────────────────────


def _sample_from_index(rows: list[dict]) -> dict:
    """Real filter values pulled from the in-memory index (no DB cost)."""
    from collections import Counter
    ids = [r["id"] for r in rows[:5000] if r.get("id") is not None][:5]
    supplier = Counter(r["supplier_id"] for r in rows if r.get("supplier_id") is not None)
    colors = Counter(c for r in rows for c in (r.get("color_families") or []))
    cats = Counter(r["category"] for r in rows if r.get("category"))
    return {
        "ids": ids,
        "supplier_id": supplier.most_common(1)[0][0] if supplier else 1,
        "color": colors.most_common(1)[0][0] if colors else None,
        "category": cats.most_common(1)[0][0] if cats else None,
    }


def cold_start_diff(first: dict, warmed: dict) -> list[Diff]:
    """The SQL path fills its unfiltered-facet cache in the background, so the
    FIRST browse after a process start can answer with an empty sidebar and a
    later one is fully populated. That is not "facets are unimplemented" — it is a
    warm-up window, and conflating the two would bury the real gaps. It still gets
    reported: on the catalog landing page, an empty sidebar is what a user sees
    after every deploy or restart.
    """
    empty_now = [d for d in FACET_DIMS if not (first.get("facets") or {}).get(d)]
    empty_later = [d for d in FACET_DIMS if not (warmed.get("facets") or {}).get(d)]
    filled = [d for d in empty_now if d not in empty_later]
    if not filled:
        return []
    return [Diff("cold_start", "facets", DEFECT, "cold-start-empty-facets",
                 "a populated sidebar on the first request", f"{len(filled)} empty dimension(s): {filled}",
                 "The first unfiltered browse after a process start returns an empty sidebar; a later "
                 "identical request returns full facets. Users hitting the catalog right after a deploy "
                 "get no filters at all. The in-memory index has the same class of warm-up problem, so "
                 "this is not a regression — but it is not parity either.")]


async def _timed(fn: Callable, *args, **kwargs) -> tuple[Any, float]:
    start = time.perf_counter()
    result = await fn(*args, **kwargs)
    return result, time.perf_counter() - start


async def run_matrix(args) -> int:
    import dotenv
    dotenv.load_dotenv(".env.supabase", override=True)
    from app.apis import products  # imported late: it reads DATABASE_URL at import time

    if not products.DATABASE_URL:
        print("DATABASE_URL is not set (looked in .env.supabase).", file=sys.stderr)
        return 2

    cap = products._DB_COUNT_CAP

    # ── Build the reference index ONCE. _load_search_index prefers a warm
    # on-disk cache, so a repeat run reads nothing from the catalog at all.
    products._INDEX_ENABLED = True
    disk = products._disk_cache_path()
    had_disk_cache = os.path.exists(disk)
    state = "present — no catalog read" if had_disk_cache else "ABSENT — this run streams the catalog once"
    print(f"index disk cache: {disk} ({state})")
    conn = await products.get_conn()
    try:
        rows, build_s = await _timed(products._load_search_index, conn)
    finally:
        await conn.close()
    index_bytes = os.path.getsize(disk) if os.path.exists(disk) else 0
    print(f"reference index ready: {len(rows):,} rows in {build_s:.1f}s "
          f"(on-disk gzip {index_bytes / 1e6:.1f} MB)")

    # The reference is only a reference while it matches the live catalog. A
    # cached index survives up to SEARCH_INDEX_TTL, and one mid-day import is
    # enough to make every facet count differ — a run against a stale reference
    # once reported 14 phantom "defects" that were really 129 newly imported
    # products the index had not seen. One COUNT(*) is cheap insurance.
    conn = await products.get_conn()
    try:
        live = await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_active = TRUE")
    finally:
        await conn.close()
    if live != len(rows):
        print(f"\n{'!' * 78}\n"
              f"!! STALE REFERENCE: the index holds {len(rows):,} rows but the live catalog\n"
              f"!! has {live:,}. The catalog changed after the cached index was built, so\n"
              f"!! facet/total mismatches below are the INDEX being out of date, not SQL\n"
              f"!! defects. Delete {disk}\n"
              f"!! and re-run to compare against a fresh reference.\n{'!' * 78}\n")
    else:
        print("reference freshness: index rows == live catalog rows\n")

    sample = _sample_from_index(rows)
    cases = build_matrix(sample)
    if args.only:
        wanted = {n.strip() for n in args.only.split(",") if n.strip()}
        cases = [c for c in cases if c.name in wanted]
        if not cases:
            print(f"no cases matched --only {args.only}", file=sys.stderr)
            return 2

    async def run_index(case: Case) -> dict:
        products._INDEX_ENABLED = True          # _index_ready() consults this
        return await products.search_products(**case.params)

    async def run_sql(case: Case) -> dict:
        products._INDEX_ENABLED = False         # → _index_ready() False, and
        return await products.search_products(**case.params)   # _ensure_index_building() no-ops

    all_diffs: list[Diff] = []
    timings: dict[str, list[float]] = {}
    results: list[dict] = []

    # Warm the SQL path's lazy caches first, so the matrix compares steady state
    # rather than a warm-up window — and report that window separately.
    browse = Case("warmup", {})
    first = await run_sql(browse)
    for _ in range(4):
        await _asyncio_sleep(2)
        warmed = await run_sql(browse)
        if all((warmed.get("facets") or {}).get(d) for d in FACET_DIMS):
            break
    cold = cold_start_diff(first, warmed)
    all_diffs += cold
    for d in cold:
        print(d.render())
    if cold:
        print()

    for case in cases:
        ref, ref_s = await _timed(run_index, case)
        cand, cand_s = await _timed(run_sql, case)
        timings.setdefault(case.name, []).append(cand_s)

        diffs = compare_responses(
            case.name, ref, cand, cap=cap, has_search=case.has_search,
            facet_params_used=case.facet_params_used, offset=int(case.params.get("offset") or 0),
        )
        if case.sku:
            diffs += sku_invariant_diffs(case.name, case.sku, ref, cand)
        all_diffs += diffs

        worst = min((VERDICT_ORDER[d.verdict] for d in diffs), default=3)
        badge = {0: "DEFECT", 1: "warn", 2: "ok (acceptable diffs)", 3: "MATCH"}[worst]
        print(f"{case.name:16} {badge:22} index {ref['total']:>7} in {ref_s * 1000:6.0f}ms | "
              f"sql {cand.get('total'):>7}{'+' if cand.get('total_is_capped') else ' '} "
              f"in {cand_s:5.1f}s | {len(diffs)} diff(s)")
        for d in sorted(diffs, key=lambda d: VERDICT_ORDER[d.verdict]):
            print(d.render())
        results.append({
            "case": case.name, "params": case.params, "why": case.why,
            "index": {"total": ref.get("total"), "ids": [i["id"] for i in ref.get("items") or []]},
            "sql": {"total": cand.get("total"), "total_is_capped": cand.get("total_is_capped"),
                    "ids": [i["id"] for i in cand.get("items") or []]},
            "diffs": [asdict(d) for d in diffs],
            "index_seconds": round(ref_s, 3), "sql_seconds": round(cand_s, 3),
        })

    # ── Timing: this instance is wildly variable, so medians over repeats.
    if args.timing_repeat > 1:
        print(f"\ntiming: {args.timing_repeat} runs of the SQL path on representative queries "
              f"(medians; a single slow run means nothing here)")
        for name in ("browse", "kw_moss", "sku_numeric"):
            case = next((c for c in cases if c.name == name), None)
            if case is None:
                continue
            for _ in range(args.timing_repeat - 1):
                _, secs = await _timed(run_sql, case)
                timings[name].append(secs)
            samples = timings[name]
            print(f"  {name:16} median {statistics.median(samples):5.1f}s  "
                  f"min {min(samples):5.1f}s  max {max(samples):5.1f}s  (n={len(samples)})")

    # ── Summary
    counts = {v: sum(1 for d in all_diffs if d.verdict == v) for v in (DEFECT, WARN, ACCEPTABLE)}
    print("\n" + "=" * 78)
    print(f"{len(cases)} queries × 2 paths — "
          f"{counts[DEFECT]} defect(s), {counts[WARN]} warning(s), "
          f"{counts[ACCEPTABLE]} acceptable difference(s)")
    if counts[DEFECT]:
        print("\nDefects by reason:")
        for reason in sorted({d.reason for d in all_diffs if d.verdict == DEFECT}):
            hits = [d for d in all_diffs if d.verdict == DEFECT and d.reason == reason]
            print(f"  {reason:28} {len(hits):3}  ({', '.join(sorted({h.query for h in hits}))})")
        print("\nVERDICT: the SQL path is NOT safe to make the default yet.")
    else:
        print("\nVERDICT: no defects — the SQL path matches the reference on this matrix.")
    print("=" * 78)

    if args.json:
        Path(args.json).write_text(json.dumps({
            "cap": cap, "index_rows": len(rows), "index_build_seconds": round(build_s, 1),
            "index_disk_bytes": index_bytes, "had_disk_cache": had_disk_cache,
            "summary": counts, "cases": results,
        }, indent=2, default=str))
        print(f"wrote {args.json}")
    return 1 if counts[DEFECT] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated case names to run")
    parser.add_argument("--json", help="write the full result to this path")
    parser.add_argument("--timing-repeat", type=int, default=3,
                        help="runs per timed query (medians; 1 disables the timing pass)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the matrix and the plan without touching the database")
    args = parser.parse_args()

    if args.dry_run:
        sample = {"ids": [1, 2, 3, 4, 5], "supplier_id": 1, "color": "Green", "category": "Home Décor"}
        cases = build_matrix(sample)
        print(f"{len(cases)} cases (sample values are placeholders in --dry-run):\n")
        for case in cases:
            print(f"  {case.name:16} {json.dumps(case.params):58} {case.why}")
        print("\nCost: one in-memory index build (whole catalog, reused for every case, and "
              "skipped entirely if a warm on-disk cache exists) + 2 SQL round trips per case.")
        return 0
    return asyncio.run(run_matrix(args))


if __name__ == "__main__":
    raise SystemExit(main())
