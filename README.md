# EcoVoyage Advisor — Conversational Agent for Sustainable Tourism Planning

A Rasa Open Source assistant that plans lower-carbon trips: it runs an adaptive
multi-turn dialogue to collect origin, destination, dates, duration, budget and
sustainability preference, then recommends ranked eco-certified hotels,
transport options, local experiences and carbon offsets, estimates the trip's
carbon footprint, and hands over to a human advisor with full conversational
context and a trackable query ID.

**Live demo:** https://ecovoyage-advisor-335329881171.europe-west3.run.app/index.html

MSc Artificial Intelligence — Advanced Conversational UI Design and Chatbot
Development (BSBI / UCA).

## Feature overview

- **Multi-turn trip planning form** — origin, destination, dates (including a
  guided year/month flow for flexible travellers), duration, travellers,
  budget, sustainability preference — with GPS-based location detection and a
  city picker covering 21 destinations across 6 continents.
- **Weighted recommendations** — ranked transport options (flight/train/coach/
  car, with live carbon data from Climatiq where available), ranked
  eco-certified hotels, local experiences, and carbon offset options, scored
  per FR-06's weighting scheme against the user's stated priority.
- **High-emission alerts** — a deterministic, always-reliable check (not
  policy-dependent) flags red-carbon routes and always surfaces offset options.
- **Trip history** — a session-scoped sidebar of previously planned trips,
  each replayable as a read-only transcript; the full permanent history lives
  in NeonDB and is visible via the admin console regardless.
- **Human advisor handover** — reachable at any point in the conversation via
  an always-visible button, captures a name and query, and returns a real,
  trackable query ID tied to the `handover_log` table.
- **Admin console** (`/admin`) — a dashboard covering trip volume, carbon-level
  breakdown, sustainability preference distribution, carbon-data-source
  reliability (live API vs. stored fallback), top destinations, transport mode
  breakdown, a full trips/handovers table, and CRUD management for all
  reference data (cities, hotels, experiences, offsets, transport options).
  Protected by two layers of authentication: nginx HTTP Basic Auth at the
  network level, and the console's own login underneath.

## Architecture at a glance

- **Frontend** (`frontend/`) — a vanilla-JS chat UI on the Rasa REST channel:
  quick-reply buttons, colour-coded result cards, a high-emission alert, a
  live trip-summary panel, session trip history with replay, and a
  human-advisor handover flow.
- **Admin console** (`admin/`) — the dashboard described above, served from
  the same image behind nginx HTTP Basic Auth, talking to a standalone Flask
  API (`actions/admin_api.py`) with its own session-token login.
- **Rasa NLU + Core** — DIETClassifier pipeline; rules, stories and a
  slot-filling form for the multi-turn flow; a two-stage fallback (clarify →
  escalate to a human). Form activation *and* submission are both
  deterministic rules — see `data/rules.yml`'s header comment and
  `docs/testing-log.md` for why this mattered in practice.
- **Custom action server** (`actions/`) — carbon estimation, transport ranking
  via a weighted scoring function, hotel/experience/offset retrieval, handover
  packaging, and GPS-based city resolution.
- **Database** — NeonDB (serverless PostgreSQL), the primary data store for
  destinations, hotels, experiences, offsets, transport options, trip sessions
  (including the recommended transport mode) and handover logs.
- **External APIs** (all optional, all with graceful fallbacks) — Climatiq,
  OpenRouteService, OpenCage, Aviationstack.
- **Deployment** — a single Docker image (nginx + Rasa server + action server
  + admin API) deployed on Google Cloud Run, scaling to zero when idle and
  waking on request (a ~15–60s cold start to load the trained model — see
  `deploy/start.sh`'s readiness-polling logic).

Full diagram: `docs/architecture_diagram_v2.svg`.

## Quick start (local, without Docker)

Rasa 3.6.x requires **Python 3.10**.

```bash
python3.10 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env             # fill in your API keys and NEON_DATABASE_URL
rasa train
rasa run actions --port 5055 &   # terminal 1: custom action server
rasa run --enable-api --cors "*" --port 5005 &  # terminal 2: REST API
python3 -m actions.admin_api &   # terminal 3: admin API (port 5002)
cd frontend && python3 -m http.server 8080  # terminal 4: chat frontend
```

**Note for local testing:** `frontend/index.html`'s `REST_ENDPOINT` and
`admin/index.html`'s `API_BASE` are set to `window.location.origin` by
default, which only resolves correctly behind nginx (Docker or the live
deployment). For local testing without Docker, temporarily point them at
`http://localhost:5005/webhooks/rest/webhook` and `http://localhost:5002/api`
respectively — **do not commit that change**.

See `setup.sh` for a scripted version of the environment setup.

## Deployment

Ships as a single Docker image (nginx + Rasa server + action server + admin
console behind one port, `$PORT`/8080). Deployed on **Google Cloud Run**,
chosen specifically because its scale-to-zero model correctly handles
unpredictable, sparse traffic (testers or graders arriving at unknown times)
without needing the service to be manually started — see
`docs/deployment.md` for the full guide and the Cloud Build / Cloud Run
commands used.

```bash
# Local Docker test:
docker compose up --build
# open http://localhost:8080

# Cloud Run (see docs/deployment.md for the full gcloud command,
# including secrets and the --no-cpu-throttling flag needed for
# reliable multi-process cold starts):
gcloud builds submit --tag <artifact-registry-path>
gcloud run deploy ecovoyage-advisor --image=<artifact-registry-path> ...
```

## Project structure
ecovoyage-advisor/
├── actions/ # Custom Rasa actions, NeonDB access, external API clients, admin API
├── data/ # NLU training data, stories, rules
├── frontend/ # Chat UI (vanilla JS)
├── admin/ # Admin console UI
├── db/ # Schema, canonical seed data, migrations
├── deploy/ # nginx config template, container startup script
├── tests/ # pytest unit tests + rasa test stories
├── docs/ # deployment guide, API integration decisions, architecture, testing log
├── config.yml # NLU pipeline + policies
├── domain.yml # Intents, entities, slots, forms, responses
├── endpoints.yml # Action server endpoint
├── credentials.yml # Channel config (REST)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
## Testing

```bash
rasa test nlu --cross-validation
rasa test core --stories tests/test_stories/test_stories.yml
pytest tests/
```

See `docs/testing-log.md` for the full testing history, including real bugs
found during live scenario testing and how each was diagnosed and fixed —
several stemmed from genuine Rasa policy-layer edge cases (e.g. `RulePolicy`'s
implicit form-continuation behaviour outranking custom rules in specific
tracker states) rather than application logic errors, and are documented as
such for the report's critical evaluation.

## Status

**Complete and deployed:**
- Core conversational flow (form, carbon estimation, weighted recommendations,
  high-emission alerts, offsets) — fully built and tested.
- Frontend: location detection, city selection, trip history with replay,
  flexible-date flow, human advisor handover.
- Admin console: dashboard (6 charts), trips/handovers tables, full CRUD for
  reference data, two-layer authentication.
- Docker/nginx wiring, deployed live on Google Cloud Run.

**Known limitation:** a narrow edge case in the "edit an answer, then
immediately re-answer" flow was traded off by removing the edit-pencil UI
affordance rather than continuing to chase a policy-layer fix — see
`docs/testing-log.md` for the full reasoning.

**Remaining:** user testing (Likert-scale survey), final report write-up.

See commit history for phase-by-phase progress.