-- db/migration_004_add_recommended_mode.sql
-- Adds recommended_mode to trip_session so the admin dashboard can show a
-- transport mode breakdown (flight/train/coach/car) across all trips.
-- The value was always computed in action_recommend_plan (it's already in
-- the recommended_mode SLOT during the conversation) but was never
-- persisted to the database — this closes that gap.

ALTER TABLE trip_session ADD COLUMN IF NOT EXISTS recommended_mode TEXT;