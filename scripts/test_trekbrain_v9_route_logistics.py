"""Regression: lodging must not reshape the hiking route, with or without a GR."""
from pathlib import Path
import os
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as free
from backend import trekbrain_route_logistics_v9 as logistics
from backend import trekbrain_route_logistics_guard_v9 as logistics_guard


class Data:
    prompt = "Je veux une boucle de 5 jours à 20 km par jour avec des campings tous les soirs"
    region = "Zone test"
    days = 5
    daily_km = 20
    require_accommodation = True

    def model_copy(self, update=None):
        clone = Data()
        for key, value in (update or {}).items():
            setattr(clone, key, value)
        return clone


class FakeRoundtrip:
    @staticmethod
    def _haversine(a, b):
        # Synthetic route uses 0.01° longitude ~= 1 km for this test.
        return abs(float(b[1]) - float(a[1])) * 100.0

    @staticmethod
    def _cumulative(coords):
        out = [0.0]
        for a, b in zip(coords, coords[1:]):
            out.append(out[-1] + FakeRoundtrip._haversine(a, b))
        return out

    @staticmethod
    def _route_index_for_progress(cum, progress):
        return min(range(len(cum)), key=lambda i: abs(cum[i] - progress))

    @staticmethod
    def _project_stay_to_route(coords, cum, stay):
        index = int(round(float(stay["lon"]) * 100))
        index = max(0, min(index, len(coords) - 1))
        off = abs(float(stay["lat"])) * 100.0
        return index, float(cum[index]), off


class FakeV3:
    def __init__(self):
        self._build_calls = []

    @staticmethod
    def _parse_intent(data):
        text = str(data.prompt).casefold()
        return {
            "days": 5,
            "daily_target": 20.0,
            "daily_min": 15.0,
            "daily_max": 25.0,
            "route_type": "Boucle",
            "accommodation": "camping" if "camping" in text else "balanced",
        }

    @staticmethod
    def _nearby(*args, **kwargs):
        return []


class FakeStayRescue:
    @staticmethod
    def _photon_stays(*args, **kwargs):
        return []

    @staticmethod
    def _nominatim_stays(*args, **kwargs):
        return []


class FakeORS:
    @staticmethod
    def get_route(coords, distance_func):
        # Every short connector is validated. Its distance is roughly the
        # vertical synthetic offset in this test.
        distance = abs(float(coords[-1][0]) - float(coords[0][0])) * 100.0
        return {"coords": coords, "distance": max(0.2, distance), "fallback": False, "routing_mode": "fake-walk"}


class FakeLegacy:
    @staticmethod
    def distance_gps(coords):
        return 100.0 if len(coords) > 10 else 1.0


coords = [[0.0, i / 100.0] for i in range(101)]
base_result = {
    "title": "Boucle sans GR",
    "route_type": "Boucle",
    "duration_days": 5,
    "start": {"name": "Départ", "lat": 0.0, "lon": 0.0},
    "end": {"name": "Départ", "lat": 0.0, "lon": 0.0},
    "route_preview": {"coords": coords, "distance_km": 100.0, "distance": 100.0, "fallback": False, "routing_mode": "ors"},
    "stages": [{"day": i + 1, "distance_km": 20.0, "overnight": "Étape"} for i in range(5)],
    "advisor_notes": [],
    "planner": {},
}

# Campsites lie near ideal 20/40/60/80 km splits. The third one is deliberately
# farther from the route and should become transfer logistics instead of making
# a 30 km hiking day.
camps = [
    {"name": "Camping A", "lat": 0.010, "lon": 0.20, "category": "camping", "source_url": "osm://a"},
    {"name": "Camping B", "lat": 0.015, "lon": 0.40, "category": "camping", "source_url": "osm://b"},
    {"name": "Camping C", "lat": 0.045, "lon": 0.60, "category": "camping", "source_url": "osm://c"},
    {"name": "Camping D", "lat": 0.012, "lon": 0.80, "category": "camping", "source_url": "osm://d"},
]

real_bbox = logistics._bbox_route_stays
logistics._bbox_route_stays = lambda _coords, category: [dict(x) for x in camps]
try:
    v3 = FakeV3()

    def original_build(data, legacy):
        v3._build_calls.append((data.prompt, getattr(data, "require_accommodation", None)))
        return {**base_result, "route_preview": dict(base_result["route_preview"]), "stages": [dict(x) for x in base_result["stages"]], "advisor_notes": [], "planner": {}}

    v3._build = original_build
    logistics._INSTALLED = False
    logistics.install_route_first_logistics(v3, FakeRoundtrip, FakeStayRescue, FakeORS)
    result = v3._build(Data(), FakeLegacy())
