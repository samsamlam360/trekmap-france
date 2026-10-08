"""Positive-only PostGIS POI cache regression, independent of external APIs."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_osm_cache_v9 as cache
from backend import trekbrain_resources_v9 as resources
from backend import database


def row(osm_id, category="food"):
    return {
        "source_url": f"https://www.openstreetmap.org/node/{osm_id}",
        "category": category, "name": f"Commerce {osm_id}",
        "lat": 45.01, "lon": 5.01,
    }


# Legacy planners omit category in per-family lists. All supported resource
# kinds must reach the PostGIS cache without assuming new response contracts.
legacy_rows = resources._cache_source_candidates({
    "water": [{"name": "Source au bord du sentier", "lat": 45.01, "lon": 5.01,
               "status": "potable_referenced",
               "source_url": "https://www.openstreetmap.org/node/900100"}],
    "food": [{"name": "Épicerie", "lat": 45.01, "lon": 5.01,
              "source_url": "https://www.openstreetmap.org/node/900101"}],
    "accommodations": [
        {"name": "Camping du lac", "type": "Camping", "lat": 45.01, "lon": 5.01,
         "source_url": "https://www.openstreetmap.org/node/900102"},
        {"name": "Refuge du col", "type": "Refuge / abri",
         "lat": 45.01, "lon": 5.01,
         "source_url": "https://www.openstreetmap.org/node/900103"},
    ],
})
assert {x["category"] for x in legacy_rows} == {
    "food", "water", "camping", "refuge"
}, legacy_rows
assert all(cache._candidate(x) for x in legacy_rows), legacy_rows
assert next(x for x in legacy_rows if x["category"] == "water")["status"] == "potable_referenced"

assert cache._candidate({**row(900011), "osm_tags": {"description": "X" * 12000}})["tags"] == "{}"
assert cache._candidate(row(900001))
assert cache._candidate(row(900001, "water"))
assert cache._candidate(row(900001, "camping"))
assert cache._candidate({**row(1), "osm_tags": {"shop": "vacant"}}) is None
assert cache._candidate({**row(1), "osm_tags": {"access": "private"}}) is None
assert cache._candidate({**row(1), "source_url": "https://example.org/1"}) is None
assert cache._candidate({**row(1), "lat": 75.0}) is None
assert cache._candidate({**row(1), "lon": float("nan")}) is None
assert cache._candidate({**row(1), "category": "bar"}) is None
plan = {
    "duration_days": 3,
    "route_preview": {
        "coords": [[45.0, 5.0], [45.01, 5.01], [45.02, 5.02]],
    },
    "stages": [{"day": n} for n in range(1, 4)],
}
assert "LINESTRING(5.000000 45.000000," in cache._route_wkt(plan)
assert cache._route_wkt({"route_preview": {"coords": [[999, 9]]}}) is None


class FakeResult:
    def __init__(self, values):
        self.values = values
    def mappings(self):
        return self
    def all(self):
        return self.values


class FakeDatabase:
    def __init__(self):
        self.calls = []
        self.closed = False
        self.committed = False
        self.rolled_back = False
        self.read_rows = [dict(row(900001), water_status="unverified", osm_tags={}),
                          dict(row(900002, "water"), water_status="potable_referenced", osm_tags={}),
                          dict(row(900003, "camping"), water_status="unverified", osm_tags={})]
    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if "SELECT" in sql:
            assert "last_seen >= NOW() - INTERVAL '10 days'" in sql, sql
            assert "ST_DWithin(location" in sql, sql
            assert "LIMIT :max_rows" in sql, sql
            assert params["max_rows"] <= 700, params
            return FakeResult(self.read_rows)
        if "INSERT" in sql:
            assert "ON CONFLICT" in sql and "last_seen = NOW()" in sql, sql
            assert all(r["source_url"].startswith("https://www.openstreetmap.org/") for r in params)
        return FakeResult([])
    def commit(self):
        self.committed = True
    def rollback(self):
        self.rolled_back = True
    def close(self):
        self.closed = True


instances = []
def session():
    instance = FakeDatabase()
    instances.append(instance)
    return instance

original_session = database.SessionLocal
database.SessionLocal = session
try:
    status = {}
    # Only food and water are requested, so cached lodging is not directly
    # queried (the fake database intentionally returns it to verify filtering
    # remains subject to outer route and kind validation).
    pts = cache.read_near_route(
        plan, {"food": True, "water": True, "sleep": True}, status,
    )
    assert status["status"] == "hit" and status["count"] == 3, status
    assert len(pts) == 3 and all(p["_cached_osm"] for p in pts), pts
    assert instances[-1].closed
    assert instances[-1].calls[-1][1]["categories"] == [
        "food", "water", "camping", "refuge", "lodging"
    ]

    write_status = {}
    count = cache.store_sourced([
        row(900004), row(900004),
        {**row(900005, "water"), "water_status": "not_potable"},
        {**row(900006), "_cached_osm": True},
        {**row(900007), "source_url": "https://irrelevant.example/poi"},
        {**row(900008), "osm_tags": {"disused": "yes"}},
    ], write_status)
    assert count == 2 and write_status == {"stored": 2, "status": "stored"}, write_status
    assert instances[-1].committed and instances[-1].closed, instances[-1]
    assert len(instances[-1].calls[-1][1]) == 2, instances[-1].calls

    count_before = len(instances)
    assert cache.store_sourced([], {}) == 0
    assert len(instances) == count_before, "Empty data must not hit Postgres"
    os.environ["TREKBRAIN_OSM_CACHE"] = "0"
    assert cache.read_near_route(plan, {"food": True}) == []
    assert cache.store_sourced([row(900009)]) == 0
    assert len(instances) == count_before
    os.environ.pop("TREKBRAIN_OSM_CACHE")

    class UnavailableSession:
        def __call__(self):
            raise RuntimeError("PostgreSQL temporarily unavailable")
    database.SessionLocal = UnavailableSession()
    offline = {}
    assert cache.read_near_route(plan, {"food": True}, offline) == []
    assert offline["status"] == "unavailable", offline
    offline_write = {}
    assert cache.store_sourced([row(900010)], offline_write) == 0
    assert offline_write["status"] == "unavailable", offline_write
finally:
    database.SessionLocal = original_session
    os.environ.pop("TREKBRAIN_OSM_CACHE", None)

# Partial food evidence must NOT satisfy the entire multi-day itinerary.
cached_partial = {
    **plan,
    "food": [dict(row(900001), lat=45.001, lon=5.001)],
}
assert resources._missing_terrain_intent(
    cached_partial, {"food": True, "water": False}
)["food"] is True
resolved = {
    **plan,
    "food": [
        dict(row(900101), lat=45.003, lon=5.003),
        dict(row(900102), lat=45.013, lon=5.013),
        dict(row(900103), lat=45.019, lon=5.019),
    ],
}
assert resources._missing_terrain_intent(
    resolved, {"food": True, "water": False}
)["food"] is False

partial_map = {
    "stages": [{"day": 1}, {"day": 2}],
    "map_resources": {"points": [{
        "kind": "food", "route_day": 1, "name": "Épicerie du départ",
    }], "coverage": {"food": "partial", "days_without_food": [2]}}
}
resources._annotate_stage_resources(partial_map)
assert partial_map["stages"][0]["food_notes"] == "Épicerie du départ"
assert "Aucun commerce vérifié" in partial_map["stages"][1]["food_notes"]
water_gap = {
    "stages": [{"day": 1}, {"day": 2}],
    "map_resources": {"points": [{
        "kind": "water", "route_day": 1, "name": "Fontaine du départ",
        "status": "potable_referenced",
    }], "coverage": {"water": "partial", "days_without_water": [2]}}
}
resources._annotate_stage_resources(water_gap)
assert "Fontaine du départ" in water_gap["stages"][0]["water_notes"]
assert "Aucun point d'eau OSM confirmé" in water_gap["stages"][1]["water_notes"]
print("TrekBrain v9 positive-only OSM cache, source-linked water/stays and daily food/water gaps: PASS")
