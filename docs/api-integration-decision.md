# API integration decisions

STATUS: all four external APIs + NeonDB verified working end-to-end during
Phase 1. Implementation details below are locked in for actions/*.py.

| API | Purpose | Why chosen | Fallback if unavailable |
|---|---|---|---|
| Climatiq | Live carbon-emission factors | Named explicitly in the brief; free tier (~500 calls/month) | Stored emission factors in NeonDB |
| OpenRouteService | Road-routed distance (train/coach/car) | Named explicitly in the brief; free tier (2,000 req/day) | Haversine (great-circle) distance |
| OpenCage | Reverse geocoding / GPS label | Named explicitly in the brief; free tier (2,500 req/day) | Nearest-supported-city match without a friendly label |
| Aviationstack | Real per-route flight sample | Amadeus for Developers sandbox is being decommissioned (2026-07-17); Aviationstack's free tier supports route filtering (dep_iata/arr_iata), confirmed working, so we can show a genuine flight on the user's actual route rather than a generic sample | Transport card omits the live-flight line |
| NeonDB | Primary structured data store | Chosen over local JSON: online storage rather than local files, generous free tier (0.5 GB storage, 100 CU-hours/month, scale-to-zero, no card required) | None — this is the primary store; see docs/deployment.md for what happens if it's briefly unreachable |

## Verified implementation details (from live testing, Phase 1)

**Climatiq**
- Endpoint: `POST https://api.climatiq.io/data/v1/estimate`
- Auth: `Authorization: Bearer <key>`, standard bearer format, no quirks
- Confirmed with a car/100km estimate — response includes `co2e`, `co2e_unit`,
  and rich `emission_factor` metadata (source, year, region) worth surfacing
  in the carbon disclaimer if useful

**OpenRouteService — base URL changed mid-project**
- The brief's suggested domain, `api.openrouteservice.org`, is being
  deprecated in favour of a unified HeiGIT domain. **Use
  `https://api.heigit.org/openrouteservice/v2/directions/driving-car`.**
- Confirmed working with a Paris->Amsterdam test (502.85 km, ~5.4 hours)
- **Coordinate order: `longitude,latitude`** — the opposite of how
  `city.latitude`/`city.longitude` are stored in our schema. `routing.py`
  must swap the order when building the request.
- Response: distance/duration live at `features[0].properties.segments[0]`,
  in **meters** and **seconds** respectively — convert to km when writing to
  `transport_option`/`trip_session`.
- New HeiGIT-issued keys are JWT-shaped (start with `ey`) but are used
  exactly like a normal API key — no special JWT handling needed.

**OpenCage**
- Endpoint: `GET https://api.opencagedata.com/geocode/v1/json?q=<lat>,<lng>&key=<key>`
- **Coordinate order: `latitude,longitude`** — matches our schema directly,
  no swap needed (unlike OpenRouteService — easy to mix these two up).
- Confirmed with Paris coordinates: `confidence: 10`, `results[0].formatted`
  gives a clean human-readable label, `results[0].components.city` gives the
  structured city name to match against our `city` table.
- Recommend only trusting `confidence >= 5` for auto-filling a slot.

**Aviationstack**
- Endpoint: `GET http://api.aviationstack.com/v1/flights` — **HTTP only**,
  the free tier does not support HTTPS. This is a genuine platform
  limitation, not a mistake in our code.
- Confirmed route filtering works on the free tier:
  `?dep_iata=CDG&arr_iata=AMS&limit=1` returned a real scheduled flight.
  This means `aviation.py` can show a genuine flight for the user's actual
  route, not just an illustrative random one.
- Requires each city to have a primary-airport IATA code — added via
  `city.iata_code` (see `db/migration_001_add_iata_code.sql`).
- Lowest quota of the four (500 req/month) — worth caching/rate-limiting
  test calls carefully during development.

## Notes

- All four external APIs are optional at the code level — every custom action
  degrades gracefully (timeout/error/missing key -> stored value / no live
  line), matching the brief's "error-handling for failed API responses"
  requirement.
- Unlike the reference implementation we reviewed (which used NeonDB as a
  fallback tier behind local JSON), we're using NeonDB as the sole primary
  store — a deliberate scope decision given more available time and a
  preference for online rather than local data.
- Two of the four APIs required adapting to a platform change mid-project
  (Amadeus decommissioning -> Aviationstack; api.openrouteservice.org ->
  api.heigit.org) — both are documented here as citable examples of adapting
  to real infrastructure changes, relevant to the report's professional
  documentation criterion.