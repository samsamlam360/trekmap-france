"""TrekMap expert planner v4: adaptive French language understanding.

The itinerary engine remains the proven v3 planner. This layer adds local French
normalisation, typo tolerance, hiking slang and persistent per-user vocabulary.
"""
from __future__ import annotations

import os
from contextvars import ContextVar

from fastapi import Depends, HTTPException

from . import smart_planner_v3 as v3
from .language_engine import (
    LanguageLesson,
    delete_rule,
    ensure_language_schema,
    extract_inline_lesson,
    learn_rule,
    list_rules,
    mark_rules_used,
    normalize_for_planner,
)

PLANNER_VERSION = "trekmap-language-planner-v4"
_RULES: ContextVar[list[dict]] = ContextVar("trekmap_language_rules", default=[])
_LAST_MATCHES: ContextVar[list[str]] = ContextVar("trekmap_language_matches", default=[])
_BASE_PARSE_INTENT = v3._parse_intent


def _language_parse_intent(data):
    rules = _RULES.get()
    normalized, matches = normalize_for_planner(data.prompt, rules)
    _LAST_MATCHES.set(matches)
    # Pydantic v2 model_copy is available in this project. Keep all structured
    # controls and only replace the free-text sentence with its semantic form.
    normalised_data = data.model_copy(update={"prompt": normalized})
    intent = _BASE_PARSE_INTENT(normalised_data)
    intent["language_matches"] = matches
    intent["normalized_prompt"] = normalized
    return intent


# v3 resolves _parse_intent from its module globals at call time. Replacing it
# once here lets us reuse the entire tested route-generation engine while
# ContextVar keeps concurrent users' dictionaries isolated.
v3._parse_intent = _language_parse_intent


def _safe_language_rules(legacy_main, user_id: int):
    try:
        ensure_language_schema(legacy_main)
        return list_rules(legacy_main, user_id)
    except Exception:
        # Language learning is an enhancement. A temporary DB migration problem
        # must not stop route planning altogether.
        return []


def _build(data, legacy_main, user_id: int):
    rules = _safe_language_rules(legacy_main, user_id)

    # Allow natural teaching during a refinement, e.g.
    # "quand je dis pépère, ça veut dire max 15 km et peu de D+".
    lesson = extract_inline_lesson(data.prompt)
    if lesson:
        try:
            ensure_language_schema(legacy_main)
            learn_rule(legacy_main, user_id, lesson[0], lesson[1])
            rules = list_rules(legacy_main, user_id)
        except Exception:
            pass

    rules_token = _RULES.set(rules)
    matches_token = _LAST_MATCHES.set([])
    try:
        result = v3._build(data, legacy_main)
        matches = _LAST_MATCHES.get()
    finally:
        _RULES.reset(rules_token)
        _LAST_MATCHES.reset(matches_token)

    result["model"] = PLANNER_VERSION
    planner = result.setdefault("planner", {})
    planner["version"] = PLANNER_VERSION
    planner["language_engine"] = "fr-adaptive-local"
    planner["language_matches"] = matches
    planner["personal_rules_loaded"] = len(rules)

    if matches:
        notes = result.setdefault("advisor_notes", [])
        summary = "J’ai compris ton vocabulaire : " + " · ".join(matches[:4]) + "."
        if summary not in notes:
            notes.insert(0, summary)
        understood = str(result.get("understood_request") or "")
        if understood:
            result["understood_request"] = understood + " · langage naturel interprété"

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
            "engine": "expert-adaptive-language",
            "language": "fr",
            "capabilities": [
                "french-natural-language",
                "hiking-slang",
                "typo-tolerance",
                "french-number-words",
                "personal-vocabulary-learning",
                "intent-parsing",
                "multi-candidate-planning",
                "scenic-scoring",
                "logistics-scoring",
                "real-routing",
                "water-check",
                "transit-proximity",
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
                detail="Le conseiller TrekMap n'a pas pu comprendre ou construire ce plan. Reformule la demande ou précise la zone.",
            ) from exc
