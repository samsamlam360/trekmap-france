"""Reset de mot de passe TrekMap : lien secret à usage unique, 30 min.

Les tokens bruts ne sont jamais persistés. L'envoi externe est activé seulement
si RESEND_API_KEY et RESET_EMAIL_FROM sont configurés dans les secrets Render.
Pas de fuite d'existence des comptes dans les réponses publiques.
"""
from datetime import datetime, timedelta
import hashlib
import os
import re
import secrets
import smtplib
from email.message import EmailMessage

import requests
from fastapi import HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import main as core

RESET_TTL_MINUTES = 30
RESET_URL = "https://trekmap-france.onrender.com/"
GENERIC_MESSAGE = ("Si cette adresse correspond à un compte TrekMap, "
                   "un lien de réinitialisation a été envoyé. Vérifie aussi les indésirables.")


class ForgotPassword(BaseModel):
    email: str = Field(min_length=5, max_length=255)


class ResetPassword(BaseModel):
    token: str = Field(min_length=40, max_length=160)
    new_password: str = Field(min_length=12, max_length=200)


def smtp_configured():
    return all(os.getenv(key, "").strip() for key in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"
    ))


def configured():
    resend_ready = bool(os.getenv("RESEND_API_KEY", "").strip() and
                        os.getenv("RESET_EMAIL_FROM", "").strip())
    return smtp_configured() or resend_ready


def hash_token(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def ensure_reset_schema():
    db = core.db_or_503()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_hash VARCHAR(64) PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                consumed_at TIMESTAMP
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS password_reset_user_idx "
                        "ON password_reset_tokens(user_id,created_at DESC)"))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


def send_reset_email(email, token):
    # URL fragment : jamais dans les logs HTTP ni dans Referer du serveur.
    # Pas de template HTML distant qui exposerait le jeton à des ressources.
    url = RESET_URL + "#reset=" + token
    body = ("Bonjour,\n\nUne réinitialisation de mot de passe a été demandée "
            "pour ton compte TrekMap France.\n\nOuvre ce lien (valable 30 minutes "
            "et une seule fois) :\n" + url + "\n\n"
            "Si tu n'as rien demandé, ignore ce message.\n"
            "L'équipe TrekMap France")
    subject = "Réinitialiser ton mot de passe TrekMap"
    # SMTP est prioritaire. Pour Gmail, utiliser un mot de passe d'application.
    if smtp_configured():
        message = EmailMessage()
        message["From"] = os.environ["SMTP_FROM"].strip()
        message["To"] = email
        message["Subject"] = subject
        message.set_content(body)
        host = os.environ["SMTP_HOST"].strip()
        port = int(os.environ["SMTP_PORT"].strip())
        username = os.environ["SMTP_USERNAME"].strip()
        password = os.environ["SMTP_PASSWORD"].strip()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=12) as server:
                server.login(username, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=12) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(username, password)
                server.send_message(message)
        return

    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"].strip(),
                 "Content-Type": "application/json"},
        json={"from": os.environ["RESET_EMAIL_FROM"].strip(),
              "to": [email], "subject": subject, "text": body},
        timeout=9,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError("Le service de courrier a refusé la demande.")


def install_password_reset(app):
    core.RATE_LIMITS["/auth/password/forgot"] = 4
    core.RATE_LIMITS["/auth/password/reset"] = 12

    @app.on_event("startup")
    def prepare_reset_storage():
        try:
            ensure_reset_schema()
        except Exception:
            # Les autres routes TrekMap continuent ; /forgot refuse si la DB
            # ne fonctionne pas, au lieu de simuler un envoi.
            pass

    @app.get("/auth/password/status")
    def reset_status():
        return {"email_reset_available": configured()}

    @app.post("/auth/password/forgot")
    def forgot_password(data: ForgotPassword):
        if not configured():
            raise HTTPException(503, "L'envoi des e-mails n'est pas encore configuré.")
        email = data.email.strip().casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise HTTPException(422, "Adresse e-mail invalide.")
        db = core.db_or_503()
        token_hash = None
        try:
            row = db.execute(text(
                "SELECT id,email FROM users WHERE LOWER(email)=:email"), {"email": email}).first()
            if row:
                now = datetime.utcnow()
                recent = db.execute(text("""
                    SELECT COUNT(*) AS n, MAX(created_at) AS latest
                    FROM password_reset_tokens
                    WHERE user_id=:uid AND created_at > :cutoff
                """), {"uid": row.id, "cutoff": now - timedelta(hours=1)}).first()
                if recent.n < 3 and (recent.latest is None or
                                      now - recent.latest >= timedelta(minutes=15)):
                    token = secrets.token_urlsafe(48)
                    token_hash = hash_token(token)
                    db.execute(text("""
                        INSERT INTO password_reset_tokens(token_hash,user_id,expires_at)
                        VALUES (:token,:uid,:expires)
                    """), {"token": token_hash, "uid": row.id,
                           "expires": now + timedelta(minutes=RESET_TTL_MINUTES)})
                    db.commit()
                    try:
                        send_reset_email(row.email, token)
                    except Exception:
                        # Suppression du token inutilisable ; aucun mot de passe
                        # n'est modifié en cas d'échec de livraison.
                        db.execute(text("DELETE FROM password_reset_tokens WHERE token_hash=:t"),
                                   {"t": token_hash})
                        db.commit()
                        raise HTTPException(503, "L'envoi du courriel a échoué. Réessaie plus tard.")
            return {"message": GENERIC_MESSAGE}
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(503, "Service de récupération indisponible.") from exc
        finally:
            db.close()

    @app.post("/auth/password/reset")
    def reset_password(data: ResetPassword, response: Response):
        if not re.fullmatch(r"[A-Za-z0-9_-]{40,160}", data.token):
            raise HTTPException(400, "Lien de réinitialisation invalide.")
        digest = hash_token(data.token)
        from .account_switch import ensure_device_schema
        ensure_device_schema()
        db = core.db_or_503()
        try:
            row = db.execute(text("""
                SELECT token_hash,user_id,expires_at,consumed_at
                FROM password_reset_tokens WHERE token_hash=:t FOR UPDATE
            """), {"t": digest}).first()
            if (not row or row.consumed_at is not None or
                    row.expires_at <= datetime.utcnow()):
                raise HTTPException(400, "Lien expiré ou déjà utilisé. Demande un nouveau lien.")
            db.execute(text("UPDATE users SET password_hash=:hash WHERE id=:uid"),
                       {"hash": core.hash_password(data.new_password), "uid": row.user_id})
            db.execute(text("UPDATE password_reset_tokens SET consumed_at=:now "
                            "WHERE user_id=:uid AND consumed_at IS NULL"),
                       {"now": datetime.utcnow(), "uid": row.user_id})
            db.execute(text("DELETE FROM user_sessions WHERE user_id=:uid"),
                       {"uid": row.user_id})
            # A reset also removes remembered quick-switch grants on every device.
            db.execute(text("DELETE FROM user_account_devices WHERE user_id=:uid"),
                       {"uid": row.user_id})
            db.commit()
            core.clear_session_cookies(response)
            response.headers["Cache-Control"] = "no-store"
            return {"message": "Mot de passe modifié. Reconnecte-toi."}
        except HTTPException:
            db.rollback()
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(503, "Impossible de réinitialiser pour le moment.") from exc
        finally:
            db.close()
