# EcoVoyage Advisor — single Docker image (nginx + Rasa + action server + admin API)
# STATUS: scaffold only — untested, to be built out during Task 6.
#
# Design: nginx listens on one public port and reverse-proxies:
#   /                        -> frontend/ (static chat UI)
#   /admin                   -> admin/ (static UI) + admin_api (behind Basic Auth)
#   /webhooks/rest/webhook   -> Rasa REST server (internal, :5005)
# The action server (:5055) is only called internally by Rasa, never exposed.

FROM python:3.10-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Model is trained at build time so the container starts quickly with no
# secrets required to build (matches the reference project's approach).
RUN rasa train

COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 7860
CMD ["/app/start.sh"]
