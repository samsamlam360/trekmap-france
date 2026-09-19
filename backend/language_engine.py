"""French natural-language layer for TrekMap Planner.

This module stays fully local: no LLM, no paid API. It combines a hiking/slang
lexicon, typo tolerance, French number normalisation and per-user learned rules
stored in PostgreSQL.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import get_close_matches
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text


class LanguageLesson(BaseModel):
    phrase: str = Field(min_length=2, max_length=80)
    meaning: str = Field(min_length=2, max_length=300)


def fold(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in raw if not unicodedata.combining(c)).casefold()


# The right-hand side is deliberately written in the planner's existing
# vocabulary. This is a semantic bridge, not just a spelling dictionary.
PHRASE_LEXICON: dict[str, str] = {
    "tranquillou": "facile tranquille",
    "tranquille": "facile tranquille",
    "pepere": "facile tranquille peu difficile",
    "chill": "facile tranquille",
    "cool": "facile tranquille",
    "pas trop dur": "facile peu difficile",
    "sans se tuer": "facile peu difficile",
    "pas trop physique": "facile peu difficile",
    "costaud": "difficile sportif soutenu",
    "sportif": "difficile sportif",
    "sportive": "difficile sportif",
    "chaud": "difficile soutenu",
    "hard": "difficile soutenu",
    "pechu": "difficile sportif soutenu",
    "qui pique": "difficile sportif soutenu",
    "ca grimpe": "denivele important",
    "ça grimpe": "denivele important",
    "pas trop de denivele": "denivele faible",
    "peu de denivele": "denivele faible",
    "pas trop de d+": "denivele faible",
    "plat": "denivele faible",
    "bornes": "km",
    "borne": "km",
    "kilometres": "km",
    "kilometre": "km",
    "kils": "km",
    "kil": "km",
    "par journee": "par jour",
    "a la journee": "par jour",
    "dodo": "nuitée",
    "dormir dehors": "bivouac",
    "a la belle etoile": "bivouac",
    "belle etoile": "bivouac",
    "sous tente": "camping tente",
    "en tente": "camping tente",
    "gite": "refuge gite",
    "cabane": "refuge abri",
    "point de flotte": "point d eau",
    "de la flotte": "eau",
    "de l eau": "eau",
    "ravito": "ravitaillement",
    "ravitaillement": "ravitaillement",
    "bouffe": "ravitaillement nourriture",
    "courses": "ravitaillement supermarche",
    "beau spot": "panorama beau paysage",
    "beaux spots": "panoramas beaux paysages",
    "spot": "point d interet",
    "belle vue": "panorama vue",
    "belles vues": "panoramas vues",
    "vue de ouf": "panorama vue",
    "coin sauvage": "nature sauvage loin des villes",
    "paume": "sauvage loin des villes",
    "paumé": "sauvage loin des villes",
    "loin de tout": "sauvage loin des villes",
    "eviter la ville": "eviter les villes",
    "pas de ville": "eviter les villes",
    "sans bagnole": "train gare bus transport en commun",
    "pas de bagnole": "train gare bus transport en commun",
    "sans voiture": "train gare bus transport en commun",
    "en train": "train gare transport en commun",
    "accessible en train": "gare train transport en commun",
    "en caisse": "voiture uniquement",
    "en bagnole": "voiture uniquement",
    "faire le tour": "boucle circuit",
    "revenir au meme endroit": "boucle circuit",
    "point de depart": "depart",
    "point d arrivee": "arrivee",
    "faire une traversee": "traversee itinerance lineaire",
    "tracer": "itineraire",
    "rando": "randonnée trek",
    "randos": "randonnées treks",
}

NUMBER_WORDS = {
    "un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4",
    "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9",
    "dix": "10", "onze": "11", "douze": "12", "treize": "13",
    "quatorze": "14", "quinze": "15", "seize": "16", "vingt": "20",
}

APPROX_NUMBERS = {
    "une dizaine": "10",
    "dizaine": "10",
    "une quinzaine": "15",
    "quinzaine": "15",
    "une vingtaine": "20",
    "vingtaine": "20",
    "une trentaine": "30",
    "trentaine": "30",
}

TYPO_VOCAB = {
    "boucle", "traversee", "itinerance", "camping", "bivouac", "refuge",
    "sommet", "sommets", "cascade", "cascades", "panorama", "panoramas",
    "village", "villages", "patrimoine", "nature", "sauvage", "tranquille",
    "difficile", "sportif", "facile", "denivele", "ravitaillement", "gare",
    "train", "transport", "depart", "arrivee", "kilometres", "jours",
}


def _replace_phrase(text_value: str, source: str, target: str) -> tuple[str, bool]:
    source = fold(source).strip()
    if not source:
        return text_value, False
    pattern = r"(?<!\w)" + re.escape(source) + r"(?!\w)"
    new, count = re.subn(pattern, target, text_value, flags=re.I)
    return new, count > 0


def _normalise_numbers(text_value: str) -> str:
    out = text_value
    for phrase, number in sorted(APPROX_NUMBERS.items(), key=lambda x: -len(x[0])):
        out, _ = _replace_phrase(out, phrase, number)
    for word, number in NUMBER_WORDS.items():
        out = re.sub(rf"\b{re.escape(word)}\b(?=\s*(?:jours?|j\b|km\b|bornes?\b))", number, out)
    return out


def _correct_typo_tokens(text_value: str) -> tuple[str, list[str]]:
    tokens = re.findall(r"\b[\w'-]+\b|\W+", text_value, flags=re.UNICODE)
    matches: list[str] = []
    out = []
    for token in tokens:
        simple = re.sub(r"[^a-z0-9]", "", fold(token))
        if len(simple) < 5 or not simple.isalpha() or simple in TYPO_VOCAB:
            out.append(token)
            continue
        close = get_close_matches(simple, TYPO_VOCAB, n=1, cutoff=0.84)
        if close:
            replacement = close[0]
            out.append(replacement)
            matches.append(f"{token} → {replacement}")
        else:
            out.append(token)
    return "".join(out), matches


def normalize_for_planner(prompt: str, learned_rules: list[dict[str, Any]] | None = None) -> tuple[str, list[str]]:
    """Return folded semantic text + explanations of what was interpreted."""
    text_value = fold(prompt)
    matches: list[str] = []

    # User vocabulary has priority over defaults.
    for rule in learned_rules or []:
        phrase = fold(rule.get("phrase") or "")
        meaning = fold(rule.get("meaning") or "")
        if not phrase or not meaning:
            continue
        text_value, applied = _replace_phrase(text_value, phrase, meaning)
        if applied:
            matches.append(f"« {rule.get('phrase', phrase)} » = {rule.get('meaning', meaning)}")

    for phrase, meaning in sorted(PHRASE_LEXICON.items(), key=lambda x: -len(x[0])):
        text_value, applied = _replace_phrase(text_value, phrase, meaning)
        if applied and phrase != meaning:
            matches.append(f"« {phrase} » compris comme « {meaning} »")

    text_value = _normalise_numbers(text_value)
    text_value, typo_matches = _correct_typo_tokens(text_value)
    matches.extend(typo_matches)
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return text_value, list(dict.fromkeys(matches))[:12]


def ensure_language_schema(legacy_main) -> None:
    db = legacy_main.SessionLocal()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_language_rules (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                phrase VARCHAR(80) NOT NULL,
                meaning VARCHAR(300) NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, phrase)
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_trek_language_rules_user ON trek_language_rules(user_id, updated_at DESC)"))
        db.commit()
    finally:
        db.close()


def list_rules(legacy_main, user_id: int) -> list[dict[str, Any]]:
    db = legacy_main.SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT id, phrase, meaning, usage_count, updated_at
            FROM trek_language_rules
            WHERE user_id=:uid
            ORDER BY updated_at DESC, id DESC
            LIMIT 50
        """), {"uid": int(user_id)}).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


