"""TrekBrain v8: a small self-learning model specialised in trekking.

This is deliberately not a fake general-purpose LLM. It is a persistent online
learning model that selects planning strategies from request features, generates
planning hypotheses, measures uncertainty and updates its weights from explicit
user feedback. It stores structured features, not full prompts.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import text

MODEL_VERSION = "trekbrain-v8"
ACTIONS = (
    "balanced",
    "scenic",
    "logistics",
    "heritage",
    "wild",
    "easy",
    "challenge",
    "events",
)

ACTION_LABELS = {
    "balanced": "équilibré",
    "scenic": "panoramique",
    "logistics": "logistique",
    "heritage": "patrimoine et villages",
    "wild": "nature sauvage",
    "easy": "confort / difficulté modérée",
    "challenge": "sportif / sommets",
    "events": "événements et vie locale",
}

# Prior knowledge. Learning only nudges these values, it does not start from
# random noise, which makes the model useful before the first feedback.
DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "balanced": {"bias": 0.75, "generic": 0.65, "multi_day": 0.25},
    "scenic": {
        "bias": 0.20, "scenic": 1.55, "lake": 1.15, "peak": 0.85,
        "waterfall": 1.0, "nature": 0.55, "photo": 0.45,
    },
    "logistics": {
        "bias": 0.15, "transit": 1.25, "sleep": 1.05, "food": 0.75,
        "water": 0.55, "camping": 0.8, "refuge": 0.75, "multi_day": 0.35,
    },
    "heritage": {
        "bias": 0.05, "heritage": 1.65, "village": 1.15, "event": 0.65,
        "food_local": 0.55,
    },
    "wild": {
        "bias": 0.05, "wild": 1.7, "nature": 1.15, "avoid_city": 0.9,
        "bivouac": 0.55,
    },
    "easy": {
        "bias": 0.05, "easy": 1.65, "short_day": 0.85, "low_elevation": 1.0,
        "hard": -1.1, "long_day": -0.7,
    },
    "challenge": {
        "bias": -0.05, "hard": 1.55, "peak": 0.85, "long_day": 0.7,
        "easy": -0.9,
    },
    "events": {
        "bias": -0.10, "event": 1.9, "dated": 1.05, "village": 0.75,
        "heritage": 0.35,
    },
}

STRATEGY_PROMPTS = {
    "balanced": "garder un équilibre entre intérêt du parcours, étapes réalistes et logistique",
    "scenic": "privilégier panoramas, lacs, cascades, crêtes et beaux paysages sans sacrifier les contraintes obligatoires",
    "logistics": "privilégier étapes réalistes, eau, ravitaillement, campings ou refuges et accès transports",
    "heritage": "privilégier patrimoine, châteaux, villages intéressants et découvertes locales",
    "wild": "privilégier nature sauvage, calme, espaces naturels et éloignement des zones urbaines",
    "easy": "privilégier un parcours confortable, étapes régulières, détours limités et dénivelé raisonnable",
    "challenge": "privilégier un parcours sportif cohérent, sommets et points hauts si les contraintes le permettent",
    "events": "privilégier villages, événements datés et vie locale en respectant strictement les dates demandées",
}


def _state_template() -> dict[str, Any]:
    return {
        "version": 1,
        "weights": deepcopy(DEFAULT_WEIGHTS),
        "counts": {action: 0 for action in ACTIONS},
        "reward_sum": {action: 0.0 for action in ACTIONS},
        "samples": 0,
    }


def ensure_schema(legacy_main) -> None:
    db = legacy_main.SessionLocal()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_brain_states (
                scope VARCHAR(64) PRIMARY KEY,
                state_json TEXT NOT NULL,
                samples INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_brain_episodes (
                token VARCHAR(64) PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                prompt_fingerprint VARCHAR(64) NOT NULL,
                action VARCHAR(32) NOT NULL,
                features_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                reward DOUBLE PRECISION,
                feedback VARCHAR(500),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_trek_brain_episodes_user ON trek_brain_episodes(user_id, created_at DESC)"))
        db.commit()
    finally:
        db.close()


def _safe_state(raw: str | None) -> dict[str, Any]:
    base = _state_template()
    if not raw:
        return base
    try:
        parsed = json.loads(raw)
    except Exception:
        return base
    if not isinstance(parsed, dict):
        return base
    weights = parsed.get("weights") or {}
    for action in ACTIONS:
        if isinstance(weights.get(action), dict):
            for feature, value in weights[action].items():
                try:
                    base["weights"][action][str(feature)] = max(-4.0, min(4.0, float(value)))
                except (TypeError, ValueError):
                    pass
    for name in ("counts", "reward_sum"):
        incoming = parsed.get(name) or {}
        if isinstance(incoming, dict):
            for action in ACTIONS:
                try:
                    base[name][action] = int(incoming.get(action, 0)) if name == "counts" else float(incoming.get(action, 0.0))
                except (TypeError, ValueError):
                    pass
    try:
        base["samples"] = max(0, int(parsed.get("samples", 0)))
    except (TypeError, ValueError):
        pass
    return base


def load_state(legacy_main, scope: str) -> dict[str, Any]:
    ensure_schema(legacy_main)
    db = legacy_main.SessionLocal()
    try:
        row = db.execute(text("SELECT state_json FROM trek_brain_states WHERE scope=:scope"), {"scope": scope}).first()
        return _safe_state(row.state_json if row else None)
    finally:
        db.close()


def save_state(legacy_main, scope: str, state: dict[str, Any]) -> None:
    db = legacy_main.SessionLocal()
    try:
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        db.execute(text("""
            INSERT INTO trek_brain_states(scope,state_json,samples,updated_at)
            VALUES(:scope,:payload,:samples,CURRENT_TIMESTAMP)
            ON CONFLICT(scope) DO UPDATE
            SET state_json=EXCLUDED.state_json,samples=EXCLUDED.samples,updated_at=CURRENT_TIMESTAMP
        """), {"scope": scope, "payload": payload, "samples": int(state.get("samples", 0))})
        db.commit()
    finally:
        db.close()


def _blend_states(global_state: dict[str, Any], user_state: dict[str, Any]) -> dict[str, Any]:
    """Blend shared experience with personal learning without erasing either."""
    out = _state_template()
    user_samples = int(user_state.get("samples", 0))
    # Personalisation rises progressively and caps at 70%.
    personal = min(0.70, user_samples / 20.0 * 0.70)
    shared = 1.0 - personal
    for action in ACTIONS:
        keys = set(DEFAULT_WEIGHTS[action]) | set((global_state.get("weights") or {}).get(action, {})) | set((user_state.get("weights") or {}).get(action, {}))
        out["weights"][action] = {}
        for feature in keys:
            g = float((global_state.get("weights") or {}).get(action, {}).get(feature, DEFAULT_WEIGHTS[action].get(feature, 0.0)))
            u = float((user_state.get("weights") or {}).get(action, {}).get(feature, DEFAULT_WEIGHTS[action].get(feature, 0.0)))
            out["weights"][action][feature] = g * shared + u * personal
        out["counts"][action] = int((global_state.get("counts") or {}).get(action, 0)) + int((user_state.get("counts") or {}).get(action, 0))
        out["reward_sum"][action] = float((global_state.get("reward_sum") or {}).get(action, 0.0)) + float((user_state.get("reward_sum") or {}).get(action, 0.0))
    out["samples"] = int(global_state.get("samples", 0)) + user_samples
    out["personal_samples"] = user_samples
    return out


def extract_features(data, normalized: str, compound: dict[str, Any] | None = None) -> dict[str, float]:
    text_value = str(normalized or "").casefold()
    compound = compound or {}
    side = compound.get("side_requests") or []
    days = max(1, int(getattr(data, "days", 1) or 1))
    km = float(getattr(data, "daily_km", 18) or 18)
    difficulty = str(getattr(data, "difficulty", "medium") or "medium").casefold()
    route_type = str(getattr(data, "route_type", "") or "").casefold()

    f: dict[str, float] = {"bias": 1.0}
    f["multi_day"] = min(1.0, max(0.0, (days - 1) / 5.0))
    f["long_day"] = min(1.0, max(0.0, (km - 18.0) / 14.0))
    f["short_day"] = min(1.0, max(0.0, (17.0 - km) / 12.0))
    f["easy"] = 1.0 if difficulty == "easy" or any(x in text_value for x in ("facile", "tranquille", "pepere", "pépère")) else 0.0
    f["hard"] = 1.0 if difficulty == "hard" or any(x in text_value for x in ("difficile", "sportif", "costaud", "soutenu")) else 0.0
    f["loop"] = 1.0 if "boucle" in route_type or "boucle" in text_value else 0.0
    f["traverse"] = 1.0 if "travers" in route_type or "travers" in text_value else 0.0
    f["transit"] = 1.0 if bool(getattr(data, "require_transit", False)) or any(x in text_value for x in ("train", "gare", "bus", "sans voiture", "sans bagnole")) else 0.0
    f["water"] = 1.0 if bool(getattr(data, "require_water", False)) or "eau" in text_value else 0.0
    f["sleep"] = 1.0 if bool(getattr(data, "require_accommodation", False)) else 0.0
    f["food"] = 1.0 if bool(getattr(data, "require_food", False)) or any(x in text_value for x in ("ravitail", "supermarche", "boulanger", "restaurant")) else 0.0
    f["camping"] = 1.0 if "camping" in text_value or "tente" in text_value else 0.0
    f["refuge"] = 1.0 if "refuge" in text_value or "gite" in text_value else 0.0
    f["bivouac"] = 1.0 if "bivouac" in text_value else 0.0
    f["low_elevation"] = 1.0 if any(x in text_value for x in ("peu de denivele", "denivele faible", "pas trop de denivele", "d+ max")) else 0.0
    f["scenic"] = 1.0 if any(x in text_value for x in ("panorama", "beau paysage", "belle vue", "beaux spots", "point de vue")) else 0.0
    f["lake"] = 1.0 if re.search(r"\blacs?\b|\betangs?\b", text_value) else 0.0
    f["peak"] = 1.0 if any(x in text_value for x in ("sommet", "pic", "crete", "crête")) else 0.0
    f["waterfall"] = 1.0 if "cascade" in text_value else 0.0
    f["nature"] = 1.0 if any(x in text_value for x in ("nature", "foret", "forêt", "reserve naturelle")) else 0.0
    f["wild"] = 1.0 if any(x in text_value for x in ("sauvage", "loin de tout", "paume", "paumé", "isolé", "isole")) else 0.0
    f["avoid_city"] = 1.0 if any(x in text_value for x in ("eviter les villes", "éviter les villes", "loin des villes", "pas de ville")) else 0.0
    f["heritage"] = 1.0 if any(x in text_value for x in ("chateau", "château", "patrimoine", "abbaye", "monument", "historique")) else 0.0
    f["village"] = 1.0 if any(x in text_value for x in ("village", "bourg", "hameau")) else 0.0
    f["food_local"] = 1.0 if any(x in text_value for x in ("specialite locale", "spécialité locale", "produit local", "marche local", "marché local")) else 0.0
    f["photo"] = 1.0 if any(x in text_value for x in ("photo", "instagram", "photogen")) else 0.0
    f["event"] = min(1.0, sum(1 for item in side if item.get("kind") == "event") / 2.0)
    f["dated"] = 1.0 if any(item.get("target_date") for item in side) or bool((compound.get("dates") or {}).get("start_date")) else 0.0
    explicit = sum(1 for k in ("scenic", "lake", "peak", "waterfall", "wild", "heritage", "event", "camping", "refuge") if f.get(k))
    f["generic"] = 1.0 if explicit == 0 else 0.0
    return {k: round(float(v), 4) for k, v in f.items() if abs(float(v)) > 1e-9}


def raw_score(state: dict[str, Any], action: str, features: dict[str, float]) -> float:
    weights = (state.get("weights") or {}).get(action, {})
    return sum(float(weights.get(k, 0.0)) * float(v) for k, v in features.items())


def rank_actions(state: dict[str, Any], features: dict[str, float]) -> list[dict[str, Any]]:
    total = max(1, int(state.get("samples", 0)))
    ranked = []
    for action in ACTIONS:
        score = raw_score(state, action, features)
        count = max(0, int((state.get("counts") or {}).get(action, 0)))
        uncertainty = math.sqrt(math.log(total + 2.0) / (count + 1.0))
        # Tiny exploration bonus. It helps the model try plausible alternatives,
        # but never overwhelms the semantic prior.
        decision_score = score + min(0.35, uncertainty * 0.12)
        ranked.append({
            "action": action,
            "label": ACTION_LABELS[action],
            "score": round(score, 4),
            "decision_score": round(decision_score, 4),
            "uncertainty": round(min(1.0, uncertainty), 4),
            "count": count,
        })
    ranked.sort(key=lambda x: x["decision_score"], reverse=True)
    if ranked:
        top = ranked[0]["decision_score"]
        second = ranked[1]["decision_score"] if len(ranked) > 1 else top
        ranked[0]["margin"] = round(top - second, 4)
    return ranked


def model_for_user(legacy_main, user_id: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    global_state = load_state(legacy_main, "global")
    user_state = load_state(legacy_main, f"user:{int(user_id)}")
    return _blend_states(global_state, user_state), global_state, user_state


def strategy_prompt(action: str) -> str:
    return STRATEGY_PROMPTS.get(action, STRATEGY_PROMPTS["balanced"])


def evaluate_plan(result: dict[str, Any], data, features: dict[str, float]) -> dict[str, Any]:
    """Local critic. Returns a transparent quality score, not hidden chain-of-thought."""
    score = 100.0
    reasons: list[str] = []
    confidence = result.get("confidence") or {}
    try:
        confidence_score = float(confidence.get("score", 70))
    except (TypeError, ValueError):
        confidence_score = 70.0
    score -= max(0.0, 78.0 - confidence_score) * 0.45

    stages = result.get("stages") or []
    target = max(3.0, float(getattr(data, "daily_km", 18) or 18))
    if stages:
        deviations = []
        for stage in stages:
            try:
                deviations.append(abs(float(stage.get("distance_km") or target) - target) / target)
            except (TypeError, ValueError):
                pass
        if deviations:
            avg = sum(deviations) / len(deviations)
            score -= min(20.0, avg * 24.0)
            if avg > 0.28:
                reasons.append("les distances quotidiennes sont assez éloignées de la cible")

    side = result.get("side_requests") or []
    required = [x for x in side if isinstance(x, dict) and ((x.get("request") or "") and x.get("preferred_day") is not None or x.get("target_date"))]
    if required:
        missed = sum(1 for x in required if not x.get("satisfied"))
        score -= missed / max(1, len(required)) * 22.0
        if missed:
            reasons.append(f"{missed} objectif(s) secondaire(s) daté(s) ou positionné(s) restent imparfaits")

    limitations = confidence.get("limitations") or []
    important_limitations = [x for x in limitations if x]
    score -= min(14.0, len(important_limitations) * 2.0)
    if result.get("route_preview", {}).get("fallback"):
        score -= 18.0
        reasons.append("le routage est en mode dégradé")

    if features.get("transit") and not ((result.get("transport") or {}).get("outbound") and (result.get("transport") or {}).get("return")):
        score -= 8.0
        reasons.append("l'accès en transports n'est pas suffisamment établi")
    if features.get("sleep") and not result.get("accommodations"):
        score -= 8.0
        reasons.append("aucune nuitée fiable n'a été trouvée")
    if features.get("water") and not result.get("water"):
        score -= 6.0
        reasons.append("aucun point d'eau cartographié n'a été trouvé")

    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
        "needs_reflection": score < 68.0,
        "reasons": reasons[:6],
    }


def _prediction(state: dict[str, Any], action: str, features: dict[str, float]) -> float:
    return math.tanh(raw_score(state, action, features) / 4.0)


def learn_state(state: dict[str, Any], action: str, features: dict[str, float], reward: float, *, scale: float = 1.0) -> dict[str, Any]:
    out = deepcopy(state)
    if action not in ACTIONS:
        return out
    reward = max(-1.0, min(1.0, float(reward)))
    samples = max(0, int(out.get("samples", 0)))
    lr = (0.12 / math.sqrt(1.0 + samples / 18.0)) * float(scale)
    error = reward - _prediction(out, action, features)
    weights = out.setdefault("weights", {}).setdefault(action, {})
    for feature, value in features.items():
        old = float(weights.get(feature, DEFAULT_WEIGHTS.get(action, {}).get(feature, 0.0)))
        weights[feature] = round(max(-4.0, min(4.0, old + lr * error * float(value))), 6)
    out.setdefault("counts", {})[action] = int(out.setdefault("counts", {}).get(action, 0)) + 1
    out.setdefault("reward_sum", {})[action] = round(float(out.setdefault("reward_sum", {}).get(action, 0.0)) + reward, 6)
    out["samples"] = samples + 1
    return out


def create_episode(legacy_main, user_id: int, prompt: str, action: str, features: dict[str, float], result: dict[str, Any]) -> str:
    ensure_schema(legacy_main)
    token = secrets.token_hex(18)
    fingerprint = hashlib.sha256(str(prompt or "").encode("utf-8", "ignore")).hexdigest()
    compact_result = {
        "title": result.get("title"),
        "region": result.get("region"),
        "quality": ((result.get("trekbrain") or {}).get("quality") or {}).get("score"),
        "distance_km": (result.get("route_preview") or {}).get("distance_km"),
        "elevation_gain_m": (result.get("route_preview") or {}).get("elevation_gain_m"),
        "duration_days": result.get("duration_days"),
    }
    db = legacy_main.SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO trek_brain_episodes(token,user_id,prompt_fingerprint,action,features_json,result_json)
            VALUES(:token,:uid,:fingerprint,:action,:features,:result)
        """), {
            "token": token, "uid": int(user_id), "fingerprint": fingerprint,
            "action": action, "features": json.dumps(features, separators=(",", ":")),
            "result": json.dumps(compact_result, ensure_ascii=False, separators=(",", ":")),
        })
        db.commit()
    finally:
        db.close()
    return token


