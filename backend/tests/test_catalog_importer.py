"""Table tests pinning behavior of catalog_importer's parsing helpers,
and cross-checking them against the near-identical helpers in scraper_base.

safe_int, parse_price, and normalize_unit agree with scraper_base on every
input tried here (including which inputs raise), so catalog_importer now
imports those three directly from scraper_base instead of redefining them.
normalize_category diverges (different category buckets / no CATEGORY_MAP),
so both versions are kept; this file pins that divergence too.
"""

import pytest

from app.libs import catalog_importer as ci
from app.libs import scraper_base as sb


# ─────────────────────────────────────────────
# parse_price — identical in both modules
# ─────────────────────────────────────────────

PARSE_PRICE_CASES = [
    (None, None),
    ("", None),
    ("   ", None),
    ("$1,234.50", 1234.5),
    ("1234", 1234.0),
    ("12.5 ea", 12.5),
    ("N/A", None),
    ("-5", 5.0),
    ("-5.5", 5.5),
    ("0", 0.0),
    ("0.0", 0.0),
    ("$0", 0.0),
    ("abc", None),
    ("  $12.00  ", 12.0),
    ("3.14159", 3.14159),
]


@pytest.mark.parametrize("raw, expected", PARSE_PRICE_CASES)
def test_parse_price_matches_scraper_base(raw, expected):
    assert ci.parse_price(raw) == expected
    assert sb.parse_price(raw) == expected
    assert ci.parse_price(raw) == sb.parse_price(raw)


# ─────────────────────────────────────────────
# safe_int — identical in both modules
# ─────────────────────────────────────────────

SAFE_INT_CASES = [
    (None, None),
    ("", None),
    ("   ", None),
    ("1234", 1234),
    ("12.5", None),
    ("-5", -5),
    ("-5.5", None),
    ("0", 0),
    ("abc", None),
    ("  42  ", 42),
    (42, 42),
    (42.9, None),
    ([1, 2], None),
    ("N/A", None),
    ("1e3", None),
]


@pytest.mark.parametrize("raw, expected", SAFE_INT_CASES)
def test_safe_int_matches_scraper_base(raw, expected):
    assert ci.safe_int(raw) == expected
    assert sb.safe_int(raw) == expected
    assert ci.safe_int(raw) == sb.safe_int(raw)


# ─────────────────────────────────────────────
# normalize_unit — identical in both modules
# ─────────────────────────────────────────────

NORMALIZE_UNIT_CASES = [
    (None, "each"),
    ("", "each"),
    ("   ", "each"),
    ("EA", "each"),
    ("each", "each"),
    ("Dz", "each"),  # not a recognized unit or substring match -> falls back to "each"
    ("dozen", "each"),
    ("case", "case"),
    ("pk", "each"),  # not a recognized abbreviation -> falls back to "each"
    ("pack", "each"),
    ("BOX", "box"),
    ("Bunch", "bunch"),
    ("bundle", "bunch"),
    ("stem", "stem"),
    ("STEMS", "stem"),
    ("clear", "each"),  # contains "ea" as a substring of "clear", not a real unit
]


@pytest.mark.parametrize("raw, expected", NORMALIZE_UNIT_CASES)
def test_normalize_unit_matches_scraper_base(raw, expected):
    assert ci.normalize_unit(raw) == expected
    assert sb.normalize_unit(raw) == expected
    assert ci.normalize_unit(raw) == sb.normalize_unit(raw)


def test_catalog_importer_reexports_scraper_base_implementations():
    """After dedup, these three are literally the same function object."""
    assert ci.parse_price is sb.parse_price
    assert ci.safe_int is sb.safe_int
    assert ci.normalize_unit is sb.normalize_unit


# ─────────────────────────────────────────────
# normalize_category — DIVERGES between the two modules; both are kept.
#
# catalog_importer uses a small hardcoded set of substring checks with no
# exact-match short circuit and no alias table. scraper_base checks
# VALID_CATEGORIES for an exact match first, then walks CATEGORY_MAP for a
# substring match. The two disagree on singular aliases like "pot"/"vase"/
# "tree"/"branch"/"container" and on categories catalog_importer doesn't
# know about at all (wood, wreaths, topiaries, succulents, "artificial
# plants" style multi-word aliases).
# ─────────────────────────────────────────────

NORMALIZE_CATEGORY_CASES = [
    # (raw, catalog_importer expected, scraper_base expected)
    (None, "other", "other"),
    ("", "other", "other"),
    ("   ", "other", "other"),
    ("pot", "containers", "other"),  # DIFFERS
    ("pots", "containers", "containers"),
    ("flowers", "florals", "florals"),
    ("florals", "florals", "florals"),
    ("vase", "containers", "other"),  # DIFFERS
    ("vases", "containers", "vases"),  # DIFFERS (different bucket name)
    ("tree", "trees", "other"),  # DIFFERS
    ("trees", "trees", "trees"),
    ("christmas", "seasonal", "seasonal"),
    ("holiday", "seasonal", "seasonal"),
    ("moss", "moss", "moss"),
    ("branch", "branches", "other"),  # DIFFERS
    ("branches", "branches", "branches"),
    ("greenery", "greenery", "greenery"),
    ("foliage", "greenery", "foliage"),  # DIFFERS (different bucket name)
    ("container", "containers", "container"),  # DIFFERS (different bucket name)
    ("containers", "containers", "containers"),
    ("wood", "other", "wood"),  # DIFFERS
    ("wreaths", "other", "wreaths"),  # DIFFERS
    ("topiaries", "other", "topiaries"),  # DIFFERS
    ("succulents", "other", "succulents"),  # DIFFERS
    ("random unknown category", "other", "other"),
    ("Artificial Plants", "other", "plant"),  # DIFFERS
]


@pytest.mark.parametrize("raw, ci_expected, sb_expected", NORMALIZE_CATEGORY_CASES)
def test_normalize_category_pinned_per_module(raw, ci_expected, sb_expected):
    assert ci.normalize_category(raw) == ci_expected
    assert sb.normalize_category(raw) == sb_expected


def test_normalize_category_kept_separate_not_reexported():
    """Unlike the other three helpers, normalize_category must stay distinct."""
    assert ci.normalize_category is not sb.normalize_category
