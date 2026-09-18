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
<style>
/* TrekMap UI 2.0: couche visuelle injectée côté production sans toucher au front historique. */
:root{
  --green:#176b45;--green2:#269b69;--green3:#dff4e9;--ink:#14221c;--muted:#6c7b73;
  --line:#e1e9e4;--bg:#eef3f0;--card:#ffffff;--shadow:0 14px 40px rgba(17,48,34,.12);--shadow2:0 5px 18px rgba(17,48,34,.09)
}
body{background:linear-gradient(135deg,#eef5f1 0%,#f8faf9 48%,#edf3f0 100%);letter-spacing:-.01em}
.sidebar{width:390px;min-width:390px;border-right:1px solid rgba(210,223,216,.9);box-shadow:8px 0 35px rgba(18,43,31,.07);background:rgba(255,255,255,.96);backdrop-filter:blur(14px)}
.sidebar.collapsed{margin-left:-390px}
.brand{padding:22px 20px 16px;background:linear-gradient(145deg,#123f2b,#1b7950);color:white;position:relative;overflow:hidden}
.brand:after{content:"";position:absolute;width:170px;height:170px;border-radius:50%;right:-55px;top:-90px;background:rgba(255,255,255,.09);box-shadow:-75px 95px 0 15px rgba(255,255,255,.045)}
.brand h1{font-size:24px;letter-spacing:-.035em;position:relative;z-index:1}.brand small{color:rgba(255,255,255,.72);position:relative;z-index:1}
.account{margin:13px 15px 11px;padding:10px 11px;background:linear-gradient(135deg,#eff8f3,#f8fbf9);border:1px solid #dcebe2;border-radius:16px;box-shadow:0 3px 12px rgba(18,64,42,.04)}
.avatar{background:linear-gradient(145deg,var(--green),var(--green2));box-shadow:0 4px 12px rgba(23,107,69,.2)}
.account .ghost-btn{background:white;border:1px solid #dbe6e0;box-shadow:0 2px 7px rgba(0,0,0,.04)}
.search-wrap{margin:0 15px 11px}.search{border:1px solid #d5e1da;background:#fbfdfc;border-radius:14px;padding:14px 44px 14px 15px;box-shadow:inset 0 1px 2px rgba(20,50,35,.025);transition:.18s}
.search:focus{border-color:#5ba77f;box-shadow:0 0 0 4px rgba(38,155,105,.10),0 4px 15px rgba(23,107,69,.07);background:#fff}
.filters{padding:1px 15px 12px;border-bottom:1px solid #e8eeea;background:#fbfdfc}.filter-row{gap:9px}.field label{font-size:10px;text-transform:uppercase;letter-spacing:.055em;color:#718078;margin:8px 0 5px}.field select,.field input{border-color:#dce6e0;border-radius:10px;background:#fff;transition:.15s}.field select:focus{border-color:#65a985;outline:none;box-shadow:0 0 0 3px rgba(38,155,105,.08)}
.tabs{padding:10px 12px;background:#fff;gap:7px}.tab{background:#f0f4f2;border:1px solid transparent;transition:.15s}.tab:hover{background:#e7f0eb}.tab.active{background:linear-gradient(135deg,#176b45,#269b69);box-shadow:0 4px 12px rgba(23,107,69,.18)}
.list-head{padding:12px 16px 7px;background:#fff}.list-head b{font-size:13px;letter-spacing:.01em}.list-head span{background:#eef4f0;padding:4px 8px;border-radius:999px}
#trek-list{padding:6px 13px 100px;background:linear-gradient(180deg,#fff 0%,#f8fbf9 100%)}
.trek-card{border:1px solid #e2eae5;border-radius:17px;padding:14px;margin-bottom:10px;box-shadow:0 2px 7px rgba(24,56,41,.035);transition:transform .18s,box-shadow .18s,border-color .18s}
.trek-card:hover{transform:translateY(-2px);box-shadow:var(--shadow2);border-color:#bdd7c8}.trek-card.active{border-color:#54a279;box-shadow:0 0 0 2px rgba(38,155,105,.11),var(--shadow2)}
.trek-title strong{font-size:15px;line-height:1.25}.badges{margin:9px 0 8px}.badge{background:#edf6f1;color:#2c6049;border:1px solid #dfede5}.badge.private{background:#f3edff;border-color:#e8dcff}.badge.extreme{background:#fff0f0;border-color:#ffd9dc}.trek-meta{color:#64736b;font-size:11.5px}.card-actions{margin-top:10px}.card-actions button{border-radius:9px!important;border:1px solid #e0e8e3!important}
#map{background:#dfe9e4}.leaflet-container{font:inherit}.leaflet-control-zoom{border:0!important;box-shadow:var(--shadow2)!important}.leaflet-control-zoom a{border:0!important;color:#244d3a!important;background:rgba(255,255,255,.96)!important}.leaflet-control-attribution{background:rgba(255,255,255,.78)!important;backdrop-filter:blur(5px)}
.map-tools button,.map-tools select{border-color:#d9e4de;border-radius:12px;box-shadow:var(--shadow2);transition:.15s}.map-tools button:hover{transform:translateY(-1px);box-shadow:0 7px 20px rgba(0,0,0,.12)}
.draw-panel{border-color:#d8e7de;box-shadow:0 18px 50px rgba(16,48,33,.18)}.draw-actions .finish{background:linear-gradient(135deg,#176b45,#269b69);box-shadow:0 5px 14px rgba(23,107,69,.2)}
.map-legend{border:1px solid #e0e8e3;box-shadow:var(--shadow2);backdrop-filter:blur(8px)}
.bottom-nav{left:calc(390px + 18px);background:rgba(255,255,255,.91);backdrop-filter:blur(18px);border-color:#dce7e1;box-shadow:0 12px 35px rgba(18,45,32,.15);padding:6px;border-radius:18px}.bottom-nav button{transition:.15s}.bottom-nav button.active,.bottom-nav button:hover{background:#e8f4ed;color:#176b45;box-shadow:inset 0 0 0 1px #d8eadf}
.modal-backdrop{background:rgba(9,26,18,.55);backdrop-filter:blur(3px)}.modal{border:1px solid rgba(220,232,225,.9);box-shadow:0 30px 90px rgba(0,0,0,.27);border-radius:23px}.modal-head{padding-bottom:4px}.modal-head h2{letter-spacing:-.025em}.stat{background:linear-gradient(145deg,#f1f8f4,#f8fbf9);border:1px solid #dfebe4}.stat b{font-size:17px}.toast{border:1px solid rgba(255,255,255,.08);box-shadow:0 12px 35px rgba(0,0,0,.18)}
.suggestions{border-color:#dbe6e0;border-radius:14px}.suggestion{padding:11px 13px}.suggestion:hover{background:#edf7f1}
#trek-list::-webkit-scrollbar{width:8px}#trek-list::-webkit-scrollbar-track{background:transparent}#trek-list::-webkit-scrollbar-thumb{background:#cbd9d1;border-radius:20px;border:2px solid white}
input[type=range]{accent-color:#20865a}
@media(max-width:900px){.sidebar{width:min(410px,94vw);min-width:0}.sidebar.collapsed{margin-left:calc(-1 * min(410px,94vw))}.bottom-nav{left:10px;right:10px}.brand{padding-top:18px}.map-tools{max-width:calc(100% - 20px)}}
</style>
<script>
(function(){
  function setupLargeTrekFilters(){
    const d=document.getElementById('distance-range'),dt=document.getElementById('distance-tolerance'),e=document.getElementById('elevation-range'),et=document.getElementById('elevation-tolerance'),dur=document.getElementById('duration-filter');
    if(d){d.max='3000';d.step='5'} if(dt){dt.max='500';dt.step='5'} if(e){e.max='15000';e.step='50'} if(et){et.max='5000';et.step='50'}
    if(dur){const existing=new Set([...dur.options].map(o=>o.value));[[60,'≤ 60 jours'],[90,'≤ 90 jours'],[120,'≤ 120 jours'],[180,'≤ 180 jours'],[365,'≤ 365 jours']].forEach(([v,label])=>{if(!existing.has(String(v))){const o=document.createElement('option');o.value=v;o.textContent=label;dur.appendChild(o)}})}
  }
  function addStatsButton(){const nav=document.getElementById('bottom-nav');if(!nav||document.getElementById('stats-nav'))return;const b=document.createElement('button');b.id='stats-nav';b.innerHTML='📊 <span>Stats</span>';b.onclick=window.TrekMapOpenStats;nav.appendChild(b)}
  function polishInterface(){
    const sidebar=document.getElementById('sidebar');
    if(sidebar) sidebar.setAttribute('aria-label','Navigation TrekMap France');
    const search=document.getElementById('search');
    if(search) search.setAttribute('aria-label','Rechercher un trek');
    const list=document.getElementById('trek-list');
    if(list) list.setAttribute('aria-label','Liste des treks');
    const head=document.querySelector('.list-head');
    if(head && !document.getElementById('tm-status-dot')){
      const dot=document.createElement('span');dot.id='tm-status-dot';dot.title='TrekMap opérationnel';dot.style.cssText='display:inline-block;width:7px;height:7px;border-radius:50%;background:#31a56d;margin-right:5px;box-shadow:0 0 0 3px rgba(49,165,109,.12)';
      const counter=head.querySelector('span');if(counter) counter.prepend(dot);
    }
  }
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
  setupLargeTrekFilters();addStatsButton();polishInterface();setTimeout(function(){addStatsButton();polishInterface()},1000);
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
    response.headers["X-Content-Type-Options"]="nosniff";response.headers["X-Frame-Options"]="DENY";response.headers["Referrer-Policy"]="strict-origin-when-cross-origin";response.headers["Permissions-Policy"]="geolocation=(self), microphone=(), camera=()";response.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0";response.headers["X-TrekMap-Version"]="4.7.0"
    if IS_PRODUCTION: response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
    return response

app.version="4.7.0"

# Static assets used by the redesigned homepage and explorer UI.
from fastapi.responses import FileResponse

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

@app.get("/home.css", include_in_schema=False)
def production_home_css():
    return FileResponse(FRONTEND_DIR / "home.css", media_type="text/css")

@app.get("/remodel.css", include_in_schema=False)
def production_remodel_css():
    return FileResponse(FRONTEND_DIR / "remodel.css", media_type="text/css")

@app.get("/logo-trekmap.svg", include_in_schema=False)
def production_logo():
    return FileResponse(FRONTEND_DIR / "logo-trekmap.svg", media_type="image/svg+xml")

