"""Tests for the designs library API.

Two things are worth locking down here, and neither needs a database:

* the **legacy/normalised dual read** — designs were historically JSON-encoded
  into the `label` column, and the parsers that recover them must never raise
  on a malformed blob, only degrade;
* the **drill-down facet contract** — a facet must ignore its own selection
  while respecting every other one. Getting this backwards silently collapses
  the sidebar to a single option, which looks like working software.

The listing test drives the real endpoint with a stubbed loader, so it exercises
the actual filter/facet/sort code rather than a copy of it.
"""

import asyncio

import pytest

from app.apis import designs


# ─── Legacy label decoding ───────────────────────────────────────────────────


def test_parse_scope_label_decodes_legacy_design():
    label = (
        'LL_SCOPE:{"label":"QA Fiddle Fig","room_id":16,"bucket_type":"Tree",'
        '"requested_quantity":2,"scope_notes":"Room test"}'
    )
    scope = designs.parse_scope_label(label)
    assert scope["label"] == "QA Fiddle Fig"
    assert scope["room_id"] == 16
    assert scope["bucket_type"] == "Tree"


def test_parse_room_label_decodes_legacy_group():
    assert designs.parse_room_label('LL_ROOM:{"name":"QA Room","notes":"Smoke test"}') == {
        "name": "QA Room",
        "notes": "Smoke test",
    }


def test_label_parsers_return_empty_for_plain_and_malformed_labels():
    # A normalised label is plain text, not an encoded blob.
    assert designs.parse_scope_label("Fiddle Fig trees") == {}
    assert designs.parse_room_label("Living room") == {}
    assert designs.parse_scope_label(None) == {}
    # Truncated / non-object JSON must degrade, never raise.
    assert designs.parse_scope_label('LL_SCOPE:{"label":"Tree"') == {}
    assert designs.parse_scope_label("LL_SCOPE:[1,2,3]") == {}
    assert designs.parse_room_label("LL_ROOM:not json at all") == {}


# ─── Build-intelligence blob ─────────────────────────────────────────────────


BUILD_INTELLIGENCE = (
    "Height: 7\nCanopy size: full\n"
    'LL_BUILD_INTELLIGENCE:{"build_type":"Tree","confidence":"high","components":['
    '{"label":"Moss / Fiber","examples":["Sheet Moss","Rocks"],"search_terms":["Moss / Fiber"]},'
    '{"label":"Trunks & Branches","examples":["30\\" Fiddle Leaf Branch"],"search_terms":[]}]}'
)


def test_parse_build_intelligence_reads_components_out_of_scope_notes():
    intel = designs.parse_build_intelligence(BUILD_INTELLIGENCE)
    assert intel["build_type"] == "Tree"
    assert [c["label"] for c in intel["components"]] == ["Moss / Fiber", "Trunks & Branches"]


def test_parse_build_intelligence_tolerates_trailing_text_after_the_object():
    intel = designs.parse_build_intelligence(
        'LL_BUILD_INTELLIGENCE:{"build_type":"Wreath","components":[]}\ntrailing note'
    )
    assert intel["build_type"] == "Wreath"


def test_parse_build_intelligence_never_raises_on_a_bad_blob():
    for bad in (None, "", "no marker here", "LL_BUILD_INTELLIGENCE:", "LL_BUILD_INTELLIGENCE:{oops",
                'LL_BUILD_INTELLIGENCE:{"components":[1,2', "LL_BUILD_INTELLIGENCE:null"):
        assert designs.parse_build_intelligence(bad) == {}


def test_strip_build_intelligence_keeps_only_the_human_half():
    assert designs.strip_build_intelligence(BUILD_INTELLIGENCE) == "Height: 7\nCanopy size: full"
    assert designs.strip_build_intelligence("LL_BUILD_INTELLIGENCE:{}") is None
    assert designs.strip_build_intelligence(None) is None


# ─── Materials vocabulary ────────────────────────────────────────────────────


