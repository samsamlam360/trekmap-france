"""Isolated PostGIS tests for fast catalog and linked device accounts.

Hard refuse running against production databases.
"""
import json
import os
from datetime import datetime,timedelta
from http.cookies import SimpleCookie
from uuid import uuid4
from fastapi import Request, Response
from sqlalchemy import text

if "127.0.0.1:5432/trekmap_ci" not in os.getenv("DATABASE_URL",""):
    raise SystemExit("Refusing to test accounts against non-CI databases")

from backend import main,app_v5,account_switch

main.ensure_schema()
account_switch.ensure_device_schema()
routes={r.path:r.endpoint for r in app_v5.app.routes if hasattr(r,"path")}
for path in ("/auth/accounts","/auth/accounts/enroll","/auth/accounts/remove",
             "/auth/accounts/switch","/catalog/bootstrap"):
    assert path in routes,path

def request(cookie=""):
    return Request({"type":"http","method":"POST","path":"/auth/accounts/enroll",
                    "scheme":"https","headers":[(b"cookie",cookie.encode())],
                    "client":("127.0.0.1",54321),"server":("testserver",443)})

def cookie_response(response,name):
    raw="\n".join(x.decode() for k,x in response.raw_headers if k.lower()==b"set-cookie")
    jar=SimpleCookie()
    for line in raw.splitlines():
        jar.load(line)
    return jar[name].value if name in jar else ""

db=main.SessionLocal()
ids=[];treks=[]
try:
    suffix=uuid4().hex[:10]
    for index in (1,2):
        uid=int(db.execute(text("""
            INSERT INTO users(username,email,password_hash)
            VALUES(:n,:e,:p) RETURNING id
        """),{"n":"ci_multi_"+suffix+str(index),
              "e":"ci_multi_"+suffix+str(index)+"@example.invalid",
              "p":main.hash_password("ci-first-pass-123")}).scalar_one())
        ids.append(uid)
    mine=int(db.execute(text("""
        INSERT INTO treks(name,region,difficulty,description,distance,elevation,is_public,owner_id)
        VALUES(:name,'Auvergne-Rhône-Alpes','easy','private CI trek',25,340,FALSE,:uid)
        RETURNING id
    """),{"name":"CI private "+suffix,"uid":ids[0]}).scalar_one())
    public=int(db.execute(text("""
        INSERT INTO treks(name,region,difficulty,description,distance,elevation,is_public,owner_id)
        VALUES(:name,'Bretagne','easy','public CI trek',12,120,TRUE,:uid)
        RETURNING id
    """),{"name":"CI public "+suffix,"uid":ids[1]}).scalar_one())
    treks.extend([mine,public])
    db.execute(text("INSERT INTO trek_favorites(user_id,trek_id) VALUES(:u,:t)"),
               {"u":ids[0],"t":public})
    first_token="ci_multi_session_"+uuid4().hex
    db.execute(text("""INSERT INTO user_sessions(user_id,token,expires_at)
        VALUES(:u,:t,:expiry)"""),{"u":ids[0],"t":first_token,
        "expiry":datetime.now()+timedelta(days=20)})
    db.commit()

    # Lightweight metadata is scoped per signed-in user and omits geometry.
    bootstrap=routes["/catalog/bootstrap"]
    for who,can_see_private in ((None,False),(ids[0],True),(ids[1],False)):
        u=None if who is None else {"id":who,"is_admin":False}
        payload=bootstrap(user=u)
        assert isinstance(payload["treks"],list) and isinstance(payload["regions"],list)
        listed={x["id"]:x for x in payload["treks"]}
        assert (mine in listed)==can_see_private,(who,mine)
        assert public in listed,(who,public)
        assert all(not item["coords"] and item["geometry"] is None for item in payload["treks"])
        if who==ids[0]:assert listed[public]["is_favorite"] is True
        else:assert not listed[public]["is_favorite"]
    # After login with a password, only the authorized device can switch.
    first=Response()
    routes["/auth/accounts/enroll"](request=request(),response=first,
                                   user={"id":ids[0],"token":first_token})
    device=cookie_response(first,account_switch.DEVICE_COOKIE)
    assert len(device)>=40
    second=Response()
    account_switch.link_login(request(account_switch.DEVICE_COOKIE+"="+device),
                              second,ids[1],db)
    db.commit()
    linked=routes["/auth/accounts"](
        request=request(account_switch.DEVICE_COOKIE+"="+device),
        user={"id":ids[0]})
    assert {entry["id"] for entry in linked["accounts"]}==set(ids),linked
    assert sum(bool(entry["active"]) for entry in linked["accounts"])==1
    switched=Response()
    result=routes["/auth/accounts/switch"](
        data=account_switch.SwitchAccount(user_id=ids[1]),
        request=request(account_switch.DEVICE_COOKIE+"="+device),
        response=switched,
        user={"id":ids[0],"token":first_token})
    assert result["user"]["id"]==ids[1]
    assert cookie_response(switched,main.SESSION_COOKIE)
    assert not db.execute(text("SELECT 1 FROM user_sessions WHERE token=:t"),
                          {"t":first_token}).first()
    # A different browser cannot switch, even if another user has enrolled.
    from fastapi import HTTPException
    try:
        routes["/auth/accounts/switch"](
            data=account_switch.SwitchAccount(user_id=ids[1]),request=request(),
            response=Response(),user={"id":ids[0],"token":"invalid"})
        raise AssertionError("Cross-device quick switch accepted")
    except HTTPException as exc:assert exc.status_code==403
    routes["/auth/accounts/remove"](
        data=account_switch.SwitchAccount(user_id=ids[1]),
        request=request(account_switch.DEVICE_COOKIE+"="+device),
        response=Response(),user={"id":ids[0]})
    listed=routes["/auth/accounts"](
        request=request(account_switch.DEVICE_COOKIE+"="+device),
        user={"id":ids[0]})
    assert {x["id"] for x in listed["accounts"]}=={ids[0]}
    print("FAST CATALOG + MULTIACCOUNT CI PASS: scoped private treks, favorites, "
          "no geometry in bootstrap, linked secure cookies, switching and device isolation")
finally:
    db.rollback()
    if ids:
        db.execute(text("DELETE FROM user_sessions WHERE user_id=ANY(:ids)"),{"ids":ids})
        db.execute(text("DELETE FROM user_account_devices WHERE user_id=ANY(:ids)"),{"ids":ids})
        db.execute(text("DELETE FROM treks WHERE id=ANY(:treks)"),{"treks":treks})
        db.execute(text("DELETE FROM users WHERE id=ANY(:ids)"),{"ids":ids})
        db.commit()
    db.close()
