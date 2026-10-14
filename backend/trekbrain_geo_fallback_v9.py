"""France-wide independent geocoding fallback for a throttled OSM provider.

IGN Géoplateforme serves BAN/BD TOPO location data over a public endpoint.
It is used only when Nominatim and Photon cannot provide a usable place.
Never convert a geocoder centre into a pedestrian route without ORS validation.
"""
from __future__ import annotations

import math
import re
import unicodedata
from contextvars import ContextVar, Token
from copy import deepcopy

from . import free_planner_v2 as geo

IGN_GEOCODAGE_URL = "https://data.geopf.fr/geocodage/search"
_IGN_STOPWORDS = {"france", "de", "du", "des", "le", "la", "les", "l", "d", "en", "au", "aux"}
_GEOCODE_TRACE: ContextVar[tuple[dict, ...] | None] = ContextVar("trekbrain_geocode_trace", default=None)
_TRACE_LIMIT = 160


def begin_geocode_trace() -> Token:
    """Open a fresh diagnostic scope, including request reconciliation."""
    return _GEOCODE_TRACE.set(())


def geocode_trace_snapshot() -> dict:
    events = _GEOCODE_TRACE.get() or ()
    return {"queries": deepcopy(list(events[:_TRACE_LIMIT])), "truncated": len(events) > _TRACE_LIMIT}


def end_geocode_trace(token: Token) -> dict:
    snapshot = geocode_trace_snapshot()
    _GEOCODE_TRACE.reset(token)
    return snapshot


def query_parts(query: str) -> tuple[str, str | None]:
    """Keep an explicit geographical qualifier without guessing its identity."""
    pieces = [part.strip() for part in str(query or "").split(",") if part.strip()]
    if pieces and _fold(pieces[-1]) == "france":
        pieces.pop()
    return (pieces[0] if pieces else "", pieces[1] if len(pieces) == 2 else None)


def record_geocode(query: str, provider: str, *, accepted: bool, reason: str,
                   point: dict | None = None, selected: bool = False) -> None:
    """Record only public geographical evidence, never raw provider payloads."""
    current = _GEOCODE_TRACE.get()
    if current is None or len(current) > _TRACE_LIMIT:
        return
    entry = {"query": str(query or "")[:200], "provider": provider,
             "accepted": bool(accepted), "selected": bool(selected), "reason": reason}
    _, qualifier = query_parts(query)
    if qualifier:
        entry["requested_department"] = qualifier
    if point:
        entry["name"] = str(point.get("name") or point.get("short_name") or "")[:300]
        try:
            lat, lon = float(point["lat"]), float(point["lon"])
            if math.isfinite(lat) and math.isfinite(lon):
                entry["coordinates"] = [lat, lon]
        except (KeyError, TypeError, ValueError):
            pass
        if point.get("department_code"):
            entry["department_code"] = str(point["department_code"])
        if point.get("geocode_department"):
            entry["department"] = str(point["geocode_department"])
    # The resolver may first validate an IGN feature, then select it. Keep one
    # event for that candidate and preserve its verified administrative fields.
    if selected:
        for index in range(len(current) - 1, -1, -1):
            old = current[index]
            if (old.get("query") == entry["query"] and old.get("provider") == provider
                    and old.get("coordinates") == entry.get("coordinates") and old.get("accepted")):
                updated = dict(old, selected=True)
                _GEOCODE_TRACE.set(current[:index] + (updated,) + current[index + 1:])
                return
    _GEOCODE_TRACE.set(current + (entry,))


def _same_area(rows: list[dict], *, max_distance_km: float = 2.0) -> bool:
    if len(rows) < 2:
        return True
    return all(geo._dist(rows[0], row) <= max_distance_km for row in rows[1:])