def test_clean_material_rejects_junk_and_placeholder_labels():
    assert designs._clean_material("  Moss / Fiber  ") == "Moss / Fiber"
    # Numeric noise leaks in from vendor lists in the intelligence blob.
    assert designs._clean_material("1.2") is None
    assert designs._clean_material("6.0") is None
    assert designs._clean_material("") is None
    assert designs._clean_material(None) is None
    # Catch-all labels match everything and mean nothing.
    assert designs._clean_material("Other") is None
    assert designs._clean_material("products") is None


def test_material_key_folds_plurals_so_one_facet_entry_covers_both():
    assert designs._material_key("Container") == designs._material_key("Containers")
    assert designs._material_key("Moss / Fiber") == designs._material_key("moss fiber")
    # Words that merely end in 's' are not plurals — no over-eager stemming.
    assert designs._material_key("Moss") != designs._material_key("Mos")
    assert designs._material_key("Cactus") != designs._material_key("Cactu")


def test_materials_come_from_components_while_examples_stay_searchable():
    """Component labels are the facet vocabulary; examples are search-only.

    Folding examples into `materials` would put thousands of one-off SKU names
    into the sidebar, so they must reach the search blob and nothing else.
    """
    intel = designs.parse_build_intelligence(BUILD_INTELLIGENCE)
    materials, terms = designs._materials_for({"build_type": "Tree"}, [], intel, {})
    assert materials == ["Moss / Fiber", "Trunks & Branches"]
    assert "Sheet Moss" in terms and "Rocks" in terms
    assert "Sheet Moss" not in materials


def test_materials_fold_in_saved_parts_and_historical_recipes():
    part = {
        "product_name": "10 Inch Honey Moss Mat",
        "sku": "AR-122330",
        "_material_hints": ["Top Dressing", "Containers", None, "Other", "Polyester"],
    }
    recipes = {"tree": {"Ornaments", "Ribbon"}}
    materials, terms = designs._materials_for({"build_type": "Tree"}, [part], {}, recipes)
    assert "Top Dressing" in materials and "Polyester" in materials
    assert "Ornaments" in materials and "Ribbon" in materials  # from the recipe library
    assert "Other" not in materials
    assert "10 Inch Honey Moss Mat" in terms


def test_recipe_materials_are_skipped_when_the_library_is_empty():
    materials, _ = designs._materials_for({"build_type": "Tree"}, [], {}, {})
    assert materials == []


# ─── Listing: filters, facets, sorting ───────────────────────────────────────


def _design(id, name, client, project, group, build_type, materials, cost=0.0, day=1):
    from datetime import datetime, timezone
    return {
        "id": id, "name": name, "build_type": build_type, "status": "draft",
        "client_name": client, "project_id": 1, "project_name": project,
        "group_id": 1, "group_name": group, "item_count": 0, "total_cost": cost,
        "hero_image_url": None, "updated_at": f"2026-01-0{day}T00:00:00+00:00",
        "materials": materials,
        "_sort_dt": datetime(2026, 1, day, tzinfo=timezone.utc),
        "_parts": [], "_quantity": 1, "_scope_notes": None, "_intel": {},
        "_blob": " ".join([name, client, project, group, build_type] + materials).lower(),
    }


FIXTURE = [
    _design(1, "Moss Tree", "Acme", "Villa", "Living room", "Tree",
            ["Moss / Fiber", "Container"], cost=300.0, day=3),
    _design(2, "Bare Tree", "Acme", "Villa", "Foyer", "Tree", ["Container"], cost=100.0, day=2),
    _design(3, "Holiday Wreath", "Beta", "Lodge", "Foyer", "Wreath",
            ["Ornaments", "Moss / Fiber"], cost=200.0, day=1),
]


@pytest.fixture
def stub_library(monkeypatch):
    """Serve the endpoint a fixed library, with no database involved."""
    async def fake_conn():
        class _Conn:
            async def close(self):
                return None
        return _Conn()

    async def fake_load(_conn):
        return [dict(d) for d in FIXTURE]

    monkeypatch.setattr(designs, "get_conn", fake_conn)
    monkeypatch.setattr(designs, "_load_designs", fake_load)


def _list(**kwargs):
    return asyncio.run(designs.list_designs(**kwargs))


