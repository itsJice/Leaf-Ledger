"""Make, list, revoke or preview client share links (app/apis/client_share).

Run from ``backend/`` with the database env loaded::

    set -a; . ./.env.supabase; set +a

    # read-only: what the M Crowd link would show, from the live board
    .venv/bin/python scripts/client_share_link.py preview --prefix "M Crowd " --strip "M Crowd "

    # make the M Crowd link (writes one row; prints its two URLs once)
    .venv/bin/python scripts/client_share_link.py create --label "M Crowd" \\
        --prefix "M Crowd " --strip "M Crowd "

    .venv/bin/python scripts/client_share_link.py list
    .venv/bin/python scripts/client_share_link.py revoke 3

``--client-id`` (repeatable) adds clients by app id, alongside or instead of
``--prefix``. The URLs carry the secret: share them only with the client.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import secrets
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.apis import client_share as share_api  # noqa: E402
from app.apis.client_share_links import ShareLinkIn, paths, validate  # noqa: E402
from app.libs import client_share, install_calendar, schedule_board  # noqa: E402
from app.libs.db import get_conn  # noqa: E402

BASE_URL = os.getenv("LL_BASE_URL", "https://leaf-ledger.onrender.com")


async def preview(args) -> None:
    body = validate(ShareLinkIn(label="preview", name_prefix=args.prefix or "",
                                client_ids=args.client_id or [], strip_prefix=args.strip or ""))
    conn = await get_conn()
    try:
        clients = [dict(r) for r in await conn.fetch("SELECT id, name, sheet_name, former_names FROM clients")]
    finally:
        await conn.close()
    board = await schedule_board.load_board()
    names = install_calendar.current_names(board, install_calendar.name_aliases(clients))
    vs = client_share.visits(board, share_api.rule_for(body.model_dump(), clients), names)
    print(f"{len(vs)} visits, {len({v.location for v in vs})} locations (season {board.season})")
    for r in client_share.csv_rows(vs):
        print(" | ".join(r))


async def create(args) -> None:
    body = validate(ShareLinkIn(label=args.label, name_prefix=args.prefix or "",
                                client_ids=args.client_id or [], strip_prefix=args.strip or ""))
    conn = await get_conn()
    try:
        await share_api.ensure_schema(conn)
        row = await conn.fetchrow(
            "INSERT INTO ll_app.client_share_links "
            "(token, label, name_prefix, client_ids, strip_prefix, created_by) "
            "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id, token",
            secrets.token_urlsafe(32), body.label, body.name_prefix, body.client_ids,
            body.strip_prefix, "scripts/client_share_link.py")
    finally:
        await conn.close()
    ics, csv_ = paths(row["token"])
    print(f"Share link #{row['id']} for {body.label}")
    print(f"  Calendar (subscribe from URL): {BASE_URL}{ics}")
    print(f"  Spreadsheet:                   {BASE_URL}{csv_}")


async def list_links(_args) -> None:
    conn = await get_conn()
    try:
        await share_api.ensure_schema(conn)
        rows = await conn.fetch("SELECT id, token, label, name_prefix, client_ids, strip_prefix, revoked, "
                                "created_at FROM ll_app.client_share_links ORDER BY id")
    finally:
        await conn.close()
    for r in rows:
        state = "REVOKED" if r["revoked"] else f"{BASE_URL}{paths(r['token'])[0]}"
        print(f"#{r['id']} {r['label']!r} prefix={r['name_prefix']!r} ids={list(r['client_ids'])} "
              f"strip={r['strip_prefix']!r}  {state}")


async def revoke(args) -> None:
    conn = await get_conn()
    try:
        await share_api.ensure_schema(conn)
        done = await conn.fetchval(
            "UPDATE ll_app.client_share_links SET revoked = true, revoked_at = COALESCE(revoked_at, now()), "
            "revoked_by = COALESCE(revoked_by, 'scripts/client_share_link.py') WHERE id = $1 RETURNING id",
            args.id)
    finally:
        await conn.close()
    print(f"Revoked #{done}" if done else f"No share link #{args.id}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("preview", "create"):
        s = sub.add_parser(name)
        if name == "create":
            s.add_argument("--label", required=True)
        s.add_argument("--prefix", help='board names starting with this, any case, e.g. "M Crowd "')
        s.add_argument("--client-id", type=int, action="append", help="an app client id (repeatable)")
        s.add_argument("--strip", help="removed from the front of shown names")
    sub.add_parser("list")
    r = sub.add_parser("revoke")
    r.add_argument("id", type=int)
    args = p.parse_args()
    asyncio.run({"preview": preview, "create": create, "list": list_links, "revoke": revoke}[args.cmd](args))


if __name__ == "__main__":
    main()