def filter_provider_places(query: str, rows: list[dict], provider: str) -> list[dict]:
    """Reject wrong departments and separate homonyms before choosing a row.

    Nominatim/Photon have already normalized their records. Their public labels
    remain usable evidence for a written department; missing evidence is never
    replaced by a score or a known regional centre.
    """
    landmark, qualifier = query_parts(query)
    wanted = _words(landmark)
    # These are *regions*, never departments. Their existing reference centres
    # are used only to reject far-away provider points, NEVER as hiking starts.
    # Jura/Vosges/Cantal deliberately stay subject to department validation.
    area_names = {"morvan", "cevennes", "queyras", "vercors", "chartreuse",
                  "beaufortain", "sancy", "mercantour", "ecrins", "bauges",
                  "aravis", "belledonne", "vanoise", "aubrac", "verdon"}
    region_hint = geo.KNOWN_CENTRES.get(_fold(qualifier)) if qualifier and _fold(qualifier) in area_names else None
    accepted = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        point = dict(raw)
        reason = None
        try:
            lat, lon = float(point["lat"]), float(point["lon"])
            valid = math.isfinite(lat) and math.isfinite(lon) and 41.0 <= lat <= 51.6 and -5.6 <= lon <= 10.0
        except (KeyError, ValueError, TypeError):
            valid = False
        if not valid:
            reason = "invalid_coordinates"
        label = str(point.get("name") or point.get("short_name") or "")
        if qualifier and not reason:
            if region_hint is not None:
                # A provider's named, located feature must be inside the
                # supplied massif, not merely in France. The centre never
                # substitutes for missing provider evidence.
                reference = {"lat": region_hint[0], "lon": region_hint[1]}
                if geo._dist(reference, point) > 75.0:
                    reason = "outside_named_region"
                elif wanted and not wanted.issubset(_words(label)):
                    reason = "name_mismatch"
                elif (provider == "ign-geoplateforme"
                      and not _fold(point.get("short_name") or "").startswith(_fold(landmark))):
                    # The IGN address index often responds with an unrelated
                    # street *in* the requested village, not the village itself.
                    reason = "name_mismatch"
            else:
                if re.fullmatch(r"(?:[0-9]{2,3}|2[abAB])", qualifier):
                    matches_department = str(point.get("department_code") or "").upper() == qualifier.upper()
                else:
                    labels = {_fold(part) for part in label.split(",")}
                    labels.add(_fold(point.get("geocode_department") or ""))
                    matches_department = _fold(qualifier) in labels
                if not matches_department:
                    reason = "department_not_confirmed"
                elif wanted and not wanted.issubset(_words(label)):
                    reason = "name_mismatch"
        if reason:
            record_geocode(query, provider, accepted=False, reason=reason, point=point)
            continue
        point["geocode_provider"] = point.get("geocode_provider") or provider
        accepted.append(point)
    matching_names = [p for p in accepted if wanted and wanted.issubset(
        _words(p.get("short_name") or str(p.get("name") or "").split(",")[0]))]
    if not _same_area(matching_names):
        # Discard roads whose names merely contain the requested landmark.
        exact = [p for p in matching_names
                 if _fold(p.get("short_name") or "") == _fold(landmark)]
        if exact:
            matching_names = exact
        if not _same_area(matching_names) and provider == "nominatim":
            # Nominatim frequently returns both a named city place node and
            # a distant administrative polygon centroid. The place node is
            # a real, provider-referenced geographic feature, not a guess.
            places = [p for p in matching_names
                      if p.get("geocode_osm_type") == "node"
                      and p.get("geocode_osm_class") == "place"
                      and p.get("geocode_osm_subtype") in
                      {"city", "town", "village", "hamlet", "locality"}]
            if len(places) == 1:
                matching_names = places
        if not matching_names or not _same_area(matching_names):
            for point in accepted:
                record_geocode(query, provider, accepted=False, reason="ambiguous_homonyms", point=point)
            return []
        accepted = matching_names
    for point in accepted:
        record_geocode(query, provider, accepted=True, reason="provider_match", point=point)
    if not rows:
        record_geocode(query, provider, accepted=False, reason="empty_result")
    return accepted


def _words(text: str) -> set[str]:
    normal = unicodedata.normalize("NFKD", str(text or ""))
    normal = "".join(c for c in normal if not unicodedata.combining(c)).casefold()
    return {word for word in re.findall(r"[a-z0-9]+", normal)
            if len(word) >= 2 and word not in _IGN_STOPWORDS}


def _department_code(props: dict) -> str | None:
    raw = props.get("depcode") or props.get("department_code") or props.get("codeDepartement")
    if isinstance(raw, list):
        raw = raw[0] if len(raw) == 1 else None
    if raw:
        return str(raw).upper()
    for field in ("citycode", "postcode"):
        value = str(props.get(field) or "").upper()
        if re.fullmatch(r"(?:[0-9]{5}|2[AB][0-9]{3})", value):
            if value.startswith("20"):
                continue  # Postal code 20 alone cannot distinguish Corsica.
            return value[:3] if value.startswith(("97", "98")) else value[:2]
    return None


