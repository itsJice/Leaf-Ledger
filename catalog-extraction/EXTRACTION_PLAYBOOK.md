# Supplier Extraction Playbook

Distilled from nine full-catalog pulls (2026-07-02 → 07-09). Every one got
dramatically cheaper by finding the site's own data channel (embedded JSON
model, product sitemap, storefront API, or an authenticated internal API)
instead of scraping rendered pages. Follow the recon order below — the wins
came from cheap recon *before* automation; the dead ends came from reaching
for heavy tools first.

**The one meta-lesson:** identify the ecommerce platform first, because the
platform dictates the data channel. Nearly every platform hands you the whole
catalog through one machine-readable endpoint if you look before you scrape.
And counter-intuitively, a **fully-locked B2B portal gives the *richest* data
once authenticated** (real per-account prices, tiers, UPC, dims, weight,
stock) — public sites strip prices for guests; locked portals don't bother.

**STANDING RULE — always capture the most data, the most detailed.** Every
supplier pull targets FULL rich detail: real prices (the authenticated buyer's
price, not an index/MSRP), ALL product images (not just the thumbnail), full
descriptions, plus UPC / dimensions / weight / variants / stock wherever the
supplier exposes them. A metadata-only or price-missing pull is INCOMPLETE, not
"done" — finish it. If a field is gated, get the login and enrich (see the
enrichment techniques below). If a field is genuinely unavailable (supplier
hides wholesale price even from logged-in accounts, or you lack the account),
say so explicitly and name the alternate source (rep price list merged by SKU)
— never silently ship a gap. Audit every finished export for price/image/
description coverage and close what you can before calling it done.

## Platform cheat sheet (what each platform's data channel is)

| Platform | Supplier | Products | Data channel | Auth | Notes |
|---|---|---|---|---|---|
| **Orchard CMS** (custom .NET) | Vickerman | 22,121 | `var model={...}` on each product page + `sitemap-products.xml`; AJAX `DoSearch` for listings | ASP.NET antiforgery form → session cookie | Prices only when logged in |
| **Wix Stores** | Craftex | 4,617 | Storefront GraphQL `/_api/wix-ecommerce-storefront-web/api` (token from `/_api/v1/access-tokens`) | none (public) | Page crawl throttles ~2k reqs; use the API |
| **Shopify** | Amazing Green | 351 | `/products.json?limit=250&page=N`, `/products/{handle}.js`, `/collections.json` | none (public) | Wholesale price hidden by a B2B lock app |
| **Emun / ServiceStack** | Select Artificials | 5,950 | Open JSON API `/service/QueryProducts.json?Take=&Skip=` | none (public) | Tier prices public; base price login-gated |
| **BigCommerce (Stencil)** | Autograph Foliages | 3,091 | Per-product `application/ld+json` + `xmlsitemap.php?type=products`; **price via `/remote/v1/product-attributes/{id}`** (page says "Call for pricing") | trade login | price only via the AJAX endpoint, not the page HTML |
| **nopCommerce** (ASP.NET) | American Best | 3,694 | Per-product `application/ld+json` + flat `sitemap.xml`; **price in `price-value-<id>` span once logged in** | trade login | IIS throttles at >4–5 concurrent; keep it low |
| **B2B Direct / RepZio** (ASP.NET + Vue) | Winward Silks | 9,186 | Same-origin JSON `/categories/0/-/products/?page=N&pageSize=500` | ASP.NET form → session cookie (approved dealer) | `NoPublicBrowsing`; richest data of all once in |
| **WooCommerce** (WordPress) | SuperMoss | 317 → 1,314 variant rows | Store API `/wp-json/wc/store/v1/products?per_page=100&page=N` (`X-WP-Total` header = count) | none (public); login didn't change prices | Prices in MINOR units (÷10^`currency_minor_unit`); variable products need per-variation fetch |
| **Magento 2 + Klevu** (trade-only) | Accent Decor | 2,274 | **Klevu** search API `https://<region>.ksearchnet.com/cs/v2/search` (key from page HTML) for enumeration; logged-in Magento product pages for authoritative price | Klevu API public w/ key; Magento login for real dealer price | Magento's own product GraphQL is broken; grid is JS-rendered by Klevu; **Klevu price ≠ dealer price** — enrich from the logged-in page |

