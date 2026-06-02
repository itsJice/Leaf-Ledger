# Leaf & Ledger Supplier + Builder Roadmap

## Purpose

Leaf & Ledger is replacing a long-running spreadsheet workflow with one centralized system for supplier catalogs, product selection, project planning, recipe-based purchasing, client quotes, invoices, and mockups.

The app should eventually let a user:

- connect many supplier catalogs,
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

- supplier sync and scraper logic,
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

## Phase 3: Supplier Onboarding System

Allstate is the reference implementation. New suppliers should follow the same repeatable connector process.

Detailed onboarding records live in:

- `supplier onboarding notes/SUPPLIER_ONBOARDING_INDEX.md`
- `supplier onboarding notes/SUPPLIER_CONNECTOR_CONTRACT.md`
- `supplier onboarding notes/SUPPLIER_ONBOARDING_CHECKLIST.md`
- `supplier onboarding notes/ALLSTATE_ONBOARDING_NOTES.md`

Supplier connector checklist:

1. Store credentials safely outside GitHub.
2. Log in.
3. Discover catalog/category structure.
4. Remember category structure so future syncs do not waste time rediscovering it.
5. Let the user choose selected categories.
6. Scrape selected product rows.
7. Preview rows and category counts.
8. Import all selected product rows.
9. Backfill images and detailed fields.
10. Sync prices safely without duplicating products.
11. Show progress, failures, and resumable status in the UI.

Goal for each supplier:

- 100% of selected product rows imported.
- No duplicate active SKUs per supplier.
- Images and details completed or explicitly marked retry-needed.

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
- invoice-ready totals.

Rule:

- Supplier source data is truth.
- Recipe math can calculate order needs, but pricing should still display the supplier source values clearly.

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
4. commit or checkpoint,
5. then move to the next workflow.
