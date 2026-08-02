#!/usr/bin/env python3
"""Shared loader for scheduler/client_config.json -- every client name the
pipeline's business rules touch across prep.py, schedule.py, rules.py and
validate.py (ZIP/coordinate/storage overrides, box counts, pins, same-day
groups, forced-first stops, drops, manual pairings, category special-
cases). Gitignored, never tracked -- the pipeline can't build a correct
schedule without it (user, 2026-08-02: no client names in the codebase),
so a missing file is a hard error, not a silent empty-rules fallback."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "client_config.json")


def load():
    if not os.path.exists(PATH):
        raise SystemExit(
            f"{PATH} not found -- this holds every named client rule "
            "(ZIP/coordinate/storage overrides, box counts, pins, "
            "groups, forced-first, drops, manual pairings, category "
            "special-cases) and is required to build a correct "
            "schedule. It's intentionally not in git; restore it from "
            "wherever the team keeps working copies."
        )
    with open(PATH) as f:
        return json.load(f)
