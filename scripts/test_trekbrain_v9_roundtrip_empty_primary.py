"""Regression: loop planning must survive total ORS round-trip candidate failure."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_roundtrip_v9 as roundtrip


class FakeV3:
    @staticmethod
    def _route_retrace_ratio(_coords):
        return 0.05


start = {"name": "Test", "lat": 47.31, "lon": -3.20}
candidate = {
    "coords": [
        [47.31, -3.20],
        [47.34, -3.18],
        [47.32, -3.10],
        [47.29, -3.16],
        [47.31, -3.20],
    ],
    "distance": 82.0,
    "fallback": False,
    "routing_mode": "secondary-waypoint-loop",
    "secondary_router": True,
    "provider": "Valhalla/OpenStreetMap",
}

real_roundtrip_request = roundtrip._roundtrip_request
real_polygon = roundtrip._polygon_loop_candidates
calls = {"roundtrip": 0, "polygon": 0}
try:
    def no_primary(*_args, **_kwargs):
        calls["roundtrip"] += 1
        return None, "synthetic ORS round-trip outage"

    def secondary_polygon(*_args, **_kwargs):
        calls["polygon"] += 1
        return [dict(candidate)]

    roundtrip._roundtrip_request = no_primary
    roundtrip._polygon_loop_candidates = secondary_polygon

    result = roundtrip._best_roundtrip(
        start,
        target_km=90.0,
        daily_min=13.5,
        daily_max=22.5,
        days=5,
        v3=FakeV3(),
    )
finally:
    roundtrip._roundtrip_request = real_roundtrip_request
    roundtrip._polygon_loop_candidates = real_polygon

assert calls["roundtrip"] == 5, calls
assert calls["polygon"] == 1, calls
assert result["fallback"] is False
assert result["routing_mode"] == "secondary-waypoint-loop"
assert result["provider"] == "Valhalla/OpenStreetMap"
assert result["distance_window_preferred"] is True

print("Round-trip empty-primary recovery through validated waypoint router: OK")
