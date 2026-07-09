---
name: leaf-ledger-catalog-scrape
description: >-
  Scrape a supplier/vendor's product catalog for Leaf & Ledger (the
  catalog-extraction workspace) into a full-detail Excel deliverable — real
  buyer prices, all images, descriptions, dimensions/UPC/variants. Use this
  WHENEVER the user wants to onboard a new supplier, "scrape"/"pull"/"extract"
  a vendor site or wholesale catalog, get a supplier's products/prices/images,
  add a vendor to the catalog, refresh a supplier feed, or hands over a supplier
  URL and/or trade-login credentials — even if they don't say the word "scrape."
  Also use for enriching an existing catalog with gated prices via a trade login.
  This is the standing recipe for that work; prefer it over ad-hoc scraping.
---

# Leaf & Ledger — Supplier Catalog Scrape

You are onboarding a supplier into Leaf & Ledger. The goal is a clean, importable
catalog with **full rich detail**, not a metadata stub. Work in the
`catalog-extraction/` workspace (the deliberately-separate "System B"; never wire
scrapers into the app backend).

## The one rule that matters most

**Full rich detail, every time.** Every pull must capture the **real buyer's
price** (the authenticated dealer/wholesale price, not MSRP/index/"list"), **all
images**, **full descriptions**, plus dimensions/weight/UPC/variants/stock when
the supplier exposes them. A pull missing prices or images is *incomplete*. If a
field is genuinely unobtainable (e.g. prices gated behind an account you don't
have), **say so explicitly, flag it in `needs_review`, and propose the alternate
source** — never silently ship a gap.

## Workflow (HTTP-first, platform-first)

Scraping is a platform-identification problem. Once you know the ecommerce
platform, the data channel and the recipe follow. Do this in order:

1. **Recon — identify the platform.** Fetch `robots.txt`, response headers, the
   homepage, and one product page. Grep for platform signatures (shopify,
   bigcommerce, woocommerce/wp-content, wix, squarespace, magento, ecwid,
   prestashop, volusion, opencart, mysimplestore, focuspoint, coldfusion/.cfm).
   Check `sitemap.xml`. For several unknown suppliers at once, **fan out one
   recon subagent per supplier in parallel** (much faster). Have each report:
   Site · Platform · Catalog size · Data channel (+URL) · Prices (public/gated +
   evidence) · Extraction method · Difficulty · Gotchas.

2. **Pick the data channel from the platform.** See the cheat sheet below and
   `references/platform-recipes.md` for the exact endpoints/parsers.

3. **Reuse before building.** Most platforms already have a runner or a
   generic module — see "Reuse map" below. Adding a supplier is often just a new
   config entry, not a new script.

4. **Smoke test on a few items first** (`--limit N` / a 1-category test) and
   verify SKU + **price** + image parse correctly *before* the full run. Assert
   any login is real by checking a value that should change (see login rule).

5. **Full run, checkpointed.** Runners write resumable NDJSON so a crash resumes.
   Run long jobs (large catalogs, browser scrapes) in the background.

6. **Export + deliver.** Export `products.xlsx` + `.csv` + `run_report.json` to
   `catalog-extraction/outputs/<supplier>-full/`, then **copy the .xlsx to the
   deliverables folder** (currently `~/Documents/From Selenium To Leaf & Ledger/
   THE FINDINGS/` — confirm with the user if unsure). Report row count, priced %,
   imaged %, and any `needs_review` gaps.

## Platform cheat sheet

| Platform | Signature | Data channel |
|---|---|---|
| **Shopify** | `/products.json`, `cdn.shopify.com`, `powered-by: Shopify` | `products.json?limit=250&page=N` (public prices in `variants[].price`) |
| **WooCommerce** | `wp-content`, `woocommerce` | Store API `/wp-json/wc/store/v1/products?per_page=100&page=N` (prices in **minor units ÷100**). If listing is crippled (X-WP-Total:1, hidden catalog), enumerate slugs from `product-sitemap.xml` and fetch `?slug=`. |
| **BigCommerce** | `x-bc-store-id`, `cdn11.bigcommerce.com`, `/xmlsitemap.php` | `xmlsitemap.php?type=products&page=1` → per-page `ld+json` Product. Gated price → login → `POST /remote/v1/product-attributes/{id}`. |
| **nopCommerce** | `__RequestVerificationToken`, nopCommerce robots | sitemap → `ld+json`; gated price → login → `price-value-<id>` span. |
| **PrestaShop** | `powered-by: PrestaShop` | sitemap → `ld+json` (URL-decode desc; `json.loads(strict=False)`; handle `<![CDATA[]]>` in `<loc>`). |
| **Fortune3 / static microdata** | `Powered by Fortune3` | sitemap/category pages → OG meta (`product:price:amount`) + schema.org microdata. |
| **Wix Stores** | `wix-warmup-data` | GraphQL storefront API. |
| **B2B Direct / RepZio** | — | same-origin `/categories/0/-/products/` JSON (approved-dealer login → real prices+tiers). |
| **Magento + Klevu/Algolia** | `Magento`, klevu/algolia hosts | 3rd-party search API to enumerate (public w/ key) + logged-in pages for authoritative price. |
| **Orchard/custom + login** | — | form login → internal paged API. |

