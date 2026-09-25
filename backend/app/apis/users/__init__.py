"""Settings > Users: who has which role. Super admins only.

Lists every login Supabase knows about, alongside anyone who has a role row
or is on the install schedule roster, so a lead can be set up before they
have ever signed in. See app.libs.roles for how a role is decided when
there is no row.
"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import AuthorizedUser
from app.libs import roles, schedule_board
from app.libs.db import get_conn

router = APIRouter(prefix="/users", tags=["users"])

MIN_ROLE = "super_admin"


@router.get("")
async def list_users() -> dict:
    conn = await get_conn()
    try:
        await roles.ensure_schema(conn)
        rows = await conn.fetch("SELECT email, role, updated_by, updated_at FROM ll_app.user_roles")
        try:
            logins = await conn.fetch(
                "SELECT lower(email) AS email, last_sign_in_at FROM auth.users WHERE email IS NOT NULL")
        except Exception as exc:  # noqa: BLE001 - the app DB role may not see auth.users
            print(f"auth.users not readable: {exc}")
            logins = []
    finally:
        await conn.close()

    people = {}
    try:
        board = await schedule_board.load_board()
        for p in (board.roster if board else []):
            if p.get("email"):
                people[roles.norm_email(p["email"])] = p
    except Exception as exc:  # noqa: BLE001
        print(f"roster not readable for users list: {exc}")

    explicit = {r["email"]: r for r in rows}
    last_seen = {r["email"]: r["last_sign_in_at"] for r in logins}
    out = []
    for email in sorted(set(explicit) | set(last_seen) | set(people)):
        effective = await roles.resolve_role(email)
        r = explicit.get(email)
        p = people.get(email)
        seen = last_seen.get(email)
        out.append({
            "email": email,
            "role": effective,
            "explicit": r["role"] if r else None,
            "locked": email in roles.SUPER_ADMIN_EMAILS,
            "rosterName": p["name"] if p else None,
            "rosterTitle": p["title"] if p else None,
            "lastSignIn": seen.isoformat() if seen else None,
        })
    return {"users": out, "roles": list(roles.ROLES)}


class RoleIn(BaseModel):
    email: str
    # None clears the row, so the role falls back to the roster/default.
    role: Literal["crew", "viewer", "lead", "staff", "admin", "super_admin"] | None


@router.put("")
async def set_role(body: RoleIn, user: AuthorizedUser) -> dict:
    email = roles.norm_email(body.email)
    if "@" not in email:
        raise HTTPException(status_code=400, detail="That isn't an email address")
    if email in roles.SUPER_ADMIN_EMAILS:
        raise HTTPException(status_code=400, detail="The owner's role can't be changed")
    conn = await get_conn()
    try:
        await roles.ensure_schema(conn)
        if body.role is None:
            await conn.execute("DELETE FROM ll_app.user_roles WHERE email = $1", email)
        else:
            await conn.execute(
                "INSERT INTO ll_app.user_roles (email, role, updated_by) VALUES ($1, $2, $3) "
                "ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role, "
                "updated_by = EXCLUDED.updated_by, updated_at = now()",
                email, body.role, user.email)
    finally:
        await conn.close()
    roles.clear_cache()
    return {"email": email, "role": await roles.resolve_role(email)}
