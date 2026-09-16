# Additions to `docs/requirements.md`

Append these to the existing FR and NFR lists. Numbering assumes the original
document ends at FR-14 and NFR-09 — adjust if yours differs.

---

## New functional requirements

### FR-15 — Arbitrary destination support

The system shall accept any real city as origin or destination, not only the
21 curated eco-destinations.

**Rationale.** Added after assessor feedback during live demonstration. The
original design fell back to an error whenever a user named a city outside the
curated set, which is unacceptable for a travel assistant — a user cannot be
expected to know which destinations happen to be seeded.

**Implementation.** City names not matching a database row (exact or
typo-corrected) are resolved via the Open-Meteo Geocoding API, returning
coordinates, region and country. Resolved cities are persisted with
`is_curated = FALSE`, de-duplicated against existing rows within a 15 km
radius so repeated use does not accumulate near-duplicate entries.

**Acceptance criteria.**
- Typing a non-curated city (e.g. "Munich") resolves rather than falling back.
- The resolved location is stated back with region and country so the user can
  verify which place was selected.
- Repeated use of the same city reuses the existing row rather than creating
  duplicates.
- Geocoding failure degrades to "city not recognised", not a crash.

---

### FR-16 — Transparent data-quality tiering

The system shall clearly distinguish curated eco-destinations from geocoded
ones, and state plainly what it can and cannot provide for each.

**Rationale.** Eco-certification data (Green Key, EU Ecolabel) is not available
from any open API — it is curated manually. Presenting a geocoded city as
though it had the same verified recommendations would misrepresent the data.
Equally, silently returning nothing would look like a failure rather than a
scoped limitation.

**Implementation.** For non-curated destinations the bot provides the full
carbon footprint estimate and ranked transport comparison, and states
explicitly that verified eco-certified stays are unavailable, offering generic
certification guidance and a route to a human advisor.

**Acceptance criteria.**
- Curated destinations return eco-certified hotels and experiences as before.
- Non-curated destinations return carbon and transport data, plus an explicit
  statement about certification availability.
- The message is phrased as a scoped capability, not an apology or an error.

---

### FR-17 — Ground transport estimation for uncurated routes

For routes under 1500 km with no seeded `transport_option` rows, the system
shall synthesise train, coach and car options from distance and stored emission
factors, rather than presenting flight as the only choice.

**Rationale.** Found during testing of FR-15. A Munich → Zurich trip (278 km)
initially recommended flying, because ground transport only existed for seeded
city pairs. For a tool whose purpose is reducing travel emissions, recommending
a flight for a short rail journey actively undermines its own premise.

**Implementation.** When no ground transport exists for a route and the
straight-line distance is within 1500 km, options are generated from
`transport_mode` and `emission_factor` templates, with distance estimated by
`routing.py`. Synthesised options are labelled in the response as estimated
rather than curated.

**Acceptance criteria.**
- Munich → Zurich (278 km) ranks train first, not flight.
- Synthesised options carry a visible disclaimer distinguishing them from
  curated route data.
- Routes beyond 1500 km remain flight-only, since ground travel ceases to be a
  realistic alternative.

---

## New non-functional requirements

### NFR-10 — Geocoding without additional credentials

The geocoding integration shall not require an API key or account registration.

**Rationale.** Open-Meteo's Geocoding API requires no key, has no per-second
rate limit (unlike OpenCage's free tier, capped at 1 request/second), and
allows 10,000 requests/day. This reduces deployment complexity — one fewer
secret to manage across `.env`, Docker and Cloud Run — and removes a
rate-limiting failure mode under demonstration load.

---

### NFR-11 — Referential integrity for user-generated destinations

Cities created from user input shall integrate with the existing schema without
compromising foreign-key integrity.

**Rationale.** `trip_session` references `city` by foreign key. Introducing
geocoded destinations could have required either a schema change (nullable
coordinates on `trip_session`) or orphaned references. Inserting proper `city`
rows with an `is_curated` flag preserves integrity while keeping the two tiers
distinguishable for reporting and administration.

**Verified.** Attempting to delete a geocoded city referenced by a trip session
is correctly rejected by the database constraint.