**JS-gated / login-gated platforms** (prices only render after JS + a real
sign-in, or the catalog is a client-rendered SPA): drive a **local headless
SeleniumBase Chrome**. It runs on the user's machine, so login is genuine and
from their IP, and the page JS executes. Covers ShopSite AJAX (Regency),
ColdFusion trade catalogs (Allstate), and GoDaddy/SPA storefronts. Details and
the exact per-platform recipes are in **`references/platform-recipes.md`** — read
it whenever the platform isn't a trivially-public JSON API, or when prices are
gated, or when a page won't render over plain HTTP.

## Reuse map (existing code in `catalog-extraction/`)

- **`src/catalog_extraction/ldjson_http.py`** + `scripts/run_ldjson_supplier.py`
  — generic sitemap→ld+json runner (BigCommerce/nopCommerce/PrestaShop).
  **Add a supplier by adding a `SupplierConfig` to the `CONFIGS` dict.**
- **`scripts/run_unlimitedcontainer_full.py`** — Shopify `products.json` (curl).
- **`scripts/run_hrcasabella_full.py`** / **`run_jayscotts_full.py`** — WooCommerce Store API.
- **`scripts/run_dfwvases_full.py`** — Fortune3 microdata + live-category enumeration.
- **`scripts/run_athome_full.py`** / **`run_athome_categories.py`** — large SFCC ld+json via curl (category-scoped variant too).
- **`scripts/run_regency_full.py`** — SeleniumBase login + ShopSite `get_products.php` quickview (tiered dealer prices).
- **`scripts/run_allstate_full.py`** — SeleniumBase login + ColdFusion CLCD→DDCODE→piclist drilldown.
- **`scripts/run_forestline_full.py`** — mysimplestore `/api/v3/products` (found via browser network capture).
- **`scripts/run_rockwarehouse_full.py`** — custom static `Source.html` div-block parser.
- **`EXTRACTION_PLAYBOOK.md`** — the living, detailed playbook. Read/append to it.

Copy the closest-matching runner and adapt (BASE url, selectors, export columns).
Keep runners **staged and resumable** (discover → details/fetch → export), and
follow the existing export-column conventions so all catalogs import uniformly.

## Hard-won rules (why they matter)

- **curl vs requests.** Cloudflare/Akamai fingerprint Python's `requests`/TLS and
  return 429/403 even with a browser UA, while **curl** sails through. If
  `requests` gets blocked, shell out to `curl -s --compressed -A <UA>`.
- **Prove the login is real.** Never trust "login didn't change the price." After
  authenticating, assert a value that *must* change when logged in (a logout
  link, a real price replacing $0.00/"Login for pricing"). A form that 200s is
  not proof.
- **Index price ≠ dealer price.** A 3rd-party search index (Klevu/Algolia) or an
  "MSRP/list" figure is not the buyer's price — verify against the authenticated
  page.
- **Stale sitemaps.** If a sitemap is >~30% dead links, enumerate from live
  category pages instead.
- **No silent caps.** If you bound coverage (top-N, sampling, skipping a broken
  category), `log()` it and flag it — don't let a partial pull read as complete.
- **Credentials.** Trade logins live in gitignored `catalog-extraction/.env`
  (`<VENDOR>_USERNAME`/`<VENDOR>_PASSWORD`); scripts read them via `os.environ`
  (python-dotenv, `override=True`). Never put credentials or session cookies in
  chat or in committed files; advise password rotation after onboarding.
- **iCloud write flakiness.** Writing straight to iCloud-synced Documents can
  throw TimeoutError — export to a temp dir, then `shutil.move`.

## When prices are genuinely gated and there's no account

Deliver the full **public metadata** (SKU, name, images, category, dimensions,
variants) with `price` blank and `needs_review = "price (account-gated)"`, and
tell the user prices need a trade account (a quick enrichment pass fills them once
one exists). This mirrors the Amazing Green / HR Casabella / Jackson Pottery
cases. Some "no-account" suppliers still expose **public retail prices** (e.g.
Rock Warehouse) — always check before assuming gated.

## Not every vendor is a catalog

Operational/service vendors (freight/logistics, packaging, raw materials) and
abandoned/template marketing sites have **no resale catalog** to scrape. Say so
plainly and don't force a scrape that yields garbage.
