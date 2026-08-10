"""
db.py — NeonDB (PostgreSQL) connection handling for EcoVoyage Advisor.

Design: a small psycopg2 connection pool rather than a full ORM. Given this
project's scope (a handful of read-heavy queries plus two write paths —
trip_session and handover_log), raw parameterized SQL via psycopg2 is more
transparent and easier to explain in the report than an ORM layer would be,
and avoids a second abstraction on top of the schema in db/schema.sql.

NeonDB is now our sole primary data store (see docs/api-integration-decision.md
— this is a deliberate deviation from the reference implementation we
reviewed, which used NeonDB as a fallback tier behind local JSON). There is
no local fallback tier here: every function in repository.py is defensive
about a transient connection error (catches, logs, returns None/empty rather
than crashing the conversation), but there is nothing to degrade *to* if
NeonDB itself is down — that's the accepted trade-off documented in
docs/api-integration-decision.md.
"""

import os
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import pool

logger = logging.getLogger(__name__)

NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL")

_connection_pool: pool.SimpleConnectionPool | None = None


def is_db_configured() -> bool:
    return bool(NEON_DATABASE_URL)


def _get_pool() -> pool.SimpleConnectionPool | None:
    """Lazily creates the connection pool on first use, not at import time —
    so actions.py can be imported (e.g. for tests) even without a configured
    NEON_DATABASE_URL, and only fails when the DB is actually touched."""
    global _connection_pool

    if not is_db_configured():
        return None

    if _connection_pool is None:
        try:
            _connection_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=5,
                dsn=NEON_DATABASE_URL,
            )
        except psycopg2.Error as e:
            logger.error("Failed to create NeonDB connection pool: %s", e)
            return None

    return _connection_pool


@contextmanager
def get_cursor(commit: bool = False):
    """
    Context manager yielding a RealDictCursor (rows come back as dicts, not
    tuples — matches the {"key": value} shape the rest of the codebase
    expects, e.g. geo.py's supported_cities list).

    Usage:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM city WHERE name = %s", (name,))
            row = cur.fetchone()

    Yields None if the pool couldn't be created (DB unconfigured or
    unreachable) — callers must check for this (see repository.py's pattern).
    """
    conn_pool = _get_pool()
    if conn_pool is None:
        yield None
        return

    conn = None
    try:
        conn = conn_pool.getconn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        if commit:
            conn.commit()
    except psycopg2.Error as e:
        logger.error("NeonDB query failed: %s", e)
        if conn:
            conn.rollback()
        yield None
    finally:
        if conn:
            conn_pool.putconn(conn)