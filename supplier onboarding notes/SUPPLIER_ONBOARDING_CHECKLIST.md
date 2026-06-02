# Supplier Onboarding Checklist

Use this checklist for each supplier before moving to the next one.

## Setup

- [ ] Confirm supplier has one clean record.
- [ ] Confirm duplicate supplier names are merged.
- [ ] Confirm `scraper_key`.
- [ ] Add credentials in the app only.
- [ ] Do not store credentials, API keys, `.env` files, or passwords in GitHub.
- [ ] Create or update this supplier's onboarding note.

## Discovery

- [ ] Confirm login URL.
- [ ] Test login.
- [ ] Identify category page structure.
- [ ] Identify category IDs, slugs, or URLs.
- [ ] Identify item counts if supplier displays them.
- [ ] Cache category structure.
- [ ] Confirm Configure Catalog shows the category list.

## Small Test Run

- [ ] Select one small category.
- [ ] Scrape selected category.
- [ ] Confirm preview count matches expected supplier count.
- [ ] Confirm preview fields include SKU, name, description, price, UOM, category, and image URL when available.
- [ ] Import previewed products.
- [ ] Confirm imported rows appear in Product Library.

## Full Selected Run

- [ ] Select desired categories.
- [ ] Scrape selected categories.
- [ ] Confirm progress shows total vs collected.
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

## Done Criteria

- [ ] Selected categories scrape correctly.
- [ ] 100% of discovered rows are imported.
- [ ] Duplicate active SKUs are zero.
- [ ] Pricing is exact supplier pricing.
- [ ] Images/details are complete or explicitly retry-needed.
- [ ] Search and filters work.
- [ ] Notes file is updated with lessons learned.

