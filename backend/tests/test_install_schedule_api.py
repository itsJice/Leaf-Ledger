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
    assert exc.value.detail == "No 2024 schedule published — run scheduler/publish_pages.py"
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
    fake_db.on_fetchval("RETURNING updated_at", T0)
    state = {"season": "2026", "placement": {"12": "d1"}}
    out = run(sched.put_state(fake_request("user-7"),
                              {"version": "build-1", "state": state, "baseUpdatedAt": None}))
    assert out == {"version": "build-1", "ok": True, "updatedBy": "user-7",
                   "updatedAt": T0.isoformat()}
    encoded = json.dumps(state)
    assert sched.MAX_HISTORY_PER_VERSION == 200
    assert fake_db.executed[1:] == [
        ("INSERT INTO ll_app.install_schedule_state (version, season, state, updated_by) "
         "VALUES ($1, $2, '{}'::jsonb, $3) ON CONFLICT (version) DO NOTHING", ("build-1", "2026", "user-7")),
        ("SELECT state, updated_by, updated_at FROM ll_app.install_schedule_state "
         "WHERE version = $1 FOR UPDATE", ("build-1",)),
        ("UPDATE ll_app.install_schedule_state SET state = $2::jsonb, updated_by = $3,     "
         "season = COALESCE($4, season),     "
         "updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond') "
         "WHERE version = $1 RETURNING updated_at",
         ("build-1", encoded, "user-7", "2026")),
        ("INSERT INTO ll_app.install_schedule_history (version, season, state, updated_by) "
         "VALUES ($1, $2, $3::jsonb, $4)", ("build-1", "2026", encoded, "user-7")),
        ("DELETE FROM ll_app.install_schedule_history WHERE version = $1 AND id NOT IN ("
         "  SELECT id FROM ll_app.install_schedule_history   WHERE version = $1 ORDER BY created_at DESC LIMIT $2)",
         ("build-1", 200)),
    ]
    assert not fake_db.seen("client_activity")


def test_put_state_reconciles_not_installing(fake_db, fake_request, monkeypatch):
    from app.libs import client_season
    monkeypatch.setattr(client_season, "now_iso", lambda: "T")
    fake_db.on_fetch("FROM client_activity ca JOIN clients cl", [
        {"id": 1, "summary": "Scheduled 11/25/2026", "name": " smith ", "flagged": False,
         "detail": '{"install_date": "2026-11-25", "total": 1200}'},
        {"id": 2, "summary": "Not installing", "name": "Jones", "flagged": True,
         "detail": {"not_installing": True, "install_date": "2026-12-01", "total": 950.4,
                    "was_scheduled": "2026-12-01", "app_edits": {"not_installing": "T0"}}},
        {"id": 3, "summary": "x", "name": "Lee", "flagged": False, "detail": None},
    ])
    state = {"season": "2026", "notInstallingNames": ["Smith"], "notInstallingDates": {"SMITH": "2026-11-25"}}
    run(sched.put_state(fake_request(), {"version": "build-1", "state": state}))
    calls = [(i, s, json.loads(d)) for (i, s, d) in (a for _, a in fake_db.calls("UPDATE client_activity"))]
    assert calls == [
        # marked: the flag is stamped as an app edit so a re-sync keeps it
        (1, "Not installing — previously scheduled 11/25/2026",
         {"install_date": "2026-11-25", "total": 1200, "was_scheduled": "2026-11-25",
          "not_installing": True, "app_edits": {"not_installing": "T"}}),
        # cleared: flag, remembered date and stamp all go; the line is rebuilt
        (2, "Scheduled 12/01/2026 · $950", {"install_date": "2026-12-01", "total": 950.4}),
    ]
    assert [a for _, a in fake_db.calls("FROM client_activity")] == [("2026",)]


