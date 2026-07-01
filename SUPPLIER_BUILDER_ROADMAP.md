# Leaf & Ledger Supplier + Builder Roadmap

## Purpose

Leaf & Ledger is replacing a long-running spreadsheet workflow with one centralized system for supplier catalogs, product selection, project planning, recipe-based purchasing, client quotes, invoices, and mockups.

The app should eventually let a user:

- receive many supplier catalogs from files, exports, PDFs, or external extraction,
- search one standardized product library,
- create clients and projects,
- break projects into rooms or design packages,
- build individual products from recipe-style component buckets,
- calculate purchase needs from historical recipe data,
- generate purchase sheets, quotes, invoices, and mockups.

## GitHub Strategy

GitHub helps the project move safely and efficiently by giving us stable checkpoints, branches, reviews, rollback points, and a deployment path.

Rules:

- Keep the repository private.
- Do not push secrets, `.env` files, API keys, passwords, or supplier credentials.
- Prefer feature branches and pull requests.
- Do not push directly to `main` unless explicitly requested.
- Use small commits grouped by workflow or feature.
- Before risky or destructive changes, ask for confirmation.

GitHub does not make the app faster by itself. It makes the work safer and easier to manage.

## Code Cleanup Strategy

The code should be cleaned up gradually, not through one large rewrite.

Targeted cleanup areas:

- catalog intake, import, and supplier-source tracking,
- legacy supplier sync and scraper fallback logic,
- product library search/filter logic,
- clients/projects/builder workflow,
- shared UI components,
- shared loading/cache/data-fetching behavior.

The rule is: clean up the area we are actively improving, then verify it still works.

## Phase 1: Stabilize The App

Goal: the app should feel dependable before adding more supplier complexity.

Priorities:

- App opens reliably.
- Pages show their shell immediately.
- Small summary data loads quickly.
- Heavy catalog data does not block client/project pages.
- No page should show fake `0` or false empty states while real data is still loading.
- Long jobs show clear progress and do not freeze navigation.

Important loading principle:

- Clients, projects, rooms, design packages, and builder shells should feel nearly instant.
- Product Library/catalog data can load slightly slower, but only inside the relevant panel.

## Phase 2: Standardize Supplier Data

All supplier data should flow into one shared product structure while preserving supplier-specific raw details.

Important product boundary:

- Leaf & Ledger is the recipient and system of record for catalog data.
- External scrapers, supplier exports, PDF parsers, contractor work, or manual cleanup can all produce the source file.
- The app should not assume it owns universal web scraping.
- The stable contract is an organized spreadsheet/CSV/XLSX/JSON import with one row per supplier product.
- Scraping and portal automation are fallback extraction paths, not the default product experience.
- See [CATALOG_DATA_STRATEGY.md](CATALOG_DATA_STRATEGY.md).

Common normalized product fields:

- supplier,
- SKU / item number,
- product name,
- description,
- image,
- category,
- product type,
- color words,
- dimensions,
- price,
- UOM,
- minimum quantity,
- box quantity,
- case quantity,
- availability,
- country of origin,
- material details,
- supplier raw fields.

Supplier-specific fields should remain visible in a structured supplier details section.

Pricing rule:

- Display supplier pricing exactly as the supplier gives it.
- Do not invent per-piece, per-branch, per-bundle, or per-case pricing unless the supplier explicitly provides that value.

## Phase 3: Supplier Catalog Intake System

Supplier onboarding should start by finding the best data source, not by coding a scraper. Allstate remains useful as a reference for readiness and product-library completeness, but the standard path is now catalog intake first.

Detailed onboarding records live in:

- `supplier onboarding notes/SUPPLIER_ONBOARDING_INDEX.md`
- `supplier onboarding notes/SUPPLIER_CONNECTOR_CONTRACT.md`
- `supplier onboarding notes/SUPPLIER_ONBOARDING_CHECKLIST.md`
- `supplier onboarding notes/ALLSTATE_ONBOARDING_NOTES.md`
- `supplier onboarding notes/ACCENT_DECOR_ONBOARDING_NOTES.md`

Supplier catalog intake checklist:

