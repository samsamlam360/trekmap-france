"""TrekBrain v9 field suite: 40 realistic request-understanding scenarios.

The suite runs without live providers so it is safe as a mandatory CI gate. It
checks the exact production reconciliation + intent stack against contradictory
form values, natural-language distances, route shapes, resources and logistics.
"""
from __future__ import annotations

import os
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("TREKBRAIN_VERSION", "v9")
os.environ.setdefault("TREKBRAIN_FREE_MODE", "1")
os.environ.setdefault("ORS_API_KEY", "ci-placeholder")

from backend import smart_planner_v7 as v7  # noqa: E402
from backend import trekbrain_request_v9 as request_v9  # noqa: E402
from backend.language_engine import normalize_for_planner  # noqa: E402
from backend.trekbrain_pipeline_core_v9 import _rebalance_stage_count  # noqa: E402
from backend import trekbrain_roundtrip_v9 as roundtrip_v9  # noqa: E402
from backend.free_planner_v2 import AIPlanRequest  # noqa: E402
from backend.trekbrain_field_contract_v9 import FIELD_SCENARIOS, FIELD_SCENARIO_COUNT  # noqa: E402


PLACES = {
    "belle ile": {"name": "Belle-Île-en-Mer", "short_name": "Belle-Île-en-Mer", "lat": 47.3331, "lon": -3.1870},
    "mont saint michel": {"name": "Mont Saint-Michel", "short_name": "Mont Saint-Michel", "lat": 48.6361, "lon": -1.5115},
    "mont st michel": {"name": "Mont Saint-Michel", "short_name": "Mont Saint-Michel", "lat": 48.6361, "lon": -1.5115},
    "chartres": {"name": "Chartres", "short_name": "Chartres", "lat": 48.4469, "lon": 1.4890},
    "tours": {"name": "Tours", "short_name": "Tours", "lat": 47.3941, "lon": 0.6848},
    "chinon": {"name": "Chinon", "short_name": "Chinon", "lat": 47.1670, "lon": 0.2428},
    "paris": {"name": "Paris", "short_name": "Paris", "lat": 48.8566, "lon": 2.3522},
    "bretagne": {"name": "Bretagne", "short_name": "Bretagne", "lat": 48.20, "lon": -2.93},
    "vercors": {"name": "Vercors", "short_name": "Vercors", "lat": 44.97, "lon": 5.55},
    "touraine": {"name": "Touraine", "short_name": "Touraine", "lat": 47.28, "lon": 0.47},
}


def fake_geocode(query):
    text = request_v9._fold(query).replace("-", " ").replace("’", " ").replace("'", " ")
    for key, row in PLACES.items():
        if key in text:
            return [dict(row)]
    return []


def close_enough(actual, expected):
    if isinstance(expected, float):
        try:
            return abs(float(actual) - expected) <= 0.11
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str):
        return request_v9._fold(str(actual or "")) == request_v9._fold(expected)
    return actual == expected


real_geocode = request_v9.geo._geocode
request_v9.geo._geocode = fake_geocode
failures = []
try:
    for case in FIELD_SCENARIOS:
        base = {
            "prompt": case["prompt"],
            "region": "Chartres",
            "days": 3,
            "daily_km": 18,
            "difficulty": "medium",
            "route_type": "Boucle",
            "require_transit": True,
            "require_water": True,
            "require_accommodation": True,
            "require_food": True,
        }
        base.update(case.get("base") or {})
        data = AIPlanRequest(**base)
        resolved, meta = request_v9.reconcile_request(data)
        intent = v7.v5.v3._parse_intent(resolved)

        for key, expected in (case.get("resolved") or {}).items():
            actual = getattr(resolved, key)
            if not close_enough(actual, expected):
                failures.append(f"{case['id']}: resolved.{key}={actual!r}, expected {expected!r}")

        for key, expected in (case.get("meta") or {}).items():
            actual = meta.get(key)
            if not close_enough(actual, expected):
                failures.append(f"{case['id']}: meta.{key}={actual!r}, expected {expected!r}")

        for key, expected in (case.get("expect") or {}).items():
            actual = intent.get(key)
            if not close_enough(actual, expected):
                failures.append(f"{case['id']}: intent.{key}={actual!r}, expected {expected!r}")

        # The two production interpreters must agree on shape after reconciliation.
        if "route_type" in (case.get("resolved") or {}) or "route_type" in (case.get("expect") or {}):
            if request_v9._fold(resolved.route_type) != request_v9._fold(intent.get("route_type")):
                failures.append(
                    f"{case['id']}: reconciliation={resolved.route_type!r} but parser={intent.get('route_type')!r}"
                )
