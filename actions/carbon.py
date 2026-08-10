"""
carbon.py — carbon emissions estimation for EcoVoyage Advisor (FR-05).

Design: given a transport mode, a distance, and a traveller count, return an
estimated CO2e figure. Tries Climatiq for a live emission factor where we
have a known activity_id; falls back to a stored kg_co2e_per_pax_km value
(passed in by the caller, sourced from NeonDB's emission_factor table via
repository.py) if Climatiq is unavailable, unconfigured, or errors.

Deliberately has no NeonDB dependency itself — repository.py owns all
database access; this module is pure "given a fallback rate, do the math and
optionally try to beat it with a live API call."

Activity ID note: only 'car' has been manually verified against the live
Climatiq API (see docs/api-integration-decision.md). 'coach' and 'train'
activity_ids below are Climatiq's documented naming convention but have not
been individually confirmed — any lookup failure for them falls back to the
stored factor automatically, so an incorrect/outdated id degrades safely
rather than breaking the estimate. 'flight' is not attempted against
Climatiq at all: Climatiq's flight-specific estimation typically needs a
route/airport-based lookup rather than a simple distance-based activity_id,
which is a heavier integration than this project's scope justifies — flights
always use the stored factor. This is a documented scope decision, not an
oversight.
"""

import os
import requests

CLIMATIQ_API_KEY = os.environ.get("CLIMATIQ_API_KEY")
CLIMATIQ_ENDPOINT = "https://api.climatiq.io/data/v1/estimate"
CLIMATIQ_TIMEOUT_SECONDS = 5

# FR-05 / NFR-04: only modes with a real Climatiq activity_id are attempted
# live. 'car' confirmed working during Phase 1 testing (see
# docs/api-integration-decision.md). 'coach'/'train' are best-effort.
CLIMATIQ_ACTIVITY_IDS = {
    "car": "passenger_vehicle-vehicle_type_car-fuel_source_na-engine_size_na-vehicle_age_na-vehicle_weight_na",
    "coach": "passenger_vehicle-vehicle_type_bus-fuel_source_na-engine_size_na-vehicle_age_na-vehicle_weight_na",
    "train": "passenger_train-route_type_na-fuel_source_na",
}
CLIMATIQ_DATA_VERSION = "^21"

# Illustrative bands only — NOT an authoritative standard. Surfaced to the
# user alongside utter_carbon_disclaimer (NFR-08: anti-greenwashing
# transparency). Thresholds are total trip CO2e in kg, all travellers combined.
CARBON_LEVEL_THRESHOLDS_KG = {
    "green": 50,    # <= 50 kg total -> green
    "amber": 150,   # <= 150 kg total -> amber, above -> red
}


def _try_climatiq(mode_name: str, distance_km: float) -> float | None:
    """
    Attempt a live Climatiq estimate for 1 passenger over distance_km.
    Returns kg CO2e per passenger, or None if unavailable/unconfigured/failed.
    Never raises — every failure mode degrades to the caller using the
    stored fallback instead (FR-05, NFR-04).
    """
    if not CLIMATIQ_API_KEY:
        return None

    activity_id = CLIMATIQ_ACTIVITY_IDS.get(mode_name)
    if not activity_id:
        return None

    try:
        response = requests.post(
            CLIMATIQ_ENDPOINT,
            headers={
                "Authorization": f"Bearer {CLIMATIQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "emission_factor": {
                    "activity_id": activity_id,
                    "data_version": CLIMATIQ_DATA_VERSION,
                },
                "parameters": {
                    "distance": distance_km,
                    "distance_unit": "km",
                },
            },
            timeout=CLIMATIQ_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return float(data["co2e"])
    except (requests.RequestException, KeyError, ValueError, TypeError):
        # Network error, timeout, bad activity_id, unexpected response shape,
        # rate limit, etc. — all treated the same: fall back silently.
        return None


def classify_carbon_level(total_co2e_kg: float) -> str:
    """Buckets a total trip CO2e figure into green/amber/red (illustrative)."""
    if total_co2e_kg <= CARBON_LEVEL_THRESHOLDS_KG["green"]:
        return "green"
    if total_co2e_kg <= CARBON_LEVEL_THRESHOLDS_KG["amber"]:
        return "amber"
    return "red"


def estimate_co2e(
    mode_name: str,
    distance_km: float,
    num_travellers: int,
    fallback_kg_per_pax_km: float,
) -> dict:
    """
    Estimate total trip CO2e for a given transport mode.

    Args:
        mode_name: 'flight' | 'train' | 'coach' | 'car'
        distance_km: one-way distance for the route
        num_travellers: number of people travelling (each counted separately)
        fallback_kg_per_pax_km: stored emission_factor.kg_co2e_per_pax_km,
            fetched by the caller from NeonDB — used whenever Climatiq
            doesn't return a usable figure

    Returns:
        {
          "co2e_total_kg": float,
          "co2e_per_person_kg": float,
          "carbon_level": "green" | "amber" | "red",
          "data_source": "climatiq" | "stored",
        }
    """
    per_person_kg = _try_climatiq(mode_name, distance_km)
    data_source = "climatiq"

    if per_person_kg is None:
        per_person_kg = fallback_kg_per_pax_km * distance_km
        data_source = "stored"

    total_kg = per_person_kg * max(num_travellers, 1)

    return {
        "co2e_total_kg": round(total_kg, 2),
        "co2e_per_person_kg": round(per_person_kg, 2),
        "carbon_level": classify_carbon_level(total_kg),
        "data_source": data_source,
    }