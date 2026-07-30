"""Parser tests for the TBDG pricing worksheets.

The numeric expectations come from the canonical reference file -- one complete
product the user built start to finish -- so a regression in the component-block
detection or the pricing chain shows up as a hard failure rather than as quietly
wrong build intelligence.
"""
import os
from pathlib import Path

import pytest

from app.libs import recipe_intake as ri

BACKEND = Path(__file__).resolve().parents[1]
RECIPES = Path(os.environ.get("LL_RECIPES_DIR")
               or BACKEND.parents[1] / "pricing-recipes" / "RECIPES")

REFERENCE = RECIPES / "Super_Full_Fiddle_Leaf_Fig_Tree_PRODUCTION_PRICE_WORK_SHEET.xlsx"
BLANK_TEMPLATE = RECIPES / "PRODUCTION_PRICE_WORK_SHEET.xlsx"
QUOTE = RECIPES / "SeverinGroup_BellLafayette_QUOTE_WORK_SHEET.xlsx"
LEGACY = RECIPES / "Cantoni 2023 and 2022 Recipes/Recipes Cantoni 2022/TT9-22422.xlsx"

needs_corpus = pytest.mark.skipif(
    not REFERENCE.exists(), reason=f"pricing-recipes corpus not present at {RECIPES}")


# ── pure helpers (no corpus needed) ───────────────────────────────────────────


def test_derive_build_type_reads_the_product_name():
    assert ri.derive_build_type("Floor Inventory _ SUPER FULL FIDDLE LEAF FIG TREE") == "Tree"
    assert ri.derive_build_type("24in Boxwood Wreath") == "Wreath"
    assert ri.derive_build_type("Cedar Garland 9ft") == "Garland"
    assert ri.derive_build_type("Holiday Centerpiece") == "Centerpiece"
    assert ri.derive_build_type("Zinc Planter with Grass") == "Planter"
    assert ri.derive_build_type("Triple Pom-Pom Amaryllis") == "Floral Arrangement"
    assert ri.derive_build_type(None) is None
    assert ri.derive_build_type("") is None


def test_derive_build_type_prefers_the_specific_family_over_the_taxonomy_fallback():
    # "topiary" is a Tree to the product taxonomy but its own build here
    assert ri.derive_build_type("Bay Leaf Topiary") == "Topiary"


def test_classify_component_tags_the_role_within_the_build():
    assert ri.classify_component("PA444AM-S", 'Zinc 20"X12"X12" Container') == "container"
    assert ri.classify_component(None, "Foam ") == "mechanics"
    assert ri.classify_component(None, "Rocks") == "mechanics"
    assert ri.classify_component("P2856-44", "Large Plant Stem") == "product"
    assert ri.classify_component(None, None) == "product"


def test_source_collection_drops_the_mirrored_pricing_folders():
    assert ri.source_collection("PRICING 4/Trees 2022/TT95321.xlsx") == "Trees 2022"
    assert ri.source_collection("PRICING/Recipes/WAYFAIR/x.xlsx") == "Recipes/WAYFAIR"
    assert ri.source_collection("PRODUCTION_PRICE_WORK_SHEET.xlsx") == "TBDG Root"


def test_recipe_year_hint_reads_the_path():
    assert ri.recipe_year_hint("Cantoni 2023 and 2022 Recipes/RECIPES 2023/x.xlsx") == 2023
    assert ri.recipe_year_hint("PRICING 4/x.xlsx") is None


# ── the canonical 2025 production worksheet ───────────────────────────────────


@needs_corpus
def test_sniff_format_identifies_each_family():
    assert ri.sniff_format(REFERENCE)[0] == ri.FORMAT_PRODUCTION_2025
    assert ri.sniff_format(QUOTE)[0] == ri.FORMAT_PRICING_2025
    assert ri.sniff_format(LEGACY)[0] == ri.FORMAT_CREATIVE_BRANCH


@needs_corpus
def test_reference_file_matches_the_sheet_exactly():
    recipe = ri.parse_recipe_xlsx(REFERENCE)

    assert recipe.format_family == ri.FORMAT_PRODUCTION_2025
    assert recipe.description == "Floor Inventory _ SUPER FULL FIDDLE LEAF FIG TREE"
    assert recipe.build_type == "Tree"
    assert recipe.recipe_year == 2025

    assert len(recipe.components) == 6
    assert recipe.pricing_summary["pre_retail_total"] == 4482
    assert recipe.pricing_summary["retail"] == 6723
    assert recipe.pricing_summary["factors"] == {
        "landed_cost": 1.2, "arrangement_labor": 1.5, "profit": 6.0}

    # retail = pre-retail x AR, and pre-retail = the sum of the PRT column
    assert recipe.pricing_summary["component_extended_sum"] == 4482
    assert recipe.pricing_summary["retail"] == pytest.approx(4482 * 1.5)


@needs_corpus
def test_reference_file_component_lines():
    lines = ri.parse_recipe_xlsx(REFERENCE).components
    first = lines[0]
    assert (first.supplier_sku, first.vendor, first.description) == (
        "P2856-44", "Amazing G", "Large Plant Stem")
    assert (first.first_cost, first.landed_cost, first.retail) == (50.0, 60.0, 360.0)
    assert (first.quantity, first.extended_total) == (7.0, 2520.0)
    assert [c.component_label for c in lines] == [
        "product", "product", "container", "mechanics", "mechanics", "mechanics"]