finally:
    request_v9.geo._geocode = real_geocode

if FIELD_SCENARIO_COUNT != 40:
    failures.append(f"field scenario count changed unexpectedly: {FIELD_SCENARIO_COUNT}")

# Matching written/form regions must not trigger a redundant geocoder call in
# the request-reconciliation layer. The geographic planner will geocode once
# later when it actually needs coordinates.
real_request_geocode = request_v9.geo._geocode
matching_geocode_calls = []
def forbidden_matching_geocode(query):
    matching_geocode_calls.append(query)
    raise AssertionError(f"redundant reconciliation geocode: {query}")

request_v9.geo._geocode = forbidden_matching_geocode
try:
    sancy_req = AIPlanRequest(
        prompt="Je veux une rando dans le massif du Sancy en 3 jours, 17 km par jour.",
        region="Massif du Sancy",
        days=3,
        daily_km=17,
        difficulty="medium",
        route_type="Boucle",
    )
    sancy_resolved, sancy_meta = request_v9.reconcile_request(sancy_req)
finally:
    request_v9.geo._geocode = real_request_geocode

if matching_geocode_calls:
    failures.append(f"matching region geocoded redundantly: {matching_geocode_calls!r}")
if sancy_resolved.region != "Massif du Sancy":
    failures.append(f"matching region changed unexpectedly: {sancy_resolved.region!r}")
if sancy_meta.get("reason") != "explicit-route-area-form-match":
    failures.append(f"matching region reason={sancy_meta.get('reason')!r}")
if not request_v9._same_place_hint("lac des Settons", "Lac des Settons, Morvan"):
    failures.append("same-place lexical regression for Lac des Settons/Morvan")

# Explicit point-to-point phrasing must override stale geographic context.
corridor_req = AIPlanRequest(
    prompt=(
        "Je veux aller de Tours à Chinon à pied en 3 jours, environ 22 km par jour. "
        "Ce n'est pas une boucle."
    ),
    region="Chartres",
    days=3,
    daily_km=22,
    difficulty="medium",
    route_type="Boucle",
)
corridor_intent = v7.v5.v3._parse_intent(corridor_req)
if request_v9._fold(corridor_intent.get("start_query")) != "tours":
    failures.append(f"corridor regression: start={corridor_intent.get('start_query')!r}")
if request_v9._fold(corridor_intent.get("end_query")) != "chinon":
    failures.append(f"corridor regression: end={corridor_intent.get('end_query')!r}")
midpoint = v7.v5.v3._corridor_center(PLACES["tours"], PLACES["chinon"])
if abs(float(midpoint["lat"]) - 47.28055) > 0.01 or abs(float(midpoint["lon"]) - 0.4638) > 0.01:
    failures.append(f"corridor regression: midpoint={midpoint!r}")

