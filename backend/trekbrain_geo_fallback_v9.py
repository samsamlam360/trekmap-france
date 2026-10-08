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


__all__ = ["geocode_ign", "IGN_GEOCODAGE_URL"]
