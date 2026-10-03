"""TrekMap expert planner v3.

A zero-cost, hiking-specific planning engine. It does not pretend to be a general
LLM: it parses hiking intent, gathers real geodata, generates competing itinerary
strategies, scores them against the request, and routes the best candidates.
"""
from __future__ import annotations

import math
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException

from . import ors
from .free_planner_v2 import (
    AIPlanRequest,
    _closest,
    _dist,
    _downsample,
    _geocode,
    _location,
    _map_url,
    _near,
    _nearby,
    _overpass,
    _photon_category_candidates,
    _request_json,
    FILTERS as BASE_FILTERS,
    PHOTON_URL,
)

PLANNER_VERSION = "trekmap-expert-planner-v3"
CORRIDOR_SEARCH_VERSION = 1

EXTRA_FILTERS = {
    "lake": [
        '["natural"="water"]["water"~"lake|reservoir|pond"]',
        '["natural"="water"]["name"]',
    ],
    "peak": ['["natural"="peak"]'],
    "waterfall": ['["natural"="waterfall"]'],
    "heritage": [
        '["historic"~"castle|ruins|monument|fort|archaeological_site"]',
        '["tourism"="attraction"]["name"]',
    ],
    "village": ['["place"~"village|town"]'],
    "nature": [
        '["leisure"="nature_reserve"]',
        '["boundary"="protected_area"]["name"]',
    ],
    "trail": ['["route"="hiking"]["name"]'],
}

CATEGORY_LABEL = {
    "viewpoint": "panorama",
    "peak": "sommet",
    "lake": "lac",
    "waterfall": "cascade",
    "nature": "espace naturel",
    "heritage": "patrimoine",
    "village": "village",
    "camping": "camping",
    "refuge": "refuge",
    "lodging": "hébergement",
    "food": "ravitaillement",
    "transit": "transport",
    "trail": "itinéraire balisé",
    "forced": "passage demandé",
}

SCENIC_CATEGORIES = {"viewpoint", "peak", "lake", "waterfall", "nature", "heritage", "village"}


@dataclass
class Candidate:
    boundaries: list[dict[str, Any]]
    strategy: str
    heuristic: float


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _num(raw: str) -> float:
    return float(str(raw).replace(",", "."))


