# Supplier Onboarding Acceleration Plan

## Current Status

This plan has been updated for the new product boundary:

Leaf & Ledger is the catalog system of record. It should receive supplier data from supplier exports, PDFs, external scrape exports, or cleaned spreadsheets before we build or run portal scrapers.

The old scraper-first acceleration plan is no longer the default roadmap. Scraper adapters, Crawlee, queue workers, SeleniumBase, and portal automation are fallback tools for suppliers that cannot provide usable data another way.

Canonical strategy: [../CATALOG_DATA_STRATEGY.md](../CATALOG_DATA_STRATEGY.md)

## Purpose

Accelerate supplier onboarding by reducing the work to one question first:

```text
What is the cleanest way to get this supplier's product catalog into a spreadsheet or JSON export?
```

Only after that question fails should we spend time on portal scraping.

## Source-First Onboarding Process

### 1. Request The Best Source

Ask every supplier for one of these before coding:

- CSV catalog export.
- XLSX price book.
- Item master.
- Dealer price list.
- Shopify export.
- API access.
- FTP/product feed.
- Full catalog PDF.
- Image export or image URL list.

The request should include: SKU, product name, category, description, wholesale/account price, UOM, MOQ, case quantity, box quantity, dimensions, weight, availability, product URL, and image URLs/files.

### 2. Classify The Supplier Source

Use these source classes:

| Rank | Source | Default action |
| --- | --- | --- |
| A | Supplier CSV/XLSX/API/feed | Import directly after field mapping |
| B | Supplier PDF/catalog with readable product rows | Parse PDF, then review rows |
| C | External scrape export from Crawlee/SeleniumBase/Apify/etc. | Import export, review completeness |
| D | Portal-only supplier with login required | Use fallback portal extraction |
| E | Blocked/captcha/no access/no clean source | Needs business decision or supplier request |

### 3. Normalize Into The Import Contract

Every source should become the standard import shape defined in [SUPPLIER_CONNECTOR_CONTRACT.md](SUPPLIER_CONNECTOR_CONTRACT.md).

The preferred output is one file per supplier per season:

```text
supplier_2026_catalog.xlsx
supplier_2026_catalog.csv
supplier_2026_catalog.json
```

### 4. Import A Small Sample

Before a full import:

- Upload a small sample.
- Confirm SKU/name/category/price/UOM/MOQ/image fields.
- Confirm duplicate behavior.
- Confirm Product Library display.
- Confirm missing fields are visible as review items.

### 5. Import The Full Source

Once the sample looks right:

- Upload/import the full source file.
- Review row counts.
- Import all usable rows.
- Preserve source traceability.
- Backfill images/details when needed.
- Verify Product Library search and project use.

### 6. Document The Refresh Path

Each supplier note should state:

- Best source type.
- Who provides the data.
- Where the file/export came from.
- Season/year.
- Import row count.
- Missing fields.
- Image completeness.
- Whether scraping is required next season.
- Next refresh steps.

## Fallback Portal Extraction

Use portal extraction only when supplier files/PDFs/exports are unavailable or incomplete.

Fallback extraction may use:

- Existing in-app supplier scraper endpoints.
- Crawlee.
- Playwright.
- SeleniumBase CDP Mode.
- Apify.
- ScrapingBee.
- Bright Data.
- Contractor-created scrape exports.

The scraper's job is not to become part of the app's core product. Its job is to produce an organized spreadsheet or JSON export that Leaf & Ledger can import.

## What Not To Build By Default

Do not default to:

- One universal website scraper.
- A full crawl queue system for every supplier.
- Proxy/CAPTCHA infrastructure inside Leaf & Ledger.
- Daily live sync across all suppliers.
- Supplier-specific browser automation before asking for files.

Those are fallback investments, not the first move.

## When A Shared Crawl Engine Is Still Useful

A shared crawl engine may still be worth building if:

- Multiple important suppliers refuse exports.
- Online catalogs are the only complete source.
- External tools are too expensive or unreliable.
- We need repeatable seasonal scraping for many portal-only suppliers.

If that happens, use [SUPPLIER_CRAWL_QUEUE_WORKER_PLAN.md](SUPPLIER_CRAWL_QUEUE_WORKER_PLAN.md) as a fallback architecture, not as the default roadmap.

## Success Metrics

- Every important supplier has a current-season source file/export.
- Easy suppliers import without scraper code.
- Portal scraping is reserved for true fallback cases.
- Product Library has one active product per supplier SKU.
- Missing prices, images, MOQs, categories, or dimensions are visible as review work.
- Supplier refresh is repeatable next season.
- Product data can be used in projects, purchasing, quotes, invoices, and mockups without visiting every supplier site.
