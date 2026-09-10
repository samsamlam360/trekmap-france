from fastapi import FastAPI, Header, HTTPException, Depends, UploadFile, File, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from .database import SessionLocal

import binascii
import hashlib
import json
import math
import os
import re
import secrets
from datetime import datetime, timedelta
from html import escape

import gpxpy
import requests
import tempfile

APP_VERSION = "4.5-secure"
ENVIRONMENT = os.getenv("TREKMAP_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()
IS_PRODUCTION = ENVIRONMENT in {"production", "prod"}
FRONTEND_ORIGINS = [x.strip().rstrip("/") for x in os.getenv(
    "FRONTEND_ORIGINS",
    "" if IS_PRODUCTION else "http://127.0.0.1:5500,http://localhost:5500"
).split(",") if x.strip()]
if IS_PRODUCTION and not FRONTEND_ORIGINS:
    raise RuntimeError("FRONTEND_ORIGINS doit être défini en production.")

ORS_API_KEY = os.getenv("ORS_API_KEY", "").strip()
ORS_URL = "https://api.heigit.org/openrouteservice/v2/directions/foot-walking/geojson"
def env_int(name, default, minimum=0, maximum=10_000_000_000):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} doit être un entier.")
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} doit être compris entre {minimum} et {maximum}.")
    return value

MAX_GPX_BYTES = env_int("MAX_GPX_BYTES", 25 * 1024 * 1024, 1_000_000, 100 * 1024 * 1024)
MAX_DRAW_POINTS = env_int("MAX_DRAW_POINTS", 50, 2, 100)
MAX_GPX_STORED_POINTS = env_int("MAX_GPX_STORED_POINTS", 50000, 100, 100000)
MAX_GPX_INPUT_POINTS = env_int("MAX_GPX_INPUT_POINTS", 300000, 1000, 2_000_000)
SESSION_DURATION_DAYS = env_int("SESSION_DURATION_DAYS", 30, 1, 365)
PASSWORD_ITERATIONS = 390000
SESSION_COOKIE = "__Host-trekmap_session" if IS_PRODUCTION else "trekmap_session"
CSRF_COOKIE = "trekmap_csrf"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    COOKIE_SAMESITE = "lax"

# Limiteur simple par adresse IP. Il protège surtout les installations mono-instance.
RATE_LIMIT_WINDOW = 60
RATE_LIMITS = {
    "/auth/login": 10,
    "/auth/register": 5,
    "/upload-gpx": 5,
    "/treks/draw-preview": 20,
    "/treks/draw": 10,
}
_rate_state = {}

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

app = FastAPI(
    title="TrekMap France API",
    version=APP_VERSION,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_origin_regex=None if IS_PRODUCTION else r"^https?://(?:localhost|127\\.0\\.0\\.1)(?::\\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

FRANCE_REGIONS = [
    "Auvergne-Rhône-Alpes", "Bourgogne-Franche-Comté", "Bretagne",
    "Centre-Val de Loire", "Corse", "Grand Est", "Hauts-de-France",
    "Île-de-France", "Normandie", "Nouvelle-Aquitaine", "Occitanie",
    "Pays de la Loire", "Provence-Alpes-Côte d'Azur", "Guadeloupe",
    "Martinique", "Guyane", "La Réunion", "Mayotte",
]
ALLOWED_DIFFICULTIES = {"easy", "medium", "hard", "extreme"}

SCHEMA_READY = False

# -----------------------------
# Pydantic payloads
# -----------------------------
class RegisterUser(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=200)

class LoginUser(BaseModel):
    login: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=200)

class TrekPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    region: str = Field(min_length=1, max_length=120)
    difficulty: str = Field(default="medium", max_length=20)
    description: str = Field(default="", max_length=10000)
    is_public: bool = True
    duration_days: float | None = Field(default=None, ge=0.25, le=365)

class DrawPayload(TrekPayload):
    coords: list[list[float]]

class DrawPreview(BaseModel):
    coords: list[list[float]]

class PlanPayload(BaseModel):
    notes: str = Field(default="", max_length=10000)
    checklist: list[dict] = Field(default_factory=list)

