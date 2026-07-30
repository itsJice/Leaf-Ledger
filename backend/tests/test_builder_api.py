"""Tests for the builder-intelligence API.

No database: the whole module is a pure function of one corpus snapshot, so the
fixture stubs the two table reads and every endpoint below runs the real
aggregation and response code rather than a copy of it.

What is worth locking down is the arithmetic that a wrong answer hides inside:

* **height → band, and band → canopy tier.** Bands are half-open, so a build at
  exactly 60″ or 84″ must land in exactly one of them. An off-by-one here
  silently retiers every 5′ and 7′ build.
* **density is keyed to species × height and never pooled.** At 7′ an Areca uses
  1 stem and a Eucalyptus 16. If a change ever makes those two share a
  baseline, the endpoint is worthless — and it would still look like working
  software.
* **the pieces_used → quantity fallback.** `quantity` mixes packs and pieces, so
  a parallel importer resolves it. The counts have to be right both before and
  after that work lands, which means both paths need a test.
* **honest sparseness.** Almost every species×height cell holds 1–5 recipes, so
  `n`, `confidence` and the class fallback are part of the contract; inventing
  a baseline for a species with no history is the failure mode to prevent.
"""

import asyncio

import pytest

from app.apis import builder


# ─── Fixture corpus ──────────────────────────────────────────────────────────
# Small, but shaped like the real thing: heights written the four ways the
# sheets write them, an Areca specimen and a Eucalyptus built-up at the same
# 7 feet, an n=1 cell, a pack-analysis line, a blank sheet with no build type,
# and a sheet that parsed but priced to nothing.


def _recipe(id, item_code, build_type, description, dims, pricing=None):
    return {
        "id": id,
        "source_file_id": None,
        "item_code": item_code,
        "product_family": None,
        "build_type": build_type,
        "description": description,
        "source_collection": "Trees 2022",
        "recipe_year": 2022,
        "dimensions": dims,
        "container_details": {},
        "pricing_summary": pricing if pricing is not None else {"component_total": 500.0,
                                                               "retail": 1250.0,
                                                               "wholesale": 625.0},
        "visual_reference_count": 0,
    }


def _comp(id, recipe_id, order, label, description, quantity, formulas=None,
          extended_total=100.0):
    return {
        "id": id, "recipe_id": recipe_id, "line_order": order,
        "component_label": label, "vendor": "Allstate", "supplier_sku": "PSF330-GR",
        "description": description, "quantity": quantity, "first_cost": 10.0,
        "landed_cost": 12.0, "retail": 60.0, "extended_total": extended_total,
        "formulas": formulas or {},
    }


RECIPES = [
    # Two 7' Fiddle trees → an n=2 cell with a real spread (4 and 8 pieces).
    _recipe(1, "TT9-A", "Tree", "7' Fiddle Leaf Tree",
            {"height": "7'", "width": "42\"", "depth": "42\""}),
    _recipe(2, "TT9-B", "Tree", "7' Fiddle Leaf Tree",
            {"height": "84", "width": "46\"", "depth": "46\""}),
    # A 7' Areca: a specimen at the same height as the Eucalyptus below.
    _recipe(3, "TT9-C", "Tree", "7' Areca Palm (Single)",
            {"height": "7'", "width": "36\"", "depth": "36\""}),
    # A 7' Eucalyptus: 16 pieces at the same 7 feet. n=1 cell.
    _recipe(4, "TT9-D", "Tree", "7' Eucalyptus Tree in zinc container",
            {"height": "7'", "width": "48''", "depth": "48''"}),
    # A 6' Fiddle, so "same species, nearby height" has something to scale from.
    _recipe(5, "TT9-E", "Tree", "6' Fiddle Tree",
            {"height": "6'", "width": "30\"", "depth": "30\""}),
    # Plant & Bush, the most-built type.
    _recipe(6, "SG7-A", "Plant & Bush", "Succulent Garden",
            {"height": "22\"", "width": "18\"", "depth": "18\""}),
    # Junk 1: a blank sheet — no build type.
    _recipe(7, None, None, "TEMPLATE QUOTE WORK SHEET", {}),
    # Junk 2: parsed, but priced to nothing (the real TT9-9522 Bay Leaf Topiary).
    _recipe(8, "TT9-9522", "Topiary", "Bay Leaf Topiary",
            {"height": "48\"", "width": "20\""},
            pricing={"retail": 0.0, "component_total": 0.0}),
]

