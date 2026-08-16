#!/bin/sh
set -e

# Render (and most PaaS platforms) inject PORT at container start, not
# build time — substitute it into nginx's config now. Explicitly scoped to
# $PORT only, so nginx's own $uri/$host/$remote_addr variables in the
# template are left alone.
export PORT="${PORT:-8080}"
envsubst '$PORT' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

# htpasswd for nginx's outer Basic Auth gate on /admin and /api — generated
# from env vars at container start, never baked into the image. Distinct
# from the admin console's own app-level login (admin@ecovoyage / ...),
# matching the two-layer auth in the architecture diagram.
ADMIN_HTTP_USER="${ADMIN_HTTP_USER:-admin}"
ADMIN_HTTP_PASSWORD="${ADMIN_HTTP_PASSWORD:-changeme}"
printf "%s:%s\n" "$ADMIN_HTTP_USER" "$(openssl passwd -apr1 "$ADMIN_HTTP_PASSWORD")" > /etc/nginx/.htpasswd

echo "Starting Rasa action server..."
rasa run actions --port 5055 &

echo "Starting Rasa server..."
rasa run --enable-api --cors "*" --port 5005 &

echo "Starting Admin API..."
python3 -m actions.admin_api &

# Crude but effective for a single-instance prototype: give the background
# services a moment to bind their ports before nginx starts routing to
# them. A production setup would poll each service's health endpoint
# instead of a fixed sleep.
# Poll Rasa's own /status endpoint until it responds, rather than guessing a
# fixed sleep duration — cold-start timing varies (57s+ observed on Cloud
# Run vs. ~14s locally), so a hardcoded sleep is inherently fragile. Caps
# at 120s as a safety net so the container doesn't hang forever if
# something is genuinely broken.
echo "Waiting for Rasa server to be ready..."
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:5005/status > /dev/null 2>&1; then
    echo "Rasa server is ready after ${i}0 checks."
    break
  fi
  sleep 2
done

echo "Starting nginx..."
exec nginx -g 'daemon off;'