class CommentPayload(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

class PasswordPayload(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)

# -----------------------------
# Schema / DB
# -----------------------------
def ensure_schema(force=False):
    global SCHEMA_READY
    if SCHEMA_READY and not force:
        return
    db = SessionLocal()
    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS treks (
                id SERIAL PRIMARY KEY,
                name VARCHAR(160) NOT NULL,
                region VARCHAR(120) NOT NULL DEFAULT 'Non renseignée',
                difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
                distance DOUBLE PRECISION NOT NULL DEFAULT 0,
                elevation INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                geom geometry(LineString,4326),
                owner_id INTEGER,
                is_public BOOLEAN NOT NULL DEFAULT TRUE,
                view_count INTEGER NOT NULL DEFAULT 0,
                duration_minutes INTEGER,
                duration_days DOUBLE PRECISION,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS owner_id INTEGER"))
        db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT TRUE"))
        db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS view_count INTEGER NOT NULL DEFAULT 0"))
        db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS duration_minutes INTEGER"))
        db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS duration_days DOUBLE PRECISION"))
        db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"))
        # Normalise les anciennes géométries sans SRID. Les nouvelles écritures utilisent toujours EPSG:4326.
        db.execute(text("""
            UPDATE treks
            SET geom = ST_SetSRID(geom,4326)
            WHERE geom IS NOT NULL AND ST_SRID(geom)=0
        """))

        db.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(80) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id SERIAL PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_favorites (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                trek_id INTEGER NOT NULL REFERENCES treks(id) ON DELETE CASCADE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id, trek_id)
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_plans (
                trek_id INTEGER NOT NULL REFERENCES treks(id) ON DELETE CASCADE,
                owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                notes TEXT NOT NULL DEFAULT '',
                checklist JSONB NOT NULL DEFAULT '[]'::jsonb,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Migration robuste: les anciennes versions utilisaient parfois owner_id, parfois user_id.
        # On conserve les préparations et on donne à chaque utilisateur sa propre préparation.
        db.execute(text("ALTER TABLE trek_plans ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE"))
        db.execute(text("ALTER TABLE trek_plans ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"))
        db.execute(text("UPDATE trek_plans SET user_id=owner_id WHERE user_id IS NULL AND owner_id IS NOT NULL"))
        db.execute(text("""
            UPDATE trek_plans p SET owner_id=t.owner_id
            FROM treks t
            WHERE p.trek_id=t.id AND p.owner_id IS NULL AND t.owner_id IS NOT NULL
        """))
        db.execute(text("""
            UPDATE trek_plans p SET user_id=p.owner_id
            WHERE p.user_id IS NULL AND p.owner_id IS NOT NULL
        """))
        # Les lignes historiques sans utilisateur ne peuvent pas être attribuées de façon sûre.
        db.execute(text("DELETE FROM trek_plans WHERE user_id IS NULL"))
        # Une ancienne version pouvait créer plusieurs lignes pour un même couple trek/utilisateur.
        # On garde la plus récente avant de créer l'index unique.
        db.execute(text("""
            DELETE FROM trek_plans a
            USING trek_plans b
            WHERE a.trek_id=b.trek_id
              AND a.user_id=b.user_id
              AND a.ctid < b.ctid
        """))
        db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_trek_plans_trek_user ON trek_plans(trek_id,user_id)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_trek_plans_owner ON trek_plans(owner_id)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_trek_plans_user ON trek_plans(user_id)"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_comments (
                id SERIAL PRIMARY KEY,
                trek_id INTEGER NOT NULL REFERENCES treks(id) ON DELETE CASCADE,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_trek_comments_trek ON trek_comments(trek_id, created_at DESC)"))

        db.execute(text("""
            UPDATE treks
            SET duration_days = GREATEST(0.25, ROUND((COALESCE(distance,0)/20.0)*4)/4.0),
                duration_minutes = GREATEST(1, ROUND((GREATEST(0.25, ROUND((COALESCE(distance,0)/20.0)*4)/4.0))*1440))
            WHERE duration_days IS NULL AND distance IS NOT NULL
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_treks_public ON treks(is_public)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_treks_owner ON treks(owner_id)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_trek_favorites_trek ON trek_favorites(trek_id)"))
        db.execute(text("DELETE FROM user_sessions WHERE expires_at <= CURRENT_TIMESTAMP"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at)"))

        if ADMIN_USERNAME and ADMIN_EMAIL and ADMIN_PASSWORD:
            existing = db.execute(text("SELECT id FROM users WHERE LOWER(username)=LOWER(:u) OR LOWER(email)=LOWER(:e)"), {"u": ADMIN_USERNAME, "e": ADMIN_EMAIL}).first()
            if existing:
                db.execute(text("UPDATE users SET is_admin=TRUE WHERE id=:id"), {"id": existing.id})
            else:
                db.execute(text("INSERT INTO users(username,email,password_hash,is_admin) VALUES(:u,:e,:p,TRUE)"), {
                    "u": ADMIN_USERNAME, "e": ADMIN_EMAIL, "p": hash_password(ADMIN_PASSWORD)
                })
        db.commit()
        SCHEMA_READY = True
    except Exception:
        db.rollback()
        SCHEMA_READY = False
        raise
    finally:
        db.close()

@app.on_event("startup")
def startup():
    try:
        ensure_schema()
        print("[TrekMap] Base de données prête")
    except Exception as exc:
        print("[TrekMap] ATTENTION: base indisponible au démarrage:", repr(exc))

# -----------------------------
# Sécurité HTTP / sessions
# -----------------------------
def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"

def rate_limited(request: Request) -> bool:
    path = request.url.path
    limit = next((v for prefix, v in RATE_LIMITS.items() if path == prefix), None)
    if limit is None:
        return False
    now = datetime.now().timestamp()
    key = (client_key(request), path)
    hits = [t for t in _rate_state.get(key, []) if now - t < RATE_LIMIT_WINDOW]
    if len(hits) >= limit:
        _rate_state[key] = hits
        return True
    hits.append(now)
    _rate_state[key] = hits
    # Nettoyage léger pour éviter une croissance infinie du dictionnaire.
    if len(_rate_state) > 5000:
        cutoff = now - RATE_LIMIT_WINDOW
        for k in list(_rate_state):
            if not any(t >= cutoff for t in _rate_state[k]):
                _rate_state.pop(k, None)
    return False

def set_session_cookies(response: Response, token_value: str):
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        SESSION_COOKIE, token_value, max_age=SESSION_DURATION_DAYS * 86400,
        httponly=True, secure=IS_PRODUCTION, samesite=COOKIE_SAMESITE, path="/"
    )
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=SESSION_DURATION_DAYS * 86400,
        httponly=False, secure=IS_PRODUCTION, samesite=COOKIE_SAMESITE, path="/"
    )

def clear_session_cookies(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if rate_limited(request):
        return JSONResponse({"detail": "Trop de requêtes. Réessaie dans un instant."}, status_code=429)
    if IS_PRODUCTION:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in FRONTEND_ORIGINS:
            return JSONResponse({"detail": "Origine non autorisée."}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get(SESSION_COOKIE):
            csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
            csrf_header = request.headers.get("X-CSRF-Token", "")
            if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
                return JSONResponse({"detail": "Protection CSRF : requête refusée."}, status_code=403)
    try:
        response = await call_next(request)
    except Exception:
        # Les détails d'exception ne doivent pas fuiter au client en production.
        if IS_PRODUCTION:
            return JSONResponse({"detail": "Erreur interne du serveur."}, status_code=500)
        raise
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(), camera=()"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/auth/") else response.headers.get("Cache-Control", "no-cache")
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# -----------------------------
# Helpers
# -----------------------------
def db_or_503():
    try:
        ensure_schema()
        return SessionLocal()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Base de données indisponible. Vérifie DATABASE_URL et PostgreSQL/PostGIS.") from exc

def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())

def difficulty(value: str) -> str:
    value = normalize_text(value).lower()
    return value if value in ALLOWED_DIFFICULTIES else "medium"

def estimate_duration_days(distance_km):
    d = max(float(distance_km or 0), 0)
    return max(0.25, round((d / 20.0) * 4) / 4)

def duration_minutes(days):
    return max(1, round(float(days) * 1440)) if days is not None else None

def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${binascii.hexlify(salt).decode()}${binascii.hexlify(key).decode()}"

def verify_password(password, stored):
    try:
        algorithm, iterations, salt_hex, key_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = binascii.unhexlify(salt_hex)
        expected = binascii.unhexlify(key_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False

def validate_coords(coords):
    if not isinstance(coords, list) or len(coords) < 2:
        return "Il faut au moins 2 points."
    if len(coords) > MAX_DRAW_POINTS:
        return f"Un trek ne peut pas dépasser {MAX_DRAW_POINTS} points de passage."
    for p in coords:
        if not isinstance(p, list) or len(p) != 2:
            return "Coordonnées invalides."
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in p):
            return "Coordonnées invalides."
        if not (-90 <= p[0] <= 90 and -180 <= p[1] <= 180):
            return "Coordonnées GPS hors limites."
    return None

def distance_gps(coords):
    total, radius = 0.0, 6371.0
    for a, b in zip(coords, coords[1:]):
        lat1, lon1 = map(math.radians, a)
        lat2, lon2 = map(math.radians, b)
        dlat, dlon = lat2-lat1, lon2-lon1
        h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        total += radius * 2 * math.atan2(math.sqrt(h), math.sqrt(1-h))
    return round(total, 2)

def coords_to_geojson(coords):
    return {"type": "LineString", "coordinates": [[float(lon), float(lat)] for lat, lon in coords]}

def geometry_to_leaflet(geometry):
    if not geometry:
        return []
    typ = geometry.get("type")
    c = geometry.get("coordinates") or []
    if typ == "LineString":
        return [[float(p[1]), float(p[0])] for p in c if len(p) >= 2]
    if typ == "MultiLineString":
        return [[float(p[1]), float(p[0])] for line in c for p in line if len(p) >= 2]
    return []

def row_to_dict(row, favorite=False):
    try:
        geometry = json.loads(row.geojson) if row.geojson else None
    except Exception:
        geometry = None
    return {
        "id": int(row.id), "name": row.name, "region": row.region or "Non renseignée",
        "difficulty": row.difficulty or "medium", "distance": float(row.distance or 0),
        "elevation": int(row.elevation or 0), "description": row.description or "",
        "owner_id": row.owner_id, "owner_username": row.owner_username,
        "is_public": bool(row.is_public), "view_count": int(row.view_count or 0),
        "favorite_count": int(row.favorite_count or 0), "is_favorite": bool(favorite),
        "duration_days": float(row.duration_days) if row.duration_days is not None else None,
        "duration_minutes": int(row.duration_minutes) if row.duration_minutes is not None else None,
        "geometry": geometry, "coords": geometry_to_leaflet(geometry),
    }

TREK_SELECT = """
SELECT t.id,t.name,t.region,t.difficulty,t.distance,t.elevation,t.description,
       t.owner_id,t.is_public,t.view_count,t.duration_minutes,t.duration_days,
       u.username AS owner_username,
       (SELECT COUNT(*) FROM trek_favorites f WHERE f.trek_id=t.id) AS favorite_count,
       ST_AsGeoJSON(ST_Force2D(t.geom)) AS geojson
FROM treks t LEFT JOIN users u ON u.id=t.owner_id
"""

def can_manage(owner_id, user):
    return bool(user and (user["is_admin"] or owner_id is None or int(owner_id) == int(user["id"])))

def get_optional_user(request: Request, authorization: str | None = Header(default=None)):
    cookie_token = request.cookies.get(SESSION_COOKIE)
    bearer_token = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else ""
    token = cookie_token or bearer_token
    via_cookie = bool(cookie_token)
    if not token or len(token) > 200:
        return None
    db = db_or_503()
    try:
        row = db.execute(text("""
            SELECT u.id,u.username,u.email,u.is_admin,s.expires_at
            FROM user_sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token=:token
        """), {"token": token}).first()
        if not row:
            return None
        if row.expires_at <= datetime.now():
            db.execute(text("DELETE FROM user_sessions WHERE token=:t"), {"t": token})
            db.commit()
            return None
        return {"id": row.id,"username":row.username,"email":row.email,
                "is_admin":bool(row.is_admin),"token":token,"via_cookie":via_cookie}
    finally:
        db.close()

def current_user(user=Depends(get_optional_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return user

# -----------------------------
# Health / diagnostics
# -----------------------------
@app.get("/")
def root():
    frontend = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))
    if os.path.exists(frontend):
        return FileResponse(frontend, media_type="text/html")
    return {"name":"TrekMap France API","version":APP_VERSION,"status":"ok"}

@app.get("/health")
def health():
    db = None
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1")).scalar()
        postgis = db.execute(text("SELECT PostGIS_Version()")).scalar()
        counts = db.execute(text("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE geom IS NOT NULL) AS with_geometry FROM treks")).first()
        return {"status":"ok","database":"ok","postgis":postgis,"treks":int(counts.total),"treks_with_geometry":int(counts.with_geometry),"ors_configured":bool(ORS_API_KEY)}
    except Exception as exc:
        return {"status":"degraded","database":"error","ors_configured":bool(ORS_API_KEY)}
    finally:
        if db: db.close()

@app.get("/diagnostics")
def diagnostics(user=Depends(current_user)):
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Accès administrateur requis.")
    db = db_or_503()
    try:
        rows = db.execute(text("""
            SELECT COUNT(*) total,
                   COUNT(*) FILTER (WHERE geom IS NOT NULL) with_geometry,
                   COUNT(*) FILTER (WHERE geom IS NULL) without_geometry,
                   COUNT(*) FILTER (WHERE geom IS NOT NULL AND ST_IsValid(geom)) valid_geometry,
                   MIN(ST_GeometryType(geom)) geometry_type
            FROM treks
        """)).first()
        return {"treks":int(rows.total),"with_geometry":int(rows.with_geometry),"without_geometry":int(rows.without_geometry),"valid_geometry":int(rows.valid_geometry),"geometry_type":rows.geometry_type,"ors_configured":bool(ORS_API_KEY)}
    finally:
        db.close()

# -----------------------------
# Treks read endpoints
# -----------------------------
@app.get("/regions")
def regions():
    db=db_or_503()
    try:
        rows=db.execute(text("SELECT COALESCE(NULLIF(TRIM(region),''),'Non renseignée') region,COUNT(*) count FROM treks WHERE is_public=TRUE GROUP BY 1")).fetchall()
        counts={r.region:int(r.count) for r in rows}
        result=[{"name":r,"count":counts.get(r,0)} for r in FRANCE_REGIONS]
        result += [{"name":r,"count":counts[r]} for r in sorted(counts,key=str.lower) if r not in FRANCE_REGIONS]
        return result
    finally: db.close()

@app.get("/treks")
def list_treks(user=Depends(get_optional_user)):
    db=db_or_503()
    try:
        uid=user["id"] if user else -1
        rows=db.execute(text(TREK_SELECT+"""
            WHERE t.is_public=TRUE OR t.owner_id=:uid OR :admin=TRUE
            ORDER BY t.is_public DESC,favorite_count DESC,t.view_count DESC,t.name ASC
        """),{"uid":uid,"admin":bool(user and user["is_admin"])}).fetchall()
        fav={r.trek_id for r in db.execute(text("SELECT trek_id FROM trek_favorites WHERE user_id=:uid"),{"uid":uid}).fetchall()} if user else set()
        return [row_to_dict(r,r.id in fav) for r in rows]
    except SQLAlchemyError as exc:
        db.rollback(); raise HTTPException(status_code=500,detail="Erreur de lecture des treks.") from exc
    finally: db.close()

@app.get("/treks/geojson")
def treks_geojson(user=Depends(get_optional_user)):
    db=db_or_503()
    try:
        uid=user["id"] if user else -1
        rows=db.execute(text("""
            SELECT t.id,t.name,t.region,t.difficulty,t.distance,t.elevation,t.owner_id,t.is_public,
                   ST_AsGeoJSON(ST_Force2D(t.geom)) AS geometry
            FROM treks t
            WHERE t.is_public=TRUE OR t.owner_id=:uid OR :admin=TRUE
            ORDER BY t.id
        """),{"uid":uid,"admin":bool(user and user["is_admin"])}).fetchall()
        features=[]
        for r in rows:
            try: geom=json.loads(r.geometry) if r.geometry else None
            except Exception: geom=None
            if not geom: continue
            if geometry_to_leaflet(geom).__len__() < 2: continue
            features.append({"type":"Feature","id":int(r.id),"geometry":geom,"properties":{"id":int(r.id),"name":r.name,"region":r.region or "Non renseignée","difficulty":r.difficulty or "medium","distance":float(r.distance or 0),"elevation":int(r.elevation or 0),"owner_id":r.owner_id,"is_public":bool(r.is_public)}})
        return {"type":"FeatureCollection","features":features}
    finally: db.close()

@app.get("/treks/{trek_id}")
def get_trek(trek_id:int,user=Depends(get_optional_user)):
    db=db_or_503()
    try:
        uid=user["id"] if user else -1
        row=db.execute(text(TREK_SELECT+"WHERE t.id=:id AND (t.is_public=TRUE OR t.owner_id=:uid OR :admin=TRUE)"),{"id":trek_id,"uid":uid,"admin":bool(user and user["is_admin"])}).first()
        if not row: raise HTTPException(status_code=404,detail="Trek introuvable ou privé.")
        fav=bool(user and db.execute(text("SELECT 1 FROM trek_favorites WHERE user_id=:uid AND trek_id=:tid"),{"uid":uid,"tid":trek_id}).first())
        return row_to_dict(row,fav)
    finally: db.close()

# -----------------------------
# Routing / creation
# -----------------------------
def get_route(coords):
    fallback={"coords":coords,"distance":distance_gps(coords),"fallback":True,"warning":"OpenRouteService indisponible : le tracé direct est conservé."}
    if not ORS_API_KEY: return fallback
    try:
        payload={"coordinates":[[p[1],p[0]] for p in coords],"instructions":False}
        r=requests.post(ORS_URL,json=payload,headers={"Authorization":ORS_API_KEY,"Content-Type":"application/json"},timeout=25)
        if not r.ok: return {**fallback,"warning":f"OpenRouteService a répondu HTTP {r.status_code} : tracé direct utilisé."}
        data=r.json(); feature=(data.get("features") or [None])[0]
        if not feature: return fallback
        geometry=feature.get("geometry",{}).get("coordinates",[])
        summary=feature.get("properties",{}).get("summary",{})
        route=[[float(p[1]),float(p[0])] for p in geometry if len(p)>=2]
        if len(route)<2 or "distance" not in summary: return fallback
        return {"coords":route,"distance":round(float(summary["distance"])/1000,2),"fallback":False}
    except requests.RequestException as exc:
        return {**fallback,"warning":f"OpenRouteService inaccessible ({exc.__class__.__name__}) : tracé direct utilisé."}
    except Exception:
        return fallback

def elevation_gain(coords):
    # Le site reste fonctionnel même si le service d'altitude externe est indisponible.
    try:
        sample=coords if len(coords)<=100 else [coords[round(i*(len(coords)-1)/99)] for i in range(100)]
        r=requests.post("https://api.open-elevation.com/api/v1/lookup",json={"locations":[{"latitude":p[0],"longitude":p[1]} for p in sample]},timeout=12)
        if not r.ok: return 0
        prev=None; gain=0
        for x in r.json().get("results",[]):
            z=x.get("elevation")
            if z is None: continue
            if prev is not None and z-prev>2: gain += z-prev
            prev=z
        return round(gain)
    except Exception: return 0

@app.post("/treks/draw-preview")
def draw_preview(data:DrawPreview):
    error=validate_coords(data.coords)
    if error: raise HTTPException(status_code=400,detail=error)
    return get_route(data.coords)

@app.post("/treks/draw")
def draw_trek(data:DrawPayload,user=Depends(current_user)):
    error=validate_coords(data.coords)
    if error: raise HTTPException(status_code=400,detail=error)
    name,region=normalize_text(data.name),normalize_text(data.region)
    if not name or not region: raise HTTPException(status_code=400,detail="Le nom et la région sont obligatoires.")
    route=get_route(data.coords)
    coords=route["coords"]
    db=db_or_503()
    try:
        days=round(float(data.duration_days),2) if data.duration_days is not None else estimate_duration_days(route["distance"])
        result=db.execute(text("""
            INSERT INTO treks(name,region,difficulty,distance,elevation,description,geom,owner_id,is_public,duration_days,duration_minutes)
            VALUES(:name,:region,:difficulty,:distance,:elevation,:description,ST_SetSRID(ST_GeomFromGeoJSON(:geo),4326),:owner,:public,:days,:minutes)
            RETURNING id
        """),{"name":name[:160],"region":region[:120],"difficulty":difficulty(data.difficulty),"distance":route["distance"],"elevation":elevation_gain(coords),"description":normalize_text(data.description)[:10000],"geo":json.dumps(coords_to_geojson(coords)),"owner":user["id"],"public":data.is_public,"days":days,"minutes":duration_minutes(days)}).scalar_one()
        db.commit()
        return {"message":"Trek créé avec succès","id":int(result),"distance":route["distance"],"duration_days":days,"coords":coords,"fallback":route.get("fallback",False),"warning":route.get("warning")}
    except Exception as exc:
        db.rollback(); raise HTTPException(status_code=500,detail="Impossible de créer le trek.") from exc
    finally: db.close()

# -----------------------------
# GPX
# -----------------------------
def simplify_gpx_coords(coords, max_points=MAX_GPX_STORED_POINTS):
    """Réduit uniquement les traces GPX gigantesques, en conservant la forme générale."""
    if len(coords) <= max_points:
        return coords, False
    # RDP en coordonnées lon/lat. Pour une trace GPS, cette approximation est suffisante
    # pour réduire les points redondants sans imposer une limite artificielle de 50 points.
    pts=[(float(p[1]), float(p[0])) for p in coords]
    def sq_dist(p, a, b):
        x,y=p; x1,y1=a; x2,y2=b
        dx=x2-x1; dy=y2-y1
        if dx==0 and dy==0: return (x-x1)**2+(y-y1)**2
        t=((x-x1)*dx+(y-y1)*dy)/(dx*dx+dy*dy)
        t=max(0,min(1,t)); q=(x1+t*dx,y1+t*dy)
        return (x-q[0])**2+(y-q[1])**2
    def rdp(points, eps2):
        if len(points)<3: return points
        best=-1; idx=-1
        a,b=points[0],points[-1]
        for i in range(1,len(points)-1):
            d=sq_dist(points[i],a,b)
            if d>best: best=d; idx=i
        if best>eps2:
            left=rdp(points[:idx+1],eps2); right=rdp(points[idx:],eps2)
            return left[:-1]+right
        return [a,b]
    # On augmente progressivement la tolérance jusqu'à atteindre une taille raisonnable.
    eps_values=(1e-10,3e-10,1e-9,3e-9,1e-8,3e-8,1e-7,3e-7,1e-6)
    reduced=pts
    for eps in eps_values:
        reduced=rdp(pts,eps)
        if len(reduced)<=max_points:
            break
    if len(reduced)>max_points:
        step=(len(reduced)-1)/(max_points-1)
        reduced=[reduced[round(i*step)] for i in range(max_points)]
    result=[[lat,lon] for lon,lat in reduced]
    return result, True

# -----------------------------
# GPX
# -----------------------------
@app.post("/upload-gpx")
async def upload_gpx(file:UploadFile=File(...),user=Depends(current_user)):
    if not file.filename or not file.filename.lower().endswith(".gpx"):
        raise HTTPException(status_code=400,detail="Le fichier doit être au format GPX.")
    total=0
    tmp=tempfile.SpooledTemporaryFile(max_size=2*1024*1024, mode="w+b")
    try:
        while True:
            chunk=await file.read(1024*1024)
            if not chunk:
                break
            total += len(chunk)
            if total>MAX_GPX_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"GPX trop volumineux. La limite est de {MAX_GPX_BYTES // (1024*1024)} Mo."
                )
            tmp.write(chunk)
    finally:
        await file.close()
    try:
        tmp.seek(0)
        gpx=gpxpy.parse(tmp)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400,detail="GPX invalide ou illisible.") from exc
    finally:
        tmp.close()
    coords=[]
    for tr in gpx.tracks:
        for seg in tr.segments:
            for p in seg.points:
                try: coords.append([float(p.latitude),float(p.longitude)])
                except (TypeError,ValueError): continue
    # Certains appareils exportent un itinéraire plutôt qu'une trace. On le prend aussi en charge.
    if len(coords)<2:
        for route in gpx.routes:
            for p in route.points:
                try: coords.append([float(p.latitude),float(p.longitude)])
                except (TypeError,ValueError): continue
    if len(coords)<2: raise HTTPException(status_code=400,detail="Le GPX ne contient pas assez de points GPS.")
    if any(not all(math.isfinite(v) for v in p) or not (-90<=p[0]<=90 and -180<=p[1]<=180) for p in coords):
        raise HTTPException(status_code=400,detail="Le GPX contient des coordonnées GPS invalides.")
    original_points=len(coords)
    if original_points > MAX_GPX_INPUT_POINTS:
        raise HTTPException(
            status_code=413,
            detail=f"GPX refusé : trop de points GPS ({original_points:,}). Limite : {MAX_GPX_INPUT_POINTS:,}."
        )
    # Les statistiques sont calculées sur la trace complète. La simplification ne sert
    # qu'à alléger la géométrie stockée et à garder la carte fluide.
    dist=distance_gps(coords); elev=elevation_gain(coords)
    coords, simplified=simplify_gpx_coords(coords)
    db=db_or_503()
    try:
        days=estimate_duration_days(dist)
        name=normalize_text(file.filename.rsplit('.',1)[0])[:160] or "Trek GPX"
        tid=db.execute(text("""
            INSERT INTO treks(name,region,difficulty,distance,elevation,description,geom,owner_id,is_public,duration_days,duration_minutes)
            VALUES(:name,'Non renseignée','medium',:distance,:elevation,'',ST_SetSRID(ST_GeomFromGeoJSON(:geo),4326),:owner,FALSE,:days,:minutes) RETURNING id
        """),{"name":name,"distance":dist,"elevation":elev,"geo":json.dumps(coords_to_geojson(coords)),"owner":user["id"],"days":days,"minutes":duration_minutes(days)}).scalar_one()
        db.commit()
        message="GPX importé avec succès"
        if simplified: message += f". {original_points:,} points réduits à {len(coords):,} pour conserver une carte fluide"
        return {"message":message,"id":int(tid),"distance":dist,"elevation":elev,"duration_days":days,"points_original":original_points,"points_stored":len(coords),"simplified":simplified}
    except HTTPException: db.rollback(); raise
    except Exception as exc:
        db.rollback(); raise HTTPException(status_code=500,detail="Impossible d'importer le GPX.") from exc
    finally: db.close()

# -----------------------------
# Auth / favorites / plans
# -----------------------------
@app.post("/auth/register")
def register(data:RegisterUser, response: Response):
    username=normalize_text(data.username); email=normalize_text(data.email).lower()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}",username): raise HTTPException(status_code=400,detail="Nom d'utilisateur invalide.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email): raise HTTPException(status_code=400,detail="Adresse e-mail invalide.")
    db=db_or_503()
    try:
        if db.execute(text("SELECT 1 FROM users WHERE LOWER(username)=LOWER(:u) OR LOWER(email)=LOWER(:e)"),{"u":username,"e":email}).first(): raise HTTPException(status_code=409,detail="Ce compte existe déjà.")
        uid=db.execute(text("INSERT INTO users(username,email,password_hash) VALUES(:u,:e,:p) RETURNING id"),{"u":username,"e":email,"p":hash_password(data.password)}).scalar_one()
        token=secrets.token_urlsafe(48); db.execute(text("INSERT INTO user_sessions(token,user_id,expires_at) VALUES(:t,:u,:x)"),{"t":token,"u":uid,"x":datetime.now()+timedelta(days=SESSION_DURATION_DAYS)})
        db.commit()
        set_session_cookies(response, token)
        payload={"user":{"id":int(uid),"username":username,"email":email,"is_admin":False}}
        if not IS_PRODUCTION:
            payload["token"]=token
        return payload
    except HTTPException: db.rollback(); raise
    finally: db.close()

@app.post("/auth/login")
def login(data:LoginUser, response: Response):
    db=db_or_503()
    try:
        row=db.execute(text("SELECT id,username,email,password_hash,is_admin FROM users WHERE LOWER(username)=LOWER(:l) OR LOWER(email)=LOWER(:l)"),{"l":normalize_text(data.login)}).first()
        if not row or not verify_password(data.password,row.password_hash): raise HTTPException(status_code=401,detail="Identifiant ou mot de passe incorrect.")
        token=secrets.token_urlsafe(48); db.execute(text("INSERT INTO user_sessions(token,user_id,expires_at) VALUES(:t,:u,:x)"),{"t":token,"u":row.id,"x":datetime.now()+timedelta(days=SESSION_DURATION_DAYS)})
        db.commit()
        set_session_cookies(response, token)
        payload={"user":{"id":row.id,"username":row.username,"email":row.email,"is_admin":bool(row.is_admin)}}
        if not IS_PRODUCTION:
            payload["token"]=token
        return payload
    finally: db.close()

@app.get("/auth/me")
def me(user=Depends(current_user)): return {"user":{k:user[k] for k in ("id","username","email","is_admin")}}

@app.post("/auth/logout")
def logout(response: Response, user=Depends(current_user)):
    db=db_or_503()
    try:
        db.execute(text("DELETE FROM user_sessions WHERE token=:t"),{"t":user["token"]})
        db.commit()
        clear_session_cookies(response)
        return {"message":"Déconnecté"}
    finally: db.close()

@app.get("/auth/profile")
def profile(user=Depends(current_user)):
    db=db_or_503()
    try:
        r=db.execute(text("SELECT COUNT(*) total,COUNT(*) FILTER(WHERE is_public) public_count,COUNT(*) FILTER(WHERE NOT is_public) private_count,COALESCE(SUM(view_count),0) views FROM treks WHERE owner_id=:u"),{"u":user["id"]}).first()
        f=db.execute(text("SELECT COUNT(*) FROM trek_favorites WHERE user_id=:u"),{"u":user["id"]}).scalar()
        return {"user":{k:user[k] for k in ("id","username","email","is_admin")},"stats":{"total":int(r.total),"public":int(r.public_count),"private":int(r.private_count),"favorites":int(f),"views":int(r.views)}}
    finally: db.close()

@app.put("/auth/password")
def password_change(data:PasswordPayload,response:Response,user=Depends(current_user)):
    db=db_or_503()
    try:
        row=db.execute(text("SELECT password_hash FROM users WHERE id=:u"),{"u":user["id"]}).first()
        if not row or not verify_password(data.old_password,row.password_hash):
            raise HTTPException(status_code=401,detail="Ancien mot de passe incorrect.")
        db.execute(text("UPDATE users SET password_hash=:p WHERE id=:u"),{"p":hash_password(data.new_password),"u":user["id"]})
        # Toutes les sessions existantes sont révoquées après un changement de mot de passe.
        db.execute(text("DELETE FROM user_sessions WHERE user_id=:u"),{"u":user["id"]})
        token=secrets.token_urlsafe(48)
        db.execute(text("INSERT INTO user_sessions(token,user_id,expires_at) VALUES(:t,:u,:x)"),
                   {"t":token,"u":user["id"],"x":datetime.now()+timedelta(days=SESSION_DURATION_DAYS)})
        db.commit()
        set_session_cookies(response, token)
        payload={"message":"Mot de passe modifié"}
        if not IS_PRODUCTION:
            payload["token"]=token
        return payload
    finally: db.close()

@app.post("/treks/{trek_id}/favorite")
def favorite_add(trek_id:int,user=Depends(current_user)):
    db=db_or_503()
    try:
        if not db.execute(text("SELECT id FROM treks WHERE id=:id AND (is_public OR owner_id=:u OR :admin)"),{"id":trek_id,"u":user["id"],"admin":user["is_admin"]}).first(): raise HTTPException(status_code=404,detail="Trek introuvable.")
        db.execute(text("INSERT INTO trek_favorites(user_id,trek_id) VALUES(:u,:t) ON CONFLICT DO NOTHING"),{"u":user["id"],"t":trek_id});db.commit();return {"favorite":True}
    finally: db.close()

@app.delete("/treks/{trek_id}/favorite")
def favorite_remove(trek_id:int,user=Depends(current_user)):
    db=db_or_503()
    try: db.execute(text("DELETE FROM trek_favorites WHERE user_id=:u AND trek_id=:t"),{"u":user["id"],"t":trek_id});db.commit();return {"favorite":False}
    finally: db.close()

@app.post("/treks/{trek_id}/view")
def view(trek_id:int,user=Depends(get_optional_user)):
    db=db_or_503()
    try:
        uid=user["id"] if user else -1
        if not db.execute(text("SELECT id FROM treks WHERE id=:id AND (is_public OR owner_id=:u OR :admin)"),{"id":trek_id,"u":uid,"admin":bool(user and user["is_admin"])}).first(): raise HTTPException(status_code=404,detail="Trek introuvable.")
        db.execute(text("UPDATE treks SET view_count=COALESCE(view_count,0)+1 WHERE id=:id"),{"id":trek_id});db.commit();return {"message":"Vue enregistrée"}
    finally: db.close()

@app.get("/favorites")
def favorites(user=Depends(current_user)):
    db=db_or_503()
    try: return [r.trek_id for r in db.execute(text("SELECT trek_id FROM trek_favorites WHERE user_id=:u ORDER BY created_at DESC"),{"u":user["id"]}).fetchall()]
    finally: db.close()

# -----------------------------
# Update / delete / export / plans
# -----------------------------
@app.put("/treks/{trek_id}")
def update_trek(trek_id:int,data:TrekPayload,user=Depends(current_user)):
    db=db_or_503()
    try:
        row=db.execute(text("SELECT owner_id,distance FROM treks WHERE id=:id"),{"id":trek_id}).first()
        if not row: raise HTTPException(status_code=404,detail="Trek introuvable.")
        if not can_manage(row.owner_id,user): raise HTTPException(status_code=403,detail="Tu ne peux pas modifier ce trek.")
        days=round(float(data.duration_days),2) if data.duration_days is not None else estimate_duration_days(row.distance)
        db.execute(text("UPDATE treks SET name=:n,region=:r,difficulty=:d,description=:x,is_public=:p,duration_days=:days,duration_minutes=:mins WHERE id=:id"),{"n":normalize_text(data.name)[:160],"r":normalize_text(data.region)[:120],"d":difficulty(data.difficulty),"x":normalize_text(data.description)[:10000],"p":data.is_public,"days":days,"mins":duration_minutes(days),"id":trek_id});db.commit();return {"message":"Trek modifié","duration_days":days}
    except HTTPException: db.rollback();raise
    finally: db.close()

@app.delete("/treks/{trek_id}")
def delete_trek(trek_id:int,user=Depends(current_user)):
    db=db_or_503()
    try:
        row=db.execute(text("SELECT owner_id FROM treks WHERE id=:id"),{"id":trek_id}).first()
        if not row: raise HTTPException(status_code=404,detail="Trek introuvable.")
        if not can_manage(row.owner_id,user): raise HTTPException(status_code=403,detail="Tu ne peux pas supprimer ce trek.")
        # Suppression explicite des dépendances pour rester compatible avec les anciennes bases.
        db.execute(text("DELETE FROM trek_comments WHERE trek_id=:id"),{"id":trek_id})
        db.execute(text("DELETE FROM trek_plans WHERE trek_id=:id"),{"id":trek_id})
        db.execute(text("DELETE FROM trek_favorites WHERE trek_id=:id"),{"id":trek_id})
        db.execute(text("DELETE FROM treks WHERE id=:id"),{"id":trek_id})
        db.commit()
        return {"message":"Trek supprimé"}
    except HTTPException: db.rollback();raise
    finally: db.close()

@app.get("/treks/{trek_id}/export-gpx")
def export_gpx(trek_id:int,user=Depends(get_optional_user)):
    db=db_or_503()
    try:
        row=db.execute(text("SELECT name,owner_id,is_public,ST_AsGeoJSON(ST_Force2D(geom)) geojson FROM treks WHERE id=:id"),{"id":trek_id}).first()
        if not row: raise HTTPException(status_code=404,detail="Trek introuvable.")
        if not row.is_public and not (user and (user["is_admin"] or user["id"]==row.owner_id)): raise HTTPException(status_code=403,detail="Ce trek est privé.")
        geom=json.loads(row.geojson or "{}");coords=geometry_to_leaflet(geom)
        pts="\n".join(f'<trkpt lat="{p[0]:.8f}" lon="{p[1]:.8f}" />' for p in coords)
        safe=escape(row.name or "trek")
        gpx=f'<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="TrekMap France" xmlns="http://www.topografix.com/GPX/1/1"><metadata><name>{safe}</name></metadata><trk><name>{safe}</name><trkseg>{pts}</trkseg></trk></gpx>'
        return {"name":row.name,"gpx":gpx}
    finally: db.close()


@app.get("/treks/{trek_id}/comments")
def get_comments(trek_id:int):
    db=db_or_503()
    try:
        r=db.execute(text("SELECT id,name,region,is_public,owner_id FROM treks WHERE id=:id"),{"id":trek_id}).first()
        if not r or not r.is_public:
            raise HTTPException(status_code=404, detail="Trek introuvable ou privé.")
        rows=db.execute(text("""
            SELECT c.id,c.content,c.created_at,c.updated_at,c.owner_id,u.username
            FROM trek_comments c JOIN users u ON u.id=c.owner_id
            WHERE c.trek_id=:t ORDER BY c.created_at DESC LIMIT 100
        """),{"t":trek_id}).mappings().all()
        return {"comments":[dict(x) for x in rows]}
    finally: db.close()

@app.post("/treks/{trek_id}/comments")
def add_comment(trek_id:int,data:CommentPayload,user=Depends(current_user)):
    db=db_or_503()
    try:
        r=db.execute(text("SELECT is_public,owner_id FROM treks WHERE id=:id"),{"id":trek_id}).first()
        if not r or (not r.is_public and not can_manage(r.owner_id,user)):
            raise HTTPException(status_code=404, detail="Trek introuvable ou privé.")
        content=data.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="Le commentaire est vide.")
        row=db.execute(text("""
            INSERT INTO trek_comments(trek_id,owner_id,content) VALUES(:t,:u,:c)
            RETURNING id,content,created_at,updated_at,owner_id
        """),{"t":trek_id,"u":user["id"],"c":content}).mappings().one()
        db.commit()
        return dict(row)
    except HTTPException: db.rollback(); raise
    except SQLAlchemyError as e:
        db.rollback(); raise HTTPException(status_code=500,detail="Impossible d'enregistrer le commentaire.")
    finally: db.close()

@app.delete("/treks/{trek_id}/comments/{comment_id}")
def delete_comment(trek_id:int,comment_id:int,user=Depends(current_user)):
    db=db_or_503()
    try:
        r=db.execute(text("SELECT owner_id FROM trek_comments WHERE id=:c AND trek_id=:t"),{"c":comment_id,"t":trek_id}).first()
        if not r: raise HTTPException(status_code=404,detail="Commentaire introuvable.")
        if not user.get("is_admin") and int(r.owner_id)!=int(user["id"]):
            raise HTTPException(status_code=403,detail="Tu ne peux supprimer que ton commentaire.")
        db.execute(text("DELETE FROM trek_comments WHERE id=:c AND trek_id=:t"),{"c":comment_id,"t":trek_id})
        db.commit()
        return {"ok":True}
    except HTTPException: db.rollback(); raise
    finally: db.close()

@app.get("/treks/{trek_id}/plan")
def get_plan(trek_id:int,user=Depends(current_user)):
    db=db_or_503()
    try:
        r=db.execute(text("SELECT owner_id,is_public FROM treks WHERE id=:id"),{"id":trek_id}).first()
        if not r or (not r.is_public and not can_manage(r.owner_id,user)):
            raise HTTPException(status_code=404,detail="Trek introuvable ou privé.")
        p=db.execute(text("SELECT notes,checklist FROM trek_plans WHERE trek_id=:t AND user_id=:u"),{"t":trek_id,"u":user["id"]}).first()
        return {"notes":p.notes if p else "","checklist":p.checklist if p and p.checklist else []}
    finally: db.close()

@app.put("/treks/{trek_id}/plan")
def save_plan(trek_id:int,data:PlanPayload,user=Depends(current_user)):
    db=db_or_503()
    try:
        r=db.execute(text("SELECT owner_id,is_public FROM treks WHERE id=:id"),{"id":trek_id}).first()
        if not r or (not r.is_public and not can_manage(r.owner_id,user)):
            raise HTTPException(status_code=404,detail="Trek introuvable ou privé.")
        checklist=[{"text":str(x.get("text", ""))[:200],"done":bool(x.get("done",False))} for x in data.checklist[:100] if isinstance(x,dict) and str(x.get("text","")).strip()]
        payload=json.dumps(checklist,ensure_ascii=False)
        db.execute(text("""
            INSERT INTO trek_plans(trek_id,owner_id,user_id,notes,checklist) VALUES(:t,:u,:u,:n,CAST(:c AS jsonb))
            ON CONFLICT (trek_id,user_id) DO UPDATE
            SET notes=EXCLUDED.notes,checklist=EXCLUDED.checklist,updated_at=CURRENT_TIMESTAMP
        """),{"t":trek_id,"u":user["id"],"n":data.notes[:10000],"c":payload})
        db.commit();return {"message":"Plan enregistré"}
    except HTTPException: db.rollback(); raise
    finally: db.close()

@app.put("/admin/recalculate-durations")
def recalc(user=Depends(current_user)):
    if not user["is_admin"]: raise HTTPException(status_code=403,detail="Accès administrateur requis.")
    db=db_or_503()
    try:
        rows=db.execute(text("SELECT id,ST_Length(ST_Transform(geom,2154))/1000 distance FROM treks WHERE geom IS NOT NULL")).fetchall()
        for r in rows:
            d=round(float(r.distance),2); days=estimate_duration_days(d)
            db.execute(text("UPDATE treks SET distance=:d,duration_days=:days,duration_minutes=:m WHERE id=:id"),{"d":d,"days":days,"m":duration_minutes(days),"id":r.id})
        db.commit();return {"message":"Distances et durées recalculées","treks_modifies":len(rows),"base":"20 km/jour"}
    finally: db.close()
