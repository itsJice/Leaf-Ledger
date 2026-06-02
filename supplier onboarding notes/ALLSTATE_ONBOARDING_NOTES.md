# Allstate Onboarding Notes

## Purpose

Allstate is the reference supplier for the Leaf & Ledger supplier onboarding process.

These notes capture what worked, what failed, what decisions were made, and what future supplier connectors should copy or avoid.

## Core Rule

Allstate source data is truth.

The app should display supplier-provided values clearly instead of inventing or recalculating them unless the supplier or recipe system explicitly gives us enough information to do so.

## Final Workflow Pattern

The Allstate supplier workflow should work in this order:

1. Save supplier credentials.
2. Log into Allstate.
3. Discover catalog/category structure.
4. Store remembered category structure.
5. Let the user select categories in Configure Catalog.
6. Scrape selected category listing pages.
7. Preview scraped rows and category counts.
8. Import all selected product rows into Product Library.
9. Backfill images and source-page details in the background.
10. Track images/details until complete or explicitly retry-needed.

## Category Rules

- Selected catalog categories are the source of truth.
- If no categories are selected, the system may treat that as all categories, but the UI must clearly communicate that state.
- Category discovery should be remembered so future syncs do not waste time rediscovering the same structure.
- Allstate categories are commonly identified by `DDCODE` values such as `HZ0002`.
- Some categories have many pages, so pagination must continue until all product listing pages are collected.

## Import Rules

100% import means every discovered product row from selected categories creates or updates one Product Library row.

Import should not wait for:

- images,
- source detail enrichment,
- availability detail,
- supplier-specific extra fields.

Those fields can finish later through backfill.

No duplicate active SKUs should exist for the same supplier.

## Image Rules

Images are first-class product data for Leaf & Ledger.

For a design company, product images are not optional polish. They are core catalog information.

Rules:

- Product cards should reserve strong image space.
- Missing images should show `Image pending` or `Image retry needed`.
- Missing images should not silently disappear.
- Backfill should keep running in safe batches until images are stored or explicitly failed.
- Stored internal images are preferred over relying only on supplier URLs.

## Price Rules

Do not invent pricing.

Allstate should display:

- `BasePrice`,
- `UOM`,
- `MinQty`,
- `BoxQty`,
- `CaseQty`,
- `SugRetail` when available.

Avoid wording like `per each` if Allstate gave a clearer source value.

Preferred display example:

`Base price $36.10 / EA`

Do not calculate per-piece, per-branch, per-bundle, or per-case pricing unless that value is explicitly given or later calculated by a recipe/purchasing system with clear assumptions.

## Product Detail Fields

The Allstate detail page can provide:

- availability status,
- minimum quantity,
- box quantity,
- case quantity,
- product dimensions,
- box dimensions,
- case dimensions,
- product weight,
- box weight,
- case weight,
- UPC,
- case cube,
- suggested retail,
- class,
- color group,
- season,
- oversize flag,
- country of origin,
- material breakdown.

These should be shown in structured expanded product details when available.

Missing fields should be marked pending or unavailable instead of hidden in a confusing way.

## Search Lessons

Search should be natural for a designer, not only exact supplier text.

Useful search behavior:

- Search by readable description.
- Search by SKU.
- Search by color words.
- Search by category.
- Search by size/dimensions.
- Support synonyms such as `yd` and `yard`.
- Translate supplier color codes into words for user-facing filters.

Color filters should show words like:

- green,
- moss,
- olive,
- red,
- silver,
- gold,
- white.

Do not show raw supplier color codes like `GR` as the primary user-facing filter labels.

## UI Lessons

What worked:

- staged progress,
- preview before import,
- clear image/detail coverage counts,
- resumable batches,
- supplier-specific details in a structured section,
- using Leaf & Ledger’s clean layout instead of copying Allstate’s old website UI.

What needed fixing:

- false empty states,
- fake `0` counts before data loaded,
- misleading ETA/time-left language,
- too many confusing buttons,
- vague price labels,
- slow pages caused by loading the full catalog when not needed.

## Backfill Lessons

Backfill should be resumable and visible.

Good progress language:

- active products,
- images stored,
- details enriched,
- still needs attention,
- checkpoints complete,
- retry-needed failures.

Avoid overconfident ETA language unless the estimate is based on enough real runtime data.

## Future Supplier Pattern

When onboarding future suppliers, copy the Allstate structure:

1. Discover catalog structure.
2. Remember catalog structure.
3. Let user select categories.
4. Scrape selected rows.
5. Preview rows.
6. Import every selected row.
7. Backfill images/details.
8. Normalize common fields.
9. Preserve supplier raw fields.
10. Track progress and failures clearly.

Future suppliers may have different websites and data formats, but they should feed the same standardized Product Library.

