#!/usr/bin/env python3
"""Tests for scheduler/common.py (5.1 scheduler-common).

Run:
    cd scheduler && python3 -m pytest -q tests_common

Deliberately does NOT import schedule.py (or anything that transitively
loads client_config.json at import time, e.g. prep.py, outputs.py) -- that
file is gitignored and required, and isn't present in a fresh checkout or
worktree (see scheduler/RULES.md ss.12). Only `common` and `season` are
imported from the package under test.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED = os.path.dirname(HERE)
sys.path.insert(0, SCHED)  # scheduler/ -- so `import common` / `import season` resolve

import pytest  # noqa: E402

import common  # noqa: E402
import season  # noqa: E402

SEASON_ENV = "TBDG_SEASON"


@pytest.fixture(autouse=True)
def _clean_season_env(monkeypatch):
    monkeypatch.delenv(SEASON_ENV, raising=False)
    yield
    monkeypatch.delenv(SEASON_ENV, raising=False)


# ===========================================================================
# current_season(): six pre-consolidation implementations, reproduced here
# to compare against common.current_season(). Each is copied from the
# script/line named in its docstring; the one deliberate change from a
# verbatim copy is that the `season.season_for()` fallback call is taken as
# a parameter (`season_for_fn`) instead of imported module state, so the
# "TBDG_SEASON unset" case can be tested by freezing "today" without
# monkeypatching module internals for six different modules.
# ===========================================================================
def sync_clients_current_season(season_for_fn):
    """sync_clients.py's current_season(), pre-consolidation (was ~line 66).
    Byte-identical (module docstrings aside) to publish_pages.py's (was
    ~line 65) and sync_notebook.py's (was ~line 38) -- verified by direct
    comparison when this test was written, not reproduced three times."""
    override = (os.environ.get(SEASON_ENV) or "").strip()
    if override:
        if len(override) != 4 or not override.isdigit():
            raise SystemExit(
                f"{SEASON_ENV}={override!r} is not a four-digit season year "
                "(a season is named for the year its October falls in)."
            )
        return override
    return str(season_for_fn())


publish_pages_current_season = sync_clients_current_season
sync_notebook_current_season = sync_clients_current_season


def prep_season(season_for_fn):
    """prep.py's _season(), pre-consolidation (was ~line 51).

    Returns an int. Does NOT check digit count: int("26") == 26 raises
    nothing, unlike the three functions above.
    """
    raw = (os.environ.get(SEASON_ENV) or "").strip()
    if not raw:
        return season_for_fn()
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"{SEASON_ENV}={raw!r} is not a 4-digit season year.")


def schedule_season(season_for_fn):
    """schedule.py's inline SEASON assignment, pre-consolidation (was
    ~line 49): `SEASON = int(os.environ.get("TBDG_SEASON") or
    season.season_for())`.

    No length/digit validation at all (int("26") silently succeeds); a
    non-numeric override raises a bare, uncaught ValueError, not SystemExit.
    """
    return int(os.environ.get(SEASON_ENV) or season_for_fn())


# build_review.py's fallback (was ~lines 41-45) is textually the same
# expression as schedule.py's old one above (`SEASON = getattr(S, "SEASON",
# None); if not isinstance(SEASON, int): SEASON = int(os.environ.get(...) or
# season_lib.season_for())`) -- and in every real run that branch never
# executes, because schedule.S.SEASON is already an int by the time
# build_review.py reads it. Included per the task for completeness; it is
# not a distinct implementation, and build_review.py is a read-only file for
# this change (not edited).
build_review_season = schedule_season


VARIANTS = {
    "sync_clients.py": sync_clients_current_season,
    "publish_pages.py": publish_pages_current_season,
    "sync_notebook.py": sync_notebook_current_season,
    "prep.py": prep_season,
    "schedule.py": schedule_season,
    "build_review.py (dead branch)": build_review_season,
}
STRICT = {"sync_clients.py", "publish_pages.py", "sync_notebook.py"}
LENIENT_INT = {"prep.py", "schedule.py", "build_review.py (dead branch)"}

INPUTS = [None, "2025", "2026", " 2026 ", "26", "abc", ""]
FIXED_TODAY_SEASON = 2029  # arbitrary stand-in for season.season_for(today)


def _season_for_fn():
    return FIXED_TODAY_SEASON


def _run(fn, value):
    """value is None for "TBDG_SEASON unset"; else the string to set it to."""
    if value is not None:
        os.environ[SEASON_ENV] = value
    else:
        os.environ.pop(SEASON_ENV, None)
    try:
        return ("ok", fn(_season_for_fn))
    except SystemExit as e:
        return ("SystemExit", str(e))
    except ValueError as e:
        return ("ValueError", str(e))
    finally:
        os.environ.pop(SEASON_ENV, None)


@pytest.mark.parametrize("value", INPUTS)
def test_variant_table(value):
    """Table test: run all six pre-consolidation variants over the six
    inputs (monkeypatching "today" via season_for_fn instead of real time),
    and pin down the disagreements this task asked to document."""
    results = {name: _run(fn, value) for name, fn in VARIANTS.items()}

    if value in (None, ""):
        # TBDG_SEASON unset (or set-but-empty, which every variant treats
        # the same via `or ""`/falsiness): every variant falls back to
        # season_for_fn(), i.e. season.season_for(today).
        for name in STRICT:
            assert results[name] == ("ok", str(FIXED_TODAY_SEASON))
        for name in LENIENT_INT:
            assert results[name] == ("ok", FIXED_TODAY_SEASON)

    elif value in ("2025", "2026", " 2026 "):
        want = value.strip()
        for name in STRICT:
            assert results[name] == ("ok", want)
        for name in LENIENT_INT:
            assert results[name] == ("ok", int(want))

    elif value == "26":
        # DISAGREEMENT: the three strict variants reject a non-four-digit
        # override; prep.py and schedule.py (and build_review.py's dead
        # branch, which shares schedule.py's code) silently accepted it as
        # season 26.
        for name in STRICT:
            assert results[name][0] == "SystemExit"
        for name in LENIENT_INT:
            assert results[name] == ("ok", 26)

    elif value == "abc":
        # DISAGREEMENT: all six reject it, but not the same way -- the
        # strict variants and prep.py raise a clean SystemExit; schedule.py
        # (and build_review.py's dead branch) raise a bare, uncaught
        # ValueError instead.
        for name in STRICT:
            assert results[name][0] == "SystemExit"
        assert results["prep.py"][0] == "SystemExit"
        assert results["schedule.py"][0] == "ValueError"
        assert results["build_review.py (dead branch)"][0] == "ValueError"

    else:
        raise AssertionError(f"unhandled table input {value!r}")


def test_common_current_season_matches_where_variants_agree(monkeypatch):
    monkeypatch.setattr(season, "season_for", _season_for_fn)

    def common_result(value):
        if value is not None:
            os.environ[SEASON_ENV] = value
        else:
            os.environ.pop(SEASON_ENV, None)
        try:
            return ("ok", common.current_season())
        except SystemExit as e:
            return ("SystemExit", str(e))
        finally:
            os.environ.pop(SEASON_ENV, None)

    # Every input where all six pre-consolidation variants agree AND
    # succeed: common.current_season() must return the identical value
    # (as a str -- the type 3 of the 6 replaced call sites need directly).
    for value, want in [
        (None, str(FIXED_TODAY_SEASON)),
        ("", str(FIXED_TODAY_SEASON)),
        ("2025", "2025"),
        ("2026", "2026"),
        (" 2026 ", "2026"),
    ]:
        assert common_result(value) == ("ok", want)

    # Where they disagree, common.current_season() takes the STRICTEST
    # behaviour: SystemExit, naming the bad value, for both "26" (which
    # prep.py/schedule.py used to silently accept) and "abc" (which
    # schedule.py used to raise a bare ValueError for).
    kind, msg = common_result("26")
    assert kind == "SystemExit"
    assert "26" in msg
    kind, msg = common_result("abc")
    assert kind == "SystemExit"
    assert "abc" in msg


# ===========================================================================
# haversine_mi()
# ===========================================================================
def _schedule_haversine_mi_original(a, b):
    """schedule.py's original haversine_mi(a, b), pre-consolidation."""
    import math
    R = 3958.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _audit_geocode_haversine_mi_original(lat1, lon1, lat2, lon2):
    """archive/audit_geocode.py's original haversine_mi(lat1, lon1, lat2,
    lon2), pre-consolidation (four separate floats, not tuple pairs)."""
    import math
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


