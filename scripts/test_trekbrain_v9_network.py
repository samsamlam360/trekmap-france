"""Offline regressions for TrekBrain v9 multi-trail/path-network loop planning."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import smart_planner_v3 as v3
from backend import trekbrain_gr_v9 as gr
from backend import trekbrain_network_v9 as network

start = {"name": "Départ", "lat": 48.600, "lon": -1.600, "category": "place", "source_url": "start"}
center = dict(start)
# Roughly rectangular 4-day loop. Consecutive straight distances are around
# 16-18 km; the network estimator turns them into realistic ~19-22 km stages.
camps = [
    {"name": "Camping Est", "lat": 48.600, "lon": -1.380, "category": "camping", "source_url": "camp-east"},
    {"name": "Camping Nord-Est", "lat": 48.760, "lon": -1.380, "category": "camping", "source_url": "camp-ne"},
    {"name": "Camping Nord-Ouest", "lat": 48.760, "lon": -1.600, "category": "camping", "source_url": "camp-nw"},
]
intent = {
    "days": 4,
    "daily_target": 20.0,
    "daily_min": 17.0,
    "daily_max": 23.0,
    "total_target": 80.0,
    "route_type": "Boucle",
    "accommodation": "camping",
    "sleep": True,
}

# No closed GR relation at all: this is precisely the case the network layer
# must solve by letting ORS combine ordinary pedestrian ways and available
# hiking corridors later.
token = gr._ACTIVE_TRAILS.set([])
real_nearby = v3._nearby
v3._nearby = lambda *args, **kwargs: []
try:
    solutions = network._candidate_sequences(v3, gr, start, center, camps, intent)
    assert solutions, "A feasible rectangular campsite loop should be generated without a closed GR"
    best = solutions[0]
    assert len(best[1]) == 3, best
    assert max(best[2]) <= 26.0, best
    assert best[3] > 0.0022, best

    candidates = network.network_loop_candidates(v3, gr, start, center, camps, intent, "logistics")
    assert candidates, "Path-network layer should expose loop candidates to TrekBrain"
    assert all(c.boundaries[0] is start and c.boundaries[-1] is start for c in candidates), candidates
    assert any("path-network-loop" in c.strategy for c in candidates), [c.strategy for c in candidates]
finally:
    v3._nearby = real_nearby
    gr._ACTIVE_TRAILS.reset(token)

# Collinear campsites have almost no enclosed area and must not be advertised as
# a loop merely because the final point equals the start.
line_camps = [
    {"name": "A", "lat": 48.600, "lon": -1.450, "category": "camping", "source_url": "a"},
    {"name": "B", "lat": 48.600, "lon": -1.300, "category": "camping", "source_url": "b"},
    {"name": "C", "lat": 48.600, "lon": -1.150, "category": "camping", "source_url": "c"},
]
token = gr._ACTIVE_TRAILS.set([])
try:
    assert not network._candidate_sequences(v3, gr, start, center, line_camps, intent), "Out-and-back-shaped campsite sets must be rejected"
finally:
    gr._ACTIVE_TRAILS.reset(token)

# Shape metric itself should distinguish a rectangle from an out-and-back line.
rectangle = [start] + camps + [start]
line = [start] + line_camps + [start]
assert network._shape_ratio(rectangle) > 0.01, network._shape_ratio(rectangle)
assert network._shape_ratio(line) < 0.0022, network._shape_ratio(line)

print("TrekBrain multi-trail/path-network loop tests: OK")
