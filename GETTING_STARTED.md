# Getting Started

This guide sets up Leaf & Ledger for local development and runs the same checks used to verify repository changes.

## Prerequisites

- Python 3.11
- Node.js 18 or newer
- [`uv`](https://docs.astral.sh/uv/)
- npm
- Access to a PostgreSQL database for database-backed workflows

## 1. Configure the backend

```bash
cd backend
uv sync --all-groups
```

Create local environment files from your team-approved configuration. Common settings include a PostgreSQL connection string and optional image-generation credentials. Environment files are ignored by Git; never commit them.

Start the API:

```bash
./run.sh
```

The development server listens on `http://localhost:8000` by default.

## 2. Configure the frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite development server normally opens at `http://localhost:5173`.

## 3. Verify the installation

Backend tests:

```bash
cd backend
uv run pytest -q tests
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

## 4. Exercise the main workflow

With a configured database:

1. Open Suppliers and create or select a supplier.
2. Upload a small catalog file and review its parsed rows.
3. Commit valid rows and confirm they appear in Product Library.
4. Search and filter the imported products.
5. Create a client and project, then add a product to a project bucket.
6. Confirm candidate and selected products remain distinct in pricing logic.

Use synthetic or approved sample data in development. Do not place customer records, supplier credentials, or downloaded production catalogs in the repository.

## Optional integrations

- Mockup generation requires an image-generation provider key.
- Portal extraction may require Playwright, SeleniumBase, or supplier-specific credentials.
- Scheduled operations require an external scheduler; see [Schedules](SCHEDULES.md).

These integrations are optional for the core build and unit-test checks.

## Troubleshooting

- If authentication is unavailable, confirm the frontend environment configuration.
- If database routes fail, verify the connection string and database access.
- If the frontend build warns about missing optional provider configuration, confirm that the affected workflow is intentionally disabled locally.
- If a supplier portal changes, prefer a new structured export before repairing browser automation.
