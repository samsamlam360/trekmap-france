"""Regression coverage for throttled geocoding and independent IGN recovery."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as geo
from backend import smart_planner_v3 as v3
from backend import smart_planner_v5 as v5
from backend import smart_planner_v9 as v9
from backend import trekbrain_geo_fallback_v9 as ign
from backend import trekbrain_speed_v9 as speed


original_request = geo._request_json
samples = {
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-1.5110, 48.6360]},
            "properties": {
                "label": "Le Mont-Saint-Michel",
                "context": "50, Manche, Normandie",
                "score": 0.91,
            },
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [2.7, 48.8]},
            "properties": {"label": "Mont Saint Michel, Chelles", "score": 0.15},
        },
    ]
}
calls = []

def fake_ign(url, **kw):
    calls.append((url, kw))
    return samples

geo._request_json = fake_ign
try:
    results = ign.geocode_ign("Mont Saint-Michel, France")
finally:
    geo._request_json = original_request
assert len(results) == 1, results
assert abs(results[0]["lon"] + 1.5110) < 0.00001
assert results[0]["geocode_provider"] == "ign-geoplateforme"
assert calls[0][0] == ign.IGN_GEOCODAGE_URL
assert calls[0][1]["timeout"] <= 2.5
assert calls[0][1]["cache_empty"] is False

# Reject a real-looking but unrelated BAN address even with a high score.
geo._request_json = lambda *a, **kw: {"features": [{
    "geometry": {"coordinates": [2.5, 48.8]},
    "properties": {"label": "Rue des Fleurs", "context": "Seine-et-Marne", "score": 0.99},
}]}
try:
    assert ign.geocode_ign("Mont Saint-Michel, France") == []
finally:
    geo._request_json = original_request

# The production fast installer must retain place safety AFTER installing fast
# mode, rather than silently bypassing the Beaufort guard.
speed._INSTALLED = False
speed.install_fast_planning(v3, v5, v9)
original_nom = geo._geocode_nominatim
original_photon = geo._geocode_photon
original_ign = ign.geocode_ign
orig_cooldown = speed._NOMINATIM_COOLDOWN_UNTIL
attempts = []

def limited_nom(query, *, retries=2):
    attempts.append(("nom", query))
    raise RuntimeError("Nominatim temporairement limité (HTTP 429).")

def available_photon(query, *, timeout=12, retries=2):
    attempts.append(("photon", query))
    return [{"name": "Vraie zone", "short_name": "Vraie zone", "lat": 45.1, "lon": 5.4}]

geo._geocode_nominatim = limited_nom
geo._geocode_photon = available_photon
speed._NOMINATIM_COOLDOWN_UNTIL = 0.0
try:
    beaufort = v3._geocode("Beaufort, Savoie, France")
    assert beaufort[0]["geocode_guard"] == "beaufort-savoie", beaufort
    assert geo._geocode("Beaufort, Savoie")[0]["geocode_guard"] == "beaufort-savoie"
    assert attempts == [], attempts

    first = v3._geocode("Lieu inedit A")
    assert first and first[0]["name"] == "Vraie zone", first
    assert [x[0] for x in attempts] == ["nom", "photon"], attempts

    # Once limited, independent Photon is tried first and Nominatim is
    # temporarily avoided for different users/queries on this worker.
    attempts.clear()
    second = v3._geocode("Lieu inedit B")
    assert second and second[0]["name"] == "Vraie zone", second
    assert [x[0] for x in attempts] == ["photon"], attempts

    # If both OSM providers fail, IGN is actually consulted as fallback.
    geo._geocode_photon = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Photon timeout"))
    ign.geocode_ign = lambda q, **kw: [{"name": "IGN", "lat": 46.2, "lon": 6.1}]
    recovered = v3._geocode("Nouvelle commune")
    assert recovered and recovered[0]["name"] == "IGN", recovered
finally:
    speed._NOMINATIM_COOLDOWN_UNTIL = orig_cooldown
    geo._geocode_nominatim = original_nom
    geo._geocode_photon = original_photon
    ign.geocode_ign = original_ign

print("TrekBrain geo provider fallback and 429 cooldown: PASS")
