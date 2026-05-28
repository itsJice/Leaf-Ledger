from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import asyncpg
import os
from datetime import datetime
from app.auth import AuthorizedUser

router = APIRouter(prefix="/mockups", tags=["mockups"])
DATABASE_URL = os.environ.get("DATABASE_URL")

async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

STYLES = ["photo-realistic", "illustrated", "mood-board"]

class MockupCreate(BaseModel):
    arrangement_id: int
    style: str

class MockupOut(BaseModel):
    id: int
    arrangement_id: int
    style: str
    image_url: Optional[str]
    prompt_used: Optional[str]
    status: str
    created_at: datetime

@router.get("/list/{arrangement_id}", response_model=List[MockupOut])
async def list_mockups(arrangement_id: int, user: AuthorizedUser):
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            "SELECT * FROM arrangement_mockups WHERE arrangement_id = $1 ORDER BY created_at DESC",
            arrangement_id
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()

@router.post("/generate", response_model=MockupOut)
async def generate_mockup(body: MockupCreate, user: AuthorizedUser):
    if body.style not in STYLES:
        raise HTTPException(status_code=400, detail=f"Style must be one of: {STYLES}")

    openai_key = os.environ.get("OPENAI_API_KEY")

    conn = await get_conn()
    try:
        # Fetch arrangement details for prompt
        arr = await conn.fetchrow("SELECT name, client_name FROM arrangements WHERE id = $1", body.arrangement_id)
        if not arr:
            raise HTTPException(status_code=404, detail="Arrangement not found")

        items = await conn.fetch("""
            SELECT p.name, p.category, ci.quantity
            FROM container_items ci
            JOIN arrangement_containers ac ON ac.id = ci.container_id
            JOIN products p ON p.id = ci.product_id
            WHERE ac.arrangement_id = $1
        """, body.arrangement_id)

        plant_list = ", ".join([f"{r['quantity']}x {r['name']}" for r in items]) or "assorted plants"

        style_desc = {
            "photo-realistic": "photo-realistic professional interior plant arrangement photograph",
            "illustrated": "illustrated painterly botanical art style",
            "mood-board": "flat lay mood board design layout",
        }[body.style]

        prompt = (
            f"A {style_desc} featuring: {plant_list}. "
            f"Arrangement name: {arr['name']}. "
            "Beautiful composition, professional plant styling, warm botanical aesthetic, "
            "deep greens and earth tones, editorial quality."
        )

        # Insert pending record
        mockup = await conn.fetchrow("""
            INSERT INTO arrangement_mockups (arrangement_id, style, prompt_used, status)
            VALUES ($1, $2, $3, 'generating') RETURNING *
        """, body.arrangement_id, body.style, prompt)

        if not openai_key:
            await conn.execute(
                "UPDATE arrangement_mockups SET status = 'failed' WHERE id = $1", mockup["id"]
            )
            raise HTTPException(status_code=503, detail="OpenAI API key not configured. Please add OPENAI_API_KEY in secrets.")

        # Generate image
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            await conn.execute(
                "UPDATE arrangement_mockups SET image_url = $1, status = 'done' WHERE id = $2",
                image_url, mockup["id"]
            )
            updated = await conn.fetchrow("SELECT * FROM arrangement_mockups WHERE id = $1", mockup["id"])
            return dict(updated)
        except Exception as e:
            await conn.execute(
                "UPDATE arrangement_mockups SET status = 'failed' WHERE id = $1", mockup["id"]
            )
            raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")
    finally:
        await conn.close()

@router.delete("/delete/{mockup_id}")
async def delete_mockup(mockup_id: int, user: AuthorizedUser):
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM arrangement_mockups WHERE id = $1", mockup_id)
        return {"ok": True}
    finally:
        await conn.close()
