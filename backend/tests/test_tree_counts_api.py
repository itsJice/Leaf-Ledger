"""Tests for the tree-counts (calibration loop) API.

No database: `get_conn` is stubbed with an in-memory table the same way
`test_preferences_api.py` does, so the real endpoint code runs end to end.
What is locked down:

* **counts normalisation** -- "4", "4.0" and 4 are one size; zero/blank
  entries vanish; junk keys, negatives and non-integers are rejected;
* **the empty-record guard** -- a record with no ornaments and no enhancers
  is a 400, not a row;
* **newest-first listing and the height window** -- `height_ft` filters to
  +/- `tolerance_ft`;
* **delete** -- 404 on an unknown id, otherwise the row is gone.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.apis import tree_counts
from app.apis.tree_counts import TreeCountIn, normalise_counts
from app.auth.user import User


# ─── Fake connection ─────────────────────────────────────────────────────────


class FakeDB:
    def __init__(self):
        self.rows: list[dict] = []
        self.next_id = 1
        self.ddl_runs = 0


class FakeConn:
    def __init__(self, db: FakeDB):
        self.db = db

    async def execute(self, sql, *args):
        assert "CREATE TABLE IF NOT EXISTS ll_app.tree_counts" in sql
        self.db.ddl_runs += 1

    async def fetchrow(self, sql, *args):
        assert sql.startswith("INSERT INTO ll_app.tree_counts")
        (recorded_at, kind, height_ft, width_in, profile, style, label,
         counts_json, enhancers, notes, created_by, created_name) = args
        import json
        row = {
            "id": self.db.next_id,
            "recorded_at": recorded_at or datetime.now(timezone.utc),
            "kind": kind,
            "height_ft": height_ft,
            "width_in": width_in,
            "profile": profile,
            "style": style,
            "label": label,
            "counts": json.loads(counts_json),
            "enhancers": enhancers,
            "notes": notes,
            "created_by": created_by,
            "created_name": created_name,
        }
        self.db.next_id += 1
        self.db.rows.append(row)
        return row

    async def fetch(self, sql, *args):
        assert sql.startswith("SELECT")
        rows = list(self.db.rows)
        if "BETWEEN" in sql:
            lo, hi, limit = args
            rows = [r for r in rows if lo <= r["height_ft"] <= hi]
        else:
            (limit,) = args
        rows.sort(key=lambda r: (r["recorded_at"], r["id"]), reverse=True)
        return rows[:limit]

    async def fetchval(self, sql, *args):
        assert sql.startswith("DELETE FROM ll_app.tree_counts")
        (count_id,) = args
        for r in self.db.rows:
            if r["id"] == count_id:
                self.db.rows.remove(r)
                return count_id
        return None

    async def close(self):
        return None


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()

    async def fake_get_conn():
        return FakeConn(fake)

    monkeypatch.setattr(tree_counts, "get_conn", fake_get_conn)
    monkeypatch.setattr(tree_counts, "_SCHEMA_READY", False)
    return fake


USER = User(sub="user-1", user_id="user-1", email="crew@example.com", name="crew")


def create(**fields):
    body = TreeCountIn(**{"kind": "install", "height_ft": 9, "width_in": 59, **fields})
    return asyncio.run(tree_counts.create_tree_count(body, USER))


def listing(**params):
    return asyncio.run(tree_counts.list_tree_counts(**params))


# ─── Counts normalisation ────────────────────────────────────────────────────


def test_counts_keys_collapse_and_zeros_drop():
    assert normalise_counts({"4": 10, "4.0": 2, 4.75: 30, "6": 0, "8": ""}) == {
        "4": 12,
        "4.75": 30,
    }


@pytest.mark.parametrize(
    "bad",
    [{"four": 1}, {"4": -1}, {"4": "lots"}, {"0": 3}, {"4": 99999}],
)
def test_counts_reject_junk(bad):
    with pytest.raises(ValueError):
        normalise_counts(bad)


def test_body_validation_rejects_bad_kind_and_dimensions():
    with pytest.raises(ValidationError):
        TreeCountIn(kind="removal", height_ft=9, width_in=59)
    with pytest.raises(ValidationError):
        TreeCountIn(kind="install", height_ft=0, width_in=59)
    with pytest.raises(ValidationError):
        TreeCountIn(kind="install", height_ft=9, width_in=59, enhancers=-2)


# ─── Create ──────────────────────────────────────────────────────────────────


def test_create_stores_normalised_record_with_attribution(db):
    out = create(
        counts={"4": 24, "4.75": 30, "6": 20, "8": "", "10": 0},
        enhancers=18,
        label="  Smith foyer ",
        notes="",
        kind="teardown",
    )
    assert out.id == 1
    assert out.kind == "teardown"
    assert out.counts == {"4": 24, "4.75": 30, "6": 20}
    assert out.enhancers == 18
    assert out.label == "Smith foyer"
    assert out.notes is None
    assert out.created_by == "user-1"
    assert out.created_name == "crew"
    assert out.height_ft == 9.0 and out.width_in == 59.0
    assert db.ddl_runs == 1


def test_create_refuses_an_empty_record(db):
    with pytest.raises(HTTPException) as exc:
        create(counts={"4": 0}, enhancers=0)
    assert exc.value.status_code == 400
    assert db.rows == []


def test_schema_is_ensured_once(db):
    create(counts={"4": 1})
    create(counts={"4": 1})
    assert db.ddl_runs == 1


# ─── List ────────────────────────────────────────────────────────────────────


def test_list_is_newest_first_and_filters_by_height_window(db):
    t0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
    create(counts={"4": 20}, height_ft=9, recorded_at=t0)
    create(counts={"4": 22}, height_ft=9.25, recorded_at=t0 + timedelta(days=1))
    create(counts={"4": 30}, height_ft=10, recorded_at=t0 + timedelta(days=2))
    create(counts={"4": 24}, height_ft=8.5, recorded_at=t0 + timedelta(days=3))

    everything = listing()
    assert [r.height_ft for r in everything] == [8.5, 10, 9.25, 9]

    nine = listing(height_ft=9)
    assert [r.height_ft for r in nine] == [9.25, 9]

    wide = listing(height_ft=9, tolerance_ft=1)
    assert [r.height_ft for r in wide] == [8.5, 10, 9.25, 9]


def test_list_degrades_to_empty_when_storage_is_down(monkeypatch):
    async def broken():
        raise RuntimeError("no database")

    monkeypatch.setattr(tree_counts, "get_conn", broken)
    assert listing() == []


# ─── Delete ──────────────────────────────────────────────────────────────────


def test_delete_removes_row_and_404s_when_missing(db):
    created = create(counts={"4": 1})
    assert asyncio.run(tree_counts.delete_tree_count(created.id)) == {"deleted": 1, "id": created.id}
    assert db.rows == []
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tree_counts.delete_tree_count(created.id))
    assert exc.value.status_code == 404
