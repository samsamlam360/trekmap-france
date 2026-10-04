"""Regression for campsite-aware ORS round-trip recovery."""
from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as free
from backend import trekbrain_place_guard_v9 as place_guard
from backend import trekbrain_roundtrip_v9 as roundtrip


# Build an approximately 72 km synthetic corridor. The three campsites sit
# around 1.5 km off the corridor and about 3 km before each mathematically exact
# 18 km split. The old exact-anchor lookup therefore misses them, even though
# they produce sensible day lengths once the stage boundaries are allowed to move.
lat = 48.60
km_per_lon_degree = 111.32 * math.cos(math.radians(lat))
lon_step = 1.0 / km_per_lon_degree
coords = [[lat, -1.80 + i * lon_step] for i in range(73)]

north_offset = 1.5 / 111.32
camp_indices = (15, 33, 51)
camps = [
    {
        "name": f"Camping test {n}",
        "lat": coords[idx][0] + north_offset,
        "lon": coords[idx][1],
        "category": "camping",
        "source_url": f"https://www.openstreetmap.org/node/{1000+n}",
    }
    for n, idx in enumerate(camp_indices, start=1)
]


class CorridorV3:
    @staticmethod
    def _nearby(lat, lon, radius, categories):
        if "camping" not in categories:
            return []
        center = [lat, lon]
        return [
            dict(camp)
            for camp in camps
            if roundtrip._haversine(center, [camp["lat"], camp["lon"]]) <= radius
        ]

    @staticmethod
    def _dist(a, b):
        return roundtrip._haversine([a["lat"], a["lon"]], [b["lat"], b["lon"]])


anchors = roundtrip._equal_anchors(coords, 4)
assert len(anchors) == 3, anchors

# Reproduce the production failure shown on mobile: no camping is found by
# looking only within 2.6 km of the exact mathematical endpoints.
legacy = roundtrip._nearest_unique_stays(CorridorV3, anchors, "camping", 2.6)
assert legacy == [], legacy

chosen, meta = roundtrip._balanced_corridor_stays(
    CorridorV3,
    coords,
    days=4,
    category="camping",
    daily_target=18.0,
    daily_min=13.5,
    daily_max=22.5,
)
assert len(chosen) == 3, (chosen, meta)
assert [x["name"] for x in chosen] == [x["name"] for x in camps], (chosen, meta)
assert all(float(x["_offroute_km"]) < 2.0 for x in chosen), chosen
assert float(meta["search_radius_km"]) >= 3.6, meta

start = {"name": "Départ", "lat": coords[0][0], "lon": coords[0][1], "category": "place"}
route_points = roundtrip._route_points_with_stays(coords, start, chosen, 4)
route_names = [str(x.get("name") or "") for x in route_points]
for camp in camps:
    assert camp["name"] in route_names, route_names
assert route_points[0]["name"] == "Départ"
assert route_points[-1]["name"] == "Départ"
assert sum(1 for x in route_points if x.get("category") == "route_anchor") >= 8, route_points

print("Adaptive campsite corridor recovery: OK")

# The latency-sensitive v9 round-trip path explicitly asks for one Nominatim
# attempt. Historical/free geocoding keeps two attempts by default.
seen_retry_budgets = []
original_request_json = free._request_json

def fake_request_json(_url, **kwargs):
    seen_retry_budgets.append((kwargs.get("service"), kwargs.get("retries")))
    return []

free._request_json = fake_request_json
try:
    free._geocode_nominatim("Zone test", retries=1)
    free._geocode_nominatim("Zone test historique")
finally:
    free._request_json = original_request_json

assert seen_retry_budgets == [("Nominatim", 1), ("Nominatim", 2)], seen_retry_budgets

# Zero is reserved for a secondary spelling fallback: do not call Nominatim,
# but still allow Photon/local to resolve the place.
skip_calls = []
original_nominatim = free._geocode_nominatim
original_photon = free._geocode_photon
original_local = free._local_geocode

def should_not_call_nominatim(*_args, **_kwargs):
    skip_calls.append("nominatim")
    raise AssertionError("Nominatim must be skipped for zero retry budget")

def fake_photon(query):
    skip_calls.append(("photon", query))
    return [{"name": query, "lat": 48.2, "lon": -4.5}]

free._geocode_nominatim = should_not_call_nominatim
free._geocode_photon = fake_photon
free._local_geocode = lambda _query: []
try:
    rows = free._geocode("Variante secondaire", nominatim_retries=0)
finally:
    free._geocode_nominatim = original_nominatim
    free._geocode_photon = original_photon
    free._local_geocode = original_local

assert rows and rows[0]["name"] == "Variante secondaire"
assert skip_calls == [("photon", "Variante secondaire")], skip_calls

roundtrip_retry_budgets = []

class FastGeoV3:
    @staticmethod
    def _geocode(query, **kwargs):
        roundtrip_retry_budgets.append(kwargs.get("nominatim_retries"))
        return [{"name": query, "lat": 48.2, "lon": -4.5}]

assert roundtrip._roundtrip_geocode(FastGeoV3, "Presqu'île test")
assert roundtrip._roundtrip_geocode(
    FastGeoV3, "Presqu'île test sans France", nominatim_retries=0
)
assert roundtrip_retry_budgets == [1, 0], roundtrip_retry_budgets

class LegacyGeoV3:
    @staticmethod
    def _geocode(query):
        return [{"name": query, "lat": 48.2, "lon": -4.5}]

assert roundtrip._roundtrip_geocode(LegacyGeoV3, "Zone historique")

# Production v9 installs the Belle-Île place guard around v3._geocode. The
# wrapper must preserve the retry budget; otherwise the zero-budget secondary
# spelling silently falls back to a normal Nominatim lookup.
forwarded = []

def guarded_original(query, **kwargs):
    forwarded.append((query, dict(kwargs)))
    return [{"name": query, "lat": 48.2, "lon": -4.5}]

guarded = place_guard.guarded_geocode_factory(guarded_original)

class GuardedGeoV3:
    _geocode = staticmethod(guarded)

assert roundtrip._roundtrip_geocode(
    GuardedGeoV3, "Presqu'île de Crozon", nominatim_retries=0
)
assert forwarded == [
    ("Presqu'île de Crozon", {"nominatim_retries": 0})
], forwarded

# The canonical Belle-Île guard still wins locally and never calls the external
# geocoder, regardless of optional retry controls.
forwarded.clear()
rows = guarded("Belle-Île-en-Mer", nominatim_retries=0)
assert rows and rows[0].get("geocode_guard") == "belle-ile-en-mer", rows
assert forwarded == [], forwarded

print("Fast round-trip geocoding retry budget: OK")

