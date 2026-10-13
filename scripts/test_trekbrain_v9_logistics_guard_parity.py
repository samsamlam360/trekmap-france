"""Generic lodging must receive the same fail-open guard as camping/refuges."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import trekbrain_route_logistics_guard_v9 as guard
from backend import trekbrain_route_logistics_v9 as logistics

class FakeV3:
    @staticmethod
    def _parse_intent(data):
        return data

cases = (
    ({"accommodation": "camping", "sleep": True}, "camping"),
    ({"accommodation": "refuge", "sleep": True}, "refuge"),
    ({"accommodation": "balanced", "sleep": True}, "lodging"),
    ({"accommodation": "hotel", "sleep": True}, "lodging"),
    ({"accommodation": "bivouac", "sleep": True}, None),
    ({"accommodation": "balanced", "sleep": False}, None),
)
for intent, expected in cases:
    assert logistics._requested_category(intent) == expected, intent
    assert guard._requested_category(FakeV3(), intent) == expected, intent

route = {"route_preview": {"coords": [[45, 5], [45.01, 5.01]], "fallback": False}, "stages": [{"day": 1, "overnight": ""}, {"day": 2, "overnight": "Fin du trek"}]}
result = guard._mark_degraded(route, {"days": 2}, FakeV3(), "lodging", RuntimeError("provider timed out"))
assert result["route_preview"]["coords"] == [[45,5],[45.01,5.01]]
assert result["logistics"]["status"] == "degraded"
assert result["logistics"]["nights_required"] == 1
assert "Nuitée à organiser" in result["stages"][0]["overnight"]
print("Generic lodging/camping/refuge guard parity and unchanged safe route: PASS")
