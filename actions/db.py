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
no local fallback tier here.

IMPORTANT DESIGN NOTE (fixed after a real crash during local testing):
get_cursor() only catches errors from ACQUIRING a connection (pool
exhausted, DB unreachable) — it yields None in that case, which callers
check for. Errors from the QUERY ITSELF (bad SQL, missing column, etc.) are
NOT caught here; they propagate to the caller as real exceptions. This is
required by Python's @contextmanager, which only permits a single yield —
an earlier version tried to catch query errors here too and yield None a
second time, which raises "generator didn't stop after throw()" on any
query failure. Each function in repository.py is responsible for wrapping
its own query in try/except and returning the correct fallback value for
that specific query (an empty list vs. None vs. re-raising, depending on
what the caller needs).
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
    Yields a RealDictCursor, or None if the connection pool itself is
    unavailable (DB not configured, or connection acquisition failed).

    Query-execution errors are NOT caught here — see module docstring.
    Callers must wrap their cur.execute(...) calls in their own
    try/except psycopg2.Error to handle that case gracefully.
    """
    conn_pool = _get_pool()
    if conn_pool is None:
        yield None
        return

    conn = None
    try:
        conn = conn_pool.getconn()
    except psycopg2.Error as e:
        logger.error("Failed to acquire a NeonDB connection: %s", e)
        yield None
        return

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        if commit:
            conn.commit()
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        conn_pool.putconn(conn)