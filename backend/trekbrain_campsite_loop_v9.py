"""Campsite-aware alternate ORS loops for TrekBrain v9.

The first ORS round-trip can be perfectly walkable yet cross a part of the area
with poor campsite coverage.  Do not keep expanding campsite detours forever.
Instead, when the normal fallback already proved that a pedestrian loop exists
but cannot place the requested nights, try a couple of different ORS round-trip
shapes and stop as soon as one gives a validated campsite sequence.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException

_INSTALLED = False


def _max_alternatives() -> int:
    try:
        value = int(os.getenv("TREKBRAIN_CAMPING_LOOP_ALTERNATIVES", "2") or 2)
    except (TypeError, ValueError):
        value = 2
    return max(1, min(value, 2))


def _start_for(v3, location: str) -> dict[str, Any]:
    geo = v3._geocode(f"{location}, France") or v3._geocode(location)
    if not geo:
        raise HTTPException(status_code=422, detail=f"Impossible de localiser « {location} ».")
    center = geo[0]
    return {
        "name": str(center.get("name") or center.get("short_name") or location or "Départ"),
        "lat": float(center["lat"]),
        "lon": float(center["lon"]),
        "category": "place",
    }


def _render_result(data, legacy_main, v3, roundtrip, ors, intent, location, start, route, stays, stage_distances, attempts):
    coords = route.get("coords") or []
    days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
    total_distance = float(route.get("distance") or 0)
    total_elevation = int(legacy_main.elevation_gain(coords) or 0)

    stages = []
    for i, distance in enumerate(stage_distances):
        overnight = "Fin du trek" if i == days - 1 else str(stays[i].get("name") or "Camping")
        stages.append({
            "day": i + 1,
            "name": f"Jour {i + 1}",
            "distance_km": round(float(distance), 1),
            "elevation_gain_m": round(total_elevation * float(distance) / max(total_distance, 1.0)),
            "overnight": overnight,
            "water_notes": "Disponibilité de l'eau à vérifier sur la carte et sur place." if getattr(data, "require_water", False) else "",
            "highlights": [],
        })

    return {
        "name": f"Boucle randonnée autour de {location}",
        "region": location,
        "description": "Boucle ORS choisie en fonction des campings réellement disponibles sur le réseau pédestre.",
        "difficulty": intent.get("difficulty") or getattr(data, "difficulty", "medium"),
        "route_type": "Boucle",
        "duration_days": days,
        "distance_km": round(total_distance, 1),
        "elevation_gain_m": total_elevation,
        "start": dict(start),
        "end": dict(start),
        "stages": stages,
        "route_preview": {
            "coords": coords,
            "distance_km": round(total_distance, 2),
            "distance": round(total_distance, 2),
            "fallback": False,
            "routing_mode": route.get("routing_mode") or "ors-campsite-aware-round-trip",
            "profile": route.get("profile") or ors.ORS_PROFILE,
        },
        "accommodations": [dict(x) for x in stays],
        "water": [],
        "transport": {
            "outbound": f"Accès au départ à vérifier pour {location}." if getattr(data, "require_transit", False) else "",
            "return": f"Retour depuis le même secteur ({location}) à vérifier." if getattr(data, "require_transit", False) else "",
        },
        "points_of_interest": [],
        "advisor_notes": [
            "La première boucle pédestre ne passait pas assez près des campings utiles.",
            f"TrekBrain a testé {attempts} forme(s) de boucle supplémentaire(s) et a retenu la première compatible avec toutes les nuitées.",
            "Les détours vers les campings et les distances finales ont ensuite été revalidés par OpenRouteService.",
        ],
        "confidence": {
            "score": 80,
            "limitations": ["Boucle ORS de secours : ouvertures et disponibilités des campings restent à vérifier."],
        },
        "planner_fallback": "ors-campsite-aware-round-trip",
    }


def _recover(data, legacy_main, v3, roundtrip, ors):
    intent = v3._parse_intent(data)
    if v3._fold(intent.get("route_type") or "") != "boucle":
        raise HTTPException(status_code=422, detail="La récupération par boucle alternative ne s'applique qu'aux boucles.")

    category = "camping" if intent.get("accommodation") == "camping" else "refuge" if intent.get("accommodation") == "refuge" else None
    days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
    if not category or days <= 1:
        raise HTTPException(status_code=422, detail="Aucune nuitée structurée à récupérer.")

    location = v3._location(data)
    start = _start_for(v3, location)
    daily_target = float(intent.get("daily_target") or getattr(data, "daily_km", 18) or 18)
    daily_min = float(intent.get("daily_min") or daily_target * 0.75)
    daily_max = float(intent.get("daily_max") or daily_target * 1.25)
    target_km = float(intent.get("total_target") or daily_target * days)

    # Seeds 3 and 11 are used by the normal fast fallback.  Start elsewhere so
    # recovery explores genuinely different loop shapes instead of paying ORS
    # for the same answer twice.
    seeds = (29, 47)[:_max_alternatives()]
    errors = []
    attempts = 0
    for seed in seeds:
        attempts += 1
        route, warning = roundtrip._roundtrip_request(start, target_km, seed)
        if route is None:
            if warning:
                errors.append(str(warning))
            continue

        coords = route.get("coords") or []
        stays, search = roundtrip._balanced_corridor_stays(
            v3, coords, days, category, daily_target, daily_min, daily_max
        )
        if len(stays) != days - 1:
            options = search.get("options") or []
            errors.append(f"seed {seed}: nuitées trouvées par zone {options}")
            continue

        route_points = roundtrip._route_points_with_stays(coords, start, stays, days)
        routed = ors.get_route(
            [[float(p["lat"]), float(p["lon"])] for p in route_points],
            legacy_main.distance_gps,
        )
        if routed.get("fallback") is not False:
            errors.append(str(routed.get("warning") or f"seed {seed}: détours non routables"))
            continue

        final_coords = routed.get("coords") or []
        boundaries = [start] + stays + [start]
        stage_distances = v3._stage_distances(
            final_coords, boundaries, legacy_main, float(routed.get("distance") or 0)
        )
        if len(stage_distances) != days:
            continue
        if any(float(d) > daily_max + 0.35 for d in stage_distances):
            errors.append(f"seed {seed}: étape finale {max(stage_distances):.1f} km > {daily_max:.1f} km")
            continue

        routed["routing_mode"] = "ors-campsite-aware-round-trip"
        routed["round_trip_seed"] = seed
        return _render_result(
            data, legacy_main, v3, roundtrip, ors, intent, location,
            start, routed, stays, stage_distances, attempts,
        )

    detail = " ; ".join(errors[:3])
    raise HTTPException(
        status_code=422,
        detail=(
            "J'ai aussi essayé d'autres formes de boucle pour mieux passer par les campings, "
            "mais aucune n'a encore donné toutes les nuitées dans la plage quotidienne."
            + (f" Détails : {detail}." if detail else "")
        ),
    )


def install_campsite_aware_roundtrip(v3, roundtrip, ors) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original = roundtrip._build_roundtrip

    def build_roundtrip(data, legacy_main, v3_module):
        try:
            return original(data, legacy_main, v3_module)
        except HTTPException as exc:
            detail = str(getattr(exc, "detail", exc)).casefold()
            campsite_failure = (
                "combinaison de campings" in detail
                or "combinaison de hébergements" in detail
                or "combinaison de hebergements" in detail
            )
            if not campsite_failure:
                raise
            try:
                return _recover(data, legacy_main, v3_module, roundtrip, ors)
            except HTTPException as recovery_error:
                original_detail = str(getattr(exc, "detail", exc))
                recovery_detail = str(getattr(recovery_error, "detail", recovery_error))
                raise HTTPException(
                    status_code=getattr(exc, "status_code", 422),
                    detail=f"{original_detail} Boucles alternatives : {recovery_detail}",
                ) from recovery_error

    roundtrip._build_roundtrip = build_roundtrip


__all__ = ["install_campsite_aware_roundtrip", "_recover"]
