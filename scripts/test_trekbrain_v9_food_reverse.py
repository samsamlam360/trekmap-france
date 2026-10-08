"""Photon reverse food searches are bounded, source-linked and route-relative."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as free
from backend import trekbrain_food_reverse_v9 as shops
from backend import trekbrain_resources_v9 as resources

route = {
    "duration_days": 3,
    "route_preview": {
        "coords": [[45.0, 5.0], [45.01, 5.01], [45.02, 5.02], [45.03, 5.03]],
        "fallback": False,
    },
    "start": {"lat": 45.0, "lon": 5.0},
    "end": {"lat": 45.03, "lon": 5.03},
    "stages": [{"day": 1}, {"day": 2}, {"day": 3}],
}
original = free._request_json
calls = []
def reverse_response(url, **kwargs):
    assert url == shops.PHOTON_REVERSE_URL, url
    params = kwargs.get("params") or {}
    assert "q" not in params, params
    assert params.get("osm_tag") == "shop", params
    assert params.get("radius") == 5 and int(params.get("limit")) <= 20, params
    assert kwargs.get("cache_empty") is False, kwargs
    assert float(kwargs.get("timeout") or 0) <= 1.8, kwargs
    calls.append(params)
    return {"features": [
        {
            "properties": {
                "name": "Épicerie référencée", "countrycode": "FR",
                "osm_key": "shop", "osm_value": "convenience",
                "osm_type": "N", "osm_id": 345678,
            },
            "geometry": {"coordinates": [5.011, 45.011]},
        },
        {
            "properties": {
                "name": "Restaurant non admis", "countrycode": "FR",
                "osm_key": "amenity", "osm_value": "restaurant",
                "osm_type": "N", "osm_id": 345679,
            },
            "geometry": {"coordinates": [5.011, 45.011]},
        },
        {
            "properties": {
                "name": "Commerce lointain", "countrycode": "FR",
                "osm_key": "shop", "osm_value": "supermarket",
                "osm_type": "N", "osm_id": 345680,
            },
            "geometry": {"coordinates": [6.0, 46.0]},
        },
        {
            "properties": {
                "name": "Commerce non documenté", "countrycode": "FR",
                "osm_key": "shop", "osm_value": "bakery",
            },
            "geometry": {"coordinates": [5.012, 45.012]},
        },
    ]}

free._request_json = reverse_response
successful_photon = {}
try:
    discovered = shops.discover_near_route_shops(route, successful_photon)
finally:
    free._request_json = original
assert 1 <= len(calls) <= 5, calls
assert len(discovered) == 1, discovered
assert successful_photon["status"] == "found" and successful_photon["responses"] >= 1
assert discovered[0]["name"] == "Épicerie référencée", discovered
assert discovered[0]["source_url"] == "https://www.openstreetmap.org/node/345678"
assert discovered[0]["osm_tags"] == {"shop": "convenience"}
assert resources._route_match(route["route_preview"]["coords"], discovered[0])[0] < 4.5

# An unavailable provider must degrade without raising or creating a fake shop.
def blocked_provider(url, **kwargs):
    raise RuntimeError("Photon HTTP 429")
free._request_json = blocked_provider
failed_photon = {}
try:
    assert shops.discover_near_route_shops(route, failed_photon) == []
finally:
    free._request_json = original

assert failed_photon["status"] == "unavailable" and failed_photon["responses"] == 0

# If primary Overpass is unavailable, use the configured independent instance,
# not the sibling FOSSGIS endpoint that typically shares the same outage.
mirrors = []
def mock_overpass(url, **kwargs):
    mirrors.append(url)
    if len(mirrors) == 1:
        raise RuntimeError("OSM mirror throttle")
    return {"elements": [{
        "type": "node", "id": 45678, "lat": 45.01, "lon": 5.01,
        "tags": {"name": "Commerce", "shop": "convenience"},
    }]}
free._request_json = mock_overpass
overpass_stats = {}
try:
    rows = resources._bbox_route_water_food(
        route, {"food": True, "water": False}, overpass_stats
    )
finally:
    free._request_json = original
assert len(mirrors) == 2, mirrors
assert mirrors[0] == free.OVERPASS_URLS[0], mirrors
assert mirrors[1] == free.OVERPASS_URLS[-1], mirrors
assert rows and rows[0]["category"] == "food", rows
assert overpass_stats["status"] == "found", overpass_stats
assert overpass_stats["attempts"] == 2 and overpass_stats["responses"] == 1

# Two failed mirrors must be reported as an unavailable search, not as proof
# that the hiking corridor contains no grocery or water points.
free._request_json = blocked_provider
no_overpass = {}
try:
    assert resources._bbox_route_water_food(
        route, {"food": True, "water": False}, no_overpass
    ) == []
finally:
    free._request_json = original
assert no_overpass["status"] == "unavailable" and no_overpass["responses"] == 0, no_overpass
assert no_overpass["attempts"] == 2, no_overpass

# Long closed loops must sample distinct overnight stages instead of
# wasting two of three reverse probes on the identical start/finish point.
loop = {
    "duration_days": 4,
    "route_preview": {
        "coords": [
            [45.0, 5.0], [45.015, 5.015], [45.03, 5.03],
            [45.04, 5.015], [45.03, 5.0], [45.015, 4.99], [45.0, 5.0],
        ],
        "fallback": False,
    },
    "start": {"lat": 45.0, "lon": 5.0},
    "end": {"lat": 45.0, "lon": 5.0},
    "stages": [{"day": i} for i in range(1, 5)],
}
probes = []
def empty_reverse(url, **kwargs):
    assert url == shops.PHOTON_REVERSE_URL
    assert (kwargs.get("params") or {}).get("osm_tag") == "shop"
    probes.append(kwargs["params"])
    return {"features": []}

free._request_json = empty_reverse
try:
    assert shops.discover_near_route_shops(loop) == []
finally:
    free._request_json = original
positions = {(round(c["lat"], 4), round(c["lon"], 4)) for c in probes}
assert len(probes) == 4 and len(positions) == 4, probes
assert sum(resources._distance_km((45.0, 5.0), p) < 0.05 for p in positions) == 1, (
    "Loop trailhead shop search was silently dropped", probes
)
assert sum(resources._distance_km((45.0, 5.0), p) > 0.25 for p in positions) == 3, probes

# Likewise, a point-to-point route must retain the departure-town AND
# arrival-town grocery probes, not only overnight stages.
traverse = {
    "duration_days": 3,
    "route_preview": {
        "coords": [[45.00, 5.00], [45.01, 5.01], [45.02, 5.02], [45.03, 5.03]],
        "fallback": False,
    },
    "start": {"lat": 45.00, "lon": 5.00},
    "end": {"lat": 45.03, "lon": 5.03},
    "stages": [{"day": i} for i in range(1, 4)],
}
probes.clear()
free._request_json = empty_reverse
try:
    assert shops.discover_near_route_shops(traverse) == []
finally:
    free._request_json = original
locations = [(c["lat"], c["lon"]) for c in probes]
assert len(locations) == 4 and len(set(locations)) == 4, locations
assert any(resources._distance_km((45.00, 5.00), p) < 0.05 for p in locations), locations
assert any(resources._distance_km((45.03, 5.03), p) < 0.05 for p in locations), locations

print("TrekBrain reverse food providers, unique loop probes and both traverse endpoints: PASS")


# A single shop on day 1 must not turn off discovery of supplies for
# days 2 and 3. Conversely, verified shops on every day avoid new HTTP calls.
partial_route = {
    **route,
    "food": [{
        "lat": 45.0, "lon": 5.0, "name": "Épicerie du départ",
        "source_url": "https://www.openstreetmap.org/node/910001",
        "category": "food",
    }],
}
assert resources._missing_terrain_intent(
    partial_route, {"food": True, "water": False}
)["food"] is True
full_route = {
    **route,
    "food": [
        {
            "lat": 45.0 + 0.01 * day, "lon": 5.0 + 0.01 * day,
            "name": f"Commerce vérifié {day}",
            "source_url": f"https://www.openstreetmap.org/node/{910010 + day}",
            "category": "food",
        } for day in range(3)
    ],
}
assert resources._missing_terrain_intent(
    full_route, {"food": True, "water": False}
)["food"] is False

# A returned water tap is not grounds for skipping the independent Overpass
# mirror when the user also asked for food. Every segment keeps an independent
# quota and out-of-corridor supermarkets are rejected.
requests = []
def fragmented_provider(url, **kwargs):
    query = (kwargs.get("data") or {}).get("data") or ""
    requests.append((url, query))
    assert "[out:json][timeout:8];" in query, query
    assert query.count("(around:4500,") >= 2, query
    assert query.count("out center tags 22;") >= 2, query
    if len(requests) == 1:
        return {"elements": [{
            "type": "node", "id": 920001, "lat": 45.0, "lon": 5.0,
            "tags": {"amenity": "drinking_water"},
        }]}
    return {"elements": [
        {
            "type": "node", "id": 920002, "lat": 45.02, "lon": 5.02,
            "tags": {"name": "Supérette d'étape", "shop": "convenience"},
        },
        {
            "type": "node", "id": 920003, "lat": 46.0, "lon": 6.0,
            "tags": {"name": "Hors itinéraire", "shop": "supermarket"},
        },
    ]}

stats = {}
free._request_json = fragmented_provider
try:
    discovered = resources._bbox_route_water_food(
        route, {"food": True, "water": True}, stats,
    )
finally:
    free._request_json = original
assert len(requests) == 2, requests
assert requests[0][0] == free.OVERPASS_URLS[0], requests
assert requests[1][0] == free.OVERPASS_URLS[-1], requests
assert stats["food_segments"] >= 2 and stats["food_accepted"] == 1, stats
assert stats["status"] == "found" and stats["responses"] == 2, stats
assert sum(p["category"] == "food" for p in discovered) == 1, discovered
assert len(discovered) == 2, discovered

# Five overnight anchors remain the maximum even for a many-day itinerary.
long_route = {
    "duration_days": 9,
    "route_preview": {
        "coords": [[45.0 + 0.01 * i, 5.0] for i in range(21)],
        "fallback": False,
    },
    "start": {"lat": 45.0, "lon": 5.0},
    "end": {"lat": 45.2, "lon": 5.0},
    "stages": [{"day": i} for i in range(1, 10)],
}
probes.clear()
free._request_json = empty_reverse
try:
    assert shops.discover_near_route_shops(long_route) == []
finally:
    free._request_json = original
assert len(probes) == 5, probes
assert len({(p["lat"], p["lon"]) for p in probes}) == 5, probes

print("TrekBrain segmented OSM food searches and per-day resupply coverage: PASS")
