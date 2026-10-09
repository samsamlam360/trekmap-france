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
print('Daily water: partial/complete/unsourced, unnamed reverse search, outage, one-day and bounded wave: PASS')
