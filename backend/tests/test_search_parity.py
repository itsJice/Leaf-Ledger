"""Catalog search parity — the invariants both search paths owe the frontend.

``/products/search`` is served two ways: an in-memory index of the whole catalog
(the reference implementation, and the thing that OOM-kills production) and the
same search answered from Postgres. The index can only be deleted once the SQL
path gives the same answers, so the answers have to be written down.

This file runs in CI with **no database**. It pins the contract in two halves:

* **the reference semantics**, exercised by driving the real ``search_products``
  endpoint with a stubbed in-memory index — drill-down facets, exact-SKU
  behaviour, typo tolerance, ranking, pagination, empty results. Whatever the SQL
  path is rewritten to do, *these* are the answers it has to reproduce;
* **the path-independent response contract**, exercised by driving the same
  endpoint with a stubbed connection — the capped-total semantics, and the
  guarantee that a warm index answers without opening a connection at all.

Whether the live SQL implementation actually produces these facet counts is a
question only a real database can answer: that is ``scripts/check_search_parity.py``.
The classifier that script uses to sort real differences into acceptable-vs-defect
is unit-tested at the bottom of this file, so the gate itself is not guesswork.
"""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

import pytest

from app.apis import products


# ─── Fixture catalog ─────────────────────────────────────────────────────────
# Rows are shaped exactly like _build_search_index emits them.


def _row(id, name, sku, price, category, colors, size, finish, avail, supplier_id,
         supplier_name, product_type, description=""):
    return {
        "id": id, "name": name, "supplier_name": supplier_name, "supplier_id": supplier_id,
        "supplier_sku": sku, "price": price, "image": f"http://img/{id}.jpg",
        "images": [f"http://img/{id}.jpg"], "class": "test", "color": (colors[0] if colors else None),
        "finish": finish, "size": size,
        "size_bucket": (f"{round(size * 2) / 2:g}" if size is not None else None),
        "product_type": product_type, "color_families": colors, "category": category,
        "avail": avail,
        "blob": products._build_blob(name, sku, description, supplier_name, product_type),
    }


CATALOG = [
    _row(1, "Green Moss Wreath", "AC-100", 20.0, "Wreaths", ["Green"], 12.0, "Matte",
         "In stock", 1, "Acme", "Wreath"),
    _row(2, "Red Moss Ball", "AC-101", 5.0, "Ornaments", ["Red"], 4.0, "Glitter",
         "In stock", 1, "Acme", "Ball Ornament"),
    _row(3, "Green Fiddle Leaf Tree", "N590321-2", 150.0, "Trees", ["Green"], 30.0, "Natural",
         "Out of stock", 2, "Beta", "Tree"),
    _row(4, "Green Wreath Deluxe", "N590321-20", 60.0, "Wreaths", ["Green", "Gold"], 24.0, "Matte",
         "In stock", 2, "Beta", "Wreath"),
    _row(5, "Blue Ornament Set", "124394892", 8.0, "Ornaments", ["Blue"], 4.0, "Shiny",
         "In stock", 1, "Acme", "Ball Ornament"),
    # Supplier data with a typo in the *description* — the fuzzy-ranking fixture.
    # The vocabulary is built from product NAMES, so "ornamnet" is not a known
    # word: a search for it is corrected to "ornament", yet this row also matches
    # it literally.
    _row(6, "Holiday Bundle", "AC-102", 12.0, "Ornaments", ["Blue"], 4.0, "Shiny",
         "In stock", 1, "Acme", "Ball Ornament", description="ornamnet assortment"),
    # size 0 is the noise bucket the size facet must drop.
    _row(7, "Flat Backdrop", "AC-103", 3.0, "Wreaths", ["Green"], 0.0, "Matte",
         "In stock", 1, "Acme", "Backdrop"),
]

NAMES = {r["id"]: r["name"] for r in CATALOG}


@pytest.fixture
def warm_index(monkeypatch):
    """A ready in-memory index, and a connection that explodes if anyone opens one."""
    monkeypatch.setattr(products, "_INDEX_ENABLED", True)
    monkeypatch.setattr(products, "_SEARCH_CACHE", {"ts": time.time(), "rows": [dict(r) for r in CATALOG]})
    monkeypatch.setattr(products, "_VOCAB_CACHE", {"ts": -1.0, "vocab": None})

    async def no_db():
        raise AssertionError("the warm index path must not open a database connection")

    monkeypatch.setattr(products, "get_conn", no_db)