# Internal-strategy isolation regression. TrekBrain may append soft planning
# advice containing words such as "campings", "refuges" or "sportif"; these are
# not user constraints and must not silently change accommodation/difficulty.
strategy_req = AIPlanRequest(
    prompt=(
        "Je veux une boucle de 2 jours autour du Mont-Saint-Michel, 16 km par jour, "
        "avec un hébergement."
        "\n\nPriorité interne TrekBrain : logistique. "
        "Privilégier campings ou refuges et un parcours sportif si pertinent."
    ),
    region="Mont Saint-Michel",
    days=2,
    daily_km=16,
    difficulty="medium",
    route_type="Boucle",
    require_accommodation=True,
)
strategy_intent = v7.v5.v3._parse_intent(strategy_req)
if strategy_intent.get("accommodation") != "balanced":
    failures.append(
        f"strategy isolation regression: accommodation={strategy_intent.get('accommodation')!r}"
    )
if strategy_intent.get("difficulty") != "medium":
    failures.append(
        f"strategy isolation regression: difficulty={strategy_intent.get('difficulty')!r}"
    )
if strategy_intent.get("days") != 2 or abs(float(strategy_intent.get("daily_target") or 0) - 16.0) > 0.11:
    failures.append(f"strategy isolation regression: numeric intent={strategy_intent!r}")

normalized_strategy, _ = normalize_for_planner(strategy_req.prompt)
normalized_strategy_intent = v7.v5.v3._parse_intent(
    strategy_req.model_copy(update={"prompt": normalized_strategy})
)
if normalized_strategy_intent.get("accommodation") != "balanced":
    failures.append(
        "normalized strategy isolation regression: "
        f"accommodation={normalized_strategy_intent.get('accommodation')!r}"
    )
if normalized_strategy_intent.get("difficulty") != "medium":
    failures.append(
        "normalized strategy isolation regression: "
        f"difficulty={normalized_strategy_intent.get('difficulty')!r}"
    )

# Language regression: a terrain constraint using the verb "traverser" is not
# a request for a route type "Traversée".
normalized, _ = normalize_for_planner(
    "Boucle autour du Mont-Saint-Michel. Je ne veux pas traverser la baie à pied."
)
if "traversee" in normalized:
    failures.append(f"language regression: traverser became route-shape noun: {normalized!r}")

# Post-route corridor resources must enrich logistics without becoming route
# waypoints. Mock Photon so CI stays deterministic and network-free.
old_request_json = v7.v5.v3._request_json
try:
    def fake_route_resource_json(url, **kwargs):
        params = kwargs.get("params") or {}
        if "/api/" not in str(url):
            raise AssertionError(f"post-route Photon should use forward API, got {url!r}")
        if not params.get("q") and not params.get("include"):
            raise AssertionError(f"post-route Photon selector missing: {params!r}")
        if "lat" not in params or "lon" not in params:
            raise AssertionError(f"post-route Photon bias missing: {params!r}")
        if "osm_tag" in params:
            raise AssertionError(f"post-route Photon must not use legacy osm_tag: {params!r}")

        query = str(params.get("q") or "").casefold()
        include = str(params.get("include") or "").casefold()

        # Structured route resources now use Photon's include=osm.* filter with
        # a local exact-tag validation. Named lodging fallbacks may still use q.
        if "osm.railway.station" in include or "gare" in query:
            name, key, value = ("Gare test", "railway", "station")
        elif "osm.amenity.drinking_water" in include or "fontaine" in query:
            name, key, value = ("Fontaine test", "amenity", "drinking_water")
        elif (
            "osm.shop.supermarket" in include
            or "osm.shop.convenience" in include
            or "osm.shop.bakery" in include
            or "boulanger" in query
            or "supermarch" in query
            or "épicer" in query
            or "epicer" in query
        ):
            name, key, value = ("Épicerie test", "shop", "convenience")
        elif "osm.tourism.camp_site" in include or "camping" in query:
            name, key, value = ("Camping test", "tourism", "camp_site")
        elif "osm.tourism.hotel" in include or "hotel" in query or "gîte" in query or "gite" in query:
            name, key, value = ("Hébergement test", "tourism", "hotel")
        else:
            name, key, value = ("Refuge test", "tourism", "wilderness_hut")
        tag = f"{key}:{value}"
        return {
            "features": [{
                "properties": {
                    "name": name,
                    "countrycode": "FR",
                    "osm_type": "N",
                    "osm_id": abs(hash((tag, params.get("lat"), params.get("lon")))) % 100000 + 1,
                    "osm_key": key,
                    "osm_value": value,
                },
                "geometry": {
                    "coordinates": [float(params.get("lon")), float(params.get("lat"))],
                },
            }]
        }

    v7.v5.v3._request_json = fake_route_resource_json
    resource_bounds = [
        dict(PLACES["tours"]),
        {"name": "Repère 1", "lat": 47.31, "lon": 0.53, "category": "route_split"},
        {"name": "Repère 2", "lat": 47.22, "lon": 0.36, "category": "route_split"},
        dict(PLACES["chinon"]),
    ]
    resource_intent = {
        "transit": True,
        "water": True,
        "food": True,
        "sleep": True,
        "accommodation": "balanced",
    }
    enriched_resources = v7.v5.v3._postroute_corridor_resources(
        resource_bounds, resource_intent, []
    )
    cats = {x.get("category") for x in enriched_resources}
    if "transit" not in cats:
        failures.append(f"post-route resources regression: no transit {enriched_resources!r}")
    if "water" not in cats:
        failures.append(f"post-route resources regression: no water {enriched_resources!r}")
    if "food" not in cats:
        failures.append(f"post-route resources regression: no food {enriched_resources!r}")
    if not ({"camping", "refuge", "lodging"} & cats):
        failures.append(f"post-route resources regression: no stay {enriched_resources!r}")
    if any(not str(x.get("source_url") or "").startswith("https://www.openstreetmap.org/") for x in enriched_resources):
        failures.append(f"post-route resources regression: bad source {enriched_resources!r}")