COMPONENTS = [
    # Recipe 1 — 4 pieces of product (3 branches + 1 pole).
    _comp(1, 1, 0, "product", '30" Fiddle Leaf Branch', 3),
    _comp(2, 1, 1, "product", "Dragonwood 1-2\" Diameter", 1),
    _comp(3, 1, 2, "container", "Zinc Container 16X16X16", 1),
    _comp(4, 1, 3, "mechanics", "Sheet Moss", None),
    _comp(5, 1, 4, "mechanics", "Foam", None),
    # Recipe 2 — 8 pieces.
    _comp(6, 2, 0, "product", '34" Fiddle Leaf Branch With 24 Leaves Green', 5),
    _comp(7, 2, 1, "product", "Dragonwood 8-10' / 1-2''", 3),
    _comp(8, 2, 2, "container", "Marta Pot 18\"X16.25\"", 1),
    _comp(9, 2, 3, "mechanics", "mixed buff moon rock, 1-2\"", None),
    # Recipe 3 — one Areca palm. Specimen: 1 piece.
    _comp(10, 3, 0, "product", "6' Areca Palm", 1),
    _comp(11, 3, 1, "container", '19" Flared Zinc Container', 1),
    _comp(12, 3, 2, "mechanics", "Top Dressing / Mechanics", 1),
    # Recipe 4 — 16 pieces of Eucalyptus at the same 7 feet.
    _comp(13, 4, 0, "product", '36" Eucalyptus Spray Gr', 13),
    _comp(14, 4, 1, "product", "Hard Mapple 1-2\"X 6'", 3),
    _comp(15, 4, 2, "container", "Zinc Container 16X16X16", 1),
    _comp(16, 4, 3, "mechanics", "natural lichen moss", None),
    # Recipe 5 — 6' Fiddle, 3 pieces.
    _comp(17, 5, 0, "product", '34" Fiddle Leaf Branch', 3),
    _comp(18, 5, 1, "container", "Fiber Resin Fluted Planter", 1),
    _comp(19, 5, 2, "mechanics", "sheet moss", None),
    # Recipe 6 — a pack line: quantity 2 means 2 packs of 6, i.e. 12 pieces.
    _comp(20, 6, 0, "product", '4" Green Succulent Stem 6/pk', 2,
          formulas={"pack_analysis": {"basis": "catalog", "pack_size": 6,
                                      "pieces_used": 12, "confidence": "high"}}),
    _comp(21, 6, 1, "container", "Concrete Bowl", 1),
    _comp(22, 6, 2, "mechanics", "reindeer moss", None),
    # Recipe 7 — blank sheet.
    _comp(23, 7, 0, "mechanics", "Top Dressing / Mechanics", None),
    # Recipe 8 — the valueless Topiary sheet.
    _comp(24, 8, 0, "product", "Bay Leaf Topiary", None, extended_total=None),
    # Foam is on nearly every real recipe; enough of them here that the derived
    # vocabulary has something with a count above the noise floor.
    _comp(25, 2, 4, "mechanics", "Foam", None),
    _comp(26, 4, 4, "mechanics", "foam, moss", None),
    _comp(27, 5, 3, "mechanics", "Foam", None),
    _comp(28, 6, 3, "mechanics", "Foam", None),
]


@pytest.fixture
def stub_corpus(monkeypatch):
    """Serve the endpoints a fixed corpus, with no database involved."""
    async def fake_conn():
        class _Conn:
            async def close(self):
                return None
        return _Conn()

    async def fake_fetch(_conn):
        return [dict(r) for r in RECIPES], [dict(c) for c in COMPONENTS]

    monkeypatch.setattr(builder, "get_conn", fake_conn)
    monkeypatch.setattr(builder, "_fetch_corpus_rows", fake_fetch)
    monkeypatch.setattr(builder, "_CACHE", {"ts": 0.0, "corpus": None})
    yield
    builder._CACHE.update(ts=0.0, corpus=None)


def _run(coro):
    return asyncio.run(coro)


# ─── Dimension parsing ───────────────────────────────────────────────────────


def test_parse_length_reads_every_shape_the_sheets_use():
    assert builder.parse_length_in("7'") == 84
    assert builder.parse_length_in("6.5'") == 78
    assert builder.parse_length_in('36"') == 36
    assert builder.parse_length_in("58''") == 58
    assert builder.parse_length_in('9 1/2"') == 9.5
    assert builder.parse_length_in(42) == 42
    # A bare number is inches, not feet: TT9-92122 records height "84" and is
    # named 7' Fiddle Leaf Tree.
    assert builder.parse_length_in("84") == 84
    # A range collapses to its midpoint, with the unit carried across.
    assert builder.parse_length_in("4.5' - 5'") == 57


def test_parse_length_returns_none_for_junk_instead_of_raising():
    for bad in (None, "", "   ", "p", "n/a", {}, []):
        assert builder.parse_length_in(bad) is None


