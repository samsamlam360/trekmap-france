"""TrekBrain v9: faster shared research, stricter auditing and clearer output.

The expensive context (LLM understanding, Web research and validated waypoint
ideas) is prepared once per request, then reused across local planning
hypotheses. Geometry still comes only from the trusted geographic planner.
"""
from __future__ import annotations

import math
import os
import re
import time
from typing import Any

from fastapi import Depends, HTTPException

from . import smart_planner_v8 as v8
from . import smart_planner_v7 as v7
from .trekbrain_v8 import (
    ACTION_LABELS,
    MODEL_VERSION,
    apply_feedback,
    create_episode,
    evaluate_plan,
    extract_features,
    model_for_user,
    public_summary,
    rank_actions,
    strategy_prompt,
    _state_template,
)
from .web_research_v9 import research_request
from .trekbrain_runtime_v9 import free_mode, seconds
from .trekbrain_dialogue_v9 import AskRequest, answer

PLANNER_VERSION = "trekmap-precision-agent-v9"
_MODEL_CACHE: dict[int, tuple[float, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]] = {}
MODEL_CACHE_TTL = 25.0


def _brain_enabled():
    return not free_mode() and v7.brain_configured()


def _analysis_for(data):
    if not free_mode():
        return v7._analysis_for(data)
    normalized, _ = v7.normalize_for_planner(data.prompt)
    compound = v7.extract_side_requests(normalized)
    return normalized, compound, None, v7._local_questions(data, normalized, compound)


def _effective_request(data):
    # Audit exactly the same interpretation as the geographic planner, not the
    # stale form defaults when the user writes a different duration/distance.
    normalized, _ = v7.normalize_for_planner(data.prompt)
    intent = v7.v5.v3._parse_intent(data.model_copy(update={"prompt": normalized}))
    return data.model_copy(update={
        "days": intent["days"], "daily_km": intent["daily_target"],
        "route_type": intent["route_type"], "difficulty": intent["difficulty"],
        "require_transit": intent["transit"],
    })


def _model_for_user_cached(legacy_main, user_id: int):
    now = time.monotonic()
    cached = _MODEL_CACHE.get(int(user_id))
    if cached and now - cached[0] <= MODEL_CACHE_TTL:
        return cached[1]
    try:
        value = model_for_user(legacy_main, int(user_id))
    except Exception:
        # Personalization is optional; auth and geographic access are not
        # bypassed. Do not cache this fallback as a successful learned model.
        combined = _state_template()
        combined["personal_samples"] = 0
        combined["learning_available"] = False
        return combined, _state_template(), _state_template()
    _MODEL_CACHE[int(user_id)] = (now, value)
    if len(_MODEL_CACHE) > 120:
        oldest = sorted(_MODEL_CACHE.items(), key=lambda x: x[1][0])[:30]
        for key, _ in oldest:
            _MODEL_CACHE.pop(key, None)
    return value


def _learning_context(data, legacy_main, user_id: int):
    normalized, _ = v7.normalize_for_planner(data.prompt)
    compound = v7.extract_side_requests(normalized)
    combined, global_state, user_state = _model_for_user_cached(legacy_main, user_id)
    features = extract_features(data, normalized, compound)
    ranked = rank_actions(combined, features)
    return normalized, compound, features, ranked, combined, global_state, user_state


def _strategy_prompt(base_prompt: str, action: str, reflection: str = "") -> str:
    context = (
        "\n\nPriorité interne TrekBrain : "
        f"{ACTION_LABELS.get(action, action)}. {strategy_prompt(action)}. "
        "Respecter d'abord toutes les contraintes explicites de l'utilisateur."
    )
    if reflection:
        context += " Correction de la tentative précédente : " + re.sub(r"\s+", " ", reflection).strip()[:650]
    return (str(base_prompt or "").strip() + context)[:4000]


