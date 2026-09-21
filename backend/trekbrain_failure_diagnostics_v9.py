"""Failure transparency for TrekBrain v9.

Historically smart_planner_v5 tried several language variants and swallowed every
underlying HTTPException. If they all failed, users always received the same
"parcours cohérent" message, hiding whether the actual cause was ORS, missing
geodata, mileage, or lodging.

Important implementation detail: after the v7/v8/v9 installers run, ``v5._build``
may itself point back to ``v7._build``. Wrapping that public reference and then
assigning the wrapper to ``v7._BASE_BUILD`` creates an infinite recursion:

    v7._build -> v7._BASE_BUILD -> wrapped v5._build -> v7._build -> ...

This module therefore wraps only the *already captured lower-level base* stored
in ``v7._BASE_BUILD``. That preserves the original v5/v3 planning chain without
creating another edge back to v7.
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
    """Surface the real v3/ORS failure without changing planner call topology."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    current_v3_build = v3._build
    current_base_build = v7._BASE_BUILD

    def diagnostic_v3_build(data, legacy_main):
        try:
            return current_v3_build(data, legacy_main)
        except HTTPException as exc:
            _LAST_ERROR.set(exc)
            raise

    v3._build = diagnostic_v3_build

    def transparent_base_build(data, legacy_main, user_id: int):
        token = _LAST_ERROR.set(None)
        try:
            return current_base_build(data, legacy_main, user_id)
        except HTTPException as exc:
            chosen = _prefer_underlying(exc, _LAST_ERROR.get())
            if chosen is not exc:
                raise chosen
            raise
        finally:
            _LAST_ERROR.reset(token)

    # V9 executes geographic hypotheses through v7._BASE_BUILD. Patch exactly
    # that captured lower-level call. Do NOT assign v5._build here: in the live
    # installer chain v5._build can already be v7._build, which would create a
    # recursion cycle when v7._BASE_BUILD points at our wrapper.
    v7._BASE_BUILD = transparent_base_build


__all__ = [
    "install_failure_diagnostics",
    "_prefer_underlying",
    "_is_generic",
]