finally:
    logistics._bbox_route_stays = real_bbox

# Main route is built with lodging removed, proving camping does not shape geometry.
assert len(v3._build_calls) == 1, v3._build_calls
assert "camping" not in v3._build_calls[0][0].casefold(), v3._build_calls
assert v3._build_calls[0][1] is False
assert result["route_preview"]["coords"] == coords
assert result["route_preview"]["distance_km"] == 100.0
assert result["planner"]["logistics_mode"] == "route-first"
assert result["logistics"]["nights_required"] == 4
assert result["logistics"]["nights_resolved"] == 4
assert len(result["accommodations"]) == 4
assert all(float(stage["distance_km"]) == 20.0 for stage in result["stages"])
assert max(float(stage["distance_km"]) for stage in result["stages"]) <= 25.0

# The distant campsite remains useful but does not deform the hiking route.
night3 = result["logistics"]["nights"][2]
assert night3["name"] == "Camping C"
assert night3["access_mode"] == "transfer", night3
assert "transfert" in result["stages"][2]["overnight"].casefold()


# Missing stays are a normal partial-logistics state, not an exception. This
# protects the production KeyError regression where an unresolved night had no
# "name" field but stage rendering accessed night["name"] anyway.
v3_partial = FakeV3()

def base_build_partial(data, legacy):
    return {**base_result, "route_preview": dict(base_result["route_preview"]), "stages": [dict(x) for x in base_result["stages"]], "advisor_notes": [], "planner": {}}

v3_partial._build = base_build_partial
real_bbox_partial = logistics._bbox_route_stays
try:
    logistics._bbox_route_stays = lambda _coords, category: []
    logistics._INSTALLED = False
    logistics.install_route_first_logistics(v3_partial, FakeRoundtrip, FakeStayRescue, FakeORS)
    partial = v3_partial._build(Data(), FakeLegacy())
finally:
    logistics._bbox_route_stays = real_bbox_partial

assert partial["route_preview"]["fallback"] is False
assert partial["logistics"]["status"] == "partial"
assert partial["logistics"]["nights_resolved"] == 0
assert all(
    "Nuitée à organiser" in str(stage.get("overnight") or "")
    for stage in partial["stages"][:-1]
)


# Structured campsite/refuge rescue must leave query_override unset so the
# shared Photon helper sends q + osm_tag + bbox in the same request. A text
# override suppresses osm_tag and made public-index results fluctuate.
class FakePhotonRoundtrip(FakeRoundtrip):
    @staticmethod
    def _equal_anchors(_coords, days):
        return [
            {"name": f"Repère jour {day}", "lat": 0.0, "lon": day * 0.20}
            for day in range(1, days)
        ]

class FakePhotonV3:
    calls = []

    @staticmethod
    def _photon_anchor_resource(anchor, category, tags, radius, query_override=None):
        tag_tuple = tuple(tags)
        FakePhotonV3.calls.append((category, tag_tuple, float(radius), query_override))
        actual = "camping" if any("camp_site" in tag for tag in tag_tuple) else "refuge"
        return {
            "name": f"{actual} test",
            "lat": anchor["lat"],
            "lon": anchor["lon"],
            "category": actual,
            "source_url": f"osm://{actual}/{anchor['lon']}",
        }

FakePhotonV3.calls = []
structured_camps = logistics._photon_split_stays(
    FakePhotonV3, FakePhotonRoundtrip, coords, "camping", 3
)
assert len(structured_camps) == 2, structured_camps
assert all(call[3] is None for call in FakePhotonV3.calls), FakePhotonV3.calls
assert all("tourism:camp_site" in call[1] for call in FakePhotonV3.calls), FakePhotonV3.calls

FakePhotonV3.calls = []
structured_refuges = logistics._photon_split_stays(
    FakePhotonV3, FakePhotonRoundtrip, coords, "refuge", 3
)
assert len(structured_refuges) == 2, structured_refuges
assert all(call[3] is None for call in FakePhotonV3.calls), FakePhotonV3.calls
assert all("tourism:alpine_hut" in call[1] for call in FakePhotonV3.calls), FakePhotonV3.calls

# Structured outdoor lodging should prefer one exact OSM corridor query and stop
# before Photon when that query already resolves every night.
real_bbox_order = logistics._bbox_route_stays
real_photon_order = logistics._photon_split_stays
order_calls = {"bbox": 0, "photon": 0}
try:
    def counted_bbox(_coords, category):
        order_calls["bbox"] += 1
        return [dict(x) for x in camps]

    def counted_photon(*args, **kwargs):
        order_calls["photon"] += 1
        return []

    logistics._bbox_route_stays = counted_bbox
    logistics._photon_split_stays = counted_photon
    chosen_fast, projected_fast, meta_fast = logistics._discover_stays(
        FakeV3(),
        FakeRoundtrip,
        FakeStayRescue,
        coords,
        {"name": "Départ", "lat": 0.0, "lon": 0.0},
        "camping",
        5,
        20.0,
        False,
    )
