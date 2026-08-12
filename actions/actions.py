"""
actions.py — custom Rasa actions for EcoVoyage Advisor.

Ties together carbon.py, routing.py, geo.py, aviation.py, and repository.py
into the actions declared in domain.yml. See docs/dialogue-flows.md for the
5 scenarios these implement, and docs/requirements.md for the FR-xx
references in comments below.

RESOLVED DESIGN DECISIONS:

1. data_source ambiguity (deferred from routing.py): trip_session.data_source
   in NeonDB reflects ONLY the winning transport option's CARBON data source
   ('climatiq' | 'stored'), matching carbon.py's estimate_co2e() output.
   routing.py's own data_source ('openrouteservice' | 'stored' | 'estimated')
   is used internally to pick a distance and is not persisted separately.

2. Avoiding duplicate Climatiq/Aviationstack calls across actions: three
   new slots were added to domain.yml (recommended_mode,
   recommended_distance_km, recommended_price_eur) so action_estimate_carbon's
   scoring result is reused by action_recommend_plan rather than
   recomputed. This is also what lets aviation.py's get_sample_flight() be
   called from exactly one place, only when the winning mode is 'flight'
   (the "call sparingly" quota decision documented in aviation.py).

3. action_scoped_fallback: implemented as a single-behavior action, not a
   literal 3-strike counter — see class docstring below for why.

4. FR-07 high-emission alert: originally a separate action
   (action_high_emission_alert) invoked via stories/TEDPolicy. This created
   a genuine story-structure conflict (two different action sequences
   possible after action_estimate_carbon) that TEDPolicy sometimes
   mispredicted in live testing, silently skipping the alert on a real
   red-carbon trip. Fixed by moving the check into a plain Python
   conditional called directly from ActionRecommendPlan
   (_dispatch_high_emission_alert_if_needed), so it fires 100% reliably
   based on the carbon_level slot rather than depending on model
   confidence. This also permanently resolved the story conflict.

5. Typo confirmation (FR-03) — REDESIGNED after live debugging: the
   original approach stored a fuzzy-match guess in a cross-slot
   (pending_city_guess) set by extract_origin/extract_destination, to be
   read back and consumed on the next turn when the user replied
   affirm/deny. Live debugging (full tracker.current_slot_values() dumps)
   proved this rasa-sdk version (3.6.2) does not reliably persist a slot
   returned from extract_<X> when that slot isn't the one the method is
   named for and isn't a form required_slot — the slot was always None on
   the following turn despite being returned correctly. Redesigned so the
   "Did you mean X?" confirmation's "Yes" button payload directly encodes
   the corrected city as /inform{"origin": "X"} (or "destination"), so
   confirming a typo flows through the exact same button-tap -> entity ->
   exact-match path already proven reliable everywhere else in the app.
   No cross-turn slot dependency at all — action_clarify_destination is
   kept registered only for symmetry with domain.yml/stories.yml, and now
   does nothing (see its docstring).

6. Multi-option recommendations: ActionRecommendPlan originally showed only
   the single winning transport option and single best hotel. Reworked to
   show up to 3 ranked transport options, up to 3 ranked hotels, and up to
   2 experiences, matching the reference demo's "Getting there /
   Eco-friendly stays / Low-impact experiences / Offset the rest" layout.
   The winning option is still what's used for carbon_level/estimated_co2
   (and hence FR-07's alert trigger) — showing more options is purely
   additive, not a change to which one is "recommended". A new slot,
   transport_options_json, carries the top-3 transport summary from
   ActionEstimateCarbon to ActionRecommendPlan as a JSON string (same
   pattern as the existing recommended_mode/distance/price slots, just
   holding a list instead of a single value). Offset options are now
   always shown at the end of every recommendation, not only on red-carbon
   routes — the red-carbon alert's own offset mention was removed to avoid
   showing the same list twice.
"""
import json
import logging
from typing import Any, Text, Dict, List, Optional

from rasa_sdk import Action, FormValidationAction, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, ActiveLoop, FollowupAction

from . import carbon
from . import routing
from . import geo
from . import aviation
from . import repository

logger = logging.getLogger(__name__)

REQUIRED_SLOTS_ORDER = [
    "origin",
    "destination",
    "travel_date",
    "trip_duration_days",
    "num_travellers",
    "budget",
    "sustainability_pref",
]

