"""Resilient campsite/refuge lookup rescue for TrekBrain v9.

A broad POI lookup can time out even when campsites really exist.  This module
therefore has a small accommodation-only recovery chain used only when the
normal planner did not return enough overnight stops:

1. a compact Overpass bounding-box query;
2. Photon, biased around the departure;
3. Nominatim, bounded to the same local box.

The extra sources are discovery only.  A campsite is never considered usable
just because a geocoder returned it: the campsite-first planner still asks the
ORS walking matrix and the final route engine to validate the actual legs.
"""
from __future__ import annotations

import math
from typing import Any

_INSTALLED = False


def _osm_url(element: dict[str, Any]) -> str:
    typ = str(element.get("type") or element.get("osm_type") or "node").casefold()
    typ = {"n": "node", "w": "way", "r": "relation"}.get(typ, typ)
    ident = element.get("id") if element.get("id") is not None else element.get("osm_id")
    return f"https://www.openstreetmap.org/{typ}/{ident}" if ident is not None and typ in {"node", "way", "relation"} else ""


def _distance_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (
        float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"]),
    ))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _bbox(start: dict[str, Any], radius_km: float) -> tuple[float, float, float, float]:
    lat = float(start["lat"])
    lon = float(start["lon"])
    dlat = float(radius_km) / 111.0
    dlon = float(radius_km) / max(35.0, 111.0 * math.cos(math.radians(lat)))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def _normalise_stay(name: str, lat: float, lon: float, category: str, source_url: str = "", tags=None) -> dict[str, Any]:
    return {
        "name": str(name or ("Camping" if category == "camping" else "Refuge"))[:180],
        "lat": float(lat),
        "lon": float(lon),
        "category": category,
        "source_url": str(source_url or ""),
        "osm_tags": dict(tags or {}),
    }


def _direct_stays(start: dict[str, Any], category: str, radius_km: float) -> list[dict[str, Any]]:
    """Fast accommodation-only Overpass lookup, independent of the broad POI breaker."""
    from . import free_planner_v2 as free

    south, west, north, east = _bbox(start, min(float(radius_km), 38.0))
    if category == "camping":
        filters = ('["tourism"="camp_site"]', '["tourism"="caravan_site"]')
    else:
        filters = (
            '["tourism"="alpine_hut"]',
            '["tourism"="wilderness_hut"]',
            '["amenity"="shelter"]',
        )
    # A bbox is significantly cheaper for Overpass than several repeated
    # around() searches and avoids the false "0 camping" seen in production.
    clauses = "".join(f"nwr{flt}({south:.6f},{west:.6f},{north:.6f},{east:.6f});" for flt in filters)
    query = f"[out:json][timeout:4];({clauses});out center tags 100;"

    data = None
    for url in list(getattr(free, "OVERPASS_URLS", []))[:3]:
        try:
            data = free._request_json(
                url,
                data={"data": query},
                timeout=2.8,
                ttl=3600,
                service="Overpass nuitées",
                retries=1,
            )
            if isinstance(data, dict):
                break
        except Exception:
            data = None
    if not isinstance(data, dict):
        return []

    rows = []
    for element in (data.get("elements") or [])[:100]:
        tags = element.get("tags") or {}
        elat, elon = element.get("lat"), element.get("lon")
        if elat is None or elon is None:
            center = element.get("center") or {}
            elat, elon = center.get("lat"), center.get("lon")
        try:
            elat, elon = float(elat), float(elon)
        except (TypeError, ValueError):
            continue
        if category == "camping" and tags.get("tourism") not in {"camp_site", "caravan_site"}:
            continue
        if category != "camping" and not (
            tags.get("tourism") in {"alpine_hut", "wilderness_hut"}
            or tags.get("amenity") == "shelter"
        ):
            continue
        rows.append(_normalise_stay(
            tags.get("name") or tags.get("ref") or "",
            elat, elon, category, _osm_url(element), tags,
        ))
    return rows


def _photon_stays(start: dict[str, Any], category: str, radius_km: float) -> list[dict[str, Any]]:
    """Second source when Overpass is unavailable or unexpectedly empty."""
    from . import free_planner_v2 as free

    term = "camping" if category == "camping" else "refuge"
    try:
        data = free._request_json(
            free.PHOTON_URL,
            params={
                "q": term,
                "lat": float(start["lat"]),
                "lon": float(start["lon"]),
                "limit": 20,
                "lang": "fr",
            },
            timeout=3.0,
            ttl=3600,
            service="Photon nuitées",
            retries=1,
        )
    except Exception:
        return []

    rows = []
    for feature in data.get("features", []) if isinstance(data, dict) else []:
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        country = str(props.get("countrycode") or props.get("country_code") or "").upper()
        if country and country != "FR":
            continue
        osm_value = str(props.get("osm_value") or "").casefold()
        name = str(props.get("name") or props.get("street") or term)
        folded = name.casefold()
        if category == "camping":
            if osm_value not in {"camp_site", "caravan_site"} and "camp" not in folded:
                continue
        elif osm_value not in {"alpine_hut", "wilderness_hut", "shelter"} and not any(x in folded for x in ("refuge", "gîte", "gite", "abri")):
            continue
        item = _normalise_stay(name, lat, lon, category, _osm_url(props), props)
        if _distance_km(start, item) <= float(radius_km) + 1.0:
            rows.append(item)
    return rows


