"""Shared database access for the API modules.

``get_conn()`` is a drop-in replacement for the per-module helper that did
``asyncpg.connect(DATABASE_URL, statement_cache_size=0)``. Call sites keep the
exact same shape::

    conn = await get_conn()
    try:
        ...
    finally:
        await conn.close()

but the connection now comes from an asyncpg pool, and ``close()`` hands it
back instead of tearing it down.

Design notes
------------
* **Lazy, per event loop.** The pool is created on first use, reading
  ``DATABASE_URL`` at call time. asyncpg pools are bound to the loop they were
  created on, and scripts/tests call ``asyncio.run`` repeatedly, so one pool is
  kept per running loop; pools of loops that have since closed are dropped.
* **Leak safety.** A code path that forgets ``close()`` used to leak one
  throwaway connection; with a pool it would slowly starve every request. So
  acquisition has a timeout (``DB_POOL_ACQUIRE_TIMEOUT``, default 5 s) and on
  timeout falls back to a plain direct connection with a warning, i.e. today's
  behaviour, rather than hanging.
* **Kill switch.** ``DB_POOL_DISABLED=true`` makes every call a direct
  connect. If pool creation raises, that call and the next
  ``POOL_RETRY_AFTER_S`` seconds of calls on that loop also direct-connect.
* ``ensure_schema_once`` replaces the per-module ``_SCHEMA_READY`` flags.

Environment: ``DATABASE_URL``, ``DB_POOL_MAX`` (default 10),
``DB_POOL_ACQUIRE_TIMEOUT`` (seconds, default 5), ``DB_POOL_DISABLED``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable

import asyncpg

logger = logging.getLogger(__name__)

DEFAULT_POOL_MAX = 10
DEFAULT_ACQUIRE_TIMEOUT_S = 5.0
#: After a failed pool creation, direct-connect for this long before retrying.
POOL_RETRY_AFTER_S = 30.0
#: How long ``close_pool`` waits for checked-out connections before terminating.
CLOSE_TIMEOUT_S = 10.0


# ─── Configuration (read at call time, never at import time) ────────────────


def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _pool_disabled() -> bool:
    return os.environ.get("DB_POOL_DISABLED", "").strip().lower() == "true"


def _env_number(name: str, default, cast):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return cast(raw.strip())
    except ValueError:
        logger.warning("ignoring invalid %s=%r; using %s", name, raw, default)
        return default


def _pool_max() -> int:
    return max(1, _env_number("DB_POOL_MAX", DEFAULT_POOL_MAX, int))


def _acquire_timeout() -> float:
    value = _env_number("DB_POOL_ACQUIRE_TIMEOUT", DEFAULT_ACQUIRE_TIMEOUT_S, float)
    return value if value > 0 else DEFAULT_ACQUIRE_TIMEOUT_S


async def _direct_connect():
    """Exactly what every module's ``get_conn`` did before the pool existed."""
    return await asyncpg.connect(_database_url(), statement_cache_size=0)


# ─── Pooled connection proxy ────────────────────────────────────────────────


class PooledConn:
    """A pool-acquired connection that looks like a plain asyncpg ``Connection``.

    Everything is delegated to the underlying connection except ``close()``,
    which releases it back to the pool (once; later calls are no-ops) and
    ``is_closed()``, which is true once released.
    """

    def __init__(self, pool, conn) -> None:
        self._pool = pool
        self._conn = conn
        self._released = False

    def __getattr__(self, name: str) -> Any:
        # Only reached for names not set in __init__. Guard the internals so a
        # half-constructed proxy (copy/pickle) cannot recurse forever.
        if name in ("_pool", "_conn", "_released"):
            raise AttributeError(name)
        return getattr(self._conn, name)

    async def close(self, *, timeout: float | None = None) -> None:
        if self._released:
            return
        self._released = True
        await self._pool.release(self._conn, timeout=timeout)

    def is_closed(self) -> bool:
        return self._released or self._conn.is_closed()

    def __repr__(self) -> str:
        state = "released" if self._released else "acquired"
        return f"<PooledConn {state} {self._conn!r}>"


# ─── Pool management (one pool per event loop) ──────────────────────────────


class _LoopState:
    __slots__ = ("pool", "lock", "failed_at")

    def __init__(self) -> None:
        self.pool = None
        self.lock = asyncio.Lock()
        self.failed_at: float | None = None


