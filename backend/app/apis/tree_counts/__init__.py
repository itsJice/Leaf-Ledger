"""Tree counts -- what was ACTUALLY on a tree at install or teardown.

The ornament calculator's golden table (frontend `utils/ornamentRecipe.ts`,
`GOLDEN_RECIPES`) is the designer's instinct written down once. This module is
the calibration loop that keeps it honest: every time a crew puts a tree up or
takes one down they record the real per-size ornament counts and enhancer
count. Each record is a candidate golden-table row; the Tree Counts page
averages the records at each golden height and shows the drift against the
approved row. Nothing here writes the table -- a designer copies an average
into `GOLDEN_RECIPES` by hand once they have approved it.

Storage follows `feedback` / `preferences`: an app-owned, append-only table in
the `ll_app` schema, created lazily on first use (the same DDL is kept in
`migrations/014_tree_counts.sql` so a rebuilt database gets it). One row per
counted tree; `counts` is a jsonb object of ornament size in inches (as a
string key, e.g. "4.75") -> pieces. Records are team-wide: `created_by` is
attribution only, and anyone signed in can list or delete them.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Literal, Optional

import asyncpg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.auth import AuthorizedUser

router = APIRouter(prefix="/tree-counts", tags=["tree_counts"])

KINDS = ("install", "teardown")
MAX_HEIGHT_FT = 60.0
MAX_WIDTH_IN = 400.0
MAX_PIECES_PER_SIZE = 5000
MAX_ENHANCERS = 1000
MAX_TEXT = 200
MAX_NOTES = 4000
#: Widest "same tree height" window the list filter accepts (feet).
MAX_TOLERANCE_FT = 2.0

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;

CREATE TABLE IF NOT EXISTS ll_app.tree_counts (
    id           bigserial PRIMARY KEY,
    recorded_at  timestamptz NOT NULL DEFAULT now(),
    kind         text NOT NULL CHECK (kind IN ('install', 'teardown')),
    height_ft    numeric(5,2) NOT NULL,
    width_in     numeric(6,2) NOT NULL,
    profile      text,
    style        text,
    label        text,
    counts       jsonb NOT NULL DEFAULT '{}'::jsonb,
    enhancers    integer NOT NULL DEFAULT 0,
    notes        text,
    created_by   text,
    created_name text
);
CREATE INDEX IF NOT EXISTS tree_counts_recorded_idx
    ON ll_app.tree_counts (recorded_at DESC);
CREATE INDEX IF NOT EXISTS tree_counts_height_idx
    ON ll_app.tree_counts (height_ft);
"""

_SCHEMA_READY = False


async def get_conn():
    return await asyncpg.connect(
        os.environ.get("DATABASE_URL"), statement_cache_size=0
    )


async def ensure_schema(conn):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    await conn.execute(DDL)
    _SCHEMA_READY = True


# ─── Shapes ──────────────────────────────────────────────────────────────────


def _clean(value: Optional[str], limit: int) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return None
    return text[:limit]


def normalise_counts(raw: Dict[Any, Any]) -> Dict[str, int]:
    """Validate a size -> pieces map and canonicalise its keys.

    Keys arrive as whatever JSON gave us ("4.75", "4", 4) and are stored as the
    shortest decimal string for the size so "4", "4.0" and 4 all collapse to
    "4". Zero and blank entries are dropped -- a size with nothing on the tree
    is simply absent, which is also what the golden table does.
    """
    out: Dict[str, int] = {}
    for key, value in (raw or {}).items():
        try:
            size = float(str(key).strip())
        except ValueError as exc:
            raise ValueError(f"ornament size {key!r} is not a number") from exc
        if not (0 < size <= 48):
            raise ValueError(f"ornament size {size} in is out of range")
        if value is None or value == "":
            continue
        try:
            pieces = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"count for {key} in must be a whole number") from exc
        if pieces < 0:
            raise ValueError(f"count for {key} in cannot be negative")
        if pieces > MAX_PIECES_PER_SIZE:
            raise ValueError(f"count for {key} in is implausibly large")
        if pieces == 0:
            continue
        size_key = f"{size:g}"
        out[size_key] = out.get(size_key, 0) + pieces
    return out


class TreeCountIn(BaseModel):
    kind: Literal["install", "teardown"]
    height_ft: float = Field(gt=0, le=MAX_HEIGHT_FT)
    width_in: float = Field(gt=0, le=MAX_WIDTH_IN)
    profile: Optional[str] = None
    style: Optional[str] = None
    label: Optional[str] = None
    counts: Dict[str, int] = Field(default_factory=dict)
    enhancers: int = Field(default=0, ge=0, le=MAX_ENHANCERS)
    notes: Optional[str] = None
    #: Optional override -- a teardown logged the morning after still belongs
    #: to the day the tree came down. Defaults to now on the server.
    recorded_at: Optional[datetime] = None

    @field_validator("counts", mode="before")
    @classmethod
    def _counts(cls, value: Any) -> Dict[str, int]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("counts must be an object of size -> pieces")
        return normalise_counts(value)


