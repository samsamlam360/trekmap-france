"""Regression: Belle-Île loops must recover GR 340 even when Overpass is unavailable."""
from pathlib import Path
from types import SimpleNamespace
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_belle_ile_gr340_v9 as belle
from backend import trekbrain_gr_v9 as gr
from backend import trekbrain_trail_loop_rescue_v9 as rescue


def dense_side(a, b, steps=24):
    return [
        [a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps]
        for i in range(steps + 1)
    ]


def rectangle_members():
    south, north = 47.22, 47.39
    west, east = -3.34, -3.08
    corners = [[south, west], [south, east], [north, east], [north, west], [south, west]]
    out = []
    for a, b in zip(corners, corners[1:]):
        points = dense_side(a, b)
        out.append({"type": "way", "geometry": [{"lat": p[0], "lon": p[1]} for p in points]})
    return out


def osm_full_xml():
    members = rectangle_members()
    node_id = 1
    nodes = []
    ways = []
    relation_members = []
    for way_index, member in enumerate(members, start=1):
        refs = []
        for point in member["geometry"]:
            refs.append(node_id)
            nodes.append(f'<node id="{node_id}" lat="{point["lat"]}" lon="{point["lon"]}" />')
            node_id += 1
        ways.append(
            f'<way id="{1000 + way_index}">' + ''.join(f'<nd ref="{ref}" />' for ref in refs) + '</way>'
        )
        relation_members.append(f'<member type="way" ref="{1000 + way_index}" role="" />')
    relation = (
        f'<relation id="{belle._GR340_RELATION_ID}">'
        + ''.join(relation_members)
        + '<tag k="type" v="route" />'
        + '<tag k="route" v="hiking" />'
        + '<tag k="ref" v="GR 340" />'
        + '<tag k="name" v="Tour de Belle-Île-en-Mer" />'
        + '<tag k="network" v="nwn" />'
        + '</relation>'
    )
    return '<osm version="0.6">' + ''.join(nodes) + ''.join(ways) + relation + '</osm>'


payload = {
    "elements": [{
        "type": "relation",
        "id": belle._GR340_RELATION_ID,
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
assert route["targeted_relation_id"] == belle._GR340_RELATION_ID
assert route["coords"][0] == route["coords"][-1]
assert str(belle._GR340_RELATION_ID) in queries[0]
assert "GR 340" in start["name"]

# Production regression: an earlier Overpass timeout can open the circuit breaker
# before round-trip recovery starts. The dedicated OSM relation/full endpoint must
# still recover the real GR 340 instead of falling through to ORS round-trip.
class FakeResponse:
    status_code = 200
    text = osm_full_xml()

real_get = belle.requests.get
belle._DIRECT_CACHE = None
api_calls = []
belle.requests.get = lambda url, **kwargs: (api_calls.append((url, kwargs)) or FakeResponse())
blocked_v3 = SimpleNamespace(_overpass=lambda _query: (_ for _ in ()).throw(RuntimeError("Overpass ignoré après un timeout récent")))
start_blocked = {"name": "Belle-Île-en-Mer", "lat": 47.31, "lon": -3.20, "category": "place"}
try:
    recovered, warning = belle._targeted_gr340(blocked_v3, gr, rescue, start_blocked, 90.0)
finally:
    belle.requests.get = real_get
assert warning is None, warning
assert recovered is not None
assert recovered["relation_ref"] == "GR 340"
assert recovered["gr340_source"] == "osm-api-relation-full"
assert recovered["targeted_relation_id"] == belle._GR340_RELATION_ID
assert api_calls and str(belle._GR340_RELATION_ID) in api_calls[0][0]

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

print("Belle-Île GR 340 survives an open Overpass circuit: OK")

# Also run the canonical end-to-end planner regression for the exact daily
# targets seen in production (18 and 22 km/day).
runpy.run_path(str(ROOT / "scripts" / "test_trekbrain_v9_belle_ile_canonical.py"), run_name="__main__")
