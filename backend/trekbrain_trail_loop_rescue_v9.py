"""Closed hiking-relation rescue for TrekBrain v9.

Some excellent multi-day loops already exist as complete OSM hiking relations.
Belle-Île-en-Mer's coastal GR is the motivating case: asking ORS to invent a
round trip is both less accurate and less reliable than using the actual hiking
relation that describes the loop.  This overlay therefore gives a closed,
continuous GR/GRP relation priority before the ORS round-trip fallback.

The geometry is never replaced by straight lines.  Tiny relation closure gaps may
be joined only by the normal pedestrian router, which itself has the independent
secondary-provider recovery installed in v9.
"""
from __future__ import annotations

from contextvars import ContextVar
import math
import re
from typing import Any

from fastapi import HTTPException

_INSTALLED = False
_LAST_META: ContextVar[dict[str, Any] | None] = ContextVar(
    "trekbrain_v9_trail_loop_meta", default=None
)
_DIRECT_CLOSE_KM = 0.10
_ROUTABLE_CLOSE_KM = 1.8
_MAX_START_OFFSET_KM = 12.0
_MAX_RELATION_GAP_KM = 2.2
_MAX_SECONDARY_POINTS = 21


def _dist(a, b) -> float:
    if isinstance(a, dict):
        a = [a["lat"], a["lon"]]
    if isinstance(b, dict):
        b = [b["lat"], b["lon"]]
    lat1, lon1, lat2, lon2 = map(math.radians, (float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _length(coords) -> float:
    return sum(_dist(a, b) for a, b in zip(coords or [], (coords or [])[1:]))


def _max_gap(coords) -> float:
    return max((_dist(a, b) for a, b in zip(coords or [], (coords or [])[1:])), default=0.0)


def _nearest_index(coords, point) -> tuple[int, float]:
    if not coords:
        return 0, float("inf")
    best_i, best_d = 0, float("inf")
    for i, coord in enumerate(coords):
        value = _dist(coord, point)
        if value < best_d:
            best_i, best_d = i, value
    return best_i, best_d


def _preferred_score(trail: dict[str, Any], target_km: float, start_off: float, length_km: float) -> float:
    ref = str(trail.get("ref") or "").casefold().replace(" ", "")
    name = str(trail.get("name") or "").casefold()
    gr_bonus = -14.0 if re.search(r"\bgr\s*\d", str(trail.get("ref") or ""), flags=re.I) else 0.0
    # GR 340 gets no hard-coded route geometry; this only breaks ties when it is
    # actually returned by OSM near the request and its length fits the trek.
    gr340_bonus = -6.0 if "gr340" in ref or "gr 340" in name else 0.0
    return abs(length_km - float(target_km)) + start_off * 0.7 + gr_bonus + gr340_bonus


def _close_relation(coords, legacy_distance=None):
    """Return a real closed geometry or None.

    A sub-100 m endpoint discrepancy is normal relation bookkeeping and may be
    closed directly.  Larger gaps must be joined by an actual pedestrian router.
    """
    if len(coords) < 4:
        return None, "relation trop courte"
    coords = [[float(p[0]), float(p[1])] for p in coords]
    if _max_gap(coords) > _MAX_RELATION_GAP_KM:
        return None, "relation discontinue"
    closure = _dist(coords[-1], coords[0])
    if closure <= _DIRECT_CLOSE_KM:
        if coords[-1] != coords[0]:
            coords.append(list(coords[0]))
        return coords, None
    if closure > _ROUTABLE_CLOSE_KM:
        return None, f"relation non fermée ({closure:.1f} km)"

    try:
        from . import ors
        routed = ors.get_route([coords[-1], coords[0]], legacy_distance or _length)
    except Exception as exc:
        return None, f"fermeture pédestre indisponible ({exc.__class__.__name__})"
    if not isinstance(routed, dict) or routed.get("fallback") is not False:
        return None, "fermeture pédestre non validée"
    connector = routed.get("coords") or []
    if len(connector) < 2:
        return None, "fermeture pédestre vide"
    for point in connector[1:]:
        if point != coords[-1]:
            coords.append([float(point[0]), float(point[1])])
    if _dist(coords[-1], coords[0]) > 0.05:
        return None, "fermeture pédestre incomplète"
    if coords[-1] != coords[0]:
        coords.append(list(coords[0]))
    return coords, None


def _rotate_closed(coords, index: int):
    if len(coords) < 4:
        return coords
    ring = list(coords)
    if _dist(ring[0], ring[-1]) <= 0.05:
        ring = ring[:-1]
    if not ring:
        return coords
    index = max(0, min(int(index), len(ring) - 1))
    out = ring[index:] + ring[:index]
    out.append(list(out[0]))
    return out


def _relation_loop(v3, gr, start: dict[str, Any], target_km: float):
    radius = min(45.0, max(14.0, float(target_km) * 0.36))
    try:
        trails = list(gr._discover(v3, start, radius) or [])
    except Exception as exc:
        return None, f"découverte des GR impossible ({exc.__class__.__name__})"
    if not trails:
        return None, "aucune relation de randonnée GR/GRP trouvée"

    rows = []
    reasons = []
    for trail in trails:
        raw = trail.get("coords") or []
        if len(raw) < 8:
            continue
        closed, reason = _close_relation(raw, _length)
        if not closed:
            if reason:
                reasons.append(reason)
            continue
        relation_km = _length(closed)
        # Avoid selecting a tiny local circuit or a huge national relation merely
        # because it passes near the requested place.
        if relation_km < max(10.0, float(target_km) * 0.62) or relation_km > float(target_km) * 1.42:
            continue
        idx, start_off = _nearest_index(closed[:-1], start)
        if start_off > _MAX_START_OFFSET_KM:
            continue
        score = _preferred_score(trail, target_km, start_off, relation_km)
        rows.append((score, trail, closed, idx, start_off, relation_km))

    if not rows:
        detail = reasons[0] if reasons else "aucune relation fermée de longueur compatible"
        return None, detail
    rows.sort(key=lambda row: row[0])
    _, trail, closed, idx, start_off, relation_km = rows[0]
    rotated = _rotate_closed(closed, idx)
    if len(rotated) < 4 or _max_gap(rotated) > _MAX_RELATION_GAP_KM:
        return None, "géométrie GR finale discontinue"

    first = rotated[0]
    # The generic round-trip fallback otherwise starts at a geocoded centre,
    # which can sit several kilometres inland.  With no explicit fixed departure
    # in that fallback, start on the actual hiking relation instead.
    start["lat"] = float(first[0])
    start["lon"] = float(first[1])
    ref = str(trail.get("ref") or "").strip()
    label = ref or str(trail.get("name") or "itinéraire balisé").strip()
    start["name"] = f"Départ sur {label}"[:120]
    start["category"] = "trail"

    result = {
        "coords": rotated,
        "distance": round(_length(rotated), 2),
        "fallback": False,
        "routing_mode": "osm-hiking-relation-loop",
        "profile": "hiking-relation",
        "provider": "OpenStreetMap hiking relation",
        "relation_ref": ref,
        "relation_name": str(trail.get("name") or "")[:160],
        "relation_source_url": trail.get("source_url"),
        "relation_geometry": True,
        "start_offset_before_snap_km": round(float(start_off), 2),
    }
    _LAST_META.set({
        "ref": ref,
        "name": str(trail.get("name") or "")[:160],
        "source_url": trail.get("source_url"),
        "distance_km": round(relation_km, 2),
    })
    return result, None


def _compact_route_points(points):
    """Keep every overnight detour while staying under secondary-router budget."""
    if len(points) <= _MAX_SECONDARY_POINTS:
        return points
    fixed = {0, len(points) - 1}
    for i, point in enumerate(points):
        category = str((point or {}).get("category") or "").casefold()
        if category in {"camping", "refuge"}:
            fixed.add(i)
            if i > 0:
                fixed.add(i - 1)
            if i + 1 < len(points):
                fixed.add(i + 1)
    remaining = [i for i in range(1, len(points) - 1) if i not in fixed]
    budget = max(0, _MAX_SECONDARY_POINTS - len(fixed))
    if budget and remaining:
        if budget >= len(remaining):
            fixed.update(remaining)
        else:
            for n in range(budget):
                pos = round((len(remaining) - 1) * n / max(1, budget - 1)) if budget > 1 else len(remaining) // 2
                fixed.add(remaining[pos])
    return [points[i] for i in sorted(fixed)]


def install_trail_loop_rescue(roundtrip, gr) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_best = roundtrip._best_roundtrip
    original_points = roundtrip._route_points_with_stays
    original_build_roundtrip = roundtrip._build_roundtrip

    def best_roundtrip(start, target_km, daily_min, daily_max, days, v3):
        _LAST_META.set(None)
        relation, relation_warning = _relation_loop(v3, gr, start, target_km)
        if relation is not None:
            return relation
        try:
            return original_best(start, target_km, daily_min, daily_max, days, v3)
        except HTTPException as exc:
            detail = str(getattr(exc, "detail", exc) or "")
            if relation_warning:
                detail = f"{detail} Secours GR/GRP: {relation_warning}.".strip()
            raise HTTPException(status_code=exc.status_code, detail=detail)

    def compact_points(coords, start, stays, days):
        return _compact_route_points(original_points(coords, start, stays, days))

    def build_roundtrip(data, legacy_main, v3):
        result = original_build_roundtrip(data, legacy_main, v3)
        route_preview = result.get("route_preview") or {}
        if route_preview.get("routing_mode") == "osm-hiking-relation-loop":
            meta = _LAST_META.get() or {}
            ref = str(meta.get("ref") or "GR/GRP").strip()
            result["description"] = (
                f"Boucle basée sur la relation de randonnée {ref} réellement cartographiée dans OpenStreetMap."
            )
            notes = [
                f"Le tracé principal suit la relation de randonnée {ref} au lieu de demander à ORS d'inventer une boucle.",
                "La relation de randonnée est une forte preuve de cheminement, mais l'état du sentier et les éventuelles déviations restent à vérifier avant le départ.",
            ]
            if result.get("accommodations"):
                notes.append("Les détours vers les nuitées ont été recalculés séparément sur le réseau pédestre.")
            result["advisor_notes"] = notes
            result["planner_fallback"] = "osm-hiking-relation-loop"
            confidence = result.setdefault("confidence", {})
            confidence["score"] = max(int(confidence.get("score") or 0), 84)
            confidence["limitations"] = [
                "Relation OSM de randonnée utilisée comme axe principal ; vérifier fermetures et déviations temporaires."
            ]
            route_preview["provider"] = "OpenStreetMap hiking relation"
            route_preview["relation_ref"] = meta.get("ref")
            route_preview["relation_name"] = meta.get("name")
            route_preview["relation_source_url"] = meta.get("source_url")
        return result

    roundtrip._best_roundtrip = best_roundtrip
    roundtrip._route_points_with_stays = compact_points
    roundtrip._build_roundtrip = build_roundtrip


__all__ = [
    "install_trail_loop_rescue",
    "_relation_loop",
    "_compact_route_points",
]
