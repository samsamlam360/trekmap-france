"""TrekBrain v9 resource and geographic-safety overlay.

Adds route-relative map resources (water, campsites, refuges and public
transport), keeps island planning inside the requested island, and refuses to
show or save a route that was not actually validated by the walking router.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any

from fastapi import Body, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import text

from . import smart_planner_v7 as v7
from .trekbrain_geo_safety_v9 import (
    _filter_active,
    activate_region,
    install_geo_filters,
    reset_region,
    route_safety_report,
    safety_error_message,
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


def _route_match(
    coords: list[list[float]],
    item: dict[str, Any],
    route_profile: tuple[list[float], float] | None = None,
) -> tuple[float, float] | None:
    target = _point(item)
    if not target or not coords:
        return None
    stride = max(1, len(coords) // 800)
    best_d, best_i = float("inf"), 0
    for i in range(0, len(coords), stride):
        if not isinstance(coords[i], (list, tuple)) or len(coords[i]) < 2:
            continue
        p = (_number(coords[i][0]), _number(coords[i][1]))
        if p[0] is None or p[1] is None:
            continue
        d = _distance_km(target, (p[0], p[1]))
        if d < best_d:
            best_d, best_i = d, i
    if coords and (len(coords) - 1) % stride:
        last = coords[-1]
        if isinstance(last, (list, tuple)) and len(last) >= 2:
            lat, lon = _number(last[0]), _number(last[1])
            if lat is not None and lon is not None:
                d = _distance_km(target, (lat, lon))
                if d < best_d:
                    best_d, best_i = d, len(coords) - 1
    if not math.isfinite(best_d):
        return None

    progress = best_i / max(1, len(coords) - 1)
    if route_profile:
        cumulative, total = route_profile
        if len(cumulative) == len(coords) and total > 0 and 0 <= best_i < len(cumulative):
            progress = max(0.0, min(1.0, float(cumulative[best_i]) / float(total)))
    return best_d, progress


def _resource_kind(item: dict[str, Any], fallback: str = "") -> str:
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


def _candidate_resources(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for w in result.get("water") or []:
        if isinstance(w, dict):
            items.append({**w, "kind": "water", "type": "Point d'eau", "notes": w.get("notes") or "Potabilité à vérifier."})
    for a in result.get("accommodations") or []:
        if isinstance(a, dict):
            kind = _resource_kind(a, "lodging")
            items.append({**a, "kind": kind, "notes": a.get("notes") or "Ouverture et disponibilité à vérifier."})
    food_rows = result.get("resources") or result.get("food") or []
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
    for item in _candidate_resources(result):
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
        key = (kind, round(point[0], 5), round(point[1], 5), str(item.get("name") or "").casefold())
        if key in seen:
            continue
        seen.add(key)
        route_day = min(days, max(1, int(math.floor(progress * days)) + 1))
        prepared.append({
            "name": str(item.get("name") or "Point")[:160],
            "kind": kind,
            "type": str(item.get("type") or kind)[:80],
            "lat": round(point[0], 6),
            "lon": round(point[1], 6),
            "route_day": route_day,
            "distance_to_route_km": round(distance, 2),
            "status": str(item.get("status") or "")[:80],
            "notes": str(item.get("notes") or "")[:500],
            "source_url": str(item.get("source_url") or "")[:1000],
        })

    priority = {"water": 0, "food": 1, "camping": 2, "refuge": 3, "lodging": 4, "station": 5, "transport": 6, "trail": 7}
    prepared.sort(key=lambda x: (x["route_day"], priority.get(x["kind"], 9), x["distance_to_route_km"], x["name"]))

    # Avoid a carpet of icons: keep the closest few of each category per day.
    limited, buckets = [], {}
    per_day_caps = {"water": 3, "food": 3, "camping": 2, "refuge": 2, "lodging": 2, "station": 2, "transport": 3, "trail": 2}
    for item in prepared:
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
    floor = 1
    for day in range(1, max(1, int(days))):
        target = total * day / max(1, int(days))
        if floor >= len(clean) - 1:
            break
        idx = min(range(floor, len(clean) - 1), key=lambda i: abs(cumulative[i] - target))
        boundaries.append({
            "name": f"Repère jour {day}",
            "lat": clean[idx][0],
            "lon": clean[idx][1],
            "category": "route_anchor",
        })
        floor = idx + 1
    boundaries.append(end)
    return boundaries


def _merge_supplemented_resources(result: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return result

    water = list(result.get("water") or [])
    food = list(result.get("resources") or result.get("food") or [])
    accommodations = list(result.get("accommodations") or [])
    pois = list(result.get("points_of_interest") or [])
    transit_rows = []

    def add_unique(target, item, *, category=None):
        key = str(item.get("source_url") or "")
        try:
            coords_key = (round(float(item.get("lat")), 5), round(float(item.get("lon")), 5))
        except (TypeError, ValueError):
            coords_key = None
        for existing in target:
            if not isinstance(existing, dict):
                continue
            if key and str(existing.get("source_url") or "") == key:
                return
            if coords_key is not None:
                try:
                    if (
                        round(float(existing.get("lat")), 5),
                        round(float(existing.get("lon")), 5),
                    ) == coords_key and (category is None or str(existing.get("category") or "") == category):
                        return
                except (TypeError, ValueError):
                    pass
        target.append(item)

    for row in rows:
        if not isinstance(row, dict):
            continue
        category = str(row.get("category") or "")
        if category == "water":
            add_unique(water, {
                "name": row.get("name") or "Point d'eau",
                "lat": row.get("lat"), "lon": row.get("lon"),
                "status": row.get("water_status") or "unverified",
                "notes": "Repère cartographique proche du tracé ; disponibilité et potabilité à vérifier.",
                "source_url": row.get("source_url") or "",
            })
        elif category == "food":
            add_unique(food, {
                "name": row.get("name") or "Ravitaillement",
                "type": "Ravitaillement", "category": "food",
                "lat": row.get("lat"), "lon": row.get("lon"),
                "notes": "Commerce proche du tracé ; horaires et disponibilité à vérifier.",
                "source_url": row.get("source_url") or "",
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



def _bbox_route_water_food(result: dict[str, Any], intent: dict[str, Any]) -> list[dict[str, Any]]:
    """One short OSM lookup for water/food close to the final validated route."""
    if not (intent.get("water") or intent.get("food")):
        return []
    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    valid = []
    for point in coords if isinstance(coords, list) else []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        lat, lon = _number(point[0]), _number(point[1])
        if lat is not None and lon is not None:
            valid.append((lat, lon))
    if len(valid) < 2:
        return []

    from . import free_planner_v2 as free

    min_lat, max_lat = min(x[0] for x in valid), max(x[0] for x in valid)
    min_lon, max_lon = min(x[1] for x in valid), max(x[1] for x in valid)
    mid_lat = (min_lat + max_lat) / 2.0
    pad_lat = 0.045
    pad_lon = max(0.045, 5.0 / max(35.0, 111.0 * math.cos(math.radians(mid_lat))))
    south, north = min_lat - pad_lat, max_lat + pad_lat
    west, east = min_lon - pad_lon, max_lon + pad_lon

    clauses = []
    if intent.get("water"):
        for flt in (
            '["amenity"="drinking_water"]',
            '["man_made"="water_tap"]',
            '["natural"="spring"]',
        ):
            clauses.append(f"nwr{flt}({south:.6f},{west:.6f},{north:.6f},{east:.6f});")
    if intent.get("food"):
        for flt in (
            '["shop"="supermarket"]',
            '["shop"="convenience"]',
            '["shop"="bakery"]',
        ):
            clauses.append(f"nwr{flt}({south:.6f},{west:.6f},{north:.6f},{east:.6f});")
    if not clauses:
        return []

    query = "[out:json][timeout:3];(" + "".join(clauses) + ");out center tags 120;"
    try:
        url = list(free.OVERPASS_URLS)[0]
        payload = free._request_json(
            url,
            data={"data": query},
            timeout=1.7,
            ttl=3600,
            service="Overpass route resources",
            retries=1,
        )
    except Exception:
        return []

    rows = []
    for element in (payload.get("elements") or [])[:120] if isinstance(payload, dict) else []:
        tags = element.get("tags") or {}
        lat, lon = element.get("lat"), element.get("lon")
        if lat is None or lon is None:
            center = element.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        lat, lon = _number(lat), _number(lon)
        if lat is None or lon is None:
            continue

        category = None
        status = ""
        if (
            tags.get("amenity") == "drinking_water"
            or tags.get("man_made") == "water_tap"
            or tags.get("natural") == "spring"
        ):
            category = "water"
            status = (
                "potable_referenced"
                if tags.get("amenity") == "drinking_water" or tags.get("drinking_water") == "yes"
                else "not_potable" if tags.get("drinking_water") == "no"
                else "unverified"
            )
        elif tags.get("shop") in {"supermarket", "convenience", "bakery"}:
            category = "food"
        if category is None:
            continue

        osm_type = str(element.get("type") or "node")
        osm_id = element.get("id")
        row = {
            "name": str(
                tags.get("name")
                or ("Point d'eau" if category == "water" else "Ravitaillement")
            )[:180],
            "lat": lat,
            "lon": lon,
            "category": category,
            "water_status": status or "unverified",
            "source_url": (
                f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
                if osm_id is not None else ""
            ),
        }
        match = _route_match(coords, row)
        if not match:
            continue
        max_distance = 5.0 if category == "water" else 7.0
        if match[0] <= max_distance:
            rows.append(row)
    return rows


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
            if isinstance(item, dict):
                existing.append({**item, "category": "water"})
        for item in result.get("resources") or result.get("food") or []:
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
        has_water = any(
            isinstance(item, dict) and _point(item) is not None
            for item in (result.get("water") or [])
        )
        food_rows = result.get("resources") or result.get("food") or []
        has_food = any(
            isinstance(item, dict) and _point(item) is not None
            for item in food_rows
        )

        post_intent["water"] = bool(intent.get("water") and not has_water)
        post_intent["food"] = bool(intent.get("food") and not has_food)

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


def _annotate_stage_resources(result: dict[str, Any]) -> dict[str, Any]:
    """Project final route-relative resources back onto the daily stage cards."""
    points = ((result.get("map_resources") or {}).get("points") or [])
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
        if water:
            stage["water_notes"] = " · ".join(
                f"{item.get('name') or 'Point d’eau'}"
                + (
                    " (potable référencée)"
                    if str(item.get("status") or "") == "potable_referenced"
                    else " (potabilité à vérifier)"
                )
                for item in water[:3]
            )
        if food:
            stage["food_notes"] = " · ".join(
                str(item.get("name") or "Ravitaillement")
                for item in food[:3]
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

            report = route_safety_report(result, data)
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
            snapshot = deepcopy(result)
            terrain_preloaded = bool(result.get("_terrain_osm_preloaded"))
            terrain_rows = []

            if terrain_preloaded:
                # Lodging discovery already queried this exact route corridor
                # and attached its water/food rows. Only the bounded Photon
                # supplement may still add something such as public transport.
                try:
                    result = _supplement_route_resources(result, data)
                except Exception:
                    pass
            else:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    logistics_future = pool.submit(
                        _supplement_route_resources, result, data
                    )
                    terrain_future = pool.submit(
                        _bbox_route_water_food, snapshot, intent
                    )
                    try:
                        result = logistics_future.result()
                    except Exception:
                        pass
                    try:
                        terrain_rows = terrain_future.result()
                    except Exception:
                        terrain_rows = []

                if terrain_rows:
                    result = _merge_supplemented_resources(
                        result,
                        _filter_active(list(terrain_rows)),
                    )
                result["_terrain_osm_preloaded"] = True
            result = enrich_resources(result)
            result.pop("_terrain_osm_preloaded", None)
            result = _annotate_stage_resources(result)
            return _refresh_quality_after_resources(result, data)
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
