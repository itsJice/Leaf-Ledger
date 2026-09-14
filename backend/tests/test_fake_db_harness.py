"""Self-tests for the shared fake asyncpg harness in ``conftest.py``."""

import asyncio
import re

from conftest import FakeConn, FakeDB, is_ddl


def _run(coro):
    return asyncio.run(coro)


def test_dispatch_by_substring_regex_and_method():
    db = FakeDB()
    db.on_fetch("FROM ll_app.widgets", [{"id": 1}, {"id": 2}])
    db.on_fetchval(re.compile(r"COUNT\(\*\)\s+FROM ll_app\.widgets"), 2)
    db.on("UPDATE ll_app.widgets", lambda sql, *args: f"UPDATE {args[0]}")
    conn = FakeConn(db)

    # Multi-line SQL still matches a one-line pattern (whitespace collapsed).
    rows = _run(conn.fetch("SELECT id\n   FROM   ll_app.widgets\n  ORDER BY id"))
    assert rows == [{"id": 1}, {"id": 2}]
    assert _run(conn.fetchval("SELECT COUNT(*)   FROM ll_app.widgets")) == 2
    assert _run(conn.execute("UPDATE ll_app.widgets SET x = 1", 3)) == "UPDATE 3"

    # on_fetch is scoped to fetch(): the same SQL via fetchrow falls through.
    assert _run(conn.fetchrow("SELECT id FROM ll_app.widgets")) is None
    # Static results are copies; mutating one call's rows does not leak.
    rows[0]["id"] = 99
    assert _run(conn.fetch("SELECT id FROM ll_app.widgets"))[0]["id"] == 1
    # Later registrations win, so a test can override a default.
    db.on_fetch("FROM ll_app.widgets", [])
    assert _run(conn.fetch("SELECT id FROM ll_app.widgets")) == []


def test_unmatched_ddl_is_counted_and_dml_gets_status_tags():
    db = FakeDB()
    conn = FakeConn(db)
    assert _run(conn.execute("CREATE TABLE IF NOT EXISTS ll_app.t (id int)")) == "OK"
    assert _run(conn.execute("CREATE SCHEMA IF NOT EXISTS ll_app; CREATE INDEX ON ll_app.t (id)")) == "OK"
    assert _run(conn.execute("  DO $$ BEGIN NULL; END $$")) == "OK"
    assert _run(conn.execute("ALTER TABLE ll_app.t ADD COLUMN y int")) == "OK"
    assert db.ddl_runs == 4
    assert _run(conn.execute("INSERT INTO ll_app.t (id) VALUES ($1)", 1)) == "INSERT 0 1"
    assert _run(conn.execute("DELETE FROM ll_app.t WHERE id = $1", 1)) == "DELETE 1"
    assert db.ddl_runs == 4
    assert not is_ddl("SELECT 'CREATE TABLE' FROM ll_app.t")
    assert _run(conn.fetch("SELECT 1")) == []
    assert _run(conn.fetchrow("SELECT 1")) is None
    assert _run(conn.fetchval("SELECT 1")) is None


def test_executed_log_records_every_call_verbatim():
    db = FakeDB()
    conn = FakeConn(db)
    _run(conn.execute("CREATE TABLE t (id int)"))
    _run(conn.fetchrow("INSERT INTO t (id)\n VALUES ($1) RETURNING *", 5))
    _run(conn.executemany("INSERT INTO t (id) VALUES ($1)", [(6,), (7,)]))
    assert db.executed == [
        ("CREATE TABLE t (id int)", ()),
        ("INSERT INTO t (id)\n VALUES ($1) RETURNING *", (5,)),
        ("INSERT INTO t (id) VALUES ($1)", (6,)),
        ("INSERT INTO t (id) VALUES ($1)", (7,)),
    ]
    assert [args for _, args in db.calls("INSERT INTO t")] == [(5,), (6,), (7,)]
    assert db.seen("RETURNING") and not db.seen("UPDATE")


def test_fixture_patches_get_conn_across_api_modules(fake_db):
    from app.apis import jobs, tree_counts

    assert fake_db.import_errors == []
    assert "app.apis.jobs" in fake_db.patched
    assert "app.apis.tree_counts" in fake_db.patched
    assert "app.apis.products" in fake_db.patched  # jobs/orders/dashboard import it
    for module in (jobs, tree_counts):
        conn = _run(module.get_conn())
        assert isinstance(conn, FakeConn) and conn.db is fake_db
    # tree_counts has migrated to app.libs.db's shared ensure_schema_once
    # registry (reset via reset_schema_registry(), asserted elsewhere); jobs
    # still carries the per-module flag this fixture resets.
    assert jobs._SCHEMA_READY is False


async def _txn_and_close(conn):
    async with conn.transaction():
        await conn.execute("UPDATE t SET x = 1")
    await conn.close()
    return conn.is_closed()


def test_transaction_is_a_noop_context_and_close_marks_closed():
    db = FakeDB()
    conn = FakeConn(db)
    assert not conn.is_closed()
    assert _run(_txn_and_close(conn)) is True
    assert db.seen("UPDATE t")
