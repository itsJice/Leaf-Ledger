-- A client's spouse/partner/assistant often has their own phone or email
-- worth having on file -- one column each for phone/email was never going
-- to fit that. secondary_contacts is a small list of {label, phone, email}
-- (label is free text: "Debbie's cell", "Wife", "Assistant" -- whatever the
-- team actually calls that person), edited as a whole array, same as any
-- other client field.
--
-- Applied to Supabase on 2026-08-29. Kept here so any rebuilt database
-- gets it.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS secondary_contacts JSONB NOT NULL DEFAULT '[]'::jsonb;
