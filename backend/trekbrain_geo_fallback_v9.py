"""France-wide independent geocoding fallback for a throttled OSM provider.

IGN Géoplateforme serves BAN/BD TOPO location data over a public endpoint.
It is used only when Nominatim and Photon cannot provide a usable place.
Never convert a geocoder centre into a pedestrian route without ORS validation.
"""
from __future__ import annotations

import math
import re
import unicodedata

from . import free_planner_v2 as geo

IGN_GEOCODAGE_URL = "https://data.geopf.fr/geocodage/search"
_IGN_STOPWORDS = {"france", "de", "du", "des", "le", "la", "les", "l", "d", "en", "au", "aux"}


def _words(text: str) -> set[str]:
    normal = unicodedata.normalize("NFKD", str(text or ""))
    normal = "".join(c for c in normal if not unicodedata.combining(c)).casefold()
    return {word for word in re.findall(r"[a-z0-9]+", normal)
            if len(word) >= 2 and word not in _IGN_STOPWORDS}


def geocode_ign(query: str, *, timeout: float = 2.5) -> list[dict]:
    """Use a real French geocoder, rejecting unrelated address suggestions.

    BAN address search can return a street with a similar word in a different
    city. Require most significant query tokens to occur in label/context; this
    fallback must never quietly move a hike to another department.
    """
    query = str(query or "").strip()
    words = _words(query)
    if not query or not words:
        return []
    payload = geo._request_json(
        IGN_GEOCODAGE_URL,
        params={"q": query, "limit": 5},
        timeout=min(4.0, max(0.8, float(timeout))),
        ttl=43200,
        service="IGN Géoplateforme",
        retries=1,
        cache_empty=False,
    )
    rows = []
    features = payload.get("features") if isinstance(payload, dict) else []
    for feature in features if isinstance(features, list) else []:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)
                and 41.0 <= lat <= 51.6 and -5.6 <= lon <= 10.0):
            continue
        label = str(props.get("label") or props.get("name") or "").strip()
        context = " ".join(str(props.get(k) or "") for k in ("city", "context", "postcode"))
        matches = words & _words(label + " " + context)
        if len(matches) < max(1, math.ceil(len(words) * 0.70)):
            continue
        if props.get("score") is not None:
            try:
                if float(props["score"]) < 0.35:
                    continue
            except (TypeError, ValueError):
                continue
        name = ", ".join(x for x in (label, str(props.get("context") or "").strip()) if x)
        point = geo._normalise_place(name or query, lat, lon)
        point["geocode_provider"] = "ign-geoplateforme"
        rows.append(point)
    return rows


DEPARTMENTS_URL = "https://geo.api.gouv.fr/departements"


def _fold(text: str) -> str:
    """Accented French labels and official department names, normalized."""
    normal = unicodedata.normalize("NFKD", str(text or ""))
    normal = "".join(c for c in normal if not unicodedata.combining(c)).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", normal))


def geocode_ign_poi(query: str, *, timeout: float = 2.5) -> list[dict]:
    """Resolve a named French landmark in an **explicit** department.

    A common landmark name such as "Lac Blanc" exists in multiple mountain
    ranges. IGN's POI index must therefore be constrained both in the query and
    in each returned feature to the exact officially resolved department.
    No department = no guessed position. Route network validation still applies.
    """
    pieces = [x.strip() for x in str(query or "").split(",") if x.strip()]
    if pieces and _fold(pieces[-1]) == "france":
        pieces.pop()
    if len(pieces) != 2:
        return []
    landmark, department = pieces
    wanted = _words(landmark)
    if not wanted or len(_fold(landmark)) < 3:
        return []
    if not re.fullmatch(r"[a-zA-ZÀ-ÿ0-9 '\-]+", department):
        return []
    budget = min(3.0, max(0.8, float(timeout)))

    # The official department lookup is exact, not a fuzzy geographical guess.
    # A code (68, 2A, 2B...) may be supplied instead of a written name.
    if re.fullmatch(r"(?:[0-9]{2,3}|2[abAB])", department):
        code = department.upper()
    else:
        official = geo._request_json(
            DEPARTMENTS_URL,
            params={"nom": department, "fields": "nom,code", "format": "json"},
            timeout=budget, ttl=43200,
            service="Départements français", retries=1, cache_empty=False,
        )
        found = {
            str(item.get("code") or "").upper()
            for item in official if isinstance(official, list) and isinstance(item, dict)
            and _fold(item.get("nom") or "") == _fold(department)
        }
        if len(found) != 1:
            return []
        code = next(iter(found))
    if not code:
        return []

    payload = geo._request_json(
        IGN_GEOCODAGE_URL,
        params={"q": landmark, "index": "poi", "depcode": code, "limit": 8},
        timeout=budget, ttl=43200,
        service="IGN Géoplateforme POI", retries=1, cache_empty=False,
    )
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return []

    accepted = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            continue
        returned_codes = props.get("depcode") or []
        if isinstance(returned_codes, str):
            returned_codes = [returned_codes]
        if not isinstance(returned_codes, list) or code not in {
            str(x).upper() for x in returned_codes
        }:
            continue
        raw_label = props.get("toponym") or props.get("name") or ""
        if isinstance(raw_label, list):
            raw_label = raw_label[0] if raw_label else ""
        label = str(raw_label).strip()
        # Every meaningful place-name token must be present in the feature's
        # actual toponym. Matching "Jura" only in its address is not sufficient.
        if not label or not wanted.issubset(_words(label)):
            continue
        try:
            score = float(props.get("score") or 0)
        except (ValueError, TypeError):
            continue
        if not math.isfinite(score) or score < 0.55:
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if not isinstance(coords, (tuple, list)) or len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (ValueError, TypeError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)
                and 41.0 <= lat <= 51.6 and -5.6 <= lon <= 10.0):
            continue
        point = geo._normalise_place(f"{label}, {department}, France", lat, lon)
        point["geocode_provider"] = "ign-bdtopo-poi"
        point["department_code"] = code
        point["geocode_precision"] = "named-poi"
        point["geocode_score"] = round(score, 3)
        # Full-name matches such as "Lac Blanc" outrank nearby visitor centres.
        same_name = _fold(label) == _fold(landmark)
        accepted.append((0 if same_name else 1, -score, point))
    accepted.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in accepted]


__all__ = ["geocode_ign", "geocode_ign_poi", "IGN_GEOCODAGE_URL", "DEPARTMENTS_URL"]