def apply_feedback(legacy_main, user_id: int, token: str, reward: float, comment: str = "") -> dict[str, Any]:
    ensure_schema(legacy_main)
    db = legacy_main.SessionLocal()
    try:
        row = db.execute(text("""
            SELECT token,action,features_json,reward FROM trek_brain_episodes
            WHERE token=:token AND user_id=:uid
        """), {"token": token, "uid": int(user_id)}).mappings().first()
        if not row:
            raise ValueError("Retour introuvable ou expiré.")
        # A token can teach only once. This prevents button-spam from poisoning the model.
        if row.get("reward") is not None:
            return {"ok": True, "already_learned": True}
        action = str(row["action"])
        features = json.loads(row["features_json"])
        reward = max(-1.0, min(1.0, float(reward)))
        feedback = re.sub(r"\s+", " ", str(comment or "")).strip()[:500]
        db.execute(text("""
            UPDATE trek_brain_episodes
            SET reward=:reward,feedback=:feedback,updated_at=CURRENT_TIMESTAMP
            WHERE token=:token AND user_id=:uid
        """), {"reward": reward, "feedback": feedback, "token": token, "uid": int(user_id)})
        db.commit()
    finally:
        db.close()

    global_state = load_state(legacy_main, "global")
    user_state = load_state(legacy_main, f"user:{int(user_id)}")
    # Personal model learns faster. Shared model moves slowly to avoid one user
    # dominating everybody else's experience.
    user_state = learn_state(user_state, action, features, reward, scale=1.0)
    global_state = learn_state(global_state, action, features, reward, scale=0.28)
    save_state(legacy_main, f"user:{int(user_id)}", user_state)
    save_state(legacy_main, "global", global_state)
    return {
        "ok": True,
        "already_learned": False,
        "reward": reward,
        "strategy": action,
        "user_samples": user_state.get("samples", 0),
        "global_samples": global_state.get("samples", 0),
    }


def public_summary(combined: dict[str, Any], ranked: list[dict[str, Any]]) -> dict[str, Any]:
    samples = int(combined.get("samples", 0))
    personal_samples = int(combined.get("personal_samples", 0))
    top = ranked[0] if ranked else None
    return {
        "version": MODEL_VERSION,
        "samples": samples,
        "personal_samples": personal_samples,
        "preferred_strategy": top.get("action") if top else "balanced",
        "preferred_strategy_label": top.get("label") if top else ACTION_LABELS["balanced"],
        "uncertainty": top.get("uncertainty") if top else 1.0,
        "top_strategies": [
            {"action": x["action"], "label": x["label"], "score": x["score"], "count": x["count"]}
            for x in ranked[:3]
        ],
        "last_updated": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