def learn_rule(legacy_main, user_id: int, phrase: str, meaning: str) -> dict[str, Any]:
    phrase_clean = re.sub(r"\s+", " ", str(phrase or "")).strip(" \t\n.,;:!?\"'«»")
    meaning_clean = re.sub(r"\s+", " ", str(meaning or "")).strip()
    if not 2 <= len(phrase_clean) <= 80:
        raise ValueError("L'expression doit contenir entre 2 et 80 caractères.")
    if not 2 <= len(meaning_clean) <= 300:
        raise ValueError("La signification doit contenir entre 2 et 300 caractères.")
    # Store a folded key so accents/case do not create duplicate personal rules.
    phrase_key = fold(phrase_clean)
    db = legacy_main.SessionLocal()
    try:
        row = db.execute(text("""
            INSERT INTO trek_language_rules(user_id, phrase, meaning, updated_at)
            VALUES(:uid, :phrase, :meaning, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, phrase)
            DO UPDATE SET meaning=EXCLUDED.meaning, updated_at=CURRENT_TIMESTAMP
            RETURNING id, phrase, meaning, usage_count, updated_at
        """), {"uid": int(user_id), "phrase": phrase_key, "meaning": meaning_clean}).mappings().first()
        # Keep the feature bounded per account. The newest 50 survive.
        db.execute(text("""
            DELETE FROM trek_language_rules
            WHERE user_id=:uid AND id NOT IN (
                SELECT id FROM trek_language_rules
                WHERE user_id=:uid
                ORDER BY updated_at DESC, id DESC
                LIMIT 50
            )
        """), {"uid": int(user_id)})
        db.commit()
        return dict(row) if row else {"phrase": phrase_key, "meaning": meaning_clean}
    finally:
        db.close()