HAVERSINE_PAIRS = [
    # (depot, a downtown Houston stop)
    ((29.8256, -95.4520), (29.7604, -95.3698)),
    # (Houston depot, The Woodlands -- a longer in-region hop)
    ((29.8256, -95.4520), (30.1658, -95.4613)),
    # (Houston, Dallas -- a long cross-region hop)
    ((29.7604, -95.3698), (32.7767, -96.7970)),
    # same point -- must be exactly 0
    ((29.7604, -95.3698), (29.7604, -95.3698)),
    # a pair crossing into negative-vs-more-negative longitude, small delta
    ((32.7767, -96.7970), (32.7555, -97.3308)),
]


@pytest.mark.parametrize("a,b", HAVERSINE_PAIRS)
def test_haversine_mi_matches_both_originals(a, b):
    got = common.haversine_mi(a, b)
    assert got == pytest.approx(_schedule_haversine_mi_original(a, b))
    assert got == pytest.approx(
        _audit_geocode_haversine_mi_original(a[0], a[1], b[0], b[1])
    )


# ===========================================================================
# merge_crew()
# ===========================================================================
def _merge_crew_original(prev, new):
    """outputs.py's / team_review.py's / archive/make_updated_copy.py's
    original merge_crew(prev, new), pre-consolidation (all three
    byte-identical)."""
    names = set()
    for c in (prev, new):
        names.update(x.strip() for x in c.replace(" (joint)", "").split(" + "))
    return " + ".join(sorted(names)) + " (joint)"


