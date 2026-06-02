# Supplier Onboarding Notes Index

## Purpose

This folder is the permanent learning log for supplier onboarding. Allstate is the reference supplier. Every new supplier should get its own note file so the scraper process gets faster and cleaner over time.

## Canonical Supplier List

Duplicate names should be merged into one clean supplier record before onboarding.

| Wave | Type | Supplier | Notes file | Status |
| --- | --- | --- | --- | --- |
| 0 | Reference | Allstate | [ALLSTATE_ONBOARDING_NOTES.md](ALLSTATE_ONBOARDING_NOTES.md) | Reference complete |
| 1 | Product-heavy florals/decor | Accent Decor | [ACCENT_DECOR_ONBOARDING_NOTES.md](ACCENT_DECOR_ONBOARDING_NOTES.md) | Next |
| 1 | Product-heavy florals/decor | Vickerman | [VICKERMAN_ONBOARDING_NOTES.md](VICKERMAN_ONBOARDING_NOTES.md) | Not started |
| 1 | Product-heavy florals/decor | Regency | [REGENCY_ONBOARDING_NOTES.md](REGENCY_ONBOARDING_NOTES.md) | Not started |
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

1. Clean supplier record.
2. Add credentials safely in the app, never in GitHub.
3. Map login and catalog structure.
4. Cache categories.
5. Run one small selected-category test.
6. Preview.
7. Import.
8. Backfill images/details.
9. Verify Product Library display and search.
10. Update that supplier note with what worked and what failed.

