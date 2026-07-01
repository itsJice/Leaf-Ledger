# Leaf & Ledger Project Context

## North Star
Leaf & Ledger is a centralized catalog and project system for The Branch Design Group. It replaces years of spreadsheet recipes, supplier browsing, image folders, pricing math, and mockup prep with one searchable product library and job workflow.

## Product Boundary
Leaf & Ledger is the catalog system of record, not primarily a scraping product.

The app should receive supplier catalog data from CSV/XLSX files, PDFs, supplier exports, external scrape exports, or manually cleaned spreadsheets. Once the data arrives, Leaf & Ledger owns validation, normalization, duplicate detection, source tracking, image handling, search, project use, quote math, invoices, and mockups.

Scraping is an external or fallback extraction method. It should produce an organized spreadsheet or JSON export that Leaf & Ledger can import. Do not make universal website scraping, proxy management, CAPTCHA bypass, or supplier-session maintenance the default app responsibility.

Reference strategy: [CATALOG_DATA_STRATEGY.md](CATALOG_DATA_STRATEGY.md).

## Catalog Model
- Product Library is the general catalog across suppliers.
- Hearts mean favorites only.
- Plus means add this product to a client project bucket.
- Supplier data stays source-truth: exact supplier SKU, description, price, UOM, availability, dimensions, origin, material, and images.
- Search should work the way a designer thinks: color words, material, size, category, product type, supplier wording, and normalized supplier codes.
- Every imported product should preserve where it came from: supplier, source file or export, source URL/page when known, import date, and season/year.
- Missing fields should be visible as review work, not hidden as if the catalog is complete.

## Project Model
- Clients are the top level for real work. A client may be a homeowner, business, designer, or designer's client.
- Each client can have many projects/jobs, such as Dining Room, Beach House, Bookshelf, or Holiday Install.
- Projects replace the old Arrangements UI.
- Each project has buckets such as Tree, Garland, Bookshelf, Bookshelf 2, etc.
- Products added to a bucket start as saved ideas/candidates.
- Only selected products affect recipe math, purchase sheets, costs, markups, quotes, and invoices.
- V1 has a lightweight clients table for creating clients before projects exist. Projects still store the client name for simple attachment, and a fuller client profile can be expanded later for addresses, designers, notes, and project history.

## Cost, Price, And Profit Model
- Every finished process that creates a client-facing quote, project package, product build, or purchase sheet should end with a pricing summary.
- The summary should show our cost, the customer price, gross profit, and profit margin.
- Our cost starts with selected supplier product cost and quantity. Later versions can include freight, labor, install, tax, card fees, waste, rush costs, and other landed-cost adjustments.
- Customer price should come from the project's markup/quote rules, not from changing the supplier source price.
- Gross profit is `customer price - our cost`.
- Profit margin is `gross profit / customer price`.
- Markup is separate from margin and can be shown as `gross profit / our cost` when useful.
- If a required cost or quote setting is missing, the process should show the missing input instead of pretending the margin is known.

## Future Workflow
- Recipe sheets and historic spreadsheets become standardized formulas.
- Selected bucket products plus recipe logic calculate quantities to order.
- Purchase sheets and client quote numbers come from selected products and pricing settings.
- AI mockups use project products and uploaded client-space photos to visualize the finished design.

## Effort Metrics
- 2026-05-29 instant-loading pass: Added/verified app bootstrap summaries, cached summary usage, paged Product Library loading, debounced catalog search, and global product filter metadata. Backend compile passed, frontend build passed, and local HTTP checks passed for bootstrap summary, product filter metadata, paged product search, and frontend routes: clients, projects, project detail, library, favorites, suppliers, invoice, and mockups.