MERGE_CREW_CASES = [
    ("Crew 1", "Crew 2"),
    ("Crew 2", "Crew 1"),  # order-independent
    ("Crew 1 + Crew 2 (joint)", "Crew 3"),  # re-merging an already-joint label
    ("Crew 1", "Crew 1"),  # a client joint with itself (shouldn't happen, but must not crash)
]


@pytest.mark.parametrize("prev,new", MERGE_CREW_CASES)
def test_merge_crew_matches_original(prev, new):
    assert common.merge_crew(prev, new) == _merge_crew_original(prev, new)


def test_merge_crew_known_values():
    assert common.merge_crew("Crew 1", "Crew 2") == "Crew 1 + Crew 2 (joint)"
    assert (common.merge_crew("Crew 1 + Crew 2 (joint)", "Crew 3")
            == "Crew 1 + Crew 2 + Crew 3 (joint)")


# ===========================================================================
# load_env()
# ===========================================================================
def test_load_env_setdefault_keeps_existing(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.supabase"
    env_file.write_text(
        "\n".join([
            "# a comment, skipped",
            "",
            "DATABASE_URL=postgres://example/from-file",
            'QUOTED="value with spaces"',
            "SINGLE_QUOTED='also quoted'",
            "no_equals_sign_line_is_skipped",
            "ALREADY_SET=from-file-should-not-win",
        ])
    )
    monkeypatch.setenv("ALREADY_SET", "from-real-environment")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)
    monkeypatch.delenv("SINGLE_QUOTED", raising=False)

    common.load_env(str(env_file))

    assert os.environ["DATABASE_URL"] == "postgres://example/from-file"
    assert os.environ["QUOTED"] == "value with spaces"
    assert os.environ["SINGLE_QUOTED"] == "also quoted"
    # setdefault, not overwrite: the real environment value survives.
    assert os.environ["ALREADY_SET"] == "from-real-environment"


def test_load_env_missing_file_is_a_noop(tmp_path):
    missing = tmp_path / "does-not-exist.env"
    common.load_env(str(missing))  # must not raise


# ===========================================================================
# season.py re-export
# ===========================================================================
#: Every public name the old (pre-refactor) scheduler/season.py defined.
OLD_SEASON_PUBLIC_NAMES = [
    "SEASON_START_MONTH", "SEASON_END_MONTH", "ROLLOVER_MONTH",
    "season_for", "season_span", "season_of_date", "year_of_month",
    "takedown_cutoff", "nth_weekday", "thanksgiving", "black_friday",
    "sunday_after_thanksgiving",
]


def test_season_reexports_every_old_public_name_as_the_same_object():
    # season.py's own import already put backend/ on sys.path.
    import app.libs.season as backend_season

    for name in OLD_SEASON_PUBLIC_NAMES:
        assert hasattr(season, name), f"season.{name} missing after re-export"
        assert getattr(season, name) is getattr(backend_season, name), (
            f"season.{name} is not the same object as app.libs.season.{name}"
        )


def test_season_agrees_with_backend_on_a_known_date():
    import datetime
    assert season.season_for(datetime.date(2027, 1, 15)) == 2026
    assert season.season_for(datetime.date(2027, 2, 1)) == 2027