def _phrase_after(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip(" .,-")
            if 1 < len(value) <= 90:
                return value
    return ""


def _parse_intent(data: AIPlanRequest) -> dict[str, Any]:
    original = data.prompt.strip()
    # TrekBrain v9 appends an internal strategy after this marker. Soft
    # priorities may use that context, but hard user constraints must never be
    # inferred from it (e.g. "campings ou refuges" must not become an explicit
    # camping request).
    parts = re.split(
        r"\bpriorit(?:é|e)\s+interne\s+trekbrain\s*:",
        original,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    explicit_original = parts[0].strip()
    text = _fold(original)
    explicit_text = _fold(explicit_original)
    days = int(data.days)
    daily_target = float(data.daily_km)
    daily_min = max(3.0, daily_target * 0.85)
    daily_max = min(40.0, daily_target * 1.15)
    difficulty = data.difficulty if data.difficulty in {"easy", "medium", "hard"} else "medium"
    route_type = data.route_type or "Boucle"

    m = re.search(r"\b(\d{1,2})\s*(?:jours?|j)\b", explicit_text)
    if m:
        days = max(1, min(int(m.group(1)), 21))

    m = re.search(
        r"\b(?:entre\s+)?(\d{1,2}(?:[.,]\d+)?)\s*(?:a|-|jusqu[' ]?a|et)\s*"
        r"(\d{1,2}(?:[.,]\d+)?)\s*km(?:\s*(?:par\s*jour|/\s*j|/\s*jour))?",
        explicit_text,
    )
    if m:
        daily_min, daily_max = sorted((_num(m.group(1)), _num(m.group(2))))
        daily_min = max(3.0, daily_min)
        daily_max = min(40.0, daily_max)
        daily_target = (daily_min + daily_max) / 2
    else:
        m = re.search(r"\b(\d{1,2}(?:[.,]\d+)?)\s*km\s*(?:/|par\s+)?(?:jour|j)\b", explicit_text)
        if m:
            daily_target = max(3.0, min(_num(m.group(1)), 40.0))
            daily_min = max(3.0, daily_target * 0.85)
            daily_max = min(40.0, daily_target * 1.15)

    m = re.search(r"(?:max(?:imum)?|pas\s+plus\s+de|moins\s+de)\s*(\d{1,2}(?:[.,]\d+)?)\s*km(?:\s*(?:par\s*jour|/\s*j|/\s*jour))?", explicit_text)
    if m:
        daily_max = min(40.0, _num(m.group(1)))
        daily_target = min(daily_target, daily_max)
    m = re.search(r"(?:au\s+moins|min(?:imum)?)\s*(\d{1,2}(?:[.,]\d+)?)\s*km(?:\s*(?:par\s*jour|/\s*j|/\s*jour))?", explicit_text)
    if m:
        daily_min = max(3.0, _num(m.group(1)))
        daily_target = max(daily_target, daily_min)

    total_target = None
    m = re.search(r"\b(\d{2,3}(?:[.,]\d+)?)\s*km\s*(?:au\s+total|total(?:ement)?)", explicit_text)
    if m:
        total_target = max(3.0, _num(m.group(1)))
        daily_target = total_target / max(days, 1)
        daily_min = max(3.0, daily_target * 0.82)
        daily_max = min(40.0, daily_target * 1.18)

    max_dplus_day = None
    for pattern in (
        r"(?:max(?:imum)?|pas\s+plus\s+de|moins\s+de)\s*(\d{2,4})\s*m\s*(?:d\+|de\s+denivele)",
        r"(?:denivele|d\+)\s*(?:max(?:imum)?|inferieur\s+a|moins\s+de)?\s*(\d{2,4})\s*m",
    ):
        m = re.search(pattern, explicit_text)
        if m:
            max_dplus_day = max(100, min(int(m.group(1)), 3000))
            break

    loop_negated = bool(re.search(
        r"\b(?:(?:ce\s+)?n[' ]?est\s+pas\s+(?:une?\s+)?boucle|"
        r"pas\s+(?:en\s+|une?\s+)?boucle|sans\s+boucle)\b",
        explicit_text,
    ))
    shape_explicit = False
    if any(k in explicit_text for k in ("aller-retour", "aller retour")):
        route_type = "Aller-retour"
        shape_explicit = True
    elif (
        loop_negated
        or any(k in explicit_text for k in (
            "traversee", "itinerance lineaire", "itineraire lineaire",
            "point a point", "point-a-point",
        ))
    ):
        route_type = "Traversée"
        shape_explicit = True
    elif any(k in explicit_text for k in ("boucle", "circuit")):
        route_type = "Boucle"
        shape_explicit = True
    elif "itinerance" in explicit_text:
        route_type = "Itinérance"
        shape_explicit = True

    if any(k in explicit_text for k in ("facile", "tranquille", "debutant", "peu difficile", "pas difficile", "sans difficulte")):
        difficulty = "easy"
    elif any(k in explicit_text for k in ("difficile", "sportif", "sportive", "soutenu")):
        difficulty = "hard"

    explicit_endpoint_pair = False

    start_query = _phrase_after(
        explicit_original,
        [
            r"(?:départ|depart|partir)\s+(?:de|depuis|à|a)\s+(.+?)(?=\s+(?:et\s+)?(?:arriv(?:ee|ée|e)?|retour|avec|pour|sur|en)\b|[,.;\n]|$)",
            r"(?:commencer|débuter|debuter)\s+(?:à|a|par)\s+(.+?)(?=\s+(?:et\s+)?(?:arriv|retour|avec|pour|sur|en)\b|[,.;\n]|$)",
        ],
    )
    end_query = _phrase_after(
        explicit_original,
        [
            r"(?:arrivée|arrivee|finir|terminer)\s+(?:à|a|au|aux)\s+(.+?)(?=\s+(?:avec|pour|sur|en)\b|[,.;\n]|$)",
        ],
    )
    via_query = _phrase_after(
        explicit_original,
        [
            r"(?:passer|passe|passage)\s+par\s+(.+?)(?=\s+(?:puis|ensuite|avec|pour|sur|en)\b|[,.;\n]|$)",
            r"\bvia\s+(.+?)(?=\s+(?:puis|ensuite|avec|pour|sur|en)\b|[,.;\n]|$)",
        ],
    )

    # Natural point-to-point phrasing often omits the words "départ" and
    # "arrivée": "aller de Tours à Chinon à pied". Treat those endpoints as
    # authoritative geographic anchors instead of keeping a stale form region.
    if not start_query or not end_query:
        pair = re.search(
            r"\b(?:aller|marcher)\s+(?:de|depuis)\s+(.+?)\s+(?:à|a|au|aux)\s+(.+?)"
            r"(?=\s+(?:à|a)\s+pied\b|\s+en\s+\d{1,2}\s*(?:jours?|j)\b|"
            r"\s+(?:avec|sans|pour)\b|[,.;\n]|$)",
            explicit_original,
            flags=re.I,
        )
        if pair:
            explicit_endpoint_pair = True
            if not start_query:
                start_query = re.sub(r"\s+", " ", pair.group(1)).strip(" .,-")
            if not end_query:
                end_query = re.sub(r"\s+", " ", pair.group(2)).strip(" .,-")

    if start_query and end_query and not shape_explicit:
        route_type = "Traversée"

    priorities = {
        "viewpoint": 2.5,
        "peak": 1.8,
        "lake": 2.4,
        "waterfall": 2.0,
        "nature": 1.8,
        "heritage": 0.8,
        "village": 0.6,
    }
    keyword_weights = [
        (("lac", "lacs", "etang"), {"lake": 5.0}),
        (("sommet", "sommets", "pic", "cretes", "crete"), {"peak": 4.8, "viewpoint": 2.0}),
        (("cascade", "cascades"), {"waterfall": 5.0}),
        (("panorama", "panoramas", "vue", "vues", "beau paysage", "beaux paysages"), {"viewpoint": 5.0, "peak": 2.5}),
        (("foret", "sauvage", "nature", "calme"), {"nature": 4.0}),
        (("chateau", "ruines", "patrimoine", "historique", "monument"), {"heritage": 5.0}),
        (("village", "villages", "typique"), {"village": 4.0}),
    ]
    for words, boosts in keyword_weights:
        if any(word in text for word in words):
            priorities.update({k: max(priorities.get(k, 0), v) for k, v in boosts.items()})

    avoid = set()
    negative_rules = {
        "peak": ("sans sommet", "eviter les sommets", "pas de sommet"),
        "village": ("sans village", "eviter les villes", "loin des villes", "pas de ville"),
        "heritage": ("sans patrimoine", "pas de visite"),
    }
    for cat, phrases in negative_rules.items():
        if any(p in explicit_text for p in phrases):
            avoid.add(cat)

    accommodation = "balanced"
    no_bivouac = any(k in explicit_text for k in ("sans bivouac", "pas de bivouac", "eviter le bivouac"))
    no_camping = any(k in explicit_text for k in ("sans camping", "pas de camping", "eviter les campings", "eviter le camping"))
    no_refuge = any(k in explicit_text for k in ("sans refuge", "pas de refuge", "eviter les refuges"))
    if not no_bivouac and any(k in explicit_text for k in ("bivouac", "tente sauvage")):
        accommodation = "bivouac"
    elif not no_camping and any(k in explicit_text for k in ("camping", "campings", "tente")):
        accommodation = "camping"
    elif not no_refuge and any(k in explicit_text for k in ("refuge", "refuges", "gite", "gîte")):
        accommodation = "refuge"

    transit = bool(data.require_transit or any(k in explicit_text for k in ("train", "gare", "bus", "transport en commun")))
    if any(k in explicit_text for k in ("sans train", "sans bus", "sans transport", "voiture uniquement", "pas besoin de transport")):
        transit = False

    water = bool(data.require_water)
    if any(k in explicit_text for k in ("pas besoin de point d'eau", "pas besoin de points d'eau", "sans point d'eau", "sans points d'eau")):
        water = False
    elif any(k in explicit_text for k in ("point d'eau", "points d'eau", "eau potable", "fontaine", "fontaines")):
        water = True

    food = bool(data.require_food)
    if any(k in explicit_text for k in ("sans ravitaillement", "pas besoin de ravitaillement", "sans commerce", "sans commerces")):
        food = False
    elif any(k in explicit_text for k in ("ravitaillement", "epicerie", "épicerie", "boulangerie", "supermarche", "supermarché", "commerce")):
        food = True

    sleep = bool(data.require_accommodation)
    if any(k in explicit_text for k in ("sans hebergement", "sans hébergement", "pas besoin d'hebergement", "pas besoin d'hébergement")):
        sleep = False
    elif any(k in explicit_text for k in ("hebergement", "hébergement", "camping", "refuge", "gite", "gîte", "bivouac")):
        sleep = True

    if data.current_plan:
        if any(k in explicit_text for k in ("plus court", "raccourc", "moins long")):
            daily_target *= 0.82
            daily_min *= 0.82
            daily_max *= 0.86
        if any(k in explicit_text for k in ("plus long", "allonge")):
            daily_target = min(40.0, daily_target * 1.15)
            daily_max = min(40.0, daily_max * 1.15)
        if not start_query and any(k in explicit_text for k in ("garde le depart", "meme depart")):
            start_query = str((data.current_plan.get("start") or {}).get("name") or "")
        if not end_query and any(k in explicit_text for k in ("garde l'arrivee", "meme arrivee")):
            end_query = str((data.current_plan.get("end") or {}).get("name") or "")

    daily_target = max(daily_min, min(daily_target, daily_max))
    total_target = total_target or daily_target * days

    return {
        "days": days,
        "daily_target": round(daily_target, 1),
        "daily_min": round(daily_min, 1),
        "daily_max": round(daily_max, 1),
        "total_target": round(total_target, 1),
        "max_dplus_day": max_dplus_day,
        "difficulty": difficulty,
        "route_type": route_type,
        "start_query": start_query,
        "end_query": end_query,
        "via_query": via_query,
        "explicit_endpoint_pair": explicit_endpoint_pair,
        "priorities": priorities,
        "avoid": avoid,
        "accommodation": accommodation,
        "transit": transit,
        "water": water,
        "food": food,
        "sleep": sleep,
        "raw": explicit_original,
    }


def _extra_nearby(center: dict[str, Any], radius_km: float) -> tuple[list[dict[str, Any]], list[str]]:
    radius_m = max(1000, min(int(radius_km * 1000), 32000))
    clauses = []
    category_for_filter = []
    for cat, filters in EXTRA_FILTERS.items():
        for flt in filters:
            element = "relation" if cat == "trail" else "nwr"
            clauses.append(f"{element}(around:{radius_m},{center['lat']},{center['lon']}){flt};")
            category_for_filter.append(cat)
    query = "[out:json][timeout:20];(" + "".join(clauses) + ");out center tags 180;"
    try:
        data = _overpass(query)
    except RuntimeError as exc:
        return [], [str(exc)]

    items, seen = [], set()
    for e in (data.get("elements") or [])[:180]:
        tags = e.get("tags") or {}
        lat, lon = e.get("lat"), e.get("lon")
        if lat is None or lon is None:
            c = e.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue

        cat = None
        if tags.get("route") == "hiking": cat = "trail"
        elif tags.get("natural") == "peak": cat = "peak"
        elif tags.get("natural") == "waterfall": cat = "waterfall"
        elif tags.get("natural") == "water": cat = "lake"
        elif tags.get("historic") or tags.get("tourism") == "attraction": cat = "heritage"
        elif tags.get("place") in {"village", "town"}: cat = "village"
        elif tags.get("leisure") == "nature_reserve" or tags.get("boundary") == "protected_area": cat = "nature"
        if not cat:
            continue
        identity = (e.get("type"), e.get("id"), cat)
        if identity in seen:
            continue
        seen.add(identity)
        name = tags.get("name") or tags.get("ref")
        if not name and cat not in {"lake", "nature"}:
            continue
        items.append({
            "name": name or CATEGORY_LABEL.get(cat, cat).title(),
            "category": cat,
            "lat": lat,
            "lon": lon,
            "source_url": f"https://www.openstreetmap.org/{e.get('type','node')}/{e.get('id')}" if e.get("id") else _map_url(lat, lon),
            "water_status": "unverified",
            "opening_hours": tags.get("opening_hours") or "",
            "trail_name": tags.get("name") if cat == "trail" else "",
        })
    return items, []



def _combined_nearby(
    center: dict[str, Any],
    radius_km: float,
    base_categories: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Fetch route logistics and scenic context in one Overpass request.

    Historically v9 paid for one broad logistics query and then immediately paid
    for a second scenic/trail query over the same circle. The merged request
    keeps the exact OSM filters and parsing semantics while cutting one network
    round trip from the interactive path.
    """
    radius_m = max(1000, min(int(radius_km * 1000), 30000))
    clauses = []
    for cat in base_categories:
        for flt in BASE_FILTERS.get(cat, []):
            clauses.append(
                f"nwr(around:{radius_m},{center['lat']},{center['lon']}){flt};"
            )
    for cat, filters in EXTRA_FILTERS.items():
        for flt in filters:
            element = "relation" if cat == "trail" else "nwr"
            clauses.append(
                f"{element}(around:{radius_m},{center['lat']},{center['lon']}){flt};"
            )
    if not clauses:
        return [], [], []

    query = "[out:json][timeout:20];(" + "".join(clauses) + ");out center tags 260;"
    data = _overpass(query)

    base_items, extra_items = [], []
    seen_base, seen_extra = set(), set()
    for e in (data.get("elements") or [])[:260]:
        tags = e.get("tags") or {}
        lat, lon = e.get("lat"), e.get("lon")
        if lat is None or lon is None:
            c = e.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue

        base_cat = None
        if (
            tags.get("amenity") == "drinking_water"
            or tags.get("man_made") == "water_tap"
            or tags.get("natural") == "spring"
        ):
            base_cat = "water"
        elif tags.get("tourism") in {"camp_site", "caravan_site"}:
            base_cat = "camping"
        elif (
            tags.get("tourism") in {"alpine_hut", "wilderness_hut"}
            or tags.get("amenity") == "shelter"
        ):
            base_cat = "refuge"
        elif (
            tags.get("railway") in {"station", "halt"}
            or tags.get("highway") == "bus_stop"
            or tags.get("public_transport") == "station"
        ):
            base_cat = "transit"
        elif (
            tags.get("shop") in {"supermarket", "convenience", "bakery"}
            or tags.get("amenity") in {"restaurant", "cafe"}
        ):
            base_cat = "food"
        elif tags.get("tourism") == "viewpoint" or tags.get("natural") in {"peak", "waterfall"}:
            base_cat = "viewpoint"

        identity = (e.get("type"), e.get("id"))
        if base_cat and base_cat in base_categories and identity not in seen_base:
            seen_base.add(identity)
            status = "unverified"
            if base_cat == "water":
                if tags.get("amenity") == "drinking_water" or tags.get("drinking_water") == "yes":
                    status = "potable_referenced"
                elif tags.get("drinking_water") == "no":
                    status = "not_potable"
            base_items.append({
                "name": tags.get("name") or tags.get("ref") or f"{base_cat.title()} OSM",
                "category": base_cat,
                "lat": lat,
                "lon": lon,
                "source_url": (
                    f"https://www.openstreetmap.org/{e.get('type','node')}/{e.get('id')}"
                    if e.get("id") else _map_url(lat, lon)
                ),
                "water_status": status,
                "opening_hours": tags.get("opening_hours") or "",
            })

        extra_cat = None
        if tags.get("route") == "hiking":
            extra_cat = "trail"
        elif tags.get("natural") == "peak":
            extra_cat = "peak"
        elif tags.get("natural") == "waterfall":
            extra_cat = "waterfall"
        elif tags.get("natural") == "water":
            extra_cat = "lake"
        elif tags.get("historic") or tags.get("tourism") == "attraction":
            extra_cat = "heritage"
        elif tags.get("place") in {"village", "town"}:
            extra_cat = "village"
        elif tags.get("leisure") == "nature_reserve" or tags.get("boundary") == "protected_area":
            extra_cat = "nature"

        if extra_cat and identity not in seen_extra:
            name = tags.get("name") or tags.get("ref")
            if name or extra_cat in {"lake", "nature"}:
                seen_extra.add(identity)
                extra_items.append({
                    "name": name or CATEGORY_LABEL.get(extra_cat, extra_cat).title(),
                    "category": extra_cat,
                    "lat": lat,
                    "lon": lon,
                    "source_url": (
                        f"https://www.openstreetmap.org/{e.get('type','node')}/{e.get('id')}"
                        if e.get("id") else _map_url(lat, lon)
                    ),
                    "water_status": "unverified",
                    "opening_hours": tags.get("opening_hours") or "",
                    "trail_name": tags.get("name") if extra_cat == "trail" else "",
                })

    return base_items, extra_items, []


def _geocode_named(
    query: str,
    location: str,
    *,
    standalone_first: bool = False,
) -> dict[str, Any] | None:
    query = re.sub(r"\s+", " ", str(query or "")).strip()
    if not query:
        return None
    if standalone_first:
        attempts = [f"{query}, France", query, f"{query}, {location}, France"]
    else:
        attempts = [f"{query}, {location}, France", f"{query}, France", query]
    for attempt in attempts:
        try:
            found = _geocode(attempt)
        except RuntimeError:
            continue
        if found:
            point = dict(found[0])
            point["category"] = "forced"
            return point
    return None


def _corridor_center(start: dict[str, Any], end: dict[str, Any]) -> dict[str, Any]:
    """Midpoint used for POI discovery on an explicit point-to-point trek."""
    lat = (float(start["lat"]) + float(end["lat"])) / 2.0
    lon = (float(start["lon"]) + float(end["lon"])) / 2.0
    start_name = str(start.get("short_name") or start.get("name") or "Départ")
    end_name = str(end.get("short_name") or end.get("name") or "Arrivée")
    return {
        "name": f"{start_name} → {end_name}",
        "short_name": f"{start_name} → {end_name}",
        "lat": lat,
        "lon": lon,
        "category": "corridor",
        "source_url": "",
    }


def _dedupe(items: list[dict[str, Any]], center: dict[str, Any], max_km: float = 45) -> list[dict[str, Any]]:
    out, seen = [], set()
    for item in items:
        try:
            if _dist(center, item) > max_km:
                continue
        except Exception:
            continue
        key = item.get("source_url") or (round(float(item["lat"]), 5), round(float(item["lon"]), 5), item.get("category"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _bearing(center, point) -> float:
    return math.atan2(float(point["lat"]) - float(center["lat"]), float(point["lon"]) - float(center["lon"]))


def _angle_delta(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def _utility(item: dict[str, Any], intent: dict[str, Any], strategy: str) -> float:
    cat = item.get("category", "")
    if cat in intent["avoid"]:
        return -30.0
    base = float(intent["priorities"].get(cat, 0.0))
    if strategy == "scenic" and cat in SCENIC_CATEGORIES:
        base *= 1.45
    if strategy == "logistics" and cat in {"camping", "refuge", "village", "food", "transit"}:
        base += 2.4
    if intent["accommodation"] == "camping" and cat == "camping":
        base += 5.0
    if intent["accommodation"] == "refuge" and cat == "refuge":
        base += 5.0
    if item.get("name") and not item["name"].lower().endswith(" osm"):
        base += 0.5
    return base


def _choose_start(center, items, intent, forced_start):
    if forced_start:
        return forced_start
    transit = [x for x in items if x.get("category") == "transit"]
    villages = [x for x in items if x.get("category") == "village"]
    stays = [x for x in items if x.get("category") in {"camping", "refuge", "lodging"}]
    if intent["transit"] and transit:
        def transit_score(x):
            name = _fold(x.get("name", ""))
            rail_bonus = -4 if "gare" in name or "station" in name else 0
            return _dist(center, x) + rail_bonus
        return min(transit, key=transit_score)
    return _closest(villages + stays, center, 8) or center


def _choose_end(start, center, items, intent, forced_end):
    loop = _fold(intent["route_type"]) in {"boucle", "aller-retour", "aller retour"}
    if forced_end:
        return forced_end
    if loop:
        return start
    transit = [x for x in items if x.get("category") == "transit" and _dist(x, start) > 3]
    pool = transit if intent["transit"] and transit else [x for x in items if x.get("category") in {"village", "camping", "refuge", "lodging", "viewpoint"} and _dist(x, start) > 3]
    if not pool:
        return center
    wanted = max(5.0, intent["total_target"] * 0.55)
    return min(pool, key=lambda x: abs(_dist(start, x) - wanted) - 0.4 * _utility(x, intent, "balanced"))


def _night_pool(items, intent):
    if intent["accommodation"] == "bivouac":
        return [x for x in items if x.get("category") in SCENIC_CATEGORIES | {"village"}]
    if intent["accommodation"] == "camping":
        preferred = [x for x in items if x.get("category") == "camping"]
    elif intent["accommodation"] == "refuge":
        preferred = [x for x in items if x.get("category") == "refuge"]
    else:
        preferred = [x for x in items if x.get("category") in {"camping", "refuge", "lodging"}]
    fallback = [x for x in items if x.get("category") in {"village", "food"}]
    scenic = [x for x in items if x.get("category") in SCENIC_CATEGORIES]
    if intent["sleep"]:
        return preferred + fallback + scenic
    return scenic + fallback + preferred


def _beam_candidates(start, end, center, items, intent, strategy: str, width: int = 8) -> list[Candidate]:
    days = intent["days"]
    loop = _fold(intent["route_type"]) in {"boucle", "aller-retour", "aller retour"}
    pool = _night_pool(items, intent)
    if days == 1:
        return [Candidate([start, end], strategy, 0.0)]

    # state: boundaries, score, used urls, used categories
    beam = [([start], 0.0, {start.get("source_url")}, set())]
    target_proxy = max(2.5, intent["daily_target"] * 0.62)

    for step in range(1, days):
        expanded = []
        for boundaries, score, used, cats in beam:
            current = boundaries[-1]
            ranked = []
            for item in pool:
                key = item.get("source_url")
                if not key or key in used:
                    continue
                d = _dist(current, item)
                if d < 1.4 or d > intent["daily_max"] * 1.15:
                    continue
                value = abs(d - target_proxy) * 1.7
                value -= _utility(item, intent, strategy) * 2.0
                if item.get("category") not in cats:
                    value -= 1.2

                remaining = days - step
                goal = start if loop else end
                max_reach = max(4.0, remaining * intent["daily_max"] * 0.72)
                excess = _dist(item, goal) - max_reach
                if excess > 0:
                    value += excess * 4.0

                if loop:
                    desired_angle = -math.pi + (2 * math.pi * step / days)
                    value += _angle_delta(_bearing(center, item), desired_angle) * (2.8 if strategy == "scenic" else 1.8)
                    wanted_radius = max(3.0, intent["total_target"] / (2 * math.pi) * 0.55)
                    value += abs(_dist(center, item) - wanted_radius) * 0.45

                if intent["sleep"] and intent["accommodation"] != "bivouac":
                    if item.get("category") not in {"camping", "refuge", "lodging", "village", "food"}:
                        nearby_stay = _closest([x for x in items if x.get("category") in {"camping", "refuge", "lodging"}], item, 3.5)
                        value += 2.0 if nearby_stay else 9.0

                ranked.append((value, item))

            for value, item in sorted(ranked, key=lambda z: z[0])[:12]:
                key = item.get("source_url")
                expanded.append((
                    boundaries + [item],
                    score + value,
                    used | {key},
                    cats | {item.get("category")},
                ))

        if not expanded:
            break
        expanded.sort(key=lambda state: state[1])
        beam = expanded[:width]

    candidates = []
    for boundaries, score, used, cats in beam:
        if boundaries[-1].get("source_url") != end.get("source_url"):
            score += abs(_dist(boundaries[-1], end) - target_proxy) * 1.8
            boundaries = boundaries + [end]
        if len(boundaries) < 2:
            continue
        proxy_total = sum(_dist(a, b) for a, b in zip(boundaries, boundaries[1:]))
        score += abs(proxy_total - intent["total_target"] * 0.62) * 0.8
        candidates.append(Candidate(boundaries, strategy, score))
    return sorted(candidates, key=lambda x: x.heuristic)[:width]


def _best_detour(a, b, items, intent, used, strategy):
    direct = max(_dist(a, b), 0.1)
    choices = []
    for item in items:
        key = item.get("source_url")
        cat = item.get("category")
        if not key or key in used or cat not in SCENIC_CATEGORIES:
            continue
        utility = _utility(item, intent, strategy)
        if utility <= 0:
            continue
        detour = _dist(a, item) + _dist(item, b) - direct
        if detour < 0:
            detour = 0
        if detour > min(8.0, intent["daily_target"] * 0.35):
            continue
        score = utility * 3.2 - detour * 2.2
        choices.append((score, item))
    return max(choices, key=lambda z: z[0])[1] if choices and max(choices, key=lambda z: z[0])[0] > 2 else None


def _route_points_for_candidate(candidate: Candidate, all_items, intent, forced_via):
    boundaries = candidate.boundaries
    route_points = [boundaries[0]]
    used = {boundaries[0].get("source_url")}
    forced_done = not forced_via
    stage_highlights = []

    for a, b in zip(boundaries, boundaries[1:]):
        segment_highlights = []
        inserts = []
        if forced_via and not forced_done:
            detour = _dist(a, forced_via) + _dist(forced_via, b) - _dist(a, b)
            alternatives = [
                _dist(x, forced_via) + _dist(forced_via, y) - _dist(x, y)
                for x, y in zip(boundaries, boundaries[1:])
            ]
            if detour <= min(alternatives) + 0.05:
                inserts.append(forced_via)
                forced_done = True
        scenic = _best_detour(a, b, all_items, intent, used | {x.get("source_url") for x in inserts}, candidate.strategy)
        if scenic:
            inserts.append(scenic)
        inserts.sort(key=lambda x: _dist(a, x))
        for item in inserts:
            route_points.append(item)
            used.add(item.get("source_url"))
            segment_highlights.append(item["name"])
        route_points.append(b)
        used.add(b.get("source_url"))
        stage_highlights.append(segment_highlights)

    if forced_via and not forced_done:
        # Insert at cheapest segment even if it is a larger detour because the user explicitly asked for it.
        best_i = min(
            range(len(route_points) - 1),
            key=lambda i: _dist(route_points[i], forced_via) + _dist(forced_via, route_points[i + 1]) - _dist(route_points[i], route_points[i + 1]),
        )
        route_points.insert(best_i + 1, forced_via)
    return route_points, stage_highlights


_ROUTE_CACHE = {}
_ROUTE_CACHE_ORDER = []
_ROUTE_CACHE_MAX = 256


def _route_cached(points, legacy_main):
    coords = [[round(float(p["lat"]), 6), round(float(p["lon"]), 6)] for p in points]
    key = tuple((p[0], p[1]) for p in coords)
    cached = _ROUTE_CACHE.get(key)
    if cached is not None:
        return dict(cached)
    result = ors.get_route(coords, legacy_main.distance_gps)
    # Cache only validated routes. Unsafe diagnostics should be retried later.
    if not result.get("fallback"):
        _ROUTE_CACHE[key] = dict(result)
        _ROUTE_CACHE_ORDER.append(key)
        if len(_ROUTE_CACHE_ORDER) > _ROUTE_CACHE_MAX:
            old = _ROUTE_CACHE_ORDER.pop(0)
            _ROUTE_CACHE.pop(old, None)
    return result


def _nearest_route_indices(route_coords, boundaries):
    if not route_coords:
        return [0] * len(boundaries)
    indices, floor = [], 0
    for point in boundaries:
        best_i, best_d = floor, float("inf")
        target = {"lat": point["lat"], "lon": point["lon"]}
        for i in range(floor, len(route_coords)):
            rc = {"lat": route_coords[i][0], "lon": route_coords[i][1]}
            d = _dist(target, rc)
            if d < best_d:
                best_i, best_d = i, d
            if i > best_i + 250 and best_d < 0.08:
                break
        indices.append(best_i)
        floor = best_i
    return indices


def _stage_distances(route_coords, boundaries, legacy_main, total_distance):
    if len(boundaries) < 2:
        return []
    idx = _nearest_route_indices(route_coords, boundaries)
    distances = []
    for a, b in zip(idx, idx[1:]):
        segment = route_coords[a:b + 1]
        distances.append(max(0.0, legacy_main.distance_gps(segment)) if len(segment) >= 2 else 0.0)
    measured = sum(distances)
    if measured > 0 and total_distance > 0:
        scale = total_distance / measured
        distances = [d * scale for d in distances]
    elif total_distance > 0:
        distances = [total_distance / max(1, len(boundaries) - 1)] * (len(boundaries) - 1)
    return distances


def _photon_anchor_resource(anchor, category: str, osm_tags, radius_km: float):
    """Fetch one real OSM resource near a validated route anchor via Photon."""
    try:
        lat, lon = float(anchor["lat"]), float(anchor["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None

    # Forward Photon search is more reliable for POI classes than reverse
    # lookup on the public instance. Coordinates only bias ranking; every result
    # is still distance-filtered below before it is accepted.
    tags = list(osm_tags)
    if category == "water":
        query = "fontaine"
    elif category == "transit":
        query = "gare"
    elif category == "food":
        # At the trip start a supermarket is ideal; around an intermediate
        # hiking split, a bakery is substantially more common in small French
        # villages. Keep one query per anchor, just make that query better suited
        # to the anchor instead of opening a second network call.
        anchor_kind = str(anchor.get("category") or "").casefold()
        anchor_name = str(anchor.get("name") or "").casefold()
        query = (
            "boulangerie"
            if anchor_kind == "route_anchor" or "repère jour" in anchor_name or "repere jour" in anchor_name
            else "supermarché"
        )
    elif category == "stay":
        if any(
            token in str(tag)
            for tag in tags
            for token in ("hotel", "hostel", "guest_house", "chalet", "apartment")
        ):
            # Generic trek lodging is usually rural; "gîte" gives Photon a
            # better chance of surfacing guest houses/chalets than an urban-only
            # hotel query. Exact OSM tags are still checked before acceptance.
            query = "gîte"
        elif any("camp_site" in str(tag) for tag in tags):
            query = "camping"
        else:
            query = "refuge"
    else:
        query = "point utile"

    params = {
        "q": query,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "zoom": 11,
        "location_bias_scale": 0.1,
        "countrycode": "FR",
        "limit": 12,
        "lang": "fr",
    }
    try:
        payload = _request_json(
            PHOTON_URL,
            params=params,
            timeout=1.4,
            ttl=21600,
            service="Photon route resources",
            retries=1,
        )
    except Exception:
        return None

    best = None
    for feature in (payload.get("features") or []) if isinstance(payload, dict) else []:
        props = feature.get("properties") or {}
        country_code = str(props.get("countrycode") or props.get("country_code") or "").upper()
        if country_code and country_code != "FR":
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        try:
            flon, flat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        item = {"lat": flat, "lon": flon}
        distance = _dist(anchor, item)
        if distance > float(radius_km) + 0.35:
            continue

        osm_key = str(props.get("osm_key") or "")
        osm_value = str(props.get("osm_value") or "")
        allowed = {
            tuple(str(tag).split(":", 1))
            for tag in tags
            if ":" in str(tag)
        }
        if allowed and (osm_key, osm_value) not in allowed:
            continue
        final_category = category
        if category == "stay":
            if osm_value in {"camp_site", "caravan_site"}:
                final_category = "camping"
            elif osm_value in {"alpine_hut", "wilderness_hut", "shelter"}:
                final_category = "refuge"
            else:
                final_category = "lodging"

        osm_type = str(props.get("osm_type") or "").upper()
        osm_id = props.get("osm_id")
        osm_kind = {"N": "node", "W": "way", "R": "relation"}.get(osm_type, "")
        source_url = (
            f"https://www.openstreetmap.org/{osm_kind}/{osm_id}"
            if osm_kind and osm_id is not None
            else _map_url(flat, flon)
        )

        name_parts = [props.get("name"), props.get("city"), props.get("county")]
        name = ", ".join(dict.fromkeys(str(x).strip() for x in name_parts if x))
        if not name:
            name = {
                "water": "Point d'eau",
                "food": "Ravitaillement",
                "stay": "Hébergement",
                "transit": "Transport public",
            }.get(category, "Point utile")

        row = {
            "name": name[:300],
            "short_name": name.split(",")[0].strip()[:160],
            "lat": flat,
            "lon": flon,
            "category": final_category,
            "source_url": source_url,
            "opening_hours": "",
            "water_status": (
                "potable_referenced"
                if category == "water" and osm_key == "amenity" and osm_value == "drinking_water"
                else "unverified"
            ),
            "_postroute_resource": True,
            "_distance_to_anchor_km": round(distance, 2),
        }
        if best is None or distance < best[0]:
            best = (distance, row)
    return best[1] if best else None


def _postroute_corridor_resources(boundaries, intent, existing_items):
    """Fill missing route logistics after geometry selection, without rerouting."""
    if len(boundaries or []) < 2:
        return []

    existing_items = list(existing_items or [])
    stays = [x for x in existing_items if x.get("category") in {"camping", "refuge", "lodging"}]
    waters = [x for x in existing_items if x.get("category") == "water"]
    foods = [x for x in existing_items if x.get("category") == "food"]
    transit = [x for x in existing_items if x.get("category") == "transit"]

    # Build small route-relative lookup groups, then interleave them. This gives
    # every requested logistics family a chance before the six-call latency cap
    # is reached instead of spending the whole budget on one category.
    transit_jobs, water_jobs, food_jobs, stay_jobs = [], [], [], []
    if intent.get("transit"):
        if _closest(transit, boundaries[0], 12) is None:
            transit_jobs.append((boundaries[0], "transit", (
                "railway:station", "railway:halt", "public_transport:station"
            ), 12.0))
        if _closest(transit, boundaries[-1], 12) is None:
            transit_jobs.append((boundaries[-1], "transit", (
                "railway:station", "railway:halt", "public_transport:station"
            ), 12.0))

    interiors = list(boundaries[1:-1])
    if len(interiors) > 2:
        interiors = [interiors[0], interiors[-1]]

    # Food near the actual start is valuable for resupply and is often much
    # easier to resolve than a shop near a mathematical mountain day split.
    food_anchors = []
    if boundaries:
        food_anchors.append(boundaries[0])
    food_anchors.extend(interiors[:1])

    for boundary in interiors:
        if intent.get("water") and _closest(waters, boundary, 4.5) is None:
            water_jobs.append((boundary, "water", (
                "amenity:drinking_water", "man_made:water_tap", "natural:spring"
            ), 5.5))
        if (
            intent.get("sleep")
            and intent.get("accommodation") != "bivouac"
            and _closest(stays, boundary, 3.5) is None
        ):
            preferred = str(intent.get("accommodation") or "balanced")
            if preferred == "camping":
                tags = ("tourism:camp_site", "tourism:caravan_site")
            elif preferred == "refuge":
                tags = ("tourism:alpine_hut", "tourism:wilderness_hut", "amenity:shelter")
            else:
                tags = (
                    "tourism:camp_site", "tourism:hotel", "tourism:hostel",
                    "tourism:guest_house", "tourism:alpine_hut", "tourism:wilderness_hut"
                )
            stay_jobs.append((boundary, "stay", tags, 8.0))

    for boundary in food_anchors:
        if intent.get("food") and _closest(foods, boundary, 5.0) is None:
            food_jobs.append((boundary, "food", (
                "shop:supermarket", "shop:convenience", "shop:bakery"
            ), 6.5))

    # Prioritise access and overnight logistics when the six-call cap is tight,
    # then food and water. All calls still run in one bounded parallel wave.
    groups = [transit_jobs, stay_jobs, food_jobs, water_jobs]
    jobs = []
    while groups and len(jobs) < 6:
        remaining = []
        for group in groups:
            if group and len(jobs) < 6:
                jobs.append(group.pop(0))
            if group:
                remaining.append(group)
        groups = remaining

    if not jobs:
        return []

    found = []
    with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as pool:
        futures = [
            pool.submit(_photon_anchor_resource, anchor, category, tags, radius)
            for anchor, category, tags, radius in jobs
        ]
        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception:
                item = None
            if item:
                found.append(item)

    deduped, seen = [], set()
    for item in found:
        key = (
            item.get("category"),
            round(float(item.get("lat")), 5),
            round(float(item.get("lon")), 5),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _equal_progress_boundaries(route_coords, start, end, days: int):
    """Place hiking-day boundaries on an already validated route geometry.

    Used only as a recovery for explicit point-to-point treks when POI-based
    stage anchors make one day artificially too long. The walking line itself is
    never redrawn: boundaries are sampled from the existing ORS polyline.
    """
    days = max(1, int(days or 1))
    if days <= 1:
        return [start, end]
    clean = []
    for point in route_coords or []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lat, lon = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)):
            continue
        if not clean or [lat, lon] != clean[-1]:
            clean.append([lat, lon])
    if len(clean) < days + 1:
        return []

    cumulative = [0.0]
    for a, b in zip(clean, clean[1:]):
        cumulative.append(
            cumulative[-1] + _dist(
                {"lat": a[0], "lon": a[1]},
                {"lat": b[0], "lon": b[1]},
            )
        )
    total = cumulative[-1]
    if total <= 0:
        return []

    indices = [0]
    floor = 1
    for day in range(1, days):
        target = total * day / days
        ceiling = len(clean) - (days - day)
        if floor >= ceiling:
            return []
        idx = min(range(floor, ceiling), key=lambda i: abs(cumulative[i] - target))
        indices.append(idx)
        floor = idx + 1
    indices.append(len(clean) - 1)

    boundaries = [dict(start)]
    for day, idx in enumerate(indices[1:-1], start=1):
        point = clean[idx]
        boundaries.append({
            "name": f"Repère jour {day}",
            "category": "route_split",
            "lat": point[0],
            "lon": point[1],
            "source_url": f"route-split:{day}:{point[0]:.5f}:{point[1]:.5f}",
        })
    boundaries.append(dict(end))
    return boundaries


def _route_retrace_ratio(coords):
    """Estimate how much of a route reuses the same corridor.

    Consecutive geometry points are collapsed into ~100 m cells first, so normal
    ORS point density does not look like retracing. A genuine loop should visit
    mostly new cells; an out-and-back route revisits a large share of them.
    """
    cells = []
    for point in coords or []:
        if len(point) < 2:
            continue
        cell = (round(float(point[0]), 3), round(float(point[1]), 3))
        if not cells or cell != cells[-1]:
            cells.append(cell)
    if len(cells) < 12:
        return 0.0
    # Ignore the final return-to-start cell: that is required for a loop.
    body = cells[:-1] if cells[-1] == cells[0] else cells
    if not body:
        return 0.0
    return max(0.0, 1.0 - len(set(body)) / len(body))


def _candidate_score(candidate, route_points, route, intent, items, legacy_main, compute_elevation=False):
    coords = route.get("coords") or [[p["lat"], p["lon"]] for p in route_points]
    distance = float(route.get("distance") or legacy_main.distance_gps(coords))
    stage_dist = _stage_distances(coords, candidate.boundaries, legacy_main, distance)
    score = candidate.heuristic
    score += abs(distance - intent["total_target"]) * 1.8
    for d in stage_dist:
        if d > intent["daily_max"]:
            score += (d - intent["daily_max"]) * 7.0
        elif d < intent["daily_min"] * 0.65:
            score += (intent["daily_min"] * 0.65 - d) * 2.5
        else:
            score += abs(d - intent["daily_target"]) * 0.7
    if route.get("fallback"):
        score += 35

    # Distance per day is a user constraint, not a decorative preference.
    # Reject candidates with a grossly oversized stage instead of merely
    # penalising them and still displaying a 30 km day for a ~20 km request.
    hard_day_max = intent["daily_max"]
    if any(d > hard_day_max + 0.25 for d in stage_dist):
        score += 1000 + sum(max(0.0, d - hard_day_max) for d in stage_dist) * 50

    # A loop must genuinely return to its start and must not collapse into an
    # out-and-back trace. End-point equality is enforced here; GR loop guidance
    # supplies the circular arc itself.
    if _fold(intent.get("route_type") or "") == "boucle":
        if _dist(candidate.boundaries[0], candidate.boundaries[-1]) > 0.35:
            score += 2000
        retrace_ratio = _route_retrace_ratio(coords)
        # Returning to the start is necessary but not sufficient: a 40 km
        # outward leg followed by the same 40 km backwards is an aller-retour,
        # not a loop. Strongly reject heavily retraced geometry.
        if retrace_ratio > 0.32:
            score += 2200 + (retrace_ratio - 0.32) * 3000

    elevation = None
    if compute_elevation or intent["max_dplus_day"]:
        elevation = int(legacy_main.elevation_gain(coords) or 0)
        if intent["max_dplus_day"]:
            max_total = intent["max_dplus_day"] * intent["days"]
            if elevation > max_total:
                score += (elevation - max_total) / 80
    return score, distance, stage_dist, elevation, coords


def _human_understanding(intent, location):
    priorities = sorted(intent["priorities"].items(), key=lambda x: -x[1])
    focus = [CATEGORY_LABEL.get(k, k) for k, v in priorities if v >= 3.5][:3]
    parts = [
        f"{intent['days']} jour{'s' if intent['days'] > 1 else ''}",
        f"{intent['daily_min']:.0f}–{intent['daily_max']:.0f} km/jour",
        intent["route_type"].lower(),
        f"secteur {location}",
    ]
    if focus:
        parts.append("priorité " + ", ".join(focus))
    if intent["accommodation"] != "balanced":
        parts.append(intent["accommodation"])
    if intent["transit"]:
        parts.append("accès transports")
    if intent["max_dplus_day"]:
        parts.append(f"≤ {intent['max_dplus_day']} m D+/jour souhaités")
    return " · ".join(parts)


def _build(data: AIPlanRequest, legacy_main):
    intent = _parse_intent(data)
    location = _location(data)
    standalone_endpoints = bool(intent.get("explicit_endpoint_pair"))

    # Explicit point-to-point requests already require geocoding both written
    # endpoints. Reuse those coordinates as the search centre instead of first
    # geocoding the (usually identical) region field and then geocoding the
    # start again. Non-explicit requests keep the historical region-first path
    # because that context helps disambiguate short place names.
    forced_start = None
    forced_end = None
    corridor_centered = False
    center = None

    if standalone_endpoints:
        forced_start = _geocode_named(
            intent["start_query"], location, standalone_first=True
        )
        forced_end = _geocode_named(
            intent["end_query"], location, standalone_first=True
        )
        if forced_start and forced_end:
            try:
                if _dist(forced_start, forced_end) >= 5.0:
                    center = _corridor_center(forced_start, forced_end)
                    corridor_centered = True
            except Exception:
                corridor_centered = False

    if center is None:
        geo = _geocode(f"{location}, France") or _geocode(location)
        if not geo:
            raise HTTPException(status_code=422, detail=f"Impossible de localiser « {location} ».")
        center = geo[0]

    if forced_start is None:
        forced_start = _geocode_named(
            intent["start_query"], location, standalone_first=standalone_endpoints
        )
    if forced_end is None:
        forced_end = _geocode_named(
            intent["end_query"], location, standalone_first=standalone_endpoints
        )
    forced_via = _geocode_named(intent["via_query"], location)

    if not corridor_centered and forced_start and forced_end:
        try:
            if _dist(forced_start, forced_end) >= 5.0:
                center = _corridor_center(forced_start, forced_end)
                corridor_centered = True
        except Exception:
            corridor_centered = False

    base_categories = ["viewpoint", "water", "camping", "refuge", "food", "transit"]
    radius = min(30.0, max(10.0, intent["daily_target"] * min(intent["days"], 4) * 0.42))
    notes = []
    if corridor_centered and intent.get("explicit_endpoint_pair") and forced_start and forced_end:
        # The two written endpoints are authoritative and already geocoded.
        # A 30 km broad POI scan cannot change their pedestrian backbone, so
        # route first and attach bounded route-relative resources afterwards.
        base, extra = [], []
    else:
        try:
            base, extra, extra_notes = _combined_nearby(center, radius, base_categories)
            notes += extra_notes
        except RuntimeError as exc:
            notes.append(str(exc))
            # For an explicit point-to-point trek the endpoints already define the
            # pedestrian backbone. Do not replace one timed-out broad OSM request by
            # another broad Photon sweep plus a second scenic OSM query. Route first,
            # then use the bounded post-route resource lookup on real day anchors.
            if corridor_centered and forced_start and forced_end:
                base, extra = [], []
            else:
                base = _photon_category_candidates(location, center, base_categories)
                extra = []

    # If a traverse has too little context but the broad OSM query succeeded,
    # one bounded endpoint fallback may add useful POIs. After an OSM timeout,
    # the two authoritative endpoints are enough to route and the post-route
    # resource pass will fill logistics without another broad search.
    if (
        corridor_centered
        and not intent.get("explicit_endpoint_pair")
        and len(base) + len(extra) < 4
        and not notes
    ):
        corridor_fallback = []
        for anchor in (forced_start, forced_end):
            if not anchor:
                continue
            label = str(anchor.get("short_name") or anchor.get("name") or "").strip()
            if not label:
                continue
            try:
                corridor_fallback.extend(
                    _photon_category_candidates(label, anchor, base_categories)
                )
            except Exception:
                continue
        if corridor_fallback:
            base += corridor_fallback
            notes.append("POI du corridor complétés près du départ et de l'arrivée.")

    items = _dedupe(base + extra + [x for x in (forced_start, forced_end, forced_via) if x], center, max_km=max(40, radius * 1.45))
    if len(items) < 4 and not (corridor_centered and forced_start and forced_end and len(items) >= 2):
        raise HTTPException(status_code=503, detail="Pas assez de données géographiques réelles ont pu être récupérées pour construire un trek pertinent dans cette zone.")

    start = _choose_start(center, items, intent, forced_start)
    end = _choose_end(start, center, items, intent, forced_end)

    raw_candidates = []
    for strategy in ("balanced", "scenic", "logistics"):
        raw_candidates += _beam_candidates(start, end, center, items, intent, strategy, width=6)
    unique, candidates = set(), []
    for candidate in sorted(raw_candidates, key=lambda c: c.heuristic):
        key = tuple(round(float(p["lat"]), 5) for p in candidate.boundaries) + tuple(round(float(p["lon"]), 5) for p in candidate.boundaries)
        if key in unique:
            continue
        unique.add(key)
        candidates.append(candidate)
        if len(candidates) >= 10:
            break
    if not candidates:
        non_loop = _fold(intent.get("route_type") or "") not in {"boucle", "aller-retour", "aller retour"}
        if corridor_centered and non_loop and forced_start and forced_end:
            # The endpoints are authoritative. Sparse or unavailable POIs must
            # not prevent routing the real pedestrian backbone; once ORS
            # validates it, the recovery below can split that geometry into the
            # requested hiking days and final resources are attached afterwards.
            candidates = [Candidate([start, end], "corridor-direct", 0.0)]
        else:
            raise HTTPException(status_code=422, detail="Je n'ai pas trouvé de combinaison d'étapes cohérente. Essaie une zone plus précise ou assouplis la distance quotidienne.")

    evaluated = []
    for candidate in candidates[:6]:
        route_points, stage_highlights = _route_points_for_candidate(candidate, items, intent, forced_via)
        route = _route_cached(route_points, legacy_main)
        score, distance, stage_dist, elevation, route_coords = _candidate_score(candidate, route_points, route, intent, items, legacy_main, compute_elevation=False)
        evaluated.append((score, candidate, route_points, stage_highlights, route, distance, stage_dist, route_coords))
    evaluated.sort(key=lambda x: x[0])

    # Do not knowingly return a trek that violates the requested daily mileage.
    # Humans asked for 20 km, not "20 km except when the optimiser feels artistic".
    minimum_total = max(3.0, float(intent["total_target"]) * 0.68)
    acceptable = [
        row for row in evaluated
        if (
            row[6]
            and max(row[6]) <= intent["daily_max"] + 0.25
            and float(row[5]) >= minimum_total
            and (
                _fold(intent.get("route_type") or "") != "boucle"
                or _route_retrace_ratio(row[7]) <= 0.32
            )
        )
    ]
    if acceptable:
        evaluated = acceptable
    elif evaluated:
        # Explicit point-to-point requests already have authoritative endpoints.
        # A good ORS geometry must not be rejected only because sparse corridor
        # POIs created poor stage anchors. Re-split the same validated polyline
        # into equal-progress hiking days, without changing the route.
        recovered = []
        non_loop = _fold(intent.get("route_type") or "") not in {"boucle", "aller-retour", "aller retour"}
        if non_loop and forced_start and forced_end:
            maximum_total = max(
                float(intent["total_target"]) * 1.30,
                float(intent["daily_max"]) * max(1, int(intent["days"])),
            )
            for row in evaluated:
                _score, candidate, route_points, stage_highlights, route, distance, _stage_dist, route_coords = row
                if route.get("fallback") is not False:
                    continue
                if not (minimum_total <= float(distance) <= maximum_total):
                    continue
                boundaries = _equal_progress_boundaries(
                    route_coords, start, end, int(intent["days"])
                )
                if len(boundaries) != int(intent["days"]) + 1:
                    continue
                split_candidate = Candidate(
                    boundaries,
                    f"{candidate.strategy}-route-split",
                    float(candidate.heuristic),
                )
                split_score, split_distance, split_stages, _elev, split_coords = _candidate_score(
                    split_candidate,
                    route_points,
                    route,
                    intent,
                    items,
                    legacy_main,
                    compute_elevation=False,
                )
                if (
                    split_stages
                    and len(split_stages) == int(intent["days"])
                    and max(split_stages) <= float(intent["daily_max"]) + 0.25
                ):
                    recovered.append((
                        split_score,
                        split_candidate,
                        route_points,
                        stage_highlights,
                        route,
                        split_distance,
                        split_stages,
                        split_coords,
                    ))
            if recovered:
                recovered.sort(key=lambda row: row[0])
                evaluated = recovered
        if not recovered:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Je n'ai pas trouvé de tracé réellement compatible avec environ "
                    f"{intent['daily_target']:.0f} km/jour. Je préfère ne pas proposer "
                    "une étape beaucoup trop longue. Élargis légèrement la zone ou la distance quotidienne."
                ),
            )

    # If D+ is an explicit concern, compare elevation of the two best real routes.
    finalists = evaluated[:2] if intent["max_dplus_day"] and len(evaluated) > 1 else evaluated[:1]
    final_rows = []
    for row in finalists:
        _, candidate, route_points, stage_highlights, route, distance, stage_dist, route_coords = row
        score, distance, stage_dist, elevation, route_coords = _candidate_score(candidate, route_points, route, intent, items, legacy_main, compute_elevation=True)
        final_rows.append((score, candidate, route_points, stage_highlights, route, distance, stage_dist, elevation or 0, route_coords))
    final_rows.sort(key=lambda x: x[0])
    score, candidate, route_points, stage_highlights, route, distance, stage_dist, elevation, route_coords = final_rows[0]

    boundaries = candidate.boundaries
    stage_rebalanced = False

    # Once a real walking geometry is validated, day boundaries may move along
    # that exact polyline without changing the trek. Re-split only when doing so
    # materially improves daily balance; no extra router or Web call is needed.
    requested_days = max(1, int(intent.get("days") or 1))
    if (
        route.get("fallback") is False
        and requested_days > 1
        and len(stage_dist) == requested_days
        and len(route_coords or []) >= requested_days + 1
    ):
        target = max(3.0, float(intent.get("daily_target") or 18.0))
        current_dev = sum(abs(float(d) - target) / target for d in stage_dist) / requested_days
        current_worst = max(abs(float(d) - target) / target for d in stage_dist)
        if current_dev > 0.12 or current_worst > 0.25:
            balanced_boundaries = _equal_progress_boundaries(
                route_coords, start, end, requested_days
            )
            if len(balanced_boundaries) == requested_days + 1:
                balanced_dist = _stage_distances(
                    route_coords, balanced_boundaries, legacy_main, distance
                )
                if len(balanced_dist) == requested_days and max(balanced_dist) <= float(intent["daily_max"]) + 0.25:
                    balanced_dev = sum(
                        abs(float(d) - target) / target for d in balanced_dist
                    ) / requested_days
                    if balanced_dev + 0.01 < current_dev:
                        boundaries = balanced_boundaries
                        stage_dist = balanced_dist
                        stage_highlights = [[] for _ in range(requested_days)]
                        stage_rebalanced = True

    # Fill missing route-relative logistics only for explicit traverses. Loops
    # already received their POIs during candidate discovery; another network
    # wave here costs seconds without improving their geometry. Keep the cheap
    # local rebalancing and resource presentation for every route.
    non_loop = _fold(intent.get("route_type") or "") not in {"boucle", "aller-retour", "aller retour"}
    if (
        route.get("fallback") is False
        and corridor_centered and non_loop and forced_start and forced_end
        and any(intent.get(key) for key in ("transit", "water", "food", "sleep"))
    ):
        postroute_items = _postroute_corridor_resources(boundaries, intent, items)
        if postroute_items:
            items = _dedupe(
                items + postroute_items,
                center,
                max_km=max(40, radius * 1.45),
            )

    stays = [x for x in items if x.get("category") in {"camping", "refuge", "lodging"}]
    waters = [x for x in items if x.get("category") == "water"]
    foods = [x for x in items if x.get("category") == "food"]
    transit = [x for x in items if x.get("category") == "transit"]
    scenic = [x for x in items if x.get("category") in SCENIC_CATEGORIES]
    trails = [x for x in items if x.get("category") == "trail"]

    total_elev = int(elevation or 0)
    total_stage_dist = sum(stage_dist) or 1
    stages = []
    for i, (a, b) in enumerate(zip(boundaries, boundaries[1:])):
        d = stage_dist[i] if i < len(stage_dist) else distance / max(1, len(boundaries) - 1)
        elev_i = round(total_elev * d / total_stage_dist) if total_elev else 0
        water_near = _near(waters, a, b, 5.5, 3)
        food_near = _near(foods, a, b, 5.5, 3)
        scenic_near = _near(scenic, a, b, 6.0, 3)
        highlight_names = list(dict.fromkeys((stage_highlights[i] if i < len(stage_highlights) else []) + [x["name"] for x in scenic_near]))[:4]
        overnight = b["name"]
        if i < len(boundaries) - 2 and b.get("category") not in {"camping", "refuge", "lodging", "village", "food"}:
            nearby_stay = _closest(stays, b, 3.5)
            if nearby_stay:
                overnight = nearby_stay["name"]
            elif intent["accommodation"] == "bivouac":
                overnight = "Bivouac envisagé : réglementation locale à vérifier"
            else:
                overnight = "Nuitée à confirmer près de cette fin d'étape"
        water_note = " · ".join(
            f"{x['name']} ({'potable référencée' if x.get('water_status') == 'potable_referenced' else 'potabilité non confirmée'})"
            for x in water_near
        ) or "Aucun point d'eau cartographié trouvé à proximité de l'étape."
        food_note = " · ".join(x["name"] for x in food_near) or "Aucun ravitaillement cartographié proche de l'étape."
        safety = []
        if d > intent["daily_max"]:
            safety.append(f"Étape plus longue que les {intent['daily_max']:.0f} km/jour demandés.")
        if intent["max_dplus_day"] and elev_i > intent["max_dplus_day"]:
            safety.append(f"D+ estimé supérieur à l'objectif de {intent['max_dplus_day']} m/jour.")
        if not water_near and intent["water"]:
            safety.append("Prévoir une autonomie en eau suffisante et vérifier les sources locales.")
        stages.append({
            "day": i + 1,
            "title": f"{a['name']} → {b['name']}",
            "from_name": a["name"],
            "to_name": b["name"],
            "distance_km": round(d, 1),
            "elevation_gain_m": int(elev_i),
            "overnight": overnight if i < len(boundaries) - 2 else "Fin du trek",
            "water_notes": water_note,
            "food_notes": food_note,
            "highlights": highlight_names,
            "safety_notes": " ".join(safety) or "Étape cohérente avec les contraintes principales ; météo et état du sentier restent à vérifier.",
        })

    outbound = _closest(transit, start, 12)
    inbound = _closest(transit, end, 12)
    transport = {
        "outbound": f"{outbound['name']} à environ {_dist(start, outbound):.1f} km du départ." if outbound else "Aucun arrêt ou gare cartographié trouvé près du départ.",
        "return": f"{inbound['name']} à environ {_dist(end, inbound):.1f} km de l'arrivée." if inbound else "Aucun arrêt ou gare cartographié trouvé près de l'arrivée.",
        "notes": "Le moteur choisit les accès géographiques ; les horaires doivent être vérifiés avant le départ.",
    }

    preferred_focus = [CATEGORY_LABEL.get(k, k) for k, v in sorted(intent["priorities"].items(), key=lambda x: -x[1]) if v >= 3.5][:3]
    advisor_notes = [
        f"J'ai comparé {len(evaluated)} scénarios réels ({', '.join(x[1].strategy for x in evaluated)}) et retenu la version « {candidate.strategy} ».",
        f"Le tracé retenu fait {distance:.1f} km pour {len(stages)} jour(s), soit environ {distance/max(len(stages),1):.1f} km/jour.",
    ]
    if preferred_focus:
        advisor_notes.append("J'ai privilégié les " + ", ".join(preferred_focus) + " demandés dans ta requête.")
    if intent["transit"]:
        advisor_notes.append("Le départ et l'arrivée ont été évalués en tenant compte des transports cartographiés.")
    if trails:
        advisor_notes.append("Des itinéraires de randonnée nommés sont présents dans le secteur, notamment : " + ", ".join(dict.fromkeys(x["name"] for x in trails[:3])) + ".")

    limitations = [
        "Le moteur comprend des contraintes de randonnée, mais ce n'est pas un modèle de langage généraliste : les formulations très ambiguës peuvent être mal interprétées.",
        "Météo, fermetures, réglementation de bivouac et horaires de transport ne sont pas vérifiés en temps réel.",
        "Les points d'eau sans mention explicite de potabilité doivent être considérés comme non vérifiés.",
    ] + notes
    if intent["sleep"] and intent["accommodation"] != "bivouac" and len(stays) < max(1, len(stages) - 1):
        limitations.append("Le secteur ne contient pas assez d'hébergements cartographiés pour garantir une nuitée à chaque étape.")
    if route.get("fallback"):
        limitations.append("OpenRouteService n'a pas fourni le tracé complet : l'aperçu utilise un routage dégradé.")

    confidence_score = 92
    confidence_score -= 30 if route.get("fallback") else 0
    confidence_score -= 12 if notes else 0
    confidence_score -= 10 if any(s["distance_km"] > intent["daily_max"] for s in stages) else 0
    confidence_score -= 10 if intent["transit"] and (not outbound or not inbound) else 0
    confidence_score = max(20, min(confidence_score, 96))

    source_items = route_points + waters[:5] + foods[:5] + stays[:5] + transit[:3] + trails[:3]
    sources, seen = [], set()
    for item in source_items:
        url = item.get("source_url")
        if not url or url in seen:
            continue
        seen.add(url)
        sources.append({"title": item["name"], "url": url, "purpose": CATEGORY_LABEL.get(item.get("category"), item.get("category", "géographie"))})
    if not route.get("fallback"):
        sources.append({"title": "OpenRouteService", "url": "https://openrouteservice.org/", "purpose": "calcul du tracé pédestre"})

    pois, seen_poi = [], set()
    for item in route_points[1:-1] + scenic + trails + foods + transit:
        key = item.get("source_url")
        if not key or key in seen_poi:
            continue
        seen_poi.add(key)
        pois.append({"name": item["name"], "type": CATEGORY_LABEL.get(item.get("category"), item.get("category", "point")), "lat": item["lat"], "lon": item["lon"], "source_url": key})
        if len(pois) >= 24:
            break

    water = [{
        "name": x["name"], "lat": x["lat"], "lon": x["lon"],
        "status": x.get("water_status", "unverified"),
        "notes": "Potabilité à confirmer sur place sauf mention explicite.",
        "source_url": x["source_url"],
    } for x in waters[:18]]
    accommodations = [{
        "name": x["name"], "type": (
            "Camping" if x.get("category") == "camping"
            else "Refuge / abri" if x.get("category") == "refuge"
            else "Hébergement"
        ),
        "lat": x["lat"], "lon": x["lon"],
        "notes": f"Horaires cartographiés : {x['opening_hours']}" if x.get("opening_hours") else "Ouverture et réservation à vérifier.",
        "source_url": x["source_url"],
    } for x in stays[:18]]
    resources = [{
        "name": x["name"], "type": "Ravitaillement", "category": "food",
        "lat": x["lat"], "lon": x["lon"],
        "notes": f"Horaires cartographiés : {x['opening_hours']}" if x.get("opening_hours") else "Horaires et disponibilité à vérifier.",
        "source_url": x["source_url"],
    } for x in foods[:18]]

    understood = _human_understanding(intent, location)
    title_focus = next((x["name"] for x in route_points[1:-1] if x.get("category") in SCENIC_CATEGORIES and x.get("name")), center["short_name"])
    summary = f"Trek conseillé après comparaison de plusieurs scénarios. {advisor_notes[1]}" + (f" Point fort : {title_focus}." if title_focus else "")

    return {
        "title": f"{intent['route_type']} · {title_focus}",
        "region": location,
        "summary": summary,
        "understood_request": understood,
        "advisor_notes": advisor_notes,
        "difficulty": intent["difficulty"],
        "route_type": intent["route_type"],
        "best_season": "À choisir selon enneigement, météo, ouvertures des hébergements et réglementation locale",
        "duration_days": len(stages),
        "start": {"name": start["name"], "lat": start["lat"], "lon": start["lon"], "access_note": transport["outbound"]},
        "end": {"name": end["name"], "lat": end["lat"], "lon": end["lon"], "access_note": transport["return"]},
        "waypoints": [{"name": p["name"], "lat": p["lat"], "lon": p["lon"], "reason": CATEGORY_LABEL.get(p.get("category"), "étape utile")} for p in route_points],
        "stages": stages,
        "points_of_interest": pois,
        "water": water,
        "resources": resources,
        "food": resources,
        "accommodations": accommodations,
        "transport": transport,
        "confidence": {
            "overall": "Bonne" if confidence_score >= 75 else "Moyenne" if confidence_score >= 50 else "Limitée",
            "score": confidence_score,
            "limitations": limitations,
        },
        "sources": sources,
        "route_preview": {
            "coords": _downsample(route_coords),
            "distance_km": round(distance, 2),
            "elevation_gain_m": total_elev,
            "fallback": bool(route.get("fallback")),
            "warning": route.get("warning"),
        },
        "planner": {
            "version": PLANNER_VERSION,
            "strategy": candidate.strategy,
            "candidates_compared": len(evaluated),
            "corridor_centered": corridor_centered,
            "corridor_search_version": CORRIDOR_SEARCH_VERSION,
            "postroute_resource_count": len([
                x for x in items if x.get("_postroute_resource")
            ]),
            "stage_rebalanced": stage_rebalanced,
            "search_center": {
                "lat": round(float(center["lat"]), 6),
                "lon": round(float(center["lon"]), 6),
            },
            "intent": {k: v for k, v in intent.items() if k not in {"raw", "priorities", "avoid"}},
        },
        "model": PLANNER_VERSION,
    }


def install_smart_planner(app, legacy_main):
    @app.get("/ai/status")
    def status():
        return {
            "configured": True,
            "model": PLANNER_VERSION,
            "web_search": False,
            "routing": bool(os.getenv("ORS_API_KEY", "").strip()),
            "cost_per_request": 0,
            "engine": "expert-multi-candidate",
            "capabilities": [
                "intent-parsing", "multi-candidate-planning", "scenic-scoring",
                "logistics-scoring", "real-routing", "water-check", "transit-proximity",
            ],
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
                detail="Le conseiller TrekMap n'a pas pu construire un plan cohérent. Essaie une zone plus précise ou assouplis une contrainte.",
            ) from exc
