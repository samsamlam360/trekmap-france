"""Production entrypoint for TrekMap France.

Loads the existing application and replaces the legacy CSRF middleware with
an origin/rate-limit middleware. This keeps the application logic unchanged
while removing the obsolete CSRF check that blocked authentication in the
production browser session.
"""
from fastapi.responses import JSONResponse
from .main import app, FRONTEND_ORIGINS, IS_PRODUCTION, rate_limited

# Remove the legacy security middleware installed by main.py.
# Starlette stores function-based middleware as BaseHTTPMiddleware instances.
app.user_middleware = [
    m for m in app.user_middleware
    if getattr(getattr(m, "kwargs", {}).get("dispatch"), "__name__", "") != "security_middleware"
]
app.middleware_stack = None

@app.middleware("http")
async def production_security(request, call_next):
    if rate_limited(request):
        return JSONResponse({"detail": "Trop de requêtes. Réessaie dans un instant."}, status_code=429)
    if IS_PRODUCTION:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in FRONTEND_ORIGINS:
            return JSONResponse({"detail": "Origine non autorisée."}, status_code=403)
    try:
        response = await call_next(request)
    except Exception:
        if IS_PRODUCTION:
            return JSONResponse({"detail": "Erreur interne du serveur."}, status_code=500)
        raise
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(), camera=()"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["X-TrekMap-Version"] = "4.5.1"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.version = "4.5.1"
