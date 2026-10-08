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
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
from copy import deepcopy
from typing import Any

from . import trekbrain_perf_profile_v9 as perf

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
    if (
        tags.get("amenity") == "drinking_water"
        or tags.get("man_made") == "water_tap"
        or tags.get("natural") == "spring"
    ):
        category = "water"
        if tags.get("amenity") == "drinking_water" or tags.get("drinking_water") == "yes":
            status = "potable_referenced"
        elif tags.get("drinking_water") == "no":
            status = "not_potable"
    elif tags.get("shop") in {"supermarket", "convenience", "bakery"}:
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
            '["amenity"="shelter"]',
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
            '["amenity"="shelter"]',
        )

    terrain_filters = (
        '["amenity"="drinking_water"]',
        '["man_made"="water_tap"]',
        '["natural"="spring"]',
        '["shop"="supermarket"]',
        '["shop"="convenience"]',
        '["shop"="bakery"]',
        '["railway"="station"]',
        '["railway"="halt"]',
        '["amenity"="bus_station"]',
        '["amenity"="ferry_terminal"]',
    ) if include_terrain else ()

    clauses = "".join(
        f"nwr{flt}({south:.6f},{west:.6f},{north:.6f},{east:.6f});"
        for flt in (*stay_filters, *terrain_filters)
    )
    query = f"[out:json][timeout:5];({clauses});out center tags {220 if include_terrain else 160};"

    data = None
    mirrors = list(free.OVERPASS_URLS)[:3]

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
    for element in (data.get("elements") or [])[: (220 if include_terrain else 160)]:
        tags = element.get("tags") or {}

        stay_match = False
        if category == "camping":
            stay_match = tags.get("tourism") in {"camp_site", "caravan_site"}
        elif category == "refuge":
            stay_match = (
                tags.get("tourism") in {"alpine_hut", "wilderness_hut"}
                or tags.get("amenity") == "shelter"
            )
        else:
            stay_match = (
                tags.get("tourism") in {
                    "hotel", "hostel", "guest_house", "chalet", "apartment",
                    "camp_site", "alpine_hut", "wilderness_hut",
                }
                or tags.get("amenity") == "shelter"
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
        typ = _fold(row.get("type") or "")
        cls = _fold(row.get("class") or "")
        display = str(row.get("display_name") or row.get("name") or query)
        semantic = _fold(display)
        accepted = False
        actual = category
        if category == "camping":
            accepted = typ in {"camp site", "caravan site"} or "camp" in semantic
        elif category == "refuge":
            accepted = (
                typ in {"alpine hut", "wilderness hut", "shelter"}
                or any(token in semantic for token in ("refuge", "gite", "abri", "hut"))
            )
        else:
            accepted = (
                cls == "tourism"
                and typ in {
                    "hotel", "hostel", "guest house", "chalet", "apartment",
                    "camp site", "alpine hut", "wilderness hut",
                }
            ) or any(token in semantic for token in (
                "hotel", "gite", "auberge", "hostel", "chalet", "camping", "refuge"
            ))
            if "camp" in semantic or typ in {"camp site", "caravan site"}:
                actual = "camping"
            elif "refuge" in semantic or typ in {"alpine hut", "wilderness hut", "shelter"}:
                actual = "refuge"
            else:
                actual = "lodging"
        if not accepted:
            continue
        source = _osm_url({
            "osm_type": row.get("osm_type"),
            "osm_id": row.get("osm_id"),
        })
        out.append({
            "name": display.split(",")[0].strip()[:180] or (
                "Camping" if actual == "camping" else "Refuge" if actual == "refuge" else "Hébergement"
            ),
            "lat": lat,
            "lon": lon,
            "category": actual,
            "source_url": source,
            "osm_tags": {
                "class": row.get("class"),
                "type": row.get("type"),
            },
        })

    deduped, seen = [], set()
    for item in out:
        key = _stay_key(item)
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:_MAX_DISCOVERED]


def _photon_split_stays(v3, roundtrip, coords, category: str, days: int) -> list[dict[str, Any]]:
    """Fast first pass: one bounded Photon lookup around each ideal night split."""
    if days <= 1 or len(coords or []) < 3:
        return []
    lookup = getattr(v3, "_photon_anchor_resource", None)
    if not callable(lookup):
        return []

    anchors = roundtrip._equal_anchors(coords, days)
    if len(anchors) != days - 1:
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
            item = dict(item)
            actual = str(item.get("category") or "")
            if category in {"camping", "refuge"} and actual != category:
                continue
            if category == "lodging" and actual not in {"camping", "refuge", "lodging"}:
                item["category"] = "lodging"
            found.append(item)

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
        item = dict(row)
        item["category"] = category
        try:
            projection = roundtrip._project_stay_to_route(coords, cum, item)
        except Exception:
            projection = None
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
):
    started = time.monotonic()
    budget = _logistics_budget_seconds()
    deadline = started + budget
    needed = max(1, days - 1)
    profile = perf.current()

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
            roundtrip, coords, preloaded_projected, days, daily_target
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
    chosen = _choose_stays(roundtrip, coords, projected, days, daily_target)

    # Overpass and route-wide Nominatim are the cheap primary sources. If they
    # are both empty/incomplete, allow exactly one bounded Photon stage-anchor
    # wave as a rescue. The jobs inside that wave run concurrently and every
    # candidate is still projected back onto the validated route before use.
    if (
        len(chosen) < needed
        and not photon_hedge_started
        and deadline - time.monotonic() >= 0.9
    ):
        rows.extend(provider_call(
            "logistics.photon_fallback",
            _photon_split_stays, v3, roundtrip, coords, category, days
        ))
        projected = _project_stays(roundtrip, coords, rows, category, max_offroute)
        chosen = _choose_stays(roundtrip, coords, projected, days, daily_target)

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
            chosen = _choose_stays(roundtrip, coords, projected, days, daily_target)

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


