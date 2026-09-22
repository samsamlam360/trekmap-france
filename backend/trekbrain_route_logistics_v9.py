"""Route-first logistics layer for TrekBrain v9.

The hiking line and the place where the hiker sleeps are two different problems.
Older planners let campsites become mandatory geometry anchors. That can turn a
perfectly good 18-20 km/day route into a 30 km day simply because a campsite is
not located at the mathematical end of a stage.

This layer makes the hierarchy explicit for every trek, GR or not:

1. build the best pedestrian route without forcing accommodation into it;
2. split that route into sensible hiking days;
3. discover campsites/refuges along the whole route corridor;
4. attach each night as logistics, using a short validated walking connector when
   practical, otherwise recommending a separate transfer and resuming at the same
   route point the next morning;
5. never invalidate an otherwise safe pedestrian route merely because lodging
   logistics are incomplete.

The actual walking backbone still comes from the existing GR/OSM/ORS planners.
No straight-line geometry is promoted to a hiking route.
"""
from __future__ import annotations

import math
import re
import unicodedata
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

_INSTALLED = False
_SAFETY_INSTALLED = False
_MAX_OFFROUTE_KM = 6.0
_WALK_CONNECTOR_LIMIT_KM = 2.8
_MAX_DISCOVERED = 80


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _stay_key(item: dict[str, Any]) -> str:
    source = str(item.get("source_url") or "").strip()
    if source:
        return source
    try:
        return f"{_fold(item.get('name'))}|{float(item['lat']):.5f}|{float(item['lon']):.5f}"
    except Exception:
        return _fold(item.get("name"))


def _requested_category(intent: dict[str, Any]) -> str | None:
    accommodation = _fold(intent.get("accommodation") or "")
    if accommodation == "camping":
        return "camping"
    if accommodation == "refuge":
        return "refuge"
    return None


