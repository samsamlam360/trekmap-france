"""TrekMap Agent v8: TrekBrain self-learning planner.

V8 keeps the v7 Web/Gemini research agent, but puts a persistent local learning
model in front of it. TrekBrain generates strategy hypotheses, evaluates the
result, can retry with an alternative strategy, learns from explicit feedback and
measures uncertainty to decide when a clarification question is useful.
"""
from __future__ import annotations

import os
import re
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from . import smart_planner_v7 as v7
from .compound_language_v5 import extract_side_requests
from .language_engine import normalize_for_planner
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
)

PLANNER_VERSION = "trekmap-self-learning-agent-v8"


class FeedbackRequest(BaseModel):
    token: str = Field(min_length=8, max_length=80)
    rating: str = Field(min_length=2, max_length=20)
    comment: str = Field(default="", max_length=500)


def _learning_context(data, legacy_main, user_id: int):
    normalized, _ = normalize_for_planner(data.prompt)
    compound = extract_side_requests(normalized)
    combined, global_state, user_state = model_for_user(legacy_main, user_id)
    features = extract_features(data, normalized, compound)
    ranked = rank_actions(combined, features)
    return normalized, compound, features, ranked, combined, global_state, user_state


def _explicit_preference(features: dict[str, float]) -> bool:
    return any(features.get(k, 0) > 0 for k in (
        "scenic", "lake", "peak", "waterfall", "heritage", "village",
        "wild", "event", "camping", "refuge", "easy", "hard",
    ))


def _learning_question(ranked: list[dict[str, Any]], features: dict[str, float], combined: dict[str, Any]) -> dict[str, Any] | None:
    if not ranked or _explicit_preference(features):
        return None
    margin = float(ranked[0].get("margin", 1.0))
    personal_samples = int(combined.get("personal_samples", 0))
    # Ask only when the request is genuinely generic and the model has no clear
    # preference yet. Once personal learning is established, it can infer this.
    if margin > 0.42 or personal_samples >= 8:
        return None
    return {
        "id": "trekbrain_priority",
        "question": "Qu’est-ce qui compte le plus pour ce trek ?",
        "why": "Ta demande laisse plusieurs parcours plausibles et ce choix peut vraiment changer l’itinéraire.",
        "options": ["Beaux paysages", "Logistique pratique", "Patrimoine et villages", "Nature sauvage", "Équilibré"],
    }


def _strategy_payload_prompt(prompt: str, action: str, *, reflection: str = "") -> str:
    strategy = strategy_prompt(action)
    extra = (
        "\n\nContexte interne TrekBrain : "
        f"explorer une hypothèse {ACTION_LABELS.get(action, action)} ; {strategy}. "
        "Ce contexte ne remplace jamais les contraintes explicites de l’utilisateur."
    )
    if reflection:
        extra += " Révision demandée : " + re.sub(r"\s+", " ", reflection).strip()[:700]
    return (str(prompt or "").strip() + extra)[:4000]


def _run_hypothesis(data, legacy_main, user_id: int, action: str, features: dict[str, float], *, reflection: str = ""):
    candidate = data.model_copy(update={"prompt": _strategy_payload_prompt(data.prompt, action, reflection=reflection)})
    result = v7._build(candidate, legacy_main, user_id)
    quality = evaluate_plan(result, data, features)
    return result, quality


def _build(data, legacy_main, user_id: int):
    normalized, compound, features, ranked, combined, global_state, user_state = _learning_context(data, legacy_main, user_id)
    primary_action = ranked[0]["action"] if ranked else "balanced"
    hypotheses: list[dict[str, Any]] = []

    first, quality1 = _run_hypothesis(data, legacy_main, user_id, primary_action, features)
    hypotheses.append({"strategy": primary_action, "quality": quality1})
    chosen_result, chosen_quality, chosen_action = first, quality1, primary_action

    threshold = float(os.getenv("TREKBRAIN_REFLECTION_THRESHOLD", "68") or 68)
    allow_reflection = str(os.getenv("TREKBRAIN_REFLECTION", "1")).strip().casefold() not in {"0", "false", "off", "no"}
    if allow_reflection and quality1["score"] < threshold and len(ranked) > 1:
        alternative = next((x["action"] for x in ranked[1:] if x["action"] != primary_action), "balanced")
        reason = "; ".join(quality1.get("reasons") or []) or "la première hypothèse manque de robustesse"
        try:
            second, quality2 = _run_hypothesis(
                data, legacy_main, user_id, alternative, features,
                reflection=f"La première hypothèse était notée {quality1['score']}/100 car {reason}. Chercher une solution réellement différente.",
            )
            hypotheses.append({"strategy": alternative, "quality": quality2})
            if quality2["score"] > quality1["score"] + 1.0:
                chosen_result, chosen_quality, chosen_action = second, quality2, alternative
        except HTTPException:
            pass
        except Exception:
            pass

    brain_summary = public_summary(combined, ranked)
    trekbrain = chosen_result.setdefault("trekbrain", {})
    trekbrain.update({
        "version": MODEL_VERSION,
        "strategy": chosen_action,
        "strategy_label": ACTION_LABELS.get(chosen_action, chosen_action),
        "quality": chosen_quality,
        "hypotheses": hypotheses,
        "model": brain_summary,
        "features_used": sorted(features.keys()),
        "learning_mode": "online-contextual",
        "stores_raw_prompt": False,
    })

    notes = chosen_result.setdefault("advisor_notes", [])
    if len(hypotheses) > 1:
        notes.insert(0, f"🧠 TrekBrain a généré {len(hypotheses)} hypothèses et a retenu la stratégie « {ACTION_LABELS.get(chosen_action, chosen_action)} » ({chosen_quality['score']}/100).")
    else:
        notes.insert(0, f"🧠 TrekBrain a choisi la stratégie « {ACTION_LABELS.get(chosen_action, chosen_action)} » et l’évalue à {chosen_quality['score']}/100.")
    if chosen_quality.get("reasons"):
        notes.append("Auto-évaluation locale : " + " ; ".join(chosen_quality["reasons"][:4]) + ".")

    token = create_episode(legacy_main, user_id, data.prompt, chosen_action, features, chosen_result)
    chosen_result["learning_token"] = token
    chosen_result["model"] = PLANNER_VERSION
    chosen_result.setdefault("agent", {})["local_learning_brain"] = {
        "version": MODEL_VERSION,
        "strategy": chosen_action,
        "quality": chosen_quality["score"],
        "hypotheses_compared": len(hypotheses),
        "personal_samples": brain_summary["personal_samples"],
        "shared_samples": brain_summary["samples"] - brain_summary["personal_samples"],
    }
    return chosen_result


