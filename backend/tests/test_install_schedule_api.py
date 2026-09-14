"""Characterisation tests for the install-schedule API (`app.apis.install_schedule`)."""

import asyncio
import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.apis import install_schedule as sched

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def test_ensure_schema_runs_once(fake_db):
    run(sched.list_history("build-1"))
    assert fake_db.ddl_runs == 1
    run(sched.list_history("build-1"))
    assert fake_db.ddl_runs == 1


# ─── /page ───────────────────────────────────────────────────────────────────


def test_page_validates_before_connecting(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(sched.get_install_schedule_page(file="secrets.html"))
    assert (exc.value.status_code, exc.value.detail) == (404, "Unknown page")
    with pytest.raises(HTTPException) as exc:
        run(sched.get_install_schedule_page(season="26"))
    assert (exc.value.status_code, exc.value.detail) == (400, "Bad season")
    assert fake_db.executed == []


def test_page_defaults_to_newest_published_season(fake_db):
    fake_db.on_fetchval("SELECT season FROM ll_app.install_schedule_pages", "2025")
    fake_db.on_fetchrow("SELECT html FROM ll_app.install_schedule_pages", {"html": "<html>2025</html>"})
    assert run(sched.get_install_schedule_page(file="map.html")) == "<html>2025</html>"
    assert [a for _, a in fake_db.calls("SELECT season FROM")] == [("map.html",)]
    assert [a for _, a in fake_db.calls("SELECT html FROM")] == [("2025", "map.html")]


def test_page_404_messages(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(sched.get_install_schedule_page())
    assert exc.value.detail == "Schedule not published yet — run scheduler/publish_pages.py"
    assert not fake_db.seen("SELECT html")
    with pytest.raises(HTTPException) as exc:
        run(sched.get_install_schedule_page(season=" 2024 "))
    assert exc.value.detail == "No  2024  schedule published — run scheduler/publish_pages.py"
    assert [a for _, a in fake_db.calls("SELECT html FROM")] == [("2024", "index.html")]


# ─── /seasons ────────────────────────────────────────────────────────────────


def test_seasons_flags_current(fake_db, monkeypatch):
    monkeypatch.setattr(sched, "season_for", lambda: 2026)
    fake_db.on_fetch("GROUP BY season ORDER BY season DESC", [
        {"season": "2025", "updated_at": T0, "pages": 2},
        {"season": "2024", "updated_at": None, "pages": 1},
    ])
    assert run(sched.list_seasons()) == {
        "currentSeason": "2026",
        "seasons": [
            {"season": "2025", "publishedAt": "2026-09-01T12:00:00+00:00", "pages": 2, "current": False},
            {"season": "2024", "publishedAt": None, "pages": 1, "current": False},
        ],
    }


# ─── /state GET ──────────────────────────────────────────────────────────────


def test_get_state_existing_row(fake_db):
    fake_db.on_fetchrow("FROM ll_app.install_schedule_state WHERE version = $1",
                        {"state": '{"placement": {"12": "d1"}}', "updated_by": "user-7", "updated_at": T0})
    assert run(sched.get_state(" build-1 ")) == {
        "version": "build-1", "state": {"placement": {"12": "d1"}}, "updatedBy": "user-7",
        "updatedAt": "2026-09-01T12:00:00+00:00",
    }
    assert not fake_db.seen("jsonb_array_length")


def test_get_state_missing_offers_inherited_people(fake_db):
    fake_db.on_fetchrow("WHERE version <> $1", {
        "version": "old-build",
        "state": json.dumps({"roster": [{"name": "A"}], "staffing": {}, "placement": {"1": "d"}}),
        "updated_at": T0,
    })
    assert run(sched.get_state("build-2", season="2026")) == {
        "version": "build-2", "state": None,
        "inherit": {"roster": [{"name": "A"}], "inheritedFrom": "old-build"},
    }
    assert [a for _, a in fake_db.calls("WHERE version <> $1")] == [("build-2", "2026")]


def test_get_state_rejects_bad_version(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(sched.get_state("bad version!"))
    assert (exc.value.status_code, exc.value.detail) == (400, "Bad schedule version")


# ─── /state PUT ──────────────────────────────────────────────────────────────


def test_put_state_statement_sequence_and_history_trim(fake_db, fake_request):
    # A version already holding MAX_HISTORY_PER_VERSION rows: trimming is done
    # by the DELETE ... NOT IN (... LIMIT $2) in SQL, not in Python.
    fake_db.on_fetch("FROM ll_app.install_schedule_history",
                     [{"id": i, "updated_by": "u", "created_at": T0} for i in range(201)])
    state = {"season": "2026", "placement": {"12": "d1"}}
    out = run(sched.put_state(fake_request("user-7"), {"version": "build-1", "state": state}))
    assert out == {"version": "build-1", "ok": True, "updatedBy": "user-7"}
    encoded = json.dumps(state)
    assert sched.MAX_HISTORY_PER_VERSION == 200
    assert fake_db.executed[1:] == [
        ("INSERT INTO ll_app.install_schedule_state (version, season, state, updated_by) "
         "VALUES ($1, $2, '{}'::jsonb, $3) ON CONFLICT (version) DO NOTHING", ("build-1", "2026", "user-7")),
        ("SELECT state FROM ll_app.install_schedule_state WHERE version = $1 FOR UPDATE", ("build-1",)),
        ("UPDATE ll_app.install_schedule_state SET state = $2::jsonb, updated_by = $3,     "
         "season = COALESCE($4, season), updated_at = now() WHERE version = $1",
         ("build-1", encoded, "user-7", "2026")),
        ("INSERT INTO ll_app.install_schedule_history (version, season, state, updated_by) "
         "VALUES ($1, $2, $3::jsonb, $4)", ("build-1", "2026", encoded, "user-7")),
        ("DELETE FROM ll_app.install_schedule_history WHERE version = $1 AND id NOT IN ("
         "  SELECT id FROM ll_app.install_schedule_history   WHERE version = $1 ORDER BY created_at DESC LIMIT $2)",
         ("build-1", 200)),
    ]
    assert not fake_db.seen("client_activity")


def test_put_state_reconciles_not_installing(fake_db, fake_request):
    fake_db.on_fetch("FROM client_activity ca JOIN clients cl", [
        {"id": 1, "summary": "Scheduled 11/25/2026", "name": " smith ", "flagged": False,
         "detail": '{"install_date": "2026-11-25", "total": 1200}'},
        {"id": 2, "summary": "Not installing", "name": "Jones", "flagged": True,
         "detail": {"not_installing": True, "install_date": "2026-12-01", "total": 950.4}},
        {"id": 3, "summary": "x", "name": "Lee", "flagged": False, "detail": None},
    ])
    state = {"season": "2026", "notInstallingNames": ["Smith"], "notInstallingDates": {"SMITH": "2026-11-25"}}
    run(sched.put_state(fake_request(), {"version": "build-1", "state": state}))
    assert [a for _, a in fake_db.calls("UPDATE client_activity")] == [
        (1, "Not installing — previously scheduled 11/25/2026",
         '{"install_date": "2026-11-25", "total": 1200, "not_installing": true}'),
        (2, "Scheduled 12/01/2026 · $950", '{"install_date": "2026-12-01", "total": 950.4}'),
    ]
    assert [a for _, a in fake_db.calls("FROM client_activity")] == [("2026",)]


@pytest.mark.parametrize(
    "body,status,detail",
    [
        ([], 400, "Body must be an object"),
        ({"version": "v1", "state": []}, 400, "state must be an object"),
        ({"version": "", "state": {}}, 400, "Bad schedule version"),
        ({"version": "v1", "state": {"blob": "x" * 2_000_000}}, 413, "State document too large"),
    ],
)
def test_put_state_validation(fake_db, fake_request, body, status, detail):
    with pytest.raises(HTTPException) as exc:
        run(sched.put_state(fake_request(), body))
    assert (exc.value.status_code, exc.value.detail) == (status, detail)
    assert fake_db.executed == []


# ─── /history ────────────────────────────────────────────────────────────────


def test_history_clamps_limit_and_maps_rows(fake_db):
    fake_db.on_fetch("FROM ll_app.install_schedule_history WHERE version = $1",
                     [{"id": 9, "updated_by": "user-7", "created_at": T0}])
    assert run(sched.list_history("build-1", limit=999)) == {
        "version": "build-1",
        "entries": [{"id": 9, "updatedBy": "user-7", "createdAt": "2026-09-01T12:00:00+00:00"}],
    }
    run(sched.list_history("build-1", limit=0))
    assert [a for _, a in fake_db.calls("FROM ll_app.install_schedule_history")] == [("build-1", 200), ("build-1", 1)]


def test_history_entry(fake_db):
    with pytest.raises(HTTPException) as exc:
        run(sched.get_history_entry(9, "build-1"))
    assert exc.value.detail == "History entry not found"
    fake_db.on_fetchrow("FROM ll_app.install_schedule_history WHERE id = $1 AND version = $2",
                        {"id": 9, "state": '{"a": 1}', "updated_by": None, "created_at": None})
    assert run(sched.get_history_entry(9, "build-1")) == {
        "id": 9, "version": "build-1", "state": {"a": 1}, "updatedBy": None, "createdAt": None}


def test_storage_outage_degrades(monkeypatch):
    async def broken():
        raise RuntimeError("no database")

    monkeypatch.setattr(sched, "get_conn", broken)
    assert run(sched.list_history("build-1")) == {"version": "build-1", "entries": [], "storage": "unavailable"}
    assert run(sched.get_state("build-1")) == {"version": "build-1", "state": None, "storage": "unavailable"}