finally:
    logistics._bbox_route_stays = real_bbox_order
    logistics._photon_split_stays = real_photon_order

assert len(chosen_fast) == 4, chosen_fast
assert order_calls == {"bbox": 1, "photon": 0}, order_calls
assert meta_fast["elapsed_ms"] >= 0

# When structured lodging and terrain are both requested, exact-tag Overpass
# and one route-bounded Nominatim stay query are independent and must start in
# the same wave. The expensive per-stage Photon wave is no longer on this hot
# path.
real_bundle_parallel = logistics._bbox_route_bundle
real_nominatim_parallel = logistics._nominatim_route_stays
real_photon_parallel = logistics._photon_split_stays
parallel_barrier = threading.Barrier(2)
parallel_errors = []
parallel_calls = {"overpass": 0, "nominatim": 0, "photon": 0}

def parallel_bundle(_coords, category):
    parallel_calls["overpass"] += 1
    try:
        parallel_barrier.wait(timeout=0.75)
    except threading.BrokenBarrierError:
        parallel_errors.append("overpass-not-concurrent")
    return (
        [dict(x) for x in camps],
        [{
            "name": "Fontaine parallèle",
            "lat": 0.0,
            "lon": 0.25,
            "category": "water",
            "water_status": "potable_referenced",
            "source_url": "osm://parallel-water",
        }],
        True,
    )

def parallel_nominatim(*args, **kwargs):
    parallel_calls["nominatim"] += 1
    try:
        parallel_barrier.wait(timeout=0.75)
    except threading.BrokenBarrierError:
        parallel_errors.append("nominatim-not-concurrent")
    return []

def forbidden_parallel_photon(*args, **kwargs):
    parallel_calls["photon"] += 1
    raise AssertionError("Photon must stay out of the route-first hot path")

try:
    logistics._bbox_route_bundle = parallel_bundle
    logistics._nominatim_route_stays = parallel_nominatim
    logistics._photon_split_stays = forbidden_parallel_photon
    chosen_parallel, _projected_parallel, meta_parallel = logistics._discover_stays(
        FakeV3(),
        FakeRoundtrip,
        FakeStayRescue,
        coords,
        {"name": "Départ", "lat": 0.0, "lon": 0.0},
        "camping",
        5,
        20.0,
        False,
        want_terrain=True,
    )
finally:
    logistics._bbox_route_bundle = real_bundle_parallel
    logistics._nominatim_route_stays = real_nominatim_parallel
    logistics._photon_split_stays = real_photon_parallel

assert parallel_errors == [], parallel_errors
assert parallel_calls == {"overpass": 1, "nominatim": 1, "photon": 0}, parallel_calls
assert len(chosen_parallel) == 4, chosen_parallel
assert meta_parallel["terrain_preloaded"] is True

# Slow structured route-wide discovery should trigger exactly one delayed
# Photon hedge, overlapping the slow tail instead of waiting for it serially.
real_bundle_hedge = logistics._bbox_route_bundle
real_nominatim_hedge = logistics._nominatim_route_stays
real_photon_hedge = logistics._photon_split_stays
old_hedge_env = os.environ.get("TREKBRAIN_STAY_HEDGE_SECONDS")
hedge_times = {}
hedge_calls = {"photon": 0}
try:
    os.environ["TREKBRAIN_STAY_HEDGE_SECONDS"] = "0.05"

    def slow_hedge_bundle(_coords, category):
        hedge_times["bundle_start"] = time.monotonic()
        time.sleep(0.12)
        hedge_times["bundle_end"] = time.monotonic()
        return [], [], False

    def empty_hedge_nominatim(*args, **kwargs):
        return []

    def successful_hedge_photon(*args, **kwargs):
        hedge_calls["photon"] += 1
        hedge_times["photon_start"] = time.monotonic()
        return [dict(x) for x in camps]

    logistics._bbox_route_bundle = slow_hedge_bundle
    logistics._nominatim_route_stays = empty_hedge_nominatim
    logistics._photon_split_stays = successful_hedge_photon
    chosen_hedge, _projected_hedge, _meta_hedge = logistics._discover_stays(
        FakeV3(),
        FakeRoundtrip,
        FakeStayRescue,
        coords,
        {"name": "Départ", "lat": 0.0, "lon": 0.0},
        "camping",
        5,
        20.0,
        False,
        want_terrain=True,
    )
