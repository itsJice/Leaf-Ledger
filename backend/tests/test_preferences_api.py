"""Tests for the per-account preferences API.

The interesting behaviour here is all about *not losing writes* and *not letting
a user break their own app*, so that is what these lock down:

* **partial merge** — a `PUT` that carries only `theme` must leave `sidebar`
  exactly as it was, and vice versa;
* **concurrency** — the sidebar editor and the appearance picker are two
  separate surfaces that `PUT` independently and can easily overlap. Two
  in-flight partial writes must both survive. The fake connection below models
  the `FOR UPDATE` row lock, so a read-modify-write that skipped the lock (or
  the transaction) would read a stale snapshot here and fail the test;
* **the un-hideable invariant** — `/` and `/settings` must be stripped
  server-side, however they are spelled, on writes *and* on reads;
* **defaults** — a brand-new user, a malformed stored document and an
  unreachable database all yield a complete document, never a 404 or a 500.

No database is involved: `get_conn` is stubbed the way `test_designs_api.py`
stubs its loader, so the real endpoint code runs against an in-memory row.
"""

import asyncio
import base64
import json

import pytest
from fastapi import HTTPException

from app.apis import preferences


# ─── Fake connection ─────────────────────────────────────────────────────────


class FakeDB:
    """One in-memory `ll_app.user_preferences` table + the row lock."""

    def __init__(self, rows: dict | None = None):
        self.rows: dict[str, str] = dict(rows or {})
        self.lock = asyncio.Lock()  # stands in for SELECT ... FOR UPDATE
        self.updates = 0

    def stored(self, user_id: str = "local-dev-user") -> dict:
        return json.loads(self.rows[user_id])


class FakeConn:
    def __init__(self, db: FakeDB):
        self.db = db
        self._holds_lock = False

    # asyncpg surface used by the endpoints ---------------------------------
    async def execute(self, sql, *args):
        await asyncio.sleep(0)  # a real suspension point, so tasks interleave
        if "CREATE SCHEMA" in sql:
            return None
        if "INSERT INTO ll_app.user_preferences" in sql:
            self.db.rows.setdefault(args[0], "{}")
            return None
        if "UPDATE ll_app.user_preferences" in sql:
            assert self._holds_lock, "wrote the row without holding its lock"
            self.db.rows[args[0]] = args[1]
            self.db.updates += 1
            return None
        raise AssertionError(f"unexpected SQL: {sql}")

    async def fetchval(self, sql, *args):
        if "FOR UPDATE" in sql:
            await self.db.lock.acquire()
            self._holds_lock = True
            # Hold the lock across a suspension so an overlapping request is
            # guaranteed to arrive while this one is mid-merge.
            await asyncio.sleep(0.01)
        else:
            await asyncio.sleep(0)
        return self.db.rows.get(args[0])

    def transaction(self):
        conn = self

        class _Txn:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                if conn._holds_lock:
                    conn._holds_lock = False
                    conn.db.lock.release()
                return False

        return _Txn()

    async def close(self):
        return None


class FakeRequest:
    """Just enough Request for `get_request_user_id`."""

    def __init__(self, user_id: str | None = None):
        if user_id is None:
            self.headers: dict[str, str] = {}
        else:
            payload = base64.urlsafe_b64encode(
                json.dumps({"sub": user_id}).encode()
            ).decode().rstrip("=")
            self.headers = {"Authorization": f"Bearer header.{payload}.signature"}


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()

    async def fake_get_conn():
        return FakeConn(fake)

    monkeypatch.setattr(preferences, "get_conn", fake_get_conn)
    monkeypatch.setattr(preferences, "_SCHEMA_READY", False)
    return fake


def get(user_id=None):
    return asyncio.run(preferences.get_preferences(FakeRequest(user_id)))


def put(body, user_id=None):
    return asyncio.run(preferences.put_preferences(FakeRequest(user_id), body=body))


# ─── Defaults ────────────────────────────────────────────────────────────────


def test_new_user_gets_complete_defaults_not_a_404(db):
    assert get() == {
        "sidebar": {"order": [], "hidden": []},
        "theme": {"mode": "system", "accent": "emerald"},
    }
    assert get() == preferences.DEFAULT_PREFERENCES
    # Reading must not create a row — a GET is not a write.
    assert db.rows == {}


def test_default_order_is_empty_so_new_tabs_still_appear():
    """An empty `order` means "no customisation": the client places every item
    at its default position. Baking today's nav in here would freeze it."""
    assert preferences.DEFAULT_PREFERENCES["sidebar"]["order"] == []


def test_get_degrades_to_defaults_when_storage_is_unreachable(monkeypatch):
    async def boom():
        raise RuntimeError("pooler is down")

    monkeypatch.setattr(preferences, "get_conn", boom)
    monkeypatch.setattr(preferences, "_SCHEMA_READY", False)
    assert get() == preferences.DEFAULT_PREFERENCES


