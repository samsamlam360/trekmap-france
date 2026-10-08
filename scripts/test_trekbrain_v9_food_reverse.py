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
try:
    discovered = shops.discover_near_route_shops(route)
finally:
    free._request_json = original
assert 1 <= len(calls) <= 3, calls
assert len(discovered) == 1, discovered
assert discovered[0]["name"] == "Épicerie référencée", discovered
assert discovered[0]["source_url"] == "https://www.openstreetmap.org/node/345678"
assert discovered[0]["osm_tags"] == {"shop": "convenience"}
assert resources._route_match(route["route_preview"]["coords"], discovered[0])[0] < 4.5

# An unavailable provider must degrade without raising or creating a fake shop.
def blocked_provider(url, **kwargs):
    raise RuntimeError("Photon HTTP 429")
free._request_json = blocked_provider
try:
    assert shops.discover_near_route_shops(route) == []
finally:
    free._request_json = original

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
try:
    rows = resources._bbox_route_water_food(route, {"food": True, "water": False})
finally:
    free._request_json = original
assert len(mirrors) == 2, mirrors
assert mirrors[0] == free.OVERPASS_URLS[0], mirrors
assert mirrors[1] == free.OVERPASS_URLS[-1], mirrors
assert rows and rows[0]["category"] == "food", rows
print("TrekBrain reverse food providers and independent OSM fallback: PASS")
