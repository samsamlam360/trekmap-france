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
assert 1 <= len(calls) <= 3, calls
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
assert len(probes) == 3 and len(positions) == 3, probes
assert sum(resources._distance_km((45.0, 5.0), p) < 0.05 for p in positions) == 1, (
    "Loop trailhead shop search was silently dropped", probes
)
assert sum(resources._distance_km((45.0, 5.0), p) > 0.25 for p in positions) == 2, probes

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
assert len(locations) == 3 and len(set(locations)) == 3, locations
assert any(resources._distance_km((45.00, 5.00), p) < 0.05 for p in locations), locations
assert any(resources._distance_km((45.03, 5.03), p) < 0.05 for p in locations), locations

print("TrekBrain reverse food providers, unique loop probes and both traverse endpoints: PASS")
