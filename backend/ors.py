"""OpenRouteService client for TrekMap France.

The planner first asks ORS for the complete walking route. If a complex
multi-waypoint request cannot be snapped reliably, it retries with a moderate
walking-network snap radius and, as a last *validated* fallback, computes each
leg separately. Straight lines remain diagnostics only and are never marked as
validated routing.
"""

import os
from typing import Any

import requests

ORS_API_KEY = os.getenv("ORS_API_KEY", "").strip()
ORS_URL = "https://api.heigit.org/openrouteservice/v2/directions/foot-walking/geojson"
SNAP_RADIUS_M = max(350, min(int(os.getenv("TREKBRAIN_ORS_SNAP_RADIUS_M", "800") or 800), 1500))


def _fallback(coords, distance_gps, warning: str | None = None):
    result = {
        "coords": coords,
        "distance": distance_gps(coords),
        "fallback": True,
        "routing_mode": "unvalidated-direct-diagnostic",
    }
    if warning:
        result["warning"] = warning
    return result


def _parse_response(response, coords, distance_gps):
    if response.status_code in (401, 403):
        return None, f"OpenRouteService : clé API refusée (HTTP {response.status_code}).", response.status_code
    if response.status_code == 429:
        return None, "OpenRouteService : limite de requêtes atteinte (HTTP 429).", response.status_code
    if response.status_code >= 500:
        return None, f"OpenRouteService indisponible temporairement (HTTP {response.status_code}).", response.status_code
    if not response.ok:
        detail = ""
        try:
            payload = response.json()
            detail = str((payload.get("error") or {}).get("message") or payload.get("message") or "").strip()
        except Exception:
            detail = ""
        suffix = f" : {detail[:180]}" if detail else ""
        return None, f"OpenRouteService a répondu HTTP {response.status_code}{suffix}.", response.status_code

    try:
        data: dict[str, Any] = response.json()
    except ValueError:
        return None, "OpenRouteService a renvoyé une réponse JSON invalide.", response.status_code

    feature = (data.get("features") or [None])[0]
    if not feature:
        return None, "OpenRouteService n'a renvoyé aucun tracé.", response.status_code

    geometry = feature.get("geometry", {}).get("coordinates", [])
    summary = feature.get("properties", {}).get("summary", {})
    route = [[float(p[1]), float(p[0])] for p in geometry if len(p) >= 2]
    if len(route) < 2 or "distance" not in summary:
        return None, "Réponse OpenRouteService invalide : aucun tracé pédestre exploitable.", response.status_code

    return {
        "coords": route,
        "distance": round(float(summary["distance"]) / 1000, 2),
        "fallback": False,
        "routing_mode": "ors",
    }, None, response.status_code


def _request_route(coords, distance_gps, snap_radius_m: int | None = None):
    payload: dict[str, Any] = {
        "coordinates": [[float(p[1]), float(p[0])] for p in coords],
        "instructions": False,
    }
    if snap_radius_m is not None:
        payload["radiuses"] = [int(snap_radius_m)] * len(coords)

    try:
        response = requests.post(
            ORS_URL,
            json=payload,
            headers={
                "Authorization": ORS_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=25,
        )
    except requests.Timeout:
        return None, "OpenRouteService : délai d'attente dépassé.", None
    except requests.RequestException as exc:
        return None, f"OpenRouteService inaccessible ({exc.__class__.__name__}).", None
    except Exception:
        return None, "Erreur inattendue avec OpenRouteService.", None
    return _parse_response(response, coords, distance_gps)


def _append_geometry(target, segment):
    for point in segment:
        if not target or point != target[-1]:
            target.append(point)


def _segmented_route(coords, distance_gps):
    """Route every consecutive leg; every returned metre still comes from ORS."""
    if len(coords) < 2:
        return None, "Pas assez de points pour un routage segmenté."

    merged = []
    total = 0.0
    retries = 0
    for index, (a, b) in enumerate(zip(coords, coords[1:]), start=1):
        result, warning, status = _request_route([a, b], distance_gps)
        if result is None and status not in {401, 403, 429} and not (status and status >= 500):
            result, warning2, _ = _request_route([a, b], distance_gps, SNAP_RADIUS_M)
            retries += 1
            warning = warning2 or warning
        if result is None:
            return None, f"Segment pédestre {index}/{len(coords)-1} non routable. {warning or ''}".strip()
        _append_geometry(merged, result["coords"])
        total += float(result.get("distance") or 0)

    if len(merged) < 2:
        return None, "Le routage segmenté n'a produit aucune géométrie exploitable."
    return {
        "coords": merged,
        "distance": round(total, 2),
        "fallback": False,
        "routing_mode": "ors-segmented",
        "snap_retries": retries,
    }, None


def get_route(coords, distance_gps):
    """Return a walking route validated by ORS, or an explicitly unsafe diagnostic fallback."""
    fallback = _fallback(coords, distance_gps)

    if not ORS_API_KEY:
        return {
            **fallback,
            "warning": "OpenRouteService non configuré : ORS_API_KEY est absente du serveur Render.",
        }
    if len(coords) < 2:
        return {**fallback, "warning": "OpenRouteService : au moins deux points sont nécessaires."}

    first_warning = None
    # ORS accepts a limited number of waypoints. For larger generated routes we
    # skip directly to the fully validated leg-by-leg strategy.
    if len(coords) <= 50:
        result, warning, status = _request_route(coords, distance_gps)
        if result is not None:
            return result
        first_warning = warning

        # A campsite or POI can sit inside a parcel rather than exactly on the
        # walking graph. Retry with a moderate snap radius, never kilometres of
        # blind straight-line tolerance.
        if status not in {401, 403, 429} and not (status and status >= 500):
            result, warning2, _ = _request_route(coords, distance_gps, SNAP_RADIUS_M)
            if result is not None:
                result["routing_mode"] = "ors-snapped"
                result["snap_radius_m"] = SNAP_RADIUS_M
                return result
            first_warning = warning2 or first_warning
        elif status in {401, 403, 429} or (status and status >= 500):
            return {**fallback, "warning": first_warning or "OpenRouteService indisponible."}

    # Complex waypoint sets can fail as one request even though every walking
    # leg is routable. Recover only by asking ORS for *every* consecutive leg.
    segmented, segmented_warning = _segmented_route(coords, distance_gps)
    if segmented is not None:
        if first_warning:
            segmented["recovered_from"] = first_warning[:300]
        return segmented

    warning = segmented_warning or first_warning or "OpenRouteService n'a pas pu valider ce tracé."
    return {**fallback, "warning": warning}
