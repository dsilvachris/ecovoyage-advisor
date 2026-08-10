# Dialogue flows — Task 3

STATUS: five scenarios drafted per the brief's requirement to "show
branching logic that adapts based on sustainability preferences and
budget." Each maps to real seeded data (docs/api-integration-decision.md,
db/seed.sql) so every step can actually be demoed once Task 4 is built.

## Scenario 1 — Short city break (intra-Europe, low_carbon preference)

London -> Paris, flexible dates, 2 travellers, mid budget, low_carbon preference.

1. User: "I want to plan a trip" -> `plan_trip` -> form activates
2. Bot asks origin -> user taps "London"
3. Bot asks destination -> user taps "Paris"
4. Bot asks travel date -> user taps "I'm flexible"
5. Bot asks travellers -> user taps "2"
6. Bot asks budget -> user taps "Mid"
7. Bot asks sustainability preference -> user taps "Lowest carbon"
8. Form completes -> `action_estimate_carbon` runs for each transport_mode
   available on this route (flight/train/coach/car all seeded for
   London<->Paris)
9. `action_recommend_plan` scores options with weights 0.80 carbon / 0.20
   price (low_carbon tier) -> **train wins** (lowest carbon_score, seeded
   distance ~490km via OpenRouteService/haversine)
10. `action_high_emission_alert` does NOT fire — the best-scoring option
    (train) is green, not red
11. Bot presents: train option, Hôtel Vert Rive Gauche (eco-certified,
    Paris), local co-op food market tour, carbon estimate + disclaimer

**Branching point demonstrated:** sustainability_pref directly changes which
transport mode wins the scoring function.

## Scenario 2 — Eco-tour in a rural/nature destination (intercontinental, local_culture preference)

London -> Nairobi, specific dates, 1 traveller, comfort budget, local_culture preference.

1-6. Same form flow, destination = Nairobi (an intercontinental pair — no
     train/coach/car rows exist for this route in `transport_option`)
