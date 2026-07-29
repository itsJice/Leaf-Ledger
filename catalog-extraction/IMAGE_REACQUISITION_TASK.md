# Task: Re-acquire product images for 3 suppliers (Melrose, Allstate, Rock Warehouse)

**Owner:** parallel agent · **Coordinated with:** main session (which is simultaneously
hardening the image proxy + adding local image caching — you do NOT need to touch that;
just get working image URLs into the DB and the caching layer will pick them up).

## Why
Leaf & Ledger is a design company — buyers pick product visually, so a product with no
picture is unusable. 98% of the catalog shows images fine. Three suppliers have **dead
image URLs** (the URLs return HTTP 404 / HTML, not an image). ~12,200 products affected:

| Supplier | supplier_id | products | Failure mode |
|---|---|---|---|
| Melrose International | 29 | 6,708 | B2B portal (solovue); SKU-path images 404 |
| Allstate | 1 | 4,784 | Ephemeral ColdFusion image URLs (expired after scrape session) |
| The Rock Warehouse | 25 | 684 | Site restructured; product pages now 404 |

## Goal
For each affected product, put a **working** image URL (returns HTTP 200 with
`content-type: image/*`) into the DB so the app renders it. One good URL per product is
enough; multiple is better (fallback chain).

## Per-supplier notes (start here)

### Allstate (id=1) — has login creds
- Dead URLs look like `…/CFFileServlet/_cf_image/_cfimg-<random>.jpg` — these are
  **session-scoped ColdFusion temp URLs** that expire; that's why they 404. You must log
  in and re-scrape the **stable** product image URL from each product page.
- Credentials ARE stored: `suppliers.login_username` / `login_password`, `login_url =
  https://www.allstatefloral.com/?login`. Read them from the DB (see "DB access").
- Product URLs exist per item: `raw_data->>'product_url'` (e.g.
  `…/design/index.cfm?piclist=Y&DDCODE=XZ6NA`). Log in first, then fetch each product
  page and extract the real `<img>` src.

### Melrose International (id=29) — B2B portal, no creds stored
- Dead URLs: `https://melrose.solovue.com/images/product/<SKU>.JPG` (404).
- `raw_data->>'product_url'` is generic (`…/product`) and returns a 200 HTML page
  (likely a login/landing page). solovue is a B2B wholesale platform — images are almost
  certainly **behind a trade login**. **Ask the user for Melrose trade-portal credentials
  before starting** (there are none in the DB). Then find the real image URL/path pattern
  once logged in (it may be a different host/CDN or require a session cookie).

### The Rock Warehouse (id=25) — no creds, public site
- Dead URLs: `https://therockwarehouse.com/assets/<SKU>_450.jpg` (404) and product pages
  `…/<Category>/General.html` now 404 → the site was restructured. Smallest set (684).
- Re-crawl the current therockwarehouse.com to find where product images live now and
  re-map by SKU (`supplier_sku`, e.g. `BE 0888`, `AMY 2873`). Public — no login needed.

## How to scrape
Use the **`leaf-ledger-catalog-scrape` skill** and `catalog-extraction/EXTRACTION_PLAYBOOK.md`
(this repo). Full-detail policy still applies, but here you only need the **image URL(s)**
per product keyed by SKU — you do NOT need to re-scrape prices/descriptions (those are fine).

## DB access & how to write results
- Connect with the app DB URL in `backend/.env.dev` (`DATABASE_URL`). The `app` role is
  **DML-only** (SELECT/INSERT/UPDATE/DELETE) — no CREATE/ALTER. `UPDATE products …` is fine.
- Match rows by `supplier_id` + `supplier_sku` (fall back to `raw_data->>'sku'`).
- Write the working URL(s) to **`image_urls` (text[])** and **`photo_url` (text)**.
  Keep it **additive/non-destructive** to the rest of `raw_data` (per project rule:
  normalization/backfill must only ADD, never wipe scraped data). Suggested:
  ```sql
  UPDATE products
     SET image_urls = $1::text[], photo_url = $2
   WHERE supplier_id = $3 AND supplier_sku = $4;
  ```
