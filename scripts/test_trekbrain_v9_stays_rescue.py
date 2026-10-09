"""Regressions for resilient accommodation discovery."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as free
from backend import trekbrain_stays_rescue_v9 as rescue


START = {"name": "Mont Saint-Michel", "lat": 48.636, "lon": -1.511, "category": "place"}


class V3:
    @staticmethod
    def _dist(a, b):
        return rescue._distance_km(a, b)


class Roundtrip:
    pass


class CampsiteLoop:
    @staticmethod
    def _diverse_stays(v3, roundtrip, start, category, days, daily_target):
        # Simulate the production failure: the normal broad POI lookup yielded
        # nothing, even though campings exist around the requested area.
        return []

    @staticmethod
    def _bearing(start, point):
        return rescue.math.atan2(float(point["lat"]) - float(start["lat"]), float(point["lon"]) - float(start["lon"]))


def overpass_success(url, **kwargs):
    query = (kwargs.get("data") or {}).get("data", "")
    assert 'tourism"="camp_site' in query
    assert "around:" not in query, "The rescue should use a cheaper bounding-box query"
    return {
        "elements": [
            {"type": "node", "id": 1, "lat": 48.66, "lon": -1.36, "tags": {"tourism": "camp_site", "name": "Camping A"}},
            {"type": "way", "id": 2, "center": {"lat": 48.78, "lon": -1.50}, "tags": {"tourism": "camp_site", "name": "Camping B"}},
            {"type": "node", "id": 3, "lat": 48.67, "lon": -1.69, "tags": {"tourism": "camp_site", "name": "Camping C"}},
            {"type": "node", "id": 4, "lat": 48.72, "lon": -1.58, "tags": {"tourism": "caravan_site", "name": "Camping D"}},
        ]
    }


old_request = free._request_json
free._request_json = overpass_success
try:
    rescue._INSTALLED = False
    rescue.install_stay_lookup_rescue(V3, CampsiteLoop, Roundtrip)
    rows = CampsiteLoop._diverse_stays(V3, Roundtrip, START, "camping", 4, 18.0)
finally:
    free._request_json = old_request

assert len(rows) >= 3, rows
assert {x["name"] for x in rows} >= {"Camping A", "Camping B", "Camping C"}
assert all(x["category"] == "camping" for x in rows)
assert all("_radial_km" in x and "_bearing" in x for x in rows)


# Second regression: every Overpass endpoint can fail and Photon must still
# provide enough candidate campings. ORS Matrix will validate walking access
# later, so this fallback is discovery, not blind route acceptance.
class CampsiteLoopPhoton:
    @staticmethod
    def _diverse_stays(v3, roundtrip, start, category, days, daily_target):
        return []

    @staticmethod
    def _bearing(start, point):
        return rescue.math.atan2(float(point["lat"]) - float(start["lat"]), float(point["lon"]) - float(start["lon"]))


def overpass_fails_photon_works(url, **kwargs):
    if "photon" not in str(url):
        raise RuntimeError("Overpass indisponible")
    return {
        "features": [
            {"geometry": {"coordinates": [-1.36, 48.66]}, "properties": {"name": "Camping Photon A", "countrycode": "FR", "osm_key": "tourism", "osm_value": "camp_site", "osm_type": "N", "osm_id": 11}},
            {"geometry": {"coordinates": [-1.50, 48.78]}, "properties": {"name": "Camping Photon B", "countrycode": "FR", "osm_key": "tourism", "osm_value": "camp_site", "osm_type": "N", "osm_id": 12}},
            {"geometry": {"coordinates": [-1.69, 48.67]}, "properties": {"name": "Camping Photon C", "countrycode": "FR", "osm_key": "tourism", "osm_value": "camp_site", "osm_type": "N", "osm_id": 13}},
        ]
    }

free._request_json = overpass_fails_photon_works
try:
    rescue._INSTALLED = False
    rescue.install_stay_lookup_rescue(V3, CampsiteLoopPhoton, Roundtrip)
    photon_rows = CampsiteLoopPhoton._diverse_stays(V3, Roundtrip, START, "camping", 4, 18.0)
finally:
    free._request_json = old_request

assert len(photon_rows) >= 3, photon_rows
assert {x["name"] for x in photon_rows} >= {"Camping Photon A", "Camping Photon B", "Camping Photon C"}
print("Accommodation discovery rescue: OK")

# Names, street addresses, malformed coordinates and missing OSM identities
# must never turn into campsites or refuges when the primary lookup fails.
for category, key, value in [("camping", "tourism", "camp_site"), ("refuge", "tourism", "alpine_hut")]:
    valid = {"osm_type": "N", "osm_id": 90, "osm_key": key, "osm_value": value, "name": "Étape"}
    candidates = [valid,
        dict(valid, osm_key="shop", osm_value="outdoor", name="Camping Refuge"),
        dict(valid, osm_key="highway", osm_value="residential", name="Rue du Refuge Camping"),
        dict(valid, osm_id=None), dict(valid, osm_type=""), dict(valid, osm_id=-1)]
    features = [{"geometry": {"coordinates": [-1.36, 48.66]}, "properties": row} for row in candidates]
    features.append({"geometry": {"coordinates": [float("nan"), 48.66]}, "properties": valid})
    free._request_json = lambda *a, **k: {"features": features}
    try:
        found = rescue._photon_stays(START, category, 30)
        assert len(found) == 1, found
        assert found[0]["name"] == "Étape"
    finally:
        free._request_json = old_request
    rows = [{"lat": 48.66, "lon": -1.36, "osm_type": "node", "osm_id": 90,
             "category": key, "type": value, "display_name": "Étape"},
            {"lat": 48.66, "lon": -1.36, "osm_type": "node", "osm_id": 91,
             "category": "shop", "type": "outdoor", "display_name": "Camping Refuge"}]
    free._request_json = lambda *a, **k: rows
    try:
        found = rescue._nominatim_stays(START, category, 30)
        assert len(found) == 1, found
        assert found[0]["name"] == "Étape"
    finally:
        free._request_json = old_request
print("Accommodation evidence validation: OK")
