"""Resilient free deterministic TrekMap planner.

No LLM and no paid AI API. Uses public geodata with multiple fallbacks,
cache, and the existing OpenRouteService integration.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from copy import deepcopy
from typing import Any

import requests
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from . import ors

PLANNER_VERSION = "trekmap-free-planner-v2"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api/"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
USER_AGENT = os.getenv(
    "TREKMAP_USER_AGENT",
    "TrekMap-France/5.0 (+https://trekmap-france.onrender.com)"
)
REFERER = "https://trekmap-france.onrender.com/"
_CACHE: dict[str, tuple[float, Any]] = {}

# Used only as a geocoding fallback. These coordinates are zone centres, never
# advertised as route waypoints by themselves unless no external geocoder works.
KNOWN_CENTRES = {
    "pyrénées": (42.936, -0.143),
    "pyrenees": (42.936, -0.143),
    "alpes": (45.350, 6.350),
    "vercors": (44.970, 5.550),
    "chartreuse": (45.360, 5.780),
    "vosges": (48.060, 7.000),
    "jura": (46.660, 5.900),
    "morvan": (47.180, 4.050),
    "cévennes": (44.280, 3.600),
    "cevennes": (44.280, 3.600),
    "mercantour": (44.140, 7.220),
    "écrins": (44.920, 6.330),
    "ecrins": (44.920, 6.330),
    "queyras": (44.730, 6.800),
    "bauges": (45.650, 6.170),
    "belledonne": (45.220, 6.050),
    "mont blanc": (45.830, 6.865),
    "aubrac": (44.650, 3.000),
    "corse": (42.150, 9.100),
    "auvergne": (45.550, 3.000),
    "sancy": (45.530, 2.820),
    "cantal": (45.050, 2.710),
    "verdon": (43.760, 6.330),
    "vanoise": (45.350, 6.830),
    "beaufortain": (45.690, 6.570),
    "aravis": (45.900, 6.460),
    "bretagne": (48.200, -2.930),
    "normandie": (49.180, 0.000),
    "occitanie": (43.890, 2.000),
    "provence": (43.950, 5.400),
}


class AIPlanRequest(BaseModel):
    # Keep the current API contract so the existing frontend keeps working.
    prompt: str = Field(min_length=8, max_length=4000)
    region: str = Field(default="", max_length=120)
    days: int = Field(default=3, ge=1, le=21)
    daily_km: float = Field(default=18, ge=3, le=40)
    difficulty: str = Field(default="medium", max_length=20)
    route_type: str = Field(default="Boucle", max_length=30)
    require_transit: bool = True
    require_water: bool = True
    require_accommodation: bool = True
    require_food: bool = True
    current_plan: dict[str, Any] | None = None


def _cache_key(url, params=None, data=None):
    return json.dumps(
        {"u": url, "p": params or {}, "d": data or {}},
        sort_keys=True,
        ensure_ascii=False,
    )


def _cache_get(key: str, ttl: int):
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < ttl:
        return deepcopy(cached[1])
    return None


def _cache_put(key: str, value: Any):
    _CACHE[key] = (time.time(), value)
    if len(_CACHE) > 400:
        for old_key, _ in sorted(_CACHE.items(), key=lambda x: x[1][0])[:100]:
            _CACHE.pop(old_key, None)


def _request_json(
    url: str,
    *,
    params=None,
    data=None,
    timeout=20,
    ttl=1800,
    service="service cartographique",
    retries=2,
):
    key = _cache_key(url, params, data)
    cached = _cache_get(key, ttl)
    if cached is not None:
        return cached

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": REFERER,
        "Accept": "application/json",
        "Accept-Language": "fr,en;q=0.7",
    }
    last_error = None
    for attempt in range(max(1, retries)):
        try:
            if data is None:
                response = requests.get(
                    url, params=params, headers=headers, timeout=timeout
                )
            else:
                response = requests.post(
                    url, data=data, headers=headers, timeout=timeout
                )

            if response.status_code == 429:
                last_error = RuntimeError(
                    f"{service} temporairement limité (HTTP 429)."
                )
                time.sleep(min(0.4 * (attempt + 1), 1.2))
                continue

            if response.status_code >= 500:
                last_error = RuntimeError(
                    f"{service} temporairement indisponible (HTTP {response.status_code})."
                )
                time.sleep(min(0.4 * (attempt + 1), 1.2))
                continue

            response.raise_for_status()
            value = response.json()
            _cache_put(key, value)
            return deepcopy(value)

        except requests.Timeout as exc:
            last_error = RuntimeError(f"{service} a dépassé le délai d'attente.")
            last_error.__cause__ = exc
        except requests.ConnectionError as exc:
            last_error = RuntimeError(f"{service} inaccessible depuis le serveur.")
            last_error.__cause__ = exc
        except requests.RequestException as exc:
            last_error = RuntimeError(
                f"{service} indisponible ({exc.__class__.__name__})."
            )
            last_error.__cause__ = exc
        except ValueError as exc:
            raise RuntimeError(f"{service} a renvoyé une réponse JSON invalide.") from exc

        if attempt + 1 < max(1, retries):
            time.sleep(min(0.4 * (attempt + 1), 1.2))

    if last_error:
        raise last_error
    raise RuntimeError(f"{service} indisponible.")


def _dist(a, b):
    lat1, lon1 = map(math.radians, (float(a["lat"]), float(a["lon"])))
    lat2, lon2 = map(math.radians, (float(b["lat"]), float(b["lon"])))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(1 - h, 0)))


def _map_url(lat, lon):
    return (
        f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}"
        f"#map=14/{lat:.6f}/{lon:.6f}"
    )


def _normalise_place(name: str, lat: float, lon: float):
    clean = " ".join(str(name or "").split()) or "Zone recherchée"
    return {
        "name": clean[:300],
        "short_name": clean.split(",")[0].strip(),
        "lat": float(lat),
        "lon": float(lon),
        "category": "place",
        "source_url": _map_url(float(lat), float(lon)),
    }


def _geocode_nominatim(query: str):
    data = _request_json(
        NOMINATIM_URL,
        params={
            "q": query,
            "format": "jsonv2",
            "limit": 5,
            "addressdetails": 1,
            "countrycodes": "fr",
        },
        timeout=12,
        ttl=43200,
        service="Nominatim",
        retries=2,
    )
    out = []
    for row in data if isinstance(data, list) else []:
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(_normalise_place(row.get("display_name") or query, lat, lon))
    return out


def _geocode_photon(query: str):
    data = _request_json(
        PHOTON_URL,
        params={"q": query, "limit": 6, "lang": "fr"},
        timeout=12,
        ttl=43200,
        service="Photon",
        retries=2,
    )
    out = []
    for feature in data.get("features", []) if isinstance(data, dict) else []:
        props = feature.get("properties") or {}
        country_code = str(props.get("countrycode") or props.get("country_code") or "").upper()
        country = str(props.get("country") or "").casefold()
        if country_code and country_code != "FR":
            continue
        if not country_code and country and "france" not in country:
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        pieces = [
            props.get("name"),
            props.get("city"),
            props.get("county"),
            props.get("state"),
            props.get("country"),
        ]
        name = ", ".join(dict.fromkeys(str(x).strip() for x in pieces if x))
        out.append(_normalise_place(name or query, lat, lon))
    return out


def _local_geocode(query: str):
    low = query.casefold()
    for key, (lat, lon) in KNOWN_CENTRES.items():
        if key in low:
            place = _normalise_place(key.title(), lat, lon)
            place["source_url"] = _map_url(lat, lon)
            place["geocode_fallback"] = True
            return [place]
    return []


def _geocode(query: str):
    errors = []
    for provider in (_geocode_nominatim, _geocode_photon):
        try:
            result = provider(query)
            if result:
                return result
        except RuntimeError as exc:
            errors.append(str(exc))
    local = _local_geocode(query)
    if local:
        return local
    if errors:
        raise RuntimeError(
            "Impossible de localiser la zone. "
            + " | ".join(dict.fromkeys(errors))
        )
    return []


FILTERS = {
    "water": [
        '["amenity"="drinking_water"]',
        '["man_made"="water_tap"]',
        '["natural"="spring"]',
    ],
    "camping": [
        '["tourism"="camp_site"]',
        '["tourism"="caravan_site"]',
    ],
    "refuge": [
        '["tourism"="alpine_hut"]',
        '["tourism"="wilderness_hut"]',
        '["amenity"="shelter"]',
    ],
    "food": [
        '["shop"="supermarket"]',
        '["shop"="convenience"]',
        '["shop"="bakery"]',
        '["amenity"="restaurant"]',
        '["amenity"="cafe"]',
    ],
    "transit": [
        '["railway"="station"]',
        '["railway"="halt"]',
        '["highway"="bus_stop"]',
        '["public_transport"="station"]',
    ],
    "viewpoint": [
        '["tourism"="viewpoint"]',
        '["natural"="peak"]',
        '["natural"="waterfall"]',
    ],
}


def _overpass(query: str):
    errors = []
    for url in OVERPASS_URLS:
        try:
            return _request_json(
                url,
                data={"data": query},
                timeout=18,
                ttl=3600,
                service=f"Overpass ({url.split('/')[2]})",
                retries=1,
            )
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError(
        "Les serveurs OpenStreetMap/Overpass sont momentanément injoignables. "
        "Réessaie dans quelques instants. Détails : "
        + " | ".join(dict.fromkeys(errors))
    )


def _nearby(lat, lon, radius_km, categories):
    radius_m = max(800, min(int(radius_km * 1000), 30000))
    clauses = [
        f"nwr(around:{radius_m},{lat},{lon}){flt};"
        for cat in categories
        for flt in FILTERS.get(cat, [])
    ]
    if not clauses:
        return []
    query = "[out:json][timeout:18];(" + "".join(clauses) + ");out center tags 120;"
    data = _overpass(query)
    items, seen = [], set()

    for e in (data.get("elements") or [])[:120]:
        tags = e.get("tags") or {}
        elat, elon = e.get("lat"), e.get("lon")
        if elat is None or elon is None:
            center = e.get("center") or {}
            elat, elon = center.get("lat"), center.get("lon")
        try:
            elat, elon = float(elat), float(elon)
        except (TypeError, ValueError):
            continue

        cat = None
        if (
            tags.get("amenity") == "drinking_water"
            or tags.get("man_made") == "water_tap"
            or tags.get("natural") == "spring"
        ):
            cat = "water"
        elif tags.get("tourism") in {"camp_site", "caravan_site"}:
            cat = "camping"
        elif (
            tags.get("tourism") in {"alpine_hut", "wilderness_hut"}
            or tags.get("amenity") == "shelter"
        ):
            cat = "refuge"
        elif (
            tags.get("railway") in {"station", "halt"}
            or tags.get("highway") == "bus_stop"
            or tags.get("public_transport") == "station"
        ):
            cat = "transit"
        elif (
            tags.get("shop") in {"supermarket", "convenience", "bakery"}
            or tags.get("amenity") in {"restaurant", "cafe"}
        ):
            cat = "food"
        elif tags.get("tourism") == "viewpoint" or tags.get("natural") in {"peak", "waterfall"}:
            cat = "viewpoint"

        if not cat or cat not in categories:
            continue

        identity = (e.get("type"), e.get("id"))
        if identity in seen:
            continue
        seen.add(identity)

        status = "unverified"
        if cat == "water":
            if (
                tags.get("amenity") == "drinking_water"
                or tags.get("drinking_water") == "yes"
            ):
                status = "potable_referenced"
            elif tags.get("drinking_water") == "no":
                status = "not_potable"

        items.append(
            {
                "name": tags.get("name") or tags.get("ref") or f"{cat.title()} OSM",
                "category": cat,
                "lat": elat,
                "lon": elon,
                "source_url": (
                    f"https://www.openstreetmap.org/{e.get('type','node')}/{e.get('id')}"
                    if e.get("id")
                    else _map_url(elat, elon)
                ),
                "water_status": status,
                "opening_hours": tags.get("opening_hours") or "",
            }
        )
    return items


# Photon fallback if every Overpass instance is unreachable. It is deliberately
# modest: enough to still propose real named places, not a replacement for OSM POIs.
PHOTON_TERMS = {
    "camping": ("camping",),
    "refuge": ("refuge", "gîte"),
    "food": ("boulangerie", "supermarché"),
    "transit": ("gare",),
    "viewpoint": ("sommet", "belvédère"),
}


def _photon_category_candidates(location: str, center, categories):
    items, seen = [], set()
    for cat in categories:
        if cat == "water":
            continue
        for term in PHOTON_TERMS.get(cat, ()):
            try:
                results = _geocode_photon(f"{term} {location}")
            except RuntimeError:
                continue
            for place in results[:4]:
                if _dist(center, place) > 35:
                    continue
                key = (round(place["lat"], 5), round(place["lon"], 5), cat)
                if key in seen:
                    continue
                seen.add(key)
                place = dict(place)
                place["category"] = cat
                place["source_url"] = _map_url(place["lat"], place["lon"])
                place["water_status"] = "unverified"
                place["opening_hours"] = ""
                items.append(place)
    return items


KNOWN = [
    "Pyrénées", "Alpes", "Vercors", "Chartreuse", "Vosges", "Jura", "Morvan",
    "Cévennes", "Mercantour", "Écrins", "Ecrins", "Queyras", "Bauges",
    "Belledonne", "Mont Blanc", "Aubrac", "Corse", "Auvergne", "Sancy",
    "Cantal", "Verdon", "Vanoise", "Beaufortain", "Aravis", "Bretagne",
    "Normandie", "Occitanie", "Provence",
]


def _prefs(data):
    text = data.prompt.casefold()
    days = data.days
    daily = float(data.daily_km)
    difficulty = data.difficulty
    route_type = data.route_type or "Boucle"

    m = re.search(r"\b(\d{1,2})\s*(?:jours?|j)\b", text)
    if m:
        days = max(1, min(int(m.group(1)), 21))

    m = re.search(r"\b(\d{1,2}(?:[.,]\d+)?)\s*km\s*(?:/|par\s+)?(?:jour|j)", text)
    if m:
        daily = max(3, min(float(m.group(1).replace(",", ".")), 40))

    if any(k in text for k in ("facile", "tranquille", "accessible")):
        difficulty = "easy"
    if any(k in text for k in ("difficile", "sportif", "sportive")):
        difficulty = "hard"

    if "boucle" in text:
        route_type = "Boucle"
    elif "travers" in text:
        route_type = "Traversée"
    elif "aller-retour" in text or "aller retour" in text:
        route_type = "Aller-retour"

    if data.current_plan and any(k in text for k in ("raccourc", "moins long", "plus court")):
        daily = max(3, daily * 0.8)
    if data.current_plan and any(k in text for k in ("plus long", "allonge")):
        daily = min(40, daily * 1.15)

    prefer = (
        "camping"
        if any(k in text for k in ("camping", "tente", "bivouac"))
        else "refuge"
        if any(k in text for k in ("refuge", "gîte", "gite"))
        else ""
    )

    return {
        "days": days,
        "daily": round(daily, 1),
        "difficulty": difficulty if difficulty in {"easy", "medium", "hard"} else "medium",
        "route_type": route_type,
        "prefer": prefer,
        "transit": data.require_transit or any(k in text for k in ("gare", "train", "bus")),
        "water": data.require_water,
        "sleep": data.require_accommodation,
        "food": data.require_food,
    }


def _location(data):
    if data.region.strip():
        return data.region.strip()
    if data.current_plan and str(data.current_plan.get("region") or "").strip():
        return str(data.current_plan["region"]).strip()
    low = data.prompt.casefold()
    for name in KNOWN:
        if name.casefold() in low:
            return name
    raise HTTPException(
        status_code=400,
        detail="Précise une région, un massif ou une ville dans « Région / massif ».",
    )


def _closest(items, point, max_km=None):
    if not items:
        return None
    item = min(items, key=lambda x: _dist(x, point))
    return item if max_km is None or _dist(item, point) <= max_km else None


def _pick(current, start, candidates, used, prefs, remaining, loop, end):
    target = prefs["daily"] * 0.62
    scored = []
    for item in candidates:
        key = item["source_url"]
        if key in used:
            continue
        d = _dist(current, item)
        if d < 1.2:
            continue
        score = abs(d - target)
        if prefs["prefer"] and item["category"] == prefs["prefer"]:
            score -= 4
        elif item["category"] in {"camping", "refuge"}:
            score -= 2
        elif item["category"] == "viewpoint":
            score -= 1
        goal = start if loop else end
        if goal and remaining:
            excess = _dist(item, goal) - remaining * max(3, prefs["daily"] * 0.72)
            if excess > 0:
                score += excess * 3.5
        scored.append((score, item))
    return min(scored, key=lambda x: x[0])[1] if scored else None


def _route_points(center, groups, prefs):
    transit = groups["transit"]
    stays = groups["camping"] + groups["refuge"]
    views = groups["viewpoint"]
    food = groups["food"]

    start = _closest(transit, center, 12) if prefs["transit"] else None
    start = start or _closest(transit + stays + food, center, 8) or center

    loop = prefs["route_type"].casefold() in {"boucle", "aller-retour", "aller retour"}
    end = start

    if not loop:
        pool = [x for x in transit if _dist(x, start) > 2] or views + stays + food
        if pool:
            end = min(
                pool,
                key=lambda x: abs(
                    _dist(x, start) - prefs["daily"] * prefs["days"] * 0.65
                ),
            )

    candidates = stays + views + food + (transit if prefs["transit"] else [])
    used = {start["source_url"]}
    points = [start]
    current = start

    if prefs["days"] == 1 and loop:
        mid = _pick(start, start, candidates, used, prefs, 1, True, start)
        if not mid:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Pas assez de lieux cartographiques pour construire une boucle ici. "
                    "Essaie une ville, vallée ou massif plus précis."
                ),
            )
        return [start, mid, start], [(0, 2)], start, start

    for i in range(max(0, prefs["days"] - 1)):
        point = _pick(
            current,
            start,
            candidates,
            used,
            prefs,
            prefs["days"] - i - 1,
            loop,
            end,
        )
        if not point:
            break
        points.append(point)
        used.add(point["source_url"])
        current = point

    points.append(start if loop else end)
    return points, [(i, i + 1) for i in range(len(points) - 1)], start, points[-1]


def _near(items, a, b, km=5, limit=2):
    ranked = [(min(_dist(x, a), _dist(x, b)), x) for x in items]
    return [x for d, x in sorted(ranked, key=lambda z: z[0]) if d <= km][:limit]


def _downsample(coords, max_points=2500):
    if len(coords) <= max_points:
        return coords
    step = (len(coords) - 1) / (max_points - 1)
    return [coords[round(i * step)] for i in range(max_points)]


def _build(data, legacy_main):
    prefs = _prefs(data)
    location = _location(data)

    geo = _geocode(f"{location}, France") or _geocode(location)
    if not geo:
        raise HTTPException(
            status_code=422,
            detail=f"Impossible de localiser « {location} ».",
        )
    center = geo[0]

    categories = ["viewpoint"]
    if prefs["water"]:
        categories.append("water")
    if prefs["sleep"]:
        categories += ["camping", "refuge"]
    if prefs["food"]:
        categories.append("food")
    if prefs["transit"]:
        categories.append("transit")

    radius = min(30, max(8, prefs["daily"] * min(prefs["days"], 4) * 0.35))
    degraded_notes = []
    try:
        found = _nearby(center["lat"], center["lon"], radius, categories)
    except RuntimeError as exc:
        degraded_notes.append(str(exc))
        found = _photon_category_candidates(location, center, categories)

    if not found:
        raise HTTPException(
            status_code=503,
            detail=(
                "Les données de lieux sont temporairement indisponibles pour cette zone. "
                "La localisation fonctionne, mais aucun point utile n'a pu être récupéré. "
                "Réessaie dans quelques instants ou indique une ville/vallée plus précise."
            ),
        )

    groups = {k: [] for k in FILTERS}
    for item in found:
        if item["category"] in groups:
            groups[item["category"]].append(item)

    points, sections, start, end = _route_points(center, groups, prefs)
    coords = [[p["lat"], p["lon"]] for p in points]
    route = ors.get_route(coords, legacy_main.distance_gps)
    route_coords = route.get("coords") or coords
    distance = float(route.get("distance") or legacy_main.distance_gps(route_coords))
    elevation = int(legacy_main.elevation_gain(route_coords) or 0)

    weights = []
    for a, b in sections:
        w = sum(_dist(points[i], points[i + 1]) for i in range(a, b))
        weights.append(max(w, 0.05))
    total_weight = sum(weights) or 1

    waters = groups["water"]
    stays = groups["camping"] + groups["refuge"]
    foods = groups["food"]
    views = groups["viewpoint"]
    transit = groups["transit"]

    stages = []
    for day, ((a, b), weight) in enumerate(zip(sections, weights), 1):
        pa, pb = points[a], points[b]
        nearby_water = _near(waters, pa, pb, 5.5)
        nearby_food = _near(foods, pa, pb, 5)
        nearby_views = _near(views, pa, pb, 7)

        overnight = (
            pb["name"]
            if pb.get("category") in {"camping", "refuge"}
            else (_closest(stays, pb, 4) or {}).get("name")
            or ("Fin du trek" if day == len(sections) else "Nuitée non trouvée à proximité")
        )
        water_note = (
            " · ".join(
                f"{x['name']} "
                f"({'potable référencée' if x['water_status']=='potable_referenced' else 'potabilité non confirmée'})"
                for x in nearby_water
            )
            or "Aucun point d'eau OSM trouvé près de cette étape."
        )
        food_note = (
            " · ".join(x["name"] for x in nearby_food)
            or "Aucun ravitaillement OSM trouvé près de cette étape."
        )

        stages.append(
            {
                "day": day,
                "title": f"{pa['name']} → {pb['name']}",
                "from_name": pa["name"],
                "to_name": pb["name"],
                "distance_km": round(distance * weight / total_weight, 1),
                "elevation_gain_m": round(elevation * weight / total_weight),
                "overnight": overnight,
                "water_notes": water_note,
                "food_notes": food_note,
                "highlights": [x["name"] for x in nearby_views],
                "safety_notes": (
                    "Vérifier météo, balisage et fermetures locales avant le départ."
                ),
            }
        )

    outbound_stop = _closest(transit, start, 12)
    return_stop = _closest(transit, end, 12)
    transport = {
        "outbound": (
            f"{outbound_stop['name']} à environ {_dist(start, outbound_stop):.1f} km du départ."
            if outbound_stop
            else "Aucun transport cartographié trouvé près du départ."
        ),
        "return": (
            f"{return_stop['name']} à environ {_dist(end, return_stop):.1f} km de l'arrivée."
            if return_stop
            else "Aucun transport cartographié trouvé près de l'arrivée."
        ),
        "notes": "Horaires non vérifiés en temps réel par le planificateur gratuit.",
    }

    limitations = [
        "Météo, fermetures de sentiers et horaires ne sont pas vérifiés en temps réel.",
        "Les données cartographiques publiques peuvent être incomplètes : confirme hébergements et ravitaillements avant de partir.",
    ]
    limitations += degraded_notes

    if prefs["water"] and not any(
        x["water_status"] == "potable_referenced" for x in waters
    ):
        limitations.append(
            "Aucun point d'eau potable explicitement référencé trouvé dans la zone."
        )

    if len(sections) < prefs["days"]:
        limitations.append(
            f"Seulement {len(sections)} étape(s) distincte(s) ont pu être construites "
            f"sur {prefs['days']} demandées."
        )

    fallback = bool(route.get("fallback"))
    score = (
        100
        - (30 if fallback else 0)
        - (15 if len(sections) < prefs["days"] else 0)
        - (15 if prefs["sleep"] and len(stays) < max(1, len(sections) - 1) else 0)
        - (15 if prefs["transit"] and (not outbound_stop or not return_stop) else 0)
        - (15 if degraded_notes else 0)
    )

    source_items = [start, end] + points[1:-1] + waters[:4] + stays[:4] + transit[:2]
    sources, seen_sources = [], set()
    for item in source_items:
        url = item.get("source_url")
        if url and url not in seen_sources:
            seen_sources.add(url)
            sources.append(
                {
                    "title": item["name"],
                    "url": url,
                    "purpose": item.get("category", "géographie"),
                }
            )
    if not fallback:
        sources.append(
            {
                "title": "OpenRouteService",
                "url": "https://openrouteservice.org/",
                "purpose": "calcul du tracé pédestre",
            }
        )

    pois, seen_pois = [], set()
    for item in points[1:-1] + views + foods + transit:
        key = item.get("source_url")
        if not key or key in seen_pois:
            continue
        seen_pois.add(key)
        pois.append(
            {
                "name": item["name"],
                "type": item.get("category", "point"),
                "lat": item["lat"],
                "lon": item["lon"],
                "source_url": key,
            }
        )
        if len(pois) >= 18:
            break

    water = [
        {
            "name": x["name"],
            "lat": x["lat"],
            "lon": x["lon"],
            "status": x["water_status"],
            "notes": "Donnée cartographique publique ; vérifie sur place.",
            "source_url": x["source_url"],
        }
        for x in waters[:15]
    ]

    accommodations = [
        {
            "name": x["name"],
            "type": "Camping" if x["category"] == "camping" else "Refuge / abri",
            "lat": x["lat"],
            "lon": x["lon"],
            "notes": (
                f"Horaires OSM : {x['opening_hours']}"
                if x.get("opening_hours")
                else "Ouverture et réservation à vérifier."
            ),
            "source_url": x["source_url"],
        }
        for x in stays[:15]
    ]

    return {
        "title": f"{prefs['route_type']} · {center['short_name']}",
        "region": location,
        "summary": (
            "Itinéraire calculé automatiquement à partir de données géographiques "
            f"réelles, avec un objectif d'environ {prefs['daily']:.0f} km/jour."
        ),
        "difficulty": prefs["difficulty"],
        "route_type": prefs["route_type"],
        "best_season": "À vérifier selon météo, neige et ouvertures locales",
        "duration_days": len(stages),
        "start": {
            "name": start["name"],
            "lat": start["lat"],
            "lon": start["lon"],
            "access_note": transport["outbound"],
        },
        "end": {
            "name": end["name"],
            "lat": end["lat"],
            "lon": end["lon"],
            "access_note": transport["return"],
        },
        "waypoints": [
            {
                "name": p["name"],
                "lat": p["lat"],
                "lon": p["lon"],
                "reason": f"Point {p.get('category','utile')} issu de données cartographiques publiques",
            }
            for p in points
        ],
        "stages": stages,
        "points_of_interest": pois,
        "water": water,
        "accommodations": accommodations,
        "transport": transport,
        "confidence": {
            "overall": "Bonne" if score >= 75 else "Moyenne" if score >= 50 else "Limitée",
            "score": max(score, 0),
            "limitations": limitations,
        },
        "sources": sources,
        "route_preview": {
            "coords": _downsample(route_coords),
            "distance_km": round(distance, 2),
            "elevation_gain_m": elevation,
            "fallback": fallback,
            "warning": route.get("warning"),
        },
        "model": PLANNER_VERSION,
    }


def install_free_planner(app, legacy_main):
    @app.get("/ai/status")
    def status():
        return {
            "configured": True,
            "model": PLANNER_VERSION,
            "web_search": False,
            "routing": bool(os.getenv("ORS_API_KEY", "").strip()),
            "cost_per_request": 0,
            "engine": "deterministic-resilient",
            "geocoders": ["Nominatim", "Photon", "local-fallback"],
            "overpass_endpoints": len(OVERPASS_URLS),
        }

    @app.post("/ai/plan")
    def plan(data: AIPlanRequest, user=Depends(legacy_main.current_user)):
        try:
            return _build(data, legacy_main)
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Le planificateur n'a pas pu construire ce trek. "
                    "Essaie une zone plus précise."
                ),
            ) from exc