_states: dict[asyncio.AbstractEventLoop, _LoopState] = {}


def _prune_dead_loops() -> None:
    """Forget pools whose event loop has finished (e.g. a past ``asyncio.run``)."""
    for loop, state in list(_states.items()):
        if not loop.is_closed():
            continue
        _states.pop(loop, None)
        if state.pool is not None:
            try:
                state.pool.terminate()
            except Exception:  # noqa: BLE001 - its loop is gone; best effort only
                pass


def _state_for(loop: asyncio.AbstractEventLoop) -> _LoopState:
    state = _states.get(loop)
    if state is None:
        _prune_dead_loops()
        state = _states[loop] = _LoopState()
    return state


def _in_failure_cooldown(state: _LoopState) -> bool:
    return state.failed_at is not None and time.monotonic() - state.failed_at < POOL_RETRY_AFTER_S


async def _get_pool():
    """The pool for the running loop, creating it if needed; ``None`` = direct-connect."""
    state = _state_for(asyncio.get_running_loop())
    if state.pool is not None:
        return state.pool
    if _in_failure_cooldown(state):
        return None
    async with state.lock:
        if state.pool is not None:
            return state.pool
        if _in_failure_cooldown(state):
            return None
        try:
            state.pool = await asyncpg.create_pool(
                _database_url(),
                statement_cache_size=0,
                min_size=1,
                max_size=_pool_max(),
            )
        except Exception as exc:  # noqa: BLE001 - fall back to today's behaviour
            state.failed_at = time.monotonic()
            logger.warning(
                "asyncpg pool creation failed (%r); using direct connections for %.0fs",
                exc,
                POOL_RETRY_AFTER_S,
            )
            return None
        state.failed_at = None
        return state.pool


async def get_conn():
    """A connection usable exactly like ``asyncpg.Connection``; always ``close()`` it."""
    if _pool_disabled():
        return await _direct_connect()
    pool = await _get_pool()
    if pool is None:
        return await _direct_connect()
    timeout = _acquire_timeout()
    try:
        conn = await pool.acquire(timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            "DB pool acquire timed out after %.1fs (max_size=%d); opening a direct "
            "connection instead. Some code path may not be closing its connection.",
            timeout,
            _pool_max(),
        )
        return await _direct_connect()
    except Exception as exc:  # noqa: BLE001 - e.g. pool closing during shutdown
        logger.warning("DB pool acquire failed (%r); opening a direct connection", exc)
        return await _direct_connect()
    return PooledConn(pool, conn)


async def close_pool() -> None:
    """Close the running loop's pool, if it has one. Safe to call repeatedly."""
    state = _states.pop(asyncio.get_running_loop(), None)
    _prune_dead_loops()
    if state is None or state.pool is None:
        return
    pool = state.pool
    try:
        await asyncio.wait_for(pool.close(), CLOSE_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(
            "DB pool did not close within %.0fs (connections still checked out); terminating",
            CLOSE_TIMEOUT_S,
        )
        pool.terminate()


# ─── Schema bootstrap ───────────────────────────────────────────────────────

_schema_done: set[str] = set()
_schema_locks: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}


async def ensure_schema_once(key: str, ddl_fn: Callable[[], Awaitable[Any]]) -> None:
    """Await ``ddl_fn()`` until it first succeeds for ``key``, then never again.

    Mirrors the old module-level ``_SCHEMA_READY`` flag: the key is marked done
    only after the DDL returns, so a failure is retried on the next call. Unlike
    the flag, concurrent first callers wait for one run instead of all running it.
    """
    if key in _schema_done:
        return
    loop = asyncio.get_running_loop()
    entry = _schema_locks.get(key)
    if entry is None or entry[0] is not loop:
        entry = _schema_locks[key] = (loop, asyncio.Lock())
    async with entry[1]:
        if key in _schema_done:
            return
        await ddl_fn()
        _schema_done.add(key)
        _schema_locks.pop(key, None)


def reset_schema_registry() -> None:
    """Forget which schemas were ensured (tests: simulate a cold process)."""
    _schema_done.clear()
    _schema_locks.clear()


# ─── Shared queries ─────────────────────────────────────────────────────────


async def has_item_status_column(conn) -> bool:
    return bool(await conn.fetchval("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'container_items'
              AND column_name = 'status'
        )
    """))
