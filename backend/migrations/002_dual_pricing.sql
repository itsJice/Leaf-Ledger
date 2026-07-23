-- Dual pricing: store the supplier's retail/list price alongside the dealer
-- (wholesale) price, plus quantity tiers and computed margin. Fully ADDITIVE —
-- only adds nullable columns; touches no existing data.
--
-- Semantics (matches the scrape exports / findings_intake):
--   current_price          = dealer / wholesale price (what Leaf & Ledger pays)
--   list_price             = retail / MSRP / RRP (public list price) when the
--                            supplier exposes one; NULL when only one price exists
--   margin_pct_off_retail  = (list_price - current_price) / list_price * 100
--   price_tiers            = free-text quantity-break pricing (e.g. Regency,
--                            Melrose, Rock Warehouse: "2ST: $10.13 | 8ST: $9.94")
--   list_price_label       = provenance of the list price ("retail_rrp", "retail_msrp", ...)

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS list_price            numeric,
  ADD COLUMN IF NOT EXISTS list_price_label      text,
  ADD COLUMN IF NOT EXISTS margin_pct_off_retail numeric,
  ADD COLUMN IF NOT EXISTS price_tiers           text;
