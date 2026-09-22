#!/usr/bin/env python3
"""Rewrite stored client_activity summaries to the season-neutral wording.

The Clients tab renders `client_activity.summary` verbatim, beside a badge
that already shows the season year. Phrases written by earlier runs repeated
that year, contradicted it, or used the wrong date format:

    "Not installing this year"        ->  "Not installing"
    "2024 season · $1,200"            ->  "No date recorded · $1,200"
    "Scheduled 2025-12-05"            ->  "Scheduled 12/05/2025"
    "...previously scheduled 2026-11-12"  ->  "...previously scheduled 11/12/2026"

"this year" is not just redundant -- it is wrong the moment the season turns
over. On 1 Feb 2027 a 2026 row still read "Not installing this year" while
the app was planning 2027, which reads as a statement about the wrong season.
"2024 season" printed the badge's year a second time. The ISO dates were
never wrong, just inconsistent with every other date in the app, which is
MM/DD/YYYY throughout (user, 2026-09-04).

All four writers (scheduler/sync_clients.py's summarize(), and the
install_schedule API's _restored_summary()/_reconcile_not_installing()) now
produce the new strings; this fixes the rows they already wrote. The
NOT_INSTALLING_SUMMARY/NO_DATE_SUMMARY constants are imported from
sync_clients rather than retyped, so those two can't drift from what the
pipeline writes.

Idempotent and narrow: each old shape is matched exactly (or, for the dates,
by the YYYY-MM-DD shape itself), so a second run is a no-op, and nothing
touches "Cancelled before install" or any summary a human wrote by hand.

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

#: An ISO date anywhere in the summary -- "Scheduled 2025-12-05" and
#: "...previously scheduled 2026-11-12" both match this, and both get the
#: same \2/\3/\1 replacement (MM/DD/YYYY), since the date is always the last
#: three capture groups regardless of what precedes it.
OLD_ISO_DATE = r"([0-9]{4})-([0-9]{2})-([0-9]{2})"
NEW_MDY_DATE = r"\2/\3/\1"

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
        # Same self-excluding property: once rewritten the date reads
        # MM/DD/YYYY, which this pattern (anchored to YYYY-MM-DD) no longer
        # matches, so a second run finds nothing here either.
        iso_dated = await conn.fetchval(
            "SELECT count(*) FROM client_activity WHERE summary ~ $1",
            OLD_ISO_DATE,
        )
        total = await conn.fetchval("SELECT count(*) FROM client_activity")

        print(f"{total:,} client_activity rows in total")
        print(f"  {not_installing:,} × {OLD_NOT_INSTALLING!r} "
              f"-> {NOT_INSTALLING_SUMMARY!r}")
        print(f"  {season_prefixed:,} × '<year> season …' "
              f"-> {NO_DATE_SUMMARY!r} + whatever followed")
        print(f"  {iso_dated:,} × an embedded YYYY-MM-DD date "
              f"-> MM/DD/YYYY, rest of the summary unchanged")

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

        if iso_dated:
            rows = await conn.fetch(
                "SELECT season, summary, "
                "       regexp_replace(summary, $1, $2) AS after "
                "  FROM client_activity WHERE summary ~ $1 "
                " ORDER BY season DESC, id LIMIT $3",
                OLD_ISO_DATE,
                NEW_MDY_DATE,
                SAMPLE,
            )
            print(f"\n  sample (up to {SAMPLE}):")
            for r in rows:
                print(f"    [{r['season']}] {r['summary']!r} -> {r['after']!r}")

        todo = not_installing + season_prefixed + iso_dated
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
            s3 = await conn.execute(
                "UPDATE client_activity "
                "   SET summary = regexp_replace(summary, $1, $2), "
                "       updated_at = now() "
                " WHERE summary ~ $1",
                OLD_ISO_DATE,
                NEW_MDY_DATE,
            )
        n1 = int(s1.split()[-1]) if s1 else 0
        n2 = int(s2.split()[-1]) if s2 else 0
        n3 = int(s3.split()[-1]) if s3 else 0

        left = await conn.fetchval(
            "SELECT count(*) FROM client_activity "
            " WHERE summary = $1 OR summary ~ $2 OR summary ~ $3",
            OLD_NOT_INSTALLING,
            OLD_SEASON_PREFIX,
            OLD_ISO_DATE,
        )
        print(f"\ndone: {n1:,} not-installing + {n2:,} season-prefixed "
              f"+ {n3:,} date-reformatted "
              f"= {n1 + n2 + n3:,} rows rewritten, {left:,} remaining")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
