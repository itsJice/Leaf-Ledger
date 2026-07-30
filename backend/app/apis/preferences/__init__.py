"""Per-account UI preferences — sidebar layout and appearance.

One row per signed-in user holding a small JSON document:

    {"sidebar": {"order": [...], "hidden": [...]},
     "theme":   {"mode": "system|light|dark", "accent": "<key>"}}

Three things make this more than a key/value store:

1. **Partial writes must not clobber siblings.** Two independent UI surfaces —
   the sidebar editor and the appearance picker — `PUT` to this same endpoint,
   at the same time, each sending only its own subtree. A whole-object write
   would have them overwrite each other (the theme picker would erase a
   drag-reorder that was in flight, and vice versa). So `PUT` takes a *partial*
   document and deep-merges it, and the read-modify-write happens inside a
   transaction that takes a `FOR UPDATE` row lock, so two concurrent requests
   serialise instead of both merging onto the same stale snapshot.

2. **`GET` never 404s and never fails the first paint.** A user with no row is
   not an error, it's the common case; and a storage hiccup must degrade to the
   defaults rather than leave the app with no sidebar. Both return
   `DEFAULT_PREFERENCES` deep-merged under whatever is stored.

3. **`/` and `/settings` can never be hidden.** They are stripped from
   `sidebar.hidden` here, on the server, on every write and every read — a user
   who hid Settings would have no screen left from which to un-hide it, and
   that invariant is too important to leave to the client.

Storage note: this lives in `ll_app.user_preferences`. `ll_app` is where
app-owned tables go — the ones this application invents for itself, as opposed
to the catalog/project tables in `public` that the scrapers and imports own.
`ll_app.orders` / `ll_app.order_items` set that convention. It is a namespacing
choice, not a permissions one: the connection is `postgres` and could create in
`public` perfectly well.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Request

from app.apis.user_context import get_request_user_id

router = APIRouter(prefix="/preferences", tags=["preferences"])


# ─── The shape ───────────────────────────────────────────────────────────────

#: `sidebar.order` is deliberately empty by default: it means "no
#: customisation", and the client places every nav item at its own default
#: position. Listing the shipped tabs here instead would freeze today's nav into
#: every user's stored preferences, so a newly-shipped tab would never appear.
DEFAULT_PREFERENCES: dict[str, Any] = {
    "sidebar": {"order": [], "hidden": []},
    "theme": {"mode": "system", "accent": "emerald"},
}

THEME_MODES = ("system", "light", "dark")

#: Nav paths a user may never hide — see the module docstring.
PINNED_PATHS = ("/", "/settings")

MAX_LIST_ITEMS = 64
MAX_PATH_LEN = 200
MAX_ACCENT_LEN = 64


async def get_conn():
    return await asyncpg.connect(
        os.environ.get("DATABASE_URL"), statement_cache_size=0
    )


_SCHEMA_READY = False

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.user_preferences (
    user_id    text PRIMARY KEY,
    prefs      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


async def ensure_schema(conn):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    await conn.execute(DDL)
    _SCHEMA_READY = True


# ─── Merging ─────────────────────────────────────────────────────────────────


def deep_merge(base: dict, patch: dict) -> dict:
    """`patch` laid over `base`, recursing into nested objects.

    Objects merge key by key, so a patch of `{"theme": {"mode": "dark"}}` keeps
    `theme.accent`. Everything else — including lists — replaces wholesale,
    which is what `sidebar.hidden` needs: un-hiding an item is expressed by
    sending the shorter list, and a merged list could never shrink.
    """
    out = dict(base)
    for key, value in patch.items():
        current = out.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            out[key] = deep_merge(current, value)
        else:
            out[key] = value
    return out


# ─── Validation ──────────────────────────────────────────────────────────────
# Two modes. Reading stored JSON is forgiving — a value that has gone bad in the
# database must degrade to the default, not 500 the sidebar. Writing is strict,
# so a buggy caller hears about it instead of silently storing junk. Both drop
# unknown keys, so an older server never chokes on a newer client's field.


def _loads(raw: Any) -> Any:
    """json.loads that returns None instead of raising. asyncpg may hand back
    either a decoded object or the raw jsonb text depending on codecs."""
    if raw is None or isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def canon_path(path: str) -> str:
    """Fold a nav path for comparison: lowercased, no trailing slash.

    So `"/Settings"`, `"/settings/"` and `"/settings"` are all recognised as the
    pinned Settings tab — the un-hideable invariant must not be defeatable by
    sending a differently-spelled path.
    """
    text = path.strip().lower()
    if not text:
        return "/"
    return text.rstrip("/") or "/"


def _string_list(value: Any, field: str, strict: bool) -> Optional[list[str]]:
    """A clean list of paths, or None when the value isn't usable at all."""
    if not isinstance(value, list):
        if strict:
            raise HTTPException(status_code=422, detail=f"{field} must be an array of strings")
        return None
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or len(item) > MAX_PATH_LEN:
            if strict:
                raise HTTPException(
                    status_code=422, detail=f"{field} must be an array of strings"
                )
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out[:MAX_LIST_ITEMS]


