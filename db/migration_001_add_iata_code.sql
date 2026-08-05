-- db/migration_001_add_iata_code.sql
-- Added after initial schema+seed: Aviationstack's free tier supports
-- dep_iata/arr_iata route filtering (confirmed working), so real per-route
-- flights can be shown instead of a generic sample flight. Requires each
-- city's primary airport IATA code.
--
-- Already applied directly against the live NeonDB during Phase 1 API
-- testing. schema.sql and seed.sql (in this same folder) have since been
-- updated to include iata_code from the start, so this file is kept only
-- as a record of the change for anyone re-running against an older DB.

ALTER TABLE city ADD COLUMN IF NOT EXISTS iata_code CHAR(3);

UPDATE city SET iata_code = 'LHR' WHERE name = 'London';
UPDATE city SET iata_code = 'CDG' WHERE name = 'Paris';
UPDATE city SET iata_code = 'MAD' WHERE name = 'Madrid';
UPDATE city SET iata_code = 'FCO' WHERE name = 'Rome';
UPDATE city SET iata_code = 'BER' WHERE name = 'Berlin';
UPDATE city SET iata_code = 'BCN' WHERE name = 'Barcelona';
UPDATE city SET iata_code = 'AMS' WHERE name = 'Amsterdam';
UPDATE city SET iata_code = 'VIE' WHERE name = 'Vienna';
UPDATE city SET iata_code = 'PRG' WHERE name = 'Prague';
UPDATE city SET iata_code = 'LIS' WHERE name = 'Lisbon';
UPDATE city SET iata_code = 'CPH' WHERE name = 'Copenhagen';
UPDATE city SET iata_code = 'DUB' WHERE name = 'Dublin';
UPDATE city SET iata_code = 'CPT' WHERE name = 'Cape Town';
UPDATE city SET iata_code = 'NBO' WHERE name = 'Nairobi';
UPDATE city SET iata_code = 'HND' WHERE name = 'Tokyo';
UPDATE city SET iata_code = 'BKK' WHERE name = 'Bangkok';
UPDATE city SET iata_code = 'JFK' WHERE name = 'New York';
UPDATE city SET iata_code = 'YYZ' WHERE name = 'Toronto';
UPDATE city SET iata_code = 'GIG' WHERE name = 'Rio de Janeiro';
UPDATE city SET iata_code = 'BOG' WHERE name = 'Bogotá';
UPDATE city SET iata_code = 'SYD' WHERE name = 'Sydney';