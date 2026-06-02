# Supplier Connector Contract

## Goal

Every supplier can format data differently, but Leaf & Ledger should receive one predictable product shape. Supplier-specific details should be preserved in structured raw data, not thrown away.

## Required Normalized Fields

Each scraper should return these fields when the supplier provides them:

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

## Pricing Rules

- Supplier source pricing is truth.
- Display pricing exactly as the supplier gives it.
- Do not calculate per-piece, per-branch, per-bundle, or per-case pricing unless the supplier explicitly gives that number.
- Store supplier-specific price labels in `source_price_label` or `raw_data`.

## Scraper Interface

Each scraper should support:

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

Scrape should yield one normalized product at a time so progress can update while the run continues.

## Category Rules

- Saved catalog selection is the source of truth.
- If no categories are selected, the UI must clearly show that the supplier is set to scrape all categories.
- Category structure should be cached after discovery so future runs do not waste time rediscovering known pages.

## Import Rules

- 100% import means every discovered product row creates or updates exactly one product row.
- Images and deep details may backfill after import.
- Failed images/details must be marked pending or retry-needed.
- Never silently drop failed enrichment.
- Enforce no duplicate active SKUs per supplier.

## UI Rules

- Product Library uses Leaf & Ledger's clean standardized layout.
- Common fields show first.
- Supplier-specific fields appear under structured supplier details.
- Missing images show `Image pending` or `Image retry needed`.
- Search should work by natural words, supplier SKU, color words, size/dimensions, category, supplier, UPC, availability, and country.

