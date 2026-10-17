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

Stage boundary positions may now move a few route-kilometres toward sourced,
route-close stays and nearby real water/grocery evidence. They never become
a confirmed place to sleep until ORS verifies both walking directions.

The actual walking backbone still comes from the existing GR/OSM/ORS planners.
No straight-line geometry is promoted to a hiking route.
"""
from __future__ import annotations

import math
from bisect import bisect_left
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
from copy import deepcopy
from contextvars import copy_context
from typing import Any

from . import trekbrain_perf_profile_v9 as perf

from fastapi import HTTPException

_INSTALLED = False
_SAFETY_INSTALLED = False
_MAX_OFFROUTE_KM = 6.0
# Candidate-only crow-flight radius; real walking distance still must be
# verified both ways by the bounded ORS matrix and remain <= 4 km.
# 2.8 km rejected legitimate near-threshold candidates on new-region treks
# before the walking router could even evaluate them. No route is assumed.
_WALK_CONNECTOR_LIMIT_KM = 3.2
_MAX_DISCOVERED = 80
_MAX_CONNECTOR_OPTIONS = 12  # One ORS Matrix, at most 24 locations.
_CONNECTOR_BUDGET_SECONDS = 4.0
_MAX_DIRECTION_CALLS = 2  # One round-trip fallback, never one request per night.


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _stay_key(item: dict[str, Any]) -> str:
    source = str(item.get("source_url") or "").strip().split("#", 1)[0].split("?", 1)[0].rstrip("/")
    if source:
        return source
    try:
        return f"{_fold(item.get('name'))}|{float(item['lat']):.5f}|{float(item['lon']):.5f}"
    except Exception:
        return _fold(item.get("name"))


def _night_anchors(roundtrip, coords, days: int, stages=None) -> list[dict[str, Any]]:
    """Interpolate the fixed backbone at actual walking-day boundaries.

    Only the search/connector origin changes; the source route and stage lengths
    remain untouched, including routes with sparse or unevenly sampled GPS.
    """
    if days <= 1 or len(coords or []) < 2:
        return []
    cumulative = roundtrip._cumulative(coords)
    total = float(cumulative[-1]) if cumulative else 0.0
    if not math.isfinite(total) or total <= 0:
        return []
    from .trekbrain_resources_v9 import _stage_progress_breaks
    breaks = _stage_progress_breaks({"stages": stages or []}, days)
    out = []
    for night, fraction in enumerate(breaks[1:-1], 1):
        target = total * fraction
        right = max(1, min(bisect_left(cumulative, target), len(coords) - 1))
        left = right - 1
        length = float(cumulative[right]) - float(cumulative[left])
        ratio = (target - float(cumulative[left])) / length if length > 0 else 0.0
        a, b = coords[left], coords[right]
        out.append({
            "night": night, "name": f"Fin du jour {night}",
            "lat": float(a[0]) + ratio * (float(b[0]) - float(a[0])),
            "lon": float(a[1]) + ratio * (float(b[1]) - float(a[1])),
            "category": "route_anchor", "route_progress_km": target,
        })
    return out


def _requested_category(intent: dict[str, Any]) -> str | None:
    accommodation = _fold(intent.get("accommodation") or "")
    if accommodation == "camping":
        return "camping"
    if accommodation == "refuge":
        return "refuge"
    if intent.get("sleep") and accommodation != "bivouac":
        # Generic accommodation requests (hotel/gîte/auberge accepted) still
        # deserve route-first night logistics. Historically they skipped this
        # layer entirely and were scored as "aucune nuitée fiable".
        return "lodging"
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
    fallback_name = (
        "Camping" if category == "camping"
        else "Refuge" if category == "refuge"
        else "Hébergement"
    )
    return {
        "name": str(tags.get("name") or tags.get("ref") or fallback_name)[:180],
        "lat": lat,
        "lon": lon,
        "category": category,
        "source_url": _osm_url(element),
        "osm_tags": dict(tags),
    }


def _element_point(element: dict[str, Any]) -> tuple[float, float] | None:
    lat, lon = element.get("lat"), element.get("lon")
    if lat is None or lon is None:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    return lat, lon


def _terrain_resource(element: dict[str, Any]) -> dict[str, Any] | None:
    tags = element.get("tags") or {}
    point = _element_point(element)
    if not point:
        return None
    lat, lon = point
    category = None
    status = "unverified"
    from .trekbrain_water_evidence_v9 import mapped_water_source, potability_status
    if mapped_water_source(tags):
        category = "water"
        # Explicit no/conditional water tags remain stronger than the icon.
        status = potability_status(tags)
    elif tags.get("shop") in {
        "supermarket", "convenience", "bakery", "general",
        "grocery", "deli", "greengrocer", "food",
    } and tags.get("access") != "private" and tags.get("disused") != "yes":
        category = "food"
    elif (
        tags.get("railway") in {"station", "halt"}
        or tags.get("amenity") in {"bus_station", "ferry_terminal"}
    ):
        category = "transit"
    if category is None:
        return None
    default_name = (
        "Point d'eau" if category == "water"
        else "Ravitaillement" if category == "food"
        else "Transport public"
    )
    return {
        "name": str(tags.get("name") or default_name)[:180],
        "lat": lat,
        "lon": lon,
        "category": category,
        "water_status": status,
        "source_url": _osm_url(element),
        "osm_tags": dict(tags),
    }


def _bbox_route_query(
    coords,
    category: str,
    *,
    include_terrain: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """One compact Overpass corridor query with one bounded empty-result failover."""
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
        return [], [], False

    min_lat = min(x[0] for x in valid)
    max_lat = max(x[0] for x in valid)
    min_lon = min(x[1] for x in valid)
    max_lon = max(x[1] for x in valid)
    mid_lat = (min_lat + max_lat) / 2.0
    search_offroute_km = 10.0 if category == "lodging" else _MAX_OFFROUTE_KM
    pad_lat = min(0.12, max(0.025, search_offroute_km / 111.0))
    pad_lon = min(
        0.16,
        max(0.03, search_offroute_km / max(35.0, 111.0 * math.cos(math.radians(mid_lat)))),
    )
    south, north = min_lat - pad_lat, max_lat + pad_lat
    west, east = min_lon - pad_lon, max_lon + pad_lon

    if category == "camping":
        stay_filters = ('["tourism"="camp_site"]', '["tourism"="caravan_site"]')
    elif category == "refuge":
        stay_filters = (
            '["tourism"="alpine_hut"]',
            '["tourism"="wilderness_hut"]',
            '["amenity"="shelter"]["shelter_type"="basic_hut"]',
        )
    else:
        stay_filters = (
            '["tourism"="hotel"]',
            '["tourism"="hostel"]',
            '["tourism"="guest_house"]',
            '["tourism"="chalet"]',
            '["tourism"="apartment"]',
            '["tourism"="camp_site"]',
            '["tourism"="alpine_hut"]',
            '["tourism"="wilderness_hut"]',
            '["amenity"="shelter"]["shelter_type"="basic_hut"]',
        )

    terrain_filters = (
        '["amenity"="drinking_water"]',
        '["man_made"="water_tap"]',
        '["natural"="spring"]',
        '["amenity"="water_point"]',
        '["man_made"="water_well"]["drinking_water"="yes"]',
        '["man_made"="water_pump"]["drinking_water"="yes"]',
        '["railway"="station"]',
        '["railway"="halt"]',
        '["amenity"="bus_station"]',
        '["amenity"="ferry_terminal"]',
    ) if include_terrain else ()

    # Keep the existing lodging+water query, but give shops a separate
    # Overpass output quota. The previous shared cap of 220 could return only
    # water/stays in dense coastal or mountain bboxes, hiding every grocery
    # even when OSM knew about it. Both queries are in one HTTP request.
    clauses = "".join(
        f"nwr{flt}({south:.6f},{west:.6f},{north:.6f},{east:.6f});"
        for flt in (*stay_filters, *terrain_filters)
    )
    query = f"[out:json][timeout:5];({clauses});out center tags {200 if include_terrain else 160};"
    if include_terrain:
        food_clause = (
            f'nwr["shop"~"^(supermarket|convenience|bakery|general|grocery|deli|greengrocer|food)$"]'
            f'({south:.6f},{west:.6f},{north:.6f},{east:.6f});'
        )
        query += f"({food_clause});out center tags 90;"

    data = None
    all_mirrors = list(free.OVERPASS_URLS)
    # Prefer an independent private.coffee instance over a sibling FOSSGIS
    # backend when the primary is throttled. Keep the legacy mirror as the
    # third option, still under the same bounded parallel fallback wave.
    mirrors = (
        [all_mirrors[0], all_mirrors[-1], all_mirrors[1]]
        if len(all_mirrors) >= 4 else all_mirrors[:3]
    )

    # Keep normal provider load unchanged: the primary mirror gets the first
    # chance on its own. Only when it fails or returns an empty corridor do we
    # fan out to the two independent fallback mirrors in parallel.
    if mirrors:
        try:
            primary = free._request_json(
                mirrors[0],
                data={"data": query},
                timeout=1.8,
                ttl=3600,
                service="Overpass route bundle" if include_terrain else "Overpass route stays",
                retries=1,
                cache_empty=False,
            )
        except Exception:
            primary = None
        if isinstance(primary, dict):
            data = primary

    if not (isinstance(data, dict) and data.get("elements")) and len(mirrors) > 1:
        fallback_urls = mirrors[1:3]

        def fallback_request(index_url):
            index, url = index_url
            try:
                return index, free._request_json(
                    url,
                    data={"data": query},
                    timeout=0.85,
                    ttl=3600,
                    service=(
                        ("Overpass route bundle" if include_terrain else "Overpass route stays")
                        + f" fallback {index}"
                    ),
                    retries=1,
                    cache_empty=False,
                )
            except Exception:
                return index, None

        fallback_results = {}
        with ThreadPoolExecutor(max_workers=len(fallback_urls)) as pool:
            futures = [
                pool.submit(fallback_request, (index + 1, url))
                for index, url in enumerate(fallback_urls)
            ]
            for future in as_completed(futures):
                index, candidate = future.result()
                fallback_results[index] = candidate
                if isinstance(candidate, dict) and candidate.get("elements"):
                    data = candidate
                    for pending in futures:
                        if pending is not future:
                            pending.cancel()
                    break

        # If every fallback mirror was empty, retain one syntactically valid
        # empty response only so the parser can return preloaded=False. The
        # outer Photon/resource fallbacks then remain eligible.
        if not (isinstance(data, dict) and data.get("elements")):
            for index in sorted(fallback_results):
                candidate = fallback_results[index]
                if isinstance(candidate, dict):
                    data = candidate
                    break

    if not isinstance(data, dict):
        return [], [], False

    stays = []
    terrain = []
    seen_terrain = set()
    for element in (data.get("elements") or [])[: (290 if include_terrain else 160)]:
        tags = element.get("tags") or {}

        stay_match = False
        if category == "camping":
            stay_match = tags.get("tourism") in {"camp_site", "caravan_site"}
        elif category == "refuge":
            stay_match = (
                tags.get("tourism") in {"alpine_hut", "wilderness_hut"}
                or (tags.get("amenity") == "shelter" and tags.get("shelter_type") == "basic_hut")
            )
        else:
            stay_match = (
                tags.get("tourism") in {
                    "hotel", "hostel", "guest_house", "chalet", "apartment",
                    "camp_site", "alpine_hut", "wilderness_hut",
                }
                or (tags.get("amenity") == "shelter" and tags.get("shelter_type") == "basic_hut")
            )
        if stay_match:
            stay = _normalise_stay(element, category)
            if stay:
                stays.append(stay)

        if include_terrain:
            resource = _terrain_resource(element)
            if resource:
                key = (
                    resource.get("category"),
                    round(float(resource["lat"]), 5),
                    round(float(resource["lon"]), 5),
                )
                if key not in seen_terrain:
                    seen_terrain.add(key)
                    terrain.append(resource)

    # "preloaded" means this query actually supplied reusable corridor
    # evidence. An empty provider response must not make the outer resource
    # overlay skip its independent terrain/Photon fallbacks.
    preloaded = bool(stays or terrain)
    return stays, terrain, preloaded


def _bbox_route_stays(coords, category: str) -> list[dict[str, Any]]:
    stays, _terrain, _preloaded = _bbox_route_query(
        coords, category, include_terrain=False
    )
    return stays


def _bbox_route_bundle(coords, category: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    return _bbox_route_query(coords, category, include_terrain=True)

def _route_probe_stays(v3, roundtrip, coords, category: str) -> list[dict[str, Any]]:
    """Bounded fallback when a full-corridor bbox lookup is unavailable."""
    cum = roundtrip._cumulative(coords)
    if not cum or float(cum[-1]) <= 0:
        return []
    rows = []
    seen = set()
    probe_count = 4
    lookup = getattr(roundtrip, "_nearby_stays", None)
    for part in range(probe_count):
        target = float(cum[-1]) * (part + 0.5) / probe_count
        idx = roundtrip._route_index_for_progress(cum, target)
        point = coords[idx]
        anchor = {"lat": float(point[0]), "lon": float(point[1])}
        try:
            if callable(lookup):
                # speed_v9 turns this into one broad cached Overpass pool.
                found = list(lookup(v3, anchor, category, 6.0) or [])
            else:
                found = list(v3._nearby(anchor["lat"], anchor["lon"], 6.0, [category]) or [])
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



def _nominatim_route_stays(coords, category: str) -> list[dict[str, Any]]:
    """One route-bounded Nominatim query for overnight candidates.

    Overpass remains the exact OSM-tag source. This fallback is intentionally
    one request for the whole route, not one request per stage.
    """
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
    radius_km = 12.5 if category == "lodging" else 8.0
    pad_lat = min(0.14, max(0.025, radius_km / 111.0))
    pad_lon = min(
        0.18,
        max(0.03, radius_km / max(35.0, 111.0 * math.cos(math.radians(mid_lat)))),
    )
    south, north = min_lat - pad_lat, max_lat + pad_lat
    west, east = min_lon - pad_lon, max_lon + pad_lon

    if category == "camping":
        query = "[camping]"
        include = "osm.tourism.camp_site,osm.tourism.caravan_site"
    elif category == "refuge":
        query = "[refuge]"
        include = "osm.tourism.alpine_hut,osm.tourism.wilderness_hut,osm.amenity.shelter"
    else:
        query = "[hotel]"
        include = (
            "osm.tourism.hotel,osm.tourism.hostel,osm.tourism.guest_house,"
            "osm.tourism.chalet,osm.tourism.apartment"
        )
    try:
        payload = free._request_json(
            free.NOMINATIM_URL,
            params={
                "q": query,
                "include": include,
                "format": "jsonv2",
                "extratags": 1,
                "limit": 30,
                "countrycodes": "fr",
                "bounded": 1,
                "viewbox": f"{west:.6f},{north:.6f},{east:.6f},{south:.6f}",
            },
            timeout=1.6,
            ttl=3600,
            service="Nominatim route stays",
            retries=1,
            cache_empty=False,
        )
    except Exception:
        return []

    out = []
    for row in payload if isinstance(payload, list) else []:
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        typ = _fold(row.get("type") or "")
        cls = _fold(row.get("category") or row.get("class") or "")
        display = str(row.get("display_name") or row.get("name") or query)
        if cls == "tourism" and typ in {"camp site", "caravan site"}:
            actual = "camping"
        elif (cls == "tourism" and typ in {"alpine hut", "wilderness hut"}) or (cls == "amenity" and typ == "shelter" and (row.get("extratags") or {}).get("shelter_type") == "basic_hut"):
            actual = "refuge"
        elif cls == "tourism" and typ in {"hotel", "hostel", "guest house", "chalet", "apartment"}:
            actual = "lodging"
        else:
            continue
        if category in {"camping", "refuge"} and actual != category:
            continue
        # Nominatim display names include entire street addresses. Never use
        # those words as evidence for a stay or to reclassify an actual hotel.
        source_type = str(row.get("osm_type") or "").casefold()
        source_id = str(row.get("osm_id") or "")
        if source_type not in {"node", "way", "relation"} or not re.fullmatch(r"[1-9][0-9]*", source_id):
            continue
        source = _osm_url({"osm_type": source_type, "osm_id": source_id})
        out.append({
            "name": display.split(",")[0].strip()[:180] or (
                "Camping" if actual == "camping" else "Refuge" if actual == "refuge" else "Hébergement"
            ),
            "lat": lat,
            "lon": lon,
            "category": actual,
            "source_url": source,
            "osm_tags": {
                "class": row.get("category") or row.get("class"),
                "type": row.get("type"),
                "shelter_type": (row.get("extratags") or {}).get("shelter_type"),
            },
        })

    deduped, seen = [], set()
    for item in out:
        key = _stay_key(item)
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:_MAX_DISCOVERED]


def _photon_split_stays(v3, roundtrip, coords, category: str, days: int, night_anchors=None) -> list[dict[str, Any]]:
    """Fast first pass: one bounded Photon lookup around each ideal night split."""
    if days <= 1 or len(coords or []) < 2:
        return []
    lookup = getattr(v3, "_photon_anchor_resource", None)
    if not callable(lookup):
        return []

    if night_anchors is not None:
        anchors = list(night_anchors)
    else:
        equal = getattr(roundtrip, "_equal_anchors", None)
        anchors = equal(coords, days) if callable(equal) else []
        if len(anchors) != days - 1:
            anchors = _night_anchors(roundtrip, coords, days)
    if not anchors or (night_anchors is None and len(anchors) != days - 1):
        return []

    if category == "camping":
        tags = ("tourism:camp_site", "tourism:caravan_site")
        radius = 8.0
    elif category == "refuge":
        tags = (
            "tourism:alpine_hut", "tourism:wilderness_hut",
            "amenity:shelter",
        )
        radius = 8.0
    else:
        tags = (
            "tourism:hotel", "tourism:hostel", "tourism:guest_house",
            "tourism:chalet", "tourism:apartment",
            "tourism:camp_site", "tourism:alpine_hut",
            "tourism:wilderness_hut", "amenity:shelter",
        )
        # Generic lodging may legitimately be a short transfer away from the
        # hiking line. Route-first logistics keeps that transfer separate from
        # the pedestrian backbone, so discover a wider pool without reshaping
        # the route itself.
        radius = 12.5

    jobs = []
    # Six requests maximum: use the existing single rescue wave on useful
    # night ends rather than opening two text requests for every day of a GR.
    max_anchors = 3 if category == "lodging" else 6
    if len(anchors) > max_anchors:
        anchors = [anchors[round((len(anchors) - 1) * i / (max_anchors - 1))]
                   for i in range(max_anchors)]
    for anchor in anchors:
        if category == "lodging":
            # One rural + one conventional lodging query, in the same bounded
            # parallel wave. This preserves Tours' gîte gains while avoiding the
            # Mont-Saint-Michel regression where "gîte" alone missed the nearby
            # hotel that the previous query found.
            jobs.append((anchor, "gîte"))
            jobs.append((anchor, "hotel"))
        elif category in {"camping", "refuge"}:
            # Keep the natural text query selected by _photon_anchor_resource,
            # but do not override it here: an override intentionally disables
            # Photon's structured osm_tag filter. Public text ranking for generic
            # words such as "camping" and "refuge" proved highly variable on
            # Render, while q + osm_tag + bbox is deterministic and costs the
            # same single request per night anchor.
            jobs.append((anchor, None))
        else:
            jobs.append((anchor, None))

    found = []
    profile = perf.current()

    def profiled_lookup(anchor, query_override):
        started = time.perf_counter()
        outcome = "ok"
        try:
            if query_override:
                return lookup(
                    anchor,
                    "stay",
                    tags,
                    radius,
                    query_override=query_override,
                )
            return lookup(anchor, "stay", tags, radius)
        except Exception:
            outcome = "error"
            raise
        finally:
            perf.record(
                "photon.lookup",
                (time.perf_counter() - started) * 1000,
                profile=profile,
                category=category,
                query=query_override or category,
                outcome=outcome,
            )

    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
        futures = [
            pool.submit(profiled_lookup, anchor, query_override)
            for anchor, query_override in jobs
        ]

        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception:
                item = None
            if not isinstance(item, dict):
                continue
            # Photon returns up to 20 features per HTTP response. Reuse
            # several real OSM stays rather than discarding other camps/gites
            # located on different walking days. Each row has already passed
            # source, tag and radius checks in the shared Photon parser.
            queue = [item] + [
                row for row in (item.get("_photon_alternatives") or [])[:6]
                if isinstance(row, dict)
            ]
            for raw in queue:
                candidate = {k: v for k, v in raw.items()
                             if k != "_photon_alternatives"}
                actual = str(candidate.get("category") or "")
                if category in {"camping", "refuge"} and actual != category:
                    continue
                if category == "lodging" and actual not in {"camping", "refuge", "lodging"}:
                    continue
                found.append(candidate)

    deduped, seen = [], set()
    for item in found:
        key = _stay_key(item)
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _project_stays(roundtrip, coords, rows, category: str, max_offroute_km: float) -> list[dict[str, Any]]:
    cum = roundtrip._cumulative(coords)
    if not cum:
        return []
    selected = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        tags = row.get("osm_tags") or {}
        if not isinstance(tags, dict):
            continue
        if tags.get("access") in {"private", "no"} or tags.get("disused") == "yes" or tags.get("opening_hours") == "closed":
            continue
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        if not str(row.get("source_url") or "").strip():
            continue
        is_shelter = tags.get("amenity") == "shelter" or (
            (tags.get("class") or tags.get("osm_key")) == "amenity"
            and (tags.get("type") or tags.get("osm_value")) == "shelter"
        )
        if is_shelter and tags.get("shelter_type") != "basic_hut":
            continue
        item = dict(row)
        item["category"] = category
        try:
            projection = roundtrip._project_stay_to_route(coords, cum, item)
        except Exception:
            projection = None
        if not projection:
            continue
        index, progress, offroute = projection
        if not all(math.isfinite(float(value)) for value in (progress, offroute)) or float(offroute) < 0 or float(offroute) > float(max_offroute_km):
            continue
        item["_route_index"] = int(index)
        item["_route_progress_km"] = float(progress)
        item["_offroute_km"] = float(offroute)
        key = _stay_key(item)
        # The same real establishment can appear as both an OSM node and way.
        # An identical name at the same location is one night option, not two.
        alias = next((k for k, other in selected.items()
                      if _fold(other.get("name")) == _fold(item.get("name"))
                      and _geo_km(other, item) <= 0.05), None)
        key = alias or key
        old = selected.get(key)
        if old is None or float(item["_offroute_km"]) < float(old["_offroute_km"]):
            selected[key] = item
    out = list(selected.values())
    out.sort(key=lambda x: (float(x.get("_route_progress_km") or 0), float(x.get("_offroute_km") or 0)))
    return out[:_MAX_DISCOVERED]


def _choose_stays(roundtrip, coords, rows, days: int, daily_target: float, night_anchors=None) -> list[dict[str, Any]]:
    """Pick one unique stay near each ideal route split without moving the route."""
    needed = max(0, int(days) - 1)
    if needed <= 0 or not rows:
        return []
    cum = roundtrip._cumulative(coords)
    if not cum or float(cum[-1]) <= 0:
        return []
    total = float(cum[-1])
    window = max(8.0, min(15.0, float(daily_target) * 0.62))
    # A missing intermediate night must not discard later discovered nights or
    # renumber them onto earlier days. Maximise coverage before proximity.
    beam = [(0, 0.0, [], frozenset())]
    for night in range(1, days):
        target = (float(night_anchors[night - 1]["route_progress_km"])
                  if night_anchors and len(night_anchors) >= night else total * night / days)
        options = [
            row for row in rows
            if abs(float(row.get("_route_progress_km") or 0) - target) <= window
        ]
        expanded = []
        for missing, score, chosen, used in beam:
            expanded.append((missing + 1, score, chosen, used))
            for row in options:
                key = _stay_key(row)
                progress = float(row.get("_route_progress_km") or 0)
                if not key or key in used:
                    continue
                offroute = float(row.get("_offroute_km") or 0)
                cost = abs(progress - target) * 0.32 + offroute * 1.2
                expanded.append((missing, score + cost, chosen + [{**row, "_night": night}], used | {key}))
        expanded.sort(key=lambda state: (state[0], state[1]))
        beam = expanded[:48]
    return beam[0][2] if beam else []


def _preloaded_result_stays(result: dict[str, Any], category: str) -> list[dict[str, Any]]:
    """Reuse overnight evidence already paid for during route construction."""
    rows = []
    for item in result.get("accommodations") or []:
        if not isinstance(item, dict):
            continue
        try:
            lat, lon = float(item.get("lat")), float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        raw = _fold(
            f"{item.get('category') or ''} {item.get('type') or ''} "
            f"{item.get('name') or ''}"
        )
        if category == "camping" and not any(token in raw for token in ("camping", "camp site", "camp_site")):
            continue
        if category == "refuge" and not any(token in raw for token in ("refuge", "abri", "gite", "hut")):
            continue
        row = dict(item)
        row["lat"], row["lon"] = lat, lon
        row["category"] = category if category in {"camping", "refuge"} else str(item.get("category") or "lodging")
        rows.append(row)
    return rows


def _logistics_budget_seconds() -> float:
    try:
        value = float(os.getenv("TREKBRAIN_LOGISTICS_BUDGET_SECONDS", "4.0") or 4.0)
    except (TypeError, ValueError):
        value = 4.0
    return max(2.5, min(value, 8.0))


def _structured_stay_hedge_seconds() -> float:
    """Head start for route-wide providers before starting structured Photon."""
    try:
        value = float(os.getenv("TREKBRAIN_STAY_HEDGE_SECONDS", "1.25") or 1.25)
    except (TypeError, ValueError):
        value = 1.25
    return max(0.05, min(value, 2.0))


def _discover_stays(
    v3, roundtrip, stay_rescue, coords, start, category: str,
    days: int, daily_target: float, strict_walk: bool,
    want_terrain: bool = False,
    preloaded_rows: list[dict[str, Any]] | None = None,
    night_anchors: list[dict[str, Any]] | None = None,
):
    started = time.monotonic()
    budget = _logistics_budget_seconds()
    deadline = started + budget
    needed = max(0, days - 1)
    profile = perf.current()

    # A one-day hike has no intermediate night to book. On a terrain-free
    # request, never spend free-provider quotas searching for a stay that cannot
    # be attached to a day. Terrain requests still use the shared OSM pass.
    if needed == 0 and not want_terrain:
        perf.record(
            "logistics.discovery", 0, profile=profile,
            category=category, resolved=0, discovered=0,
            budget_seconds=budget, single_day=True,
        )
        return [], [], {
            "budget_seconds": budget,
            "elapsed_ms": 0,
            "budget_exhausted": False,
            "terrain_rows": [],
            "terrain_preloaded": False,
        }

    def provider_call(metric, func, *args):
        call_started = time.perf_counter()
        outcome = "ok"
        try:
            return func(*args)
        except Exception:
            outcome = "error"
            raise
        finally:
            perf.record(
                metric,
                (time.perf_counter() - call_started) * 1000,
                profile=profile,
                category=category,
                outcome=outcome,
            )

    rows = [dict(x) for x in (preloaded_rows or []) if isinstance(x, dict)]
    max_offroute = (
        3.2 if strict_walk
        else 12.5 if category == "lodging"
        else _MAX_OFFROUTE_KM
    )

    terrain_rows = []
    terrain_preloaded = False

    # A route engine can already have verified every overnight candidate.
    # Project and order those stays against the fixed backbone before opening
    # any redundant lodging provider requests. Terrain remains independent:
    # a requested water/food pass still queries the shared Overpass bundle,
    # but does not re-query Nominatim or Photon for nights we already have.
    if rows:
        preloaded_projected = _project_stays(
            roundtrip, coords, rows, category, max_offroute
        )
        preloaded_chosen = _choose_stays(
            roundtrip, coords, preloaded_projected, days, daily_target, night_anchors
        )
        if len(preloaded_chosen) >= needed:
            if want_terrain:
                try:
                    _extra_stays, terrain_rows, terrain_preloaded = provider_call(
                        "logistics.overpass_bundle", _bbox_route_bundle, coords, category
                    )
                except Exception:
                    terrain_rows, terrain_preloaded = [], False
            elapsed_ms = round((time.monotonic() - started) * 1000)
            perf.record(
                "logistics.discovery", elapsed_ms, profile=profile,
                category=category, resolved=len(preloaded_chosen),
                discovered=len(preloaded_projected), budget_seconds=budget,
                preloaded_complete=True,
            )
            return preloaded_chosen, preloaded_projected, {
                "budget_seconds": budget,
                "elapsed_ms": elapsed_ms,
                "budget_exhausted": time.monotonic() >= deadline,
                "terrain_rows": list(terrain_rows or []),
                "terrain_preloaded": bool(terrain_preloaded),
            }

    # Route-first lodging has two independent route-wide discovery sources:
    # exact-tag Overpass and one bounded Nominatim query. Production profiling
    # showed the public Photon wave repeatedly spending ~2-3 seconds and
    # returning no stays, so keep Photon out of the hot path rather than paying
    # for several per-stage text searches.
    structured = category in {"camping", "refuge"}
    photon_hedge_started = False
    if want_terrain:
        photon_hedge_rows = []
        with ThreadPoolExecutor(max_workers=3 if structured else 2) as pool:
            bbox_future = pool.submit(
                provider_call, "logistics.overpass_bundle",
                _bbox_route_bundle, coords, category
            )
            nominatim_future = pool.submit(
                provider_call, "logistics.nominatim_wave",
                _nominatim_route_stays, coords, category
            )
            photon_future = None

            if structured:
                try:
                    bbox_stays, terrain_rows, terrain_preloaded = bbox_future.result(
                        timeout=_structured_stay_hedge_seconds()
                    )
                except FutureTimeoutError:
                    # Do not wait for a slow public Overpass corridor query to
                    # finish before opening the one Photon rescue wave. Give the
                    # route-wide sources a real head start, then overlap only
                    # their slow tail. This keeps normal provider load low while
                    # shaving the sequential stall seen on Vercors.
                    photon_hedge_started = True
                    photon_future = pool.submit(
                        provider_call,
                        "logistics.photon_hedge",
                        _photon_split_stays,
                        v3,
                        roundtrip,
                        coords,
                        category,
                        days,
                        night_anchors,
                    )
                    try:
                        bbox_stays, terrain_rows, terrain_preloaded = bbox_future.result()
                    except Exception:
                        bbox_stays, terrain_rows, terrain_preloaded = [], [], False
                except Exception:
                    bbox_stays, terrain_rows, terrain_preloaded = [], [], False
            else:
                try:
                    bbox_stays, terrain_rows, terrain_preloaded = bbox_future.result()
                except Exception:
                    bbox_stays, terrain_rows, terrain_preloaded = [], [], False

            try:
                nominatim_stays = nominatim_future.result()
            except Exception:
                nominatim_stays = []

            if photon_future is not None:
                try:
                    photon_hedge_rows = list(photon_future.result() or [])
                except Exception:
                    photon_hedge_rows = []

        rows.extend(list(bbox_stays or []))
        rows.extend(list(nominatim_stays or []))
        rows.extend(photon_hedge_rows)
    elif structured:
        rows.extend(provider_call(
            "logistics.overpass_stays", _bbox_route_stays, coords, category
        ))
        if not rows and deadline - time.monotonic() >= 0.7:
            rows.extend(provider_call(
                "logistics.nominatim_fallback", _nominatim_route_stays, coords, category
            ))
    else:
        rows.extend(provider_call(
            "logistics.nominatim_wave", _nominatim_route_stays, coords, category
        ))

    projected = _project_stays(roundtrip, coords, rows, category, max_offroute)
    chosen = _choose_stays(roundtrip, coords, projected, days, daily_target, night_anchors)

    # Overpass and route-wide Nominatim are the cheap primary sources. If they
    # are both empty/incomplete, allow exactly one bounded Photon stage-anchor
    # wave as a rescue. The jobs inside that wave run concurrently and every
    # candidate is still projected back onto the validated route before use.
    if (
        len(chosen) < needed
        and not photon_hedge_started
        and deadline - time.monotonic() >= 0.9
    ):
        rescued_anchors = night_anchors
        if night_anchors is not None:
            supplied_nights = {int(row.get("_night") or 0) for row in chosen}
            rescued_anchors = [anchor for anchor in night_anchors if anchor["night"] not in supplied_nights]
        rows.extend(provider_call(
            "logistics.photon_fallback",
            _photon_split_stays, v3, roundtrip, coords, category, days, rescued_anchors
        ))
        projected = _project_stays(roundtrip, coords, rows, category, max_offroute)
        chosen = _choose_stays(roundtrip, coords, projected, days, daily_target, night_anchors)

    # For a single generic night, a valid lodging already discovered inside the
    # transfer radius is more useful than reporting "no lodging" merely because
    # it does not sit near the exact geometric midpoint of the loop. Keep the
    # hiking line immutable: downstream connector logic will mark it as a
    # separate transfer whenever it is not a short validated walking link.
    if (
        not chosen
        and int(days) == 2
        and category == "lodging"
        and not strict_walk
        and projected
    ):
        total = float(roundtrip._cumulative(coords)[-1] or 0)
        target = total / 2.0 if total > 0 else float(daily_target)
        chosen = [
            min(
                projected,
                key=lambda row: (
                    abs(float(row.get("_route_progress_km") or 0) - target) * 0.20
                    + float(row.get("_offroute_km") or 0) * 1.0
                ),
            )
        ]

    if len(chosen) < needed and deadline - time.monotonic() >= 0.7:
        # Generic lodging without terrain may still use one exact-tag Overpass
        # route-wide fallback after the Photon rescue. No provider is repeated.
        if not want_terrain and not structured:
            rows.extend(provider_call(
                "logistics.overpass_fallback", _bbox_route_stays, coords, category
            ))
            projected = _project_stays(roundtrip, coords, rows, category, max_offroute)
            chosen = _choose_stays(roundtrip, coords, projected, days, daily_target, night_anchors)

    elapsed_ms = round((time.monotonic() - started) * 1000)
    perf.record(
        "logistics.discovery",
        elapsed_ms,
        profile=profile,
        category=category,
        resolved=len(chosen),
        discovered=len(projected),
        budget_seconds=budget,
    )
    return chosen, projected, {
        "budget_seconds": budget,
        "elapsed_ms": elapsed_ms,
        "budget_exhausted": time.monotonic() >= deadline,
        "terrain_rows": list(terrain_rows or []),
        "terrain_preloaded": bool(terrain_preloaded),
    }


def _connector_key(stay) -> str:
    key = _stay_key(stay)
    return f"{stay['_night']}:{key}" if stay.get("_night") else key


def _connector_anchor(coords, stay):
    if isinstance(stay.get("_anchor"), dict):
        point = stay["_anchor"]
        return [float(point["lat"]), float(point["lon"])]
    index = max(0, min(int(stay.get("_route_index") or 0), len(coords) - 1))
    return [float(coords[index][0]), float(coords[index][1])]


def _matrix_connectors(ors, coords, stays, deadline=None) -> dict[str, dict[str, Any]]:
    """One bounded pedestrian matrix verifies outward AND next-day return.

    Stage-end anchors are independent from the nearest point on the backbone.
    A finite outbound cell alone cannot certify resuming the trek next morning.
    No synthetic distance or geometry is accepted when Matrix falls back.
    """
    if deadline is None:
        deadline = time.monotonic() + _CONNECTOR_BUDGET_SECONDS
    eligible = [
        stay for stay in stays
        if isinstance(stay, dict) and float(stay.get("_anchor_distance_km", stay.get("_offroute_km")) or 0) <= _WALK_CONNECTOR_LIMIT_KM
    ][:_MAX_CONNECTOR_OPTIONS]
    out: dict[str, dict[str, Any]] = {}
    # One call only: even a large POI pool cannot multiply provider charges.
    for chunk in [eligible] if eligible else []:
        points = []
        valid = []
        for stay in chunk:
            try:
                anchor = _connector_anchor(coords, stay)
                points.extend([
                    [float(anchor[0]), float(anchor[1])],
                    [float(stay["lat"]), float(stay["lon"])],
                ])
                valid.append(stay)
            except (KeyError, TypeError, ValueError):
                continue
        if not valid or len(points) != len(valid) * 2:
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            continue
        try:
            bounded_matrix = getattr(ors, "get_distance_matrix_bounded", None)
            if callable(bounded_matrix):
                result = perf.call("logistics.matrix_connector_batch", bounded_matrix,
                                   points, timeout_s=remaining)
            else:
                # Legacy injected fake routers remain usable in offline tests.
                # Production ORS always supplies the bounded HTTP helper above.
                result = perf.call("logistics.matrix_connector_batch", ors.get_distance_matrix, points)
        except Exception:
            result = None
        if time.monotonic() >= deadline:
            continue
        pedestrian = isinstance(result, dict) and (not result.get("profile") or str(result["profile"]).casefold() in {"foot-hiking", "foot-walking", "walking", "pedestrian", "hiking"})
        matrix = result.get("distances") if pedestrian and result.get("fallback") is False else None
        if not isinstance(matrix, list) or len(matrix) != len(points):
            continue
        for index, stay in enumerate(valid):
            try:
                if isinstance(matrix[index * 2][index * 2 + 1], bool) or isinstance(matrix[index * 2 + 1][index * 2], bool):
                    continue
                distance = float(matrix[index * 2][index * 2 + 1])
                back = float(matrix[index * 2 + 1][index * 2])
            except (IndexError, TypeError, ValueError):
                continue
            same_point = _geo_km(stay, {"lat": points[index*2][0], "lon": points[index*2][1]}) <= 0.025
            if all(math.isfinite(value) and (value > 0 or value == 0 and same_point) for value in (distance, back)):
                out[_connector_key(stay)] = {
                    "validated": True,
                    "distance_km": round(distance, 2),
                    "return_distance_km": round(back, 2),
                    "return_validated": True,
                    "routing_mode": "ors-matrix",
                    "geometry_available": False,
                }
    return out


def _connector(ors, legacy_main, roundtrip, coords, stay: dict[str, Any], deadline=None) -> dict[str, Any]:
    if deadline is None:
        deadline = time.monotonic() + _CONNECTOR_BUDGET_SECONDS
    anchor = _connector_anchor(coords, stay)
    destination = [float(stay["lat"]), float(stay["lon"])]
    legs = []
    direction_calls = 0
    failed = {"validated": False, "distance_km": None}
    try:
        for a, b in ((anchor, destination), (destination, anchor)):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or direction_calls >= _MAX_DIRECTION_CALLS:
                return {**failed, "direction_calls": direction_calls}
            bounded_route = getattr(ors, "get_route_direct_bounded", None)
            direction_calls += 1
            if callable(bounded_route):
                routed = perf.call("logistics.walk_connector", bounded_route, [a, b],
                                   legacy_main.distance_gps, timeout_s=remaining)
            else:
                routed = perf.call("logistics.walk_connector", ors.get_route, [a, b], legacy_main.distance_gps)
            if time.monotonic() >= deadline:
                return {**failed, "direction_calls": direction_calls}
            if not isinstance(routed, dict) or routed.get("fallback") is not False:
                return {**failed, "direction_calls": direction_calls}
            if routed.get("profile") and str(routed["profile"]).casefold() not in {"foot-hiking", "foot-walking", "walking", "pedestrian", "hiking"}:
                return {**failed, "direction_calls": direction_calls}
            geometry = routed.get("coords") or []
            distance = float(routed.get("distance") or routed.get("distance_km") or 0)
            if len(geometry) < 2 or not math.isfinite(distance) or distance <= 0:
                return {**failed, "direction_calls": direction_calls}
            clean = [[float(p[0]), float(p[1])] for p in geometry]
            if not all(math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 for lat, lon in clean):
                return {**failed, "direction_calls": direction_calls}
            if any(_geo_km({"lat": p[0], "lon": p[1]}, {"lat": q[0], "lon": q[1]}) > 0.15 for p, q in ((clean[0], a), (clean[-1], b))):
                return {**failed, "direction_calls": direction_calls}
            legs.append({"coords": clean, "distance_km": distance, "routing_mode": routed.get("routing_mode") or "walking"})
    except Exception:
        return {**failed, "direction_calls": direction_calls}
    return {
        "validated": True, "return_validated": True,
        "direction_calls": direction_calls,
        "distance_km": round(legs[0]["distance_km"], 2),
        "return_distance_km": round(legs[1]["distance_km"], 2),
        "routing_mode": legs[0]["routing_mode"],
        "geometry_available": True, "outward": legs[0], "return": legs[1],
    }


def _night_options(anchors, rows, daily_target, *, allow_distant_transfer=False):
    """Build at most four source-backed options per fixed end of stage."""
    window = max(8.0, min(15.0, float(daily_target) * 0.62))
    out = {}
    for anchor in anchors:
        options = []
        for stay in rows:
            gap = abs(float(stay.get("_route_progress_km") or 0) - anchor["route_progress_km"])
            distance = _geo_km(anchor, stay)
            if not math.isfinite(distance):
                continue
            # On intersecting/looped paths a real lodging can sit right at
            # this stage end but its nearest-route projection belongs to a
            # different lap. Don't discard its ACTUAL proximity to this night
            # anchor merely because the progress indices differ. Only ORS
            # pedestrian outward+return links, checked below, can certify it.
            if (gap > window and distance > _WALK_CONNECTOR_LIMIT_KM
                    and not allow_distant_transfer):
                continue
            options.append({**stay, "_night": anchor["night"], "_anchor": dict(anchor),
                            "_anchor_distance_km": distance, "_progress_gap_km": gap})
        options.sort(key=lambda item: (item["_anchor_distance_km"], item["_progress_gap_km"], _stay_key(item)))
        out[anchor["night"]] = options[:4]
    return out


def _validate_night_options(ors, legacy_main, roundtrip, coords, options):
    """Spend one Matrix and at most one two-leg Directions rescue in 4 s.

    Round-robin sampling gives later nights a place in the same bounded matrix.
    Provider timeouts leave access unverified, not a straight-line walking link.
    """
    started = time.monotonic()
    deadline = started + _CONNECTOR_BUDGET_SECONDS
    eligible = []
    for rank in range(4):
        for night in sorted(options):
            if rank < len(options[night]):
                row = options[night][rank]
                if row["_anchor_distance_km"] <= _WALK_CONNECTOR_LIMIT_KM:
                    eligible.append(row)
    eligible = eligible[:_MAX_CONNECTOR_OPTIONS]
    connectors = {}
    matrix_calls = direction_calls = direction_limit = 0

    if eligible and deadline > time.monotonic() and any(callable(getattr(ors, name, None)) for name in ("get_distance_matrix_bounded", "get_distance_matrix")):
        matrix_calls = 1
        # Synchronous transport receives the real remaining HTTP budget. A
        # timed-out worker cannot continue into retries after this stage ends.
        connectors = _matrix_connectors(ors, coords, eligible, deadline) or {}
    pending = [row for row in eligible if _connector_key(row) not in connectors]
    if pending and deadline - time.monotonic() >= 0.2 and any(callable(getattr(ors, name, None)) for name in ("get_route_direct_bounded", "get_route")):
        # One candidate only; two route legs. The other options remain honest
        # unverified candidates when the public router cannot answer in budget.
        direction_limit = _MAX_DIRECTION_CALLS
        row = pending[0]
        connector = _connector(ors, legacy_main, roundtrip, coords, row, deadline)
        direction_calls = int(connector.get("direction_calls") or 0) if connector else 0
        if connector and connector.get("validated"):
            connectors[_connector_key(row)] = connector
    return connectors, {
        "connector_matrix_calls": matrix_calls,
        "connector_direction_calls": direction_calls,
        "connector_direction_calls_max": direction_limit,
        "connector_candidates_checked": len(eligible) if matrix_calls else min(len(eligible), 1 if direction_calls else 0),
        "connector_candidates_verified": len(connectors),
        "connector_budget_seconds": _CONNECTOR_BUDGET_SECONDS,
        "connector_budget_exhausted": time.monotonic() >= deadline,
        "connector_matrix_ms": round((time.monotonic() - started) * 1000),
    }


def _night_access_diagnostics(anchors, projected, options, connectors, assigned):
    """Explain missing walkable nights using existing evidence, no HTTP calls.

    The closest straight-line distance is diagnostic ONLY. It is not a walking
    connector, a suggested transfer, or a guaranteed usable accommodation.
    """
    diagnostics = []
    for anchor in anchors:
        night = int(anchor["night"])
        available = options.get(night, [])
        walk_range = [row for row in available
                      if float(row.get("_anchor_distance_km") or 0) <= _WALK_CONNECTOR_LIMIT_KM]
        verified = [row for row in walk_range
                    if (connectors.get(_connector_key(row)) or {}).get("validated") is True
                    and (connectors.get(_connector_key(row)) or {}).get("return_validated") is True]
        chosen = assigned[night - 1] if night - 1 < len(assigned) else None
        if not projected:
            reason = "no_sourced_accommodation"
        elif not available:
            reason = "no_accommodation_near_stage"
        elif not walk_range:
            reason = "candidates_too_far_for_connector_check"
        elif not verified:
            reason = "walking_connector_unverified"
        elif not chosen or chosen.get("_access_mode") != "walk":
            reason = "candidate_not_compatible_with_daily_limits"
        else:
            reason = "walk_verified"
        distances = [_geo_km(anchor, row) for row in projected]
        nearest = min((distance for distance in distances if math.isfinite(distance)), default=None)
        gaps = [abs(float(row.get("_route_progress_km") or 0)
                    - float(anchor["route_progress_km"])) for row in projected]
        diagnostics.append({
            "night": night,
            "reason": reason,
            "candidate_options": len(available),
            "within_walk_check_radius": len(walk_range),
            "walking_connectors_verified_both_directions": len(verified),
            "nearest_mapped_candidate_straight_km": round(nearest, 2) if nearest is not None else None,
            "nearest_candidate_route_progress_gap_km": round(min(gaps), 2) if gaps else None,
            "distance_is_walking_route": False,
            "night_walk_confirmed": bool(chosen and chosen.get("_access_mode") == "walk"),
        })
    return diagnostics


def _assign_verified_nights(options, connectors, stage_lengths, daily_max, strict_walk):
    """Prefer independently verified walkable stays, allowing a safe base camp.

    Missing nights are explicit slots. Forward and next-morning access effort
    both count against the walking limit; lodging never changes the backbone.
    """
    # missing, transfers, cost, chosen, used, previous return effort
    beam = [(0, 0, 0.0, [], frozenset(), 0.0)]
    for night in range(1, len(stage_lengths)):
        expanded = []
        for missing, transfers, cost, chosen, used, previous_return in beam:
            expanded.append((missing + 1, transfers, cost, chosen + [None], used, 0.0))
            for row in options.get(night, []):
                key = _stay_key(row)
                connector = connectors.get(_connector_key(row)) or {}
                outward = float(connector.get("distance_km") or 0)
                back = float(connector.get("return_distance_km") or 0)
                validated = connector.get("validated") is True and connector.get("return_validated") is True
                walks = (validated and max(outward, back) <= 4.0
                         and stage_lengths[night - 1] + previous_return + outward <= daily_max + 0.01
                         and stage_lengths[night] + back <= daily_max + 0.01)
                reason = ("walk_confirmed" if walks else "access_effort_exceeds_limit" if validated
                          else "walking_access_unverified")
                if strict_walk and not walks:
                    continue
                # Reusing the same accommodation on separate nights is valid
                # for a hub-and-spoke trek only if *each* stage-end anchor has
                # its OWN independently validated outward and return route.
                # A prior night's route must not validate a different night.
                # Never reuse a transfer candidate without confirmed access.
                reused = key in used
                if reused and not walks:
                    continue
                mode = "walk" if walks else "transfer"
                chosen_row = {**row, "_access_mode": mode, "_access_reason": reason, "_connector": connector}
                effort = outward + back if walks else row["_anchor_distance_km"]
                # Prefer an equally walkable distinct stay, but do not mark
                # a correctly validated second night as missing just because
                # the same real campsite is usable again.
                reuse_cost = 1.0 if reused else 0.0
                expanded.append((missing, transfers + (not walks), cost + effort + reuse_cost,
                                 chosen + [chosen_row], used | {key}, back if walks else 0.0))
        expanded.sort(key=lambda state: state[:3])
        beam = expanded[:64]
    return beam[0][3] if beam else []


def _source_aware_stage_plan(
    roundtrip, coords, old_stages, anchors, candidates, days, daily_max,
    resource_rows=None, daily_min=None,
):
    """Rebalance *walking-stage boundaries* near sourced, route-close nights.

    This is a bounded local optimizer on an existing pedestrian backbone.
    The night itself is NEVER inferred walkable from crow-flight proximity:
    independent ORS outward/return connector verification follows unchanged.
    No route geometry, user-day count, provider calls, or endpoints change.
    """
    no_change = {"changed": False, "reason": "no_safe_improvement"}
    if days <= 1 or len(anchors) != days - 1 or len(old_stages) != days:
        return None, no_change
    # Some upstream planners attach stage-specific geometry; never desynchronise
    # that geometry from route-stage boundaries we do not own.
    if any(not isinstance(row, dict) or any(
            key in row for key in ("coords", "geometry", "route_coords",
                                   "route_geometry", "waypoints"))
           for row in old_stages):
        return None, {"changed": False, "reason": "stage_geometry_owned_elsewhere"}
    try:
        cumulative = roundtrip._cumulative(coords)
        total = float(cumulative[-1])
        original = [float(row["distance_km"]) for row in old_stages]
        if not (math.isfinite(total) and total > 0
                and all(math.isfinite(km) and km > 0 for km in original)):
            return None, no_change
    except (KeyError, TypeError, ValueError, IndexError):
        return None, no_change
    reported = sum(original)
    # Only reconcile routes whose existing stage sum is actually consistent
    # with the GPS/ORS backbone. Otherwise keep the original values.
    if abs(reported - total) > max(3.0, total * 0.08):
        return None, {"changed": False, "reason": "route_stage_distance_mismatch"}

    baseline = [float(a["route_progress_km"]) for a in anchors]
    # Candidate nights must have a real external reference and project very
    # close to the *walked* route. Route-projection alone proves no access.
    from .trekbrain_water_evidence_v9 import confirmed_water_reference, has_osm_identity
    from .trekbrain_resources_v9 import _confirmed_food_reference
    terrain = []
    for item in (resource_rows or [])[:100]:
        if not isinstance(item, dict) or not has_osm_identity(item):
            continue
        if not ((item.get("category") == "water" and confirmed_water_reference(item))
                or (item.get("category") == "food" and _confirmed_food_reference(item))):
            continue
        try:
            projection = roundtrip._project_stay_to_route(coords, cumulative, item)
            progress, offroute = float(projection[1]), float(projection[2])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        # A water point near a crossing section of the route can belong to a
        # completely different hiking day. Do not borrow it as night evidence.
        if not math.isfinite(progress) or not math.isfinite(offroute) or offroute > 1.5:
            continue
        terrain.append((item, progress))
    options = []
    for night, centre in enumerate(baseline, 1):
        left = 0.0 if night == 1 else baseline[night - 2]
        right = total if night == days - 1 else baseline[night]
        window = min(5.0, original[night - 1] * 0.27,
                     original[night] * 0.27)
        possible = [(centre, None)]
        if window >= 0.3:
            eligible = []
            for stay in candidates:
                try:
                    progress = float(stay["_route_progress_km"])
                    offroute = float(stay["_offroute_km"])
                except (KeyError, TypeError, ValueError):
                    continue
                if (not math.isfinite(progress) or not math.isfinite(offroute)
                        or offroute > 1.25 or offroute < 0
                        or abs(progress - centre) > window
                        or progress <= left + 2.0 or progress >= right - 2.0
                        or not str(stay.get("source_url") or "").strip()):
                    continue
                eligible.append((progress, stay))
            eligible.sort(key=lambda x: (x[1]["_offroute_km"],
                                          abs(x[0] - centre), _stay_key(x[1])))
            # Max five options per boundary: ≤ 5^N work, pruned with beam.
            possible.extend(eligible[:4])
        options.append(possible)
    if not any(len(group) > 1 for group in options):
        return None, no_change

    # Each state contains (reward, total movement, boundaries, matched stay,
    # previous route progress). Maintain a bounded beam of alternatives.
    beam = [(0.0, 0.0, [], [], 0.0)]
    scale = reported / total
    for index, choices in enumerate(options):
        expanded = []
        for reward, moved, boundaries, selected, previous in beam:
            for progress, stay in choices:
                length = (progress - previous) * scale
                if length < 2.0 or length > daily_max + 0.01:
                    continue
                if daily_min is not None and length < float(daily_min) - 0.01:
                    continue
                if length < min(original[index] * 0.73, 5.0):
                    continue
                motion = abs(progress - baseline[index])
                benefit = (3.0 - min(1.0, float(stay["_offroute_km"]) / 1.25)
                           if stay else 0.0)
                if stay and terrain:
                    # These are source-backed *planning preferences*, not
                    # walking-access validation nor a promise of fresh water.
                    # Prefer ends of stages with actual mapped drinkable water
                    # and groceries, all else being reasonably equal.
                    near = [row for row, water_progress in terrain
                            if abs(water_progress - progress) <= 3.0
                            and _geo_km(stay, row) <= 1.5]
                    benefit += (0.3 if any(row.get("category") == "water"
                                          and confirmed_water_reference(row)
                                          for row in near) else 0.0)
                    benefit += (0.2 if any(row.get("category") == "food"
                                          and _confirmed_food_reference(row)
                                          for row in near) else 0.0)
                score = reward + benefit - motion * 0.12
                expanded.append((score, moved + motion, boundaries + [progress],
                                 selected + [stay], progress))
        expanded.sort(key=lambda row: (-row[0], row[1]))
        beam = expanded[:40]
        if not beam:
            return None, no_change

    candidates_final = []
    for reward, moved, boundaries, selected, previous in beam:
        last_length = (total - previous) * scale
        if last_length < min(original[-1] * 0.73, 5.0) or last_length > daily_max + 0.01:
            continue
        if daily_min is not None and last_length < float(daily_min) - 0.01:
            continue
        if not any(stay is not None for stay in selected):
            continue
        # Candidate positioning is only a heuristic. A connector must be
        # independently checked before declaring a walking overnight.
        lengths = [(b - a) * scale for a, b in zip(
            [0.0] + boundaries, boundaries + [total]
        )]
        if any(abs(new - old) > max(5.0, 0.31 * old)
               for old, new in zip(original, lengths)):
            continue
        candidates_final.append((reward, moved, boundaries, lengths, selected))
    if not candidates_final:
        return None, no_change
    candidates_final.sort(key=lambda row: (-row[0], row[1]))
    reward, moved, boundaries, lengths, selected = candidates_final[0]
    if reward <= 0.05 or moved <= 0.10:
        return None, no_change
    # Preserve the reported distance sum (and avoid artificial extra km).
    lengths[-1] = reported - sum(lengths[:-1])
    return {
        "lengths": lengths, "progress": boundaries,
        "matched_nights": [index for index, stay in enumerate(selected, 1)
                            if stay is not None],
        "movement_km": round(moved, 2),
    }, {"changed": True, "matched_nights": sum(x is not None for x in selected),
         "total_shift_km": round(moved, 2),
         "reason": "sourced_stays_near_existing_walking_line"}


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




def _geo_km(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float:
    try:
        lat1, lon1 = math.radians(float(a["lat"])), math.radians(float(a["lon"]))
        lat2, lon2 = math.radians(float(b["lat"])), math.radians(float(b["lon"]))
    except (KeyError, TypeError, ValueError):
        return float("inf")
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, h))))


def _attach_preloaded_terrain(
    result: dict[str, Any],
    rows: list[dict[str, Any]],
    preloaded: bool,
) -> None:
    if preloaded:
        result["_terrain_osm_preloaded"] = True
    if not rows:
        return

    water = [dict(x) for x in (result.get("water") or []) if isinstance(x, dict)]
    food = [
        dict(x)
        for x in (result.get("resources") or result.get("food") or [])
        if isinstance(x, dict)
    ]
    pois = [dict(x) for x in (result.get("points_of_interest") or []) if isinstance(x, dict)]
    transit = [
        dict(x) for x in rows
        if isinstance(x, dict) and str(x.get("category") or "") == "transit"
    ]

    def coord_key(item):
        try:
            return (round(float(item.get("lat")), 5), round(float(item.get("lon")), 5))
        except (TypeError, ValueError):
            return None

    seen_water = {key for item in water if (key := coord_key(item)) is not None}
    seen_water_sources = {
        str(item.get("source_url") or "")
        for item in water if item.get("source_url")
    }
    seen_food = {key for item in food if (key := coord_key(item)) is not None}
    seen_pois = {key for item in pois if (key := coord_key(item)) is not None}

    for row in rows:
        if not isinstance(row, dict):
            continue
        key = coord_key(row)
        if key is None:
            continue
        kind = str(row.get("category") or "")
        source = str(row.get("source_url") or "")
        if kind == "water" and (key in seen_water or (source and source in seen_water_sources)):
            # Merge the original OSM restriction tags too. Prior to this fix,
            # a later 'access=private' or 'seasonal=yes' point was silently
            # discarded during deduplication and counted as drinking water.
            from .trekbrain_water_evidence_v9 import merge_water_evidence
            for existing in water:
                old_source = str(existing.get("source_url") or "")
                same_source = bool(source and source == old_source)
                if not same_source and coord_key(existing) != key:
                    continue
                if source and old_source and source != old_source:
                    continue
                merge_water_evidence(existing, row)
            continue
        if kind == "water" and key not in seen_water:
            seen_water.add(key)
            if source:
                seen_water_sources.add(source)
            status = str(row.get("water_status") or "unverified")
            water.append({
                "name": row.get("name") or "Point d'eau",
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "category": "water",
                "type": "Point d'eau",
                "status": status,
                "water_status": status,
                "notes": (
                    "Eau signalée non potable : ne pas boire."
                    if status == "not_potable"
                    else "Point d'eau cartographié près du tracé ; disponibilité et potabilité à vérifier."
                ),
                "source_url": row.get("source_url") or "",
                "osm_tags": dict(row.get("osm_tags") or {})
                if isinstance(row.get("osm_tags"), dict) else {},
                "display_only": True,
            })
        elif kind == "food" and key not in seen_food:
            seen_food.add(key)
            food.append({
                "name": row.get("name") or "Ravitaillement",
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "category": "food",
                "type": "Ravitaillement",
                "notes": "Commerce cartographié près du tracé ; horaires et disponibilité à vérifier.",
                "source_url": row.get("source_url") or "",
                "display_only": True,
            })
        elif kind == "transit" and key not in seen_pois:
            seen_pois.add(key)
            pois.append({
                "name": row.get("name") or "Transport public",
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "category": "transit",
                "type": "Transport public",
                "notes": "Accès cartographié près du tracé ; desserte et horaires à vérifier.",
                "source_url": row.get("source_url") or "",
                "display_only": True,
            })

    result["water"] = water
    result["resources"] = food
    result["food"] = food
    result["points_of_interest"] = pois

    if transit:
        transport = result.setdefault("transport", {})
        start = result.get("start") or {}
        end = result.get("end") or {}
        if start:
            nearest = min(transit, key=lambda item: _geo_km(start, item))
            distance = _geo_km(start, nearest)
            if math.isfinite(distance) and distance <= 12.0:
                transport["outbound"] = (
                    f"{nearest.get('name') or 'Transport public'} à environ {distance:.1f} km du départ "
                    "(desserte et horaires à vérifier)."
                )
        if end:
            nearest = min(transit, key=lambda item: _geo_km(end, item))
            distance = _geo_km(end, nearest)
            if math.isfinite(distance) and distance <= 12.0:
                transport["return"] = (
                    f"{nearest.get('name') or 'Transport public'} à environ {distance:.1f} km de l'arrivée "
                    "(desserte et horaires à vérifier)."
                )


def _attach_logistics(result: dict[str, Any], data, legacy_main, v3, roundtrip, stay_rescue, ors, intent, category: str):
    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    if len(coords) < 2 or route.get("fallback") is not False:
        return result

    days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
    daily_target = float(intent.get("daily_target") or getattr(data, "daily_km", 18) or 18)
    from .trekbrain_distance_tolerance_v9 import intent_daily_bounds
    declared_min, declared_max = intent_daily_bounds(intent)
    # A minimum-only request does not forbid a longer walking day. Preserve
    # its real stay access up to the product ceiling instead of declaring an
    # unnecessary transfer based on the parser's inferred partner maximum.
    daily_max = (float(declared_max) if declared_max is not None else 40.0
                 if declared_min is not None else float(intent.get("daily_max") or daily_target * 1.25))
    strict_walk = _strict_walk_request(data)
    start = dict(result.get("start") or {})
    if "lat" not in start or "lon" not in start:
        start = {"name": "Départ", "lat": float(coords[0][0]), "lon": float(coords[0][1])}

    logistics_started = time.monotonic()
    old_stages = list(result.get("stages") or [])
    anchors = _night_anchors(roundtrip, coords, days, old_stages)
    want_terrain = bool(intent.get("water") or intent.get("food"))
    preloaded_stays = _preloaded_result_stays(result, category)
    chosen, discovered, discovery_meta = _discover_stays(
        v3, roundtrip, stay_rescue, coords, start, category, days,
        daily_target, strict_walk, want_terrain=want_terrain,
        preloaded_rows=preloaded_stays,
        night_anchors=anchors,
    )
    _attach_preloaded_terrain(
        result,
        list(discovery_meta.get("terrain_rows") or []),
        bool(discovery_meta.get("terrain_preloaded")),
    )
    total_distance = _route_distance(result, coords, legacy_main)
    if total_distance <= 0:
        return result
    base_per_day = total_distance / max(days, 1)
    stage_lengths = []
    for day in range(days):
        stage = old_stages[day] if day < len(old_stages) and isinstance(old_stages[day], dict) else {}
        try:
            length = float(stage.get("distance_km") or base_per_day)
        except (TypeError, ValueError):
            length = base_per_day
        stage_lengths.append(length if math.isfinite(length) and length > 0 else base_per_day)
    # Include every discovered alternative, not just a proximity-only winner.
    # Discovery may also supply a selected transfer from the two-day rescue.
    pool = _project_stays(roundtrip, coords, list(discovered) + list(chosen), category,
                          3.2 if strict_walk else 12.5 if category == "lodging" else _MAX_OFFROUTE_KM)
    # Shape the DAILY STAGE SPLITS using already discovered, source-linked
    # overnight options. The main pedestrian geometry is unchanged. Preserve
    # the old split when candidates are absent, too far, or incompatible with
    # hard daily limits. ORS will still verify actual walking access below.
    stage_plan, stage_plan_diagnostics = _source_aware_stage_plan(
        roundtrip, coords, old_stages, anchors, pool, days, daily_max,
        daily_min=declared_min,
        resource_rows=(
            [{**row, "category": "water"}
             for row in (result.get("water") or []) if isinstance(row, dict)]
            + [{**row, "category": "food"}
               for row in (result.get("resources") or result.get("food") or [])
               if isinstance(row, dict)]
        ),
    )
    if stage_plan:
        stage_lengths = stage_plan["lengths"]
        anchors = _night_anchors(roundtrip, coords, days, [
            {"distance_km": km} for km in stage_lengths
        ])
    options = _night_options(anchors, pool, daily_target,
                             allow_distant_transfer=days == 2 and category == "lodging" and not strict_walk)
    connector_map, connector_meta = _validate_night_options(ors, legacy_main, roundtrip, coords, options)
    assigned = _assign_verified_nights(options, connector_map, stage_lengths, daily_max, strict_walk)
    night_diagnostics = _night_access_diagnostics(anchors, pool, options, connector_map, assigned)
    by_night = {night: stay for night, stay in enumerate(assigned, 1) if stay is not None}

    logistics_rows = []
    accommodations = []
    for night in range(1, days):
        stay = by_night.get(night)
        if not stay:
            logistics_rows.append({
                "night": night,
                "status": "unresolved",
                "access_mode": "to_arrange",
                "route_anchor": dict(anchors[night - 1]) if night <= len(anchors) else None,
                "reason": "no_verified_walking_stay" if strict_walk and options.get(night) else "no_unique_stay_near_stage_end",
                "action": "Chercher une nuitée sourcée près de cette fin d'étape et faire vérifier sa liaison pédestre avant de partir.",
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
            "route_anchor": dict(stay["_anchor"]),
            "distance_from_stage_end_km": round(stay["_anchor_distance_km"], 2),
            "reason": stay["_access_reason"],
            "booking_status": "to_check",  # A mapped place is never a reservation.
            "transfer_confirmed": False,
        }

        connector = stay.get("_connector") or {}
        connector_km = float(connector.get("distance_km") or 0)
        if stay["_access_mode"] == "walk":
            access["status"] = "confirmed"
            access["access_mode"] = "walk"
            access["access_distance_km"] = round(connector_km, 2)
            access["return_distance_km"] = connector.get("return_distance_km")
            access["walking_connector"] = dict(connector)
            access["action"] = "Vérifier l'ouverture et réserver cette nuitée ; l'aller et le retour pédestres ont été validés."
            access["note"] = "Petite liaison pédestre validée ; reprendre le même point de l'itinéraire principal le lendemain."
        elif strict_walk:
            access["status"] = "unresolved"
            access["access_mode"] = "walk_unverified"
            access["note"] = "La demande impose le tout-à-pied, mais la liaison pédestre vers cette nuitée n'a pas été validée."
            access["action"] = "Faire vérifier une autre nuitée et son accès pédestre sans modifier le tracé principal."
        else:
            access["status"] = "usable_with_transfer"
            access["access_mode"] = "transfer"
            access["note"] = "Hébergement gardé comme logistique séparée ; transfert à organiser et reprise au même point du trek le lendemain."
            access["action"] = "Confirmer et réserver le transfert aller-retour et l'hébergement avant de partir ; aucune desserte n'est encore vérifiée."

        logistics_rows.append(access)
        accommodations.append({
            "name": access["name"],
            "type": (
                "Camping" if category == "camping"
                else "Refuge / gîte" if category == "refuge"
                else "Hébergement"
            ),
            "category": category,
            "lat": access["lat"],
            "lon": access["lon"],
            "source_url": access["source_url"],
            "notes": access["note"],
            "access_mode": access["access_mode"],
            "distance_to_route_km": access["distance_from_route_km"],
        })

    stages = []
    previous_return = 0.0
    for day in range(1, days + 1):
        old = old_stages[day - 1] if day - 1 < len(old_stages) and isinstance(old_stages[day - 1], dict) else {}
        night = next((row for row in logistics_rows if row.get("night") == day), None) if day < days else None
        access_out = float((night or {}).get("access_distance_km") or 0) if (night or {}).get("access_mode") == "walk" else 0.0
        base_distance = stage_lengths[day - 1]
        estimated_effort = base_distance + previous_return + access_out
        if night and night.get("access_mode") == "walk" and estimated_effort > daily_max + 1.0 and not strict_walk:
            night["access_mode"] = "transfer"
            night["status"] = "usable_with_transfer"
            night["note"] = "La liaison à pied rendrait la journée trop longue ; transfert conseillé et reprise au même point du trek le lendemain."
            access_out = 0.0
            estimated_effort = base_distance + previous_return
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
            overnight = f"{night.get('name') or 'Nuitée'} · liaison pédestre {night.get('access_distance_km', 0):.1f} km"
        elif night.get("access_mode") == "transfer":
            overnight = f"{night.get('name') or 'Nuitée'} · transfert conseillé"
        elif night.get("status") == "unresolved":
            overnight = "Nuitée à organiser sans modifier le tracé principal"
        else:
            overnight = f"{night.get('name') or 'Nuitée'} · liaison à vérifier"

        stages.append({
            **old,
            "day": day,
            "name": old.get("name") or f"Jour {day}",
            "title": old.get("title") or f"Jour {day} · itinéraire principal",
            "distance_km": round(base_distance, 2) if stage_plan else old.get("distance_km", round(base_distance, 1)),
            "route_distance_km": round(base_distance, 2) if stage_plan else old.get("route_distance_km", old.get("distance_km", round(base_distance, 1))),
            "stage_anchor": (
                {"lat": anchors[day - 1]["lat"], "lon": anchors[day - 1]["lon"]}
                if stage_plan and day < days else old.get("stage_anchor")
            ),
            "estimated_walking_km_with_access": round(estimated_effort, 1),
            "overnight": overnight,
            "overnight_logistics": night,
        })
        previous_return = float((night or {}).get("return_distance_km") or 0) if (night or {}).get("access_mode") == "walk" else 0.0

    nights_required = max(0, days - 1)
    nights_walk_confirmed = sum(
        row.get("status") == "confirmed" and row.get("access_mode") == "walk"
        for row in logistics_rows
    )
    nights_transfer_required = sum(
        row.get("status") == "usable_with_transfer" and row.get("access_mode") == "transfer"
        for row in logistics_rows
    )
    nights_missing = max(
        0, nights_required - nights_walk_confirmed - nights_transfer_required
    )
    # Keep the existing complete/partial API contract for compatibility.
    # It means a candidate was found, NOT that a multi-day walk is ready
    # without additional transport or campsite arrangements.
    complete = nights_missing == 0
    walking_readiness = (
        "ready_on_foot" if nights_walk_confirmed == nights_required
        else "missing_nights" if nights_missing
        else "transfer_to_arrange"
    )
    result["stages"] = stages
    result["duration_days"] = days
    result["accommodations"] = accommodations
    result["logistics"] = {
        "mode": "route-first",
        "category": category,
        "stage_boundary_optimization": stage_plan_diagnostics,
        "status": "complete" if complete else "partial",
        "route_immutable": True,
        "discovered_candidates": len(discovered),
        "nights_required": nights_required,
        "nights_resolved": nights_walk_confirmed + nights_transfer_required,
        "nights_walk_confirmed": nights_walk_confirmed,
        "nights_transfer_required": nights_transfer_required,
        "nights_missing": nights_missing,
        "walking_readiness": walking_readiness,
        "ready_without_transfer": walking_readiness == "ready_on_foot",
        "strict_walk": strict_walk,
        "nights": logistics_rows,
        "night_diagnostics": night_diagnostics,
        "alternatives": [
            {"night": night, "name": row.get("name"), "lat": row.get("lat"), "lon": row.get("lon"),
             "source_url": row.get("source_url"), "route_anchor": dict(row["_anchor"]),
             "selected": _stay_key(row) == _stay_key(by_night[night]) if night in by_night else False,
             "walking_access_validated": bool((connector_map.get(_connector_key(row)) or {}).get("validated") is True
                                              and (connector_map.get(_connector_key(row)) or {}).get("return_validated") is True),
             "walking_connector": dict(connector_map.get(_connector_key(row)) or {}),
             "booking_status": "to_check", "transfer_confirmed": False}
            for night in sorted(options) for row in options[night]
        ],
        "timing": {
            "discovery_ms": discovery_meta.get("elapsed_ms"),
            "discovery_budget_seconds": discovery_meta.get("budget_seconds"),
            "discovery_budget_exhausted": discovery_meta.get("budget_exhausted"),
            "connector_matrix_hits": len(connector_map),
            **connector_meta,
            "total_ms": round((time.monotonic() - logistics_started) * 1000),
        },
        "principle": "Tracé pédestre inchangé ; découpage des étapes ajustable près des nuitées sourcées, mais accès à pied confirmé uniquement après vérification ORS aller-retour.",
    }
    advisor_notes = result.get("advisor_notes")
    if not isinstance(advisor_notes, list):
        advisor_notes = [str(advisor_notes)] if advisor_notes else []
        result["advisor_notes"] = advisor_notes
    advisor_notes.insert(
        0,
        "🧭 Itinéraire d'abord : TrekBrain a séparé le parcours pédestre des nuitées. Un camping éloigné ne déforme plus le trek ; une petite liaison est ajoutée si elle est validée, sinon un transfert séparé est conseillé.",
    )
    if nights_missing:
        advisor_notes.insert(
            0,
            f"⚠️ Nuitées à organiser : {nights_missing} nuit(s) sans solution d'hébergement utilisable. "
            "Ce trek n'est pas prêt pour un départ avec ces nuitées.",
        )
    if nights_transfer_required:
        advisor_notes.insert(
            0,
            f"⚠️ Transfert à organiser : {nights_transfer_required} nuit(s) ne sont pas "
            "accessibles par une liaison pédestre validée. Le tracé principal "
            "reste à pied, mais le séjour complet n'est pas garanti tout-à-pied.",
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
    "_matrix_connectors",
    "_logistics_budget_seconds",
]
