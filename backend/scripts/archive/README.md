# Archived one-off scripts

These scripts were one-time data migrations or backfills. Each has already
run against the production database; they are kept here for reference only,
not for reuse.

- **backfill_dual_pricing.py** — Promotes dual-pricing values (`list_price`,
  `list_price_label`, `margin_pct_off_retail`, `price_tiers`) out of
  `raw_data` and into their real columns now that migration 002 is applied.
  Already run; kept for reference.
- **backfill_ident_norm.py** — Backfills `product_facets.ident_norm` for
  migration 011. Already run; kept for reference.
- **normalize_containers.py** — Phase 0 normalization of the
  arrangement/container data model (migration 004): splits designs and rooms
  out of the overloaded `arrangement_containers.label` column and re-points
  design room references at `project_rooms.id`. Already run; kept for
  reference.
- **reclassify_build_types.py** — Recomputes `historical_recipes.build_type`
  with the corrected classifier logic in `app.libs.recipe_intake` (fixed
  vessel-negation matching and added missing species keywords). Already run;
  kept for reference.
- **load_burtonandburton_chunked.py** — One-time chunked import of the
  `BurtonAndBurton_Catalog_2026.xlsx` findings file into `products`, using a
  fresh connection per chunk to survive Supabase pooler drops. Already run;
  kept for reference.