def _route_only_prompt(prompt: str) -> str:
    """Remove lodging words without destroying the geographic request."""
    text = str(prompt or "")
    replacements = (
        (r"\b(?:des?|les?)\s+campings?\b", "des nuitées"),
        (r"\bcampings?\b", "nuitées"),
        (r"\brefuges?\b", "nuitées"),
        (r"\bg[iî]tes?\b", "nuitées"),
        (r"\bh[eé]bergements?\b", "nuitées"),
        (r"\btente(?:s)?\b", "nuitée"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _clone_route_only(data):
    updates = {"prompt": _route_only_prompt(getattr(data, "prompt", ""))}
    if hasattr(data, "require_accommodation"):
        updates["require_accommodation"] = False
    if hasattr(data, "model_copy"):
        return data.model_copy(update=updates)
    if hasattr(data, "copy"):
        try:
            return data.copy(update=updates)
        except TypeError:
            pass
    clone = deepcopy(data)
    for key, value in updates.items():
        try:
            setattr(clone, key, value)
        except Exception:
            pass
    return clone


def _osm_url(element: dict[str, Any]) -> str:
    typ = str(element.get("type") or element.get("osm_type") or "node").casefold()
    typ = {"n": "node", "w": "way", "r": "relation"}.get(typ, typ)
    ident = element.get("id") if element.get("id") is not None else element.get("osm_id")
    if ident is None or typ not in {"node", "way", "relation"}:
        return ""
    return f"https://www.openstreetmap.org/{typ}/{ident}"


def _normalise_stay(element: dict[str, Any], category: str) -> dict[str, Any] | None:
    tags = element.get("tags") or {}
    lat, lon = element.get("lat"), element.get("lon")
    if lat is None or lon is None:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return {
        "name": str(tags.get("name") or tags.get("ref") or ("Camping" if category == "camping" else "Refuge"))[:180],
        "lat": lat,
        "lon": lon,
        "category": category,
        "source_url": _osm_url(element),
        "osm_tags": dict(tags),
    }


def _bbox_route_stays(coords, category: str) -> list[dict[str, Any]]:
    """One compact Overpass query covering the full route instead of endpoint searches."""
    from . import free_planner_v2 as free

    valid = []
    for point in coords or []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            valid.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            continue
    if len(valid) < 2:
        return []

    min_lat = min(x[0] for x in valid)
    max_lat = max(x[0] for x in valid)
    min_lon = min(x[1] for x in valid)
    max_lon = max(x[1] for x in valid)
    mid_lat = (min_lat + max_lat) / 2.0
    pad_lat = min(0.09, max(0.025, _MAX_OFFROUTE_KM / 111.0))
    pad_lon = min(0.13, max(0.03, _MAX_OFFROUTE_KM / max(35.0, 111.0 * math.cos(math.radians(mid_lat)))))
    south, north = min_lat - pad_lat, max_lat + pad_lat
    west, east = min_lon - pad_lon, max_lon + pad_lon

    if category == "camping":
        filters = ('["tourism"="camp_site"]', '["tourism"="caravan_site"]')
    else:
        filters = (
            '["tourism"="alpine_hut"]',
            '["tourism"="wilderness_hut"]',
            '["amenity"="shelter"]',
        )
    clauses = "".join(
        f"nwr{flt}({south:.6f},{west:.6f},{north:.6f},{east:.6f});"
        for flt in filters
    )
    query = f"[out:json][timeout:5];({clauses});out center tags 160;"

    data = None
    for url in list(getattr(free, "OVERPASS_URLS", []))[:2]:
        try:
            data = free._request_json(
                url,
                data={"data": query},
                timeout=3.2,
                ttl=3600,
                service="Overpass logistique nuitées",
                retries=1,
            )
            if isinstance(data, dict):
                break
        except Exception:
            data = None
    if not isinstance(data, dict):
        return []

    rows = []
    for element in (data.get("elements") or [])[:160]:
        tags = element.get("tags") or {}
        if category == "camping" and tags.get("tourism") not in {"camp_site", "caravan_site"}:
            continue
        if category == "refuge" and not (
            tags.get("tourism") in {"alpine_hut", "wilderness_hut"}
            or tags.get("amenity") == "shelter"
        ):
            continue
        stay = _normalise_stay(element, category)
        if stay:
            rows.append(stay)
    return rows


def _route_probe_stays(v3, roundtrip, coords, category: str) -> list[dict[str, Any]]:
    """Bounded fallback when a full-corridor bbox lookup is unavailable."""
    cum = roundtrip._cumulative(coords)
    if not cum or float(cum[-1]) <= 0:
        return []
    rows = []
    seen = set()
    for part in range(6):
        target = float(cum[-1]) * (part + 0.5) / 6.0
        idx = roundtrip._route_index_for_progress(cum, target)
        point = coords[idx]
        try:
            found = list(v3._nearby(float(point[0]), float(point[1]), 6.0, [category]) or [])
        except Exception:
            found = []
        for item in found:
            if not isinstance(item, dict) or str(item.get("category") or "") != category:
                continue
            key = _stay_key(item)
            if key and key not in seen:
                seen.add(key)
                rows.append(dict(item))
    return rows


def _project_stays(roundtrip, coords, rows, category: str, max_offroute_km: float) -> list[dict[str, Any]]:
    cum = roundtrip._cumulative(coords)
    if not cum:
        return []
    selected = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item["category"] = category
        projection = roundtrip._project_stay_to_route(coords, cum, item)
        if not projection:
            continue
        index, progress, offroute = projection
        if float(offroute) > float(max_offroute_km):
            continue
        item["_route_index"] = int(index)
        item["_route_progress_km"] = float(progress)
        item["_offroute_km"] = float(offroute)
        key = _stay_key(item)
        old = selected.get(key)
        if old is None or float(item["_offroute_km"]) < float(old["_offroute_km"]):
            selected[key] = item
    out = list(selected.values())
    out.sort(key=lambda x: (float(x.get("_route_progress_km") or 0), float(x.get("_offroute_km") or 0)))
    return out[:_MAX_DISCOVERED]


def _choose_stays(roundtrip, coords, rows, days: int, daily_target: float) -> list[dict[str, Any]]:
    """Pick one unique stay near each ideal route split without moving the route."""
    needed = max(0, int(days) - 1)
    if needed <= 0 or not rows:
        return []
    cum = roundtrip._cumulative(coords)
    if not cum or float(cum[-1]) <= 0:
        return []
    total = float(cum[-1])
    window = max(8.0, min(15.0, float(daily_target) * 0.62))
    beam = [(0.0, [], frozenset(), -0.01)]
    for night in range(1, days):
        target = total * night / days
        options = [
            row for row in rows
            if abs(float(row.get("_route_progress_km") or 0) - target) <= window
        ]
        if not options:
            # Do not drag a stage tens of kilometres merely to satisfy lodging.
            return beam[0][1] if beam and beam[0][1] else []
        expanded = []
        for score, chosen, used, previous in beam:
            for row in options:
                key = _stay_key(row)
                progress = float(row.get("_route_progress_km") or 0)
                if not key or key in used or progress <= previous + 1.0:
                    continue
                offroute = float(row.get("_offroute_km") or 0)
                cost = abs(progress - target) * 0.32 + offroute * 1.2
                expanded.append((score + cost, chosen + [row], used | {key}, progress))
        if not expanded:
            return beam[0][1] if beam and beam[0][1] else []
        expanded.sort(key=lambda state: state[0])
        beam = expanded[:48]
    return beam[0][1] if beam else []


def _discover_stays(v3, roundtrip, stay_rescue, coords, start, category: str, days: int, daily_target: float, strict_walk: bool):
    rows = []
    rows.extend(_bbox_route_stays(coords, category))
    if len(rows) < max(2, days - 1):
        rows.extend(_route_probe_stays(v3, roundtrip, coords, category))

    max_offroute = 3.2 if strict_walk else _MAX_OFFROUTE_KM
    projected = _project_stays(roundtrip, coords, rows, category, max_offroute)

    # Public geocoders remain discovery-only fallbacks. Route projection filters
    # mainland/irrelevant hits before any stay can be selected.
    if len(projected) < max(1, days - 1):
        try:
            rows.extend(stay_rescue._photon_stays(start, category, 38.0))
        except Exception:
            pass
        projected = _project_stays(roundtrip, coords, rows, category, max_offroute)
    if len(projected) < max(1, days - 1):
        try:
            rows.extend(stay_rescue._nominatim_stays(start, category, 38.0))
        except Exception:
            pass
        projected = _project_stays(roundtrip, coords, rows, category, max_offroute)

    return _choose_stays(roundtrip, coords, projected, days, daily_target), projected


def _connector(ors, legacy_main, roundtrip, coords, stay: dict[str, Any]) -> dict[str, Any]:
    index = max(0, min(int(stay.get("_route_index") or 0), len(coords) - 1))
    anchor = coords[index]
    try:
        routed = ors.get_route(
            [[float(anchor[0]), float(anchor[1])], [float(stay["lat"]), float(stay["lon"])]],
            legacy_main.distance_gps,
        )
    except Exception:
        routed = None
    if not isinstance(routed, dict) or routed.get("fallback") is not False:
        return {"validated": False, "distance_km": None}
    try:
        distance = float(routed.get("distance") or routed.get("distance_km") or 0)
    except (TypeError, ValueError):
        distance = 0.0
    return {
        "validated": distance > 0,
        "distance_km": round(distance, 2) if distance > 0 else None,
        "routing_mode": routed.get("routing_mode") or "walking",
    }


def _strict_walk_request(data) -> bool:
    text = _fold(getattr(data, "prompt", ""))
    return any(phrase in text for phrase in (
        "100 a pied", "100 pourcent a pied", "tout a pied", "uniquement a pied",
        "sans bus", "sans transfert", "aucun transfert",
    ))


def _route_distance(result: dict[str, Any], coords, legacy_main) -> float:
    route = result.get("route_preview") or {}
    for key in ("distance_km", "distance"):
        try:
            value = float(route.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    try:
        return float(result.get("distance_km") or 0) or float(legacy_main.distance_gps(coords))
    except Exception:
        return 0.0


def _attach_logistics(result: dict[str, Any], data, legacy_main, v3, roundtrip, stay_rescue, ors, intent, category: str):
    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    if len(coords) < 2 or route.get("fallback") is not False:
        return result

    days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
    daily_target = float(intent.get("daily_target") or getattr(data, "daily_km", 18) or 18)
    daily_max = float(intent.get("daily_max") or daily_target * 1.25)
    strict_walk = _strict_walk_request(data)
    start = dict(result.get("start") or {})
    if "lat" not in start or "lon" not in start:
        start = {"name": "Départ", "lat": float(coords[0][0]), "lon": float(coords[0][1])}

    chosen, discovered = _discover_stays(
        v3, roundtrip, stay_rescue, coords, start, category, days, daily_target, strict_walk
    )
    by_night = {index + 1: stay for index, stay in enumerate(chosen[: max(0, days - 1)])}

    total_distance = _route_distance(result, coords, legacy_main)
    if total_distance <= 0:
        return result
    base_per_day = total_distance / max(days, 1)

    logistics_rows = []
    accommodations = []
    for night in range(1, days):
        stay = by_night.get(night)
        if not stay:
            logistics_rows.append({
                "night": night,
                "status": "unresolved",
                "access_mode": "to_arrange",
                "note": "Aucun hébergement suffisamment proche de cette portion n'a été confirmé. Le tracé principal reste valable.",
            })
            continue

        offroute = float(stay.get("_offroute_km") or 0)
        access = {
            "night": night,
            "name": stay.get("name") or ("Camping" if category == "camping" else "Refuge"),
            "category": category,
            "lat": stay.get("lat"),
            "lon": stay.get("lon"),
            "source_url": stay.get("source_url") or "",
            "distance_from_route_km": round(offroute, 2),
            "route_progress_km": round(float(stay.get("_route_progress_km") or 0), 2),
            "resume_same_route_point": True,
        }

        connector = {"validated": False, "distance_km": None}
        if offroute <= _WALK_CONNECTOR_LIMIT_KM:
            connector = _connector(ors, legacy_main, roundtrip, coords, stay)
        connector_km = float(connector.get("distance_km") or 0)
        if connector.get("validated") and connector_km <= 4.0:
            access["status"] = "confirmed"
            access["access_mode"] = "walk"
            access["access_distance_km"] = round(connector_km, 2)
            access["note"] = "Petite liaison pédestre validée ; reprendre le même point de l'itinéraire principal le lendemain."
        elif strict_walk:
            access["status"] = "unresolved"
            access["access_mode"] = "walk_unverified"
            access["note"] = "La demande impose le tout-à-pied, mais la liaison pédestre vers cette nuitée n'a pas été validée."
        else:
            access["status"] = "usable_with_transfer"
            access["access_mode"] = "transfer"
            access["note"] = "Hébergement gardé comme logistique séparée ; transfert à organiser et reprise au même point du trek le lendemain."

        logistics_rows.append(access)
        accommodations.append({
            "name": access["name"],
            "type": "Camping" if category == "camping" else "Refuge / gîte",
            "category": category,
            "lat": access["lat"],
            "lon": access["lon"],
            "source_url": access["source_url"],
            "notes": access["note"],
            "access_mode": access["access_mode"],
            "distance_to_route_km": access["distance_from_route_km"],
        })

    old_stages = list(result.get("stages") or [])
    stages = []
    previous_return = 0.0
    for day in range(1, days + 1):
        old = old_stages[day - 1] if day - 1 < len(old_stages) and isinstance(old_stages[day - 1], dict) else {}
        night = next((row for row in logistics_rows if row.get("night") == day), None) if day < days else None
        access_out = float((night or {}).get("access_distance_km") or 0) if (night or {}).get("access_mode") == "walk" else 0.0
        estimated_effort = base_per_day + previous_return + access_out
        if night and night.get("access_mode") == "walk" and estimated_effort > daily_max + 1.0 and not strict_walk:
            night["access_mode"] = "transfer"
            night["status"] = "usable_with_transfer"
            night["note"] = "La liaison à pied rendrait la journée trop longue ; transfert conseillé et reprise au même point du trek le lendemain."
            access_out = 0.0
            estimated_effort = base_per_day + previous_return
            for accommodation in accommodations:
                if accommodation.get("name") == night.get("name"):
                    accommodation["access_mode"] = "transfer"
                    accommodation["notes"] = night["note"]
                    break

        if day == days:
            overnight = "Fin du trek"
        elif not night:
            overnight = "Nuitée à organiser sans modifier le tracé principal"
        elif night.get("access_mode") == "walk":
            overnight = f"{night['name']} · liaison pédestre {night.get('access_distance_km', 0):.1f} km"
        elif night.get("access_mode") == "transfer":
            overnight = f"{night['name']} · transfert conseillé"
        else:
            overnight = f"{night['name']} · liaison à vérifier"

        stages.append({
            **old,
            "day": day,
            "name": old.get("name") or f"Jour {day}",
            "title": old.get("title") or f"Jour {day} · itinéraire principal",
            "distance_km": round(base_per_day, 1),
            "route_distance_km": round(base_per_day, 1),
            "estimated_walking_km_with_access": round(estimated_effort, 1),
            "overnight": overnight,
            "overnight_logistics": night,
        })
        previous_return = access_out

    complete = len([row for row in logistics_rows if row.get("status") in {"confirmed", "usable_with_transfer"}]) == max(0, days - 1)
    result["stages"] = stages
    result["duration_days"] = days
    result["accommodations"] = accommodations
    result["logistics"] = {
        "mode": "route-first",
        "category": category,
        "status": "complete" if complete else "partial",
        "route_immutable": True,
        "discovered_candidates": len(discovered),
        "nights_required": max(0, days - 1),
        "nights_resolved": len([row for row in logistics_rows if row.get("status") in {"confirmed", "usable_with_transfer"}]),
        "strict_walk": strict_walk,
        "nights": logistics_rows,
        "principle": "Le tracé pédestre est calculé d'abord. Les nuitées sont une logistique secondaire et ne rallongent pas artificiellement l'itinéraire principal.",
    }
    result.setdefault("advisor_notes", []).insert(
        0,
        "🧭 Itinéraire d'abord : TrekBrain a séparé le parcours pédestre des nuitées. Un camping éloigné ne déforme plus le trek ; une petite liaison est ajoutée si elle est validée, sinon un transfert séparé est conseillé.",
    )
    planner = result.setdefault("planner", {})
    if isinstance(planner, dict):
        planner["logistics_mode"] = "route-first"
        planner["lodging_does_not_shape_route"] = True
    understood = str(result.get("understood_request") or "").strip()
    if understood and category not in _fold(understood):
        result["understood_request"] = understood + f" · {category} traité en logistique séparée"
    return result


def install_route_first_logistics(v3, roundtrip, stay_rescue, ors) -> None:
    """Install after GR/round-trip/canonical planners so it becomes the final planning policy."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    original_build = v3._build

    def build(data, legacy_main):
        intent = v3._parse_intent(data)
        category = _requested_category(intent)
        days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
        if category is None or days <= 1:
            return original_build(data, legacy_main)

        # Accommodation must never decide the main hiking geometry. Re-run the
        # exact same planner stack with only lodging removed from the request,
        # then solve lodging against the validated result.
        route_data = _clone_route_only(data)
        result = original_build(route_data, legacy_main)
        if not isinstance(result, dict):
            return result
        return _attach_logistics(
            result, data, legacy_main, v3, roundtrip, stay_rescue, ors, intent, category
        )

    v3._build = build


def install_logistics_safety_semantics(safety_module) -> None:
    """Keep route safety strict while treating lodging/water as logistics warnings."""
    global _SAFETY_INSTALLED
    if _SAFETY_INSTALLED:
        return
    _SAFETY_INSTALLED = True
    original_report = safety_module.route_safety_report

    def report(result, request=None):
        value = original_report(result, request)
        blockers = list(value.get("blockers") or [])
        warnings = list(value.get("warnings") or [])
        logistics = result.get("logistics") or {}
        if logistics.get("mode") == "route-first":
            kept = []
            for blocker in blockers:
                if str(blocker).startswith("La demande impose des campings"):
                    warnings.append(
                        "Logistique nuitée incomplète : le tracé pédestre reste validé, mais une ou plusieurs nuits doivent encore être organisées."
                    )
                else:
                    kept.append(blocker)
            blockers = kept
        # Water is display-only in v9: missing mapped water cannot invalidate a
        # pedestrian geometry. It remains an important preparation warning.
        kept = []
        for blocker in blockers:
            if str(blocker).startswith("Aucune étape ne dispose d'une information d'eau"):
                warnings.append(str(blocker))
            else:
                kept.append(blocker)
        blockers = kept
        value["blockers"] = blockers
        value["warnings"] = list(dict.fromkeys(warnings))
        value["safe"] = not blockers
        return value

    safety_module.route_safety_report = report


__all__ = [
    "install_route_first_logistics",
    "install_logistics_safety_semantics",
    "_attach_logistics",
    "_bbox_route_stays",
    "_choose_stays",
]
