-- Let a client have more than one freeform comment.
--
-- client_activity's unique index was (client_id, kind, season) -- exactly
-- right for "one Christmas-install row per season," wrong for comments:
-- a second comment added the same day (same client, kind='comment', and
-- whatever season-ish tag a comment gets) would collide with the first
-- and either fail or silently overwrite it, depending on how the insert
-- was written. Comments aren't season-scoped at all, so they're excluded
-- from that constraint entirely rather than needing a workaround value.
--
-- Applied to Supabase on 2026-08-29. Kept here so any rebuilt database
-- gets it.

DROP INDEX IF EXISTS client_activity_unique_season;

CREATE UNIQUE INDEX IF NOT EXISTS client_activity_unique_season
    ON client_activity (client_id, kind, season)
    WHERE kind <> 'comment';
