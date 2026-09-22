"""Regression for accommodation-only Overpass rescue."""
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as free
from backend import trekbrain_stays_rescue_v9 as rescue


START = {"name": "Mont Saint-Michel", "lat": 48.636, "lon": -1.511, "category": "place"}


def fake_request_json(url, **kwargs):
    query = (kwargs.get("data") or {}).get("data", "")
    assert 'tourism"="camp_site' in query
    return {
        "elements": [
            {"type": "node", "id": 1, "lat": 48.66, "lon": -1.36, "tags": {"tourism": "camp_site", "name": "Camping A"}},
            {"type": "way", "id": 2, "center": {"lat": 48.78, "lon": -1.50}, "tags": {"tourism": "camp_site", "name": "Camping B"}},
            {"type": "node", "id": 3, "lat": 48.67, "lon": -1.69, "tags": {"tourism": "camp_site", "name": "Camping C"}},
            {"type": "node", "id": 4, "lat": 48.72, "lon": -1.58, "tags": {"tourism": "caravan_site", "name": "Camping D"}},
        ]
    }


class V3:
    @staticmethod
    def _dist(a, b):
        # Enough for this regression: all fake stays are within the 35 km rescue radius.
        return 12.0


class CampsiteLoop:
    @staticmethod
    def _diverse_stays(v3, roundtrip, start, category, days, daily_target):
        # Simulate the real production failure: the broad Overpass lookup was
        # circuit-broken and silently appeared as an empty pool.
        return []

    @staticmethod
    def _bearing(start, point):
        return float(point["lon"]) + 2.0


class Roundtrip:
    pass


old_request = free._request_json
free._request_json = fake_request_json
try:
    rescue._INSTALLED = False
    rescue.install_stay_lookup_rescue(V3, CampsiteLoop, Roundtrip)
    rows = CampsiteLoop._diverse_stays(V3, Roundtrip, START, "camping", 4, 18.0)
finally:
    free._request_json = old_request

assert len(rows) >= 3, rows
assert {x["name"] for x in rows} >= {"Camping A", "Camping B", "Camping C"}
assert all(x["category"] == "camping" for x in rows)
assert all("_radial_km" in x and "_bearing" in x for x in rows)
print("Accommodation-only Overpass rescue: OK")
