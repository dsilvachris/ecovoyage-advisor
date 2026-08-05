"""
actions.py — custom Rasa actions for EcoVoyage Advisor.

STATUS: scaffold only. To be implemented during Task 4.

Design (agreed):
- Reads collected slots, fetches data through repository.py (NeonDB as the
  primary store — no local JSON fallback tier, per our decision to rely on
  NeonDB directly), estimates emissions through carbon.py (Climatiq -> stored
  factor), and replies in friendly conversational language.
- Every external API call (Climatiq, OpenRouteService, OpenCage, Aviationstack)
  is optional and degrades gracefully on failure/timeout/missing key.
- action_handover packages full slot state for the human-advisor handoff and
  persists it via repository.save_handover_log().
- action_scoped_fallback implements the two-stage clarification -> escalation
  flow described in the brief.

# from rasa_sdk import Action, FormValidationAction, Tracker
# import carbon, geo, routing, aviation, repository
"""
