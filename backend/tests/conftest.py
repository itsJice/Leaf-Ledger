"""Shared test harness: an SQL-dispatching fake asyncpg connection.

The API modules under ``app.apis`` each define (or import) a module-level
``get_conn()`` coroutine that opens a real asyncpg connection. Tests stub it.
Before this file existed every test module carried its own hand-rolled
``FakeDB``/``FakeConn`` pair that asserted on exact SQL strings; this is the
generalised, opt-in replacement. Existing tests that patch ``get_conn``
themselves keep working untouched -- nothing here is autouse.

Usage::

    from app.apis import tree_counts

    def test_create(fake_db, fake_user):
        fake_db.on_fetchrow("INSERT INTO ll_app.tree_counts", {"id": 7, ...})
        body = tree_counts.TreeCountIn(kind="install", height_ft=9, width_in=59)
        out = asyncio.run(tree_counts.create_tree_count(body, fake_user))
        assert out.id == 7
        assert fake_db.ddl_runs == 1                    # the CREATE TABLE ran once
        assert fake_db.seen("INSERT INTO ll_app.tree_counts")

Dispatch rules
--------------
* ``db.on(pattern, handler, method=None)`` registers ``handler(sql, *args)``
  for any SQL whose whitespace-collapsed text contains ``pattern`` (a
  substring, or a compiled regex which is ``search``-ed). ``method`` narrows
  it to one asyncpg method (``"fetch"``, ``"fetchrow"``, ``"fetchval"``,
  ``"execute"``); ``None`` matches all of them. Handlers may be plain or
  ``async`` functions. The most recently registered matching handler wins,
  so a test can override a default it set up earlier.
* ``db.on_fetch(pattern, rows)`` / ``db.on_fetchrow(pattern, row)`` /
  ``db.on_fetchval(pattern, value)`` / ``db.on_execute(pattern, status)``
  are the static-return conveniences; ``rows``/``row`` are shallow-copied
  on every call so a handler's mutation of one result cannot leak.
* Unmatched calls fall back to asyncpg-shaped defaults: ``fetch`` -> ``[]``,
  ``fetchrow``/``fetchval`` -> ``None``, ``execute`` of DDL (``CREATE``,
  ``ALTER``, ``DROP``, ``DO $$`` ... at the start of any statement in the
  string) increments ``db.ddl_runs`` and returns ``"OK"``; any other
  ``execute`` returns an asyncpg-style status tag (``"INSERT 0 1"``,
  ``"UPDATE 1"``, ``"DELETE 1"``).
* Every call, matched or not, is appended to ``db.executed`` as
  ``(sql, args)`` with the SQL exactly as the code sent it.

Rows
----
Handlers return plain ``dict`` rows. That is enough for the code under test:
asyncpg ``Record`` supports ``row["col"]``, ``dict(row)``, ``row.get(...)``,
``.keys()``/``.items()`` and iteration over values -- a ``dict`` matches all
but the last, and nothing in ``app.apis`` iterates a Record positionally.
"""

from __future__ import annotations

import base64
import importlib
import inspect
import json
import pathlib
import re
from typing import Any, Callable, Pattern

import pytest

from app.auth.user import User

# ─── SQL helpers ─────────────────────────────────────────────────────────────

_WS = re.compile(r"\s+")
# A DDL keyword at the start of the string or of any `;`-separated statement.
_DDL = re.compile(r"(?:^|;)\s*(?:(?:CREATE|ALTER|DROP|TRUNCATE)\b|DO\s+\$\$)", re.I)
_FIRST_WORD = re.compile(r"^\s*([A-Za-z]+)")


def normalise_sql(sql: str) -> str:
    """Collapse whitespace so multi-line SQL matches a one-line pattern."""
    return _WS.sub(" ", sql).strip()


def is_ddl(sql: str) -> bool:
    return _DDL.search(normalise_sql(sql)) is not None


def _default_execute_status(sql: str) -> str:
    word = (_FIRST_WORD.match(sql) or [None, ""])[1].upper()
    if word == "INSERT":
        return "INSERT 0 1"
    if word in ("UPDATE", "DELETE", "SELECT"):
        return f"{word} 1"
    return "OK"


