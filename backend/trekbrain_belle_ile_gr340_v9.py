"""Targeted GR 340 priority for Belle-Île-en-Mer in TrekBrain v9.

Belle-Île is a known closed hiking loop and should not depend on ORS inventing a
round trip.  The preferred geometry is the live OpenStreetMap GR 340 relation.

The generic Overpass discovery can already be unavailable by the time fallback
planning starts (for example because the interactive circuit breaker opened after
an earlier timeout).  For that reason this module has two independent ways to
retrieve the *same live OSM relation*:

1. a tiny Overpass lookup by the canonical relation id;
2. the normal OpenStreetMap relation/full API as a bounded backup.

Only the OSM relation id is pinned here.  No route coordinates are embedded in
TrekBrain, so edits to the OSM relation remain authoritative after cache expiry.
"""
from __future__ import annotations

import time
import unicodedata
import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import Any

import requests
from fastapi import HTTPException

_INSTALLED = False
_GR340_RELATION_ID = 6850120
_OSM_FULL_URL = f"https://api.openstreetmap.org/api/0.6/relation/{_GR340_RELATION_ID}/full"
_OSM_TIMEOUT = 6.0
_CACHE_TTL = 6 * 60 * 60
_DIRECT_CACHE: tuple[float, dict[str, Any]] | None = None


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().replace(" ", "")


def _is_belle_ile(start: dict[str, Any]) -> bool:
    try:
        lat, lon = float(start["lat"]), float(start["lon"])
    except (KeyError, TypeError, ValueError):
        return False
    # Loose island-only box. It is only a selector for the dedicated lookup,
    # never route geometry.
    return 47.20 <= lat <= 47.44 and -3.40 <= lon <= -2.95


def _is_gr340(tags: dict[str, Any]) -> bool:
    ref = _fold(tags.get("ref"))
    name = _fold(tags.get("name"))
    return ("gr340" in ref or "gr340" in name) and str(tags.get("route") or "").casefold() == "hiking"


def _relation_from_osm_xml(xml_text: str) -> dict[str, Any] | None:
    """Convert relation/full XML to the relation shape used by trekbrain_gr_v9."""
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError, ValueError):
        return None

    nodes: dict[int, tuple[float, float]] = {}
    for node in root.findall("node"):
        try:
            nodes[int(node.attrib["id"])] = (float(node.attrib["lat"]), float(node.attrib["lon"]))
        except (KeyError, TypeError, ValueError):
            continue

    ways: dict[int, list[dict[str, float]]] = {}
    for way in root.findall("way"):
        try:
            way_id = int(way.attrib["id"])
        except (KeyError, TypeError, ValueError):
            continue
        geometry = []
        for nd in way.findall("nd"):
            try:
                point = nodes.get(int(nd.attrib["ref"]))
            except (KeyError, TypeError, ValueError):
                point = None
            if point is not None:
                geometry.append({"lat": point[0], "lon": point[1]})
        if len(geometry) >= 2:
            ways[way_id] = geometry

    selected = None
    for relation in root.findall("relation"):
        try:
            relation_id = int(relation.attrib.get("id", "0"))
        except (TypeError, ValueError):
            relation_id = 0
        tags = {tag.attrib.get("k", ""): tag.attrib.get("v", "") for tag in relation.findall("tag")}
        if relation_id == _GR340_RELATION_ID or _is_gr340(tags):
            selected = (relation_id, relation, tags)
            if relation_id == _GR340_RELATION_ID:
                break
    if selected is None:
        return None

    relation_id, relation, tags = selected
    members = []
    for member in relation.findall("member"):
        if member.attrib.get("type") != "way":
            continue
        try:
            way_id = int(member.attrib["ref"])
        except (KeyError, TypeError, ValueError):
            continue
        geometry = ways.get(way_id)
        if geometry:
            members.append({
                "type": "way",
                "ref": way_id,
                "role": member.attrib.get("role", ""),
                "geometry": geometry,
            })
    if not members:
        return None
    return {
        "type": "relation",
        "id": relation_id or _GR340_RELATION_ID,
        "tags": tags,
        "members": members,
    }


def _direct_osm_relation() -> tuple[dict[str, Any] | None, str | None]:
    """Fetch GR 340 without Overpass, with a long cache and short timeout."""
    global _DIRECT_CACHE
    now = time.monotonic()
    if _DIRECT_CACHE is not None and now - _DIRECT_CACHE[0] < _CACHE_TTL:
        return deepcopy(_DIRECT_CACHE[1]), None
    try:
        response = requests.get(
            _OSM_FULL_URL,
            headers={
                "Accept": "application/xml,text/xml",
                "User-Agent": "TrekMap-France/9 (trekmap-france.onrender.com)",
            },
            timeout=_OSM_TIMEOUT,
        )
    except requests.Timeout:
        return None, "API OSM directe : délai dépassé"
    except requests.RequestException as exc:
        return None, f"API OSM directe inaccessible ({exc.__class__.__name__})"
    if response.status_code != 200:
        return None, f"API OSM directe HTTP {response.status_code}"
    relation = _relation_from_osm_xml(response.text)
    if relation is None:
        return None, "API OSM directe : relation 6850120 illisible ou incomplète"
    _DIRECT_CACHE = (time.monotonic(), deepcopy(relation))
    return relation, None


