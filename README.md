# EcoVoyage Advisor — Conversational Agent for Sustainable Tourism Planning

A Rasa Open Source assistant that plans lower-carbon trips: it runs an adaptive
multi-turn dialogue to collect origin, destination, dates, budget and
sustainability preference, then recommends eco-certified hotels, transport
options, local experiences and carbon offsets, estimates the trip's carbon
footprint, and hands over to a human advisor with full conversational context.

MSc Artificial Intelligence — Advanced Conversational UI Design and Chatbot
Development (BSBI / UCA).

## Architecture at a glance

- **Frontend** (`frontend/`) — a vanilla-JS chat UI on the Rasa REST channel:
  quick-reply buttons, colour-coded result cards, a high-emission alert, and a
  human-advisor handover indicator.
- **Admin console** (`admin/`) — a lightweight dashboard for trip sessions,
  pending handovers, and hotel/experience/offset records, served from the same
  image behind HTTP Basic Auth.
- **Rasa NLU + Core** — DIETClassifier pipeline; rules, stories and a
  slot-filling form for the multi-turn flow; a two-stage fallback (clarify →
  escalate to a human).
- **Custom action server** (`actions/`) — carbon estimation, transport ranking
  via a weighted scoring function, hotel/experience/offset retrieval, and
  handover packaging.
- **Database** — NeonDB (serverless PostgreSQL), the primary data store for
  destinations, hotels, experiences, offsets, transport options, trip sessions
  and handover logs.
- **External APIs** (all optional, all with fallbacks) — Climatiq,
  OpenRouteService, OpenCage, Aviationstack.

Full diagram: `docs/architecture.md`.

## Quick start (local, without Docker)

Rasa 3.6.x requires **Python 3.10**.

```bash
python3.10 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env             # fill in your API keys and NEON_DATABASE_URL
rasa train
rasa run actions --port 5055 &   # terminal 1: custom action server
rasa run --enable-api --cors "*" --port 5005   # terminal 2: REST API
# then open frontend/index.html in a browser
```

See `setup.sh` for a scripted version of the same steps.

## Deployment

Ships as a single Docker image (nginx + Rasa server + action server + admin
console behind one port). See `docs/deployment.md` for the full guide,
including the Render deployment steps and the secrets list.

```bash
docker compose up --build
# open http://localhost:7860
```

## Project structure

```
ecovoyage-advisor/
├── actions/          # Custom Rasa actions, NeonDB access, external API clients
├── data/             # NLU training data, stories, rules
├── frontend/         # Chat UI (vanilla JS)
├── admin/            # Admin console UI
├── deploy/           # nginx config, container startup script
├── tests/            # pytest unit tests + rasa test stories
├── docs/             # deployment guide, API integration decisions, architecture
├── config.yml        # NLU pipeline + policies
├── domain.yml        # Intents, entities, slots, forms, responses
├── endpoints.yml     # Action server endpoint
├── credentials.yml   # Channel config (REST)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Testing

```bash
rasa test nlu --cross-validation
rasa test core
pytest tests/
```

## Status

## Status

**Phase 1 complete:**
- NeonDB provisioned, schema applied, seeded with 21 cities across 6
  continents (including IATA codes for flight lookups), transport modes,
  emission factors, tags, starter hotels/experiences/offsets.
- All 4 external APIs verified working — see `docs/api-integration-decision.md`
  for confirmed endpoints, auth, coordinate-order gotchas, and two mid-project
  platform changes (OpenRouteService's domain migration, Amadeus's
  decommissioning) already accounted for.

**Next: Phase 2** — finalize `domain.yml` (intents/slots/forms/responses)
and sketch the dialogue flows for Task 3.

See commit history for phase-by-phase progress.