finally:
    v7.v5.v3._request_json = old_request_json

# Structured Photon categories are the reliable primary selector for known OSM
# resource tags. Keep the new local bbox, while named lodging overrides remain
# text searches.
structured_calls = []
old_structured_request = v7.v5.v3._request_json
try:
    def fake_structured_photon(url, **kwargs):
        params = kwargs.get("params") or {}
        structured_calls.append(dict(params))
        osm_tag = request_v9._fold(str(params.get("osm_tag") or ""))
        query = request_v9._fold(str(params.get("q") or ""))
        if not params.get("bbox"):
            raise AssertionError(f"Photon resource request must stay bbox-bounded: {params!r}")
        if osm_tag == "tourism camp site":
            name, key, value = "Camping structuré", "tourism", "camp_site"
        elif osm_tag == "amenity drinking water":
            name, key, value = "Fontaine structurée", "amenity", "drinking_water"
        elif "hotel" in query:
            name, key, value = "Hôtel nommé", "tourism", "hotel"
        else:
            raise AssertionError(f"unexpected Photon selector: {params!r}")
        return {
            "features": [{
                "properties": {
                    "name": name,
                    "countrycode": "FR",
                    "osm_type": "N",
                    "osm_id": 12345 + len(structured_calls),
                    "osm_key": key,
                    "osm_value": value,
                },
                "geometry": {"coordinates": [2.82, 45.53]},
            }]
        }

    v7.v5.v3._request_json = fake_structured_photon
    structured_camp = v7.v5.v3._photon_anchor_resource(
        {"name": "Repère", "lat": 45.53, "lon": 2.82, "category": "route_anchor"},
        "stay",
        ("tourism:camp_site", "tourism:caravan_site"),
        8.0,
    )
    structured_water = v7.v5.v3._photon_anchor_resource(
        {"name": "Repère", "lat": 45.53, "lon": 2.82, "category": "route_anchor"},
        "water",
        ("amenity:drinking_water", "man_made:water_tap", "natural:spring"),
        4.0,
    )
    named_lodging = v7.v5.v3._photon_anchor_resource(
        {"name": "Repère", "lat": 45.53, "lon": 2.82, "category": "route_anchor"},
        "stay",
        ("tourism:hotel", "tourism:hostel", "tourism:guest_house"),
        12.5,
        query_override="hotel",
    )