def _nominatim_stays(start: dict[str, Any], category: str, radius_km: float) -> list[dict[str, Any]]:
    """Last bounded discovery fallback.  One query only, never used for routing."""
    from . import free_planner_v2 as free

    south, west, north, east = _bbox(start, min(float(radius_km), 38.0))
    term = "camping" if category == "camping" else "refuge"
    try:
        rows = free._request_json(
            free.NOMINATIM_URL,
            params={
                "q": term,
                "format": "jsonv2",
                "limit": 20,
                "countrycodes": "fr",
                "bounded": 1,
                "viewbox": f"{west:.6f},{north:.6f},{east:.6f},{south:.6f}",
            },
            timeout=3.0,
            ttl=3600,
            service="Nominatim nuitées",
            retries=1,
        )
    except Exception:
        return []

    out = []
    for row in rows if isinstance(rows, list) else []:
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        typ = str(row.get("type") or "").casefold()
        display = str(row.get("display_name") or term)
        folded = display.casefold()
        if category == "camping":
            if typ not in {"camp_site", "caravan_site"} and "camp" not in folded:
                continue
        elif not any(x in typ + " " + folded for x in ("refuge", "hut", "shelter", "gîte", "gite", "abri")):
            continue
        source = _osm_url({"osm_type": row.get("osm_type"), "osm_id": row.get("osm_id")})
        item = _normalise_stay(display.split(",")[0], lat, lon, category, source, row)
        if _distance_km(start, item) <= float(radius_km) + 1.0:
            out.append(item)
    return out


def _merge_and_enrich(v3_module, campsite_loop, start, rows, radius: float) -> list[dict[str, Any]]:
    merged = []
    seen = set()
    for row in rows:
        key = str(row.get("source_url") or f"{row.get('name')}:{row.get('lat')}:{row.get('lon')}")
        if key in seen:
            continue
        seen.add(key)
        try:
            radial = float(v3_module._dist(start, row))
        except Exception:
            radial = _distance_km(start, row)
        if radial < 0.35 or radial > radius + 0.75:
            continue
        enriched = dict(row)
        enriched["_radial_km"] = radial
        enriched["_bearing"] = campsite_loop._bearing(start, enriched)
        enriched["_start_lat"] = float(start["lat"])
        enriched["_start_lon"] = float(start["lon"])
        merged.append(enriched)
    return merged


def install_stay_lookup_rescue(v3, campsite_loop, roundtrip) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_diverse = campsite_loop._diverse_stays

    def diverse_stays(v3_module, roundtrip_module, start, category: str, days: int, daily_target: float):
        normal = list(original_diverse(v3_module, roundtrip_module, start, category, days, daily_target))
        needed = max(1, int(days) - 1)
        if len(normal) >= needed:
            return normal

        radius = min(38.0, max(25.0, float(daily_target) * 2.0))
        discovered = list(normal)
        discovered += _direct_stays(start, category, radius)
        merged = _merge_and_enrich(v3_module, campsite_loop, start, discovered, radius)

        if len(merged) < needed:
            discovered += _photon_stays(start, category, radius)
            merged = _merge_and_enrich(v3_module, campsite_loop, start, discovered, radius)
        if len(merged) < needed:
            discovered += _nominatim_stays(start, category, radius)
            merged = _merge_and_enrich(v3_module, campsite_loop, start, discovered, radius)

        # Keep angular diversity so a nearest-only list does not recreate an
        # out-and-back cycle.  ORS Matrix remains the final feasibility check.
        if len(merged) <= 20:
            return merged
        sectors = [[] for _ in range(8)]
        for stay in merged:
            sector = int(float(stay["_bearing"]) / (2 * math.pi) * 8) % 8
            sectors[sector].append(stay)
        for sector in sectors:
            sector.sort(key=lambda x: abs(float(x["_radial_km"]) - float(daily_target) * 0.75))
        selected = []
        index = 0
        while len(selected) < 20 and any(index < len(s) for s in sectors):
            for sector in sectors:
                if index < len(sector) and len(selected) < 20:
                    selected.append(sector[index])
            index += 1
        return selected

    campsite_loop._diverse_stays = diverse_stays


__all__ = [
    "install_stay_lookup_rescue", "_direct_stays", "_photon_stays", "_nominatim_stays",
]
