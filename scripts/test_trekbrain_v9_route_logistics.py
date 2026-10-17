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
    def get_distance_matrix(points):
        # Both directed access legs are routable in this synthetic network.
        return {"distances": [[
            (abs(float(a[0]) - float(b[0])) + abs(float(a[1]) - float(b[1]))) * 100.0
            for b in points] for a in points], "fallback": False, "profile": "foot-hiking"}

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
# An available campsite with a transfer is not equivalent to a complete
# hike on foot. Keep the legacy status but expose the actual readiness.
assert result["logistics"]["status"] == "complete"
assert result["logistics"]["nights_walk_confirmed"] == 3
assert result["logistics"]["nights_transfer_required"] == 1
assert result["logistics"]["nights_missing"] == 0
assert result["logistics"]["walking_readiness"] == "transfer_to_arrange"
assert result["logistics"]["ready_without_transfer"] is False
assert any("Transfert à organiser" in note for note in result["advisor_notes"])
assert len(result["accommodations"]) == 4
assert all(float(stage["distance_km"]) == 20.0 for stage in result["stages"])
assert max(float(stage["distance_km"]) for stage in result["stages"]) <= 25.0

# The distant campsite remains useful but does not deform the hiking route.
night3 = result["logistics"]["nights"][2]
assert night3["name"] == "Camping C"
assert night3["access_mode"] == "transfer", night3
assert "transfert" in result["stages"][2]["overnight"].casefold()


# All four stays really connected on foot must be marked ready without
# transfers. The same source-backed itinerary is left geometrically intact.
real_bbox_all_walk = logistics._bbox_route_stays
try:
    camps_all_walk = [
        {**item, "lat": 0.010} for item in camps
    ]
    logistics._bbox_route_stays = lambda _coords, category: [
        dict(item) for item in camps_all_walk
    ]
    fully_walkable = v3._build(Data(), FakeLegacy())
finally:
    logistics._bbox_route_stays = real_bbox_all_walk

assert fully_walkable["logistics"]["nights_walk_confirmed"] == 4
assert fully_walkable["logistics"]["nights_transfer_required"] == 0
assert fully_walkable["logistics"]["nights_missing"] == 0
assert fully_walkable["logistics"]["walking_readiness"] == "ready_on_foot"
assert fully_walkable["logistics"]["ready_without_transfer"] is True
assert fully_walkable["route_preview"]["coords"] == coords
assert not any(
    "Transfert à organiser" in note or "Nuitées à organiser" in note
    for note in fully_walkable["advisor_notes"]
)

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
assert partial["logistics"]["nights_walk_confirmed"] == 0
assert partial["logistics"]["nights_transfer_required"] == 0
assert partial["logistics"]["nights_missing"] == 4
assert partial["logistics"]["walking_readiness"] == "missing_nights"
assert partial["logistics"]["ready_without_transfer"] is False
assert any("Nuitées à organiser" in note for note in partial["advisor_notes"])
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


# Diagnostic-only classification must distinguish absent OSM evidence, a
# distant stage candidate, and a pedestrian connector outage without ever
# claiming straight-line distance is a verified walking route.
anchors = [
    {"night": i, "lat": 0.0, "lon": i * 0.2, "route_progress_km": float(i*20)}
    for i in range(1, 6)
]
mapped = [
    {"name": "Gîte du départ", "lat": 0.005, "lon": 0.201,
     "_route_progress_km": 20.0, "source_url": "https://www.openstreetmap.org/node/301"},
    {"name": "Camping éloigné", "lat": 0.04, "lon": 0.400,
     "_route_progress_km": 40.0, "source_url": "https://www.openstreetmap.org/node/302"},
]
valid = {**mapped[0], "_night": 1, "_anchor_distance_km": 0.5}
far = {**mapped[1], "_night": 2, "_anchor_distance_km": 4.4}
unverified = {**mapped[0], "_night": 3, "_anchor_distance_km": 1.3}
distance_limited = {**mapped[0], "_night": 4, "_anchor_distance_km": 1.2}
opts = {1: [valid], 2: [far], 3: [unverified], 4: [distance_limited], 5: []}
verified_connectors = {
    logistics._connector_key(valid): {"validated": True, "return_validated": True},
    logistics._connector_key(distance_limited): {"validated": True, "return_validated": True},
}
# Fake local OSM identities repeat across nights but the diagnostic does not
# certify availability, reservation, or deduplicated assignment.
report = logistics._night_access_diagnostics(
    anchors, mapped, opts, verified_connectors,
    [{**valid, "_access_mode": "walk"}, {**far, "_access_mode": "transfer"},
     None, None, None],
)
assert [x["reason"] for x in report] == [
    "walk_verified", "candidates_too_far_for_connector_check",
    "walking_connector_unverified", "candidate_not_compatible_with_daily_limits",
    "no_accommodation_near_stage",
], report
assert all(not x["distance_is_walking_route"] for x in report)
assert report[0]["night_walk_confirmed"] is True
assert report[1]["within_walk_check_radius"] == 0
assert report[2]["walking_connectors_verified_both_directions"] == 0
assert report[3]["walking_connectors_verified_both_directions"] == 1
assert logistics._night_access_diagnostics(anchors[:1], [], {1: []}, {}, [None])[0]["reason"] == "no_sourced_accommodation"
# A one-way Matrix result does NOT qualify an alternative as a validated walk.
assert logistics._night_access_diagnostics(
    anchors[:1], mapped, {1: [valid]},
    {logistics._connector_key(valid): {"validated": True, "return_validated": False}},
    [None],
)[0]["reason"] == "walking_connector_unverified"
print("Night-stage candidate diagnostics distinguish unsearched, distant and unverified walk: OK")


