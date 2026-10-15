"""Profile integration contract against GitHub Actions' local PostGIS only.

Never executes on Neon/Render/production URLs, and cleans up every test row.
"""
import os
import base64
from datetime import date
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

url = os.environ.get("DATABASE_URL", "")
if "127.0.0.1:5432/trekmap_ci" not in url:
    raise SystemExit("Refusing profile write tests outside local CI PostGIS")

from backend import app_v5, main, profile_v2

main.ensure_schema()
suffix = uuid4().hex[:10]
username = "ci_prof_" + suffix
email = username + "@example.invalid"
uid = None
trek_id = None
db = main.SessionLocal()
try:
    uid = int(db.execute(text("""
        INSERT INTO users(username,email,password_hash) VALUES(:name,:email,'ci-no-login')
        RETURNING id
    """), {"name": username, "email": email}).scalar_one())
    trek_id = int(db.execute(text("""
        INSERT INTO treks(name,region,difficulty,distance,elevation,is_public,owner_id)
        VALUES('CI profile hike','CI region','easy',24.5,600,TRUE,:u) RETURNING id
    """), {"u":uid}).scalar_one())
    db.commit()

    user={"id":uid,"username":username,"email":email,"is_admin":False}
    paths={x.path for x in app_v5.app.routes}
    assert "/profile/v2" in paths
    assert "/profile/public/{username}" in paths

    initial=profile_v2.dashboard(user=user)
    assert initial["settings"]["public_profile"] is False
    assert initial["stats"]["completed"]==0 and initial["stats"]["actual_km"]==0
    assert initial["treks"] and initial["treks"][0]["id"]==trek_id

    try:
        profile_v2.public_profile(username)
        raise AssertionError("Private profile must not be public")
    except HTTPException as exc:
        assert exc.status_code==404

    settings=profile_v2.SettingsPayload(
        bio="Marcheur CI",avatar="compass",public_profile=True,share_completed=False,
        preferences={"daily_km":19,"difficulty":"medium","lodging":"camping",
                     "route_type":"Boucle","transit":True,"water":True,"food":True,"sleep":True})
    profile_v2.save_settings(settings,user=user)
    local_photo = "data:image/jpeg;base64," + base64.b64encode(
        b"\\xff\\xd8\\xff" + b"test-local-photo" + b"\\xff\\xd9"
    ).decode("ascii")
    profile_v2.save_journey(trek_id,
        profile_v2.JourneyPayload(status="completed",completed_on=date(2026,8,12),
            actual_distance_km=21.7,actual_ascent_m=421,rating=4,
            notes="Notes CI strictement privées",photo_urls=["https://example.org/photo.jpg", local_photo]),user=user)
    changed=profile_v2.dashboard(user=user)
    assert changed["stats"]["completed"]==1
    assert changed["stats"]["actual_km"]==21.7
    assert changed["stats"]["actual_ascent_m"]==421
    assert changed["achievements"]==["Premier trek terminé"]
    assert changed["settings"]["preferences"]["daily_km"]==19
    assert local_photo in changed["journeys"][0]["photo_urls"]

    collection_id=profile_v2.add_collection(profile_v2.CollectionPayload(name="Montagnes CI"),user=user)["id"]
    profile_v2.add_to_collection(collection_id,trek_id,user=user)
    again=profile_v2.dashboard(user=user)
    assert again["collections"][0]["treks"][0]["id"]==trek_id
    profile_v2.remove_from_collection(collection_id,trek_id,user=user)
    profile_v2.remove_collection(collection_id,user=user)

    shared=profile_v2.public_profile(username)
    assert shared["username"]==username
    assert shared["completed"]==[], "Completed hikes require second opt-in"
    assert "email" not in shared
    assert "Notes CI strictement privées" not in str(shared)
    assert "https://example.org/photo.jpg" not in str(shared)
    assert local_photo not in str(shared)

    settings.share_completed=True
    profile_v2.save_settings(settings,user=user)
    shared=profile_v2.public_profile(username)
    assert len(shared["completed"])==1
    assert "completed_on" not in str(shared)
    assert "photo_urls" not in str(shared)
    try:
        profile_v2.save_journey(trek_id,profile_v2.JourneyPayload(
            status="planned",actual_distance_km=9000),user=user)
        raise AssertionError("Uncompleted treks cannot increase walked stats")
    except HTTPException as exc:
        assert exc.status_code==422

    other={"id":uid+5000000,"username":"another","email":"no@example.invalid","is_admin":False}
    # Private route permission is tested by temporarily flipping only the CI trek.
    db.execute(text("UPDATE treks SET is_public=FALSE WHERE id=:t"),{"t":trek_id})
    db.commit()
    try:
        profile_v2.save_journey(trek_id,profile_v2.JourneyPayload(status="planned"),user=other)
        raise AssertionError("Non-owner must not save a private trek")
    except HTTPException as exc:
        assert exc.status_code==404
    shared=profile_v2.public_profile(username)
    assert not shared["treks"] and not shared["completed"]
    print("PROFILE REAL DB PASS: add-only schema, private/public sharing, journals, km, collections, permissions")
finally:
    if uid is not None:
        try:
            db.rollback()
            if trek_id is not None:
                db.execute(text("DELETE FROM treks WHERE id=:t AND owner_id=:u"),{"t":trek_id,"u":uid})
            db.execute(text("DELETE FROM users WHERE id=:u"),{"u":uid})
            db.commit()
        except Exception:
            db.rollback()
            raise
    db.close()
