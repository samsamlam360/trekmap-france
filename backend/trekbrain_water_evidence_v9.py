"""Single source of truth for interpreting OSM water-potability evidence.

Used by the route-first OSM bundle, the post-route Overpass corridor and the
display-only water query. No network access, provider requests, or changes to
route geometry. An explicit unsafe tag takes priority over generic drinking
water amenities or contradictory positive tags. Positive OSM evidence must
still be checked in the field; it is not a laboratory safety guarantee.
"""
from __future__ import annotations
from typing import Mapping, Any
import re


def has_osm_identity(item: Mapping[str, Any] | None) -> bool:
    """A traceable OSM object, not a suggestive URL or an invented address."""
    return bool(isinstance(item, Mapping) and re.fullmatch(
        r"https://www\.openstreetmap\.org/(?:node|way|relation)/[1-9][0-9]*",
        str(item.get("source_url") or "").strip(),
    ))


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


def water_evidence_status(item: Mapping[str, Any] | None) -> str:
    """Preserve explicit negative evidence across raw and cached schemas."""
    item = item if isinstance(item, Mapping) else {}
    tags = item.get("osm_tags")
    tag_status = potability_status(tags)
    statuses = {str(item.get(key) or "").strip().casefold()
                for key in ("status", "water_status")}
    if "not_potable" in statuses or tag_status == "not_potable":
        return "not_potable"
    if "potable_referenced" in statuses or tag_status == "potable_referenced":
        return "potable_referenced"
    return "unverified"


def confirmed_water_reference(item: Mapping[str, Any] | None) -> bool:
    """Mapped drinking water, with no known access/closure restriction.

    This is a cartographic reference. It never guarantees flow, availability
    or current water quality and still requires a check before departure.
    """
    if not has_osm_identity(item) or water_evidence_status(item) != "potable_referenced":
        return False
    tags = item.get("osm_tags") or {}
    if not isinstance(tags, Mapping):
        tags = {}
    return (str(tags.get("access") or "").casefold() not in {"private", "no"}
            and str(tags.get("disused") or "").casefold() != "yes")


__all__ = ["potability_status", "has_osm_identity", "water_evidence_status", "confirmed_water_reference"]
