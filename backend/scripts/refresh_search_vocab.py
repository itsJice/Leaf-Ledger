#!/usr/bin/env python3
"""Rebuild search_vocab, the typo-correction dictionary (migrations/012).

Run after a catalog import. Cheap enough to run nightly: the whole table is
~18k rows, and rebuilding it is one scan of product names.

    python scripts/refresh_search_vocab.py            # report only
    python scripts/refresh_search_vocab.py --commit
"""
import asyncio
import os
import sys
import time

# Three letters is the shortest worth correcting; below that almost anything is
# within one edit of anything else. Words are taken from product names only —
# the raw_data blob is mostly codes and measurements, which would pad the
# dictionary with strings no one searches for and that dilute the ranking.
MIN_LEN = 3


async def main() -> None:
    import asyncpg

    commit = "--commit" in sys.argv
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set (source backend/.env.supabase)")

    conn = await asyncpg.connect(url, statement_cache_size=0, timeout=600)
    try:
        before = await conn.fetchval("SELECT count(*) FROM search_vocab")
        t0 = time.time()
        if not commit:
            n = await conn.fetchval(
                f"""
                SELECT count(DISTINCT m[1])
                  FROM products p,
                       LATERAL regexp_matches(lower(p.name), '[a-z]{{{MIN_LEN},}}', 'g') m
                 WHERE p.is_active
                """
            )
            print(f"search_vocab holds {before:,} words; a rebuild would hold {n:,}")
            print("dry run — pass --commit to write")
            return

        # Swap in one transaction so a concurrent search never sees an empty
        # dictionary: a truncate + insert would leave a window where every
        # correction silently returns nothing.
        async with conn.transaction():
            await conn.execute(
                f"""
                CREATE TEMP TABLE vocab_new ON COMMIT DROP AS
                SELECT m[1] AS word, count(*)::int AS freq
                  FROM products p,
                       LATERAL regexp_matches(lower(p.name), '[a-z]{{{MIN_LEN},}}', 'g') m
                 WHERE p.is_active
                 GROUP BY m[1]
                """
            )
            await conn.execute("DELETE FROM search_vocab")
            await conn.execute(
                "INSERT INTO search_vocab (word, freq) SELECT word, freq FROM vocab_new"
            )

        after = await conn.fetchval("SELECT count(*) FROM search_vocab")
        await conn.execute("ANALYZE search_vocab")
        print(f"search_vocab rebuilt: {before:,} -> {after:,} words in {time.time()-t0:.1f}s")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