def _ign_evidence(label: str, props: dict, coords, department: str | None = None) -> dict:
    point = {"name": label}
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        point.update(lon=coords[0], lat=coords[1])
    code = _department_code(props)
    if code:
        point["department_code"] = code
    if department:
        point["geocode_department"] = department
    return point


def geocode_ign(query: str, *, timeout: float = 2.5) -> list[dict]:
    """Use a real French geocoder, rejecting unrelated address suggestions.

    BAN address search can return a street with a similar word in a different
    city. Require most significant query tokens to occur in label/context; this
    fallback must never quietly move a hike to another department.
    """
    query = str(query or "").strip()
    words = _words(query)
    if not query or not words:
        record_geocode(query, "ign-geoplateforme", accepted=False, reason="empty_query")
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
        label = str(props.get("label") or props.get("name") or "").strip()
        evidence = _ign_evidence(label, props, coords)
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            record_geocode(query, "ign-geoplateforme", accepted=False, reason="invalid_coordinates", point=evidence)
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            record_geocode(query, "ign-geoplateforme", accepted=False, reason="invalid_coordinates", point=evidence)
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)
                and 41.0 <= lat <= 51.6 and -5.6 <= lon <= 10.0):
            record_geocode(query, "ign-geoplateforme", accepted=False, reason="invalid_coordinates", point=evidence)
            continue
        context = " ".join(str(props.get(k) or "") for k in ("city", "context", "postcode"))
        matches = words & _words(label + " " + context)
        if len(matches) < max(1, math.ceil(len(words) * 0.70)):
            record_geocode(query, "ign-geoplateforme", accepted=False, reason="name_mismatch", point=evidence)
            continue
        if props.get("score") is not None:
            try:
                if float(props["score"]) < 0.35:
                    record_geocode(query, "ign-geoplateforme", accepted=False, reason="low_score", point=evidence)
                    continue
            except (TypeError, ValueError):
                record_geocode(query, "ign-geoplateforme", accepted=False, reason="invalid_score", point=evidence)
                continue
        name = ", ".join(x for x in (label, str(props.get("context") or "").strip()) if x)
        point = geo._normalise_place(name or query, lat, lon)
        point["geocode_provider"] = "ign-geoplateforme"
        if evidence.get("department_code"):
            point["department_code"] = evidence["department_code"]
        _, qualifier = query_parts(query)
        if qualifier and _fold(qualifier) in {_fold(x) for x in str(props.get("context") or "").split(",")}:
            point["geocode_department"] = qualifier
        # A commune and several streets bearing its name may be kilometres
        # apart. A street must not turn one verified municipality into a false
        # "ambiguous homonyms" error. Only an explicitly typed municipality
        # with the exact city name and official INSEE code gets this priority.
        # It still passes the normal department and homonym safety checks.
        landmark, _ = query_parts(query)
        if (str(props.get("type") or "").casefold() == "municipality"
                and _fold(props.get("city") or "") == _fold(landmark)
                and str(props.get("citycode") or "").strip()):
            point["geocode_precision"] = "official-municipality"
            point["commune_insee"] = str(props["citycode"])
        rows.append(point)
    municipalities = [point for point in rows
                      if point.get("geocode_precision") == "official-municipality"]
    if municipalities:
        # A genuine municipality may coexist with multiple street matches.
        # But two different official INSEE codes remain ambiguous.
        codes = {point["commune_insee"] for point in municipalities}
        if len(codes) == 1:
            verified = filter_provider_places(query, municipalities, "ign-geoplateforme")
            if verified:
                return verified
    return filter_provider_places(query, rows, "ign-geoplateforme")


DEPARTMENTS_URL = "https://geo.api.gouv.fr/departements"


def _fold(text: str) -> str:
    """Accented French labels and official department names, normalized."""
    normal = unicodedata.normalize("NFKD", str(text or ""))
    normal = "".join(c for c in normal if not unicodedata.combining(c)).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", normal))


