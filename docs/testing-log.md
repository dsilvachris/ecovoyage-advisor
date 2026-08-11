# Testing log — Phase 3 manual verification

STATUS: captures the manual, scenario-based testing conducted after building
actions.py, before Task 5's formal rasa test nlu/rasa test core/pytest
suite. This log is a primary source for the report's Testing section —
each entry below maps to a real bug found and fixed against the live
system (NeonDB + all 4 external APIs), not a hypothetical.

## Methodology

Testing was conducted two ways:
1. **`rasa shell`** — for straightforward happy-path walkthroughs.
2. **Direct REST calls via `curl`** against `/webhooks/rest/webhook` — used
   whenever `rasa shell`'s interactive menu made it ambiguous whether a
   free-text phrase or a menu selection had actually been sent (see Bug 6
   below, where this ambiguity itself caused a false negative). Sending
   raw JSON payloads directly removes that ambiguity entirely and proved
   essential for diagnosing several of the harder bugs.

Each of the 5 dialogue scenarios in `docs/dialogue-flows.md` was tested
against the live NeonDB instance and all 4 external APIs (no mocking),
which is why several bugs only surfaced once specific data conditions were
met (e.g. a route with real seeded ground transport, a route with no
seeded IATA-relevant data, a genuinely fuzzy-matchable typo).

## Scenario verification summary

| # | Scenario | Route tested | Result |
|---|---|---|---|
| 1 | Short city break, low_carbon | London -> Paris | Train correctly won over flight (495km, €89.40, 29.7kg CO2e, green) |
| 2 | Intercontinental eco-tour, high-emission alert | London -> Nairobi | Alert + offsets fired correctly (6820.5km, 1677.84kg CO2e, red) |
| 3 | Human handover with full context | London -> Paris | `handover_log.context_json` verified populated with real trip data, not null |
| 4 | Free-text entry + phrase parsing | Toronto -> Bangkok | "family of four" correctly parsed to `num_travellers=4`; verified via price-total cross-check (€5067.32 = ×4 travellers) |
| 5 | Typo confirmation + fallback escalation | Bangkok(typo) -> Paris | Both a critical bug and a critical bug fix verified live (see Bugs 8-9) |

## Bug log

Nine real defects were found and fixed during this phase, each reproduced
against the live system and confirmed resolved by rerunning the exact
scenario that exposed it.

### 1. Broken relative imports (ModuleNotFoundError)
**Symptom:** action server failed to register any actions at startup.
**Cause:** `actions.py` used absolute imports (`import carbon`) for sibling
modules within the `actions/` package; Python's import system requires
relative imports (`from . import carbon`) when the file is loaded as part
of a package, which is how `rasa-sdk` loads it.
**Fix:** converted all intra-package imports to relative form.
**Relevance:** infrastructure defect, not tied to a specific FR — but
without this fix, zero actions were reachable.

### 2. Contextmanager single-yield violation (RuntimeError)
**Symptom:** `RuntimeError: generator didn't stop after throw()` on any
database query failure.
**Cause:** `db.py`'s `get_cursor()` context manager attempted to `yield`
twice — once for the cursor, once again inside an `except` block on query
failure — which violates Python's `@contextmanager` single-yield
requirement.
**Fix:** moved query-level error handling out of `get_cursor()` and into
each individual function in `repository.py`, so `get_cursor()` only ever
yields once (or yields `None` if connection acquisition itself fails).
**Relevance:** NFR-04 (graceful degradation) — the original design intent
was correct, the implementation had a structural bug.

### 3. Strict rule vs. story contradiction (InvalidRule)
**Symptom:** `rasa train` failed outright with `InvalidRule: Contradicting
rules or stories found`.
**Cause:** a rule with no `condition:` block is a global constraint in
Rasa ("this action must ALWAYS follow that one"), not a default that
stories can override. A rule forcing `utter_carbon_disclaimer` immediately
after `action_recommend_plan` contradicted every story that ended the
turn right after `action_recommend_plan` (implicit `action_listen`).
**Fix:** removed the rule; placed `utter_carbon_disclaimer` explicitly and
consistently in every story instead.
**Relevance:** a genuine framework-semantics lesson relevant to discussing
Rasa's rule/story model in the report's technical implementation section.

