"""Regression tests for user-visible TrekBrain v9 error codes."""
from pathlib import Path
from types import SimpleNamespace
import sys

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.trekbrain_error_codes_v9 import classify_failure
from backend.trekbrain_request_overlay_v9 import _failure_detail


# Exact production-style failure from the Belle-Île screenshot: API answers 422
# because the plan is rejected, while the underlying provider actually returned
# HTTP 500. The diagnostic must preserve both numbers and identify Directions.
d = classify_failure(
    "OpenRouteService indisponible temporairement (HTTP 500).",
    api_status=422,
    preview=None,
)
assert d["code"] == "TB-ORS-DIR-500"
assert d["stage"] == "routage pédestre"
assert d["service"] == "OpenRouteService Directions"
assert d["api_status"] == 422
assert d["provider_http_status"] == 500
assert d["retryable"] is True
assert d["preview_available"] is False
assert len(d["id"]) == 10

matrix = classify_failure("OpenRouteService Matrix HTTP 500.", api_status=422)
assert matrix["code"] == "TB-ORS-MATRIX-500"
assert "nuitées" in matrix["stage"]

camp = classify_failure(
    "La boucle pédestre existe, mais je n'ai pas trouvé assez de campings.",
    api_status=422,
)
assert camp["code"] == "TB-PLAN-CAMPING"

safety = classify_failure(
    "Le tracé pédestre n'est pas suffisamment validé.",
    api_status=422,
)
assert safety["code"] == "TB-SAFETY-ROUTE"

# Even without a failed preview the public overlay must now return a structured
# detail object. This is the case that previously showed only a bare HTTP 500.
effective = SimpleNamespace(
    region="Belle-Île-en-Mer",
    days=5,
    daily_km=18.0,
    difficulty="medium",
    route_type="Boucle",
    require_transit=True,
    require_water=True,
    require_accommodation=True,
    require_food=True,
)
exc = HTTPException(status_code=422, detail="OpenRouteService indisponible temporairement (HTTP 500).")
payload = _failure_detail(
    exc,
    effective,
    {
        "effective_region": "Belle-Île-en-Mer",
        "effective_route_type": "Boucle",
        "preferred_trail": "GR 340",
    },
    preview=None,
)
assert payload["message"].startswith("OpenRouteService")
assert payload["diagnostic"]["code"] == "TB-ORS-DIR-500"
assert payload["effective_request"]["region"] == "Belle-Île-en-Mer"
assert payload["effective_request"]["route_type"] == "Boucle"
assert payload["request_resolution"]["preferred_trail"] == "GR 340"
assert "failed_preview" not in payload

# With a preview, the same diagnostic must explicitly say that an inspectable
# candidate exists so the failure screen can explain why the button is enabled.
preview = {"coords": [[47.3, -3.2], [47.4, -3.1]], "candidate_only": True}
payload2 = _failure_detail(exc, effective, {}, preview=preview)
assert payload2["diagnostic"]["preview_available"] is True
assert payload2["failed_preview"] is preview

print("TrekBrain structured error codes: OK")
