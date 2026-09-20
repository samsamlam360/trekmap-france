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


def _has_explicit_bounds(prompt: str) -> bool:
    text = _fold(prompt)
    number = r"\d{1,2}(?:[.,]\d+)?"
    # Explicit ranges remain authoritative: "18 à 22 km/jour", "18-22 km".
    if re.search(rf"\b{number}\s*(?:a|-|jusqu[' ]?a)\s*{number}\s*km", text):
        return True
    # Explicit upper/lower limits must not be relaxed.
    if re.search(rf"(?:max(?:imum)?|pas\s+plus\s+de|moins\s+de)\s*{number}\s*km", text):
        return True
    if re.search(rf"(?:au\s+moins|min(?:imum)?)\s*{number}\s*km", text):
        return True
    return False


def install_distance_tolerance(v3) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_parse = v3._parse_intent

    def parse_intent(data):
        intent = original_parse(data)
        if _has_explicit_bounds(getattr(data, "prompt", "")):
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


__all__ = ["install_distance_tolerance", "_has_explicit_bounds"]