### 4. Button payload NLG interpolation errors
**Symptom:** non-fatal `KeyError` spam in server logs on every quick-reply
button response (e.g. `utter_ask_origin`).
**Cause:** Rasa's NLG interpolator calls `.format()` on every response
string, including button payloads. A payload like
`/inform{"origin": "London"}` was misread as containing a format
placeholder.
**Fix:** escaped literal braces in `domain.yml` payloads by doubling them
(`{{`/`}}`), which `.format()` correctly resolves to a single literal
brace.
**Relevance:** NFR-01 (usability) — cosmetic to the user but noisy for
debugging; worth noting as a Rasa-specific gotcha in the report.

### 5. Button taps not extracting correctly (silent extraction failure)
**Symptom:** tapping a quick-reply button appeared to work, but the
underlying `extract_origin`/`extract_destination` methods were matching
against the raw command string (`/inform{"origin": "London"}`) rather than
the parsed entity, since the code only read `tracker.latest_message.text`.
**Cause:** Rasa parses button-tap payloads into proper entities via its
`RegexMessageHandler`, but the original extraction code never consulted
`tracker.latest_message["entities"]` at all.
**Fix:** both extraction methods now check for a matching entity first,
falling back to raw text only if no entity was found — covering both
button-tap and free-text NLU paths correctly.
**Relevance:** FR-01 — this bug meant button-driven trip planning was
silently broken from the start of testing; only surfaced through direct
inspection of `extract_origin`'s logic, not from surface-level symptoms.

### 6. Missing ground-transport seed data
**Symptom:** every intra-Europe route (including Berlin->Copenhagen)
returned flight-only recommendations regardless of `sustainability_pref`.
**Cause:** `db/seed.sql` never actually populated any `transport_option`
rows for any route — an oversight from Phase 1, invisible until a
low-carbon-preference test on a route that should have had train/coach
options.
**Fix:** added curated `transport_option` rows (train/coach/car, both
directions) for a spread of intra-Europe city pairs, consolidated into the
canonical seed file.
**Relevance:** FR-06 (weighted scoring) — the scoring function itself was
correct throughout; this was a data-completeness gap that made it
impossible to observe the function actually discriminating between modes.

### 7. Decimal/float type mismatch (TypeError)
**Symptom:** `TypeError: unsupported operand type(s) for *: 'float' and
'decimal.Decimal'` — first appeared only once Bug 6 was fixed and a real
curated distance was available to use.
**Cause:** `psycopg2` correctly returns PostgreSQL `NUMERIC` columns as
Python `Decimal` (to preserve precision), but `routing.py`'s
`get_distance_km()` passed that value straight through without conversion;
Python does not allow direct arithmetic between `float` and `Decimal`.
**Fix:** explicit `float()` conversion at the point the curated distance
is returned.
**Relevance:** a reminder that ORM/driver type behavior (psycopg2's
`Decimal` mapping) needs to be handled explicitly at integration
boundaries — worth a line in the report's technical-implementation
reflection.

