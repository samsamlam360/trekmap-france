"""Compound French request parser for TrekMap Planner v5.

Pure Python, no LLM: extracts secondary objectives, dates and importance from long,
messy hiking requests after language_engine has normalised slang and common typos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Any

from .language_engine import fold

MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12,
}

ORDINAL_DAYS = {
    "premier": 1, "1er": 1, "deuxieme": 2, "2e": 2, "second": 2,
    "troisieme": 3, "3e": 3, "quatrieme": 4, "4e": 4, "cinquieme": 5,
    "5e": 5, "sixieme": 6, "6e": 6, "septieme": 7, "7e": 7,
}

SIDE_CATEGORIES = {
    "castle": ("chateau", "fort", "forteresse", "citadelle", "ruines"),
    "village": ("village", "bourg", "hameau"),
    "event": ("fete", "festival", "fest noz", "fest-noz", "foire", "brocante", "concert", "bal", "marche nocturne"),
    "lake": ("lac", "etang"),
    "waterfall": ("cascade",),
    "peak": ("sommet", "pic", "crete"),
    "heritage": ("musee", "monument", "eglise", "abbaye", "patrimoine"),
    "food_local": ("restaurant local", "resto local", "produit local", "marche local", "specialite locale"),
}

ACTION_WORDS = (
    "visiter", "voir", "passer par", "faire un detour par", "decouvrir", "s arreter",
    "m arreter", "dormir", "manger", "aller", "traverser", "profiter", "assister",
)

SOFT_MARKERS = ("si possible", "si on peut", "si y a", "si il y a", "idealement", "de preference", "pourquoi pas")
HARD_MARKERS = ("obligatoire", "absolument", "imperatif", "il faut", "je veux", "je voudrais", "doit")


@dataclass
class SideRequest:
    kind: str
    text: str
    required: bool = False
    preferred_day: int | None = None
    target_date: str | None = None
    keywords: str = ""
    resolved_name: str | None = None
    source: str | None = None


def _safe_date(day: int, month: int, year: int | None, *, today: date | None = None) -> date | None:
    today = today or date.today()
    y = year or today.year
    try:
        candidate = date(y, month, day)
    except ValueError:
        return None
    if year is None and candidate < today - timedelta(days=7):
        try:
            candidate = date(y + 1, month, day)
        except ValueError:
            return None
    return candidate


def extract_dates(text_value: str, *, today: date | None = None) -> dict[str, Any]:
    """Extract explicit trek dates and standalone calendar dates from French text."""
    text = fold(text_value)
    today = today or date.today()
    out: dict[str, Any] = {"start_date": None, "end_date": None, "mentioned_dates": []}

    # du 12 au 15 juillet [2027]
    m = re.search(r"\bdu\s+(\d{1,2})\s+au\s+(\d{1,2})\s+([a-z]+)(?:\s+(20\d{2}))?\b", text)
    if m and m.group(3) in MONTHS:
        month = MONTHS[m.group(3)]
        year = int(m.group(4)) if m.group(4) else None
        start = _safe_date(int(m.group(1)), month, year, today=today)
        end = _safe_date(int(m.group(2)), month, year or (start.year if start else None), today=today)
        if start and end:
            if end < start:
                try:
                    end = end.replace(year=end.year + 1)
                except ValueError:
                    pass
            out["start_date"], out["end_date"] = start.isoformat(), end.isoformat()

    # du 12 juillet au 15 juillet [2027]
    m = re.search(r"\bdu\s+(\d{1,2})\s+([a-z]+)\s+au\s+(\d{1,2})\s+([a-z]+)(?:\s+(20\d{2}))?\b", text)
    if m and m.group(2) in MONTHS and m.group(4) in MONTHS:
        year = int(m.group(5)) if m.group(5) else None
        start = _safe_date(int(m.group(1)), MONTHS[m.group(2)], year, today=today)
        end_year = year or (start.year if start else None)
        end = _safe_date(int(m.group(3)), MONTHS[m.group(4)], end_year, today=today)
        if start and end:
            if end < start:
                try:
                    end = end.replace(year=end.year + 1)
                except ValueError:
                    pass
            out["start_date"], out["end_date"] = start.isoformat(), end.isoformat()

    # départ le 12 juillet [2027]
    m = re.search(r"(?:depart|partir|commencer)\s+(?:le\s+)?(\d{1,2})\s+([a-z]+)(?:\s+(20\d{2}))?", text)
    if m and m.group(2) in MONTHS:
        d = _safe_date(int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)) if m.group(3) else None, today=today)
        if d:
            out["start_date"] = d.isoformat()

    # Every explicit day-month mention is useful for side requests.
    for m in re.finditer(r"\b(?:le\s+)?(\d{1,2})\s+([a-z]+)(?:\s+(20\d{2}))?\b", text):
        month_name = m.group(2)
        if month_name not in MONTHS:
            continue
        d = _safe_date(int(m.group(1)), MONTHS[month_name], int(m.group(3)) if m.group(3) else None, today=today)
        if d and d.isoformat() not in out["mentioned_dates"]:
            out["mentioned_dates"].append(d.isoformat())

    # 14/07[/2027]
    for m in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\b", text):
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None, today=today)
        if d and d.isoformat() not in out["mentioned_dates"]:
            out["mentioned_dates"].append(d.isoformat())

    return out


def _day_from_clause(clause: str) -> int | None:
    text = fold(clause)
    m = re.search(r"\bjour\s*(\d{1,2})\b", text)
    if m:
        return max(1, min(int(m.group(1)), 21))
    m = re.search(r"\b(\d{1,2})(?:e|eme|er)?\s+jour\b", text)
    if m:
        return max(1, min(int(m.group(1)), 21))
    for word, number in ORDINAL_DAYS.items():
        if re.search(rf"\b{re.escape(word)}\s+jour\b", text):
            return number
    return None


def _date_from_clause(clause: str, dates: dict[str, Any]) -> str | None:
    text = fold(clause)
    for m in re.finditer(r"\b(?:le\s+)?(\d{1,2})\s+([a-z]+)(?:\s+(20\d{2}))?\b", text):
        if m.group(2) in MONTHS:
            d = _safe_date(int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)) if m.group(3) else None)
            if d:
                return d.isoformat()
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\b", text)
    if m:
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None)
        if d:
            return d.isoformat()
    # If the clause speaks about an event and there is only one date in the whole request,
    # associate it with that event.
    if any(k in text for k in SIDE_CATEGORIES["event"]) and len(dates.get("mentioned_dates") or []) == 1:
        return dates["mentioned_dates"][0]
    return None


def _segment(text_value: str) -> list[str]:
    """Keep meaningful conjunctions while splitting a long request into objectives."""
    text = re.sub(r"\s+", " ", fold(text_value)).strip()
    rough = re.split(r"[.;!?\n]+|\s+(?:puis|ensuite|et aussi|mais aussi|par contre|en plus)\s+", text)
    clauses: list[str] = []
    for part in rough:
        part = part.strip(" ,")
        if not part:
            continue
        # Split repeated action clauses joined by 'et' without exploding ordinary noun lists.
        pieces = re.split(r"\s+et\s+(?=(?:je\s+)?(?:veux|voudrais|aimerais|souhaite|passer|visiter|voir|dormir|manger|assister|aller)\b)", part)
        clauses.extend(x.strip(" ,") for x in pieces if x.strip(" ,"))
    return clauses[:24]


def extract_side_requests(normalized_text: str, *, today: date | None = None) -> dict[str, Any]:
    dates = extract_dates(normalized_text, today=today)
    requests: list[SideRequest] = []
    clauses = _segment(normalized_text)

    for clause in clauses:
        hits: list[tuple[str, str]] = []
        for kind, words in SIDE_CATEGORIES.items():
            for word in words:
                if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", clause):
                    hits.append((kind, word))
                    break
        if not hits:
            continue

        has_action = any(action in clause for action in ACTION_WORDS)
        has_event = any(kind == "event" for kind, _ in hits)
        if not has_action and not has_event:
            # Keep explicit preference clauses such as 'avec un château' or 'un village typique'.
            if not re.search(r"\b(?:avec|pres de|proche de|un|une|des)\b", clause):
                continue

        soft = any(marker in clause for marker in SOFT_MARKERS)
        hard = any(marker in clause for marker in HARD_MARKERS)
        preferred_day = _day_from_clause(clause)
        target_date = _date_from_clause(clause, dates)

        for kind, word in hits:
            requests.append(SideRequest(
                kind=kind,
                text=clause[:260],
                required=bool(hard and not soft),
                preferred_day=preferred_day,
                target_date=target_date,
                keywords=word,
            ))

    # Merge duplicate category/date/day requests while preserving strongest wording.
    merged: dict[tuple[str, int | None, str | None], SideRequest] = {}
    for req in requests:
        key = (req.kind, req.preferred_day, req.target_date)
        old = merged.get(key)
        if old is None or (req.required and not old.required):
            merged[key] = req
    result = list(merged.values())[:10]

    return {
        "dates": dates,
        "side_requests": [asdict(x) for x in result],
        "clauses": clauses,
    }


def semantic_summary(compound: dict[str, Any]) -> list[str]:
    labels = {
        "castle": "visite d’un château / site fortifié",
        "village": "passage par un village",
        "event": "événement local",
        "lake": "passage par un lac",
        "waterfall": "passage par une cascade",
        "peak": "passage par un sommet",
        "heritage": "visite patrimoine",
        "food_local": "étape gourmande locale",
    }
    out = []
    for req in compound.get("side_requests") or []:
        line = labels.get(req.get("kind"), req.get("kind", "demande secondaire"))
        if req.get("preferred_day"):
            line += f" · jour {req['preferred_day']}"
        if req.get("target_date"):
            line += f" · {req['target_date']}"
        line += " · obligatoire" if req.get("required") else " · préférence"
        out.append(line)
    return out
