"""Secondary pedestrian routing for TrekBrain v9.

OpenRouteService remains the primary router. If ORS has already exhausted its
bounded retry/segmented recovery and still reports a transient 5xx/network
failure, this layer makes one bounded attempt with the public Valhalla pedestrian
router. It never replaces ORS auth/rate-limit errors and never accepts a straight
line as a route.

The public Valhalla instance is a fair-use fallback, not a guaranteed production
SLA. Requests identify TrekMap with X-Client-Id as requested by the service.
"""
from __future__ import annotations

import os
import time
from copy import deepcopy
from typing import Any

import requests

_INSTALLED = False
_URL = os.getenv("TREKBRAIN_VALHALLA_URL", "https://valhalla1.openstreetmap.de/route").strip()
_TIMEOUT = max(3.0, min(float(os.getenv("TREKBRAIN_VALHALLA_TIMEOUT", "7") or 7), 12.0))
_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 6 * 60 * 60
_COOLDOWN_UNTIL = 0.0
_MAX_POINTS = 22
_CHUNK_SIZE = 8


def _key(coords):
    try:
        return tuple((round(float(p[0]), 5), round(float(p[1]), 5)) for p in coords)
    except Exception:
        return None


def _decode_polyline6(value: str) -> list[list[float]]:
    """Decode Valhalla's default 1e-6 encoded polyline into [lat, lon]."""
    out: list[list[float]] = []
    index = lat = lon = 0
    length = len(value or "")
    try:
        while index < length:
            result = shift = 0
            while True:
                b = ord(value[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            lat += ~(result >> 1) if result & 1 else result >> 1

            result = shift = 0
            while True:
                b = ord(value[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            lon += ~(result >> 1) if result & 1 else result >> 1
            out.append([lat / 1_000_000.0, lon / 1_000_000.0])
    except (IndexError, TypeError, ValueError):
        return []
    return out


def _shape_coords(shape) -> list[list[float]]:
    raw = None
    if isinstance(shape, dict):
        raw = shape.get("coordinates")
    elif isinstance(shape, list):
        raw = shape
    elif isinstance(shape, str):
        return _decode_polyline6(shape)
    if not isinstance(raw, list):
        return []
    out = []
    for point in raw:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lon, lat = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            row = [lat, lon]
            if not out or row != out[-1]:
                out.append(row)
    return out


def _append(target, segment):
    for point in segment or []:
        if not target or point != target[-1]:
            target.append(point)


def _parse_response(response) -> tuple[dict[str, Any] | None, str | None]:
    if not response.ok:
        return None, f"Valhalla HTTP {response.status_code}."
    try:
        data = response.json()
    except ValueError:
        return None, "Valhalla a renvoyé une réponse JSON invalide."
    trip = data.get("trip") or {}
    legs = trip.get("legs") or []
    merged: list[list[float]] = []
    for leg in legs:
        _append(merged, _shape_coords((leg or {}).get("shape")))
    if len(merged) < 2:
        _append(merged, _shape_coords(trip.get("shape")))
    if len(merged) < 2:
        return None, "Valhalla n'a renvoyé aucune géométrie pédestre exploitable."
    try:
        distance = float((trip.get("summary") or {}).get("length"))
    except (TypeError, ValueError):
        distance = 0.0
    if distance <= 0:
        for leg in legs:
            try:
                distance += float(((leg or {}).get("summary") or {}).get("length") or 0)
            except (TypeError, ValueError):
                pass
    return {
        "coords": merged,
        "distance": round(distance, 2),
        "fallback": False,
        "routing_mode": "valhalla-pedestrian-fallback",
        "profile": "pedestrian",
        "provider": "Valhalla/OpenStreetMap",
        "secondary_router": True,
        "recovered_from_primary_failure": True,
    }, None


def _request(coords) -> tuple[dict[str, Any] | None, str | None]:
    global _COOLDOWN_UNTIL
    now = time.monotonic()
    if now < _COOLDOWN_UNTIL:
        return None, "Valhalla ignoré après un échec récent."
    key = _key(coords)
    if key and key in _CACHE and now - _CACHE[key][0] < _CACHE_TTL:
        result = deepcopy(_CACHE[key][1])
        result["route_cache"] = True
        return result, None
    payload = {
        "locations": [{"lat": float(p[0]), "lon": float(p[1]), "type": "break"} for p in coords],
        "costing": "pedestrian",
        "units": "kilometers",
        "directions_type": "none",
        "shape_format": "geojson",
    }
    try:
        response = requests.post(
            _URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "TrekMap-France/9",
                "X-Client-Id": "trekmap-france.onrender.com",
            },
            timeout=_TIMEOUT,
        )
    except requests.Timeout:
        _COOLDOWN_UNTIL = time.monotonic() + 20.0
        return None, "Valhalla : délai dépassé."
    except requests.RequestException as exc:
        _COOLDOWN_UNTIL = time.monotonic() + 20.0
        return None, f"Valhalla inaccessible ({exc.__class__.__name__})."
    result, warning = _parse_response(response)
    if result is None:
        if response.status_code >= 500 or response.status_code == 429:
            _COOLDOWN_UNTIL = time.monotonic() + 20.0
        return None, warning
    if key:
        _CACHE[key] = (time.monotonic(), deepcopy(result))
        while len(_CACHE) > 120:
            _CACHE.pop(next(iter(_CACHE)))
    return result, None


def _route_secondary(coords) -> tuple[dict[str, Any] | None, str | None]:
    if len(coords) < 2 or len(coords) > _MAX_POINTS:
        return None, "Valhalla : nombre de points hors budget de secours."
    if len(coords) <= _CHUNK_SIZE:
        return _request(coords)

    merged: list[list[float]] = []
    total = 0.0
    chunks = 0
    start = 0
    while start < len(coords) - 1:
        end = min(len(coords), start + _CHUNK_SIZE)
        chunk = coords[start:end]
        result, warning = _request(chunk)
        if result is None:
            return None, warning
        _append(merged, result.get("coords") or [])
        try:
            total += float(result.get("distance") or 0)
        except (TypeError, ValueError):
            pass
        chunks += 1
        if end >= len(coords):
            break
        start = end - 1
        time.sleep(1.02)  # public demo fair-use limit: at most about one request/s
    if len(merged) < 2:
        return None, "Valhalla : géométrie segmentée vide."
    return {
        "coords": merged,
        "distance": round(total, 2),
        "fallback": False,
        "routing_mode": "valhalla-pedestrian-segmented-fallback" if chunks > 1 else "valhalla-pedestrian-fallback",
        "profile": "pedestrian",
        "provider": "Valhalla/OpenStreetMap",
        "secondary_router": True,
        "recovered_from_primary_failure": True,
        "segments": chunks,
    }, None


def _is_transient_primary_failure(route) -> bool:
    if not isinstance(route, dict) or route.get("fallback") is not True:
        return False
    text = str(route.get("warning") or "").casefold()
    if any(x in text for x in ("clé api refusée", "http 401", "http 403", "http 429", "limite de requêtes")):
        return False
    return any(x in text for x in (
        "http 500", "http 501", "http 502", "http 503", "http 504", "http 599",
        "indisponible", "délai", "delai", "timeout", "inaccessible", "ignoré",
    ))


def install_secondary_router(ors) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    primary_get_route = ors.get_route

    def get_route_with_secondary(coords, distance_gps):
        primary = primary_get_route(coords, distance_gps)
        if not _is_transient_primary_failure(primary):
            return primary
        secondary, secondary_warning = _route_secondary(coords)
        if secondary is not None:
            secondary["primary_warning"] = str(primary.get("warning") or "")[:300]
            return secondary
        result = dict(primary)
        if secondary_warning:
            result["secondary_warning"] = secondary_warning[:300]
            result["warning"] = (
                f"{primary.get('warning') or 'Routeur principal indisponible'} "
                f"Secours Valhalla: {secondary_warning}"
            ).strip()
        return result

    ors.get_route = get_route_with_secondary


__all__ = ["install_secondary_router", "_is_transient_primary_failure"]