def test_format_height_writes_it_back_the_way_the_shop_does():
    assert builder.format_height(84) == "7'"
    assert builder.format_height(78) == "6.5'"
    assert builder.format_height(42) == '42"'
    assert builder.format_height(None) is None


# ─── Height bands and canopy tiers ───────────────────────────────────────────


def test_height_bands_are_half_open_so_a_build_lands_in_exactly_one():
    assert builder.height_band(59.9) == "<5'"
    assert builder.height_band(60) == "5-7'"       # exactly 5' is the 5-7' band
    assert builder.height_band(83.9) == "5-7'"
    assert builder.height_band(84) == "7-9'"       # exactly 7' is the 7-9' band
    assert builder.height_band(107.9) == "7-9'"
    assert builder.height_band(108) == "9'+"       # exactly 9' is the 9'+ band
    assert builder.height_band(200) == "9'+"
    assert builder.height_band(None) is None


def test_the_same_width_is_a_different_tier_at_a_different_height():
    """The whole point of per-band tiers: 42" is not one fixed fullness."""
    assert builder.canopy_tier_for(72, 42) == "XL"   # 42" on a 6' tree is huge
    assert builder.canopy_tier_for(84, 42) == "M"    # ...and standard on a 7'
    assert builder.canopy_tier_for(120, 42) == "XS"  # ...and thin on a 10'


def test_canopy_tier_boundaries_are_inclusive_low_exclusive_high():
    # 7-9' band cut points: 36 / 42 / 45 / 48
    assert builder.canopy_tier_for(84, 35.9) == "XS"
    assert builder.canopy_tier_for(84, 36) == "S"
    assert builder.canopy_tier_for(84, 41.9) == "S"
    assert builder.canopy_tier_for(84, 42) == "M"
    assert builder.canopy_tier_for(84, 45) == "L"
    assert builder.canopy_tier_for(84, 47.9) == "L"
    assert builder.canopy_tier_for(84, 48) == "XL"
    assert builder.canopy_tier_for(84, 500) == "XL"


def test_canopy_tier_needs_both_numbers():
    assert builder.canopy_tier_for(None, 42) is None
    assert builder.canopy_tier_for(84, None) is None


def test_canopy_tiers_endpoint_serves_cut_points_and_the_live_measurement(stub_corpus):
    result = _run(builder.get_canopy_tiers(height="7'"))
    assert result["band"] == "7-9'"
    assert result["height_in"] == 84 and result["height_display"] == "7'"
    assert [t["key"] for t in result["tiers"]] == ["XS", "S", "M", "L", "XL"]
    assert [t["min_in"] for t in result["tiers"]] == [None, 36, 42, 45, 48]
    assert [t["max_in"] for t in result["tiers"]] == [36, 42, 45, 48, None]
    assert result["default_tier"] == "M"
    assert result["provisional"] is False
    # The measurement travels with the constants so a drift is visible.
    assert result["measured"]["n"] == 4          # the four 7' trees in the fixture
    assert result["n"] == 4
    # Silhouette is offered as capture-going-forward, defaulting to full-round.
    assert [s["key"] for s in result["silhouettes"]] == ["full_round", "corner", "flat_back"]
    assert result["silhouettes"][0]["default"] is True


def test_canopy_tiers_flags_the_9ft_band_as_provisional(stub_corpus):
    """n=3 in the corpus — served, but the UI must be able to say so."""
    assert _run(builder.get_canopy_tiers(height_in=120))["provisional"] is True
    assert _run(builder.get_canopy_tiers(height_in=84))["provisional"] is False


def test_canopy_tiers_can_place_a_width_and_serve_the_whole_table(stub_corpus):
    assert _run(builder.get_canopy_tiers(height_in=84, width_in=47))["matched_tier"] == "L"
    whole = _run(builder.get_canopy_tiers())
    assert [b["band"] for b in whole["bands"]] == ["<5'", "5-7'", "7-9'", "9'+"]


def test_canopy_tiers_rejects_an_unreadable_height(stub_corpus):
    with pytest.raises(Exception) as excinfo:
        _run(builder.get_canopy_tiers(height="tall-ish"))
    assert getattr(excinfo.value, "status_code", None) == 400


# ─── Piece counting: pack_analysis vs quantity ───────────────────────────────


def test_pieces_prefer_pack_analysis_when_the_importer_has_resolved_the_line():
    """`quantity` 2 means 2 six-packs — 12 pieces, not 2."""
    pieces, basis = builder.component_pieces({
        "quantity": 2,
        "formulas": {"pack_analysis": {"pack_size": 6, "pieces_used": 12}},
    })
    assert (pieces, basis) == (12.0, "pack_analysis")


