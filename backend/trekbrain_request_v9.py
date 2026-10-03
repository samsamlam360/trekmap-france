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


def _mentions_belle_ile(value: str) -> bool:
    text = _fold(value).replace("’", "'")
    return bool(re.search(r"\bbelle[ -]?ile(?:\s+en\s+mer)?\b", text))


def _route_type_from_prompt(prompt: str) -> str | None:
    """Return an explicit route shape stated in natural language.

    A phrase such as "faire le tour de Belle-Île" is a loop request even when
    the stale form still says "Traversée". Conversely, an explicit negation such
    as "ce n'est pas une boucle" must beat the mere presence of the word
    "boucle"; this matters for natural point-to-point prompts like Tours -> Chinon.
    """
    text = _fold(prompt).replace("’", "'")

    # Strong explicit shapes first. In particular, do not let the token
    # "boucle" inside "ce n'est pas une boucle" turn a traverse into a loop.
    if re.search(r"\baller[- ]retour\b", text):
        return "Aller-retour"
    if re.search(
        r"\b(?:traversee|itin[eé]rance\s+lineaire|itinerance\s+lineaire|"
        r"itineraire\s+lineaire|point[- ]a[- ]point)\b",
        text,
    ):
        return "Traversée"
    if re.search(
        r"\b(?:(?:ce\s+)?n[' ]?est\s+pas\s+(?:une?\s+)?boucle|"
        r"pas\s+(?:en\s+|une?\s+)?boucle|sans\s+boucle)\b",
        text,
    ):
        return "Traversée"
    if (
        re.search(r"\b(?:faire\s+)?(?:le\s+)?tour\s+(?:de|du|des|d[' ]?)\b", text)
        or re.search(r"\b(?:boucle|circuit)\b", text)
    ):
        return "Boucle"
    # Explicit start + explicit finish is point-to-point unless a stronger
    # shape above says otherwise. This also defeats a stale "Boucle" form value.
    if (
        re.search(r"\b(?:depart|partir|commencer|debuter)\b", text)
        and re.search(r"\b(?:arrivee|finir|terminer)\b", text)
    ):
        return "Traversée"
    if re.search(r"\bitinerance\b", text):
        return "Itinérance"
    return None


def _explicit_endpoint_pair(prompt: str) -> tuple[str, str] | None:
    """Extract strong natural point-to-point wording such as Tours -> Chinon."""
    text = re.sub(r"\s+", " ", str(prompt or "")).strip()
    match = re.search(
        r"\b(?:aller|marcher)\s+(?:de|depuis)\s+(.+?)\s+(?:à|a|au|aux)\s+(.+?)"
        r"(?=\s+(?:à|a)\s+pied\b|\s+en\s+\d{1,2}\s*(?:jours?|j)\b|"
        r"\s+(?:avec|sans|pour)\b|[,.;!?]|$)",
        text,
        flags=re.I,
    )
    if not match:
        return None
    start = _clean_place(match.group(1))
    end = _clean_place(match.group(2))
    if len(start) < 2 or len(end) < 2:
        return None
    return start, end


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
    if re.fullmatch(r"mont\s+st[ .-]*michel", _fold(value)):
        return "Mont Saint-Michel"
    if _mentions_belle_ile(value):
        return "Belle-Île-en-Mer"
    return value[:100]


