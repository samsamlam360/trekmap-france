"""Offline regressions for GR corridor guidance."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_gr_v9 as gr


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

# Synthetic 4-day loop with three campsites distributed along one hiking route.
trail = {
    "id": 223,
    "name": "Tour test",
    "ref": "GR 223",
    "network": "nwn",
    "coords": [
        [48.60, -1.60],
        [48.60, -1.32],
        [48.78, -1.32],
        [48.78, -1.60],
        [48.60, -1.60],
    ],
    "length_km": 80.0,
    "source_url": "https://www.openstreetmap.org/relation/223",
    "confidence": "high-route-evidence",
}

gclass = type("Candidate", (), {"__init__": lambda self, boundaries, strategy, heuristic: (setattr(self, "boundaries", boundaries), setattr(self, "strategy", strategy), setattr(self, "heuristic", heuristic), None)[-1]})
class FakeV3:
    Candidate = gclass

start = {"name": "Départ", "lat": 48.60, "lon": -1.60, "category": "village", "source_url": "start"}
end = start
camps = [
    {"name": "Camping 1", "lat": 48.60, "lon": -1.32, "category": "camping", "source_url": "c1"},
    {"name": "Camping 2", "lat": 48.78, "lon": -1.32, "category": "camping", "source_url": "c2"},
    {"name": "Camping 3", "lat": 48.78, "lon": -1.60, "category": "camping", "source_url": "c3"},
]
intent = {
    "days": 4,
    "daily_target": 20.0,
    "daily_max": 28.0,
    "accommodation": "camping",
}

token = gr._ACTIVE_TRAILS.set([trail])
try:
    candidates = gr.gr_candidates(FakeV3, start, end, camps, intent, "logistics")
    assert candidates, "A GR corridor with three usable campsites should create a 4-day hypothesis"
    best = candidates[0]
    assert len(best.boundaries) == 5, best.boundaries
    assert all(point.get("category") == "camping" for point in best.boundaries[1:-1]), best.boundaries
    assert best.strategy.endswith("-gr"), best.strategy
finally:
    gr._ACTIVE_TRAILS.reset(token)

print("TrekBrain GR corridor tests: OK")
