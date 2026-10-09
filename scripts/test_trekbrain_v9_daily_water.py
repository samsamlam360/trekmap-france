"""Unnamed water and first-visit daily gaps must survive provider failures."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import smart_planner_v3 as planner
from backend import trekbrain_resources_v9 as resources

plan = {"duration_days": 3, "stages": [{"day": d} for d in (1, 2, 3)],
        "route_preview": {"coords": [[45+i*.05, 5] for i in range(4)]}, "water": []}
def point(i):
    return {"lat": 45.025+i*.05, "lon": 5, "category": "water",
            "source_url": f"https://www.openstreetmap.org/node/{i+1}"}
for count in range(4):
    plan["water"] = [point(i) for i in range(count)]
    assert resources._missing_terrain_intent(plan, {"water": True})["water"] == (count < 3)
plan["water"] = [{**point(i), "source_url": ""} for i in range(3)]
assert resources._missing_terrain_intent(plan, {"water": True})["water"]
assert not resources._missing_terrain_intent(plan, {"water": False})["water"]

old = planner._request_json
calls = []
def reverse(url, **kwargs):
    calls.append((url, kwargs))
    assert url.endswith('/reverse') and 'q' not in kwargs['params']
    assert kwargs['params']['radius'] <= 5.5 and kwargs['cache_empty'] is False
    assert 'amenity:drinking_water' in kwargs['params']['osm_tag']
    return {"features": [{"properties": {"osm_type": "N", "osm_id": 222,
             "osm_key": "amenity", "osm_value": "drinking_water", "countrycode": "FR"},
             "geometry": {"coordinates": [5, 45.001]}}]}
planner._request_json = reverse
try:
    result = planner._photon_anchor_resource({"lat":45,"lon":5}, 'water',
        ('amenity:drinking_water','natural:spring','man_made:water_tap'),5.5)
    assert result and result['water_status'] == 'potable_referenced'
    assert result['source_url'].endswith('/222') and len(calls) == 1
    def unavailable(*args, **kwargs):
        raise RuntimeError('provider unavailable')
    planner._request_json = unavailable
    assert planner._photon_anchor_resource({'lat':45,'lon':5},'water',('amenity:drinking_water',),5.5) is None
finally:
    planner._request_json = old

old_lookup = planner._photon_anchor_resource
seen=[]
planner._photon_anchor_resource = lambda p, kind, tags, radius: seen.append((p,kind))
try:
    # One day still has water probes. A closed loop spends no duplicate slot.
    planner._postroute_corridor_resources([point(0),point(0)], {'water':True}, [])
    assert len(seen) == 1, seen
    seen.clear()
    bounds=[{'lat':45+i*.1,'lon':5} for i in range(9)]
    planner._postroute_corridor_resources(bounds, {'water':True,'food':True,'sleep':True,'transit':True}, [])
    assert len(seen) <= 6 and {'water','food','stay','transit'} <= {kind for _,kind in seen},seen
finally:
    planner._photon_anchor_resource = old_lookup
# Regression: preserve a real mapped source on the map without pretending
# drinking_water=no meets the overnight drinking-water requirement.
unsafe_plan = {
    "duration_days": 2,
    "stages": [{"day": 1}, {"day": 2}],
    "route_preview": {"coords": [[45.0, 5.0], [45.05, 5.0], [45.10, 5.0]]},
    "water": [
        {"name": "Fontaine potable", "lat": 45.02, "lon": 5.0,
         "water_status": "potable_referenced",
         "source_url": "https://www.openstreetmap.org/node/9101"},
        {"name": "Source à ne pas boire", "lat": 45.08, "lon": 5.0,
         "water_status": "not_potable",
         "source_url": "https://www.openstreetmap.org/node/9102"},
    ],
    "accommodations": [],
}
assert resources._missing_terrain_intent(
    unsafe_plan, {"water": True}
)["water"] is True
display = resources.enrich_resources(unsafe_plan)
water_map = [p for p in display["map_resources"]["points"] if p["kind"] == "water"]
assert len(water_map) == 2, water_map
assert resources._sourced_water_coverage(water_map) == ([1], 1), water_map
assert any(
    p["status"] == "not_potable" and "ne pas boire" in p["notes"]
    for p in water_map
), water_map
resources._annotate_stage_resources(display)
assert "Aucune eau potable" in display["stages"][1]["water_notes"], display["stages"]

# A newer non-potable OSM record must take precedence over a stale cached
# "potable" record at the same node, even when coordinates are identical.
stale_plan = {
    **unsafe_plan,
    "water": [{
        **unsafe_plan["water"][1],
        "water_status": "potable_referenced", "status": "potable_referenced",
        "notes": "Ancien état",
    }],
}
resources._merge_supplemented_resources(stale_plan, [unsafe_plan["water"][1] | {"category": "water"}])
assert len(stale_plan["water"]) == 1
assert stale_plan["water"][0]["status"] == "not_potable", stale_plan["water"]
assert "ne pas boire" in stale_plan["water"][0]["notes"]

# Route-first logistics preloads water before the final resource overlay.
# The same OSM source can already be present as "potable" from old data.
# New drinking_water=no evidence must NOT be discarded by coord dedup.
from backend import trekbrain_route_logistics_v9 as lodging
old_source = {
    "name": "Source du sentier", "lat": 45.08, "lon": 5.0,
    "water_status": "potable_referenced", "status": "potable_referenced",
    "source_url": "https://www.openstreetmap.org/node/9102",
    "notes": "Old potable",
}
preload_plan = {"water": [old_source], "resources": [], "points_of_interest": []}
unsafe_row = {
    "category": "water", "water_status": "not_potable",
    "lat": 45.08, "lon": 5.0,
    "source_url": "https://www.openstreetmap.org/node/9102",
}
lodging._attach_preloaded_terrain(preload_plan, [unsafe_row], True)
assert len(preload_plan["water"]) == 1, preload_plan["water"]
assert preload_plan["water"][0]["status"] == "not_potable", preload_plan
assert "ne pas boire" in preload_plan["water"][0]["notes"], preload_plan

# OSM geometry may move by a few metres between observations while the
# OSM source ID stays unchanged; identity must beat rounded coordinates.
shifted_old = {**old_source, "lat": 45.0798, "status": "potable_referenced"}
shifted_plan = {"water": [shifted_old], "resources": [], "points_of_interest": []}
lodging._attach_preloaded_terrain(shifted_plan, [unsafe_row], True)
assert len(shifted_plan["water"]) == 1, shifted_plan["water"]
assert shifted_plan["water"][0]["status"] == "not_potable", shifted_plan

fresh_plan = {"water": [], "resources": [], "points_of_interest": []}
lodging._attach_preloaded_terrain(fresh_plan, [unsafe_row], True)
assert fresh_plan["water"][0]["status"] == "not_potable", fresh_plan
assert "ne pas boire" in fresh_plan["water"][0]["notes"], fresh_plan

# The exact source identity guards against mistakenly marking a distinct
# source at the same coordinate as non-potable.
other_source = {
    **old_source, "source_url": "https://www.openstreetmap.org/node/9999",
}
different_plan = {"water": [other_source], "resources": [], "points_of_interest": []}
lodging._attach_preloaded_terrain(different_plan, [unsafe_row], True)
assert different_plan["water"][0]["status"] == "potable_referenced", different_plan
# Every other discovery endpoint continues to use its old bounded query;
# this test does not open any network connection.
# A real OSM object can carry contradictory tags. The explicit water safety
# label always wins over the generic amenity=drinking_water hint, at both
# route-first discovery and the shared v3 Overpass parser.
conflicting = {
    "type": "node", "id": 990011, "lat": 45.04, "lon": 5.0,
    "tags": {"amenity": "drinking_water", "drinking_water": "no", "name": "Fontaine condamnée"},
}
safe = {
    "type": "node", "id": 990012, "lat": 45.06, "lon": 5.0,
    "tags": {"amenity": "drinking_water", "drinking_water": "yes"},
}
unknown = {
    "type": "node", "id": 990013, "lat": 45.08, "lon": 5.0,
    "tags": {"natural": "spring"},
}
assert lodging._terrain_resource(conflicting)["water_status"] == "not_potable"
assert lodging._terrain_resource(safe)["water_status"] == "potable_referenced"
assert lodging._terrain_resource(unknown)["water_status"] == "unverified"

real_overpass = planner._overpass
try:
    planner._overpass = lambda _query, **_kwargs: {
        "elements": [conflicting, safe, unknown]
    }
    checked, _extras, _notes = planner._combined_nearby(
        {"lat": 45.0, "lon": 5.0}, 5.0, ["water"]
    )
finally:
    planner._overpass = real_overpass
status_by_id = {x["source_url"].rsplit("/", 1)[-1]: x["water_status"] for x in checked}
assert status_by_id["990011"] == "not_potable", status_by_id
assert status_by_id["990012"] == "potable_referenced", status_by_id
assert status_by_id["990013"] == "unverified", status_by_id
print("Contradictory OSM water tags: explicit not-potable precedence: PASS")

print("Non-potable source isolation and stale-cache safety: PASS")

print('Daily water: partial/complete/unsourced, unnamed reverse search, outage, one-day and bounded wave: PASS')