def _prepare_shared(data):
    started = time.perf_counter()
    normalized, compound, brain, questions = _analysis_for(data)
    if questions and not v7._has_answer_block(data.prompt):
        raise HTTPException(status_code=422, detail="Précise ta demande : " + " ".join(q["question"] for q in questions))
    location = str(data.region or "").strip() or v7.v5.v3._location(data)
    brain_queries = [str(x) for x in ((brain or {}).get("research_queries") or [])[:4]]
    research = research_request(data.prompt, location, compound, brain_queries)
    waypoints = v7._validated_brain_waypoints(brain, location)
    base_prompt = v7._enrich_prompt(normalized, brain, waypoints)
    return {
        "normalized": normalized,
        "compound": compound,
        "brain": brain,
        "questions": questions,
        "location": location,
        "research": research,
        "waypoints": waypoints,
        "base_prompt": base_prompt,
        "prepare_ms": round((time.perf_counter() - started) * 1000),
    }


def _distance_km(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float | None:
    if not a or not b:
        return None
    try:
        lat1, lon1 = math.radians(float(a["lat"])), math.radians(float(a["lon"]))
        lat2, lon2 = math.radians(float(b["lat"])), math.radians(float(b["lon"]))
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in (lat1, lon1, lat2, lon2)):
        return None
    if max(abs(lat1), abs(lat2)) > math.pi / 2 or max(abs(lon1), abs(lon2)) > math.pi:
        return None
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _check(name: str, status: str, detail: str, impact: str = "medium") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail, "impact": impact}