def search(**kwargs):
    return asyncio.run(products.search_products(**kwargs))


def ids(result):
    return [item["id"] for item in result["items"]]


def facet(result, dim):
    return {f["value"]: f["count"] for f in result["facets"][dim]}


# ─── Browse, pagination, empty results ───────────────────────────────────────


def test_unfiltered_browse_returns_everything_in_name_order(warm_index):
    result = search()
    assert result["total"] == len(CATALOG)
    assert [NAMES[i] for i in ids(result)] == sorted(NAMES.values(), key=str.lower)
    assert result["limit"] == 48 and result["offset"] == 0


def test_pagination_walks_the_same_order_without_gaps_or_repeats(warm_index):
    """Offset paging is only safe if the underlying order is stable — the whole
    reason a browse-order difference between the two paths is a defect."""
    full = ids(search(limit=100))
    pages = [ids(search(limit=3, offset=off)) for off in (0, 3, 6)]
    assert pages[0] + pages[1] + pages[2] == full
    assert search(limit=3, offset=6)["total"] == len(CATALOG)  # total is of the whole match
    assert ids(search(limit=3, offset=999)) == []


def test_facets_are_built_only_on_the_first_page(warm_index):
    assert "facets" in search(offset=0)
    assert "facets" not in search(offset=48)


def test_a_query_that_matches_nothing_returns_an_empty_page_and_empty_facets(warm_index):
    result = search(search="zzqqxnothingmatchesthis")
    assert result["total"] == 0 and result["items"] == []
    assert set(result["facets"]) == {"categories", "colors", "sizes", "finishes",
                                     "availability", "product_types", "suppliers"}
    assert all(v == [] for v in result["facets"].values())


def test_an_empty_ids_filter_means_nothing_selected_not_no_filter(warm_index):
    """``ids=`` is what an empty Favourites list sends. It must return nothing —
    treating it as "no filter" would show the user the entire catalog."""
    assert search(ids="")["total"] == 0
    assert search(ids=None)["total"] == len(CATALOG)


# ─── Filters ─────────────────────────────────────────────────────────────────


def test_column_backed_filters(warm_index):
    assert set(ids(search(price_min=10, price_max=60))) == {1, 4, 6}
    assert set(ids(search(supplier_ids="2"))) == {3, 4}
    assert set(ids(search(supplier_ids="1,2"))) == {r["id"] for r in CATALOG}
    assert set(ids(search(ids="1,3,5"))) == {1, 3, 5}
    assert set(ids(search(ids="3,5", price_min=100))) == {3}


def test_price_filters_exclude_products_with_no_price(warm_index, monkeypatch):
    rows = [dict(r) for r in CATALOG]
    rows[0]["price"] = None
    monkeypatch.setattr(products, "_SEARCH_CACHE", {"ts": time.time(), "rows": rows})
    assert 1 not in ids(search(price_min=0))
    assert 1 in ids(search())


def test_multi_select_within_a_dimension_is_a_union(warm_index):
    assert set(ids(search(categories="Wreaths,Trees"))) == {1, 3, 4, 7}


def test_selections_across_dimensions_are_an_intersection(warm_index):
    assert set(ids(search(categories="Wreaths", colors="Gold"))) == {4}


def test_colors_are_multi_valued(warm_index):
    """A product belongs to every colour family it carries."""
    assert set(ids(search(colors="Gold"))) == {4}
    assert set(ids(search(colors="Green"))) == {1, 3, 4, 7}


# ─── Keyword matching ────────────────────────────────────────────────────────


def test_keyword_search_ands_its_terms(warm_index):
    assert set(ids(search(search="moss"))) == {1, 2}
    assert set(ids(search(search="green"))) == {1, 3, 4}
    assert set(ids(search(search="green wreath"))) == {1, 4}


