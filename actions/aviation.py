"""
aviation.py — real per-route flight sample for EcoVoyage Advisor.

Design: queries Aviationstack filtered by departure/arrival IATA codes
(confirmed working on the free tier during Phase 1 testing — see
docs/api-integration-decision.md), so the transport card can show a genuine
scheduled flight for the user's actual route rather than a generic
illustrative one. This is purely a supporting/illustrative data point: the
carbon and price figures used in scoring come from carbon.py and NeonDB, not
from this flight record — Aviationstack is not authoritative for either.

HTTP-only note: the free tier does not support HTTPS. This is a genuine
platform limitation of the free plan, not a bug in this code.

Requires both cities to have an iata_code set in NeonDB's city table
(added via db/migration_001_add_iata_code.sql). If either is missing, or the
route simply has no results, this degrades to no live-flight line — the
transport card still works using carbon.py/repository.py data alone (FR-04,
NFR-04).

QUOTA MANAGEMENT (500 req/month free tier — the tightest of the 4 APIs):
Two-part strategy agreed for this project:
1. CACHING (implemented here): a same-day, in-process cache per route, so
   repeated lookups for the same origin/destination within one day cost
   only one real API call. This is a simple dict, not a distributed cache —
   it resets on container restart, which is an acceptable trade-off given
   this project's scope and traffic level.
2. CALL SPARINGLY (must be enforced by the CALLER in actions.py, not here):
   only call get_sample_flight() when flight is the actually-recommended/
   winning transport option for a trip, never speculatively for every
   option being scored. This file exposes no logic to enforce that — it's
   a design rule for actions.py's action_recommend_plan to follow.
"""

import os
import time
import requests

AVIATIONSTACK_API_KEY = os.environ.get("AVIATIONSTACK_API_KEY")

# HTTP only — confirmed during Phase 1 testing that the free tier does not
# support HTTPS. Do not "fix" this to https:// — it will fail.
AVIATIONSTACK_ENDPOINT = "http://api.aviationstack.com/v1/flights"
AVIATIONSTACK_TIMEOUT_SECONDS = 6

# In-process cache: {(origin_iata, destination_iata): (cached_at_epoch, result)}
# Not shared across container restarts or multiple worker processes — see
# module docstring. Good enough for this project's traffic level.
_flight_cache: dict[tuple[str, str], tuple[float, dict | None]] = {}
CACHE_TTL_SECONDS = 24 * 60 * 60  # one day — flight schedules don't change minute-to-minute


def _cache_get(origin_iata: str, destination_iata: str) -> tuple[bool, dict | None]:
    """Returns (cache_hit, cached_value). cached_value may legitimately be
    None (a previously-confirmed 'no flight found' result is cached too, so
    we don't hammer the API repeatedly for a route with no service)."""
    key = (origin_iata, destination_iata)
    entry = _flight_cache.get(key)
    if entry is None:
        return False, None
    cached_at, value = entry
    if time.time() - cached_at > CACHE_TTL_SECONDS:
        return False, None
    return True, value


def _cache_set(origin_iata: str, destination_iata: str, value: dict | None) -> None:
    _flight_cache[(origin_iata, destination_iata)] = (time.time(), value)


def get_sample_flight(origin_iata: str, destination_iata: str) -> dict | None:
    """
    Fetch one real scheduled flight for a route, filtered by IATA codes
    (confirmed working on the free tier — see docs/api-integration-decision.md).

    Cached per route for CACHE_TTL_SECONDS (see module docstring, point 1).
    Callers are responsible for only invoking this when flight is the
    actual recommended option, not speculatively (point 2) — this function
    cannot enforce that itself.

    Args:
        origin_iata: e.g. "CDG" — from city.iata_code in NeonDB
        destination_iata: e.g. "AMS"

    Returns:
        {
          "airline_name": str,
          "flight_number": str,       # IATA-style, e.g. "6E8032"
          "departure_airport": str,
          "departure_scheduled": str, # ISO 8601 timestamp as returned by the API
          "arrival_airport": str,
          "arrival_scheduled": str,
          "flight_status": str,       # e.g. "scheduled", "active"
        }
        or None if unconfigured, missing IATA codes, no results, or the
        call fails — every failure mode degrades gracefully (NFR-04); the
        transport card simply omits the live-flight line (FR-04).
    """
    if not AVIATIONSTACK_API_KEY:
        return None
    if not origin_iata or not destination_iata:
        return None

    cache_hit, cached_value = _cache_get(origin_iata, destination_iata)
    if cache_hit:
        return cached_value

    result = _fetch_from_aviationstack(origin_iata, destination_iata)
    _cache_set(origin_iata, destination_iata, result)
    return result


def _fetch_from_aviationstack(origin_iata: str, destination_iata: str) -> dict | None:
    """The actual network call, isolated so get_sample_flight() only has to
    reason about caching, not request/response handling."""
    try:
        response = requests.get(
            AVIATIONSTACK_ENDPOINT,
            params={
                "access_key": AVIATIONSTACK_API_KEY,
                "dep_iata": origin_iata,
                "arr_iata": destination_iata,
                "limit": 1,
            },
            timeout=AVIATIONSTACK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        flights = data.get("data") or []
        if not flights:
            return None

        flight = flights[0]
        return {
            "airline_name": flight["airline"]["name"],
            "flight_number": flight["flight"]["iata"],
            "departure_airport": flight["departure"]["airport"],
            "departure_scheduled": flight["departure"]["scheduled"],
            "arrival_airport": flight["arrival"]["airport"],
            "arrival_scheduled": flight["arrival"]["scheduled"],
            "flight_status": flight["flight_status"],
        }
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None