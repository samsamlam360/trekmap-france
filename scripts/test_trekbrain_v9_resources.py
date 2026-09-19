"""Regression checks for TrekBrain v9.1 route-relative resources."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("TREKBRAIN_VERSION", "v9")

from backend.trekbrain_resources_v9 import enrich_resources


def sample_plan():
    return {
        "duration_days": 2,
        "start": {"name": "Départ", "lat": 45.0000, "lon": 5.0000},
        "end": {"name": "Arrivée", "lat": 45.1000, "lon": 5.1000},
        "route_preview": {
            "coords": [
                [45.0000, 5.0000],
                [45.0250, 5.0250],
                [45.0500, 5.0500],
                [45.0750, 5.0750],
                [45.1000, 5.1000],
            ]
        },
        "stages": [{"day": 1}, {"day": 2}],
        "water": [
            {"name": "Fontaine proche", "lat": 45.024, "lon": 5.024, "status": "potable_referenced", "source_url": "https://www.openstreetmap.org/node/1"},
            {"name": "Source trop loin", "lat": 45.300, "lon": 5.300, "status": "unverified", "source_url": "https://www.openstreetmap.org/node/2"},
        ],
        "accommodations": [
            {"name": "Camping du test", "type": "Camping", "lat": 45.052, "lon": 5.052, "source_url": "https://www.openstreetmap.org/node/3"},
            {"name": "Refuge du test", "type": "Refuge / abri", "lat": 45.077, "lon": 5.077, "source_url": "https://www.openstreetmap.org/node/4"},
        ],
        "points_of_interest": [
            {"name": "Gare du départ", "type": "transport", "lat": 45.001, "lon": 5.001, "source_url": "https://www.openstreetmap.org/node/5"},
            {"name": "Arrêt de bus arrivée", "type": "transport", "lat": 45.099, "lon": 5.099, "source_url": "https://www.openstreetmap.org/node/6"},
            {"name": "GR Test", "type": "itinéraire balisé", "lat": 45.060, "lon": 5.060, "source_url": "https://www.openstreetmap.org/relation/7"},
        ],
        "transport": {"outbound": "Gare du départ", "return": "Arrêt de bus arrivée"},
    }


plan = enrich_resources(sample_plan())
resources = plan["map_resources"]
points = resources["points"]
names = {p["name"] for p in points}
assert "Fontaine proche" in names
assert "Source trop loin" not in names, "far resources must be filtered from the map"
assert "Camping du test" in names
assert "Refuge du test" in names
assert "Gare du départ" in names
assert "Arrêt de bus arrivée" in names
assert "GR Test" in names
assert all(p["route_day"] in {1, 2} for p in points)
assert all(p["distance_to_route_km"] >= 0 for p in points)
assert resources["counts"]["water"] == 1
assert resources["counts"]["camping"] == 1
assert resources["counts"]["refuge"] == 1
assert resources["counts"]["station"] == 1
assert resources["counts"]["transport"] == 1
assert resources["counts"]["trail"] == 1
assert plan["transport"]["outbound_point"]["name"] == "Gare du départ"
assert plan["transport"]["return_point"]["name"] == "Arrêt de bus arrivée"
assert plan["trail_context"]["near_route"][0]["name"] == "GR Test"

# Production regression: /ai/plan must accept the planner model as JSON body,
# never as a query parameter named `data`.
from backend import app_v5

schema = app_v5.app.openapi()
plan_post = schema["paths"]["/ai/plan"]["post"]
assert "requestBody" in plan_post, "/ai/plan lost its JSON request body"
parameters = plan_post.get("parameters") or []
assert not any(p.get("in") == "query" and p.get("name") == "data" for p in parameters), \
    "/ai/plan incorrectly exposes data as a query parameter"
content = plan_post["requestBody"].get("content") or {}
assert "application/json" in content, "/ai/plan no longer accepts application/json"

print("TrekBrain v9.1 route resources + JSON body contract: OK")
