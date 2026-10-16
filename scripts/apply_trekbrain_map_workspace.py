"""Responsive TrekBrain map workspace: replace exploration chrome, not hiking logic.

Installs after the TrekBrain planner, desktop UI, map and mobile navigation.
Only activate after an explicit user click on 'Voir sur la carte'.
Never change filtering data, routes, Neon, or provider budgets.
"""
from pathlib import Path
import re

path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
html = path.read_text(encoding="utf-8")
html = re.sub(
    r"\s*<!-- TREKMAP_BRAIN_ROUTE_WORKSPACE_START -->.*?<!-- TREKMAP_BRAIN_ROUTE_WORKSPACE_END -->\s*",
    "\n", html, flags=re.S,
)
for prerequisite in (
    "TREKMAP_UNIFIED_EXPERIENCE_START",
    "TREKMAP_MOBILE_EXPERIENCE_START",
    "TREKMAP_AI_EXPERIENCE_START",
    "TREKMAP_ROUTE_DAY_CLARITY_V94",
    "TREKMAP_TREKBRAIN_DESKTOP_2026_START",
):
    if prerequisite not in html:
        raise SystemExit("Missing prerequisite for TrekBrain map workspace: " + prerequisite)

block = r'''<!-- TREKMAP_BRAIN_ROUTE_WORKSPACE_START -->
<style id="trekbrain-route-workspace-css">
/* One temporary, reversible view for PC and phone. Never remove original DOM. */
#tm-brain-route-panel {display:none}
body.tm-brain-route-mode #sidebar,
body.tm-brain-route-mode #tm-unified-drawer,
body.tm-brain-route-mode .tm-route-day-legend {display:none!important}
body.tm-brain-route-mode #tm-brain-route-panel {
  position:fixed;
  z-index:3600;
  top:calc(var(--tm-top,76px) + 14px);
  left:14px;
  bottom:14px;
  width:var(--tm-panel,370px);
  min-width:0;
  max-height:calc(100dvh - var(--tm-top,76px) - 28px);
  display:flex;
  flex-direction:column;
  overflow:hidden;
  background:rgba(255,255,255,.985);
  border:1px solid #d1e1d7;
  border-radius:20px;
  box-shadow:0 16px 44px rgba(10,48,31,.18);
  color:#173e2d;
  font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
}
#tm-brain-route-panel * {box-sizing:border-box}
/* Keep the footer outside the scrolling content so it cannot cover controls. */
#tm-brain-route-panel .tm-brain-content {
  min-height:0;flex:1 1 auto;overflow-y:auto;
  overscroll-behavior:contain;scrollbar-width:thin;scroll-padding-block:12px;
}
#tm-brain-route-panel .tm-brain-head {
  flex:none;
  display:flex;
  align-items:flex-start;
  gap:12px;
  padding:18px 17px 10px;
}
#tm-brain-route-panel .tm-brain-titlewrap {min-width:0;flex:1}
#tm-brain-route-panel .tm-brain-kicker {
  display:block;color:#15704b;
  font-weight:850;letter-spacing:.07em;text-transform:uppercase;
  font-size:10px;line-height:1.5;margin-bottom:5px;
}
#tm-brain-route-panel h2 {
  font-size:20px;line-height:1.2;letter-spacing:-.035em;
  color:#153c2b;margin:0;overflow-wrap:anywhere;
}
#tm-brain-route-panel .tm-brain-exit {
  flex:none;min-height:42px;border-radius:11px;
  padding:9px 11px;border:1px solid #d4e4d9;
  color:#225c40;background:#f2f8f4;font-size:12px;font-weight:800;
}
#tm-brain-route-panel .tm-brain-overview {
  flex:none;padding:0 17px 13px;
}
#tm-brain-route-panel .tm-brain-location {
  font-size:12px;line-height:1.5;color:#576f60;margin:0 0 10px;
  overflow-wrap:anywhere;
}
#tm-brain-route-panel .tm-brain-metrics {
  display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;
}
#tm-brain-route-panel .tm-brain-metric {
  padding:11px 8px;background:#eff7f1;border:1px solid #e0eee4;
  border-radius:12px;text-align:center;min-width:0;
}
#tm-brain-route-panel .tm-brain-metric b {
  font-size:17px;font-weight:850;color:#164d36;display:block;line-height:1.2;
}
#tm-brain-route-panel .tm-brain-metric span {
  color:#557063;font-size:10px;display:block;margin-top:4px;line-height:1.4;
}
#tm-brain-route-panel .tm-brain-alert {
  padding:11px 12px;border-radius:12px;
  background:#fff8ed;border:1px solid #e6cba3;
  color:#674918;font-size:12px;line-height:1.55;
  margin:1px 17px 12px;flex:none;
}
#tm-brain-route-panel .tm-brain-alert b {font-weight:850}
#tm-brain-route-panel .tm-brain-alert p {margin:5px 0 0}
#tm-brain-route-panel .tm-brain-content>.tm-v9-readiness {margin:0 17px 12px;font-size:12px;padding:10px 12px}
#tm-brain-route-panel .tm-brain-content>.tm-v9-readiness h3 {font-size:16px}
#tm-brain-route-panel .tm-brain-content>.tm-v9-readiness li {margin:5px 0}
#tm-brain-route-panel .tm-brain-safe {
  padding:9px 12px;border-radius:11px;margin:1px 17px 12px;
  background:#eff7f3;border:1px solid #d8e9df;
  font-size:12px;line-height:1.5;color:#426450;
}
#tm-brain-route-panel .tm-brain-tools {
  flex:none;display:flex;gap:8px;flex-wrap:wrap;padding:0 17px 13px;
}
#tm-brain-route-panel .tm-brain-tools button {
  min-height:42px;border-radius:11px;padding:9px 11px;
  font-size:12px;font-weight:800;border:1px solid #cfe2d5;
  background:#f5faf7;color:#235b3e;
}
#tm-brain-route-panel .tm-brain-tools button[aria-pressed="true"] {
  background:#dff0e5;border-color:#74b38b;
}
#tm-brain-route-panel .tm-brain-detail {
  padding:14px 17px 16px;
  border-top:1px solid #e0eae3;
}
#tm-brain-route-panel .tm-brain-detail h3 {
  font-size:15px;margin:0 0 12px;color:#1f4c36;
}
#tm-brain-route-panel .tm-brain-stage {
  background:#fff;border:1px solid #dbe7df;border-left:4px solid #217ac2;
  border-radius:12px;padding:12px 12px 11px;
  margin-bottom:10px;box-shadow:0 2px 8px rgba(17,66,41,.04);
}
#tm-brain-route-panel .tm-brain-stage[data-day-color="1"] {border-left-color:#cc4343}
#tm-brain-route-panel .tm-brain-stage[data-day-color="2"] {border-left-color:#298347}
#tm-brain-route-panel .tm-brain-stage[data-day-color="3"] {border-left-color:#ed8c2f}
#tm-brain-route-panel .tm-brain-stage[data-day-color="4"] {border-left-color:#8555ad}
#tm-brain-route-panel .tm-brain-stage-head {
  display:flex;justify-content:space-between;align-items:center;gap:9px;
}
#tm-brain-route-panel .tm-brain-stage-head b {font-size:13px;color:#234b38}
#tm-brain-route-panel .tm-brain-stage-head span {font-size:12px;color:#42664f;font-weight:750}
#tm-brain-route-panel .tm-brain-stage p {
  font-size:12px;line-height:1.55;color:#4c6458;margin:6px 0 0;
}
#tm-brain-route-panel .tm-brain-extra {
  margin:12px 0 0;padding:11px 12px;
  border-radius:11px;border:1px solid #d7e8dc;
  font-size:12px;line-height:1.55;color:#506c5b;
}
#tm-brain-route-panel .tm-brain-extra b {color:#214a35}
#tm-brain-route-panel .tm-brain-extra p {margin:5px 0}
#tm-brain-route-panel .tm-brain-actions {
  flex:none;display:grid;grid-template-columns:1fr 1fr;gap:8px;
  padding:12px 17px 16px;border-top:1px solid #dce9df;
  background:#fbfdfb;
}
#tm-brain-route-panel .tm-brain-actions button {
  min-height:47px;border-radius:12px;padding:10px;
  background:#fff;color:#185b3c;
  border:1px solid #bad7c4;font-size:13px;font-weight:850;
}
#tm-brain-route-panel .tm-brain-actions .tm-brain-primary {
  background:#116b49;color:#fff;border-color:#116b49;
}
#tm-brain-route-panel button:focus-visible {
  outline:3px solid #e6a934!important;outline-offset:3px;
}
#tm-brain-route-panel .tm-brain-expand {display:none}
/* POI controls remain accessible on demand, and the true map markers persist. */
body.tm-brain-route-mode .tm-v91-legend {display:none!important}
body.tm-brain-route-mode.tm-brain-show-resources .tm-v91-legend {display:block!important}
@media(min-width:821px) and (max-width:1100px) {
  body.tm-brain-route-mode #tm-brain-route-panel {left:12px;width:var(--tm-panel,340px)}
}
@media(max-width:820px) {
  body.tm-brain-route-mode #tm-brain-route-panel {
    z-index:9100;
    left:9px;right:9px;top:auto;
    bottom:calc(var(--tm-mobile-nav-h,74px) + 15px + env(safe-area-inset-bottom,0px));
    width:auto;max-height:min(58dvh,570px);
    border-radius:18px;
    box-shadow:0 10px 42px rgba(8,45,28,.22);
  }
  #tm-brain-route-panel .tm-brain-head {padding:13px 13px 7px;gap:9px}
  #tm-brain-route-panel h2 {font-size:17px}
  #tm-brain-route-panel .tm-brain-exit {min-height:42px;padding:8px 10px}
  #tm-brain-route-panel .tm-brain-overview {padding:0 13px 10px}
  #tm-brain-route-panel .tm-brain-location {font-size:11px;margin-bottom:8px}
  #tm-brain-route-panel .tm-brain-metric {padding:7px 5px}
  #tm-brain-route-panel .tm-brain-metric b {font-size:15px}
  #tm-brain-route-panel .tm-brain-alert,
  #tm-brain-route-panel .tm-brain-safe {margin:0 13px 9px;padding:8px 10px}
  #tm-brain-route-panel .tm-brain-content>.tm-v9-readiness {margin:0 13px 9px;padding:8px 10px}
  #tm-brain-route-panel .tm-brain-tools {padding:0 13px 9px;gap:6px}
  #tm-brain-route-panel .tm-brain-tools button {min-height:40px;padding:7px 9px}
  #tm-brain-route-panel .tm-brain-actions {
    padding:9px 13px 12px;gap:8px;
    background:#fbfdfb;
  }
  #tm-brain-route-panel .tm-brain-actions button {min-height:46px}
  #tm-brain-route-panel .tm-brain-detail {padding:10px 13px}
  #tm-brain-route-panel .tm-brain-expand {display:block!important;flex:1}
  body.tm-brain-route-mode #tm-brain-route-panel:not(.expanded) .tm-brain-detail {display:none}
  body.tm-brain-route-mode #tm-brain-route-panel.expanded .tm-brain-detail {
    display:block;
  }
  body.tm-brain-route-mode.tm-brain-show-resources .leaflet-bottom.leaflet-right .tm-v91-legend {
    margin-bottom:calc(var(--tm-brain-sheet-height,220px) + var(--tm-mobile-nav-h,74px) + 31px + env(safe-area-inset-bottom,0px))!important;
    max-height:min(25dvh,210px)!important;
    max-width:min(215px,50vw)!important;
    overflow-y:auto!important;
  }
  body.tm-brain-route-mode .leaflet-popup-content-wrapper {max-height:48dvh}
}
@media(max-width:380px){
  #tm-brain-route-panel .tm-brain-kicker {font-size:9px}
  #tm-brain-route-panel h2 {font-size:15px}
  #tm-brain-route-panel .tm-brain-tools button {font-size:11px}
}
@media(prefers-reduced-motion:reduce){
  #tm-brain-route-panel * {scroll-behavior:auto!important;transition:none!important}
}
</style>
<script id="trekbrain-route-workspace-js">
(function(){
  "use strict";
  if(window.TrekBrainMapWorkspace)return;
  var body=document.body;
  var panel=document.createElement('aside');
  panel.id='tm-brain-route-panel';
  panel.setAttribute('role','complementary');
  panel.setAttribute('aria-label','TrekBrain : le parcours proposé');
  panel.hidden=true;
  document.body.appendChild(panel);
  var active=false,plan=null,expanded=false;
  var reducedMotion=function(){
    return !!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  };
  function mobile(){return window.innerWidth<=820;}
  function escapeText(value){
    return String(value==null?'':value).replace(/[&<>"']/g,function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function numeric(value,decimals){
    var n=Number(value);
    return value!==''&&value!=null&&Number.isFinite(n)&&n>=0?n.toFixed(decimals):'—';
  }
  function count(value){return Number.isFinite(Number(value))?Math.max(0,Math.trunc(Number(value))):0;}
  function formatSteps(value){
    var n=count(value);return n===1?'1 jour':n+' jours';
  }
  function unique(list){
    var values=[];
    list.forEach(function(x){
      var s=String(x||'').trim();
      if(s&&!values.includes(s))values.push(s);
    });
    return values;
  }
  function collectWarnings(p){
    var notices=[];
    var cover=p.map_resources?.coverage||{};
    var logistics=p.logistics||{};
    var route=p.route_preview||{};
    var dist=p.planner?.distance_contract;
    if(dist?.target_exceeded&&Array.isArray(dist.days_exceeding)){
      var days=dist.days_exceeding.map(function(row){return 'J'+row.day+' : '+row.distance_km+' km'});
      notices.push('Distance supérieure à l’objectif de '+dist.daily_target_km+
        ' km/jour ('+days.join(', ')+'). Vérifier les journées avant de partir.');
    }
    if(route.warning)notices.push('Tracé : '+route.warning);
    var rawCoords=Array.isArray(route.coords)?route.coords:[];
    if(rawCoords.length<2)notices.push('Le tracé pédestre n’est pas disponible.');
    var missingWater=Array.isArray(cover.days_without_water)?cover.days_without_water:[];
    var missingFood=Array.isArray(cover.days_without_food)?cover.days_without_food:[];
    if(missingWater.length)notices.push('Eau non vérifiée pour les jours '+missingWater.join(', ')+'.');
    else if(['not_verified','providers_unavailable'].includes(cover.water))notices.push('Aucune eau potable confirmée sur cet itinéraire.');
    if(missingFood.length)notices.push('Ravitaillement non vérifié pour les jours '+missingFood.join(', ')+'.');
    else if(['not_verified','providers_unavailable'].includes(cover.food))notices.push('Ravitaillement non confirmé sur cet itinéraire.');
    var nightsMissing=count(logistics.nights_missing);
    var nightsTransfer=count(logistics.nights_transfer_required);
    if(nightsMissing)notices.push(nightsMissing+' nuitée(s) restent sans hébergement identifié.');
    if(nightsTransfer)notices.push(nightsTransfer+' nuitée(s) nécessitent un transfert à organiser.');
    (p.stages||[]).forEach(function(stage){
      if(stage&&stage.safety_notes)notices.push('Jour '+(stage.day||'?')+' : '+stage.safety_notes);
    });
    (p.confidence?.limitations||[]).forEach(function(note){
      if(/sécurit|dang|interdit|fermetur|non potable|sans eau|absence d.eau|risqu|inaccessib|transfert/i.test(String(note)))notices.push(note);
    });
    return unique(notices);
  }
  function statusInfo(p){
    var c=p.map_resources?.coverage||{},l=p.logistics||{};
    var water=c.water==='complete'?'Points d’eau cartographiés, potabilité à contrôler'
      :Array.isArray(c.days_without_water)&&c.days_without_water.length?'Certains jours sans eau confirmée':'Eau à vérifier';
    var food=c.food==='complete'?'Ravitaillement cartographié'
      :Array.isArray(c.days_without_food)&&c.days_without_food.length?'Certains jours sans commerce confirmé':'Ravitaillement à vérifier';
    var nights=count(l.nights_missing)?count(l.nights_missing)+' nuitée(s) manquantes'
      :count(l.nights_transfer_required)?count(l.nights_transfer_required)+' transfert(s) à organiser'
      :l.walking_readiness==='ready_on_foot'?'Nuitées accessibles à pied repérées':'Nuitées à confirmer';
    return [water,food,nights];
  }
  function validCoords(p){
    var coords=p?.route_preview?.coords;
    return Array.isArray(coords)&&coords.length>=2&&coords.every(function(pt){
      if(!Array.isArray(pt)||pt.length!==2)return false;
      if(pt.some(function(v){return v===null||v===''||typeof v==='boolean';}))return false;
      return Number.isFinite(Number(pt[0]))&&Number.isFinite(Number(pt[1]))&&
        Math.abs(Number(pt[0]))<=90&&Math.abs(Number(pt[1]))<=180;
    })&&coords.some(function(pt,index){
      return index>0&&(Number(pt[0])!==Number(coords[0][0])||
        Number(pt[1])!==Number(coords[0][1]));
    });
  }
  function gpxEscape(value){
    return String(value==null?'':value)
      .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g,'')
      .replace(/[&<>"']/g,function(char){
        return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[char];
      });
  }
  function formatGPX(p){
    if(!p||!validCoords(p))throw new Error('Aucun tracé GPS exploitable à exporter.');
    if(p.route_preview.fallback!==false){
      throw new Error('Tracé pédestre non validé : export GPX bloqué pour éviter les lignes non praticables.');
    }
    var coords=p.route_preview.coords;
    if(coords.length>50000)throw new Error('Le tracé est trop volumineux pour cet export.');
    var name=gpxEscape(String(p.title||'Itinéraire TrekBrain').slice(0,160));
    var points=coords.map(function(point){
      return '<trkpt lat="'+Number(point[0]).toFixed(7)+
        '" lon="'+Number(point[1]).toFixed(7)+'"></trkpt>';
    });
    return '<?xml version="1.0" encoding="UTF-8"?>\n'+
      '<gpx version="1.1" creator="TrekMap France - TrekBrain" '+
      'xmlns="http://www.topografix.com/GPX/1/1">'+
      '<metadata><name>'+name+'</name></metadata>'+
      '<trk><name>'+name+'</name><trkseg>'+
      points.join('')+'</trkseg></trk></gpx>';
  }
  function exportGPX(){
    if(!active||!plan)return false;
    try{
      var gpx=formatGPX(plan);
      var title=String(plan.title||'trekbrain').normalize('NFKD')
        .replace(/[\u0300-\u036f]/g,'').toLowerCase()
        .replace(/[^a-z0-9-]+/g,'-').replace(/^-+|-+$/g,'').slice(0,64)||'trekbrain';
      var blob=new Blob([gpx],{type:'application/gpx+xml;charset=utf-8'});
      var url=URL.createObjectURL(blob);
      var link=document.createElement('a');
      link.href=url;link.download=title+'.gpx';
      link.setAttribute('aria-label','Télécharger le parcours GPX');
      link.hidden=true;document.body.appendChild(link);
      try{link.click();}
      finally{
        link.remove();
        setTimeout(function(){URL.revokeObjectURL(url);},5000);
      }
      if(typeof toast==='function')toast('Tracé GPX téléchargé. Les fonds de carte ne sont pas inclus.');
      return true;
    }catch(error){
      if(typeof toast==='function')toast(error.message||'Export GPX indisponible.');
      return false;
    }
  }
  function updatePanelHeight(){
    if(active){
      body.style.setProperty('--tm-brain-sheet-height',
        Math.round(panel.getBoundingClientRect().height)+'px');
    }
  }
  function syncExpanded(){
    panel.classList.toggle('expanded',expanded);
    var btn=panel.querySelector('[data-workspace-action="expand"]');
    if(btn){
      btn.setAttribute('aria-expanded',String(expanded));
      btn.textContent=expanded?'Replier les détails':'Voir les étapes et alertes';
    }
    updatePanelHeight();
  }
  function render(){
    if(!plan)return;
    var p=plan,route=p.route_preview||{};
    var stages=Array.isArray(p.stages)?p.stages:[];
    var days=count(p.duration_days||stages.length);
    var total=numeric(route.distance_km,1);
    var perDay=total!=='—'&&days>0?(Number(route.distance_km)/days).toFixed(1):'—';
    var warnings=collectWarnings(p);
    var statuses=statusInfo(p);
    var where=[p.start?.name,p.end?.name].filter(Boolean);
    var location=where.length===2?
      (where[0]===where[1]?'Boucle depuis '+where[0]:where[0]+' → '+where[1]):
      (p.region||'France');
    var parts=[];
    parts.push('<div class="tm-brain-head"><div class="tm-brain-titlewrap">'+
      '<span class="tm-brain-kicker">✦ TrekBrain · mon itinéraire</span>'+
      '<h2>'+escapeText(p.title||'Trek proposé')+'</h2></div>'+
      '<button type="button" class="tm-brain-exit" data-workspace-action="exit" aria-label="Quitter le trek proposé et revenir à Explorer">✕ Explorer</button></div>');
    parts.push('<div class="tm-brain-content">');
    if(window.TrekMapTripReadiness)parts.push(window.TrekMapTripReadiness.html(p));
    parts.push('<div class="tm-brain-overview"><p class="tm-brain-location">'+
      escapeText(location)+'</p><div class="tm-brain-metrics">'+
      '<div class="tm-brain-metric"><b>'+escapeText(days?formatSteps(days):'—')+'</b><span>Durée</span></div>'+
      '<div class="tm-brain-metric"><b>'+escapeText(total==='—'?'—':total+' km')+'</b><span>Distance totale</span></div>'+
      '<div class="tm-brain-metric"><b>'+escapeText(perDay==='—'?'—':perDay+' km')+'</b><span>Par jour</span></div></div></div>');
    if(warnings.length&&!window.TrekMapTripReadiness){
      parts.push('<div class="tm-brain-alert" role="note">'+
        '<b>⚠️ '+warnings.length+' point'+(warnings.length>1?'s':'')+' à vérifier</b>'+
        '<p>'+escapeText(warnings[0])+'</p>'+
        (warnings.length>1?'<small>Autres précautions dans les détails du trek.</small>':'')+'</div>');
    }else if(!window.TrekMapTripReadiness){
      parts.push('<div class="tm-brain-safe">Itinéraire à confirmer sur le terrain : météo, horaires et accès peuvent changer.</div>');
    }
    parts.push('<div class="tm-brain-tools">'+
      '<button type="button" data-workspace-action="fit">⌖ Recentrer le tracé</button>'+
      '<button type="button" data-workspace-action="gpx" title="Télécharger le tracé GPX pour une application GPS hors ligne">⬇ GPX</button>'+
      '<button type="button" data-workspace-action="resources" aria-pressed="'+
      String(body.classList.contains('tm-brain-show-resources'))+'">📍 Repères</button>'+
      '<button type="button" class="tm-brain-expand" data-workspace-action="expand" aria-controls="tm-brain-route-detail" aria-expanded="'+String(expanded)+'">'+
      (expanded?'Replier les détails':'Voir les étapes et alertes')+'</button></div>');
    parts.push('<div class="tm-brain-detail" id="tm-brain-route-detail"><h3>Étapes de la randonnée</h3>');
    if(stages.length){
      stages.slice(0,21).forEach(function(s,i){
        parts.push('<article class="tm-brain-stage" data-day-color="'+(i%5)+'">'+
          '<div class="tm-brain-stage-head"><b>Jour '+escapeText(s.day||i+1)+'</b>'+
          '<span>'+escapeText(numeric(s.distance_km,1))+' km · +'+
          escapeText(numeric(s.elevation_gain_m,0))+' m</span></div>'+
          '<p>'+escapeText([s.from_name,s.to_name].filter(Boolean).join(' → ')||s.title||'Étape proposée')+'</p>'+
          (s.overnight?'<p>🌙 '+escapeText(s.overnight)+'</p>':'')+
          (s.water_notes?'<p>💧 '+escapeText(s.water_notes)+'</p>':'')+
          (s.food_notes?'<p>🥖 '+escapeText(s.food_notes)+'</p>':'')+
          (s.safety_notes?'<p>⚠️ '+escapeText(s.safety_notes)+'</p>':'')+
          '</article>');
      });
    }else parts.push('<p>Les étapes ne sont pas détaillées pour ce parcours.</p>');
    parts.push('<div class="tm-brain-extra"><b>Ressources à vérifier</b>'+
      '<p>💧 '+escapeText(statuses[0])+'</p>'+
      '<p>🥖 '+escapeText(statuses[1])+'</p>'+
      '<p>🛏️ '+escapeText(statuses[2])+'</p></div>');
    var extraWarnings=window.TrekMapTripReadiness?warnings:warnings.slice(1);
    if(extraWarnings.length){
      parts.push('<div class="tm-brain-extra"><b>Autres précautions</b>'+
        extraWarnings.slice(0,15).map(function(note){return '<p>⚠️ '+escapeText(note)+'</p>';}).join('')+
        (extraWarnings.length>15?'<p>Consulter l’analyse détaillée pour toutes les limites.</p>':'')+
        '</div>');
    }
    parts.push('</div></div><div class="tm-brain-actions">'+
      '<button type="button" data-workspace-action="navigate">🥾 Mode randonnée</button>'+
      '<button type="button" data-workspace-action="modify">✏️ Modifier</button>'+
      '<button type="button" class="tm-brain-primary" data-workspace-action="save">✓ Enregistrer</button></div>');
    panel.innerHTML=parts.join('');
    window.TrekMapStageEdit?.renderNotes(p,panel);
    window.TrekMapTripReadiness?.bind(panel,p);
    syncExpanded();
  }
  function recenter(){
    if(!active||!plan||!validCoords(plan))return;
    try{
      if(typeof map==='undefined'||typeof L==='undefined')return;
      var rect=panel.getBoundingClientRect();
      var isPhone=mobile();
      var paddingLeft=isPhone?18:Math.ceil(rect.width+rect.left+22);
      var bottomPadding=isPhone?Math.min(window.innerHeight*.52,rect.height+108):60;
      var bounds=L.latLngBounds(plan.route_preview.coords);
      if(bounds.isValid()){
        map.invalidateSize();
        map.fitBounds(bounds.pad(.07),{
          paddingTopLeft:[paddingLeft,isPhone?90:70],
          paddingBottomRight:[22,Math.round(bottomPadding)],
          maxZoom:15,animate:!reducedMotion()
        });
      }
    }catch(_){}
  }
  function enter(p){
    if(!p||typeof p!=='object'||!validCoords(p))return false;
    plan=p;active=true;expanded=!mobile();previousMobile=mobile();
    body.classList.remove('tm-mobile-filters-open');
    body.classList.remove('tm-brain-show-resources');
    panel.hidden=false;
    render();
    body.classList.add('tm-brain-route-mode');
    syncExpanded();
    bindMap();
    setTimeout(recenter,230);
    return true;
  }
  function exit(){
    if(!active)return;
    active=false;plan=null;expanded=false;
    document.querySelectorAll('#tm-mobile-nav [data-mobile-action]').forEach(function(button){
      button.classList.toggle('active',button.dataset.mobileAction==='explore');
    });
    body.classList.remove('tm-brain-route-mode','tm-brain-show-resources');
    body.style.removeProperty('--tm-brain-sheet-height');
    panel.hidden=true;panel.innerHTML='';
    // Fermer le panneau enlève réellement TOUT l'aperçu IA de la carte,
    // sans retirer le tracé sélectionné ou les treks enregistrés.
    window.TrekMapClearAIPreview?.();
    window.TrekMapClearAIRoute?.();
    window.TrekMapClearAIResources?.();
    try{if(typeof map!=='undefined')map.invalidateSize();}catch(_){}
  }
  function mapMaybe(){
    try{return typeof map!=='undefined'&&map&&typeof map.on==='function'?map:null;}catch(_){return null}
  }
  function bindMap(){
    var instance=mapMaybe();
    if(!instance||instance._trekBrainWorkspaceBound)return;
    instance._trekBrainWorkspaceBound=true;
    instance.on('movestart',function(){
      if(active&&mobile()&&expanded){
        expanded=false;syncExpanded();
      }
    });
    instance.on('popupopen',function(e){
      if(!active||!mobile()||!e?.popup?.getLatLng||!instance.panInside)return;
      if(expanded){expanded=false;syncExpanded();}
      var height=panel.getBoundingClientRect().height;
      try{
        instance.panInside(e.popup.getLatLng(),{
          paddingTopLeft:[18,80],
          paddingBottomRight:[18,Math.round(Math.min(window.innerHeight*.49,height+100))]
        });
      }catch(_){}
    });
  }
  function makeAction(ev){
    var button=ev.target.closest?.('[data-workspace-action]');
    if(!button||!active)return;
    var action=button.dataset.workspaceAction;
    if(action==='exit')exit();
    else if(action==='fit')recenter();
    else if(action==='gpx')exportGPX();
    else if(action==='expand'){expanded=!expanded;syncExpanded();}
    else if(action==='resources'){
      var show=!body.classList.contains('tm-brain-show-resources');
      body.classList.toggle('tm-brain-show-resources',show);
      button.setAttribute('aria-pressed',String(show));
    }
    else if(action==='navigate'){
      var route=plan&&plan.route_preview;
      if(!route||!Array.isArray(route.coords))return;
      var coords=route.coords;
      var data={id:'brain-'+String(plan.title||'trekbrain').slice(0,32),
        name:plan.title||'TrekBrain',region:plan.region||'',coords:coords};
      window.TrekMapHikingNavigation?.open(data);
    }
    else if(action==='modify'){
      if(window.TrekMapTripReadiness)window.TrekMapTripReadiness.edit(plan);
      else window.TrekMapOpenAI?.();
    }
    else if(action==='save'){
      var original=document.getElementById('tm-ai-save');
      if(original){
        if(!original.disabled)original.click();
      }else{
        window.TrekMapOpenAI?.();
      }
    }
  }
  panel.addEventListener('click',makeAction);
  /* Switching to normal explorer operations always restores filters/drawer. */
  document.addEventListener('click',function(ev){
    if(!active)return;
    var element=ev.target;
    if(!element||!element.closest)return;
    var back=element.closest(
      '#tm-brand,#tm-import-btn,#tm-create-btn,#tm-favorites-btn,'+
      '#tm-drawer-track .tm-trek-tile,#tm-filter-toggle,'+
      '#tm-mobile-nav [data-mobile-action="explore"],'+
      '#tm-mobile-nav [data-mobile-action="filters"],'+
      '#tm-mobile-nav [data-mobile-action="favorites"],'+
      '#tm-mobile-nav [data-mobile-action="profile"],'+
      '#tm-mobile-nav [data-mobile-action="draw"]'
    );
    if(back)exit();
  },true);
  var search=document.getElementById('tm-main-search');
  if(search)search.addEventListener('focus',function(){if(active)exit()});
  /* Saving a TrekBrain route opens a saved trek: do not leave the AI panel up. */
  var oldOpen=window.TrekMapOpenTrek;
  if(typeof oldOpen==='function'&&!oldOpen._brainWorkspaceWrapped){
    window.TrekMapOpenTrek=function(){exit();return oldOpen.apply(this,arguments)};
    window.TrekMapOpenTrek._brainWorkspaceWrapped=true;
  }
  var resizeTimer,previousMobile=mobile();
  window.addEventListener('resize',function(){
    if(!active)return;
    clearTimeout(resizeTimer);
    resizeTimer=setTimeout(function(){
      // A small viewport resize (browser chrome, scrollbars, keyboard) must
      // never overwrite the user's expanded/collapsed stage preference.
      var nowMobile=mobile();
      if(nowMobile!==previousMobile)expanded=!nowMobile;
      previousMobile=nowMobile;
      syncExpanded();recenter();
    },120);
  },{passive:true});
  if(typeof ResizeObserver==='function'){
    new ResizeObserver(updatePanelHeight).observe(panel);
  }
  window.TrekBrainMapWorkspace={
    open:enter,exit:exit,recenter:recenter,
    exportGPX:exportGPX,
    getPlan:function(){return active?plan:null;},
    isActive:function(){return active;}
  };
})();
</script>
<!-- TREKMAP_BRAIN_ROUTE_WORKSPACE_END -->'''

if html.count("</body>") != 1:
    raise SystemExit("Unexpected closing body marker")
html=html.replace("</body>",block+"\n</body>",1)
path.write_text(html,encoding="utf-8")
print("TrekBrain map workspace: desktop sidebar and mobile expandable sheet installed")

# Installed last by every Render/CI build; preserves existing TrekBrain map logic.
from runpy import run_path
run_path(str(Path(__file__).with_name("apply_sitewide_ux.py")))