def test_get_fills_missing_keys_from_defaults(db):
    db.rows["local-dev-user"] = json.dumps({"theme": {"mode": "dark"}})
    prefs = get()
    assert prefs["theme"] == {"mode": "dark", "accent": "emerald"}
    assert prefs["sidebar"] == {"order": [], "hidden": []}


def test_get_repairs_a_malformed_stored_document(db):
    db.rows["local-dev-user"] = json.dumps({
        "theme": {"mode": "chartreuse", "accent": "amber"},
        "sidebar": {"order": "not-a-list", "hidden": ["/orders", 7]},
        "somethingElse": {"from": "a newer client"},
    })
    prefs = get()
    assert prefs["theme"] == {"mode": "system", "accent": "amber"}  # bad mode → default
    assert prefs["sidebar"]["order"] == []                          # bad list → default
    assert prefs["sidebar"]["hidden"] == ["/orders"]                # junk element dropped
    assert "somethingElse" not in prefs                             # unknown key ignored


def test_get_survives_unparseable_stored_json(db):
    db.rows["local-dev-user"] = "{not json"
    assert get() == preferences.DEFAULT_PREFERENCES


def test_preferences_are_scoped_per_user(db):
    put({"theme": {"accent": "rose"}}, user_id="user-a")
    put({"theme": {"accent": "sky"}}, user_id="user-b")
    assert get("user-a")["theme"]["accent"] == "rose"
    assert get("user-b")["theme"]["accent"] == "sky"
    assert get()["theme"]["accent"] == "emerald"  # a third user is untouched


# ─── Deep merge ──────────────────────────────────────────────────────────────


def test_deep_merge_keeps_sibling_keys_and_replaces_lists():
    base = {"sidebar": {"order": ["/", "/designs"], "hidden": ["/invoice"]},
            "theme": {"mode": "light", "accent": "emerald"}}
    merged = preferences.deep_merge(base, {"theme": {"mode": "dark"}})
    assert merged["theme"] == {"mode": "dark", "accent": "emerald"}
    assert merged["sidebar"] == base["sidebar"]
    # Lists replace, so un-hiding (a shorter list) actually takes effect.
    assert preferences.deep_merge(base, {"sidebar": {"hidden": []}})["sidebar"] == {
        "order": ["/", "/designs"], "hidden": []
    }
    assert base["theme"]["mode"] == "light"  # inputs are not mutated


def test_put_partial_does_not_clobber_the_other_subtree(db):
    put({"sidebar": {"order": ["/designs", "/"], "hidden": ["/invoice"]}})
    result = put({"theme": {"mode": "dark"}})
    # The theme write kept the sidebar, and kept the accent it wasn't sent.
    assert result["sidebar"] == {"order": ["/designs", "/"], "hidden": ["/invoice"]}
    assert result["theme"] == {"mode": "dark", "accent": "emerald"}
    # And the reverse direction.
    result = put({"sidebar": {"hidden": ["/invoice", "/mockups"]}})
    assert result["theme"] == {"mode": "dark", "accent": "emerald"}
    assert result["sidebar"]["order"] == ["/designs", "/"]
    assert result["sidebar"]["hidden"] == ["/invoice", "/mockups"]


def test_put_returns_the_full_document(db):
    assert put({"theme": {"accent": "amber"}}) == {
        "sidebar": {"order": [], "hidden": []},
        "theme": {"mode": "system", "accent": "amber"},
    }


def test_empty_put_changes_nothing(db):
    put({"theme": {"mode": "dark"}})
    assert put({})["theme"]["mode"] == "dark"
    assert put(None)["theme"]["mode"] == "dark"


def test_reset_is_a_full_put_of_the_defaults(db):
    put({"sidebar": {"order": ["/orders"], "hidden": ["/invoice"]},
         "theme": {"mode": "dark", "accent": "amber"}})
    assert put(preferences.DEFAULT_PREFERENCES) == preferences.DEFAULT_PREFERENCES
    assert db.stored() == preferences.DEFAULT_PREFERENCES


# ─── Concurrency: two surfaces writing at once ───────────────────────────────


def test_concurrent_partial_puts_from_two_surfaces_both_survive(db):
    """The drag-reorder and the theme picker overlap; neither may be lost.

    Both requests are in flight at the same time (the fake row lock forces the
    second to wait mid-merge). A read-modify-write without the lock would merge
    onto the same stale snapshot and drop one of the two subtrees.
    """
    async def scenario():
        return await asyncio.gather(
            preferences.put_preferences(
                FakeRequest(), body={"sidebar": {"order": ["/designs", "/", "/orders"]}}
            ),
            preferences.put_preferences(
                FakeRequest(), body={"theme": {"mode": "dark", "accent": "amber"}}
            ),
        )

    asyncio.run(scenario())
    assert db.updates == 2
    final = db.stored()
    assert final["sidebar"]["order"] == ["/designs", "/", "/orders"]
    assert final["theme"] == {"mode": "dark", "accent": "amber"}
    assert get() == {
        "sidebar": {"order": ["/designs", "/", "/orders"], "hidden": []},
        "theme": {"mode": "dark", "accent": "amber"},
    }