def test_keyword_search_reaches_beyond_the_name(warm_index):
    """The blob folds in sku, description, supplier and the searchable raw_data
    values. The SQL path only searches name/description/supplier_sku, so this is
    the recall difference the live harness is looking for."""
    assert 5 in ids(search(search="acme"))          # supplier name
    assert set(ids(search(search="ball ornament"))) == {2, 5, 6}   # product type


def test_facets_narrow_to_the_search(warm_index):
    assert set(facet(search(search="moss"), "categories")) == {"Wreaths", "Ornaments"}
    assert facet(search(search="moss"), "colors") == {"Green": 1, "Red": 1}


# ─── Exact SKU ───────────────────────────────────────────────────────────────


def test_an_exact_sku_finds_its_product(warm_index):
    assert ids(search(search="124394892")) == [5]
    assert 3 in ids(search(search="N590321-2"))


def test_a_sku_is_never_fuzzy_matched_to_a_different_sku(warm_index):
    """A SKU is an identifier, not a word. Typo correction must not fire on it —
    otherwise a one-character-off SKU silently returns somebody else's product."""
    assert ids(search(search="124394893")) == []      # one digit off → no results, not product 5
    assert ids(search(search="AC-1000")) == []


@pytest.mark.xfail(
    reason="KNOWN DEFECT (products API, not this harness): both paths match SKUs with a "
           "substring/ILIKE test, so searching N590321-2 also returns N590321-20 — a different "
           "product. Fixing it needs an exact-identifier branch in the products API, which this "
           "harness does not own. Flips to XPASS when that lands.",
)
def test_a_sku_query_does_not_return_a_longer_sku_that_contains_it(warm_index):
    assert ids(search(search="N590321-2")) == [3]


# ─── Typo tolerance and ranking ──────────────────────────────────────────────


def test_a_misspelling_still_finds_the_product(warm_index):
    assert set(ids(search(search="wreth"))) == {1, 4, 7} - {7}   # 7 has no "wreath" in its blob


def test_a_correctly_spelled_word_is_not_expanded(warm_index):
    """Words in the vocabulary skip fuzzy expansion entirely — that is what keeps
    a correct query both fast and precise."""
    assert set(ids(search(search="tree"))) == {3}


def test_exact_matches_rank_ahead_of_fuzzy_ones(warm_index):
    """Product 6 carries the literal misspelling; products 5 and 2 only match once
    "ornamnet" is corrected to "ornament". Alphabetically 5 sorts first, so this
    ordering is proof the relevance score is applied before the name sort."""
    assert set(ids(search(search="ornamnet"))) == {2, 5, 6}
    assert ids(search(search="ornamnet"))[:2] == [6, 5]


def test_a_misspelling_that_the_catalog_itself_contains_is_taken_literally(warm_index,
                                                                          monkeypatch):
    """Typo correction only fires for words the catalog's *names* do not contain.
    Once a misspelling is a real product name, it is a word, and the search is
    exact — worth knowing before assuming every near-miss gets corrected."""
    rows = [dict(r) for r in CATALOG]
    rows[5]["name"] = "Ornamnet Bundle"
    rows[5]["blob"] = products._build_blob("Ornamnet Bundle", "AC-102", "", "Acme", "Ball Ornament")
    monkeypatch.setattr(products, "_SEARCH_CACHE", {"ts": time.time(), "rows": rows})
    monkeypatch.setattr(products, "_VOCAB_CACHE", {"ts": -1.0, "vocab": None})
    assert ids(search(search="ornamnet")) == [6]


def test_fuzzy_expansion_takes_only_the_closest_spellings():
    vocab = {"wreath", "weather", "breath"}
    assert products._fuzzy_variants("wreathe", vocab, 2) == ["wreath"]
    # A transposition is one edit, not two — the commonest real typo.
    assert products._bounded_distance("ornamnet", "ornament", 2) == 1
    assert products._bounded_distance("moss", "tree", 2) is None


# ─── Drill-down facets ───────────────────────────────────────────────────────