1. Identify the best available supplier data source: CSV/XLSX/API/feed, PDF/catalog, external scrape export, or portal extraction.
2. Request a dealer/product export from the supplier before building a scraper.
3. Store any credentials safely outside GitHub only when portal access is actually needed.
4. Convert the source into the standard catalog import format.
5. Upload/import the source file.
6. Preview rows, duplicates, missing fields, images, and source references.
7. Import all usable product rows into Product Library.
8. Mark incomplete rows for review instead of silently dropping them.
9. Backfill images and detailed fields when the source provides enough information.
10. Compare new seasonal imports against prior imports.
11. Reserve in-app scraper/portal tools for suppliers that cannot provide usable files or exports.

Goal for each supplier:

- One current-season source file or export is available.
- 100% of usable product rows imported.
- No duplicate active SKUs per supplier.
- Images and details completed or explicitly marked retry-needed.
- Missing prices, MOQs, images, or details are visible as review items.

Current Allstate baseline:

- Allstate has a read-only readiness endpoint and Suppliers-page panel.
- The readiness panel checks credentials, cached categories, selected catalog scope, Product Library upload, standardized fields, photos/details, internal picture storage, and builder usage.
- Local verification on 2026-06-02 reported Allstate as 100% display-ready: 8,470 active imported products, 8,470 standardized/enriched/displayable products, and 18 builder line items using Allstate products.
- Picture storage is 99% complete: 8,449 photos are stored inside Leaf & Ledger, with 21 supplier-hosted fallback images still worth retrying.
- Future supplier imports should get the same kind of readiness summary once their source file/export has been imported.

Current Accent Decor target:

- Accent Decor is the active supplier onboarding workflow after the Allstate reference implementation.
- Supplier id `15` has saved credentials, but the latest live Configure Catalog check was rejected by Accent Decor.
- Accent Decor should not run fallback portal extraction, price sync, or full import until portal credentials are known-good. If a supplier export is available, prefer importing that source instead.
- Backend and UI now preserve/display Accent image arrays, source photo URLs, dimensions, finish/style, and readiness/admin image fallback counts; these pieces are ready for a real credential-passing catalog import.
- Once a usable source is available, the workflow should proceed through catalog import, standardized Product Library fields, images/details, picture storage, and builder search/selection. Portal category discovery is only needed for fallback extraction.

Current strategic shift:

- Future supplier work should prefer supplier-provided exports, PDFs, and external scrape exports before in-app scraping.
- For 200k+ seasonal products, the operational goal is one organized spreadsheet/export per supplier per season.
- Leaf & Ledger should become excellent at receiving and using that data, not at owning every supplier website's browser automation.

## Phase 4: Product Library Search

The Product Library should become one searchable catalog across all suppliers.

Search should support:

- natural words,
- supplier SKU,
- UPC,
- product type,
- category,
- color words,
- dimensions,
- size synonyms like `yd` and `yard`,
- availability,
- country of origin,
- supplier-specific details.

Search should use standardized data, not only raw supplier strings.

Color rule:

- User-facing color filters should show words like `green`, `olive`, `moss`, `silver`.
- Do not show supplier color codes like `GR` as filter labels.
- Supplier codes can still be stored internally.

## Phase 5: Recipe And Builder Data

The builder should eventually use historical recipe spreadsheets to know what components are needed for each kind of product.

Example:

- `Tree` may require `Container`, `Top Dressing`, `Trunks & Branches`, and `Leaves`.
- An `8 ft tree` may require a different quantity of materials than a `6 ft tree`.

The app should convert recipe history into structured templates:

- product type,
- component buckets,
- required questions,
- size rules,
- quantity formulas,
- purchasing units,
- markup/quote rules.

Builder `Select type` should eventually pull from this recipe data.

Current manual framework:

- User chooses a product type.
- App creates relevant component buckets.
- User manually selects products for each bucket.
- Selected products affect cost.
- Candidate/saved ideas do not affect cost until marked selected.

Builder visual standard:

- Use the compact fill-in-the-blank bubble/card UI as the standard for build parts.
- Each part should feel like a clean slot: number badge, part title, short helper text, and a product button.
- Nested groups, such as Christmas Tree `Enhancers`, should stay as one larger bubble with smaller product rows inside it.
- Keep the same left-side build sheet style across Select Type, Choose Parts, Review, and Order so the build does not visually change shape between steps.

Product type builder note:

Use the Christmas Tree builder as the first complete reference pattern for future product types.

