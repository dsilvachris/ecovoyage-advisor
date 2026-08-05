-- db/seed.sql
-- STATUS: consolidated seed — 21 cities (12 Europe-focused + 9 across other
-- continents), each with an IATA code for Aviationstack route lookups,
-- transport modes, emission factors, tags, and a starter set of
-- hotels/experiences/offsets. Expand hotel/experience/offset coverage during
-- Task 4.
-- NOTE: ground transport (train/coach/car) is only meaningful for intra-Europe
-- pairs; intercontinental routes are flight-only, computed via haversine at
-- query time — no transport_option rows are needed for those pairs.

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

-- Starter hotels — one eco-certified example per select city, to be expanded in Task 4
INSERT INTO hotel (city_id, name, eco_certification, nightly_price_estimate, sustainability_score, carbon_score) VALUES
((SELECT id FROM city WHERE name = 'Paris'),      'Hôtel Vert Rive Gauche', 'EU Ecolabel', 120.00, 0.85, 0.20),
((SELECT id FROM city WHERE name = 'Amsterdam'),  'Green Canal Lodge',      'Green Key',   95.00,  0.90, 0.15),
((SELECT id FROM city WHERE name = 'Lisbon'),     'Casa Sustentável',       'EU Ecolabel', 80.00,  0.80, 0.25),
((SELECT id FROM city WHERE name = 'Copenhagen'), 'Nordic Eco Stay',        'Green Key',   140.00, 0.92, 0.10),
((SELECT id FROM city WHERE name = 'Cape Town'),  'Table Mountain Eco Lodge', 'Green Key', 90.00,  0.88, 0.22),
((SELECT id FROM city WHERE name = 'Tokyo'),      'Sakura Sustainable Inn', 'EU-equivalent local cert', 110.00, 0.78, 0.30),
((SELECT id FROM city WHERE name = 'Sydney'),     'Harbour Green Stay',     'EarthCheck',  130.00, 0.83, 0.28);

-- Starter experiences
INSERT INTO experience (city_id, name, type, estimated_price, local_community_score) VALUES
((SELECT id FROM city WHERE name = 'Paris'),          'Local co-op food market tour', 'culinary', 25.00, 0.80),
((SELECT id FROM city WHERE name = 'Rome'),           'Community-led history walk',   'cultural', 20.00, 0.85),
((SELECT id FROM city WHERE name = 'Copenhagen'),     'Urban cycling tour',            'nature',   30.00, 0.75),
((SELECT id FROM city WHERE name = 'Nairobi'),        'Community wildlife conservancy visit', 'nature', 40.00, 0.90),
((SELECT id FROM city WHERE name = 'Bangkok'),        'Local floating market tour',    'culinary', 18.00, 0.82),
((SELECT id FROM city WHERE name = 'Rio de Janeiro'), 'Favela community-led tour',     'cultural', 22.00, 0.88);

-- Offset options
INSERT INTO offset_option (provider_name, project_type, estimated_cost_per_tonne) VALUES
('Gold Standard',           'renewable energy', 22.00),
('Verra (VCS)',             'reforestation',    15.00),
('Climate Impact Partners', 'community energy access', 18.50);