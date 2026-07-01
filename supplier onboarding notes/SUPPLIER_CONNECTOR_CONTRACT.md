# Supplier Connector Contract

This contract defines the stable normalized product shape that file imports and optional supplier-specific extractors must produce.

## Goal

Every supplier can format data differently, but Leaf & Ledger should receive one predictable product shape. Supplier-specific details should be preserved in structured raw data, not thrown away.

Leaf & Ledger is the recipient and system of record for this data. The data may come from a supplier CSV/XLSX export, supplier API/feed, PDF parser, external scraper, contractor-created spreadsheet, or the app's legacy portal extraction tools.

The extraction method is replaceable. The import contract is not.

## Source Priority

Use the cleanest source first:

1. Supplier-provided CSV/XLSX/API/product feed.
2. Supplier price book, item master, dealer export, Shopify export, FTP feed, or ERP export.
3. Supplier PDF/catalog parsed into rows.
4. External scrape export from Crawlee, SeleniumBase, Apify, ScrapingBee, Bright Data, or another extraction process.
5. In-app portal extraction only when no better source exists.
6. Manual cleanup into the standard spreadsheet format.

The preferred output is one spreadsheet or JSON file per supplier per season.

## Required Normalized Fields

Each import source should provide these fields when the supplier provides them:

- `supplier_sku`
- `name`
- `description`
- `category`
- `product_type`
- `current_price`
- `source_price_label`
- `uom`
- `minimum_quantity`
- `box_quantity`
- `case_quantity`
- `availability`
- `photo_url`
- `upc`
- `color`
- `color_words`
- `dimensions`
- `weight`
- `box_dimensions`
- `box_weight`
- `case_dimensions`
- `case_weight`
- `country_of_origin`
- `material_breakdown`
- `raw_data`

## Recommended Spreadsheet Columns

External extraction tools and manual cleanup should target these column names where possible:

- `supplier`
- `season`
- `sku`
- `product_name`
- `category`
- `subcategory`
- `description`
- `price`
- `uom`
- `moq`
- `box_quantity`
- `case_quantity`
- `dimensions`
- `weight`
- `color`
- `material`
- `availability`
- `product_url`
- `image_url`
- `source_url`
- `source_file`
- `exported_at`
- `notes`

## Pricing Rules

- Supplier source pricing is truth.
- Display pricing exactly as the supplier gives it.
- Do not calculate per-piece, per-branch, per-bundle, or per-case pricing unless the supplier explicitly gives that number.
- Store supplier-specific price labels in `source_price_label` or `raw_data`.
- Treat supplier price as our starting product cost, not the customer price.
- Customer price, gross profit, and profit margin belong to the quote/build/order layer after selected quantities and markup rules are known.
- Do not save a calculated customer price back into supplier product fields.

## Cost And Margin Output

Any process that turns supplier products into a client-facing build, quote, order, or invoice should end with these values:

- `our_cost`: selected supplier product cost multiplied by selected quantity, plus known landed-cost adjustments.
- `customer_price`: the price shown to the customer from quote rules or approved markup settings.
- `gross_profit`: `customer_price - our_cost`.
- `profit_margin_percent`: `gross_profit / customer_price`.
- `markup_percent`: `gross_profit / our_cost`, when useful.
- `pricing_status`: `complete`, `estimate`, or `missing_inputs`.
- `missing_pricing_inputs`: plain-language list of missing values, such as supplier cost, quantity, freight, labor, markup rule, or customer price.

The UI should show these values at the end of each pricing process before the user finalizes the workflow.

## Import And Extraction Interface

External scrapers should produce a CSV/XLSX/JSON export in the normalized shape above. Their job is to visit supplier sources, collect product rows, and stop at a file export.

When the app keeps a portal extractor for a supplier, it may still support:

```text
discover_{supplier_key}_catalog(username, password, on_progress, supplier_id)
scrape_{supplier_key}(username, password, max_products, on_progress, subcategories, supplier_id)
```

Discovery should return:

```json
{
  "subcategories": [
    {
      "label": "Category name",
      "slug": "supplier category code or URL",
      "section": "optional grouping",
      "item_count": 0
    }
  ],
  "total_products": 0
}
```

Portal extraction should yield one normalized product at a time so progress can update while the run continues. This is a fallback path, not the default contract for every supplier.

## Category Rules

- For file/import sources, the uploaded export is the source of truth.
- For portal extraction fallback, saved catalog selection is the source of truth.
- If no portal categories are selected, the UI must clearly show that the supplier is set to extract all categories.
- Portal category structure should be cached after discovery so future fallback runs do not waste time rediscovering known pages.

## Import Rules

- 100% import means every usable product row from the source file/export creates or updates exactly one product row.
- Images and deep details may backfill after import.
- Failed images/details must be marked pending or retry-needed.
- Never silently drop failed enrichment.
- Enforce no duplicate active SKUs per supplier.
- Preserve source traceability: source file/export, source URL, product URL, season/year, and import date when known.
- Rows with missing SKU/name/price/image/category should be visible in review instead of hidden.

## UI Rules

- Product Library uses Leaf & Ledger's clean standardized layout.
- Common fields show first.
- Supplier-specific fields appear under structured supplier details.
- Missing images show `Image pending` or `Image retry needed`.
- Search should work by natural words, supplier SKU, color words, size/dimensions, category, supplier, UPC, availability, and country.
