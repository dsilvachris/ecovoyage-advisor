FROM python:3.10-slim

# nginx: reverse proxy + static file server
# gcc/libpq-dev: needed to build psycopg2 from source
# gettext-base: provides envsubst, used to inject $PORT into nginx.conf at
#   container startup (Render assigns PORT dynamically, not at build time)
# openssl: used to generate the htpasswd file for nginx's Basic Auth gate
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx gcc libpq-dev gettext-base openssl curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

# Trains the model at BUILD time rather than shipping a pre-trained
# artifact — guarantees the image is always self-consistent with the
# domain/data/actions baked into it, and needs no external API keys or
# network access (training only reads local nlu.yml/stories.yml/rules.yml).
RUN rasa train

COPY deploy/nginx.conf.template /etc/nginx/nginx.conf.template
RUN chmod +x /app/deploy/start.sh

EXPOSE 8080

CMD ["/app/deploy/start.sh"]