def test_pieces_fall_back_to_quantity_when_pack_analysis_is_absent():
    """This is the path that runs today: 0 of 1106 lines carry pack_analysis."""
    for formulas in ({}, None, {"retail": "=E20*6"}, {"pack_analysis": None},
                     {"pack_analysis": {}}, {"pack_analysis": {"pieces_used": None}},
                     {"pack_analysis": "not a dict"}):
        assert builder.component_pieces({"quantity": 7, "formulas": formulas}) == (7.0, "quantity")


def test_pieces_survive_jsonb_arriving_as_text():
    pieces, basis = builder.component_pieces({
        "quantity": 1, "formulas": '{"pack_analysis": {"pieces_used": 6}}',
    })
    assert (pieces, basis) == (6.0, "pack_analysis")


def test_a_missing_quantity_counts_as_zero_not_as_an_error():
    assert builder.component_pieces({"quantity": None, "formulas": {}}) == (0.0, "quantity")
    assert builder.component_pieces({"quantity": "oops", "formulas": {}}) == (0.0, "quantity")


def test_the_response_says_which_piece_basis_it_actually_used(stub_corpus):
    basis = _run(builder.get_health())["piece_basis"]
    # One fixture line carries pack_analysis, the rest fall back.
    assert basis["primary"] == "mixed"
    assert basis["lines_from_pack_analysis"] == 1
    assert basis["lines_from_quantity"] == len(COMPONENTS) - 1


def test_a_pack_line_is_counted_as_pieces_in_the_density_baseline(stub_corpus):
    """The fixture's succulent garden is 2 packs = 12 pieces, and must read 12."""
    result = _run(builder.get_density(species="Succulent", height_in=22))
    assert result["baseline_pieces"] == 12


# ─── Density: species × height, never pooled ─────────────────────────────────


def test_density_never_pools_species_at_the_same_height(stub_corpus):
    """1 stem vs 16 at an identical 7 feet is the reason baselines are f(species, height)."""
    areca = _run(builder.get_density(species="Areca", height="7'"))
    eucalyptus = _run(builder.get_density(species="Eucalyptus", height="7'"))
    assert areca["baseline_pieces"] == 1
    assert eucalyptus["baseline_pieces"] == 16
    assert areca["source"] == eucalyptus["source"] == "species_height"


def test_density_reports_n_and_the_observed_spread(stub_corpus):
    result = _run(builder.get_density(species="Fiddle", height="7'"))
    assert result["n"] == 2
    assert result["baseline_pieces"] == 6         # median of 4 and 8
    assert result["observed_min"] == 4 and result["observed_max"] == 8
    assert result["confidence"] == "very_low"     # n=2 is not evidence
    assert result["examples"]


def test_an_n_of_1_cell_answers_but_says_how_thin_it_is(stub_corpus):
    result = _run(builder.get_density(species="Eucalyptus", height_in=84))
    assert result["n"] == 1
    assert result["observed_min"] == result["observed_max"] == 16
    assert result["confidence"] == "very_low"
    assert result["source"] == "species_height"


def test_density_bands_are_variance_around_that_species_baseline(stub_corpus):
    result = _run(builder.get_density(species="Eucalyptus", height_in=84))
    bands = {b["key"]: b["pieces"] for b in result["bands"]}
    assert list(bands) == ["sparse", "standard", "full", "super_full"]
    assert bands["standard"] == 16                       # the baseline itself
    assert bands["sparse"] == 12                         # 16 x 0.75
    assert bands["full"] == 26                           # 16 x 1.6
    assert bands["super_full"] == 36                     # 16 x 2.25
    assert all(b["basis"] == "pooled_spread" for b in result["bands"])
    assert result["default_band"] == "standard"


def test_a_specimen_has_no_super_full_and_none_is_invented(stub_corpus):
    """A 1-stem Areca Palm has no fuller version. Inventing one is the failure."""
    result = _run(builder.get_density(species="Areca", height="7'"))
    assert [b["pieces"] for b in result["bands"]] == [1, 1, 1, 1]
    assert all(b["basis"] == "specimen_flat" for b in result["bands"])
    assert result["density_applies"] is False


def test_built_up_bands_stay_four_distinct_rungs_on_a_tiny_sample(stub_corpus):
    """Rounding a 3-piece baseline must not collapse Full into Standard."""
    result = _run(builder.get_density(species="Succulent", height_in=22))
    pieces = [b["pieces"] for b in result["bands"]]
    assert pieces == sorted(pieces)
    # Standard is always the baseline itself, never a rounded-away neighbour.
    assert pieces[1] == result["baseline_pieces"]
    assert pieces[2] > pieces[1] and pieces[3] > pieces[2]


