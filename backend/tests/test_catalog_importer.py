"""Table tests pinning behavior of catalog_importer's parsing helpers,
and cross-checking them against the near-identical helpers in scraper_base.

safe_int, parse_price, normalize_unit, and normalize_category all agree with
scraper_base on every input tried here (including which inputs raise), so
catalog_importer now imports all four directly from scraper_base instead of
redefining them.
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
    """After dedup, these four are literally the same function object."""
    assert ci.parse_price is sb.parse_price
    assert ci.safe_int is sb.safe_int
    assert ci.normalize_unit is sb.normalize_unit
    assert ci.normalize_category is sb.normalize_category


# ─────────────────────────────────────────────
# normalize_category — used to diverge between the two modules (catalog_importer
# used a small hardcoded set of substring checks with no exact-match short
# circuit and no alias table; scraper_base checked VALID_CATEGORIES for an
# exact match first, then walked CATEGORY_MAP for a substring match, and
# lacked aliases for singulars like "pot"/"vase"/"tree"/"branch"/"container").
# scraper_base.normalize_category now covers every alias either version
# understood, and catalog_importer just re-exports it -- so both modules agree
# on every input below.
# ─────────────────────────────────────────────

NORMALIZE_CATEGORY_CASES = [
    (None, "other"),
    ("", "other"),
    ("   ", "other"),
    ("pot", "containers"),
    ("pots", "containers"),
    ("flowers", "florals"),
    ("florals", "florals"),
    ("vase", "vases"),
    ("vases", "vases"),
    ("tree", "trees"),
    ("trees", "trees"),
    ("christmas", "seasonal"),
    ("holiday", "seasonal"),
    ("moss", "moss"),
    ("branch", "branches"),
    ("branches", "branches"),
    ("greenery", "greenery"),
    ("foliage", "foliage"),
    ("container", "containers"),
    ("containers", "containers"),
    ("wood", "wood"),
    ("wreaths", "wreaths"),
    ("topiaries", "topiaries"),
    ("succulents", "succulents"),
    ("random unknown category", "other"),
    ("Artificial Plants", "plant"),
]


@pytest.mark.parametrize("raw, expected", NORMALIZE_CATEGORY_CASES)
def test_normalize_category_matches_scraper_base(raw, expected):
    assert ci.normalize_category(raw) == expected
    assert sb.normalize_category(raw) == expected
    assert ci.normalize_category(raw) == sb.normalize_category(raw)