def test_list_returns_every_design_and_all_facets(stub_library):
    result = _list()
    assert result["total"] == 3
    assert {i["id"] for i in result["items"]} == {1, 2, 3}
    assert set(result["facets"]) == {"clients", "projects", "groups", "build_types", "materials"}
    assert result["facets"]["clients"] == [{"value": "Acme", "count": 2}, {"value": "Beta", "count": 1}]
    # Multi-valued: a design counts toward every material it is made of.
    assert {f["value"]: f["count"] for f in result["facets"]["materials"]} == {
        "Container": 2, "Moss / Fiber": 2, "Ornaments": 1,
    }


def test_material_filter_answers_the_made_of_question(stub_library):
    result = _list(materials="Moss / Fiber")
    assert {i["id"] for i in result["items"]} == {1, 3}


def test_multi_select_within_a_facet_is_a_union(stub_library):
    assert _list(build_types="Tree,Wreath")["total"] == 3


def test_facets_drill_down_ignoring_their_own_selection(stub_library):
    """Picking one client must not collapse the client list to that client."""
    result = _list(clients="Acme")
    assert result["total"] == 2
    # Own facet: still offers Beta, so a second client can be added.
    assert {f["value"] for f in result["facets"]["clients"]} == {"Acme", "Beta"}
    # Other facets: narrowed to the current query.
    assert {f["value"] for f in result["facets"]["build_types"]} == {"Tree"}
    assert {f["value"] for f in result["facets"]["groups"]} == {"Living room", "Foyer"}


def test_other_selections_still_constrain_a_facets_own_counts(stub_library):
    """The materials facet ignores materials, but still respects build_types."""
    result = _list(build_types="Tree", materials="Moss / Fiber")
    assert {i["id"] for i in result["items"]} == {1}
    materials = {f["value"] for f in result["facets"]["materials"]}
    assert "Container" in materials       # the other Tree's material is still offered
    assert "Ornaments" not in materials   # belongs to the excluded Wreath


def test_search_matches_across_every_field_and_ands_its_words(stub_library):
    assert {i["id"] for i in _list(search="moss")["items"]} == {1, 3}
    assert {i["id"] for i in _list(search="villa")["items"]} == {1, 2}
    assert {i["id"] for i in _list(search="moss villa")["items"]} == {1}
    assert _list(search="nonexistent")["total"] == 0


def test_search_narrows_the_facets_too(stub_library):
    assert {f["value"] for f in _list(search="wreath")["facets"]["clients"]} == {"Beta"}


def test_sorting_and_paging(stub_library):
    assert [i["id"] for i in _list(sort="recent")["items"]] == [1, 2, 3]
    assert [i["name"] for i in _list(sort="name")["items"]][0] == "Bare Tree"
    assert [i["id"] for i in _list(sort="cost")["items"]] == [1, 3, 2]
    assert [i["build_type"] for i in _list(sort="type")["items"]][0] == "Tree"
    # An unknown sort falls back to `recent` rather than erroring.
    assert [i["id"] for i in _list(sort="bogus")["items"]] == [1, 2, 3]

    page = _list(limit=2)
    assert len(page["items"]) == 2 and page["total"] == 3
    assert [i["id"] for i in _list(limit=2, offset=2)["items"]] == [3]


def test_limit_is_clamped_to_a_sane_range(stub_library):
    assert _list(limit=10_000)["limit"] == designs.MAX_LIMIT
    assert _list(limit=0)["limit"] == 1
    assert _list(offset=-5)["offset"] == 0


def test_csv_filters_tolerate_whitespace_and_empties(stub_library):
    assert designs._csv_list(" a , b ,, c ") == ["a", "b", "c"]
    assert designs._csv_list("") == [] and designs._csv_list(None) == []
    assert _list(clients=" Acme , ")["total"] == 2


def test_filters_are_case_insensitive(stub_library):
    assert _list(build_types="tree")["total"] == 2
    assert _list(materials="moss / fiber")["total"] == 2


def test_items_expose_exactly_the_frontend_contract(stub_library):
    item = _list()["items"][0]
    assert set(item) == {
        "id", "name", "build_type", "status", "client_name", "project_id", "project_name",
        "group_id", "group_name", "item_count", "total_cost", "hero_image_url", "materials",
        "updated_at",
    }
    # Internal working fields never leak to the client.
    assert not any(k.startswith("_") for k in item)
