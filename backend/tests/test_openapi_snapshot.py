"""The API surface must match ``tests/fixtures/openapi_paths.json``.

No database: ``main.app.openapi()`` only walks the route table. When a route
is added, removed or renamed on purpose, regenerate the fixture with::

    .venv/bin/python scripts/openapi_snapshot.py

and commit the result alongside the change. ``/health`` and the SPA
catch-all are ``include_in_schema=False`` and are never part of the snapshot.
"""

from scripts.openapi_snapshot import (
    FIXTURE_PATH,
    current_paths,
    diff,
    format_diff,
    load_fixture,
)


def test_openapi_paths_match_fixture():
    expected = load_fixture()
    actual = current_paths()
    added, removed = diff(expected, actual)
    assert not added and not removed, (
        "OpenAPI surface drifted from "
        f"{FIXTURE_PATH.relative_to(FIXTURE_PATH.parents[2])}:\n"
        + format_diff(added, removed)
        + "\n\nIf intentional: .venv/bin/python scripts/openapi_snapshot.py"
    )


def test_fixture_is_the_full_api_not_an_empty_stub():
    # Guards against a fixture accidentally regenerated from a broken import
    # (main.py swallows router import errors and continues).
    assert len(load_fixture()) > 100
