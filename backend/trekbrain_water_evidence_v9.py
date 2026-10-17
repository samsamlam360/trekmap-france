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
    def tag(name: str) -> str:
        return str(tags.get(name) or "").strip().casefold()

    # These are availability/access restrictions, NOT claims that the water
    # itself is unsafe. Keep the point visible on the map, but do not count
    # a locked, private, abandoned or seasonal source as a guaranteed daily
    # public resupply. Each conclusion must be grounded in actual OSM tags.
    if tag("access") in {"private", "no", "customers", "permit"}:
        return False
    if any(tag(key) in {"yes", "true", "1"} for key in (
        "disused", "abandoned", "locked", "intermittent",
    )):
        return False
    if tag("seasonal") not in {"", "no", "false", "0"}:
        return False
    # amenity=drinking_water is often present even when a more precise
    # conditional status says availability or potability is uncertain.
    if any(tag(key) in {"conditional", "seasonal", "intermittent", "unknown"} for key in (
        "drinking_water", "water:potable", "potable",
    )):
        return False
    return True

def merge_water_evidence(existing: dict[str, Any], incoming: Mapping[str, Any]) -> None:
    """Merge the SAME OSM water source without erasing safety/access warnings.

    A route-first POI and a later mirror can return different subsets of
    OSM tags. Neither an incomplete response nor a recent generic potable
    amenity can erase an older explicit restriction or 'not potable' tag.
    This changes evidence only, never the route or provider budgets.
    """
    if not isinstance(existing, dict) or not isinstance(incoming, Mapping):
        return
    current = existing.get("osm_tags")
    old = current if isinstance(current, Mapping) else {}
    recent = incoming.get("osm_tags")
    fresh = recent if isinstance(recent, Mapping) else {}
    merged = dict(old)
    for key, value in fresh.items():
        name = str(key)
        previous = str(old.get(key) or "").strip().casefold()
        newest = str(value or "").strip().casefold()
        if name in {"drinking_water", "water:potable", "potable"}:
            # Explicitly unsafe or conditional statuses win over 'yes'.
            rank = {"no": 4, "conditional": 3, "seasonal": 3,
                    "intermittent": 3, "unknown": 2}
            if rank.get(previous, 0) > rank.get(newest, 0):
                continue
        if name == "access" and previous in {"no", "private", "customers", "permit"}:
            if newest not in {"no", "private", "customers", "permit"}:
                continue
        if name in {"locked", "disused", "abandoned", "intermittent"}:
            if previous in {"yes", "true", "1"} and newest not in {"yes", "true", "1"}:
                continue
        if name == "seasonal" and previous not in {"", "no", "false", "0"}:
            if newest in {"", "no", "false", "0"}:
                continue
        merged[key] = value
    if merged:
        existing["osm_tags"] = merged
    original_status = water_evidence_status(existing)
    new_status = water_evidence_status(incoming)
    if "not_potable" in (original_status, new_status):
        existing.update(status="not_potable", water_status="not_potable",
                        notes="Eau signalée non potable : ne pas boire.")
    elif original_status == "unverified" and new_status == "potable_referenced":
        existing.update(status="potable_referenced", water_status="potable_referenced")


__all__ = ["potability_status", "has_osm_identity", "water_evidence_status", "confirmed_water_reference", "merge_water_evidence"]
