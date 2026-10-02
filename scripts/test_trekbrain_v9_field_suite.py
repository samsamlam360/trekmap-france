"""TrekBrain v9 field suite: 40 realistic request-understanding scenarios.

The suite runs without live providers so it is safe as a mandatory CI gate. It
checks the exact production reconciliation + intent stack against contradictory
form values, natural-language distances, route shapes, resources and logistics.
"""
from __future__ import annotations

import os
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

if failures:
    raise AssertionError("TrekBrain v9 field suite failed:\\n- " + "\\n- ".join(failures))

print(f"TrekBrain v9 field suite: {FIELD_SCENARIO_COUNT}/40 realistic request scenarios OK")
