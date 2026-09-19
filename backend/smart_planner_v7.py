"""TrekMap Agent v7: reasoning, clarification and Web research.

This layer keeps the trusted geographic planner underneath and adds an optional
LLM brain, pre-flight clarification questions, Web research and post-plan audit.
No model is ever allowed to invent route geometry: waypoints are accepted only
after geocoding and the final route still comes from the geographic engine.
"""
from __future__ import annotations

import os
import re
from typing import Any

from fastapi import Depends, HTTPException

# Import v6 for its French-language pack side effects, then work with v5's
# underlying installer/build function. This avoids duplicating the route engine.
from . import smart_planner_v6 as _v6  # noqa: F401
from . import smart_planner_v5 as v5
from .compound_language_v5 import extract_side_requests
from .gemini_brain_v7 import analyze_request, configured as brain_configured, critique_plan
from .language_engine import normalize_for_planner
from .web_research_v7 import research_request

PLANNER_VERSION = "trekmap-research-agent-v7"
_BASE_BUILD = v5._build


def _form_snapshot(data) -> dict[str, Any]:
    return {
        "region": data.region,
        "days": data.days,
        "daily_km": data.daily_km,
        "difficulty": data.difficulty,
        "route_type": data.route_type,
        "require_transit": data.require_transit,
        "require_water": data.require_water,
        "require_accommodation": data.require_accommodation,
        "require_food": data.require_food,
    }


def _has_answer_block(prompt: str) -> bool:
    text = str(prompt or "").casefold()
    return "réponses aux questions" in text or "reponses aux questions" in text


def _local_questions(data, normalized: str, compound: dict[str, Any]) -> list[dict[str, Any]]:
    """Small deterministic fallback when no LLM key is configured."""
    q: list[dict[str, Any]] = []
    low = normalized.casefold()

    # The form already carries days/km/difficulty/type, so do not ask them again.
    # Region is the only truly essential free-form item that may still be absent.
    if not str(data.region or "").strip():
        known_places = (
            "pyrenees", "pyrénées", "alpes", "vercors", "chartreuse", "vosges",
            "jura", "morvan", "cevennes", "cévennes", "mercantour", "ecrins",
            "écrins", "queyras", "bauges", "belledonne", "mont blanc", "aubrac",
            "corse", "auvergne", "sancy", "cantal", "verdon", "vanoise",
            "beaufortain", "aravis", "bretagne", "normandie", "provence",
        )
        has_place_hint = any(x in low for x in known_places) or bool(
            re.search(r"\b(?:autour de|près de|pres de|dans|vers|depuis|au départ de|au depart de)\s+[a-zà-ÿ][\wà-ÿ' -]{2,50}", low)
        )
        if not has_place_hint:
            q.append({
                "id": "zone",
                "question": "Dans quelle région, massif ou ville veux-tu faire ce trek ?",
                "why": "Sans zone, je ne peux pas faire de recherche géographique sérieuse.",
                "options": [],
            })

    contradictory_easy = any(x in low for x in ("facile", "tranquille", "pepere", "pépère"))
    contradictory_hard = any(x in low for x in ("difficile", "sportif", "costaud", "soutenu"))
    if contradictory_easy and contradictory_hard:
        q.append({
            "id": "difficulty",
            "question": "Tu veux surtout un trek tranquille ou plutôt sportif ?",
            "why": "Ta phrase contient des indications de difficulté contradictoires.",
            "options": ["Plutôt tranquille", "Équilibré", "Plutôt sportif"],
        })

    route_words = {"Boucle": "boucle" in low, "Traversée": "traversee" in low or "traversée" in low}
    if all(route_words.values()):
        q.append({
            "id": "route_type",
            "question": "Tu préfères une boucle ou une traversée ?",
            "why": "Les deux types de parcours apparaissent dans ta demande.",
            "options": ["Boucle", "Traversée"],
        })

    # If an event is a hard requirement with a date but the trek dates are absent,
    # knowing the start date matters more than guessing the stage calendar.
    dates = compound.get("dates") or {}
    hard_dated_event = any(
        x.get("kind") == "event" and x.get("target_date") and x.get("required")
        for x in (compound.get("side_requests") or [])
    )
    if hard_dated_event and not dates.get("start_date"):
        q.append({
            "id": "start_date",
            "question": "À quelle date veux-tu commencer le trek ?",
            "why": "Tu demandes un événement à une date précise, donc je dois placer les étapes sur le calendrier.",
            "options": [],
        })

    return q[:3]