def test_every_facet_dimension_is_counted_on_an_unfiltered_browse(warm_index):
    result = search()
    assert facet(result, "categories") == {"Wreaths": 3, "Ornaments": 3, "Trees": 1}
    assert facet(result, "colors") == {"Green": 4, "Blue": 2, "Gold": 1, "Red": 1}
    assert facet(result, "finishes") == {"Matte": 3, "Shiny": 2, "Glitter": 1, "Natural": 1}
    assert facet(result, "availability") == {"In stock": 6, "Out of stock": 1}
    assert facet(result, "product_types") == {"Ball Ornament": 3, "Wreath": 2, "Backdrop": 1, "Tree": 1}
    assert facet(result, "suppliers") == {"Acme": 5, "Beta": 2}
    assert [f["id"] for f in result["facets"]["suppliers"]] == [1, 2]


def test_a_facet_ignores_its_own_selection_so_it_can_still_be_widened(warm_index):
    """Getting this backwards collapses the sidebar to the one value the user
    picked, which looks like working software and quietly ends their session."""
    result = search(colors="Green")
    assert set(ids(result)) == {1, 3, 4, 7}
    assert facet(result, "colors") == {"Green": 4, "Blue": 2, "Gold": 1, "Red": 1}


def test_other_selections_still_constrain_a_facets_own_counts(warm_index):
    """colors is counted ignoring colors — but still inside categories=Wreaths."""
    result = search(colors="Green", categories="Wreaths")
    assert set(ids(result)) == {1, 4, 7}
    assert facet(result, "colors") == {"Green": 3, "Gold": 1}   # Red/Blue are Ornaments
    assert facet(result, "categories") == {"Wreaths": 3, "Trees": 1}  # own dim ignored, Green applies
    assert "Ornaments" not in facet(result, "categories")


def test_search_and_price_constrain_every_facet_including_its_own(warm_index):
    """search/price/ids are not facet dimensions, so they narrow everything."""
    result = search(search="green", colors="Gold")
    assert set(ids(result)) == {4}
    assert facet(result, "colors") == {"Green": 3, "Gold": 1}
    assert facet(result, "categories") == {"Wreaths": 1}


def test_facet_ordering_is_deterministic(warm_index):
    """Counts descending, then the value itself — so there are no ties left and
    any ordering difference between the two paths is a real bug."""
    values = [f["value"] for f in search()["facets"]["finishes"]]
    assert values == ["Matte", "Shiny", "Glitter", "Natural"]


def test_sizes_are_ordered_numerically_and_drop_the_zero_bucket(warm_index):
    sizes = search()["facets"]["sizes"]
    assert [f["value"] for f in sizes] == ["4", "12", "24", "30"]   # not "12" < "24" < "30" < "4"
    assert all(f["value"] != "0" for f in sizes)


def test_item_payload_is_the_frontend_contract(warm_index):
    item = search(ids="5")["items"][0]
    assert set(item) == {"id", "name", "supplier_name", "supplier_sku", "current_price",
                         "image_urls", "raw_data"}
    assert set(item["raw_data"]["normalized"]) == {"color", "finish", "size_in", "class"}
    assert item["raw_data"]["normalized"]["size_in"] == 4.0


# ─── Path-independent response contract (stubbed connection) ─────────────────


class FakeConn:
    """Enough asyncpg surface for the SQL path, with no database behind it."""

    def __init__(self, rows=(), count=0):
        self._rows = list(rows)
        self._count = count
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        # First fetch is the page; anything after it (facet passes) gets nothing,
        # because facet correctness needs a real engine — that is the live script.
        return self._rows if len([c for c in self.calls if c[0] == "fetch"]) == 1 else []

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        return self._count

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        return None

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        return ""

    async def close(self):
        return None

    @property
    def bound(self):
        """Every argument value handed to the database this request."""
        return [a for _, _, args in self.calls for a in args]


DB_ROW = {
    "id": 5, "name": "Blue Ornament Set", "supplier_name": "Acme", "supplier_sku": "124394892",
    "current_price": 8.0, "image_urls": ["http://img/5.jpg"], "photo_url": None,
    "raw_data": {"normalized": {"color": "Blue", "finish": "Shiny", "size_in": 4.0, "class": "test"}},
}


