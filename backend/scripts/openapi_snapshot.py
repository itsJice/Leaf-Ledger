"""Snapshot of the API surface: every OpenAPI path and its HTTP methods.

The fixture at ``tests/fixtures/openapi_paths.json`` maps each path to its
sorted list of upper-case methods. ``tests/test_openapi_snapshot.py`` fails
whenever the live app disagrees, so a refactor that silently drops, renames
or duplicates a route is caught without a database.

Usage (from ``backend/``)::

    .venv/bin/python scripts/openapi_snapshot.py          # (re)write the fixture
    .venv/bin/python scripts/openapi_snapshot.py --check  # exit 1 on any drift

Routes registered with ``include_in_schema=False`` (``/health`` and the SPA
catch-all) never appear here, by design.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "openapi_paths.json"

Paths = dict[str, list[str]]


def current_paths() -> Paths:
    """``{path: [METHOD, ...]}`` from the live FastAPI app, fully sorted."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    # main.py prints every route and its env-loading status on import.
    with contextlib.redirect_stdout(io.StringIO()):
        import main  # noqa: WPS433 - deliberate late import
    schema = main.app.openapi()
    return {
        path: sorted(method.upper() for method in ops)
        for path, ops in sorted(schema["paths"].items())
    }


def load_fixture(path: pathlib.Path = FIXTURE_PATH) -> Paths:
    with path.open() as fh:
        data = json.load(fh)
    return {p: sorted(m.upper() for m in methods) for p, methods in data.items()}


def _flatten(paths: Paths) -> set[str]:
    return {f"{method} {path}" for path, methods in paths.items() for method in methods}


def diff(expected: Paths, actual: Paths) -> tuple[list[str], list[str]]:
    """``(added, removed)`` as sorted ``"METHOD /path"`` lines.

    ``added`` is what ``actual`` has that ``expected`` lacks; ``removed`` the
    reverse. Both empty means the two surfaces are identical.
    """
    before, after = _flatten(expected), _flatten(actual)
    return sorted(after - before), sorted(before - after)


def write_fixture(paths: Paths, path: pathlib.Path = FIXTURE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(paths, indent=2, sort_keys=True) + "\n")


def format_diff(added: list[str], removed: list[str]) -> str:
    lines: list[str] = []
    if added:
        lines.append(f"{len(added)} added (live app has, fixture lacks):")
        lines += [f"  + {line}" for line in added]
    if removed:
        lines.append(f"{len(removed)} removed (fixture has, live app lacks):")
        lines += [f"  - {line}" for line in removed]
    return "\n".join(lines)


def main_cli(argv: list[str]) -> int:
    live = current_paths()
    if "--check" in argv:
        if not FIXTURE_PATH.exists():
            print(f"missing fixture {FIXTURE_PATH}; run without --check to create it")
            return 1
        added, removed = diff(load_fixture(), live)
        if added or removed:
            print(format_diff(added, removed))
            print(f"\nrun `python {pathlib.Path(__file__).relative_to(BACKEND_DIR)}` to accept")
            return 1
        print(f"OpenAPI surface unchanged: {len(live)} paths")
        return 0
    write_fixture(live)
    print(f"wrote {len(live)} paths to {FIXTURE_PATH.relative_to(BACKEND_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli(sys.argv[1:]))
