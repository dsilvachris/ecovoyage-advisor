#!/usr/bin/env bash
# Local dev environment setup for EcoVoyage Advisor.
# Requires Python 3.10 (Rasa 3.6.x does not support 3.11+/3.12).
set -euo pipefail

if ! command -v python3.10 &> /dev/null; then
  echo "python3.10 not found. Install it first (e.g. via pyenv or your OS package manager)."
  exit 1
fi

python3.10 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill in NEON_DATABASE_URL and API keys before running."
fi

echo "Setup complete. Activate with: source .venv/bin/activate"
echo "Then: rasa train"