finally:
    v7.v5.v3._request_json = old_structured_request

if not structured_camp or structured_camp.get("category") != "camping":
    failures.append(f"Photon structured camping regression: {structured_camp!r}")
if not structured_water or structured_water.get("category") != "water":
    failures.append(f"Photon structured water regression: {structured_water!r}")
if not named_lodging or named_lodging.get("category") != "lodging":
    failures.append(f"Photon named lodging regression: {named_lodging!r}")
if len(structured_calls) != 3:
    failures.append(f"Photon structured call count regression: {structured_calls!r}")
elif (
    structured_calls[0].get("osm_tag") != "tourism:camp_site"
    or request_v9._fold(str(structured_calls[0].get("q") or "")) != "camping"
    or structured_calls[1].get("osm_tag") != "amenity:drinking_water"
    or request_v9._fold(str(structured_calls[1].get("q") or "")) != "fontaine"
    or structured_calls[2].get("osm_tag")
    or request_v9._fold(str(structured_calls[2].get("q") or "")) != "hotel"
):
    failures.append(f"Photon structured/text selector regression: {structured_calls!r}")

# Explicit traverses may recover a validated route by splitting its existing
# geometry into equal-progress days. No new path geometry may be invented.
split_route = [
    [47.3941, 0.6848],
    [47.36, 0.62],
    [47.32, 0.55],
    [47.28, 0.47],
    [47.24, 0.39],
    [47.20, 0.31],
    [47.1670, 0.2428],
]
split_bounds = v7.v5.v3._equal_progress_boundaries(
    split_route, PLACES["tours"], PLACES["chinon"], 3
)
if len(split_bounds) != 4:
    failures.append(f"corridor split regression: boundaries={split_bounds!r}")
elif (
    abs(float(split_bounds[0]["lat"]) - PLACES["tours"]["lat"]) > 1e-6
    or abs(float(split_bounds[-1]["lat"]) - PLACES["chinon"]["lat"]) > 1e-6
):
    failures.append(f"corridor split regression: endpoints changed {split_bounds!r}")
elif any(
    [round(float(row["lat"]), 6), round(float(row["lon"]), 6)]
    not in [[round(p[0], 6), round(p[1], 6)] for p in split_route]
    for row in split_bounds[1:-1]
):
    failures.append(f"corridor split regression: off-route boundary {split_bounds!r}")

# Stage-count regression: a validated two-stage geometry can safely be exposed
# as three requested hiking days without redrawing the route.
fake = {
    "start": {"name": "Tours", "lat": 47.39, "lon": 0.68},
    "end": {"name": "Chinon", "lat": 47.17, "lon": 0.24},
    "stages": [
        {"day": 1, "distance_km": 24.0},
        {"day": 2, "distance_km": 25.0},
    ],
    "route_preview": {
        "fallback": False,
        "distance_km": 49.0,
        "coords": [
            [47.39, 0.68], [47.34, 0.58], [47.29, 0.48],
            [47.24, 0.37], [47.17, 0.24],
        ],
    },
    "accommodations": [],
    "advisor_notes": [],
}
_rebalance_stage_count(fake, {"days": 3})
if len(fake.get("stages") or []) != 3 or fake.get("duration_days") != 3:
    failures.append(f"stage rebalance regression: {fake.get('stages')!r}")

