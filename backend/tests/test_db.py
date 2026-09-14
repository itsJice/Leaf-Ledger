"""app.libs.db (pool + proxy + schema registry), jsonutil and export_format.

No real database: ``asyncpg.create_pool`` and ``asyncpg.connect`` are replaced
with fakes for every test in this file (see the autouse ``fakes`` fixture).
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg
import pytest

import app.libs.db as db
from app.libs import export_format, jsonutil


# ─── Fakes ───────────────────────────────────────────────────────────────────


class FakeTx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.tx_entered += 1
        return self

    async def __aexit__(self, *exc):
        return False


class FakeRawConn:
    def __init__(self, label: str):
        self.label = label
        self.closed = False
        self.tx_entered = 0

    async def fetchval(self, sql, *args):
        return (self.label, sql, args)

    def transaction(self):
        return FakeTx(self)

    def is_closed(self):
        return self.closed

    async def close(self):
        self.closed = True


class FakePool:
    def __init__(self, dsn, **kwargs):
        self.dsn = dsn
        self.kwargs = kwargs
        self.loop = asyncio.get_running_loop()
        self.acquire_timeouts: list = []
        self.acquire_error: BaseException | None = None
        self.released: list = []
        self.closed = False
        self.terminated = False
        self.close_hangs = False

    async def acquire(self, *, timeout=None):
        self.acquire_timeouts.append(timeout)
        if self.acquire_error is not None:
            raise self.acquire_error
        return FakeRawConn("pooled")

    async def release(self, conn, *, timeout=None):
        self.released.append(conn)

    async def close(self):
        if self.close_hangs:
            await asyncio.sleep(3600)
        self.closed = True

    def terminate(self):
        self.terminated = True


class Recorder:
    def __init__(self):
        self.pools: list[FakePool] = []
        self.create_error: BaseException | None = None
        self.create_calls = 0
        self.connects: list[tuple] = []
        self.pool_setup = None  # optional callback(pool)

    async def create_pool(self, dsn=None, **kwargs):
        self.create_calls += 1
        await asyncio.sleep(0)  # let concurrent first callers pile up on the lock
        if self.create_error is not None:
            raise self.create_error
        pool = FakePool(dsn, **kwargs)
        if self.pool_setup:
            self.pool_setup(pool)
        self.pools.append(pool)
        return pool

    async def connect(self, dsn=None, **kwargs):
        self.connects.append((dsn, kwargs))
        return FakeRawConn("direct")


@pytest.fixture(autouse=True)
def fakes(monkeypatch) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(asyncpg, "create_pool", rec.create_pool)
    monkeypatch.setattr(asyncpg, "connect", rec.connect)
    monkeypatch.setattr(db, "_states", {})
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake-host/fake-db")
    for name in ("DB_POOL_MAX", "DB_POOL_ACQUIRE_TIMEOUT", "DB_POOL_DISABLED"):
        monkeypatch.delenv(name, raising=False)
    db.reset_schema_registry()
    yield rec
    db.reset_schema_registry()


# ─── PooledConn ──────────────────────────────────────────────────────────────


def test_close_releases_exactly_once(fakes):
    async def scenario():
        conn = await db.get_conn()
        assert isinstance(conn, db.PooledConn)
        assert not conn.is_closed()
        await conn.close()
        assert conn.is_closed()
        await conn.close()  # second close is a no-op
        return conn

    conn = asyncio.run(scenario())
    (pool,) = fakes.pools
    assert len(pool.released) == 1 and pool.released[0] is conn._conn
    assert fakes.connects == []


def test_attribute_delegation(fakes):
    async def scenario():
        conn = await db.get_conn()
        try:
            val = await conn.fetchval("SELECT $1", 1)
            async with conn.transaction():
                pass
            with pytest.raises(AttributeError):
                conn.no_such_method
            return val, conn._conn.tx_entered
        finally:
            await conn.close()

    val, tx_entered = asyncio.run(scenario())
    assert val == ("pooled", "SELECT $1", (1,))
    assert tx_entered == 1


# ─── Pool lifecycle ──────────────────────────────────────────────────────────


def test_pool_created_once_per_loop_and_reused(fakes, monkeypatch):
    # Read at call time, not import time.
    monkeypatch.setenv("DATABASE_URL", "postgresql://set-after-import/db")

    async def scenario():
        first = await asyncio.gather(*(db.get_conn() for _ in range(5)))
        for c in first:
            await c.close()
        for _ in range(3):
            c = await db.get_conn()
            await c.close()

    asyncio.run(scenario())
    assert fakes.create_calls == 1
    (pool,) = fakes.pools
    assert pool.dsn == "postgresql://set-after-import/db"
    assert pool.kwargs == {"statement_cache_size": 0, "min_size": 1, "max_size": 10}
    assert len(pool.released) == 8
    assert pool.acquire_timeouts == [5.0] * 8


def test_pool_max_from_env(fakes, monkeypatch):
    monkeypatch.setenv("DB_POOL_MAX", "3")

    async def scenario():
        await (await db.get_conn()).close()

    asyncio.run(scenario())
    assert fakes.pools[0].kwargs["max_size"] == 3


def test_second_asyncio_run_gets_its_own_pool(fakes):
    async def scenario():
        conn = await db.get_conn()
        await conn.close()
        return conn._pool

    pool_a = asyncio.run(scenario())
    pool_b = asyncio.run(scenario())
    assert pool_a is not pool_b
    assert fakes.create_calls == 2
    assert pool_a.loop is not pool_b.loop
    # The finished loop's pool was dropped rather than reused.
    assert pool_a.terminated
    assert list(db._states) == [pool_b.loop]


def test_pool_disabled_uses_direct_connect(fakes, monkeypatch):
    monkeypatch.setenv("DB_POOL_DISABLED", "true")

    async def scenario():
        conn = await db.get_conn()
        await conn.close()
        return conn

    conn = asyncio.run(scenario())
    assert isinstance(conn, FakeRawConn) and conn.label == "direct" and conn.closed
    assert fakes.create_calls == 0
    assert fakes.connects == [("postgresql://fake-host/fake-db", {"statement_cache_size": 0})]


def test_pool_creation_failure_falls_back_then_retries_after_cooldown(fakes, monkeypatch, caplog):
    fakes.create_error = OSError("boom")

    async def scenario():
        a = await db.get_conn()
        b = await db.get_conn()  # inside cooldown: no second create attempt
        assert fakes.create_calls == 1
        monkeypatch.setattr(db, "POOL_RETRY_AFTER_S", 0.0)
        fakes.create_error = None
        c = await db.get_conn()
        return a, b, c

    with caplog.at_level(logging.WARNING, logger="app.libs.db"):
        a, b, c = asyncio.run(scenario())
    assert isinstance(a, FakeRawConn) and isinstance(b, FakeRawConn)
    assert isinstance(c, db.PooledConn)
    assert len(fakes.connects) == 2
    assert fakes.create_calls == 2
    assert "pool creation failed" in caplog.text


def test_acquire_timeout_falls_back_to_direct_connect(fakes, monkeypatch, caplog):
    monkeypatch.setenv("DB_POOL_ACQUIRE_TIMEOUT", "0.25")
    fakes.pool_setup = lambda pool: setattr(pool, "acquire_error", asyncio.TimeoutError())

    async def scenario():
        return await db.get_conn()

    with caplog.at_level(logging.WARNING, logger="app.libs.db"):
        conn = asyncio.run(scenario())
    assert isinstance(conn, FakeRawConn) and conn.label == "direct"
    assert fakes.pools[0].acquire_timeouts == [0.25]
    assert fakes.connects == [("postgresql://fake-host/fake-db", {"statement_cache_size": 0})]
    assert "timed out" in caplog.text


def test_close_pool(fakes, monkeypatch):
    async def scenario():
        await db.close_pool()  # nothing to close yet: no-op
        await (await db.get_conn()).close()
        await db.close_pool()
        await db.close_pool()  # idempotent
        await (await db.get_conn()).close()  # a later call builds a fresh pool
        fakes.pools[1].close_hangs = True
        monkeypatch.setattr(db, "CLOSE_TIMEOUT_S", 0.01)
        await db.close_pool()

    asyncio.run(scenario())
    first, second = fakes.pools
    assert first.closed and not first.terminated
    assert second.terminated  # close() hung past the timeout
    assert db._states == {}


# ─── ensure_schema_once ──────────────────────────────────────────────────────


class DDLCounter:
    def __init__(self, fail_times: int = 0):
        self.runs = 0
        self.fail_times = fail_times

    async def __call__(self):
        self.runs += 1
        await asyncio.sleep(0)
        if self.runs <= self.fail_times:
            raise RuntimeError("ddl failed")


def test_ensure_schema_once_sequential():
    ddl = DDLCounter()

    async def scenario():
        await db.ensure_schema_once("feedback", ddl)
        await db.ensure_schema_once("feedback", ddl)

    asyncio.run(scenario())
    assert ddl.runs == 1
    asyncio.run(scenario())  # still done in a later event loop
    assert ddl.runs == 1


def test_ensure_schema_once_concurrent():
    ddl = DDLCounter()

    async def scenario():
        await asyncio.gather(*(db.ensure_schema_once("orders", ddl) for _ in range(5)))

    asyncio.run(scenario())
    assert ddl.runs == 1


def test_ensure_schema_once_retries_after_exception():
    ddl = DDLCounter(fail_times=1)

    async def scenario():
        with pytest.raises(RuntimeError):
            await db.ensure_schema_once("jobs", ddl)
        await db.ensure_schema_once("jobs", ddl)
        await db.ensure_schema_once("jobs", ddl)

    asyncio.run(scenario())
    assert ddl.runs == 2


def test_ensure_schema_once_retry_in_a_new_loop_and_reset():
    ddl = DDLCounter(fail_times=1)
    other = DDLCounter()

    async def fail():
        with pytest.raises(RuntimeError):
            await db.ensure_schema_once("tree_counts", ddl)

    async def ok():
        await db.ensure_schema_once("tree_counts", ddl)
        await db.ensure_schema_once("preferences", other)

    asyncio.run(fail())
    asyncio.run(ok())  # the per-key lock from the first loop is not reused
    assert (ddl.runs, other.runs) == (2, 1)
    db.reset_schema_registry()
    asyncio.run(ok())
    assert (ddl.runs, other.runs) == (3, 2)


# ─── Shared helpers match the originals ──────────────────────────────────────


def test_has_item_status_column_matches_clients_and_arrangements():
    from app.apis import arrangements, clients

    class Conn:
        def __init__(self, value):
            self.value = value
            self.sql: list[str] = []

        async def fetchval(self, sql, *args):
            self.sql.append(sql)
            return self.value

    for value, expected in ((True, True), (None, False), (0, False)):
        conns = [Conn(value) for _ in range(3)]
        results = [
            asyncio.run(fn(c))
            for fn, c in zip(
                (db.has_item_status_column, clients.has_item_status_column,
                 arrangements.has_item_status_column),
                conns,
            )
        ]
        assert results == [expected] * 3
        assert conns[0].sql == conns[1].sql == conns[2].sql


def test_products_reexports_shared_get_conn():
    import importlib

    for name in ("products", "jobs", "orders", "dashboard"):
        module = importlib.import_module(f"app.apis.{name}")
        # fake_db is not active here, so every one is the real shared function.
        assert module.get_conn is db.get_conn, name


HELPER_INPUTS = [0, 1234.5, 1234.567, None, "abc", -5, '<a href="x">&</a>', 'Tom & "Jerry" <b>']


def _outcome(fn, value):
    try:
        return ("ok", fn(value))
    except Exception as exc:  # noqa: BLE001
        return ("raises", type(exc).__name__)


@pytest.mark.parametrize("value", HELPER_INPUTS)
def test_export_format_matches_orders_and_jobs(value):
    from app.apis.jobs import export as jobs_export
    from app.apis.orders import export as orders_export

    assert _outcome(export_format.money, value) == _outcome(orders_export._money, value)
    assert _outcome(export_format.money, value) == _outcome(jobs_export._money, value)
    assert _outcome(export_format.esc, value) == _outcome(orders_export._esc, value)
    assert _outcome(export_format.esc, value) == _outcome(jobs_export._esc, value)


def test_export_format_concrete_values():
    assert export_format.esc(0) == "0"
    assert export_format.esc(None) == ""
    assert export_format.esc('a "b" & <c>') == "a &quot;b&quot; &amp; &lt;c&gt;"
    assert export_format.money("abc") == ""
    assert export_format.money(None) == ""
    assert export_format.money(0) == "$0.00"


@pytest.mark.parametrize(
    "value",
    [None, {"a": 1}, [1], (1,), 5, b"{}", '{"a": 1}', "{nope", "", "NaN"],
)
def test_loads_json_matches_preferences_and_install_schedule(value):
    from app.apis import install_schedule, preferences

    expected = _outcome(preferences._loads, value)
    assert _outcome(jsonutil.loads_json, value) == expected
    assert _outcome(install_schedule._loads, value) == expected


def test_loads_json_diverges_from_designs_on_deep_nesting():
    from app.apis import designs

    deep = "[" * 200_000 + "]" * 200_000
    assert _outcome(designs._loads, deep) == ("ok", None)
    assert _outcome(jsonutil.loads_json, deep) == ("raises", "RecursionError")
