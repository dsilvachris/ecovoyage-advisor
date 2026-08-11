-- db/migration_002_add_trip_duration.sql
-- Adds trip_duration_days to trip_session, supporting the new duration
-- question in the trip planning form (FR-01 extension).
--
-- Already applied directly against the live NeonDB. schema.sql has been
-- updated to include this column from the start, so this file is kept
-- only as a record for anyone rebuilding from an older schema.

ALTER TABLE trip_session ADD COLUMN IF NOT EXISTS trip_duration_days INTEGER;