def install_smart_planner(app, legacy_main):
    # Install all v7 language/research endpoints first, then replace only the
    # planning, clarification and status endpoints with the learning versions.
    v7.install_smart_planner(app, legacy_main)
    replace = {"/ai/status", "/ai/clarify", "/ai/plan", "/ai/feedback", "/ai/brain"}
    app.router.routes = [route for route in app.router.routes if route.path not in replace]

    @app.get("/ai/status")
    def status():
        google = bool(os.getenv("GOOGLE_CSE_API_KEY", "").strip() and os.getenv("GOOGLE_CSE_CX", "").strip())
        brave = bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip())
        return {
            "configured": True,
            "model": PLANNER_VERSION,
            "engine": "self-learning-research-agent",
            "local_brain": MODEL_VERSION,
            "learning": True,
            "brain": "gemini-teacher+trekbrain" if v7.brain_configured() else "trekbrain-local",
            "web_search": True,
            "web_provider": "Google" if google else ("Brave" if brave else "DuckDuckGo fallback"),
            "routing": bool(os.getenv("ORS_API_KEY", "").strip()),
            "cost_per_request": 0 if not v7.brain_configured() else "gemini-free-tier-dependent",
            "capabilities": [
                "online-learning", "persistent-model", "personal-adaptation", "shared-learning",
                "hypothesis-generation", "self-evaluation", "reflection-retry", "uncertainty",
                "clarification-dialogue", "optional-gemini-teacher", "web-research",
                "validated-waypoints", "real-routing", "feedback-learning",
            ],
        }

    @app.post("/ai/clarify")
    def clarify(data: v7.v5.v3.AIPlanRequest, user=Depends(legacy_main.current_user)):
        normalized, compound, brain, questions = v7._analysis_for(data)
        if v7._has_answer_block(data.prompt):
            questions = []
        try:
            features, ranked, combined = None, None, None
            _, _, features, ranked, combined, _, _ = _learning_context(data, legacy_main, int(user["id"]))
            local_q = _learning_question(ranked, features, combined)
            if local_q and not questions and not v7._has_answer_block(data.prompt):
                questions = [local_q]
        except Exception:
            ranked, combined = [], {}
        return {
            "needs_clarification": bool(questions),
            "questions": questions[:3],
            "understood": (brain or {}).get("summary") or normalized[:700],
            "confidence": (brain or {}).get("confidence"),
            "brain": "gemini+trekbrain" if v7.brain_configured() else "trekbrain-local",
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
            raise HTTPException(
                status_code=500,
                detail="TrekBrain n’a pas réussi à produire un plan assez cohérent. Essaie une zone plus précise ou réponds aux questions de clarification.",
            ) from exc

    @app.post("/ai/feedback")
    def feedback(body: FeedbackRequest, user=Depends(legacy_main.current_user)):
        rating = body.rating.strip().casefold()
        mapping = {
            "up": 1.0, "good": 1.0, "like": 1.0, "positive": 1.0,
            "down": -1.0, "bad": -1.0, "dislike": -1.0, "negative": -1.0,
            "saved": 0.7, "save": 0.7,
        }
        if rating not in mapping:
            raise HTTPException(status_code=400, detail="Retour invalide.")
        try:
            learned = apply_feedback(legacy_main, int(user["id"]), body.token, mapping[rating], body.comment)
            learned["message"] = "TrekBrain a intégré ce retour." if not learned.get("already_learned") else "Ce résultat avait déjà été utilisé pour l’apprentissage."
            return learned
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="L’apprentissage est momentanément indisponible.") from exc

    @app.get("/ai/brain")
    def brain_state(user=Depends(legacy_main.current_user)):
        try:
            combined, _, _ = model_for_user(legacy_main, int(user["id"]))
            # Neutral request features are enough to expose learning statistics;
            # strategy ranking here is not used to plan anything.
            ranked = rank_actions(combined, {"bias": 1.0, "generic": 1.0})
            return public_summary(combined, ranked)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Le modèle d’apprentissage est momentanément indisponible.") from exc
