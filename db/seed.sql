-- db/seed.sql
-- STATUS: consolidated seed — 21 cities (12 Europe-focused + 9 across other
-- continents), each with an IATA code for Aviationstack route lookups,
-- transport modes, emission factors, tags, curated ground-transport
-- distances for a spread of intra-Europe pairs, a full hotel+experience
-- for every city, and offset options. Expand further as needed.
-- NOTE: ground transport (train/coach/car) is only meaningful for intra-Europe
-- pairs; intercontinental routes are flight-only, computed via haversine at
-- query time — no transport_option rows are needed for those pairs.
-- NOTE: hotel/experience coverage was originally sparse (7/21 cities had a
-- hotel, 6/21 had an experience) — a real gap found via the admin console's
-- reference-data view during Phase 3. Every city now has at least one of
-- each (migration_003_expand_hotels_experiences.sql, folded in here).

-- Cities (Europe-focused set)
INSERT INTO city (name, country, latitude, longitude, iata_code) VALUES
('London', 'United Kingdom', 51.5072, -0.1276, 'LHR'),
('Paris', 'France', 48.8566, 2.3522, 'CDG'),
('Madrid', 'Spain', 40.4168, -3.7038, 'MAD'),
('Rome', 'Italy', 41.9028, 12.4964, 'FCO'),
('Berlin', 'Germany', 52.5200, 13.4050, 'BER'),
('Barcelona', 'Spain', 41.3851, 2.1734, 'BCN'),
('Amsterdam', 'Netherlands', 52.3676, 4.9041, 'AMS'),
('Vienna', 'Austria', 48.2082, 16.3738, 'VIE'),
('Prague', 'Czech Republic', 50.0755, 14.4378, 'PRG'),
('Lisbon', 'Portugal', 38.7223, -9.1393, 'LIS'),
('Copenhagen', 'Denmark', 55.6761, 12.5683, 'CPH'),
('Dublin', 'Ireland', 53.3498, -6.2603, 'DUB');

-- Additional cities — one/two per other continent
INSERT INTO city (name, country, latitude, longitude, iata_code) VALUES
('Cape Town', 'South Africa', -33.9249, 18.4241, 'CPT'),
('Nairobi', 'Kenya', -1.2921, 36.8219, 'NBO'),
('Tokyo', 'Japan', 35.6762, 139.6503, 'HND'),
('Bangkok', 'Thailand', 13.7563, 100.5018, 'BKK'),
('New York', 'United States', 40.7128, -74.0060, 'JFK'),
('Toronto', 'Canada', 43.6532, -79.3832, 'YYZ'),
('Rio de Janeiro', 'Brazil', -22.9068, -43.1729, 'GIG'),
('Bogotá', 'Colombia', 4.7110, -74.0721, 'BOG'),
('Sydney', 'Australia', -33.8688, 151.2093, 'SYD');

-- Transport modes
INSERT INTO transport_mode (name, overhead_hours, avg_speed_kmh, base_price_eur, price_per_km) VALUES
('flight', 2.5, 700, 40.00, 0.09),
('train',  0.5, 140,  15.00, 0.06),
('coach',  0.5,  70,  10.00, 0.03),
('car',    0.25, 90,   0.00, 0.12);

-- Emission factors (kg CO2e per passenger-km) — indicative figures, cite
-- DEFRA/ICAO in the report as the authoritative source per NFR-08
INSERT INTO emission_factor (transport_mode_id, kg_co2e_per_pax_km, source) VALUES
((SELECT id FROM transport_mode WHERE name = 'flight'), 0.246, 'stored'),
((SELECT id FROM transport_mode WHERE name = 'train'),  0.041, 'stored'),
((SELECT id FROM transport_mode WHERE name = 'coach'),  0.029, 'stored'),
((SELECT id FROM transport_mode WHERE name = 'car'),    0.171, 'stored');

-- Sustainability tags
INSERT INTO tag (name) VALUES
('eco_certified'),
('locally_owned'),
('low_carbon'),
('community_supporting');