Reusable code by shape: `vickerman_http.py` (shared-auth worker pool +
per-product detail fetch + checkpointing), `craftex_http.py` (GraphQL paging),
`amazinggreen_http.py` (Shopify JSON), `winward_http.py` (form login → single
paged internal API, no detail fetch), `supermoss_http.py` (WooCommerce Store
API + variation expansion), `accentdecor_http.py` (third-party search API for
enumeration + logged-in page enrichment for price/images/desc). Pick the
closest and adapt.

## Enrichment techniques — unlocking gated prices & missing images (2026-07-09)

When a base scrape has everything but prices/images, don't re-scrape — write a
small **enrichment stage** that reads the existing `products.xlsx` (it already
has `product_url`), logs in, fetches the gated field per product, and merges it
back (`stage fetch` → `stage merge`). Pattern lives in
`scripts/enrich_american_best.py` and `scripts/enrich_autograph.py`. Techniques
proven per platform:

- **nopCommerce (American Best) — login exposes prices directly.** GET `/login`,
  parse `__RequestVerificationToken`, POST `Email`/`Password`/token to `/login`.
  Assert `logout` present on `/customer/info`. The `price-value-<id>` span (empty
  for guests) then shows the real `$N.NN`. 3,693/3,694 priced.
- **BigCommerce (Autograph) — the price hides behind an API, not the page.** The
  product page still says "Call for pricing" even when logged in — but
  `POST /remote/v1/product-attributes/{product_id}` returns the real dealer
  price (`data.price.without_tax.value`) for the authenticated session. Login:
  GET `/login.php` → `authenticity_token` → POST `/login.php?action=check_login`
  with `login_email`/`login_pass`; assert `logout` on `/account.php`. Per
  product: fetch page → `data-product-id` → price API. 3,078/3,082 priced.
  Lesson: when a logged-in page shows no price, probe the platform's AJAX
  endpoints (`/remote/v1/...`) before concluding prices are unavailable.
- **Emun / ServiceStack (Select Artificials) — images are on S3, filename is
  derivable.** Images live at
  `https://s3.amazonaws.com/emuncloud-staticassets/productImages/<merchant>/large/<sku>.jpg`
  (merchant `sa159`, found by rendering one product page and reading the real
  `<img src>` — it was NOT the `mw141` literal in the JS bundle). Position 1 =
  `<sku>.jpg`, position 2+ = `<sku>_<pos>.jpg`; SKUs with `/` encode as
  `$FORWARDSLASH$`. Build straight from each product's own `productImages`
  array (`{productId, position}`) — no per-image HEAD check needed. 80% got a
  primary image (the rest are genuinely imageless on the supplier side).
- **Shopify passwordless accounts (Amazing Green) — genuine dead end.** Login
  redirects to `shopify.com/<id>/account` (new customer accounts = email OTP, no
  password field) so it can't be scripted; and prices stay hidden even inside a
  real logged-in session (B2B lock app shows a `$1,234.56` placeholder). Result:
  content is 100% complete (images/desc/variants) but **price is unobtainable by
  scraping** — rep price list merged by SKU is the only path. State this plainly.

Verifying an enrichment login is real is non-negotiable — see the "prove the
login is real" lesson below. And an index price is not the buyer's price — see
the Klevu lesson.

## The recipe that worked (in order)

### 1. Recon with curl before any automation (~10 minutes, saved hours)

- `curl` the homepage, one category page, one product page. Identify the
  platform (Vickerman = Orchard CMS) and whether content is server-rendered
  or JS-rendered (mustache templates like `{{ productDescription }}` in raw
  HTML = client-side rendering).
