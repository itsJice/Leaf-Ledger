# Vickerman Onboarding Notes

## Status

- Wave: 1
- Type: Product-heavy florals/decor
- Status: Checkpointed full-catalog import in progress; paused at 10,476 active products after transient DNS failure

## Current Interpretation

Vickerman is historical evidence for why large in-app portal scraping is expensive and fragile. Keep these notes for recovery, maintenance, and fallback extraction design, but do not use this as the default supplier onboarding pattern.

The current strategy is to seek a supplier export, PDF/catalog parse, or external scrape export before continuing or expanding portal scraping. If Vickerman still requires portal extraction, use these notes as fallback run history and failure evidence.

## Notes

- Use [SUPPLIER_ONBOARDING_CHECKLIST.md](SUPPLIER_ONBOARDING_CHECKLIST.md).
- Preserve supplier-specific fields in `raw_data`.
- Do not store credentials in GitHub.
- Recon/proof report: [VICKERMAN_RECON_REPORT.md](VICKERMAN_RECON_REPORT.md).
- Login URL: `https://www.vickerman.com/Users/Account/LogOn`.
- Product selector endpoint: `https://www.vickerman.com/April.Vickerman.Commerce/ProductSelector/DoSearch`.
- Category discovery found `123` normalized category pages.
- Current configured/root catalog estimate is `41,712` products/listings.
- Full discovered category-listing coverage is `113,265` appearances because many products appear under multiple browse paths.
- Proof job `45` imported `25` products with prices, detail data, and internally stored photos.
- Process lesson: category counts are useful but not always the final SKU count. Vickerman detail pages include `ProductOptions` variants, so the full import should expand those unique variant item numbers.
- Process lesson: the most helpful user-provided data was the actual `productselector/...` URLs, visible listing counts, and screenshots showing count-affecting state like availability and sort mode. Screenshots did not need to cover every page.
- Count lesson: for planning, duplicate category appearances are acceptable. During import, dedupe by supplier plus SKU, store photos once, and merge every discovered browse path into `raw_data.category_tags`.
- Scale lesson: Vickerman runs as a two-pass scrape: first queue unique product detail URLs from category pages, then fetch every product detail. A 1,000-product validation run is long-running, so the full 40k+ catalog should use checkpoint/resume before a full import attempt.
- Current validation run: job `51`, capped at `1,000` unique products, reached the detail-scrape phase without errors. Follow-up queue is image backfill, readiness check, edge-case review, then decide whether to ship full import or build resumable Vickerman runner first.
- Job `51` result: `999` scraped products imported, bringing Vickerman to `1,047` active products. Image backfill stored all `1,047` photos internally after adding Vickerman silhouette `T`-variant fallback images for broken primary image URLs.
- Edge cases from job `51`: `D445001`, `D445011`, and `K201415LEDCC` are missing standardized price because Vickerman returns raw `Price: 0.0`, `SalePrice: null`, and `PricePerPiece: 0.0`. Treat these as supplier data review items, not parser misses.
- Checkpoint runner added after job `51`: Vickerman now has `/api/scraper/vickerman/{supplier_id}/run-until-complete`, `/stop`, and `/status` endpoints. The runner imports in batches, skips active SKUs already in the product table, runs image backfill after each batch, and can be resumed by running it again.
- Checkpoint proof: job `52` ran one 50-product batch after excluding `1,047` already-imported SKUs. It inserted `50` new products, stored `50` new photos, skipped the `1,047` existing photos, and ended with `1,097` active Vickerman products, `1,097` internally stored photos, and `0` image failures.
- Larger checkpoint proof: job `53` ran one 500-product batch after excluding `1,097` already-imported SKUs. It scraped/imported `499` new products, stored `499` new photos, skipped the `1,097` existing photos, and ended with `1,596` active Vickerman products, `1,596` internally stored photos, and `0` image failures. The only standardization blockers remain the same supplier zero-price items: `D445001`, `D445011`, and `K201415LEDCC`.
- Recovery checkpoint: job `54` was created by a 1,000-product run that stalled during import. Resuming `/api/scraper/import` for job `54` completed the saved payload, then image backfill stored all `1,000` photos. Readiness ended at `2,596` active products, `2,596` internally stored photos, and `0` image failures.
- Checkpoint proof: job `55` ran after excluding `2,596` SKUs. It scraped/imported `998` new products, stored `998` new photos, and ended with `3,594` active products, `3,594` internally stored photos, and `0` image failures.
- Recovery checkpoint: the next run hit a transient DNS failure before an import job was created, so the partial scrape could not be reused. Restarting from the last clean checkpoint worked. Process improvement: add mid-scrape checkpointing so a network drop after hundreds of detail pages does not require re-scraping that partial batch.
- Recovery checkpoint: job `56` was created after restarting from `3,594` active products. It stalled during import at partial progress, then manual `/api/scraper/import` resume completed all `888` products. Image backfill stored all `888` new photos, ending with `4,482` active products, `4,482` internally stored photos, and `0` image failures.
- Runner recovery improvement: `/api/scraper/vickerman/run-until-complete/status` and `/start` now reconcile a stale `running` + `stop_requested` state when the current checkpoint job has been manually recovered to `done`. This prevents the runner from getting trapped behind an already-completed job.
- Checkpoint proof: job `57` ran after excluding `4,482` SKUs. It scraped/imported `997` new products, stored `997` new photos, and ended with `5,479` active products, `5,479` internally stored photos, and `0` image failures. Runner automatically started the next batch excluding `5,479` already-imported SKUs.
- Recovery checkpoint: job `58` ran after excluding `5,479` SKUs. It imported `999` new products, then the runner hit a transient DNS error during image backfill. Manual image backfill stored the remaining `130` supplier-hosted photos, ending with `6,478` active products, `6,478` internally stored photos, and `0` image failures. Runner restarted from this clean checkpoint excluding `6,478` already-imported SKUs.
- Checkpoint proof: job `59` ran after excluding `6,478` SKUs. It scraped/imported `999` new products, stored `999` new photos, and ended with `7,477` active products, `7,477` internally stored photos, and `0` image failures. Runner automatically started the next batch excluding `7,477` already-imported SKUs.
- Current live checkpoint, 2026-06-18: runner has imported `10,476` active Vickerman products. Readiness is `99%`: `10,465` products have standardized SKU/name/category/price/UOM, `10,476` have displayable photos/details, and `10,475` photos are stored internally.
- Current runner state: `/api/scraper/vickerman/run-until-complete/status` is `failed` after a transient DNS error while starting batch `5`; it is safe to restart `/api/scraper/vickerman/9/run-until-complete` because the runner excludes already-active SKUs before scraping the next batch.
- Resume attempt, 2026-06-18: restarted `/api/scraper/vickerman/9/run-until-complete?batch_limit=1000&max_batches=37`. Runner entered `running` state and skipped `10,476` already-imported SKUs. First live warning was supplier-side connection closure on category `Trees and Bushes`: `Remote end closed connection without response`. Leave the runner alive while it continues through categories, but treat repeated category disconnects as evidence for adding per-category retry/backoff and mid-batch checkpointing.
- Reliability patch, 2026-06-18: Vickerman category/detail HTTP fetches now retry transient `requests` failures with backoff, failed categories are skipped after retries instead of freezing the batch, and `/status` exposes `category_index`, `category_total`, `category_label`, `category_failures`, and last category/product error fields. After backend restart, the runner moved past the old failure, reached category `104/123`, queued `134` new products, recorded one supplier `500` category failure, and kept scanning instead of stalling.
- Current cleanup queue: review the remaining zero-price/standardization items and retry or mark the one image fallback for SKU `X4K9558F`. Do this in parallel with checkpointed imports unless the failure pattern grows.
- Process improvement to carry forward: the checkpoint runner is good enough to resume at SKU-level checkpoints, but Vickerman still needs mid-batch scrape checkpointing so a DNS drop after hundreds of detail pages does not waste that partial batch.