-- Ground transport (train/coach/car) for a spread of intra-Europe pairs.
INSERT INTO transport_option (origin_city_id, destination_city_id, transport_mode_id, distance_km)
SELECT o.id, d.id, tm.id, v.distance_km FROM (VALUES
    -- London <-> Paris (Scenario 1)
    ('London','Paris','train',495.0),
    ('London','Paris','coach',460.0),
    ('London','Paris','car',460.0),
    ('Paris','London','train',495.0),
    ('Paris','London','coach',460.0),
    ('Paris','London','car',460.0),

    -- Berlin <-> Copenhagen (Scenario 3)
    ('Berlin','Copenhagen','train',360.0),
    ('Berlin','Copenhagen','coach',355.0),
    ('Berlin','Copenhagen','car',355.0),
    ('Copenhagen','Berlin','train',360.0),
    ('Copenhagen','Berlin','coach',355.0),
    ('Copenhagen','Berlin','car',355.0),

    -- Madrid <-> Barcelona
    ('Madrid','Barcelona','train',505.0),
    ('Madrid','Barcelona','coach',620.0),
    ('Madrid','Barcelona','car',620.0),
    ('Barcelona','Madrid','train',505.0),
    ('Barcelona','Madrid','coach',620.0),
    ('Barcelona','Madrid','car',620.0),

    -- Paris <-> Amsterdam
    ('Paris','Amsterdam','train',430.0),
    ('Paris','Amsterdam','coach',510.0),
    ('Paris','Amsterdam','car',510.0),
    ('Amsterdam','Paris','train',430.0),
    ('Amsterdam','Paris','coach',510.0),
    ('Amsterdam','Paris','car',510.0),

    -- Berlin <-> Prague
    ('Berlin','Prague','train',350.0),
    ('Berlin','Prague','coach',350.0),
    ('Berlin','Prague','car',350.0),
    ('Prague','Berlin','train',350.0),
    ('Prague','Berlin','coach',350.0),
    ('Prague','Berlin','car',350.0),

    -- Vienna <-> Prague
    ('Vienna','Prague','train',330.0),
    ('Vienna','Prague','coach',330.0),
    ('Vienna','Prague','car',330.0),
    ('Prague','Vienna','train',330.0),
    ('Prague','Vienna','coach',330.0),
    ('Prague','Vienna','car',330.0),

    -- London <-> Amsterdam
    ('London','Amsterdam','train',490.0),
    ('London','Amsterdam','coach',540.0),
    ('London','Amsterdam','car',540.0),
    ('Amsterdam','London','train',490.0),
    ('Amsterdam','London','coach',540.0),
    ('Amsterdam','London','car',540.0),

    -- Dublin <-> London
    ('Dublin','London','coach',600.0),
    ('Dublin','London','car',600.0),
    ('London','Dublin','coach',600.0),
    ('London','Dublin','car',600.0),

    -- Lisbon <-> Madrid
    ('Lisbon','Madrid','train',660.0),
    ('Lisbon','Madrid','coach',630.0),
    ('Lisbon','Madrid','car',630.0),
    ('Madrid','Lisbon','train',660.0),
    ('Madrid','Lisbon','coach',630.0),
    ('Madrid','Lisbon','car',630.0),

    -- Rome <-> Barcelona
    ('Rome','Barcelona','coach',1250.0),
    ('Rome','Barcelona','car',1250.0),
    ('Barcelona','Rome','coach',1250.0),
    ('Barcelona','Rome','car',1250.0)
) AS v(origin, destination, mode, distance_km)
JOIN city o ON o.name = v.origin
JOIN city d ON d.name = v.destination
JOIN transport_mode tm ON tm.name = v.mode;

