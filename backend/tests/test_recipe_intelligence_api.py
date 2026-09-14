"""Characterisation tests for the recipe-intelligence API (`app.apis.recipe_intelligence`).

`db.storage` (the databutton shim) backs the InsufficientPrivilege fallback;
it is replaced with an in-memory dict here so nothing touches the local store.
"""

import asyncio
import types

import asyncpg
import pytest

from app.apis import recipe_intelligence as ri


def run(coro):
    return asyncio.run(coro)


class _MemJson:
    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self.puts = []

    def get(self, key, default=None):
        return self.data.get(key, default)

    def put(self, key, value):
        self.puts.append(key)
        self.data[key] = value


@pytest.fixture
def storage(monkeypatch):
    mem = types.SimpleNamespace(json=_MemJson(), text=_MemJson(), binary=_MemJson())
    monkeypatch.setattr(ri, "db", types.SimpleNamespace(storage=mem))
    return mem


def _deny_ddl(fake_db):
    def deny(sql, *args):
        raise asyncpg.InsufficientPrivilegeError("permission denied for schema public")

    fake_db.on("CREATE TABLE IF NOT EXISTS recipe_source_files", deny, method="execute")


def test_ensure_schema_runs_ddl_once_per_process(fake_db, storage):
    """Changed deliberately in Phase 2: `ensure_schema` used to rerun its 7
    `CREATE TABLE` statements on every call (previously named
    `test_ensure_schema_runs_ddl_every_call_today`, asserting 7 then 14). It
    is now wrapped in `ensure_schema_once`, so the second call is a no-op."""
    run(ri.get_build_types())
    first = fake_db.ddl_runs
    assert first == 7
    run(ri.get_build_types())
    assert fake_db.ddl_runs == first


def test_build_types_maps_rows(fake_db, storage):
    fake_db.on_fetch("FROM historical_recipes WHERE build_type IS NOT NULL", [
        {"build_type": "Tree", "evidence_count": 12, "prefixes": ["GT", "TT"]},
        {"build_type": "Wreath", "evidence_count": 1, "prefixes": None},
    ])
    assert run(ri.get_build_types()) == [
        {"label": "Tree", "evidence_count": 12, "prefixes": ["GT", "TT"]},
        {"label": "Wreath", "evidence_count": 1, "prefixes": []},
    ]


def test_build_types_falls_back_to_local_store_without_privilege(fake_db, storage):
    _deny_ddl(fake_db)
    storage.json.data[ri.LOCAL_STORE_KEY] = {"recipes": {
        "a": {"build_type": "Tree", "product_family": "TT"},
        "b": {"build_type": "Tree", "product_family": "GT"},
        "c": {"build_type": "Arrangement", "product_family": None},
        "d": {"build_type": None},
    }}
    assert run(ri.get_build_types()) == [
        {"label": "Tree", "evidence_count": 2, "prefixes": ["GT", "TT"]},
        {"label": "Arrangement", "evidence_count": 1, "prefixes": []},
    ]
    assert not fake_db.seen("FROM historical_recipes")
    assert storage.json.puts == []


def test_import_status_summary(fake_db, storage):
    fake_db.on_fetch("FROM recipe_source_files GROUP BY status", [{"status": "parsed", "count": 5}])
    fake_db.on_fetch("FROM recipe_source_files GROUP BY extension", [{"extension": ".xlsx", "count": 5}])
    fake_db.on_fetchval("SELECT COUNT(*) FROM historical_recipes", 4)
    fake_db.on_fetchval("SELECT COUNT(*) FROM historical_recipe_components", 40)
    fake_db.on_fetchval("SELECT COUNT(*) FROM visual_reference_assets", None)
    fake_db.on_fetch("WHERE status IN ('failed_needs_review', 'unsupported_deferred')",
                     [{"relative_path": "x.psd", "status": "unsupported_deferred", "error_message": None}])
    assert run(ri.get_recipe_import_status()) == {
        "source_root": str(ri.SOURCE_ROOT),
        "statuses": [{"status": "parsed", "count": 5}],
        "extensions": [{"extension": ".xlsx", "count": 5}],
        "recipe_count": 4, "component_count": 40, "asset_count": 0,
        "failures": [{"relative_path": "x.psd", "status": "unsupported_deferred", "error_message": None}],
        "parser_version": "2026-06-03.v1",
    }


