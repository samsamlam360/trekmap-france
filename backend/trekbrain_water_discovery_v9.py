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


def _sample_route(coords: list[list[float]], days: int) -> list[list[float]]:
    if not coords:
        return []
    count = min(16, max(6, int(days) * 3))
    if len(coords) <= count:
        return coords
    indexes = {round(i * (len(coords) - 1) / max(1, count - 1)) for i in range(count)}
    return [coords[i] for i in sorted(indexes)]


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
    query = "[out:json][timeout:12];(" + "".join(clauses) + ");out center tags 120;"
    try:
        payload = v3._overpass(query)
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
        key = (round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        is_spring = tags.get("natural") == "spring"
        is_tap = tags.get("man_made") == "water_tap"
        default_name = "Source" if is_spring else "Robinet d'eau" if is_tap else "Point d'eau"
        element_type = str(element.get("type") or "node")
        element_id = element.get("id")
        source_url = f"https://www.openstreetmap.org/{element_type}/{element_id}" if element_id else ""
        out.append({
            "name": str(tags.get("name") or default_name)[:160],
            "lat": lat,
            "lon": lon,
            "category": "water",
            "type": "Point d'eau",
            "notes": "Repère cartographique uniquement ; disponibilité et potabilité à vérifier.",
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
        discovered = discover_water_points(v3, result)
        merged = []
        seen = set()
        for item in existing + discovered:
            try:
                key = (round(float(item.get("lat")), 5), round(float(item.get("lon")), 5))
            except (TypeError, ValueError):
                continue
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        result["water"] = merged
        enriched = original_enrich(result)
        enriched.setdefault("map_resources", {})["water_discovery"] = "post-route-overpass"
        return enriched

    resources.enrich_resources = enrich_resources


__all__ = ["install_water_discovery", "discover_water_points", "_sample_route"]