def _copy(value: Any) -> Any:
    """Shallow-copy static results so one call cannot corrupt the next."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return [dict(v) if isinstance(v, dict) else v for v in value]
    return value


# ─── Fake DB ─────────────────────────────────────────────────────────────────

Handler = Callable[..., Any]


class FakeDB:
    """Handler registry + call log shared by every ``FakeConn`` a test opens."""

    METHODS = ("execute", "fetch", "fetchrow", "fetchval")

    def __init__(self) -> None:
        self.ddl_runs: int = 0
        self.executed: list[tuple[str, tuple]] = []
        self.import_errors: list[tuple[str, str]] = []
        self.patched: list[str] = []
        self._handlers: list[tuple[str | Pattern[str], str | None, Handler]] = []

    # registration ----------------------------------------------------------
    def on(self, pattern: str | Pattern[str], handler: Handler, *, method: str | None = None) -> "FakeDB":
        if method is not None and method not in self.METHODS:
            raise ValueError(f"unknown asyncpg method {method!r}; expected one of {self.METHODS}")
        if isinstance(pattern, str):
            pattern = normalise_sql(pattern)
        self._handlers.append((pattern, method, handler))
        return self

    def on_fetch(self, pattern: str | Pattern[str], rows: list[dict]) -> "FakeDB":
        return self.on(pattern, lambda sql, *args: _copy(list(rows)), method="fetch")

    def on_fetchrow(self, pattern: str | Pattern[str], row: dict | None) -> "FakeDB":
        return self.on(pattern, lambda sql, *args: _copy(row), method="fetchrow")

    def on_fetchval(self, pattern: str | Pattern[str], value: Any) -> "FakeDB":
        return self.on(pattern, lambda sql, *args: _copy(value), method="fetchval")

    def on_execute(self, pattern: str | Pattern[str], status: str = "OK") -> "FakeDB":
        return self.on(pattern, lambda sql, *args: status, method="execute")

    # inspection ------------------------------------------------------------
    def calls(self, pattern: str | Pattern[str]) -> list[tuple[str, tuple]]:
        """Every ``(sql, args)`` in ``executed`` whose SQL matches ``pattern``."""
        return [(sql, args) for sql, args in self.executed if self._matches(pattern, sql)]

    def seen(self, pattern: str | Pattern[str]) -> bool:
        return bool(self.calls(pattern))

    # dispatch --------------------------------------------------------------
    @staticmethod
    def _matches(pattern: str | Pattern[str], sql: str) -> bool:
        text = normalise_sql(sql)
        if isinstance(pattern, str):
            return normalise_sql(pattern) in text
        return pattern.search(text) is not None

    def _find(self, method: str, sql: str) -> Handler | None:
        for pattern, wanted, handler in reversed(self._handlers):
            if wanted not in (None, method):
                continue
            if self._matches(pattern, sql):
                return handler
        return None

    async def dispatch(self, method: str, sql: str, args: tuple) -> Any:
        self.executed.append((sql, tuple(args)))
        handler = self._find(method, sql)
        if handler is not None:
            result = handler(sql, *args)
            if inspect.isawaitable(result):
                result = await result
            return result
        if method == "fetch":
            return []
        if method in ("fetchrow", "fetchval"):
            return None
        if is_ddl(sql):
            self.ddl_runs += 1
            return "OK"
        return _default_execute_status(sql)


class _NoopTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    # asyncpg also allows `tx = conn.transaction(); await tx.start(); ...`
    async def start(self):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


class FakeConn:
    """The asyncpg connection surface the API modules use, backed by a FakeDB."""

    def __init__(self, db: FakeDB) -> None:
        self.db = db
        self._closed = False

    async def execute(self, sql: str, *args):
        return await self.db.dispatch("execute", sql, args)

    async def fetch(self, sql: str, *args):
        return await self.db.dispatch("fetch", sql, args)

    async def fetchrow(self, sql: str, *args):
        return await self.db.dispatch("fetchrow", sql, args)

    async def fetchval(self, sql: str, *args):
        return await self.db.dispatch("fetchval", sql, args)

    async def executemany(self, sql: str, args_iter, *_, **__):
        for args in args_iter:
            await self.db.dispatch("execute", sql, tuple(args))
        return None

    def transaction(self, *_, **__):
        return _NoopTransaction()

    def is_closed(self) -> bool:
        return self._closed

    async def close(self, *_, **__):
        self._closed = True


# ─── Request / user stand-ins ────────────────────────────────────────────────


class FakeRequest:
    """Just enough ``Request`` for ``app.apis.user_context.get_request_user_id``.

    That helper only decodes the JWT payload (it never verifies a signature),
    so an unsigned ``header.<payload>.signature`` token is enough. ``None``
    means an anonymous request with no Authorization header.
    """

    def __init__(self, user_id: str | None = None):
        if user_id is None:
            self.headers: dict[str, str] = {}
        else:
            payload = base64.urlsafe_b64encode(
                json.dumps({"sub": user_id}).encode()
            ).decode().rstrip("=")
            self.headers = {"Authorization": f"Bearer header.{payload}.signature"}


# ─── Fixtures ────────────────────────────────────────────────────────────────

_APIS_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "apis"
_EXTRA_MODULES = ("jobs.export", "orders.export")
_RESET_FLAGS = {"_SCHEMA_READY": False, "_PROJECT_SCHEMA_CHECKED": False}


def api_module_names() -> list[str]:
    """Every ``app.apis.<pkg>`` package plus the known submodules."""
    names = sorted(p.parent.name for p in _APIS_DIR.glob("*/__init__.py"))
    return names + list(_EXTRA_MODULES)


@pytest.fixture
def fake_db(monkeypatch) -> FakeDB:
    """A FakeDB wired into every ``app.apis`` module's ``get_conn``.

    Also resets the module-level "schema already ensured" flags so the DDL
    path runs (and is counted in ``ddl_runs``) exactly as it would on a cold
    process. Modules that fail to import are recorded in ``db.import_errors``
    rather than failing the fixture.
    """
    db = FakeDB()

    async def fake_get_conn(*_, **__):
        return FakeConn(db)

    for name in api_module_names():
        dotted = f"app.apis.{name}"
        try:
            module = importlib.import_module(dotted)
        except Exception as exc:  # noqa: BLE001 - collected for the test to assert on
            db.import_errors.append((dotted, repr(exc)))
            continue
        if hasattr(module, "get_conn"):
            monkeypatch.setattr(module, "get_conn", fake_get_conn)
            db.patched.append(dotted)
        for flag, value in _RESET_FLAGS.items():
            if hasattr(module, flag):
                monkeypatch.setattr(module, flag, value)
    return db


@pytest.fixture
def fake_user() -> User:
    return User(sub="user-1", user_id="user-1", email="crew@example.com", name="crew")


@pytest.fixture
def fake_request() -> Callable[[str | None], FakeRequest]:
    """Factory: ``fake_request("user-7")`` or ``fake_request()`` for anonymous."""
    return FakeRequest
