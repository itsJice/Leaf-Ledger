#!/usr/bin/env python3
"""Shared helpers that used to be copy-pasted across the scheduler pipeline.

Consolidated here (5.1 scheduler-common): `load_env`, `current_season`,
`merge_crew`, `haversine_mi`. Each was independently defined -- sometimes
identically, sometimes with a subtly different rule -- in several scripts;
this is the one place a fix now needs to land.

See the 5.1 report / commit message for which `current_season()` inputs
change behaviour for which caller (prep.py and schedule.py's old inline
versions were looser than sync_clients.py/publish_pages.py/sync_notebook.py's;
this module takes the strictest of the six).
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # season.py is a sibling; this may be imported from anywhere

import season  # noqa: E402

#: Same file every pipeline script that talks to Postgres reads its DB creds
#: from (sync_clients.py, publish_pages.py, board_state.py all pointed here).
ENV_FILE = os.path.join(HERE, "..", "backend", ".env.supabase")

#: Same env var the whole pipeline reads to override the derived season
#: (prep.py, schedule.py, sync_clients.py, publish_pages.py, sync_notebook.py,
#: build_review.py).
SEASON_ENV = "TBDG_SEASON"


def load_env(path=ENV_FILE):
    """Populate os.environ from a `KEY=VALUE` file (e.g. .env.supabase).

    setdefault, not overwrite -- a value already in the real environment
    wins over the file. Blank lines, `#` comments, and lines with no `=`
    are skipped; a value's surrounding quotes are stripped. Does nothing if
    `path` doesn't exist (no error -- an absent .env is normal outside a
    dev machine that has real environment variables set instead).

    This was three byte-for-byte identical copies (sync_clients.py,
    publish_pages.py, board_state.py) before this consolidation -- diffed
    to confirm identity, so this is a pure move, not a behaviour change.
    """
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def current_season() -> str:
    """The season this run belongs to, as a four-digit string.

    TBDG_SEASON overrides it (the same variable the whole pipeline reads);
    otherwise it's `season.season_for()` -- named for the year its October
    falls in, rolling over on 1 February.

    Validated STRICTLY: the override must be exactly four digits, or this
    raises SystemExit naming the bad value. This is the strictest of the six
    near-duplicate implementations it replaces:

      - sync_clients.py, publish_pages.py and sync_notebook.py already
        validated exactly this way (identical code in all three) -- no
        behaviour change for those callers.
      - prep.py's old `_season()` accepted ANY int-parseable string
        regardless of length (`TBDG_SEASON=26` silently built season 26) and
        returned an int. Consolidating here means `TBDG_SEASON=26` now
        raises instead of silently building the wrong season -- a real, and
        intentional, behaviour change; see the 5.1 report.
      - schedule.py's old inline `SEASON = int(os.environ.get(...) or
        season.season_for())` did no validation at all: a short year like
        "26" silently succeeded, and a non-numeric value crashed with a
        bare, uncaught ValueError instead of a clean message. Both are
        replaced by the same SystemExit as everyone else.
      - build_review.py's fallback expression is textually the same as
        schedule.py's old one, but in every real run it never executes --
        `SEASON = getattr(S, "SEASON", None)` already gets an int from
        schedule.py's own (now-consolidated) SEASON. build_review.py is not
        owned by this change and was not edited.

    Returns a str (the season LABEL -- a DB column value, a sheet-name
    suffix, a print banner: what 3 of the 6 replaced call sites need
    directly). A caller that wants the year as an int for arithmetic
    (prep.py, schedule.py) wraps it: `int(current_season())`.
    """
    override = (os.environ.get(SEASON_ENV) or "").strip()
    if override:
        if len(override) != 4 or not override.isdigit():
            raise SystemExit(
                f"{SEASON_ENV}={override!r} is not a four-digit season year "
                "(a season is named for the year its October falls in)."
            )
        return override
    return str(season.season_for())


def merge_crew(prev: str, new: str) -> str:
    """Joint stops appear on two crews' cards -> one merged label.

    e.g. merge_crew("Crew 1", "Crew 2") -> "Crew 1 + Crew 2 (joint)";
    merging a third crew into an already-merged label folds it in rather
    than nesting labels.

    Identical across outputs.py, team_review.py and make_updated_copy.py
    before this consolidation (make_updated_copy.py is archived, not
    repointed -- see scheduler/archive/README.md).
    """
    names = set()
    for c in (prev, new):
        names.update(x.strip() for x in c.replace(" (joint)", "").split(" + "))
    return " + ".join(sorted(names)) + " (joint)"


def haversine_mi(a, b) -> float:
    """Great-circle distance in miles between two (lat, lon) pairs.

    Same formula as schedule.py's original (tuple-pair signature, kept here
    since schedule.py is the still-live caller) and audit_geocode.py's
    original (four separate lat/lon floats, algebraically identical) --
    verified to return the same value as both for the same coordinates.
    audit_geocode.py is archived, not repointed (see
    scheduler/archive/README.md), so it keeps its own copy.
    """
    R = 3958.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def _minutes_of_day(v):
    """A time cell (datetime.time, datetime, or "H:MM" / "3:30 PM" text) ->
    minutes since midnight, or None."""
    if v is None or v == "":
        return None
    if hasattr(v, "hour") and hasattr(v, "minute"):
        return v.hour * 60 + v.minute
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*([AaPp][Mm])?\s*$", str(v))
    if not m:
        return None
    hh, mm, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if ap == "pm" and hh < 12:
        hh += 12
    if ap == "am" and hh == 12:
        hh = 0
    if hh > 23 or mm > 59:
        return None
    return hh * 60 + mm


def hours_between(start, end):
    """Hours from a start time to an end time, wrapping past midnight (a
    10 PM to 1 AM night install is 3 hours). None when either is missing
    or unreadable, or when they are the same moment."""
    a, b = _minutes_of_day(start), _minutes_of_day(end)
    if a is None or b is None:
        return None
    mins = (b - a) % (24 * 60)
    return round(mins / 60.0, 2) if mins else None
