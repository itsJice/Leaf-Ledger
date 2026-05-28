from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import asyncpg
import os
from datetime import datetime
from app.auth import AuthorizedUser

router = APIRouter(prefix="/settings", tags=["settings"])
DATABASE_URL = os.environ.get("DATABASE_URL")

async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

CATEGORIES = ["plant", "container", "filler", "accent", "other"]

class MarkupSettingOut(BaseModel):
    id: int
    category: Optional[str]
    markup_percentage: float
    updated_at: datetime

class MarkupUpdate(BaseModel):
    category: Optional[str] = None  # None = global
    markup_percentage: float

class AllMarkupSettings(BaseModel):
    global_markup: float
    category_markups: List[MarkupSettingOut]

class UserRoleOut(BaseModel):
    user_id: str
    role: str
    created_at: datetime

class UserRoleUpdate(BaseModel):
    user_id: str
    role: str

@router.get("/markup", response_model=AllMarkupSettings)
async def get_markup_settings():
    conn = await get_conn()
    try:
        rows = await conn.fetch("SELECT * FROM markup_settings ORDER BY category NULLS FIRST")
        global_markup = 30.0
        category_markups = []
        for r in rows:
            if r["category"] is None:
                global_markup = float(r["markup_percentage"])
            else:
                category_markups.append(dict(r))
        return {"global_markup": global_markup, "category_markups": category_markups}
    finally:
        await conn.close()

@router.put("/markup")
async def update_markup(body: MarkupUpdate, user: AuthorizedUser):
    conn = await get_conn()
    try:
        existing = await conn.fetchrow(
            "SELECT id FROM markup_settings WHERE category IS NOT DISTINCT FROM $1", body.category
        )
        if existing:
            await conn.execute(
                "UPDATE markup_settings SET markup_percentage = $1, updated_by = $2, updated_at = NOW() WHERE id = $3",
                body.markup_percentage, user.sub, existing["id"]
            )
        else:
            await conn.execute(
                "INSERT INTO markup_settings (category, markup_percentage, updated_by) VALUES ($1, $2, $3)",
                body.category, body.markup_percentage, user.sub
            )
        return {"ok": True}
    finally:
        await conn.close()

@router.delete("/markup/category/{category}")
async def delete_category_markup(category: str, user: AuthorizedUser):
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM markup_settings WHERE category = $1", category)
        return {"ok": True}
    finally:
        await conn.close()

@router.get("/roles", response_model=List[UserRoleOut])
async def list_user_roles(user: AuthorizedUser):
    conn = await get_conn()
    try:
        rows = await conn.fetch("SELECT * FROM user_roles ORDER BY created_at DESC")
        return [dict(r) for r in rows]
    finally:
        await conn.close()

@router.post("/roles")
async def set_user_role(body: UserRoleUpdate, user: AuthorizedUser):
    conn = await get_conn()
    try:
        await conn.execute("""
            INSERT INTO user_roles (user_id, role) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET role = $2
        """, body.user_id, body.role)
        return {"ok": True}
    finally:
        await conn.close()

@router.get("/my-role")
async def get_my_role(user: AuthorizedUser):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT role FROM user_roles WHERE user_id = $1", user.sub)
        return {"role": row["role"] if row else "designer"}
    finally:
        await conn.close()