@pytest.fixture
def sql_path(monkeypatch):
    """Force the SQL path and hand it a stub connection. Returns the stub."""
    conn = FakeConn()

    async def fake_conn():
        return conn

    monkeypatch.setattr(products, "_INDEX_ENABLED", False)
    monkeypatch.setattr(products, "_SEARCH_CACHE", {"ts": 0.0, "rows": None})
    monkeypatch.setattr(products, "get_conn", fake_conn)
    return conn


def test_disabling_the_index_never_reads_the_catalog(sql_path):
    """SEARCH_INDEX_ENABLED=0 is the OOM escape hatch: it must not trigger the
    background build, or the process re-reads the whole catalog anyway."""
    sql_path._count = 0
    search()
    assert products._index_ready() is False
    assert products._SEARCH_CACHE["rows"] is None
    assert not any("jsonb_each_text" in sql for _, sql, _ in sql_path.calls)


def test_sql_path_reports_an_exact_total_below_the_cap(sql_path):
    sql_path._rows, sql_path._count = [DB_ROW], 12
    result = search()
    assert result["total"] == 12
    assert result["total_is_capped"] is False
    assert [i["id"] for i in result["items"]] == [5]


def test_sql_path_caps_the_total_instead_of_counting_the_catalog(sql_path):
    """Above the cap the SQL path answers "at least N" rather than paying for a
    full scan. The frontend renders it as "5000+"; parity therefore cannot demand
    an exact count above the cap."""
    sql_path._rows, sql_path._count = [DB_ROW], products._DB_COUNT_CAP + 1
    result = search()
    assert result["total"] == products._DB_COUNT_CAP
    assert result["total_is_capped"] is True


def test_sql_path_exposes_the_same_page_contract(sql_path):
    sql_path._rows, sql_path._count = [DB_ROW], 1
    result = search(limit=48, offset=0)
    assert {"items", "total", "limit", "offset"} <= set(result)
    item = result["items"][0]
    assert {"id", "name", "supplier_name", "supplier_sku", "current_price",
            "image_urls", "raw_data"} <= set(item)
    assert set(item["raw_data"]["normalized"]) == {"color", "finish", "size_in", "class"}


def test_sql_path_binds_the_column_backed_filters(sql_path):
    """Implementation-agnostic: whatever SQL it builds, the user's price, supplier
    and id selections have to reach the database as bound parameters."""
    sql_path._count = 0
    search(search="moss", price_min=5, price_max=40, supplier_ids="2,3", ids="1,2,3")
    bound = sql_path.bound
    assert "%moss%" in bound
    assert 5 in bound and 40 in bound
    assert [2, 3] in bound and [1, 2, 3] in bound


def test_sql_path_survives_a_row_whose_raw_data_is_a_json_string(sql_path):
    """asyncpg hands jsonb back as text on some connections; a decode failure here
    would 500 the catalog."""
    sql_path._rows = [{**DB_ROW, "raw_data": '{"normalized": {"color": "Blue"}}'}]
    sql_path._count = 1
    assert search()["items"][0]["raw_data"]["normalized"]["color"] == "Blue"
    sql_path.calls.clear()
    sql_path._rows = [{**DB_ROW, "raw_data": "not json at all"}]
    assert search()["items"][0]["raw_data"]["normalized"]["color"] is None


# ─── The gate's own classifier ───────────────────────────────────────────────


