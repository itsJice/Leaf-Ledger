# Leaf & Ledger Web Application

The frontend is a React and TypeScript application for supplier intake, catalog search, client projects, recipe-driven product selection, pricing, and mockup workflows.

## Setup

```bash
npm install
npm run dev
```

The development server normally runs at `http://localhost:5173`.

## Verification

```bash
npm run lint
npm run typecheck
npm run build
```

## Structure

- `src/pages/` contains route-level product workflows.
- `src/components/` contains reusable application components.
- `src/apiclient/` contains generated API contracts and clients.
- `src/extensions/` contains platform and component-library integration code.

## UI principles

- Show source data faithfully and make missing values explicit.
- Keep catalog search responsive with pagination, cached summaries, and debounced filters.
- Distinguish saved candidates from selected products that affect quantities and cost.
- Explain recovery actions in plain language when imports or supplier jobs fail.
- Preserve user work while navigating long-running processes.

Generated API contracts should be updated from the backend schema rather than edited casually by hand.