def _matrix_connectors(ors, coords, stays) -> dict[str, dict[str, Any]]:
    """Validate short stay connectors with real ORS Matrix distances in batches."""
    eligible = [
        stay for stay in stays
        if isinstance(stay, dict) and float(stay.get("_offroute_km") or 0) <= _WALK_CONNECTOR_LIMIT_KM
    ]
    out: dict[str, dict[str, Any]] = {}
    # 10 stays -> 20 Matrix locations, below TrekBrain's 24-location cap.
    for offset in range(0, len(eligible), 10):
        chunk = eligible[offset:offset + 10]
        points = []
        valid = []
        for stay in chunk:
            try:
                index = max(0, min(int(stay.get("_route_index") or 0), len(coords) - 1))
                anchor = coords[index]
                points.extend([
                    [float(anchor[0]), float(anchor[1])],
                    [float(stay["lat"]), float(stay["lon"])],
                ])
                valid.append(stay)
            except (KeyError, TypeError, ValueError):
                continue
        if not valid or len(points) != len(valid) * 2:
            continue
        try:
            result = perf.call(
                "logistics.matrix_connector_batch",
                ors.get_distance_matrix,
                points,
            )
        except Exception:
            result = None
        matrix = result.get("distances") if isinstance(result, dict) else None
        if not isinstance(matrix, list) or len(matrix) != len(points):
            continue
        for index, stay in enumerate(valid):
            try:
                distance = float(matrix[index * 2][index * 2 + 1])
            except (IndexError, TypeError, ValueError):
                continue
            if math.isfinite(distance) and distance > 0:
                out[_stay_key(stay)] = {
                    "validated": True,
                    "distance_km": round(distance, 2),
                    "routing_mode": "ors-matrix",
                }
    return out


def _connector(ors, legacy_main, roundtrip, coords, stay: dict[str, Any]) -> dict[str, Any]:
    index = max(0, min(int(stay.get("_route_index") or 0), len(coords) - 1))
    anchor = coords[index]
    try:
        routed = perf.call(
            "logistics.walk_connector",
            ors.get_route,
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
    seen_food = {key for item in food if (key := coord_key(item)) is not None}
    seen_pois = {key for item in pois if (key := coord_key(item)) is not None}

    for row in rows:
        if not isinstance(row, dict):
            continue
        key = coord_key(row)
        if key is None:
            continue
        kind = str(row.get("category") or "")
        if kind == "water" and key not in seen_water:
            seen_water.add(key)
            status = str(row.get("water_status") or "unverified")
            water.append({
                "name": row.get("name") or "Point d'eau",
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "category": "water",
                "type": "Point d'eau",
                "status": status,
                "water_status": status,
                "notes": "Point d'eau cartographié près du tracé ; disponibilité et potabilité à vérifier.",
                "source_url": row.get("source_url") or "",
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
    daily_max = float(intent.get("daily_max") or daily_target * 1.25)
    strict_walk = _strict_walk_request(data)
    start = dict(result.get("start") or {})
    if "lat" not in start or "lon" not in start:
        start = {"name": "Départ", "lat": float(coords[0][0]), "lon": float(coords[0][1])}

    logistics_started = time.monotonic()
    want_terrain = bool(intent.get("water") or intent.get("food"))
    preloaded_stays = _preloaded_result_stays(result, category)
    chosen, discovered, discovery_meta = _discover_stays(
        v3, roundtrip, stay_rescue, coords, start, category, days,
        daily_target, strict_walk, want_terrain=want_terrain,
        preloaded_rows=preloaded_stays,
    )
    _attach_preloaded_terrain(
        result,
        list(discovery_meta.get("terrain_rows") or []),
        bool(discovery_meta.get("terrain_preloaded")),
    )
    by_night = {index + 1: stay for index, stay in enumerate(chosen[: max(0, days - 1)])}

    matrix_started = time.monotonic()
    connector_map = _matrix_connectors(ors, coords, list(by_night.values()))
    matrix_elapsed_ms = round((time.monotonic() - matrix_started) * 1000)

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
            connector = connector_map.get(_stay_key(stay)) or _connector(
                ors, legacy_main, roundtrip, coords, stay
            )
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
        "timing": {
            "discovery_ms": discovery_meta.get("elapsed_ms"),
            "discovery_budget_seconds": discovery_meta.get("budget_seconds"),
            "discovery_budget_exhausted": discovery_meta.get("budget_exhausted"),
            "connector_matrix_ms": matrix_elapsed_ms,
            "connector_matrix_hits": len(connector_map),
            "total_ms": round((time.monotonic() - logistics_started) * 1000),
        },
        "principle": "Le tracé pédestre est calculé d'abord. Les nuitées sont une logistique secondaire et ne rallongent pas artificiellement l'itinéraire principal.",
    }
    advisor_notes = result.get("advisor_notes")
    if not isinstance(advisor_notes, list):
        advisor_notes = [str(advisor_notes)] if advisor_notes else []
        result["advisor_notes"] = advisor_notes
    advisor_notes.insert(
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
    "_matrix_connectors",
    "_logistics_budget_seconds",
]
