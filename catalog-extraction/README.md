# Catalog Extraction Workspace

This folder is the optional external extraction workspace for producing validated Leaf & Ledger supplier catalog files.

It is intentionally portable and can be separated from the application when extraction needs an independent runtime or access boundary.

Leaf & Ledger should not become a universal scraping product. Scrapers here produce clean CSV/JSON exports. The app imports those exports through the standard catalog intake flow.

## What This Owns

- Log into supplier catalog sites when needed.
- Visit listing/category/product pages.
- Extract supplier product fields.
- Save organized exports under `outputs/`.
- Make one export per supplier per season.

See [Extraction Design Notes](EXTRACTION_DESIGN_NOTES.md) for the operating boundary and handoff standard.

## What Leaf & Ledger Owns

- Importing files.
- Normalizing rows.
- Deduping products.
- Tracking source batch, supplier, season, and review status.
- Displaying products in the Product Library and project workflows.

## Setup

```bash
cd catalog-extraction
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Install the browser driver used by SeleniumBase:

```bash
sbase install chromedriver
```

## Run A Supplier

Start with an example config:

```bash
python scripts/run_supplier.py --config suppliers/american_best.example.json --limit 25
```

If a supplier requires login, set environment variables before running:

```bash
export SUPPLIER_USERNAME="your-login"
export SUPPLIER_PASSWORD="your-password"
python scripts/run_supplier.py --config suppliers/american_best.example.json --limit 25 --headed
```

Exports are written to:

```text
outputs/{supplier_key}/{run_id}/products.csv
outputs/{supplier_key}/{run_id}/products.json
outputs/{supplier_key}/{run_id}/run_report.json
```

## GitHub Actions

The workflow at `.github/workflows/catalog-extraction.yml` can run this from GitHub manually. Add supplier credentials as repository secrets, then dispatch the workflow with a supplier config path and optional product limit.

Recommended secrets:

- `SUPPLIER_USERNAME`
- `SUPPLIER_PASSWORD`

For suppliers with different credential names, create supplier-specific secrets and map them in the workflow before running.

## Recommended Repo Split

Best long-term setup:

- `leaf-and-ledger`: the app, catalog import, Product Library, projects, quotes, invoices, and mockups.
- `leaf-ledger-catalog-extraction`: supplier scrapers, GitHub Actions runs, exported CSV/XLSX/JSON files, and scrape logs.

The extraction repo should never directly mutate the app database. Its output should be files that Leaf & Ledger imports.

To split this into a new repo later:

1. Copy this `catalog-extraction/` folder into a new project.
2. Move `.github/workflows/catalog-extraction.yml` into that repo's `.github/workflows/` folder.
3. Add supplier credentials as GitHub repository secrets.
4. Run a supplier smoke extraction with a small limit.
5. Download the generated artifact and import the CSV into Leaf & Ledger.

## Export Contract

Every export should include these columns when available:

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

Missing values are okay. Leaf & Ledger should flag them for review instead of silently dropping the product.

## Supplier Configs

Supplier configs live in `suppliers/`.

The starter runner is selector-based. It is meant to prove and export a catalog, not to handle every site forever. If a supplier needs custom pagination, XHR/API calls, or special login, copy the config and add a supplier-specific script instead of making the generic runner too clever.

## First Targets

Use this order:

1. American Best.
2. Allstate PDF/export comparison.
3. Regency or Accent as a known portal pattern.
4. Remaining suppliers by business priority.
