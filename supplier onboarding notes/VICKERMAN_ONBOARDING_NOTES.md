# Vickerman Onboarding Notes

This case record documents why large portal imports require checkpoints, resumable batches, and an explicit fallback boundary.

## Status

- Type: large product catalog
- Integration: legacy portal adapter with checkpointed import and image backfill
- Current interpretation: recovery reference, not the default onboarding pattern

## What worked

- A bounded proof imported products with normalized detail and internally stored images.
- Subsequent batches skipped already active supplier SKUs.
- Saved import payloads could be resumed after a stalled commit.
- Image backfill could continue independently and report remaining failures.
- Stop, status, and restart controls made the workflow observable from the application.

## Failures and edge cases

- Transient network failures interrupted long detail and image passes.
- Work completed before the next durable checkpoint could be lost.
- Some source products legitimately reported zero or unavailable prices; these were review items rather than parser errors.
- Combining discovery, detail collection, import, and image storage into one run made recovery harder.

## Resulting decisions

1. Divide large work into bounded, idempotent stages.
2. Persist checkpoints before expensive downstream work.
3. Skip known supplier SKUs without hiding changed source data.
4. Keep import and image recovery independently resumable.
5. Prefer structured catalog exports over repeated portal traversal.
6. Show source-quality exceptions explicitly instead of inventing values.

## Recovery standard

- Reconcile the saved job state before starting another batch.
- Resume a durable import payload rather than repeating extraction.
- Run image storage independently after product commit.
- Verify readiness and exception counts at the end of each batch.
- Record the failure mode without copying account or product identifiers into public notes.