def precision_audit(result: dict[str, Any], data, features: dict[str, float], research: dict[str, Any], compound: dict[str, Any]) -> dict[str, Any]:
    """Strict, user-visible audit. No hidden reasoning, only measurable checks."""
    data = _effective_request(data)
    local = evaluate_plan(result, data, features)
    score = float(local.get("score") or 0)
    if not math.isfinite(score):
        score = 0.0
    checks: list[dict[str, str]] = []
    blockers: list[str] = []

    requested_days = max(1, int(getattr(data, "days", 1) or 1))
    stages = result.get("stages") or []
    actual_days = len(stages)
    if actual_days == requested_days:
        checks.append(_check("Durée", "ok", f"{actual_days} jour(s), conforme à la demande."))
    else:
        delta = abs(actual_days - requested_days)
        score -= min(20, delta * 8)
        blockers.append("durée différente de la demande")
        checks.append(_check("Durée", "failed", f"Demandé : {requested_days} jour(s), proposé : {actual_days}.", "high"))

    target = max(3.0, float(getattr(data, "daily_km", 18) or 18))
    distances = []
    for stage in stages:
        try:
            distance = float(stage.get("distance_km") or 0)
            if math.isfinite(distance) and distance > 0:
                distances.append(distance)
        except (TypeError, ValueError):
            pass
    if len(distances) != len(stages) or not distances:
        score -= 20
        blockers.append("distances manquantes ou invalides")
        checks.append(_check("Distances", "failed", "Les distances de toutes les étapes ne sont pas exploitables.", "high"))
    if distances:
        folded = v7.v5.v3._fold(data.prompt)
        limit = re.search(r"(?:max(?:imum)?|pas\s+plus\s+de|moins\s+de)\s*(\d{1,2}(?:[.,]\d+)?)\s*km", folded)
        if limit and any(d > float(limit[1].replace(',', '.')) + 0.1 for d in distances):
            blockers.append("distance maximale dépassée")
            score -= 18
            checks.append(_check("Limite quotidienne", "failed", "Au moins une étape dépasse le maximum demandé.", "high"))
        mean_dev = sum(abs(x - target) / target for x in distances) / len(distances)
        worst = max(abs(x - target) / target for x in distances)
        if mean_dev <= 0.16 and worst <= 0.30:
            checks.append(_check("Étapes", "ok", f"Étapes bien équilibrées autour de {target:.0f} km/jour."))
        elif mean_dev <= 0.28:
            score -= 5
            checks.append(_check("Étapes", "partial", "Certaines journées s'écartent sensiblement de la distance cible."))
        else:
            score -= 13
            blockers.append("étapes mal équilibrées")
            checks.append(_check("Étapes", "failed", "Les distances quotidiennes s'écartent trop de la cible.", "high"))

    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    geometry_ok = len(coords) >= 2 and all(
        isinstance(p, (list, tuple)) and len(p) >= 2
        and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p[:2])
        and -90 <= p[0] <= 90 and -180 <= p[1] <= 180 for p in coords
    )
    if not geometry_ok or route.get("fallback") is not False:
        score -= 18
        blockers.append("routage dégradé")
        checks.append(_check("Tracé", "failed", "Le tracé n'a pas été calculé complètement par le moteur de randonnée.", "high"))
    else:
        checks.append(_check("Tracé", "ok", "Tracé pédestre calculé par le moteur géographique."))

    route_type = str(getattr(data, "route_type", "") or "").casefold()
    if "boucle" in route_type:
        closing = _distance_km(result.get("start"), result.get("end"))
        if closing is not None and closing <= 0.25:
            checks.append(_check("Boucle", "ok", f"Arrivée à environ {closing:.1f} km du départ."))
        elif closing is not None:
            score -= min(14, max(4, closing * 1.2))
            blockers.append("boucle mal refermée")
            checks.append(_check("Boucle", "failed", f"L'arrivée reste à environ {closing:.1f} km du départ.", "high"))
        else:
            score -= 14
            blockers.append("fermeture de boucle invérifiable")
            checks.append(_check("Boucle", "unknown", "Coordonnées de départ ou d'arrivée manquantes ou invalides.", "high"))

    if features.get("transit"):
        transport = result.get("transport") or {}
        text = (str(transport.get("outbound") or "") + " " + str(transport.get("return") or "")).casefold()
        if not all(str(transport.get(k) or "").strip() for k in ("outbound", "return")):
            score -= 12
            blockers.append("accès en transport non renseigné")
            checks.append(_check("Transports", "failed", "Aucun accès aller ou retour en transport n'est renseigné.", "high"))
        elif "aucun" in text or "non trouvé" in text or "non trouve" in text:
            score -= 8
            checks.append(_check("Transports", "partial", "Un accès aller ou retour en transport n'est pas établi."))
        else:
            checks.append(_check("Transports", "partial", "Accès signalés au départ et à l'arrivée ; desserte, horaires et correspondances non vérifiés."))

    if features.get("sleep") and requested_days > 1:
        intermediate = stages[:-1]
        if len(intermediate) < requested_days - 1:
            blockers.append("nuitées manquantes")
        uncertain_sleep = sum(
            1 for stage in intermediate
            if not str(stage.get("overnight") or "").strip() or any(x in str(stage.get("overnight") or "").casefold() for x in ("à confirmer", "a confirmer", "envisagé", "envisage", "aucun"))
        )
        if uncertain_sleep:
            score -= min(12, uncertain_sleep * 4)
            checks.append(_check("Nuitées", "partial", f"{uncertain_sleep} nuitée(s) restent à confirmer."))
        else:
            checks.append(_check("Nuitées", "partial", "Solutions de nuitée signalées ; ouverture, disponibilité et autorisation non vérifiées."))

    if features.get("water"):
        missing_water = sum(1 for stage in stages if "aucun point d'eau" in str(stage.get("water_notes") or "").casefold())
        verified = sum(1 for x in (result.get("water") or []) if x.get("status") == "potable_referenced")
        undocumented = sum(1 for stage in stages if not str(stage.get("water_notes") or "").strip())
        if undocumented:
            score -= min(12, undocumented * 3)
            checks.append(_check("Eau", "unknown", f"{undocumented} étape(s) sans information sur l'eau ; {verified} point(s) potable(s) explicitement référencé(s)."))
        elif missing_water:
            score -= min(10, missing_water * 2.5)
            checks.append(_check("Eau", "partial", f"{missing_water} étape(s) sans point d'eau cartographié proche ; {verified} point(s) potable(s) explicitement référencé(s)."))
        else:
            checks.append(_check("Eau", "partial", f"{verified} point(s) référencé(s) potable(s) dans les données ; débit et état actuels non vérifiés, couverture de chaque journée à contrôler."))

    side = result.get("side_requests") or []
    important = [x for x in side if isinstance(x, dict) and (x.get("target_date") or x.get("preferred_day") or x.get("required"))]
    missed = [x for x in important if not x.get("satisfied")]
    requested_important = [x for x in compound.get("side_requests", [])
                           if x.get("required") or x.get("preferred_day") or x.get("target_date")]
    for req in requested_important:
        # The compound extractor emits one objective per kind; the underlying
        # planner enriches its text, so literal full-sentence equality is wrong.
        matches = [x for x in side if x.get("kind") == req.get("kind")]
        if not matches or not any(x.get("satisfied") and
                (not req.get("preferred_day") or x.get("route_day") == req["preferred_day"]) and
                (not req.get("target_date") or (x.get("target_date") == req["target_date"] and
                 x.get("preferred_day") is not None and x.get("route_day") == x.get("preferred_day"))) for x in matches):
            missed.append(req)
    missed = list({(x.get("kind"), x.get("target_date"), x.get("preferred_day")): x for x in missed}.values())
    if missed:
        score -= min(24, len(missed) * 9)
        blockers.append("objectif secondaire important non satisfait")
        checks.append(_check("Demandes spéciales", "failed", f"{len(missed)} objectif(s) daté(s), positionné(s) ou obligatoire(s) restent non satisfaits.", "high"))
    elif important:
        checks.append(_check("Demandes spéciales", "ok", f"{len(important)} objectif(s) important(s) intégrés au parcours."))

    evidence = research.get("evidence") or {}
    needs_web = bool((compound.get("side_requests") or [])) or any(
        word in str(data.prompt or "").casefold()
        for word in ("ouvert", "fermé", "ferme", "fête", "festival", "horaire", "réglement", "interdit")
    )
    if needs_web:
        strong = int(evidence.get("strong_results") or 0)
        if strong >= 2:
            checks.append(_check("Sources Web", "partial", f"{strong} résultat(s) bien classé(s), mais les extraits de recherche ne valident pas les horaires, dates ou ouvertures."))
        elif int(evidence.get("results") or 0) > 0:
            score -= 5
            checks.append(_check("Sources Web", "partial", "Des résultats existent, mais peu de sources fortes ont été trouvées."))
        else:
            score -= 10
            checks.append(_check("Sources Web", "unknown", "Aucune preuve Web exploitable trouvée pour les demandes qui dépendent d'informations récentes."))

    score = round(max(0.0, min(100.0, score)), 1)
    if blockers:
        score = min(score, 59.0)
    return {
        "score": score,
        "grade": "excellent" if score >= 88 else "bon" if score >= 76 else "à vérifier" if score >= 60 else "fragile",
        "checks": checks,
        "blockers": list(dict.fromkeys(blockers))[:6],
        "needs_reflection": bool(blockers) or score < 78,
        "base_local_score": local.get("score"),
        "score_meaning": "Indicateur heuristique de cohérence, pas une probabilité de réussite ni une garantie de sécurité.",
        "reasons": list(dict.fromkeys((local.get("reasons") or []) + blockers))[:8],
    }


