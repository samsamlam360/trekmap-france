"""Overpass circuit breaker must save time under outages and self-recover."""
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as free
from backend import trekbrain_resources_v9 as terrain

route = {
    "duration_days": 2,
    "route_preview": {"coords": [[45.0, 5.0], [45.01, 5.01],
                                   [45.02, 5.02]]},
}
original = free._request_json
terrain._OSM_OVERPASS_FAILURES = 0
terrain._OSM_OVERPASS_COOLDOWN_UNTIL = 0.0

calls = []
def blocked(url, **kwargs):
    calls.append(url)
    raise RuntimeError("HTTP 429 public Overpass refused")

try:
    free._request_json = blocked
    for _ in range(2):
        result = {}
        assert terrain._bbox_route_water_food(
            route, {"food": True, "water": True}, result,
        ) == []
        assert result["status"] == "unavailable", result
        assert result["attempts"] == 2, result
    assert len(calls) == 4, calls
    assert terrain._OSM_OVERPASS_FAILURES == 2
    assert terrain._OSM_OVERPASS_COOLDOWN_UNTIL > time.monotonic()

    # Third plan during provider outage must NOT hammer the same public APIs.
    stats = {}
    assert terrain._bbox_route_water_food(
        route, {"food": True, "water": True}, stats,
    ) == []
    assert stats["status"] == "unavailable" and stats["attempts"] == 0, stats
    assert "circuit_open" in stats["errors"], stats
    assert len(calls) == 4, calls

    # A later request retries after the cooldown. The first good response
    # resets the breaker even when the dataset is empty; empty is not outage.
    terrain._OSM_OVERPASS_COOLDOWN_UNTIL = 0.0
    def empty_but_healthy(url, **kwargs):
        calls.append(url)
        return {"elements": []}
    free._request_json = empty_but_healthy
    empty_status = {}
    assert terrain._bbox_route_water_food(
        route, {"food": True, "water": False}, empty_status,
    ) == []
    assert empty_status["status"] == "empty", empty_status
    assert terrain._OSM_OVERPASS_FAILURES == 0
    assert terrain._OSM_OVERPASS_COOLDOWN_UNTIL == 0.0

    def recovered(url, **kwargs):
        calls.append(url)
        return {"elements": [{
            "type": "node", "id": 901234,
            "lat": 45.01, "lon": 5.01,
            "tags": {"shop": "convenience", "name": "Épicerie du col"},
        }]}
    free._request_json = recovered
    status = {}
    items = terrain._bbox_route_water_food(
        route, {"food": True, "water": False}, status,
    )
    assert status["status"] == "found" and len(items) == 1, (status, items)
    assert items[0]["source_url"].endswith("/901234"), items
finally:
    free._request_json = original
    terrain._OSM_OVERPASS_FAILURES = 0
    terrain._OSM_OVERPASS_COOLDOWN_UNTIL = 0.0

print("TrekBrain v9 Overpass outage cooldown, healthy-empty response, automatic recovery: PASS")
