# EcoVoyage Advisor — Conversational Agent for Sustainable Tourism Planning

A Rasa Open Source assistant that plans lower-carbon trips. It runs an adaptive
multi-turn dialogue to collect origin, destination, dates, duration, travellers,
budget and sustainability preference, then estimates the trip's carbon footprint
and returns ranked transport options, eco-certified hotels, local experiences and
carbon offsets — with a human-advisor handover that carries full conversational
context and a trackable query ID.

**Live demo:** https://ecovoyage-advisor-335329881171.europe-west3.run.app/index.html

> First message after a period of inactivity takes ~15–60s while the container
> wakes and loads the trained model. Subsequent messages are fast. This is a
> deliberate trade-off — see [Deployment](#deployment).

MSc Artificial Intelligence — Advanced Conversational UI Design and Chatbot
Development (BSBI / UCA).

---

## Table of contents

- [What it does](#what-it-does)
- [How the bot makes decisions](#how-the-bot-makes-decisions)
- [Curated vs. geocoded destinations](#curated-vs-geocoded-destinations)
- [Feature detail](#feature-detail)
- [Architecture](#architecture)
- [Data model](#data-model)
- [External APIs](#external-apis)
- [Quick start (local)](#quick-start-local)
- [Deployment](#deployment)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Documentation](#documentation)
- [Status and known limitations](#status-and-known-limitations)

---

## What it does

A user describes a trip in conversation. The bot:

1. Collects seven pieces of information through a slot-filling form, accepting
   free text, quick-reply buttons, GPS location, or a guided year/month picker
   for flexible dates.
2. Resolves origin and destination to real places — either one of 21 curated
   eco-destinations, a typo-corrected match, or any other city on earth via
   geocoding.
3. Estimates carbon emissions for every viable transport mode on that route,
   using live emission factors where available.
4. Ranks options against the user's stated priority (lowest carbon,
   eco-certified, local community, or balanced) using a transparent weighted
   score.
5. Returns a plan: ranked transport, eco-certified stays, low-impact
   experiences, and carbon offset providers — flagging high-emission routes
   explicitly.
6. Hands over to a human advisor at any point, capturing the user's name and
   query and returning a real query ID.

Every completed trip is persisted and visible in an admin dashboard.

---

## How the bot makes decisions

Two distinct mechanisms, deliberately separated:

**Conversational decisions (learned, probabilistic).** Rasa's `DIETClassifier`
classifies intent and extracts entities; `RulePolicy`, `TEDPolicy` and
`MemoizationPolicy` then compete to predict the next action. Deterministic flows
(form activation, form submission, human handover, reset) are declared as
**rules** rather than left to policy prediction — a decision driven directly by
debugging experience, documented in `data/rules.yml` and `docs/testing-log.md`.

**Recommendation decisions (deterministic, explainable).** Which transport,
hotel or experience gets recommended is **not** machine learning. It is a
weighted scoring function in `actions/actions.py`:

```
normalise carbon and price to 0–1 across available options
score = (carbon_weight × normalised_carbon) + (price_weight × normalised_price)
lowest score wins
```

Weights by stated priority:

| Priority          | Carbon | Price |
|-------------------|--------|-------|
| `low_carbon`      | 0.80   | 0.20  |
| `eco_certified`   | 0.70   | 0.30  |
| `local_culture`   | 0.50   | 0.50  |
| `balanced`        | 0.50   | 0.50  |

This means "why did it recommend the train?" always has a traceable arithmetic
answer — a deliberate design choice given that opacity is a common and fair
criticism of AI-driven recommendations.

---

## Curated vs. geocoded destinations

The bot handles **any** city, but distinguishes two tiers honestly rather than
implying uniform data quality:

**Curated destinations (21 cities, 6 continents).** Hand-seeded with verified
eco-certified hotels (Green Key, EU Ecolabel, EarthCheck, LEED), low-impact
local experiences, IATA codes, and curated ground-transport distances for
intra-Europe pairs.

**Geocoded destinations (anywhere else).** Resolved live via the Open-Meteo
Geocoding API, inserted into the database on first use (de-duplicated within a
15 km radius, flagged `is_curated = FALSE`). The user gets:

- A full carbon footprint estimate and ranked transport comparison
- Ground transport options synthesised from distance for routes under 1500 km,
  so a 280 km hop correctly recommends rail rather than defaulting to flight
- An explicit statement that eco-certified stays aren't available there, with
  guidance to look for Green Key / EU Ecolabel certification, or to reach a
  human advisor

The resolved location is always stated back with region and country
("📍 I found Zurich, Canton of Zurich, Switzerland") so the user can see which
place was selected.

---

## Feature detail

### Conversation

- **Slot-filling form** — origin, destination, travel date, duration,
  travellers, budget, sustainability preference.
- **Flexible dates** — a guided year → month flow for users without fixed
  plans; past months are filtered out automatically.
- **GPS location** — resolves the user's coordinates to the nearest supported
  city.
- **Typo tolerance** — "Barselona" resolves to Barcelona via string similarity
  against curated city names, scoped so that geocoded cities don't absorb
  typos meant for curated ones.
- **Two-stage fallback** — re-asks the current question in context, then offers
  escalation to a human.
- **Reset** — clears the trip and starts fresh, preserving the completed trip
  in history.

### Recommendations

- **Ranked transport** — up to three modes with distance, price, CO2e and a
  colour-coded carbon level.
- **High-emission alert** — deterministic check on `carbon_level`, fired from
  Python rather than predicted by a policy, so it cannot be silently skipped.
- **Eco-certified stays** — up to three ranked hotels with certification and
  nightly price.
- **Low-impact experiences** — up to two, ranked by community-benefit score.
- **Carbon offsets** — always shown, from real providers (Gold Standard, Verra,
  Climate Impact Partners).
- **Real flight examples** — a live sample flight via Aviationstack when flight
  is the winning mode (called sparingly to respect a 500/month quota).

### Interface

- **Live trip summary panel** — fills in as the conversation progresses.
- **Session trip history** — previously planned trips in a sidebar, each
  replayable as a read-only transcript. Session-scoped by design; the permanent
  record lives in the database.
- **Colour-coded result cards** — transport, stays, experiences and offsets each
  rendered distinctly.
- **Slow-response reassurance** — after 8 seconds, the bot explains it may be
  waking from idle, rather than leaving a silent typing indicator.

### Human handover

Reachable at any point via a header button. Captures name and free-text query,
writes a `handover_log` row with full trip context, and returns the row ID to
the user as a trackable query reference.

### Admin console (`/admin`)

- Six charts: trips per day, carbon-level breakdown, sustainability preference
  distribution, carbon-data-source reliability (live API vs. stored fallback),
  top destinations, recommended transport mode.
- Trips table and handover log with reason classification (user-requested vs.
  fallback escalation).
- Full CRUD for cities, hotels, experiences, offsets and transport options.
- Two authentication layers: nginx HTTP Basic Auth at the network edge, and the
  console's own token-based login underneath.

---

## Architecture

- **Frontend** (`frontend/`) — vanilla JS on Rasa's REST channel. No build step,
  no framework; deliberately simple so the conversational layer is the focus.
- **Admin console** (`admin/`) — vanilla JS + Chart.js, talking to a standalone
  Flask API (`actions/admin_api.py`) on its own port.
- **Rasa NLU + Core** — DIETClassifier pipeline; rules, stories and a
  slot-filling form; `RulePolicy` handles deterministic flows, `TEDPolicy`
  generalises the rest.
- **Custom action server** (`actions/`) — carbon estimation, transport ranking,
  city resolution, recommendation assembly, handover packaging.
- **Database** — NeonDB (serverless PostgreSQL), the sole primary store. No
  local JSON fallback tier.
- **Deployment** — one Docker image running nginx, the Rasa server, the action
  server and the admin API together, on Google Cloud Run.

Full diagram: `docs/architecture_diagram_v2.svg`.

---

## Data model

Eleven tables in NeonDB:

| Table | Purpose |
|---|---|
| `city` | Destinations, with `is_curated` distinguishing hand-seeded from geocoded |
| `transport_mode` | Flight, train, coach, car — with speed, overhead and pricing |
| `emission_factor` | kg CO2e per passenger-km per mode (stored fallback) |
| `transport_option` | Curated distances for specific intra-Europe city pairs |
| `hotel` | Eco-certified stays with sustainability and carbon scores |
| `experience` | Low-impact local activities with community-benefit scores |
| `offset_option` | Carbon offset providers and per-tonne pricing |
| `tag`, `hotel_tag` | Sustainability tagging |
| `trip_session` | Every completed trip, including recommended mode and data source |
| `handover_log` | Human-advisor requests with full trip context as JSON |

Schema in `db/schema.sql`, canonical data in `db/seed.sql`, incremental changes
in `db/migration_*.sql`.

---

## External APIs

| API | Purpose | Key required | Fallback if unavailable |
|---|---|---|---|
| **Climatiq** | Live carbon emission factors | Yes | Stored factors from `emission_factor` |
| **Open-Meteo Geocoding** | Resolving arbitrary city names | No | City treated as unrecognised |
| **OpenRouteService** | Road routing distances | Yes | Haversine distance estimate |
| **OpenCage** | Reverse geocoding for GPS labels | Yes | Nearest-city match without label |
| **Aviationstack** | Real flight examples | Yes | Omitted from the response |

Every integration degrades gracefully — no API failure breaks the conversation.
See `docs/api-integration-decision.md` for endpoint choices, coordinate-order
gotchas, and two mid-project platform changes that had to be accommodated.

---

## Quick start (local)

Rasa 3.6.x requires **Python 3.10**.

```bash
python3.10 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env             # fill in API keys and NEON_DATABASE_URL
rasa train
```

Then, in separate terminals — each needs the environment loaded first
(`export $(grep -v '^#' .env | xargs)`), or database calls silently return empty:

```bash
rasa run actions                            # action server, port 5055
rasa run --enable-api --cors "*"            # Rasa server, port 5005
python3 -m actions.admin_api                # admin API, port 5002
cd frontend && python3 -m http.server 8080  # chat UI
```

**Local testing note:** `frontend/index.html`'s `REST_ENDPOINT` and
`admin/index.html`'s `API_BASE` use `window.location.origin`, which only
resolves behind nginx. For local testing, point them at
`http://localhost:5005/webhooks/rest/webhook` and `http://localhost:5002/api`
respectively — **and revert before committing**.

---

## Deployment

One Docker image (nginx + Rasa + action server + admin API) on **Google Cloud
Run**.

**Why Cloud Run:** access is sparse and unpredictable — testers and assessors
arrive at unknown times over months. Scale-to-zero means no cost while idle and
no server to remember to start. The trade-off is a cold start on the first
request after inactivity; `deploy/start.sh` polls Rasa's `/status` endpoint
before starting nginx, so requests are never routed to a half-started model.

Two non-obvious requirements, both found through failed deployments:

- `--no-cpu-throttling` is **required** — Cloud Run otherwise starves the
  background Rasa process during startup.
- `--memory=2Gi --cpu=2` minimum; the default allocation cannot load the model.

```bash
docker compose up --build   # local, http://localhost:8080

gcloud builds submit --tag <artifact-registry-path>
gcloud run deploy ecovoyage-advisor --image=<artifact-registry-path> ...
```

Full commands, IAM prerequisites and troubleshooting: `docs/deployment.md`.

---

## Project structure

```
ecovoyage-advisor/
├── actions/          # Custom Rasa actions, NeonDB access, API clients, admin API
│   ├── actions.py    # All custom actions and form validation
│   ├── carbon.py     # Climatiq integration + stored-factor fallback
│   ├── routing.py    # OpenRouteService + haversine fallback
│   ├── geo.py        # GPS resolution, typo matching, forward geocoding
│   ├── aviation.py   # Aviationstack with in-process caching
│   ├── db.py         # Connection pooling
│   ├── repository.py # Data access layer
│   └── admin_api.py  # Standalone Flask admin API
├── data/             # NLU training data, stories, rules
├── frontend/         # Chat UI (vanilla JS)
├── admin/            # Admin console UI
├── db/               # Schema, canonical seed data, migrations
├── deploy/           # nginx config template, container startup script
├── tests/            # pytest unit tests + rasa test stories
├── docs/             # Requirements, deployment, API decisions, dialogue flows, testing log
├── config.yml        # NLU pipeline + policies
├── domain.yml        # Intents, entities, slots, forms, responses
├── endpoints.yml     # Action server endpoint
├── credentials.yml   # Channel config (REST)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Testing

```bash
rasa test nlu --cross-validation    # NLU cross-validation
rasa test core --stories tests/test_stories/test_stories.yml
pytest tests/                       # unit tests with mocked external APIs
```

Current state: **23/23 unit tests passing, 10/10 test stories passing.**

`docs/testing-log.md` documents the full testing history — including a dozen
real bugs found through live scenario testing, each with its diagnosis and fix.
Several stemmed from genuine Rasa policy-layer behaviour rather than application
logic, and are written up as such for the report's critical evaluation.

---

## Documentation

| Document | Contents |
|---|---|
| `docs/requirements.md` | Functional (FR-01…16) and non-functional (NFR-01…09) requirements |
| `docs/dialogue-flows.md` | Seven documented conversation scenarios |
| `docs/api-integration-decision.md` | API selection rationale and integration gotchas |
| `docs/deployment.md` | Cloud Run deployment guide and troubleshooting |
| `docs/testing-log.md` | Testing history, bug diagnoses, deferred features |
| `docs/architecture_diagram_v2.svg` | System architecture diagram |

---

## Status and known limitations

**Complete and deployed.** Core conversation, recommendations, geocoding,
admin console, and deployment are all live and tested.

**Known limitations, each documented with reasoning in `docs/testing-log.md`:**

- **Inline editing of answers** was removed from the summary panel. The
  underlying `edit_answer` flow works via typed input, but a narrow
  "edit-then-immediately-re-answer" case proved unreliable at the policy layer
  and the UI affordance was withdrawn rather than shipped rough.
- **Button-based disambiguation** for ambiguous city names (Springfield, MO vs.
  IL vs. MA) was built and verified at the action level, but Rasa discards
  messages dispatched from a slot-extraction method that doesn't fill its slot.
  Four mitigations were attempted and measured; the feature was withdrawn in
  favour of stating the resolved location back to the user with full region and
  country context.
- **Eco-certification data is curated, not live.** No open API provides
  eco-certification status for hotels — it belongs to booking-system partners.
  Non-curated destinations therefore get footprint estimation without verified
  stays, stated explicitly rather than implied.
- **Emission factors come from Climatiq where available**, which can produce
  mode rankings that differ from generic published averages (coach is not
  always lower-carbon than rail in Climatiq's regional data).
- **Secrets are passed as environment variables** on the Cloud Run deploy
  command. Acceptable for coursework; production would use Secret Manager.

**Remaining:** final report write-up.

See commit history for phase-by-phase progress.