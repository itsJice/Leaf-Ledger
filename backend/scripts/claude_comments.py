#!/usr/bin/env python3
"""
Read and answer the Comments tab from the daily Claude Code review.

The scheduled task on the office Mac runs this to see what's waiting and to
leave its review on each submission. It writes straight to the database named
by DATABASE_URL (backend/.env.supabase unless already set) -- the same one the
live app reads -- so a review shows up in the Comments tab immediately.

Usage (from backend/):
    .venv/bin/python scripts/claude_comments.py queue
        Open submissions Claude hasn't reviewed yet, plus ones a person has
        since approved or replied to. JSON on stdout.
    .venv/bin/python scripts/claude_comments.py screenshot ID OUT.png
        Save a submission's attached screenshot to a file.
    .venv/bin/python scripts/claude_comments.py review ID --status STATUS --note TEXT [--link URL]
        Leave Claude's review. STATUS is one of: fixed, needs_approval,
        needs_human, unclear.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.apis import feedback  # noqa: E402


def _load_env() -> None:
    if os.environ.get("DATABASE_URL"):
        return
    env_file = BACKEND / f".env.{os.environ.get('ENV', 'supabase')}"
    for line in env_file.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"')
            return
    sys.exit(f"No DATABASE_URL in {env_file}")


async def _conn():
    import asyncpg

    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    await conn.execute(feedback.DDL)
    return conn


async def queue() -> None:
    conn = await _conn()
    try:
        rows = await conn.fetch(
            f"SELECT {feedback.ROW_COLUMNS} FROM ll_app.feature_requests "
            "WHERE status <> 'done' AND (claude_status IS NULL OR claude_status = ANY($1::text[])) "
            "ORDER BY created_at",
            sorted(feedback.CLAUDE_QUEUE_STATUSES),
        )
    finally:
        await conn.close()
    print(json.dumps([feedback.to_row(r).model_dump() for r in rows], indent=2))


async def screenshot(feedback_id: int, out: str) -> None:
    conn = await _conn()
    try:
        data = await conn.fetchval(
            "SELECT screenshot FROM ll_app.feature_requests WHERE id = $1", feedback_id
        )
    finally:
        await conn.close()
    if not data:
        sys.exit(f"#{feedback_id} has no screenshot")
    Path(out).write_bytes(base64.b64decode(data.split(",", 1)[1]))
    print(out)


async def review(feedback_id: int, status: str, note: str, link: str | None) -> None:
    conn = await _conn()
    try:
        found = await conn.fetchval(
            "UPDATE ll_app.feature_requests SET claude_status = $2, claude_note = $3, "
            "claude_link = $4, claude_reviewed_at = now() WHERE id = $1 RETURNING id",
            feedback_id, status, note.strip(), link,
        )
    finally:
        await conn.close()
    if not found:
        sys.exit(f"No submission #{feedback_id}")
    print(f"Reviewed #{feedback_id}: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("queue")
    shot = sub.add_parser("screenshot")
    shot.add_argument("id", type=int)
    shot.add_argument("out")
    rev = sub.add_parser("review")
    rev.add_argument("id", type=int)
    rev.add_argument("--status", required=True, choices=sorted(feedback.CLAUDE_REVIEW_STATUSES))
    rev.add_argument("--note", required=True)
    rev.add_argument("--link")
    args = parser.parse_args()

    _load_env()
    if args.cmd == "queue":
        asyncio.run(queue())
    elif args.cmd == "screenshot":
        asyncio.run(screenshot(args.id, args.out))
    else:
        asyncio.run(review(args.id, args.status, args.note, args.link))


if __name__ == "__main__":
    main()
