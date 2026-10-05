"""High-confidence place guards for TrekBrain v9.

Some French place names are ambiguous enough that a generic geocoder can return
an entirely different place. This module hardens a very small list of anchors
where the hiking context makes the intended place unambiguous.
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

BEAUFORT_SAVOIE = {
    "name": "Beaufort, Savoie, Auvergne-Rhône-Alpes, France",
    "short_name": "Beaufort",
    "lat": 45.7189,
    "lon": 6.5756,
    "category": "place",
    "source_url": "https://www.openstreetmap.org/?mlat=45.718900&mlon=6.575600#map=12/45.718900/6.575600",
    "geocode_guard": "beaufort-savoie",
}


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    text = re.sub(r"[-_'’.,;/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_belle_ile_en_mer(value: str) -> bool:
    """Recognise both the official name and the common short form Belle-Île."""
    text = _fold(value)
    if not re.search(r"\bbelle ile(?: en mer)?\b", text):
        return False
    # Do not hijack an explicitly disambiguated homonym.
    if any(word in text for word in ("chelles", "seine et marne")):
        return False
    return True


def _is_beaufort_savoie(value: str) -> bool:
    """Recognise Beaufort in Savoie without hijacking French homonyms."""
    text = _fold(value)
    if "beaufortain" in text or "beaufort sur doron" in text:
        return True
    if not re.search(r"\bbeaufort\b", text):
        return False
    return bool(
        re.search(r"\bsavoie\b", text)
        or "73270" in text
        or "auvergne rhone alpes" in text
    )


def guarded_geocode_factory(original):
    def geocode(query: str, **kwargs):
        if _is_belle_ile_en_mer(query):
            return [dict(BELLE_ILE)]
        if _is_beaufort_savoie(query):
            return [dict(BEAUFORT_SAVOIE)]
        # Preserve optional geocoder controls added by v9 (for example the
        # Nominatim retry budget). Dropping these kwargs silently re-enabled a
        # redundant Nominatim lookup on the round-trip fallback path.
        return original(query, **kwargs)

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

        if _is_beaufort_savoie(prompt):
            canonical = {"kind": "route_area", "place": "Beaufort, Savoie", "after_trip": False}
            rows = [
                row for row in rows
                if not _is_beaufort_savoie(str((row or {}).get("place") or ""))
            ]
            rows = [canonical] + rows[:5]

        if _is_belle_ile_en_mer(prompt):
            canonical = {"kind": "route_area", "place": "Belle-Île-en-Mer", "after_trip": False}
            rows = [
                row for row in rows
                if not _is_belle_ile_en_mer(str((row or {}).get("place") or ""))
            ]
            rows = [canonical] + rows[:5]

        return rows[:6]

    request_module._extract_prompt_places = extract_prompt_places


__all__ = [
    "install_place_guard",
    "guarded_geocode_factory",
    "BELLE_ILE",
    "BEAUFORT_SAVOIE",
    "_is_belle_ile_en_mer",
    "_is_beaufort_savoie",
]
