"""Offline regression: French commune fallback with strict geography checks."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as geo
from backend import trekbrain_commune_fallback_v9 as communes

rows = [
    {"code": "74208", "nom": "Passy",
     "departement": {"nom": "Haute-Savoie", "code": "74"},
     "centre": {"type": "Point", "coordinates": [6.69, 45.92]}},
    {"code": "89291", "nom": "Passy",
     "departement": {"nom": "Yonne", "code": "89"},
     "centre": {"type": "Point", "coordinates": [3.30, 48.65]}},
    {"code": "12345", "nom": "Passy-sur-Seine",
     "departement": {"nom": "Haute-Savoie", "code": "74"},
     "centre": {"type": "Point", "coordinates": [6.70, 45.95]}},
]
original_request = geo._request_json
calls = []
geo._request_json = lambda url, **kw: (calls.append((url, kw)) or rows)
try:
    passy = communes.geocode_commune("Passy, Haute-Savoie, France")
    assert len(passy) == 1 and passy[0]["department_code"] == "74", passy
    assert abs(passy[0]["lat"] - 45.92) < 0.00001
    assert passy[0]["geocode_provider"] == "geo-api-gouv-communes"
    assert calls[0][0] == communes.COMMUNES_URL
    assert calls[0][1]["retries"] == 1
    assert calls[0][1]["cache_empty"] is False
    assert calls[0][1]["timeout"] <= 2.5
    assert communes.geocode_commune("Passy, Savoie, France") == []
    assert communes.geocode_commune("Passy, France") == []
    assert communes.geocode_commune("Passy, Haute-Savoie, Espagne") == []
    assert communes.geocode_commune("Passy, Yonne")[0]["department_code"] == "89"
    geo._request_json = lambda *a, **kw: [
        {"code": "74208", "nom": "Passy",
         "departement": {"nom": "Haute-Savoie", "code": "74"},
         "centre": {"coordinates": [float("nan"), 45.92]}}
    ]
    assert communes.geocode_commune("Passy, Haute-Savoie") == []
finally:
    geo._request_json = original_request

# Reproduce the actual failure path: Nominatim 429, Photon timeout,
# IGN no match, then exact municipality centre recovered. No network calls.
from backend import smart_planner_v3 as v3
from backend import smart_planner_v5 as v5
from backend import smart_planner_v9 as v9
from backend import trekbrain_speed_v9 as speed
from backend import trekbrain_geo_fallback_v9 as ign

original_nom = geo._geocode_nominatim
original_photon = geo._geocode_photon
original_ign = ign.geocode_ign
original_commune = communes.geocode_commune
old_cooldown = speed._NOMINATIM_COOLDOWN_UNTIL
called = []

def limited_nom(query, *, retries=2):
    called.append(("nom", query))
    raise RuntimeError("Nominatim temporairement limité (HTTP 429).")

def timed_out_photon(query, *, timeout=12, retries=2):
    called.append(("photon", query))
    raise RuntimeError("Photon a dépassé le délai d'attente.")

geo._geocode_nominatim = limited_nom
geo._geocode_photon = timed_out_photon
ign.geocode_ign = lambda query, **kw: (called.append(("ign", query)) or [])
communes.geocode_commune = lambda query, **kw: (
    called.append(("communes", query)) or
    [{"name": "Passy, Haute-Savoie, France", "lat": 45.92,
      "lon": 6.69, "geocode_provider": "geo-api-gouv-communes"}]
)
speed._NOMINATIM_COOLDOWN_UNTIL = 0.0
try:
    speed._INSTALLED = False
    speed.install_fast_planning(v3, v5, v9)
    result = v3._geocode("Passy, Haute-Savoie, France")
    assert result and result[0]["geocode_provider"] == "geo-api-gouv-communes", result
    assert [name for name, _ in called] == ["nom", "photon", "ign", "communes"], called
finally:
    geo._geocode_nominatim = original_nom
    geo._geocode_photon = original_photon
    ign.geocode_ign = original_ign
    communes.geocode_commune = original_commune
    speed._NOMINATIM_COOLDOWN_UNTIL = old_cooldown

print("Official French commune geocoding: strict municipality, department and provider-outage rescue PASS")
