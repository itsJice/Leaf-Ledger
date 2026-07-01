# Regency Onboarding Notes

## Status

- Wave: 1
- Type: Product-heavy florals/decor
- Status: Expanded test import ready
- Scraper key: `regency`
- Dedupe: merge any duplicate Regency supplier records before onboarding.

## Current Interpretation

Regency is a useful proof that portal extraction can work, but it is fallback evidence, not the default future pattern. Before expanding Regency or using this approach elsewhere, first ask for a supplier export/price book or look for a usable catalog/PDF/external scrape export.

Keep the category and `get_products.php` notes for fallback extraction maintenance.

## Current Evidence

Last updated from user screenshots and pasted category/facet text on 2026-06-03.

- Site: `https://www.regency-rib.com`
- Recon report: [REGENCY_RECON_REPORT.md](REGENCY_RECON_REPORT.md)
- Login flow: `Sign In / Register` opens a page at `/cgi-regency-rib/sb/registration.cgi?...&func=2...`.
- Login fields: email address and password.
- Existing customer note: existing customers must sign up before they can log in and view pricing.
- Signed-in indicator: header changes from `Sign In / Register` to `My Account`, and pricing/cart state become visible.
- Public/signed-in navigation includes `Christmas`, `Home & Garden`, `Flowers & Foliage`, `Easter`, `Fall & Halloween`, `Clearance`, and `Locate a Sales Rep`.
- Category pages are `.html` paths, for example `christmas-collection.html`.
- Product detail pages are SKU `.html` paths, for example `MTX77830.html`.
- Product listing pages render placeholders server-side and load real product cards through `https://www.regency-rib.com/get_products.php`.
- Product-grid request shape: `skip=<offset>&pageType=products&pageId=<page id parsed from category HTML>`.
- Category pages can contain category/facet links that look SKU-like, for example `flowers-foliage-bushes_ss96.html`; these are not product details and must be ignored.

## Current App Status

Last verified in Leaf & Ledger on 2026-06-04.

- Regency supplier readiness: green.
- Imported products: 25 active Regency products.
- Standardized data: 25 of 25 have SKU, name, category, price, and UOM.
- Details/photos: 25 of 25 have detail payloads and displayable photos.
- Picture storage: 25 of 25 photos stored internally.
- Selected category cache: 6 categories, 60 product appearances; products overlap between categories, so unique imported product count is lower than category appearances.
- Verified path: 25-product controlled sync from `christmas-collection.html`, then Product Library import, then supplier image backfill.

## Catalog Structure Notes

Top-level menu groupings seen in screenshots:

- Christmas
  - Christmas Decor: Ornaments / Shatterproof, Table Top, Wall Art, Ribbon, Premades, Berries, Floral, Garlands/Wreaths, Natural Touch Greenery, Outdoor.
  - Christmas Greens (PVC): Trees, Garlands, Wreaths, Teardrops, Swags, Picks, Sprays & Stems, UV Greens / PVC.
  - Christmas 2026 Themes: All Tied Up, Autumn Warmth, Charleston, Christmas Greens PVC, Christmas Past, Cozy Christmas, Girls Trip, Glacier Ridge, Mermaid Fantasy, Oh What Fun, Peppermint Lane, Starlite, Vixen, Winter Warmth, Halloween Tricks, Valentine's Day.
  - Other Holidays: Independence Day, Mardi Gras, St. Patrick's Day.
- Home & Garden
  - Home Decor: Table Top, Premade Arrangements, Lanterns, Wall Art / Decor, Furniture, Baskets, Mats/Doormats, Clocks, Ribbon.
  - Garden: Planters / Containers, Fountains, Statuary.
  - General: Birds / Bugs, Fruit, Berries, UV Flowers / Foliage.
  - Spring 2026 Themes: American Spirit, Citrus Burst, Coastal Comforts, Easter Parade, Floral, Foliage Greenery, Hamptons Farm Stand, Regency Chocolatier, Statuary Pottery, Think Pink.