# FR-06 weighted scoring: carbon vs price weight per sustainability preference
SCORING_WEIGHTS = {
    "low_carbon":    {"carbon": 0.80, "price": 0.20},
    "eco_certified": {"carbon": 0.70, "price": 0.30},
    "local_culture": {"carbon": 0.50, "price": 0.50},
    "balanced":      {"carbon": 0.50, "price": 0.50},
}

FIELD_TO_SLOT = {
    "origin": "origin",
    "destination": "destination",
    "travel date": "travel_date",
    "dates": "travel_date",
    "trip duration": "trip_duration_days",
    "duration": "trip_duration_days",
    "number of travellers": "num_travellers",
    "travellers": "num_travellers",
    "budget": "budget",
    "sustainability preference": "sustainability_pref",
    "preference": "sustainability_pref",
}


# --------------------------------------------------------------------------
# Small parsing helpers (free-text slot normalization — FR-01)
# --------------------------------------------------------------------------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8,
}


def _parse_traveller_count(raw: str) -> Optional[int]:
    """Parses phrases like '2', 'just me', 'me and my wife', 'family of
    four' into a traveller count. Returns None if unparseable."""
    text = raw.lower().strip()

    if "just me" in text or text in ("me", "myself", "solo", "1"):
        return 1

    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        try:
            n = int(digits)
            if 1 <= n <= 20:
                return n
        except ValueError:
            pass

    for word, value in _NUMBER_WORDS.items():
        if word in text:
            return value

    if "me and" in text or "and my" in text:
        return 2

    return None

def _parse_trip_duration(raw: str) -> Optional[int]:
    """Parses phrases like '3', '3 days', 'a week', 'weekend' into a
    number of days. Returns None if unparseable."""
    text = raw.lower().strip()

    if "weekend" in text:
        return 2
    if "week" in text:
        return 7

    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        try:
            n = int(digits)
            if 1 <= n <= 90:
                return n
        except ValueError:
            pass

    for word, value in _NUMBER_WORDS.items():
        if word in text:
            return value

    return None


def _parse_budget_tier(raw: str) -> Optional[str]:
    text = raw.lower().strip()
    if text in ("budget", "mid", "comfort"):
        return text
    if any(w in text for w in ("budget", "cheap", "afford", "low cost")):
        return "budget"
    if any(w in text for w in ("mid", "moderate", "medium")):
        return "mid"
    if any(w in text for w in ("comfort", "premium", "upscale")):
        return "comfort"
    return None


def _parse_sustainability_pref(raw: str) -> Optional[str]:
    text = raw.lower().strip()
    if text == "low_carbon" or "low carbon" in text or "lowest carbon" in text:
        return "low_carbon"
    if text == "eco_certified" or "eco" in text or "certified" in text:
        return "eco_certified"
    if text == "local_culture" or "local" in text or "community" in text:
        return "local_culture"
    if "balanced" in text or "balance" in text or "mix" in text:
        return "balanced"
    if "carbon" in text:
        return "low_carbon"
    return None


# --------------------------------------------------------------------------
# City resolution helper shared by extract_origin / extract_destination
# --------------------------------------------------------------------------

def _resolve_city_input(raw_text: str) -> Dict[str, Any]:
    """
    Resolves free text (or a 'geo:LAT,LON' GPS payload — FR-02) to a
    supported city.

    Returns one of:
      {"status": "exact", "name": <city name>}
      {"status": "fuzzy", "guess": <city name>}
      {"status": "none"}
    """
    text = raw_text.strip()

    if text.lower().startswith("geo:"):
        try:
            lat_str, lon_str = text[4:].split(",")
            lat, lon = float(lat_str), float(lon_str)
            cities = repository.get_supported_cities()
            if not cities:
                return {"status": "none"}
            resolved = geo.resolve_gps_location(lat, lon, cities)
            return {"status": "exact", "name": resolved["city_name"], "via_gps": True}
        except (ValueError, IndexError):
            return {"status": "none"}

    exact = repository.resolve_city(text)
    if exact:
        return {"status": "exact", "name": exact["name"]}

    cities = repository.get_supported_cities()
    supported_names = [c["name"] for c in cities]
    guess = geo.find_city_typo_match(text, supported_names)
    if guess:
        return {"status": "fuzzy", "guess": guess}

    return {"status": "none"}


