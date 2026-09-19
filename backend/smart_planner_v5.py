"""TrekMap Planner v5: long French requests + dated side objectives.

Still zero-cost on the planning side. It keeps the v3 route engine, the v4
personal language learning, and adds compound-intent planning. Optional dated
event verification uses DATAtourisme when DATATOURISME_API_KEY is configured.
"""
from __future__ import annotations

import math
import os
import re
from contextvars import ContextVar
from datetime import date, timedelta
from typing import Any

from fastapi import Depends, HTTPException

from . import smart_planner_v3 as v3
from .compound_language_v5 import extract_side_requests, semantic_summary
from .language_engine import (
    LanguageLesson,
    delete_rule,
    ensure_language_schema,
    extract_inline_lesson,
    learn_rule,
    list_rules,
    mark_rules_used,
    normalize_for_planner,
    fold,
)
from .tourism_events import configured as events_configured, search_events

PLANNER_VERSION = "trekmap-language-planner-v5"
_BASE_PARSE_INTENT = v3._parse_intent
_RULES: ContextVar[list[dict[str, Any]]] = ContextVar("trekmap_v5_language_rules", default=[])
_MATCHES: ContextVar[list[str]] = ContextVar("trekmap_v5_language_matches", default=[])
_COMPOUND: ContextVar[dict[str, Any]] = ContextVar("trekmap_v5_compound", default={})

CATEGORY_TERMS = {
    "castle": "chateau patrimoine historique",
    "village": "village typique",
    "event": "village patrimoine",
    "lake": "lac",
    "waterfall": "cascade",
    "peak": "sommet panorama",
    "heritage": "patrimoine monument historique",
    "food_local": "village ravitaillement",
}

OSM_FILTERS = {
    "castle": ['nwr["historic"="castle"]', 'nwr["historic"="fort"]'],
    "village": ['nwr["place"="village"]', 'nwr["place"="town"]'],
    "lake": ['nwr["natural"="water"]["water"~"lake|reservoir|pond"]'],
    "waterfall": ['nwr["natural"="waterfall"]'],
    "peak": ['nwr["natural"="peak"]'],
    "heritage": ['nwr["historic"]', 'nwr["tourism"="attraction"]["name"]'],
}


def _language_parse_intent(data):
    rules = _RULES.get()
    normalized, matches = normalize_for_planner(data.prompt, rules)
    compound = extract_side_requests(normalized)
    _MATCHES.set(matches)
    _COMPOUND.set(compound)

    semantic_terms = []
    for req in compound.get("side_requests") or []:
        term = CATEGORY_TERMS.get(req.get("kind"))
        if term:
            semantic_terms.append(term)
    enriched = normalized + (" " + " ".join(semantic_terms) if semantic_terms else "")
    intent = _BASE_PARSE_INTENT(data.model_copy(update={"prompt": enriched}))
    intent["language_matches"] = matches
    intent["normalized_prompt"] = normalized
    intent["compound"] = compound

    # Secondary objectives should affect route scoring even when no exact POI can
    # be resolved. v3 already understands these categories.
    boosts = {
        "castle": ("heritage", 8.0), "heritage": ("heritage", 7.0),
        "village": ("village", 7.0), "event": ("village", 7.5),
        "lake": ("lake", 8.0), "waterfall": ("waterfall", 8.0),
        "peak": ("peak", 8.0),
    }
    for req in compound.get("side_requests") or []:
        pair = boosts.get(req.get("kind"))
        if pair:
            intent["priorities"][pair[0]] = max(intent["priorities"].get(pair[0], 0), pair[1])
    return intent


# v3 resolves its parser from module globals when building a plan.
v3._parse_intent = _language_parse_intent


def _safe_rules(legacy_main, user_id: int) -> list[dict[str, Any]]:
    try:
        ensure_language_schema(legacy_main)
        return list_rules(legacy_main, user_id)
    except Exception:
        return []


def _osm_special(center: dict[str, Any], kind: str, radius_km: float = 28) -> list[dict[str, Any]]:
    filters = OSM_FILTERS.get(kind) or []
    if not filters:
        return []
    radius = max(1000, min(int(radius_km * 1000), 40000))
    clauses = [f"{flt}(around:{radius},{center['lat']},{center['lon']});" for flt in filters]
    query = "[out:json][timeout:18];(" + "".join(clauses) + ");out center tags 60;"
    try:
        data = v3._overpass(query)
    except Exception:
        return []
    out, seen = [], set()
    for e in data.get("elements") or []:
        tags = e.get("tags") or {}
        lat, lon = e.get("lat"), e.get("lon")
        if lat is None or lon is None:
            c = e.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        name = str(tags.get("name") or tags.get("ref") or "").strip()
        if not name:
            continue
        key = (round(lat, 5), round(lon, 5), name.casefold())
        if key in seen:
            continue
        seen.add(key)
        item = {
            "name": name,
            "lat": lat,
            "lon": lon,
            "kind": kind,
            "source": "OpenStreetMap",
            "source_url": f"https://www.openstreetmap.org/{e.get('type','node')}/{e.get('id')}",
        }
        out.append(item)
    out.sort(key=lambda x: v3._dist(center, x))
    return out[:12]