def test_put_state_reconciles_hold(fake_db, fake_request, monkeypatch):
    from app.libs import client_season
    monkeypatch.setattr(client_season, "now_iso", lambda: "T")
    fake_db.on_fetch("FROM client_activity ca JOIN clients cl", [
        {"id": 1, "summary": "Scheduled 11/25/2026", "name": "Smith", "flagged": False, "held": False,
         "detail": '{"install_date": "2026-11-25"}'},
        {"id": 2, "summary": "On hold · Scheduled 12/01/2026", "name": "Jones", "flagged": False, "held": True,
         "detail": {"install_date": "2026-12-01", "hold": True, "app_edits": {"hold": "T0"}}},
        # on hold AND not installing: not-installing wins, hold is dropped
        {"id": 3, "summary": "x", "name": "Lee", "flagged": False, "held": False, "detail": {}},
    ])
    state = {"season": "2026", "notInstallingNames": ["Lee"], "holdNames": ["Smith", "Lee"]}
    run(sched.put_state(fake_request(), {"version": "build-1", "state": state}))
    calls = [(i, s, json.loads(d)) for (i, s, d) in (a for _, a in fake_db.calls("UPDATE client_activity"))]
    assert calls == [
        (1, "On hold · Scheduled 11/25/2026",
         {"install_date": "2026-11-25", "hold": True, "app_edits": {"hold": "T"}}),
        (2, "Scheduled 12/01/2026", {"install_date": "2026-12-01"}),
        (3, "Not installing", {"not_installing": True, "app_edits": {"not_installing": "T"}}),
    ]


def test_put_state_without_hold_names_leaves_holds_alone(fake_db, fake_request):
    fake_db.on_fetch("FROM client_activity ca JOIN clients cl", [
        {"id": 2, "summary": "On hold · Scheduled 12/01/2026", "name": "Jones", "flagged": False, "held": True,
         "detail": {"install_date": "2026-12-01", "hold": True}},
    ])
    # an older cached page: sends notInstallingNames but has never heard of holds
    state = {"season": "2026", "notInstallingNames": []}
    run(sched.put_state(fake_request(), {"version": "build-1", "state": state}))
    assert not fake_db.seen("UPDATE client_activity")


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


# ─── board dates -> client cards (Comments #14-17) ──────────────────────────


def _card_rows():
    return [
        {"id": 1, "client_id": 41, "name": "Amy Jinks", "sheet_name": "Jinks, Amy", "former_names": [],
         "detail": '{"install_date": "2026-11-07", "total": 900, "notes": "Gate code"}'},
        {"id": 2, "client_id": 42, "name": "Crane Worldwide", "sheet_name": None, "former_names": ["Crane WW"],
         "detail": {"install_date": "2026-11-18"}},
        {"id": 3, "client_id": 43, "name": "Pulled Out", "sheet_name": None, "former_names": [],
         "detail": {"not_installing": True, "install_date": "2026-11-20"}},
        # two clients answering to one spelling: never guessed between
        {"id": 4, "client_id": 44, "name": "Smith", "sheet_name": None, "former_names": [], "detail": {}},
        {"id": 5, "client_id": 45, "name": "Smith House", "sheet_name": "Smith", "former_names": [], "detail": {}},
    ]


def _date_updates(fake_db):
    return [(a[0], a[1], json.loads(a[2]), a[3]) for _, a in fake_db.calls("UPDATE client_activity")]


@pytest.fixture
def season_2026(monkeypatch):
    from app.libs import client_season
    monkeypatch.setattr(client_season, "now_iso", lambda: "T")
    monkeypatch.setattr(sched, "season_for", lambda: 2026)


