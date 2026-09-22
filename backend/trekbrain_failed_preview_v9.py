"""Request-local provisional route capture for failed TrekBrain v9 plans.

When planning ultimately fails, the user may still want to inspect the last route
candidate that reached the routing layer.  This module captures that candidate in
a ContextVar so it cannot leak between concurrent requests/users.  A captured
route is diagnostic only: it may violate requested constraints or come from an
unvalidated direct fallback, so the frontend must label it as provisional.
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


def _capture(result) -> None:
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
        "warning": str(result.get("warning") or "").strip()[:500],
        "provisional": True,
    })


def install_failed_preview_capture(ors) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    current_get_route = ors.get_route

    def captured_get_route(coords, distance_gps):
        result = current_get_route(coords, distance_gps)
        _capture(result)
        return result

    ors.get_route = captured_get_route


__all__ = [
    "install_failed_preview_capture",
    "clear_failed_preview",
    "get_failed_preview",
]
