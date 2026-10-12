"""Route-relative drinking-water discovery for TrekBrain v9.

Water is discovered only after the walking line has been chosen.  The resulting
points are display-only map context and never become ORS waypoints.
"""
from __future__ import annotations

import math
from typing import Any

_INSTALLED = False


def _valid_coords(raw) -> list[list[float]]:
    out = []
    for point in raw if isinstance(raw, list) else []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lat, lon = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            out.append([lat, lon])
    return out


def _distance_km(a: list[float], b: list[float]) -> float:
    """Short-segment great-circle distance; no external provider or map call."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, h))))


def _sample_route(coords: list[list[float]], days: int) -> list[list[float]]:
    """Sample by walked distance, NOT by vertex index.

    Imported GPX files can contain 2,000 closely spaced vertices on day one
    and just 10 on a long next day. The old index sampling used its whole
    Overpass budget on day one, leaving the remaining stages unsearched.
    Keep the same cap (6..16 sample points) and the same single request.
    """
    clean = _valid_coords(coords)
    if not clean:
        return []
    if len(clean) == 1:
        return clean
    count = min(16, max(6, int(days) * 3))
    cumulative = [0.0]
    for a, b in zip(clean, clean[1:]):
        cumulative.append(cumulative[-1] + _distance_km(a, b))
    total = cumulative[-1]
    if total < 0.00001:
        return [clean[0]]
    result = []
    segment = 1
    for index in range(count):
        target = total * index / (count - 1)
        while segment < len(clean) - 1 and cumulative[segment] < target:
            segment += 1
        lower, upper = cumulative[segment - 1], cumulative[segment]
        ratio = 0.0 if upper <= lower else max(0.0, min(1.0, (target - lower) / (upper - lower)))
        start, end = clean[segment - 1], clean[segment]
        point = [
            round(start[0] + ratio * (end[0] - start[0]), 6),
            round(start[1] + ratio * (end[1] - start[1]), 6),
        ]
        if not result or result[-1] != point:
            result.append(point)
    # Endpoint precision must not drift on short or sparse GPS polylines.
    if result:
        result[0], result[-1] = clean[0], clean[-1]
    return result


def _element_point(element: dict[str, Any]):
    lat, lon = element.get("lat"), element.get("lon")
    if lat is None or lon is None:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    return lat, lon


def discover_water_points(v3, result: dict[str, Any]) -> list[dict[str, Any]]:
    route = result.get("route_preview") or {}
    coords = _valid_coords(route.get("coords") or [])
    if len(coords) < 2:
        return []
    days = max(1, int(result.get("duration_days") or len(result.get("stages") or []) or 1))
    samples = _sample_route(coords, days)
    if not samples:
        return []

    radius_m = 3200
    clauses = []
    for lat, lon in samples:
        clauses.extend([
            f'nwr(around:{radius_m},{lat:.6f},{lon:.6f})["amenity"="drinking_water"];',
            f'nwr(around:{radius_m},{lat:.6f},{lon:.6f})["man_made"="water_tap"];',
            f'nwr(around:{radius_m},{lat:.6f},{lon:.6f})["natural"="spring"];',
        ])
    query = "[out:json][timeout:4];(" + "".join(clauses) + ");out center tags 120;"
    try:
        # This is display-only context after a validated route already exists.
        # One short mirror attempt is enough; failing fast is preferable to
        # delaying the whole itinerary by the full generic Overpass budget.
        from . import free_planner_v2 as free
        url = list(free.OVERPASS_URLS)[0]
        payload = free._request_json(
            url,
            data={"data": query},
            timeout=1.6,
            ttl=3600,
            service="Overpass water display",
            retries=1,
        )
    except Exception:
        return []

    out = []
    seen = set()
    for element in (payload.get("elements") or [])[:120] if isinstance(payload, dict) else []:
        point = _element_point(element)
        if not point:
            continue
        lat, lon = point
        tags = element.get("tags") or {}
        # Explicit negative OSM tags override amenity=drinking_water.
        # A spring/water_tap is never guaranteed potable without evidence.
        unsafe = (
            str(tags.get("drinking_water") or "").casefold() == "no"
            or str(tags.get("water:potable") or "").casefold() == "no"
            or str(tags.get("potable") or "").casefold() == "no"
        )
        referenced = not unsafe and (
            tags.get("amenity") == "drinking_water"
            or tags.get("drinking_water") == "yes"
            or tags.get("water:potable") == "yes"
        )
        status = "not_potable" if unsafe else "potable_referenced" if referenced else "unverified"
        is_spring = tags.get("natural") == "spring"
        is_tap = tags.get("man_made") == "water_tap"
        default_name = "Source" if is_spring else "Robinet d'eau" if is_tap else "Point d'eau"
        element_type = str(element.get("type") or "node")
        element_id = element.get("id")
        source_url = (
            f"https://www.openstreetmap.org/{element_type}/{element_id}"
            if element_type in {"node", "way", "relation"}
            and isinstance(element_id, int) and element_id > 0 else ""
        )
        key = source_url or (round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": str(tags.get("name") or default_name)[:160],
            "lat": lat,
            "lon": lon,
            "category": "water",
            "type": "Point d'eau",
            "water_status": status,
            "status": status,
            "notes": (
                "Eau signalée non potable : ne pas boire."
                if unsafe else
                "Source OSM signalée potable : disponibilité et potabilité à vérifier sur place."
                if referenced else
                "Point d'eau cartographié ; potabilité inconnue, ne pas supposer l'eau potable."
            ),
            "source_url": source_url,
            "display_only": True,
        })
    return out


def install_water_discovery(v3, resources) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_enrich = resources.enrich_resources

    def enrich_resources(result: dict[str, Any]):
        existing = [x for x in (result.get("water") or []) if isinstance(x, dict)]
        preloaded = bool(result.get("_terrain_osm_preloaded"))
        discovered = [] if preloaded else discover_water_points(v3, result)
        merged = []
        seen = {}
        for item in existing + discovered:
            try:
                key = (round(float(item.get("lat")), 5), round(float(item.get("lon")), 5))
            except (TypeError, ValueError):
                continue
            if key in seen:
                previous = seen[key]
                old_source = str(previous.get("source_url") or "")
                new_source = str(item.get("source_url") or "")
                # Do not accidentally poison a separate water source sharing a
                # coordinate. Prefer explicit non-potable evidence for the
                # same OSM object, even over stale cached potable metadata.
                same_source = bool(old_source and old_source == new_source)
                if not (same_source or not old_source or not new_source):
                    continue
                if str(item.get("status") or item.get("water_status") or "") == "not_potable":
                    previous.update({
                        "status": "not_potable",
                        "water_status": "not_potable",
                        "notes": "Eau signalée non potable : ne pas boire.",
                    })
                    if new_source and not old_source:
                        previous["source_url"] = new_source
                continue
            seen[key] = item
            merged.append(item)
        result["water"] = merged
        enriched = original_enrich(result)
        enriched.setdefault("map_resources", {})["water_discovery"] = (
            "post-route-parallel-osm" if preloaded else "post-route-overpass"
        )
        return enriched

    resources.enrich_resources = enrich_resources


__all__ = ["install_water_discovery", "discover_water_points", "_sample_route"]
