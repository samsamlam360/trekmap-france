"""Geographic safety layer for TrekBrain v9.

The planner may use straight-line coordinates as a diagnostic fallback when a
walking route cannot be computed. That behaviour is acceptable internally, but
it must never be presented to a hiker as a usable itinerary. This module also
limits candidate POIs to the geographic bounds of explicit islands so nearby
mainland points do not contaminate island treks.
"""
from __future__ import annotations

from contextvars import ContextVar
import math
import re
import unicodedata
from typing import Any

from . import free_planner_v2 as geo

_ACTIVE_BOUNDS: ContextVar[dict[str, float] | None] = ContextVar(
    "trekbrain_v9_active_bounds", default=None
)
_INSTALLED = False


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _is_island_hint(region: str) -> bool:
    text = _fold(region).replace("'", " ")
    return bool(
        re.search(r"\bile?s?\b|\bisland\b|\barchipel\b", text)
        or any(name in text for name in ("ouessant", "groix", "noirmoutier", "oleron", "corse", "corsica"))
    )


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _discover_island_bounds(region: str) -> dict[str, float] | None:
    """Resolve an island bounding box only when the request actually looks island-like."""
    if not _is_island_hint(region):
        return None
    try:
        rows = geo._request_json(
            geo.NOMINATIM_URL,
            params={
                "q": f"{region}, France",
                "format": "jsonv2",
                "limit": 4,
                "addressdetails": 1,
                "countrycodes": "fr",
            },
            timeout=10,
            ttl=43200,
            service="Nominatim",
            retries=1,
        )
    except Exception:
        rows = []

    for row in rows if isinstance(rows, list) else []:
        bbox = row.get("boundingbox") or []
        if len(bbox) < 4:
            continue
        try:
            south, north, west, east = map(float, bbox[:4])
        except (TypeError, ValueError):
            continue
        display = _fold(row.get("display_name") or "")
        place_type = _fold(row.get("type") or "")
        place_class = _fold(row.get("class") or "")
        islandish = (
            place_type in {"island", "archipelago"}
            or "ile" in display
            or "island" in display
            or (place_class == "place" and _is_island_hint(region))
        )
        if not islandish:
            continue
        # Small padding keeps POIs just outside an administrative outline while
        # still excluding mainland features across a channel.
        pad_lat = max(0.008, min(0.018, (north - south) * 0.08))
        pad_lon = max(0.008, min(0.018, (east - west) * 0.08))
        return {
            "south": south - pad_lat,
            "north": north + pad_lat,
            "west": west - pad_lon,
            "east": east + pad_lon,
            "island": 1.0,
        }

    # If Nominatim is temporarily unavailable, keep a conservative local box
    # around the geocoded centre instead of silently allowing mainland POIs.
    try:
        results = geo._geocode(f"{region}, France") or geo._geocode(region)
    except Exception:
        results = []
    if results:
        lat = _safe_float(results[0].get("lat"))
        lon = _safe_float(results[0].get("lon"))
        if lat is not None and lon is not None:
            radius_km = 14.0
            dlat = radius_km / 111.0
            dlon = radius_km / max(35.0, 111.0 * math.cos(math.radians(lat)))
            return {
                "south": lat - dlat,
                "north": lat + dlat,
                "west": lon - dlon,
                "east": lon + dlon,
                "island": 1.0,
            }
    return None


def activate_region(region: str):
    return _ACTIVE_BOUNDS.set(_discover_island_bounds(str(region or "").strip()))


def reset_region(token) -> None:
    _ACTIVE_BOUNDS.reset(token)


def _inside_bounds(item: dict[str, Any], bounds: dict[str, float]) -> bool:
    lat, lon = _safe_float(item.get("lat")), _safe_float(item.get("lon"))
    if lat is None or lon is None:
        return False
    return (
        bounds["south"] <= lat <= bounds["north"]
        and bounds["west"] <= lon <= bounds["east"]
    )


