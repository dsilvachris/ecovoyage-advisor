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

3. action_clarify_destination: the typo-confirmation flow (FR-03) is
   implemented directly inside extract_destination/extract_origin, so it's
   deterministic rather than depending on the dialogue policy correctly
   predicting a separate action. action_clarify_destination is kept as a
   real, working standalone action for symmetry with domain.yml/stories.yml.

4. action_scoped_fallback: implemented as a single-behavior action, not a
   literal 3-strike counter — see class docstring below for why.
"""

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
            return {"status": "exact", "name": resolved["city_name"]}
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


def _dispatch_city_confirmation(dispatcher: CollectingDispatcher, guess: str) -> None:
    dispatcher.utter_message(
        text=f"Did you mean {guess}?",
        buttons=[
            {"title": "Yes", "payload": "/affirm"},
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


def _score_hotels(
    hotels: List[Dict[str, Any]], sustainability_pref: str
) -> Optional[Dict[str, Any]]:
    """Picks the best hotel per FR-06's weighting, using carbon_score as the
    carbon proxy and nightly_price_estimate as the price proxy. Returns None
    if no hotels are seeded for this destination yet (db/seed.sql's hotel
    coverage is currently sparse — expand during further Task 4 work)."""
    if not hotels:
        return None

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
    return scored[0][1]


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

        raw = tracker.latest_message.get("text", "")
        result = _resolve_city_input(raw)

        if result["status"] == "exact":
            return {"origin": result["name"]}
        if result["status"] == "fuzzy":
            _dispatch_city_confirmation(dispatcher, result["guess"])
            return {"destination_guess": result["guess"]}
        return {}

    async def extract_destination(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        if tracker.get_slot("requested_slot") != "destination":
            return {}

        # Confirmation follow-up from a prior fuzzy match (FR-03)
        pending_guess = tracker.get_slot("destination_guess")
        latest_intent = tracker.latest_message.get("intent", {}).get("name")
        if pending_guess and latest_intent == "affirm":
            return {"destination": pending_guess, "destination_guess": None}
        if pending_guess and latest_intent == "deny":
            dispatcher.utter_message(text="No problem — which destination did you mean?")
            return {"destination_guess": None}

        raw = tracker.latest_message.get("text", "")
        result = _resolve_city_input(raw)

        if result["status"] == "exact":
            if result["name"] == tracker.get_slot("origin"):
                dispatcher.utter_message(
                    text="That's the same as your origin — where would you like to go instead?"
                )
                return {}
            return {"destination": result["name"]}

        if result["status"] == "fuzzy":
            _dispatch_city_confirmation(dispatcher, result["guess"])
            return {"destination_guess": result["guess"]}

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

        return [
            SlotSet("estimated_co2", winner["co2e_total_kg"]),
            SlotSet("carbon_level", winner["carbon_level"]),
            SlotSet("data_source", winner["data_source"]),
            SlotSet("recommended_mode", winner["mode_name"]),
            SlotSet("recommended_distance_km", winner["distance_km"]),
            SlotSet("recommended_price_eur", winner["price_total_eur"]),
        ]


class ActionHighEmissionAlert(Action):
    """FR-07: only fires when the BEST available option is still red — not
    merely because some other, already-rejected option was red."""

    def name(self) -> Text:
        return "action_high_emission_alert"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        if tracker.get_slot("carbon_level") != "red":
            return []

        dispatcher.utter_message(
            text=(
                "Heads up — even the lowest-carbon option for this route is fairly "
                "carbon-intensive. You might consider offsetting the footprint."
            )
        )

        offsets = repository.get_offset_options()
        if offsets:
            lines = [
                f"- {o['provider_name']} ({o['project_type']}) — approx. €{o['estimated_cost_per_tonne']}/tonne"
                for o in offsets[:2]
            ]
            dispatcher.utter_message(text="\n".join(lines))

        return []


# --------------------------------------------------------------------------
# Recommendation (FR-04) — hotels, experience, transport summary, and the
# single point where aviation.py is called (only when flight is the winner)
# --------------------------------------------------------------------------

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

        mode = tracker.get_slot("recommended_mode")
        distance_km = tracker.get_slot("recommended_distance_km")
        price_eur = tracker.get_slot("recommended_price_eur")
        co2_kg = tracker.get_slot("estimated_co2")
        carbon_level = tracker.get_slot("carbon_level")
        num_travellers = tracker.get_slot("num_travellers") or 1
        sustainability_pref = tracker.get_slot("sustainability_pref") or "balanced"

        dispatcher.utter_message(
            text=(
                f"Recommended transport: {mode} ({distance_km} km, ~€{price_eur} total, "
                f"~{co2_kg} kg CO2e — {carbon_level})"
            )
        )

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

        hotels = repository.get_hotels_for_destination(destination_city["id"])
        best_hotel = _score_hotels(hotels, sustainability_pref)
        if best_hotel:
            cert = best_hotel.get("eco_certification") or "no formal certification"
            dispatcher.utter_message(
                text=(
                    f"Suggested stay: {best_hotel['name']} ({cert}), "
                    f"~€{best_hotel['nightly_price_estimate']}/night"
                )
            )
        else:
            dispatcher.utter_message(
                text=f"I don't have curated hotel data for {destination_city['name']} yet — "
                     f"a human advisor can help find eco-certified options there."
            )

        experiences = repository.get_experiences_for_destination(destination_city["id"])
        if experiences:
            top_experience = experiences[0]
            dispatcher.utter_message(
                text=f"Local experience: {top_experience['name']} (~€{top_experience['estimated_price']})"
            )

        repository.save_trip_session(
            sender_id=tracker.sender_id,
            origin_city_id=origin_city["id"],
            destination_city_id=destination_city["id"],
            travel_date=tracker.get_slot("travel_date"),
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
# point 3, for why the typo flow itself doesn't depend on this being called.
# --------------------------------------------------------------------------

class ActionClarifyDestination(Action):
    def name(self) -> Text:
        return "action_clarify_destination"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        guess = tracker.get_slot("destination_guess")
        if guess:
            _dispatch_city_confirmation(dispatcher, guess)
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
            "destination_guess",
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
# Fallback (FR-10) — see module docstring, point 4
# --------------------------------------------------------------------------

class ActionScopedFallback(Action):
    """Single-behavior fallback, not a literal 3-strike counter: inside the
    form, re-asks the SAME question the user just failed to answer
    (context-aware); outside the form, dispatches utter_ask_rephrase, which
    already offers both 'Plan a trip' and 'Talk to a human' — so a user is
    never more than one tap from reaching a human on any fallback."""

    def name(self) -> Text:
        return "action_scoped_fallback"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        if tracker.active_loop.get("name") == "trip_planning_form":
            return [FollowupAction("trip_planning_form")]

        dispatcher.utter_message(response="utter_ask_rephrase")
        return []