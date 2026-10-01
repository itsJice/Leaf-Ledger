-- Comments tab: a "What we fixed" note when the owner checks an item off.
--
-- The feedback API (backend/app/apis/feedback) adds these on first use with
-- the identical DDL; this file is the record, so a rebuilt database gets the
-- same columns. resolution_note is shown to everyone who can see the item,
-- unlike Claude's review fields, which only the owner sees.

ALTER TABLE ll_app.feature_requests
    ADD COLUMN IF NOT EXISTS resolution_note  text,
    ADD COLUMN IF NOT EXISTS resolved_by_name text,
    ADD COLUMN IF NOT EXISTS resolved_at      timestamptz;
