"""Failure transparency for TrekBrain v9.

Historically smart_planner_v5 tried several language variants and swallowed every
underlying HTTPException. If they all failed, users always received the same
"parcours cohérent" message, hiding whether the actual cause was ORS, missing
geodata, mileage, or lodging. This layer preserves the useful orchestration while
surfacing the most recent real planner failure when all variants fail.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException

_INSTALLED = False
_LAST_ERROR: ContextVar[HTTPException | None] = ContextVar(
    "trekbrain_v9_last_planner_error", default=None
)
_GENERIC_FRAGMENT = "parcours cohérent avec l’ensemble de ces demandes"
_GENERIC_FRAGMENT_ASCII = "parcours coherent avec l'ensemble de ces demandes"


def _is_generic(exc: HTTPException) -> bool:
    detail = str(getattr(exc, "detail", exc) or "").casefold()
    return _GENERIC_FRAGMENT.casefold() in detail or _GENERIC_FRAGMENT_ASCII in detail


def _prefer_underlying(wrapper_error: HTTPException, underlying: HTTPException | None) -> HTTPException:
    if underlying is not None and _is_generic(wrapper_error):
        return underlying
    return wrapper_error


def install_failure_diagnostics(v3: Any, v5: Any, v7: Any) -> None:
    """Make v5/v7 propagate the real v3/ORS error instead of a generic 422."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    current_v3_build = v3._build
    current_v5_build = v5._build

    def diagnostic_v3_build(data, legacy_main):
        try:
            return current_v3_build(data, legacy_main)
        except HTTPException as exc:
            _LAST_ERROR.set(exc)
            raise

    v3._build = diagnostic_v3_build

    def transparent_v5_build(data, legacy_main, user_id: int):
        token = _LAST_ERROR.set(None)
        try:
            return current_v5_build(data, legacy_main, user_id)
        except HTTPException as exc:
            chosen = _prefer_underlying(exc, _LAST_ERROR.get())
            if chosen is not exc:
                raise chosen
            raise
        finally:
            _LAST_ERROR.reset(token)

    # v7 captured v5._build at import time, so patch both references.
    v5._build = transparent_v5_build
    v7._BASE_BUILD = transparent_v5_build


__all__ = [
    "install_failure_diagnostics",
    "_prefer_underlying",
    "_is_generic",
]
