"""
db.py — NeonDB (PostgreSQL) connection and session handling.

STATUS: scaffold only. To be implemented during Task 4.

Design (agreed):
- Reads the connection string from the NEON_DATABASE_URL env var only —
  never hardcoded, never logged.
- Exposes is_db_configured() and get_session() for repository.py to use.
- SQLAlchemy models: Destination, OriginCity, TransportMode, EmissionFactor,
  TransportOption, Hotel, Experience, OffsetOption, Tag, Trip, HandoverLog.
  (Same schema shape as the reference repo's seed data, since NeonDB is now
  our single source of truth rather than a fallback tier.)
"""
