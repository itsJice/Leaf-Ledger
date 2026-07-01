# Leaf & Ledger API

The backend is a FastAPI application that validates catalog data, coordinates supplier and project workflows, applies pricing rules, and exposes recovery controls for long-running work.

## Structure

- `app/apis/` contains route modules grouped by product domain.
- `app/libs/` contains catalog importers, supplier adapters, and shared services.
- `app/internal/` contains application bootstrapping, configuration, middleware, and generated platform support.
- `tests/` covers normalization, onboarding adapters, and representative supplier parsers.
- `routers.json` registers API modules used by the application runtime.

## Setup

```bash
uv sync --all-groups
./run.sh
```

Local database and provider settings belong in ignored environment files. Never commit credentials or production connection strings.

## Test

```bash
uv run pytest -q tests
```

For a syntax-only check:

```bash
uv run python -m compileall -q app
```

## Design boundaries

- Route modules should validate HTTP input and delegate reusable behavior to services.
- Supplier-specific extraction must normalize into the shared catalog contract.
- Missing source fields remain visible review items.
- Supplier cost and customer pricing are separate concepts.
- Long-running supplier work must report progress and support safe retry or resume behavior.