def geocode_ign_poi(query: str, *, timeout: float = 2.5) -> list[dict]:
    """Resolve a named French landmark in an **explicit** department.

    A common landmark name such as "Lac Blanc" exists in multiple mountain
    ranges. IGN's POI index must therefore be constrained both in the query and
    in each returned feature to the exact officially resolved department.
    No department = no guessed position. Route network validation still applies.
    """
    pieces = [x.strip() for x in str(query or "").split(",") if x.strip()]
    if pieces and _fold(pieces[-1]) == "france":
        pieces.pop()
    if len(pieces) != 2:
        record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="department_required")
        return []
    landmark, department = pieces
    wanted = _words(landmark)
    if not wanted or len(_fold(landmark)) < 3:
        record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="empty_landmark")
        return []
    if not re.fullmatch(r"[a-zA-ZÀ-ÿ0-9 '\-]+", department):
        record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="invalid_department")
        return []
    budget = min(3.0, max(0.8, float(timeout)))

    # The official department lookup is exact, not a fuzzy geographical guess.
    # A code (68, 2A, 2B...) may be supplied instead of a written name.
    if re.fullmatch(r"(?:[0-9]{2,3}|2[abAB])", department):
        code = department.upper()
    else:
        official = geo._request_json(
            DEPARTMENTS_URL,
            params={"nom": department, "fields": "nom,code", "format": "json"},
            timeout=budget, ttl=43200,
            service="Départements français", retries=1, cache_empty=False,
        )
        found = {
            str(item.get("code") or "").upper()
            for item in official if isinstance(official, list) and isinstance(item, dict)
            and _fold(item.get("nom") or "") == _fold(department)
        }
        if len(found) != 1:
            record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="department_not_resolved")
            return []
        code = next(iter(found))
    if not code:
        return []

    payload = geo._request_json(
        IGN_GEOCODAGE_URL,
        params={"q": landmark, "index": "poi", "depcode": code, "limit": 8},
        timeout=budget, ttl=43200,
        service="IGN Géoplateforme POI", retries=1, cache_empty=False,
    )
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="invalid_response")
        return []

    accepted = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            continue
        raw_label = props.get("toponym") or props.get("name") or ""
        if isinstance(raw_label, list):
            raw_label = raw_label[0] if raw_label else ""
        label = str(raw_label).strip()
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        evidence = _ign_evidence(label, props, coords)
        returned_codes = props.get("depcode") or []
        if isinstance(returned_codes, str):
            returned_codes = [returned_codes]
        if not isinstance(returned_codes, list) or code not in {
            str(x).upper() for x in returned_codes
        }:
            record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="wrong_department", point=evidence)
            continue
        # Every meaningful place-name token must be present in the feature's
        # actual toponym. Matching "Jura" only in its address is not sufficient.
        if not label or not wanted.issubset(_words(label)):
            record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="name_mismatch", point=evidence)
            continue
        try:
            score = float(props.get("score") or 0)
        except (ValueError, TypeError):
            record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="invalid_score", point=evidence)
            continue
        if not math.isfinite(score) or score < 0.55:
            record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="low_score", point=evidence)
            continue
        if not isinstance(coords, (tuple, list)) or len(coords) < 2:
            record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="invalid_coordinates", point=evidence)
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (ValueError, TypeError):
            record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="invalid_coordinates", point=evidence)
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)
                and 41.0 <= lat <= 51.6 and -5.6 <= lon <= 10.0):
            record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="invalid_coordinates", point=evidence)
            continue
        point = geo._normalise_place(f"{label}, {department}, France", lat, lon)
        point["geocode_provider"] = "ign-bdtopo-poi"
        point["department_code"] = code
        point["geocode_department"] = department
        point["geocode_precision"] = "named-poi"
        point["geocode_score"] = round(score, 3)
        # Full-name matches such as "Lac Blanc" outrank nearby visitor centres.
        same_name = _fold(label) == _fold(landmark)
        accepted.append((0 if same_name else 1, -score, point))
    accepted.sort(key=lambda row: (row[0], row[1]))
    # Scores rank spellings, not spatially separate homonyms. Refuse two
    # equally named sites in the same department instead of guessing the first.
    if accepted:
        strongest = [row[2] for row in accepted if row[0] == accepted[0][0]]
        if not _same_area(strongest):
            for _, _, point in accepted:
                record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="ambiguous_homonyms", point=point)
            return []
        for _, _, point in accepted:
            record_geocode(query, "ign-bdtopo-poi", accepted=True, reason="name_and_department_match", point=point)
    else:
        record_geocode(query, "ign-bdtopo-poi", accepted=False, reason="empty_result")
    return [row[2] for row in accepted]


__all__ = ["geocode_ign", "geocode_ign_poi", "IGN_GEOCODAGE_URL", "DEPARTMENTS_URL",
           "begin_geocode_trace", "end_geocode_trace", "geocode_trace_snapshot",
           "record_geocode", "filter_provider_places", "query_parts"]
