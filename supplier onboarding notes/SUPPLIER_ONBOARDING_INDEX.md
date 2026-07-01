# Supplier Onboarding Notes Index

## Purpose

This folder is the permanent learning log for supplier onboarding. Every new supplier should get its own note file so catalog acquisition, import, review, and Product Library use get faster and cleaner over time.

Current product direction: Leaf & Ledger is the catalog system of record. It should receive supplier data from supplier exports, PDFs, external scrape exports, or cleaned spreadsheets before we consider building/using portal scraping. See [../CATALOG_DATA_STRATEGY.md](../CATALOG_DATA_STRATEGY.md).

Use [SUPPLIER_ONBOARDING_CHECKLIST.md](SUPPLIER_ONBOARDING_CHECKLIST.md) for the source-first onboarding process. Use [SUPPLIER_CONNECTOR_CONTRACT.md](SUPPLIER_CONNECTOR_CONTRACT.md) for the import shape that every source must produce.

Legacy scraper plans and queue-worker notes remain useful for fallback portal extraction, but they are not the default path for every supplier.

## Canonical Supplier List

Duplicate names should be merged into one clean supplier record before onboarding.

| Wave | Type | Supplier | Notes file | Status |
| --- | --- | --- | --- | --- |
| 0 | Reference | Allstate | [ALLSTATE_ONBOARDING_NOTES.md](ALLSTATE_ONBOARDING_NOTES.md) | Reference complete |
| 1 | Product-heavy florals/decor | Accent Decor | [ACCENT_DECOR_ONBOARDING_NOTES.md](ACCENT_DECOR_ONBOARDING_NOTES.md) | Ready: 2,338 products imported |
| 1 | Product-heavy florals/decor | Vickerman | [VICKERMAN_ONBOARDING_NOTES.md](VICKERMAN_ONBOARDING_NOTES.md) | Checkpointed full catalog in progress |
| 1 | Product-heavy florals/decor | Regency | [REGENCY_ONBOARDING_NOTES.md](REGENCY_ONBOARDING_NOTES.md) | Expanded test import ready |
| 1 | Product-heavy florals/decor | Winward Silks | [WINWARD_SILKS_ONBOARDING_NOTES.md](WINWARD_SILKS_ONBOARDING_NOTES.md) | Not started |
| 1 | Product-heavy florals/decor | Select Artificial | [SELECT_ARTIFICIAL_ONBOARDING_NOTES.md](SELECT_ARTIFICIAL_ONBOARDING_NOTES.md) | Not started |
| 1 | Product-heavy florals/decor | Amazing Green | [AMAZING_GREEN_ONBOARDING_NOTES.md](AMAZING_GREEN_ONBOARDING_NOTES.md) | Not started |
| 1 | Product-heavy florals/decor | American Best | [AMERICAN_BEST_ONBOARDING_NOTES.md](AMERICAN_BEST_ONBOARDING_NOTES.md) | Not started |
| 1 | Product-heavy florals/decor | Autograph Foliages | [AUTOGRAPH_FOLIAGES_ONBOARDING_NOTES.md](AUTOGRAPH_FOLIAGES_ONBOARDING_NOTES.md) | Merge Autograph Foliage/Foliages |
| 1 | Product-heavy florals/decor | Craftex | [CRAFTEX_ONBOARDING_NOTES.md](CRAFTEX_ONBOARDING_NOTES.md) | Merge duplicates |
| 2 | Containers/vases/pottery | Unlimited Container Inc | [UNLIMITED_CONTAINER_INC_ONBOARDING_NOTES.md](UNLIMITED_CONTAINER_INC_ONBOARDING_NOTES.md) | Not started |
| 2 | Containers/vases/pottery | WGV International | [WGV_INTERNATIONAL_ONBOARDING_NOTES.md](WGV_INTERNATIONAL_ONBOARDING_NOTES.md) | Not started |
| 2 | Containers/vases/pottery | At Home | [AT_HOME_ONBOARDING_NOTES.md](AT_HOME_ONBOARDING_NOTES.md) | Not started |
| 2 | Containers/vases/pottery | DFW Glass and Vases | [DFW_GLASS_AND_VASES_ONBOARDING_NOTES.md](DFW_GLASS_AND_VASES_ONBOARDING_NOTES.md) | Not started |
| 2 | Containers/vases/pottery | Jay Scotts | [JAY_SCOTTS_ONBOARDING_NOTES.md](JAY_SCOTTS_ONBOARDING_NOTES.md) | Not started |
| 2 | Containers/vases/pottery | HR Casabella | [HR_CASABELLA_ONBOARDING_NOTES.md](HR_CASABELLA_ONBOARDING_NOTES.md) | Not started |
| 2 | Containers/vases/pottery | Jackson Pottery Inc. | [JACKSON_POTTERY_INC_ONBOARDING_NOTES.md](JACKSON_POTTERY_INC_ONBOARDING_NOTES.md) | Not started |
| 2 | Containers/vases/pottery | PMJC | [PMJC_ONBOARDING_NOTES.md](PMJC_ONBOARDING_NOTES.md) | Not started |
| 3 | Natural/floral support | Supermoss | [SUPERMOSS_ONBOARDING_NOTES.md](SUPERMOSS_ONBOARDING_NOTES.md) | Not started |
| 3 | Natural/floral support | Forest Line | [FOREST_LINE_ONBOARDING_NOTES.md](FOREST_LINE_ONBOARDING_NOTES.md) | Not started |
| 3 | Natural/floral support | Second Flor | [SECOND_FLOR_ONBOARDING_NOTES.md](SECOND_FLOR_ONBOARDING_NOTES.md) | Not started |
| 3 | Natural/floral support | Schusters | [SCHUSTERS_ONBOARDING_NOTES.md](SCHUSTERS_ONBOARDING_NOTES.md) | Not started |
| 4 | Stone/supplies/logistics | The Champion Stone | [THE_CHAMPION_STONE_ONBOARDING_NOTES.md](THE_CHAMPION_STONE_ONBOARDING_NOTES.md) | Not started |
| 4 | Stone/supplies/logistics | The Rock Warehouse | [THE_ROCK_WAREHOUSE_ONBOARDING_NOTES.md](THE_ROCK_WAREHOUSE_ONBOARDING_NOTES.md) | Not started |
| 4 | Stone/supplies/logistics | Sealed Air | [SEALED_AIR_ONBOARDING_NOTES.md](SEALED_AIR_ONBOARDING_NOTES.md) | Not started |
| 4 | Stone/supplies/logistics | Polytek Development | [POLYTEK_DEVELOPMENT_ONBOARDING_NOTES.md](POLYTEK_DEVELOPMENT_ONBOARDING_NOTES.md) | Not started |
| 4 | Stone/supplies/logistics | TQL | [TQL_ONBOARDING_NOTES.md](TQL_ONBOARDING_NOTES.md) | Not started |