def _analysis_for(data) -> tuple[str, dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    normalized, _ = normalize_for_planner(data.prompt)
    compound = extract_side_requests(normalized)
    brain = analyze_request(data.prompt, _form_snapshot(data), compound) if brain_configured() else None
    questions = []
    if brain and isinstance(brain.get("clarifying_questions"), list):
        for item in brain["clarifying_questions"][:3]:
            if not isinstance(item, dict) or not str(item.get("question") or "").strip():
                continue
            questions.append({
                "id": str(item.get("id") or f"q{len(questions)+1}")[:40],
                "question": str(item.get("question"))[:260],
                "why": str(item.get("why") or "Cette précision peut changer le parcours.")[:320],
                "options": [str(x)[:120] for x in (item.get("options") or [])[:5]],
            })
    if not questions:
        questions = _local_questions(data, normalized, compound)
    return normalized, compound, brain, questions


def _validated_brain_waypoints(brain: dict[str, Any] | None, location: str) -> list[dict[str, Any]]:
    if not brain:
        return []
    out = []
    for item in (brain.get("candidate_waypoints") or [])[:4]:
        if not isinstance(item, dict):
            continue
        name = re.sub(r"\s+", " ", str(item.get("name") or "")).strip()[:100]
        if len(name) < 2:
            continue
        try:
            point = v5.v3._geocode_named(name, location)
        except Exception:
            point = None
        if not point:
            continue
        out.append({
            "name": name,
            "reason": str(item.get("reason") or "")[:240],
            "mandatory": bool(item.get("mandatory")),
            "lat": point.get("lat"),
            "lon": point.get("lon"),
        })
    return out


def _enrich_prompt(normalized: str, brain: dict[str, Any] | None, waypoints: list[dict[str, Any]]) -> str:
    pieces = [normalized]
    if brain:
        for constraint in (brain.get("must_have") or [])[:6]:
            pieces.append("contrainte obligatoire: " + str(constraint)[:180])
        for pref in (brain.get("nice_to_have") or [])[:5]:
            pieces.append("si possible: " + str(pref)[:180])
    for item in waypoints[:3]:
        prefix = "passer par" if item.get("mandatory") else "si possible passer par"
        pieces.append(f"{prefix} {item['name']}")
    return " ; ".join(x for x in pieces if x)[:4000]


def _research_sources(research: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": r.get("snippet"),
            "provider": r.get("provider"),
            "query": r.get("query"),
        }
        for r in (research.get("results") or [])[:12]
    ]


