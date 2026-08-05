# Deployment guide

STATUS: placeholder — to be completed during Task 6, once the Dockerfile and
nginx config are actually tested end-to-end.

## Plan (agreed)

- **Primary hosting:** Render (free web service), deployed from the Dockerfile.
- **Backup demo:** local `docker compose up` or Rasa run natively + pyngrok
  tunnel, in case Render's free tier is asleep or unreachable during a live
  demo.
- **Database:** NeonDB (PostgreSQL), external managed service — not part of
  the container, connected via `NEON_DATABASE_URL`.
- **Secrets:** set via Render's dashboard (env vars), never committed. See
  `.env.example` for the full list.
- **Portability note:** the container listens on a single configurable port
  rather than a hardcoded one, so moving to Google Cloud Run, AWS App Runner,
  or a paid HF Docker Space later should only require re-adding the same
  secrets and confirming the port — not a rebuild.

## To be added once implemented

- Exact Render setup steps (screenshots/commands)
- Confirmed working docker compose instructions
- Any gotchas discovered during first deploy
