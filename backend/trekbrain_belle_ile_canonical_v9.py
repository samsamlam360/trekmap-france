"""Canonical Belle-Ile GR 340 planner for TrekBrain v9.

Belle-Ile is a special case where the user's request usually matches an existing
complete hiking route: GR 340.  The generic planner is useful elsewhere, but it
must not re-invent this island loop with a large ORS request when the authoritative
OSM hiking relation is already available.

This planner therefore:
- recognises a Belle-Ile loop before the generic candidate engine;
- uses the live GR 340 relation as the immutable walking backbone;
- chooses overnight stays along that backbone;
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
    stay_search = {"search_radius_km": 0.0, "window_km": 0.0, "options": []}
    if category and days > 1:
        stays, stay_search = roundtrip._balanced_corridor_stays(
            v3,
            coords,
            days,
            category,
            daily_target,
            daily_min,
            daily_max,
        )
        if len(stays) != days - 1:
            label = "campings" if category == "camping" else "hébergements"
            radius = float(stay_search.get("search_radius_km") or 0)
            window = float(stay_search.get("window_km") or 0)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Le GR 340 est bien disponible, mais je n'ai trouvé que {len(stays)} nuitée(s) exploitable(s) "
                    f"sur {days - 1} nécessaires. Recherche de {label} jusqu'à environ {radius:.1f} km du GR "
                    f"et ±{window:.1f} km autour des fins d'étape idéales."
                ),
            )

        stitched, stitch_warning = stitch._stitch_relation_with_stays(
            relation, stays, ors, legacy_main
        )
        if stitched is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Le GR 340 est bien trouvé, mais une petite liaison vers une nuitée n'a pas pu être validée : "
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

    # Daily kilometres are a target. A long outlier is still rejected, but a
    # slightly shorter coastal stage is legitimate when campings impose it.
    if any(float(d) > daily_max + 0.5 for d in stage_distances):
        raise HTTPException(
            status_code=422,
            detail=(
                "Le GR 340 est bien construit, mais la combinaison actuelle de nuitées laisse une journée trop longue "
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
        notes.append("Seules les petites liaisons GR ↔ nuitée sont routées séparément sur le réseau pédestre.")

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
]