def _extract_prompt_places(prompt: str) -> list[dict[str, Any]]:
    """Return likely geographic anchors in strongest-to-weakest order.

    Evening/post-hike visits can still identify the correct geographic area, but
    they are marked as non-routing objectives so they do not silently become
    mandatory hiking waypoints.
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
                "after_trip": bool(kind == "visit" and (after_trip_global or after_daily_hike)),
            })

    # Belle-Île is a particularly ambiguous short place name. In a hiking
    # request, "Belle-Île" means the Morbihan island unless the user explicitly
    # gives a different disambiguator. Canonicalising it here also makes island
    # bounds available before POI discovery.
    if _mentions_belle_ile(text):
        canonical = {"kind": "route_area", "place": "Belle-Île-en-Mer", "after_trip": False}
        found = [canonical] + [x for x in found if not _mentions_belle_ile(x.get("place") or "")]

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
    prompt = str(getattr(data, "prompt", "") or "").strip()
    form_region = str(getattr(data, "region", "") or "").strip()
    form_route_type = str(getattr(data, "route_type", "") or "").strip() or "Boucle"
    places = _extract_prompt_places(prompt)
    endpoint_pair = _explicit_endpoint_pair(prompt)
    form_in_prompt = bool(form_region and _fold(form_region) in _fold(prompt))

    explicit_area = next((x for x in places if x["kind"] == "route_area"), None)
    # A visit can identify the right region even when it happens after the day's
    # hike. Whether it becomes a mandatory waypoint is decided separately below.
    visit = next((x for x in places if x["kind"] == "visit"), None)
    selected = explicit_area or visit

    effective_region = form_region
    anchor_name = None
    anchor_point = None
    region_overridden = False
    forced_waypoint = None
    reason = "form-region-kept"

    if endpoint_pair:
        start_name, end_name = endpoint_pair
        # Strong "de X à Y" wording is already authoritative text. Do not
        # geocode both cities here and then geocode them again in the geographic
        # planner. Validation belongs to that planner, which needs the actual
        # coordinates anyway. This removes two serial network lookups from
        # point-to-point requests such as Tours -> Chinon.
        anchor_name = start_name[:120]
        effective_region = anchor_name
        region_overridden = _fold(effective_region) != _fold(form_region)
        reason = "explicit-endpoint-pair-deferred-geocode"
        selected = None

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
                if form_point is None or separation is None or separation >= 35.0:
                    effective_region = anchor_name
                    region_overridden = _fold(effective_region) != _fold(form_region)
                    reason = "stale-form-region-conflict"

            if selected["kind"] == "visit" and not selected["after_trip"]:
                region_point = _geocode_one(effective_region) if effective_region else None
                separation = _distance_km(region_point, anchor_point)
                if separation is None or separation > 3.0:
                    forced_waypoint = anchor_name
                else:
                    reason = reason + "+visit-near-region"

    explicit_route_type = _route_type_from_prompt(prompt)
    effective_route_type = explicit_route_type or form_route_type
    route_type_overridden = bool(explicit_route_type and _fold(explicit_route_type) != _fold(form_route_type))

    belle_ile_tour = bool(
        _mentions_belle_ile(prompt)
        and effective_route_type == "Boucle"
        and re.search(r"\b(?:faire\s+)?(?:le\s+)?tour\b", _fold(prompt))
    )

    effective_prompt = prompt
    if forced_waypoint:
        marker = f"passer par {forced_waypoint}"
        if _fold(marker) not in _fold(effective_prompt):
            effective_prompt = (effective_prompt + " ; " + marker).strip()[:4000]

    if belle_ile_tour:
        # Keep the ferry/boat as access information only. The hiking geometry
        # must remain on the island. GR 340 is the canonical coastal tour, but
        # "prioritairement" leaves the normal router free to make local safe
        # connections if the relation has a temporary gap in OSM.
        marker = (
            "boucle pédestre entièrement sur Belle-Île-en-Mer ; "
            "suivre prioritairement le GR 340 ; "
            "l'accès maritime est un transport d'accès et ne fait pas partie du tracé pédestre"
        )
        if "gr 340" not in _fold(effective_prompt):
            effective_prompt = (effective_prompt + " ; " + marker).strip()[:4000]

    effective = data.model_copy(update={
        "region": effective_region,
        "prompt": effective_prompt,
        "route_type": effective_route_type,
    })
    meta = {
        "original_region": form_region,
        "effective_region": effective_region,
        "region_overridden": region_overridden,
        "original_route_type": form_route_type,
        "effective_route_type": effective_route_type,
        "route_type_overridden": route_type_overridden,
        "prompt_anchor": anchor_name,
        "forced_waypoint": forced_waypoint,
        "reason": reason,
        "form_region_mentioned_in_prompt": form_in_prompt,
        "after_trip_places": [x["place"] for x in places if x.get("after_trip")],
        "island_access_mode": "transport-then-hike" if belle_ile_tour else None,
        "preferred_trail": "GR 340" if belle_ile_tour else None,
        "endpoint_pair": list(endpoint_pair) if endpoint_pair else None,
    }
    return effective, meta


__all__ = [
    "reconcile_request",
    "_extract_prompt_places",
    "_route_type_from_prompt",
    "_mentions_belle_ile",
]
