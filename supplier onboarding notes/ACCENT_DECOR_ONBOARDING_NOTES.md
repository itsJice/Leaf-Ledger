# Accent Decor Onboarding Notes

## Status

- Wave: 1
- Type: Product-heavy florals/decor
- Status: Ready; selected catalog imported, standardized, photo-stored, and connected to Builder
- Scraper key: `accent_decor`

## Current Interpretation

Accent Decor is a historical working portal-extraction reference. Keep the credential, Magento, image, and readiness notes for maintenance, but do not use this file as the default pattern for future suppliers.

Future supplier work should first try supplier exports, PDFs, external scrape exports, or cleaned spreadsheets. Use Accent-style portal extraction only when no better source exists.

## Current Live Snapshot

Last checked locally on 2026-06-18.

- Supplier id: `15`
- Credentials: saved and passing catalog discovery.
- Product Library upload: `2,338` active products imported.
- Cached category index: `149` active Accent Decor categories.
- Selected catalog: `149` selected categories; category/listing appearances total `22,807` before SKU dedupe.
- Standardized product data: `2,338 / 2,338`.
- Photos and details: `2,338 / 2,338`.
- Picture storage: `2,338 / 2,338` internally stored photos.
- Builder connection: `1` builder line exists.
- Readiness: `100%`.
- Next action: treat Accent Decor as a working supplier reference for Magento-style onboarding, while keeping credential and price-sync notes below for future maintenance.

## Historical Local Snapshot

Last checked locally on 2026-06-03.

- Supplier id: `15`
- Credentials: saved in the app/database.
- Login URL: `https://www.accentdecor.com/customer/account/`
- Product Library upload: 0 active products imported.
- Catalog filters: none saved yet, meaning the workflow should treat this as all categories once discovery is available.
- Cached category index: 0 active Accent Decor categories.
- Scrape jobs: none recorded for Accent Decor.
- Latest discovery attempt: live login form was reached, but Accent Decor rejected the previously saved credentials.
- New workflow evidence from 2026-06-03 screenshots: Accent online access is activated with account number + billing zip, then ongoing login uses the Customer Login email/password form.
- Alternate workflow evidence from 2026-06-03 screenshots: the Accent homepage `SIGN IN | REGISTER` control opens a right-side `Sign in to Accent Decor` drawer with email/password fields; the scraper now tries this route as a fallback after the direct Customer Login page.
- Live retry result after adding homepage drawer fallback: the scraper submitted both the direct Customer Login page and the homepage sign-in drawer, but neither produced account dashboard access, so the saved app credential is still being rejected.
- Historical next action at that time: save the activated Accent Decor email/password in the supplier credentials, then rerun Configure Catalog.
- UI verification: Suppliers now shows `Credentials failed` on Accent Decor with supplier-aware Accent email/password guidance, and Configure Catalog should surface an email/password credential message for activated accounts.
- UX path: the failed-credentials warning includes `Edit credentials`, which opens the supplier editor with Accent-specific fields: `Accent email` and `Accent password`, plus a note that account number/billing zip are only for one-time online access activation.
- Browser verification: the Accent supplier card and expanded failed-credentials warning wrap cleanly in the current in-app browser width; the disabled price sync and edit-credentials path remain readable.
- Failed/untested credential controls: `Configure Catalog` stays enabled so the corrected credentials can be tested, but `Sync Catalog` and the product limit input are disabled while credentials are marked `failed` or `untested`.
- API guard: direct `POST /api/scraper/start` calls for Accent Decor are rejected while credentials are `failed` or `untested`, so product scrape jobs cannot bypass Configure Catalog credential validation.
- Price sync guard: Accent Decor price sync is also disabled/rejected while credentials are `failed` or `untested`; direct `POST /api/scraper/sync-prices/15` returns the same Accent email/password guidance.
- Product Library/builder support: frontend search and detail views include Accent raw fields such as `Category`, `Style`, `Finish`, `Material`, `Materials`, `Unit of Measure`, `Country`, `Height`, `Width`, `Diameter`, `Length`, and `Availability` once products are imported.
- Preview support: scraper preview rows now expose Accent image lists, source/detail URLs, dimensions, style, and finish before import.

## Historical Portal Maintenance Notes

The credential, discovery, parser, readiness, and working-plan sections below are maintenance notes for the existing Accent portal extractor. They should not override the current source-first catalog strategy in [../CATALOG_DATA_STRATEGY.md](../CATALOG_DATA_STRATEGY.md).

Use this path only when Accent cannot provide a current-season export, PDF, external scrape export, or cleaned spreadsheet.

## Credentials