def test_import_status_local_fallback(fake_db, storage):
    _deny_ddl(fake_db)
    storage.json.data[ri.LOCAL_STORE_KEY] = {
        "sources": {
            "/a.xlsx": {"status": "parsed", "extension": ".xlsx"},
            "/b.psd": {"status": "unsupported_deferred", "extension": ".psd", "relative_path": "b.psd"},
            "/c.xlsx": {"status": "parsed", "extension": ".xlsx"},
        },
        "recipes": {"1": {}}, "components": [{}, {}], "visual_refs": {},
    }
    assert run(ri.get_recipe_import_status()) == {
        "source_root": str(ri.SOURCE_ROOT),
        "statuses": [{"status": "parsed", "count": 2}, {"status": "unsupported_deferred", "count": 1}],
        "extensions": [{"extension": ".xlsx", "count": 2}, {"extension": ".psd", "count": 1}],
        "recipe_count": 1, "component_count": 2, "asset_count": 0,
        "failures": [{"relative_path": "b.psd", "status": "unsupported_deferred", "error_message": None}],
        "parser_version": "2026-06-03.v1.local",
        "storage": "local",
    }


def test_suggest_from_registered_corpus(fake_db, storage):
    fake_db.on_fetch("FROM historical_recipe_components c JOIN historical_recipes r", [
        {"component_label": "Container", "evidence_count": 12, "avg_quantity": 1.25, "median_quantity": 1.0,
         "avg_extended_total": 45.5, "vendors": ["Accent Decor", None], "descriptions": ["Ceramic pot 8in"]},
        {"component_label": None, "evidence_count": 3, "avg_quantity": None, "median_quantity": None,
         "avg_extended_total": None, "vendors": None, "descriptions": None},
    ])
    fake_db.on_fetchval("SELECT COUNT(*) FROM historical_recipes WHERE LOWER(build_type)", 11)
    fake_db.on_fetchrow("AS avg_total", {"avg_total": 250.0, "min_total": 120.0, "max_total": 400.0})
    body = ri.SuggestRequest(build_type=" planter ", height="24in")
    out = run(ri.suggest_recipe_components(body))
    aliases = ["planter", "container garden", "plant / vase", "container arrangement"]
    assert [a for _, a in fake_db.calls("FROM historical_recipe_components c")] == [(aliases,)]
    assert out == {
        "build_type": "planter",
        "input": {"build_type": " planter ", "height": "24in", "width": None, "depth": None, "length": None,
                  "quantity": 1, "notes": None},
        "evidence_count": 11,
        "confidence": "high",
        "components": [
            {"label": "Container", "suggested_quantity": 1.0, "average_quantity": 1.25, "evidence_count": 12,
             "average_extended_total": 45.5, "vendors": ["Accent Decor"], "examples": ["Ceramic pot 8in"],
             "search_terms": ["Container", "Accent Decor", "Ceramic pot 8in"]},
            {"label": "Product", "suggested_quantity": 1.0, "average_quantity": 1.0, "evidence_count": 3,
             "average_extended_total": None, "vendors": [], "examples": [], "search_terms": ["Product"]},
        ],
        "cost_range": {"avg_total": 250.0, "min_total": 120.0, "max_total": 400.0},
    }


def test_suggest_starter_fallback_for_unknown_build_type(fake_db, storage):
    out = run(ri.suggest_recipe_components(ri.SuggestRequest(build_type="Topiary")))
    assert [a for _, a in fake_db.calls("FROM historical_recipe_components c")] == [(["topiary"],)]
    assert out["evidence_count"] == 0
    assert out["confidence"] == "starter"
    assert [c["label"] for c in out["components"]] == ["Container", "Foliage / Greenery", "Foam", "Top Dressing"]
    assert all(c["evidence_count"] == 0 and c["suggested_quantity"] == 1.0 for c in out["components"])
    assert out["cost_range"] == {"avg_total": None, "min_total": None, "max_total": None}


def test_visual_references_normalises_code_and_clamps_limit(fake_db, storage):
    fake_db.on_fetch("FROM visual_reference_assets WHERE item_code = $1", [{"id": 1, "item_code": "OR7-73820"}])
    assert run(ri.get_visual_references(item_code=" or7__73820 ", limit=500)) == [{"id": 1, "item_code": "OR7-73820"}]
    run(ri.get_visual_references())
    assert [a for _, a in fake_db.calls("FROM visual_reference_assets")] == [("OR7-73820", 200), (50,)]


def test_visual_references_local_fallback(fake_db, storage):
    _deny_ddl(fake_db)
    storage.json.data[ri.LOCAL_STORE_KEY] = {"visual_refs": {
        "a": {"id": 1, "item_code": "OR7-1", "updated_at": "2026-01-01"},
        "b": {"id": 2, "item_code": "OR7-1", "updated_at": "2026-03-01"},
        "c": {"id": 3, "item_code": "TT-9", "updated_at": "2026-02-01"},
    }}
    assert [r["id"] for r in run(ri.get_visual_references(item_code="or7_1"))] == [2, 1]
