"""Stable-release metadata for TrekBrain v9.

This module is deliberately observational. It does not alter route generation.
It only enriches /ai/status with the exact backend build running in production so
screenshots and diagnostics can be tied to a Git commit instead of guesswork.
"""
from __future__ import annotations

import os
from typing import Any

from .trekbrain_pipeline_core_v9 import PIPELINE_VERSION
from .trekbrain_stability_contract_v9 import REFERENCE_PROMPTS

_RELEASE = "v9-stable"
_INSTALLED = False


def release_metadata() -> dict[str, Any]:
    commit = (
        os.getenv("RENDER_GIT_COMMIT", "").strip()
        or os.getenv("GITHUB_SHA", "").strip()
        or os.getenv("SOURCE_VERSION", "").strip()
        or "unknown"
    )
    channel = os.getenv("TREKBRAIN_RELEASE_CHANNEL", _RELEASE).strip() or _RELEASE
    return {
        "channel": channel,
        "stable": channel == _RELEASE,
        "pipeline_version": PIPELINE_VERSION,
        "build_commit": commit,
        "build_short": commit[:10] if commit != "unknown" else "unknown",
        "golden_prompt_count": len(REFERENCE_PROMPTS),
        "stability_gate": "required",
    }


def install_release_status(app) -> None:
    """Replace only /ai/status, preserving the original status implementation."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    matches = [
        route for route in app.router.routes
        if getattr(route, "path", None) == "/ai/status"
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one GET /ai/status route, found {len(matches)}")
    original = matches[0].endpoint
    app.router.routes = [route for route in app.router.routes if getattr(route, "path", None) != "/ai/status"]

    @app.get("/ai/status")
    def stable_status():
        base = original()
        payload = dict(base) if isinstance(base, dict) else {"configured": True}
        meta = release_metadata()
        payload["release"] = meta
        payload["release_channel"] = meta["channel"]
        payload["pipeline_version"] = meta["pipeline_version"]
        payload["build_commit"] = meta["build_commit"]
        payload["build_short"] = meta["build_short"]
        payload["stability_gate"] = meta["stability_gate"]
        payload["golden_prompt_count"] = meta["golden_prompt_count"]
        return payload


__all__ = ["install_release_status", "release_metadata"]
