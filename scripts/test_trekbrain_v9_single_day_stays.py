"""Prevent unnecessary external lodging calls on a single-day itinerary.

No network access, no database writes, no fake field results promoted to production.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import trekbrain_route_logistics_v9 as logistics

def unexpected_provider(*args, **kwargs):
    raise AssertionError("No overnight on a one-day hike: external provider must not be queried")

originals = {name: getattr(logistics, name) for name in (
    "_bbox_route_stays", "_nominatim_route_stays", "_photon_split_stays",
)}
try:
    for name in originals:
        setattr(logistics, name, unexpected_provider)
    for category in ("camping", "refuge", "lodging"):
        chosen, discovered, meta = logistics._discover_stays(
            object(), object(), object(),
            [[45.0, 5.0], [45.01, 5.01]],
            {"name": "Départ", "lat": 45.0, "lon": 5.0},
            category, 1, 12.0, False, want_terrain=False,
        )
        assert chosen == [] and discovered == []
        assert meta["elapsed_ms"] == 0
        assert meta["terrain_rows"] == []
finally:
    for name, original in originals.items():
        setattr(logistics, name, original)
print("Single-day TrekBrain: zero unnecessary overnight-provider requests PASS")
