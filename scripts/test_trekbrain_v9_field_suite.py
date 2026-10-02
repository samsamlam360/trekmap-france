"""TrekBrain v9 field suite: 40 realistic request-understanding scenarios.

The suite runs without live providers so it is safe as a mandatory CI gate. It
checks the exact production reconciliation + intent stack against contradictory
form values, natural-language distances, route shapes, resources and logistics.
"""
from __future__ import annotations

import os
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("TREKBRAIN_VERSION", "v9")
os.environ.setdefault("TREKBRAIN_FREE_MODE", "1")
os.environ.setdefault("ORS_API_KEY", "ci-placeholder")

from backend import smart_planner_v7 as v7  # noqa: E402
from backend import trekbrain_request_v9 as request_v9  # noqa: E402
from backend.language_engine import normalize_for_planner  # noqa: E402
from backend.trekbrain_pipeline_core_v9 import _rebalance_stage_count  # noqa: E402
from backend import trekbrain_roundtrip_v9 as roundtrip_v9  # noqa: E402
from backend.free_planner_v2 import AIPlanRequest  # noqa: E402
from backend.trekbrain_field_contract_v9 import FIELD_SCENARIOS, FIELD_SCENARIO_COUNT  # noqa: E402


PLACES = {
    "belle ile": {"name": "Belle-Île-en-Mer", "short_name": "Belle-Île-en-Mer", "lat": 47.3331, "lon": -3.1870},
    "mont saint michel": {"name": "Mont Saint-Michel", "short_name": "Mont Saint-Michel", "lat": 48.6361, "lon": -1.5115},
    "mont st michel": {"name": "Mont Saint-Michel", "short_name": "Mont Saint-Michel", "lat": 48.6361, "lon": -1.5115},
    "chartres": {"name": "Chartres", "short_name": "Chartres", "lat": 48.4469, "lon": 1.4890},
    "tours": {"name": "Tours", "short_name": "Tours", "lat": 47.3941, "lon": 0.6848},
    "chinon": {"name": "Chinon", "short_name": "Chinon", "lat": 47.1670, "lon": 0.2428},
    "paris": {"name": "Paris", "short_name": "Paris", "lat": 48.8566, "lon": 2.3522},
    "bretagne": {"name": "Bretagne", "short_name": "Bretagne", "lat": 48.20, "lon": -2.93},
    "vercors": {"name": "Vercors", "short_name": "Vercors", "lat": 44.97, "lon": 5.55},
    "touraine": {"name": "Touraine", "short_name": "Touraine", "lat": 47.28, "lon": 0.47},
}


def fake_geocode(query):
    text = request_v9._fold(query).replace("-", " ").replace("’", " ").replace("'", " ")
    for key, row in PLACES.items():
        if key in text:
            return [dict(row)]
    return []


def close_enough(actual, expected):
    if isinstance(expected, float):
        try:
            return abs(float(actual) - expected) <= 0.11
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str):
        return request_v9._fold(str(actual or "")) == request_v9._fold(expected)
    return actual == expected


real_geocode = request_v9.geo._geocode
request_v9.geo._geocode = fake_geocode
failures = []
try:
    for case in FIELD_SCENARIOS:
        base = {
            "prompt": case["prompt"],
            "region": "Chartres",
            "days": 3,
            "daily_km": 18,
            "difficulty": "medium",
            "route_type": "Boucle",
            "require_transit": True,
            "require_water": True,
            "require_accommodation": True,
            "require_food": True,
        }
        base.update(case.get("base") or {})
        data = AIPlanRequest(**base)
        resolved, meta = request_v9.reconcile_request(data)
        intent = v7.v5.v3._parse_intent(resolved)

        for key, expected in (case.get("resolved") or {}).items():
            actual = getattr(resolved, key)
            if not close_enough(actual, expected):
                failures.append(f"{case['id']}: resolved.{key}={actual!r}, expected {expected!r}")

        for key, expected in (case.get("meta") or {}).items():
            actual = meta.get(key)
            if not close_enough(actual, expected):
                failures.append(f"{case['id']}: meta.{key}={actual!r}, expected {expected!r}")

        for key, expected in (case.get("expect") or {}).items():
            actual = intent.get(key)
            if not close_enough(actual, expected):
                failures.append(f"{case['id']}: intent.{key}={actual!r}, expected {expected!r}")

        # The two production interpreters must agree on shape after reconciliation.
        if "route_type" in (case.get("resolved") or {}) or "route_type" in (case.get("expect") or {}):
            if request_v9._fold(resolved.route_type) != request_v9._fold(intent.get("route_type")):
                failures.append(
                    f"{case['id']}: reconciliation={resolved.route_type!r} but parser={intent.get('route_type')!r}"
                )