## Dedupe Decisions

- `Autograph Foliage` and `Autograph Foliages` should become `Autograph Foliages`.
- `Craftex` should have one supplier record.
- `Regency` should have one supplier record.

## Standard Order

1. Create the supplier intake packet.
2. Ask supplier for a full catalog export, price book, item master, feed, or API access.
3. Check whether PDFs/catalog downloads or existing supplier files can cover the catalog.
4. If no file exists, decide whether to use external scraping, contractor extraction, or portal extraction.
5. Clean supplier record.
6. Add credentials safely in the app only if portal extraction is required.
7. Convert the source into the standard import format.
8. Run one small import test.
9. Preview rows, duplicates, missing fields, images, and pricing.
10. Import.
11. Backfill images/details when needed.
12. Verify Product Library display and search.
13. Verify Builder/project use.
14. Update that supplier note with source type, what worked, what failed, and next season's refresh path.

## Reference Recon Packets

- Regency: [REGENCY_RECON_REPORT.md](REGENCY_RECON_REPORT.md)
- Vickerman: [VICKERMAN_RECON_REPORT.md](VICKERMAN_RECON_REPORT.md)

## Engine Build Plans

- Queue/worker crawl engine fallback: [SUPPLIER_CRAWL_QUEUE_WORKER_PLAN.md](SUPPLIER_CRAWL_QUEUE_WORKER_PLAN.md)
