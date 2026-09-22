"""Targeted GR 340 priority for Belle-Île-en-Mer in TrekBrain v9.

The generic hiking-relation discovery is intentionally broad and capped.  On a
well-known island loop such as Belle-Île, that can let unrelated relations win or
make the planner fall through to ORS round-trip generation.  This overlay performs
one small, targeted OSM lookup for GR 340 before the generic round-trip fallback.
No route geometry is hard-coded: the geometry still comes from the live OSM
hiking relation.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_INSTALLED = False


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().replace(" ", "")


def _is_belle_ile(start: dict[str, Any]) -> bool:
    try:
        lat, lon = float(start["lat"]), float(start["lon"])
    except (KeyError, TypeError, ValueError):
        return False
    # Deliberately a loose island-only box.  It is not route geometry and merely
    # decides whether a targeted GR 340 lookup is relevant.
    return 47.20 <= lat <= 47.44 and -3.40 <= lon <= -2.95


def _is_gr340(tags: dict[str, Any]) -> bool:
    ref = _fold(tags.get("ref"))
    name = _fold(tags.get("name"))
    return ("gr340" in ref or "gr340" in name) and str(tags.get("route") or "").casefold() == "hiking"


def _targeted_gr340(v3, gr, rescue, start: dict[str, Any], target_km: float):
    if not _is_belle_ile(start):
        return None, "hors Belle-Île"

    query = (
        "[out:json][timeout:9];("
        f"relation(around:45000,{start['lat']},{start['lon']})[\"route\"=\"hiking\"][\"ref\"~\"340\",i];"
        f"relation(around:45000,{start['lat']},{start['lon']})[\"route\"=\"hiking\"][\"name\"~\"GR.?340\",i];"
        ");out geom tags 12;"
    )
    try:
        payload = v3._overpass(query)
    except Exception as exc:
        return None, f"recherche ciblée GR 340 indisponible ({exc.__class__.__name__})"

    rows = []
    for element in (payload or {}).get("elements") or []:
        if element.get("type") != "relation":
            continue
        tags = element.get("tags") or {}
        if not _is_gr340(tags):
            continue
        coords = gr._join_relation_members(element.get("members") or [])
        if len(coords) < 8:
            continue
        # Keep enough points that the coastal loop cannot acquire kilometre-wide
        # gaps merely because OSM contains a very detailed relation.
        coords = gr._downsample(coords, max_points=900)
        closed, reason = rescue._close_relation(coords, rescue._length)
        if not closed:
            continue
        relation_km = rescue._length(closed)
        if relation_km < max(45.0, float(target_km) * 0.55) or relation_km > float(target_km) * 1.55:
            continue
        idx, start_off = rescue._nearest_index(closed[:-1], start)
        if start_off > 15.0:
            continue
        score = abs(relation_km - float(target_km)) + start_off * 0.5
        rows.append((score, element, tags, closed, idx, start_off, relation_km))

    if not rows:
        return None, "GR 340 ciblé non exploitable dans les données OSM reçues"

    rows.sort(key=lambda row: row[0])
    _, element, tags, closed, idx, start_off, relation_km = rows[0]
    rotated = rescue._rotate_closed(closed, idx)
    if len(rotated) < 4 or rescue._max_gap(rotated) > rescue._MAX_RELATION_GAP_KM:
        return None, "GR 340 ciblé discontinu après reconstruction"

    first = rotated[0]
    start["lat"], start["lon"] = float(first[0]), float(first[1])
    start["name"] = "Départ sur GR 340"
    start["category"] = "trail"
    source_url = f"https://www.openstreetmap.org/relation/{element.get('id')}"
    name = str(tags.get("name") or "Tour de Belle-Île-en-Mer").strip()
    rescue._LAST_META.set({
        "ref": "GR 340",
        "name": name[:160],
        "source_url": source_url,
        "distance_km": round(relation_km, 2),
        "targeted": True,
    })
    return {
        "coords": rotated,
        "distance": round(relation_km, 2),
        "fallback": False,
        "routing_mode": "osm-hiking-relation-loop",
        "profile": "hiking-relation",
        "provider": "OpenStreetMap hiking relation",
        "relation_ref": "GR 340",
        "relation_name": name[:160],
        "relation_source_url": source_url,
        "relation_geometry": True,
        "targeted_relation_lookup": True,
        "start_offset_before_snap_km": round(float(start_off), 2),
    }, None


def install_belle_ile_gr340_priority(roundtrip, gr, rescue) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    current_best = roundtrip._best_roundtrip

    def best_roundtrip(start, target_km, daily_min, daily_max, days, v3):
        if _is_belle_ile(start) and 55.0 <= float(target_km) <= 130.0:
            route, _warning = _targeted_gr340(v3, gr, rescue, start, target_km)
            if route is not None:
                return route
        return current_best(start, target_km, daily_min, daily_max, days, v3)

    roundtrip._best_roundtrip = best_roundtrip


__all__ = [
    "install_belle_ile_gr340_priority",
    "_targeted_gr340",
    "_is_belle_ile",
    "_is_gr340",
]
