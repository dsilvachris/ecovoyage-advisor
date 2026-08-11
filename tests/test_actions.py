"""
tests/test_actions.py — unit tests with mocked external dependencies.

Complements docs/testing-log.md's live, non-mocked scenario testing: these
tests prove the LOGIC is correct in isolation (parsing, scoring, fallback
behavior), independent of whether NeonDB/Climatiq/OpenRouteService/OpenCage/
Aviationstack are actually reachable. Per the brief's Task 5 requirement,
each external-API-touching function has a success case, a failure/fallback
case, and at least one edge case.

Import note: actions/*.py use relative imports (e.g. geo.py's
`from .routing import haversine_km`) because rasa-sdk loads them as the
`actions` package. Importing them as bare top-level modules (e.g. a plain
`import geo`) breaks those relative imports with
"ImportError: attempted relative import with no known parent package" —
this file imports everything through the actions package instead
(`from actions import geo`), matching how rasa-sdk actually loads them.

Run with: pytest tests/ -v
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from actions import carbon
from actions import routing
from actions import geo


# --------------------------------------------------------------------------
# carbon.py — FR-05
# --------------------------------------------------------------------------

class TestCarbonEstimation:
    def test_estimate_co2e_uses_stored_fallback_when_no_api_key(self):
        """Success case for the FALLBACK path: no Climatiq key configured,
        should compute from the stored per-km rate directly."""
        with patch.object(carbon, "CLIMATIQ_API_KEY", None):
            result = carbon.estimate_co2e(
                mode_name="train", distance_km=100, num_travellers=2,
                fallback_kg_per_pax_km=0.041,
            )
        assert result["data_source"] == "stored"
        assert result["co2e_total_kg"] == 8.2  # 0.041 * 100 * 2
        assert result["carbon_level"] == "green"

    @patch("actions.carbon.requests.post")
    def test_estimate_co2e_uses_climatiq_on_success(self, mock_post):
        """Success case: Climatiq responds cleanly, its figure should win
        over the stored fallback."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"co2e": 19.0}
        mock_post.return_value = mock_response

        with patch.object(carbon, "CLIMATIQ_API_KEY", "fake-key-for-test"):
            result = carbon.estimate_co2e(
                mode_name="car", distance_km=100, num_travellers=1,
                fallback_kg_per_pax_km=0.171,  # deliberately different from Climatiq's 19.0
            )
        assert result["data_source"] == "climatiq"
        assert result["co2e_total_kg"] == 19.0

    @patch("actions.carbon.requests.post")
    def test_estimate_co2e_falls_back_on_climatiq_timeout(self, mock_post):
        """Failure case (NFR-04): Climatiq times out, must degrade to the
        stored rate rather than raising."""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        with patch.object(carbon, "CLIMATIQ_API_KEY", "fake-key-for-test"):
            result = carbon.estimate_co2e(
                mode_name="car", distance_km=100, num_travellers=1,
                fallback_kg_per_pax_km=0.171,
            )
        assert result["data_source"] == "stored"
        assert result["co2e_total_kg"] == 17.1

    def test_estimate_co2e_never_attempts_climatiq_for_flight(self):
        """Edge case: flight is a deliberate scope exclusion (see carbon.py
        module docstring) — must always use the stored rate, even with a
        configured API key."""
        with patch.object(carbon, "CLIMATIQ_API_KEY", "fake-key-for-test"):
            with patch.object(carbon, "requests") as mock_requests:
                result = carbon.estimate_co2e(
                    mode_name="flight", distance_km=1000, num_travellers=1,
                    fallback_kg_per_pax_km=0.246,
                )
                mock_requests.post.assert_not_called()
        assert result["data_source"] == "stored"

    def test_classify_carbon_level_boundaries(self):
        """Edge case: exact threshold boundaries (green/amber/red cutoffs)."""
        assert carbon.classify_carbon_level(50) == "green"
        assert carbon.classify_carbon_level(50.01) == "amber"
        assert carbon.classify_carbon_level(150) == "amber"
        assert carbon.classify_carbon_level(150.01) == "red"


# --------------------------------------------------------------------------
# routing.py — FR-04
# --------------------------------------------------------------------------