# Cold benchmark Nantua exposed a source-backed night candidate around 2.8 km
# in a straight line from the stage end. The previous 2.8-km gate never even
# asked the walking Matrix whether a legitimate <=4-km pedestrian connector
# exists. Open a narrow 3.2-km *candidate check*, never a presumed shortcut.
assert logistics._WALK_CONNECTOR_LIMIT_KM == 3.2
borderline = {
    "name": "Camping proche à vérifier",
    "source_url": "https://www.openstreetmap.org/node/771001",
    "lat": 0.027, "lon": 0.0,
    "_night": 1, "_anchor": {"lat": 0.0, "lon": 0.0},
    "_anchor_distance_km": 3.0,
}
verified_borderline, checked_meta = logistics._validate_night_options(
    FakeORS, FakeLegacy, FakeRoundtrip, coords, {1: [borderline]}
)
key = logistics._connector_key(borderline)
assert checked_meta["connector_matrix_calls"] == 1, checked_meta
assert checked_meta["connector_candidates_checked"] == 1, checked_meta
assert verified_borderline[key]["validated"] is True
assert verified_borderline[key]["return_validated"] is True
selected_borderline = logistics._assign_verified_nights(
    {1: [borderline]}, verified_borderline, [15.0, 15.0], 20.0, True
)
assert selected_borderline[0]["_access_mode"] == "walk", selected_borderline

# Slightly farther away, no connector call is made; do not widen the walk
# guarantee beyond the verified pedestrian limit or consume extra API quota.
out_of_range = {**borderline, "_anchor_distance_km": 3.3}
unused, unused_meta = logistics._validate_night_options(
    FakeORS, FakeLegacy, FakeRoundtrip, coords, {1: [out_of_range]}
)
assert unused == {} and unused_meta["connector_matrix_calls"] == 0, unused_meta
# Even a technically valid walking route longer than four kilometres must not
# turn a distant camp into an on-foot overnight or an altered hiking backbone.
too_long = {key: {"validated": True, "return_validated": True,
                  "distance_km": 4.1, "return_distance_km": 4.1}}
rejected = logistics._assign_verified_nights(
    {1: [borderline]}, too_long, [15.0, 15.0], 21.0, True
)
assert rejected == [None], rejected
print("Borderline 3.2km candidates get one bounded round-trip check, never a fake 4km walking connection: OK")


# A loop can cross itself or return next to an earlier portion. The POI's
# closest projected route-progress can be on day 1 even though the actual
# stage-end anchor on day 3 is just metres away. This is a real candidate, not
# a confirmed hiking connector: the ORS walking matrix remains mandatory.
crossing_anchor = [{"night": 2, "lat": 0.0, "lon": 0.200,
                    "route_progress_km": 46.0}]
crossing_stay = {
    "name": "Gîte près du deuxième passage",
    "lat": 0.001, "lon": 0.200,
    "_route_progress_km": 3.0,
    "source_url": "https://www.openstreetmap.org/node/771003",
}
crossing_candidates = logistics._night_options(
    crossing_anchor, [crossing_stay], 15.0
)
assert len(crossing_candidates[2]) == 1, crossing_candidates
assert crossing_candidates[2][0]["_progress_gap_km"] == 43.0
assert crossing_candidates[2][0]["_anchor_distance_km"] < 0.3
# A remotely located candidate still cannot bypass the stage-progress window.
far_crossing_stay = {**crossing_stay, "lat": 0.25,
                     "source_url": "https://www.openstreetmap.org/node/771004"}
assert logistics._night_options(
    crossing_anchor, [far_crossing_stay], 15.0
)[2] == []
# No unvalidated or one-way walk may certify the geographically close place.
no_pedestrian_proof = logistics._assign_verified_nights(
    {1: crossing_candidates[2]}, {}, [15.0, 15.0], 20.0, True
)
assert no_pedestrian_proof == [None], no_pedestrian_proof
print("Loop intersection stay candidate no longer lost, walking checks still mandatory: OK")