7. `action_estimate_carbon` finds only `flight` is offered for this route
   (per our schema design: ground modes aren't seeded intercontinentally);
   distance computed via haversine using `city.latitude/longitude`,
   Aviationstack queried for a real LHR->NBO flight if one exists that day
8. `action_recommend_plan` scores with local_culture weighting -> flight is
   the *only* option, so it "wins" by default
9. `action_high_emission_alert` **fires** — the best (only) available option
   is still carbon-intensive (long-haul flight) — bot surfaces a carbon
   offset suggestion alongside the result (Gold Standard / Verra, priced
   per tonne from `offset_option`)
10. Bot presents: the real flight (if Aviationstack had one for that date),
    the community wildlife conservancy visit experience, and the offset
    options

**Branching point demonstrated:** when only one transport mode exists for a
route, the high-emission alert becomes the primary sustainability lever
instead of mode selection — a genuinely different conversational shape than
Scenario 1, worth highlighting in the report as evidence of adaptive
branching logic (LO1).

## Scenario 3 — Carbon-neutral business trip (intra-Europe, tight dates, balanced preference)

Berlin -> Copenhagen, specific near-term date, 1 traveller, comfort budget,
balanced preference.

1-6. Same form flow, specific (non-flexible) date entered as free text
7. `action_estimate_carbon` runs for all modes on this route
8. `action_recommend_plan` scores with balanced weights (0.50/0.50) ->
   flight may still win on a tight-timeline route despite higher carbon
   score, because time pressure isn't itself a scoring input but a
   comfort-budget traveller's price sensitivity is low, letting carbon
   dominate less than in Scenario 1's low_carbon case
9. `action_high_emission_alert` fires if the winning option is red -> offers
   a carbon offset alongside the flight (Copenhagen: Nordic Eco Stay hotel,
   urban cycling tour experience)
10. Bot offers `request_human` explicitly here as a suggested next step
    ("business trip" complexity is a natural trigger for human advisor
    handover per FR-08, even without a fallback)

**Branching point demonstrated:** the same scoring function under a
different preference/budget combination produces a different outcome than
Scenario 1, and this scenario deliberately exercises the human-handover path
on request rather than via fallback.

## Scenario 4 — Budget-conscious family trip (intercontinental, eco_certified preference)

Toronto -> Bangkok, "family of four", flexible dates, budget budget, eco_certified preference.

1. User: "I want to plan a trip" -> `plan_trip` -> form activates
2. Bot asks origin -> user types "Toronto" (typed, not tapped, to also exercise
   free-text city resolution)
3. Bot asks destination -> user types "Bangkok"
4. Bot asks travel date -> user taps "I'm flexible"
5. Bot asks travellers -> user types "family of four" -> `validate_trip_planning_form`
   parses this phrase to `num_travellers = 4` (same free-text parsing pattern
   noted in the reference repo's validator)
6. Bot asks budget -> user taps "Budget"
7. Bot asks sustainability preference -> user taps "Eco-certified hotels"
8. Form completes -> only `flight` exists for this intercontinental route
   (no ground transport_option rows seeded), distance via haversine,
   Aviationstack queried for a real YYZ->BKK flight
9. `action_recommend_plan` scores with eco_certified weights (0.70 carbon /
   0.30 price) -> since transport has only one option, the weighting mainly
   affects **hotel selection** — a hotel with `eco_certification` set and a
   high `sustainability_score` is prioritised over a cheaper uncertified one,
   even on a budget-tier trip
10. Bot presents: the flight, an eco-certified hotel appropriate for 4
    travellers, the floating market tour experience, offset suggestion

**Branching point demonstrated:** free-text slot parsing (traveller-count
phrase, typed cities) rather than button taps, and eco_certified preference
changing hotel ranking specifically rather than transport ranking.

## Scenario 5 — Ambiguous input and fallback escalation to human handover

User provides vague/ambiguous answers throughout; no clean happy path.

1. User: "plan something" -> low intent confidence -> `action_scoped_fallback`
   stage 1: constrained re-prompt with quick-reply buttons (FR-10)
2. User taps "Plan a trip" -> form activates normally
3. Bot asks destination -> user types "Bankok" (typo) -> `action_clarify_destination`
   fires: "Did you mean Bangkok?" confirmation (FR-03)
4. User confirms -> destination slot filled correctly
5. Bot asks travel date -> user types something unparseable ("sometime maybe
   idk") -> second low-confidence fallback -> `action_scoped_fallback`
   stage 2: after 2 consecutive fallbacks, offers `request_human` explicitly
   alongside the constrained re-prompt (FR-09, FR-10)
6. User taps "Talk to a human" -> `action_handover` packages whatever slots
   *were* successfully collected (origin, destination) plus a `reason` of
   `fallback_escalation` -> `handover_log` row created with `status = pending`

**Branching point demonstrated:** this is the only scenario where the
conversation never reaches `action_recommend_plan` at all — it demonstrates
the error-recovery path (FR-10) and the `reason` field on `handover_log`
distinguishing an escalation from a deliberate `request_human` ask, both of
which the admin console's handover list will need to display differently.

## Cross-cutting flows (apply to all five scenarios)

- **Typo correction**: origin/destination handled by `action_clarify_destination`
  — e.g. "Pariiis" -> "Did you mean Paris?" confirmation before proceeding.
- **Go back / edit answer**: at any point after a slot is filled, `go_back`
  or `edit_answer` intents reopen the relevant question without restarting
  the form.
- **Fallback escalation**: two consecutive low-confidence messages trigger
  `action_scoped_fallback`'s constrained re-prompt; a third offers
  `request_human` (FR-10).
- **Reset**: `reset_trip` clears all trip slots and restarts cleanly (FR-12).

## Visual flow diagram

`docs/architecture_diagram_v2.svg` (or the interactive version generated in
chat) shows the core flow through its three decision points — typo check,
high-emission alert, human handover request — using Scenario 1's numbers as
the illustrated happy path (straight down through all three "no" branches),
with the "yes" branch at each decision point noting which other scenario
lives there:
- **Typo decision "yes"** -> the clarification step exercised fully in
  Scenario 5
- **High-emission decision "yes"** -> the primary lever in Scenario 2
  (intercontinental, flight-only routes)
- **Human-requested decision "yes"** -> Scenario 5's handover endpoint, and
  Scenario 3's deliberate on-request handover