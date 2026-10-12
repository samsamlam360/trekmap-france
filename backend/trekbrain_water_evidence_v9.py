"""Single source of truth for interpreting OSM water-potability evidence.

Used by the route-first OSM bundle, the post-route Overpass corridor and the
display-only water query. No network access, provider requests, or changes to
route geometry. An explicit unsafe tag takes priority over generic drinking
water amenities or contradictory positive tags. Positive OSM evidence must
still be checked in the field; it is not a laboratory safety guarantee.
"""
from __future__ import annotations
from typing import Mapping, Any


def potability_status(tags: Mapping[str, Any] | None) -> str:
    tags = tags if isinstance(tags, Mapping) else {}

    def normalized(name: str) -> str:
        return str(tags.get(name) or "").strip().casefold()

    if any(normalized(key) == "no" for key in (
        "drinking_water", "water:potable", "potable",
    )):
        return "not_potable"

    if (
        normalized("amenity") == "drinking_water"
        or any(normalized(key) == "yes" for key in (
            "drinking_water", "water:potable", "potable",
        ))
    ):
        return "potable_referenced"

    return "unverified"


__all__ = ["potability_status"]
