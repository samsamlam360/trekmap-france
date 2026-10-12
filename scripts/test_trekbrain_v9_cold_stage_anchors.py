"""Provider-free cold-region stage-anchor regression for TrekBrain v9.

Twenty synthetic route geometries across France (not twenty live hikes).
The tested map contains some high-density GPX segments and long low-density
segments. The response must still position each day's resource search near
the actual walked-distance boundary, without an ORS call or extra Photon slots.
"""
from __future__ import annotations

from copy import deepcopy
from math import isfinite
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import trekbrain_resources_v9 as resources
from backend import smart_planner_v3 as v3


def route_shape(index: int) -> dict:
    lat0 = 42.5 + index * 0.25
    lon0 = -4.3 + (index % 5) * 2.0
    dense = 360 + index * 17
    # First 0.005° is represented by hundreds of vertices, then the rest
    # (0.60°) by two vertices. Correct boundaries must NOT hug the first km.
    points = [[lat0 + 0.005 * k / dense, lon0] for k in range(dense + 1)]
    points += [[lat0 + 0.30, lon0], [lat0 + 0.605, lon0]]
    days = 2 + (index % 5)
    return {
        "duration_days": days,
        "route_preview": {"coords": points, "fallback": False},
        "start": {"name": "Départ", "lat": points[0][0], "lon": points[0][1]},
        "end": {"name": "Arrivée", "lat": points[-1][0], "lon": points[-1][1]},
        "stages": [{"day": d + 1, "distance_km": 12.0} for d in range(days)],
    }


errors = []
for i in range(20):
    plan = route_shape(i)
    before = deepcopy(plan)
    days = plan["duration_days"]
    boundaries = resources._route_day_boundaries(plan, days)
    assert len(boundaries) == days + 1, (i, len(boundaries), days)
    assert boundaries[0]["lat"] == plan["start"]["lat"]
    assert boundaries[-1]["lat"] == plan["end"]["lat"]
    for day, anchor in enumerate(boundaries[1:-1], 1):
        frac = (anchor["lat"] - boundaries[0]["lat"]) / (
            boundaries[-1]["lat"] - boundaries[0]["lat"]
        )
        expected = day / days
        assert abs(frac - expected) < 0.002, (i, day, frac, expected)
        assert isfinite(anchor["lat"]) and isfinite(anchor["lon"])
        assert anchor["category"] == "route_anchor"
        assert 42 <= anchor["lat"] <= 49
    assert plan == before, f"Original route was mutated in scenario {i}"

# Two vertices are sufficient to produce every day's resource-search anchor,
# rather than returning only departure and arrival.
sparse = {
    "duration_days": 4,
    "route_preview": {"coords": [[45.0, 5.0], [45.4, 5.0]], "fallback": False},
    "stages": [{"day": d + 1, "distance_km": 11.1} for d in range(4)],
}
bounds = resources._route_day_boundaries(sparse, 4)
assert len(bounds) == 5, bounds
assert [round(x["lat"], 2) for x in bounds] == [45.0, 45.1, 45.2, 45.3, 45.4], bounds

# An intentionally unbalanced trek must use the actual stage lengths:
# 5km + 15km + 20km = 40km, not 3 equal-length segments.
uneven = {
    "duration_days": 3,
    "route_preview": {"coords": [[44.0, 6.0], [44.4, 6.0]], "fallback": False},
    "stages": [
        {"day": 1, "distance_km": 5},
        {"day": 2, "distance_km": 15},
        {"day": 3, "distance_km": 20},
    ],
}
boundaries = resources._route_day_boundaries(uneven, 3)
assert abs(boundaries[1]["lat"] - 44.05) < 0.0002, boundaries
assert abs(boundaries[2]["lat"] - 44.2) < 0.0002, boundaries

# A real downstream Photon fallback receives the new anchors in the unchanged
# six-call budget; all category probes are mocked so this costs zero quota.
real_photon = v3._photon_anchor_resource
calls = []
def fake_photon(point, category, tags, radius):
    calls.append((float(point["lat"]), category))
    return {
        "name": "Test POI",
        "lat": point["lat"],
        "lon": point["lon"],
        "category": category,
        "source_url": f"https://www.openstreetmap.org/node/{700001 + len(calls)}",
    }

v3._photon_anchor_resource = fake_photon
try:
    anchors = resources._route_day_boundaries(sparse, 4)
    discovered = v3._postroute_corridor_resources(
        anchors,
        {
            "water": True, "food": True, "sleep": True,
            "transit": True, "accommodation": "camping",
        },
        [],
    )
finally:
    v3._photon_anchor_resource = real_photon

assert len(calls) <= 6 and len(discovered) <= 6, (calls, discovered)
assert sum(kind == "food" for _, kind in calls) >= 2, calls
assert sum(kind == "water" for _, kind in calls) >= 1, calls
assert sum(kind == "stay" for _, kind in calls) >= 1, calls
assert any(abs(lat - 45.1) < 0.001 for lat, kind in calls if kind in {"food", "stay"}), calls
assert all(45.0 <= lat <= 45.4 for lat, kind in calls), calls

# No invalid route may create fictitious day anchors.
assert resources._route_day_boundaries({"route_preview": {"coords": []}}, 3) == []
assert resources._route_day_boundaries({
    "route_preview": {"coords": [[45, 5], [45, 5]]}
}, 3) == []

print("20 sparse/uneven France route geometries: walk-distance accurate daily lookup anchors PASS")
print("Sparse polyline four-day food/water/stay fallback: six-call budget and original geometry preserved PASS")