- **Check `robots.txt` and sitemaps immediately.** Vickerman's
  `sitemap-products.xml` listed all ~22k product URLs — the complete catalog
  universe with zero pagination crawling. This single finding replaced an
  entire listing-discovery stage.
- **Search the raw product-page HTML for embedded data** before assuming you
  must scrape rendered DOM. Vickerman embeds `var model = {"CurrentItem":...}`
  with EVERY field we need: SKU, UPC, descriptions, product type, prices,
  quantities, stock, product + package dimensions, material, warranty,
  category/subcategory, and all 10 image URLs. Also check for
  `application/ld+json` (schema.org Product) blocks.

### 2. Prefer HTTP with a requests.Session over a browser

- The whole pull ran over plain HTTP at ~8 products/sec. A browser per page
  would have taken 30+ hours; HTTP took 48 minutes.
- Login was a standard ASP.NET antiforgery form: GET the login page, parse
  `__RequestVerificationToken`, POST credentials + token. Verify success by
  checking for a logout link in the response.
- Pricing rendered only when logged in (`Price`/`SalePrice` null vs populated
  in the embedded model). Confirm the priced view with one product before
  scaling.
- AJAX listing endpoints (Vickerman: `ProductSelector/DoSearch`) return 500
  without session cookies + verification token + `Referer`/`X-Requested-With`
  headers. With them, they work fine from requests.

### 3. Concurrency rules learned the hard way

- **One login, shared cookies.** Six workers each logging in simultaneously →
  login rejections and connection resets. Fix: login once up front, share the
  cookie jar, serialize any re-login behind a lock (see `_SharedAuth` in
  `src/catalog_extraction/vickerman_http.py`).
- 6 workers + ~0.15s jittered delay ≈ 8 req/s was sustained for an hour with
  zero errors and no throttling.
- Retry 3x with backoff on connection errors; detect session expiry per
  response and re-login once.

### 4. Bounded, checkpointed, resumable stages (per the onboarding notes)

Structure: `discover -> details -> export` (`scripts/run_vickerman_full.py`).

- Discovery output (`items.json`) and per-product NDJSON checkpoint
  (`details.ndjson`, one line appended + flushed per product) meant every
  interruption was resumable — re-running skipped completed SKUs and retried
  failures automatically. This was exercised for real and worked.
- Export is a separate stage so formatting changes never require refetching.
  We re-ran export three times (units fix, image-column fix) at zero fetch cost.

### 5. Coverage verification is its own crawl — and it caught real gaps

- The user-visible per-header counts are the **landing page** totals with the
  default "Available" filter. Full sections are bigger (subcategories), and
  listing rows massively double-count (39k listing rows -> 22k unique SKUs;
  Ornaments alone: 18,135 rows -> 9,641 SKUs). Dedupe by supplier+SKU and
  verify at SKU level, not row level.
- Crawling every header/subcategory listing and diffing against the fetched
  set caught **54 products in listings that were missing from the sitemap**.
  Do both discovery methods; neither alone was complete.
- Record where each SKU was seen (`listed_under` column) and put the
  per-header table in the run report so coverage is provable to the user.

### 6. Export formatting that survived user QC

- **Units in column headers**: `height_in`, `weight_lbs`, etc. Keeps values
  numeric for Excel sorting/filtering.
- **One URL per cell.** Semicolon-joining image URLs in one cell made users
  (and Excel) treat the joined string as one broken link. Split to
  `image_url`, `image_url_2` ... `image_url_10` + an `image_count` QC column.
- `needs_review` column listing exactly which fields are missing per row —
  never invent values; blank + flag.
- Generate a `qc_first_100.xlsx` early, while the full pull runs, and let the
  user QC it. All three of their corrections were applied before the final
  export cost anything.
