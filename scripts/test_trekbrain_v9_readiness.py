"""Evidence-based readiness, immutable routes and real HTTP body integration."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import Body, Depends, FastAPI, HTTPException
from backend.free_planner_v2 import AIPlanRequest
from backend.trekbrain_readiness_v9 import (
    preparation_report, annotate_preparation, install_preparation_overlay,
)


def reference(kind, day):
    return {
        "kind": kind, "route_day": day, "lat": 45.02, "lon": 5.02,
        "distance_to_route_km": 0.1,
        "source_url": f"https://www.openstreetmap.org/node/{day + (100 if kind == 'food' else 0)}",
        "status": "potable_referenced" if kind == "water" else "",
        "osm_tags": {"amenity": "drinking_water"} if kind == "water" else {"shop": "bakery"},
    }


def sample():
    return {
        "effective_request": {
            "days": 2, "daily_km": 16, "require_water": True,
            "require_food": True, "require_accommodation": True,
            "require_transit": False,
        },
        "route_preview": {
            "coords": [[45, 5], [45.12, 5.12], [45, 5]], "distance_km": 32,
            "fallback": False,
        },
        "route_type": "Boucle",
        "route_safety": {"safe": True},
        "start": {"lat": 45, "lon": 5}, "end": {"lat": 45, "lon": 5},
        "stages": [{"day": 1, "distance_km": 16}, {"day": 2, "distance_km": 16}],
        "trekbrain": {"quality": {"score": 95, "blockers": []}},
        "map_resources": {
            "points": [reference(kind, day) for day in (1, 2) for kind in ("water", "food")],
            "coverage": {"water": "verified", "food": "verified"},
        },
        "logistics": {"nights": [{
            "night": 1, "name": "Refuge sourcé", "lat": 45.02, "lon": 5.02,
            "source_url": "https://www.openstreetmap.org/node/999",
            "status": "confirmed", "access_mode": "walk",
            "walking_connector": {"validated": True, "return_validated": True,
                                  "distance_km": 0.2, "return_distance_km": 0.3},
        }]},
        "decision_summary": {"quality": 95, "important": []},
    }


class ReadinessTests(unittest.TestCase):
    def test_ready_keeps_score_geometry_and_all_evidence_immutable(self):
        plan = sample()
        before = deepcopy(plan)
        annotate_preparation(plan)
        first = deepcopy(plan["trip_readiness"])
        annotate_preparation(plan)
        self.assertEqual(plan["trip_readiness"], first)
        self.assertEqual(first["status"], "ready")
        self.assertTrue(all(req["status"] == "confirmed" for req in first["requirements"].values() if req["required"]))
        for key in ("route_preview", "stages", "logistics", "map_resources", "trekbrain"):
            self.assertEqual(plan[key], before[key])
        self.assertEqual(plan["decision_summary"]["quality"], 95)

    def test_daily_needs_cannot_be_replaced_by_reassuring_text_or_high_score(self):
        plan = sample()
        plan["map_resources"]["points"] = [reference("food", 1)]
        plan["map_resources"]["coverage"] = {"water": "verified", "food": "verified"}
        plan["stages"][1]["water_notes"] = "Tout est prévu"
        plan["stages"][0]["overnight"] = "Un très bon refuge"
        plan["logistics"]["nights"] = []
        report = preparation_report(plan)
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(report["route_validated"])
        self.assertEqual(report["requirements"]["water"]["missing_days"], [1, 2])
        self.assertEqual(report["requirements"]["food"]["missing_days"], [2])
        self.assertEqual(report["requirements"]["accommodation"]["missing_days"], [1])

    def test_nonpotable_private_or_forged_sources_never_confirm_water(self):
        for update in (
            {"status": "not_potable"},
            {"osm_tags": {"amenity": "drinking_water", "drinking_water": "no"}},
            {"osm_tags": {"amenity": "drinking_water", "access": "private"}},
            {"source_url": "https://www.openstreetmap.org.evil.example/node/1"},
            {"distance_to_route_km": 20},
            {"lat": float("nan")},
            {"route_day": True},
        ):
            with self.subTest(update=update):
                plan = sample()
                plan["map_resources"]["points"][0].update(update)
                self.assertEqual(preparation_report(plan)["requirements"]["water"]["missing_days"], [1])

    def test_evidence_beyond_display_cap_still_covers_late_days(self):
        plan = sample()
        plan["map_resources"]["evidence_points"] = deepcopy(plan["map_resources"]["points"])
        plan["map_resources"]["points"] = []
        self.assertEqual(preparation_report(plan)["status"], "ready")

    def test_walk_outward_alone_or_nonfinite_return_is_not_confirmed(self):
        for update in ({"return_validated": False}, {"return_distance_km": float("inf")}):
            plan = sample()
            plan["logistics"]["nights"][0]["walking_connector"].update(update)
            self.assertEqual(preparation_report(plan)["requirements"]["accommodation"]["missing_days"], [1])

    def test_transfer_is_incomplete_until_explicitly_confirmed(self):
        plan = sample()
        night = plan["logistics"]["nights"][0]
        night.update(status="usable_with_transfer", access_mode="transfer", transfer_confirmed=False)
        report = preparation_report(plan)
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(any(x["code"] == "transfer_unconfirmed" for x in report["issues"]))
        night["transfer_confirmed"] = True
        self.assertEqual(preparation_report(plan)["status"], "ready")

    def test_approximate_distance_and_access_effort_are_measured_independently(self):
        for value, field in ((20.4, "distance_km"), (19.5, "estimated_walking_km_with_access")):
            plan = sample()
            plan["stages"][0][field] = value
            # No optional distance_contract may hide the real excess.
            report = preparation_report(plan)
            self.assertEqual(report["status"], "incomplete")
            self.assertEqual(report["requirements"]["distance"]["missing_days"], [1])

    def test_only_declared_limits_are_hard_and_lower_bound_is_checked(self):
        plan = sample()
        maximum_only = AIPlanRequest(prompt="Une boucle, maximum 20 km par jour", days=2, daily_km=16)
        plan["stages"][0]["distance_km"] = 10
        self.assertEqual(preparation_report(plan, maximum_only)["requirements"]["distance"]["status"], "confirmed")
        interval = maximum_only.model_copy(update={"prompt": "Une boucle entre 18 et 20 km par jour"})
        self.assertEqual(preparation_report(plan, interval)["status"], "refused")
        minimum_only = maximum_only.model_copy(update={"prompt": "Au moins 18 km par jour"})
        self.assertEqual(preparation_report(plan, minimum_only)["status"], "refused")

    def test_missing_mandatory_objective_is_visible_even_without_audit_blocker(self):
        plan = sample()
        plan["side_requests"] = [{"kind": "lake", "required": True, "satisfied": False}]
        report = preparation_report(plan)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["requirements"]["objectives"]["status"], "missing")

    def test_effective_negative_request_overrides_old_form_defaults(self):
        plan = sample()
        plan["map_resources"]["points"] = []
        plan["logistics"]["nights"] = []
        plan["effective_request"].update(require_water=False, require_food=False, require_accommodation=False)
        stale = AIPlanRequest(prompt="Sans hébergement et pas besoin de points d'eau", days=2, daily_km=16)
        self.assertEqual(preparation_report(plan, stale)["status"], "ready")

    def test_invalid_geometry_distances_and_stage_lists_are_refused(self):
        mutations = [
            lambda p: p["route_preview"].update(fallback=True),
            lambda p: p["route_preview"].update(provisional=True),
            lambda p: p["route_preview"].update(coords=[[45, 5], [45, 5]]),
            lambda p: p["stages"].append("invalid stage"),
            lambda p: p["stages"][0].update(distance_km=float("nan")),
            lambda p: p["effective_request"].update(days=0),
        ]
        for mutate in mutations:
            plan = sample()
            mutate(plan)
            self.assertEqual(preparation_report(plan)["status"], "refused")


class EndpointTests(unittest.TestCase):
    def app(self, failure=False):
        app = FastAPI()
        legacy = SimpleNamespace(current_user=lambda: {"id": 42})
        @app.post("/ai/plan")
        def plan(data: AIPlanRequest = Body(...), user=Depends(legacy.current_user)):
            if failure:
                raise HTTPException(503, detail={
                    "message": "Fournisseur indisponible", "diagnostic": {"code": "TB-GEO-GEOCODE"},
                    "failed_preview": {"coords": [[45, 5], [46, 5]], "provisional": True},
                }, headers={"Retry-After": "20"})
            result = sample()
            result["effective_request"]["require_water"] = False
            result["map_resources"]["points"] = [x for x in result["map_resources"]["points"] if x["kind"] != "water"]
            return result
        install_preparation_overlay(app, legacy)
        return app

    def test_json_body_openapi_and_effective_metadata_survive_real_endpoint(self):
        app = self.app()
        schema = app.openapi()["paths"]["/ai/plan"]["post"]
        self.assertIn("requestBody", schema)
        self.assertNotIn("data", [x["name"] for x in schema.get("parameters", [])])
        self.assertEqual(sum(route.path == "/ai/plan" for route in app.routes), 1)
        body = AIPlanRequest.model_validate({"prompt": "Boucle de 2 jours", "days": 2, "daily_km": 16})
        endpoint = next(route.endpoint for route in app.routes if route.path == "/ai/plan")
        payload = endpoint(body, {"id": 42})
        self.assertEqual(payload["trip_readiness"]["status"], "ready")
        self.assertFalse(payload["trip_readiness"]["requirements"]["water"]["required"])

    def test_http_refusal_keeps_diagnostic_preview_header_and_never_approves(self):
        app = self.app(failure=True)
        endpoint = next(route.endpoint for route in app.routes if route.path == "/ai/plan")
        body = AIPlanRequest.model_validate({"prompt": "Boucle de 2 jours", "days": 2, "daily_km": 16})
        with self.assertRaises(HTTPException) as captured:
            endpoint(body, {"id": 42})
        self.assertEqual(captured.exception.status_code, 503)
        self.assertEqual(captured.exception.headers["Retry-After"], "20")
        detail = captured.exception.detail
        self.assertEqual(detail["diagnostic"]["code"], "TB-GEO-GEOCODE")
        self.assertTrue(detail["failed_preview"]["provisional"])
        self.assertEqual(detail["trip_readiness"]["status"], "refused")
        self.assertFalse(detail["trip_readiness"]["route_validated"])


if __name__ == "__main__":
    unittest.main()
