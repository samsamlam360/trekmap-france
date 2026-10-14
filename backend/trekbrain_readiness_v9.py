"""Final, evidence-based preparation verdict after every V9 overlay.

A validated hiking backbone survives incomplete logistics. Readiness describes
the requested needs separately from the heuristic quality score and never
changes geometry, measured kilometres, provider evidence or reservations.
"""
from __future__ import annotations

import math
from typing import Any

from fastapi import Body, Depends, HTTPException

from .free_planner_v2 import AIPlanRequest
from .trekbrain_distance_tolerance_v9 import explicit_daily_bounds, intent_daily_bounds
from .trekbrain_water_evidence_v9 import confirmed_water_reference, has_osm_identity

LABELS = {"ready": "Besoins confirmés", "incomplete": "Préparation incomplète", "refused": "Tracé refusé"}


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _rows(value) -> list[dict]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _day(value, maximum: int) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() and 1 <= number <= maximum else None


def _point(value) -> tuple[float, float] | None:
    if isinstance(value, dict):
        lat, lon = _number(value.get("lat")), _number(value.get("lon"))
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        lat, lon = _number(value[0]), _number(value[1])
    else:
        return None
    return (lat, lon) if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 else None


def _distance(a, b) -> float:
    a, b = _point(a), _point(b)
    if a is None or b is None:
        return math.inf
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, h))))


def _requirement(required: bool, status: str, detail: str, missing_days=()) -> dict:
    return {"required": bool(required), "status": status if required else "not_required", "detail": detail, "missing_days": list(missing_days) if required else []}


def _resource_days(result: dict, kind: str, days: int) -> set[int]:
    resources = _dict(result.get("map_resources"))
    points = resources.get("evidence_points")
    if not isinstance(points, list):
        points = resources.get("points")
    covered = set()
    for row in _rows(points):
        if row.get("kind") != kind or _point(row) is None or not has_osm_identity(row):
            continue
        if kind == "water" and not confirmed_water_reference(row):
            continue
        if kind == "food":
            from .trekbrain_resources_v9 import _confirmed_food_reference
            if not _confirmed_food_reference(row):
                continue
        distance = _number(row.get("distance_to_route_km"))
        if distance is None or distance < 0 or distance > (2.8 if kind == "water" else 4.5):
            continue
        day = _day(row.get("route_day"), days)
        if day is not None:
            covered.add(day)
    return covered