finally:
    logistics._bbox_route_bundle = real_bundle_hedge
    logistics._nominatim_route_stays = real_nominatim_hedge
    logistics._photon_split_stays = real_photon_hedge
    if old_hedge_env is None:
        os.environ.pop("TREKBRAIN_STAY_HEDGE_SECONDS", None)
    else:
        os.environ["TREKBRAIN_STAY_HEDGE_SECONDS"] = old_hedge_env

assert hedge_calls["photon"] == 1, hedge_calls
assert len(chosen_hedge) == 4, chosen_hedge
assert hedge_times["bundle_start"] < hedge_times["photon_start"] < hedge_times["bundle_end"], hedge_times

# Overnight evidence already discovered while shaping the route must survive
# into route-first logistics. A provider fluctuation after routing must not make
# TrekBrain forget camps/refuges it has already paid to discover.
real_bundle_preloaded = logistics._bbox_route_bundle
real_nominatim_preloaded = logistics._nominatim_route_stays
real_photon_preloaded = logistics._photon_split_stays
preloaded_calls = {"overpass": 0, "nominatim": 0, "photon": 0}
try:
    def empty_preloaded_bundle(_coords, category):
        preloaded_calls["overpass"] += 1
        return [], [], False

    def empty_preloaded_nominatim(*args, **kwargs):
        preloaded_calls["nominatim"] += 1
        return []

    def forbidden_preloaded_photon(*args, **kwargs):
        preloaded_calls["photon"] += 1
        raise AssertionError("already-discovered stays must prevent Photon re-discovery")

    logistics._bbox_route_bundle = empty_preloaded_bundle
    logistics._nominatim_route_stays = empty_preloaded_nominatim
    logistics._photon_split_stays = forbidden_preloaded_photon
    chosen_preloaded, projected_preloaded, _meta_preloaded = logistics._discover_stays(
        FakeV3(),
        FakeRoundtrip,
        FakeStayRescue,
        coords,
        {"name": "Départ", "lat": 0.0, "lon": 0.0},
        "camping",
        5,
        20.0,
        False,
        want_terrain=True,
        preloaded_rows=[dict(x) for x in camps],
    )
finally:
    logistics._bbox_route_bundle = real_bundle_preloaded
    logistics._nominatim_route_stays = real_nominatim_preloaded
    logistics._photon_split_stays = real_photon_preloaded

assert len(projected_preloaded) == 4, projected_preloaded
assert len(chosen_preloaded) == 4, chosen_preloaded
assert preloaded_calls == {"overpass": 1, "nominatim": 0, "photon": 0}, preloaded_calls

# A complete set of preloaded nights without terrain needs no provider at all.
# In particular the generic route-first layer must not discard good canonical
# stays merely to perform a second camping search.
no_terrain_provider_calls = []
real_preloaded_bbox = logistics._bbox_route_stays
real_preloaded_nominatim = logistics._nominatim_route_stays
real_preloaded_photon = logistics._photon_split_stays
try:
    def forbidden_preloaded_provider(*args, **kwargs):
        no_terrain_provider_calls.append("unexpected")
        raise AssertionError("complete preloaded nights must skip stay providers")

    logistics._bbox_route_stays = forbidden_preloaded_provider
    logistics._nominatim_route_stays = forbidden_preloaded_provider
    logistics._photon_split_stays = forbidden_preloaded_provider
    chosen_without_terrain, projected_without_terrain, meta_without_terrain = logistics._discover_stays(
        FakeV3(), FakeRoundtrip, FakeStayRescue, coords,
        {"name": "Départ", "lat": 0.0, "lon": 0.0},
        "camping", 5, 20.0, False,
        want_terrain=False, preloaded_rows=[dict(x) for x in camps],
    )
finally:
    logistics._bbox_route_stays = real_preloaded_bbox
    logistics._nominatim_route_stays = real_preloaded_nominatim
    logistics._photon_split_stays = real_preloaded_photon

assert not no_terrain_provider_calls, no_terrain_provider_calls
assert len(chosen_without_terrain) == 4, chosen_without_terrain
assert len(projected_without_terrain) == 4, projected_without_terrain
assert meta_without_terrain["terrain_preloaded"] is False, meta_without_terrain