finally:
    request_v9.geo._geocode = real_geocode

if FIELD_SCENARIO_COUNT != 40:
    failures.append(f"field scenario count changed unexpectedly: {FIELD_SCENARIO_COUNT}")

# Language regression: a terrain constraint using the verb "traverser" is not
# a request for a route type "Traversée".
normalized, _ = normalize_for_planner(
    "Boucle autour du Mont-Saint-Michel. Je ne veux pas traverser la baie à pied."
)
if "traversee" in normalized:
    failures.append(f"language regression: traverser became route-shape noun: {normalized!r}")

# Stage-count regression: a validated two-stage geometry can safely be exposed
# as three requested hiking days without redrawing the route.
fake = {
    "start": {"name": "Tours", "lat": 47.39, "lon": 0.68},
    "end": {"name": "Chinon", "lat": 47.17, "lon": 0.24},
    "stages": [
        {"day": 1, "distance_km": 24.0},
        {"day": 2, "distance_km": 25.0},
    ],
    "route_preview": {
        "fallback": False,
        "distance_km": 49.0,
        "coords": [
            [47.39, 0.68], [47.34, 0.58], [47.29, 0.48],
            [47.24, 0.37], [47.17, 0.24],
        ],
    },
    "accommodations": [],
    "advisor_notes": [],
}
_rebalance_stage_count(fake, {"days": 3})
if len(fake.get("stages") or []) != 3 or fake.get("duration_days") != 3:
    failures.append(f"stage rebalance regression: {fake.get('stages')!r}")

# Oversized-loop regression. The shortening layer must only return geometry
# closed through a routed connector, never through a direct diagnostic segment.
old_get_route = roundtrip_v9.ors.get_route
try:
    def fake_connector(points, distance_fn):
        a, b = points
        return {
            "coords": [list(a), [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], list(b)],
            "distance": max(2.0, float(distance_fn(points)) * 1.15),
            "fallback": False,
            "routing_mode": "test-routed-connector",
            "profile": "foot-hiking",
        }

    roundtrip_v9.ors.get_route = fake_connector
    centre = {"lat": 48.0, "lon": 1.0}
    ring = []
    for n in range(73):
        angle = 2 * math.pi * n / 72
        ring.append([48.0 + 0.10 * math.sin(angle), 1.0 + 0.14 * math.cos(angle)])
    oversized = {"coords": ring, "distance": 58.0, "fallback": False, "profile": "foot-hiking"}
    variants = roundtrip_v9._shorten_oversized_loop(
        oversized, centre, 36.0, 12.0, 20.0, 2, v7.v5.v3
    )
    if not variants or not all(x.get("fallback") is False for x in variants):
        failures.append("round-trip shortening regression: no routed shortened loop")
    elif not any(21.6 <= float(x.get("distance") or 0) <= 40.35 for x in variants):
        failures.append(
            f"round-trip shortening regression: bad distances {[x.get('distance') for x in variants]}"
        )
finally:
    roundtrip_v9.ors.get_route = old_get_route

# Matrix-first internal-arc shortcut regression. The planner must evaluate many
# on-route pairs with one Matrix call and render only the selected connector.
old_get_route = roundtrip_v9.ors.get_route
old_get_matrix = roundtrip_v9.ors.get_distance_matrix
try:
    def fake_arc_matrix(points):
        n = len(points)
        distances = []
        for i in range(n):
            row = []
            for j in range(n):
                if i == j:
                    row.append(0.0)
                else:
                    # A usable network shortcut whose cost grows much more slowly
                    # than the removed arc.
                    row.append(2.0 + abs(j - i) * 1.25)
            distances.append(row)
        return {"distances": distances, "fallback": False, "routing_mode": "test-matrix"}

    def fake_arc_connector(points, distance_fn):
        a, b = points
        mid = [(a[0] + b[0]) / 2 + 0.002, (a[1] + b[1]) / 2]
        return {
            "coords": [list(a), mid, list(b)],
            "distance": max(2.0, float(distance_fn(points)) * 1.10),
            "fallback": False,
            "routing_mode": "test-arc-connector",
            "profile": "foot-hiking",
        }

    roundtrip_v9.ors.get_distance_matrix = fake_arc_matrix
    roundtrip_v9.ors.get_route = fake_arc_connector
    ring = []
    for n in range(145):
        angle = 2 * math.pi * n / 144
        ring.append([48.0 + 0.11 * math.sin(angle), 1.0 + 0.16 * math.cos(angle)])
    centre = {"lat": ring[0][0], "lon": ring[0][1]}
    oversized = {"coords": ring, "distance": 58.0, "fallback": False, "profile": "foot-hiking"}
    shortcuts = roundtrip_v9._shortcut_oversized_loop(
        oversized, centre, 36.0, 12.0, 20.0, 2, v7.v5.v3
    )
    if not shortcuts:
        failures.append("matrix arc-shortcut regression: no routed variant")
    elif not all(x.get("routing_mode") == "ors-matrix-arc-shortcut" for x in shortcuts):
        failures.append(f"matrix arc-shortcut regression: bad mode {shortcuts!r}")
    elif not all(x.get("matrix_shortcut") is True for x in shortcuts):
        failures.append("matrix arc-shortcut regression: Matrix metadata missing")
    elif not any(float(x.get("distance") or 0) < 58.0 for x in shortcuts):
        failures.append(f"matrix arc-shortcut regression: loop was not shortened {shortcuts!r}")
