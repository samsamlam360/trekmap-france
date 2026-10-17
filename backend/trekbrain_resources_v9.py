"""TrekBrain v9 resource and geographic-safety overlay.

Adds route-relative map resources (water, campsites, refuges and public
transport), keeps island planning inside the requested island, and refuses to
show or save a route that was not actually validated by the walking router.
"""
from __future__ import annotations

import json
import math
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any

from fastapi import Body, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import text

from . import smart_planner_v7 as v7
from .trekbrain_water_evidence_v9 import (
    confirmed_water_reference, has_osm_identity, water_evidence_status,
    merge_water_evidence,
)
from .trekbrain_geo_safety_v9 import (
    _filter_active,
    activate_region,
    install_geo_filters,
    reset_region,
    route_safety_report,
    safety_error_message,
)


# Stop repeatedly hammering public Overpass mirrors after two complete
# outages. No negative results are cached: one live request retries after the
# cooldown, and any successful provider response resets the breaker.
_OSM_OVERPASS_LOCK = threading.Lock()
_OSM_OVERPASS_FAILURES = 0
_OSM_OVERPASS_COOLDOWN_UNTIL = 0.0
_OSM_OVERPASS_COOLDOWN_SECONDS = 60.0


def _overpass_circuit_open() -> bool:
    with _OSM_OVERPASS_LOCK:
        return time.monotonic() < _OSM_OVERPASS_COOLDOWN_UNTIL


def _overpass_circuit_report(provider_responded: bool) -> None:
    global _OSM_OVERPASS_FAILURES, _OSM_OVERPASS_COOLDOWN_UNTIL
    with _OSM_OVERPASS_LOCK:
        if provider_responded:
            _OSM_OVERPASS_FAILURES = 0
            _OSM_OVERPASS_COOLDOWN_UNTIL = 0.0
        else:
            _OSM_OVERPASS_FAILURES += 1
            if _OSM_OVERPASS_FAILURES >= 2:
                _OSM_OVERPASS_COOLDOWN_UNTIL = (
                    time.monotonic() + _OSM_OVERPASS_COOLDOWN_SECONDS
                )


RESOURCE_LIMITS = {
    "water": 2.8,
    "food": 4.5,
    "camping": 4.0,
    "refuge": 4.0,
    "lodging": 6.2,
    "station": 12.0,
    "transport": 8.0,
    "trail": 2.2,
}
FOOD_SHOPS = {"supermarket", "convenience", "bakery", "general", "grocery",
              "deli", "greengrocer", "food"}


def _confirmed_food_reference(item: dict[str, Any]) -> bool:
    if not has_osm_identity(item):
        return False
    tags = item.get("osm_tags") or {}
    if not isinstance(tags, dict):
        return False
    return (not tags or tags.get("shop") in FOOD_SHOPS) and (
        str(tags.get("access") or "").casefold() not in {"private", "no"}
        and str(tags.get("disused") or "").casefold() != "yes"
    )


class AIRedrawPayload(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=160)
    region: str = Field(min_length=1, max_length=120)
    difficulty: str = Field(default="medium", max_length=20)
    description: str = Field(default="", max_length=10000)
    duration_days: float | None = Field(default=None, ge=0.25, le=365)
    coords: list[list[float]] = Field(min_length=2, max_length=100)