def preparation_report(result: dict[str, Any], data=None) -> dict[str, Any]:
    """Assess the final server-produced plan without making external calls."""
    result = _dict(result)
    effective = _dict(result.get("effective_request"))

    def requested(name, default=False):
        return effective.get(name, getattr(data, name, default) if data is not None else default)

    requested_days = _day(requested("days", result.get("duration_days") or len(_rows(result.get("stages"))) or 1), 21)
    days = requested_days or 1
    raw_stages = result.get("stages")
    stages = _rows(result.get("stages"))
    route = _dict(result.get("route_preview"))
    coords = route.get("coords")
    geometric = bool(isinstance(coords, list) and len(coords) >= 2 and all(_point(p) is not None for p in coords)
                     and route.get("fallback") is False and route.get("provisional") is not True)
    if geometric and len({_point(point) for point in coords}) < 2:
        geometric = False
    safety = _dict(result.get("route_safety"))
    if safety.get("safe") is False:
        geometric = False
    requirements, issues, actions = {}, [], []
    refused = not geometric

    def issue(code, requirement, detail, missing=()):
        issues.append({"code": code, "requirement": requirement, "days": list(missing), "detail": detail})

    structural = (geometric and requested_days is not None and isinstance(raw_stages, list)
                  and len(raw_stages) == len(stages) == days
                  and all((_number(row.get("distance_km")) or 0) > 0 for row in stages))
    requirements["route"] = _requirement(True, "confirmed" if structural else "missing", "Tracé pédestre et durée validés." if structural else "Tracé, durée ou distances d’étape non validés.")
    if not structural:
        refused = True
        issue("route_not_validated", "route", requirements["route"]["detail"])

    planner = _dict(result.get("planner"))
    distance = _dict(planner.get("distance_contract"))
    parsed_intent = _dict(planner.get("intent"))
    if data is not None:
        try:
            from .smart_planner_v3 import _parse_intent
            parsed_intent = _parse_intent(data.model_copy(update=effective))
        except (AttributeError, TypeError, ValueError, KeyError):
            pass
    excess = _rows(distance.get("days_exceeding"))
    # Only explicit limits cause refusal. An approximate goal remains distinct
    # from a strict maximum and a longer valid line is honestly incomplete.
    minimum, maximum = intent_daily_bounds(parsed_intent)
    if data is not None:
        minimum, maximum = explicit_daily_bounds(getattr(data, "prompt", ""))
    minimum = _number(distance.get("explicit_daily_min_km", minimum))
    maximum = _number(distance.get("explicit_daily_max_km", maximum))
    explicit = distance.get("explicit_bounds") is True or minimum is not None or maximum is not None
    target = _number(requested("daily_km", distance.get("daily_target_km")))
    if target is not None and not 3 <= target <= 40:
        target = None
    actual = []
    for stage in stages:
        base = _number(stage.get("distance_km"))
        effort = _number(stage.get("estimated_walking_km_with_access"))
        actual.append(max(base, effort) if base is not None and effort is not None else base)
    measured_excess = [i + 1 for i, km in enumerate(actual) if km is not None and target is not None and target > 0
                       and km > target * 1.18 and km - target >= 2.0]
    outside_bounds = [i + 1 for i, km in enumerate(actual) if km is not None and explicit and (
        (maximum is not None and km > maximum + 1e-6) or (minimum is not None and km < minimum - 1e-6))]
    limit_failed = bool(outside_bounds) or (explicit and distance.get("bounds_satisfied") is False)
    lower = _rows(distance.get("days_below_minimum"))
    excess_days = sorted({day for row in excess + lower if (day := _day(row.get("day"), days)) is not None})
    excess_days = sorted(set(excess_days + measured_excess + outside_bounds))
    requirements["distance"] = _requirement(True, "missing" if limit_failed else "partial" if excess_days else "unknown" if target is None else "confirmed", "Limite quotidienne explicite non respectée." if limit_failed else "Des journées dépassent sensiblement l’objectif demandé." if excess_days else "Objectif de distance inconnu." if target is None else "Distances compatibles avec la demande.", excess_days)
    if limit_failed or excess_days:
        refused = refused or limit_failed
        issue("distance_limit_exceeded" if limit_failed else "distance_target_exceeded", "distance", requirements["distance"]["detail"], excess_days)
        for suggestion in _rows(distance.get("suggestions")):
            changes = {key: value for key, value in _dict(suggestion.get("changes")).items() if key in {"days", "daily_km"} and _number(value) is not None}
            if changes:
                changes = {key: value for key, value in changes.items() if (
                    _day(value, 21) is not None if key == "days" else 3 <= float(value) <= 40)}
            if changes:
                actions.append({"type": "edit_request", "requirement": "distance", "label": "Adapter la durée" if "days" in changes else "Adapter la distance quotidienne", "detail": "Cette proposition exige un nouveau calcul et une nouvelle validation du parcours.", "suggested_changes": changes})
    if target is None:
        issue("distance_goal_unknown", "distance", "L’objectif quotidien doit être précisé avant de confirmer les distances.")

    coverage = _dict(_dict(result.get("map_resources")).get("coverage"))
    for kind, flag, label in (("water", "require_water", "eau potable référencée"), ("food", "require_food", "ravitaillement sourcé")):
        required = bool(requested(flag))
        covered = _resource_days(result, kind, days) if required else set()
        missing = [day for day in range(1, days+1) if day not in covered] if required else []
        unavailable = coverage.get(kind) == "providers_unavailable"
        status = "confirmed" if not missing else "partial" if covered else "unknown" if unavailable else "missing"
        detail = f"{label.capitalize()} sur chaque journée." if not missing else f"{label.capitalize()} non confirmé(e) pour les jours " + ", ".join(map(str, missing)) + (" ; fournisseurs indisponibles." if unavailable else ".")
        requirements[kind] = _requirement(required, status, detail, missing)
        if missing:
            issue(f"{kind}_unverified", kind, detail, missing)

    sleep = bool(requested("require_accommodation")) and days > 1
    nights = _rows(_dict(result.get("logistics")).get("nights"))
    by_night = {}
    for night in nights:
        day = _day(night.get("night"), days-1)
        if day is not None:
            by_night.setdefault(day, []).append(night)
    missing_nights, transfers = [], []
    for day in range(1, days) if sleep else []:
        candidates = by_night.get(day, [])
        if len(candidates) != 1:
            missing_nights.append(day)
            continue
        night = candidates[0]
        sourced = has_osm_identity(night) and _point(night) is not None
        connector = _dict(night.get("walking_connector"))
        outward = _number(connector.get("distance_km"))
        returning = _number(connector.get("return_distance_km"))
        walk = (sourced and night.get("status") == "confirmed" and night.get("access_mode") == "walk"
                and connector.get("validated") is True and connector.get("return_validated") is True
                and outward is not None and outward >= 0 and returning is not None and returning >= 0)
        transfer = sourced and night.get("status") == "usable_with_transfer" and night.get("transfer_confirmed") is True
        if not walk and not transfer:
            missing_nights.append(day)
            if night.get("access_mode") == "transfer":
                transfers.append(day)
    sleep_status = "confirmed" if not missing_nights else "partial" if len(missing_nights) < days-1 else "missing"
    sleep_detail = "Hébergements sourcés et accès aller-retour validés pour chaque nuit." if not missing_nights else "Nuitées ou accès non confirmés aux soirs " + ", ".join(map(str, missing_nights)) + "."
    requirements["accommodation"] = _requirement(sleep, sleep_status, sleep_detail, missing_nights)
    if missing_nights:
        issue("overnight_unresolved", "accommodation", sleep_detail, missing_nights)
    if transfers:
        issue("transfer_unconfirmed", "accommodation", "Transfert aller-retour à organiser et confirmer.", transfers)

    transit = bool(requested("require_transit"))
    transport = _dict(result.get("transport"))
    confirmed_access = []
    for field, anchor in (("outbound_point", result.get("start")), ("return_point", result.get("end"))):
        point = _dict(transport.get(field))
        confirmed_access.append(bool(has_osm_identity(point) and _point(point) is not None and _distance(anchor, point) <= 8.0))
    transit_status = "confirmed" if all(confirmed_access) else "partial" if any(confirmed_access) else "missing"
    requirements["transit"] = _requirement(transit, transit_status, "Accès de départ et d’arrivée cartographiés ; horaires et desserte restent à vérifier." if all(confirmed_access) else "Accès en transport non localisé ou trop éloigné au départ ou à l’arrivée.")
    if transit and not all(confirmed_access):
        issue("transit_unverified", "transit", requirements["transit"]["detail"])

    quality = _dict(_dict(result.get("trekbrain")).get("quality"))
    blockers = [str(value) for value in quality.get("blockers", []) if value] if isinstance(quality.get("blockers"), list) else []
    if any(not row.get("satisfied") for row in _rows(result.get("side_requests"))
           if row.get("required") or row.get("target_date") or row.get("preferred_day")):
        blockers = list(dict.fromkeys(blockers + ["objectif obligatoire non satisfait"]))
    critical = {"durée différente de la demande", "distances manquantes ou invalides", "distance maximale dépassée", "routage dégradé", "boucle mal refermée", "fermeture de boucle invérifiable"}
    if any(blocker in critical for blocker in blockers):
        refused = True
    requirements["objectives"] = _requirement(bool(blockers), "missing" if blockers else "confirmed", "; ".join(blockers) if blockers else "Aucun objectif obligatoire signalé comme manquant.")
    if blockers:
        issue("required_objective_unmet", "objectives", "Objectif ou contrôle non satisfait : " + "; ".join(blockers))
    score = _number(quality.get("score"))
    if score is not None and score < 60 and not blockers:
        issue("audit_fragile", "audit", f"Audit fragile ({score:.1f}/100) : la proposition demande une vérification supplémentaire.")

    status = "refused" if refused else "incomplete" if issues else "ready"
    labels = {"water": "Adapter les étapes pour l’eau", "food": "Adapter les étapes pour le ravitaillement", "accommodation": "Adapter les étapes ou les nuitées", "transit": "Préciser les accès en transport", "objectives": "Préciser les objectifs manquants", "route": "Modifier la demande", "audit": "Préciser la demande"}
    existing = {action.get("requirement") for action in actions}
    for entry in issues:
        requirement = entry["requirement"]
        if requirement not in existing:
            actions.append({"type": "edit_request", "requirement": requirement, "label": labels.get(requirement, "Adapter la distance ou la durée"), "detail": entry["detail"]})
            existing.add(requirement)
    return {"version": 1, "status": status, "label": LABELS[status], "route_validated": geometric,
            "requirements": requirements, "issues": issues, "actions": actions,
            "meaning": "Confirmation des références cartographiques et contraintes calculées ; ouverture, horaires et état réel restent à vérifier."}


