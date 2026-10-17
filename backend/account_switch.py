"""Sessions de plusieurs comptes sur un seul navigateur.

Le navigateur ne reçoit jamais de jeton de session en JavaScript. Un cookie
HttpOnly aléatoire identifie cet appareil; sa seule empreinte est en base.
Chaque compte doit d'abord être connecté avec son mot de passe avant d'être
disponible pour les changements rapides.
"""
from datetime import datetime, timedelta
from hashlib import sha256
import os
import secrets
from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import main as core

DEVICE_COOKIE="__Host-trekmap_accounts" if core.IS_PRODUCTION else "trekmap_accounts"
MAX_LINKED=5
DEVICE_DAYS=30
DEVICE_SCHEMA_READY=False


class SwitchAccount(BaseModel):
    user_id: int = Field(gt=0)


def device_digest(raw):
    return sha256(raw.encode("ascii")).hexdigest()


def ensure_device_schema():
    global DEVICE_SCHEMA_READY
    if DEVICE_SCHEMA_READY:
        return
    db=core.db_or_503()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_account_devices (
                device_hash VARCHAR(64) NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                PRIMARY KEY(device_hash,user_id)
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_account_devices_user ON user_account_devices(user_id)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_account_devices_expiry ON user_account_devices(expires_at)"))
        db.commit()
        DEVICE_SCHEMA_READY=True
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


def set_device_cookie(response,raw):
    response.set_cookie(DEVICE_COOKIE,raw,path="/",secure=core.IS_PRODUCTION,
        httponly=True,samesite="lax",max_age=DEVICE_DAYS*86400)


def forget_device(request,response,db):
    raw=request.cookies.get(DEVICE_COOKIE,"")
    if len(raw)>=40 and len(raw)<=160:
        db.execute(text("DELETE FROM user_account_devices WHERE device_hash=:h"),
                   {"h":device_digest(raw)})
    response.delete_cookie(DEVICE_COOKIE,path="/")


def link_login(request,response,uid,db):
    """Called inside the successful password-authentication transaction."""
    now=datetime.now()
    raw=request.cookies.get(DEVICE_COOKIE,"")
    exists=False
    if 40<=len(raw)<=160:
        exists=bool(db.execute(text("""
            SELECT 1 FROM user_account_devices
            WHERE device_hash=:h AND expires_at>:now LIMIT 1
        """),{"h":device_digest(raw),"now":now}).first())
    if not exists:
        raw=secrets.token_urlsafe(48)
    digest=device_digest(raw)
    count=int(db.execute(text("""
        SELECT COUNT(*) FROM user_account_devices
        WHERE device_hash=:h AND expires_at>:now
    """),{"h":digest,"now":now}).scalar() or 0)
    already=bool(db.execute(text("""
        SELECT 1 FROM user_account_devices WHERE device_hash=:h AND user_id=:u
    """),{"h":digest,"u":uid}).first())
    if count>=MAX_LINKED and not already:
        # Authentication still succeeds, but don't link a sixth account.
        return
    db.execute(text("""
        INSERT INTO user_account_devices(device_hash,user_id,expires_at)
        VALUES(:h,:u,:expires)
        ON CONFLICT(device_hash,user_id) DO UPDATE SET expires_at=EXCLUDED.expires_at
    """),{"h":digest,"u":uid,"expires":now+timedelta(days=DEVICE_DAYS)})
    set_device_cookie(response,raw)


def install_account_switch(app):
    core.RATE_LIMITS["/auth/accounts/enroll"]=8
    core.RATE_LIMITS["/auth/accounts/switch"]=12
    core.RATE_LIMITS["/auth/accounts/remove"]=12

    @app.on_event("startup")
    def device_schema_startup():
        try:
            ensure_device_schema()
        except Exception:
            # The rest of the service remains accessible.
            pass

    @app.post("/auth/accounts/enroll")
    def enroll_current_device(request:Request,response:Response,
                              user=Depends(core.current_user)):
        """Remember the already-authenticated user, with explicit user action."""
        ensure_device_schema()
        db=core.db_or_503()
        try:
            link_login(request,response,int(user["id"]),db)
            db.commit()
            return {"message":"Compte ajouté à cet appareil."}
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(503,"Enregistrement du compte indisponible.") from exc
        finally:
            db.close()

    @app.get("/auth/accounts")
    def accounts(request:Request,user=Depends(core.current_user)):
        raw=request.cookies.get(DEVICE_COOKIE,"")
        if not 40<=len(raw)<=160:
            return {"accounts":[],"max_accounts":MAX_LINKED}
        db=core.db_or_503()
        try:
            rows=db.execute(text("""
                SELECT u.id,u.username,u.email
                FROM user_account_devices d JOIN users u ON d.user_id=u.id
                WHERE d.device_hash=:h AND d.expires_at>:now
                ORDER BY d.linked_at,u.id
                LIMIT :max
            """),{"h":device_digest(raw),"now":datetime.now(),"max":MAX_LINKED}).all()
            return {"accounts":[{"id":int(row.id),"username":row.username,
                                 "email":row.email,"active":int(row.id)==int(user["id"])}
                                for row in rows],
                    "max_accounts":MAX_LINKED}
        finally:
            db.close()

    @app.post("/auth/accounts/switch")
    def switch_account(data:SwitchAccount,request:Request,response:Response,
                       user=Depends(core.current_user)):
        raw=request.cookies.get(DEVICE_COOKIE,"")
        if not 40<=len(raw)<=160:
            raise HTTPException(403,"Appareil non reconnu. Reconnecte-toi.")
        ensure_device_schema()
        db=core.db_or_503()
        try:
            row=db.execute(text("""
                SELECT u.id,u.username,u.email,u.is_admin
                FROM user_account_devices d JOIN users u ON u.id=d.user_id
                WHERE d.device_hash=:h AND d.user_id=:uid AND d.expires_at>:now
            """),{"h":device_digest(raw),"uid":data.user_id,"now":datetime.now()}).first()
            if not row:
                raise HTTPException(403,"Ce compte doit être ajouté avec son mot de passe.")
            token=secrets.token_urlsafe(48)
            db.execute(text("""
                INSERT INTO user_sessions(token,user_id,expires_at)
                VALUES(:token,:u,:expiry)
            """),{"token":token,"u":int(row.id),
                   "expiry":datetime.now()+timedelta(days=core.SESSION_DURATION_DAYS)})
            # Invalidate active session, but keep linked accounts on this device.
            db.execute(text("DELETE FROM user_sessions WHERE token=:t"),
                       {"t":user["token"]})
            db.commit()
            core.set_session_cookies(response,token)
            response.headers["Cache-Control"]="no-store"
            return {"user":{"id":int(row.id),"username":row.username,
                            "email":row.email,"is_admin":bool(row.is_admin)}}
        except HTTPException:
            db.rollback()
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(503,"Changement de compte indisponible.") from exc
        finally:
            db.close()

    @app.post("/auth/accounts/remove")
    def remove_account(data:SwitchAccount,request:Request,response:Response,
                       user=Depends(core.current_user)):
        raw=request.cookies.get(DEVICE_COOKIE,"")
        if not 40<=len(raw)<=160:
            raise HTTPException(403,"Appareil non reconnu.")
        db=core.db_or_503()
        try:
            db.execute(text("""
                DELETE FROM user_account_devices
                WHERE device_hash=:h AND user_id=:uid
            """),{"h":device_digest(raw),"uid":data.user_id})
            db.commit()
            return {"message":"Compte retiré de cet appareil."}
        finally:
            db.close()