### 8. Unreliable high-emission alert (FR-07 silently skipped)
**Symptom:** on a confirmed red-carbon trip (London->Nairobi), the
high-emission alert sometimes failed to display at all.
**Cause:** the alert was implemented as a separate action
(`action_high_emission_alert`) whose invocation depended on `TEDPolicy`
correctly predicting it after `action_estimate_carbon` — but two different
action sequences were possible from that same point (straight to
`action_recommend_plan`, or via the alert first), which is inherently
ambiguous for a policy trained on limited story examples. `rasa train` had
in fact been warning about this exact structural conflict since the first
successful training run.
**Fix:** removed the standalone action; folded the check into a plain
Python conditional called directly inside `action_recommend_plan`, keyed
on the `carbon_level` slot. This also permanently resolved the story
conflict, since every story now has one deterministic action sequence.
**Relevance:** FR-07 directly, and a substantive case study for the
report: a genuinely user-visible functional requirement was being
satisfied "most of the time" by a probabilistic dialogue policy, when the
underlying decision was actually deterministic and belonged in code, not
in trained behaviour. This is a good example for the "critical evaluation
of AI/NLP techniques" component of Task 1/5.

### 9. Typo-confirmation cross-slot persistence failure + fallback infinite loop
Two compounding bugs, found together via direct tracker-state debugging.