class TreeCountOut(BaseModel):
    id: int
    recorded_at: str
    kind: str
    height_ft: float
    width_in: float
    profile: Optional[str] = None
    style: Optional[str] = None
    label: Optional[str] = None
    counts: Dict[str, int]
    enhancers: int
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_name: Optional[str] = None


COLUMNS = (
    "id, recorded_at, kind, height_ft, width_in, profile, style, label, "
    "counts, enhancers, notes, created_by, created_name"
)


def row_out(r: Any) -> TreeCountOut:
    counts = r["counts"]
    if isinstance(counts, str):
        counts = json.loads(counts)
    return TreeCountOut(
        id=r["id"],
        recorded_at=r["recorded_at"].isoformat(),
        kind=r["kind"],
        height_ft=float(r["height_ft"]),
        width_in=float(r["width_in"]),
        profile=r["profile"],
        style=r["style"],
        label=r["label"],
        counts={k: int(v) for k, v in (counts or {}).items()},
        enhancers=int(r["enhancers"] or 0),
        notes=r["notes"],
        created_by=r["created_by"],
        created_name=r["created_name"],
    )


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("", response_model=TreeCountOut)
async def create_tree_count(body: TreeCountIn, user: AuthorizedUser) -> TreeCountOut:
    if not body.counts and body.enhancers == 0:
        raise HTTPException(status_code=400, detail="Record at least one ornament count")
    try:
        conn = await get_conn()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Tree count storage unavailable") from exc
    try:
        await ensure_schema(conn)
        row = await conn.fetchrow(
            "INSERT INTO ll_app.tree_counts "
            "(recorded_at, kind, height_ft, width_in, profile, style, label, "
            " counts, enhancers, notes, created_by, created_name) "
            "VALUES (COALESCE($1, now()), $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11, $12) "
            f"RETURNING {COLUMNS}",
            body.recorded_at,
            body.kind,
            round(body.height_ft, 2),
            round(body.width_in, 2),
            _clean(body.profile, MAX_TEXT),
            _clean(body.style, MAX_TEXT),
            _clean(body.label, MAX_TEXT),
            json.dumps(body.counts),
            body.enhancers,
            _clean(body.notes, MAX_NOTES),
            user.sub,
            user.display_name,
        )
    finally:
        await conn.close()
    return row_out(row)


@router.get("", response_model=list[TreeCountOut])
async def list_tree_counts(
    height_ft: Optional[float] = None,
    tolerance_ft: float = 0.25,
    limit: int = 500,
) -> Any:
    """Newest first. `height_ft` narrows to trees within `tolerance_ft` of
    that height (default +/- 0.25 ft, so a "9 ft" tree and a 9.25 ft tree
    land in the same bucket -- the same window the frontend averages over)."""
    limit = max(1, min(limit, 2000))
    tolerance_ft = max(0.0, min(tolerance_ft, MAX_TOLERANCE_FT))
    try:
        conn = await get_conn()
    except Exception:
        return []
    try:
        await ensure_schema(conn)
        if height_ft is None:
            rows = await conn.fetch(
                f"SELECT {COLUMNS} FROM ll_app.tree_counts "
                "ORDER BY recorded_at DESC, id DESC LIMIT $1",
                limit,
            )
        else:
            rows = await conn.fetch(
                f"SELECT {COLUMNS} FROM ll_app.tree_counts "
                "WHERE height_ft BETWEEN $1 AND $2 "
                "ORDER BY recorded_at DESC, id DESC LIMIT $3",
                height_ft - tolerance_ft,
                height_ft + tolerance_ft,
                limit,
            )
    finally:
        await conn.close()
    return [row_out(r) for r in rows]


@router.delete("/{count_id}")
async def delete_tree_count(count_id: int) -> dict:
    """Team-wide delete: a mis-typed count is everyone's problem, so anyone
    signed in can remove it, not just whoever entered it."""
    try:
        conn = await get_conn()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Tree count storage unavailable") from exc
    try:
        await ensure_schema(conn)
        deleted = await conn.fetchval(
            "DELETE FROM ll_app.tree_counts WHERE id = $1 RETURNING id", count_id
        )
    finally:
        await conn.close()
    if deleted is None:
        raise HTTPException(status_code=404, detail="No tree count with that id")
    return {"deleted": 1, "id": count_id}
