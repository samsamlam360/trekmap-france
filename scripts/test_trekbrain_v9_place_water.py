"""Regressions for Belle-Île geocoding and post-route water discovery."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.trekbrain_place_guard_v9 import guarded_geocode_factory, install_place_guard
from backend.trekbrain_water_discovery_v9 import discover_water_points
from backend import trekbrain_resources_v9 as resources


# A generic geocoder is allowed to be wrong; the guard must never send the
# explicit Belle-Île-en-Mer request to that ambiguous provider.
calls = []

def wrong_geocoder(query):
    calls.append(query)
    return [{"name": "Belle Île, Chelles", "short_name": "Belle Île", "lat": 48.8668, "lon": 2.5988}]

guarded = guarded_geocode_factory(wrong_geocoder)
row = guarded("Belle-Île-en-Mer, France")[0]
assert abs(float(row["lat"]) - 47.3331) < 0.001
assert abs(float(row["lon"]) + 3.1870) < 0.001
assert row["short_name"] == "Belle-Île-en-Mer"
assert not calls, "Belle-Île-en-Mer must be resolved before the ambiguous provider"

guarded("Paris, France")
assert calls == ["Paris, France"]


# The request layer must recognise the island even with wording that the generic
# parser used to miss ("trek de ..." rather than "trek à ...").
class DummyGeo:
    _geocode = staticmethod(wrong_geocoder)

class DummyV3:
    _geocode = staticmethod(wrong_geocoder)

class DummyRequest:
    _extract_prompt_places = staticmethod(lambda _prompt: [])

install_place_guard(DummyV3, DummyGeo, DummyRequest)
places = DummyRequest._extract_prompt_places("Je veux faire un trek de Belle-Île-en-Mer en 4 jours")
assert places and places[0]["kind"] == "route_area"
assert places[0]["place"] == "Belle-Île-en-Mer"
assert DummyGeo._geocode("Belle-Ile-en-Mer France")[0]["lon"] < -3.0


# Water discovery is one batched Overpass query after routing. It supplies map
# markers but never changes the route geometry.
class WaterV3:
    calls = 0

    @staticmethod
    def _overpass(query):
        WaterV3.calls += 1
        assert 'amenity"="drinking_water' in query
        return {
            "elements": [
                {
                    "type": "node",
                    "id": 123,
                    "lat": 47.3340,
                    "lon": -3.1840,
                    "tags": {"amenity": "drinking_water", "name": "Fontaine du test"},
                }
            ]
        }

route_coords = [
    [47.3331, -3.1870],
    [47.3340, -3.1840],
    [47.3360, -3.1800],
]
plan = {
    "duration_days": 2,
    "route_preview": {"coords": route_coords, "distance": 2.0, "distance_km": 2.0, "fallback": False},
    "start": {"lat": 47.3331, "lon": -3.1870},
    "end": {"lat": 47.3360, "lon": -3.1800},
    "stages": [],
    "water": [],
    "accommodations": [],
    "points_of_interest": [],
    "transport": {},
}
points = discover_water_points(WaterV3, plan)
assert WaterV3.calls == 1, "Water discovery should use one batched Overpass request"
assert len(points) == 1 and points[0]["display_only"] is True
assert points[0]["name"] == "Fontaine du test"
plan["water"] = points
before = [list(x) for x in route_coords]
enriched = resources.enrich_resources(plan)
assert enriched["route_preview"]["coords"] == before
map_water = [x for x in enriched["map_resources"]["points"] if x.get("kind") == "water"]
assert map_water and map_water[0]["name"] == "Fontaine du test"

print("Belle-Île place guard + display-only water discovery: OK")
