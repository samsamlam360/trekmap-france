"""Cold discovery must identify an actual resource, not a suggestive address."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import smart_planner_v3 as planner

original = planner._request_json
anchor = {"lat": 45.0, "lon": 5.0}

def feature(key, value, name, **extra):
    return {"properties": {"osm_key": key, "osm_value": value,
            "name": name, "osm_type": "N", "osm_id": 123,
            "countrycode": "FR", **extra},
            "geometry": {"coordinates": [5.001, 45.001]}}

def lookup(row, category, tags):
    planner._request_json = lambda *a, **k: {"features": [row]}
    return planner._photon_anchor_resource(anchor, category, tags, 5)

try:
    cases = [
        (feature("highway", "residential", "Rue de la Fontaine"), "water", ("amenity:drinking_water",)),
        (feature("amenity", "restaurant", "La Boulangerie"), "food", ("shop:bakery",)),
        (feature("tourism", "museum", "Musée", street="Rue du Gîte"), "stay", ("tourism:guest_house",)),
        (feature("tourism", "hotel", "Hôtel du Camping"), "stay", ("tourism:camp_site",)),
        (feature("amenity", "drinking_water", "Fontaine", osm_id=None), "water", ("amenity:drinking_water",)),
    ]
    for row, category, tags in cases:
        assert lookup(row, category, tags) is None, (category, row)
    for category, key, value, label in [
        ("food", "shop", "bakery", "Chez Paul"),
        ("water", "amenity", "drinking_water", "Point communal"),
        ("stay", "tourism", "guest_house", "Maison du Camping"),
        ("stay", "tourism", "wilderness_hut", "Cabane forestière"),
    ]:
        row = lookup(feature(key, value, label), category, (f"{key}:{value}",))
        assert row and row["source_url"].endswith("/node/123"), row
        assert row["osm_tags"] == {key: value}, row
        if value == "guest_house":
            assert row["category"] == "lodging", row
    spring = lookup(feature("natural", "spring", "Source"), "water", ("natural:spring",))
    assert spring["water_status"] == "unverified", spring
    invalid = feature("shop", "bakery", "Invalid")
    invalid["geometry"]["coordinates"] = [float("nan"), 45.0]
    assert lookup(invalid, "food", ("shop:bakery",)) is None
finally:
    planner._request_json = original

print("Resource evidence: misleading names, missing identity, invalid coordinates rejected; exact OSM types retained: PASS")
