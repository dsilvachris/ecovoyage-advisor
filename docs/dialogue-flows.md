# Additions to `docs/dialogue-flows.md`

Two new scenarios covering arbitrary-destination support (FR-15, FR-16, FR-17).
Append after the existing five. All transcripts below are taken from actual
verified runs against the deployed system, not illustrative mock-ups.

---

## Scenario 6 — Non-curated destination, short European route

**Purpose.** Demonstrates FR-15 (arbitrary city support), FR-16 (transparent
data tiering) and FR-17 (synthesised ground transport) together. This is the
scenario that exposed the flight-recommendation bug during development.

**Setup.** Munich → Zurich. Neither city is one of the 21 curated
destinations; the route has no seeded `transport_option` rows; straight-line
distance is 242 km, well within the 1500 km ground-transport threshold.

### Transcript

| Turn | Speaker | Content |
|---|---|---|
| 1 | User | *Plan a trip* |
| 2 | Bot | Where are you travelling from? *(city buttons + location option)* |
| 3 | User | Munich |
| 4 | Bot | 📍 I found Munich, Bavaria, Germany. It's not one of our curated eco-destinations, so I'll estimate your trip's carbon footprint but won't have verified eco-certified stays there. |
| 5 | Bot | Which destination would you like to explore? |
| 6 | User | Zurich |
| 7 | Bot | 📍 I found Zurich, Canton of Zurich, Switzerland. *(same caveat)* |
| 8 | Bot | *(date → duration → travellers → budget → priority)* |
| 9 | Bot | **Getting there — Munich to Zurich** (balanced) — 3 day trip:<br>1. Train — 278.14 km, ~€63.38, ~16.69 kg CO2e — green **[RECOMMENDED]**<br>2. Coach — 278.14 km, ~€36.69, ~57.85 kg CO2e — amber<br>3. Car — 321.06 km, ~€77.05, ~122.0 kg CO2e — amber<br>*(Ground options for this route are estimated from distance — we don't have curated timetable data for it yet.)* |
| 10 | Bot | Zurich isn't one of our curated eco-destinations… *(certification guidance)* |
| 11 | Bot | **Offset the rest:** Verra (VCS), Climate Impact Partners |
| 12 | Bot | *(carbon estimation disclaimer)* |

### What this demonstrates

- Both cities resolved through geocoding with region and country stated back,
  so the user can confirm the right places were selected.
- Ground transport synthesised where none was seeded — rail correctly ranked
  first rather than flight.
- The estimated-route disclaimer distinguishes synthesised options from curated
  data without hiding them.
- The hotel gap is stated as a scoped limitation with practical guidance, not
  presented as a failure.

### Development note

Before FR-17 was implemented, turn 9 offered only a flight (241.86 km,
119.0 kg CO2e, amber) because ground transport existed solely for seeded city
pairs. Recommending a flight for a 240 km journey directly contradicted the
product's purpose. This was caught during testing rather than by a user, and
drove the synthesised-transport requirement.

---

## Scenario 7 — Ambiguous city name

**Purpose.** Documents how the system handles city names shared across
countries or regions — raised by the module assessor as a concern during
live demonstration.

**Setup.** The user types "Springfield", which matches four distinct US cities
(Missouri, Illinois, Massachusetts, Ohio) in the geocoding results.

### Transcript

| Turn | Speaker | Content |
|---|---|---|
| 1 | User | *Plan a trip* |
| 2 | Bot | Where are you travelling from? |
| 3 | User | Springfield |
| 4 | Bot | 📍 I found Springfield, Missouri, United States. It's not one of our curated eco-destinations… |
| 5 | Bot | Which destination would you like to explore? |

### Current behaviour

The geocoder's highest-ranked result is accepted, and the full location —
including region and country — is stated back. If the user meant a different
Springfield, the discrepancy is visible immediately and ↺ Reset restarts the
trip.

### Attempted alternative

A button-based disambiguation flow was built, offering one button per candidate:

> There are a few places called Springfield — which one did you mean?
> `[Springfield, Missouri, United States]` `[Springfield, Illinois, United States]` …

Supporting logic was implemented and verified in isolation, including a
population-dominance heuristic (10:1 ratio) so that genuinely dominant matches
skip the prompt — "Zurich" (Switzerland, ~400k, vs. a 700-person Montana
settlement) resolves silently, while "Springfield" (170k vs. 115k) would ask.

The flow could not be made reliable end-to-end: Rasa discards messages
dispatched from an `extract_<slot>` method that returns without filling its
slot, and the form's own re-ask overwrites them. Four mitigations were
attempted and measured before the feature was withdrawn. Full analysis in
`docs/testing-log.md`.

### Residual risk

A user could be shown a different Springfield than intended. Mitigated by
always stating the resolved region and country, and by Reset being available
at any point. Worth noting that curated cities are matched before geocoding is
attempted, so a user typing "Paris" reaches curated Paris, France rather than
any ambiguity — the risk applies only to names outside the curated set.