@needs_corpus
def test_reference_file_flags_the_hand_built_math_without_correcting_it():
    lines = ri.parse_recipe_xlsx(REFERENCE).components

    # Draggon Wood multiplies FC by the AR factor (1.5) instead of landed cost
    draggon = next(c for c in lines if c.supplier_sku == "Draggon Wood")
    assert draggon.landed_cost == 4.5  # the value stands; 3.0 x 1.2 would be 3.6
    assert draggon.formulas["landed_cost"] == "=D16*B30"
    assert any("landed factor" in a for a in draggon.anomalies)

    # the container applies the profit factor twice
    container = next(c for c in lines if c.component_label == "container")
    assert container.landed_cost == 300.0  # 50 x 6, not 50 x 1.2
    assert container.formulas["landed_cost"] == "=D17*B31"
    assert any("implied factor 6" in a for a in container.anomalies)

    assert sum(len(c.anomalies) for c in lines) == 2


@needs_corpus
def test_unpriced_lines_are_kept_on_the_header_not_thrown_away():
    recipe = ri.parse_recipe_xlsx(REFERENCE)
    unpriced = recipe.raw_header["unpriced_lines"]
    assert [u["cells"]["C"] for u in unpriced] == ["Other Mechanics"]


@needs_corpus
def test_raw_row_captures_the_whole_original_row():
    first = ri.parse_recipe_xlsx(REFERENCE).components[0]
    assert first.raw_row["row"] == 15
    assert first.raw_row["cells"]["A"] == "P2856-44"
    assert first.raw_row["cells"]["H"] == 2520


@needs_corpus
def test_blank_template_is_rejected_rather_than_imported_as_a_build():
    with pytest.raises(ri.RecipeParseError):
        ri.parse_recipe_xlsx(BLANK_TEMPLATE)


# ── the 2025 quote worksheet ──────────────────────────────────────────────────


@needs_corpus
def test_quote_worksheet_merges_line_items_split_over_two_rows():
    recipe = ri.parse_recipe_xlsx(QUOTE)
    assert recipe.format_family == ri.FORMAT_PRICING_2025
    assert recipe.dimensions == {"length": '48"', "width": '16"', "height": "4.5' - 5'"}

    grass = next(c for c in recipe.components if c.supplier_sku == "A-174800")
    assert grass.vendor == "Autograph Foliages"          # from the row above
    assert "Outdoor UV Grass" in grass.description       # from the priced row
    assert grass.extended_total == pytest.approx(43027.2)
    assert grass.formulas["merged_from_row"] == 22

    assert recipe.pricing_summary["pre_retail_total"] == pytest.approx(56105.4)
    assert recipe.pricing_summary["retail"] == pytest.approx(84158.1)


# ── the Creative Branch legacy family ─────────────────────────────────────────


@needs_corpus
def test_legacy_recipe_reads_codes_dimensions_and_totals():
    recipe = ri.parse_recipe_xlsx(LEGACY)

    assert recipe.format_family == ri.FORMAT_CREATIVE_BRANCH
    assert recipe.item_code == "TT9-22422"
    assert recipe.customer_item_code == "57581"       # the CANTONI item number
    assert recipe.description == "Triple Pom-Pom Amaryllis Half-Head Removable"
    assert recipe.recipe_year == 2022
    assert recipe.build_type == "Floral Arrangement"
    assert recipe.visual_reference_count == 1         # the embedded product photo

    assert recipe.dimensions["height"] == "9'"
    assert recipe.container_details["material"] == "Zinc"

    assert recipe.pricing_summary["component_total"] == pytest.approx(1420.216)
    assert recipe.pricing_summary["retail"] == pytest.approx(1775.27)
    assert recipe.pricing_summary["wholesale"] == pytest.approx(887.635)
    assert recipe.pricing_summary["factors"]["retail_markup"] == pytest.approx(1.25)


@needs_corpus
def test_legacy_components_carry_supplier_attribution():
    recipe = ri.parse_recipe_xlsx(LEGACY)
    assert len(recipe.components) == 7
    vendors = {c.vendor for c in recipe.components}
    assert {"PMJC", "Gold Eagle", "Forest Line", "Flora Craft", "Schuster"} <= vendors

    dragon = next(c for c in recipe.components if c.supplier_sku == "DRAGTK12")
    assert dragon.first_cost == 4.5
    assert dragon.landed_cost == pytest.approx(5.4)     # x 1.2
    assert dragon.retail == pytest.approx(32.4)         # x 6
    assert dragon.extended_total == pytest.approx(97.2)  # x qty 3


@needs_corpus
def test_every_parsed_recipe_agrees_with_its_own_sheet_total():
    """The component block boundaries are right only if the lines we picked up
    add back to the total the sheet itself printed. Run across the whole corpus."""
    checked = mismatched = 0
    for path in sorted(RECIPES.rglob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        family, _ = ri.sniff_format(path)
        if family not in ri.SUPPORTED_FORMATS:
            continue
        try:
            recipe = ri.parse_recipe_xlsx(path, format_family=family)
        except ri.RecipeParseError:
            continue
        summary = recipe.pricing_summary
        stated = summary.get("component_total") or summary.get("pre_retail_total")
        if not stated:
            continue
        checked += 1
        if abs(stated - summary["component_extended_sum"]) > max(0.05, stated * 0.001):
            mismatched += 1
    assert checked > 100, "corpus should provide plenty of cross-checks"
    assert mismatched == 0