def _number(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _point(item: dict[str, Any] | None) -> tuple[float, float] | None:
    if not isinstance(item, dict):
        return None
    lat, lon = _number(item.get("lat")), _number(item.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _route_distance_profile(coords: list[list[float]]) -> tuple[list[float], float]:
    """Cumulative route distance aligned to coordinate indices.

    Resource day assignment must follow kilometres walked, not the density of
    router geometry points. ORS may emit many points in one technical section
    and few in another, so index/len(coords) is not a reliable route progress.
    """
    if not isinstance(coords, list) or not coords:
        return [], 0.0
    cumulative = [0.0] * len(coords)
    total = 0.0
    previous: tuple[float, float] | None = None
    for index, point in enumerate(coords):
        current = None
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            lat, lon = _number(point[0]), _number(point[1])
            if lat is not None and lon is not None:
                current = (lat, lon)
        if current is not None:
            if previous is not None:
                total += _distance_km(previous, current)
            previous = current
        cumulative[index] = total
    return cumulative, total


def _stage_progress_breaks(result: dict[str, Any], days: int) -> list[float]:
    """Actual walking-day boundaries as route-distance fractions.

    A 12 km day followed by 25 km does not split the trail at 50%.
    Fall back to uniform distances only when stage lengths are unavailable.
    No route geometry or itinerary stage is modified here.
    """
    days = max(1, int(days))
    uniform = [index / days for index in range(days + 1)]
    stages = result.get("stages") or []
    if not isinstance(stages, list) or len(stages) < days:
        return uniform
    lengths = []
    for stage in stages[:days]:
        if not isinstance(stage, dict):
            return uniform
        km = _number(stage.get("distance_km"))
        if km is None or km <= 0:
            return uniform
        lengths.append(km)
    total = sum(lengths)
    if not math.isfinite(total) or total <= 0:
        return uniform
    walked = 0.0
    breaks = [0.0]
    for km in lengths[:-1]:
        walked += km
        breaks.append(walked / total)
    breaks.append(1.0)
    return breaks


def _route_day_from_progress(progress: float, boundaries: list[float]) -> int:
    """Assign exact stage boundaries to the next day's walking section."""
    if not boundaries or len(boundaries) < 2:
        return 1
    progress = max(0.0, min(1.0, float(progress)))
    for day, upper in enumerate(boundaries[1:], start=1):
        if progress < upper or day == len(boundaries) - 1:
            return day
    return len(boundaries) - 1



def _sourced_water_coverage(points: list[dict[str, Any]]) -> tuple[list[int], int]:
    """Referenced drinking water; unknown springs remain display-only context."""
    usable = [
        point for point in points or []
        if isinstance(point, dict)
        and point.get("kind") == "water"
        and confirmed_water_reference(point)
    ]
    days = sorted({
        int(point["route_day"]) for point in usable
        if isinstance(point.get("route_day"), int) and point["route_day"] >= 1
    })
    return days, len(usable)


def _route_match(
    coords: list[list[float]],
    item: dict[str, Any],
    route_profile: tuple[list[float], float] | None = None,
) -> tuple[float, float] | None:
    """Nearest point on walked *segments*, and progress by distance walked.

    The old vertex-only lookup misplaced village stores on sparse polylines:
    a shop a quarter-way down an edge could be classified as day 2, or
    wrongly discarded as several kilometres away from the hiking trail.
    """
    target = _point(item)
    if not target or not isinstance(coords, list) or len(coords) < 2:
        return None
    if route_profile is None:
        route_profile = _route_distance_profile(coords)
    cumulative, total = route_profile
    if len(cumulative) != len(coords):
        cumulative, total = _route_distance_profile(coords)

    # Cap the cost on exceptionally long GPS traces, while preserving both
    # endpoints. Ordinary (<=1400 vertex) routes retain full precision.
    stride = max(1, (len(coords) - 1) // 1400)
    indices = list(range(0, len(coords), stride))
    if indices[-1] != len(coords) - 1:
        indices.append(len(coords) - 1)

    best_distance = float("inf")
    best_progress = 0.0
    for start_index, end_index in zip(indices, indices[1:]):
        first, last = coords[start_index], coords[end_index]
        if not (
            isinstance(first, (list, tuple)) and len(first) >= 2
            and isinstance(last, (list, tuple)) and len(last) >= 2
        ):
            continue
        a_lat, a_lon = _number(first[0]), _number(first[1])
        b_lat, b_lon = _number(last[0]), _number(last[1])
        if None in (a_lat, a_lon, b_lat, b_lon):
            continue
        # Locally planar projection determines the nearest place on an edge.
        # Its distance is then verified with the same haversine metric used
        # everywhere else for route-relative filtering.
        lat_scale = 111.195
        lon_scale = lat_scale * max(0.01, math.cos(math.radians(target[0])))
        dx = (b_lon - a_lon) * lon_scale
        dy = (b_lat - a_lat) * lat_scale
        vx = (target[1] - a_lon) * lon_scale
        vy = (target[0] - a_lat) * lat_scale
        length_sq = dx * dx + dy * dy
        position = (
            max(0.0, min(1.0, (vx * dx + vy * dy) / length_sq))
            if length_sq > 0 else 0.0
        )
        projected = (
            a_lat + (b_lat - a_lat) * position,
            a_lon + (b_lon - a_lon) * position,
        )
        distance = _distance_km(target, projected)
        if distance < best_distance:
            best_distance = distance
            if total > 0:
                walked = (
                    cumulative[start_index]
                    + position * (cumulative[end_index] - cumulative[start_index])
                )
                best_progress = max(0.0, min(1.0, walked / total))
            else:
                best_progress = max(
                    0.0, min(1.0, (start_index + position * (end_index - start_index)) / (len(coords) - 1))
                )
    if not math.isfinite(best_distance):
        return None
    return best_distance, best_progress


def _resource_kind(item: dict[str, Any], fallback: str = "") -> str:
    explicit = str(item.get("category") or item.get("kind") or "").casefold()
    if explicit in {"food", "water"}:
        return explicit
    raw = f"{item.get('type') or ''} {item.get('category') or ''} {item.get('name') or ''} {fallback}".casefold()
    if fallback == "water" or any(x in raw for x in ("eau", "fontaine", "source")):
        return "water"
    if fallback == "food" or any(x in raw for x in ("ravitail", "boulanger", "epicer", "épicer", "supermarch", "convenience", "bakery")):
        return "food"
    if any(x in raw for x in ("camping", "camp_site", "caravan_site", "campement")):
        return "camping"
    if any(x in raw for x in ("refuge", "abri", "gîte", "gite", "hut")):
        return "refuge"
    if any(x in raw for x in ("hébergement", "hebergement", "hotel", "hostel", "guest_house", "auberge")):
        return "lodging"
    if any(x in raw for x in ("gare", "station ferroviaire", "train", "sncf")):
        return "station"
    if fallback == "transport" or any(x in raw for x in ("transport", "bus", "arrêt", "arret")):
        return "transport"
    if any(x in raw for x in ("itinéraire balisé", "itineraire balise", "gr ", "gr®", "sentier")):
        return "trail"
    return fallback or "poi"


def _food_candidates(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Combine both legacy food fields instead of silently dropping one.

    Some route planners write `food`, others `resources`. Both can be
    populated independently during route-first and terrain enrichment. An
    `or` expression silently loses the second list and can hide genuine,
    route-close, source-linked shops from the map and daily stage cards.
    """
    seen: set[tuple[Any, ...]] = set()
    merged: list[dict[str, Any]] = []
    for field in ("resources", "food"):
        for item in result.get(field) or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source_url") or "").strip()
            point = _point(item)
            if source:
                key = ("source", source)
            elif point is not None:
                key = ("location", round(point[0], 5), round(point[1], 5),
                       str(item.get("name") or "").casefold())
            else:
                key = ("label", str(item.get("name") or "").casefold(),
                       str(item.get("type") or "").casefold())
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _cache_source_candidates(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Tag legacy resource lists for persistent OSM storage.

    Existing planners put water, food, and accommodation items in dedicated
    lists without necessarily setting `category`. The cache may store only
    explicitly classified, source-linked types, so normalize the field's
    meaning here before attempting persistence.
    """
    out = []
    for field, default in (
        ("water", "water"), ("food", "food"),
        ("resources", "food"), ("accommodations", "lodging"),
        ("points_of_interest", ""),
    ):
        for item in result.get(field) or []:
            if not isinstance(item, dict):
                continue
            kind = _resource_kind(item, default)
            if kind not in {"water", "food", "camping", "refuge", "lodging"}:
                continue
            out.append({**item, "category": kind})
    return out


def _candidate_resources(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for w in result.get("water") or []:
        if isinstance(w, dict):
            status = water_evidence_status(w)
            unsafe = status == "not_potable"
            items.append({
                **w, "kind": "water", "type": "Point d'eau",
                "status": status, "water_status": status,
                "notes": (
                    "Eau signalée non potable : ne pas boire."
                    if unsafe else w.get("notes") or "Potabilité à vérifier."
                ),
            })
    for a in result.get("accommodations") or []:
        if isinstance(a, dict):
            kind = _resource_kind(a, "lodging")
            items.append({**a, "kind": kind, "notes": a.get("notes") or "Ouverture et disponibilité à vérifier."})
    food_rows = _food_candidates(result)
    for resource in food_rows:
        if isinstance(resource, dict):
            items.append({
                **resource,
                "kind": "food",
                "type": resource.get("type") or "Ravitaillement",
                "notes": resource.get("notes") or "Horaires et disponibilité à vérifier.",
            })
    for p in result.get("points_of_interest") or []:
        if not isinstance(p, dict):
            continue
        kind = _resource_kind(p)
        if kind in {"food", "station", "transport", "trail"}:
            items.append({**p, "kind": kind, "notes": p.get("notes") or "Donnée cartographique ; conditions actuelles à vérifier."})
    return items


def enrich_resources(result: dict[str, Any]) -> dict[str, Any]:
    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    days = max(1, int(result.get("duration_days") or len(result.get("stages") or []) or 1))
    prepared, seen = [], set()
    route_profile = _route_distance_profile(coords)
    day_boundaries = _stage_progress_breaks(result, days)
    candidates = sorted(_candidate_resources(result), key=lambda item: (
        0 if item.get("kind") == "water" and water_evidence_status(item) == "not_potable" else 1
    ))
    for item in candidates:
        point = _point(item)
        if not point:
            continue
        kind = str(item.get("kind") or "poi")
        match = _route_match(coords, item, route_profile)
        if not match:
            continue
        distance, progress = match
        limit = RESOURCE_LIMITS.get(kind, 4.0)
        if distance > limit:
            continue
        key = ((kind, item["source_url"]) if has_osm_identity(item) else (
            kind, round(point[0], 5), round(point[1], 5), str(item.get("name") or "").casefold()
        ))
        if key in seen:
            continue
        seen.add(key)
        route_day = _route_day_from_progress(progress, day_boundaries)
        prepared.append({
            "name": str(item.get("name") or "Point")[:160],
            "kind": kind,
            "type": str(item.get("type") or kind)[:80],
            "lat": round(point[0], 6),
            "lon": round(point[1], 6),
            "route_day": route_day,
            "distance_to_route_km": round(distance, 2),
            "status": str(item.get("status") or (item.get("water_status") if kind == "water" else "") or "")[:80],
            "notes": str(item.get("notes") or "")[:500],
            "source_url": str(item.get("source_url") or "")[:1000],
            "osm_tags": dict(item.get("osm_tags") or {})
            if isinstance(item.get("osm_tags"), dict) else {},
        })

    priority = {"water": 0, "food": 1, "camping": 2, "refuge": 3, "lodging": 4, "station": 5, "transport": 6, "trail": 7}
    prepared.sort(key=lambda x: (
        x["route_day"], priority.get(x["kind"], 9),
        0 if (confirmed_water_reference(x) if x["kind"] == "water" else has_osm_identity(x)) else 1,
        x["distance_to_route_km"], x["name"],
    ))

    # Avoid a carpet of icons: keep the closest few of each category per day.
    limited, buckets = [], {}
    per_day_caps = {"water": 3, "food": 3, "camping": 2, "refuge": 2, "lodging": 2, "station": 2, "transport": 3, "trail": 2}
    # Round-robin days before filling extra icons on early stages. A 48-icon
    # display cap must not erase every source on the last day of a long trek.
    display_rows = []
    for rank in range(max(per_day_caps.values())):
        for kind in priority:
            groups = {}
            for item in prepared:
                if item["kind"] == kind:
                    groups.setdefault(item["route_day"], []).append(item)
            if rank < per_day_caps.get(kind, 2):
                display_rows.extend(rows[rank] for rows in groups.values() if len(rows) > rank)
    for item in display_rows:
        bucket = (item["route_day"], item["kind"])
        count = buckets.get(bucket, 0)
        if count >= per_day_caps.get(item["kind"], 2):
            continue
        buckets[bucket] = count + 1
        limited.append(item)
        if len(limited) >= 48:
            break

    counts = {k: 0 for k in ("water", "food", "camping", "refuge", "lodging", "station", "transport", "trail")}
    for item in limited:
        if item["kind"] in counts:
            counts[item["kind"]] += 1

    transport = result.setdefault("transport", {})
    start, end = _point(result.get("start")), _point(result.get("end"))
    mobility = [x for x in limited if x["kind"] in {"station", "transport"}]
    if start and mobility:
        transport["outbound_point"] = min(mobility, key=lambda x: _distance_km(start, (x["lat"], x["lon"])))
    if end and mobility:
        transport["return_point"] = min(mobility, key=lambda x: _distance_km(end, (x["lat"], x["lon"])))

    trails = [x for x in limited if x["kind"] == "trail"]
    result["trail_context"] = {
        "near_route": trails,
        "note": "Les noms de sentiers sont des repères cartographiques proches du tracé. TrekBrain ne prétend pas suivre intégralement un GR sans géométrie de relation vérifiée.",
    }
    result["map_resources"] = {
        "version": "v9.2",
        "points": limited,
        "counts": counts,
        "route_filtered": True,
        "meaning": "Points cartographiques proches d'un tracé pédestre validé. Horaires, ouverture, débit et disponibilité restent à vérifier avant le départ.",
        # Readiness uses all valid references, independently of icon limits.
        "evidence_points": prepared,
    }
    return result




def _route_day_boundaries(result: dict[str, Any], days: int) -> list[dict[str, Any]]:
    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    clean = []
    for point in coords if isinstance(coords, list) else []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        lat, lon = _number(point[0]), _number(point[1])
        if lat is None or lon is None:
            continue
        if not clean or [lat, lon] != clean[-1]:
            clean.append([lat, lon])
    if len(clean) < 2:
        return []

    cumulative = [0.0]
    for a, b in zip(clean, clean[1:]):
        cumulative.append(cumulative[-1] + _distance_km((a[0], a[1]), (b[0], b[1])))
    total = cumulative[-1]
    if total <= 0:
        return []

    start = dict(result.get("start") or {})
    end = dict(result.get("end") or {})
    if _point(start) is None:
        start = {"name": "Départ", "lat": clean[0][0], "lon": clean[0][1], "category": "route_anchor"}
    if _point(end) is None:
        end = {"name": "Arrivée", "lat": clean[-1][0], "lon": clean[-1][1], "category": "route_anchor"}

    boundaries = [start]
    progress_breaks = _stage_progress_breaks(result, days)

    # The planner may return only a few route vertices on a validated walking
    # segment. Nearest-vertex snapping previously placed a four-day trek's
    # overnight anchors at the very start, or returned only start+finish. This
    # deprived the first-visit Photon fallback of actual middle-day villages.
    # Interpolate on the existing walking geometry at each stage-distance
    # fraction. This changes only discovery anchors, never the stored line.
    segment = 1
    for day in range(1, max(1, int(days))):
        target = total * progress_breaks[day]
        while segment < len(clean) - 1 and cumulative[segment] < target:
            segment += 1
        lower, upper = cumulative[segment - 1], cumulative[segment]
        portion = (
            max(0.0, min(1.0, (target - lower) / (upper - lower)))
            if upper > lower else 0.0
        )
        a, b = clean[segment - 1], clean[segment]
        boundaries.append({
            "name": f"Repère jour {day}",
            "lat": a[0] + (b[0] - a[0]) * portion,
            "lon": a[1] + (b[1] - a[1]) * portion,
            "category": "route_anchor",
        })
    boundaries.append(end)
    return boundaries


def _merge_supplemented_resources(result: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return result

    water = list(result.get("water") or [])
    food = _food_candidates(result)
    accommodations = list(result.get("accommodations") or [])
    pois = list(result.get("points_of_interest") or [])
    transit_rows = []

    def add_unique(target, item, *, category=None):
        # Preserve restrictions even when an OSM object already exists in the
        # primary result; don't treat a newly merged point as available water.
        def preserve_newer_unsafe_status(existing):
            if target is water:
                merge_water_evidence(existing, item)

        key = str(item.get("source_url") or "")
        try:
            coords_key = (round(float(item.get("lat")), 5), round(float(item.get("lon")), 5))
        except (TypeError, ValueError):
            coords_key = None
        for existing in target:
            if not isinstance(existing, dict):
                continue
            if key and str(existing.get("source_url") or "") == key:
                preserve_newer_unsafe_status(existing)
                return
            if key and existing.get("source_url"):
                # Separate OSM sources can share a coordinate. In particular,
                # a condemned fountain cannot poison a neighbouring tap.
                continue
            if coords_key is not None:
                try:
                    if (
                        round(float(existing.get("lat")), 5),
                        round(float(existing.get("lon")), 5),
                    ) == coords_key and (category is None or str(existing.get("category") or "") == category):
                        preserve_newer_unsafe_status(existing)
                        return
                except (TypeError, ValueError):
                    pass
        target.append(item)

    for row in rows:
        if not isinstance(row, dict):
            continue
        category = str(row.get("category") or "")
        if category == "water":
            status = water_evidence_status(row)
            add_unique(water, {
                "name": row.get("name") or "Point d'eau",
                "lat": row.get("lat"), "lon": row.get("lon"),
                "status": status,
                "water_status": status,
                "notes": (
                    "Eau signalée non potable : ne pas boire."
                    if status == "not_potable"
                    else "Repère cartographique proche du tracé ; disponibilité et potabilité à vérifier."
                ),
                "source_url": row.get("source_url") or "",
                "osm_tags": row.get("osm_tags") or {},
            })
        elif category == "food":
            add_unique(food, {
                "name": row.get("name") or "Ravitaillement",
                "type": "Ravitaillement", "category": "food",
                "lat": row.get("lat"), "lon": row.get("lon"),
                "notes": "Commerce proche du tracé ; horaires et disponibilité à vérifier.",
                "source_url": row.get("source_url") or "",
                "osm_tags": row.get("osm_tags") or {},
            }, category="food")
        elif category in {"camping", "refuge", "lodging"}:
            type_label = (
                "Camping" if category == "camping"
                else "Refuge / abri" if category == "refuge"
                else "Hébergement"
            )
            add_unique(accommodations, {
                "name": row.get("name") or type_label,
                "type": type_label, "category": category,
                "lat": row.get("lat"), "lon": row.get("lon"),
                "notes": "Hébergement proche du tracé ; ouverture et disponibilité à vérifier.",
                "source_url": row.get("source_url") or "",
            }, category=category)
        elif category == "transit":
            transit_rows.append(row)
            add_unique(pois, {
                "name": row.get("name") or "Transport public",
                "type": "Transport public", "category": "transit",
                "lat": row.get("lat"), "lon": row.get("lon"),
                "source_url": row.get("source_url") or "",
                "notes": "Accès cartographique ; desserte et horaires à vérifier.",
            }, category="transit")

    result["water"] = water
    result["resources"] = food
    result["food"] = food
    result["accommodations"] = accommodations
    result["points_of_interest"] = pois

    transport = result.setdefault("transport", {})
    start, end = _point(result.get("start")), _point(result.get("end"))
    if transit_rows and start:
        nearest = min(transit_rows, key=lambda x: _distance_km(start, _point(x) or start))
        current = str(transport.get("outbound") or "")
        if not current or "aucun" in current.casefold() or "non trouv" in current.casefold():
            transport["outbound"] = f"{nearest.get('name') or 'Transport public'} à environ {_distance_km(start, _point(nearest) or start):.1f} km du départ."
    if transit_rows and end:
        nearest = min(transit_rows, key=lambda x: _distance_km(end, _point(x) or end))
        current = str(transport.get("return") or "")
        if not current or "aucun" in current.casefold() or "non trouv" in current.casefold():
            transport["return"] = f"{nearest.get('name') or 'Transport public'} à environ {_distance_km(end, _point(nearest) or end):.1f} km de l'arrivée."
    return result



def _bbox_route_water_food(
    result: dict[str, Any],
    intent: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Find real OSM supplies beside the walked line, with bounded provider calls.

    A global bounding box and a single 100-row quota are unsuitable for long
    or winding treks: a town at one corner consumes the quota before rural
    shops near other stages can be emitted. Search small, distance-balanced
    pieces of the validated route instead. All pieces share one HTTP request.
    """
    if diagnostics is not None:
        diagnostics.update(
            status="not_attempted", attempts=0, responses=0, errors=[],
            food_segments=0, accepted=0,
        )
    if not (intent.get("water") or intent.get("food")):
        return []
    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    valid = []
    for point in coords if isinstance(coords, list) else []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        lat, lon = _number(point[0]), _number(point[1])
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            if not valid or (lat, lon) != valid[-1]:
                valid.append((lat, lon))
    if len(valid) < 2:
        return []

    from . import free_planner_v2 as free

    days = max(1, int(result.get("duration_days") or len(result.get("stages") or []) or 1))
    breaks = _stage_progress_breaks(result, days)
    cumulative, length = _route_distance_profile([list(point) for point in valid])
    if length <= 0:
        return []
    missing = _missing_terrain_intent(result, intent)

    def at_fraction(fraction: float) -> tuple[float, float]:
        target = length * max(0.0, min(1.0, fraction))
        for index in range(1, len(cumulative)):
            if cumulative[index] >= target:
                span = cumulative[index] - cumulative[index - 1]
                ratio = (target - cumulative[index - 1]) / span if span > 0 else 0.0
                a, b = valid[index - 1], valid[index]
                return a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio
        return valid[-1]

    statements = []
    for kind in ("water", "food"):
        if not intent.get(kind):
            continue
        missing_days = missing.get(f"missing_{kind}_days") or []
        # A caller may already have narrowed the wave to particular stages.
        if f"missing_{kind}_days" in intent:
            missing_days = [day for day in missing_days if day in intent[f"missing_{kind}_days"]]
        if not missing_days:
            continue
        # Eight stage-local quotas retain the established food budget. For
        # longer trips, spread this wave across missing days and disclose the
        # unsearched days instead of pretending they were checked.
        if len(missing_days) > 8:
            selected_days = [missing_days[round(index * (len(missing_days) - 1) / 7)]
                             for index in range(8)]
        else:
            selected_days = missing_days
        if diagnostics is not None:
            diagnostics[f"{kind}_days_searched"] = list(selected_days)
            diagnostics[f"{kind}_days_not_searched"] = [
                day for day in missing_days if day not in selected_days
            ]

        sections = [(day, breaks[day - 1], breaks[day]) for day in selected_days]
        # Keep two independently limited pieces on a single food stage, as
        # before: shops in the start town cannot exhaust the finish quota.
        if kind == "food" and len(sections) == 1:
            day, lower, upper = sections[0]
            midpoint = (lower + upper) / 2.0
            sections = [(day, midpoint, upper), (day, lower, midpoint)]
        water_quota = max(1, 90 // len(sections))
        for day, lower, upper in sections:
            # Finish first: this is where supplies for the overnight and next
            # morning are most useful. Interpolation samples the authoritative
            # walked line; no resource becomes a router waypoint.
            fractions = [upper] + [upper - (upper - lower) * index / 11 for index in range(1, 12)]
            vertices = [at_fraction(fraction) for fraction in fractions]
            line = ",".join(f"{lat:.6f},{lon:.6f}" for lat, lon in vertices)
            if kind == "water":
                clauses = "".join(
                    f'nwr(around:2800,{line}){flt};'
                    for flt in ('["amenity"="drinking_water"]',
                                '["man_made"="water_tap"]', '["natural"="spring"]',
                                '["amenity"="water_point"]',
                                '["man_made"="water_well"]["drinking_water"="yes"]',
                                '["man_made"="water_pump"]["drinking_water"="yes"]')
                )
                statements.append(f"({clauses});out center tags {water_quota};")
            else:
                shop_filter = '["shop"~"^(supermarket|convenience|bakery|general|grocery|deli|greengrocer|food)$"]'
                statements.append(f"nwr{shop_filter}(around:4500,{line});out center tags 22;")
            if diagnostics is not None:
                diagnostics[f"{kind}_segments"] = diagnostics.get(f"{kind}_segments", 0) + 1

    if not statements:
        return []
    if _overpass_circuit_open():
        if diagnostics is not None:
            diagnostics["status"] = "unavailable"
            diagnostics["errors"].append("circuit_open")
            for kind in ("water", "food"):
                targeted = diagnostics.get(f"{kind}_days_searched", [])
                diagnostics[f"{kind}_days_not_searched"] = sorted(set(
                    targeted + diagnostics.get(f"{kind}_days_not_searched", [])
                ))
                diagnostics[f"{kind}_days_searched"] = []
        return []
    query = "[out:json][timeout:8];" + "".join(statements)
    urls = list(free.OVERPASS_URLS)
    mirrors = [urls[0], urls[-1]] if len(urls) >= 4 else urls[:2]
    found: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    any_elements = False
    provider_responded = False
    route_profile = _route_distance_profile(coords)

    for index, url in enumerate(mirrors):
        if diagnostics is not None:
            diagnostics["attempts"] += 1
        try:
            payload = free._request_json(
                url,
                data={"data": query},
                timeout=3.0 if index == 0 else 2.3,
                ttl=3600,
                service="Overpass route resources",
                retries=1,
                cache_empty=False,
            )
        except Exception as exc:
            if diagnostics is not None:
                message = str(exc).casefold()
                kind = ("rate_limited" if "429" in message
                        else "timeout" if "délai" in message or "timeout" in message
                        else "provider_error")
                diagnostics["errors"].append(kind)
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list) or payload.get("remark"):
            if diagnostics is not None:
                diagnostics["errors"].append("incomplete_response")
            continue
        provider_responded = True
        if diagnostics is not None:
            diagnostics["responses"] += 1
        elements = payload.get("elements") or []
        any_elements = any_elements or bool(elements)
        for element in elements:
            if not isinstance(element, dict):
                continue
            tags = element.get("tags") or {}
            if not isinstance(tags, dict):
                continue
            lat, lon = element.get("lat"), element.get("lon")
            if lat is None or lon is None:
                center = element.get("center") or {}
                lat, lon = center.get("lat"), center.get("lon")
            lat, lon = _number(lat), _number(lon)
            if lat is None or lon is None:
                continue
            category, water_status = None, "unverified"
            from .trekbrain_water_evidence_v9 import mapped_water_source, potability_status
            if mapped_water_source(tags):
                category = "water"
                # A well or pump without explicit potable evidence stays
                # unknown; negatives and access restrictions remain binding.
                water_status = potability_status(tags)
            elif (
                tags.get("shop") in {
                    "supermarket", "convenience", "bakery", "general",
                    "grocery", "deli", "greengrocer", "food",
                }
                and tags.get("access") not in {"private", "no"}
                and tags.get("disused") != "yes"
                and tags.get("shop") != "vacant"
            ):
                category = "food"
            if category is None:
                continue
            osm_type, osm_id = str(element.get("type") or ""), element.get("id")
            if (osm_type not in {"node", "way", "relation"}
                    or not isinstance(osm_id, int) or isinstance(osm_id, bool) or osm_id <= 0):
                continue
            source = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
            if source in seen:
                if category == "water" and water_status == "not_potable":
                    seen[source]["water_status"] = "not_potable"
                    seen[source]["osm_tags"] = dict(tags)
                continue
            row = {
                "name": str(
                    tags.get("name")
                    or ("Point d'eau" if category == "water" else "Ravitaillement")
                )[:180],
                "lat": lat, "lon": lon, "category": category,
                "water_status": water_status,
                "source_url": source,
                "osm_tags": dict(tags),
            }
            matched = _route_match(coords, row, route_profile)
            if not matched:
                continue
            if matched[0] <= RESOURCE_LIMITS["water" if category == "water" else "food"]:
                seen[source] = row
                found.append(row)
        # A point on day 1 cannot resolve the unsearched days. Give the second
        # bounded mirror a chance until requested daily evidence is complete.
        remaining = _missing_terrain_intent(
            _merge_supplemented_resources(deepcopy(result), found), intent,
        )
        if not remaining.get("water") and not remaining.get("food"):
            break

    _overpass_circuit_report(provider_responded)
    if diagnostics is not None:
        diagnostics["status"] = (
            "found" if found
            else "no_route_match" if any_elements
            else "empty" if diagnostics["responses"]
            else "unavailable"
        )
        diagnostics["accepted"] = len(found)
        diagnostics["food_accepted"] = sum(row["category"] == "food" for row in found)
    return found


def _missing_terrain_intent(result: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    """Missing supplies by actual walking day, with traceable evidence only.

    A mapped spring of unknown potability does not resolve drinking water.
    A shop or fountain on one day does not cover the rest of the itinerary.
    """
    adjusted = dict(intent or {})
    coords = ((result.get("route_preview") or {}).get("coords") or [])
    days = max(1, int(result.get("duration_days") or len(result.get("stages") or []) or 1))
    profile = _route_distance_profile(coords)
    breaks = _stage_progress_breaks(result, days)
    covered = {"water": set(), "food": set()}
    for item in _candidate_resources(result):
        kind = item.get("kind")
        if kind not in covered or _point(item) is None:
            continue
        if not (confirmed_water_reference(item) if kind == "water" else _confirmed_food_reference(item)):
            continue
        match = _route_match(coords, item, profile)
        if match and match[0] <= RESOURCE_LIMITS[kind]:
            covered[kind].add(_route_day_from_progress(match[1], breaks))
    for kind in covered:
        missing_days = [day for day in range(1, days + 1) if day not in covered[kind]]
        adjusted[kind] = bool((intent or {}).get(kind) and missing_days)
        adjusted[f"missing_{kind}_days"] = missing_days if (intent or {}).get(kind) else []
    return adjusted


def _supplement_route_resources(result: dict[str, Any], data) -> dict[str, Any]:
    """Bounded Photon safety net on final day anchors, never used for routing."""
    try:
        v3 = v7.v5.v3
        intent = v3._parse_intent(data)
        days = max(1, int(intent.get("days") or len(result.get("stages") or []) or 1))
        boundaries = _route_day_boundaries(result, days)
        if len(boundaries) < 2:
            return result

        existing = []
        for item in result.get("water") or []:
            if isinstance(item, dict) and confirmed_water_reference(item):
                existing.append({**item, "category": "water"})
        for item in _food_candidates(result):
            if isinstance(item, dict):
                existing.append({**item, "category": "food"})
        for item in result.get("accommodations") or []:
            if isinstance(item, dict):
                kind = _resource_kind(item, "lodging")
                existing.append({**item, "category": kind})
        for item in result.get("points_of_interest") or []:
            if isinstance(item, dict) and _resource_kind(item) in {"station", "transport"}:
                existing.append({**item, "category": "transit"})

        # Water already has a dedicated OSM terrain lookup in this outer
        # resource overlay, so another Photon water wave is duplicate work.
        # Route-first lodging is likewise authoritative once it has returned a
        # normal complete/partial state. Keep Photon here for the categories
        # that still add unique value: food and public transport.
        post_intent = dict(intent)
        # Skip Photon water only when a previous route-relative layer actually
        # found water. If OSM returned no usable point, keep one bounded Photon
        # fallback in the same resource wave. This restores coverage without
        # reintroducing a sequential network phase.
        terrain_intent = _missing_terrain_intent(result, intent)
        post_intent["water"] = bool(terrain_intent.get("water"))
        post_intent["food"] = bool(terrain_intent.get("food"))

        transit_items = [
            item for item in (result.get("points_of_interest") or [])
            if isinstance(item, dict) and _resource_kind(item) in {"station", "transport"}
        ]
        start_point = _point(result.get("start"))
        end_point = _point(result.get("end"))
        has_start_transit = bool(
            start_point and any(
                (point := _point(item)) is not None
                and _distance_km(start_point, point) <= 12.0
                for item in transit_items
            )
        )
        has_end_transit = bool(
            end_point and any(
                (point := _point(item)) is not None
                and _distance_km(end_point, point) <= 12.0
                for item in transit_items
            )
        )
        post_intent["transit"] = bool(
            intent.get("transit") and not (has_start_transit and has_end_transit)
        )

        logistics_status = str((result.get("logistics") or {}).get("status") or "")
        if logistics_status in {"complete", "partial"}:
            post_intent["sleep"] = False

        # Everything requested may already have been resolved by the route-first
        # logistics/terrain pass. Do not open a Photon wave merely to rediscover
        # the same water, food or lodging. Transit remains eligible when the
        # request explicitly needs it and no concrete transit resource is known.
        if not any(
            bool(post_intent.get(key))
            for key in ("transit", "water", "food", "sleep")
        ):
            return result

        try:
            rows = v3._postroute_corridor_resources(boundaries, post_intent, existing)
        except Exception:
            rows = []
        rows = _filter_active(list(rows or []))
        return _merge_supplemented_resources(result, rows)
    except Exception:
        return result


def _resource_coverage(
    result: dict[str, Any], intent: dict[str, Any],
    terrain_diagnostics: dict[str, Any] | None = None,
    reverse_diagnostics: dict[str, Any] | None = None,
    cache_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Daily preparation evidence; a failed lookup never means absence."""
    mapped = result.get("map_resources") or {}
    points = mapped.get("evidence_points", mapped.get("points") or [])
    terrain = terrain_diagnostics or {}
    reverse = reverse_diagnostics or {}
    cache = cache_diagnostics or {}
    days = max(1, len(result.get("stages") or []) or int(result.get("duration_days") or 1))
    valid_water = [point for point in points if isinstance(point, dict)
                   and point.get("kind") == "water" and has_osm_identity(point)]
    potable = [point for point in valid_water if confirmed_water_reference(point)]
    food = [point for point in points if isinstance(point, dict)
            and point.get("kind") == "food" and _confirmed_food_reference(point)]

    def point_days(rows):
        return sorted({point["route_day"] for point in rows
                       if isinstance(point.get("route_day"), int)
                       and 1 <= point["route_day"] <= days})

    verified = {"water": potable, "food": food}
    covered = {kind: point_days(rows) for kind, rows in verified.items()}
    # A failed Overpass wave leaves water unknown. Food additionally has an
    # independent reverse-shop provider, so either valid response can verify
    # its own lookup even when the other provider was down.
    unavailable = {
        "water": terrain.get("status") == "unavailable",
        "food": terrain.get("status") == "unavailable"
                and reverse.get("status") in {"unavailable", "not_attempted", None},
    }
    coverage = {}
    for kind in ("water", "food"):
        missing = [day for day in range(1, days + 1) if day not in covered[kind]]
        requested = bool(intent.get(kind))
        coverage[kind] = (
            "not_requested" if not requested
            else "verified" if not missing
            else "partial" if covered[kind]
            else "providers_unavailable" if unavailable[kind]
            else "not_verified"
        )
        coverage[f"verified_{kind}_points"] = len(verified[kind])
        coverage[f"days_with_{kind}"] = covered[kind]
        coverage[f"days_without_{kind}"] = missing if requested else []
    coverage.update({
        "mapped_water_points": len(valid_water),
        "days_with_unverified_water": point_days([
            point for point in valid_water if water_evidence_status(point) == "unverified"
        ]),
        "cache": {"status": cache.get("status"), "hits": cache.get("count", 0)},
        "terrain_provider": terrain.get("status"),
        "reverse_provider": reverse.get("status"),
        "searched_water_days": terrain.get("water_days_searched", []),
        "searched_food_days": terrain.get("food_days_searched", []),
        "daily": [
            {"day": day, **{
                kind: {
                    "status": (
                        "not_requested" if not intent.get(kind)
                        else "verified" if day in covered[kind]
                        else "providers_unavailable" if unavailable[kind]
                        else "not_verified"
                    ),
                    "verified_points": sum(point.get("route_day") == day for point in verified[kind]),
                    "mapped_points": sum(point.get("route_day") == day for point in (
                        valid_water if kind == "water" else food
                    )),
                } for kind in ("water", "food")
            }} for day in range(1, days + 1)
        ],
        "meaning": "Eau potable référencée dans OSM et commerces cartographiés proches du tracé ; débit, potabilité actuelle, horaires et disponibilité à vérifier avant le départ.",
    })
    return coverage


def _annotate_stage_resources(result: dict[str, Any]) -> dict[str, Any]:
    """Project final route-relative resources back onto the daily stage cards."""
    mapped = result.get("map_resources") or {}
    points = mapped.get("evidence_points", mapped.get("points") or [])
    stages = result.get("stages") or []
    if not isinstance(stages, list):
        return result

    by_day: dict[int, dict[str, list[dict[str, Any]]]] = {}
    for item in points:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        if kind not in {"water", "food"}:
            continue
        if not has_osm_identity(item) or (kind == "food" and not _confirmed_food_reference(item)):
            continue
        try:
            day = max(1, int(item.get("route_day") or 1))
        except (TypeError, ValueError):
            continue
        by_day.setdefault(day, {}).setdefault(kind, []).append(item)

    for index, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            continue
        resources = by_day.get(index) or {}
        water = resources.get("water") or []
        food = resources.get("food") or []
        daily = next((entry for entry in ((mapped.get("coverage") or {}).get("daily") or [])
                      if entry.get("day") == index), {})
        for kind, items in (("water", water), ("food", food)):
            details = daily.get(kind) or {}
            verified = (any(confirmed_water_reference(item) for item in items)
                        if kind == "water" else bool(items))
            stage[f"{kind}_verification"] = {
                "status": details.get("status") or ("verified" if verified else "not_verified"),
                "source_urls": [item["source_url"] for item in items],
            }
        if water:
            stage["water_notes"] = " · ".join(
                f"{item.get('name') or 'Point d’eau'}"
                + (
                    " (potable référencée, disponibilité à vérifier)"
                    if confirmed_water_reference(item)
                    else " (potabilité référencée mais accès ou disponibilité restreints)"
                    if water_evidence_status(item) == "potable_referenced"
                    else " (non potable : ne pas boire)"
                    if str(item.get("status") or "") == "not_potable"
                    else " (potabilité à vérifier)"
                )
                for item in water[:3]
            )
            if not any(confirmed_water_reference(item) for item in water):
                stage["water_notes"] += (
                    " · Aucune eau potable identifiée pour cette étape : "
                    "prévoir une réserve suffisante."
                )
        elif ((daily.get("water") or {}).get("status") == "providers_unavailable"
              or ((mapped.get("coverage") or {}).get("water") == "providers_unavailable")):
            stage["water_notes"] = (
                "Eau non vérifiée : services cartographiques indisponibles. "
                "Prévoir une réserve suffisante et vérifier les points d'eau avant le départ."
            )
        else:  # Route-wide coverage cannot guarantee water on this particular day.
            stage["water_notes"] = (
                "Aucun point d'eau OSM confirmé pour cette étape ; "
                "prévoir une réserve et vérifier les sources avant le départ."
            )
        if food:
            stage["food_notes"] = " · ".join(
                str(item.get("name") or "Ravitaillement")
                for item in food[:3]
            )
        elif ((daily.get("food") or {}).get("status") == "providers_unavailable"
              or ((result.get("map_resources") or {}).get("coverage") or {}).get("food") == "providers_unavailable"):
            stage["food_notes"] = (
                "Ravitaillement non vérifié : services cartographiques indisponibles. "
                "Prévoir ses provisions avant le départ."
            )
        else:  # A shop on another day cannot cover this stage.
            stage["food_notes"] = (
                "Aucun commerce vérifié pour cette étape sur le tracé ; "
                "vérifier les possibilités de ravitaillement avant de partir."
            )
    return result


def _refresh_quality_after_resources(result: dict[str, Any], data) -> dict[str, Any]:
    """Recompute the public v9 audit after final water/food overlays.

    Geometry and route choice are unchanged; this only makes the score observe
    the same final result the user actually receives.
    """
    try:
        from . import smart_planner_v9 as planner_v9

        normalized, _ = v7.normalize_for_planner(data.prompt)
        compound = v7.extract_side_requests(normalized)
        features = planner_v9.extract_features(data, normalized, compound)
        web = result.get("web_research") or {}
        research = {
            "evidence": web.get("evidence") or {},
            "results": result.get("web_sources") or [],
        }
        audit = planner_v9.precision_audit(
            result,
            data,
            features,
            research,
            compound,
        )
    except Exception:
        return result

    trekbrain = result.setdefault("trekbrain", {})
    if isinstance(trekbrain, dict):
        trekbrain["quality"] = audit
    decision = result.get("decision_summary")
    if isinstance(decision, dict):
        decision["quality"] = audit.get("score")
        decision["grade"] = audit.get("grade")
        decision["score_meaning"] = audit.get("score_meaning")
    return result


def _install_plan_overlay(app, legacy_main):
    original = next((r for r in app.router.routes if getattr(r, "path", None) == "/ai/plan" and "POST" in getattr(r, "methods", set())), None)
    if not original:
        raise RuntimeError("Route /ai/plan TrekBrain introuvable pour l'overlay ressources.")
    original_endpoint = original.endpoint
    app.router.routes = [r for r in app.router.routes if r is not original]

    @app.post("/ai/plan")
    def plan_with_resources(
        data: v7.v5.v3.AIPlanRequest = Body(...),
        user=Depends(legacy_main.current_user),
    ):
        # Candidate discovery becomes island-aware for the duration of this
        # request. The ContextVar keeps concurrent requests isolated.
        token = activate_region(data.region or "")
        try:
            result = original_endpoint(data, user)
            if not isinstance(result, dict):
                return result

            overlay_started = time.monotonic()
            safety_started = time.monotonic()
            report = route_safety_report(result, data)
            safety_ms = round((time.monotonic() - safety_started) * 1000)
            if not report["safe"]:
                # Never expose ORS fallback points as a hiking line. A clear
                # refusal is much safer than a convincing-looking route at sea.
                raise HTTPException(status_code=422, detail=safety_error_message(report))

            result["route_safety"] = report
            result.setdefault("advisor_notes", []).insert(
                0,
                "🛡️ Sécurité géographique : tracé pédestre validé avant affichage. Les lignes directes de secours sont interdites dans le conseiller.",
            )

            # The route is already authoritative. Final resource discovery is
            # display/logistics-only, so independent Photon and OSM terrain
            # lookups can safely overlap instead of adding their latency.
            try:
                intent = v7.v5.v3._parse_intent(data)
            except Exception:
                intent = {}
            from . import trekbrain_osm_cache_v9 as osm_cache

            # The initial planner's OSM references count as freshly observed;
            # previously cached records must NOT renew their own expiration.
            initial_sources = _cache_source_candidates(result)
            initial_source_urls = {
                str(item.get("source_url") or "") for item in initial_sources
            }
            cache_diagnostics: dict[str, Any] = {}
            cache_write_diagnostics: dict[str, Any] = {}
            cached_rows = osm_cache.read_near_route(result, intent, cache_diagnostics)
            cached_sources = {
                str(row.get("source_url") or "") for row in cached_rows
            }
            if cached_rows:
                # Geographic region filters remain authoritative (islands,
                # mainland etc.) even for references loaded from our database.
                result = _merge_supplemented_resources(
                    result, _filter_active(cached_rows)
                )

            snapshot = deepcopy(result)
            terrain_preloaded = bool(result.get("_terrain_osm_preloaded"))
            terrain_intent = _missing_terrain_intent(snapshot, intent)
            terrain_lookup_needed = bool(
                terrain_intent.get("water") or terrain_intent.get("food")
            )
            terrain_rows = []
            reverse_food_rows = []
            terrain_diagnostics: dict[str, Any] = {"status": "not_attempted"}
            reverse_diagnostics: dict[str, Any] = {"status": "not_attempted"}
            supplement_ms = 0
            terrain_ms = 0
            reverse_food_ms = 0

            def _timed_resource_call(kind, func, *args):
                nonlocal supplement_ms, terrain_ms, reverse_food_ms
                started = time.monotonic()
                try:
                    return func(*args)
                finally:
                    elapsed = round((time.monotonic() - started) * 1000)
                    if kind == "supplement":
                        supplement_ms = elapsed
                    elif kind == "terrain":
                        terrain_ms = elapsed
                    elif kind == "reverse_food":
                        reverse_food_ms = elapsed

            resource_started = time.monotonic()
            if terrain_preloaded and not terrain_lookup_needed:
                # Reuse lodging's terrain bundle ONLY when every requested
                # water/food category has a concrete located resource. If one
                # is missing, the independent targeted terrain search below
                # must still have a chance, in parallel with Photon.
                try:
                    result = _timed_resource_call(
                        "supplement", _supplement_route_resources, result, data
                    )
                except Exception:
                    pass
            elif terrain_lookup_needed:
                # A partial route bundle is not evidence that missing water or
                # food was checked successfully. Query *only* missing classes,
                # without re-requesting already located categories. The bounded
                # OSM lookup and Photon supplement run concurrently.
                # The Photon text index and public Overpass mirrors may be
                # unavailable simultaneously. Reverse shop lookup is independent
                # of the text query and works directly around route-day anchors.
                # Launch it IN PARALLEL with existing providers, not as a slow
                # serial retry. Only real OSM shops close to the route qualify.
                from . import trekbrain_food_reverse_v9 as reverse_shops
                with ThreadPoolExecutor(max_workers=3) as pool:
                    logistics_future = pool.submit(
                        _timed_resource_call,
                        "supplement",
                        _supplement_route_resources,
                        result,
                        data,
                    )
                    terrain_future = pool.submit(
                        _timed_resource_call,
                        "terrain",
                        _bbox_route_water_food,
                        snapshot,
                        terrain_intent,
                        terrain_diagnostics,
                    )
                    reverse_future = (
                        pool.submit(
                            _timed_resource_call,
                            "reverse_food",
                            reverse_shops.discover_near_route_shops,
                            snapshot,
                            reverse_diagnostics,
                        )
                        if terrain_intent.get("food") else None
                    )
                    try:
                        result = logistics_future.result()
                    except Exception:
                        pass
                    try:
                        terrain_rows = terrain_future.result()
                    except Exception:
                        terrain_rows = []
                    if reverse_future is not None:
                        try:
                            reverse_food_rows = reverse_future.result()
                        except Exception:
                            reverse_food_rows = []

                if terrain_rows or reverse_food_rows:
                    result = _merge_supplemented_resources(
                        result,
                        _filter_active(list(terrain_rows) + list(reverse_food_rows)),
                    )
                # If both bounded terrain mirrors were unavailable, the
                # independent water display scanner must NOT be suppressed by
                # a flag meaning merely "we tried". Give it one short attempt
                # on a different existing free mirror, only for missing water.
                # Never grant verified coverage without an OSM potable tag.
                water_rescue_needed = (
                    bool(terrain_intent.get("water"))
                    and terrain_diagnostics.get("status") == "unavailable"
                )
                result["_terrain_osm_preloaded"] = not water_rescue_needed
                if water_rescue_needed:
                    result["_water_rescue_mirror"] = "independent"
            else:
                # Water/food are already present in the validated route result.
                # Keep transit or a genuinely missing lodging supplement eligible
                # without reopening an OSM terrain request that cannot add value.
                try:
                    result = _timed_resource_call(
                        "supplement", _supplement_route_resources, result, data
                    )
                except Exception:
                    pass
                result["_terrain_osm_preloaded"] = True
            resource_fetch_ms = round((time.monotonic() - resource_started) * 1000)

            enrich_started = time.monotonic()
            result = enrich_resources(result)
            enrich_ms = round((time.monotonic() - enrich_started) * 1000)
            result.pop("_terrain_osm_preloaded", None)
            result.pop("_water_rescue_mirror", None)

            # Store positively identified OSM objects from fresh providers,
            # never empty results or records that were merely read from cache.
            source_linked = [
                item for item in _cache_source_candidates(result)
                if (
                    str(item.get("source_url") or "") not in cached_sources
                    or str(item.get("source_url") or "") in initial_source_urls
                )
            ]
            osm_cache.store_sourced(
                initial_sources + source_linked + terrain_rows + reverse_food_rows,
                cache_write_diagnostics,
            )

            # A provider outage is not evidence that a region has no shops.
            # Return the evidence status with the itinerary and show it on
            # individual stage cards. No POIs are invented to hide outages.
            coverage = _resource_coverage(
                result, intent, terrain_diagnostics, reverse_diagnostics, cache_diagnostics,
            )
            result.setdefault("map_resources", {})["coverage"] = coverage
            food_status, water_status = coverage["food"], coverage["water"]
            water_days, food_days = coverage["days_with_water"], coverage["days_with_food"]
            missing_water_days, missing_food_days = coverage["days_without_water"], coverage["days_without_food"]
            water_requested, food_requested = bool(intent.get("water")), bool(intent.get("food"))

            annotate_started = time.monotonic()
            result = _annotate_stage_resources(result)
            annotate_ms = round((time.monotonic() - annotate_started) * 1000)

            quality_started = time.monotonic()
            result = _refresh_quality_after_resources(result, data)
            quality_refresh_ms = round((time.monotonic() - quality_started) * 1000)

            planner = result.setdefault("planner", {})
            if isinstance(planner, dict):
                food_rows = _food_candidates(result)
                planner["resource_overlay"] = {
                    "total_ms": round((time.monotonic() - overlay_started) * 1000),
                    "safety_ms": safety_ms,
                    "resource_fetch_ms": resource_fetch_ms,
                    "supplement_ms": supplement_ms,
                    "terrain_ms": terrain_ms,
                    "reverse_food_ms": reverse_food_ms,
                    "reverse_food_rows": len(reverse_food_rows),
                    "enrich_ms": enrich_ms,
                    "annotate_ms": annotate_ms,
                    "quality_refresh_ms": quality_refresh_ms,
                    "terrain_preloaded": terrain_preloaded,
                    "terrain_lookup_needed": terrain_lookup_needed,
                    "terrain_rows": len(terrain_rows),
                    "terrain_provider": dict(terrain_diagnostics),
                    "reverse_provider": dict(reverse_diagnostics),
                    "food_coverage": food_status,
                    "water_coverage": water_status,
                    "water_days_covered": len(water_days),
                    "water_days_missing": missing_water_days if water_requested else [],
                    "food_days_covered": len(food_days),
                    "food_days_missing": missing_food_days if food_requested else [],
                    "osm_cache": dict(cache_diagnostics),
                    "osm_cache_write": dict(cache_write_diagnostics),
                    "water_count": len(result.get("water") or []),
                    "food_count": len(food_rows),
                    "accommodation_count": len(result.get("accommodations") or []),
                }
            return result
        finally:
            reset_region(token)


def _install_redraw_endpoint(app, legacy_main):
    @app.put("/treks/{trek_id}/ai-redraw")
    def ai_redraw(trek_id: int, data: AIRedrawPayload, user=Depends(legacy_main.current_user)):
        error = legacy_main.validate_coords(data.coords)
        if error:
            raise HTTPException(status_code=400, detail=error)

        route = legacy_main.get_route(data.coords)
        coords = route.get("coords") or []
        report = route_safety_report({
            "route_preview": {
                "coords": coords,
                "distance_km": route.get("distance"),
                "fallback": route.get("fallback"),
            }
        })
        if not report["safe"]:
            raise HTTPException(
                status_code=422,
                detail="Mise à jour refusée : le moteur pédestre n'a pas validé ce tracé. Aucun segment direct de secours ne sera enregistré.",
            )

        db = legacy_main.db_or_503()
        try:
            row = db.execute(text("SELECT owner_id,is_public FROM treks WHERE id=:id"), {"id": trek_id}).first()
            if not row:
                raise HTTPException(status_code=404, detail="Trek introuvable.")
            if not legacy_main.can_manage(row.owner_id, user):
                raise HTTPException(status_code=403, detail="Tu ne peux pas modifier ce trek.")
            name = legacy_main.normalize_text(data.name)[:160]
            region = legacy_main.normalize_text(data.region)[:120]
            days = round(float(data.duration_days), 2) if data.duration_days is not None else legacy_main.estimate_duration_days(route["distance"])
            db.execute(text("""
                UPDATE treks
                SET name=:name,region=:region,difficulty=:difficulty,description=:description,
                    distance=:distance,elevation=:elevation,geom=ST_SetSRID(ST_GeomFromGeoJSON(:geo),4326),
                    duration_days=:days,duration_minutes=:minutes
                WHERE id=:id
            """), {
                "name": name, "region": region, "difficulty": legacy_main.difficulty(data.difficulty),
                "description": legacy_main.normalize_text(data.description)[:10000],
                "distance": route["distance"], "elevation": legacy_main.elevation_gain(coords),
                "geo": json.dumps(legacy_main.coords_to_geojson(coords)), "days": days,
                "minutes": legacy_main.duration_minutes(days), "id": trek_id,
            })
            db.commit()
            return {
                "message": "Trek recalculé et mis à jour",
                "id": trek_id,
                "distance": route["distance"],
                "duration_days": days,
                "coords": coords,
                "fallback": False,
                "route_safety": report,
            }
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail="Mise à jour du tracé momentanément indisponible.") from exc
        finally:
            db.close()


def install_resource_overlay(app, legacy_main):
    # Apply once to v3 candidate discovery. The wrappers are inert unless an
    # island-aware request activates bounds in the current request context.
    install_geo_filters(v7.v5.v3)
    _install_plan_overlay(app, legacy_main)
    _install_redraw_endpoint(app, legacy_main)