def annotate_preparation(result: dict, data=None) -> dict:
    if not isinstance(result, dict):
        return result
    report = preparation_report(result, data)
    result["trip_readiness"] = report
    summary = result.setdefault("decision_summary", {})
    if isinstance(summary, dict):
        summary["preparation_status"] = report["status"]
        summary["preparation_label"] = report["label"]
        summary["preparation_issues"] = report["issues"]
        important = [entry["detail"] for entry in report["issues"]]
        previous = summary.get("important")
        previous = [str(value) for value in previous] if isinstance(previous, list) else []
        summary["important"] = list(dict.fromkeys(important + previous))
    return result


def install_preparation_overlay(app, legacy_main) -> None:
    """Run after safety, resources and effective-request reconciliation."""
    original = next(route for route in app.router.routes if getattr(route, "path", None) == "/ai/plan" and "POST" in getattr(route, "methods", set()))
    endpoint = original.endpoint
    app.router.routes = [route for route in app.router.routes if route is not original]

    @app.post("/ai/plan")
    def prepared(data: AIPlanRequest = Body(...), user=Depends(legacy_main.current_user)):
        try:
            result = endpoint(data, user)
        except HTTPException as exc:
            detail = dict(exc.detail) if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            message = str(detail.get("message") or "Le tracé n’a pas été validé.")
            detail["trip_readiness"] = {"version": 1, "status": "refused", "label": LABELS["refused"], "route_validated": False,
                                      "requirements": {"route": _requirement(True, "missing", message)},
                                      "issues": [{"code": "route_not_validated", "requirement": "route", "days": [], "detail": message}],
                                      "actions": [{"type": "edit_request", "requirement": "route", "label": "Modifier la demande", "detail": message}]}
            raise HTTPException(status_code=exc.status_code, detail=detail, headers=exc.headers) from exc
        return annotate_preparation(result, data)


__all__ = ["preparation_report", "annotate_preparation", "install_preparation_overlay"]