def _nearest_village(point: dict[str, Any], radius_km: float = 6) -> dict[str, Any] | None:
    villages = _osm_special(point, "village", radius_km)
    return villages[0] if villages else None


def _event_target(center: dict[str, Any], req: dict[str, Any]) -> dict[str, Any] | None:
    raw = req.get("target_date")
    if not raw or not events_configured():
        return None
    try:
        target_date = date.fromisoformat(raw)
    except ValueError:
        return None
    try:
        events = search_events(center["lat"], center["lon"], target_date, radius_km=30)
    except Exception:
        return None
    if not events:
        return None
    event_words = ("fete", "festival", "foire", "brocante", "bal", "concert", "marche")
    ranked = []
    for event in events:
        name_fold = fold(event.get("name") or "")
        relevance = 0 if any(w in name_fold for w in event_words) else 4
        relevance += v3._dist(center, event) / 12
        ranked.append((relevance, event))
    event = min(ranked, key=lambda x: x[0])[1]
    target = dict(event)
    target["kind"] = "event"
    village = _nearest_village(target)
    if village:
        target["village_name"] = village["name"]
    return target


def _resolve_targets(location: str, center: dict[str, Any], compound: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    targets, notes = [], []
    for req in compound.get("side_requests") or []:
        kind = req.get("kind")
        target = None
        if kind == "event":
            target = _event_target(center, req)
            if req.get("target_date") and not events_configured():
                notes.append(
                    f"J’ai compris la demande d’événement du {req['target_date']}, mais aucune source d’agenda n’est configurée pour la vérifier."
                )
            elif req.get("target_date") and target is None:
                notes.append(f"Aucun événement vérifié n’a été trouvé près de {location} pour le {req['target_date']}.")
        elif kind in OSM_FILTERS:
            candidates = _osm_special(center, kind)
            target = candidates[0] if candidates else None

        if target:
            enriched = dict(target)
            enriched["request"] = req
            targets.append(enriched)
        elif kind != "event":
            notes.append(f"Demande « {req.get('text','')} » comprise, mais aucun lieu suffisamment fiable n’a été trouvé pour la forcer dans le tracé.")
    return targets[:6], notes


def _route_distance_to_target(coords: list[list[float]], target: dict[str, Any]) -> tuple[float, float]:
    if not coords:
        return float("inf"), 0.0
    stride = max(1, len(coords) // 900)
    best_d, best_i = float("inf"), 0
    t = {"lat": target["lat"], "lon": target["lon"]}
    for i in range(0, len(coords), stride):
        p = {"lat": coords[i][0], "lon": coords[i][1]}
        d = v3._dist(t, p)
        if d < best_d:
            best_d, best_i = d, i
    if (len(coords) - 1) % stride:
        p = {"lat": coords[-1][0], "lon": coords[-1][1]}
        d = v3._dist(t, p)
        if d < best_d:
            best_d, best_i = d, len(coords) - 1
    progress = best_i / max(1, len(coords) - 1)
    return best_d, progress


def _desired_day(req: dict[str, Any], compound: dict[str, Any], days: int) -> int | None:
    if req.get("preferred_day"):
        return max(1, min(int(req["preferred_day"]), days))
    target_date = req.get("target_date")
    start_date = (compound.get("dates") or {}).get("start_date")
    if target_date and start_date:
        try:
            delta = (date.fromisoformat(target_date) - date.fromisoformat(start_date)).days + 1
            if 1 <= delta <= days:
                return delta
        except ValueError:
            pass
    return None


def _score_side_requests(result: dict[str, Any], targets: list[dict[str, Any]], compound: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    coords = (result.get("route_preview") or {}).get("coords") or []
    days = max(1, int(result.get("duration_days") or len(result.get("stages") or []) or 1))
    penalty = 0.0
    statuses = []
    for target in targets:
        req = target.get("request") or {}
        dist, progress = _route_distance_to_target(coords, target)
        route_day = min(days, max(1, int(math.floor(progress * days)) + 1))
        threshold = 2.2 if target.get("kind") != "event" else 3.0
        satisfied = dist <= threshold
        weight = 3.2 if req.get("required") else 1.4
        if not satisfied:
            penalty += weight * min(45.0, 12 + max(0, dist - threshold) * 3)
        desired = _desired_day(req, compound, days)
        if desired:
            penalty += abs(route_day - desired) * (13 if req.get("required") else 6)
        statuses.append({
            "kind": target.get("kind"),
            "request": req.get("text"),
            "name": target.get("name"),
            "route_day": route_day,
            "preferred_day": desired,
            "target_date": req.get("target_date"),
            "distance_to_route_km": round(dist, 2),
            "satisfied": satisfied and (desired is None or abs(route_day - desired) <= 1),
            "source": target.get("source"),
            "source_url": target.get("source_url"),
            "village_name": target.get("village_name"),
        })
    return penalty, statuses


def _candidate_prompts(normalized: str, targets: list[dict[str, Any]], compound: dict[str, Any]) -> list[str]:
    semantic = " ".join(CATEGORY_TERMS.get(req.get("kind"), "") for req in compound.get("side_requests") or [])
    base = (normalized + " " + semantic).strip()
    ranked = sorted(
        targets,
        key=lambda t: (
            0 if (t.get("request") or {}).get("target_date") else 1,
            0 if (t.get("request") or {}).get("required") else 1,
            0 if (t.get("request") or {}).get("preferred_day") else 1,
        ),
    )
    prompts = [base]
    for target in ranked[:2]:
        prompts.append(base + f" ; passer par {target['name']}")
    return list(dict.fromkeys(prompts))[:3]


def _build(data, legacy_main, user_id: int):
    rules = _safe_rules(legacy_main, user_id)
    lesson = extract_inline_lesson(data.prompt)
    if lesson:
        try:
            ensure_language_schema(legacy_main)
            learn_rule(legacy_main, user_id, lesson[0], lesson[1])
            rules = list_rules(legacy_main, user_id)
        except Exception:
            pass

    normalized, matches = normalize_for_planner(data.prompt, rules)
    compound = extract_side_requests(normalized)
    location = v3._location(data)
    geo = v3._geocode(f"{location}, France") or v3._geocode(location)
    if not geo:
        raise HTTPException(status_code=422, detail=f"Impossible de localiser « {location} ».")
    center = geo[0]
    targets, resolution_notes = _resolve_targets(location, center, compound)

    rules_token = _RULES.set(rules)
    matches_token = _MATCHES.set(matches)
    compound_token = _COMPOUND.set(compound)
    candidates = []
    try:
        for prompt in _candidate_prompts(normalized, targets, compound):
            candidate_data = data.model_copy(update={"prompt": prompt})
            try:
                result = v3._build(candidate_data, legacy_main)
            except HTTPException:
                continue
            penalty, statuses = _score_side_requests(result, targets, compound)
            # Keep distance/difficulty quality from v3, but strongly prefer plans
            # that actually go near the requested side objectives.
            base_conf = float((result.get("confidence") or {}).get("score") or 0)
            candidates.append((penalty - base_conf * 0.08, result, statuses))
    finally:
        _RULES.reset(rules_token)
        _MATCHES.reset(matches_token)
        _COMPOUND.reset(compound_token)

    if not candidates:
        raise HTTPException(status_code=422, detail="Je n’ai pas trouvé de parcours cohérent avec l’ensemble de ces demandes. Essaie de rendre une contrainte secondaire facultative.")
    candidates.sort(key=lambda x: x[0])
    _, result, statuses = candidates[0]

    side_summaries = semantic_summary(compound)
    notes = result.setdefault("advisor_notes", [])
    if matches:
        notes.insert(0, "J’ai interprété ton français naturel : " + " · ".join(matches[:4]) + ".")
    if side_summaries:
        notes.insert(1 if matches else 0, "Demandes secondaires comprises : " + " ; ".join(side_summaries[:5]) + ".")
    for status in statuses:
        if status["satisfied"]:
            when = f" au jour {status['route_day']}" if status.get("route_day") else ""
            notes.append(f"✓ {status['name']} est intégré au parcours{when} (écart au tracé ≈ {status['distance_to_route_km']:.1f} km).")
        else:
            notes.append(f"△ J’ai compris « {status.get('request') or status['name']} », mais le meilleur tracé reste à {status['distance_to_route_km']:.1f} km de {status['name']}.")
    notes.extend(resolution_notes[:4])

    limitations = (result.setdefault("confidence", {})).setdefault("limitations", [])
    dates = compound.get("dates") or {}
    start_date = dates.get("start_date")
    for status in statuses:
        target_date = status.get("target_date")
        if target_date and not start_date:
            suggested = date.fromisoformat(target_date) - timedelta(days=max(0, int(status.get("route_day") or 1) - 1))
            result["suggested_start_date"] = suggested.isoformat()
            notes.append(f"Pour être à {status['name']} le {target_date}, départ conseillé autour du {suggested.isoformat()} avec ce découpage d’étapes.")
        elif target_date and start_date:
            desired = _desired_day({"target_date": target_date}, compound, max(1, int(result.get("duration_days") or 1)))
            if desired is None:
                limitations.append(f"La date {target_date} ne tombe pas pendant le trek avec le départ prévu le {start_date}.")

    if any(req.get("kind") == "event" and req.get("target_date") for req in compound.get("side_requests") or []) and not events_configured():
        limitations.append("Événement daté compris mais non vérifié : configure une clé gratuite DATAtourisme pour rechercher les fêtes et manifestations réelles.")

    result["side_requests"] = statuses + [
        {
            "kind": req.get("kind"), "request": req.get("text"), "target_date": req.get("target_date"),
            "preferred_day": req.get("preferred_day"), "satisfied": False, "status": "compris_non_resolu",
        }
        for req in compound.get("side_requests") or []
        if not any((s.get("request") == req.get("text") and s.get("kind") == req.get("kind")) for s in statuses)
    ]
    result["request_structure"] = {
        "dates": dates,
        "secondary_objectives": side_summaries,
        "clauses_understood": (compound.get("clauses") or [])[:12],
    }
    result["model"] = PLANNER_VERSION
    planner = result.setdefault("planner", {})
    planner.update({
        "version": PLANNER_VERSION,
        "language_engine": "fr-compound-adaptive",
        "language_matches": matches,
        "personal_rules_loaded": len(rules),
        "side_objectives": len(compound.get("side_requests") or []),
        "event_source_configured": events_configured(),
        "route_variants_compared": len(candidates),
    })
    if result.get("understood_request") and side_summaries:
        result["understood_request"] += " · " + " · ".join(side_summaries[:3])

    try:
        mark_rules_used(legacy_main, user_id, rules, matches)
    except Exception:
        pass
    return result


def install_smart_planner(app, legacy_main):
    @app.get("/ai/status")
    def status():
        return {
            "configured": True,
            "model": PLANNER_VERSION,
            "web_search": False,
            "routing": bool(os.getenv("ORS_API_KEY", "").strip()),
            "cost_per_request": 0,
            "engine": "expert-compound-language",
            "language": "fr",
            "event_source": "DATAtourisme" if events_configured() else None,
            "capabilities": [
                "long-french-requests", "multi-intent", "typo-tolerance", "hiking-slang",
                "dated-side-objectives", "castle-and-village-objectives", "optional-event-verification",
                "personal-vocabulary-learning", "multi-candidate-planning", "real-routing",
            ],
        }

    @app.get("/ai/language")
    def language_rules(user=Depends(legacy_main.current_user)):
        try:
            ensure_language_schema(legacy_main)
            return {"rules": list_rules(legacy_main, int(user["id"])), "max_rules": 50}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Le dictionnaire personnel est momentanément indisponible.") from exc

    @app.post("/ai/language/learn")
    def language_learn(lesson: LanguageLesson, user=Depends(legacy_main.current_user)):
        try:
            ensure_language_schema(legacy_main)
            rule = learn_rule(legacy_main, int(user["id"]), lesson.phrase, lesson.meaning)
            return {"ok": True, "rule": rule, "message": f"J’ai appris « {lesson.phrase} »."}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Impossible d’enregistrer cette expression pour le moment.") from exc

    @app.delete("/ai/language/{rule_id}")
    def language_forget(rule_id: int, user=Depends(legacy_main.current_user)):
        try:
            ensure_language_schema(legacy_main)
            if not delete_rule(legacy_main, int(user["id"]), rule_id):
                raise HTTPException(status_code=404, detail="Expression introuvable.")
            return {"ok": True}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Impossible de supprimer cette expression pour le moment.") from exc

    @app.post("/ai/plan")
    def plan(data: v3.AIPlanRequest, user=Depends(legacy_main.current_user)):
        try:
            return _build(data, legacy_main, int(user["id"]))
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="Le conseiller TrekMap n’a pas pu combiner toutes les contraintes. Reformule ou rends une demande secondaire facultative.",
            ) from exc
