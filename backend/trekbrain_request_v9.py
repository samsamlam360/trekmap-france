"""TrekBrain v9 request reconciliation.

Users often edit the natural-language request without resetting every field in
TrekMap's form. The text is therefore allowed to replace stale form values when
it contains an unambiguous geographic anchor. This module stays deterministic:
it never invents coordinates and only accepts place names that geocode in the
existing France-only geographic stack.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from . import free_planner_v2 as geo


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _clean_place(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;:-")
    value = re.sub(r"^(?:le|la|les|l['’])\s*", "", value, flags=re.I)
    value = re.sub(
        r"\s+(?:un|le)\s+(?:soir|matin|apres-midi|après-midi)(?:\b.*)?$",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"\s+(?:apres|après|avant|pendant)\s+(?:la|le|mon|notre)\b.*$", "", value, flags=re.I)
    value = re.sub(r"\s+en\s+\d{1,2}\s*(?:jours?|j)\b.*$", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" ,.;:-")
    # Common spoken abbreviation. Keep this intentionally narrow rather than
    # rewriting every French place that happens to contain "st".
    if re.fullmatch(r"mont\s+st[ .-]*michel", _fold(value)):
        return "Mont Saint-Michel"
    return value[:100]


def _extract_prompt_places(prompt: str) -> list[dict[str, Any]]:
    """Return likely geographic anchors in strongest-to-weakest order.

    Evening/post-hike visits are deliberately marked as non-routing objectives.
    Visiting a monument after the day's walk must not silently become a hard
    hiking waypoint and make an otherwise valid loop impossible.
    """
    text = re.sub(r"\s+", " ", str(prompt or "")).strip()
    if not text:
        return []

    stop = (
        r"(?=\s+(?:un|le)\s+(?:soir|matin|apres-midi|après-midi)\b"
        r"|\s+(?:apres|après|avant|pendant)\s+(?:la|le|mon|notre)\b"
        r"|\s+en\s+\d{1,2}\s*(?:jours?|j)\b"
        r"|\s+et\s+(?:je|nous|on)\b"
        r"|\s+avec\b|\s+pour\b|[,.;!?]|$)"
    )
    patterns = [
        ("route_area", rf"(?:faire\s+)?(?:le\s+)?tour\s+(?:de|du|des|d['’])\s*(.+?){stop}"),
        ("route_area", rf"(?:trek|rando|randonn[eé]e)\s+(?:a|à|au|aux|dans|autour\s+de|pres\s+de|près\s+de)\s+(.+?){stop}"),
        ("route_area", rf"(?:autour|pres|près|a\s+proximite|à\s+proximité)\s+(?:de|du|des|d['’])\s*(.+?){stop}"),
        ("visit", rf"(?:visiter|voir|decouvrir|découvrir|passer\s+par|aller\s+(?:a|à|au|aux))\s+(.+?){stop}"),
    ]

    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    folded_all = _fold(text)
    after_trip_global = bool(
        re.search(
            r"\bapres\s+(?:(?:le|mon|notre)\s+trek|la\s+fin\s+du\s+trek)\b",
            folded_all,
        )
    )
    for kind, pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            place = _clean_place(match.group(1))
            key = _fold(place)
            if len(place) < 3 or key in seen:
                continue
            # Avoid treating generic planning vocabulary as a place name.
            if key in {"camping", "campings", "refuge", "refuges", "gare", "train", "bus", "boucle"}:
                continue
            seen.add(key)

            tail = _fold(text[match.end(): match.end() + 160])
            after_daily_hike = bool(
                re.match(
                    r"\s*(?:(?:un|le)\s+(?:soir|matin|apres-midi)\s+)?"
                    r"apres\s+(?:la|le|une|mon|notre)\s+"
                    r"(?:randonnee|rando|marche|journee(?:\s+de\s+randonnee)?|etape)\b",
                    tail,
                )
            )
            found.append({
                "kind": kind,
                "place": place,
                # Historical field name retained for compatibility. It now also
                # means "visit outside the hiking trace", such as an evening visit.
                "after_trip": bool(kind == "visit" and (after_trip_global or after_daily_hike)),
            })
    return found[:6]


def _geocode_one(place: str) -> dict[str, Any] | None:
    queries = [place]
    if _fold(place) == "mont st michel":
        queries.insert(0, "Mont Saint-Michel")
    for query in dict.fromkeys(queries):
        try:
            rows = geo._geocode(f"{query}, France") or geo._geocode(query)
        except Exception:
            rows = []
        if rows:
            return rows[0]
    return None


def _distance_km(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float | None:
    if not a or not b:
        return None
    try:
        return float(geo._dist(a, b))
    except Exception:
        return None


def reconcile_request(data):
    """Reconcile stale form geography with an explicit natural-language request.

    Returns ``(effective_request, metadata)``. Other form fields are intentionally
    left untouched here; TrekBrain's existing intent parser remains the single
    source of truth for days, distance, difficulty and route type.
    """
    prompt = str(getattr(data, "prompt", "") or "").strip()
    form_region = str(getattr(data, "region", "") or "").strip()
    places = _extract_prompt_places(prompt)
    form_in_prompt = bool(form_region and _fold(form_region) in _fold(prompt))

    explicit_area = next((x for x in places if x["kind"] == "route_area" and not x["after_trip"]), None)
    visit = next((x for x in places if x["kind"] == "visit" and not x["after_trip"]), None)
    selected = explicit_area or visit

    effective_region = form_region
    anchor_name = None
    anchor_point = None
    region_overridden = False
    forced_waypoint = None
    reason = "form-region-kept"

    if selected:
        anchor_point = _geocode_one(selected["place"])
        if anchor_point:
            anchor_name = str(anchor_point.get("short_name") or selected["place"]).strip()[:120]
            if selected["kind"] == "route_area":
                effective_region = anchor_name
                region_overridden = _fold(effective_region) != _fold(form_region)
                reason = "explicit-route-area"
            elif not form_region:
                effective_region = anchor_name
                region_overridden = True
                reason = "explicit-visit-without-form-region"
            elif not form_in_prompt:
                form_point = _geocode_one(form_region)
                separation = _distance_km(form_point, anchor_point)
                # A large conflict combined with an absent form-region mention is
                # the characteristic stale-form case seen on mobile.
                if form_point is None or separation is None or separation >= 35.0:
                    effective_region = anchor_name
                    region_overridden = _fold(effective_region) != _fold(form_region)
                    reason = "stale-form-region-conflict"

            if selected["kind"] == "visit" and not selected["after_trip"]:
                # Do not manufacture a hard waypoint when the requested visit is
                # already the trek's geographic centre. This was blocking the ORS
                # round-trip fallback for requests such as Mont-Saint-Michel.
                region_point = _geocode_one(effective_region) if effective_region else None
                separation = _distance_km(region_point, anchor_point)
                if separation is None or separation > 3.0:
                    forced_waypoint = anchor_name
                else:
                    reason = reason + "+visit-near-region"

    effective_prompt = prompt
    if forced_waypoint:
        marker = f"passer par {forced_waypoint}"
        if _fold(marker) not in _fold(effective_prompt):
            effective_prompt = (effective_prompt + " ; " + marker).strip()[:4000]

    effective = data.model_copy(update={
        "region": effective_region,
        "prompt": effective_prompt,
    })
    meta = {
        "original_region": form_region,
        "effective_region": effective_region,
        "region_overridden": region_overridden,
        "prompt_anchor": anchor_name,
        "forced_waypoint": forced_waypoint,
        "reason": reason,
        "form_region_mentioned_in_prompt": form_in_prompt,
        "after_trip_places": [x["place"] for x in places if x.get("after_trip")],
    }
    return effective, meta


__all__ = ["reconcile_request", "_extract_prompt_places"]