def test_specimen_species_say_density_barely_applies(stub_corpus):
    result = _run(builder.get_density(species="Areca", height="7'"))
    assert result["structural_class"] == "specimen"
    assert result["density_applies"] is False
    assert any("specimen" in n.lower() for n in result["notes"])
    # ...while a built-up species is a real dial.
    fiddle = _run(builder.get_density(species="Fiddle", height="7'"))
    assert fiddle["structural_class"] == "built_up"
    assert fiddle["density_applies"] is True


def test_density_falls_back_to_a_nearby_height_of_the_same_species(stub_corpus):
    """No 8' Fiddle in the fixture: scale from the 7' cell and say so."""
    result = _run(builder.get_density(species="Fiddle", height="8'"))
    assert result["source"] == "species_nearby_height"
    assert result["confidence"] == "low"
    assert any("scaled" in n for n in result["notes"])


def test_an_unseen_species_falls_back_to_its_class_and_labels_it(stub_corpus):
    """Never invent a baseline: say it is a class average, and that n is 0."""
    result = _run(builder.get_density(species="Croton", height="7'"))
    assert result["species"] == "Croton"
    assert result["source"] == "class_fallback"
    assert result["n"] == 0
    assert result["confidence"] == "none"
    assert any("class" in n for n in result["notes"])


def test_an_unseen_specimen_species_falls_back_to_one_plant(stub_corpus):
    result = _run(builder.get_density(species="Palm", height="9'"))
    assert result["structural_class"] == "specimen"
    assert result["source"] == "class_fallback"
    assert result["baseline_pieces"] == 1
    assert result["density_applies"] is False


def test_a_species_outside_the_vocabulary_is_answered_and_flagged(stub_corpus):
    result = _run(builder.get_density(species="Unobtainium Bush", height="7'"))
    assert result["requested_species"] == "Unobtainium Bush"
    assert result["species"] is None
    assert result["structural_class"] == builder._DEFAULT_CLASS
    assert result["class_basis"] == "default"
    assert result["source"] == "class_fallback"
    assert any("not in the recipe vocabulary" in n for n in result["notes"])


def test_density_with_no_species_at_all_still_answers_from_the_class(stub_corpus):
    result = _run(builder.get_density(height="7'"))
    assert result["species"] is None
    assert result["source"] == "class_fallback"
    assert result["n"] == 0


def test_density_accepts_a_species_alias(stub_corpus):
    """"fiddle leaf fig" is what a designer types; "Fiddle" is what we store."""
    assert _run(builder.get_density(species="fiddle leaf fig", height="7'"))["species"] == "Fiddle"
    assert _run(builder.get_density(species="YUCCA", height="7'"))["species"] == "Yucca"


def test_density_names_its_metric_so_the_number_is_interpretable(stub_corpus):
    basis = _run(builder.get_density(species="Fiddle", height="7'"))["basis"]
    assert basis["metric"] == "product_lines"
    assert basis["piece_field"] in ("quantity", "pack_analysis", "mixed")


# ─── Species classification ──────────────────────────────────────────────────


def test_species_detection_reads_the_description_then_the_parts():
    assert builder.detect_species("7' Fiddle Leaf Tree") == "Fiddle"
    assert builder.detect_species(None, '36" Eucalyptus Spray Gr') == "Eucalyptus"
    assert builder.detect_species("nothing botanical here") is None
    assert builder.detect_species(None, None) is None


def test_palm_fiber_is_top_dressing_and_never_a_palm():
    """16 lines say "Palm Fiber"; counted as a palm they hand generic Palm a fake baseline."""
    assert builder.detect_species("Palm Fiber") is None
    assert builder.detect_species("Coco Palm Fiber") is None
    assert builder.detect_species("6' Areca Palm") == "Areca"
    assert builder.detect_species("9' Kentia Palm") == "Kentia"
    assert builder.detect_species("Palm tree") == "Palm"


def test_specific_species_win_over_the_generic_palm():
    assert builder.detect_species("8' Travelers Palm") == "Travelers Palm"
    assert builder.detect_species("8' Traveller's Palm") == "Travelers Palm"


def test_species_endpoint_tags_every_species_with_its_class(stub_corpus):
    result = _run(builder.get_species())
    by_name = {s["name"]: s for s in result["species"]}
    assert by_name["Fiddle"]["structural_class"] == "built_up"
    assert by_name["Fiddle"]["recipe_count"] == 3
    assert by_name["Areca"]["structural_class"] == "specimen"
    assert by_name["Areca"]["density_applies"] is False
    # The spec's pinned classes are cross-checked against the data.
    assert by_name["Areca"]["class_basis"] == "spec"
    assert by_name["Areca"]["class_agrees_with_data"] is True
    assert set(result["classes"]) == {"built_up", "specimen"}


