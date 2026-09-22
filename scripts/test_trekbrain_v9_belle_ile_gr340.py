"""Regression: Belle-Île loops must target GR 340 before generic ORS round-trip."""
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_belle_ile_gr340_v9 as belle
from backend import trekbrain_gr_v9 as gr
from backend import trekbrain_trail_loop_rescue_v9 as rescue


def rectangle_members():
    south, north = 47.22, 47.39
    west, east = -3.34, -3.08
    def geom(points):
        return {"type": "way", "geometry": [{"lat": a, "lon": b} for a, b in points]}
    return [
        geom([[south, west], [south, -3.22], [south, east]]),
        geom([[south, east], [47.30, east], [north, east]]),
        geom([[north, east], [north, -3.22], [north, west]]),
        geom([[north, west], [47.30, west], [south, west]]),
    ]

payload = {
    "elements": [{
        "type": "relation",
        "id": 9340,
        "tags": {"route": "hiking", "ref": "GR 340", "name": "Tour de Belle-Île-en-Mer", "network": "nwn"},
        "members": rectangle_members(),
    }]
}
queries = []
v3 = SimpleNamespace(_overpass=lambda query: (queries.append(query) or payload))
start = {"name": "Belle-Île-en-Mer", "lat": 47.31, "lon": -3.20, "category": "place"}
route, warning = belle._targeted_gr340(v3, gr, rescue, start, 90.0)
assert warning is None, warning
assert route is not None
assert route["fallback"] is False
assert route["routing_mode"] == "osm-hiking-relation-loop"
assert route["relation_ref"] == "GR 340"
assert route["targeted_relation_lookup"] is True
assert route["coords"][0] == route["coords"][-1]
assert "340" in queries[0]
assert "GR 340" in start["name"]

# Installing the priority wrapper must bypass a generic ORS round-trip whenever
# the targeted OSM relation is available.
generic_calls = []
roundtrip = SimpleNamespace(
    _best_roundtrip=lambda *args, **kwargs: (generic_calls.append(True) or {"routing_mode": "ors-round-trip"})
)
belle._INSTALLED = False
belle.install_belle_ile_gr340_priority(roundtrip, gr, rescue)
start2 = {"name": "Belle-Île-en-Mer", "lat": 47.31, "lon": -3.20, "category": "place"}
route2 = roundtrip._best_roundtrip(start2, 90.0, 12.0, 25.0, 5, v3)
assert route2["relation_ref"] == "GR 340"
assert not generic_calls, generic_calls

# Outside Belle-Île, preserve the generic planner.
start3 = {"name": "Tours", "lat": 47.39, "lon": 0.68, "category": "place"}
route3 = roundtrip._best_roundtrip(start3, 90.0, 12.0, 25.0, 5, v3)
assert route3["routing_mode"] == "ors-round-trip"
assert len(generic_calls) == 1

print("Belle-Île targeted GR 340 priority: OK")
