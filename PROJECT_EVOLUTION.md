# Project Evolution

This is the canonical record of how Leaf & Ledger developed: the problems encountered, approaches attempted, evidence gathered, decisions changed, and work that remains incomplete.

It is intentionally different from the roadmap. The roadmap describes intended direction; this document explains why that direction exists. Detailed implementation and recovery instructions remain in the linked runbooks.

## Status language

- **Shipped** — implemented in the application and covered by repeatable verification or operational use.
- **Validated** — tested with representative data or a bounded workflow, but not yet generalized.
- **Explored** — investigated or prototyped; not a dependable product capability.
- **Planned** — documented future work with no claim of completion.

## 1. From scattered operations to one system

**Problem.** Product research, supplier catalogs, design recipes, images, and pricing lived across spreadsheets, portals, and folders. Reusing prior work required remembering where it was stored and how earlier calculations had been made.

**Initial approach.** The project began with a platform-generated React and FastAPI foundation and modeled the visible workflow first: products, suppliers, clients, arrangements, settings, invoices, and mockups.

**What worked.** The generated foundation made it possible to test the workflow quickly and establish a shared web application rather than another spreadsheet.

**What did not.** Screen coverage alone did not create a trustworthy system of record. Supplier data still arrived in inconsistent shapes, some product fields were incomplete, and the project model mixed saved ideas with products that should affect cost.

**Decision.** Define explicit catalog, project, and pricing invariants before expanding the feature surface. These rules now live in [Project Context](PROJECT_CONTEXT.md).

**Status:** Shipped foundation; product rules continue to mature.

## 2. Building a searchable Product Library

**Problem.** A useful catalog needed to preserve supplier truth while supporting the language a designer uses to search: product type, color, material, size, supplier terms, and normalized categories.

**Approach.** Products were normalized into shared fields while retaining supplier-specific raw data. Search and filtering were added to the Product Library, together with favorites and project-selection actions.

**What worked.** A shared catalog made products reusable across suppliers and projects. Keeping raw source fields prevented normalization from erasing details that later proved important.

**What did not.** Loading broad product sets and filter data eagerly made the application feel slow as the catalog grew.

**Decision.** Add paginated product retrieval, debounced search, global filter metadata, and cached bootstrap summaries. A May 2026 loading pass verified the API and main application routes after these changes.

**Status:** Shipped, with further bundle and query optimization still possible.

## 3. Learning the cost of portal-first supplier onboarding

**Problem.** Supplier sites exposed products through different authentication flows, page structures, APIs, and image systems. The early assumption was that each supplier could be connected through an in-application scraper.

**Approach attempted.** Supplier-specific browser and HTTP adapters were built, along with catalog discovery, price synchronization, detail enrichment, and image backfill tools.

**What worked.** Bounded adapters proved that Leaf & Ledger could normalize real, inconsistent supplier records. The work also produced reusable lessons about category caching, source preservation, duplicate handling, image storage, and progress reporting.

**What failed or became brittle.** Login changes, transient network failures, long detail passes, account-specific behavior, and site-specific pagination made universal portal automation expensive to maintain. A successful parser did not guarantee a dependable end-to-end import.

**Decision.** Portal automation became a fallback extraction method rather than the core product. The preferred path is a supplier export, normalized file, PDF-derived dataset, or external extraction output that enters a stable import contract.

See [Catalog Data Strategy](CATALOG_DATA_STRATEGY.md) and the [Supplier Connector Contract](supplier%20onboarding%20notes/SUPPLIER_CONNECTOR_CONTRACT.md).

**Status:** Shipped product boundary; legacy adapters remain supported selectively.

## 4. Making large imports observable and recoverable

**Problem.** Large supplier runs could fail after substantial work because of a network interruption, stalled import, or image-storage error. Restarting from zero wasted time and made completion difficult to reason about.

**Approach.** The backend added job records, progress reporting, supplier-scoped conflict handling, checkpointed batches, SKU skipping, image backfill status, and stop/resume controls.

