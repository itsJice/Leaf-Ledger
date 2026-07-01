# Regency Recon Report

## Run

- Date: 2026-06-05
- Recon command: `.venv/bin/python -m app.libs.supplier_onboarding.recon_cli https://www.regency-rib.com/christmas-collection.html`
- Start URL: `https://www.regency-rib.com/christmas-collection.html`
- Final URL: `https://www.regency-rib.com/christmas-collection.html`
- Status: `200`
- Page title: `Christmas`
- Sitemap: `https://www.regency-rib.com/sitemap.xml`
- Sitemap status: `404`

## Classification

- Difficulty rank: `A`
- Likely strategy: `http_xhr`
- Key signal: `storefront_product_grid: pageId/pageType variables`

Regency category pages expose Storefront variables such as `pageId` and `pageType = "products"`. The product cards are loaded through the supplier's product-grid endpoint rather than being present as normal product links in the first category HTML response.

## Useful Category Candidates

- `Christmas Decor` -> `https://www.regency-rib.com/christmas-collection.html`
- `Ornaments / Shatterproof` -> `https://www.regency-rib.com/christmas-decor-ornaments.html`
- `Table Top` -> `https://www.regency-rib.com/christmas-decor-table-top.html`
- `Wall Art` -> `https://www.regency-rib.com/christmas-decor-wall-art.html`
- `Ribbon` -> `https://www.regency-rib.com/christmas-decor-ribbon.html`
- `Premades` -> `https://www.regency-rib.com/christmas-decor-premades.html`
- `Christmas Greens (PVC)` -> `https://www.regency-rib.com/trees-greenery.html`
- `Trees` -> `https://www.regency-rib.com/christmas-greens-trees.html`
- `Garlands` -> `https://www.regency-rib.com/christmas-greens-garlands.html`
- `Wreaths` -> `https://www.regency-rib.com/christmas-greens-wreaths.html`

## Forms Found

- Search form: `https://www.regency-rib.com/search.html`
- Mailing list form: Mailchimp subscribe endpoint
- Registration form: `https://www.regency-rib.com/cgi-regency-rib/sb/registration.cgi`

## Parser Notes

- Do not treat `_ss` category/facet URLs as product detail URLs.
- Do not expect product links in the initial category page HTML.
- Use category `pageId` plus `pageType` to request product-grid data.
- Preserve supplier-specific price tiers, UOM, box/carton quantities, MOQ, style inventory, current quantity, future quantity, and future ship date in `raw_data`.

## Follow-Up

- Regency already has a working scraper and 25-product proof import.
- Use this report as the reference packet format for the next Wave 1 supplier.
