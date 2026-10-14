"""Offline regressions for declared daily bounds and sparse-route projection."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from backend import ors, smart_planner_v3 as v3
from backend import trekbrain_pipeline_core_v9 as pipeline
from backend import trekbrain_roundtrip_v9 as roundtrip
from backend import trekbrain_route_logistics_v9 as logistics
from backend.free_planner_v2 import AIPlanRequest
from backend.trekbrain_distance_contract_v9 import annotate_daily_distance
from backend.trekbrain_distance_tolerance_v9 import explicit_daily_bounds, install_distance_tolerance

install_distance_tolerance(v3)


class DeclaredBoundsTests(unittest.TestCase):
    def parse(self, prompt):
        return v3._parse_intent(AIPlanRequest(
            prompt=prompt, region="Zone", days=2, daily_km=19,
            difficulty="medium", route_type="Boucle", require_water=False,
            require_accommodation=False, require_food=False, require_transit=False,
        ))

    def test_range_syntax_and_decimal_bounds_survive_parsing(self):
        for text, expected in (("entre 18 et 20 km par jour", (18., 20.)),
                               ("18 à 20 km/jour", (18., 20.)),
                               ("20-18 km par jour", (18., 20.)),
                               ("entre 18,5 et 20,5 km par jour", (18.5, 20.5))):
            self.assertEqual(explicit_daily_bounds(text), expected)
            intent = self.parse(text)
            self.assertEqual((intent["explicit_daily_min"], intent["explicit_daily_max"]), expected)
            self.assertEqual(intent["distance_tolerance"], "explicit")
            self.assertEqual((intent["daily_min"], intent["daily_max"]), expected)

    def test_only_declared_side_is_enforced_and_short_max_only_days_are_valid(self):
        intent = self.parse("Maximum 20 km par jour")
        self.assertIsNone(intent["explicit_daily_min"])
        plan = {"stages": [{"distance_km": 4.}, {"distance_km": 18.}], "advisor_notes": []}
        self.assertIs(pipeline._enforce_explicit_distance_limit(plan, intent), plan)
        annotate_daily_distance(plan, intent)
        self.assertTrue(plan["planner"]["distance_contract"]["bounds_satisfied"])
        minimum = self.parse("Au moins 18 km par jour")
        self.assertIsNone(minimum["explicit_daily_max"])
        self.assertEqual(pipeline._enforce_explicit_distance_limit(
            {"stages": [{"distance_km": 25.}, {"distance_km": 25.}]}, minimum
        ).get("stages")[0]["distance_km"], 25.)
        larger = {"stages": [{"distance_km": 25.}, {"distance_km": 25.}]}
        annotate_daily_distance(larger, minimum)
        self.assertTrue(larger["planner"]["distance_contract"]["bounds_satisfied"])

    def test_range_and_minimum_violations_are_rejected_without_relabeling(self):
        for text in ("entre 18 et 20 km par jour", "Minimum 18 km par jour"):
            intent = self.parse(text)
            plan = {"stages": [{"distance_km": 16.}, {"distance_km": 19.}],
                    "route_preview": {"coords": [[45., 1.], [45., 1.3]]}, "advisor_notes": []}
            before = deepcopy(plan["route_preview"])
            with self.assertRaises(HTTPException) as raised:
                pipeline._enforce_explicit_distance_limit(plan, intent)
            self.assertEqual(raised.exception.status_code, 422)
            self.assertIn("minimum explicite", raised.exception.detail)
            annotate_daily_distance(plan, intent)
            contract = plan["planner"]["distance_contract"]
            self.assertEqual(contract["status"], "limit_exceeded")
            self.assertFalse(contract["bounds_satisfied"])
            self.assertEqual([d["day"] for d in contract["days_below_minimum"]], [1])
            self.assertTrue(contract["adjustment_required"])
            self.assertEqual([s["distance_km"] for s in plan["stages"]], [16., 19.])
            self.assertEqual(plan["route_preview"], before)

    def test_precision_search_cannot_relax_a_declared_minimum_by_ten_percent(self):
        start = {"lat": 45., "lon": 1.}
        coords = [[45., 1.], [45.1, 1.1], [45.1, .9], [45., 1.]]
        route = lambda km: {"distance": km, "coords": deepcopy(coords), "fallback": False}
        intent = {**self.parse("entre 18 et 20 km par jour"), "total_target": 38., "raw": "entre 18 et 20 km par jour"}
        with patch.object(ors, "ORS_API_KEY", "offline"), \
                patch.object(roundtrip, "_roundtrip_request", return_value=(route(35.5), None)), \
                patch.object(roundtrip, "_polygon_loop_candidates", return_value=[]):
            chosen = roundtrip._optimize_target_roundtrip(
                route(48.), start, 38., 18., 20., 2,
                SimpleNamespace(_route_retrace_ratio=lambda coords: .05), intent,
            )
        self.assertEqual(chosen["distance"], 48.)
        self.assertFalse(chosen["distance_search"]["candidates"][1]["within_window"])

    def test_roundtrip_builder_rejects_below_minimum_real_measurement(self):
        intent = self.parse("Minimum 18 km par jour")
        route = {"distance": 32., "coords": [[45., 1.], [45.1, 1.1], [45.1, .9], [45., 1.]], "fallback": False}
        stub = SimpleNamespace(_parse_intent=lambda data: intent, _fold=lambda s: s.casefold(),
                               _location=lambda data: "Zone")
        data = SimpleNamespace(days=2, daily_km=19.)
        with patch.object(roundtrip, "_optimize_target_roundtrip", side_effect=lambda route, *args: route):
            with self.assertRaises(HTTPException) as raised:
                roundtrip._build_roundtrip(data, object(), stub, route_candidate=route,
                                          route_start={"lat": 45., "lon": 1.})
        self.assertIn("minimum explicite", raised.exception.detail)

    def test_a_driving_variant_cannot_win_the_pedestrian_distance_search(self):
        start = {"lat": 45., "lon": 1.}
        coords = [[45., 1.], [45.1, 1.1], [45.1, .9], [45., 1.]]
        route = {"distance": 48., "coords": coords, "fallback": False, "profile": "foot-hiking"}
        driving = {**route, "distance": 38., "profile": "driving-car"}
        intent = {**self.parse("entre 18 et 20 km par jour"), "total_target": 38.}
        with patch.object(ors, "ORS_API_KEY", "offline"), \
                patch.object(roundtrip, "_roundtrip_request", return_value=(driving, None)), \
                patch.object(roundtrip, "_polygon_loop_candidates", return_value=[]):
            chosen = roundtrip._optimize_target_roundtrip(
                route, start, 38., 18., 20., 2,
                SimpleNamespace(_route_retrace_ratio=lambda coords: .05), intent,
            )
        self.assertEqual(chosen["distance"], 48.)
        self.assertEqual(chosen["profile"], "foot-hiking")

    def test_middle_segment_stay_keeps_true_progress_and_offroute_distance(self):
        coords = [[45., 1.], [45., 1.3]]
        before = deepcopy(coords)
        stay = {"lat": 45.001, "lon": 1.15, "name": "Refuge réel",
                "source_url": "https://www.openstreetmap.org/node/12"}
        cumulative = roundtrip._cumulative(coords)
        projection = roundtrip._project_stay_to_route(coords, cumulative, stay)
        self.assertAlmostEqual(projection[1], cumulative[-1] / 2, places=5)
        self.assertAlmostEqual(projection[2], .111195, places=5)
        projected = logistics._project_stays(roundtrip, coords, [stay], "refuge", 6.)
        self.assertEqual(len(projected), 1)
        self.assertAlmostEqual(projected[0]["_route_progress_km"], cumulative[-1] / 2, places=5)
        self.assertEqual(coords, before)

    def test_minimum_only_request_keeps_verified_access_on_a_longer_day(self):
        coords = [[45., 1.], [45., 1.6359]]
        original = {"route_preview": {"coords": coords, "distance_km": 50., "fallback": False},
                    "stages": [{"day": 1, "distance_km": 25.}, {"day": 2, "distance_km": 25.}],
                    "planner": {}, "advisor_notes": []}
        anchor = logistics._night_anchors(roundtrip, coords, 2, original["stages"])[0]
        stay = {"name": "Refuge sourcé", "lat": anchor["lat"] + .001, "lon": anchor["lon"],
                "source_url": "https://www.openstreetmap.org/node/25",
                "category": "refuge", "osm_tags": {"tourism": "alpine_hut"}}
        projected = logistics._project_stays(roundtrip, coords, [stay], "refuge", 6.)
        router = SimpleNamespace(get_distance_matrix=lambda points: {
            "distances": [[0., .2], [.2, 0.]], "fallback": False, "profile": "foot-hiking",
        })
        data = SimpleNamespace(days=2, daily_km=19., prompt="Au moins 18 km par jour")
        minimum = {**self.parse(data.prompt), "daily_max": 21.8}
        maximum = {**minimum, "explicit_daily_max": 21.8}
        approximate = {**minimum, "raw": "Environ 19 km par jour", "distance_tolerance": "soft-25pct",
                       "explicit_daily_min": None, "explicit_daily_max": None}
        for intent, expected in ((minimum, "walk"), (maximum, "transfer"), (approximate, "transfer")):
            result = deepcopy(original)
            with patch.object(logistics, "_discover_stays", return_value=([], projected, {
                "terrain_rows": [], "terrain_preloaded": False,
            })):
                logistics._attach_logistics(result, data, SimpleNamespace(distance_gps=roundtrip._polyline_haversine),
                                            object(), roundtrip, object(), router, intent, "refuge")
            night = result["logistics"]["nights"][0]
            self.assertEqual(night["access_mode"], expected)
            self.assertEqual(result["route_preview"], original["route_preview"])
            self.assertEqual([s["distance_km"] for s in result["stages"]], [25., 25.])
            if expected == "walk":
                self.assertTrue(night["walking_connector"]["return_validated"])
                self.assertEqual([s["estimated_walking_km_with_access"] for s in result["stages"]], [25.2, 25.2])


if __name__ == "__main__":
    unittest.main()