def _build(data, legacy_main, user_id: int):
    normalized, compound, brain, questions = _analysis_for(data)

    # The pre-flight UI normally asks these first. If an old client bypasses it,
    # do not fail: the deterministic form values still let the route engine work.
    location = str(data.region or "").strip() or v5.v3._location(data)
    brain_queries = [str(x) for x in ((brain or {}).get("research_queries") or [])[:5]]
    research = research_request(data.prompt, location, compound, brain_queries)
    waypoints = _validated_brain_waypoints(brain, location)
    enriched_prompt = _enrich_prompt(normalized, brain, waypoints)

    candidate_data = data.model_copy(update={"prompt": enriched_prompt})
    result = _BASE_BUILD(candidate_data, legacy_main, user_id)

    audit = critique_plan(data.prompt, result, research) if brain_configured() else None
    notes = result.setdefault("advisor_notes", [])
    if brain and brain.get("summary"):
        notes.insert(0, "🧠 Compréhension IA : " + str(brain["summary"])[:500])
    if research.get("results"):
        notes.append(
            f"🔎 Recherche Web : {len(research['results'])} résultat(s) consulté(s) via {research.get('provider') or 'le Web'}."
        )
    for item in waypoints:
        notes.append(f"✓ Lieu proposé par le cerveau puis vérifié géographiquement : {item['name']}.")
    if audit:
        for advice in (audit.get("advice") or [])[:5]:
            notes.append("💡 " + str(advice)[:500])

    limitations = result.setdefault("confidence", {}).setdefault("limitations", [])
    if questions and not _has_answer_block(data.prompt):
        limitations.append(
            "Certaines précisions auraient pu améliorer le plan : "
            + " / ".join(str(x.get("question")) for x in questions[:3])
        )
    if audit:
        for warning in (audit.get("warnings") or [])[:5]:
            if str(warning) not in limitations:
                limitations.append(str(warning)[:500])

    result["model"] = PLANNER_VERSION
    result["agent"] = {
        "version": PLANNER_VERSION,
        "brain": "gemini" if brain_configured() else "local-fallback",
        "brain_model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash") if brain_configured() else None,
        "web_provider": research.get("provider"),
        "research_queries": research.get("queries") or [],
        "clarification_questions_considered": len(questions),
        "validated_brain_waypoints": waypoints,
        "constraint_checks": (audit or {}).get("constraint_checks") or [],
        "research_takeaways": (audit or {}).get("research_takeaways") or [],
    }
    result["web_sources"] = _research_sources(research)
    result["web_research"] = {
        "provider": research.get("provider"),
        "queries": research.get("queries") or [],
        "pages_read": len(research.get("pages") or []),
    }
    return result


def install_smart_planner(app, legacy_main):
    # Make v5's existing authenticated endpoints use the new build function.
    v5.PLANNER_VERSION = PLANNER_VERSION
    v5._build = _build
    v5.install_smart_planner(app, legacy_main)

    # Replace the old status route so the UI can see the real agent capabilities.
    app.router.routes = [route for route in app.router.routes if route.path != "/ai/status"]

    @app.get("/ai/status")
    def status():
        google = bool(os.getenv("GOOGLE_CSE_API_KEY", "").strip() and os.getenv("GOOGLE_CSE_CX", "").strip())
        brave = bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip())
        return {
            "configured": True,
            "model": PLANNER_VERSION,
            "engine": "research-agent",
            "brain": "gemini" if brain_configured() else "local-fallback",
            "brain_model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash") if brain_configured() else None,
            "web_search": True,
            "web_provider": "Google" if google else ("Brave" if brave else "DuckDuckGo fallback"),
            "routing": bool(os.getenv("ORS_API_KEY", "").strip()),
            "cost_per_request": 0 if not brain_configured() else "free-tier-dependent",
            "capabilities": [
                "clarification-dialogue", "long-french-requests", "typo-tolerance",
                "optional-llm-reasoning", "web-research", "source-links",
                "validated-waypoints", "multi-candidate-planning", "post-plan-audit",
                "real-routing", "personal-vocabulary-learning",
            ],
        }

    @app.post("/ai/clarify")
    def clarify(data: v5.v3.AIPlanRequest, user=Depends(legacy_main.current_user)):
        normalized, compound, brain, questions = _analysis_for(data)
        # If the user already answered a clarification block, avoid an infinite
        # interview loop unless the brain found a genuinely new conflict.
        if _has_answer_block(data.prompt):
            questions = []
        return {
            "needs_clarification": bool(questions),
            "questions": questions[:3],
            "understood": (brain or {}).get("summary") or normalized[:700],
            "confidence": (brain or {}).get("confidence"),
            "brain": "gemini" if brain_configured() else "local-fallback",
            "side_requests": compound.get("side_requests") or [],
        }
