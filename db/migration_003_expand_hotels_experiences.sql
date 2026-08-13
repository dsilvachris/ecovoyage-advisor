-- db/migration_003_expand_hotels_experiences.sql
-- Fills a real coverage gap surfaced via the admin console: only 7/21
-- cities had a seeded hotel, and only 6/21 had a seeded experience,
-- meaning most destinations fell back to "I don't have curated hotel
-- data yet" regardless of how good a match they'd otherwise be. Adds at
-- least one hotel and one experience for every remaining city, plus a
-- second hotel for a few cities used in our documented test scenarios
-- (London, Berlin, Nairobi) so FR-06's ranking logic has something
-- genuinely visible to rank, not just a single option by default.

-- Hotels for the 14 cities that had none
INSERT INTO hotel (city_id, name, eco_certification, nightly_price_estimate, sustainability_score, carbon_score)
SELECT c.id, v.name, v.cert, v.price, v.sustain, v.carbon
FROM (VALUES
    ('London', 'Camden Green House', 'EU Ecolabel', 145.00, 0.86, 0.24),
    ('Madrid', 'Hostal Verde Centro', 'EU Ecolabel', 88.00, 0.79, 0.27),
    ('Rome', 'Roma Sostenibile', 'EU Ecolabel', 105.00, 0.81, 0.26),
    ('Berlin', 'Kreuzberg Eco Rooms', 'Green Key', 92.00, 0.87, 0.19),
    ('Barcelona', 'Casa Verda Gracia', 'EU Ecolabel', 98.00, 0.82, 0.23),
    ('Vienna', 'Wien Grün Hotel', 'Green Key', 115.00, 0.84, 0.21),
    ('Prague', 'Praha Eco Stay', 'Green Key', 75.00, 0.80, 0.28),
    ('Dublin', 'Liffey Green Lodge', 'EU Ecolabel', 100.00, 0.78, 0.29),
    ('Nairobi', 'Karen Eco Retreat', 'EarthCheck', 70.00, 0.89, 0.18),
    ('Bangkok', 'Sukhumvit Green Stay', 'Green Key', 55.00, 0.76, 0.31),
    ('New York', 'Brooklyn Eco Loft', 'LEED Certified', 190.00, 0.74, 0.33),
    ('Toronto', 'Distillery Green Inn', 'LEED Certified', 135.00, 0.83, 0.25),
    ('Rio de Janeiro', 'Ipanema Eco Pousada', 'EarthCheck', 85.00, 0.77, 0.30),
    ('Bogotá', 'Chapinero Verde', 'Green Key', 60.00, 0.81, 0.27)
) AS v(city, name, cert, price, sustain, carbon)
JOIN city c ON c.name = v.city;

-- A second hotel each for London, Berlin, Nairobi — gives ranking (FR-06)
-- something to actually differentiate on for the routes used in our
-- documented dialogue-flow scenarios.
INSERT INTO hotel (city_id, name, eco_certification, nightly_price_estimate, sustainability_score, carbon_score)
SELECT c.id, v.name, v.cert, v.price, v.sustain, v.carbon
FROM (VALUES
    ('London', 'Shoreditch Budget Green', NULL, 78.00, 0.68, 0.35),
    ('Berlin', 'Mitte Budget Eco', NULL, 65.00, 0.70, 0.33),
    ('Nairobi', 'CBD Green Budget Inn', NULL, 42.00, 0.65, 0.36)
) AS v(city, name, cert, price, sustain, carbon)
JOIN city c ON c.name = v.city;

-- Experiences for the 15 cities that had none
INSERT INTO experience (city_id, name, type, estimated_price, local_community_score)
SELECT c.id, v.name, v.type, v.price, v.score
FROM (VALUES
    ('London', 'East End community market walk', 'cultural', 20.00, 0.79),
    ('Madrid', 'Local tapas & vermouth crawl', 'culinary', 28.00, 0.81),
    ('Berlin', 'Kreuzberg street art & community tour', 'cultural', 18.00, 0.83),
    ('Barcelona', 'Gràcia neighbourhood co-op tour', 'cultural', 22.00, 0.84),
    ('Amsterdam', 'Canal-side community garden visit', 'nature', 15.00, 0.80),
    ('Vienna', 'Naschmarkt local producers tour', 'culinary', 24.00, 0.78),
    ('Prague', 'Old Town community-led walk', 'cultural', 16.00, 0.82),
    ('Lisbon', 'Alfama fado & local eats tour', 'culinary', 26.00, 0.85),
    ('Dublin', 'Liberties community history walk', 'cultural', 18.00, 0.80),
    ('Cape Town', 'Bo-Kaap community cooking class', 'culinary', 35.00, 0.90),
    ('Tokyo', 'Yanaka local shotengai walk', 'cultural', 20.00, 0.77),
    ('New York', 'Queens community food tour', 'culinary', 45.00, 0.83),
    ('Toronto', 'Kensington Market co-op tour', 'cultural', 25.00, 0.81),
    ('Bogotá', 'La Candelaria community art walk', 'cultural', 15.00, 0.86),
    ('Sydney', 'Bondi community beach cleanup + tour', 'nature', 12.00, 0.88)
) AS v(city, name, type, price, score)
JOIN city c ON c.name = v.city;