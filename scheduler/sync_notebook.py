#!/usr/bin/env python3
"""Refresh overrides.json (the notebook) from the live board before a rebuild.

The board staff work on all season is the published review tool plus its
shared state in Postgres. `schedule.py` replays overrides.json verbatim and
schedules only around it -- so as long as the notebook matches the board,
a rebuild cannot move anyone. This script makes that true without anyone
having to remember the tool's "Export notebook" button:

    .venv/bin/python3 sync_notebook.py            # write overrides.json
    .venv/bin/python3 sync_notebook.py --dry-run  # just say what it would freeze
    TBDG_SEASON=2025 .venv/bin/python3 sync_notebook.py

Run it FIRST in the pipeline (before schedule.py) -- see RULES.md §8.

Failure modes are loud and conservative: if the database is unreachable, or
nothing is published for the season yet, the existing overrides.json is left
exactly as it is and the script exits non-zero so a scripted pipeline stops
rather than re-solving the whole season from scratch.
"""
import asyncio
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import board_state as B  # noqa: E402
from common import current_season  # noqa: E402

OVERRIDES = os.path.join(HERE, "overrides.json")
CACHE = os.path.join(HERE, "cache")


def read_prior():
    if not os.path.exists(OVERRIDES):
        return None
    try:
        with open(OVERRIDES) as f:
            doc = json.load(f)
    except (ValueError, OSError):
        return None
    return doc if doc.get("kind") == "tbdg-install-overrides" else None


async def main(dry_run):
    season = current_season()
    print(f"Season {season}: reading the live board")
    try:
        conn = await B.connect()
    except Exception as e:  # noqa: BLE001 -- any connection failure means stop
        raise SystemExit(f"  !! cannot reach the database ({e}); overrides.json left untouched")
    try:
        payload, published_at = await B.fetch_published_payload(conn, season)
        if payload is None:
            raise SystemExit(
                f"  !! nothing published for season {season} -- overrides.json left untouched"
            )
        version = B.payload_version(payload)
        state, state_at = await B.fetch_state(conn, version)
    finally:
        await conn.close()

    print(f"  published build {version} ({published_at:%Y-%m-%d %H:%M} UTC)")
    if state and state.get("placement"):
        print(f"  shared state: {len(state['placement'])} placed client(s), "
              f"last saved {state_at:%Y-%m-%d %H:%M} UTC")
    else:
        print("  shared state: none yet -- freezing the build's own plan")

    prior = read_prior()
    notebook, rep = B.notebook_from_board(payload, state, prior)

    print(f"  freezing {rep['days']} crew-day(s), {rep['stops']} stop(s), "
          f"{rep['clients']} distinct client(s)")
    print(f"  new_clients carried: {[c['name'] for c in notebook['new_clients']]}")
    if rep["unknown_rows"]:
        print(f"  !! {len(rep['unknown_rows'])} placed row(s) name nobody in this build "
              f"(skipped): {rep['unknown_rows']}")
    if rep["bad_days"]:
        print(f"  !! placed on day id(s) outside the calendar (skipped): {rep['bad_days']}")
    if rep["ghost_clients"]:
        print(f"  !! in-tool client(s) whose row the build reassigned -- not carried, "
              f"re-add in the tool if still wanted: {rep['ghost_clients']}")
    not_inst = [n for n in (state or {}).get("notInstallingNames") or []]
    if not_inst:
        print(f"  not installing (left unfrozen; the tool keeps them off the board): {not_inst}")

    if dry_run:
        print("  --dry-run: overrides.json not written")
        return

    if os.path.exists(OVERRIDES):
        os.makedirs(CACHE, exist_ok=True)
        backup = os.path.join(CACHE, f"overrides.{time.strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy(OVERRIDES, backup)
        print(f"  previous notebook kept at cache/{os.path.basename(backup)}")
    with open(OVERRIDES, "w") as f:
        json.dump(notebook, f, indent=2, ensure_ascii=False)
    print(f"  wrote overrides.json for build {version}")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv[1:]))