# Raw ORS round-trip regression. A validated oversized loop that bypasses the
# normal candidate ranker must be recalibrated before daily-stage validation.
old_roundtrip_request = roundtrip_v9._roundtrip_request
old_matrix_subloops = roundtrip_v9._matrix_subloop_candidates
try:
    calibration_calls = []

    def fake_roundtrip_request(start, requested_km, seed):
        calibration_calls.append((round(float(requested_km), 2), int(seed)))
        return {
            "coords": [
                [48.0, 1.0], [48.08, 1.08], [48.02, 1.16],
                [47.94, 1.08], [48.0, 1.0],
            ],
            "distance": 34.0,
            "fallback": False,
            "routing_mode": "ors-round-trip",
            "round_trip_seed": int(seed),
        }, None

    roundtrip_v9._roundtrip_request = fake_roundtrip_request
    roundtrip_v9._matrix_subloop_candidates = lambda *args, **kwargs: []
    recovered = roundtrip_v9._recover_unranked_oversized_roundtrip(
        {
            "coords": [
                [48.0, 1.0], [48.12, 1.12], [48.0, 1.24],
                [47.88, 1.12], [48.0, 1.0],
            ],
            "distance": 50.0,
            "fallback": False,
            "routing_mode": "ors-round-trip",
        },
        {"lat": 48.0, "lon": 1.0},
        32.0, 12.0, 20.0, 2, v7.v5.v3,
    )
    if float(recovered.get("distance") or 0) != 34.0:
        failures.append(f"raw round-trip recovery regression: {recovered!r}")
    elif recovered.get("raw_roundtrip_recovery") is not True:
        failures.append("raw round-trip recovery regression: metadata missing")
    elif not calibration_calls or calibration_calls[0][0] >= 32.0:
        failures.append(f"raw round-trip recovery regression: no downward calibration {calibration_calls!r}")
finally:
    roundtrip_v9._roundtrip_request = old_roundtrip_request
    roundtrip_v9._matrix_subloop_candidates = old_matrix_subloops

# Oversized-loop regression. The shortening layer must only return geometry
# closed through a routed connector, never through a direct diagnostic segment.
old_get_route = roundtrip_v9.ors.get_route
try:
    def fake_connector(points, distance_fn):
        a, b = points
        return {
            "coords": [list(a), [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], list(b)],
            "distance": max(2.0, float(distance_fn(points)) * 1.15),
            "fallback": False,
            "routing_mode": "test-routed-connector",
            "profile": "foot-hiking",
        }

    roundtrip_v9.ors.get_route = fake_connector
    centre = {"lat": 48.0, "lon": 1.0}
    ring = []
    for n in range(73):
        angle = 2 * math.pi * n / 72
        ring.append([48.0 + 0.10 * math.sin(angle), 1.0 + 0.14 * math.cos(angle)])
    oversized = {"coords": ring, "distance": 58.0, "fallback": False, "profile": "foot-hiking"}
    variants = roundtrip_v9._shorten_oversized_loop(
        oversized, centre, 36.0, 12.0, 20.0, 2, v7.v5.v3
    )
    if not variants or not all(x.get("fallback") is False for x in variants):
        failures.append("round-trip shortening regression: no routed shortened loop")
    elif not any(21.6 <= float(x.get("distance") or 0) <= 40.35 for x in variants):
        failures.append(
            f"round-trip shortening regression: bad distances {[x.get('distance') for x in variants]}"
        )
finally:
    roundtrip_v9.ors.get_route = old_get_route

