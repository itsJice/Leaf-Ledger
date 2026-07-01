# Vickerman Recon Report

## Run

- Date: 2026-06-06
- Recon command: `.venv/bin/python -m app.libs.supplier_onboarding.recon_cli https://www.vickerman.com/`
- Start URL: `https://www.vickerman.com/`
- Final URL: `https://www.vickerman.com/`
- Status: `200`
- Page title: `Artificial Christmas Trees, Ornaments and Home Decor`
- Sitemap: `https://www.vickerman.com/sitemap.xml`
- Sitemap status: `200`

## Classification

- Difficulty rank: `A/B`
- Likely strategy: `logged-in HTTP session + product-selector POST`
- Login URL: `https://www.vickerman.com/Users/Account/LogOn`
- Product selector endpoint: `https://www.vickerman.com/April.Vickerman.Commerce/ProductSelector/DoSearch`

Vickerman category navigation is available in static HTML. Category product rows are loaded by posting `product_type`, `page_indx`, `sort`, and the request verification token to the product selector endpoint. Product detail pages include an embedded `var model = {...}` JSON object that contains the normalized product payload and account-specific pricing after login.

## Proof Result

- Supplier id: `9`
- Scraper key: `vickerman`
- Credentials: passed catalog discovery
- Categories cached: `66`
- Estimated category listings: `6,947`
- Confirmed count method: read `Total items found` from each product-selector category page and add the counts.
- Count caveat: category totals are product-selector listings/groups, not guaranteed final unique sellable SKU count.
- Variant caveat: detail pages can expose additional `ProductOptions` rows. A full Vickerman SKU import should expand unique `CurrentItem.ItemNumber` plus unique `ProductOptions[].ItemNumber`.
- Proof scrape job: `45`
- Proof products scraped/imported: `25`
- Standardized products: `25 of 25`
- Detail payloads: `25 of 25`
- Displayable photos: `25 of 25`
- Stored photos: `25 of 25`
- Final readiness: all checklist steps green for the proof set

## Useful Category Candidates

- `Christmas Trees › Colorful Trees` -> `https://www.vickerman.com/productselector/christmas-trees/colorful-trees?sort=group`
- `Christmas Trees › Flocked Trees` -> `https://www.vickerman.com/productselector/christmas-trees/flocked-trees?sort=group`
- `Christmas Trees › Green Trees` -> `https://www.vickerman.com/productselector/christmas-trees/green-trees?sort=group`
- `Wreaths › Green Wreaths` -> `https://www.vickerman.com/productselector/wreaths/green-wreaths`
- `Garland › Green Garlands` -> `https://www.vickerman.com/productselector/garland/green-garlands`
- `Textiles › Ribbons` -> `https://www.vickerman.com/productselector/textiles/ribbons`
- `Commercial Decor › Large Ornaments` -> `https://www.vickerman.com/productselector/commercial-decor/large-ornaments`
- `Natural Botanicals › Flowering` -> `https://www.vickerman.com/productselector/natural-botanicals/flowering`

## Parser Notes

- Use the logged-in `requests.Session`; price fields are null without a validated account session.
- Get `__RequestVerificationToken` from the category page before posting to `DoSearch`.
- Page index starts at `1`; `0` returns a server error.
- Parse `Total items found: N` and `page 1 of N` from selector HTML.
- Detail pages expose product fields in embedded `var model = {...}` before Vue renders.
- Do not treat the listing count as the final SKU count until variants are expanded.
- Preserve and expand `ProductOptions` because those rows can represent additional item numbers, prices, stock, images, dimensions, and variant labels.
- Preserve the full Vickerman model in `raw_data.vickerman_model`.
- Store image URLs from `ImageUrl` and `Image1Url` through `Image9Url`.

## Follow-Up

- Full catalog import is feasible.
- Before full import, decide whether to import all `66` cached categories or a selected subset.
- The proof run used 25 products; full category listing count is `6,947` before SKU-level variant expansion.
- Next scraper improvement: count and import unique variant SKUs from `ProductOptions`, not just the clicked/current detail item.