# If both cheap route-wide primaries are empty, exactly one bounded Photon
# rescue wave may recover real overnight candidates. This restores the proven
# resource coverage without putting Photon back on the normal hot path.
real_bundle_rescue = logistics._bbox_route_bundle
real_nominatim_rescue = logistics._nominatim_route_stays
real_photon_rescue = logistics._photon_split_stays
rescue_calls = {"overpass": 0, "nominatim": 0, "photon": 0}
try:
    def empty_rescue_bundle(_coords, category):
        rescue_calls["overpass"] += 1
        return [], [], False

    def empty_rescue_nominatim(*args, **kwargs):
        rescue_calls["nominatim"] += 1
        return []

    def successful_rescue_photon(*args, **kwargs):
        rescue_calls["photon"] += 1
        return [dict(x) for x in camps]

    logistics._bbox_route_bundle = empty_rescue_bundle
    logistics._nominatim_route_stays = empty_rescue_nominatim
    logistics._photon_split_stays = successful_rescue_photon
    chosen_rescue, projected_rescue, meta_rescue = logistics._discover_stays(
        FakeV3(),
        FakeRoundtrip,
        FakeStayRescue,
        coords,
        {"name": "Départ", "lat": 0.0, "lon": 0.0},
        "camping",
        5,
        20.0,
        False,
        want_terrain=True,
    )
finally:
    logistics._bbox_route_bundle = real_bundle_rescue
    logistics._nominatim_route_stays = real_nominatim_rescue
    logistics._photon_split_stays = real_photon_rescue

assert rescue_calls == {"overpass": 1, "nominatim": 1, "photon": 1}, rescue_calls
assert len(projected_rescue) == 4, projected_rescue
assert len(chosen_rescue) == 4, chosen_rescue
assert meta_rescue["terrain_preloaded"] is False

# Nominatim route-stay discovery is one bounded route-wide request and keeps
# real OSM provenance. This is the resilient stay source when public Overpass is
# empty from Render.
real_nominatim_request = free._request_json
captured_nominatim = {}
try:
    def fake_nominatim_request(url, **kwargs):
        captured_nominatim.update(dict(kwargs.get("params") or {}))
        return [{
            "lat": "0.01",
            "lon": "0.20",
            "class": "tourism",
            "type": "camp_site",
            "display_name": "Camping Nominatim, Zone test, France",
            "osm_type": "node",
            "osm_id": 4242,
        }]
    free._request_json = fake_nominatim_request
    nominatim_camps = logistics._nominatim_route_stays(coords, "camping")
finally:
    free._request_json = real_nominatim_request

assert len(nominatim_camps) == 1, nominatim_camps
assert nominatim_camps[0]["name"] == "Camping Nominatim", nominatim_camps
assert nominatim_camps[0]["source_url"].endswith("/node/4242"), nominatim_camps
assert captured_nominatim.get("bounded") == 1, captured_nominatim
assert captured_nominatim.get("countrycodes") == "fr", captured_nominatim
assert captured_nominatim.get("viewbox"), captured_nominatim
assert captured_nominatim.get("q") == "[camping]", captured_nominatim
assert "osm.tourism.camp_site" in str(captured_nominatim.get("include") or ""), captured_nominatim

# A public Overpass primary may be empty or unavailable while another mirror
# still has the corridor data. Keep the normal single-primary path, then race at
# most two short fallback mirrors only after that miss.
real_overpass_request = free._request_json
real_overpass_urls = list(free.OVERPASS_URLS)
overpass_failover_calls = []
fallback_barrier = threading.Barrier(2)
fallback_parallel_errors = []
try:
    free.OVERPASS_URLS = [
        "https://primary.test/api/interpreter",
        "https://secondary.test/api/interpreter",
        "https://tertiary.test/api/interpreter",
    ]

    def fake_overpass_failover(url, **kwargs):
        overpass_failover_calls.append((
            url,
            float(kwargs.get("timeout") or 0),
            kwargs.get("cache_empty"),
        ))
        if "primary.test" in url:
            return {"elements": []}
        try:
            fallback_barrier.wait(timeout=0.75)
        except threading.BrokenBarrierError:
            fallback_parallel_errors.append(url)
        if "secondary.test" in url:
            return {"elements": []}
        if "tertiary.test" in url:
            return {
                "elements": [
                    {
                        "type": "node",
                        "id": 1,
                        "lat": 0.0,
                        "lon": 0.20,
                        "tags": {"tourism": "camp_site", "name": "Camping miroir"},
                    },
                    {
                        "type": "node",
                        "id": 2,
                        "lat": 0.0,
                        "lon": 0.25,
                        "tags": {"amenity": "drinking_water", "name": "Fontaine miroir"},
                    },
                    {
                        "type": "node",
                        "id": 3,
                        "lat": 0.0,
                        "lon": 0.30,
                        "tags": {"shop": "bakery", "name": "Boulangerie miroir"},
                    },
                ]
            }
        raise AssertionError(f"unexpected Overpass mirror call: {url}")

    free._request_json = fake_overpass_failover
    mirror_stays, mirror_terrain, mirror_preloaded = logistics._bbox_route_bundle(
        coords, "camping"
    )

    # All mirrors returning syntactically valid empty results must keep the outer
    # resource fallbacks eligible instead of pretending terrain was loaded.
    free._request_json = lambda url, **kwargs: {"elements": []}
    empty_stays, empty_terrain, empty_preloaded = logistics._bbox_route_bundle(
        coords, "camping"
    )
