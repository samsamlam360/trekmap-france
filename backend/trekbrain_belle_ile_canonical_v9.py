"""Canonical Belle-Ile GR 340 planner for TrekBrain v9.

Belle-Ile is a special case where the user's request usually matches an existing
complete hiking route: GR 340. The generic planner is useful elsewhere, but it
must not re-invent this island loop with a large ORS request when the authoritative
OSM hiking relation is already available.

This planner therefore:
- recognises a Belle-Ile loop before the generic candidate engine;
- uses the live GR 340 relation as the immutable walking backbone;
- discovers overnight stays along the *whole* GR 340 corridor, not only around
  mathematically ideal stage endpoints;
- routes only the short GR -> stay -> GR branches;
- never includes the ferry crossing in the pedestrian geometry.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from fastapi import HTTPException

_INSTALLED = False
_MAX_STAY_OFFROUTE_KM = 5.0
_MAX_GLOBAL_STAYS = 40


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _looks_belle_ile(data, location: str) -> bool:
    text = _fold(
        f"{location} {getattr(data, 'region', '')} {getattr(data, 'prompt', '')}"
    )
    return "belle ile" in text


def _canonical_start(v3, belle, location: str):
    queries = (
        "Belle-Île-en-Mer, Morbihan, France",
        "Belle Ile en Mer, Morbihan, France",
        f"{location}, Morbihan, France",
        location,
    )
    for query in queries:
        try:
            rows = list(v3._geocode(query) or [])
        except Exception:
            rows = []
        for row in rows:
            try:
                candidate = {
                    "name": str(row.get("name") or row.get("short_name") or "Belle-Île-en-Mer"),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "category": "place",
                }
            except (KeyError, TypeError, ValueError):
                continue
            if belle._is_belle_ile(candidate):
                return candidate
    return None


def _stage_boundaries(roundtrip, coords, start, stays, days: int):
    if stays:
        return [start] + [dict(x) for x in stays] + [start]
    anchors = roundtrip._equal_anchors(coords, days)
    if len(anchors) != max(0, days - 1):
        return None
    return [start] + anchors + [start]


def _stay_key(stay: dict[str, Any]) -> str:
    source = str(stay.get("source_url") or "").strip()
    if source:
        return source
    try:
        return (
            f"{_fold(stay.get('name'))}|"
            f"{float(stay['lat']):.5f}|{float(stay['lon']):.5f}"
        )
    except Exception:
        return _fold(stay.get("name"))


def _range_penalty(distance: float, target: float, low: float, high: float) -> float:
    penalty = abs(float(distance) - float(target))
    if distance < low:
        penalty += (low - distance) * 5.0
    if distance > high:
        penalty += (distance - high) * 9.0
    return penalty


def _route_probe_rows(v3, roundtrip, coords, category: str) -> list[dict[str, Any]]:
    """Cheap normal lookup spread over the whole island loop.

    Previous code searched near only three/four ideal stage endpoints. A campsite
    a few kilometres before or after those exact mathematical points could simply
    be invisible. Probing the whole route also avoids relying on one geocoded
    centre point for a long, narrow island.
    """
    if len(coords) < 3:
        return []
    cum = roundtrip._cumulative(coords)
    if not cum or float(cum[-1]) <= 0:
        return []
    total = float(cum[-1])
    rows: list[dict[str, Any]] = []
    seen = set()
    for part in range(12):
        progress = total * (part + 0.5) / 12.0
        index = roundtrip._route_index_for_progress(cum, progress)
        point = coords[index]
        try:
            found = list(v3._nearby(float(point[0]), float(point[1]), 5.2, [category]) or [])
        except Exception:
            found = []
        for stay in found:
            if not isinstance(stay, dict) or str(stay.get("category") or "") != category:
                continue
            key = _stay_key(stay)
            if key and key not in seen:
                seen.add(key)
                rows.append(dict(stay))
    return rows


def _project_stays(roundtrip, coords, rows, category: str) -> list[dict[str, Any]]:
    cum = roundtrip._cumulative(coords)
    projected = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item["category"] = category
        key = _stay_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        projection = roundtrip._project_stay_to_route(coords, cum, item)
        if not projection:
            continue
        route_index, progress, offroute = projection
        if float(offroute) > _MAX_STAY_OFFROUTE_KM:
            continue
        item["_route_index"] = int(route_index)
        item["_route_progress_km"] = float(progress)
        item["_offroute_km"] = float(offroute)
        projected.append(item)
    projected.sort(key=lambda x: (float(x.get("_route_progress_km") or 0), float(x.get("_offroute_km") or 0)))
    return projected[:_MAX_GLOBAL_STAYS]


def _choose_ordered_stays(
    roundtrip,
    coords,
    stays,
    days: int,
    daily_target: float,
    daily_min: float,
    daily_max: float,
) -> list[dict[str, Any]]:
    """Choose unique campsites globally along GR 340.

    Campsites are first projected onto the GR. Then a small beam search chooses
    an ordered combination close to the ideal day splits while accounting for
    each off-route branch. This means a valid campsite 3 km before the ideal
    endpoint can be selected instead of being ignored.
    """
    needed = max(0, int(days) - 1)
    if needed == 0:
        return []
    if len(stays) < needed:
        return []
    cum = roundtrip._cumulative(coords)
    if not cum or float(cum[-1]) <= 0:
        return []
    total = float(cum[-1])
    min_progress_gap = max(2.0, min(float(daily_min) * 0.35, 7.0))
    beam = [(0.0, [], frozenset(), 0.0, 0.0)]

    for night in range(1, days):
        target_progress = total * night / days
        window = max(9.0, float(daily_target) * 0.55)
        options = [
            stay for stay in stays
            if abs(float(stay.get("_route_progress_km") or 0) - target_progress) <= window
        ]
        if not options:
            # Keep a broad fallback. Final stage-distance validation still rejects
            # genuinely excessive walking days.
            options = list(stays)

        expanded = []
        for score, chosen, used, previous_progress, previous_detour in beam:
            for stay in options:
                key = _stay_key(stay)
                if not key or key in used:
                    continue
                progress = float(stay.get("_route_progress_km") or 0)
                detour = float(stay.get("_offroute_km") or 0)
                if progress <= previous_progress + min_progress_gap:
                    continue
                estimated_stage = (progress - previous_progress) + previous_detour + detour
                score_stage = _range_penalty(
                    estimated_stage, daily_target, daily_min, daily_max
                )
                placement = abs(progress - target_progress) * 0.25 + detour * 0.75
                expanded.append((
                    score + score_stage + placement,
                    chosen + [stay],
                    used | {key},
                    progress,
                    detour,
                ))
        if not expanded:
            return []
        expanded.sort(key=lambda state: state[0])
        beam = expanded[:64]

    finalists = []
    for score, chosen, used, previous_progress, previous_detour in beam:
        final_stage = (total - previous_progress) + previous_detour
        score += _range_penalty(final_stage, daily_target, daily_min, daily_max)
        finalists.append((score, chosen))
    finalists.sort(key=lambda row: row[0])
    return finalists[0][1] if finalists else []


def _discover_canonical_stays(
    v3,
    roundtrip,
    coords,
    start,
    category: str,
    days: int,
    daily_target: float,
    daily_min: float,
    daily_max: float,
):
    """Discover stays independently of the generic planner/circuit breaker."""
    from . import trekbrain_stays_rescue_v9 as stay_rescue

    needed = max(0, int(days) - 1)
    discovered = _route_probe_rows(v3, roundtrip, coords, category)

    # Independent lookup around the island. The result is projected back onto GR
    # 340, so mainland results or irrelevant geocoder hits are discarded by the
    # corridor-distance filter.
    radius = 30.0
    discovered += stay_rescue._direct_stays(start, category, radius)
    projected = _project_stays(roundtrip, coords, discovered, category)

    if len(projected) < needed:
        discovered += stay_rescue._photon_stays(start, category, radius)
        projected = _project_stays(roundtrip, coords, discovered, category)
    if len(projected) < needed:
        discovered += stay_rescue._nominatim_stays(start, category, radius)
        projected = _project_stays(roundtrip, coords, discovered, category)

    chosen = _choose_ordered_stays(
        roundtrip,
        coords,
        projected,
        days,
        daily_target,
        daily_min,
        daily_max,
    )
    diagnostics = {
        "needed": needed,
        "discovered": len(projected),
        "chosen": len(chosen),
        "max_offroute_km": _MAX_STAY_OFFROUTE_KM,
    }
    return chosen, diagnostics


def _build_canonical(data, legacy_main, v3, gr, rescue, roundtrip, stitch, ors, belle):
    intent = v3._parse_intent(data)
    if v3._fold(intent.get("route_type") or "") != "boucle":
        return None

    location = v3._location(data)
    if not _looks_belle_ile(data, location):
        return None

    start = _canonical_start(v3, belle, location)
    if not start:
        raise HTTPException(
            status_code=422,
            detail="Belle-Île-en-Mer a bien été comprise, mais son point de départ n'a pas pu être localisé sur l'île.",
        )

    days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
    daily_target = float(intent.get("daily_target") or getattr(data, "daily_km", 18) or 18)
    daily_min = float(intent.get("daily_min") or daily_target * 0.75)
    daily_max = float(intent.get("daily_max") or daily_target * 1.25)
    target_km = float(intent.get("total_target") or daily_target * days)

    relation, warning = belle._targeted_gr340(v3, gr, rescue, start, target_km)
    if relation is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Le tour de Belle-Île a été reconnu comme GR 340, mais la relation OSM n'a pas pu être reconstruite. "
                f"Diagnostic GR 340 : {warning or 'raison inconnue'}."
            ),
        )

    coords = relation.get("coords") or []
    if len(coords) < 4:
        raise HTTPException(status_code=503, detail="Le GR 340 récupéré ne contient pas assez de géométrie exploitable.")

    category = None
    accommodation = str(intent.get("accommodation") or "").casefold()
    if accommodation == "camping":
        category = "camping"
    elif accommodation == "refuge":
        category = "refuge"

    stays = []
    stay_diag = {"needed": 0, "discovered": 0, "chosen": 0, "max_offroute_km": _MAX_STAY_OFFROUTE_KM}
    if category and days > 1:
        stays, stay_diag = _discover_canonical_stays(
            v3,
            roundtrip,
            coords,
            start,
            category,
            days,
            daily_target,
            daily_min,
            daily_max,
        )
        if len(stays) != days - 1:
            label = "campings" if category == "camping" else "hébergements"
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Le GR 340 est bien disponible. J'ai trouvé {stay_diag['discovered']} {label} à moins de "
                    f"{stay_diag['max_offroute_km']:.1f} km du GR, mais seulement {len(stays)} peuvent être ordonnés "
                    f"correctement pour {days - 1} nuitée(s). La recherche couvre maintenant tout le GR 340, "
                    "pas seulement les fins d'étape idéales."
                ),
            )

        stitched, stitch_warning = stitch._stitch_relation_with_stays(
            relation, stays, ors, legacy_main
        )
        if stitched is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Le GR 340 et les nuitées sont bien trouvés, mais une petite liaison vers une nuitée n'a pas pu être validée : "
                    f"{stitch_warning or 'raison inconnue'}."
                ),
            )
        route = stitched
    else:
        route = relation

    coords = route.get("coords") or []
    total = float(route.get("distance") or 0)
    if total <= 0:
        total = sum(
            float(legacy_main.distance_gps([a, b]))
            for a, b in zip(coords, coords[1:])
        )

    boundaries = _stage_boundaries(roundtrip, coords, start, stays, days)
    if not boundaries:
        raise HTTPException(status_code=422, detail="Le GR 340 n'a pas pu être découpé proprement en journées.")

    stage_distances = v3._stage_distances(coords, boundaries, legacy_main, total)
    if len(stage_distances) != days:
        stage_distances = [total / max(days, 1)] * days

    if any(float(d) > daily_max + 0.5 for d in stage_distances):
        raise HTTPException(
            status_code=422,
            detail=(
                "Le GR 340 et les campings sont bien construits, mais la meilleure combinaison actuelle laisse une journée trop longue "
                f"({max(stage_distances):.1f} km pour une limite de {daily_max:.1f} km)."
            ),
        )

    try:
        total_elevation = int(legacy_main.elevation_gain(coords) or 0)
    except Exception:
        total_elevation = 0

    stages = []
    for i, distance in enumerate(stage_distances):
        if i < days - 1:
            if stays:
                overnight = str(stays[i].get("name") or ("Camping" if category == "camping" else "Nuitée"))
            else:
                overnight = "Étape intermédiaire"
        else:
            overnight = "Fin du trek"
        stages.append({
            "day": i + 1,
            "name": f"Jour {i + 1}",
            "distance_km": round(float(distance), 1),
            "elevation_gain_m": round(total_elevation * float(distance) / max(total, 1.0)),
            "overnight": overnight,
            "overnight_place": dict(stays[i]) if stays and i < days - 1 else None,
            "water_notes": "Points d'eau affichés comme repères sur la carte ; disponibilité à vérifier sur place.",
            "highlights": ["GR 340", "Côte de Belle-Île-en-Mer"],
        })

    end = dict(start)
    source_url = str(route.get("relation_source_url") or relation.get("relation_source_url") or "")
    relation_name = str(route.get("relation_name") or relation.get("relation_name") or "Tour de Belle-Île-en-Mer")
    relation_ref = str(route.get("relation_ref") or relation.get("relation_ref") or "GR 340")

    notes = [
        "Le GR 340 réel est utilisé comme colonne vertébrale du trek ; TrekBrain ne demande pas à ORS de réinventer le tour de l'île.",
        "Le trajet en bateau sert uniquement à rejoindre Belle-Île et n'est jamais inclus dans la géométrie pédestre.",
        "Les points d'eau sont informatifs et ne forcent aucun détour du parcours.",
    ]
    if stays:
        notes.append(
            f"{len(stays)} nuitée(s) ont été choisies après recherche des campings sur l'ensemble du corridor GR 340 ; seules les petites liaisons GR ↔ nuitée sont routées séparément."
        )

    return {
        "name": "Tour de Belle-Île-en-Mer par le GR 340",
        "region": "Belle-Île-en-Mer",
        "description": "Tour pédestre de Belle-Île-en-Mer basé sur la relation OSM du GR 340, avec accès maritime traité séparément.",
        "difficulty": intent.get("difficulty") or getattr(data, "difficulty", "medium"),
        "route_type": "Boucle",
        "duration_days": days,
        "distance_km": round(total, 1),
        "elevation_gain_m": total_elevation,
        "start": start,
        "end": end,
        "stages": stages,
        "route_preview": {
            "coords": coords,
            "distance_km": round(total, 2),
            "distance": round(total, 2),
            "fallback": False,
            "routing_mode": route.get("routing_mode") or "osm-hiking-relation-loop",
            "profile": route.get("profile") or "hiking-relation",
            "provider": route.get("provider") or "OpenStreetMap hiking relation",
            "relation_ref": relation_ref,
            "relation_name": relation_name,
            "relation_source_url": source_url,
            "relation_geometry": True,
            "max_segment_gap_km": route.get("max_segment_gap_km"),
        },
        "accommodations": [dict(x) for x in stays],
        "water": [],
        "transport": {
            "outbound": "Accès à Belle-Île par liaison maritime à organiser séparément du trek pédestre.",
            "return": "Retour par liaison maritime à organiser séparément du trek pédestre.",
        },
        "points_of_interest": [{
            "name": relation_ref,
            "category": "trail",
            "lat": float(start["lat"]),
            "lon": float(start["lon"]),
            "source_url": source_url,
        }],
        "advisor_notes": notes,
        "confidence": {
            "score": 92,
            "limitations": [
                "Relation OSM de randonnée utilisée comme axe principal ; vérifier fermetures et déviations temporaires avant le départ."
            ],
        },
        "planner_fallback": "belle-ile-gr340-canonical",
        "canonical_route": True,
        "stay_search": stay_diag,
    }


def install_belle_ile_canonical(v3, gr, rescue, roundtrip, stitch, ors, belle) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    original_build = v3._build

    def build(data, legacy_main):
        location = v3._location(data)
        if _looks_belle_ile(data, location):
            result = _build_canonical(
                data, legacy_main, v3, gr, rescue, roundtrip, stitch, ors, belle
            )
            if result is not None:
                return result
        return original_build(data, legacy_main)

    v3._build = build


__all__ = [
    "install_belle_ile_canonical",
    "_build_canonical",
    "_looks_belle_ile",
    "_discover_canonical_stays",
    "_choose_ordered_stays",
    "_project_stays",
]
