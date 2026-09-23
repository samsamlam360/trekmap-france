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
        return {
            "name": "Tour de Belle-Île-en-Mer par le GR 340",
            "route_type": "Boucle",
            "route_preview": {
                "coords": [[47.33, -3.18], [47.38, -3.20], [47.33, -3.18]],
                "fallback": False,
                "relation_ref": "GR 340",
            },
            "stages": [{"day": i + 1, "distance_km": 18} for i in range(data.days)],
            "planner": {},
        }


DUMMY = object()


def install(v3):
    pipeline._INSTALLED = False
    pipeline.install_planning_pipeline(
        v3,
        DUMMY, DUMMY, DUMMY, DUMMY, DUMMY, DUMMY, DUMMY,
        FakeLogistics, FakeGuard, FakeCanonical,
    )


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
FakeLogistics.crash = False
install(v3)
result = v3._build(Data("boucle Belle-Île camping", region="Belle-Île-en-Mer", days=5, daily_km=18, accommodation="camping"), DUMMY)
assert result["route_preview"]["relation_ref"] == "GR 340"
assert result["logistics"]["mode"] == "route-first"
assert FakeCanonical.calls[-1][2] is False, FakeCanonical.calls
assert not v3.calls
assert "logistics" in result["planner"]["pipeline_phases"]

# 3. Generic loop with camping: generic route built once with lodging removed.
v3 = FakeV3()
FakeCanonical.calls.clear()
install(v3)
result = v3._build(Data("boucle générique camping", region="Chartres", accommodation="camping"), DUMMY)
assert len(v3.calls) == 1, v3.calls
assert v3.calls[0][2] is False
assert result["logistics"]["route_immutable"] is True
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
