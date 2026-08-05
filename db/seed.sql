-- db/seed.sql
-- STATUS: initial seed — cities, transport modes, emission factors, tags,
-- and a small starter set of hotels/experiences/offsets per city.
-- Expand hotel/experience/offset coverage during Task 4.

-- Cities (origin + destination both enabled for all, per our current scope)
INSERT INTO city (name, country, latitude, longitude) VALUES
('London', 'United Kingdom', 51.5072, -0.1276),
('Paris', 'France', 48.8566, 2.3522),
('Madrid', 'Spain', 40.4168, -3.7038),
('Rome', 'Italy', 41.9028, 12.4964),
('Berlin', 'Germany', 52.5200, 13.4050),
('Barcelona', 'Spain', 41.3851, 2.1734),
('Amsterdam', 'Netherlands', 52.3676, 4.9041),
('Vienna', 'Austria', 48.2082, 16.3738),
('Prague', 'Czech Republic', 50.0755, 14.4378),
('Lisbon', 'Portugal', 38.7223, -9.1393),
('Copenhagen', 'Denmark', 55.6761, 12.5683),
('Dublin', 'Ireland', 53.3498, -6.2603),
('Cape Town', 'South Africa', -33.9249, 18.4241),
('Nairobi', 'Kenya', -1.2921, 36.8219),
('Tokyo', 'Japan', 35.6762, 139.6503),
('Bangkok', 'Thailand', 13.7563, 100.5018),
('New York', 'United States', 40.7128, -74.0060),
('Toronto', 'Canada', 43.6532, -79.3832),
('Rio de Janeiro', 'Brazil', -22.9068, -43.1729),
('Bogotá', 'Colombia', 4.7110, -74.0721),
('Sydney', 'Australia', -33.8688, 151.2093);

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

-- A small starter set of hotels — one eco-certified example per city, to be expanded
INSERT INTO hotel (city_id, name, eco_certification, nightly_price_estimate, sustainability_score, carbon_score) VALUES
((SELECT id FROM city WHERE name = 'Paris'),      'Hôtel Vert Rive Gauche', 'EU Ecolabel', 120.00, 0.85, 0.20),
((SELECT id FROM city WHERE name = 'Amsterdam'),  'Green Canal Lodge',      'Green Key',   95.00,  0.90, 0.15),
((SELECT id FROM city WHERE name = 'Lisbon'),     'Casa Sustentável',       'EU Ecolabel', 80.00,  0.80, 0.25),
((SELECT id FROM city WHERE name = 'Copenhagen'), 'Nordic Eco Stay',        'Green Key',   140.00, 0.92, 0.10);

-- A small starter set of experiences
INSERT INTO experience (city_id, name, type, estimated_price, local_community_score) VALUES
((SELECT id FROM city WHERE name = 'Paris'),      'Local co-op food market tour', 'culinary', 25.00, 0.80),
((SELECT id FROM city WHERE name = 'Rome'),       'Community-led history walk',   'cultural', 20.00, 0.85),
((SELECT id FROM city WHERE name = 'Copenhagen'), 'Urban cycling tour',            'nature',   30.00, 0.75);

-- Offset options
INSERT INTO offset_option (provider_name, project_type, estimated_cost_per_tonne) VALUES
('Gold Standard',          'renewable energy', 22.00),
('Verra (VCS)',            'reforestation',    15.00),
('Climate Impact Partners', 'community energy access', 18.50);