def test_species_ordered_by_how_much_history_backs_them(stub_corpus):
    counts = [s["recipe_count"] for s in _run(builder.get_species())["species"]]
    assert counts == sorted(counts, reverse=True)


def test_species_can_be_narrowed_to_one_build_type(stub_corpus):
    trees = _run(builder.get_species(build_type="Tree"))
    assert {s["name"] for s in trees["species"]} == {"Fiddle", "Areca", "Eucalyptus"}
    assert trees["build_type"] == "Tree"
    bushes = _run(builder.get_species(build_type="Plant & Bush"))
    assert {s["name"] for s in bushes["species"]} == {"Succulent"}


def test_a_filtered_species_list_narrows_every_count_together(stub_corpus):
    """A Tree-filtered row reporting a whole-corpus usable count is unusable."""
    every = {s["name"]: s for s in _run(builder.get_species())["species"]}
    trees = {s["name"]: s for s in _run(builder.get_species(build_type="Tree"))["species"]}
    assert every["Areca"]["recipe_count"] == every["Areca"]["usable_recipe_count"] == 1
    for row in trees.values():
        assert row["usable_recipe_count"] <= row["recipe_count"]
        assert row["recipe_count"] == sum(row["build_types"].values())


def test_species_can_drop_the_vocabulary_entries_with_no_history(stub_corpus):
    every = _run(builder.get_species())["species"]
    backed = _run(builder.get_species(include_empty=False))["species"]
    assert any(s["recipe_count"] == 0 for s in every)
    assert all(s["recipe_count"] > 0 for s in backed)
    # A history-less species is still offered by default, so it can be picked.
    assert "Croton" in {s["name"] for s in every}


def test_species_rejects_an_unknown_build_type(stub_corpus):
    with pytest.raises(Exception) as excinfo:
        _run(builder.get_species(build_type="Interpretive Dance"))
    assert getattr(excinfo.value, "status_code", None) == 400


# ─── Build types ─────────────────────────────────────────────────────────────


def test_build_types_lead_with_what_actually_gets_built(stub_corpus):
    result = _run(builder.get_build_types())
    labels = [b["label"] for b in result["build_types"]]
    assert labels[0] == "Tree"          # the fixture's most-built type
    counts = [b["recipe_count"] for b in result["build_types"]]
    assert counts == sorted(counts, reverse=True)
    # The three historical types the user approved adding are all present.
    assert {"Plant & Bush", "Container Only", "Topiary"} <= set(labels)
    # ...alongside the ones the builder already had.
    assert {"Tree", "Floral Arrangement", "Planter", "Drop-in", "Custom"} <= set(labels)


def test_slot_templates_read_bottom_up_container_last(stub_corpus):
    by_label = {b["label"]: b for b in _run(builder.get_build_types())["build_types"]}
    tree = by_label["Tree"]
    assert [s["label"] for s in tree["slots"]] == [
        "Leaves", "Trunks & Branches", "Top Dressing", "Container"]
    assert [s["order"] for s in tree["slots"]] == [0, 1, 2, 3]
    assert tree["slot_order"] == "bottom_up"
    # Container is the bottom slot of every type that has one.
    for build_type in by_label.values():
        if build_type["slots"]:
            assert build_type["slots"][-1]["scope"] == "container"


def test_a_type_never_advertises_a_field_it_cannot_use(stub_corpus):
    by_label = {b["label"]: b for b in _run(builder.get_build_types())["build_types"]}
    for label in ("Tree", "Plant & Bush", "Topiary"):
        assert by_label[label]["fields"]["canopy"] is True
        assert by_label[label]["fields"]["silhouette"] is True
    for label in ("Container Only", "Drop-in"):
        assert by_label[label]["fields"]["canopy"] is False
        assert by_label[label]["fields"]["silhouette"] is False
    # Container Only holds no plant material, so density is meaningless too.
    assert by_label["Container Only"]["fields"]["density"] is False
    assert [s["scope"] for s in by_label["Container Only"]["slots"]] == [
        "top_dressing", "container"]
    # `applies` is the same fact as a list, for a UI that would rather iterate.
    assert set(by_label["Tree"]["applies"]) == {
        f for f, on in by_label["Tree"]["fields"].items() if on}


def test_build_type_aliases_resolve_the_names_the_builder_already_uses():
    assert builder.resolve_build_type("Arrangement")["label"] == "Floral Arrangement"
    assert builder.resolve_build_type("Drop-in Arrangement")["label"] == "Drop-in"
    assert builder.resolve_build_type("tree")["label"] == "Tree"
    assert builder.resolve_build_type("plant_bush")["label"] == "Plant & Bush"
    assert builder.resolve_build_type("Nonsense") is None
    assert builder.resolve_build_type(None) is None