finally:
    free._request_json = real_overpass_request
    free.OVERPASS_URLS = real_overpass_urls

assert fallback_parallel_errors == [], fallback_parallel_errors
assert len(overpass_failover_calls) == 3, overpass_failover_calls
assert "primary.test" in overpass_failover_calls[0][0], overpass_failover_calls
assert overpass_failover_calls[0][1] <= 1.81, overpass_failover_calls
assert all(call[1] <= 0.86 for call in overpass_failover_calls[1:]), overpass_failover_calls
assert all(call[2] is False for call in overpass_failover_calls), overpass_failover_calls
assert {call[0] for call in overpass_failover_calls[1:]} == {
    "https://secondary.test/api/interpreter",
    "https://tertiary.test/api/interpreter",
}, overpass_failover_calls
assert [x["name"] for x in mirror_stays] == ["Camping miroir"], mirror_stays
assert {x.get("category") for x in mirror_terrain} == {"water", "food"}, mirror_terrain
assert mirror_preloaded is True
assert empty_stays == [] and empty_terrain == [], (empty_stays, empty_terrain)
assert empty_preloaded is False

# When water/food are requested, the lodging corridor OSM response is reused
# instead of paying for a second terrain query after planning.
real_bundle_terrain = logistics._bbox_route_bundle
real_nominatim_terrain = logistics._nominatim_route_stays
real_photon_terrain = logistics._photon_split_stays
try:
    logistics._bbox_route_bundle = lambda _coords, category: (
        [dict(x) for x in camps],
        [
            {
                "name": "Fontaine terrain",
                "lat": 0.0,
                "lon": 0.25,
                "category": "water",
                "water_status": "potable_referenced",
                "source_url": "osm://water",
            },
            {
                "name": "Épicerie terrain",
                "lat": 0.0,
                "lon": 0.45,
                "category": "food",
                "source_url": "osm://food",
            },
            {
                "name": "Gare terrain",
                "lat": 0.0,
                "lon": 0.01,
                "category": "transit",
                "source_url": "osm://station",
            },
        ],
        True,
    )
    logistics._nominatim_route_stays = lambda *args, **kwargs: []
    logistics._photon_split_stays = lambda *args, **kwargs: []
    chosen_terrain, _projected_terrain, meta_terrain = logistics._discover_stays(
        FakeV3(),
        FakeRoundtrip,
        FakeStayRescue,
        coords,
        {"name": "Départ", "lat": 0.0, "lon": 0.0},
        "camping",
        5,
        20.0,
        False,
        want_terrain=True,
    )
finally:
    logistics._bbox_route_bundle = real_bundle_terrain
    logistics._nominatim_route_stays = real_nominatim_terrain
    logistics._photon_split_stays = real_photon_terrain

assert len(chosen_terrain) == 4, chosen_terrain
assert meta_terrain["terrain_preloaded"] is True
assert {x.get("category") for x in meta_terrain["terrain_rows"]} == {"water", "food", "transit"}

terrain_plan = {
    "water": [],
    "resources": [],
    "food": [],
    "points_of_interest": [],
    "transport": {},
    "start": {"name": "Départ", "lat": 0.0, "lon": 0.0},
    "end": {"name": "Arrivée", "lat": 0.0, "lon": 0.0},
}
logistics._attach_preloaded_terrain(
    terrain_plan,
    meta_terrain["terrain_rows"],
    meta_terrain["terrain_preloaded"],
)
assert terrain_plan["_terrain_osm_preloaded"] is True
assert terrain_plan["water"][0]["name"] == "Fontaine terrain"
assert terrain_plan["resources"][0]["name"] == "Épicerie terrain"
assert terrain_plan["points_of_interest"][0]["name"] == "Gare terrain"
assert "Gare terrain" in terrain_plan["transport"]["outbound"]
assert "Gare terrain" in terrain_plan["transport"]["return"]