def test_put_state_writes_moved_board_dates_to_cards(fake_db, fake_request, season_2026):
    from datetime import date
    fake_db.on_fetch("SELECT ca.id, ca.client_id, ca.detail", _card_rows())
    state = {"season": "2026", "dateMoves": [
        # by id (the page knew the app client)
        {"id": 41, "name": "Amy Jinks", "kind": "install", "date": "2026-11-13", "from": "2026-11-07"},
        # by a former spelling, folded like the page folds names
        {"id": None, "name": "crane  ww.", "kind": "install", "date": "2026-11-19", "from": "2026-11-18"},
        {"id": None, "name": "Crane Worldwide", "kind": "takedown", "date": "2027-01-08", "from": None},
        # skipped: not installing / ambiguous / unknown / no-op / junk
        {"name": "Pulled Out", "kind": "install", "date": "2026-11-21"},
        {"name": "Smith", "kind": "install", "date": "2026-11-21"},
        {"name": "Nobody", "kind": "install", "date": "2026-11-21"},
        {"name": "Amy Jinks", "kind": "install", "date": "2026-11-13"},
        {"name": "Amy Jinks", "kind": "install", "date": "2027-03-01"},   # outside the season
        {"name": "Amy Jinks", "kind": "cleanup", "date": "2026-11-14"},
        {"name": "Amy Jinks", "kind": "install", "date": "11/14/2026"},
    ]}
    run(sched.put_state(fake_request("user-7"), {"version": "build-1", "state": state}))
    assert _date_updates(fake_db) == [
        (1, "Scheduled 11/13/2026 · $900",
         {"install_date": "2026-11-13", "total": 900, "notes": "Gate code",
          "app_edits": {"install_date": "T"},
          "date_history": [{"field": "install_date", "from": "2026-11-07", "to": "2026-11-13",
                            "at": "T", "by": "user-7", "source": "install schedule"}]},
         date(2026, 11, 13)),
        (2, "Scheduled 11/19/2026",
         {"install_date": "2026-11-19", "takedown_date": "2027-01-08",
          "app_edits": {"install_date": "T", "takedown_date": "T"},
          "date_history": [
              {"field": "install_date", "from": "2026-11-18", "to": "2026-11-19",
               "at": "T", "by": "user-7", "source": "install schedule"},
              {"field": "takedown_date", "from": None, "to": "2027-01-08",
               "at": "T", "by": "user-7", "source": "install schedule"}]},
         date(2026, 11, 19)),
    ]
    # the card query is this season's only; the save itself still happened
    assert [a for _, a in fake_db.calls("SELECT ca.id, ca.client_id")] == [("2026",)]
    assert fake_db.seen("INSERT INTO ll_app.install_schedule_history")


def test_undo_resends_the_old_date(fake_db, fake_request, season_2026):
    rows = _card_rows()
    rows[0] = {**rows[0], "detail": {"install_date": "2026-11-13",
                                     "app_edits": {"install_date": "T0"},
                                     "date_history": [{"field": "install_date", "from": "2026-11-07",
                                                       "to": "2026-11-13"}]}}
    fake_db.on_fetch("SELECT ca.id, ca.client_id, ca.detail", rows)
    state = {"season": "2026", "dateMoves": [
        {"id": 41, "name": "Amy Jinks", "kind": "install", "date": "2026-11-07", "from": "2026-11-13"}]}
    run(sched.put_state(fake_request("u"), {"version": "build-1", "state": state}))
    [(row_id, summary, detail, _)] = _date_updates(fake_db)
    assert (row_id, summary, detail["install_date"]) == (1, "Scheduled 11/07/2026", "2026-11-07")
    assert [h["to"] for h in detail["date_history"]] == ["2026-11-13", "2026-11-07"]


def test_date_moves_ignored_for_archived_seasons_and_old_pages(fake_db, fake_request, season_2026):
    fake_db.on_fetch("SELECT ca.id, ca.client_id, ca.detail", _card_rows())
    move = [{"id": 41, "name": "Amy Jinks", "kind": "install", "date": "2025-11-13"}]
    run(sched.put_state(fake_request(), {"version": "build-0", "state": {"season": "2025", "dateMoves": move}}))
    run(sched.put_state(fake_request(), {"version": "build-1", "state": {"season": "2026"}}))
    run(sched.put_state(fake_request(), {"version": "build-1", "state": {"season": "2026", "dateMoves": []}}))
    assert not fake_db.seen("client_activity")


def test_card_write_failure_never_fails_the_save(fake_db, fake_request, season_2026):
    def boom(*_):
        raise RuntimeError("db hiccup")
    fake_db.on("SELECT ca.id, ca.client_id, ca.detail", boom)
    state = {"season": "2026", "dateMoves": [{"id": 41, "name": "A", "kind": "install", "date": "2026-11-13"}]}
    out = run(sched.put_state(fake_request("u"), {"version": "build-1", "state": state}))
    assert out["ok"] is True


def test_viewer_and_production_cannot_put_state():
    """The card write lives inside PUT /state, so the router's role check is
    its gate: the viewer login reads only, production is GET-only here."""
    from app.libs import roles
    minimum = getattr(sched, "MIN_ROLE", "staff")
    path = "/api/install-schedule/state"
    for role in ("viewer", "production", "lead", "crew"):
        assert not roles.allowed(role, minimum, "PUT", sched.VIEWER_READ, path), role
        assert role in ("lead", "crew") or roles.allowed(role, minimum, "GET", sched.VIEWER_READ, path)
    for role in ("staff", "admin", "super_admin"):
        assert roles.allowed(role, minimum, "PUT", sched.VIEWER_READ, path), role
