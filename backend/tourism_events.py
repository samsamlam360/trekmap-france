"""Optional free tourism/event enrichment for TrekMap.

DATAtourisme is optional. TrekMap remains usable without a key; dated-event
requests are then kept as understood-but-unverified constraints.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import requests

BASE_URL = "https://api.datatourisme.fr/v1"
TIMEOUT = 14


def configured() -> bool:
    return bool(os.getenv("DATATOURISME_API_KEY", "").strip())


def _first_label(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("fr", "@fr", "label", "name"):
            if isinstance(value.get(key), str) and value.get(key).strip():
                return value[key].strip()
        for item in value.values():
            if isinstance(item, str) and item.strip():
                return item.strip()
    if isinstance(value, list):
        for item in value:
            label = _first_label(item)
            if label:
                return label
    return ""


def _geo(obj: dict[str, Any]) -> tuple[float, float] | None:
    located = obj.get("isLocatedAt") or {}
    geo = located.get("geo") or {}
    candidates = [geo]
    if isinstance(geo, list):
        candidates = geo
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        lat = candidate.get("latitude")
        lon = candidate.get("longitude")
        if lat is None or lon is None:
            # Some serialisations use lat/long or coordinates.
            lat = candidate.get("lat")
            lon = candidate.get("lon") or candidate.get("lng")
        try:
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        except (TypeError, ValueError):
            pass
    return None


def _periods(obj: dict[str, Any]) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    periods = obj.get("takesPlaceAt") or []
    if isinstance(periods, dict):
        periods = [periods]
    for period in periods:
        if not isinstance(period, dict):
            continue
        raw_start = period.get("startDate")
        raw_end = period.get("endDate") or raw_start
        try:
            start = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00")).date()
            end = datetime.fromisoformat(str(raw_end).replace("Z", "+00:00")).date()
        except (TypeError, ValueError):
            continue
        out.append((start, end))
    return out


def search_events(lat: float, lon: float, target_date: date, *, radius_km: int = 25, query: str = "") -> list[dict[str, Any]]:
    key = os.getenv("DATATOURISME_API_KEY", "").strip()
    if not key:
        return []

    params = {
        "lang": "fr",
        "page_size": 80,
        "geo_distance": f"{float(lat):.6f},{float(lon):.6f},{max(2, min(int(radius_km), 50))}km",
        "fields": "uuid,uri,label,type,isLocatedAt.geo,isLocatedAt.address,takesPlaceAt,hasDescription",
    }
    if query.strip():
        params["search"] = query.strip()

    response = requests.get(
        BASE_URL + "/entertainmentAndEvent",
        params=params,
        headers={"X-API-Key": key, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    objects = payload.get("objects") or [] if isinstance(payload, dict) else []

    results = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        periods = _periods(obj)
        if periods and not any(start <= target_date <= end for start, end in periods):
            continue
        coords = _geo(obj)
        if not coords:
            continue
        address = obj.get("isLocatedAt") or {}
        results.append({
            "name": _first_label(obj.get("label")) or "Événement local",
            "lat": coords[0],
            "lon": coords[1],
            "date": target_date.isoformat(),
            "periods": [{"start": a.isoformat(), "end": b.isoformat()} for a, b in periods],
            "source_url": str(obj.get("uri") or "https://www.datatourisme.fr/"),
            "source": "DATAtourisme",
            "address": _first_label(address.get("address")) if isinstance(address, dict) else "",
        })
    return results
