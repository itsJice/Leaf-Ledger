# Allstate Onboarding Notes

## Purpose

Allstate is a historical reference supplier for Leaf & Ledger readiness, normalization, image handling, and Product Library completeness.

These notes capture what worked, what failed, what decisions were made, and what future supplier imports or fallback extractors should copy or avoid.

## Current Interpretation

This file documents a working in-app portal scraper, but it is not the default strategy for future suppliers. The current product direction is source-first catalog intake: supplier exports, PDFs, external scrape exports, or cleaned spreadsheets should be tried before building portal automation.

Use Allstate as a reference for readiness checks, standardized product display, image storage, and review flags. Do not treat it as proof that every supplier should get an in-app scraper.

## Core Rule

Allstate source data is truth.

The app should display supplier-provided values clearly instead of inventing or recalculating them unless the supplier or recipe system explicitly gives us enough information to do so.

## Historical Portal Workflow Pattern

The historical Allstate portal workflow worked in this order:

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

## Verified Readiness Snapshot

Last verified locally on 2026-06-02 through `/api/scraper/allstate-readiness/1`.

- Credentials: saved in the app/database.
- Catalog configuration: 30 active Allstate categories cached.
- Catalog selection: all 30 cached categories selected.
- Estimated selected catalog size: 9,444 products.
- Product Library upload: 8,470 active Allstate products imported.
- Standardized product data: 8,470 of 8,470 products have SKU, name, category, price, and UOM.
- Photos and source details: 8,470 of 8,470 products have detail payloads; 8,449 have real displayable product photos and 21 currently show supplier placeholders.
- Internal picture storage: 8,449 photos are stored inside Leaf & Ledger; 21 placeholder image cases should be reviewed and marked `no_supplier_image` when appropriate.
- Image review samples include SKUs such as `RW0060-GR`, `RW0081-RE`, `FBQ576-LV/GR`, `FBQ576-PK/GR`, and `FSP570-PK`; several point to Allstate's `price_update.gif`, which appears to be a supplier placeholder rather than a real product photo.
- Builder connection: Allstate products are used in 18 builder line items.
- Readiness result before placeholder review: 99% resolved, 99% internally stored pictures, with next action to review supplier placeholder images and mark them as no-image when appropriate.

The Suppliers page now has an expanded Allstate readiness panel that combines configuration, import, standardization, photos/details, picture storage, and builder usage into one workflow status.

## Historical Portal Working Plan

This was the plan to get Allstate fully working from setup through builder use through the in-app portal extractor. Keep it as a maintenance reference for Allstate and as evidence for what a finished import should look like.

For future suppliers or future Allstate season refreshes, first try supplier exports, PDFs, external scrape exports, or cleaned spreadsheets. Return to this portal plan only when the source-first path cannot produce a usable catalog import.

### 1. Configuration Workflow

Goal: Allstate can be configured by a normal user without touching code.

- Save Allstate username and password on the supplier record.
- Confirm credentials stay in the app/database and never appear in GitHub.
- Let the user open Configure Catalog from the Suppliers page.
- Discover Allstate categories live when needed.
- Reuse the remembered category index when it is still valid.
- Let the user select all categories or a smaller subset.
- Save selected categories as the source of truth for future syncs.
- Show configuration readiness in the Allstate readiness panel.

Done when:

- credentials are saved,
- category discovery has cached Allstate categories,
- selected category mode is clear,
- the UI can recheck readiness without a developer.

### 2. Catalog Upload

Goal: every selected Allstate listing row can be brought into Product Library.

- Run Sync Catalog for the selected categories.
- Scrape listing pages using the saved category selection.
- Preview rows before import.
- Import listing rows into Product Library.
- Upsert by supplier and SKU so reruns update products instead of duplicating them.
- Keep inactive/discontinued handling explicit instead of silently deleting old rows.
- Track import count against estimated selected product count.

Done when:

- every selected row has a Product Library product or a clear skip reason,
- no duplicate active SKUs exist for Allstate,
- the readiness panel shows Product Library upload complete.

### 3. Standardized Product Information

Goal: Allstate products are useful in search, quoting, purchasing, and builder screens.

- Store supplier SKU, name, category, current price, and UOM on every active product.
- Preserve supplier-provided values in raw data.
- Normalize common fields for app search and filters.
- Decode user-facing colors where possible while keeping Allstate color codes internally.
- Show pricing exactly as Allstate provides it unless a later recipe system has enough data to calculate derived pricing.
- Store detail-page fields such as dimensions, UPC, country of origin, case quantity, box quantity, suggested retail, material, season, and availability.

Done when:

- every active Allstate product has required standardized fields,
- expanded product details can show the important supplier data,
- Product Library filters/search use clean display values instead of raw supplier codes where practical.

### 4. Full Pictures

Goal: every Allstate product has a displayable image or an explicit image status.

- Backfill product detail pages in safe batches.
- Prefer storing product images inside Leaf & Ledger.
- Keep supplier-hosted URLs as a temporary display fallback.
- Retry failed image storage jobs.
- Detect supplier placeholder images, especially `price_update.gif`.
- Mark true placeholders separately from retryable failures so the app does not keep retrying images Allstate does not actually provide.
- Use the Suppliers readiness action to mark known Allstate placeholder images as reviewed `no_supplier_image` products.
- Count reviewed no-image products as resolved for readiness, while keeping stored-photo coverage separate.
- Product Library and builder product search should display reviewed placeholders as `No supplier image`, not as pending or retry-needed.
- Known supplier placeholder URLs should display as `Supplier placeholder` instead of rendering the placeholder GIF as a product image.
- Keep sample problem SKUs visible in the Suppliers readiness panel.

Done when:

- every active product has a displayable photo or an explicit placeholder/no-image status,
- stored image coverage is tracked separately from display-ready coverage,
- the remaining image problems are actionable instead of vague.

### 5. Builder Connection

Goal: Allstate products can be selected inside the builder with enough information to quote and purchase correctly.

- Make Allstate products searchable from builder product-selection buckets.
- Show image, SKU, supplier, category, unit, price, and key dimensions in builder results.
- Add selected products to project/container/builder line items.
- Keep supplier product IDs attached to builder lines.
- Use standardized product data for builder display.
- Preserve raw supplier details for future purchase order and quote logic.
- Later, connect recipe templates so each arrangement type knows which Allstate product buckets are needed.

Done when:

- Allstate products appear in builder search,
- selecting an Allstate product creates a builder line item,
- the readiness panel reports builder usage,
- selected builder products retain the data needed for purchasing and quoting.

### 6. Final Acceptance Checklist

Allstate is fully working when:

- credentials are configured and not public,
- categories are discovered and remembered,
- selected categories are saved,
- selected catalog rows import into Product Library,
- products are standardized,
- product details are backfilled,
- product images are stored or explicitly marked,
- Product Library search/filtering uses the standardized data,
- builder search can find Allstate products,
- builder line items can hold Allstate selections,
- the Suppliers readiness panel shows what is complete and what still needs attention.

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
- Supplier placeholders such as `price_update.gif` should be classified separately from retryable image failures.

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
