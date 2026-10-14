"""Optional TrekMap profile v2: private hiking hub, journeys and collections.

All tables are additive and scoped to the authenticated account. Schema
initialization is lazy and isolated from the critical login/route pipeline.
"""
import json
from datetime import date
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from . import main as core

router = APIRouter(prefix="/profile", tags=["profile-v2"])
_schema_ready = False

_AVATARS = {"mountain", "compass", "tent", "forest", "hiker"}
_STATES = {"planned", "preparing", "ready", "completed"}
_DIFFICULTIES = {"easy", "medium", "hard"}
_LODGINGS = {"any", "camping", "refuge", "hotel"}
_ROUTES = {"Boucle", "Traversée", "Itinérance", "Aller-retour"}
_PREFERENCE_KEYS = {"daily_km", "difficulty", "lodging", "route_type", "transit", "water", "food", "sleep"}


class SettingsPayload(BaseModel):
    bio: str = Field(default="", max_length=280)
    avatar: str = Field(default="mountain", max_length=20)
    public_profile: bool = False
    share_completed: bool = False
    preferences: dict = Field(default_factory=dict)


class JourneyPayload(BaseModel):
    status: str = Field(default="planned", max_length=20)
    notes: str = Field(default="", max_length=2000)
    completed_on: date | None = None
    actual_distance_km: float | None = Field(default=None, ge=0, le=20000)
    actual_ascent_m: int | None = Field(default=None, ge=0, le=150000)
    rating: int | None = Field(default=None, ge=1, le=5)
    photo_urls: list[str] = Field(default_factory=list, max_length=5)


class CollectionPayload(BaseModel):
    name: str = Field(min_length=1, max_length=70)