**9a. Cross-slot persistence failure**
**Symptom:** confirming a fuzzy-matched typo ("Bankok" -> "Did you mean
Bangkok?" -> user taps "Yes") looped back to the same question instead of
proceeding.
**Cause:** the original design stored the pending guess in a slot
(`destination_guess`, later `pending_city_guess`) set by
`extract_origin`/`extract_destination` and intended to be read back on the
next turn. Direct inspection of `tracker.current_slot_values()` (added as
temporary debug logging) proved this slot was always `None` on the
following turn, despite being returned correctly by the extraction method
— a limitation of this rasa-sdk version (3.6.2), where a slot returned
from `extract_<X>` that is neither the method's own slot nor a form
`required_slot` is not reliably persisted.
**Fix:** redesigned entirely — the "Yes" confirmation button now encodes
the corrected city directly in its payload (e.g.
`/inform{"origin": "Bangkok"}`), so confirming a typo flows through the
same button-tap -> entity -> exact-match path already proven reliable
everywhere else, with no dependency on any slot surviving between turns.

**9b. Fallback-in-form infinite loop**
**Symptom:** a single low-confidence message inside the form produced 9
identical fallback messages in one response, until Rasa's internal
per-turn action-count safety cap forcibly terminated it.
**Cause:** `action_scoped_fallback`'s in-form branch returned
`FollowupAction("trip_planning_form")`, which re-invokes the form
immediately against the same (still-unparseable) message with no new user
input — producing the same fallback outcome repeatedly within a single
turn.
**Fix:** replaced the `FollowupAction` with a direct dispatch of the
current question's own `utter_ask_<slot>` response, then returns control
to `action_listen` so the user has a genuine opportunity to respond before
anything runs again.

**Relevance:** FR-03 (typo clarification) and FR-10 (fallback recovery) —
both are core error-recovery requirements, and 9a/9b are strong evidence
for the report's "technical robustness" discussion: a defect this subtle
(correct-looking code, wrong framework assumption) genuinely required
live debugging with tracker-state inspection to diagnose, not just code
review.

## Reflection points for the report

- **Live, non-mocked testing surfaced defects code review didn't** — Bugs
  6, 7, 8, and 9 in particular were invisible from reading the code alone
  and only appeared once real data conditions (a specific route, a
  specific typo, a specific NUMERIC column) were exercised.
- **Rasa's dialogue policies are probabilistic; some decisions need to be
  deterministic** — Bug 8 is the clearest example: a requirement that
  "must always happen when X is true" should be code, not trained
  behaviour, however tempting it is to model it as a story branch.
- **Framework version-specific limitations exist and aren't always
  documented** — Bug 9a required direct empirical verification
  (`tracker.current_slot_values()` logging) rather than trusting the
  documented API contract, since the actual behaviour of `extract_<X>`
  slot-setting for non-required slots differed from what the rasa-sdk
  docs implied.
- **Testing tool choice matters** — switching from `rasa shell`'s
  interactive menu to direct `curl` REST calls was itself a debugging
  decision that resolved ambiguity (Bug 6 in particular) and should be
  mentioned as a deliberate methodological choice, not an afterthought.

## Not yet covered by this manual pass

- `rasa test nlu` (intent/entity accuracy, confusion matrix) — Task 5
- `rasa test core` (story/rule coverage beyond the 5 manually-run
  scenarios) — Task 5
- `pytest` unit tests with mocked API responses (success/fail/edge case
  per action) — Task 5
- User testing / Likert survey — Task 5

## rasa test nlu — cross-validation, after targeted data expansion

Same command, run after expanding `out_of_scope` (8 -> 15 examples) and
`bot_challenge` (8 -> 12 examples) in `data/nlu.yml`.

| Metric | Before | After | Change |
|---|---|---|---|
| Intent Test Accuracy | 0.665 (±0.093) | 0.733 (±0.045) | +0.068 |
| Intent Test F1 | 0.635 (±0.095) | 0.703 (±0.055) | +0.068 |
| Intent Test Precision | 0.641 (±0.105) | 0.711 (±0.069) | +0.070 |
| Entity Test F1 (DIETClassifier) | 0.305 (±0.046) | 0.342 (±0.041) | +0.037 |

**Interpretation:** a real, measurable improvement from a small, targeted
intervention — adding 7 `out_of_scope` and 4 `bot_challenge` examples
raised intent accuracy by ~7 points and, notably, reduced the standard
deviation across folds (0.093 -> 0.045), indicating a more stable model,
not just a favourable split. The updated confusion matrix shows
`out_of_scope` reaching full correct classification on at least one fold
(14/14), directly confirming the diagnosis from the first run.

**What this demonstrates for the report:** a concrete instance of the
"train -> evaluate -> diagnose -> refine -> re-evaluate" cycle (LO2),
with before/after evidence rather than an unverified claim of improvement.

**Remaining limitation, stated honestly:** intent accuracy at 0.733 and
entity F1 at 0.342 are still well below the train-fold scores (1.000 and
0.982 respectively), confirming the dataset remains small relative to
DIETClassifier's capacity. Further improvement would require materially
more examples per intent — a genuine scope/time tradeoff for this
project, not a claim that the gap is closed. Given more time, `affirm` vs
`inform` confusion (still present in this run) would be the next target,
since single-word affirmatives carry limited distinguishing signal against
`inform`'s broad vocabulary.

## rasa test core — initial run and diagnosis

First run against `tests/test_stories/test_stories.yml` showed only 3/10
stories passing (0.300 conversation-level accuracy), with every failure
showing the identical pattern: `action_scoped_fallback` predicted instead
of the expected next step, starting immediately after the first user turn
inside the active form.

**Diagnosis:** the test stories, as originally written, omitted the
repeated `action: trip_planning_form` step that must appear after every
user turn while a form is active. Training stories in `data/stories.yml`
can use a compact shorthand (a single `active_loop: trip_planning_form`
line covering the whole multi-turn form sequence) and this trained
correctly — but `rasa test core`'s exact-match evaluation against a test
story requires every intermediate action to be spelled out explicitly.
Skipping this in the test stories meant the tracker states being evaluated
were never actually seen during training, which pushed `RulePolicy`'s
`core_fallback_threshold` (0.4) below confidence and triggered the
fallback safety net at nearly every step.

**Confirmed as a test-authoring issue, not a model defect,** by the fact
that all 5 real scenarios these test stories represent had already passed
cleanly in extensive live testing (see the manual scenario verification
section above) using the exact same form-filling sequences.

**Fix:** rewrote all 10 test stories with the explicit
`trip_planning_form` step included after every in-form user turn.

**Reflection for the report:** this is a genuine, citable nuance of Rasa's
story format — the shorthand that's valid for *training* data is not
sufficient for *test* data's stricter exact-match evaluation, which is
easy to miss and not obviously documented. Worth a line in the Testing
section as an example of framework-specific tooling behaviour discovered
through direct experimentation rather than assumed from the docs.