def _run_hypothesis(data, legacy_main, user_id: int, action: str, shared: dict[str, Any], features: dict[str, float], reflection: str = ""):
    prompt = _strategy_prompt(shared["base_prompt"], action, reflection)
    candidate = data.model_copy(update={"prompt": prompt})
    started = time.perf_counter()
    # Critical speed improvement: call the trusted base planner directly instead
    # of rerunning v7's Gemini + Web research for every hypothesis.
    result = v7._BASE_BUILD(candidate, legacy_main, user_id)
    audit = precision_audit(result, data, features, shared["research"], shared["compound"])
    return result, audit, round((time.perf_counter() - started) * 1000)


def _attach_research(result: dict[str, Any], shared: dict[str, Any]) -> None:
    research = shared["research"]
    result["web_sources"] = [
        {
            "title": x.get("title"), "url": x.get("url"), "snippet": x.get("snippet"),
            "provider": x.get("provider"), "query": x.get("query"),
            "evidence_score": x.get("evidence_score"),
        }
        for x in (research.get("results") or [])[:10]
    ]
    result["web_research"] = {
        "provider": research.get("provider"),
        "queries": research.get("queries") or [],
        "pages_read": len(research.get("pages") or []),
        "evidence": research.get("evidence") or {},
        "status": research.get("status"),
        "claims_verified": False,
        "elapsed_ms": research.get("elapsed_ms"),
        "cache_hits": research.get("cache_hits", 0),
    }