def delete_rule(legacy_main, user_id: int, rule_id: int) -> bool:
    db = legacy_main.SessionLocal()
    try:
        result = db.execute(text("DELETE FROM trek_language_rules WHERE id=:id AND user_id=:uid"), {"id": int(rule_id), "uid": int(user_id)})
        db.commit()
        return bool(result.rowcount)
    finally:
        db.close()


def mark_rules_used(legacy_main, user_id: int, rules: list[dict[str, Any]], normalized_matches: list[str]) -> None:
    if not rules or not normalized_matches:
        return
    used_ids = []
    joined = "\n".join(normalized_matches)
    for rule in rules:
        if f"« {rule.get('phrase')} »" in joined:
            used_ids.append(int(rule["id"]))
    if not used_ids:
        return
    db = legacy_main.SessionLocal()
    try:
        db.execute(text("""
            UPDATE trek_language_rules
            SET usage_count=usage_count+1, updated_at=CURRENT_TIMESTAMP
            WHERE user_id=:uid AND id = ANY(:ids)
        """), {"uid": int(user_id), "ids": used_ids})
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def extract_inline_lesson(prompt: str) -> tuple[str, str] | None:
    """Recognise explicit teaching such as 'quand je dis X, ça veut dire Y'."""
    raw = re.sub(r"\s+", " ", str(prompt or "")).strip()
    patterns = [
        r"(?:retiens|mémorise|memorise)\s+que\s+[«\"']?(.+?)[»\"']?\s+(?:veut\s+dire|signifie|=)\s+(.+)$",
        r"quand\s+je\s+dis\s+[«\"']?(.+?)[»\"']?\s*[,;:]?\s*(?:ça|ca|cela)\s+(?:veut\s+dire|signifie)\s+(.+)$",
        r"pour\s+moi\s+[«\"']?(.+?)[»\"']?\s*(?:=|veut\s+dire|signifie)\s+(.+)$",
    ]
    for pattern in patterns:
        m = re.search(pattern, raw, flags=re.I)
        if m:
            phrase = m.group(1).strip(" \"'«».,;:")
            meaning = m.group(2).strip()
            if 2 <= len(phrase) <= 80 and 2 <= len(meaning) <= 300:
                return phrase, meaning
    return None
