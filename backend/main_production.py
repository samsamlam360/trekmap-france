"""Production entrypoint for TrekMap France."""

import time
from pathlib import Path

from fastapi import HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy import text

from . import main as legacy_main
from .ors import get_route as ors_get_route

app = legacy_main.app
FRONTEND_ORIGINS = legacy_main.FRONTEND_ORIGINS
IS_PRODUCTION = legacy_main.IS_PRODUCTION
rate_limited = legacy_main.rate_limited

# Replace the legacy ORS implementation without rewriting the large main.py.
legacy_main.get_route = lambda coords: ors_get_route(coords, legacy_main.distance_gps)

# Retry léger pour les connexions PostgreSQL transitoirement indisponibles.
_original_db_or_503 = legacy_main.db_or_503

def robust_db_or_503():
    last_error = None
    for attempt in range(2):
        try:
            return _original_db_or_503()
        except HTTPException as exc:
            last_error = exc
            legacy_main.SCHEMA_READY = False
            if attempt == 0:
                time.sleep(0.35)
        except Exception as exc:
            last_error = exc
            legacy_main.SCHEMA_READY = False
            if attempt == 0:
                time.sleep(0.35)
    if isinstance(last_error, HTTPException):
        raise last_error
    raise HTTPException(status_code=503, detail="Base de données temporairement indisponible. Réessaie dans quelques secondes.") from last_error

legacy_main.db_or_503 = robust_db_or_503

# Retirer les anciennes routes que l'on remplace par les versions production ci-dessous.
app.router.routes = [r for r in app.router.routes if r.path not in {"/", "/auth/statistics", "/statistics"}]

@app.get("/auth/statistics")
def user_statistics(user=Depends(legacy_main.current_user)):
    db = robust_db_or_503()
    try:
        mine = db.execute(text("""
            SELECT COUNT(*) total,
                   COUNT(*) FILTER (WHERE is_public=TRUE) public,
                   COUNT(*) FILTER (WHERE is_public=FALSE) private,
                   COALESCE(SUM(distance),0) distance,
                   COALESCE(SUM(elevation),0) elevation,
                   COALESCE(SUM(view_count),0) views
            FROM treks WHERE owner_id=:u
        """), {"u": user["id"]}).first()
        favorites = db.execute(text("SELECT COUNT(*) FROM trek_favorites WHERE user_id=:u"), {"u": user["id"]}).scalar() or 0
        comments = db.execute(text("SELECT COUNT(*) FROM trek_comments c JOIN treks t ON t.id=c.trek_id WHERE t.owner_id=:u"), {"u": user["id"]}).scalar() or 0
        plans = db.execute(text("SELECT COUNT(*) FROM trek_plans WHERE user_id=:u"), {"u": user["id"]}).scalar() or 0
        received = db.execute(text("SELECT COUNT(*) FROM trek_favorites f JOIN treks t ON t.id=f.trek_id WHERE t.owner_id=:u"), {"u": user["id"]}).scalar() or 0
        top = db.execute(text("SELECT id,name,view_count,distance FROM treks WHERE owner_id=:u ORDER BY view_count DESC,name ASC LIMIT 1"), {"u": user["id"]}).first()
        return {
            "treks": {"total": int(mine.total or 0), "public": int(mine.public or 0), "private": int(mine.private or 0), "distance_km": round(float(mine.distance or 0),1), "elevation_m": int(mine.elevation or 0), "views": int(mine.views or 0)},
            "favorites": int(favorites), "favorites_received": int(received), "comments_received": int(comments), "plans": int(plans),
            "most_viewed": ({"id":int(top.id),"name":top.name,"views":int(top.view_count or 0),"distance":float(top.distance or 0)} if top else None)
        }
    finally:
        db.close()

@app.get("/statistics")
def public_statistics():
    db = robust_db_or_503()
    try:
        row = db.execute(text("""
            SELECT COUNT(*) FILTER (WHERE is_public=TRUE) treks,
                   COUNT(DISTINCT owner_id) FILTER (WHERE owner_id IS NOT NULL AND is_public=TRUE) creators,
                   COALESCE(SUM(distance) FILTER (WHERE is_public=TRUE),0) distance,
                   COALESCE(SUM(elevation) FILTER (WHERE is_public=TRUE),0) elevation,
                   COALESCE(SUM(view_count) FILTER (WHERE is_public=TRUE),0) views
            FROM treks
        """)).first()
        users = db.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
        favorites = db.execute(text("SELECT COUNT(*) FROM trek_favorites f JOIN treks t ON t.id=f.trek_id WHERE t.is_public=TRUE")).scalar() or 0
        comments = db.execute(text("SELECT COUNT(*) FROM trek_comments c JOIN treks t ON t.id=c.trek_id WHERE t.is_public=TRUE")).scalar() or 0
        return {"treks":int(row.treks or 0),"creators":int(row.creators or 0),"users":int(users),"distance_km":round(float(row.distance or 0),1),"elevation_m":int(row.elevation or 0),"views":int(row.views or 0),"favorites":int(favorites),"comments":int(comments)}
    finally:
        db.close()

