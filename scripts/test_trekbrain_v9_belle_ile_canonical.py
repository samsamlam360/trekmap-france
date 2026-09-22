"""Regressions for the canonical Belle-Ile GR 340 planner.

Checks both plain GR use and the production bug where normal POI lookup returns
zero campsites although accommodation-only discovery can find them on the island.
"""
from pathlib import Path
from types import SimpleNamespace
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_belle_ile_canonical_v9 as canonical
from backend import trekbrain_roundtrip_v9 as real_roundtrip
from backend import trekbrain_stays_rescue_v9 as stay_rescue


class FakeData:
    prompt = "Je veux faire le tour de Belle-Île en 5 jours"
    region = "Belle-Île-en-Mer"
    days = 5
    daily_km = 18
    difficulty = "medium"


class FakeV3:
    def __init__(self, daily, accommodation="balanced"):
        self.daily = daily
        self.accommodation = accommodation

    def _parse_intent(self, data):
        return {
            "route_type": "Boucle",
            "days": 5,
            "daily_target": float(self.daily),
            "daily_min": 13.5 if self.daily == 18 else 16.5,
            "daily_max": 22.5 if self.daily == 18 else 27.5,
            "total_target": float(self.daily) * 5,
            "accommodation": self.accommodation,
            "difficulty": "medium",
        }

    @staticmethod
    def _fold(value):
        return str(value).casefold()

    @staticmethod
    def _location(data):
        return "Belle-Île-en-Mer"

    @staticmethod
    def _geocode(query):
        return [{"name": "Belle-Île-en-Mer", "lat": 47.33, "lon": -3.18}]

    @staticmethod
    def _stage_distances(coords, boundaries, legacy, total):
        return [float(total) / 5.0] * 5

    @staticmethod
    def _nearby(*args, **kwargs):
        return []


class FakeBelle:
    @staticmethod
    def _is_belle_ile(point):
        return 47.20 <= float(point["lat"]) <= 47.44 and -3.40 <= float(point["lon"]) <= -2.95

    @staticmethod
    def _targeted_gr340(v3, gr, rescue, start, target_km):
        coords = synthetic_gr340()
        start["lat"], start["lon"] = coords[0]
        start["name"] = "Départ sur GR 340"
        start["category"] = "trail"
        return {
            "coords": coords,
            "distance": 90.0,
            "fallback": False,
            "routing_mode": "osm-hiking-relation-loop",
            "profile": "hiking-relation",
            "provider": "OpenStreetMap hiking relation",
            "relation_ref": "GR 340",
            "relation_name": "Tour de Belle-Île-en-Mer",
            "relation_source_url": "https://www.openstreetmap.org/relation/6850120",
            "relation_geometry": True,
        }, None


def synthetic_gr340():
    centre_lat, centre_lon = 47.31, -3.18
    radius_lat, radius_lon = 0.13, 0.19
    coords = []
    for i in range(101):
        angle = 2 * math.pi * i / 100
        coords.append([
            centre_lat + radius_lat * math.sin(angle),
            centre_lon + radius_lon * math.cos(angle),
        ])
    coords[-1] = list(coords[0])
    return coords


class FakeRoundtrip:
    @staticmethod
    def _equal_anchors(coords, days):
        indices = [20, 40, 60, 80]
        return [
            {"name": f"Repère jour {i+1}", "lat": coords[idx][0], "lon": coords[idx][1], "category": "route_anchor"}
            for i, idx in enumerate(indices)
        ]

    @staticmethod
    def _balanced_corridor_stays(*args, **kwargs):
        raise AssertionError("Legacy exact-endpoint camping search must not be used by canonical Belle-Ile")


class NoORS:
    @staticmethod
    def get_route(*args, **kwargs):
        raise AssertionError("Belle-Ile canonical route must not ask ORS to rebuild the full loop")


class FakeLegacy:
    @staticmethod
    def distance_gps(coords):
        return 1.0

    @staticmethod
    def elevation_gain(coords):
        return 600


for daily in (18, 22):
    data = FakeData()
    data.daily_km = daily
    result = canonical._build_canonical(
        data,
        FakeLegacy(),
        FakeV3(daily),
        object(),
        object(),
        FakeRoundtrip(),
        object(),
        NoORS(),
        FakeBelle(),
    )
    assert result["canonical_route"] is True
    assert result["route_type"] == "Boucle"
    assert result["route_preview"]["relation_ref"] == "GR 340"
    assert result["route_preview"]["fallback"] is False
    assert result["distance_km"] == 90.0
    assert len(result["stages"]) == 5

coords = synthetic_gr340()
camps = []
for n, idx in enumerate((20, 40, 60, 80), start=1):
    camps.append({
        "name": f"Camping test {n}",
        "lat": coords[idx][0],
        "lon": coords[idx][1],
        "category": "camping",
        "source_url": f"https://www.openstreetmap.org/node/{9000+n}",
    })

real_direct = stay_rescue._direct_stays
real_photon = stay_rescue._photon_stays
real_nominatim = stay_rescue._nominatim_stays
stay_rescue._direct_stays = lambda start, category, radius: [dict(x) for x in camps]
stay_rescue._photon_stays = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Photon should not be needed"))
stay_rescue._nominatim_stays = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Nominatim should not be needed"))
try:
    chosen, diag = canonical._discover_canonical_stays(
        FakeV3(18, "camping"),
        real_roundtrip,
        coords,
        {"name": "Départ GR 340", "lat": coords[0][0], "lon": coords[0][1], "category": "trail"},
        "camping",
        5,
        18.0,
        13.5,
        22.5,
    )
finally:
    stay_rescue._direct_stays = real_direct
    stay_rescue._photon_stays = real_photon
    stay_rescue._nominatim_stays = real_nominatim

assert diag["needed"] == 4, diag
assert diag["discovered"] == 4, diag
assert len(chosen) == 4, chosen
assert [x["name"] for x in chosen] == [f"Camping test {i}" for i in range(1, 5)]
assert all(float(x["_offroute_km"]) < 0.05 for x in chosen)

print("Belle-Ile canonical GR 340 + whole-corridor camping discovery: OK")
