"""Offline regression: cold-region ORS round-trip failure uses bounded real-route failover.

No HTTP, database access or production credentials.
"""
from pathlib import Path
import sys
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import ors
from backend import smart_planner_v3 as v3
from backend import smart_planner_v5 as v5
from backend import smart_planner_v9 as v9
from backend import trekbrain_speed_v9 as speed
from backend import trekbrain_roundtrip_v9 as roundtrip

speed._INSTALLED = False
speed.install_fast_planning(v3, v5, v9)

start = {"lat": 48.0, "lon": -1.0}
points = [[48.0, -1.0], [48.07, -0.96], [48.08, -1.03], [48.0, -1.0]]
secondary = {
    "coords": points, "distance": 30.2, "fallback": False,
    "routing_mode": "secondary-waypoint-loop",
    "secondary_router": True, "provider": "Valhalla/OpenStreetMap",
}
original_request = roundtrip._roundtrip_request
original_polygons = roundtrip._polygon_loop_candidates
original_route = ors.get_route
try:
    calls = []
    def timeout(_start, _target, _seed):
        calls.append("roundtrip")
        return None, "OpenRouteService round-trip : délai interactif dépassé."
    def rescue(*args, **kwargs):
        assert kwargs == {"max_attempts": 2}, kwargs
        calls.append("polygon")
        return [dict(secondary)]
    roundtrip._roundtrip_request = timeout
    roundtrip._polygon_loop_candidates = rescue
    result = roundtrip._best_roundtrip(start, 30, 12, 18, 2, v3)
    assert calls == ["roundtrip", "polygon"], calls
    assert result["fallback"] is False and result["secondary_router"] is True, result
    assert result["routing_mode"] == "secondary-waypoint-loop", result
    assert result["fast_ranked"] and result["distance_window_preferred"], result

    # A valid but grossly oversized pedestrian loop is NOT fit for the trek.
    calls.clear()
    roundtrip._polygon_loop_candidates = lambda *a, **k: [dict(secondary, distance=75.0)]
    try:
        roundtrip._best_roundtrip(start, 30, 12, 18, 2, v3)
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("Dangerously oversized fallback accepted")

    # An absent/invalid API key and HTTP 429 must not turn into unbounded
    # third-party calls masquerading as error recovery.
    for warning in (
        "OpenRouteService non configuré : ORS_API_KEY est absente.",
        "OpenRouteService HTTP 429 : limite de requêtes.",
        "OpenRouteService HTTP 403 : accès interdit.",
    ):
        roundtrip._roundtrip_request = lambda *a: (None, warning)
        roundtrip._polygon_loop_candidates = lambda *a, **k: (
            (_ for _ in ()).throw(AssertionError("Bypassed auth/quota failure"))
        )
        try:
            roundtrip._best_roundtrip(start, 30, 12, 18, 2, v3)
        except HTTPException as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError("Auth/quota outage should fail closed")

    # Test actual polygon-loop geometry validation and external call budget.
    directions = []
    def valid_pedestrian_route(coords, _distance):
        directions.append(coords)
        return dict(secondary, coords=coords)
    ors.get_route = valid_pedestrian_route
    routes = original_polygons(start, 30, 12, 18, 2, v3, max_attempts=1)
    assert len(directions) == 1, directions
    assert routes and routes[0]["fallback"] is False, routes
    assert routes[0]["routing_mode"] == "secondary-waypoint-loop"

    directions.clear()
    ors.get_route = lambda coords, _distance: (
        directions.append(coords) or
        {"fallback": True, "warning": "route non vérifiée"}
    )
    assert original_polygons(start, 30, 12, 18, 2, v3, max_attempts=1) == []
    assert len(directions) == 1
finally:
    ors.get_route = original_route
    roundtrip._roundtrip_request = original_request
    roundtrip._polygon_loop_candidates = original_polygons
print("Cold-region route: bounded timeout failover, closed geometry, distance gate and auth/quota safeguards PASS")