-- Hotels — full coverage, all 21 cities. Originally only 7/21 had a hotel;
-- expanded via migration_003 after the gap was found through the admin
-- console's reference-data view.
INSERT INTO hotel (city_id, name, eco_certification, nightly_price_estimate, sustainability_score, carbon_score)
SELECT c.id, v.name, v.cert, v.price, v.sustain, v.carbon
FROM (VALUES
    ('Paris',          'Hôtel Vert Rive Gauche',       'EU Ecolabel',           120.00, 0.85, 0.20),
    ('Amsterdam',       'Green Canal Lodge',            'Green Key',             95.00,  0.90, 0.15),
    ('Lisbon',          'Casa Sustentável',              'EU Ecolabel',           80.00,  0.80, 0.25),
    ('Copenhagen',      'Nordic Eco Stay',               'Green Key',            140.00, 0.92, 0.10),
    ('Cape Town',       'Table Mountain Eco Lodge',      'Green Key',             90.00,  0.88, 0.22),
    ('Tokyo',           'Sakura Sustainable Inn',        'EU-equivalent local cert', 110.00, 0.78, 0.30),
    ('Sydney',          'Harbour Green Stay',            'EarthCheck',           130.00, 0.83, 0.28),
    ('London',          'Camden Green House',            'EU Ecolabel',          145.00, 0.86, 0.24),
    ('London',          'Shoreditch Budget Green',       NULL,                    78.00, 0.68, 0.35),
    ('Madrid',          'Hostal Verde Centro',           'EU Ecolabel',           88.00, 0.79, 0.27),
    ('Rome',            'Roma Sostenibile',              'EU Ecolabel',          105.00, 0.81, 0.26),
    ('Berlin',          'Kreuzberg Eco Rooms',           'Green Key',             92.00, 0.87, 0.19),
    ('Berlin',          'Mitte Budget Eco',              NULL,                    65.00, 0.70, 0.33),
    ('Barcelona',       'Casa Verda Gracia',             'EU Ecolabel',           98.00, 0.82, 0.23),
    ('Vienna',          'Wien Grün Hotel',               'Green Key',            115.00, 0.84, 0.21),
    ('Prague',          'Praha Eco Stay',                'Green Key',             75.00, 0.80, 0.28),
    ('Dublin',          'Liffey Green Lodge',            'EU Ecolabel',          100.00, 0.78, 0.29),
    ('Nairobi',         'Karen Eco Retreat',             'EarthCheck',            70.00, 0.89, 0.18),
    ('Nairobi',         'CBD Green Budget Inn',          NULL,                    42.00, 0.65, 0.36),
    ('Bangkok',         'Sukhumvit Green Stay',          'Green Key',             55.00, 0.76, 0.31),
    ('New York',        'Brooklyn Eco Loft',             'LEED Certified',       190.00, 0.74, 0.33),
    ('Toronto',         'Distillery Green Inn',          'LEED Certified',       135.00, 0.83, 0.25),
    ('Rio de Janeiro',  'Ipanema Eco Pousada',           'EarthCheck',            85.00, 0.77, 0.30),
    ('Bogotá',          'Chapinero Verde',               'Green Key',             60.00, 0.81, 0.27)
) AS v(city, name, cert, price, sustain, carbon)
JOIN city c ON c.name = v.city;

-- Experiences — full coverage, all 21 cities. Same gap/fix history as hotels.
INSERT INTO experience (city_id, name, type, estimated_price, local_community_score)
SELECT c.id, v.name, v.type, v.price, v.score
FROM (VALUES
    ('Paris',           'Local co-op food market tour',            'culinary', 25.00, 0.80),
    ('Rome',            'Community-led history walk',               'cultural', 20.00, 0.85),
    ('Copenhagen',      'Urban cycling tour',                        'nature',   30.00, 0.75),
    ('Nairobi',         'Community wildlife conservancy visit',      'nature',   40.00, 0.90),
    ('Bangkok',         'Local floating market tour',                'culinary', 18.00, 0.82),
    ('Rio de Janeiro',  'Favela community-led tour',                 'cultural', 22.00, 0.88),
    ('London',          'East End community market walk',           'cultural', 20.00, 0.79),
    ('Madrid',          'Local tapas & vermouth crawl',              'culinary', 28.00, 0.81),
    ('Berlin',          'Kreuzberg street art & community tour',     'cultural', 18.00, 0.83),
    ('Barcelona',       'Gràcia neighbourhood co-op tour',           'cultural', 22.00, 0.84),
    ('Amsterdam',       'Canal-side community garden visit',         'nature',   15.00, 0.80),
    ('Vienna',          'Naschmarkt local producers tour',           'culinary', 24.00, 0.78),
    ('Prague',          'Old Town community-led walk',               'cultural', 16.00, 0.82),
    ('Lisbon',          'Alfama fado & local eats tour',             'culinary', 26.00, 0.85),
    ('Dublin',          'Liberties community history walk',          'cultural', 18.00, 0.80),
    ('Cape Town',       'Bo-Kaap community cooking class',           'culinary', 35.00, 0.90),
    ('Tokyo',           'Yanaka local shotengai walk',                'cultural', 20.00, 0.77),
    ('New York',        'Queens community food tour',                'culinary', 45.00, 0.83),
    ('Toronto',         'Kensington Market co-op tour',               'cultural', 25.00, 0.81),
    ('Bogotá',          'La Candelaria community art walk',          'cultural', 15.00, 0.86),
    ('Sydney',          'Bondi community beach cleanup + tour',      'nature',   12.00, 0.88)
) AS v(city, name, type, price, score)
JOIN city c ON c.name = v.city;

-- Offset options — global providers, not destination-specific, so a small
-- fixed set is correct coverage rather than a gap.
INSERT INTO offset_option (provider_name, project_type, estimated_cost_per_tonne) VALUES
('Gold Standard',           'renewable energy', 22.00),
('Verra (VCS)',             'reforestation',    15.00),
('Climate Impact Partners', 'community energy access', 18.50);