# Matrix compact-subloop regression: reuse real sampled points and select a
# shorter closed cycle before falling back to arc replacement.
old_get_route = roundtrip_v9.ors.get_route
old_get_matrix = roundtrip_v9.ors.get_distance_matrix
try:
    def fake_compact_matrix(points):
        n = len(points)
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    matrix[i][j] = 5.0 + abs(i - j) * 1.2
        return {"distances": matrix, "fallback": False}

    def fake_compact_route(points, distance_fn):
        return {
            "coords": [list(x) for x in points],
            "distance": 33.0,
            "fallback": False,
            "routing_mode": "test-compact",
            "profile": "foot-hiking",
        }

    roundtrip_v9.ors.get_distance_matrix = fake_compact_matrix
    roundtrip_v9.ors.get_route = fake_compact_route
    ring = []
    for n in range(145):
        angle = 2 * math.pi * n / 144
        ring.append([48.0 + 0.11 * math.sin(angle), 1.0 + 0.16 * math.cos(angle)])
    compact = roundtrip_v9._matrix_subloop_candidates(
        {"coords": ring, "distance": 58.0, "fallback": False},
        {"lat": ring[0][0], "lon": ring[0][1]},
        32.0, 12.0, 20.0, 2, v7.v5.v3,
    )
    if not compact:
        failures.append("matrix compact-subloop regression: no candidate")
    elif compact[0].get("routing_mode") != "ors-matrix-subloop":
        failures.append(f"matrix compact-subloop regression: bad mode {compact[0]!r}")
    elif float(compact[0].get("distance") or 0) != 33.0:
        failures.append(f"matrix compact-subloop regression: bad distance {compact[0]!r}")
finally:
    roundtrip_v9.ors.get_route = old_get_route
    roundtrip_v9.ors.get_distance_matrix = old_get_matrix

# Matrix-first internal-arc shortcut regression. The planner must evaluate many
# on-route pairs with one Matrix call and render only the selected connector.
old_get_route = roundtrip_v9.ors.get_route
old_get_matrix = roundtrip_v9.ors.get_distance_matrix
try:
    def fake_arc_matrix(points):
        n = len(points)
        distances = []
        for i in range(n):
            row = []
            for j in range(n):
                if i == j:
                    row.append(0.0)
                else:
                    # A usable network shortcut whose cost grows much more slowly
                    # than the removed arc.
                    row.append(2.0 + abs(j - i) * 1.25)
            distances.append(row)
        return {"distances": distances, "fallback": False, "routing_mode": "test-matrix"}

    def fake_arc_connector(points, distance_fn):
        a, b = points
        mid = [(a[0] + b[0]) / 2 + 0.002, (a[1] + b[1]) / 2]
        return {
            "coords": [list(a), mid, list(b)],
            "distance": max(2.0, float(distance_fn(points)) * 1.10),
            "fallback": False,
            "routing_mode": "test-arc-connector",
            "profile": "foot-hiking",
        }

    roundtrip_v9.ors.get_distance_matrix = fake_arc_matrix
    roundtrip_v9.ors.get_route = fake_arc_connector
    ring = []
    for n in range(145):
        angle = 2 * math.pi * n / 144
        ring.append([48.0 + 0.11 * math.sin(angle), 1.0 + 0.16 * math.cos(angle)])
    centre = {"lat": ring[0][0], "lon": ring[0][1]}
    oversized = {"coords": ring, "distance": 58.0, "fallback": False, "profile": "foot-hiking"}
    shortcuts = roundtrip_v9._shortcut_oversized_loop(
        oversized, centre, 36.0, 12.0, 20.0, 2, v7.v5.v3
    )
    if not shortcuts:
        failures.append("matrix arc-shortcut regression: no routed variant")
    elif not all(x.get("routing_mode") == "ors-matrix-arc-shortcut" for x in shortcuts):
        failures.append(f"matrix arc-shortcut regression: bad mode {shortcuts!r}")
    elif not all(x.get("matrix_shortcut") is True for x in shortcuts):
        failures.append("matrix arc-shortcut regression: Matrix metadata missing")
    elif not any(float(x.get("distance") or 0) < 58.0 for x in shortcuts):
        failures.append(f"matrix arc-shortcut regression: loop was not shortened {shortcuts!r}")
finally:
    roundtrip_v9.ors.get_route = old_get_route
    roundtrip_v9.ors.get_distance_matrix = old_get_matrix

