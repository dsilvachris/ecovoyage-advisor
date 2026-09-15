-- db/migration_005_add_city_curated_flag.sql
-- Distinguishes our 21 hand-curated destinations (full eco-certified
-- hotel/experience data) from cities inserted on the fly when a user
-- types somewhere outside that list (resolved via geocoding, footprint-
-- estimate only — no eco-certification data exists for arbitrary cities).
-- Lets the admin console visually separate "real" curated destinations
-- from ad-hoc user-driven entries.

ALTER TABLE city ADD COLUMN IF NOT EXISTS is_curated BOOLEAN NOT NULL DEFAULT FALSE;

-- Mark all 21 originally-seeded cities as curated (they predate this
-- column, so backfill them explicitly rather than relying on insert order).
UPDATE city SET is_curated = TRUE WHERE name IN (
  'London', 'Paris', 'Madrid', 'Rome', 'Berlin', 'Barcelona', 'Amsterdam',
  'Vienna', 'Prague', 'Lisbon', 'Copenhagen', 'Dublin', 'Cape Town',
  'Nairobi', 'Tokyo', 'Bangkok', 'New York', 'Toronto', 'Rio de Janeiro',
  'Bogotá', 'Sydney'
);