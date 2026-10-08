"""Regression tests for the explicit TrekBrain v9 route/logistics pipeline."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_pipeline_core_v9 as pipeline


class Data:
    def __init__(self, prompt, region="Zone", days=4, daily_km=20, accommodation=None):
        self.prompt = prompt
        self.region = region
        self.days = days
        self.daily_km = daily_km
        self.route_type = "Boucle" if "boucle" in prompt.casefold() or "belle" in prompt.casefold() else "Traversée"
        self.require_accommodation = accommodation is not None
        self.accommodation = accommodation

    def model_copy(self, update=None):
        clone = Data(self.prompt, self.region, self.days, self.daily_km, self.accommodation)
        for key, value in (update or {}).items():
            setattr(clone, key, value)
        return clone


class FakeV3:
    def __init__(self):
        self.calls = []
        self._build = self.base_build

    def _parse_intent(self, data):
        return {
            "days": data.days,
            "daily_target": data.daily_km,
            "daily_min": data.daily_km * 0.75,
            "daily_max": data.daily_km * 1.25,
            "route_type": data.route_type,
            "accommodation": data.accommodation or "balanced",
        }

    def base_build(self, data, legacy):
        self.calls.append(("generic", data.prompt, data.require_accommodation))
        return {
            "name": "Generic route",
            "route_type": data.route_type,
            "route_preview": {"coords": [[48.0, 1.0], [48.1, 1.1]], "fallback": False},
            "stages": [{"day": i + 1, "distance_km": data.daily_km} for i in range(data.days)],
            "planner": {},
        }


class FakeLogistics:
    crash = False

    @staticmethod
    def _requested_category(intent):
        value = intent.get("accommodation")
        return value if value in {"camping", "refuge"} else None

    @staticmethod
    def _clone_route_only(data):
        clone = data.model_copy(update={"require_accommodation": False, "accommodation": None})
        clone.prompt = clone.prompt.replace("camping", "nuitée")
        return clone

    @staticmethod
    def _attach_logistics(result, data, legacy, v3, roundtrip, stay_rescue, ors, intent, category):
        if FakeLogistics.crash:
            raise RuntimeError("camping provider exploded")
        result["logistics"] = {
            "mode": "route-first",
            "category": category,
            "route_immutable": True,
            "nights_required": max(0, data.days - 1),
            "preloaded_accommodations": len(result.get("accommodations") or []),
        }
        result.setdefault("planner", {})["lodging_does_not_shape_route"] = True
        return result


class FakeGuard:
    @staticmethod
    def _mark_degraded(result, data, v3, category, exc):
        result["logistics"] = {
            "mode": "route-first",
            "category": category,
            "status": "degraded",
            "route_immutable": True,
            "error_code": "TB-LOGISTICS-DEGRADED",
        }
        return result


class FakeCanonical:
    calls = []

    @staticmethod
    def _build_canonical(data, legacy, v3, gr, rescue, roundtrip, stitch, ors, belle):
        FakeCanonical.calls.append((data.region, data.prompt, data.require_accommodation))
        if "belle" not in (data.region + " " + data.prompt).casefold():
            return None
        coords = [
            [47.33, -3.18], [47.38, -3.10], [47.36, -3.02],
            [47.27, -3.03], [47.24, -3.18], [47.33, -3.18],
        ]
        return {
            "name": "Tour de Belle-Île-en-Mer par le GR 340",
            "route_type": "Boucle",
            "canonical_route": True,
            "start": {"name": "Départ GR 340", "lat": coords[0][0], "lon": coords[0][1]},
            "route_preview": {
                "coords": coords,
                "fallback": False,
                "relation_ref": "GR 340",
            },
            "stages": [{"day": i + 1, "distance_km": 18} for i in range(data.days)],
            "planner": {},
        }

    @staticmethod
    def _project_stays(roundtrip, coords, rows, category):
        projected = []
        for index, row in enumerate(rows):
            item = dict(row)
            item["category"] = category
            item["_route_index"] = min(index + 1, len(coords) - 2)
            item["_route_progress_km"] = float((index + 1) * 18)
            item["_offroute_km"] = 0.5
            projected.append(item)
        return projected

    @staticmethod
    def _choose_ordered_stays(roundtrip, coords, stays, days, daily_target, daily_min, daily_max):
        return [dict(row) for row in stays[: max(0, int(days) - 1)]]


class FakeStayRescue:
    calls = []

    @staticmethod
    def _direct_stays(start, category, radius):
        FakeStayRescue.calls.append(("overpass", category, radius))
        return [
            {
                "name": f"Camping canonique {i}",
                "lat": 47.30 + i * 0.01,
                "lon": -3.20 + i * 0.02,
                "category": category,
                "source_url": f"osm://canonical/{i}",
            }
            for i in range(1, 5)
        ]

    @staticmethod
    def _photon_stays(*args, **kwargs):
        FakeStayRescue.calls.append(("photon",))
        raise AssertionError("canonical direct stays should already resolve every night")

    @staticmethod
    def _nominatim_stays(*args, **kwargs):
        FakeStayRescue.calls.append(("nominatim",))
        raise AssertionError("canonical direct stays should already resolve every night")


DUMMY = object()


def install(v3):
    pipeline._INSTALLED = False
    pipeline.install_planning_pipeline(
        v3,
        DUMMY, DUMMY, DUMMY, DUMMY, DUMMY, DUMMY, FakeStayRescue,
        FakeLogistics, FakeGuard, FakeCanonical,
    )


# The direct-loop shortcut is intentionally narrow. It must help common short
# generic loops without stealing named hiking relations or long itineraries from
# the advanced planner.
assert pipeline._fast_generic_loop_allowed({
    "route_type": "Boucle", "days": 3, "total_target": 51.0,
    "start_query": "", "end_query": "", "via_query": "",
    "max_dplus_day": None, "avoid": set(),
    "raw": "boucle dans le massif du Sancy avec de beaux paysages",
}) is True
assert pipeline._fast_generic_loop_allowed({
    "route_type": "Boucle", "days": 3, "total_target": 51.0,
    "start_query": "", "end_query": "", "via_query": "",
    "max_dplus_day": None, "avoid": set(),
    "raw": "boucle en suivant le GR 30",
}) is False
assert pipeline._fast_generic_loop_allowed({
    "route_type": "Boucle", "days": 5, "total_target": 90.0,
    "start_query": "", "end_query": "", "via_query": "",
    "max_dplus_day": None, "avoid": set(),
    "raw": "grande boucle cinq jours",
}) is False

# 1. Belle-Île without lodging: canonical route, no generic planner.
v3 = FakeV3()
FakeCanonical.calls.clear()
install(v3)
result = v3._build(Data("boucle Belle-Île 5 jours", region="Belle-Île-en-Mer", days=5, daily_km=18), DUMMY)
assert result["route_preview"]["relation_ref"] == "GR 340"
assert not v3.calls, v3.calls
assert result["planner"]["pipeline_phases"] == ["understand", "route", "route:canonical-gr340", "finalize"]

# 2. Belle-Île with camping: canonical route receives route-only input, then lodging.
v3 = FakeV3()
FakeCanonical.calls.clear()
FakeStayRescue.calls.clear()
FakeLogistics.crash = False
install(v3)
result = v3._build(Data("boucle Belle-Île camping", region="Belle-Île-en-Mer", days=5, daily_km=18, accommodation="camping"), DUMMY)
assert result["route_preview"]["relation_ref"] == "GR 340"
assert result["logistics"]["mode"] == "route-first"
assert FakeCanonical.calls[-1][2] is False, FakeCanonical.calls
assert not v3.calls
assert result["logistics"]["preloaded_accommodations"] == 4, result["logistics"]
assert result["planner"]["canonical_stays_preloaded"] == 4, result["planner"]
assert FakeStayRescue.calls == [("overpass", "camping", 30.0)], FakeStayRescue.calls
assert result["planner"]["pipeline_phases"] == [
    "understand", "route", "route:canonical-gr340",
    "logistics:canonical-preload", "logistics", "finalize",
]

# 3. Generic loop with camping: generic route built once with lodging removed.
v3 = FakeV3()
FakeCanonical.calls.clear()
FakeStayRescue.calls.clear()
install(v3)
result = v3._build(Data("boucle générique camping", region="Chartres", accommodation="camping"), DUMMY)
assert len(v3.calls) == 1, v3.calls
assert v3.calls[0][2] is False
assert result["logistics"]["route_immutable"] is True
assert FakeStayRescue.calls == [], FakeStayRescue.calls
assert result["planner"]["pipeline_phases"][:3] == ["understand", "route", "route:generic"]

# 4. Generic traverse without lodging is left to the existing generic stack.
v3 = FakeV3()
FakeCanonical.calls.clear()
install(v3)
result = v3._build(Data("traversée générique", region="Tours", days=3, daily_km=18), DUMMY)
assert len(v3.calls) == 1
assert result["route_type"] == "Traversée"
assert "logistics" not in result

# 5. Lodging crash cannot destroy an already built route and does not recalculate it.
v3 = FakeV3()
FakeCanonical.calls.clear()
FakeLogistics.crash = True
install(v3)
result = v3._build(Data("boucle générique camping", region="Chartres", accommodation="camping"), DUMMY)
FakeLogistics.crash = False
assert len(v3.calls) == 1, "valid pedestrian route must not be recalculated after lodging crash"
assert result["logistics"]["status"] == "degraded"
assert result["logistics"]["error_code"] == "TB-LOGISTICS-DEGRADED"
assert result["route_preview"]["fallback"] is False
assert "logistics:degraded" in result["planner"]["pipeline_phases"]

print("Explicit TrekBrain route/logistics pipeline: OK")
