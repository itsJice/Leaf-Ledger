# Leaf & Ledger Catalog Data Strategy

This document records the source-first catalog strategy and the boundary between Leaf & Ledger's stable import responsibilities and optional extraction tooling.

## Decision

Leaf & Ledger is not primarily a scraping product. It is the catalog system of record for a design operations team.

Its job is to receive supplier product data, standardize it, organize it, and make it useful inside product search, favorites, projects, recipes, quotes, invoices, and mockups.

Scraping is an extraction method, not the core app function.

## System Boundary

The clean workflow is:

```text
Supplier websites, PDFs, CSVs, XLSX files, online catalogs, or portals
  -> external extraction process
  -> standardized spreadsheet or JSON export
  -> Leaf & Ledger catalog intake
  -> Product Library
  -> projects, purchasing, quotes, invoices, and mockups
```

Leaf & Ledger should be excellent at everything after the data arrives.

## What Leaf & Ledger Owns

- Supplier records and contacts.
- Product Library storage.
- Catalog file intake.
- Spreadsheet/CSV/XLSX/PDF import.
- External scrape export import.
- Field mapping into the standard product model.
- Duplicate detection by supplier and SKU.
- Missing-field detection.
- Category normalization.
- Image storage and display.
- Source tracking: supplier, source file, source URL, season, imported date.
- Import history.
- Review queue for incomplete or low-confidence rows.
- Seasonal comparison: new, removed, changed, price changed.
- Product use in favorites, projects, recipe builders, purchasing, quotes, invoices, and mockups.

## What Leaf & Ledger Does Not Need To Own By Default

- Universal website scraping.
- Proxy management.
- Bot detection bypass.
- CAPTCHA handling.
- Long-running browser automation across every supplier.
- Every supplier's login/session quirks.
- Scraper hosting as a core user workflow.

Those may exist as external tools, scripts, or fallback utilities, but they should not define the app.

## Data Acquisition Priority

Use the cheapest and cleanest source first:

1. Supplier-provided CSV/XLSX/API/product feed.
2. Supplier price book, item master, Shopify export, FTP feed, or ERP export.
3. Supplier PDF/catalog file parsed into rows.
4. External scrape export produced by Crawlee, SeleniumBase, Apify, ScrapingBee, Bright Data, a contractor, or another extraction tool.
5. In-app portal extraction fallback for the few suppliers where it is already proven useful.
6. Manual cleanup into the standard spreadsheet format.

The goal is not to scrape everything. The goal is to get one reliable catalog export per supplier per season.

## Standard Import Contract

Every acquisition method should produce the same general shape:

```text
supplier
season
sku
product_name
category
subcategory
description
price
uom
moq
box_quantity
case_quantity
dimensions
weight
color
material
availability
product_url
image_url
source_url
source_file
scraped_at_or_exported_at
notes
```

Leaf & Ledger can accept more fields, but these are the core columns that make imported products useful.

## Scraper Role

Scrapers should be treated as external catalog-export generators.

Their job is simple:

```text
Go to the supplier website or portal.
Collect all product rows and associated fields.
Export an organized spreadsheet or JSON file.
Stop.
```

They do not need to directly mutate the Product Library. They should produce a file that Leaf & Ledger can import and validate.

## Recommended Extraction Stack

Use the least complex tool that works for a supplier:

- Simple public catalog: Crawlee, Playwright, Scrapy, or direct HTTP/API extraction.
- Login-heavy or bot-detection-heavy site: SeleniumBase CDP Mode.
- Blocked or proxy-heavy site: Bright Data, ScrapingBee, or Apify.
- Supplier file/PDF available: skip scraping and import/parse the file.

This keeps paid scraping and brittle browser automation reserved for the suppliers that actually require it.

## Seasonal Operating Model

The business only needs a full supplier catalog extraction at the beginning of each Christmas season, plus occasional updates if a supplier publishes a major price or availability change.

Therefore reliability means:

- The extraction can complete once per season.
- The export can be checked.
- Failed rows are visible.
- The same supplier can be rerun next season.
- Leaf & Ledger can compare this season to the prior season.

It does not require daily live sync for every supplier.

## Product Direction

The Suppliers page should prioritize:

1. Add supplier.
2. Track whether supplier data has been requested.
3. Upload catalog data.
4. Import and validate rows.
5. Review missing fields/images/prices.
6. See Product Library readiness.

Fallback extraction tools may remain available, but they should sit behind an advanced/fallback area.

## Success Criteria

The system is working when:

- Every important supplier has one current-season source file or export.
- Product Library has one active product per supplier SKU.
- Imported products show usable images and supplier pricing where available.
- Missing data is flagged instead of hidden.
- Designers can search and use products without visiting every supplier site.
- Seasonal refresh is a repeatable import/comparison process instead of a manual browsing project.