def _dispatch_city_confirmation(dispatcher: CollectingDispatcher, slot_name: str, guess: str) -> None:
    """FR-03 — see module docstring, point 5. The "Yes" button carries the
    corrected city directly in its /inform payload rather than relying on
    a slot surviving to the next turn. Single braces here, NOT double —
    this text is built directly in Python and sent via
    dispatcher.utter_message(), so it never passes through Rasa's NLG
    .format() interpolator (that's only for domain.yml response templates,
    which is why utter_ask_origin etc. needed doubled {{ }} but this
    doesn't)."""
    dispatcher.utter_message(
        text=f"Did you mean {guess}?",
        buttons=[
            {"title": "Yes", "payload": f'/inform{{"{slot_name}": "{guess}"}}'},
            {"title": "No", "payload": "/deny"},
        ],
    )


# --------------------------------------------------------------------------
# Transport / hotel scoring (FR-06)
# --------------------------------------------------------------------------

def _score_transport_options(
    origin_city: Dict[str, Any],
    destination_city: Dict[str, Any],
    num_travellers: int,
    sustainability_pref: str,
) -> List[Dict[str, Any]]:
    """
    Computes carbon + price for every transport mode available on this
    route, scores them per FR-06, and returns them best-first (lowest score
    first). Each option carries a data_source ('climatiq'|'stored') from
    carbon.py.
    """
    rows = repository.get_transport_options_for_route(origin_city["id"], destination_city["id"])
    options = []

    for row in rows:
        mode = row["mode_name"]

        if mode == "flight":
            distance_km = routing.haversine_km(
                origin_city["latitude"], origin_city["longitude"],
                destination_city["latitude"], destination_city["longitude"],
            )
            distance_source = "haversine"
        else:
            dist_result = routing.get_distance_km(
                mode,
                origin_city["latitude"], origin_city["longitude"],
                destination_city["latitude"], destination_city["longitude"],
                row["curated_distance_km"],
            )
            distance_km = dist_result["distance_km"]
            distance_source = dist_result["data_source"]

        carbon_result = carbon.estimate_co2e(
            mode, distance_km, num_travellers, float(row["kg_co2e_per_pax_km"])
        )

        price_total = round(
            (float(row["base_price_eur"]) + float(row["price_per_km"]) * distance_km)
            * num_travellers,
            2,
        )

        options.append({
            "mode_name": mode,
            "distance_km": round(distance_km, 2),
            "distance_source": distance_source,
            "price_total_eur": price_total,
            "co2e_total_kg": carbon_result["co2e_total_kg"],
            "carbon_level": carbon_result["carbon_level"],
            "data_source": carbon_result["data_source"],
        })

    if not options:
        return []

    max_co2e = max(o["co2e_total_kg"] for o in options) or 0.0001
    max_price = max(o["price_total_eur"] for o in options) or 0.0001
    weights = SCORING_WEIGHTS.get(sustainability_pref, SCORING_WEIGHTS["balanced"])

    for o in options:
        norm_carbon = o["co2e_total_kg"] / max_co2e
        norm_price = o["price_total_eur"] / max_price
        o["score"] = weights["carbon"] * norm_carbon + weights["price"] * norm_price

    options.sort(key=lambda o: o["score"])
    return options


def _score_hotels_ranked(
    hotels: List[Dict[str, Any]], sustainability_pref: str, top_n: int = 3
) -> List[Dict[str, Any]]:
    """Ranks all hotels for a destination per FR-06's weighting, returning
    up to top_n. Most destinations currently have only 1-2 hotels seeded
    (db/seed.sql coverage is sparse — see its own docstring), so this
    often just returns everything available, ranked. Replaces the earlier
    single-winner _score_hotels now that ActionRecommendPlan shows a
    ranked list rather than just the top pick."""
    if not hotels:
        return []

    max_carbon = max(float(h["carbon_score"]) for h in hotels) or 0.0001
    max_price = max(float(h["nightly_price_estimate"]) for h in hotels) or 0.0001
    weights = SCORING_WEIGHTS.get(sustainability_pref, SCORING_WEIGHTS["balanced"])

    scored = []
    for h in hotels:
        norm_carbon = float(h["carbon_score"]) / max_carbon
        norm_price = float(h["nightly_price_estimate"]) / max_price
        score = weights["carbon"] * norm_carbon + weights["price"] * norm_price
        scored.append((score, h))

    scored.sort(key=lambda pair: pair[0])
    return [h for _, h in scored[:top_n]]