def _schema(db):
    global _schema_ready
    if _schema_ready:
        return
    # Deliberately do not modify existing users/treks/favorites/trek_plans.
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_user_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                bio VARCHAR(280) NOT NULL DEFAULT '',
                avatar VARCHAR(20) NOT NULL DEFAULT 'mountain',
                public_profile BOOLEAN NOT NULL DEFAULT FALSE,
                share_completed BOOLEAN NOT NULL DEFAULT FALSE,
                preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_user_journeys (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                trek_id INTEGER NOT NULL REFERENCES treks(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'planned',
                notes VARCHAR(2000) NOT NULL DEFAULT '',
                completed_on DATE,
                actual_distance_km DOUBLE PRECISION,
                actual_ascent_m INTEGER,
                rating SMALLINT,
                photo_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id,trek_id),
                CONSTRAINT trek_user_journeys_status_chk CHECK (status IN ('planned','preparing','ready','completed'))
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_user_collections (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(70) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_user_collection_items (
                collection_id INTEGER NOT NULL REFERENCES trek_user_collections(id) ON DELETE CASCADE,
                trek_id INTEGER NOT NULL REFERENCES treks(id) ON DELETE CASCADE,
                PRIMARY KEY(collection_id,trek_id)
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_trek_user_collections_owner ON trek_user_collections(user_id)"))
        db.commit()
        _schema_ready = True
    except Exception:
        db.rollback()
        raise


def _db():
    db = core.db_or_503()
    try:
        _schema(db)
        return db
    except Exception as exc:
        db.close()
        raise HTTPException(status_code=503, detail="Fonctionnalités du profil temporairement indisponibles.") from exc


def _prefs(raw):
    if not isinstance(raw, dict):
        raise HTTPException(422, "Préférences invalides.")
    if len(json.dumps(raw)) > 2000:
        raise HTTPException(422, "Préférences trop volumineuses.")
    p = {k: v for k, v in raw.items() if k in _PREFERENCE_KEYS}
    if "daily_km" in p:
        try:
            p["daily_km"] = float(p["daily_km"])
        except (TypeError, ValueError):
            raise HTTPException(422, "Distance quotidienne invalide.")
        if not 3 <= p["daily_km"] <= 40:
            raise HTTPException(422, "Distance quotidienne hors limites.")
    for k, values in [("difficulty", _DIFFICULTIES), ("lodging", _LODGINGS), ("route_type", _ROUTES)]:
        if k in p and (not isinstance(p[k], str) or p[k] not in values):
            raise HTTPException(422, "Préférence invalide : " + k)
    for k in ("transit", "water", "food", "sleep"):
        if k in p and type(p[k]) is not bool:
            raise HTTPException(422, "Préférence booléenne attendue : " + k)
    return p


def _allowed(db, uid, tid):
    row = db.execute(text("SELECT id,name,region,is_public,owner_id FROM treks WHERE id=:id AND (is_public OR owner_id=:uid)"),
                     {"id": tid, "uid": uid}).mappings().first()
    if not row:
        raise HTTPException(404, "Trek inaccessible.")
    return row


def _photo_url(value):
    if not isinstance(value, str) or len(value) > 400:
        raise HTTPException(422, "Lien de photo invalide.")
    try:
        u = urlsplit(value)
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None, 443):
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "Les photos doivent avoir une URL HTTPS publique.")
    return value


def _settings(db, uid):
    r = db.execute(text("SELECT bio,avatar,public_profile,share_completed,preferences FROM trek_user_profiles WHERE user_id=:u"),
                   {"u": uid}).mappings().first()
    return dict(r) if r else {"bio": "", "avatar": "mountain", "public_profile": False,
                             "share_completed": False, "preferences": {}}


def _journeys(db, uid):
    rows = db.execute(text("""
        SELECT j.trek_id,j.status,j.notes,j.completed_on,j.actual_distance_km,j.actual_ascent_m,
               j.rating,j.photo_urls,j.updated_at,t.name,t.region,t.distance,t.elevation,t.is_public
        FROM trek_user_journeys j JOIN treks t ON t.id=j.trek_id
        WHERE j.user_id=:u AND (t.is_public OR t.owner_id=:u)
        ORDER BY j.updated_at DESC LIMIT 250
    """), {"u": uid}).mappings().all()
    result = []
    for row in rows:
        a = dict(row)
        a["completed_on"] = row["completed_on"].isoformat() if row["completed_on"] else None
        a["updated_at"] = row["updated_at"].isoformat() if row["updated_at"] else None
        result.append(a)
    return result


def _collections(db, uid):
    rows = db.execute(text("""
        SELECT c.id,c.name,COALESCE(json_agg(json_build_object('id',t.id,'name',t.name,'region',t.region))
                     FILTER (WHERE t.id IS NOT NULL),'[]'::json) AS treks
        FROM trek_user_collections c
        LEFT JOIN trek_user_collection_items i ON i.collection_id=c.id
        LEFT JOIN treks t ON t.id=i.trek_id AND (t.is_public OR t.owner_id=:u)
        WHERE c.user_id=:u GROUP BY c.id,c.name ORDER BY c.id DESC LIMIT 40
    """), {"u": uid}).mappings().all()
    return [dict(row) for row in rows]


@router.get("/v2")
def dashboard(user=Depends(core.current_user)):
    db = _db()
    try:
        uid = user["id"]
        summary = db.execute(text("""
            SELECT count(*) AS total,count(*) FILTER(WHERE is_public) AS public,
                   count(*) FILTER(WHERE NOT is_public) AS private
            FROM treks WHERE owner_id=:u
        """), {"u": uid}).mappings().one()
        favorites = db.execute(text("SELECT count(*) FROM trek_favorites WHERE user_id=:u"), {"u": uid}).scalar()
        owned = db.execute(text("""
            SELECT id,name,region,distance,elevation,is_public FROM treks
            WHERE owner_id=:u ORDER BY created_at DESC LIMIT 80
        """), {"u": uid}).mappings().all()
        favs = db.execute(text("""
            SELECT t.id,t.name,t.region,t.distance,t.elevation,t.is_public FROM trek_favorites f
            JOIN treks t ON t.id=f.trek_id
            WHERE f.user_id=:u AND (t.is_public OR t.owner_id=:u)
            ORDER BY f.created_at DESC LIMIT 80
        """), {"u": uid}).mappings().all()
        journeys = _journeys(db, uid)
        completed = [j for j in journeys if j["status"] == "completed"]
        distance = round(sum(float(j["actual_distance_km"] or 0) for j in completed), 1)
        ascent = sum(int(j["actual_ascent_m"] or 0) for j in completed)
        achievements = []
        if len(completed) >= 1: achievements.append("Premier trek terminé")
        if len(completed) >= 5: achievements.append("Cinq aventures")
        if distance >= 100: achievements.append("100 km parcourus")
        if len({j["region"] for j in completed}) >= 3: achievements.append("Trois régions explorées")
        return {"user": {"id":uid, "username":user["username"], "email":user["email"],
                         "is_admin":user["is_admin"]},
                "settings": _settings(db,uid),
                "stats": {**dict(summary), "favorites":int(favorites), "completed":len(completed),
                          "actual_km":distance, "actual_ascent_m":ascent},
                "achievements":achievements,"treks":[dict(t) for t in owned],
                "favorites":[dict(t) for t in favs],
                "journeys":journeys,"collections":_collections(db,uid)}
    finally:
        db.close()


@router.put("/v2")
def save_settings(payload: SettingsPayload, user=Depends(core.current_user)):
    if payload.avatar not in _AVATARS:
        raise HTTPException(422, "Avatar inconnu.")
    p = _prefs(payload.preferences)
    db = _db()
    try:
        db.execute(text("""
            INSERT INTO trek_user_profiles(user_id,bio,avatar,public_profile,share_completed,preferences)
            VALUES(:u,:bio,:a,:pub,:share,CAST(:p AS jsonb))
            ON CONFLICT(user_id) DO UPDATE SET
                bio=EXCLUDED.bio, avatar=EXCLUDED.avatar,public_profile=EXCLUDED.public_profile,
                share_completed=EXCLUDED.share_completed,preferences=EXCLUDED.preferences,
                updated_at=CURRENT_TIMESTAMP
        """), {"u":user["id"],"bio":payload.bio.strip(),"a":payload.avatar,
               "pub":payload.public_profile,"share":payload.share_completed and payload.public_profile,
               "p":json.dumps(p)})
        db.commit()
        return {"settings":_settings(db,user["id"])}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.put("/v2/journeys/{trek_id}")
def save_journey(trek_id:int,payload: JourneyPayload,user=Depends(core.current_user)):
    if payload.status not in _STATES:
        raise HTTPException(422, "Statut inconnu.")
    if payload.status != "completed" and (payload.completed_on or payload.actual_distance_km is not None or payload.actual_ascent_m is not None):
        raise HTTPException(422, "Les chiffres réels sont réservés aux treks terminés.")
    if payload.completed_on and payload.completed_on > date.today():
        raise HTTPException(422, "La date de réalisation ne peut pas être future.")
    urls = [_photo_url(v) for v in payload.photo_urls]
    db = _db()
    try:
        _allowed(db,user["id"],trek_id)
        db.execute(text("""
            INSERT INTO trek_user_journeys(user_id,trek_id,status,notes,completed_on,actual_distance_km,
                    actual_ascent_m,rating,photo_urls)
            VALUES(:u,:t,:s,:n,:d,:km,:asc,:rating,CAST(:photos AS jsonb))
            ON CONFLICT(user_id,trek_id) DO UPDATE SET
                status=EXCLUDED.status, notes=EXCLUDED.notes,completed_on=EXCLUDED.completed_on,
                actual_distance_km=EXCLUDED.actual_distance_km,actual_ascent_m=EXCLUDED.actual_ascent_m,
                rating=EXCLUDED.rating,photo_urls=EXCLUDED.photo_urls,updated_at=CURRENT_TIMESTAMP
        """), {"u":user["id"],"t":trek_id,"s":payload.status,"n":payload.notes.strip(),
               "d":payload.completed_on if payload.status=="completed" else None,
               "km":payload.actual_distance_km if payload.status=="completed" else None,
               "asc":payload.actual_ascent_m if payload.status=="completed" else None,
               "rating":payload.rating if payload.status=="completed" else None,
               "photos":json.dumps(urls)})
        db.commit()
        return {"saved":True,"trek_id":trek_id}
    except Exception:
        db.rollback()
        raise
    finally: db.close()


@router.post("/v2/collections")
def add_collection(payload:CollectionPayload,user=Depends(core.current_user)):
    if not payload.name.strip(): raise HTTPException(422,"Nom vide.")
    db=_db()
    try:
        if int(db.execute(text("SELECT count(*) FROM trek_user_collections WHERE user_id=:u"),{"u":user["id"]}).scalar()) >= 25:
            raise HTTPException(422,"Limite de 25 collections.")
        result=db.execute(text("INSERT INTO trek_user_collections(user_id,name) VALUES(:u,:n) RETURNING id"),
                          {"u":user["id"],"n":payload.name.strip()}).scalar_one()
        db.commit()
        return {"id":result}
    except Exception: db.rollback();raise
    finally: db.close()


@router.put("/v2/collections/{collection_id}")
def rename_collection(collection_id:int,payload:CollectionPayload,user=Depends(core.current_user)):
    if not payload.name.strip(): raise HTTPException(422,"Nom vide.")
    db=_db()
    try:
        row=db.execute(text("UPDATE trek_user_collections SET name=:n WHERE id=:id AND user_id=:u RETURNING id"),
                       {"n":payload.name.strip(),"id":collection_id,"u":user["id"]}).first()
        if not row:raise HTTPException(404,"Collection introuvable.")
        db.commit();return {"saved":True}
    except Exception:db.rollback();raise
    finally:db.close()


@router.delete("/v2/collections/{collection_id}")
def remove_collection(collection_id:int,user=Depends(core.current_user)):
    db=_db()
    try:
        result=db.execute(text("DELETE FROM trek_user_collections WHERE id=:id AND user_id=:u RETURNING id"),
                          {"id":collection_id,"u":user["id"]}).first()
        if not result:raise HTTPException(404,"Collection introuvable.")
        db.commit();return {"removed":True}
    except Exception:db.rollback();raise
    finally:db.close()


@router.put("/v2/collections/{collection_id}/treks/{trek_id}")
def add_to_collection(collection_id:int,trek_id:int,user=Depends(core.current_user)):
    db=_db()
    try:
        _allowed(db,user["id"],trek_id)
        if not db.execute(text("SELECT id FROM trek_user_collections WHERE id=:id AND user_id=:u"),
                          {"id":collection_id,"u":user["id"]}).first():
            raise HTTPException(404,"Collection introuvable.")
        count=db.execute(text("SELECT count(*) FROM trek_user_collection_items WHERE collection_id=:id"),
                         {"id":collection_id}).scalar()
        if count >= 100:raise HTTPException(422,"Limite de 100 treks.")
        db.execute(text("INSERT INTO trek_user_collection_items(collection_id,trek_id) VALUES(:c,:t) ON CONFLICT DO NOTHING"),
                   {"c":collection_id,"t":trek_id})
        db.commit();return {"saved":True}
    except Exception:db.rollback();raise
    finally:db.close()


@router.delete("/v2/collections/{collection_id}/treks/{trek_id}")
def remove_from_collection(collection_id:int,trek_id:int,user=Depends(core.current_user)):
    db=_db()
    try:
        if not db.execute(text("SELECT id FROM trek_user_collections WHERE id=:c AND user_id=:u"),
                          {"c":collection_id,"u":user["id"]}).first():raise HTTPException(404,"Collection introuvable.")
        db.execute(text("DELETE FROM trek_user_collection_items WHERE collection_id=:c AND trek_id=:t"),
                   {"c":collection_id,"t":trek_id})
        db.commit();return {"removed":True}
    except Exception:db.rollback();raise
    finally:db.close()


@router.get("/public/{username}")
def public_profile(username:str):
    if not 1<=len(username)<=80:
        raise HTTPException(404,"Profil introuvable.")
    db=_db()
    try:
        row=db.execute(text("""
            SELECT u.id,u.username,p.bio,p.avatar,p.share_completed FROM users u
            JOIN trek_user_profiles p ON p.user_id=u.id
            WHERE LOWER(u.username)=LOWER(:n) AND p.public_profile=TRUE
        """),{"n":username}).mappings().first()
        if not row:raise HTTPException(404,"Profil privé ou introuvable.")
        treks=db.execute(text("""
            SELECT id,name,region,distance,elevation FROM treks
            WHERE owner_id=:u AND is_public=TRUE ORDER BY created_at DESC LIMIT 40
        """),{"u":row["id"]}).mappings().all()
        completed=[]
        if row["share_completed"]:
            completed=db.execute(text("""
                SELECT j.trek_id,t.name,t.region FROM trek_user_journeys j
                JOIN treks t ON t.id=j.trek_id
                WHERE j.user_id=:u AND j.status='completed' AND t.is_public=TRUE
                ORDER BY j.updated_at DESC LIMIT 30
            """),{"u":row["id"]}).mappings().all()
        # Never expose email, dates, journal notes, private treks, photos, or GPS history.
        return {"username":row["username"],"bio":row["bio"],"avatar":row["avatar"],
                "treks":[dict(t) for t in treks],"completed":[dict(t) for t in completed]}
    finally:db.close()