- Keep full raw supplier JSON in `products.json` / `details.ndjson`; keep the
  spreadsheet lean (raw JSON can exceed Excel's 32,767-char cell limit).
- **Write exports to a local temp dir, then `shutil.move` into place.** The
  workspace lives under an iCloud-synced Documents folder; large in-place
  writes died with `TimeoutError: [Errno 60]`.

### 7. Credentials

- `.env` (gitignored) + `python-dotenv`; never in code, configs, or recordings.
- Rotate the supplier portal password after onboarding if it was ever pasted
  into a chat or terminal.

## Platform notes: Wix Stores (Craftex, 2026-07-02)

- Wix sites list every collection in the `categoryId` filter of any listing
  page's warmup data (`filters_*` keys) — union across section pages to get
  the full taxonomy with collection IDs.
- Product pages embed the catalog model in `wix-warmup-data`, but a small
  percentage render with an EMPTY warmup (retrying doesn't help) — fall back
  to the storefront GraphQL API (`/_api/wix-ecommerce-storefront-web/api`,
  Authorization: instance token from `/_api/v1/access-tokens`).
- **Page crawling gets rate-limited after ~2k requests** (throttled to
  ~0.03/s, not blocked). The storefront API is NOT throttled and returns 100
  full products per `getFilteredProducts` call — the whole 4.6k catalog took
  ~90s. Lesson: when a platform has a storefront API, use it for the bulk
  pull and keep page fetches for spot checks. Checkpoint format shared
  between both paths made the mid-run pivot free.
- Category pages accept cumulative `?page=N` (page 5 = first 300 products)
  but the embedded list caps ~2k items — use the API for big collections.
- Wix `weight` is pounds for US stores; SKUs may be UPC-like digits or
  alphanumeric — populate `upc` only when it looks like a UPC (12–13 digits).
- Variants: `productItems[]` each carry own SKU/price/inventory;
  `optionsSelections` ids map to `options[].selections` for names. One export
  row per variant.

## Platform notes: B2B Direct / RepZio (Winward Silks, 2026-07-08)

The "hard / blocked" supplier from recon turned into the single best pull
(9,186 products, 100% UPC/images/dims/weight/color, real dealer prices +
every tier). Recipe, in the order it cracked:

- **Identify the wall**: homepage carries `data-site-access-level="NoPublicBrowsing"`
  and `_isAuthenticated = false`; every catalog URL 302s to
  `/account/login?ReturnUrl=...`. CSP `connect-src` names `repzio.azure-api.net`,
  `*.repzio.com`, `b2bbucket.s3.amazonaws.com` — data lives off-domain on RepZio.
- **Check the login shape before assuming a token flow.** Winward's is a plain
  ASP.NET form (`#Username`, `#Password`, `__RequestVerificationToken`) — GET
  login page, parse the hidden token, POST. Scriptable exactly like Vickerman;
  no browser needed for auth. (A B2B portal that turned out to be a real token/
  OAuth flow would be where you'd fall back to the browser session-handoff.)
- **After login, find where the data actually comes from.** The category page
  was an empty Vue shell (0 products in the HTML) → it's API-driven. The app
  bundles are `/selljs` and `/sellheaderjs`; grepping them surfaced the endpoint
  shape `/categories/{id}/-/products/`.
- **Test the endpoint with the session cookie + XHR headers.** It returns
  same-origin JSON (the server proxies to RepZio; the session cookie *is* the
  auth — no API key). Set `X-Requested-With: XMLHttpRequest` and
  `Accept: application/json`; **set those AFTER login**, not before (they change
  how the login page responds and break token parsing).
- **`category 0` = the whole catalog.** `/categories/0/-/products/?page=N&pageSize=500`
  returns everything with `TotalRecords` for paging — 9,186 in ~19 calls, ~20s.
  No per-product detail fetch: the listing record is fully rich (`ItemID`=SKU,
  `UPC`, `ItemName`, `RenderedDescription`, `Price` + `AllPrices` tiers,
  `Dimensions`, `Weight`, `OnHandQuantity`, `ImageURL` + `AdditionalImageList`,
  color in `Udf17`). `ShowPricing:true` / `PriceLevel:N` confirms priced view.
- **Gotchas**: the flat `category 0` view has no per-product category
  (`CategoryId:0`) — a category tree crawl is a separate stage if `category` is
  needed. Image URLs arrive with a trailing empty `?width=` — strip the query.
  Login GET can be slow to first byte — wrap login + page fetches in retries
  (a single 30s timeout killed the first run).

## Platform notes: WooCommerce (SuperMoss, 2026-07-09)

- **Detect it**: `wp-content` / `woocommerce` all over the HTML, Yoast
  `sitemap_index.xml`, `/wp-json/` present. The `/account/` URL was a custom
  My-Account page, not Shopify — don't assume Shopify from an `/account/` path.
- **Data channel = WooCommerce Store API** (public when enabled):
  `GET /wp-json/wc/store/v1/products?per_page=100&page=N`. Count is in the
  `X-WP-Total` response header; `X-WP-TotalPages` for paging. Records are rich:
  sku, name, description, `prices`, `images[]`, `categories`, `dimensions`,
  `weight`, stock. (The authenticated `/wp-json/wc/v3/` REST API needs a
  consumer key/secret — don't go there; the Store API is the public one.)
- **Prices are in MINOR units.** `"price":"79500"` with
  `currency_minor_unit:2` = $795.00. Divide by `10**minor_unit` — do NOT treat
  the integer as dollars.
- **Variable products need expansion.** `type=="variable"` parents carry only a
  `price_range` and `variations:[{id, attributes:[{name,value}]}]`. Fetch each
  `/products/{variation_id}` for its own sku + price; take the variant label
  (e.g. "Size: 2-cu-ft") from the parent's `variations[].attributes`. One row
  per variation (317 base products → 1,314 rows here). ~20 base products had
  no sku — key on product id (`woo-<id>`) as fallback.
- **WooCommerce login (if a wholesale-pricing plugin is suspected)**: many
  themes use a custom AJAX login, not the default WooCommerce form. SuperMoss's
  `/account/` form had `action="#"` + hidden `action=user_login` + a JS `nonce`
  → it POSTs to `/wp-admin/admin-ajax.php` with
  `{action:user_login, login_name, login_password, nonce}`. Success =
  `{"errors":[]}` and a `*_logged_in_*` cookie on the session. The Store API
  honors that session, so member pricing (if any) flows through automatically.
- **Verdict for SuperMoss**: login did NOT change prices (compared 8 products
  across the full range, all identical guest vs member) — the public prices are
  the real prices. Confirmed only after a *real* login; see the lesson below.

## Platform notes: Magento 2 + Klevu (Accent Decor, 2026-07-09)

The full escalation ladder — every earlier tier failed before the real channel
surfaced. Work it in this order for any hard/gated site:

1. Embedded page data? No (trade-gated shells, `/customer/account/login`).
2. Platform API — Magento GraphQL: `generateCustomerToken(email,password){token}`
   logs in and `categories` works, but the **`products` resolver throws
   "Internal server error"** on every filter/shape (their Elasticsearch is
   misconfigured server-side — unfixable from outside). `category(id){products}`
   fails too. GraphQL is dead for product listing here.
3. Storefront HTML scrape? The category grid is **JS-rendered** — only a few
   `product-item-info` blocks in the HTML, `?product_list_limit=all` changes
   nothing. Products aren't in the server HTML.
4. **Third-party search provider.** Grep the category page for
   `algolia|searchspring|klevu|nosto|bloomreach|constructor|findify|unbxd`.
   Accent Decor = **Klevu** (447 hits, `js.klevu.com`; key `klevu-…` in the HTML).
   That's the real data channel.
5. **Klevu API** — POST `{context:{apiKeys:[KEY]}, recordQueries:[{id,
   typeOfRequest:"SEARCH", settings:{query:{term:"*"},
   typeOfRecords:["KLEVU_PRODUCT"], limit:100, offset:N}}]}` to
   `https://<region>.ksearchnet.com/cs/v2/search`. `term:"*"` returns the whole
   catalog; `meta.totalResultsFound` = count; 100/page cap; offset paging.
   Public with the key — **no Magento login needed for enumeration.**
6. **Finding the region host.** Klevu shards stores; a guessed host returns
   `{"error":{"message":"search-request-on-wrong-server"}}`. Config-discovery
   endpoints 404'd. What worked: **capture the browser's own request** — load a
   category page in headless Chrome and read the CDP performance log
   (`Network.requestWillBeSent`) for the `ksearchnet.com` host. (Key detail:
   patching `window.fetch`/XHR missed it — Klevu used a beacon/script; the CDP
   network log catches every request type. And with SeleniumBase, the driver
   IS `d` — `d.get_log("performance")`, not `d.driver.get_log`.)
7. **Enrichment for the fields Klevu lacks / gets wrong.** Klevu gives one
   image + short desc, and its price is NOT the dealer price (see below). Fetch
   each product page with a **logged-in Magento session** for the real
   `finalPrice`, all images, and the full description. Price lives in the JS
   price config: `"finalPrice":{"amount":"NNN"}` (multiple = configurable
   variants; take min/max). Real SKU = Klevu `sku` split on `;;;;` (matches the
   product-page ld+json `sku`).

## Lesson: an indexed price is not necessarily the price the customer pays

Klevu's indexed prices for Accent Decor were consistently ~1.2× LOWER than the
logged-in Magento `finalPrice` (Doric $225 Klevu vs $270 page; the ratio wasn't
even constant across products). Shipping the Klevu price as "the dealer price"
would have been wrong on every row. **A third-party search index (Klevu,
Algolia, etc.) reflects whatever was indexed — a base price, a stale price, a
different customer group — not necessarily the authenticated buyer's price.**
When the number matters (it always does for a catalog), verify one product's
index price against the logged-in product page, and if they differ, make the
logged-in page the source of truth. Keep the index price as a labeled
comparison column, never as the headline `price`.

## Lesson: a "prices are the same" result is worthless until the login is proven real

Chasing SuperMoss wholesale pricing produced TWO false negatives before the
truth. Both times the comparison said "guest == member, no login needed" — and
both times the login had silently failed:

1. First attempt hit `/my-account/` (WordPress default) — this site uses a
   custom `/account/`; wrong URL, no login, `logged_in` cookie absent.
2. Second attempt used the right AJAX endpoint but the `.env` credentials were
   still blank (the user's first save hadn't taken) — the server replied
   `"Enter your email"`, i.e. it received empty fields.

Only the third attempt (correct endpoint + populated creds) logged in for real
(`{"errors":[]}`, `logged_in` cookie present) and gave a trustworthy compare.
**Rule: never report "login doesn't change X" until you have asserted the
session is authenticated** — check for the logged-in cookie / a logout link /
an empty-errors response. A failed login and a no-op login look identical in
the data. Print the auth-state assertion next to any such comparison.

## Craftex case notes: what worked / what didn't (2026-07-02)

Worked well:

- **Total recon-to-done time was a fraction of Vickerman's** because the
  playbook order was followed: robots.txt -> product sitemap (4,617 URLs) ->
  embedded `wix-warmup-data` on a product page, all confirmed in ~5 minutes
  before writing any code.
- **The storefront GraphQL API beat page scraping outright.** 100 complete
  products per call, no throttling, whole catalog in ~90 seconds. Page-by-page
  fetching would have been the wrong bulk path even without the rate limit.
- **Two-source coverage came out perfect and provable**: sitemap said 4,617,
  the union of all 64 collections said 4,617, fetched 4,617 — 0 missing, and
  the run report shows it.
- **Variant handling** (`productItems[]` -> one row each with own SKU, price,
  stock) matched how the user thinks about "each individual item."
- **The reusable stage skeleton** (discover/details/export + NDJSON
  checkpoint) transferred from Vickerman nearly unchanged; export re-runs for
  formatting fixes stayed free.
- The user's recorder session, though it captured no login, **mapped the nav
  sections and product-page URL shape in one pass** — useful recon input.

Didn't work / cost time:

- **Page crawling hit a throttle after ~2k requests** (slowed to ~0.03/s, not
  blocked — looks like a stall, is actually rate-limiting). Mid-run pivot to
  the API was only cheap because the checkpoint format was shared. Next Wix
  site: start on the API.
- **~1.3% of product pages render with an empty warmup** and retries don't
  help — only the API fallback recovered them. Budget for a sweep stage.
- **Wix product objects carry no category names** (`categories: []`,
  `breadcrumbs: null`) — category mapping had to come from the collections
  crawl, unlike Vickerman where each product self-reported its category.
- **First GraphQL attempt failed on query formatting** — write the query as
  the site's own client sends it; don't improvise syntax.
- **The user's four top-nav sections are the category truth** (All Ribbons /
  Christmas Store / Seasons and Decor / Floral Store); the 64 raw collections
  are subcategories. Ask/confirm the human taxonomy before wiring `category`.
- **macOS TCC blocked Terminal.app from the Documents folder** ("operation
  not permitted" on `source .venv/bin/activate`), which broke recorder
  launches — fixed by putting the recorder venv in the home directory.
  Symptom to remember: the error looks like a venv problem but is a
  folder-permission problem.

## Dead ends (don't repeat)

- **SeleniumBase desktop recorder**: needs a live interactive terminal (it
  finishes via a `(Pdb+)` prompt reading stdin). Launched from an agent /
  background process it opens-then-closes instantly. Also hit: bare `python`
  not on PATH (it shells out to `python -m pytest`), and `pkg_resources`
  missing on Python 3.14 with older SeleniumBase (fix: `setuptools<81`, or
  SeleniumBase >= 4.50). Ultimately unnecessary — HTTP recon replaced it.
- **Generic CSS-selector runner** (`seleniumbase_runner.py`) can't handle
  JS-rendered catalogs (AJAX listings, click-based pagination, Vue detail
  pages). A browser was only useful for initial rendered-DOM recon probes.
- **Estimating from listing counts**: headline numbers like "39,051 products"
  were listing rows, not products. Reconcile before promising row counts.

## Next-supplier checklist

1. Structured export first (CSV/XLSX/API/feed) — per the connector contract,
   scraping is the fallback, not the default.
2. **Identify the platform** (grep homepage for shopify/bigcommerce/wix/
   nopcommerce/orchard/`b2bdirect`/`emun`/`repzio`/etc.) and match it against
   the **platform cheat sheet** above — that tells you the data channel before
   you write a line. Fan out one recon subagent per supplier when doing several.
3. `robots.txt` -> sitemaps -> product sitemap?
4. `curl` one product page -> embedded JSON model or ld+json? If the page is an
   empty SPA shell (0 products in HTML), the data is in an API — read the app's
   JS bundle for the endpoint shape, then test it with session cookies.
5. Find the listing/search endpoint; test it with session cookies + XHR headers
   (`X-Requested-With`, `Accept: application/json`) set AFTER login.
6. HTTP login (token form) -> verify priced view on one product
   (`ShowPricing`/populated price). Wrap login + fetches in retries.
7. Smoke run (20–25) -> `qc_first_*.xlsx` to the user -> corrections -> full run
   with checkpoints + background monitor.
8. Listings/coverage crawl -> diff vs fetched -> fetch gaps -> `listed_under`.
9. Export with units-in-headers, one-URL-per-cell, `needs_review`, run report
   with per-header coverage. Write via temp dir; copy deliverable to
   ~/Downloads for the user.
