#!/usr/bin/env bash
# Container entrypoint — starts the action server, Rasa REST server, and the
# admin API in the background, generates the nginx Basic Auth file from env
# vars, then runs nginx in the foreground (keeps the container alive).
#
# STATUS: scaffold only, to be tested during Task 6.
set -euo pipefail

htpasswd -bc /etc/nginx/.htpasswd "${ADMIN_USERNAME:-admin}" "${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}"

rasa run actions --port 5055 &
rasa run --enable-api --cors "*" --port 5005 &
# python actions/admin_api.py --port 5056 &   # TODO once admin_api.py is implemented

nginx -g "daemon off;"
