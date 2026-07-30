"""Unit tests for the per-line pack-vs-piece detector.

Every test here is pure: no database, no network, no worksheet corpus. The
numeric expectations come from lines the user hand-verified in the real corpus
(the ``4" Green Succulent Stem 6/pk`` conflict, the ``19" Green Boston Fern
3/pk``, the DFW glass ``p/c`` cartons), so a threshold regression fails loudly
instead of quietly re-reading the history.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "detect_component_packs.py"


def _load_module():
    """Import the script by path -- ``scripts/`` is not a package."""
    spec = importlib.util.spec_from_file_location("detect_component_packs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = _load_module()


# ══════════════════════════════════════════════════════════════════════════════
# Pack-size parser
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("name,expected", [
    ('4" Green Succulent Stem 6/pk', 6),
    ('19" Green Boston Fern Bush 24 Lvs 3/pk', 3),
    ('13" Green Succulent Spray 2/Pk', 2),
    ('11" Aeonium Spray-Green 3/pk', 3),
    ('17" Green Ivy Bush 101Lvs 3/Pk', 3),
    ('8" Green Springtime Pick 3/Pk', 3),
    ('5.5" Limestone Drop 4 Finish Asst 8/Bx', 8),
    ('3" Purple Matte Ball 32/Bx', 32),
    ('4.75" Midnight Blue Iced Ball Orn 4/Box', 4),
    ('27" Brown Lotus Pod 4/Bag', 4),
    ('2.75" Juniper Shiny Ball UV Drill 12/Bag', 12),
    ('37" Red Wavy Twig Glitter Spray 6/Bg', 6),
    ('19.5" Brown Wheat 3/Bundle', 3),
    ('44" Dark Brown Reed Spry 2/Bndle', 2),
    ('60-72" Navy Uva Palm Spray 10/Bunch', 10),
    ('3"-5"-7" Silver Glitter Oval Tree 3/Set', 3),
    ('7.5"MR & MRS PLAID MOUSE(2/ST)', 2),
    ('4-6" Natural Sponge Mushroom 24/tray', 24),
    ('20-24" Bleached Ninja 10/Pack', 10),
    ('Tree (Set of 2) 9"H, 11"H Resin', 2),
    ('Mini Tree (Set of 3) 4.5”H Plastic/PVC', 3),
    ('Pumpkin Stack Votive - Set of 3', 3),
    ('MINI CARDINAL 3.5", BOX OF 12,ACETATE', 12),
    ('Ornament (Box of 22) 2"H - 7"H Plastic', 22),
    ('Pack of 3 Fisherman Core Sardine Sponges 2x5.5', 3),
    # glass trade: N pieces per carton, and current_price is the carton
    ('Cylinder Glass Vase 8" x 24", 4 p/c', 4),
    ('Bubble Bowl Glass Vase 4" x 5", 12 p/c', 12),
    ('Cylinder Glass Vase 5" x 16", 6 p/c', 6),
    # an explicit single unit is a real answer, not a missing one
    ('8" Coral Matte Glitter Swirl Ball 1/Bx', 1),
])
def test_parses_real_pack_sizes(name, expected):
    assert pack.parse_pack_size(name)[0] == expected


@pytest.mark.parametrize("name", [
    # X# is parts-per-plant (blooms / leaves / fronds), NOT a pack. These SKUs
    # are all uom = 'EA' in the catalog.
    'Phalaenopsis x7 33.5"',
    '27" Yucca Spray X60',
    '27" Fiddle Leaf Plant X3',
    'ORCHID PHALAENOPSIS X12 44\'\' (TWO-T',
    'AGAVE PLANT X15, 16", PE, GREEN',
    'LEATHER FERN BUSH X7, 34", 34 LEAVES, GREEN',
    'SCHEFFLERA-MINI X15/641 LVS',
    '14 Inch Artificial Variegated Pothos Bush x 9',
    'MINI ECHEVERIA X24, 6.5"X4.5", 7.5" ROSETTE, PE, GREEN/BURGUNDY',
    # dimensions, not multipliers
    'Zinc 20"X12"X12"',
    'Hard Mapple 1-2"X 6\'',
    'Zinc 15.7"X15.7"X15.7"',
    'Snowman Divided Tray 15"L x 9.5"W x 1"H Wood',
    'CBR1444WT - White Glossy Long Flat Rectangle - 14"x4"x4"',
    'STONE GROOVED POT 5"X5.7"D',
    'Long glass 24"X4"X4',
    # shipping cases and assortment counts are not retail packs
    '8-12" Nectarine Repens Nat Stem 180/Cs',
    '3-4" Natural Sora Pods 250/Bulk Case',
    '7.5"EGG (12/CARTON BOX)GR/TT',
    '14" REGAL NUTCRACKER 2/AST',
    '6" Lime Pearl Sequin Ball Orn 4/Asst',
    '15"/24"/30" Silver Cone Tree 3/Assorted',
    '4" Silver Glitter Snowflake 24/Pvc Box',
    # fractions and bare numbers must not be mistaken for packs
    '1/2" Satin Ribbon',
    '3/4 Inch Dowel',
    'Dragonwood 12-14\' / 3-4\'\'',
    # plain names
    '10.5" Gray Tillandsia Pick',
    '61 Inch PVC Onion Grass Bush',
    None,
    '',
])
def test_rejects_non_pack_patterns(name):
    assert pack.parse_pack_size(name) == (None, None)


def test_x_pattern_is_detected_for_the_evidence_trail_only():
    assert pack.find_x_pattern('Phalaenopsis x7 33.5"') == "X7"
    assert pack.find_x_pattern('27" Yucca Spray X60') == "X60"
    assert pack.find_x_pattern('AGAVE PLANT X15, 16", PE, GREEN') == "X15"
    assert pack.find_x_pattern('14 Inch Pothos Bush x 9') == "X9"
    # ...and it never becomes a pack size
    assert pack.parse_pack_size('27" Yucca Spray X60')[0] is None


def test_x_pattern_ignores_dimension_strings():
    for name in ('Zinc 20"X12"X12"', 'Hard Mapple 1-2"X 6\'',
                 'Snowman Divided Tray 15"L x 9.5"W x 1"H Wood',
                 'STONE GROOVED POT 5"X5.7"D'):
        assert pack.find_x_pattern(name) is None, name


def test_loose_parser_reads_the_hand_typed_line_form():
    # a real recipe line: mechanics bought as a 6-bag of foam balls
    assert pack.parse_pack_size_loose("3.9'' Smooth Foam Ball  6bag")[0] == 6
    # but the loose form is never applied to catalog names, where it would
    # collide with dimensions -- verify the strict parser still refuses it
    assert pack.parse_pack_size("3.9'' Smooth Foam Ball  6bag")[0] is None


def test_loose_parser_still_refuses_dimensions_and_x_patterns():
    assert pack.parse_pack_size_loose('Zinc 20"X12"X12"')[0] is None
    assert pack.parse_pack_size_loose('27" Fiddle Leaf Plant X3')[0] is None
    assert pack.parse_pack_size_loose('61 Inch PVC Onion Grass Bush')[0] is None


def test_pack_size_bounds():
    assert pack.parse_pack_size("Widget 0/pk")[0] is None
    assert pack.parse_pack_size("Widget 500/bag")[0] == 500
    assert pack.parse_pack_size("Widget 501/bag")[0] is None


def test_case_qty_is_never_treated_as_a_retail_pack():
    # the shipping-case sizes the user called out explicitly
    for value in (32, 36, 48, 80, 60, 72, 144, 160):
        assert pack.case_qty_pack_hint(value) is None, value
    # small values are only ever a *hint*
    assert pack.case_qty_pack_hint(6) == 6
    assert pack.case_qty_pack_hint(12) == 12
    assert pack.case_qty_pack_hint(1) is None
    assert pack.case_qty_pack_hint(None) is None


# ══════════════════════════════════════════════════════════════════════════════
# Classifier — the hand-verified corpus cases
# ══════════════════════════════════════════════════════════════════════════════

def _classify(**kw):
    return pack.classify_line(**kw)


def test_cactus_pack_reading():
    """`Cactus` FC 12.34 against a 6/pk costing 11.14 -- one whole pack."""
    out = _classify(quantity=2, first_cost=12.34, description="Cactus",
                    catalog_sku="FA170501",
                    catalog_name='4" Green Succulent Stem 6/pk',
                    catalog_price=11.14, case_qty=36)
    assert out["basis"] == "pack"
    assert out["pack_size"] == 6
    assert out["pieces_used"] == 12
    assert out["confidence"] > 0.95


def test_cactus_piece_reading_same_sku():
    """The same SKU at FC 2.05 -- a single stem. This is the conflict case."""
    out = _classify(quantity=2, first_cost=2.05, description='4" Cactus - Green',
                    catalog_sku="FA170501",
                    catalog_name='4" Green Succulent Stem 6/pk',
                    catalog_price=11.14, case_qty=36)
    assert out["basis"] == "piece"
    assert out["pack_size"] == 6
    assert out["pieces_used"] == 2
    assert out["confidence"] > 0.95


def test_boston_fern_is_one_fern_not_a_three_pack():
    out = _classify(quantity=1, first_cost=3.89, description='18" Green Boston Fern',
                    catalog_sku="FA190618",
                    catalog_name='19" Green Boston Fern Bush 24 Lvs 3/pk',
                    catalog_price=12.08, case_qty=72)
    assert out["basis"] == "piece"
    assert out["pieces_used"] == 1


def test_glass_carton_priced_per_piece():
    """DFW glass: 104.08 / 4 p/c == 26.02 exactly, so FC 26.02 is one vase."""
    out = _classify(quantity=1, first_cost=26.02,
                    description='8" Opening tall Cylinder H-24"',
                    catalog_name='Cylinder Glass Vase 8" x 24", 4 p/c',
                    catalog_price=104.08, case_qty=4)
    assert out["basis"] == "piece"
    assert out["pack_size"] == 4
    assert out["pieces_used"] == 1


def test_glass_carton_priced_per_carton():
    """Same vendor, FC == the whole carton price, so quantity is cartons."""
    out = _classify(quantity=1, first_cost=34.88, description="Bubble Bowl",
                    catalog_name='Bubble Bowl Glass Vase 5.5" x 6", 8 p/c',
                    catalog_price=34.88, case_qty=8)
    assert out["basis"] == "pack"
    assert out["pack_size"] == 8
    assert out["pieces_used"] == 8


def test_fractional_quantity_never_yields_a_pack_verdict():
    """0.25 of a 3-pack is not a real piece count -- stay ambiguous."""
    out = _classify(quantity=0.25, first_cost=4.31,
                    description='17" Green Ivy Real Tch',
                    catalog_name='17" Green Ivy Bush 101Lvs 3/Pk',
                    catalog_price=10.01, case_qty=32)
    assert out["basis"] == "ambiguous"
    assert out["pieces_used"] == 0.25
    assert "not a whole number of packs" in out["evidence"]["reason"]


def test_two_pack_readings_that_cannot_be_separated_are_ambiguous():
    """A 2-pack whose FC sits between the two readings must not be guessed."""
    out = _classify(quantity=1, first_cost=5.55, description="Magnolia Leaf Stem",
                    catalog_name='Tree (Set of 2) 9"H, 11"H Resin',
                    catalog_price=13.50)
    assert out["basis"] == "ambiguous"
    assert out["confidence"] < pack.MIN_CONFIDENCE
    assert out["pieces_used"] == 1


def test_no_pack_size_means_quantity_is_pieces():
    out = _classify(quantity=8, first_cost=12.75,
                    description='34" Fiddle Leaf Fig Spray',
                    catalog_name='34 Inch Fiddle Leaf Fig Spray (Sold By Piece) Regular',
                    catalog_price=15.90)
    assert out["basis"] == "piece"
    assert out["pack_size"] is None
    assert out["pieces_used"] == 8


def test_x_pattern_product_is_priced_per_plant_not_per_bloom():
    out = _classify(quantity=1, first_cost=26.10,
                    description="Phalaenopsis x7 33.5'' - Fuchsia",
                    catalog_name="ORCHID PHALAENOPSIS X7 33.5'' (FUSC",
                    catalog_price=40.00)
    assert out["pack_size"] is None
    assert out["basis"] == "piece"
    assert out["pieces_used"] == 1
    assert out["evidence"]["x_pattern"] == "X7"
    assert any("parts-per-unit" in n for n in out["evidence"]["notes"])


# ══════════════════════════════════════════════════════════════════════════════
# Classifier — degenerate inputs
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("kw", [
    dict(quantity=1, first_cost=None, catalog_name='4" Stem 6/pk', catalog_price=11.14),
    dict(quantity=1, first_cost=0, catalog_name='4" Stem 6/pk', catalog_price=11.14),
    dict(quantity=1, first_cost=5.0, catalog_name='4" Stem 6/pk', catalog_price=None),
    dict(quantity=1, first_cost=5.0, catalog_name='4" Stem 6/pk', catalog_price=0),
    dict(quantity=1, first_cost=5.0),  # no catalog match at all
])
def test_missing_inputs_degrade_to_unknown_keeping_quantity(kw):
    out = _classify(**kw)
    assert out["basis"] == "unknown"
    assert out["confidence"] == 0.0
    assert out["pieces_used"] == kw.get("quantity")
    assert out["evidence"]["reason"]


def test_null_quantity_is_carried_through_as_null():
    out = _classify(quantity=None, first_cost=12.34,
                    catalog_name='4" Green Succulent Stem 6/pk', catalog_price=11.14)
    assert out["pieces_used"] is None
    assert out["quantity"] is None


def test_wildly_wrong_catalog_price_rejects_the_match():
    """`Marta Pot` FC 51.00 answering to a Melrose bird-house ornament @ 10.40."""
    out = _classify(quantity=1, first_cost=51.00, description='Marta Pot  18"X16.25"',
                    catalog_sku="95078",
                    catalog_name='Bird House and Bird Bath Ornament (2 Asst) 4"H, 7.25"H Resin',
                    catalog_price=10.40)
    assert out["basis"] == "unknown"
    assert "collision" in out["evidence"]["reason"]
    assert out["pieces_used"] == 1


def test_zero_name_overlap_plus_a_disagreeing_price_rejects_the_match():
    out = _classify(quantity=5, first_cost=1.67, description="Bush of Grass",
                    catalog_name="Raffia", catalog_price=16.95)
    assert out["basis"] == "unknown"
    assert "collision" in out["evidence"]["reason"]


def test_overlap_is_fuzzy_so_misspellings_keep_their_match():
    """The corpus is full of typos; "Thilandsia" must still match Tillandsia."""
    out = _classify(quantity=1, first_cost=5.84, description="Thilandsia",
                    catalog_name='10.5" Gray Tillandsia Pick', catalog_price=6.42,
                    case_qty=36)
    assert out["basis"] == "piece"
    assert out["evidence"]["name_overlap"] > 0.0


@pytest.mark.parametrize("left,right,expected", [
    ("Echeverria", "20\" Aquarius Echeveria", True),
    ("Hard Mapple 1-2\"", "Maple Poles", True),
    ("Vicerman 22\" aloe", "Vickerman Aloe Plant", True),
    ("Succulent Spray", "Green Succulents Sprays", True),
    # near-misses that must NOT be treated as the same word
    ("Cement Planter", "Concrete Plate", False),
    ("Gallery Vase", "Gingerbread Man Ekkolight", False),
    ("Bush of Grass", "Raffia", False),
])
def test_fuzzy_overlap_boundaries(left, right, expected):
    assert (pack.name_overlap(left, right) > 0.0) is expected


def test_zero_overlap_survives_when_the_price_agrees():
    out = _classify(quantity=1, first_cost=6.60, description="Zzzqqq Widget",
                    catalog_name="Totally Different Thing", catalog_price=10.00)
    assert out["evidence"]["name_overlap"] == 0.0
    assert out["basis"] == "piece"  # 6.60/(10*0.64) = 1.03x, well inside ln(2.0)


def test_sku_embedded_in_the_catalog_name_suppresses_the_overlap_rejection():
    """`CBR1444WT - White Glossy Long Flat Rectangle` is certainly the right row."""
    out = _classify(quantity=1, first_cost=5.00,
                    description="Rectangular white container",
                    catalog_sku="CBR1444WT",
                    catalog_name="CBR1444WT - White Glossy Long Flat Rectangle - 14\"x4\"x4\"",
                    catalog_price=26.75)
    assert out["evidence"]["sku_in_name"] is True
    assert out["basis"] != "unknown"
    assert "collision" not in out["evidence"]["reason"]


def test_sku_in_name_needs_a_meaningful_sku():
    assert pack.sku_in_name("CBR1444WT", 'CBR1444WT - White Glossy Rectangle') is True
    assert pack.sku_in_name("ABC", "ABCDEF Widget") is False       # too short to trust
    assert pack.sku_in_name("95078", 'Tree (Set of 2) 9"H') is False
    assert pack.sku_in_name(None, "Anything") is False


def test_small_case_qty_stays_silent_on_an_ordinary_single_unit():
    """A $49.78 potted palm bought one at a time must not become ambiguous.

    On price alone almost any well-matched single unit "could" be a small case,
    so case_qty is not allowed to speak while the single-unit reading still fits.
    """
    out = _classify(quantity=1, first_cost=50.69, description="4' Travelers Palm",
                    catalog_name="4' Potted Travelers Palm 6 Leaves",
                    catalog_price=49.78, case_qty=6)
    assert out["basis"] == "piece"
    assert out["pieces_used"] == 1
    assert not any("case_qty" in n for n in out["evidence"]["notes"])


def test_small_case_qty_casts_doubt_once_the_single_unit_reading_fails():
    """FC 5x the era expectation for one unit, but ~0.8x for one of a case of 6."""
    out = _classify(quantity=1, first_cost=32.00, description="Ceramic Pot",
                    catalog_name="Ceramic Pot", catalog_price=10.00, case_qty=6)
    assert out["basis"] == "ambiguous"          # never "pack"
    assert out["pack_size"] is None             # case_qty is not adopted as a pack size
    assert out["pieces_used"] == 1              # quantity kept as written
    assert any("case_qty 6" in n for n in out["evidence"]["notes"])


def test_shipping_case_qty_is_ignored_entirely():
    """36/48/80 are shipping cases; they must not cast any doubt at all."""
    out = _classify(quantity=1, first_cost=32.00, description="Ceramic Pot",
                    catalog_name="Ceramic Pot", catalog_price=10.00, case_qty=36)
    assert out["basis"] == "piece"
    assert not any("case_qty" in n for n in out["evidence"]["notes"])


def test_case_qty_corroborates_a_name_pack_size():
    out = _classify(quantity=2, first_cost=12.34, description="Cactus",
                    catalog_name='4" Green Succulent Stem 6/pk',
                    catalog_price=11.14, case_qty=36)
    assert out["basis"] == "pack"
    assert any("multiple of pack size 6" in n for n in out["evidence"]["notes"])


def test_line_description_pack_size_cannot_carry_a_pack_verdict():
    out = _classify(quantity=2, first_cost=2.68,
                    description="3.9'' Smooth Foam Ball  6bag",
                    catalog_name="3.9 Inch Smooth Foam Ball", catalog_price=4.20)
    assert out["pack_size"] == 6
    assert out["pack_size_source"] == "line_description"
    assert out["basis"] == "piece"
    assert out["pieces_used"] == 2


def test_era_factor_is_configurable_and_recorded():
    out = _classify(quantity=1, first_cost=7.10,
                    catalog_name='10.5" Gray Tillandsia Pick', catalog_price=7.10,
                    era_factor=1.0)
    assert out["era_factor"] == 1.0
    assert out["evidence"]["pack_ratio"] == 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Thresholds
# ══════════════════════════════════════════════════════════════════════════════

def test_documented_threshold_values():
    """The docstring promises these numbers; keep them honest."""
    assert pack.ERA_FACTOR == 0.64
    assert pack.SIGMA == 0.35
    assert pack.MIN_CONFIDENCE == 0.70
    assert pack.MAX_ABS_LOG == pytest.approx(math.log(3.0))
    assert pack.REJECT_ABS_LOG == pytest.approx(math.log(5.0))
    assert pack.REJECT_NO_OVERLAP_LOG == pytest.approx(math.log(2.0))
    assert pack.CASE_QTY_PACK_MAX == 12


def test_confidence_is_a_probability():
    for cost in (1.0, 2.05, 5.0, 7.0, 11.14, 12.34, 30.0, 60.0):
        out = _classify(quantity=1, first_cost=cost,
                        description='4" Cactus',
                        catalog_name='4" Green Succulent Stem 6/pk',
                        catalog_price=11.14)
        assert 0.0 <= out["confidence"] <= 1.0
        if out["basis"] in ("pack", "piece"):
            assert out["confidence"] >= pack.MIN_CONFIDENCE


def test_a_perfect_era_fit_beats_a_ten_times_off_alternative():
    """Relative fit drives the verdict; absolute fit only sanity-gates it."""
    out = _classify(quantity=1, first_cost=11.14 * pack.ERA_FACTOR,
                    description="Cactus", catalog_name='4" Stem 6/pk',
                    catalog_price=11.14)
    assert out["basis"] == "pack"
    assert out["confidence"] == pytest.approx(1.0, abs=1e-3)


def test_beyond_the_sanity_band_nothing_is_asserted():
    """Between the factor-3 sanity band and the factor-5 reject band: ambiguous.

    FC 1.14 against a 2/pk at 11.14 reads as 0.32x the era expectation even on the
    better (piece) reading -- too cheap to assert, not absurd enough to call the
    catalog match wrong.
    """
    out = _classify(quantity=1, first_cost=1.14, description="Cactus stem green",
                    catalog_name='4" Green Cactus Stem 2/pk', catalog_price=11.14)
    assert out["basis"] == "ambiguous"
    assert out["pieces_used"] == 1
    assert "sanity band" in out["evidence"]["reason"]


def test_beyond_the_reject_band_the_match_itself_is_discarded():
    out = _classify(quantity=1, first_cost=45.0, description="Cactus stem green",
                    catalog_name='4" Green Cactus Stem 2/pk', catalog_price=11.14)
    assert out["basis"] == "unknown"
    assert "collision" in out["evidence"]["reason"]
    assert out["pieces_used"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# JSONB merge safety
# ══════════════════════════════════════════════════════════════════════════════

def _merge(existing: dict, block: dict) -> dict:
    """Mirror of the SQL `formulas || jsonb_build_object('pack_analysis', ...)`."""
    return {**(existing or {}), pack.ANALYSIS_KEY: block}


EXISTING = {
    "retail": "=E20*6",
    "landed_cost": "=D20*1.2",
    "extended_total": "=F20*G20",
    "anomalies": ["retail 20 != landed_cost 20 x profit factor 6"],
    "flat_priced": ["landed_cost 20 != first_cost 20 x landed factor 1.2"],
    "merged_from_row": 21,
}


def test_merge_preserves_every_existing_key():
    block = _classify(quantity=2, first_cost=12.34,
                      catalog_name='4" Green Succulent Stem 6/pk', catalog_price=11.14)
    merged = _merge(EXISTING, block)
    for key, value in EXISTING.items():
        assert merged[key] == value, key
    assert merged[pack.ANALYSIS_KEY]["basis"] == "pack"
    assert set(merged) == set(EXISTING) | {pack.ANALYSIS_KEY}


def test_merge_into_empty_formulas():
    block = _classify(quantity=1, first_cost=5.0)
    assert _merge({}, block) == {pack.ANALYSIS_KEY: block}


def test_rerunning_the_merge_replaces_only_the_analysis_key():
    first = _merge(EXISTING, _classify(quantity=2, first_cost=12.34,
                                       catalog_name='4" Stem 6/pk',
                                       catalog_price=11.14))
    second = _merge(first, _classify(quantity=2, first_cost=12.34,
                                     catalog_name='4" Stem 6/pk',
                                     catalog_price=11.14))
    assert second == first
    for key, value in EXISTING.items():
        assert second[key] == value, key


def test_the_analysis_key_never_collides_with_an_existing_key():
    assert pack.ANALYSIS_KEY not in EXISTING


def test_block_is_json_round_trippable_and_stable():
    """Idempotency depends on the block serialising identically every time."""
    block = _classify(quantity=3, first_cost=10.67, description="Echeveria 5 Heads",
                      catalog_name='8" Green Springtime Pick 3/Pk',
                      catalog_price=9.41, case_qty=32)
    once = json.dumps(block, sort_keys=True)
    twice = json.dumps(json.loads(once), sort_keys=True)
    assert once == twice
    again = _classify(quantity=3, first_cost=10.67, description="Echeveria 5 Heads",
                      catalog_name='8" Green Springtime Pick 3/Pk',
                      catalog_price=9.41, case_qty=32)
    assert json.dumps(again, sort_keys=True) == once


def test_block_carries_the_documented_shape():
    block = _classify(quantity=2, first_cost=12.34, description="Cactus",
                      catalog_sku="FA170501",
                      catalog_name='4" Green Succulent Stem 6/pk',
                      catalog_price=11.14, catalog_supplier="Regency",
                      case_qty=36, vendor="Regency")
    assert set(block) == {
        "version", "basis", "pack_size", "pack_size_source", "pieces_used",
        "confidence", "quantity", "catalog_sku", "catalog_name", "catalog_price",
        "catalog_supplier", "era_factor", "evidence",
    }
    assert set(block["evidence"]) == {
        "reason", "pack_text", "x_pattern", "case_qty", "vendor", "name_overlap",
        "sku_in_name", "pack_ratio", "piece_ratio", "posterior_pack", "notes",
    }
    assert block["version"] == pack.VERSION


def test_pricing_fields_are_absent_from_the_block():
    """The block must not carry, and therefore cannot be used to rewrite, prices."""
    block = _classify(quantity=2, first_cost=12.34,
                      catalog_name='4" Stem 6/pk', catalog_price=11.14)
    for forbidden in ("first_cost", "landed_cost", "retail", "extended_total"):
        assert forbidden not in block
        assert forbidden not in block["evidence"]


def test_update_sql_is_an_additive_merge():
    """Guard the SQL itself: a bare assignment would silently drop keys."""
    sql = " ".join(pack.UPDATE_SQL.split())
    assert "formulas = coalesce(formulas, '{}'::jsonb) || jsonb_build_object" in sql
    assert "SET formulas = $2" not in sql
    for column in ("quantity", "first_cost", "landed_cost", "retail", "extended_total"):
        assert f"{column} =" not in sql


def test_no_ddl_anywhere_in_the_script():
    """The `app` role cannot run DDL on the public schema."""
    source = SCRIPT.read_text(encoding="utf-8").lower()
    for statement in ("create table", "alter table", "drop table", "create index",
                      "add column"):
        assert statement not in source, statement
