-- The install schedule's Area ("North") and Zone ("The Woodlands") as the
-- client sheet / a spreadsheet import gives them (Comment #11 import). The
-- scheduler still derives both from the ZIP (scheduler/prep.py ZIP_ZONE);
-- these keep the spreadsheet's values on the client record. The app adds
-- them itself on first use (app.apis.clients.ensure_schema).
ALTER TABLE clients ADD COLUMN IF NOT EXISTS area text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS zone text;
