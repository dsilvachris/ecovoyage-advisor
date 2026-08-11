-- EcoVoyage Advisor — NeonDB (PostgreSQL) schema
-- STATUS: draft for Phase 1. Run against the NeonDB instance once created.
-- Matches the shape referenced in actions/db.py and actions/repository.py.

CREATE TABLE city (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    country         TEXT NOT NULL,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    iata_code       CHAR(3),                            -- primary airport, used for Aviationstack route lookups
    is_origin       BOOLEAN NOT NULL DEFAULT TRUE,      -- can be selected as an origin
    is_destination  BOOLEAN NOT NULL DEFAULT TRUE       -- can be selected as a destination
);

CREATE TABLE transport_mode (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,               -- flight, train, coach, car
    overhead_hours  NUMERIC(4,2) NOT NULL,               -- fixed time cost (check-in, transfers)
    avg_speed_kmh   NUMERIC(6,2) NOT NULL,
    base_price_eur  NUMERIC(8,2) NOT NULL,
    price_per_km    NUMERIC(8,4) NOT NULL
);

CREATE TABLE emission_factor (
    id                  SERIAL PRIMARY KEY,
    transport_mode_id   INTEGER NOT NULL REFERENCES transport_mode(id),
    kg_co2e_per_pax_km  NUMERIC(8,5) NOT NULL,
    source              TEXT NOT NULL DEFAULT 'stored',  -- 'climatiq' rows are inserted/updated at query time, not seeded
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- NOTE: only seed rows here for train/coach/car — modes that make sense
-- within the same continent/region (mostly intra-Europe for now). For any
-- intercontinental pair, only 'flight' is offered, and its distance is
-- computed on the fly via haversine (great-circle) using city.latitude/
-- longitude — no seed row needed for flights at all.
CREATE TABLE transport_option (
    id                  SERIAL PRIMARY KEY,
    origin_city_id      INTEGER NOT NULL REFERENCES city(id),
    destination_city_id INTEGER NOT NULL REFERENCES city(id),
    transport_mode_id   INTEGER NOT NULL REFERENCES transport_mode(id),
    distance_km         NUMERIC(8,2) NOT NULL,           -- curated fallback distance (used if OpenRouteService is unavailable)
    UNIQUE (origin_city_id, destination_city_id, transport_mode_id)
);

CREATE TABLE hotel (
    id                      SERIAL PRIMARY KEY,
    city_id                 INTEGER NOT NULL REFERENCES city(id),
    name                    TEXT NOT NULL,
    eco_certification       TEXT,                        -- e.g. 'Green Key', 'EU Ecolabel', NULL if none
    nightly_price_estimate  NUMERIC(8,2) NOT NULL,
    sustainability_score    NUMERIC(3,2) NOT NULL,        -- 0.00–1.00, used in the weighted scoring function
    carbon_score            NUMERIC(3,2) NOT NULL         -- 0.00–1.00, lower = better
);

CREATE TABLE experience (
    id                      SERIAL PRIMARY KEY,
    city_id                 INTEGER NOT NULL REFERENCES city(id),
    name                    TEXT NOT NULL,
    type                    TEXT,                         -- e.g. 'cultural', 'nature', 'culinary'
    estimated_price         NUMERIC(8,2) NOT NULL,
    local_community_score   NUMERIC(3,2) NOT NULL         -- 0.00–1.00
);

CREATE TABLE offset_option (
    id                      SERIAL PRIMARY KEY,
    provider_name           TEXT NOT NULL,
    project_type            TEXT NOT NULL,                -- e.g. 'reforestation', 'renewable energy'
    estimated_cost_per_tonne NUMERIC(8,2) NOT NULL
);

CREATE TABLE tag (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE                          -- e.g. 'eco_certified', 'locally_owned', 'low_carbon'
);

CREATE TABLE hotel_tag (
    hotel_id  INTEGER NOT NULL REFERENCES hotel(id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (hotel_id, tag_id)
);

-- Conversation-produced records (written by the chatbot, read by the admin console)

CREATE TABLE trip_session (
    id                  SERIAL PRIMARY KEY,
    sender_id           TEXT NOT NULL,                    -- Rasa conversation id, no PII
    origin_city_id      INTEGER REFERENCES city(id),
    destination_city_id INTEGER REFERENCES city(id),
    travel_date         TEXT,                              -- free text; may be a real date or "flexible"
    trip_duration_days  INTEGER,
    num_travellers      INTEGER,
    budget_tier         TEXT,                              -- 'budget' | 'mid' | 'comfort'
    sustainability_pref TEXT,                              -- 'low_carbon' | 'eco_certified' | 'local_culture' | 'balanced'
    estimated_co2_kg    NUMERIC(10,2),
    carbon_level        TEXT,                              -- 'green' | 'amber' | 'red'
    data_source         TEXT,                              -- 'climatiq' | 'stored'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE handover_log (
    id              SERIAL PRIMARY KEY,
    trip_session_id INTEGER REFERENCES trip_session(id),
    reason          TEXT,                                  -- 'user_requested' | 'fallback_escalation' | 'complex_itinerary'
    context_json    JSONB NOT NULL,                         -- full slot snapshot at handover time
    status          TEXT NOT NULL DEFAULT 'pending',        -- 'pending' | 'resolved'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);

-- Indexes for the lookups the chatbot performs most often
CREATE INDEX idx_transport_option_route ON transport_option(origin_city_id, destination_city_id);
CREATE INDEX idx_hotel_city ON hotel(city_id);
CREATE INDEX idx_experience_city ON experience(city_id);
CREATE INDEX idx_handover_status ON handover_log(status);