def _decision_summary(result: dict[str, Any], audit: dict[str, Any], shared: dict[str, Any], elapsed_ms: int) -> dict[str, Any]:
    verified, uncertain, important = [], [], []
    for item in audit.get("checks") or []:
        line = f"{item.get('name')}: {item.get('detail')}"
        if item.get("status") == "ok":
            verified.append(line)
        elif item.get("impact") == "high" or item.get("status") == "failed":
            important.append(line)
        else:
            uncertain.append(line)
    for limitation in ((result.get("confidence") or {}).get("limitations") or [])[:4]:
        text = str(limitation).strip()
        if text and text not in uncertain and text not in important:
            uncertain.append(text)
    return {
        "quality": audit.get("score"),
        "grade": audit.get("grade"),
        "score_meaning": audit.get("score_meaning"),
        "elapsed_ms": elapsed_ms,
        "understood": result.get("understood_request") or (shared.get("brain") or {}).get("summary") or shared.get("normalized"),
        "verified": verified[:6],
        "uncertain": uncertain[:6],
        "important": important[:5],
        "sources_found": len((shared.get("research") or {}).get("results") or []),
        "strong_sources": int(((shared.get("research") or {}).get("evidence") or {}).get("strong_results") or 0),
    }


def _build(data, legacy_main, user_id: int):
    total_started = time.perf_counter()
    data = _effective_request(data)
    normalized, compound, features, ranked, combined, _, _ = _learning_context(data, legacy_main, user_id)
    shared = _prepare_shared(data)
    primary = ranked[0]["action"] if ranked else "balanced"
    hypotheses: list[dict[str, Any]] = []

    first, audit1, ms1 = _run_hypothesis(data, legacy_main, user_id, primary, shared, features)
    hypotheses.append({"strategy": primary, "quality": audit1["score"], "grade": audit1["grade"], "elapsed_ms": ms1})
    chosen_result, chosen_audit, chosen_action = first, audit1, primary

    threshold = seconds("TREKBRAIN_V9_RETRY_THRESHOLD", 80, 100)
    margin = float(ranked[0].get("margin", 0)) if ranked else 0.0
    should_retry = bool(audit1.get("needs_reflection")) or (audit1["score"] < threshold and margin < 1.2)
    retry_budget = seconds("TREKBRAIN_RETRY_BUDGET_SECONDS", 25)
    if should_retry and len(ranked) > 1 and time.perf_counter() - total_started < retry_budget:
        alternative = next((x["action"] for x in ranked[1:] if x["action"] != primary), "balanced")
        reason = "; ".join(audit1.get("reasons") or []) or "la première hypothèse n'est pas assez précise"
        try:
            second, audit2, ms2 = _run_hypothesis(
                data, legacy_main, user_id, alternative, shared, features,
                reflection=f"Score précédent {audit1['score']}/100. Corriger surtout : {reason}.",
            )
            hypotheses.append({"strategy": alternative, "quality": audit2["score"], "grade": audit2["grade"], "elapsed_ms": ms2})
            if (len(audit2["blockers"]), -audit2["score"]) < (len(audit1["blockers"]), -audit1["score"]):
                chosen_result, chosen_audit, chosen_action = second, audit2, alternative
        except Exception:
            pass

    _attach_research(chosen_result, shared)

    # One optional Gemini audit, after the route winner is known. V8 could do
    # this repeatedly; V9 never needs more than one audit per request.
    gemini_audit = None
    use_gemini_audit = _brain_enabled() and str(os.getenv("TREKBRAIN_GEMINI_AUDIT", "1")).casefold() not in {"0", "false", "off", "no"}
    if use_gemini_audit and (chosen_audit["score"] < 92 or shared["compound"].get("side_requests")):
        try:
            gemini_audit = v7.critique_plan(data.prompt, chosen_result, shared["research"])
        except Exception:
            gemini_audit = None

    brain_summary = public_summary(combined, ranked)
    chosen_result["trekbrain"] = {
        "version": "trekbrain-v9",
        "strategy": chosen_action,
        "strategy_label": ACTION_LABELS.get(chosen_action, chosen_action),
        "quality": chosen_audit,
        "hypotheses": hypotheses,
        "model": brain_summary,
        "features_used": sorted(features.keys()),
        "learning_mode": "online-contextual",
        "stores_raw_prompt": False,
        "shared_context_reused": True,
        "personalization_available": combined.get("learning_available", True),
    }

    notes = chosen_result.setdefault("advisor_notes", [])
    notes.insert(0, f"🧠 TrekBrain v9 a retenu « {ACTION_LABELS.get(chosen_action, chosen_action)} » après {len(hypotheses)} hypothèse(s), avec un audit de {chosen_audit['score']}/100.")
    if shared["research"].get("results"):
        ev = shared["research"].get("evidence") or {}
        notes.append(f"🔎 Recherche Web mutualisée : {len(shared['research']['results'])} résultat(s), dont {int(ev.get('strong_results') or 0)} bien classé(s). Extraits à vérifier sur les sites sources.")
    if not combined.get("learning_available", True):
        notes.append("La personnalisation est indisponible : les stratégies locales par défaut ont été utilisées.")
    if gemini_audit:
        for advice in (gemini_audit.get("advice") or [])[:3]:
            notes.append("💡 " + str(advice)[:450])
        limitations = chosen_result.setdefault("confidence", {}).setdefault("limitations", [])
        for warning in (gemini_audit.get("warnings") or [])[:3]:
            if str(warning) not in limitations:
                limitations.append(str(warning)[:450])

    try:
        token = create_episode(legacy_main, user_id, data.prompt, chosen_action, features, chosen_result)
    except Exception:
        # A feedback-store failure must not discard an already computed route.
        token = None
        notes.append("Le parcours est disponible, mais l'enregistrement du retour d'expérience est momentanément indisponible.")
    chosen_result["learning_token"] = token
    chosen_result["model"] = PLANNER_VERSION
    elapsed_ms = round((time.perf_counter() - total_started) * 1000)
    chosen_result["decision_summary"] = _decision_summary(chosen_result, chosen_audit, shared, elapsed_ms)
    chosen_result.setdefault("agent", {}).update({
        "version": PLANNER_VERSION,
        "brain": "gemini+trekbrain" if _brain_enabled() else "trekbrain-local",
        "free_mode": free_mode(),
        "limits": "Pas de quota d'essais TrekBrain ; disponibilité et limites des services externes applicables.",
        "local_learning_brain": {
            "version": "trekbrain-v9",
            "strategy": chosen_action,
            "quality": chosen_audit["score"],
            "hypotheses_compared": len(hypotheses),
            "personal_samples": brain_summary.get("personal_samples", 0),
        },
        "performance": {
            "total_ms": elapsed_ms,
            "context_prepare_ms": shared.get("prepare_ms"),
            "shared_research": True,
            "gemini_audits": 1 if gemini_audit else 0,
        },
    })
    return chosen_result