- Start with simple user-facing buckets: `Tree`, `Enhancers`, `Tree Skirt`, and `Tree Topper`.
- Put setup questions on the right side before product selection. For Christmas Tree, this is tree size/profile; for future types, it should be the smallest set of questions needed to calculate quantities.
- Store setup choices in scope notes so the build can reopen correctly. For Christmas Tree, this includes tree type, height, canopy/diameter, profile, and enhancer package.
- If a bucket has internal recipe choices, keep them inside the bucket instead of creating more top-level buckets. Christmas Tree `Enhancers` uses a Regular/Premium selector inside the Enhancers bubble.
- Show calculated need as plain language, not business math. Example: `48 enhancers needed for the 14 ft standard tree selected.`
- Material rows should show only the part name, the calculated amount, and the product button. Avoid extra formula labels when the green amount already explains what to select.
- Use the selected setup to drive product quantities. For Christmas Tree, height/profile drives enhancer and ornament counts; Regular/Premium drives which material rows appear and ribbon yardage.
- Keep hidden recipe mechanics behind the scenes, but make the fill-in-the-blank product slots feel obvious to a non-business user.
- Persist any selector choices before review/order so reopening the build restores the same visible recipe.
- Add future validation when selected products conflict with the planned setup, such as a selected tree size not matching the planned tree size.

## Phase 6: Purchasing Logic

Purchasing should be calculated from:

- selected products,
- supplier price and UOM,
- recipe quantity rules,
- requested project quantity,
- supplier minimums, box quantities, and case quantities.

Outputs:

- purchase sheet,
- supplier order quantities,
- selected raw material cost,
- quote estimate,
- invoice-ready totals,
- cost/price/profit summary.

Rule:

- Supplier source data is truth.
- Recipe math can calculate order needs, but pricing should still display the supplier source values clearly.

Cost, price, and profit margin plan:

- At the end of every builder, quote, order, and invoice process, show a pricing summary before the user finalizes the workflow.
- The summary should include our cost, customer price, gross profit, profit margin, and any missing pricing inputs.
- Our cost should start with selected product cost multiplied by recipe/order quantity.
- Add landed-cost inputs when available: freight, labor, install, tax, card fees, waste, rush cost, and other project-specific adjustments.
- Customer price should be calculated from project quote rules, customer-specific pricing, or approved markup settings.
- Gross profit is `customer price - our cost`.
- Profit margin is `gross profit / customer price`.
- Markup is `gross profit / our cost`; keep it separate from margin so the app does not confuse the two.
- Do not overwrite supplier price with customer price. Supplier price remains the source cost, while customer price belongs to the quote/invoice layer.
- If a process cannot calculate margin yet, it should show exactly which input is missing, such as supplier cost, selected quantity, markup rule, labor, freight, or customer price.

Future Christmas tree validation:

- When a Christmas tree build starts, store the planned tree size/profile, such as `9 ft standard`, `7.5 ft pencil`, or `12 ft slim`.
- Before review/order is finalized, compare the planned tree size/profile against the actual selected tree product.
- If the selected product looks like a different size or profile, show a clear confirmation prompt before purchase order creation.
- Example: if the build was planned as `9 ft standard` but the selected product is a `15 ft tree`, ask whether to update the build to the selected tree or go back and choose the intended tree.
- If the user confirms the selected tree is correct, update the planned tree setup, enhancer/ornament counts, pricing multiple, and related quote math so the order reflects the real tree.
- If the mismatch is accidental, send the user back to the tree product slot to correct it.

## Phase 7: UI Polish

The app should feel clean, fast, visual, and guided.

UI priorities:

- page shell appears immediately,
- no false empty states,
- skeletons for unknown data,
- product images are first-class,
- builder workflow is clear step by step,
- buttons have obvious meaning,
- destructive actions are discreet but confirmed,
- project/client breadcrumbs preserve the entry path,
- Product Library plus button adds to projects/buckets,
- heart button controls Favorites only.

Builder visual direction:

- Use the polished mockup images as inspiration for layout, flow, spacing, and interaction.
- Keep Leaf & Ledger branding as the source of truth for colors, typography, and product identity.
- Do not copy the mockups blindly; adapt the useful visual ideas into the Leaf & Ledger system.

## Phase 8: Deployment

After local workflows are stable:

- deploy frontend and backend,
- configure production database,
- configure secure secret storage,
- configure image/file storage,
- set up backups,
- protect GitHub `main`,
- add deployment documentation.

## Working Rule

When making changes, prefer this order:

1. stabilize current workflow,
2. verify with the browser,
3. run build/compile checks,
4. confirm the process ends with cost, customer price, and profit margin when pricing is involved,
5. commit or checkpoint,
6. then move to the next workflow.
