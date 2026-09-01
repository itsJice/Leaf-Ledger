-- Suppliers carry operational knowledge that lives nowhere on their websites:
-- how fast they actually ship, what terms we're on, our credit line, who to
-- call about what, and how payment actually gets taken. None of it is
-- scrapeable -- a vendor never publishes "we're slow, you'll need to prompt
-- us" -- so these are hand-entered fields the team fills in from experience.
--
-- shipping_speed is a coarse bucket for scanning/filtering; shipping_notes
-- carries the nuance that actually matters operationally ("must prompt them
-- or the order sits"). Kept as plain text rather than a CHECK constraint or
-- enum: the UI dropdown owns the vocabulary, so adding a bucket later is a
-- one-line frontend change instead of another migration + a confusing
-- insert failure for anyone writing to the table directly.
--
-- net_terms is text, not a number -- real terms are messy ("2/10 Net 30",
-- "COD", "Prepay", "Net 30 after first order").
--
-- secondary_contacts follows the exact shape clients already use
-- (010_client_secondary_contacts): a small list edited as a whole array,
-- so a vendor can have an AP person AND a shipping person AND a rep without
-- another migration. `name` is added over the clients version because for a
-- vendor "Bob in AP" is the useful bit, where for a client the label was
-- enough. The existing contact_name/contact_email/contact_phone columns stay
-- as the primary Account Rep -- no rename, no data migration, nothing lost.
--
-- Applied to Supabase on 2026-08-18. Kept here so any rebuilt database gets it.

ALTER TABLE suppliers
    ADD COLUMN IF NOT EXISTS shipping_speed     TEXT,
    ADD COLUMN IF NOT EXISTS shipping_notes     TEXT,
    ADD COLUMN IF NOT EXISTS net_terms          TEXT,
    ADD COLUMN IF NOT EXISTS credit_limit       NUMERIC,
    ADD COLUMN IF NOT EXISTS payment_process    TEXT,
    ADD COLUMN IF NOT EXISTS secondary_contacts JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN suppliers.shipping_speed IS
    'Coarse bucket, vocabulary owned by the UI dropdown: next_day | 2_3_days | about_1_week | 2_weeks_plus | varies. NULL = not yet recorded.';
COMMENT ON COLUMN suppliers.shipping_notes IS
    'Free text nuance, e.g. "ships fast but must be prompted or it sits".';
COMMENT ON COLUMN suppliers.net_terms IS
    'Free text -- real terms are messy: "Net 30", "2/10 Net 30", "COD", "Prepay".';
COMMENT ON COLUMN suppliers.payment_process IS
    'How payment is actually taken, e.g. "site cannot take payment; call in or email to authorize after ordering; card kept on file".';
COMMENT ON COLUMN suppliers.secondary_contacts IS
    'JSONB array of {label, name, phone, email} -- AP / credit / shipping / alternate people beyond the primary rep in contact_*.';
