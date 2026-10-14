"""Daily-distance tolerance for TrekBrain v9.

A value such as ``20 km/jour`` is a target, not an exact equality. Unless the
user explicitly gives a range/minimum/maximum, TrekBrain accepts roughly +/-25%
per day while continuing to score routes by closeness to the target.
"""
from __future__ import annotations

import re
import unicodedata

_INSTALLED = False


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def explicit_daily_bounds(prompt: str) -> tuple[float | None, float | None]:
    """Return only kilometre bounds actually stated, never inferred limits."""
    text = _fold(prompt)
    number = r"\d{1,2}(?:[.,]\d+)?"
    value = lambda match: float(match.replace(",", "."))
    minimum = maximum = None
    interval = re.search(
        rf"\b(?:entre\s+)?({number})\s*(?:a|-|jusqu[' ]?a|et)\s*({number})\s*km", text,
    )
    if interval:
        minimum, maximum = sorted((value(interval.group(1)), value(interval.group(2))))
    upper = re.search(rf"(?:max(?:imum)?|pas\s+plus\s+de|moins\s+de)\s*({number})\s*km", text)
    lower = re.search(rf"(?:au\s+moins|min(?:imum)?)\s*({number})\s*km", text)
    if upper:
        maximum = value(upper.group(1))
    if lower:
        minimum = value(lower.group(1))
    return minimum, maximum


def _has_explicit_bounds(prompt: str) -> bool:
    return any(bound is not None for bound in explicit_daily_bounds(prompt))


def intent_daily_bounds(intent) -> tuple[float | None, float | None]:
    """Read declared bounds from parsed intent or its original request text."""
    intent = intent or {}
    parsed = explicit_daily_bounds(intent.get("raw") or "")
    return tuple(intent.get(key, bound) for key, bound in zip(
        ("explicit_daily_min", "explicit_daily_max"), parsed,
    ))


def install_distance_tolerance(v3) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_parse = v3._parse_intent

    def parse_intent(data):
        intent = original_parse(data)
        minimum, maximum = explicit_daily_bounds(getattr(data, "prompt", ""))
        intent["explicit_daily_min"] = minimum
        intent["explicit_daily_max"] = maximum
        if minimum is not None or maximum is not None:
            intent["distance_tolerance"] = "explicit"
            return intent

        target = float(intent.get("daily_target") or getattr(data, "daily_km", 18) or 18)
        # 20 km -> 15..25 km. Keep the product's global 3..40 km limits.
        intent["daily_min"] = round(max(3.0, target * 0.75), 1)
        intent["daily_max"] = round(min(40.0, target * 1.25), 1)
        intent["distance_tolerance"] = "soft-25pct"
        # total_target remains centred on the requested target. The optimisers
        # therefore still prefer ~20 km days even though 15..25 is feasible.
        intent["total_target"] = round(target * max(1, int(intent.get("days") or 1)), 1)
        return intent

    v3._parse_intent = parse_intent


__all__ = ["install_distance_tolerance", "_has_explicit_bounds", "explicit_daily_bounds", "intent_daily_bounds"]
