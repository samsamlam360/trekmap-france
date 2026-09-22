"""Resilient campsite/refuge lookup rescue for TrekBrain v9.

The normal planner uses the shared Overpass circuit breaker.  That is good for
latency, but a broad POI query timing out could make the later campsite-first
fallback see an empty list and incorrectly report "0 campings".  This overlay
adds one tiny accommodation-only Overpass query when the normal lookup did not
return enough nights.

The rescue is deliberately bounded: two public endpoints maximum, short
timeouts, no retries, and it only runs when the normal pool is insufficient.
"""
from __future__ import annotations

import math
from typing import Any

_INSTALLED = False


def _osm_url(element: dict[str, Any]) -> str:
    typ = str(element.get("type") or "node")
    ident = element.get("id")
    return f"https://www.openstreetmap.org/{typ}/{ident}" if ident is not None else ""


def _direct_stays(start: dict[str, Any], category: str, radius_km: float) -> list[dict[str, Any]]:
    """One lightweight accommodation-only Overpass lookup.

    This intentionally calls the low-level cached request helper rather than the
    broad planner _overpass wrapper, because the latter may be inside its short
    circuit-breaker cooldown after an unrelated POI timeout.
    """
    from . import free_planner_v2 as free

    radius_m = max(1500, min(int(float(radius_km) * 1000), 35000))
    lat = float(start["lat"])
    lon = float(start["lon"])
    if category == "camping":
        filters = ('["tourism"="camp_site"]', '["tourism"="caravan_site"]')
    else:
        filters = (
            '["tourism"="alpine_hut"]',
            '["tourism"="wilderness_hut"]',
            '["amenity"="shelter"]',
        )
    clauses = "".join(f"nwr(around:{radius_m},{lat},{lon}){flt};" for flt in filters)
    query = f"[out:json][timeout:4];({clauses});out center tags 80;"

    data = None
    for url in list(getattr(free, "OVERPASS_URLS", []))[:2]:
        try:
            data = free._request_json(
                url,
                data={"data": query},
                timeout=3.0,
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
    for element in (data.get("elements") or [])[:80]:
        tags = element.get("tags") or {}
        elat, elon = element.get("lat"), element.get("lon")
        if elat is None or elon is None:
            center = element.get("center") or {}
            elat, elon = center.get("lat"), center.get("lon")
        try:
            elat, elon = float(elat), float(elon)
        except (TypeError, ValueError):
            continue

        if category == "camping":
            if tags.get("tourism") not in {"camp_site", "caravan_site"}:
                continue
        else:
            if not (
                tags.get("tourism") in {"alpine_hut", "wilderness_hut"}
                or tags.get("amenity") == "shelter"
            ):
                continue

        name = str(tags.get("name") or ("Camping" if category == "camping" else "Refuge"))
        rows.append({
            "name": name,
            "lat": elat,
            "lon": elon,
            "category": category,
            "source_url": _osm_url(element),
            "osm_tags": dict(tags),
        })
    return rows


def _distance_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (
        float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"]),
    ))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


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

        # Four hiking days around 18–20 km can easily put useful campsites more
        # than 20 km radially from the centre.  35 km is still a bounded local
        # lookup, not a France-wide search.
        radius = min(35.0, max(24.0, float(daily_target) * 1.9))
        rescue = _direct_stays(start, category, radius)

        merged = []
        seen = set()
        for row in normal + rescue:
            key = str(row.get("source_url") or f"{row.get('name')}:{row.get('lat')}:{row.get('lon')}")
            if key in seen:
                continue
            seen.add(key)
            try:
                radial = float(v3_module._dist(start, row))
            except Exception:
                radial = _distance_km(start, row)
            if radial < 0.5 or radial > radius + 0.5:
                continue
            enriched = dict(row)
            enriched["_radial_km"] = radial
            enriched["_bearing"] = campsite_loop._bearing(start, enriched)
            enriched["_start_lat"] = float(start["lat"])
            enriched["_start_lon"] = float(start["lon"])
            merged.append(enriched)

        # Keep angular diversity so the matrix can form a real loop rather than
        # selecting three campsites along the same road.
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


__all__ = ["install_stay_lookup_rescue", "_direct_stays"]
