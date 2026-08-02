#!/usr/bin/env python3
"""
Push the locally-generated review tool (review.html, map.html) straight
into Postgres, where the backend serves it from (see
backend/app/apis/install_schedule/__init__.py). This is deliberately NOT
a file copy into the git repo or the deploy image -- both files embed
every client's name, address, phone number and install date, and this is
the only step that's supposed to see that content leave this machine.

Run after build_review.py (which regenerates review.html/map.html
locally) any time you want the deployed tool updated:

    .venv/bin/python3 build_review.py
    .venv/bin/python3 publish_pages.py
"""
import asyncio
import os

import asyncpg

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, "..", "backend", ".env.supabase")

DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;
CREATE TABLE IF NOT EXISTS ll_app.install_schedule_pages (
    name       text PRIMARY KEY,
    html       text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""

PAGES = {
    "index.html": os.path.join(HERE, "review.html"),
    "map.html": os.path.join(HERE, "map.html"),
}


def load_env(path):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


async def main():
    load_env(ENV_FILE)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit(
            "DATABASE_URL not set (checked env and "
            f"{ENV_FILE}) -- can't publish without it."
        )

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute(DDL)
        for name, path in PAGES.items():
            if not os.path.exists(path):
                print(f"  skip {name}: {path} not found (run build_review.py first)")
                continue
            html = open(path, encoding="utf-8").read()
            await conn.execute(
                "INSERT INTO ll_app.install_schedule_pages (name, html, updated_at) "
                "VALUES ($1, $2, now()) "
                "ON CONFLICT (name) DO UPDATE SET html = $2, updated_at = now()",
                name,
                html,
            )
            print(f"  published {name} ({len(html)/1024:.0f} KB)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