# --------------------------------------------------------------------------
# Form validation (FR-01, FR-02, FR-03)
# --------------------------------------------------------------------------

class ValidateTripPlanningForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_trip_planning_form"

    async def extract_origin(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        if tracker.get_slot("requested_slot") != "origin":
            return {}

        latest_intent = tracker.latest_message.get("intent", {}).get("name")
        if latest_intent == "deny":
            dispatcher.utter_message(text="No problem — where are you travelling from?")
            return {}

        # Prefer the entity Rasa already extracted (covers both button taps,
        # which arrive as /inform{"origin": "City"} payloads parsed by
        # Rasa's RegexMessageHandler, and free-text NLU extraction) — only
        # fall back to raw text if no entity was found at all.
        entities = tracker.latest_message.get("entities", [])
        entity_value = next((e["value"] for e in entities if e["entity"] == "origin"), None)
        raw = entity_value if entity_value else tracker.latest_message.get("text", "")

        result = _resolve_city_input(raw)

        if result["status"] == "exact":
            if result.get("via_gps"):
                dispatcher.utter_message(
                    text=f"📍 We've detected your location near {result['name']} — setting that as your departure city."
                )
            return {"origin": result["name"]}
        if result["status"] == "fuzzy":
            _dispatch_city_confirmation(dispatcher, "origin", result["guess"])
            return {}
        return {}

    async def extract_destination(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        if tracker.get_slot("requested_slot") != "destination":
            return {}

        latest_intent = tracker.latest_message.get("intent", {}).get("name")
        if latest_intent == "deny":
            dispatcher.utter_message(text="No problem — which destination did you mean?")
            return {}

        entities = tracker.latest_message.get("entities", [])
        entity_value = next((e["value"] for e in entities if e["entity"] == "destination"), None)
        raw = entity_value if entity_value else tracker.latest_message.get("text", "")

        result = _resolve_city_input(raw)

        if result["status"] == "exact":
            if result["name"] == tracker.get_slot("origin"):
                dispatcher.utter_message(
                    text="That's the same as your origin — where would you like to go instead?"
                )
                return {}
            return {"destination": result["name"]}

        if result["status"] == "fuzzy":
            _dispatch_city_confirmation(dispatcher, "destination", result["guess"])
            return {}

        return {}

    async def validate_travel_date(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        if not slot_value or not str(slot_value).strip():
            dispatcher.utter_message(text="I didn't catch a date — could you try again, or tap 'I'm flexible'?")
            return {"travel_date": None}
        if str(slot_value).lower().strip() in ("flexible", "i'm flexible", "im flexible"):
            return {"travel_date": "flexible"}
        return {"travel_date": str(slot_value).strip()}

    async def validate_trip_duration_days(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        parsed = _parse_trip_duration(str(slot_value))
        if parsed is None:
            dispatcher.utter_message(
                text="Sorry, how many days? A number works, or something like 'a week' or 'weekend'."
            )
            return {"trip_duration_days": None}
        return {"trip_duration_days": parsed}

    async def validate_num_travellers(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        parsed = _parse_traveller_count(str(slot_value))
        if parsed is None:
            dispatcher.utter_message(
                text="Sorry, how many people is that? A number works, or a phrase like 'me and my partner'."
            )
            return {"num_travellers": None}
        return {"num_travellers": parsed}

    async def validate_budget(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        parsed = _parse_budget_tier(str(slot_value))
        if parsed is None:
            dispatcher.utter_message(text="Sorry, is that budget, mid, or comfort?")
            return {"budget": None}
        return {"budget": parsed}

    async def validate_sustainability_pref(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        parsed = _parse_sustainability_pref(str(slot_value))
        if parsed is None:
            dispatcher.utter_message(
                text="Sorry, could you pick one: lowest carbon, eco-certified, local community, or balanced?"
            )
            return {"sustainability_pref": None}
        return {"sustainability_pref": parsed}


# --------------------------------------------------------------------------
# Carbon estimation + scoring (FR-05, FR-06)
# --------------------------------------------------------------------------

class ActionEstimateCarbon(Action):
    def name(self) -> Text:
        return "action_estimate_carbon"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        origin_city = repository.resolve_city(tracker.get_slot("origin"))
        destination_city = repository.resolve_city(tracker.get_slot("destination"))

        if not origin_city or not destination_city:
            dispatcher.utter_message(
                text="I'm having trouble looking up those cities right now — could we try again shortly?"
            )
            return []

        num_travellers = tracker.get_slot("num_travellers") or 1
        sustainability_pref = tracker.get_slot("sustainability_pref") or "balanced"

        options = _score_transport_options(
            origin_city, destination_city, num_travellers, sustainability_pref
        )

        if not options:
            dispatcher.utter_message(
                text="I couldn't find any transport options for that route — let's try a different destination."
            )
            return []

        winner = options[0]
        top_options = options[:3]
        options_summary = [
            {
                "mode": o["mode_name"],
                "distance_km": o["distance_km"],
                "price_eur": o["price_total_eur"],
                "co2_kg": o["co2e_total_kg"],
                "carbon_level": o["carbon_level"],
            }
            for o in top_options
        ]

        return [
            SlotSet("estimated_co2", winner["co2e_total_kg"]),
            SlotSet("carbon_level", winner["carbon_level"]),
            SlotSet("data_source", winner["data_source"]),
            SlotSet("recommended_mode", winner["mode_name"]),
            SlotSet("recommended_distance_km", winner["distance_km"]),
            SlotSet("recommended_price_eur", winner["price_total_eur"]),
            SlotSet("transport_options_json", json.dumps(options_summary)),
        ]


# --------------------------------------------------------------------------
# Recommendation (FR-04, FR-07) — hotels, experiences, transport comparison,
# the high-emission alert, offsets, and the single point where aviation.py
# is called (only when flight is the winner)
# --------------------------------------------------------------------------

def _dispatch_high_emission_alert_if_needed(
    dispatcher: CollectingDispatcher, tracker: Tracker
) -> None:
    """FR-07: fires deterministically based on the carbon_level slot —
    called directly from ActionRecommendPlan's code rather than left as a
    separate action for the dialogue policy to predict. See module
    docstring, point 4, for why."""
    if tracker.get_slot("carbon_level") != "red":
        return

    dispatcher.utter_message(
        text=(
            "Heads up — even the lowest-carbon option for this route is fairly "
            "carbon-intensive. You might consider offsetting the footprint."
        )
    )
    # Offset options are now always listed at the end of the recommendation
    # (see ActionRecommendPlan's "Offset the rest" section below), not
    # duplicated here — see module docstring, point 6.


class ActionRecommendPlan(Action):
    def name(self) -> Text:
        return "action_recommend_plan"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        origin_city = repository.resolve_city(tracker.get_slot("origin"))
        destination_city = repository.resolve_city(tracker.get_slot("destination"))
        if not origin_city or not destination_city:
            dispatcher.utter_message(text="I've lost track of your route — let's start the trip again.")
            return []

        _dispatch_high_emission_alert_if_needed(dispatcher, tracker)

        mode = tracker.get_slot("recommended_mode")
        co2_kg = tracker.get_slot("estimated_co2")
        carbon_level = tracker.get_slot("carbon_level")
        num_travellers = tracker.get_slot("num_travellers") or 1
        sustainability_pref = tracker.get_slot("sustainability_pref") or "balanced"
        duration = tracker.get_slot("trip_duration_days")

        # --- Transport comparison (up to 3 options, ranked) ---
        options_json = tracker.get_slot("transport_options_json")
        try:
            top_options = json.loads(options_json) if options_json else []
        except (TypeError, ValueError):
            top_options = []

        duration_suffix = f" — {duration} day trip" if duration else ""

        if top_options:
            lines = [
                f"Getting there — {origin_city['name']} to {destination_city['name']} "
                f"(sorted by your priority: {sustainability_pref}){duration_suffix}:"
            ]
            for i, o in enumerate(top_options, start=1):
                tag = " [RECOMMENDED]" if i == 1 else ""
                lines.append(
                    f"{i}. {o['mode'].capitalize()} — {o['distance_km']} km, "
                    f"~€{o['price_eur']} total, ~{o['co2_kg']} kg CO2e — {o['carbon_level']}{tag}"
                )
            dispatcher.utter_message(text="\n".join(lines))
        else:
            dispatcher.utter_message(text="I couldn't retrieve transport options for this route.")

        # Only call Aviationstack when flight is the actual winner — the
        # "call sparingly" quota decision from aviation.py's docstring.
        if mode == "flight" and origin_city.get("iata_code") and destination_city.get("iata_code"):
            flight = aviation.get_sample_flight(origin_city["iata_code"], destination_city["iata_code"])
            if flight:
                dispatcher.utter_message(
                    text=(
                        f"A real example on this route: {flight['airline_name']} "
                        f"{flight['flight_number']}, {flight['departure_airport']} -> "
                        f"{flight['arrival_airport']} ({flight['flight_status']})"
                    )
                )

        # --- Hotels (up to 3, ranked) ---
        hotels = repository.get_hotels_for_destination(destination_city["id"])
        ranked_hotels = _score_hotels_ranked(hotels, sustainability_pref)
        if ranked_hotels:
            lines = [f"Eco-friendly stays in {destination_city['name']}:"]
            for i, h in enumerate(ranked_hotels, start=1):
                cert = h.get("eco_certification") or "no formal certification"
                tag = " [BEST MATCH]" if i == 1 else ""
                lines.append(
                    f"{i}. {h['name']} — {cert} — ~€{h['nightly_price_estimate']}/night{tag}"
                )
            dispatcher.utter_message(text="\n".join(lines))
        else:
            dispatcher.utter_message(
                text=f"I don't have curated hotel data for {destination_city['name']} yet — "
                     f"a human advisor can help find eco-certified options there."
            )

        # --- Experiences (up to 2, ranked by community impact) ---
        experiences = repository.get_experiences_for_destination(destination_city["id"])
        ranked_experiences = sorted(
            experiences, key=lambda e: float(e.get("local_community_score") or 0), reverse=True
        )[:2]
        if ranked_experiences:
            lines = [f"Low-impact experiences in {destination_city['name']}:"]
            for e in ranked_experiences:
                lines.append(f"- {e['name']} (~€{e['estimated_price']})")
            dispatcher.utter_message(text="\n".join(lines))

        # --- Offset the rest (always shown, not just on red-carbon routes) ---
        offsets = repository.get_offset_options()
        if offsets:
            lines = ["Offset the rest:"]
            for o in offsets[:2]:
                lines.append(
                    f"- {o['provider_name']} ({o['project_type']}) — approx. €{o['estimated_cost_per_tonne']}/tonne"
                )
            dispatcher.utter_message(text="\n".join(lines))

        repository.save_trip_session(
            sender_id=tracker.sender_id,
            origin_city_id=origin_city["id"],
            destination_city_id=destination_city["id"],
            travel_date=tracker.get_slot("travel_date"),
            trip_duration_days=duration,
            num_travellers=num_travellers,
            budget_tier=tracker.get_slot("budget"),
            sustainability_pref=sustainability_pref,
            estimated_co2_kg=co2_kg,
            carbon_level=carbon_level,
            data_source=tracker.get_slot("data_source"),
        )

        return []


# --------------------------------------------------------------------------
# Typo clarification standalone action (FR-03) — see module docstring,
# point 5, for why this now does nothing: the real flow happens inline
# inside extract_origin/extract_destination.
# --------------------------------------------------------------------------

class ActionClarifyDestination(Action):
    """Kept registered for symmetry with domain.yml/stories.yml. The typo
    confirmation flow itself now lives entirely inside extract_origin/
    extract_destination — see module docstring, point 5."""

    def name(self) -> Text:
        return "action_clarify_destination"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        return []


# --------------------------------------------------------------------------
# Navigation: go back / edit / reset (FR-11, FR-12)
# --------------------------------------------------------------------------

class ActionGoBack(Action):
    def name(self) -> Text:
        return "action_go_back"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        current = tracker.get_slot("requested_slot")
        if current not in REQUIRED_SLOTS_ORDER:
            dispatcher.utter_message(text="There's nothing to go back to just yet.")
            return []

        index = REQUIRED_SLOTS_ORDER.index(current)
        if index == 0:
            dispatcher.utter_message(text="We're already on the first question.")
            return []

        previous_slot = REQUIRED_SLOTS_ORDER[index - 1]
        return [SlotSet(previous_slot, None)]


class ActionEditAnswer(Action):
    def name(self) -> Text:
        return "action_edit_answer"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        entities = tracker.latest_message.get("entities", [])
        field_value = next((e["value"] for e in entities if e["entity"] == "field_to_edit"), None)

        target_slot = FIELD_TO_SLOT.get((field_value or "").lower())
        if not target_slot:
            dispatcher.utter_message(
                text="Which would you like to change: origin, destination, travel date, "
                     "number of travellers, budget, or sustainability preference?"
            )
            return []

        return [SlotSet(target_slot, None), ActiveLoop("trip_planning_form")]


class ActionResetTrip(Action):
    def name(self) -> Text:
        return "action_reset_trip"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        slots_to_clear = REQUIRED_SLOTS_ORDER + [
            "estimated_co2", "carbon_level", "data_source",
            "recommended_mode", "recommended_distance_km", "recommended_price_eur",
            "transport_options_json",
        ]
        return [SlotSet(s, None) for s in slots_to_clear] + [ActiveLoop(None)]


# --------------------------------------------------------------------------
# Human handover (FR-08, FR-09)
# --------------------------------------------------------------------------

class ActionHandover(Action):
    def name(self) -> Text:
        return "action_handover"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        context = {
            "origin": tracker.get_slot("origin"),
            "destination": tracker.get_slot("destination"),
            "travel_date": tracker.get_slot("travel_date"),
            "num_travellers": tracker.get_slot("num_travellers"),
            "budget": tracker.get_slot("budget"),
            "sustainability_pref": tracker.get_slot("sustainability_pref"),
            "estimated_co2": tracker.get_slot("estimated_co2"),
            "carbon_level": tracker.get_slot("carbon_level"),
        }

        # Heuristic: a recent scoped-fallback execution in this conversation
        # suggests an escalation rather than a deliberate ask. Not a fully
        # reliable signal, but a reasonable one — see module docstring.
        recent_actions = [
            e.get("name") for e in tracker.events[-10:]
            if e.get("event") == "action" and e.get("name")
        ]
        reason = "fallback_escalation" if "action_scoped_fallback" in recent_actions else "user_requested"

        repository.save_handover_log(
            trip_session_id=None,  # not linked to a specific trip_session row — see repository.py's docstring
            reason=reason,
            context_json=context,
        )

        dispatcher.utter_message(
            text="I've passed your details to a human travel advisor — they'll be in touch shortly.",
        )

        return [ActiveLoop(None)]


# --------------------------------------------------------------------------
# Fallback (FR-10) — see module docstring, point 3
# --------------------------------------------------------------------------

class ActionScopedFallback(Action):
    """Context-aware fallback (FR-10): inside the form, re-asks the SAME
    question the user just failed to answer by dispatching that slot's own
    utter_ask_<slot> response directly.

    CRITICAL: explicitly returns FollowupAction("action_listen") to force
    the turn to end immediately after speaking. Without this, a real
    infinite-loop bug was found during live testing: when this action
    returns no events at all, the tracker state is completely unchanged
    from the moment before it ran, so Core re-predicts the next action
    from that identical state, gets the identical low-confidence result
    from RulePolicy's core_fallback_threshold safety net, and fires this
    same action again — repeating until Rasa's circuit breaker (a fixed
    action-count cap, not a graceful stop) forcibly cuts the turn off
    mid-loop, producing many duplicate messages in one response. Forcing
    action_listen guarantees the loop cannot continue past one iteration,
    regardless of how policy confidence behaves on this tracker state."""

    def name(self) -> Text:
        return "action_scoped_fallback"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        if tracker.active_loop.get("name") == "trip_planning_form":
            requested_slot = tracker.get_slot("requested_slot")
            utter_name = f"utter_ask_{requested_slot}"
            if requested_slot and utter_name in domain.get("responses", {}):
                dispatcher.utter_message(response=utter_name)
            else:
                dispatcher.utter_message(response="utter_ask_rephrase")
        else:
            dispatcher.utter_message(response="utter_ask_rephrase")

        return [FollowupAction("action_listen")]