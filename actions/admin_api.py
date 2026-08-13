"""
admin_api.py — standalone Flask backend for the admin console.

Deliberately NOT part of the Rasa action server (different framework,
different lifecycle, different port) — run separately:
    python3 -m actions.admin_api
(must be run as a module from the project root, not `python admin_api.py`
from inside actions/, for the same relative-import reason documented in
actions.py's own module docstring — `from . import db` needs the actions
package to be loaded properly.)

Uses the same db.get_cursor() contract as repository.py: get_cursor()
yields None if the connection pool itself is unavailable (checked below
before every query), and commits only happen when explicitly requested via
get_cursor(commit=True) — never via a manual cur.connection.commit() call,
to stay consistent with how the rest of the codebase handles this (see
db.py's own module docstring for why query-level errors are deliberately
NOT caught inside get_cursor()).

SECURITY NOTE (documented honestly, not hidden): credentials are checked
here, server-side, never compared in the browser. This is still a
plaintext-in-source-code credential store, acceptable for a coursework
prototype behind local/demo access only — a production version would use
hashed credentials and a real session store, not an in-memory dict. Noted
as a known limitation for the report rather than pretending this is
production-grade auth. The architecture diagram also specifies nginx-level
HTTP Basic Auth as an outer gate on /admin, on top of this app-level login
— that layer is added when nginx is wired up (Docker deployment stage).
"""

import secrets
from flask import Flask, request, jsonify
from flask_cors import CORS

from .db import get_cursor

app = Flask(__name__)
CORS(app)  # admin/index.html is served from a different port locally

ADMIN_USERNAME = "admin@ecovoyage"
ADMIN_PASSWORD = "Ecovoyage@2026"

# In-memory session store — fine for a single-instance prototype; tokens
# are lost on restart, which just means logging in again.
SESSIONS = set()


def require_auth(fn):
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token not in SESSIONS:
            return jsonify({"error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def _db_unavailable_response():
    return jsonify({"error": "Database is currently unavailable — please try again shortly."}), 503


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True, silent=True) or {}
    if data.get("username") == ADMIN_USERNAME and data.get("password") == ADMIN_PASSWORD:
        token = secrets.token_hex(24)
        SESSIONS.add(token)
        return jsonify({"token": token})
    return jsonify({"error": "Invalid credentials"}), 401


@app.route("/api/logout", methods=["POST"])
@require_auth
def logout():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    SESSIONS.discard(token)
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

@app.route("/api/stats", methods=["GET"])
@require_auth
def stats():
    with get_cursor() as cur:
        if cur is None:
            return _db_unavailable_response()

        cur.execute("SELECT COUNT(*) AS total FROM trip_session;")
        total_trips = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM handover_log;")
        total_handovers = cur.fetchone()["total"]

        cur.execute(
            "SELECT COUNT(*) AS total FROM handover_log WHERE reason = 'fallback_escalation';"
        )
        total_fallback_escalations = cur.fetchone()["total"]

        cur.execute("SELECT AVG(estimated_co2_kg) AS avg_co2 FROM trip_session;")
        avg_co2_row = cur.fetchone()
        avg_co2 = round(float(avg_co2_row["avg_co2"]), 1) if avg_co2_row["avg_co2"] else None

        cur.execute("""
            SELECT carbon_level, COUNT(*) AS count
            FROM trip_session
            WHERE carbon_level IS NOT NULL
            GROUP BY carbon_level;
        """)
        carbon_breakdown = {row["carbon_level"]: row["count"] for row in cur.fetchall()}

        cur.execute("""
            SELECT DATE(created_at) AS day, COUNT(*) AS count
            FROM trip_session
            WHERE created_at >= NOW() - INTERVAL '14 days'
            GROUP BY DATE(created_at)
            ORDER BY day ASC;
        """)
        trips_per_day = [{"day": str(r["day"]), "count": r["count"]} for r in cur.fetchall()]

        cur.execute("""
            SELECT sustainability_pref, COUNT(*) AS count
            FROM trip_session
            WHERE sustainability_pref IS NOT NULL
            GROUP BY sustainability_pref;
        """)
        sustainability_breakdown = {row["sustainability_pref"]: row["count"] for row in cur.fetchall()}

        cur.execute("""
            SELECT data_source, COUNT(*) AS count
            FROM trip_session
            WHERE data_source IS NOT NULL
            GROUP BY data_source;
        """)
        data_source_breakdown = {row["data_source"]: row["count"] for row in cur.fetchall()}

        cur.execute("""
            SELECT dc.name AS destination, COUNT(*) AS count
            FROM trip_session ts
            JOIN city dc ON dc.id = ts.destination_city_id
            GROUP BY dc.name
            ORDER BY count DESC
            LIMIT 8;
        """)
        top_destinations = [{"destination": r["destination"], "count": r["count"]} for r in cur.fetchall()]

        cur.execute("""
            SELECT recommended_mode, COUNT(*) AS count
            FROM trip_session
            WHERE recommended_mode IS NOT NULL
            GROUP BY recommended_mode;
        """)
        mode_breakdown = {row["recommended_mode"]: row["count"] for row in cur.fetchall()}

    return jsonify({
        "total_trips": total_trips,
        "total_handovers": total_handovers,
        "total_fallback_escalations": total_fallback_escalations,
        "avg_co2_kg": avg_co2,
        "carbon_breakdown": carbon_breakdown,
        "trips_per_day": trips_per_day,
        "sustainability_breakdown": sustainability_breakdown,
        "data_source_breakdown": data_source_breakdown,
        "top_destinations": top_destinations,
        "mode_breakdown": mode_breakdown,
    })


@app.route("/api/trips", methods=["GET"])
@require_auth
def list_trips():
    with get_cursor() as cur:
        if cur is None:
            return _db_unavailable_response()
        cur.execute("""
            SELECT
                ts.id, ts.sender_id, ts.travel_date, ts.trip_duration_days,
                ts.num_travellers, ts.budget_tier, ts.sustainability_pref,
                ts.estimated_co2_kg, ts.carbon_level, ts.data_source, ts.created_at,
                oc.name AS origin_name, dc.name AS destination_name
            FROM trip_session ts
            LEFT JOIN city oc ON oc.id = ts.origin_city_id
            LEFT JOIN city dc ON dc.id = ts.destination_city_id
            ORDER BY ts.created_at DESC
            LIMIT 100;
        """)
        rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/handovers", methods=["GET"])
@require_auth
def list_handovers():
    with get_cursor() as cur:
        if cur is None:
            return _db_unavailable_response()
        cur.execute("""
            SELECT id, trip_session_id, reason, status, context_json, created_at
            FROM handover_log
            ORDER BY created_at DESC
            LIMIT 100;
        """)
        rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])


