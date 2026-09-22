"""Preserve trusted hiking-relation geometry while adding overnight detours.

A closed GR relation is already a real mapped walking corridor. Re-routing the
whole loop through a sparse set of daily/campsite waypoints can make a fallback
router shortcut, snap badly, or concatenate disconnected legs. That is exactly
how a valid GR 340 loop could become a route with a multi-kilometre geometric
jump at the final safety gate.

This overlay keeps the relation itself as the backbone and asks the pedestrian
router only for small out-and-back connectors from the GR to each selected stay.
The final polyline is accepted only when every connector is routed and joins the
relation continuously. No straight-line bridge is inserted.
"""
from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
import math
from typing import Any

from fastapi import HTTPException

_INSTALLED = False
_ACTIVE_RELATION: ContextVar[dict[str, Any] | None] = ContextVar(
    "trekbrain_v9_active_relation_backbone", default=None
)
_MAX_JOIN_KM = 0.18
_MAX_CONNECTOR_GAP_KM = 0.55


def _dist(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(
        math.radians,
        (float(a[0]), float(a[1]), float(b[0]), float(b[1])),
    )
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _length(coords) -> float:
    return sum(_dist(a, b) for a, b in zip(coords or [], (coords or [])[1:]))


def _max_gap(coords) -> float:
    return max((_dist(a, b) for a, b in zip(coords or [], (coords or [])[1:])), default=0.0)


def _append(target: list[list[float]], segment) -> None:
    for point in segment or []:
        row = [float(point[0]), float(point[1])]
        if not target or row != target[-1]:
            target.append(row)


def _connector_for_stay(ors, legacy_main, anchor, stay):
    request = [
        [float(anchor[0]), float(anchor[1])],
        [float(stay["lat"]), float(stay["lon"])],
        [float(anchor[0]), float(anchor[1])],
    ]
    routed = ors.get_route(request, legacy_main.distance_gps)
    if not isinstance(routed, dict) or routed.get("fallback") is not False:
        warning = str((routed or {}).get("warning") or "connecteur pédestre non validé")
        return None, warning
    coords = routed.get("coords") or []
    if len(coords) < 2:
        return None, "connecteur de nuitée vide"
    if _max_gap(coords) > _MAX_CONNECTOR_GAP_KM:
        return None, f"connecteur discontinu ({_max_gap(coords):.1f} km)"
    if _dist(anchor, coords[0]) > _MAX_JOIN_KM or _dist(coords[-1], anchor) > _MAX_JOIN_KM:
        return None, "le routeur a trop éloigné le connecteur de sa jonction au GR"
    stay_point = [float(stay["lat"]), float(stay["lon"])]
    nearest_stay = min((_dist(point, stay_point) for point in coords), default=float("inf"))
    if nearest_stay > 0.55:
        return None, f"le connecteur ne dessert pas réellement la nuitée ({nearest_stay:.1f} km)"
    return routed, None


def _stitch_relation_with_stays(relation, stays, ors, legacy_main):
    base = [[float(p[0]), float(p[1])] for p in (relation.get("coords") or [])]
    if len(base) < 4 or _max_gap(base) > 1.0:
        return None, "géométrie de relation principale discontinue"

    rows = []
    for stay in stays or []:
        try:
            idx = int(stay.get("_route_index"))
            lat, lon = float(stay["lat"]), float(stay["lon"])
        except (TypeError, ValueError, KeyError):
            return None, "une nuitée n'est pas correctement projetée sur le GR"
        idx = max(1, min(idx, len(base) - 2))
        item = dict(stay)
        item["lat"], item["lon"] = lat, lon
        rows.append((idx, item))
    rows.sort(key=lambda row: row[0])

    out: list[list[float]] = []
    cursor = 0
    connector_km = 0.0
    connector_modes = []
    for idx, stay in rows:
        if idx < cursor:
            return None, "ordre des nuitées incohérent sur la relation"
        _append(out, base[cursor:idx + 1])
        anchor = base[idx]
        connector, warning = _connector_for_stay(ors, legacy_main, anchor, stay)
        if connector is None:
            return None, warning
        connector_coords = connector.get("coords") or []
        if out and connector_coords and _dist(out[-1], connector_coords[0]) > _MAX_JOIN_KM:
            return None, "jonction GR vers nuitée trop éloignée"
        _append(out, connector_coords)
        if out and _dist(out[-1], anchor) > _MAX_JOIN_KM:
            return None, "retour de nuitée vers le GR incomplet"
        connector_km += float(connector.get("distance") or _length(connector_coords))
        connector_modes.append(str(connector.get("routing_mode") or "pedestrian"))
        cursor = idx
    _append(out, base[cursor:])

    if len(out) < 4:
        return None, "géométrie finale vide"
    gap = _max_gap(out)
    if gap > _MAX_CONNECTOR_GAP_KM:
        return None, f"géométrie finale encore discontinue ({gap:.1f} km)"

    polyline_km = _length(out)
    expected = float(relation.get("distance") or _length(base)) + connector_km
    # Polyline and routed summaries need not be identical, but a large mismatch
    # means a provider probably returned malformed geometry.
    if expected > 0 and not (0.82 <= polyline_km / expected <= 1.18):
        return None, "distance des connecteurs incohérente avec leur géométrie"
    return {
        "coords": out,
        "distance": round(polyline_km, 2),
        "fallback": False,
        "routing_mode": "osm-hiking-relation-loop-with-routed-stays",
        "profile": "hiking-relation+pedestrian-connectors",
        "provider": "OpenStreetMap hiking relation + pedestrian connectors",
        "relation_ref": relation.get("relation_ref"),
        "relation_name": relation.get("relation_name"),
        "relation_source_url": relation.get("relation_source_url"),
        "relation_geometry": True,
        "connector_modes": connector_modes,
        "max_segment_gap_km": round(gap, 3),
    }, None


def install_relation_stitch(roundtrip, ors, v3) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    current_best = roundtrip._best_roundtrip
    current_build = roundtrip._build_roundtrip

    def best_roundtrip(start, target_km, daily_min, daily_max, days, planner_v3):
        _ACTIVE_RELATION.set(None)
        route = current_best(start, target_km, daily_min, daily_max, days, planner_v3)
        if isinstance(route, dict) and route.get("relation_geometry") is True:
            _ACTIVE_RELATION.set(deepcopy(route))
        return route

    def build_roundtrip(data, legacy_main, planner_v3):
        _ACTIVE_RELATION.set(None)
        result = current_build(data, legacy_main, planner_v3)
        relation = _ACTIVE_RELATION.get()
        if not relation:
            return result

        preview = result.get("route_preview") or {}
        accommodations = [dict(x) for x in (result.get("accommodations") or []) if isinstance(x, dict)]
        preview_gap = _max_gap(preview.get("coords") or [])

        if accommodations:
            repaired, warning = _stitch_relation_with_stays(relation, accommodations, ors, legacy_main)
            if repaired is None:
                if preview_gap > 3.0:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Le GR principal est bien trouvé, mais le raccord vers au moins une nuitée "
                            f"n'est pas continu : {warning or 'raison inconnue'}."
                        ),
                    )
                return result
            route = repaired
        else:
            # No overnight detour: if a later router accidentally damaged a valid
            # relation, restore the relation itself rather than failing safety.
            if preview_gap <= 3.0:
                return result
            route = deepcopy(relation)

        coords = route.get("coords") or []
        total = float(route.get("distance") or _length(coords))
        start = result.get("start") or {}
        boundaries = [start] + accommodations + [start] if accommodations else None
        if boundaries:
            distances = planner_v3._stage_distances(coords, boundaries, legacy_main, total)
            if len(distances) == len(result.get("stages") or []):
                for stage, distance in zip(result.get("stages") or [], distances):
                    stage["distance_km"] = round(float(distance), 1)

        result["distance_km"] = round(total, 1)
        result["route_preview"] = {
            "coords": coords,
            "distance_km": round(total, 2),
            "distance": round(total, 2),
            "fallback": False,
            "routing_mode": route.get("routing_mode"),
            "profile": route.get("profile"),
            "provider": route.get("provider"),
            "relation_ref": route.get("relation_ref"),
            "relation_name": route.get("relation_name"),
            "relation_source_url": route.get("relation_source_url"),
            "relation_geometry": True,
            "max_segment_gap_km": round(_max_gap(coords), 3),
        }
        result["planner_fallback"] = "osm-hiking-relation-loop-with-local-stays"
        notes = list(result.get("advisor_notes") or [])
        notes.append(
            "Le GR reste l'axe principal ; seules les petites branches vers les nuitées sont routées séparément, puis raccordées au même point du GR."
        )
        result["advisor_notes"] = list(dict.fromkeys(notes))
        return result

    roundtrip._best_roundtrip = best_roundtrip
    roundtrip._build_roundtrip = build_roundtrip


__all__ = [
    "install_relation_stitch",
    "_stitch_relation_with_stays",
    "_max_gap",
]