finally:
    roundtrip_v9.ors.get_route = old_get_route
    roundtrip_v9.ors.get_distance_matrix = old_get_matrix

# Routed waypoint-loop regression: when provider round-trip length is unreliable,
# the fallback must be able to create a closed candidate from routed waypoints.
old_get_route = roundtrip_v9.ors.get_route
try:
    def fake_waypoint_route(points, distance_fn):
        distance = float(distance_fn(points)) * 1.38
        return {
            "coords": [list(p) for p in points],
            "distance": distance,
            "fallback": False,
            "routing_mode": "test-waypoint-routing",
            "profile": "foot-hiking",
        }

    roundtrip_v9.ors.get_route = fake_waypoint_route
    polygon = roundtrip_v9._polygon_loop_candidates(
        {"lat": 48.0, "lon": 1.0}, 32.0, 12.0, 20.0, 2, v7.v5.v3
    )
    if not polygon:
        failures.append("waypoint-loop regression: no routed candidate")
    elif polygon[0].get("routing_mode") != "ors-waypoint-loop":
        failures.append(f"waypoint-loop regression: bad mode {polygon[0]!r}")
    elif roundtrip_v9._haversine(polygon[0]["coords"][0], polygon[0]["coords"][-1]) > 0.15:
        failures.append("waypoint-loop regression: route is not closed")
    elif "waypoint_retrace_ratio" not in polygon[0]:
        failures.append("waypoint-loop regression: missing retrace metadata")
finally:
    roundtrip_v9.ors.get_route = old_get_route

# Candidate-selection regression: once a genuinely routed shortened loop is
# available inside the distance window, a prettier but oversized ORS loop must
# never win the final ranking.
old_roundtrip_request = roundtrip_v9._roundtrip_request
old_shortener = roundtrip_v9._shorten_oversized_loop
try:
    def fake_roundtrip_request(start, requested_km, seed):
        return {
            "coords": [[48.0, 1.0], [48.1, 1.1], [48.0, 1.2], [48.0, 1.0]],
            "distance": 52.0,
            "fallback": False,
            "routing_mode": "test-oversized",
        }, None

    def fake_shortener(route, start, target_km, daily_min, daily_max, days, v3):
        return [{
            "coords": [[48.0, 1.0], [48.08, 1.08], [48.02, 1.16], [48.0, 1.0]],
            "distance": 34.0,
            "fallback": False,
            "routing_mode": "test-shortened",
        }]

    roundtrip_v9._roundtrip_request = fake_roundtrip_request
    roundtrip_v9._shorten_oversized_loop = fake_shortener
    selected = roundtrip_v9._best_roundtrip(
        {"lat": 48.0, "lon": 1.0}, 32.0, 12.0, 20.0, 2, v7.v5.v3
    )
    if selected.get("routing_mode") != "test-shortened" or float(selected.get("distance") or 0) != 34.0:
        failures.append(f"round-trip feasibility selection regression: {selected!r}")
finally:
    roundtrip_v9._roundtrip_request = old_roundtrip_request
    roundtrip_v9._shorten_oversized_loop = old_shortener

if failures:
    raise AssertionError("TrekBrain v9 field suite failed:\\n- " + "\\n- ".join(failures))

print(f"TrekBrain v9 field suite: {FIELD_SCENARIO_COUNT}/40 realistic request scenarios OK")