# Stage boundaries can move a few kilometres toward REAL sourced lodging
# BEFORE any connector calls. Geometry and route length must remain unchanged;
# a source-linked stay nearby is still NOT proof of walking access.
template_stages=[{"day":i+1,"distance_km":20.0} for i in range(5)]
fixed_anchors=logistics._night_anchors(
    FakeRoundtrip,coords,5,template_stages)
stay_22={"name":"Camping à 22 km","lat":0.001,"lon":0.22,
         "category":"camping","source_url":"https://www.openstreetmap.org/node/880022",
         "_route_progress_km":22.0,"_offroute_km":0.1}
candidate_plan,diag=logistics._source_aware_stage_plan(
    FakeRoundtrip,coords,template_stages,fixed_anchors,
    [stay_22],5,25.0)
assert diag["changed"] is True,diag
assert diag["matched_nights"]==1,diag
assert abs(candidate_plan["lengths"][0]-22.0)<0.02,candidate_plan
assert abs(candidate_plan["lengths"][1]-18.0)<0.02,candidate_plan
assert abs(sum(candidate_plan["lengths"])-100.0)<0.0001
assert candidate_plan["matched_nights"]==[1]
assert all(stage["distance_km"]==20.0 for stage in template_stages)
assert coords==base_result["route_preview"]["coords"]
shifted_anchors=logistics._night_anchors(
    FakeRoundtrip,coords,5,
    [{"distance_km":km} for km in candidate_plan["lengths"]])
assert abs(shifted_anchors[0]["route_progress_km"]-22.0)<0.01
# The following original ORS checks remain mandatory: a close OSM camp is
# still a transfer candidate if ORS does not validate the walking connector.
shifted_options=logistics._night_options(shifted_anchors,[stay_22],20.0)
assert len(shifted_options[1])==1,shifted_options
assert logistics._assign_verified_nights(
    {1:shifted_options[1]}, {}, [22.0,18.0],25.0,True
)==[None]
# Never split using an AI-guessed place, a distant campsite, or old stage
# metadata whose own geometry cannot safely be regenerated here.
for untrusted in (
    {**stay_22,"source_url":""},
    {**stay_22,"_offroute_km":0.9},
    {**stay_22,"_route_progress_km":30.0},
):
    rejected,reason=logistics._source_aware_stage_plan(
        FakeRoundtrip,coords,template_stages,fixed_anchors,
        [untrusted],5,25.0)
    assert rejected is None and not reason["changed"],reason
no_shape,reason=logistics._source_aware_stage_plan(
    FakeRoundtrip,coords,[{**x,"coords":[[0,0],[0,1]]} for x in template_stages],
    fixed_anchors,[stay_22],5,25.0)
assert no_shape is None and reason["reason"]=="stage_geometry_owned_elsewhere"
# Hard 20 km/day limit blocks even a 2 km shift.
strict_plan,_=logistics._source_aware_stage_plan(
    FakeRoundtrip,coords,template_stages,fixed_anchors,
    [stay_22],5,20.0)
assert strict_plan is None
# No invented route length if prior stage sums disagree with route geometry.
invalid_plan,reason=logistics._source_aware_stage_plan(
    FakeRoundtrip,coords,[{"distance_km":30.0} for _ in range(5)],
    fixed_anchors,[stay_22],5,40.0)
assert invalid_plan is None and reason["reason"]=="route_stage_distance_mismatch"
# Drinking-water and groceries are tie-breakers, not falsely validated
# overnight access and not independently trusted when missing an OSM link.
near_water={"name":"Public drinking fountain","lat":0.001,"lon":0.225,
            "category":"water","water_status":"potable_referenced",
            "source_url":"https://www.openstreetmap.org/node/880101",
            "osm_tags":{"amenity":"drinking_water"}}
near_food={"name":"Village grocery","lat":0.001,"lon":0.224,
           "category":"food","source_url":"https://www.openstreetmap.org/node/880102",
           "osm_tags":{"shop":"convenience"}}
similar_stay={**stay_22,"name":"Camping à 21,5 km",
              "source_url":"https://www.openstreetmap.org/node/880023",
              "_route_progress_km":21.5,"lon":0.215}
with_resources,_=logistics._source_aware_stage_plan(
    FakeRoundtrip,coords,template_stages,fixed_anchors,
    [similar_stay,stay_22],5,25.0,
    resource_rows=[near_water,near_food])
assert abs(with_resources["progress"][0]-22.0)<0.02,with_resources
print("Source-aware stage boundary planner: real campsite/water/shop, hard daily limits, immutable pedestrian geometry and ORS walk validation: PASS")
