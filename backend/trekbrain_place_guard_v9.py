"""High-confidence place guards for TrekBrain v9.

Some French place names are ambiguous enough that a generic geocoder can return
an entirely different place.  This module only hardens a very small list of
well-known ambiguous anchors where the user's wording is explicit.
"""
from __future__ import annotations

import re
import unicodedata

_INSTALLED = False

BELLE_ILE = {
    "name": "Belle-Île-en-Mer, Morbihan, Bretagne, France",
    "short_name": "Belle-Île-en-Mer",
    "lat": 47.3331,
    "lon": -3.1870,
    "category": "place",
    "source_url": "https://www.openstreetmap.org/?mlat=47.333100&mlon=-3.187000#map=12/47.333100/-3.187000",
    "geocode_guard": "belle-ile-en-mer",
}


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    text = re.sub(r"[-_'’.,;/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_belle_ile_en_mer(value: str) -> bool:
    text = _fold(value)
    return "belle ile en mer" in text


def guarded_geocode_factory(original):
    def geocode(query: str):
        if _is_belle_ile_en_mer(query):
            return [dict(BELLE_ILE)]
        return original(query)

    return geocode


def install_place_guard(v3, geo, request_module) -> None:
    """Pin Belle-Île-en-Mer and make natural-language detection wording-agnostic."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_geo = geo._geocode
    guarded_geo = guarded_geocode_factory(original_geo)
    geo._geocode = guarded_geo
    v3._geocode = guarded_geo

    original_extract = request_module._extract_prompt_places

    def extract_prompt_places(prompt: str):
        rows = list(original_extract(prompt) or [])
        if not _is_belle_ile_en_mer(prompt):
            return rows
        canonical = {"kind": "route_area", "place": "Belle-Île-en-Mer", "after_trip": False}
        filtered = [
            row for row in rows
            if not _is_belle_ile_en_mer(str((row or {}).get("place") or ""))
        ]
        return [canonical] + filtered[:5]

    request_module._extract_prompt_places = extract_prompt_places


__all__ = ["install_place_guard", "guarded_geocode_factory", "BELLE_ILE", "_is_belle_ile_en_mer"]
