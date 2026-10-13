"""Deterministic zero-network regression for cold mountainous loops.

The pedestrian router is simulated at the module boundary. No inferred road,
straight-line shortcut or candidate beyond the 2-attempt limit is ever accepted.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import ors
from backend import trekbrain_roundtrip_v9 as loop
from backend import trekbrain_perf_profile_v9 as perf

class FakeV3:
    @staticmethod
    def _route_retrace_ratio(coords):
        return 0.1

start = {"lat": 48.13, "lon": 7.10}
saved_route = ors.get_route
saved_mark = perf.mark
saved_sleep = __import__("time").sleep
observed = []
events = []
sleep_delays = []

def routed(coords, _gps):
    radius = loop._haversine(coords[0], coords[1])
    observed.append((radius, coords))
    # A mountain routing network can overshoot dramatically. The second,
    # smaller radius should then allow a distance within the requested window.
    km = 72.0 if len(observed) == 1 else 28.1
    return {
        "fallback": False, "secondary_router": True,
        "provider": "Valhalla/OpenStreetMap", "distance": km,
        "coords": [list(p) for p in coords], "routing_mode": "valhalla-pedestrian-fallback",
    }

try:
    ors.get_route = routed
    perf.mark = lambda name, **details: events.append((name, details))
    __import__("time").sleep = lambda seconds: sleep_delays.append(seconds)
    rows = loop._polygon_loop_candidates(
        start, 28.0, 10.5, 17.5, 2, FakeV3(), max_attempts=2,
    )
    assert len(observed) == 2, observed
    assert len(rows) == 2 and rows[0]["distance"] == 72 and rows[1]["distance"] == 28.1, rows
    assert observed[1][0] < observed[0][0] * 0.6, observed
    assert rows[1]["waypoint_orientation_deg"] == rows[0]["waypoint_orientation_deg"], rows
    assert [d["reason"] for _, d in events] == ["too_long", "feasible"], events
    assert all("lat" not in d and "lon" not in d for _,d in events)
    assert len(sleep_delays) == 1 and sleep_delays[0] >= 1.0

    # The first loop may be too short instead. Calibrate upwards but not beyond
    # the hard 18 km waypoint radius cap; still require network-proven geometry.
    observed.clear(); events.clear(); sleep_delays.clear()
    def short_first(coords, _gps):
        radius = loop._haversine(coords[0], coords[1])
        observed.append((radius, coords))
        km = 10 if len(observed) == 1 else 28
        return {"fallback": False, "distance": km, "coords": [list(p) for p in coords]}
    ors.get_route = short_first
    rows = loop._polygon_loop_candidates(start, 28, 10.5, 17.5, 2, FakeV3(), max_attempts=2)
    assert len(rows) == 2
    assert observed[1][0] > observed[0][0], observed
    assert [d["reason"] for _, d in events] == ["too_short", "feasible"], events

    # A 200 response that does not close the loop must not become an acceptable
    # hike even if the provider announces the perfect distance.
    observed.clear(); events.clear()
    def open_first(coords, _gps):
        observed.append(coords)
        if len(observed) == 1:
            return {"fallback": False, "distance": 28, "coords": [list(p) for p in coords[:-1]]}
        return {"fallback": True, "warning": "Network outage"}
    ors.get_route = open_first
    rows = loop._polygon_loop_candidates(start, 28, 10.5, 17.5, 2, FakeV3(), max_attempts=2)
    assert not rows and len(observed) == 2, (rows, observed)
    assert [d["reason"] for _, d in events] == ["open_loop", "router_unavailable"], events

    # Historical 4-orientation fallback is not silently altered by cold
    # fast-planner calibration.
    observed.clear(); events.clear()
    def no_routes(coords, _gps):
        observed.append(coords)
        return {"fallback": True}
    ors.get_route = no_routes
    rows = loop._polygon_loop_candidates(start, 28, 10.5, 17.5, 2, FakeV3())
    assert rows == [] and len(observed) == 4
    assert not sleep_delays[-4:] == [1.05] * 4
    assert [d["orientation"] for _,d in events] == [90,180,0,270], events
finally:
    ors.get_route = saved_route
    perf.mark = saved_mark
    __import__("time").sleep = saved_sleep

print("Polygon adaptation: large/small first loops, open geometry, quotas and legacy fan PASS")