- Store credentials in the app only.
- Never commit credentials or `.env` files.
- Accent Decor online access activation uses account number plus billing zip code.
- Accent Decor scraper login should use the activated Customer Login email/password after online access has been activated.
- Accent Decor login fallback: if the direct Customer Login page is not usable, the scraper opens the Accent homepage, clicks `SIGN IN | REGISTER`, fills the right-side sign-in drawer, and verifies access by loading the account dashboard.
- If credentials fail, use Suppliers → Accent Decor → `Edit credentials`, enter the activated Accent email/password, save, then rerun `Configure Catalog`.
- Saving changed credentials marks them `untested`; a successful Configure Catalog discovery is what promotes them to `ok` and unlocks Sync Catalog.
- Readiness behavior: credentials stay `partial` while `failed` or `untested`; they are only `done` after catalog discovery succeeds and marks them `ok`.
- Successful discovery handoff: CatalogWizard now refreshes the supplier row and readiness summary after any successful catalog load, so when Accent credentials are corrected and discovery succeeds, the `Credentials failed/untested` badge should clear without a manual page reload.
- Cache safety: Accent Configure Catalog forces a live login for credential validation; cached category rows cannot promote credentials to `ok` by themselves.

## Discovery Notes

- Login URL: `https://www.accentdecor.com/customer/account/login`
- Category structure: Magento category slugs.
- Product count source: Magento toolbar amount when available; otherwise listing link estimates.
- Pagination behavior: Magento listing pagination via `rel="next"` or `.next`.
- Known crawl slugs in code include `all-products`, `floral-and-botanical`, `vases-and-planters`, `baskets-and-boxes`, `candles-and-lanterns`, `seasonal`, `wreaths-and-garlands`, `home-accents`, `decorative-accessories`, `trays-and-books`, `moss-and-bark`, `ribbon-and-wire`, and `containers`.
- Current blocker: saved credentials did not pass Accent Decor login during live discovery.
- Current login evidence: direct Customer Login and homepage drawer paths were both attempted; the blocker is now credential acceptance, not the missing drawer route.

## Product Detail Notes

- SKU field: Magento itemprop/product-info SKU, with URL fallback.
- Price fields: primary `span.price` / itemprop price.
- UOM field: `Unit of Measure`, `UOM`, or `Unit` from product attributes.
- Availability field: stock/availability text parsed by scraper base.
- Availability filter support: Product Library metadata recognizes Accent `Availability` values such as `In Stock`.
- Image behavior: product page image tags and gallery data-src values, excluding logo/placeholder/spacer/icon images.
- Source tracking: parsed products now preserve `detail_url`, `source_url`, `source_photo_url`, `image_urls`, `detail_status`, and `image_status` in `raw_data`.
- Dimensions/weights: dimensions parsed from Magento product attributes.
- Country/material fields: `Country of Origin`, `Country`, `Material`, or `Materials`.
- Product Library detail support: Accent dimensions, style, finish, material, unit, country, availability, and raw price fields are displayed/searchable from `raw_data` after import.
- Product Library typed-field support: when typed product columns are present, Product Library can display `height_in`, `width_in`, `diameter_in`, `finish`, and `style`, with raw Accent fields as fallback.
- Builder search support: typed Accent dimensions, finish, and style are included in builder product search, in addition to raw Accent fields.
- Image display fallback: Product Library, builder picker, builder line items, and recipe-intelligence context can use imported `image_urls` / `source_photo_url` when `photo_url` is still empty before internal photo storage finishes.
- Readiness image fallback: supplier readiness and enrichment counts now use the same display-image fallback, so imported Accent rows with `image_urls` are counted as photo-ready while still showing separately as supplier-hosted until internal storage finishes.
- Admin dashboard image fallback: supplier health and global missing-image counts now use `photo_url`, `image_urls[1]`, and `raw_data.source_photo_url`, excluding `no_supplier_image`, so Accent rows with imported supplier-hosted images are not counted as missing photos.
- Zero-product readiness copy: standardized data, photos/details, and picture storage steps now point back to Product Library import before suggesting enrichment/storage actions.
- Import persistence support: core import now writes Accent image arrays, height, width, diameter, finish, and style into first-class product columns as well as preserving the raw payload.
- Import contract support: cached Accent preview rows are normalized through a shared import helper before database upsert, covering SKU decoding, price parsing, category/unit mapping, image status, detail status, dimensions, finish, style, material, availability, and raw payload preservation.
- Image-array import fallback: if an Accent preview/cache row has `image_urls` but no separate `photo_url` or `source_photo_url`, import now promotes the first image URL into `raw_data.source_photo_url` so photo storage can still download it.
- Selected import support: selected SKU imports compare both raw and URL-decoded SKU values so encoded Accent catalog SKUs still match the preview selection and import progress counts.
- Photo storage support: the Suppliers panel now exposes an Accent-safe photo storage action that calls and polls supplier-scoped image backfill, so Accent supplier-hosted photos can be copied into Leaf & Ledger storage without starting image work for every supplier. The backend image-storage worker now also reads first-class `image_urls`, not only `photo_url` and `raw_data.source_photo_url`.
- Photo storage conflict handling: if another supplier-scoped image job is already running, Accent photo storage now returns and displays a specific conflict message instead of pretending the Accent job started.
- Schema check: the local `products` table has `image_urls`, `height_in`, `width_in`, `diameter_in`, `finish`, and `style` columns, so the richer import path matches the database.

