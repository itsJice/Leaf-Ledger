# Allstate Onboarding Notes

This case record documents a mature supplier workflow used to establish shared readiness, normalization, image, and Product Library expectations.

## Status

- Type: product-heavy decor catalog
- Integration: legacy portal adapter with Product Library and project usage
- Current interpretation: readiness reference, not a requirement to reproduce portal automation for every source

## What worked

- Category discovery could be cached and reviewed before a full import.
- Supplier SKUs, descriptions, units, dimensions, source URLs, and raw fields were retained during normalization.
- Detail and image backfill could improve previously imported rows without creating duplicate products.
- A readiness summary translated credentials, catalog scope, normalization, images, and downstream use into actionable checks.
- Product Library and project-builder usage provided stronger evidence than a completed extraction job alone.

## Problems encountered

- Placeholder images could look like successful photo coverage.
- Unit and pack information required supplier-specific interpretation.
- Long-running enrichment needed progress and retry visibility.
- Portal access was an operational dependency unrelated to the core catalog model.

## Resulting decisions

1. Evaluate readiness after import, not merely extraction completion.
2. Detect placeholders and retain source-image fallback state.
3. Keep raw supplier values alongside normalized fields.
4. Make enrichment idempotent and safe to retry.
5. Use the same readiness concepts for file-based imports.

## Reusable readiness questions

- Is the intended catalog scope known?
- Are active supplier SKUs unique?
- Are required display fields present or explicitly flagged?
- Are images internal, externally referenced, or missing?
- Can products be found and used in a project?
- Is the next remediation action clear?