def _load_parity_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "check_search_parity.py"
    spec = importlib.util.spec_from_file_location("check_search_parity", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module   # dataclasses resolves annotations through sys.modules
    spec.loader.exec_module(module)
    return module


parity = _load_parity_script()
CAP = products._DB_COUNT_CAP


def _resp(ids_, total, **extra):
    return {"items": [{"id": i, "name": NAMES.get(i, str(i))} for i in ids_], "total": total, **extra}


def test_capped_total_above_the_cap_is_acceptable_not_a_defect():
    diffs = parity.compare_total("q", _resp([], 90_000), _resp([], CAP, total_is_capped=True), cap=CAP)
    assert [d.verdict for d in diffs] == [parity.ACCEPTABLE]
    assert diffs[0].reason == "capped-total"


def test_a_capped_total_below_the_cap_is_a_defect():
    diffs = parity.compare_total("q", _resp([], 10), _resp([], CAP, total_is_capped=True), cap=CAP)
    assert diffs[0].verdict == parity.DEFECT and diffs[0].reason == "capped-total-overstated"


def test_an_uncapped_total_must_match_exactly():
    assert parity.compare_total("q", _resp([], 10), _resp([], 10), cap=CAP) == []
    assert parity.compare_total("q", _resp([], 10), _resp([], 11), cap=CAP)[0].verdict == parity.DEFECT


def test_a_different_result_set_is_always_a_defect():
    diffs = parity.compare_items("q", _resp([1, 2], 2), _resp([1, 3], 2), has_search=True)
    assert diffs[0].verdict == parity.DEFECT and diffs[0].dimension == "items.ids"


def test_a_missing_row_on_a_keyword_query_is_named_a_recall_gap():
    diffs = parity.compare_items("q", _resp([1, 2], 2), _resp([1], 1), has_search=True)
    assert diffs[0].reason == "recall-gap"


def test_extra_rows_under_a_facet_filter_are_named_an_unapplied_filter():
    diffs = parity.compare_items("q", _resp([1], 1), _resp([1, 2], 2),
                                 has_search=False, facet_params_used=("colors",))
    assert diffs[0].reason == "filter-not-applied"


def _page(*pairs):
    return {"items": [{"id": i, "name": n} for i, n in pairs], "total": len(pairs)}


def test_reordering_an_alphabetical_page_is_a_collation_defect_even_on_a_search():
    """If the reference page is plain A-Z then relevance is not reordering it, so a
    difference is the two paths sorting names differently — which breaks paging."""
    ref = _page((1, '3" Ball'), (2, "Aster"))
    cand = _page((2, "Aster"), (1, '3" Ball'))
    for has_search in (False, True):
        diff = parity.compare_items("q", ref, cand, has_search=has_search)[0]
        assert diff.verdict == parity.DEFECT and diff.reason == "collation-order"
        assert diff.expected["first_differs_at"] == 0   # points at the divergence, not a prefix


def test_reranking_a_search_is_only_a_warning():
    """Here the reference is NOT alphabetical — relevance put "Zinnia" first — so
    the difference really is ranking, and ranking is allowed to differ."""
    ref = _page((9, "Zinnia"), (1, "Aster"))
    cand = _page((1, "Aster"), (9, "Zinnia"))
    diff = parity.compare_items("q", ref, cand, has_search=True)[0]
    assert diff.verdict == parity.WARN and diff.reason == "ranking-order"


def test_an_unexplained_browse_reorder_is_a_defect():
    ref = _page((9, "Zinnia"), (1, "Aster"))
    cand = _page((1, "Aster"), (9, "Zinnia"))
    diff = parity.compare_items("q", ref, cand, has_search=False)[0]
    assert diff.verdict == parity.DEFECT and diff.reason == "browse-order"


def test_swapping_identically_named_products_is_acceptable():
    ref = {"items": [{"id": 1, "name": "Moss"}, {"id": 2, "name": "Moss"}], "total": 2}
    cand = {"items": [{"id": 2, "name": "Moss"}, {"id": 1, "name": "Moss"}], "total": 2}
    diffs = parity.compare_items("q", ref, cand, has_search=False)
    assert [d.verdict for d in diffs] == [parity.ACCEPTABLE]


def test_facet_differences_are_defects():
    ref = {"items": [], "total": 0, "facets": {"colors": [{"value": "Green", "count": 4}]}}
    empty = {"items": [], "total": 0, "facets": {"colors": []}}
    assert parity.compare_facets("q", ref, empty)[0].reason == "facet-not-implemented"

    wrong = {"items": [], "total": 0, "facets": {"colors": [{"value": "Green", "count": 3}]}}
    diffs = parity.compare_facets("q", ref, wrong)
    assert diffs[0].verdict == parity.DEFECT and diffs[0].reason == "facet-counts"

    absent = {"items": [], "total": 0}
    assert parity.compare_facets("q", ref, absent)[0].reason == "facets-absent"
    assert parity.compare_facets("q", ref, ref) == []


def _facets(dim, pairs):
    return {"items": [], "total": 0,
            "facets": {dim: [{"value": v, "count": c} for v, c in pairs]}}


def test_facet_reordering_is_a_defect_because_the_order_is_fully_determined():
    a = _facets("colors", [("Green", 4), ("Red", 4)])
    b = _facets("colors", [("Red", 4), ("Green", 4)])
    diff = parity.compare_facets("q", a, b)[0]
    assert diff.verdict == parity.DEFECT and diff.reason == "facet-order"
    assert diff.expected["first_differs_at"] == 0


def test_a_tied_supplier_order_is_acceptable_because_the_reference_has_no_tie_break():
    """search_products builds `suppliers` with Counter.most_common(), which leaves
    equal counts in arbitrary insertion order. Demanding the SQL path reproduce an
    arbitrary order would be demanding a bug — so equal-count swaps are allowed
    there, and only there."""
    a = _facets("suppliers", [("Unlimited Container Inc", 145), ("Schusters", 145)])
    b = _facets("suppliers", [("Schusters", 145), ("Unlimited Container Inc", 145)])
    assert parity.compare_facets("q", a, b)[0].verdict == parity.ACCEPTABLE

    # ...but a swap that changes the COUNT order is still a defect there too.
    c = _facets("suppliers", [("A", 9), ("B", 4)])
    d = _facets("suppliers", [("B", 4), ("A", 9)])
    assert parity.compare_facets("q", c, d)[0].verdict == parity.DEFECT


def test_cold_start_facets_are_reported_separately_from_missing_facets():
    """An empty sidebar that fills in on the next request is a warm-up window, not
    an unimplemented feature; conflating them buries the real gaps."""
    first = {"facets": {d: [] for d in parity.FACET_DIMS}}
    warmed = {"facets": {d: [{"value": "x", "count": 1}] for d in parity.FACET_DIMS}}
    diff = parity.cold_start_diff(first, warmed)[0]
    assert diff.reason == "cold-start-empty-facets"
    assert parity.cold_start_diff(warmed, warmed) == []
    assert parity.cold_start_diff(first, first) == []   # genuinely empty ≠ cold start


def test_a_payload_type_change_is_a_warning_but_a_value_change_is_a_defect():
    ref = {"items": [{"id": 1, "name": "A", "raw_data": {"normalized": {"size_in": 10.5}}}], "total": 1}
    typed = {"items": [{"id": 1, "name": "A", "raw_data": {"normalized": {"size_in": "10.5"}}}], "total": 1}
    valued = {"items": [{"id": 1, "name": "A", "raw_data": {"normalized": {"size_in": 9.0}}}], "total": 1}
    assert parity.compare_items("q", ref, typed, has_search=False)[0].verdict == parity.WARN
    assert parity.compare_items("q", ref, valued, has_search=False)[0].verdict == parity.DEFECT


def test_the_sku_invariant_catches_a_longer_sku_matching_a_shorter_query():
    hit = {"items": [{"id": 3, "supplier_sku": "N590321-2"}], "total": 1}
    bleed = {"items": [{"id": 3, "supplier_sku": "N590321-2"},
                       {"id": 4, "supplier_sku": "N590321-20"}], "total": 2}
    assert parity.sku_buckets("N590321-2", bleed) == {"exact": [3], "superstring": [4], "other": []}
    assert parity.sku_invariant_diffs("q", "N590321-2", hit, hit) == []
    diffs = parity.sku_invariant_diffs("q", "N590321-2", hit, bleed)
    assert {d.reason for d in diffs} == {"sku-cross-match", "sku-parity"}
    assert all(d.verdict == parity.DEFECT for d in diffs)


def test_the_matrix_covers_the_agreed_shape_of_query():
    cases = {c.name: c for c in parity.build_matrix(
        {"ids": [1, 2, 3], "supplier_id": 1, "color": "Green", "category": "Wreaths"})}
    assert {"browse", "browse_p2", "browse_deep", "kw_moss", "sku_numeric", "sku_alnum",
            "price_band", "supplier", "ids_favorites", "no_match"} <= set(cases)
    # Combinations, not just single filters.
    assert any(len(c.params) > 1 for c in cases.values())
    assert cases["sku_numeric"].sku == "124394892"
    assert cases["facet_color"].facet_params_used == ("colors",)
