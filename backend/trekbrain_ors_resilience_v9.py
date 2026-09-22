"""Bounded pedestrian-router recovery for TrekBrain v9.

OpenRouteService remains the primary router. A complex multi-waypoint Directions
request can occasionally fail with HTTP 5xx while smaller pedestrian legs still
work, so this layer retries once and probes segmented legs. If ORS is genuinely
unavailable even on a small leg, TrekBrain now makes one bounded attempt with the
secondary Valhalla pedestrian router instead of immediately killing the trek.
"""
from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

_INSTALLED = False
_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 6 * 60 * 60
_MAX_SEGMENTS = 10


def _key(coords, snap_radius_m=None):
    try:
        points = tuple((round(float(p[0]), 5), round(float(p[1]), 5)) for p in coords)
    except Exception:
        return None
    return points, int(snap_radius_m) if snap_radius_m is not None else None


def _cached(coords, snap_radius_m=None):
    key = _key(coords, snap_radius_m)
    if key is None:
        return None
    row = _CACHE.get(key)
    if not row or time.monotonic() - row[0] > _CACHE_TTL:
        if row:
            _CACHE.pop(key, None)
        return None
    result = deepcopy(row[1])
    result["route_cache"] = True
    return result


def _remember(coords, snap_radius_m, result):
    key = _key(coords, snap_radius_m)
    if key is None or not isinstance(result, dict) or result.get("fallback") is not False:
        return
    _CACHE[key] = (time.monotonic(), deepcopy(result))
    while len(_CACHE) > 120:
        _CACHE.pop(next(iter(_CACHE)))


def _append_geometry(target, segment):
    for point in segment or []:
        if not target or point != target[-1]:
            target.append(point)


def _is_server_error(status) -> bool:
    try:
        return int(status) >= 500
    except (TypeError, ValueError):
        return False


def _secondary_route(coords):
    """Lazy import keeps the normal ORS path dependency-free and easy to test."""
    try:
        from .trekbrain_secondary_router_v9 import _route_secondary
        return _route_secondary(coords)
    except Exception as exc:
        return None, f"Routeur secondaire indisponible ({exc.__class__.__name__})."


def _secondary_or_primary_failure(coords, warning, status):
    secondary, secondary_warning = _secondary_route(coords)
    if secondary is not None:
        recovered = dict(secondary)
        recovered["primary_warning"] = str(warning or "")[:300]
        recovered["recovered_from_ors_5xx"] = True
        return recovered, None, 200
    combined = str(warning or "OpenRouteService indisponible.").strip()
    if secondary_warning:
        combined = f"{combined} Secours Valhalla: {secondary_warning}".strip()
    return None, combined, status


def install_ors_resilience(ors) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    raw_request = ors._request_route

    def resilient_request(coords, distance_gps, snap_radius_m=None):
        cached = _cached(coords, snap_radius_m)
        if cached is not None:
            return cached, None, 200

        result, warning, status = raw_request(coords, distance_gps, snap_radius_m)
        if result is not None:
            _remember(coords, snap_radius_m, result)
            return result, warning, status
        if not _is_server_error(status):
            return result, warning, status

        # One retry absorbs a short-lived ORS worker failure without turning a
        # 30-second interactive request into a retry festival.
        time.sleep(0.22)
        retry, retry_warning, retry_status = raw_request(coords, distance_gps, snap_radius_m)
        if retry is not None:
            retry = dict(retry)
            retry["recovered_from_ors_5xx"] = True
            retry["routing_mode"] = "ors-5xx-retry"
            _remember(coords, snap_radius_m, retry)
            return retry, None, 200

        warning = retry_warning or warning
        status = retry_status if retry_status is not None else status
        if not _is_server_error(status):
            return None, warning, status

        # Two-point requests cannot be split any further. Likewise, an enormous
        # waypoint list is deliberately not exploded into dozens of ORS calls.
        # In both cases, use the independent pedestrian fallback.
        if len(coords) < 3 or len(coords) - 1 > _MAX_SEGMENTS:
            recovered, recovered_warning, recovered_status = _secondary_or_primary_failure(coords, warning, status)
            if recovered is not None:
                _remember(coords, snap_radius_m, recovered)
            return recovered, recovered_warning, recovered_status

        # A multi-waypoint request may itself be what ORS dislikes. Probe legs
        # individually. If even a tiny leg fails after one retry, that is strong
        # evidence of a provider-side outage and we switch providers once.
        merged = []
        total = 0.0
        segment_count = len(coords) - 1
        for index, (a, b) in enumerate(zip(coords, coords[1:]), start=1):
            leg, leg_warning, leg_status = raw_request([a, b], distance_gps, snap_radius_m)
            if leg is None and _is_server_error(leg_status):
                time.sleep(0.12)
                leg, leg_warning2, leg_status2 = raw_request([a, b], distance_gps, snap_radius_m)
                leg_warning = leg_warning2 or leg_warning
                leg_status = leg_status2 if leg_status2 is not None else leg_status
            if leg is None:
                segment_warning = (
                    f"OpenRouteService reste indisponible sur le segment pédestre "
                    f"{index}/{segment_count}. {leg_warning or warning or ''}"
                ).strip()
                recovered, recovered_warning, recovered_status = _secondary_or_primary_failure(
                    coords, segment_warning, leg_status
                )
                if recovered is not None:
                    _remember(coords, snap_radius_m, recovered)
                return recovered, recovered_warning, recovered_status
            _append_geometry(merged, leg.get("coords") or [])
            try:
                total += float(leg.get("distance") or 0)
            except (TypeError, ValueError):
                pass

        if len(merged) < 2:
            recovered, recovered_warning, recovered_status = _secondary_or_primary_failure(
                coords,
                warning or "OpenRouteService n'a produit aucune géométrie exploitable.",
                status,
            )
            if recovered is not None:
                _remember(coords, snap_radius_m, recovered)
            return recovered, recovered_warning, recovered_status

        recovered = {
            "coords": merged,
            "distance": round(total, 2),
            "fallback": False,
            "routing_mode": "ors-segmented-5xx-recovery",
            "profile": getattr(ors, "ORS_PROFILE", "foot-hiking"),
            "recovered_from_ors_5xx": True,
            "segments": segment_count,
        }
        _remember(coords, snap_radius_m, recovered)
        return recovered, None, 200

    ors._request_route = resilient_request


__all__ = ["install_ors_resilience"]