**What worked.** Completed batches could be retained, and known products could be skipped on later runs. Manual recovery of a saved import demonstrated that preserving intermediate state was more valuable than treating a run as one indivisible task.

**What did not.** Early runs still coupled too much work into one process, and failures before a durable checkpoint could require repeating discovery or detail requests.

**Decision.** New long-running work should be idempotent, batch-oriented, and resumable from durable state. It should expose progress and the next safe action in the UI.

See [Operations and Handoff](OPERATIONS.md) for the current recovery standard.

**Status:** Validated across representative supplier workflows; not every legacy path follows the same standard yet.

## 5. Turning imports into a readiness decision

**Problem.** “The import finished” did not answer whether a supplier was actually usable in the Product Library or project builder.

**Approach.** Readiness summaries were introduced to check catalog scope, normalized fields, product visibility, images, and downstream use. Missing data remained visible instead of being counted as success.

**What worked.** The readiness view translated backend state into a practical next action and separated imported rows from display-ready products.

**What did not.** The first readiness logic was too closely associated with individual supplier implementations.

**Decision.** Treat readiness as a general post-import contract. Supplier-specific adapters may collect data differently, but completeness should be evaluated through shared concepts.

**Status:** Shipped for established paths; generalization is ongoing.

## 6. Refining projects, recipes, and pricing

**Problem.** A list of products was not enough to model design work. Users needed to save possibilities, choose final products, apply recipe quantities, and understand cost without losing the original supplier price.

**Approach.** Clients became the top-level owner of projects. Projects gained named buckets, candidate and selected states, product-type setup questions, and recipe-driven quantity logic. Pricing foundations separated supplier cost from customer price, profit, margin, and markup.

**What worked.** Candidate-versus-selected state prevented every saved idea from affecting purchasing. Keeping setup questions small made recipe workflows easier to explain to non-technical users.

**What remains incomplete.** Some pricing inputs and finished quote or invoice paths are still evolving. Several route-level UI files grew too large while the workflow was being discovered.

**Decision.** Preserve the working model and extract components incrementally. Do not hide incomplete pricing inputs or rewrite stable workflows solely for architectural neatness.

**Status:** Mixed: core project behavior is shipped; broader pricing and structural cleanup remain in progress.

## 7. Separating extraction from the application

**Problem.** Even after changing the product boundary, some suppliers still require external extraction.

**Approach.** A portable `catalog-extraction/` workspace was created. It produces CSV and JSON artifacts that conform to the same import contract and does not write directly to the application database.

**What worked.** The separation gives extraction a narrow responsibility and makes its output inspectable before import.

**What remains uncertain.** Selector-based runners are demonstrations, not proof that every supplier site can be automated reliably. Authentication and terms of access must be evaluated per source.

**Decision.** Keep extraction optional, file-producing, and independently replaceable. Prefer source cooperation over increasingly complex automation.

**Status:** Validated framework; supplier coverage remains selective.

## 8. Improving maintainability and handoff

**Problem.** Operational knowledge accumulated across implementation notes, generated boilerplate, and large modules. A future owner—or an AI-assisted development session—could see what the code did without understanding why it had changed direction.

**Approach.** The repository now separates the product story, architecture, operations, source strategy, roadmap, and chronological evolution. Automated tests cover normalization and representative adapters; frontend lint, type-check, and build checks are being made reproducible in CI.

**Lesson.** A tool is not finished when only its original builder can recover it. The runbook, failure state, and ownership boundary are part of the product.

**Status:** In progress.

## Current priorities

1. Make structured catalog intake dependable across common file sources.
2. Generalize readiness and review behavior beyond individual suppliers.
3. Complete pricing summaries without conflating cost, markup, and margin.
4. Decompose oversized modules behind stable interfaces.
5. Keep verification and handoff documentation current with shipped behavior.

## Updating this record

Add an entry only when evidence changes the understanding of the product. Record the problem, attempted approach, outcome, lesson, and resulting decision. Link commits, tests, or runbooks where useful, but do not copy credentials, private datasets, raw chat transcripts, or speculative claims into this file.
