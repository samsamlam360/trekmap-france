"""Offline regressions for GR corridor and campsite-detour guidance."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_gr_v9 as gr
from backend import trekbrain_gr_detours_v9 as detours
from backend import smart_planner_v3 as v3
from backend import ors


assert gr._is_priority_relation({"route": "hiking", "ref": "GR 223"})
assert gr._is_priority_relation({"route": "hiking", "network": "nwn", "name": "Coastal walk"})
assert not gr._is_priority_relation({"route": "hiking", "network": "lwn", "name": "Promenade locale"})

members = [
    {"type": "way", "geometry": [{"lat": 48.60, "lon": -1.60}, {"lat": 48.60, "lon": -1.50}, {"lat": 48.60, "lon": -1.40}]},
    # Deliberately reversed: the reassembler must orient it correctly.
    {"type": "way", "geometry": [{"lat": 48.60, "lon": -1.20}, {"lat": 48.60, "lon": -1.30}, {"lat": 48.60, "lon": -1.40}]},
]
chain = gr._join_relation_members(members)
assert len(chain) >= 5, chain
assert abs(chain[0][1] + 1.60) < 1e-6, chain
assert abs(chain[-1][1] + 1.20) < 1e-6, chain


def sampled_edge(a, b, count=80):
    return [
        [a[0] + (b[0] - a[0]) * i / count, a[1] + (b[1] - a[1]) * i / count]
        for i in range(count)
    ]


# Synthetic ~80 km GR loop with dense geometry. Campsites are deliberately
# around 1.8-2.2 km off the GR, matching the real-world case reported on mobile.
p1 = [48.60, -1.60]
p2 = [48.60, -1.33]
p3 = [48.78, -1.33]
p4 = [48.78, -1.60]
coords = sampled_edge(p1, p2) + sampled_edge(p2, p3) + sampled_edge(p3, p4) + sampled_edge(p4, p1) + [p1]
trail = {
    "id": 223,
    "name": "Tour test",
    "ref": "GR 223",
    "network": "nwn",
    "coords": coords,
    "length_km": round(gr._path_length(coords), 1),
    "source_url": "https://www.openstreetmap.org/relation/223",
    "confidence": "high-route-evidence",
}

start = {"name": "Départ", "lat": p1[0], "lon": p1[1], "category": "village", "source_url": "start"}
end = start
camps = [
    # Roughly 2 km south/east/north of the corridor at each quarter.
    {"name": "Camping 1", "lat": 48.582, "lon": -1.330, "category": "camping", "source_url": "c1"},
    {"name": "Camping 2", "lat": 48.780, "lon": -1.303, "category": "camping", "source_url": "c2"},
    {"name": "Camping 3", "lat": 48.798, "lon": -1.600, "category": "camping", "source_url": "c3"},
]
village = {"name": "Village tentant mais interdit comme nuitée", "lat": 48.69, "lon": -1.60, "category": "village", "source_url": "v1"}
intent = {
    "days": 4,
    "daily_target": 20.0,
    "daily_min": 17.0,
    "daily_max": 23.0,
    "total_target": 80.0,
    "accommodation": "camping",
    "sleep": True,
    "route_type": "Boucle",
    "avoid": set(),
    "priorities": {},
    "max_dplus_day": None,
}

# Install the same layers as production.
gr.install_gr_guidance(v3)
detours.install_gr_detours(v3, gr)

token = gr._ACTIVE_TRAILS.set([trail])
try:
    # Explicit camping means campsites only: no silent village substitute.
    pool = v3._night_pool(camps + [village], intent)
    assert len(pool) == 3, pool
    assert all(point.get("category") == "camping" for point in pool), pool

    candidates = gr.gr_candidates(v3, start, end, camps + [village], intent, "logistics")
    assert candidates, "A GR corridor with three off-route campsites should create a 4-day hypothesis"
    valid = [c for c in candidates if len(c.boundaries) == 5 and all(p.get("category") == "camping" for p in c.boundaries[1:-1])]
    assert valid, [getattr(c, "boundaries", None) for c in candidates]
    assert any("gr-global" in c.strategy or "gr-detour" in c.strategy or c.strategy.endswith("-gr") for c in valid), [c.strategy for c in valid]
    # "Boucle" means the candidate closes on the exact departure object.
    assert all(c.boundaries[-1] is start for c in valid), [c.boundaries[-1] for c in valid]

    # The new optimiser chooses all nights at once and verifies every estimated
    # day before spending ORS requests. This prevents a locally attractive camp
    # from creating a 30 km final stage.
    cum = gr._cumulative(trail["coords"])
    rows = []
    for camp in camps:
        pos, off = gr._trail_position(camp, trail, cum)
        rows.append((camp, pos, off))
    global_solutions = []
    for direction in (1, -1):
        global_solutions += detours._global_loop_sequences(trail, start, rows, intent, gr, direction)
    assert global_solutions, "Global loop optimiser should find a feasible campsite sequence"
    best_global = min(global_solutions, key=lambda row: row[0])
    assert len(best_global[1]) == 3, best_global
    assert max(best_global[2]) <= intent["daily_max"] + 0.35, best_global
    assert max(best_global[2]) - min(best_global[2]) < 12.0, best_global

    # A campsite branch must explicitly insert a GR junction so routing follows
    # camp -> junction -> GR -> junction -> next camp rather than a generic chord.
    anchors = gr._anchors_for(camps[0], camps[1], intent, max_anchors=3)
    assert anchors, "Expected GR anchors between off-corridor campsites"
    assert any("jonction nuitée" in str(a.get("name")) for a in anchors), anchors
    assert all(a.get("gr_guidance") for a in anchors), anchors
finally:
    gr._ACTIVE_TRAILS.reset(token)


# ORS resilience regression: if one complex request fails, every consecutive
# walking leg is independently validated and merged. No straight-line route is
# ever marked as safe.
real_request = ors._request_route
real_key = ors.ORS_API_KEY
calls = []

def fake_request(points, distance_gps, snap_radius_m=None):
    calls.append((len(points), snap_radius_m))
    if len(points) > 2:
        return None, "complex waypoint request rejected", 400
    return {
        "coords": [list(points[0]), list(points[1])],
        "distance": 1.25,
        "fallback": False,
        "routing_mode": "ors",
    }, None, 200

ors._request_route = fake_request
ors.ORS_API_KEY = "test-key"
try:
    routed = ors.get_route([[48.60, -1.60], [48.61, -1.58], [48.62, -1.56]], lambda pts: 2.5)
    assert routed["fallback"] is False, routed
    assert routed["routing_mode"] == "ors-segmented", routed
    assert abs(routed["distance"] - 2.5) < 0.01, routed
    assert sum(1 for size, _ in calls if size == 2) == 2, calls
finally:
    ors._request_route = real_request
    ors.ORS_API_KEY = real_key

print("TrekBrain GR corridor + campsite detour tests: OK")


# Daily mileage is a hard constraint at final selection: a 30 km day must not
# survive when the request is around 20 km/day.
oversized = v3.Candidate([start, camps[0], camps[1], camps[2], start], "test", 0.0)
fake_route = {"coords": [[48.6, -1.6], [48.6, -1.4]], "distance": 80.0, "fallback": False}
real_stage = v3._stage_distances
v3._stage_distances = lambda *args, **kwargs: [18.0, 30.0, 17.0, 15.0]
try:
    score, *_ = v3._candidate_score(oversized, [start, camps[0], camps[1], camps[2], start], fake_route, intent, camps, type("L", (), {"distance_gps": staticmethod(lambda x: 80.0), "elevation_gain": staticmethod(lambda x: 0)})())
    assert score >= 1000, score
finally:
    v3._stage_distances = real_stage


# Retrace detector: a real rectangular loop should pass, while an exact
# out-and-back must be rejected even though both end at the start.
real_loop = trail["coords"]
out_leg = sampled_edge(p1, p2, 100) + sampled_edge(p2, p3, 100)
out_and_back = out_leg + list(reversed(out_leg))
assert v3._route_retrace_ratio(real_loop) < 0.32, v3._route_retrace_ratio(real_loop)
assert v3._route_retrace_ratio(out_and_back) > 0.32, v3._route_retrace_ratio(out_and_back)
print("Retrace detector: OK")