def normalize(raw: Any, strict: bool = False) -> dict:
    """Validate a full or partial preferences document.

    Returns only the keys that were actually present, so the result is safe to
    deep-merge as a patch. `strict=True` raises 422 on a malformed value;
    otherwise the bad value is dropped and the default shows through.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        if strict:
            raise HTTPException(status_code=422, detail="preferences must be an object")
        return {}

    out: dict[str, Any] = {}

    if "sidebar" in raw:
        raw_sidebar = raw["sidebar"]
        if not isinstance(raw_sidebar, dict):
            if strict:
                raise HTTPException(status_code=422, detail="sidebar must be an object")
        else:
            sidebar: dict[str, Any] = {}
            if "order" in raw_sidebar:
                order = _string_list(raw_sidebar["order"], "sidebar.order", strict)
                if order is not None:
                    sidebar["order"] = order
            if "hidden" in raw_sidebar:
                hidden = _string_list(raw_sidebar["hidden"], "sidebar.hidden", strict)
                if hidden is not None:
                    # The invariant, enforced server-side on every write AND
                    # every read: Dashboard and Settings are never hidden.
                    sidebar["hidden"] = [
                        p for p in hidden if canon_path(p) not in PINNED_PATHS
                    ]
            if sidebar:
                out["sidebar"] = sidebar

    if "theme" in raw:
        raw_theme = raw["theme"]
        if not isinstance(raw_theme, dict):
            if strict:
                raise HTTPException(status_code=422, detail="theme must be an object")
        else:
            theme: dict[str, Any] = {}
            if "mode" in raw_theme:
                mode = raw_theme["mode"]
                mode = mode.strip().lower() if isinstance(mode, str) else None
                if mode in THEME_MODES:
                    theme["mode"] = mode
                elif strict:
                    raise HTTPException(
                        status_code=422,
                        detail="theme.mode must be one of: " + ", ".join(THEME_MODES),
                    )
            if "accent" in raw_theme:
                accent = raw_theme["accent"]
                accent = accent.strip() if isinstance(accent, str) else None
                # The accent vocabulary lives in the frontend's THEME_ACCENTS,
                # so this checks shape only — a bounded, non-empty key — rather
                # than a list the backend would have to be kept in sync with.
                if accent and len(accent) <= MAX_ACCENT_LEN:
                    theme["accent"] = accent
                elif strict:
                    raise HTTPException(
                        status_code=422, detail="theme.accent must be a non-empty string"
                    )
            if theme:
                out["theme"] = theme

    return out


def with_defaults(stored: Any) -> dict:
    """The full document the client sees: defaults, with stored values on top."""
    return deep_merge(DEFAULT_PREFERENCES, normalize(stored, strict=False))


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("")
async def get_preferences(request: Request) -> dict:
    """This user's preferences, always complete, never a 404.

    A missing row and an unreachable database both mean "no stored
    preferences" as far as the UI is concerned, and both yield the defaults —
    the sidebar has to render either way.
    """
    user_id = get_request_user_id(request)
    stored: Any = None
    try:
        conn = await get_conn()
        try:
            await ensure_schema(conn)
            stored = await conn.fetchval(
                "SELECT prefs FROM ll_app.user_preferences WHERE user_id = $1", user_id
            )
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001 — degrade to defaults, never blank the app
        print(f"preferences: read failed for {user_id}, serving defaults: {exc}")
    return with_defaults(_loads(stored))


@router.put("")
async def put_preferences(request: Request, body: Any = Body(default=None)) -> dict:
    """Deep-merge a **partial** document into this user's preferences.

    Send only what changed. Keys that aren't sent are left exactly as they are,
    which is what makes it safe for the sidebar editor and the theme picker to
    write independently and concurrently. The response is the resulting full
    document, so the caller can reconcile its optimistic state against it.
    """
    patch = normalize(body, strict=True)
    user_id = get_request_user_id(request)

    try:
        conn = await get_conn()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Preferences storage unavailable") from exc
    try:
        await ensure_schema(conn)
        # Read-modify-write under a row lock. Without the lock, two concurrent
        # partial PUTs would both read the same snapshot and the second write
        # would drop the first one's subtree; with it, the second request waits
        # and merges onto the already-updated row.
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO ll_app.user_preferences (user_id, prefs)
                VALUES ($1, '{}'::jsonb)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id,
            )
            current = await conn.fetchval(
                "SELECT prefs FROM ll_app.user_preferences WHERE user_id = $1 FOR UPDATE",
                user_id,
            )
            merged = deep_merge(normalize(_loads(current), strict=False), patch)
            await conn.execute(
                """
                UPDATE ll_app.user_preferences
                   SET prefs = $2::jsonb, updated_at = now()
                 WHERE user_id = $1
                """,
                user_id,
                json.dumps(merged),
            )
    finally:
        await conn.close()

    return with_defaults(merged)