def _filter_active(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bounds = _ACTIVE_BOUNDS.get()
    if not bounds:
        return items
    return [item for item in items if isinstance(item, dict) and _inside_bounds(item, bounds)]


def install_geo_filters(v3) -> None:
    """Patch only candidate discovery. Routing and scoring remain the trusted v3 code."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_nearby = v3._nearby
    original_extra = v3._extra_nearby
    original_photon = v3._photon_category_candidates

    def nearby(lat, lon, radius_km, categories):
        return _filter_active(original_nearby(lat, lon, radius_km, categories))

    def extra_nearby(center, radius_km):
        items, notes = original_extra(center, radius_km)
        filtered = _filter_active(items)
        if _ACTIVE_BOUNDS.get() and len(filtered) < len(items):
            notes = list(notes or []) + [
                "Zone insulaire : les points situés hors de l'île ont été écartés avant le calcul du parcours."
            ]
        return filtered, notes

    def photon(location, center, categories):
        return _filter_active(original_photon(location, center, categories))

    v3._nearby = nearby
    v3._extra_nearby = extra_nearby
    v3._photon_category_candidates = photon


def _haversine(a: list[float] | tuple[float, float], b: list[float] | tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _valid_coords(raw: Any) -> list[list[float]]:
    out: list[list[float]] = []
    for point in raw if isinstance(raw, list) else []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return []
        lat, lon = _safe_float(point[0]), _safe_float(point[1])
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return []
        out.append([lat, lon])
    return out


def route_safety_report(result: dict[str, Any], request: Any | None = None) -> dict[str, Any]:
    """Return a deterministic go/no-go report for a route shown to users."""
    route = result.get("route_preview") or {}
    coords = _valid_coords(route.get("coords") or [])
    blockers: list[str] = []
    warnings: list[str] = []

    if route.get("fallback") is not False:
        blockers.append("Le moteur pédestre n'a pas validé le tracé ; un tracé direct de secours serait nécessaire.")
    if len(coords) < 2:
        blockers.append("Aucune géométrie pédestre exploitable n'est disponible.")

    max_gap = 0.0
    polyline_km = 0.0
    if len(coords) >= 2:
        for a, b in zip(coords, coords[1:]):
            gap = _haversine(a, b)
            max_gap = max(max_gap, gap)
            polyline_km += gap
        if max_gap > 3.0:
            blockers.append(
                f"Le tracé contient un saut géographique de {max_gap:.1f} km, incompatible avec un cheminement pédestre continu."
            )

    route_km = _safe_float(route.get("distance_km"))
    if route_km is None:
        route_km = _safe_float(route.get("distance"))
    if route_km and polyline_km > 0:
        ratio = polyline_km / route_km
        if ratio < 0.70 or ratio > 1.35:
            blockers.append("La longueur de la géométrie ne correspond pas à la distance annoncée par le moteur de routage.")

    def declared_point(name: str):
        item = result.get(name) or {}
        lat, lon = _safe_float(item.get("lat")), _safe_float(item.get("lon"))
        return [lat, lon] if lat is not None and lon is not None else None

    if coords:
        start = declared_point("start")
        end = declared_point("end")
        if start and _haversine(start, coords[0]) > 1.5:
            blockers.append("Le début du tracé ne correspond pas au point de départ annoncé.")
        if end and _haversine(end, coords[-1]) > 1.5:
            blockers.append("La fin du tracé ne correspond pas au point d'arrivée annoncé.")

    stages = result.get("stages") or []
    stage_distances = []
    for stage in stages if isinstance(stages, list) else []:
        value = _safe_float((stage or {}).get("distance_km")) if isinstance(stage, dict) else None
        if value and value > 0:
            stage_distances.append(value)
    if route_km and stage_distances and len(stage_distances) == len(stages):
        stage_total = sum(stage_distances)
        mismatch = abs(stage_total - route_km) / max(route_km, 1.0)
        if mismatch > 0.22:
            blockers.append("La somme des étapes ne correspond pas au tracé réellement calculé.")

    prompt = _fold(getattr(request, "prompt", "") if request is not None else "")
    requested_days = int(getattr(request, "days", 0) or len(stages) or 1) if request is not None else int(result.get("duration_days") or len(stages) or 1)
    if "camping" in prompt and requested_days > 1:
        accommodations = result.get("accommodations") or []
        camping_names = {
            _fold(item.get("name") or "")
            for item in accommodations
            if isinstance(item, dict)
            and "camp" in _fold(f"{item.get('category') or ''} {item.get('type') or ''} {item.get('name') or ''}")
        }
        uncertain_terms = ("a confirmer", "envisage", "aucun", "non trouve", "inconnu")
        missing_nights = 0
        for stage in (stages[:-1] if isinstance(stages, list) else []):
            overnight = _fold((stage or {}).get("overnight") or "") if isinstance(stage, dict) else ""
            known_name = any(name and name in overnight for name in camping_names)
            if not overnight or any(term in overnight for term in uncertain_terms) or ("camp" not in overnight and not known_name):
                missing_nights += 1
        if missing_nights:
            blockers.append(
                f"La demande impose des campings, mais {missing_nights} nuitée(s) ne sont pas reliées à un camping identifié."
            )

    if request is not None and getattr(request, "require_water", False):
        undocumented = 0
        for stage in stages if isinstance(stages, list) else []:
            notes = _fold((stage or {}).get("water_notes") or "") if isinstance(stage, dict) else ""
            if not notes or "aucun point d'eau" in notes or "aucun point d eau" in notes:
                undocumented += 1
        if undocumented == len(stages) and stages:
            blockers.append("Aucune étape ne dispose d'une information d'eau exploitable alors que l'eau est demandée.")
        elif undocumented:
            warnings.append(f"{undocumented} étape(s) ont encore une information d'eau insuffisante.")

    return {
        "safe": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "max_segment_gap_km": round(max_gap, 3),
        "polyline_distance_km": round(polyline_km, 2),
        "routing_verified": route.get("fallback") is False,
        "island_bounds_active": bool(_ACTIVE_BOUNDS.get()),
    }


def safety_error_message(report: dict[str, Any]) -> str:
    reasons = [str(x).strip() for x in report.get("blockers") or [] if str(x).strip()]
    detail = " ".join(reasons[:3])
    return (
        "Je refuse de proposer ce parcours comme randonnée sûre car le tracé pédestre n'est pas suffisamment validé. "
        + (detail or "Le moteur géographique n'a pas produit de parcours fiable.")
        + " Modifie légèrement la zone ou les contraintes puis relance la génération."
    )
