"""Request-local provisional route capture for failed TrekBrain v9 plans.

When planning ultimately fails, the user may still want to inspect the last route
candidate that reached the routing layer. This module captures both the candidate
waypoints *before* a routing call and any better ORS geometry returned afterwards.
That matters when ORS itself raises/fails before producing a normal result: the UI
can still show what TrekBrain was trying to build instead of exposing a dead button.

Everything stored here is diagnostic only and request-local. A candidate-only
preview may connect sparse waypoints and must never be presented as a validated
walking route.
"""
from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from typing import Any

_INSTALLED = False
_LAST_PREVIEW: ContextVar[dict[str, Any] | None] = ContextVar(
    "trekbrain_v9_failed_preview", default=None
)
_MAX_POINTS = 3000


def clear_failed_preview() -> None:
    _LAST_PREVIEW.set(None)


def get_failed_preview() -> dict[str, Any] | None:
    value = _LAST_PREVIEW.get()
    return deepcopy(value) if isinstance(value, dict) else None


def _clean_coords(value):
    out = []
    for point in value or []:
        try:
            lat, lon = float(point[0]), float(point[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        out.append([lat, lon])
        if len(out) >= _MAX_POINTS:
            break
    return out


def _safe_distance(coords, distance_gps) -> float:
    try:
        value = float(distance_gps(coords))
        return round(value, 2) if value >= 0 else 0.0
    except Exception:
        return 0.0


def _capture_candidate(coords, distance_gps) -> None:
    """Store route inputs before calling ORS.

    This is intentionally lower confidence than a routed geometry. It is only a
    visual explanation of the candidate TrekBrain was attempting to validate.
    A later successful/fallback routing result will overwrite it with richer data.
    """
    clean = _clean_coords(coords)
    if len(clean) < 2:
        return
    _LAST_PREVIEW.set({
        "coords": clean,
        "distance_km": _safe_distance(clean, distance_gps),
        "routing_mode": "candidate-waypoints",
        "routing_validated": False,
        "candidate_only": True,
        "warning": (
            "Aperçu des points candidats avant validation du routage. "
            "Les segments entre ces points ne sont pas un itinéraire pédestre validé."
        ),
        "provisional": True,
    })


def capture_failed_preview(result) -> None:
    """Capture the best geometry produced so far by a routing layer."""
    if not isinstance(result, dict):
        return
    coords = _clean_coords(result.get("coords"))
    if len(coords) < 2:
        return
    try:
        distance = round(float(result.get("distance") or 0), 2)
    except (TypeError, ValueError):
        distance = 0.0
    _LAST_PREVIEW.set({
        "coords": coords,
        "distance_km": distance,
        "routing_mode": str(result.get("routing_mode") or "provisional"),
        "routing_validated": result.get("fallback") is False,
        "candidate_only": False,
        "warning": str(result.get("warning") or "").strip()[:500],
        "provisional": True,
    })


def install_failed_preview_capture(ors, roundtrip=None) -> None:
    """Capture normal ORS candidates plus direct ORS round-trip geometry."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    current_get_route = ors.get_route

    def captured_get_route(coords, distance_gps):
        # Capture first. If a wrapper unexpectedly raises on HTTP 5xx, the
        # failure screen still has something useful to display.
        _capture_candidate(coords, distance_gps)
        result = current_get_route(coords, distance_gps)
        capture_failed_preview(result)
        return result

    ors.get_route = captured_get_route

    # trekbrain_roundtrip_v9 talks to ORS directly instead of ors.get_route.
    # Without this hook a perfectly real round-trip could be rejected later by
    # the daily-distance gate, yet the "Voir quand même" button received no
    # geometry at all.
    if roundtrip is not None and hasattr(roundtrip, "_roundtrip_request"):
        current_roundtrip_request = roundtrip._roundtrip_request

        def captured_roundtrip_request(start, target_km, seed):
            result, warning = current_roundtrip_request(start, target_km, seed)
            if isinstance(result, dict):
                capture_failed_preview(result)
            return result, warning

        roundtrip._roundtrip_request = captured_roundtrip_request


__all__ = [
    "install_failed_preview_capture",
    "clear_failed_preview",
    "get_failed_preview",
    "capture_failed_preview",
]
