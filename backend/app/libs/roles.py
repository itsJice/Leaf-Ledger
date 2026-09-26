"""Who may do what: roles for signed-in users.

Before this, every signed-in user could reach every page. Field leads now sign
in too, and they must only ever see the crew-days they run -- the install
schedule tool has every client's name, address and phone baked in.

Roles, lowest to highest:

    crew < lead < staff < admin < super_admin

plus ``viewer``, which sits outside that ladder: a read-only display login
(the warehouse iPad on the shop TV). It ranks with crew for every router,
except that it may make GET requests to a router that sets
``VIEWER_READ = True`` -- the install schedule. A lead can't read those, and
a viewer can't write anything.

How a login's role is decided, first match wins:

1. ``SUPER_ADMIN_EMAILS`` -- hard-coded so the owner can never be locked out,
   even by a bad row in the table below.
2. A row in ``ll_app.user_roles`` -- set from Settings > Users.
3. The install schedule's roster: a person whose email matches is ``lead`` if
   their title is Lead, else ``crew``. So a lead added to the roster in the
   schedule tool can sign in and see their shifts with no second setup step.
4. Anyone else is ``staff`` -- exactly the access every signed-in user had
   before roles existed, so office teammates keep working unchanged.

Routers opt in through a module-level ``MIN_ROLE`` (main.py reads it); a
router without one needs ``staff``.
"""
from __future__ import annotations

import os
import time
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException, Request

from app.auth.supabase_auth import get_current_user
from app.auth.user import User
from app.libs import db
from app.libs.db import ensure_schema_once

ROLES = ("crew", "viewer", "lead", "staff", "admin", "super_admin")
RANK = {"crew": 0, "viewer": 0, "lead": 1, "staff": 2, "admin": 3, "super_admin": 4}
READ_METHODS = frozenset({"GET", "HEAD"})
DEFAULT_ROLE = "staff"

SUPER_ADMIN_EMAILS = frozenset({"justice@wenzdays.com"})

#: Role lookups happen on every API call; the table changes a few times a
#: season. A short cache keeps that off the database, and writes clear it.
CACHE_TTL_S = 30.0
_cache: dict[str, tuple[float, str]] = {}

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;
CREATE TABLE IF NOT EXISTS ll_app.user_roles (
    email      text PRIMARY KEY,
    role       text NOT NULL,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
-- Re-stated on every boot rather than inline, so adding a role widens an
-- existing table too (this is how 'viewer' arrived -- migrations/016).
ALTER TABLE ll_app.user_roles DROP CONSTRAINT IF EXISTS user_roles_role_check;
ALTER TABLE ll_app.user_roles ADD CONSTRAINT user_roles_role_check
    CHECK (role IN ('crew','viewer','lead','staff','admin','super_admin'));
INSERT INTO ll_app.user_roles (email, role, updated_by)
VALUES ('justice@wenzdays.com', 'super_admin', 'seed')
ON CONFLICT (email) DO NOTHING;
"""


async def ensure_schema(conn) -> None:
    async def _ddl():
        await conn.execute(DDL)

    await ensure_schema_once("user_roles", _ddl)


def norm_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def at_least(role: str, minimum: str) -> bool:
    return RANK.get(role, -1) >= RANK[minimum]


def clear_cache() -> None:
    _cache.clear()


#: Returns the roster person for an email, or None. Injected so this module
#: does not import the schedule loader (and tests can stub it).
RosterLookup = Callable[[str], Awaitable[Optional[dict]]]


async def _roster_person(email: str) -> Optional[dict]:
    from app.libs import schedule_board

    return await schedule_board.roster_person_for_email(email)


async def resolve_role(email: Optional[str], roster_lookup: RosterLookup = None) -> str:
    e = norm_email(email)
    if e in SUPER_ADMIN_EMAILS:
        return "super_admin"
    if not e:
        return DEFAULT_ROLE
    hit = _cache.get(e)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        return hit[1]

    role: Optional[str] = None
    conn = await db.get_conn()
    try:
        await ensure_schema(conn)
        role = await conn.fetchval("SELECT role FROM ll_app.user_roles WHERE email = $1", e)
    finally:
        await conn.close()
    if role not in RANK:
        try:
            person = await (roster_lookup or _roster_person)(e)
        except Exception as exc:  # noqa: BLE001
            # Fail closed and don't cache: if the roster can't be read we
            # can't tell a lead from office staff, and guessing "staff" would
            # show a lead every client's address. The next call retries.
            print(f"roster role lookup failed for {e}: {exc}")
            return "crew"
        if person:
            role = "lead" if person.get("title") == "Lead" else "crew"
        else:
            role = DEFAULT_ROLE
    _cache[e] = (time.monotonic(), role)
    return role


def allowed(role: str, minimum: str, method: str, viewer_read: bool = False) -> bool:
    if role == "viewer" and viewer_read and method.upper() in READ_METHODS:
        return True
    return at_least(role, minimum)


def require_role(minimum: str, viewer_read: bool = False):
    """Router/endpoint dependency: 403 unless the user's role is >= minimum
    (or it's a viewer reading a ``viewer_read`` router)."""
    if minimum not in RANK:
        raise ValueError(f"unknown role {minimum!r}")

    async def _dep(request: Request) -> str:
        # Same local-dev-only escape hatch as main.py's AUTH_DISABLED.
        if os.getenv("AUTH_DISABLED", "").lower() == "true" and os.getenv("ENV", "dev") == "dev":
            return "super_admin"
        role = await resolve_role(get_current_user(request).email)
        if not allowed(role, minimum, request.method, viewer_read):
            raise HTTPException(status_code=403, detail="You don't have access to this")
        return role

    return _dep


async def role_of(user: User) -> str:
    return await resolve_role(user.email)
