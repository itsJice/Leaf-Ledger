#!/usr/bin/env python3
"""Rewrite stored client_activity summaries to the season-neutral wording.

The Clients tab renders `client_activity.summary` verbatim, beside a badge
that already shows the season year. Two phrases written by earlier runs
repeated that year, or worse, contradicted it:

    "Not installing this year"   ->  "Not installing"
    "2024 season · $1,200"       ->  "No date recorded · $1,200"

"this year" is not just redundant -- it is wrong the moment the season turns
over. On 1 Feb 2027 a 2026 row still read "Not installing this year" while
the app was planning 2027, which reads as a statement about the wrong season.
"2024 season" printed the badge's year a second time.

Both writers (scheduler/sync_clients.py and the install_schedule API) now
produce the new strings; this fixes the rows they already wrote. The
constants are imported from sync_clients rather than retyped, so this cannot
drift from what the pipeline writes.

Idempotent and narrow: it only matches the two old shapes, so a second run is
a no-op, and it never touches "Scheduled ...", "Cancelled before install", or
any summary a human wrote.

    .venv/bin/python3 backfill_summary_wording.py            # dry run
    .venv/bin/python3 backfill_summary_wording.py --commit
"""
import asyncio
import os
import sys

import asyncpg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sync_clients import (  # noqa: E402
    NOT_INSTALLING_SUMMARY,
    NO_DATE_SUMMARY,
    ENV_FILE,
    load_env,
)

#: Exactly what the old code wrote. Matched literally -- not a LIKE -- so a
#: summary that merely contains the phrase is left alone.
OLD_NOT_INSTALLING = "Not installing this year"

#: The old date-less prefix: a four-digit year, then " season". Anchored, so it
#: only ever replaces the leading label and keeps whatever followed (the " ·
#: $1,200" half is real information and must survive).
OLD_SEASON_PREFIX = r"^[0-9]{4} season"

SAMPLE = 5


async def main() -> None:
    commit = "--commit" in sys.argv

    load_env(ENV_FILE)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit(f"DATABASE_URL not set (checked env and {ENV_FILE})")

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        not_installing = await conn.fetchval(
            "SELECT count(*) FROM client_activity WHERE summary = $1",
            OLD_NOT_INSTALLING,
        )
        # Excludes rows already rewritten: the replacement never starts with a
        # year, so a second run finds nothing.
        season_prefixed = await conn.fetchval(
            "SELECT count(*) FROM client_activity WHERE summary ~ $1",
            OLD_SEASON_PREFIX,
        )
        total = await conn.fetchval("SELECT count(*) FROM client_activity")

        print(f"{total:,} client_activity rows in total")
        print(f"  {not_installing:,} × {OLD_NOT_INSTALLING!r} "
              f"-> {NOT_INSTALLING_SUMMARY!r}")
        print(f"  {season_prefixed:,} × '<year> season …' "
              f"-> {NO_DATE_SUMMARY!r} + whatever followed")

        if season_prefixed:
            rows = await conn.fetch(
                "SELECT season, summary, "
                "       regexp_replace(summary, $1, $2) AS after "
                "  FROM client_activity WHERE summary ~ $1 "
                " ORDER BY season DESC, id LIMIT $3",
                OLD_SEASON_PREFIX,
                NO_DATE_SUMMARY,
                SAMPLE,
            )
            print(f"\n  sample (up to {SAMPLE}):")
            for r in rows:
                print(f"    [{r['season']}] {r['summary']!r} -> {r['after']!r}")

        todo = not_installing + season_prefixed
        if not todo:
            print("\nnothing to do")
            return
        if not commit:
            print("\ndry run — pass --commit to write")
            return

        async with conn.transaction():
            s1 = await conn.execute(
                "UPDATE client_activity SET summary = $2, updated_at = now() "
                " WHERE summary = $1",
                OLD_NOT_INSTALLING,
                NOT_INSTALLING_SUMMARY,
            )
            s2 = await conn.execute(
                "UPDATE client_activity "
                "   SET summary = regexp_replace(summary, $1, $2), "
                "       updated_at = now() "
                " WHERE summary ~ $1",
                OLD_SEASON_PREFIX,
                NO_DATE_SUMMARY,
            )
        n1 = int(s1.split()[-1]) if s1 else 0
        n2 = int(s2.split()[-1]) if s2 else 0

        left = await conn.fetchval(
            "SELECT count(*) FROM client_activity "
            " WHERE summary = $1 OR summary ~ $2",
            OLD_NOT_INSTALLING,
            OLD_SEASON_PREFIX,
        )
        print(f"\ndone: {n1:,} not-installing + {n2:,} season-prefixed "
              f"= {n1 + n2:,} rows rewritten, {left:,} remaining")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