# --------------------------------------------------------------------------
# Generic CRUD for reference-data tables
# --------------------------------------------------------------------------

TABLES = {
    "cities": {
        "table": "city",
        "columns": ["name", "country", "latitude", "longitude", "iata_code"],
    },
    "hotels": {
        "table": "hotel",
        "columns": ["city_id", "name", "eco_certification", "nightly_price_estimate",
                    "sustainability_score", "carbon_score"],
    },
    "experiences": {
        "table": "experience",
        "columns": ["city_id", "name", "type", "estimated_price", "local_community_score"],
    },
    "offsets": {
        "table": "offset_option",
        "columns": ["provider_name", "project_type", "estimated_cost_per_tonne"],
    },
    "transport-options": {
        "table": "transport_option",
        "columns": ["origin_city_id", "destination_city_id", "transport_mode_id",
                    "distance_km", "curated_distance_km"],
    },
}


def _register_crud(key: str, table: str, columns: list):
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    set_clause = ", ".join(f"{c} = %s" for c in columns)

    @app.route(f"/api/{key}", methods=["GET"], endpoint=f"list_{key}")
    @require_auth
    def list_rows():
        with get_cursor() as cur:
            if cur is None:
                return _db_unavailable_response()
            cur.execute(f"SELECT * FROM {table} ORDER BY id ASC;")
            rows = cur.fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route(f"/api/{key}", methods=["POST"], endpoint=f"create_{key}")
    @require_auth
    def create_row():
        data = request.get_json(force=True, silent=True) or {}
        values = [data.get(c) for c in columns]
        with get_cursor(commit=True) as cur:
            if cur is None:
                return _db_unavailable_response()
            cur.execute(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) RETURNING id;",
                values,
            )
            new_id = cur.fetchone()["id"]
        return jsonify({"id": new_id})

    @app.route(f"/api/{key}/<int:row_id>", methods=["PUT"], endpoint=f"update_{key}")
    @require_auth
    def update_row(row_id):
        data = request.get_json(force=True, silent=True) or {}
        values = [data.get(c) for c in columns] + [row_id]
        with get_cursor(commit=True) as cur:
            if cur is None:
                return _db_unavailable_response()
            cur.execute(f"UPDATE {table} SET {set_clause} WHERE id = %s;", values)
        return jsonify({"ok": True})

    @app.route(f"/api/{key}/<int:row_id>", methods=["DELETE"], endpoint=f"delete_{key}")
    @require_auth
    def delete_row(row_id):
        with get_cursor(commit=True) as cur:
            if cur is None:
                return _db_unavailable_response()
            cur.execute(f"DELETE FROM {table} WHERE id = %s;", (row_id,))
        return jsonify({"ok": True})


for _key, _cfg in TABLES.items():
    _register_crud(_key, _cfg["table"], _cfg["columns"])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)