def test_build_types_surface_the_unlabelled_blank_sheets_rather_than_hiding_them(stub_corpus):
    assert _run(builder.get_build_types())["unlabelled_recipes"] == 1


# ─── Common builds ───────────────────────────────────────────────────────────


def test_common_builds_prefill_every_step_1_field(stub_corpus):
    result = _run(builder.get_common_builds(build_type="Tree", species="Fiddle"))
    build = result["builds"][0]
    assert build["recipe_count"] == 2            # the two 7' Fiddles recur
    assert build["height_display"] == "7'"
    assert build["width_in"] == 44.0             # median of 42 and 46
    assert build["canopy_tier"] == "M"
    assert build["pieces"] == 6
    assert build["typical_component_cost"] == 500.0
    assert build["silhouette"] == "full_round"
    assert build["item_codes"]


def test_common_builds_are_ordered_by_recurrence(stub_corpus):
    counts = [b["recipe_count"] for b in _run(builder.get_common_builds())["builds"]]
    assert counts == sorted(counts, reverse=True)


def test_common_builds_exclude_the_junk_sheets(stub_corpus):
    """A blank sheet and a valueless one must never be suggested as a build."""
    builds = _run(builder.get_common_builds())["builds"]
    assert all(b["build_type"] for b in builds)
    assert "TT9-9522" not in {code for b in builds for code in b["item_codes"]}
    assert not any(b["name"] == "Bay Leaf Topiary" for b in builds)
    assert not any("TEMPLATE" in (b["name"] or "") for b in builds)
    assert _run(builder.get_common_builds())["excluded_recipes"] == 2


def test_common_builds_filter_and_page(stub_corpus):
    assert _run(builder.get_common_builds(species="Areca"))["total"] == 1
    assert _run(builder.get_common_builds(build_type="Plant & Bush"))["total"] == 1
    page = _run(builder.get_common_builds(limit=1))
    assert len(page["builds"]) == 1 and page["total"] > 1
    assert _run(builder.get_common_builds(limit=0))["limit"] == 1
    assert _run(builder.get_common_builds(limit=10_000))["limit"] == 100


def test_common_builds_reject_unknown_filters(stub_corpus):
    for kwargs in ({"build_type": "Nope"}, {"species": "Nope"}):
        with pytest.raises(Exception) as excinfo:
            _run(builder.get_common_builds(**kwargs))
        assert getattr(excinfo.value, "status_code", None) == 400


# ─── Scope filters ───────────────────────────────────────────────────────────


def test_container_slot_surfaces_containers_and_excludes_dried_botanicals(stub_corpus):
    result = _run(builder.get_scope_filters(slot="Container"))
    slot = result["slots"][0]
    assert slot["slot"] == "container"
    categories = [c["value"] for c in slot["filters"]["categories"]]
    assert categories[0] == "Containers & Vases"
    assert "Botanicals & Fillers" in slot["exclude_categories"]
    # ...and the terms are the shop's own container words, not free text.
    assert "zinc container" in {t["term"] for t in slot["search_terms"]}


def test_top_dressing_vocabulary_is_derived_from_real_usage(stub_corpus):
    slot = _run(builder.get_scope_filters(slot="top_dressing"))["slots"][0]
    terms = {t["term"] for t in slot["search_terms"]}
    # Every one of these is in the fixture's mechanics lines, none is typed in.
    assert {"sheet moss", "foam"} <= terms
    assert all(t["source"] == "derived" for t in slot["search_terms"])
    # The sheets' own section heading is not product vocabulary.
    assert "mechanics" not in terms and "top dressing mechanics" not in terms


def test_terms_are_unchecked_not_condemned_when_the_catalog_index_is_cold(stub_corpus):
    """`null` means "we couldn't check", which is not the same as "no match"."""
    slot = _run(builder.get_scope_filters(slot="top_dressing"))["slots"][0]
    assert all(t["catalog_verified"] is None for t in slot["search_terms"])


def test_a_warm_catalog_index_demotes_terms_that_match_nothing(stub_corpus, monkeypatch):
    """A phrase the shop writes can still find no product — it must not lead."""
    monkeypatch.setattr(builder, "_catalog_index",
                        lambda: [{"blob": "supermoss sheet moss green bag"}])
    monkeypatch.setattr(builder, "_TERM_VERDICT", {"products_ts": None, "verified": {}})
    terms = _run(builder.get_scope_filters(slot="top_dressing"))["slots"][0]["search_terms"]
    by_term = {t["term"]: t for t in terms}
    assert by_term["sheet moss"]["catalog_verified"] is True
    assert by_term["foam"]["catalog_verified"] is False
    # Matching terms lead, so a pre-applied filter always returns products —
    # even though `foam` outweighs `sheet moss` in the recipe history.
    verified = [t["term"] for t in terms if t["catalog_verified"]]
    assert [t["term"] for t in terms][:len(verified)] == verified
    assert "sheet moss" in verified and "foam" not in verified
    # The unmatched vocabulary is still returned, just not leading.
    assert "foam" in by_term


