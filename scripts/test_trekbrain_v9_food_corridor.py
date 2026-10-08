"""Food resupply must be real, route-close and visible without preprepared treks."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as geo
from backend import trekbrain_resources_v9 as resources
from backend import trekbrain_route_logistics_v9 as logistics
from backend import smart_planner_v3 as planner

coords = [[44.0000, 3.0000], [44.0100, 3.0100], [44.0200, 3.0200]]
far_food = {"name": "Épicerie éloignée", "category": "food", "lat": 44.3, "lon": 3.3}
near_food = {
    "name": "Épicerie du sentier", "category": "food",
    "lat": 44.01, "lon": 3.01,
    "source_url": "https://www.openstreetmap.org/node/9990",
}
plan = {"route_preview": {"coords": coords}, "water": [], "resources": [far_food]}
missing = resources._missing_terrain_intent(plan, {"food": True, "water": False})
assert missing["food"] is True, missing
assert resources._missing_terrain_intent(
    {**plan, "resources": [near_food]}, {"food": True}
)["food"] is False
# Food supplied as a genuine OSM point of interest must be considered too.
assert resources._missing_terrain_intent({
    **plan, "resources": [],
    "points_of_interest": [near_food],
}, {"food": True})["food"] is False
from_poi = resources.enrich_resources({
    **plan, "resources": [], "duration_days": 1,
    "points_of_interest": [near_food], "accommodations": [], "water": [],
})
assert from_poi["map_resources"]["counts"]["food"] == 1, from_poi["map_resources"]

# One HTTP request but separate Overpass output quotas: water cannot consume
# rural shops, each trail segment receives its own quota.
old_json = geo._request_json
calls = []
def fake_route_query(url, **kwargs):
    query = kwargs["data"]["data"]
    calls.append((url, query))
    assert "out center tags 90;" in query and "out center tags 22;" in query and "(around:4500," in query, query
    assert '["shop"~' in query and "greengrocer" in query, query
    elements = [
        {"type": "node", "id": index, "lat": 44.008, "lon": 3.008,
         "tags": {"amenity": "drinking_water"}}
        for index in range(80)
    ]
    elements.append({
        "type": "node", "id": 91111, "lat": 44.011, "lon": 3.011,
        "tags": {"name": "Épicerie de proximité", "shop": "general"},
    })
    elements.append({
        "type": "node", "id": 91112, "lat": 44.012, "lon": 3.012,
        "tags": {"name": "Commerce privé", "shop": "convenience", "access": "private"},
    })
    return {"elements": elements}

geo._request_json = fake_route_query
try:
    terrain = resources._bbox_route_water_food(plan, {"food": True, "water": True})
finally:
    geo._request_json = old_json
assert len(calls) == 1, calls
groceries = [r for r in terrain if r["category"] == "food"]
assert len(groceries) == 1 and groceries[0]["name"] == "Épicerie de proximité", groceries
assert groceries[0]["source_url"].endswith("/91111"), groceries

# Route-first lodging bundle uses an independent quota for food too, and
# preserves actual OSM coordinates and source identifiers for a rural shop.
calls.clear()
def fake_bundle(url, **kwargs):
    query = kwargs["data"]["data"]
    calls.append(query)
    assert "out center tags 90;" in query, query
    assert "shop" in query and "greengrocer" in query
    return {"elements": [
        {"type": "node", "id": 93223, "lat": 44.012, "lon": 3.012,
         "tags": {"shop": "greengrocer", "name": "Primeur du sentier"}},
    ]}
geo._request_json = fake_bundle
try:
    stays, rows, preloaded = logistics._bbox_route_bundle(coords, "camping")
finally:
    geo._request_json = old_json
assert calls and preloaded and not stays, (calls, stays, rows)
assert len(rows) == 1 and rows[0]["category"] == "food", rows
assert rows[0]["source_url"].endswith("/93223"), rows

# The old Photon query was q=boulangerie + osm_tag=shop:supermarket,
# an impossible match for OSM bakeries. Search across real food shop classes
# and post-filter by an exact eligible shop subtype.
old_photon = planner._request_json
seen_params = {}
def mock_photon(url, **kwargs):
    seen_params.update(kwargs["params"])
    return {"features": [{
        "properties": {"name": "Boulangerie réelle", "osm_key": "shop",
                       "osm_value": "bakery", "countrycode": "FR",
                       "osm_type": "N", "osm_id": 43210},
        "geometry": {"coordinates": [3.0008, 44.0008]},
    }, {
        "properties": {"name": "Restaurant non admis", "osm_key": "amenity",
                       "osm_value": "restaurant", "countrycode": "FR"},
        "geometry": {"coordinates": [3.0001, 44.0001]},
    }]}

planner._request_json = mock_photon
try:
    food = planner._photon_anchor_resource(
        {"lat": 44.0, "lon": 3.0, "category": "route_anchor"},
        "food",
        ("shop:supermarket", "shop:convenience", "shop:bakery"),
        6.5,
    )
finally:
    planner._request_json = old_photon
assert seen_params["q"] == "boulangerie", seen_params
assert seen_params["osm_tag"] == "shop", seen_params
assert food and "Boulangerie" in food["name"] and food["category"] == "food", food
assert food["source_url"].endswith("/43210"), food

print("TrekBrain v9 real near-route food coverage and Photon filter: PASS")