# Routed waypoint-loop regression: when provider round-trip length is unreliable,
# the fallback must be able to create a closed candidate from routed waypoints.
old_get_route = roundtrip_v9.ors.get_route
try:
    def fake_waypoint_route(points, distance_fn):
        distance = float(distance_fn(points)) * 1.38
        return {
            "coords": [list(p) for p in points],
            "distance": distance,
            "fallback": False,
            "routing_mode": "test-waypoint-routing",
            "profile": "foot-hiking",
        }

    roundtrip_v9.ors.get_route = fake_waypoint_route
    polygon = roundtrip_v9._polygon_loop_candidates(
        {"lat": 48.0, "lon": 1.0}, 32.0, 12.0, 20.0, 2, v7.v5.v3
    )
    if not polygon:
        failures.append("waypoint-loop regression: no routed candidate")
    elif polygon[0].get("routing_mode") != "ors-waypoint-loop":
        failures.append(f"waypoint-loop regression: bad mode {polygon[0]!r}")
    elif roundtrip_v9._haversine(polygon[0]["coords"][0], polygon[0]["coords"][-1]) > 0.15:
        failures.append("waypoint-loop regression: route is not closed")
    elif "waypoint_retrace_ratio" not in polygon[0]:
        failures.append("waypoint-loop regression: missing retrace metadata")
finally:
    roundtrip_v9.ors.get_route = old_get_route

# Closed-loop stage regression: plain equal-progress anchors must not be
# re-matched by geographic proximity on a self-crossing loop.
class _FakeLegacy:
    @staticmethod
    def distance_gps(coords):
        return 999.0  # would expose accidental use of the old proximity split

plain_stage_distances = roundtrip_v9._roundtrip_stage_distances(
    [[48.0, 1.0], [48.1, 1.1], [48.0, 1.0], [47.9, 0.9], [48.0, 1.0]],
    [
        {"lat": 48.0, "lon": 1.0},
        {"lat": 48.0, "lon": 1.0, "route_progress_km": 20.0},
        {"lat": 48.0, "lon": 1.0},
    ],
    [],
    2,
    40.0,
    _FakeLegacy(),
    v7.v5.v3,
)
if plain_stage_distances != [20.0, 20.0]:
    failures.append(f"closed-loop stage split regression: {plain_stage_distances!r}")

# Candidate-selection regression: once a genuinely routed shortened loop is
# available inside the distance window, a prettier but oversized ORS loop must
# never win the final ranking.
old_roundtrip_request = roundtrip_v9._roundtrip_request
old_shortener = roundtrip_v9._shorten_oversized_loop
try:
    def fake_roundtrip_request(start, requested_km, seed):
        return {
            "coords": [[48.0, 1.0], [48.1, 1.1], [48.0, 1.2], [48.0, 1.0]],
            "distance": 52.0,
            "fallback": False,
            "routing_mode": "test-oversized",
        }, None

    def fake_shortener(route, start, target_km, daily_min, daily_max, days, v3):
        return [{
            "coords": [[48.0, 1.0], [48.08, 1.08], [48.02, 1.16], [48.0, 1.0]],
            "distance": 34.0,
            "fallback": False,
            "routing_mode": "test-shortened",
        }]

    roundtrip_v9._roundtrip_request = fake_roundtrip_request
    roundtrip_v9._shorten_oversized_loop = fake_shortener
    selected = roundtrip_v9._best_roundtrip(
        {"lat": 48.0, "lon": 1.0}, 32.0, 12.0, 20.0, 2, v7.v5.v3
    )
    if selected.get("routing_mode") != "test-shortened" or float(selected.get("distance") or 0) != 34.0:
        failures.append(f"round-trip feasibility selection regression: {selected!r}")
finally:
    roundtrip_v9._roundtrip_request = old_roundtrip_request
    roundtrip_v9._shorten_oversized_loop = old_shortener

if failures:
    raise AssertionError("TrekBrain v9 field suite failed:\\n- " + "\\n- ".join(failures))

print(f"TrekBrain v9 field suite: {FIELD_SCENARIO_COUNT}/40 realistic request scenarios OK")