# Generic lodging may be a separate transfer without reshaping the hiking line.
# Discovery already searches to 12.5 km; preserve those candidates through the
# projection stage when the user did not demand 100% walk.
generic_lodging = [
    {"name": "Gîte A", "lat": 0.110, "lon": 0.20, "category": "lodging", "source_url": "osm://ga"},
    {"name": "Gîte B", "lat": 0.110, "lon": 0.40, "category": "lodging", "source_url": "osm://gb"},
    {"name": "Gîte C", "lat": 0.110, "lon": 0.60, "category": "lodging", "source_url": "osm://gc"},
    {"name": "Gîte D", "lat": 0.110, "lon": 0.80, "category": "lodging", "source_url": "osm://gd"},
]
real_nominatim_generic = logistics._nominatim_route_stays
real_bbox_generic = logistics._bbox_route_stays
try:
    logistics._nominatim_route_stays = lambda *args, **kwargs: [dict(x) for x in generic_lodging]
    logistics._bbox_route_stays = lambda *args, **kwargs: []
    chosen_generic, projected_generic, _meta_generic = logistics._discover_stays(
        FakeV3(),
        FakeRoundtrip,
        FakeStayRescue,
        coords,
        {"name": "Départ", "lat": 0.0, "lon": 0.0},
        "lodging",
        5,
        20.0,
        False,
    )
finally:
    logistics._nominatim_route_stays = real_nominatim_generic
    logistics._bbox_route_stays = real_bbox_generic

assert len(chosen_generic) == 4, chosen_generic
assert all(10.0 < float(x.get("_offroute_km") or 0) <= 12.5 for x in chosen_generic), chosen_generic


# One generic night on a two-day loop may be outside the ideal midpoint
# window while still being a perfectly usable transfer. Keep the route intact
# and surface that lodging instead of reporting no night at all.
two_day_lodging = [
    {"name": "Hôtel transfert", "lat": 0.110, "lon": 0.10, "category": "lodging", "source_url": "osm://transfer"}
]
real_nominatim_two_day = logistics._nominatim_route_stays
real_bbox_two_day = logistics._bbox_route_stays
try:
    logistics._nominatim_route_stays = lambda *args, **kwargs: [dict(x) for x in two_day_lodging]
    logistics._bbox_route_stays = lambda *args, **kwargs: []
    chosen_two_day, projected_two_day, _meta_two_day = logistics._discover_stays(
        FakeV3(),
        FakeRoundtrip,
        FakeStayRescue,
        coords,
        {"name": "Départ", "lat": 0.0, "lon": 0.0},
        "lodging",
        2,
        20.0,
        False,
    )
finally:
    logistics._nominatim_route_stays = real_nominatim_two_day
    logistics._bbox_route_stays = real_bbox_two_day

assert len(projected_two_day) == 1, projected_two_day
assert len(chosen_two_day) == 1, chosen_two_day
assert chosen_two_day[0]["name"] == "Hôtel transfert"
assert float(chosen_two_day[0].get("_offroute_km") or 0) > logistics._WALK_CONNECTOR_LIMIT_KM

two_day_result = {
    "title": "Boucle 2 jours",
    "route_type": "Boucle",
    "duration_days": 2,
    "start": {"name": "Départ", "lat": 0.0, "lon": 0.0},
    "end": {"name": "Départ", "lat": 0.0, "lon": 0.0},
    "route_preview": {"coords": coords, "distance_km": 40.0, "distance": 40.0, "fallback": False, "routing_mode": "ors"},
    "stages": [{"day": 1, "distance_km": 20.0}, {"day": 2, "distance_km": 20.0}],
    "advisor_notes": [],
    "planner": {},
}
real_discover_two_day = logistics._discover_stays
try:
    logistics._discover_stays = lambda *args, **kwargs: (
        [dict(chosen_two_day[0])],
        [dict(chosen_two_day[0])],
        {
            "budget_seconds": 4.0,
            "elapsed_ms": 1,
            "budget_exhausted": False,
            "terrain_rows": [],
            "terrain_preloaded": False,
        },
    )
    attached_two_day = logistics._attach_logistics(
        two_day_result,
        Data(),
        FakeLegacy,
        FakeV3(),
        FakeRoundtrip,
        FakeStayRescue,
        FakeORS,
        {
            "days": 2,
            "daily_target": 20.0,
            "daily_max": 25.0,
            "water": False,
            "food": False,
        },
        "lodging",
    )
finally:
    logistics._discover_stays = real_discover_two_day

assert attached_two_day["route_preview"]["coords"] == coords
assert attached_two_day["route_preview"]["distance_km"] == 40.0
assert attached_two_day["logistics"]["route_immutable"] is True
assert attached_two_day["logistics"]["status"] == "complete"
assert attached_two_day["logistics"]["nights_resolved"] == 1
assert attached_two_day["logistics"]["nights"][0]["access_mode"] == "transfer"
assert "transfert" in attached_two_day["stages"][0]["overnight"].casefold()

# Generic lodging sends gîte + hotel in the same bounded Photon wave.
class PhotonRoundtrip(FakeRoundtrip):
    @staticmethod
    def _equal_anchors(_coords, days):
        return [
            {"name": f"Repère jour {i}", "lat": 0.0, "lon": i / 10.0, "category": "route_anchor"}
            for i in range(1, days)
        ]


