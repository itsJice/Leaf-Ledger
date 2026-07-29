# Platform recipes & breakthroughs

Detailed, copy-ready recipes. Read the section for the platform you're on. Every
proven pattern here shipped a real supplier — the named `run_*.py` script in
`catalog-extraction/scripts/` is the working reference implementation.

## Table of contents
- [Public JSON APIs](#public-json-apis) — Shopify, WooCommerce, mysimplestore
- [Sitemap → ld+json](#sitemap--ldjson) — BigCommerce, nopCommerce, PrestaShop, SFCC
- [Static HTML / microdata](#static-html--microdata) — Fortune3, custom static
- [Login-gated over HTTP](#login-gated-over-http) — nopCommerce, BigCommerce
- [JS-gated → headless browser](#js-gated--headless-browser) — ShopSite, ColdFusion, SPA
- [Anti-bot: curl vs requests](#anti-bot-curl-vs-requests)
- [Export conventions](#export-conventions)

---

## Public JSON APIs

### Shopify — `run_unlimitedcontainer_full.py`, `amazinggreen_http.py`
`GET /products.json?limit=250&page=N` until a page returns 0. Public price in
`variants[].price`; images in `images[]`; extra detail (dims, case-pack) often in
`body_html` — parse it. `/products/{handle}.js` adds `variant.barcode` (UPC).
Passwordless-login Shopify stores may hide wholesale price even when logged in →
price is rep-list only (flag it).

### WooCommerce Store API — `run_hrcasabella_full.py`, `run_jayscotts_full.py`
`GET /wp-json/wc/store/v1/products?per_page=100&page=N`. **Prices are in minor
units** — divide by `10**currency_minor_unit`. `X-WP-Total`/`X-WP-TotalPages`
headers give counts. Variable products: parent gives a price *range*; fetch
`?type=variation&parent=<id>` for per-SKU prices. **Crippled listing** (hidden
catalog visibility → `X-WP-Total: 1`): enumerate product slugs from
`product-sitemap.xml`, fetch each `?slug=<slug>`. B2B stores return `price: 0` for
guests → gated (flag).

### mysimplestore (GoDaddy "OLS" storefronts) — `run_forestline_full.py`
GoDaddy Websites+Marketing stores whose `/ols/products/*` pages are a
client-rendered SPA (won't render even in a browser via direct URL) are usually a
**SimpleStore** behind the scenes. Load a product page in a headless browser and
read `performance.getEntriesByType('resource')` (or the network log) — you'll see
`https://<storeUUID>.mysimplestore.com/api/v3/config`. Then hit
`https://<storeUUID>.mysimplestore.com/api/v3/products?per_page=100` — the whole
catalog as JSON (public prices, `assets[].url`, `description_raw` as Draft.js
blocks). One request. Lesson: **when a SPA won't render, capture its network
requests to find the real backend API.**

---

## Sitemap → ld+json

Use the generic runner: add a `SupplierConfig` to `CONFIGS` in
`scripts/run_ldjson_supplier.py`. The module `src/catalog_extraction/ldjson_http.py`
handles discovery, threaded checkpointed fetch, ld+json parsing, price gating.

Robustness details baked into the module (don't re-solve these):
- `json.loads(raw, strict=False)` — PrestaShop embeds raw control chars in strings.
- `<loc>` regex is CDATA-aware (`<![CDATA[...]]>`).
- `Accept-Encoding: gzip, deflate` (NOT `br` — brotli garbles `requests` unless
  the brotli package is installed; some servers return a truncated/wrong ld+json
  without a compression header).
- SFCC/`ItemPage` wrappers: the Product is under `mainEntity` — the module
  unwraps it.

Config knobs: `description_urldecode=True` (BigCommerce), `title_must_contain`
(skip misrouted slugs). **BigCommerce/nopCommerce prices are often login-gated**
("Call for pricing" / empty span) — see the next section to enrich them.

**SFCC (Salesforce Commerce Cloud) at scale** — `run_athome_full.py`: 45k+ PDPs,
`sitemap_*-product.xml` → PDP `ld+json`. Akamai 403s `requests` → **curl**. To
scope to specific categories, use the grid AJAX
`Search-UpdateGrid?cgid=<slug>&start=N&sz=100` (returns `data-pid` tiles;
paginate `start`), resolve category names to real cgid slugs against the site's
slug universe — see `run_athome_categories.py`.

---

## Static HTML / microdata

### Fortune3 & schema.org microdata — `run_dfwvases_full.py`
Product pages carry clean **Open Graph** product meta
(`product:price:amount`, `product:price:currency`, `product:retailer_item_id`=SKU)
+ schema.org microdata. Prefer OG meta (clean) over `itemprop` attrs (unescaped
inch-quotes break naive parsers — use bs4/lxml). If the sitemap is mostly dead
404s, **enumerate live products from the category pages** instead.

### Custom static tables — `run_rockwarehouse_full.py`
Dreamweaver-era sites hide the real payload in per-category include files
(`/{Cat}/Source.html`, not the sitemap's `General.html` shell). Products are
`div.tb_layer3` blocks laid out `[image][name+SKU][retail price][volume tiers]`.
Parse by walking the blocks, starting a new product at each image block. **Public
retail prices with quantity breaks** here even though wholesale is gated.

---

## Login-gated over HTTP

When the platform is a normal store but prices are hidden for guests, and the
login is a plain form (no heavy JS), authenticate with `requests` and re-fetch.

- **nopCommerce** (`enrich_american_best.py`): `GET /login` → grab
  `__RequestVerificationToken` → `POST /login` with Email/Password/token →
  assert `logout` on `/customer/info` → price is in a `price-value-<id>` span.
- **BigCommerce** (`enrich_autograph.py`): `GET /login.php` → `authenticity_token`
  → `POST /login.php?action=check_login` → assert `logout` on `/account.php` →
  per product: page → `data-product-id` → `POST /remote/v1/product-attributes/{id}`
  → price at `data.price.without_tax.value` (works even when the page says "Call
  for pricing").

Pattern: an **enrichment stage** reads the existing `products.xlsx` (has
`product_url`), logs in, fetches the gated field per row, merges back. Keep it a
separate `enrich_<supplier>.py` with `--stage fetch|merge`.

---

## JS-gated → headless browser

When prices only render via JavaScript after a genuine sign-in, or the catalog is
a client-rendered SPA, drive **local headless SeleniumBase Chrome**. It runs on
the user's machine (same IP as their browser) so the login is real and the page
JS executes — pure-HTTP cookie reuse fails because sessions aren't portable.

Boilerplate:
```python
from seleniumbase import SB
with SB(headless=True, browser="chrome") as sb:
    sb.open(LOGIN_URL); sb.sleep(3)
    sb.execute_script("var p=document.querySelector('input[type=password]');"
                      "var f=p.closest('form');"
                      "f.querySelector('input[name=EMAIL_FIELD]').value=arguments[0];"
                      "p.value=arguments[1];"
                      "f.requestSubmit?f.requestSubmit():f.submit();", USER, PW)
    sb.sleep(6)
    # ASSERT login is real, e.g. a group/name variable or logout link:
    assert "customer group" in (sb.execute_script("return (window.group||'')+''")).lower()
```
Notes: fill via JS if fields are inside a hidden popup (`wait_for_element` fails on
invisible inputs). Avoid `uc=True` headless (undetected-chromedriver crashes);
plain `headless=True` is stable. Once logged in, you can either read rendered
values from the DOM, **or** call the site's own endpoints from the authenticated
page context via `sb.driver.execute_async_script("fetch(url,{credentials:'include'})…")`
— often far faster than clicking through pages.

### ShopSite + custom AJAX (Regency) — `run_regency_full.py`
Prices are Customer-Group prices rendered client-side by a JS function reading a
hidden field (`ss_field27` for Group #0), unlocked only after the server sets an
`ss_reg_<serial>` cookie on a real sign-in. After logging in via the browser,
`fetch('/get_products.php?...&pageId=N&skip=M',{credentials:'include'})` returns
tiles whose `quickview` attribute (HTML-entity-encoded) holds `.price`
("As low as: $X") **and** `.qntyprice` (the full quantity-tier table). Enumerate
categories from the rendered nav; paginate `skip` until `total`; dedupe by SKU.

### ColdFusion trade catalog (Allstate) — `run_allstate_full.py`
Login persists in the **app section** (`/design/`, `/pro/`) even though the public
`/` splash always shows a login link (don't test login there). Drilldown:
`/design/` → category codes `index.cfm?CL=1&CLCD=<E|X|W|M>` → subcategory codes
`index.cfm?piclist=Y&DDCODE=<code>` → product cells (item#, "List Price"=trade
price, unit EA/BX/ST, desc, CFFileServlet image), paginated. Give image-heavy CF
pages a longer wait + a retry-if-empty.

### SoloVue B2B portal (Melrose) — `run_melrose_full.py`
A vendor's public site may be only marketing while the real wholesale catalog is
a **SoloVue** portal on a separate host (e.g. `melrose.solovue.com`) — ASP.NET +
Vue SPA + JSON API. The login is a Vue form (`LogonEmail`/`LogonPassword` + a
`logIn` button): **set the field values AND dispatch `input`/`change` events**
(Vue won't register a plain `.value=`), then **click the button** (a native form
submit does a GET that leaks creds into the URL — avoid it). Success sets
`.ASPXAUTH` + `SwApi` cookies and seeds `UserToken`/`AccessToken` into the API
URLs. Then, from the authed page context:
`/api/soloweb/GetCategories/?UserToken=..&AccessToken=..` → all category ids;
`/api/soloweb/GetProductList/?ProductCategoryId=<id>&PageNumber=N&ReturnAllImages=true&<tokens>`
→ products, paginate on `IsMoreProducts`. Real quantity-tier wholesale prices.
Field quirks: `Pnumber`=SKU (matches image filename), `Item`=product name,
`Detail`=color, `Prices[]`=`{Price,UnitDescription,Quantity}` tiers,
`OriginalPrice1Amount`=MSRP, `Images[]`. Do API calls via
`sb.driver.execute_async_script(...)` (fetch with `credentials:'include'`).

### SPA with no obvious channel
Load in the browser, capture network (see mysimplestore above), find the backend
API. If truly nothing (abandoned template site, no store), report "no catalog."

---

## Anti-bot: curl vs requests

Cloudflare and Akamai fingerprint Python's TLS/HTTP2 stack and return 429/403 to
`requests` even with a perfect browser UA — while `curl` (system binary) is
allowed. When `requests` gets blocked but `curl` returns 200 for the same URL,
shell out:
```python
proc = subprocess.run(["curl","-s","--compressed","-A",UA, url],
                      capture_output=True, text=True, timeout=90)
data = json.loads(proc.stdout)
```
A homepage "warmup" GET to seed cookies sometimes helps but is not sufficient
against TLS fingerprinting — curl is the reliable fix. Also honor `robots.txt`
crawl-delay and throttle (some hosts silently return empties under rapid loops).

---

## Export conventions

Every runner ends with an export stage producing, in
`catalog-extraction/outputs/<supplier>-full/`:
- `products.xlsx` (sheet `products`) + `products.csv` (+ `products.json` with raw)
- `run_report.json` — `rows_exported`, `with_price`, `with_image`,
  `needs_review_count`, `pricing_note`.

Keep column names consistent across suppliers so imports are uniform: `supplier,
season, sku, upc, product_name, variant, category, description, price,
source_price_label, image_url, image_url_2..N, image_count, product_url,
source_url, needs_review, extracted_at, run_id`. Put the gated/label note in
`source_price_label` (e.g. `dealer_login_price`, `public_retail_price`,
`price (account-gated)`). Write to a temp dir then `shutil.move` (iCloud). Finally
**copy the `.xlsx` to the deliverables folder** and report priced%/imaged%/gaps.
