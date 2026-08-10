"""
repository.py — the NeonDB data-access layer for EcoVoyage Advisor (FR-04).

Every function here is defensive: a failed query logs and returns None/empty
rather than raising, since there is no fallback data tier to degrade to
(NeonDB is our sole primary store — see db.py's module docstring). Callers
in actions.py are responsible for turning an empty/None result into a
sensible conversational response (e.g. "I couldn't reach the database right
now" rather than crashing).
"""

import logging
import psycopg2.extras
from db import get_cursor

logger = logging.getLogger(__name__)


# --- City resolution (used by geo.py's caller, and form validation) ---

def get_supported_cities() -> list[dict]:
    """All cities, for geo.py's nearest_supported_city() and typo matching.
    Returns [] if the DB is unreachable — callers should treat an empty
    list as 'city support is temporarily unavailable', not 'no cities exist'."""
    with get_cursor() as cur:
        if cur is None:
            return []
        cur.execute("SELECT id, name, country, latitude, longitude, iata_code FROM city ORDER BY name")
        return cur.fetchall()


def resolve_city(name: str) -> dict | None:
    """Exact-match city lookup by name (case-insensitive)."""
    with get_cursor() as cur:
        if cur is None:
            return None
        cur.execute("SELECT * FROM city WHERE lower(name) = lower(%s)", (name,))
        return cur.fetchone()


# --- Transport options for a route (FR-04, FR-06) ---

def get_transport_options_for_route(origin_city_id: int, destination_city_id: int) -> list[dict]:
    """
    All transport modes available for a route, each with its emission
    factor and, if one is seeded, a curated distance_km.

    Ground modes (train/coach/car) only return rows if a transport_option
    was seeded for this exact route (see db/seed.sql's design note: only
    intra-continent pairs have these seeded). 'flight' is always included
    regardless of whether a transport_option row exists, since flight
    distance is computed via haversine in routing.py/geo.py rather than
    requiring a seeded row — this function returns flight's emission
    factor unconditionally so the caller can always at least offer flight.
    """
    with get_cursor() as cur:
        if cur is None:
            return []

        cur.execute(
            """
            SELECT
                tm.id AS transport_mode_id,
                tm.name AS mode_name,
                tm.overhead_hours,
                tm.avg_speed_kmh,
                tm.base_price_eur,
                tm.price_per_km,
                ef.kg_co2e_per_pax_km,
                to_.distance_km AS curated_distance_km
            FROM transport_mode tm
            JOIN emission_factor ef ON ef.transport_mode_id = tm.id
            LEFT JOIN transport_option to_
                ON to_.transport_mode_id = tm.id
                AND to_.origin_city_id = %s
                AND to_.destination_city_id = %s
            WHERE tm.name = 'flight' OR to_.id IS NOT NULL
            ORDER BY tm.name
            """,
            (origin_city_id, destination_city_id),
        )
        return cur.fetchall()


# --- Hotels, experiences, offsets (FR-04) ---

def get_hotels_for_destination(destination_city_id: int) -> list[dict]:
    with get_cursor() as cur:
        if cur is None:
            return []
        cur.execute(
            "SELECT * FROM hotel WHERE city_id = %s ORDER BY sustainability_score DESC",
            (destination_city_id,),
        )
        return cur.fetchall()


def get_experiences_for_destination(destination_city_id: int) -> list[dict]:
    with get_cursor() as cur:
        if cur is None:
            return []
        cur.execute(
            "SELECT * FROM experience WHERE city_id = %s ORDER BY local_community_score DESC",
            (destination_city_id,),
        )
        return cur.fetchall()


def get_offset_options() -> list[dict]:
    with get_cursor() as cur:
        if cur is None:
            return []
        cur.execute("SELECT * FROM offset_option ORDER BY estimated_cost_per_tonne ASC")
        return cur.fetchall()


# --- Writes: trip sessions and handovers (FR-08, FR-09) ---

def save_trip_session(
    sender_id: str,
    origin_city_id: int | None,
    destination_city_id: int | None,
    travel_date: str | None,
    num_travellers: int | None,
    budget_tier: str | None,
    sustainability_pref: str | None,
    estimated_co2_kg: float | None,
    carbon_level: str | None,
    data_source: str | None,
) -> int | None:
    """Persists a completed (or partially completed) trip. Returns the new
    trip_session.id, or None if the write failed — callers should not block
    the conversation on this succeeding (it's a record for the admin
    console, not something the user-facing flow depends on)."""
    with get_cursor(commit=True) as cur:
        if cur is None:
            return None
        cur.execute(
            """
            INSERT INTO trip_session (
                sender_id, origin_city_id, destination_city_id, travel_date,
                num_travellers, budget_tier, sustainability_pref,
                estimated_co2_kg, carbon_level, data_source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                sender_id, origin_city_id, destination_city_id, travel_date,
                num_travellers, budget_tier, sustainability_pref,
                estimated_co2_kg, carbon_level, data_source,
            ),
        )
        row = cur.fetchone()
        return row["id"] if row else None


def save_handover_log(
    trip_session_id: int | None,
    reason: str,
    context_json: dict,
) -> int | None:
    """
    Persists a handover request (FR-08, FR-09). trip_session_id may be None
    if the handover happens mid-form before a trip_session row exists yet
    (see Scenario 5 in docs/dialogue-flows.md) — context_json carries
    whatever slot data was actually collected in that case, since the
    admin console needs something to show even without a completed trip.
    """
    with get_cursor(commit=True) as cur:
        if cur is None:
            return None
        cur.execute(
            """
            INSERT INTO handover_log (trip_session_id, reason, context_json, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING id
            """,
            (trip_session_id, reason, psycopg2.extras.Json(context_json)),
        )
        row = cur.fetchone()
        return row["id"] if row else None