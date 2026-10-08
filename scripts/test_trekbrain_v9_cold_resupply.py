"""New-region food discovery must receive fair Photon slots without extra calls.

Simulates an uncached, four-day walking route where transit, lodging, and
water all need discovery too. Route geometry and API contracts remain untouched.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import smart_planner_v3 as planner


def anchor(i):
    return {
        "name": "Départ" if i == 0 else f"Repère jour {i}",
        "category": "route_anchor",
        "lat": 45.0 + i * .01,
        "lon": 5.0 + i * .01,
    }


boundaries = [anchor(i) for i in range(5)]
intent = {
    "food": True, "water": True, "sleep": True,
    "transit": True, "accommodation": "camping",
}
calls = []
original = planner._photon_anchor_resource


def fake_resource(point, category, tags, radius):
    calls.append((point, category, tags, radius))
    return {
        "lat": point["lat"], "lon": point["lon"],
        "name": f"Source {category} {point['name']}",
        "category": category,
        "source_url": f"https://www.openstreetmap.org/node/{900000+len(calls)}",
    }


planner._photon_anchor_resource = fake_resource
try:
    cold = planner._postroute_corridor_resources(boundaries, intent, [])
    groups = [kind for _point, kind, _tags, _radius in calls]
    assert len(calls) == 6 and len(cold) == 6, (calls, cold)
    assert groups.count("food") == 2, groups
    assert groups.count("transit") >= 1, groups
    assert groups.count("water") >= 1, groups
    assert groups.count("stay") >= 1, groups
    searched = {round(p["lat"], 5) for p, kind, _, _ in calls if kind == "food"}
    assert len(searched) == 2, searched
    assert 45.0 in searched, "Trailhead grocery should be probed on a cold visit"

    # An invented shop without a source must NOT suppress the first visit's
    # real grocery probe, even if its coordinates match the trailhead.
    calls.clear()
    unsourced = planner._postroute_corridor_resources(boundaries, intent, [{
        "category": "food", "name": "AI-guessed market",
        "lat": boundaries[0]["lat"], "lon": boundaries[0]["lon"],
    }])
    assert len(calls) <= 6 and len(unsourced) <= 6, calls
    assert any(
        kind == "food" and abs(p["lat"] - 45.0) < 0.00001
        for p, kind, _, _ in calls
    ), calls

    # A verified shop at the start DOES suppress just the redundant probe;
    # the missing first and last overnight regions now get their own probes.
    calls.clear()
    sourced = planner._postroute_corridor_resources(boundaries, intent, [{
        "category": "food", "name": "Confirmed OSM market",
        "lat": 45.0, "lon": 5.0,
        "source_url": "https://www.openstreetmap.org/node/990001",
    }])
    food_locations = {
        round(point["lat"], 5)
        for point, category, _, _ in calls if category == "food"
    }
    assert len(calls) <= 6 and len(sourced) <= 6, calls
    assert 45.0 not in food_locations, food_locations
    assert food_locations == {45.01, 45.03}, food_locations

    # If no food is requested, existing water, transit, and overnight
    # categories remain eligible, still within the same request budget.
    calls.clear()
    no_food = planner._postroute_corridor_resources(
        boundaries, {**intent, "food": False}, [],
    )
    assert calls and len(calls) <= 6, calls
    assert "food" not in [kind for _, kind, _, _ in calls], calls
    assert len(no_food) <= 6, no_food
finally:
    planner._photon_anchor_resource = original

print("TrekBrain first-visit food coverage: 2 distinct groceries in six-call cap, no unsourced suppression: PASS")