class TestRouting:
    def test_get_distance_km_uses_curated_when_available(self):
        """Success case: a curated distance exists, ORS shouldn't even be
        attempted for non-car modes."""
        result = routing.get_distance_km(
            "train", 48.8566, 2.3522, 52.3676, 4.9041,
            curated_distance_km=430.0,
        )
        assert result == {"distance_km": 430.0, "data_source": "stored"}

    @patch("actions.routing.requests.get")
    def test_get_distance_km_uses_ors_for_car_on_success(self, mock_get):
        """Success case: live OpenRouteService response for car mode."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "features": [{"properties": {"segments": [{"distance": 502850.7}]}}]
        }
        mock_get.return_value = mock_response

        with patch.object(routing, "OPENROUTESERVICE_API_KEY", "fake-key-for-test"):
            result = routing.get_distance_km(
                "car", 48.8566, 2.3522, 52.3676, 4.9041,
                curated_distance_km=None,
            )
        assert result["data_source"] == "openrouteservice"
        assert result["distance_km"] == 502.85

    @patch("actions.routing.requests.get")
    def test_get_distance_km_falls_back_to_estimate_on_ors_failure(self, mock_get):
        """Failure case (NFR-04): ORS errors out and no curated row exists
        — must fall back to the haversine+detour estimate, not crash."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        with patch.object(routing, "OPENROUTESERVICE_API_KEY", "fake-key-for-test"):
            result = routing.get_distance_km(
                "car", 48.8566, 2.3522, 52.3676, 4.9041,
                curated_distance_km=None,
            )
        assert result["data_source"] == "estimated"
        assert result["distance_km"] > 0

    def test_get_distance_km_train_never_calls_ors(self):
        """Edge case: ORS has no rail profile (see routing.py module
        docstring) — 'train' must never attempt a live call, regardless of
        whether a key is configured."""
        with patch.object(routing, "OPENROUTESERVICE_API_KEY", "fake-key-for-test"):
            with patch.object(routing, "requests") as mock_requests:
                routing.get_distance_km(
                    "train", 48.8566, 2.3522, 52.3676, 4.9041,
                    curated_distance_km=430.0,
                )
                mock_requests.get.assert_not_called()

    def test_haversine_km_known_distance(self):
        """Sanity check against a known real-world figure: Paris-Amsterdam
        great-circle distance is ~430km (verified against the live
        OpenRouteService driving distance of 502.85km during Phase 1
        testing — haversine is expected to read lower, since it's a
        straight line, not a road route)."""
        km = routing.haversine_km(48.8566, 2.3522, 52.3676, 4.9041)
        assert 425 < km < 435


# --------------------------------------------------------------------------
# geo.py — FR-02, FR-03
# --------------------------------------------------------------------------

class TestGeo:
    def test_nearest_supported_city_finds_closest(self):
        """Success case: GPS point nearest a known city resolves correctly."""
        supported = [
            {"name": "Paris", "latitude": 48.8566, "longitude": 2.3522},
            {"name": "London", "latitude": 51.5072, "longitude": -0.1276},
        ]
        result = geo.nearest_supported_city(48.85, 2.35, supported)
        assert result["city_name"] == "Paris"
        assert result["distance_km"] < 5

    @patch("actions.geo.requests.get")
    def test_resolve_gps_location_degrades_without_opencage_key(self, mock_get):
        """Failure/degradation case (NFR-04): no OpenCage key configured —
        nearest-city matching still works, friendly_label is just None."""
        supported = [{"name": "Paris", "latitude": 48.8566, "longitude": 2.3522}]
        with patch.object(geo, "OPENCAGE_API_KEY", None):
            result = geo.resolve_gps_location(48.85, 2.35, supported)
        mock_get.assert_not_called()
        assert result["city_name"] == "Paris"
        assert result["friendly_label"] is None

    def test_find_city_typo_match_confirms_close_match(self):
        """Success case: a genuine typo resolves to the right city."""
        result = geo.find_city_typo_match("Pariiis", ["Paris", "London", "Bangkok"])
        assert result == "Paris"

    def test_find_city_typo_match_rejects_unrelated_input(self):
        """Edge case (critical for FR-03): input with no genuine close
        match must return None, not a confident-looking wrong guess."""
        result = geo.find_city_typo_match("Xyzabc123", ["Paris", "London", "Bangkok"])
        assert result is None


# --------------------------------------------------------------------------
# actions.py helpers — FR-01 free-text parsing
# --------------------------------------------------------------------------

from actions.actions import _parse_traveller_count, _parse_budget_tier, _parse_sustainability_pref


class TestFreeTextParsing:
    def test_parse_traveller_count_digit(self):
        assert _parse_traveller_count("2") == 2

    def test_parse_traveller_count_phrase_word(self):
        """Regression test for the bug found in live testing (Scenario 4,
        docs/testing-log.md) — 'four' as a word, not a digit."""
        assert _parse_traveller_count("family of four") == 4

    def test_parse_traveller_count_just_me(self):
        assert _parse_traveller_count("just me") == 1

    def test_parse_traveller_count_unparseable_returns_none(self):
        """Edge case: genuinely unparseable input must return None so the
        form's validator can re-prompt, not silently default to a number."""
        assert _parse_traveller_count("sometime maybe idk") is None

    def test_parse_budget_tier_exact(self):
        assert _parse_budget_tier("mid") == "mid"

    def test_parse_budget_tier_synonym(self):
        assert _parse_budget_tier("keep it cheap") == "budget"

    def test_parse_sustainability_pref_exact(self):
        assert _parse_sustainability_pref("eco_certified") == "eco_certified"

    def test_parse_sustainability_pref_free_text(self):
        assert _parse_sustainability_pref("I care about the local community") == "local_culture"

    def test_parse_sustainability_pref_unparseable_returns_none(self):
        assert _parse_sustainability_pref("whatever you think") is None