def _overpass_relation(v3) -> tuple[dict[str, Any] | None, str | None]:
    """Ask only for the known relation instead of scanning a 45 km circle."""
    query = (
        "[out:json][timeout:7];"
        f"relation({_GR340_RELATION_ID});"
        "out body geom;"
    )
    try:
        payload = v3._overpass(query)
    except Exception as exc:
        return None, f"Overpass GR 340 indisponible ({exc.__class__.__name__}: {str(exc)[:120]})"
    for element in (payload or {}).get("elements") or []:
        if element.get("type") != "relation":
            continue
        tags = element.get("tags") or {}
        if element.get("id") == _GR340_RELATION_ID or _is_gr340(tags):
            return element, None
    return None, "Overpass n'a pas renvoyé la relation 6850120"


def _relation_route(element, gr, rescue, start: dict[str, Any], target_km: float):
    tags = element.get("tags") or {}
    # The canonical id is sufficient identity if tagging is temporarily incomplete;
    # another relation still has to identify itself explicitly as GR 340.
    if element.get("id") != _GR340_RELATION_ID and not _is_gr340(tags):
        return None, "relation reçue différente du GR 340"
    coords = gr._join_relation_members(element.get("members") or [])
    if len(coords) < 8:
        return None, f"GR 340 : seulement {len(coords)} points reconstruits"

    # Preserve enough coastal detail that downsampling itself cannot manufacture
    # kilometre-wide gaps.
    coords = gr._downsample(coords, max_points=1200)
    closed, reason = rescue._close_relation(coords, rescue._length)
    if not closed:
        return None, f"GR 340 non refermable ({reason or 'raison inconnue'})"
    relation_km = rescue._length(closed)
    if relation_km < max(45.0, float(target_km) * 0.50) or relation_km > float(target_km) * 1.65:
        return None, f"GR 340 reconstruit à {relation_km:.1f} km, incompatible avec la demande"
    idx, start_off = rescue._nearest_index(closed[:-1], start)
    if start_off > 15.0:
        return None, f"GR 340 trouvé mais à {start_off:.1f} km du départ interprété"
    rotated = rescue._rotate_closed(closed, idx)
    if len(rotated) < 4 or rescue._max_gap(rotated) > rescue._MAX_RELATION_GAP_KM:
        return None, "GR 340 discontinu après reconstruction"

    first = rotated[0]
    start["lat"], start["lon"] = float(first[0]), float(first[1])
    start["name"] = "Départ sur GR 340"
    start["category"] = "trail"
    source_url = f"https://www.openstreetmap.org/relation/{element.get('id') or _GR340_RELATION_ID}"
    name = str(tags.get("name") or "Tour de Belle-Île-en-Mer").strip()
    rescue._LAST_META.set({
        "ref": "GR 340",
        "name": name[:160],
        "source_url": source_url,
        "distance_km": round(relation_km, 2),
        "targeted": True,
        "relation_id": int(element.get("id") or _GR340_RELATION_ID),
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
        "targeted_relation_id": int(element.get("id") or _GR340_RELATION_ID),
        "start_offset_before_snap_km": round(float(start_off), 2),
    }, None


def _targeted_gr340(v3, gr, rescue, start: dict[str, Any], target_km: float):
    if not _is_belle_ile(start):
        return None, "hors Belle-Île"

    reasons = []
    element, warning = _overpass_relation(v3)
    if element is not None:
        route, route_warning = _relation_route(element, gr, rescue, start, target_km)
        if route is not None:
            route["gr340_source"] = "overpass-relation-id"
            return route, None
        if route_warning:
            reasons.append(route_warning)
    elif warning:
        reasons.append(warning)

    # Critical production fallback: this path does not use v3._overpass, so an
    # already-open Overpass circuit breaker cannot hide the known island route.
    element, warning = _direct_osm_relation()
    if element is not None:
        route, route_warning = _relation_route(element, gr, rescue, start, target_km)
        if route is not None:
            route["gr340_source"] = "osm-api-relation-full"
            return route, None
        if route_warning:
            reasons.append(route_warning)
    elif warning:
        reasons.append(warning)

    detail = "; ".join(dict.fromkeys(x for x in reasons if x))
    return None, detail or "GR 340 ciblé non exploitable"


def install_belle_ile_gr340_priority(roundtrip, gr, rescue) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    current_best = roundtrip._best_roundtrip

    def best_roundtrip(start, target_km, daily_min, daily_max, days, v3):
        targeted_warning = None
        if _is_belle_ile(start) and 55.0 <= float(target_km) <= 130.0:
            route, targeted_warning = _targeted_gr340(v3, gr, rescue, start, target_km)
            if route is not None:
                return route
        try:
            return current_best(start, target_km, daily_min, daily_max, days, v3)
        except HTTPException as exc:
            detail = str(getattr(exc, "detail", exc) or "")
            if targeted_warning:
                detail = f"{detail} Diagnostic GR 340 ciblé : {targeted_warning}.".strip()
            raise HTTPException(status_code=exc.status_code, detail=detail)

    roundtrip._best_roundtrip = best_roundtrip


__all__ = [
    "install_belle_ile_gr340_priority",
    "_targeted_gr340",
    "_is_belle_ile",
    "_is_gr340",
    "_relation_from_osm_xml",
    "_direct_osm_relation",
    "_GR340_RELATION_ID",
]
