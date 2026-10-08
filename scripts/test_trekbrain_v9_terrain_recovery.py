"""Regression for partial terrain bundles, Overpass fallback and final retry latency."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as free
from backend import trekbrain_resources_v9 as resources

route = {
    "route_preview": {"coords": [[48.000, 2.000], [48.010, 2.010]], "fallback": False},
    "water": [],
    "resources": [
        {"category": "food", "name": "Commerce", "lat": 48.005, "lon": 2.005}
    ],
}
missing = resources._missing_terrain_intent(route, {"water": True, "food": True})
assert missing["water"] is True and missing["food"] is False, missing
assert resources._missing_terrain_intent(
    {**route, "water": [{"lat": 48.005, "lon": 2.005}]},
    {"water": True, "food": True},
) == {"water": False, "food": False}, "A complete terrain preload is reusable"

original_json = free._request_json
attempts = []
def mock_overpass(url, **kwargs):
    attempts.append((url, kwargs))
    if len(attempts) == 1:
        raise RuntimeError("Overpass temporarily unavailable")
    return {"elements": [{
        "id": 11223344, "type": "node",
        "lat": 48.005, "lon": 2.005,
        "tags": {"amenity": "drinking_water", "name": "Fontaine contrôlée"},
    }]}
free._request_json = mock_overpass
try:
    rows = resources._bbox_route_water_food(route, missing)
finally:
    free._request_json = original_json
assert len(attempts) == 2, attempts
assert attempts[0][0] != attempts[1][0], attempts
assert attempts[1][1]["timeout"] <= 0.9, attempts
assert all(a["cache_empty"] is False for _, a in attempts), attempts
assert len(rows) == 1 and rows[0]["category"] == "water", rows
assert rows[0]["water_status"] == "potable_referenced", rows
assert rows[0]["source_url"].endswith("/11223344"), rows

# A terminal HTTP 429 is not a retry. The client must not sleep for 400 ms
# after the *last* attempt, especially when Photon/IGN is the next fallback.
class LimitResponse:
    status_code = 429
    ok = False

original_get = free.requests.get
original_sleep = free.time.sleep
sleeps = []
free.requests.get = lambda *a, **kw: LimitResponse()
free.time.sleep = lambda duration: sleeps.append(duration)
try:
    try:
        free._request_json(
            "https://geocode-test.invalid/429-terminal-no-wait",
            service="Nominatim test",
            retries=1,
        )
    except RuntimeError as exc:
        assert "429" in str(exc), exc
    else:
        raise AssertionError("Expected HTTP 429")
finally:
    free.requests.get = original_get
    free.time.sleep = original_sleep
assert sleeps == [], sleeps
print("TrekBrain targeted terrain fallback and fast 429 terminal failures: PASS")
