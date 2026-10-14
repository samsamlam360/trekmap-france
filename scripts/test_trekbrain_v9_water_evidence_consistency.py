"""Cross-provider water safety contract, fully offline.

Run the same OSM contradictory tags through:
- the route-first lodging/terrain bundle;
- the post-route full-corridor Overpass scanner;
- the independent display-only water scanner.
All must agree, and even 'potable_referenced' is not proof of potability.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.trekbrain_water_evidence_v9 import potability_status
from backend import trekbrain_water_discovery_v9 as water
from backend import trekbrain_resources_v9 as resources
from backend import trekbrain_route_logistics_v9 as logistics
from backend import free_planner_v2 as free

tag_cases = [
    ({"amenity": "drinking_water", "drinking_water": "no"}, "not_potable"),
    ({"amenity": "drinking_water", "potable": "no"}, "not_potable"),
    ({"amenity": "drinking_water", "water:potable": "no"}, "not_potable"),
    ({"amenity": "drinking_water", "water:potable": "NO"}, "not_potable"),
    ({"amenity": "drinking_water", "drinking_water": "yes", "potable": "no"}, "not_potable"),
    ({"natural": "spring", "drinking_water": "no"}, "not_potable"),
    ({"natural": "spring", "water:potable": "yes"}, "potable_referenced"),
    ({"natural": "spring"}, "unverified"),
    ({"man_made": "water_tap"}, "unverified"),
    ({"man_made": "water_tap", "potable": "yes"}, "potable_referenced"),
    ({"amenity": "drinking_water", "drinking_water": "yes"}, "potable_referenced"),
]
for tags, expected in tag_cases:
    assert potability_status(tags) == expected, (tags, expected)
assert potability_status({}) == "unverified"
assert potability_status(None) == "unverified"

elements = [
    {"type": "node", "id": 923100 + i,
     "lat": 45.001 + i * 0.0001, "lon": 5.001,
     "tags": tags}
    for i, (tags, _expected) in enumerate(tag_cases)
]
expected_by_source = {
    str(el["id"]): expected
    for el, (_tags, expected) in zip(elements, tag_cases)
}
# The route-first OSM parser works independently of HTTP.
for element in elements:
    parsed = logistics._terrain_resource(element)
    assert parsed and parsed["category"] == "water", element
    assert parsed["water_status"] == expected_by_source[str(element["id"])], parsed

real_request = free._request_json
calls = []
def fake_provider(url, **kwargs):
    calls.append((url, kwargs))
    return {"elements": elements}

free._request_json = fake_provider
try:
    plan = {
        "duration_days": 2,
        "route_preview": {"coords": [[45.0, 5.0], [45.02, 5.02]], "fallback": False},
        "stages": [{"day": 1, "distance_km": 1.4}, {"day": 2, "distance_km": 1.4}],
    }
    # The geographical resource layer filters by distance to the route.
    bbox_rows = resources._bbox_route_water_food(
        plan, {"water": True, "food": False}
    )
    assert len(calls) == 2, "Incomplete daily coverage may try the second bounded mirror"
    assert len(bbox_rows) == len(tag_cases), (len(bbox_rows), bbox_rows)
    actual_bbox = {
        row["source_url"].rsplit("/", 1)[-1]: row["water_status"]
        for row in bbox_rows
    }
    assert actual_bbox == expected_by_source, (actual_bbox, expected_by_source)

    calls.clear()
    shown = water.discover_water_points(None, plan)
    assert len(calls) == 1, calls
    assert len(shown) == len(tag_cases), (len(shown), shown)
    actual_display = {
        row["source_url"].rsplit("/", 1)[-1]: row["water_status"]
        for row in shown
    }
    assert actual_display == expected_by_source, (actual_display, expected_by_source)
    assert all(
        row["display_only"] is True for row in shown
    ), shown
    for row in shown:
        if row["status"] == "not_potable":
            assert "ne pas boire" in row["notes"], row
        else:
            assert "vérifier" in row["notes"] or "potabilité inconnue" in row["notes"], row

    # An unavailable primary terrain search gets exactly one bounded attempt
    # on the already configured third, independent free Overpass endpoint.
    calls.clear()
    recovered = water.discover_water_points(None, {
        **plan, "_water_rescue_mirror_index": 2,
    })
    assert len(calls) == 1 and calls[0][0] == free.OVERPASS_URLS[2], calls
    assert calls[0][1]["timeout"] <= 1.6 and calls[0][1]["retries"] == 1
    assert len(recovered) == len(tag_cases)
    assert recovered[0]["status"] == "not_potable", recovered[0]
finally:
    free._request_json = real_request

print("11 contradictory OSM water tags: three provider layers produce exactly the same statuses PASS")
print("No new request wave, explicit non-potable warnings and field-check caveats PASS")
