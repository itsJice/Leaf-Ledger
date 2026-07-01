# Supplier Crawl Queue And Worker Plan

This architecture note preserves a fallback design for queued portal extraction while keeping file-based catalog intake as the default product path.

## Current Status

This is a fallback architecture note, not the default product roadmap.

Leaf & Ledger's primary responsibility is to import and organize supplier catalog data after it has been extracted into a file/export. The default path is:

```text
supplier export / PDF / external scrape export / cleaned spreadsheet
  -> Leaf & Ledger catalog intake
  -> Product Library
```

Build a crawl queue only if too many important suppliers cannot provide usable files or external scrape exports.

Canonical strategy: [../CATALOG_DATA_STRATEGY.md](../CATALOG_DATA_STRATEGY.md)

## When To Use This Plan

Use this plan only when all of these are true:

- The supplier cannot provide CSV/XLSX/API/feed data.
- PDF/catalog parsing is incomplete or unavailable.
- A one-off external scrape export is not sufficient.
- The supplier must be extracted from a website or portal.
- The extraction needs resumable, repeatable seasonal runs.

If those conditions are not true, do not build queue-worker infrastructure.

## Purpose

For portal-only suppliers, a queue-backed crawler can make extraction safer:

- resumable progress,
- no duplicate product work,
- controlled concurrency,
- retryable failures,
- reviewable missing fields,
- clear run audit,
- exportable final dataset.

The output should still be treated as a catalog export that Leaf & Ledger imports and validates.

## Target Output

The crawler should produce:

```text
supplier_YYYY_catalog.csv
supplier_YYYY_catalog.xlsx
supplier_YYYY_catalog.json
```

with the standard import columns from [SUPPLIER_CONNECTOR_CONTRACT.md](SUPPLIER_CONNECTOR_CONTRACT.md).

Direct database mutation should be avoided unless the output also remains exportable and auditable.

## Core Design

### 1. Discovery Queue

Catalog discovery saves product candidates before product detail extraction.

Each candidate should include:

- supplier id,
- source category URL,
- category path/tags,
- product detail URL when known,
- supplier SKU when known,
- listing title/image/price hints when available,
- status,
- retry count,
- last error,
- timestamps.

Counting duplicate category appearances is acceptable for planning, but product output should dedupe by supplier plus SKU or stable detail URL.

### 2. Atomic Claiming

Workers should not each build stale lists of imported SKUs.

Instead, workers ask the database or local queue store for the next pending rows. The queue marks those rows as claimed in the same transaction.

Statuses:

- `pending`
- `claimed`
- `extracted`
- `exported`
- `failed`
- `skipped`

### 3. Detail Workers

Use controlled worker counts per supplier. Start low.

Each worker should:

- fetch one claimed product detail,
- parse supplier-specific raw data,
- normalize into the standard product contract,
- save the parsed payload,
- mark the row `extracted`,
- increment retry count and release/fail the row if a network or parser error occurs.

If supplier errors spike, reduce concurrency and increase delay.

### 4. Export Worker

The export worker writes normalized rows to CSV/XLSX/JSON.

Rules:

- one row per supplier SKU when possible,
- preserve category tags,
- preserve raw supplier data,
- record missing price/UOM/image/category issues,
- keep source URL and source category references,
- produce an audit summary.

### 5. Image Handling

Image handling should support both URLs and downloaded files.

Each image row should include:

- source image URL,
- product SKU,
- public accessibility status,
- download/storage status,
- retry count,
- last error.

Default image policy:

- If the image URL loads publicly, keep the URL and let Leaf & Ledger decide whether to store a copy.
- If the image requires login/cookies or blocks backend access, download/store a durable copy during extraction.
- If image extraction fails, export the product row with an image review flag rather than dropping the row.

## UI Requirements If Built In-App

If this fallback queue is exposed inside Leaf & Ledger, the UI must clearly label it as fallback portal extraction.

Show:

- run status,
- source type,
- selected categories,
- discovered candidates,
- extracted rows,
- exported rows,
- failed rows,
- skipped rows,
- retryable failures,
- current worker count,
- last error,
- export file location.

Useful controls:

- Start fallback extraction.
- Pause.
- Resume.
- Stop after current claims finish.
- Retry failed rows.
- Export failure report.

## Run Modes

Keep run modes conservative:

- `recon`: inspect structure and counts only.
- `proof`: export 10-25 products.
- `sample`: export 100-500 products.
- `full`: continue until selected catalog is done.
- `refresh`: update existing SKUs/prices/availability only.
- `repair`: retry failed rows and missing images only.

## Failure Buckets

Bucket failures into:

- network retry,
- supplier server error,
- login/session expired,
- parser missing SKU,
- parser missing price,
- image missing,
- image blocked,
- duplicate/merged,
- intentionally skipped.

Failures should become review rows or export notes, not silent drops.

## Run Audit Log

Each run should leave a plain audit trail:

- start/stop time,
- run mode,
- source URLs/categories,
- worker settings,
- products discovered,
- products exported,
- products failed,
- images downloaded,
- final completeness summary.

## Open Decisions

- Whether this queue belongs inside Leaf & Ledger or in an external scraper repo.
- Whether output should be imported automatically or manually uploaded after review.
- Whether queue rows should be keyed first by detail URL or SKU when both are not known during discovery.
- How many concurrent workers to allow per supplier by default.
- Whether image downloads should start during extraction or after file import.

## Decision Rule

Before building this, ask:

```text
Can we get a supplier export, PDF parse, or one-off external scrape export instead?
```

If yes, use that path.

If no, this queue plan is the fallback architecture.
