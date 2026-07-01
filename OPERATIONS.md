# Operations and Handoff

This runbook describes how to operate, verify, recover, and hand off Leaf & Ledger without depending on undocumented local knowledge.

## Ownership checklist

An owner should be able to:

1. start the API and web application;
2. run backend and frontend verification;
3. import and review a small catalog;
4. identify incomplete or duplicate product rows;
5. inspect supplier readiness and long-running job status;
6. retry or resume a failed batch safely;
7. explain which settings are local secrets;
8. distinguish shipped behavior from roadmap ideas.

## Routine verification

```bash
cd backend && uv run pytest -q tests
cd frontend && npm run lint && npm run typecheck && npm run build
```

Before a release, also exercise a synthetic catalog import, Product Library search, client/project creation, candidate-versus-selected behavior, and pricing summaries.

## Catalog import recovery

- Keep the original source file unchanged.
- Inspect the import preview and failure counts before committing.
- Reprocess a batch after mapping or parser corrections.
- Treat repeated supplier SKU rows as a deduplication decision, not an automatic overwrite.
- Confirm committed products retain their source batch and supplier identity.

## Extraction recovery

- Prefer a supplier-provided export when portal automation becomes unstable.
- Resume from the last confirmed checkpoint instead of restarting a large catalog blindly.
- Store credentials only in approved environment or repository-secret storage.
- Never commit downloaded catalogs, browser profiles, recordings, or extraction output.
- Validate exported files before importing them into the application.

## Incident notes

Record failures in the relevant runbook with the symptom, affected boundary, evidence, recovery, and prevention. Do not include passwords, customer data, private prices, or account identifiers.

## Handoff standard

A handoff is complete when a new owner can follow the documented setup, run the checks, import sample data, recover a failed batch, and explain the product boundary without relying on the previous developer.
