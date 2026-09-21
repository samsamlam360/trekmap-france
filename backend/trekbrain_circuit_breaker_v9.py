"""Per-process circuit breakers for slow external TrekBrain services.

Interactive planning should fail over after one clear network timeout instead of
repeating the same doomed request for every candidate, snap retry and route leg.
Successful calls immediately keep the circuit healthy; only connectivity/time
failures open a short cooldown.
"""
from __future__ import annotations

import time
from threading import Lock

_INSTALLED = False
_LOCK = Lock()
_STATE = {"overpass": 0.0, "ors": 0.0, "matrix": 0.0}


def _open(name: str, seconds: float = 15.0) -> None:
    with _LOCK:
        _STATE[name] = max(float(_STATE.get(name, 0.0)), time.monotonic() + seconds)


def _closed(name: str) -> bool:
    with _LOCK:
        return time.monotonic() >= float(_STATE.get(name, 0.0))


def _network_failure(text: str) -> bool:
    low = str(text or "").casefold()
    return any(x in low for x in (
        "délai", "delai", "timeout", "inaccessible", "injoignable",
        "connexion", "connection", "temporairement indisponible",
    ))


def install_circuit_breakers(v3, ors, roundtrip) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from . import free_planner_v2 as free

    current_overpass = v3._overpass
    current_request_route = ors._request_route
    current_matrix = ors.get_distance_matrix
    current_roundtrip = roundtrip._roundtrip_request

    def guarded_overpass(query: str):
        if not _closed("overpass"):
            raise RuntimeError("OpenStreetMap/Overpass ignoré après un timeout récent pour préserver le budget interactif.")
        try:
            return current_overpass(query)
        except RuntimeError as exc:
            if _network_failure(str(exc)):
                _open("overpass")
            raise

    def guarded_request_route(coords, distance_gps, snap_radius_m=None):
        if not _closed("ors"):
            return None, "OpenRouteService ignoré après un timeout récent pour préserver le budget interactif.", 599
        result, warning, status = current_request_route(coords, distance_gps, snap_radius_m)
        if result is None and (status is None or status >= 500) and _network_failure(warning or ""):
            _open("ors")
            # 599 is deliberately treated as a server/network failure by
            # ors.get_route, which prevents snap + segmented retry storms.
            status = 599
        return result, warning, status

    def guarded_matrix(coords):
        if not _closed("matrix"):
            return {"distances": None, "fallback": True, "warning": "ORS Matrix ignorée après un timeout récent."}
        result = current_matrix(coords)
        if isinstance(result, dict) and result.get("fallback") and _network_failure(result.get("warning") or ""):
            _open("matrix")
        return result

    def guarded_roundtrip(start, target_km, seed):
        if not _closed("ors"):
            return None, "OpenRouteService round-trip ignoré après un timeout récent."
        result, warning = current_roundtrip(start, target_km, seed)
        if result is None and _network_failure(warning or ""):
            _open("ors")
        return result, warning

    # _nearby executes in free_planner_v2 and resolves _overpass from that
    # module's globals, while GR/network code calls v3._overpass directly.
    v3._overpass = guarded_overpass
    free._overpass = guarded_overpass
    ors._request_route = guarded_request_route
    ors.get_distance_matrix = guarded_matrix
    roundtrip._roundtrip_request = guarded_roundtrip


__all__ = ["install_circuit_breakers"]