FRONTEND_FILE = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
UI_ENHANCEMENT = r"""
<script>
(function(){
  function setupLargeTrekFilters(){
    const d=document.getElementById('distance-range'),dt=document.getElementById('distance-tolerance'),e=document.getElementById('elevation-range'),et=document.getElementById('elevation-tolerance'),dur=document.getElementById('duration-filter');
    if(d){d.max='3000';d.step='5'} if(dt){dt.max='500';dt.step='5'} if(e){e.max='15000';e.step='50'} if(et){et.max='5000';et.step='50'}
    if(dur){const existing=new Set([...dur.options].map(o=>o.value));[[60,'≤ 60 jours'],[90,'≤ 90 jours'],[120,'≤ 120 jours'],[180,'≤ 180 jours'],[365,'≤ 365 jours']].forEach(([v,label])=>{if(!existing.has(String(v))){const o=document.createElement('option');o.value=v;o.textContent=label;dur.appendChild(o)}})}
  }
  function addStatsButton(){const nav=document.getElementById('bottom-nav');if(!nav||document.getElementById('stats-nav'))return;const b=document.createElement('button');b.id='stats-nav';b.innerHTML='📊 <span>Stats</span>';b.onclick=window.TrekMapOpenStats;nav.appendChild(b)}
  window.TrekMapOpenStats=async function(){
    const modal=document.getElementById('modal'),back=document.getElementById('modal-backdrop');if(!modal||!back)return;
    modal.innerHTML='<div class="modal-head"><h2>📊 Statistiques TrekMap</h2><button class="close" id="stats-close">✕</button></div><div id="stats-content" class="detail-grid"><div class="stat"><small>Chargement</small><b>…</b></div></div>';
    back.style.display='flex';document.getElementById('stats-close').onclick=()=>{back.style.display='none';modal.innerHTML=''};
    try{
      const logged=!!localStorage.getItem('trekmap_token');
      const endpoint=logged?'/auth/statistics':'/statistics';
      const r=await fetch(endpoint,{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.detail||('HTTP '+r.status));
      const c=document.getElementById('stats-content');let cards;
      if(logged){cards=[['🥾','Mes treks',d.treks.total],['🌍','Treks publics',d.treks.public],['🔒','Treks privés',d.treks.private],['📏','Distance créée',Number(d.treks.distance_km).toFixed(1)+' km'],['↗','Dénivelé cumulé',Math.round(d.treks.elevation_m)+' m'],['👁','Vues reçues',d.treks.views],['⭐','Favoris reçus',d.favorites_received],['💬','Commentaires reçus',d.comments_received],['🗺️','Plans préparés',d.plans],['⭐','Mes favoris',d.favorites]]}
      else{cards=[['🥾','Treks publics',d.treks],['👥','Créateurs',d.creators],['👤','Utilisateurs',d.users],['📏','Distance totale',Number(d.distance_km).toFixed(1)+' km'],['↗','Dénivelé cumulé',Math.round(d.elevation_m)+' m'],['👁','Vues',d.views],['⭐','Favoris',d.favorites],['💬','Commentaires',d.comments]]}
      c.style.gridTemplateColumns='repeat(auto-fit,minmax(130px,1fr))';c.innerHTML=cards.map(x=>`<div class="stat"><small>${x[0]} ${x[1]}</small><b>${x[2]}</b></div>`).join('')+(d.most_viewed?`<div class="stat" style="grid-column:1/-1"><small>🏆 Trek le plus vu</small><b>${String(d.most_viewed.name).replace(/[&<>'"]/g,'')} · ${d.most_viewed.views} vues</b></div>`:'');
    }catch(e){document.getElementById('stats-content').innerHTML='<div class="empty">Impossible de charger les statistiques.</div>'}
  };
  setupLargeTrekFilters();addStatsButton();setTimeout(addStatsButton,1000);
})();
</script>
"""

@app.get("/", include_in_schema=False)
def production_root():
    if not FRONTEND_FILE.exists(): return {"name":"TrekMap France","version":app.version,"status":"ok"}
    html=FRONTEND_FILE.read_text(encoding="utf-8").replace("</body>",UI_ENHANCEMENT+"</body>",1)
    return HTMLResponse(html,media_type="text/html")

# Remove the legacy security middleware installed by main.py.
app.user_middleware[:] = [m for m in app.user_middleware if getattr(getattr(m,"kwargs",{}).get("dispatch"),"__name__","")!="security_middleware"]
app.middleware_stack=None

@app.middleware("http")
async def production_security(request,call_next):
    if rate_limited(request): return JSONResponse({"detail":"Trop de requêtes. Réessaie dans un instant."},status_code=429)
    if IS_PRODUCTION:
        origin=request.headers.get("origin")
        if origin and origin.rstrip("/") not in FRONTEND_ORIGINS: return JSONResponse({"detail":"Origine non autorisée."},status_code=403)
    try: response=await call_next(request)
    except Exception:
        if IS_PRODUCTION: return JSONResponse({"detail":"Erreur interne du serveur."},status_code=500)
        raise
    response.headers["X-Content-Type-Options"]="nosniff";response.headers["X-Frame-Options"]="DENY";response.headers["Referrer-Policy"]="strict-origin-when-cross-origin";response.headers["Permissions-Policy"]="geolocation=(self), microphone=(), camera=()";response.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0";response.headers["X-TrekMap-Version"]="4.6.1"
    if IS_PRODUCTION: response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
    return response

app.version="4.6.1"
