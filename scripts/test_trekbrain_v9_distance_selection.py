"""Offline regression for measured distance selection and exact daily maxima.

Exercises the real selection/rendering helpers with deterministic router results.
No API keys, network, geocoding or database are required.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import HTTPException
from backend import ors
from backend import trekbrain_roundtrip_v9 as roundtrip
from backend import trekbrain_pipeline_core_v9 as pipeline
from backend import trekbrain_matrix_rescue_v9 as matrix_rescue
from backend.trekbrain_distance_contract_v9 import annotate_daily_distance


START = {"name": "Départ vérifié", "lat": 48.0, "lon": 1.0}
OLD_COORDS = [[48.0, 1.0], [48.08, 1.04], [48.07, 0.98], [48.0, 1.0]]
NEW_COORDS = [[48.0, 1.0], [48.05, 1.03], [48.06, 0.99], [48.0, 1.0]]


def route(km, coords=OLD_COORDS, **extra):
    return {
        "distance": km, "coords": deepcopy(coords), "fallback": False,
        "routing_mode": "ors-round-trip", "round_trip_requested_km": 32.0,
        **extra,
    }


INTENT = {
    "route_type": "Boucle", "days": 2, "daily_target": 16.0,
    "daily_min": 12.0, "daily_max": 20.0, "total_target": 32.0,
    "distance_tolerance": "soft-25pct", "raw": "boucle de deux jours",
    "accommodation": "balanced",
}
DATA = SimpleNamespace(days=2, daily_km=16.0, difficulty="medium", require_accommodation=False,
                       require_water=False, require_transit=False)


class V3:
    _route_retrace_ratio = staticmethod(lambda coords: 0.05)
    _parse_intent = staticmethod(lambda data: dict(INTENT))
    _fold = staticmethod(lambda value: str(value).casefold())
    _location = staticmethod(lambda data: "Zone vérifiée")


LEGACY = SimpleNamespace(elevation_gain=lambda coords: 0, distance_gps=roundtrip._polyline_haversine)


def optimize(initial, intent=INTENT, v3=V3):
    return roundtrip._optimize_target_roundtrip(
        initial, START, intent["total_target"], intent["daily_min"],
        intent["daily_max"], intent["days"], v3, intent,
    )


# A +27% loop that had already been ranked by the fast planner must still be
# compared against the requested goal. Retain the new geometry and its own km.
source = route(40.8, candidate_pool_size=2)
before = deepcopy(source)
with patch.object(ors, "ORS_API_KEY", "offline"), \
        patch.object(roundtrip, "_roundtrip_request", return_value=(route(32.2, NEW_COORDS), None)) as request, \
        patch.object(roundtrip, "_polygon_loop_candidates", side_effect=AssertionError("unnecessary extra call")):
    chosen = optimize(source)
    assert request.call_count == 1
    assert 24.9 < request.call_args.args[1] < 25.2, request.call_args
    assert chosen["distance"] == 32.2 and chosen["coords"] == NEW_COORDS
    assert chosen["distance_search"]["status"] == "closer_route_selected"
    assert chosen["distance_search"]["additional_routing_calls"] == 1
    assert source == before, "The original measured route was rewritten"

# A stubborn ORS length gets one additional Directions request. The regular
# snap/segment/provider chain must not exceed the precision search budget.
with patch.object(ors, "ORS_API_KEY", "offline"), \
        patch.object(roundtrip, "_roundtrip_request", return_value=(route(38.0), None)) as request, \
        patch.object(ors, "_request_route", return_value=(route(33.1, NEW_COORDS), None, 200)) as directions, \
        patch.object(ors, "get_route", side_effect=AssertionError("unbounded Directions recovery")):
    chosen = optimize(route(38.0))
    assert chosen["distance"] == 33.1, chosen
    assert request.call_count == directions.call_count == 1
    assert chosen["distance_search"]["additional_routing_calls"] == 2

# An invalid/open or non-pedestrian variant cannot win by reporting ideal km.
with patch.object(ors, "ORS_API_KEY", "offline"), \
        patch.object(roundtrip, "_roundtrip_request", return_value=(route(32.0, fallback=True), None)), \
        patch.object(ors, "_request_route", return_value=(route(32.0, [[48, 1], [48.02, 1], [48.04, 1], [49, 1]]), None, 200)):
    chosen = optimize(route(40.8))
    assert chosen["distance"] == 40.8 and chosen["coords"] == OLD_COORDS
    assert chosen["distance_search"]["status"] == "no_closer_route"

# These independently observed shapes also merit a search: Hohneck +18.75%,
# Camargue +24%. Moderate ordinary variation costs no additional network call.
for actual, target, needs_search in [(38.0, 32.0, True), (37.2, 30.0, True), (35.0, 32.0, False)]:
    intent = {**INTENT, "daily_target": target / 2, "total_target": target,
              "daily_min": target / 2 * 0.75, "daily_max": target / 2 * 1.25}
    with patch.object(ors, "ORS_API_KEY", "offline"), \
            patch.object(roundtrip, "_roundtrip_request", return_value=(route(target, NEW_COORDS), None)) as request:
        chosen = optimize(route(actual), intent)
        assert bool(request.call_count) == needs_search, (actual, target, request.call_count)

# GR evidence, pinned places, environmental constraints and good-enough routes
# retain their original geometry without starting another routing experiment.
for initial, intent in [
    (route(40.8, relation_geometry=True), INTENT),
    (route(40.8, relation_ref="GR 34"), INTENT),
    (route(40.8), {**INTENT, "raw": "suivre le GR34"}),
    (route(40.8), {**INTENT, "via_query": "Lac obligatoire"}),
    (route(40.8), {**INTENT, "avoid": {"route"}}),
    (route(32.2), INTENT),
]:
    with patch.object(roundtrip, "_roundtrip_request", side_effect=AssertionError("protected route rebuilt")):
        assert optimize(initial, intent) is initial

# No precision fallback can bypass API auth/quota or consume multiple timeout
# attempts. An absent configuration also retains a previously validated route.
for warning in ["HTTP 403", "HTTP 429", "délai interactif dépassé"]:
    with patch.object(ors, "ORS_API_KEY", "offline"), \
            patch.object(roundtrip, "_roundtrip_request", return_value=(None, warning)) as request, \
            patch.object(ors, "_request_route", side_effect=AssertionError("auth/quota/timeout bypass")):
        chosen = optimize(route(40.8))
        assert request.call_count == 1 and chosen["distance"] == 40.8
with patch.object(ors, "ORS_API_KEY", ""), \
        patch.object(roundtrip, "_roundtrip_request", side_effect=AssertionError("missing configuration")):
    chosen = optimize(route(40.8))
    assert chosen["distance_search"]["additional_routing_calls"] == 0
    assert chosen["distance_search"]["status"] == "routing_unavailable"

# An explicit maximum has no 0.35/0.75 km loophole, including in a builder
# outside the round-trip engine. Approximate targets retain their own tolerance.
explicit = {**INTENT, "daily_max": 16.0, "distance_tolerance": "explicit",
            "explicit_daily_min": None, "explicit_daily_max": 16.0}
with patch.object(ors, "ORS_API_KEY", "offline"), \
        patch.object(roundtrip, "_roundtrip_request", return_value=(route(32.2, NEW_COORDS), None)), \
        patch.object(ors, "_request_route", return_value=(route(31.8, NEW_COORDS), None, 200)):
    assert optimize(route(32.4), explicit)["distance"] == 31.8
try:
    pipeline._enforce_explicit_distance_limit({"stages": [{"distance_km": 16.1}]}, explicit)
except HTTPException as exc:
    assert exc.status_code == 422 and "maximum explicite" in exc.detail
else:
    raise AssertionError("Explicit maximum was relaxed")

# Rendering the selected alternative remeasures its stages, uses the existing
# departure and completes the comparison before the logistics phase.
result = {
    "start": dict(START), "route_preview": route(40.8),
    "stages": [{"day": 1, "distance_km": 20.4}, {"day": 2, "distance_km": 20.4}],
    "planner": {},
}
state = pipeline.PlanningState(DATA, DATA, dict(INTENT), None)
with patch.object(ors, "ORS_API_KEY", "offline"), \
        patch.object(roundtrip, "_roundtrip_request", return_value=(route(32.2, NEW_COORDS), None)), \
        patch.object(V3, "_geocode", side_effect=AssertionError("departure geocoded again"), create=True):
    selected = pipeline._improve_backbone_distance(result, state, LEGACY, v3=V3, roundtrip=roundtrip)
    assert selected["route_preview"]["coords"] == NEW_COORDS
    assert [s["distance_km"] for s in selected["stages"]] == [16.1, 16.1]
    assert selected["duration_days"] == 2
    assert selected["start"]["lat"] == START["lat"]
    assert selected["planner"]["distance_selection"]["selected_before_logistics"] is True
    assert "route:distance-alternative" in state.phases

# Exact progress markers are placed on the routed segments even with sparse
# geometry. They do not truncate, stretch or modify the route itself.
coords = [[48.0, 1.0], [48.0, 1.04], [48.0, 1.3], [48.0, 1.0]]
snapshot = deepcopy(coords)
anchor = roundtrip._equal_anchors(coords, 2)[0]
assert 1.04 < anchor["lon"] <= 1.3, anchor
assert abs(anchor["route_progress_km"] - roundtrip._cumulative(coords)[-1] / 2) < 1e-5
assert coords == snapshot

# A failed real-night boundary measurement cannot be replaced by total/days.
try:
    roundtrip._roundtrip_stage_distances(
        OLD_COORDS, [START, START, START], [START], 2, 32.0,
        LEGACY, SimpleNamespace(_stage_distances=lambda *args: [32.0]),
    )
except HTTPException as exc:
    assert exc.status_code == 422
else:
    raise AssertionError("Unknown nightly legs were fabricated as equal days")

# Unresolved excess receives actionable request edits based on the actual
# total. These are proposals that must revalidate stages and nights, not an
# automatic relabelling of the same route as a shorter hike.
excess = {"stages": [{"distance_km": 20.4}, {"distance_km": 20.4}],
          "route_preview": route(40.8), "planner": {}, "advisor_notes": []}
annotate_daily_distance(excess, INTENT)
contract = excess["planner"]["distance_contract"]
assert contract["adjustment_required"] is True
duration = contract["suggestions"][0]
assert duration["changes"] == {"days": 3}
assert duration["average_km_if_rebalanced"] == 13.6
assert duration["requires_replan_and_validation"] is True
assert [s["distance_km"] for s in excess["stages"]] == [20.4, 20.4]
explicit_result = {"stages": [{"distance_km": 16.1}, {"distance_km": 16.0}], "planner": {}}
annotate_daily_distance(explicit_result, explicit)
assert explicit_result["planner"]["distance_contract"]["status"] == "limit_exceeded"
assert len(explicit_result["planner"]["distance_contract"]["suggestions"]) == 1

# Matrix rescue also ranks final hiking days rather than selecting the first
# merely feasible camping cycle. Its historical three-Directions budget stays.
matrix_intent = {**INTENT, "daily_max": 21.0, "accommodation": "camping"}
camp_a = {"name": "Camping A", "lat": 48.04, "lon": 1.02}
camp_b = {"name": "Camping B", "lat": 48.06, "lon": 0.98}
camp = SimpleNamespace(
    _start_for=lambda *args: dict(START),
    _diverse_stays=lambda *args: [camp_a, camp_b],
    _render_result=lambda data, legacy, v3, provider, intent, location, start, routed, stays, distances: {
        "route_preview": dict(routed), "stages": [{"distance_km": d} for d in distances],
        "accommodations": stays, "advisor_notes": [], "confidence": {"limitations": []},
    },
)
matrix_v3 = SimpleNamespace(
    _parse_intent=lambda data: dict(matrix_intent), _location=lambda data: "Zone",
    _fold=lambda text: text.casefold(),
    _stage_distances=lambda coords, boundaries, legacy, total: [20.4, 20.4] if total == 40.8 else [16.1, 16.2],
)
provider = SimpleNamespace(get_route=lambda coords, distance: route(40.8 if coords[1][1] == camp_a["lon"] else 32.3))
with patch.object(matrix_rescue, "_geometry_solutions", return_value=[
    (0, [camp_a], [16, 16], 0.01), (1, [camp_b], [16, 16], 0.01),
]):
    matrix_result = matrix_rescue._recover_without_matrix(
        DATA, LEGACY, matrix_v3, roundtrip, provider, camp, "Matrix indisponible",
    )
assert matrix_result["accommodations"] == [camp_b], matrix_result
assert [s["distance_km"] for s in matrix_result["stages"]] == [16.1, 16.2]

print("Distance selection: bounded real-route alternatives, measured stages, protected GR, strict maxima and actionable edits PASS")
