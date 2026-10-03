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


# Route-day assignment must follow walked distance, not coordinate-array index.
# Router geometries are intentionally non-uniform: the third point is still
# near the start despite sitting halfway through the array.
uneven = sample_plan()
uneven["route_preview"]["coords"] = [
    [45.0000, 5.0000],
    [45.0010, 5.0000],
    [45.0020, 5.0000],
    [45.0990, 5.0000],
    [45.1000, 5.0000],
]
uneven["water"] = [
    {
        "name": "Fontaine encore jour 1",
        "lat": 45.0020,
        "lon": 5.0000,
        "status": "potable_referenced",
        "source_url": "https://www.openstreetmap.org/node/101",
    }
]
uneven["accommodations"] = []
uneven["points_of_interest"] = []
uneven_plan = enrich_resources(uneven)
uneven_water = next(
    point for point in uneven_plan["map_resources"]["points"]
    if point["name"] == "Fontaine encore jour 1"
)
assert uneven_water["route_day"] == 1, uneven_water


# The final resource overlay must not duplicate water or normal route-first
# lodging discovery. Food and transport remain active because they are not
# guaranteed by the lodging layer.
from backend import trekbrain_resources_v9 as resources_module
from backend.free_planner_v2 import AIPlanRequest

captured_post_intent = {}
real_postroute_resources = resources_module.v7.v5.v3._postroute_corridor_resources

def fake_postroute_resources(boundaries, intent, existing_items):
    captured_post_intent.update(dict(intent))
    return []

resources_module.v7.v5.v3._postroute_corridor_resources = fake_postroute_resources
try:
    dedupe_plan = sample_plan()
    dedupe_plan["logistics"] = {"status": "partial"}
    dedupe_request = AIPlanRequest(
        prompt=(
            "Boucle de 2 jours avec eau, ravitaillement, hébergement "
            "et transports utiles."
        ),
        region="Zone test",
        days=2,
        daily_km=18,
        route_type="Boucle",
        require_transit=True,
        require_water=True,
        require_accommodation=True,
        require_food=True,
    )
    resources_module._supplement_route_resources(dedupe_plan, dedupe_request)
finally:
    resources_module.v7.v5.v3._postroute_corridor_resources = real_postroute_resources

assert captured_post_intent.get("water") is False, captured_post_intent
assert captured_post_intent.get("sleep") is False, captured_post_intent
assert captured_post_intent.get("food") is True, captured_post_intent
assert captured_post_intent.get("transit") is True, captured_post_intent

# If the exact OSM terrain lookup found no water, one bounded Photon fallback
# must remain enabled. This runs inside the same post-route wave.
captured_missing_water = {}
def fake_missing_water(boundaries, intent, existing_items):
    captured_missing_water.update(dict(intent))
    return []

resources_module.v7.v5.v3._postroute_corridor_resources = fake_missing_water
try:
    missing_water_plan = sample_plan()
    missing_water_plan["water"] = []
    missing_water_plan["logistics"] = {"status": "complete"}
    resources_module._supplement_route_resources(missing_water_plan, dedupe_request)
finally:
    resources_module.v7.v5.v3._postroute_corridor_resources = real_postroute_resources

assert captured_missing_water.get("water") is True, captured_missing_water
assert captured_missing_water.get("sleep") is False, captured_missing_water

# Photon route resources must query exact OSM categories instead of relying on
# names such as "fontaine". This improves water/food/transit coverage without
# adding another network call.
v3_module = resources_module.v7.v5.v3
real_request_json = v3_module._request_json
captured_photon = {}

def fake_photon_request(url, *, params=None, **kwargs):
    captured_photon.update(dict(params or {}))
    return {
        "features": [{
            "properties": {
                "name": "Point d'eau test",
                "countrycode": "FR",
                "osm_key": "amenity",
                "osm_value": "drinking_water",
                "osm_type": "N",
                "osm_id": 123,
            },
            "geometry": {"coordinates": [5.001, 45.001]},
        }]
    }

v3_module._request_json = fake_photon_request
try:
    exact_water = v3_module._photon_anchor_resource(
        {"name": "Repère jour 1", "lat": 45.0, "lon": 5.0, "category": "route_anchor"},
        "water",
        ("amenity:drinking_water", "man_made:water_tap", "natural:spring"),
        5.5,
    )
finally:
    v3_module._request_json = real_request_json

assert exact_water and exact_water["water_status"] == "potable_referenced", exact_water
assert "q" not in captured_photon, captured_photon
assert "osm.amenity.drinking_water" in captured_photon.get("include", ""), captured_photon
assert "osm.natural.spring" in captured_photon.get("include", ""), captured_photon

captured_lodging = {}
def fake_lodging_request(url, *, params=None, **kwargs):
    captured_lodging.update(dict(params or {}))
    return {
        "features": [{
            "properties": {
                "name": "Gîte test",
                "countrycode": "FR",
                "osm_key": "tourism",
                "osm_value": "guest_house",
                "osm_type": "N",
                "osm_id": 124,
            },
            "geometry": {"coordinates": [5.001, 45.001]},
        }]
    }

v3_module._request_json = fake_lodging_request
try:
    text_lodging = v3_module._photon_anchor_resource(
        {"name": "Repère jour 1", "lat": 45.0, "lon": 5.0, "category": "route_anchor"},
        "stay",
        ("tourism:hotel", "tourism:guest_house", "tourism:hostel"),
        8.0,
        query_override="gîte",
    )
finally:
    v3_module._request_json = real_request_json

assert text_lodging and text_lodging["category"] == "lodging", text_lodging
assert captured_lodging.get("q") == "gîte", captured_lodging
assert "include" not in captured_lodging, captured_lodging


# Production regression: /ai/plan must accept the planner model as JSON body,
# never as a query parameter named `data`.
from backend import app_v5

assert resources_module.v7.v5.v3.POSTROUTE_RESOURCE_ENRICHMENT is False, (
    "TrekBrain v9 must leave post-route resources to the final overlays"
)

schema = app_v5.app.openapi()
plan_post = schema["paths"]["/ai/plan"]["post"]
assert "requestBody" in plan_post, "/ai/plan lost its JSON request body"
parameters = plan_post.get("parameters") or []
assert not any(p.get("in") == "query" and p.get("name") == "data" for p in parameters), \
    "/ai/plan incorrectly exposes data as a query parameter"
content = plan_post["requestBody"].get("content") or {}
assert "application/json" in content, "/ai/plan no longer accepts application/json"

print("TrekBrain v9.1 route resources + JSON body contract: OK")