class DualQueryV3:
    calls = []

    @staticmethod
    def _photon_anchor_resource(anchor, category, tags, radius, query_override=None):
        DualQueryV3.calls.append((anchor["name"], query_override))
        suffix = "g" if query_override == "gîte" else "h"
        return {
            "name": f"{query_override} {anchor['name']}",
            "lat": float(anchor["lat"]),
            "lon": float(anchor["lon"]) + (0.001 if suffix == "g" else 0.002),
            "category": "lodging",
            "source_url": f"osm://{anchor['name']}-{suffix}",
        }


DualQueryV3.calls.clear()
dual_rows = logistics._photon_split_stays(
    DualQueryV3,
    PhotonRoundtrip,
    coords,
    "lodging",
    3,
)
assert len(DualQueryV3.calls) == 4, DualQueryV3.calls
assert {query for _anchor, query in DualQueryV3.calls} == {"gîte", "hotel"}
assert len(dual_rows) == 4, dual_rows

# Production guard: even if lodging post-processing throws an unexpected Python
# exception, a valid pedestrian route must still be returned instead of
# TB-INTERNAL-500.
v3_guard = FakeV3()

def base_build_guard(data, legacy):
    return {**base_result, "route_preview": dict(base_result["route_preview"]), "stages": [dict(x) for x in base_result["stages"]], "advisor_notes": [], "planner": {}}

v3_guard._build = base_build_guard
logistics._INSTALLED = False
logistics_guard._INSTALLED = False
logistics.install_route_first_logistics(v3_guard, FakeRoundtrip, FakeStayRescue, FakeORS)
wrapped_route_first = v3_guard._build

# Force the exact post-route failure class seen in production: the route exists,
# then lodging enrichment crashes for an unrelated reason.
real_attach = logistics._attach_logistics
try:
    def boom(*args, **kwargs):
        raise RuntimeError("synthetic lodging crash")
    logistics._attach_logistics = boom
    logistics_guard.install_route_logistics_guard(v3_guard)
    degraded = v3_guard._build(Data(), FakeLegacy())
finally:
    logistics._attach_logistics = real_attach

assert degraded["route_preview"]["coords"] == coords
assert degraded["route_preview"]["fallback"] is False
assert degraded["logistics"]["status"] == "degraded"
assert degraded["logistics"]["error_code"] == "TB-LOGISTICS-DEGRADED"
assert degraded["planner"]["lodging_does_not_shape_route"] is True

print("Route-first lodging logistics + fail-open recovery: OK")

# Route-wide fallback must apply the same evidence rule as night-anchor lookup.
real_request = free._request_json
try:
    genuine = {"lat": "0.01", "lon": "0.20", "category": "tourism", "type": "hotel",
               "display_name": "Camping Refuge Hôtel, rue du Camping", "osm_type": "node", "osm_id": 777}
    fake = dict(genuine, category="shop", type="outdoor", osm_id=778)
    free._request_json = lambda *a, **k: [genuine, fake, dict(genuine, osm_id=None), dict(genuine, lat="nan")]
    evidence_rows = logistics._nominatim_route_stays(coords, "lodging")
    assert len(evidence_rows) == 1 and evidence_rows[0]["category"] == "lodging", evidence_rows
    assert logistics._nominatim_route_stays(coords, "camping") == []
    assert logistics._nominatim_route_stays(coords, "refuge") == []
finally:
    free._request_json = real_request
print("Route-wide accommodation evidence: OK")

real_request = free._request_json
try:
    shelter = {'lat': '0.01', 'lon': '0.20', 'category': 'amenity', 'type': 'shelter',
               'display_name': 'Abri', 'osm_type': 'node', 'osm_id': 880}
    free._request_json = lambda *a, **k: [shelter, dict(shelter, osm_id=881, extratags={'shelter_type': 'public_transport'}),
         dict(shelter, osm_id=882, extratags={'shelter_type': 'basic_hut'})]
    sleeping = logistics._nominatim_route_stays(coords, 'refuge')
    assert len(sleeping) == 1 and sleeping[0]['source_url'].endswith('/882'), sleeping
finally:
    free._request_json = real_request
print('Route shelter sleeping evidence: OK')

# The final projection gate also rejects old/preloaded generic shelters.
preloaded_shelter = {"name": "Ancien abri", "lat": 0.01, "lon": 0.20,
                     "source_url": "https://www.openstreetmap.org/node/999",
                     "osm_tags": {"amenity": "shelter"}}
assert logistics._project_stays(FakeRoundtrip, coords, [preloaded_shelter], "refuge", 8) == []
print("Preloaded shelter evidence gate: OK")
