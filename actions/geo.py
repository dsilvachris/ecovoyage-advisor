"""
geo.py — location resolution for EcoVoyage Advisor: GPS-to-nearest-city
matching (FR-02) and typo-tolerant city name matching (FR-03).

Design: nearest-city matching from GPS coordinates works entirely offline
using haversine distance against our 21 supported cities — OpenCage is only
used to add a friendly human-readable label ("near Montmartre, Paris")
alongside the resolved city, and is skipped gracefully if unconfigured or
low-confidence. Typo matching (e.g. "Pariiis" -> "Paris") is separate:
pure string similarity against the supported city list, no external API
involved at all — this is what powers action_clarify_destination's "did you
mean...?" flow (FR-03).

Reuses haversine_km from routing.py rather than duplicating the formula.
"""

import os
import difflib
import requests

from .routing import haversine_km

OPENCAGE_API_KEY = os.environ.get("OPENCAGE_API_KEY")
OPENCAGE_ENDPOINT = "https://api.opencagedata.com/geocode/v1/json"
OPENCAGE_TIMEOUT_SECONDS = 5

# Confirmed during Phase 1 testing (see docs/api-integration-decision.md):
# OpenCage takes lat,lng order — matches our NeonDB storage order directly,
# no swap needed (unlike OpenRouteService in routing.py).
OPENCAGE_MIN_CONFIDENCE = 5  # OpenCage's own 0-10 scale; below this, skip the label

# FR-03: how close a typed city name needs to be to a supported city to
# trigger a "did you mean...?" confirmation rather than an outright rejection.
TYPO_MATCH_CUTOFF = 0.6


def nearest_supported_city(
    lat: float, lon: float, supported_cities: list[dict]
) -> dict:
    """
    Find the closest supported city to a GPS coordinate (FR-02).

    Args:
        lat, lon: the user's GPS coordinates
        supported_cities: list of {"name": str, "latitude": float, "longitude": float}
            — the caller fetches this from NeonDB's city table via repository.py

    Returns:
        {"city_name": str, "distance_km": float}
    """
    closest = min(
        supported_cities,
        key=lambda c: haversine_km(lat, lon, c["latitude"], c["longitude"]),
    )
    distance_km = haversine_km(lat, lon, closest["latitude"], closest["longitude"])
    return {"city_name": closest["name"], "distance_km": round(distance_km, 2)}


def _try_opencage_label(lat: float, lon: float) -> str | None:
    """
    Attempt a friendly place label for a GPS coordinate via OpenCage.
    Returns None if unconfigured, low-confidence, or the call fails —
    every failure mode degrades gracefully (NFR-04); the nearest-city match
    from nearest_supported_city() works without this.
    """
    if not OPENCAGE_API_KEY:
        return None

    try:
        response = requests.get(
            OPENCAGE_ENDPOINT,
            params={"q": f"{lat},{lon}", "key": OPENCAGE_API_KEY, "limit": 1},
            timeout=OPENCAGE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        result = data["results"][0]
        if result["confidence"] < OPENCAGE_MIN_CONFIDENCE:
            return None
        return result["formatted"]
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def resolve_gps_location(lat: float, lon: float, supported_cities: list[dict]) -> dict:
    """
    Full GPS resolution (FR-02): nearest supported city plus an optional
    friendly label for what's actually shown to the user.

    Returns:
        {
          "city_name": str,          # matches a city.name row in NeonDB
          "distance_km": float,      # how far the GPS point is from that city
          "friendly_label": str | None,  # e.g. "6 City Hall Plaza, Paris, France"
        }
    """
    nearest = nearest_supported_city(lat, lon, supported_cities)
    nearest["friendly_label"] = _try_opencage_label(lat, lon)
    return nearest


def find_city_typo_match(typed_name: str, supported_city_names: list[str]) -> str | None:
    """
    Typo-tolerant city matching (FR-03) — pure string similarity, no API call.

    Args:
        typed_name: whatever the user typed (e.g. "Pariiis", "Bankok")
        supported_city_names: list of city.name values from NeonDB

    Returns:
        The best-matching supported city name if similarity clears
        TYPO_MATCH_CUTOFF, otherwise None (meaning: don't guess, ask the
        user to pick from the list instead — action_clarify_destination
        handles both cases differently).
    """
    matches = difflib.get_close_matches(
        typed_name, supported_city_names, n=1, cutoff=TYPO_MATCH_CUTOFF
    )
    return matches[0] if matches else None