"""Tests de récupération sécurisée, uniquement sur PostGIS de la CI locale.

Aucun courrier externe : l'envoi est remplacé par une capture en mémoire.
Ni utilisateurs réels ni données Neon ne sont lus ou modifiés.
"""
import os
from datetime import datetime, timedelta
from uuid import uuid4
from fastapi import HTTPException, Response
from sqlalchemy import text

url=os.getenv("DATABASE_URL","")
if "127.0.0.1:5432/trekmap_ci" not in url:
    raise SystemExit("Password-reset integration tests require isolated local CI PostGIS")

from backend import app_v5, main, password_reset as recovery

main.ensure_schema()
recovery.ensure_reset_schema()
route_by_path={r.path:r.endpoint for r in app_v5.app.routes if hasattr(r,"path")}
assert all(path in route_by_path for path in
           ("/auth/password/forgot","/auth/password/reset","/auth/password/status"))
assert main.RATE_LIMITS["/auth/password/forgot"]==4
assert main.RATE_LIMITS["/auth/password/reset"]==12

old_key=os.environ.get("RESEND_API_KEY")
old_from=os.environ.get("RESET_EMAIL_FROM")
old_sender=recovery.send_reset_email
user_id=None
db=main.SessionLocal()
captured=[]
try:
    os.environ.pop("RESEND_API_KEY",None)
    os.environ.pop("RESET_EMAIL_FROM",None)
    assert not route_by_path["/auth/password/status"]()["email_reset_available"]
    try:
        route_by_path["/auth/password/forgot"](recovery.ForgotPassword(email="missing@example.org"))
        raise AssertionError("Misconfigured email transport must fail closed")
    except HTTPException as e:
        assert e.status_code==503
    os.environ["RESEND_API_KEY"]="fake-for-test-only"
    os.environ["RESET_EMAIL_FROM"]="Test <test@testing.invalid>"
    recovery.send_reset_email=lambda address,token:captured.append((address,token))
    assert route_by_path["/auth/password/status"]()["email_reset_available"]

    random_name="ci_reset_"+uuid4().hex[:12]
    email=random_name+"@example.invalid"
    user_id=db.execute(text("""
       INSERT INTO users(username,email,password_hash)
       VALUES(:name,:email,:password) RETURNING id
    """),{"name":random_name,"email":email,
          "password":main.hash_password("initial-password-123")}).scalar_one()
    db.execute(text("""
       INSERT INTO user_sessions(user_id,token,expires_at)
       VALUES(:uid,:token,:expiry)
    """),{"uid":user_id,"token":"ci-session-"+uuid4().hex,
          "expiry":datetime.utcnow()+timedelta(days=5)})
    db.commit()

    generic=route_by_path["/auth/password/forgot"](
        recovery.ForgotPassword(email="nobody-"+random_name+"@example.invalid"))
    assert generic["message"]==recovery.GENERIC_MESSAGE and not captured
    result=route_by_path["/auth/password/forgot"](recovery.ForgotPassword(email=email.upper()))
    assert result==generic and len(captured)==1
    address,token=captured[0]
    assert address==email and len(token)>=40
    assert token not in str(db.execute(text("""
        SELECT token_hash,expires_at FROM password_reset_tokens WHERE user_id=:u
    """),{"u":user_id}).all())
    assert db.execute(text("""
        SELECT token_hash FROM password_reset_tokens WHERE user_id=:u
    """),{"u":user_id}).scalar_one()==recovery.hash_token(token)
    # Retry throttled per account, no mail storm.
    route_by_path["/auth/password/forgot"](recovery.ForgotPassword(email=email))
    assert len(captured)==1

    invalid="x"*64
    try:
        route_by_path["/auth/password/reset"](
            recovery.ResetPassword(token=invalid,new_password="safer-new-password-123"),
            Response())
        raise AssertionError("Unknown reset token was accepted")
    except HTTPException as e: assert e.status_code==400

    endpoint=route_by_path["/auth/password/reset"]
    success=endpoint(
        recovery.ResetPassword(token=token,new_password="safer-new-password-123"), Response())
    assert success["message"].startswith("Mot de passe modifié")
    row=db.execute(text("SELECT password_hash FROM users WHERE id=:u"),{"u":user_id}).first()
    # Close/expire SQLAlchemy session identity map before reading writes.
    db.expire_all()
    row=db.execute(text("SELECT password_hash FROM users WHERE id=:u"),{"u":user_id}).first()
    assert main.verify_password("safer-new-password-123",row.password_hash)
    assert not main.verify_password("initial-password-123",row.password_hash)
    assert not db.execute(text("SELECT 1 FROM user_sessions WHERE user_id=:u"),{"u":user_id}).first()
    try:
        endpoint(recovery.ResetPassword(token=token,new_password="yet-another-password-123"),Response())
        raise AssertionError("Reused reset token accepted")
    except HTTPException as e: assert e.status_code==400

    # Create an expired reset token directly, verify expiry cannot be bypassed.
    expired="ci-expired-"+uuid4().hex+uuid4().hex
    db.execute(text("""
      INSERT INTO password_reset_tokens(token_hash,user_id,expires_at)
      VALUES(:t,:u,:expires)
    """),{"t":recovery.hash_token(expired),"u":user_id,
          "expires":datetime.utcnow()-timedelta(seconds=1)})
    db.commit()
    try:
        endpoint(recovery.ResetPassword(token=expired,new_password="yet-another-password-123"),Response())
        raise AssertionError("Expired reset token accepted")
    except HTTPException as e: assert e.status_code==400

    assert all(token not in repr(v) for v in (generic,success))
    print("PASSWORD RESET CI PASS: no account enumeration, sender fail-closed, throttling, "
          "hashed expiring single-use token, login-session revocation")
finally:
    recovery.send_reset_email=old_sender
    if old_key is None:os.environ.pop("RESEND_API_KEY",None)
    else:os.environ["RESEND_API_KEY"]=old_key
    if old_from is None:os.environ.pop("RESET_EMAIL_FROM",None)
    else:os.environ["RESET_EMAIL_FROM"]=old_from
    if user_id is not None:
        db.rollback()
        db.execute(text("DELETE FROM users WHERE id=:u"),{"u":user_id})
        db.commit()
    db.close()
