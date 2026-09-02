#!/usr/bin/env python3
"""
Push the locally-generated review tool (review.html, map.html) straight
into Postgres, where the backend serves it from (see
backend/app/apis/install_schedule/__init__.py). This is deliberately NOT
a file copy into the git repo or the deploy image -- both files embed
every client's name, address, phone number and install date, and this is
the only step that's supposed to see that content leave this machine.

Published under a SEASON. The table is keyed on (season, name), so a new
autumn's build lands beside last autumn's rather than on top of it -- the
routed plan, crews, stop order and approvals for a finished season stay
openable in the tool instead of becoming 4 KB of unreadable placement JSON
(migrations/013). The season comes from season.py, so it rolls over on its
own each 1 February; TBDG_SEASON overrides it when you need to publish a
season other than the one today falls in -- rebuilding a past season's
page, or getting next season's tool up before the rollover date.

Run after build_review.py (which regenerates review.html/map.html
locally) any time you want the deployed tool updated:

    .venv/bin/python3 build_review.py
    .venv/bin/python3 publish_pages.py
    TBDG_SEASON=2025 .venv/bin/python3 publish_pages.py   # re-publish 2025
"""
import asyncio
import os
import sys

import asyncpg

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, "..", "backend", ".env.supabase")

sys.path.insert(0, HERE)  # season.py is a sibling; this script may be run from anywhere
from season import season_for  # noqa: E402

#: Same variable the rest of the pipeline reads (schedule.py), so one export
#: steers a whole rebuild-and-publish at a non-default season.
SEASON_ENV = "TBDG_SEASON"

#: Mirrors migrations/013 -- see the backend router's DDL for why this only
#: describes the post-013 shape and does not attempt 013's surgery. On the
#: live database CREATE TABLE IF NOT EXISTS is a no-op, so this cannot fight
#: the migration; on a fresh database it produces the same table 013 leaves
#: behind.
DDL = """
CREATE SCHEMA IF NOT EXISTS ll_app;
CREATE TABLE IF NOT EXISTS ll_app.install_schedule_pages (
    season     text NOT NULL,
    name       text NOT NULL,
    html       text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT install_schedule_pages_pkey PRIMARY KEY (season, name)
);
"""

PAGES = {
    "index.html": os.path.join(HERE, "review.html"),
    "map.html": os.path.join(HERE, "map.html"),
}


def current_season() -> str:
    """Which season to publish under: TBDG_SEASON if set, else today's.

    Validated rather than trusted -- a typo'd export would otherwise create a
    junk season row that shows up in the tool's picker forever, and nothing
    downstream would notice.
    """
    override = (os.environ.get(SEASON_ENV) or "").strip()
    if override:
        if len(override) != 4 or not override.isdigit():
            raise SystemExit(
                f"{SEASON_ENV}={override!r} is not a four-digit season year "
                "(a season is named for the year its October falls in)."
            )
        return override
    return str(season_for())


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
    season = current_season()
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit(
            "DATABASE_URL not set (checked env and "
            f"{ENV_FILE}) -- can't publish without it."
        )

    source = "TBDG_SEASON" if os.environ.get(SEASON_ENV) else "season.py"
    print(f"Publishing the {season} season (from {source})")

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute(DDL)
        for name, path in PAGES.items():
            if not os.path.exists(path):
                print(f"  skip {name}: {path} not found (run build_review.py first)")
                continue
            html = open(path, encoding="utf-8").read()
            await conn.execute(
                "INSERT INTO ll_app.install_schedule_pages "
                "(season, name, html, updated_at) "
                "VALUES ($1, $2, $3, now()) "
                "ON CONFLICT (season, name) DO UPDATE "
                "SET html = $3, updated_at = now()",
                season,
                name,
                html,
            )
            print(f"  published {season}/{name} ({len(html)/1024:.0f} KB)")

        rows = await conn.fetch(
            "SELECT season, count(*) AS pages, max(updated_at) AS updated_at "
            "  FROM ll_app.install_schedule_pages GROUP BY season ORDER BY season DESC"
        )
        print("\nSeasons now published (newest first):")
        for r in rows:
            mark = " <- just published" if r["season"] == season else ""
            print(f"  {r['season']}: {r['pages']} page(s), {r['updated_at']:%Y-%m-%d %H:%M}{mark}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