def install_smart_planner(app, legacy_main):
    # Install v8's language/learning infrastructure, then replace the five public
    # agent endpoints with V9 implementations.
    v8.install_smart_planner(app, legacy_main)
    replace = {"/ai/status", "/ai/clarify", "/ai/plan", "/ai/feedback", "/ai/brain"}
    app.router.routes = [route for route in app.router.routes if route.path not in replace]

    @app.post("/ai/ask")
    def ask(body: AskRequest, user=Depends(legacy_main.current_user)):
        return answer(body)

    @app.get("/ai/status")
    def status():
        google = bool(os.getenv("GOOGLE_CSE_API_KEY", "").strip() and os.getenv("GOOGLE_CSE_CX", "").strip())
        brave = bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip())
        return {
            "configured": True,
            "model": PLANNER_VERSION,
            "engine": "precision-self-learning-agent",
            "local_brain": "trekbrain-v9",
            "learning": True,
            "brain": "gemini-teacher+trekbrain" if _brain_enabled() else "trekbrain-local",
            "free_mode": free_mode(),
            "paid_ai_calls": not free_mode() and _brain_enabled(),
            "attempt_quota": None,
            "limits": "Services cartographiques, recherche et hébergement soumis à disponibilité et quotas propres.",
            "web_search": True,
            "web_provider": "DuckDuckGo fallback" if free_mode() else "Google" if google else ("Brave" if brave else "DuckDuckGo fallback"),
            "routing": bool(os.getenv("ORS_API_KEY", "").strip()),
            "capabilities": [
                "shared-research-context", "parallel-web-search", "ranked-evidence",
                "strict-route-audit", "adaptive-retry", "online-learning", "personal-adaptation",
                "clarification-dialogue", "optional-gemini-teacher", "validated-waypoints",
                "real-routing", "clear-decision-summary", "feedback-learning",
                "grounded-plan-dialogue", "free-mode",
            ],
        }

    @app.post("/ai/clarify")
    def clarify(data: v7.v5.v3.AIPlanRequest, user=Depends(legacy_main.current_user)):
        data = _effective_request(data)
        normalized, compound, brain, questions = _analysis_for(data)
        if v7._has_answer_block(data.prompt):
            questions = []
        try:
            _, _, features, ranked, combined, _, _ = _learning_context(data, legacy_main, int(user["id"]))
            local_q = v8._learning_question(ranked, features, combined)
            if local_q and not questions and not v7._has_answer_block(data.prompt):
                questions = [local_q]
        except Exception:
            ranked, combined = [], {}
        return {
            "needs_clarification": bool(questions),
            "questions": questions[:3],
            "understood": (brain or {}).get("summary") or normalized[:700],
            "confidence": (brain or {}).get("confidence"),
            "brain": "gemini+trekbrain-v9" if _brain_enabled() else "trekbrain-v9",
            "side_requests": compound.get("side_requests") or [],
            "trekbrain": public_summary(combined, ranked) if ranked and combined else None,
        }

    @app.post("/ai/plan")
    def plan(data: v7.v5.v3.AIPlanRequest, user=Depends(legacy_main.current_user)):
        try:
            return _build(data, legacy_main, int(user["id"]))
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="TrekBrain v9 n'a pas réussi à construire un plan suffisamment fiable. Précise la zone ou assouplis une contrainte importante.") from exc

    @app.post("/ai/feedback")
    def feedback(body: v8.FeedbackRequest, user=Depends(legacy_main.current_user)):
        mapping = {"up": 1.0, "good": 1.0, "like": 1.0, "positive": 1.0, "down": -1.0, "bad": -1.0, "dislike": -1.0, "negative": -1.0, "saved": 0.7, "save": 0.7}
        rating = body.rating.strip().casefold()
        if rating not in mapping:
            raise HTTPException(status_code=400, detail="Retour invalide.")
        try:
            learned = apply_feedback(legacy_main, int(user["id"]), body.token, mapping[rating], body.comment)
            _MODEL_CACHE.clear()  # shared state changed too
            learned["message"] = "TrekBrain a intégré ce retour." if not learned.get("already_learned") else "Ce résultat avait déjà été utilisé pour l'apprentissage."
            return learned
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="L'apprentissage est momentanément indisponible.") from exc

    @app.get("/ai/brain")
    def brain_state(user=Depends(legacy_main.current_user)):
        try:
            combined, _, _ = _model_for_user_cached(legacy_main, int(user["id"]))
            ranked = rank_actions(combined, {"bias": 1.0, "generic": 1.0})
            summary = public_summary(combined, ranked)
            summary["runtime_version"] = "trekbrain-v9"
            return summary
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Le modèle d'apprentissage est momentanément indisponible.") from exc