def test_many_concurrent_writes_all_land(db):
    """Rapid drag-reorder plus an accent change: last order wins, accent kept."""
    async def scenario():
        jobs = [
            preferences.put_preferences(FakeRequest(), body={"sidebar": {"hidden": [f"/p{i}"]}})
            for i in range(5)
        ]
        jobs.append(
            preferences.put_preferences(FakeRequest(), body={"theme": {"accent": "rose"}})
        )
        await asyncio.gather(*jobs)

    asyncio.run(scenario())
    final = db.stored()
    assert final["theme"]["accent"] == "rose"
    assert len(final["sidebar"]["hidden"]) == 1  # one of the five, never merged into six


# ─── The un-hideable invariant ───────────────────────────────────────────────


def test_dashboard_and_settings_can_never_be_hidden(db):
    result = put({"sidebar": {"hidden": ["/", "/settings", "/invoice"]}})
    assert result["sidebar"]["hidden"] == ["/invoice"]
    assert db.stored()["sidebar"]["hidden"] == ["/invoice"]


def test_the_pinned_check_is_not_defeated_by_spelling(db):
    result = put({"sidebar": {"hidden": ["/Settings", "/settings/", " /settings ", "//", "/orders"]}})
    assert result["sidebar"]["hidden"] == ["/orders"]
    assert preferences.canon_path("/Settings/") == "/settings"
    assert preferences.canon_path("  ") == "/"


def test_pinned_items_are_stripped_on_read_too(db):
    """A row written before this rule existed (or edited by hand) must not lock
    the user out either."""
    db.rows["local-dev-user"] = json.dumps({"sidebar": {"hidden": ["/settings", "/orders"]}})
    assert get()["sidebar"]["hidden"] == ["/orders"]


def test_pinned_items_may_still_be_reordered(db):
    """They can't be hidden, but the user is free to move them."""
    assert put({"sidebar": {"order": ["/settings", "/", "/designs"]}})["sidebar"]["order"] == [
        "/settings", "/", "/designs"
    ]


# ─── Bad input ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", [
    {"theme": {"mode": "chartreuse"}},
    {"theme": {"mode": 3}},
    {"theme": {"accent": ""}},
    {"theme": {"accent": "x" * 200}},
    {"theme": "dark"},
    {"sidebar": {"order": "/designs"}},
    {"sidebar": {"order": ["/designs", 7]}},
    {"sidebar": {"hidden": {"/invoice": True}}},
    {"sidebar": []},
    ["not", "an", "object"],
    "nope",
])
def test_put_rejects_malformed_input(db, bad):
    with pytest.raises(HTTPException) as err:
        put(bad)
    assert err.value.status_code == 422
    assert db.rows == {}  # nothing was written


def test_put_accepts_every_valid_mode(db):
    for mode in ("system", "light", "dark", "DARK", " light "):
        assert put({"theme": {"mode": mode}})["theme"]["mode"] == mode.strip().lower()


def test_put_ignores_unknown_keys_instead_of_failing(db):
    """Forward compatibility: a newer client may send fields this server has
    never heard of, and that must not 422 the fields it does understand."""
    result = put({"theme": {"mode": "dark", "density": "compact"}, "experiments": {"beta": True}})
    assert result["theme"]["mode"] == "dark"
    assert "experiments" not in result and "density" not in result["theme"]
    assert db.stored() == {"theme": {"mode": "dark"}}


def test_lists_are_deduped_trimmed_and_bounded(db):
    result = put({"sidebar": {"hidden": [" /invoice ", "/invoice", "/orders", ""]}})
    assert result["sidebar"]["hidden"] == ["/invoice", "/orders"]
    huge = put({"sidebar": {"order": [f"/p{i}" for i in range(500)]}})
    assert len(huge["sidebar"]["order"]) == preferences.MAX_LIST_ITEMS


def test_put_reports_a_storage_failure_rather_than_pretending_to_save(monkeypatch):
    async def boom():
        raise RuntimeError("pooler is down")

    monkeypatch.setattr(preferences, "get_conn", boom)
    monkeypatch.setattr(preferences, "_SCHEMA_READY", False)
    with pytest.raises(HTTPException) as err:
        put({"theme": {"mode": "dark"}})
    assert err.value.status_code == 503


# ─── Wiring ──────────────────────────────────────────────────────────────────


def test_routes_are_exactly_the_contracted_paths():
    paths = {(r.path, tuple(sorted(r.methods))) for r in preferences.router.routes}
    assert paths == {("/preferences", ("GET",)), ("/preferences", ("PUT",))}


def test_router_is_registered_in_routers_json():
    import pathlib
    cfg = json.loads((pathlib.Path(__file__).parent.parent / "routers.json").read_text())
    assert "preferences" in cfg["routers"]
