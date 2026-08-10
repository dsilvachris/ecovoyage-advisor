"""
routing.py — ground-transport distance for EcoVoyage Advisor.

Design: OpenRouteService only has a genuine road-routing profile for driving
(no train/coach profile exists on their API), so this module's live-API path
applies to the 'car' mode only. Train/coach distances come from the curated
distance_km already stored in NeonDB's transport_option table (fetched by
the caller via repository.py) — OpenRouteService adds nothing there.
Intercontinental routes (no transport_option row at all) fall back to a
haversine great-circle estimate with a detour multiplier, since flight is
the only mode offered on those routes anyway (see docs/dialogue-flows.md,
Scenario 2/4) and this function isn't even called for flights — carbon.py's
stored emission_factor is distance-independent enough for that case, and
flight distance for display purposes uses haversine directly in geo.py.

Coordinate order warning (see docs/api-integration-decision.md): OpenRoute-
Service expects [longitude, latitude] in its query params — the OPPOSITE of
how city.latitude/city.longitude are stored in our NeonDB schema. Every
function below that builds an ORS request swaps the order explicitly; do not
"simplify" this by passing lat/lon straight through.
"""

import os
import math
import requests

OPENROUTESERVICE_API_KEY = os.environ.get("OPENROUTESERVICE_API_KEY")

# Confirmed working during Phase 1 testing (see docs/api-integration-decision.md).
# The old api.openrouteservice.org domain is being deprecated by HeiGIT.
OPENROUTESERVICE_ENDPOINT = "https://api.heigit.org/openrouteservice/v2/directions/driving-car"
OPENROUTESERVICE_TIMEOUT_SECONDS = 6

EARTH_RADIUS_KM = 6371.0

# Straight-line (haversine) distance understates real travel distance —
# roads/rail curve around terrain, coastlines, borders. This multiplier is a
# rough correction, not a precise model; only used when no curated
# transport_option row and no live ORS response are available.
HAVERSINE_DETOUR_MULTIPLIER = 1.15


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in km."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def estimated_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance with the detour multiplier applied — used as the
    last-resort fallback when neither a curated row nor a live API result
    is available (FR-04, NFR-04)."""
    return round(haversine_km(lat1, lon1, lat2, lon2) * HAVERSINE_DETOUR_MULTIPLIER, 2)


def _try_openrouteservice_driving(
    origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float
) -> float | None:
    """
    Attempt a live driving-route distance via OpenRouteService.
    Returns km, or None if unavailable/unconfigured/failed — every failure
    mode degrades to the caller using a fallback distance instead (NFR-04).
    """
    if not OPENROUTESERVICE_API_KEY:
        return None

    try:
        response = requests.get(
            OPENROUTESERVICE_ENDPOINT,
            params={
                "api_key": OPENROUTESERVICE_API_KEY,
                # ORS wants "lon,lat" — swapped from our lat/lon storage order.
                "start": f"{origin_lon},{origin_lat}",
                "end": f"{dest_lon},{dest_lat}",
            },
            timeout=OPENROUTESERVICE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        distance_meters = data["features"][0]["properties"]["segments"][0]["distance"]
        return round(distance_meters / 1000, 2)
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_distance_km(
    mode_name: str,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    curated_distance_km: float | None,
) -> dict:
    """
    Resolve a distance for a given transport mode.

    Args:
        mode_name: 'car' | 'train' | 'coach' (not 'flight' — see module docstring)
        origin_lat/lon, dest_lat/lon: from NeonDB's city table
        curated_distance_km: transport_option.distance_km if a row exists
            for this route+mode, else None

    Returns:
        {"distance_km": float, "data_source": "openrouteservice" | "stored" | "estimated"}
    """
    if mode_name == "car":
        live_km = _try_openrouteservice_driving(origin_lat, origin_lon, dest_lat, dest_lon)
        if live_km is not None:
            return {"distance_km": live_km, "data_source": "openrouteservice"}

    if curated_distance_km is not None:
        return {"distance_km": float(curated_distance_km), "data_source": "stored"}

    # No curated row (e.g. intercontinental pair with no train/coach seeded,
    # or 'car' with ORS unavailable and no stored row either).
    return {
        "distance_km": estimated_distance_km(origin_lat, origin_lon, dest_lat, dest_lon),
        "data_source": "estimated",
    }