## Test Notes

- Small category tested: discovery could not reach category crawl because login failed.
- Parser smoke test: a synthetic Accent-style product page returns detail/source URLs, source image URL, image list, category, availability, detail status, and image status.
- Parser/import contract test: `backend/tests/test_accent_decor_scraper.py` covers the synthetic Accent product page fields, cached-preview-to-product-import normalization, image-array-only storage fallback, encoded/decoded selected-SKU matching, supplier-scoped image backfill conflict handling, and Accent credential copy so this behavior can be checked by pytest once dev dependencies are installed.
- Live API verification: backend verification on port `8000` confirmed the updated Accent readiness response, Accent enrichment response, and admin dashboard query against the local database after restarting the app backend with the current code.
- Preview count: none yet.
- Import count: 0.
- Duplicate active SKUs: TBD
- Image/detail backfill result: TBD

## Historical Readiness Workflow

Accent Decor should now use the shared Suppliers readiness panel:

1. Credentials.
2. Catalog configuration.
3. Selected catalog.
4. Product Library upload.
5. Standardized product data.
6. Photos and full details.
7. Picture storage.
8. Builder connection.

The current readiness result should show credentials partial/failed, catalog configuration missing, and Product Library upload missing.

## Fallback Portal Working Plan

This is the old portal-extraction plan. For any new Accent season refresh, first try to obtain a supplier export, price book, PDF catalog, external scrape export, or cleaned spreadsheet. Return to this plan only if those sources cannot produce a usable import file.

1. Credentials and configuration gate.
   - Use Suppliers -> Accent Decor -> Edit credentials.
   - Enter the activated Accent Decor email/password. If online access has not been activated yet, use Accent's Express Registration page with account number and billing zip first.
   - Save credentials in the app/database only.
   - Run Configure Catalog with live discovery.
   - Done when `credential_status` becomes `ok` and Accent categories are cached.

2. Catalog scope.
   - Review discovered Magento categories and estimated product counts.
   - Start with a small category test before a full catalog run.
   - Save selected categories only after the counts look sane.

3. Test scrape and preview.
   - Run Sync Catalog with a small limit.
   - Confirm preview rows include SKU, name, price, UOM, category, availability, dimensions, material/origin, detail URL, and usable image URL.
   - Fix parsing before importing if required fields are missing.

4. Product Library import and standardization.
   - Import the test preview rows.
   - Verify no duplicate active SKUs for Accent Decor.
   - Map Accent raw fields into the shared Product Library view while preserving supplier-specific raw fields.
   - Confirm Product Library search finds Accent products by SKU, name, category, style, finish, material, country, dimensions, and availability.

5. Full details and pictures.
   - Store displayable product photos inside Leaf & Ledger when possible.
   - Use the Accent `Store supplier photos` action in Suppliers after import if photos are still supplier-hosted.
   - Mark true no-image cases explicitly instead of leaving them as retryable failures.
   - Keep detail attributes such as style, finish, material, dimensions, country, availability, and UOM visible in the product detail modal.

6. Full catalog upload.
   - Expand from the small test category to selected production categories.
   - Run full Sync Catalog, preview, and import.
   - Re-check readiness counts: imported products, standardized products, photo-ready products, stored images, details, and retryable problems.

7. Builder tie-in.
   - Confirm Accent products appear in builder product search and component buckets.
   - Add an Accent product to a builder line item and verify image, supplier, SKU, UOM, price, quantity, and cost display correctly.
   - Use Accent categories/materials/styles to improve bucket matching for containers, botanicals, decor, and accessories.

8. Ongoing sync.
   - Re-enable price sync only after credentials are `ok`.
   - Confirm price sync updates existing products without duplicating SKUs.
   - Track discontinued/unavailable items cleanly.

Accent Decor portal extraction is fully working when Configure Catalog passes, selected categories are saved, the selected catalog imports into Product Library, products have standardized fields and full pictures/details, and builder search can select Accent products with correct cost context. The business goal, however, is still a reliable current-season catalog import, whether the source is a supplier file, external scrape export, PDF-derived table, or this fallback extractor.

## Lessons Learned

- TBD
