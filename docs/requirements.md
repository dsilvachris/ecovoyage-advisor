# Requirements — EcoVoyage Advisor

STATUS: locked in for Phase 1 — reflects every decision made through planning.
Each requirement carries an ID (FR-xx / NFR-xx) so code and tests can
reference back to it directly (comments like `# FR-03` in actions.py).

## Functional Requirements

| ID | Requirement | Notes |
|---|---|---|
| FR-01 | Trip intake via adaptive multi-turn dialogue collecting origin, destination, travel date, number of travellers, budget, and sustainability preference | Implemented as `trip_planning_form` |
| FR-02 | Location detection via manual city input or GPS coordinates | `geo.py`; falls back to nearest-supported-city matching without OpenCage |
| FR-03 | Typo-tolerant city resolution with a confirmation step (e.g. "Did you mean Paris?") | `action_clarify_destination` equivalent |
| FR-04 | Retrieval of eco-certified hotels, transport options, cultural experiences, and carbon-offset programmes from NeonDB | `repository.py` |
| FR-05 | Carbon-footprint estimation per transport option, using live Climatiq data where available | `carbon.py`; falls back to stored emission factors |
| FR-06 | Weighted scoring of options combining carbon impact, price, and stated sustainability preference | Formula: `score = w_carbon * norm(carbon) + w_price * norm(price)`, weights per preference (see docs/api-integration-decision.md style table) |
| FR-07 | High-emission alert when the lowest-carbon available option is still carbon-intensive | Not triggered merely because *an* option is red — only when the *best* option is |
| FR-08 | Human-advisor escalation with full conversational context handed over | `action_handover`; persisted via `repository.save_handover_log()` |
| FR-09 | User can request human handover at any point, not only after repeated fallback | Buttons on `utter_ask_rephrase`, `utter_default`, and an explicit `request_human` intent |
| FR-10 | Error recovery for incomplete/ambiguous messages via a two-stage clarification flow before escalating | `action_scoped_fallback`; stage 1 = re-prompt with constrained buttons, stage 2 = offer human handover |
| FR-11 | Users can go back to a previous question or edit a previously given answer without restarting | `action_go_back`, `action_edit_answer` |
| FR-12 | Full trip reset on request | `action_reset_trip` |
| FR-13 | Admin console for reviewing trip sessions, managing handover requests, and CRUD on hotel/experience/offset records | Bonus scope, beyond the brief's minimum; served at `/admin` |
| FR-14 | Admin console access is restricted to authenticated admin users | HTTP Basic Auth at the nginx layer |

## Non-Functional Requirements

| ID | Requirement | How we're meeting it |
|---|---|---|
| NFR-01 (Usability) | Clear conversational language, minimal cognitive load | Quick-reply buttons cap at ~4-6 options per question (not all 12 cities); free text always accepted as an alternative |
| NFR-02 (Usability) | Tooltip/explanation of sustainability metrics | `utter_carbon_disclaimer` explains estimates are approximate, points to DEFRA/ICAO for authoritative figures |
| NFR-03 (Reliability) | Consistent behaviour under varying load / across devices | Slots use `influence_conversation: false` so TEDPolicy's next-action prediction isn't destabilised by slot-value variation; stateless REST channel |
| NFR-04 (Reliability) | Graceful degradation of every external dependency | Climatiq / OpenRouteService / OpenCage / Aviationstack are all optional with defined fallbacks (see docs/api-integration-decision.md) |
| NFR-05 (Performance) | Response latency under 3 seconds for critical interactions | DIETClassifier (not a heavier transformer pipeline) chosen for CPU-hosted latency; to be measured in Task 5 |
| NFR-06 (Accessibility) | Screen-reader friendliness | Semantic HTML in frontend/admin (proper labels, ARIA roles on buttons); no meaning conveyed by colour alone (emission colour + text label) |
| NFR-07 (Data privacy) | GDPR-compliant handling of personal and travel data | No account/login for travellers (no persistent PII beyond a session); NeonDB connection over SSL; secrets never committed (`.env` gitignored); admin data restricted via Basic Auth |
| NFR-08 (Data privacy) | Transparent carbon-estimate disclaimers (anti-greenwashing) | NFR-02's disclaimer response; data_source is tracked per estimate so we can be explicit about live vs. stored figures |
| NFR-09 (Portability) | Deployable across hosting platforms without a rebuild | Single Docker image, configurable port, all state externalised to NeonDB (see the earlier hosting-portability discussion) |

## Explicitly out of scope

- User accounts / login for travellers (kept anonymous per-session, simplifies GDPR posture)
- Payment processing
- Real-time flight/hotel booking (Aviationstack/hotel data is informational only, not transactional)
- Multi-language support (listed as "optional" in the brief; not planned unless time allows)