- Optionally also stash provenance in raw_data (e.g. `raw_data['image_reacquired_at']`),
  but do not remove existing keys.

## Verify before finishing
For a random sample per supplier, re-fetch the new URLs and assert HTTP 200 +
`content-type: image/*` (a quick `requests.get` with a browser User-Agent; add
`Referer` = site origin if the host hotlink-guards). Report counts: fixed / still-missing
per supplier. Anything you genuinely can't recover (discontinued items), leave as-is and
list it — the app will show a clean "image unavailable → View on supplier" tile for those.

## Do NOT
- Don't change other product fields (name, price, description, category, normalized).
- Don't deactivate or delete rows.
- Don't touch the proxy / frontend / `ll_app.*` order tables — the main session owns those.

---

# RESULTS (completed)

| Supplier | id | products | images fixed | still missing | where the image lives |
|---|---|---|---|---|---|
| Melrose International | 29 | 6,708 | **6,705** | 3 (catalog books, not products) | remote URL in `photo_url` / `image_urls` |
| Allstate | 1 | 4,784 | **4,667** | 117 (absent from supplier site) | GitHub: itsJice/L-Limages (raw URLs) |
| The Rock Warehouse | 25 | 684 | **6** | 678 (site defunct) | Wayback URL in `photo_url` |

## Melrose — fixed at the URL level
Original scrape built the wrong path (`/images/product/<sku>`). Real public SoloVue path is
`/images/products/detail/desktop/<ImageName>` (no login needed). Written to `image_urls` +
`photo_url`; `raw_data.image_source = melrose_solovue`. Verified: random sample all 200 image/jpeg.

## Allstate — SOLVED: permanent GitHub-hosted URLs (no ingest needed)
**The task doc's premise did not hold: Allstate has no stable image URL.** Verified:
* Images are served *only* as ColdFusion temp files `/CFFileServlet/_cf_image/_cfimg<rand>.jpg`
  that expire **within minutes** (measured). No cookie needed while alive.
* Neither the piclist page, `Productitemdetail.cfm`, nor the public site exposes any durable path
  (15 candidate stable paths probed → all 404). archive.org Save Page Now was tried and works but
  anonymous rate limits made 4.7k captures a ~7-day job — abandoned.

**Final fix:** the bytes were downloaded during a live scrape (4,668 valid JPEGs, 434 MB) and
pushed to the public GitHub repo **itsJice/L-Limages**. Every product now points at
`https://raw.githubusercontent.com/itsJice/L-Limages/main/allstate/<SKU>.jpg` — a permanent
public https URL that behaves exactly like every other supplier's remote image.
* `photo_url` + `image_urls` updated for 4,667 products; `raw_data.image_source = github_llimages`.
* Verified: sampled URLs serve `200 image/jpeg`; `/api/products/page` hands them out; direct fetch OK.
* Local backup remains at `catalog-extraction/outputs/allstate-full/images/` + `images_manifest.json`.
* To re-host elsewhere later: push the same files and re-run
  `scripts/point_allstate_to_github.py` with the new base URL.

## Rock Warehouse — effectively unrecoverable
Site is defunct (redirects to an Etsy shop); all product URLs 404. Wayback holds 709 images for the
domain, but they are trade-show banners and index-page graphics — only **6** products have their own
recorded image archived. Those 6 are committed as `web.archive.org/…im_/` URLs (verified 200 image/jpeg).
The other 678 were **left empty on purpose**: the closest archived filenames belong to *different*
products (e.g. `MEX 1143` would have inherited `MEX_1142`'s photo), and fabricating an image is worse
than showing none. Recovering these needs images from the vendor directly, not the web.