def test_scope_filters_are_weighted_suggestions_not_mandates(stub_corpus):
    result = _run(builder.get_scope_filters())
    assert result["contract"]["mandatory"] is False
    assert result["contract"]["removable"] is True
    assert result["searchable_via"] == "/api/products/search"
    for slot in result["slots"]:
        for entry in slot["search_terms"]:
            assert 0 < entry["weight"] <= 1
        for entry in slot["filters"]["categories"]:
            assert 0 < entry["weight"] <= 1


def test_scope_filters_return_every_scope_by_default(stub_corpus):
    slots = {s["slot"] for s in _run(builder.get_scope_filters())["slots"]}
    assert slots == set(builder.SLOT_CLASSES)


def test_a_build_types_own_slot_label_resolves_to_a_scope():
    assert builder._resolve_slot("Finish/Top Dressing") == "top_dressing"
    assert builder._resolve_slot("Drop-in Base") == "container"
    assert builder._resolve_slot("Leaves") == "plant_material"
    assert builder._resolve_slot("Trunks & Branches") == "trunks"
    assert builder._resolve_slot("top_dressing") == "top_dressing"
    assert builder._resolve_slot("Top Dressing") == "top_dressing"
    assert builder._resolve_slot("nonsense") is None
    assert builder._resolve_slot(None) is None


def test_scope_filters_narrow_to_the_slots_a_build_type_has(stub_corpus):
    slots = {s["slot"] for s in
             _run(builder.get_scope_filters(build_type="Container Only"))["slots"]}
    assert slots == {"top_dressing", "container"}


def test_scope_filters_reject_an_unknown_slot(stub_corpus):
    with pytest.raises(Exception) as excinfo:
        _run(builder.get_scope_filters(slot="Vibes"))
    assert getattr(excinfo.value, "status_code", None) == 400


# ─── Slot classification ─────────────────────────────────────────────────────


def test_a_fiddle_leaf_branch_is_foliage_but_a_dragonwood_pole_is_a_trunk():
    """Both say "wood"/"branch"; only one is the canopy."""
    assert builder.classify_slot("product", '34" Fiddle Leaf Branch') == "plant_material"
    assert builder.classify_slot("product", "Dragonwood 8-10' / 1-2''") == "trunks"
    assert builder.classify_slot("product", "6' Hard Maple") == "trunks"


def test_the_sheets_own_container_section_wins_over_the_text():
    assert builder.classify_slot("container", "19x19x19 LG") == "container"
    assert builder.classify_slot("mechanics", "foam, moss") == "top_dressing"
    assert builder.classify_slot("mechanics", "mixed buff moon rock") == "top_dressing"
    assert builder.classify_slot("product", "Zinc 15.7\"X15.7\"") == "container"
    assert builder.classify_slot("product", "something unrecognisable") == "other"


# ─── Caching ─────────────────────────────────────────────────────────────────


def test_the_corpus_is_loaded_once_and_reused(stub_corpus, monkeypatch):
    """A warm request must not touch the database — these run on every step."""
    calls = {"n": 0}
    original = builder._fetch_corpus_rows

    async def counting(conn):
        calls["n"] += 1
        return await original(conn)

    monkeypatch.setattr(builder, "_fetch_corpus_rows", counting)
    _run(builder.get_build_types())
    _run(builder.get_species())
    _run(builder.get_density(species="Fiddle", height="7'"))
    assert calls["n"] == 1


def test_measured_percentiles_travel_with_the_spec_constants(stub_corpus):
    """A drift alarm: the served cut points are checked against live data."""
    data = _run(builder.corpus())
    for band in builder.CANOPY_TIERS:
        measured = data["canopy"][band]
        assert set(measured) >= {"n", "p20", "p40", "p60", "p80", "median", "min", "max"}
    # With 3+ trees in a band the check runs; with fewer it abstains rather than
    # claiming agreement it can't test.
    assert builder._spec_matches(builder.CANOPY_TIERS["7-9'"], data["canopy"]["7-9'"]) is not None
    assert builder._spec_matches(builder.CANOPY_TIERS["9'+"], data["canopy"]["9'+"]) is None
