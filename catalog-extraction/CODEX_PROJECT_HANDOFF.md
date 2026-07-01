# Codex Project Handoff: Leaf & Ledger Catalog Extraction

## Who This Is For

This project is for The Branch Design Group / Leaf & Ledger.

Leaf & Ledger is an internal catalog and project system for organizing supplier products, building design projects, quoting, purchasing, and eventually invoicing/mockups.

## Core Mission

Build and run an external supplier catalog extraction system.

The scraper project should visit supplier websites or online catalogs, extract product data, and output organized files that Leaf & Ledger can import.

Leaf & Ledger itself should not become the universal scraper. This project is the extraction layer. Leaf & Ledger is the recipient and system of record.

## Why This Exists

The business currently has to visit many supplier websites one by one to build products and source materials. That is slow and painful.

The biggest business value is getting supplier products into one searchable Product Library.

Many suppliers have online catalogs. Some may provide CSV/XLSX exports, price books, PDFs, or feeds. When they do not, this project should scrape the catalog and produce a clean export file.

The goal is not daily scraping. The likely operating model is one major scrape per supplier per season, especially before Christmas season.

Scale target: over 200,000 supplier products across all suppliers.

## Product Boundary

This scraper project owns:

- Logging into supplier catalog sites when needed.
- Navigating catalog/category/listing/product pages.
- Handling pagination or infinite scroll.
- Extracting product information and image URLs.
- Producing CSV/XLSX/JSON exports.
- Keeping scrape logs and run reports.
- Running from GitHub Actions or local Codex sessions.

Leaf & Ledger owns:

- Importing exported files.
- Normalizing product rows.
- Deduping products.
- Storing import batches.
- Tracking missing fields and review status.
- Storing/using images.
- Displaying products in Product Library.
- Using products in projects, quotes, purchasing, invoices, and mockups.

The scraper project should not directly mutate the Leaf & Ledger database.

## Required Output Contract

Every supplier scrape should produce at least:

- `products.csv`
- `products.json`
- `run_report.json`

Preferred folder format:

```text
outputs/{supplier_key}/{run_id}/products.csv
outputs/{supplier_key}/{run_id}/products.json
outputs/{supplier_key}/{run_id}/run_report.json
```

Each product row should include these columns when available:

- `supplier_key`
- `supplier_name`
- `season`
- `sku`
- `name`
- `description`
- `category`
- `price`
- `uom`
- `moq`
- `box_qty`
- `case_qty`
- `availability`
- `dimensions`
- `image_url`
- `source_url`
- `source_category_url`
- `raw_json`

Missing values are allowed, but should be visible in the export/report.

Do not silently drop products unless there is no usable SKU or product identity. If rows are skipped, include skip counts and reasons in `run_report.json`.

## Success Criteria

A supplier scrape is successful when:

- It exports all reachable product rows for the selected supplier scope.
- Each product has supplier identity, SKU/item number, name, source URL, and as many details as the site provides.
- Image URLs are captured when available.
- Pricing reflects the logged-in/account-specific price when credentials are required and available.
- Duplicate supplier SKUs are either deduped or reported clearly.
- The resulting CSV can be imported by Leaf & Ledger without manual cleanup beyond review of genuinely missing fields.

## Operating Model

Use this priority order for each supplier:

1. If supplier provides CSV/XLSX/API/feed, use that instead of scraping.
2. If supplier provides PDF catalog plus price sheet, extract/convert it if practical.
3. If supplier only has an online catalog, scrape it.
4. If the site blocks automation or is too complex, produce a partial report and recommend another acquisition path.

## Technical Direction

Preferred stack:

- Python.
- SeleniumBase for browser automation and login-heavy sites.
- BeautifulSoup/lxml for HTML parsing.
- pandas/openpyxl for CSV/XLSX exports.
- GitHub Actions for manual seasonal runs.

The starter scaffold currently lives at:

```text
catalog-extraction/
```

Important starter files:

```text
catalog-extraction/README.md
catalog-extraction/requirements.txt
catalog-extraction/scripts/run_supplier.py
catalog-extraction/scripts/validate_export.py
catalog-extraction/src/catalog_extraction/schema.py
catalog-extraction/src/catalog_extraction/exporter.py
catalog-extraction/src/catalog_extraction/seleniumbase_runner.py
catalog-extraction/suppliers/american_best.example.json
.github/workflows/catalog-extraction.yml
```

Long-term, this should probably become its own repo:

```text
leaf-ledger-catalog-extraction
```

## Supplier Config Pattern

Each supplier should have a config file under:

```text
suppliers/{supplier_key}.json
```

The config should define:

- `supplier_key`
- `supplier_name`
- `season`
- login URL and selectors if needed
- category/start URLs
- product link/listing selectors
- pagination selector
- product detail selectors

If a supplier requires custom logic, create a supplier-specific script or adapter rather than making the generic runner too complex.

## First Supplier Target

Start with American Best.

Known URL:

```text
https://americanbest.com/login
```

Initial goal:

- Prove login if credentials are available.
- Find catalog/category pages.
- Extract 25 products first.
- Export CSV/JSON.
- Validate the export.
- Then scale to the full catalog.

If American Best blocks or cannot be completed quickly, move to a supplier with easier public catalog structure and return later.

## Supplier List To Eventually Support

Known suppliers include:

- Allstate Floral
- Select Artificials
- Regency
- American Best
- Autograph Foliages
- Winward Silks
- Amazing Green
- Craftex
- Vickerman
- Schusters of Texas
- Forest Line Products
- SecondFlor
- SuperMoss
- Accent Decor
- Unlimited Containers
- Wholesale Glass Vases International
- At Home
- DFW Vases
- Jay Scotts
- PMJC
- HR Casabella
- Jackson Pottery
- Champion Stone
- The Rock Warehouse

## GitHub Actions Requirement

Add a manual workflow that can run a supplier scrape with:

- supplier config path
- optional product limit
- credentials stored as GitHub repository secrets
- exported files uploaded as artifacts

Never commit supplier credentials.

## What Not To Do

- Do not build product-library UI here.
- Do not connect directly to the Leaf & Ledger database.
- Do not make the generic runner so abstract that it becomes impossible to debug.
- Do not hide failed pages, missing fields, or skipped products.
- Do not assume all suppliers behave the same.
- Do not scrape aggressively. Use reasonable pacing and respect site limits.

## Immediate Next Steps For The New Codex Project

1. Create or use a separate repo/project named `leaf-ledger-catalog-extraction`.
2. Copy the `catalog-extraction/` folder into that repo.
3. Move `.github/workflows/catalog-extraction.yml` into the new repo's `.github/workflows/` folder.
4. Install dependencies locally.
5. Run the American Best example config with a small limit.
6. Adjust selectors based on the actual site.
7. Export 25 products.
8. Validate the CSV with `scripts/validate_export.py`.
9. Report what fields are complete, missing, blocked, or require credentials.
10. Once the proof works, scale American Best to the full catalog.

## Final Goal

This project should produce reliable supplier catalog files.

Leaf & Ledger then imports those files and becomes the central place where the business searches, organizes, quotes, purchases, and uses products.
