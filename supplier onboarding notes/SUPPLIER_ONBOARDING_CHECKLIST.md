# Supplier Onboarding Checklist

Use this checklist for each supplier before moving to the next one.

## Operating Principle

Supplier onboarding starts by getting a usable catalog source, not by building a scraper.

Preferred path:

```text
supplier export / PDF / external scrape export / cleaned spreadsheet
  -> Leaf & Ledger import
  -> Product Library review
```

Portal scraping is a fallback when the supplier cannot provide a usable source file or export.

## Setup

- [ ] Confirm supplier has one clean record.
- [ ] Confirm duplicate supplier names are merged.
- [ ] Confirm best data source: supplier export, PDF/catalog, external scrape export, portal extraction, or manual cleanup.
- [ ] Confirm `scraper_key` only if portal extraction is required.
- [ ] Add credentials in the app only when portal extraction is required.
- [ ] Do not store credentials, API keys, `.env` files, or passwords in GitHub.
- [ ] Create or update this supplier's onboarding note.

## Supplier Intake Packet

Collect this before building any supplier-specific extraction. The best input is a supplier-provided file or export. URLs/screenshots are fallback evidence for external or portal extraction.

- [ ] Supplier site URL.
- [ ] Login URL.
- [ ] Ask supplier for a full catalog export, price book, item master, product feed, Shopify export, API/FTP feed, or CSV/XLSX.
- [ ] Save any supplier-provided files outside GitHub and import through the app.
- [ ] Confirm whether supplier data includes account/preferred pricing.
- [ ] Confirm credentials are saved in the app only if portal extraction is needed.
- [ ] If scraping is needed, provide every top-level catalog/category URL that should count toward the initial catalog estimate.
- [ ] If scraping is needed, provide 3-5 product detail URLs from different category types.
- [ ] If scraping is needed, provide one listing URL that shows a large count and one listing URL that shows a small count.
- [ ] Note the visible total item count for important listing pages or source files.
- [ ] Note whether initial count can include duplicates across categories.
- [ ] Note whether duplicate products should be stored once and tagged under every category path.
- [ ] Note any categories that should be excluded from first import.
- [ ] Add screenshots of homepage navigation, category listing, product card/listing row, product detail, price/stock area, and variant/option area when available.
- [ ] Note if pages use filters such as available/in stock, sort mode, pagination, load more, or search.
- [ ] Note any unusual fields: MOQ, box qty, case qty, UOM, tier pricing, future stock dates, variants, color/size choices, or account-only pricing.
- [ ] Note any known access issues, captchas, account approval gates, or pages that only work after login.

## Source Discovery

- [ ] Confirm source type: supplier file, PDF/catalog, external scrape export, portal extraction, or manual cleanup.
- [ ] Confirm the source can produce one row per product.
- [ ] Confirm the source includes SKU and product name.
- [ ] Confirm whether the source includes price, UOM, MOQ, case quantity, image URL/file, category, and product URL.
- [ ] If portal extraction is required, confirm login URL.
- [ ] If portal extraction is required, test login.
- [ ] If portal extraction is required, confirm signed-in account/preferred pricing is visible.
- [ ] If portal extraction is required, identify and cache category page structure.
- [ ] If portal extraction is required, confirm fallback Configure Portal shows the category list.

## Small Import Test

- [ ] Select one small category.
- [ ] Export or upload a small source sample.
- [ ] Confirm preview count matches expected supplier count.
- [ ] Confirm preview fields include SKU, name, description, price, UOM, category, and image URL when available.
- [ ] Confirm prices came from the authenticated session, not a public catalog page.
- [ ] Import previewed products.
- [ ] Confirm imported rows appear in Product Library.

## Full Source Import

- [ ] Upload/import the full supplier source file or external scrape export.
- [ ] If portal extraction is required, select desired categories.
- [ ] If portal extraction is required, extract selected categories.
- [ ] Confirm progress shows total vs collected/imported.
- [ ] Confirm preview count matches selected category total.
- [ ] Import 100% of discovered rows.
- [ ] Confirm no duplicate active SKUs.

## Image And Detail Backfill

- [ ] Run image/detail backfill.
- [ ] Confirm stored image count increases.
- [ ] Confirm details enriched count increases.
- [ ] Confirm failed images/details are marked retry-needed.
- [ ] Confirm resume/retry works.

## Product Library Verification

- [ ] Search by SKU.
- [ ] Search by product name.
- [ ] Search by plain language color.
- [ ] Search by size/dimension.
- [ ] Search by category.
- [ ] Search by supplier.
- [ ] Open a product card.
- [ ] Confirm expanded product details show supplier fields.
- [ ] Confirm price and UOM match source.
- [ ] Confirm images render or show retry-needed.

## Cost, Price, And Profit Verification

- [ ] Confirm supplier price is treated as our starting product cost.
- [ ] Add at least one imported product to a builder/project bucket.
- [ ] Mark the product selected so it affects quote math.
- [ ] Confirm selected quantity is included in our cost.
- [ ] Confirm customer price comes from project quote rules or approved markup settings.
- [ ] Confirm the process-end summary shows our cost, customer price, gross profit, and profit margin.
- [ ] Confirm profit margin uses `gross profit / customer price`.
- [ ] Confirm markup, if shown, uses `gross profit / our cost` and is not mislabeled as margin.
- [ ] Confirm missing supplier cost, quantity, freight, labor, markup rule, or customer price appears as a missing input instead of a fake margin.

## Done Criteria

- [ ] Current-season supplier source file/export is saved or documented.
- [ ] 100% of usable source rows are imported.
- [ ] Duplicate active SKUs are zero.
- [ ] Pricing is exact supplier pricing.
- [ ] Pricing reflects our account/preferred pricing when the source provides it.
- [ ] Images/details are complete or explicitly retry-needed.
- [ ] Missing fields are marked for review.
- [ ] Search and filters work.
- [ ] Builder/project pricing summary shows our cost, customer price, gross profit, and profit margin when pricing inputs are complete.
- [ ] Notes file is updated with lessons learned.
