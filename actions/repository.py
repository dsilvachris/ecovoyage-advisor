"""
repository.py — the data-access layer for EcoVoyage Advisor.

STATUS: scaffold only. To be implemented during Task 4.

Design (agreed): NeonDB is the single primary source (no local JSON fallback
tier — this is a deliberate simplification vs. the reference implementation
we reviewed, since we're accepting NeonDB's free-tier availability as
sufficient for this project's scope). Every read function should still be
defensive about a transient NeonDB outage (catch/log, don't crash the
conversation), but there is no secondary JSON tier to degrade to.

Planned functions (mirrors the reference repo's shape):
- get_destinations(), resolve_destination(), resolve_origin()
- get_hotels_for_destination(), get_experiences_for_destination(),
  get_offset_options()
- get_transport_options() — the distance/scoring engine
- save_trip_session(), save_handover_log()
- Admin-facing reads/writes for the admin console (list/update handovers,
  CRUD on hotels/experiences/offsets)
"""