- Easter
  - Easter Decor, Tabletop, Wall Art, Ornaments, Picks, Sprays & Stems, Wreaths & Garlands.
- Fall & Halloween
  - Fall Decor, Halloween, Garlands, Wreaths, Table Top, Picks, Sprays & Stems.
- Flowers & Foliage
  - Foliage: Succulents / Cactus, Branches, Bushes, Trees / Topiaries, Potted / Premade, Orbs / Balls.
  - Flowers: Bouquets, Garlands, Wreaths, Stems, Bushes, Premade Arrangements.
- Clearance
  - Clearance, Promotions.

Facet groups seen on category/listing pages:

- Availability: `in stock`, `future ship date`.
- Shop by Department.
- Shop by Category.
- Shop by Size.
- Shop by Color.

The pasted category/facet text contains useful counts for Christmas, Home Decor, Christmas Greens, Fall Decor, Easter, Foliage, Garden, and Flower pages. Keep these as discovery hints, but live category discovery should use the site links/counts when credentials pass.

## Product Detail Data Contract

Example product: `https://www.regency-rib.com/MTX77830.html`

Observed fields:

- Name: `4" GLS SMILAX BEADED BALL ORNAMENT 3/AST`
- SKU: `MTX77830`
- Source price label: `As low as: $3.91`
- Tier pricing table:
  - quantity bands: `6 - 23`, `24 - 47`, `48 - 239`, `240+`
  - prices: `$5.53`, `$4.68`, `$4.25`, `$3.91`
- UOM: `PC`
- BOX: `6`
- CARTON: `48`
- Style row:
  - style: `CINNAMON SPICE`
  - current quantity: `0`
  - future quantity: `690`
  - future ship date: `8/19/2026`
- Minimum order copy:
  - `Minimum order amount: 6 PC`
  - `Must be ordered in multiples of: 6 PC`
- Product image and thumbnail gallery are visible.

Normalization notes:

- Use lowest tier/current `as low as` price as `current_price`, but preserve the full tier table in `raw_data.price_tiers`.
- Map `UOM: PC` to Leaf & Ledger unit `each`, while preserving `raw_data.UOM = "PC"`.
- Map `BOX` to `box_qty` and `CARTON` to `case_qty`.
- Map minimum order amount to `moq`.
- Preserve style inventory rows in `raw_data.style_inventory`.
- Availability should be `future ship date`/`eta` when current quantity is 0 and future quantity/date are present, with the exact future date in `availability_note`.
- Preserve source category, department, color, size, and all filters/facets in raw data when available.

## Fallback Portal Working Plan

This plan is for Regency portal extraction only. Before using it for a new season or copying it to another supplier, first try a supplier export, price book, PDF catalog, external scrape export, or cleaned spreadsheet.

1. Clean supplier record.
   - Supplier should use `scraper_key = regency`.
   - Store credentials in the app only.
2. Configure Catalog.
   - Log in with email/password.
   - Discover top-level and submenu category links from the signed-in homepage/menu.
   - Cache category URLs and counts.
3. Small test scrape.
   - Start with one category, likely `christmas-collection.html`, and a small product limit.
   - Confirm product cards expose detail URLs, SKU, name, image, and price.
4. Product detail parser.
   - Capture SKU, name, image URLs, tier prices, UOM, box/carton, MOQ/multiples, style inventory, current/future quantities, future ship dates, category/facet context.
5. Import and verify.
   - Import a small preview set.
   - Confirm Product Library search by SKU, product name, category, color, size, style, and availability.
   - Confirm Builder can select Regency items with correct supplier, SKU, UOM, price, quantity, and cost.
6. Full catalog.
   - Expand selected categories gradually after preview/import looks correct.

The target business outcome is a reliable Regency catalog import in Product Library. Portal extraction is one possible source, not the product boundary.

## Notes

- Use [SUPPLIER_ONBOARDING_CHECKLIST.md](SUPPLIER_ONBOARDING_CHECKLIST.md).
- Preserve supplier-specific fields in `raw_data`.
- Do not store credentials in GitHub.
