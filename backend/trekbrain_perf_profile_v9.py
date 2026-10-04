"""Request-local latency profiling for TrekBrain v9.

This module is deliberately observational: it records where interactive planning
spends time without changing route selection, quality scoring or fallbacks.
Profiles are attached to v9 planner diagnostics and emitted as one compact JSON
line so production benchmarks can compare cold and warm passes.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
import json
import os
import threading
import time
from typing import Any

_CURRENT: ContextVar[dict[str, Any] | None] = ContextVar(
    "trekbrain_v9_perf_profile", default=None
)
_MAX_EVENTS = 96


def enabled() -> bool:
    return os.getenv("TREKBRAIN_PROFILE", "1").strip().casefold() not in {
        "0", "false", "off", "no"
    }


def begin(meta: dict[str, Any] | None = None) -> Token:
    if not enabled():
        return _CURRENT.set(None)
    profile: dict[str, Any] = {
        "started": time.perf_counter(),
        "meta": dict(meta or {}),
        "events": [],
        "totals": {},
        "counts": {},
        "maxima": {},
        "sequences": {},
        "cache_hits": {},
        "_lock": threading.Lock(),
    }
    return _CURRENT.set(profile)


def current() -> dict[str, Any] | None:
    return _CURRENT.get()


def next_sequence(name: str, *, profile: dict[str, Any] | None = None) -> int:
    target = profile if profile is not None else _CURRENT.get()
    if target is None:
        return 1
    lock = target.get("_lock")
    if lock is None:
        return 1
    with lock:
        value = int(target["sequences"].get(name, 0)) + 1
        target["sequences"][name] = value
        return value


def record(
    name: str,
    elapsed_ms: float,
    *,
    profile: dict[str, Any] | None = None,
    cache_hit: bool = False,
    **details: Any,
) -> None:
    target = profile if profile is not None else _CURRENT.get()
    if target is None:
        return
    try:
        elapsed = max(0.0, round(float(elapsed_ms), 2))
    except (TypeError, ValueError):
        elapsed = 0.0

    clean_details: dict[str, Any] = {}
    for key, value in details.items():
        if value is None:
            continue
        if isinstance(value, (bool, int, float)):
            clean_details[str(key)] = value
        else:
            clean_details[str(key)] = str(value)[:120]

    event = {"name": str(name), "ms": elapsed}
    event.update(clean_details)

    lock = target.get("_lock")
    if lock is None:
        return
    with lock:
        counts = target["counts"]
        totals = target["totals"]
        maxima = target["maxima"]
        counts[name] = int(counts.get(name, 0)) + 1
        totals[name] = round(float(totals.get(name, 0.0)) + elapsed, 2)
        maxima[name] = max(float(maxima.get(name, 0.0)), elapsed)
        if cache_hit:
            hits = target["cache_hits"]
            hits[name] = int(hits.get(name, 0)) + 1
        if len(target["events"]) < _MAX_EVENTS:
            target["events"].append(event)


def mark(name: str, *, cache_hit: bool = False, **details: Any) -> None:
    record(name, 0.0, cache_hit=cache_hit, **details)


def call(name: str, func, *args, profile: dict[str, Any] | None = None, **kwargs):
    started = time.perf_counter()
    outcome = "ok"
    try:
        return func(*args, **kwargs)
    except Exception:
        outcome = "error"
        raise
    finally:
        record(
            name,
            (time.perf_counter() - started) * 1000,
            profile=profile,
            outcome=outcome,
        )


def _summary(profile: dict[str, Any]) -> dict[str, Any]:
    total_ms = round((time.perf_counter() - float(profile["started"])) * 1000)
    providers = {}
    for name in sorted(profile["counts"]):
        providers[name] = {
            "count": int(profile["counts"].get(name, 0)),
            "total_ms": round(float(profile["totals"].get(name, 0.0))),
            "max_ms": round(float(profile["maxima"].get(name, 0.0))),
            "cache_hits": int(profile["cache_hits"].get(name, 0)),
        }
    slowest = sorted(
        list(profile["events"]),
        key=lambda row: float(row.get("ms") or 0),
        reverse=True,
    )[:12]
    return {
        "version": 1,
        "total_ms": total_ms,
        "request": dict(profile.get("meta") or {}),
        "providers": providers,
        "slowest": slowest,
    }


def finish(
    token: Token,
    result: dict[str, Any] | None = None,
    *,
    error: BaseException | None = None,
) -> dict[str, Any] | None:
    profile = _CURRENT.get()
    if profile is None:
        _CURRENT.reset(token)
        return None
    if error is not None:
        record(
            "request.error",
            0.0,
            error_type=error.__class__.__name__,
        )
    summary = _summary(profile)
    if isinstance(result, dict):
        planner = result.setdefault("planner", {})
        if isinstance(planner, dict):
            planner["performance_profile"] = summary
        performance = result.setdefault("agent", {}).setdefault("performance", {})
        if isinstance(performance, dict):
            performance["profiled_ms"] = summary["total_ms"]
            performance["provider_profile"] = summary["providers"]
    print(
        "[TrekBrain v9][profile] "
        + json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )
    _CURRENT.reset(token)
    return summary


__all__ = [
    "begin",
    "call",
    "current",
    "enabled",
    "finish",
    "mark",
    "next_sequence",
    "record",
]
