"""Fail-closed French commune fallback for cold geocoding failures.

The public French administrative dataset locates *communes*, not trailheads.
Use it only after the normal Nominatim, Photon and IGN fallback exhausted.
Never accept a similarly named commune in another department; the pedestrian
route still needs independent network validation before being shown.
"""
from __future__ import annotations

import math
import re
import unicodedata

from . import free_planner_v2 as geo

COMMUNES_URL = "https://geo.api.gouv.fr/communes"


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def geocode_commune(query: str, *, timeout: float = 2.5) -> list[dict]:
    """Return an administrative commune centre only when location is unambiguous.

    An optional department must match the complete official name or code:
    'Passy, Haute-Savoie' must never silently resolve to Passy in Yonne.
    Unqualified homonyms remain unresolved rather than guessed.
    """
    pieces = [part.strip() for part in str(query or "").split(",") if part.strip()]
    if pieces and _fold(pieces[-1]) == "france":
        pieces.pop()
    if not 1 <= len(pieces) <= 2:
        return []
    city = pieces[0]
    wanted_city = _fold(city)
    wanted_department = _fold(pieces[1]) if len(pieces) == 2 else ""
    if not wanted_city or len(wanted_city) < 2:
        return []

    payload = geo._request_json(
        COMMUNES_URL,
        params={"nom": city, "fields": "nom,code,centre,departement", "format": "json"},
        timeout=min(3.0, max(0.8, float(timeout))),
        ttl=43200,
        service="Communes françaises (API publique)",
        retries=1,
        cache_empty=False,
    )
    if not isinstance(payload, list):
        return []

    matched: dict[str, dict] = {}
    for entry in payload:
        if not isinstance(entry, dict) or _fold(entry.get("nom") or "") != wanted_city:
            continue
        department = entry.get("departement") or {}
        if not isinstance(department, dict):
            continue
        dept_name = str(department.get("nom") or "")
        dept_code = str(department.get("code") or entry.get("codeDepartement") or "")
        if wanted_department and wanted_department not in {_fold(dept_name), _fold(dept_code)}:
            continue
        centre = entry.get("centre") or {}
        coords = centre.get("coordinates") if isinstance(centre, dict) else None
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)
                and 41.0 <= lat <= 51.6 and -5.6 <= lon <= 10.0):
            continue
        code = str(entry.get("code") or "")
        if not code or not dept_code:
            continue
        name = ", ".join(filter(None, (str(entry["nom"]), dept_name, "France")))
        place = geo._normalise_place(name, lat, lon)
        place["geocode_provider"] = "geo-api-gouv-communes"
        place["commune_insee"] = code
        place["department_code"] = dept_code
        matched[code] = place

    # A fuzzy query can return multiple identically named municipalities.
    # Requiring exactly one official INSEE code prevents homonym misrouting.
    return list(matched.values()) if len(matched) == 1 else []


__all__ = ["geocode_commune", "COMMUNES_URL"]
