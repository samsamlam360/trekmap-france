"""Phase 3 : GPS volontaire et fiche de parcours autonome, sans fausse promesse de fond de carte hors ligne."""
from pathlib import Path
import re
p=Path(__file__).resolve().parents[1]/"frontend"/"index.html"
html=p.read_text(encoding="utf-8")
html=re.sub(r"\s*<!-- TM_JOURNEY_PHASE3_START -->.*?<!-- TM_JOURNEY_PHASE3_END -->\s*","\n",html,flags=re.S)
for marker in ("TM_JOURNEY_PHASE2_START","TREKMAP_EXPLORER_FINISH_START"):
    if marker not in html:raise SystemExit("Phase 3 prerequisite missing: "+marker)
block=r'''<!-- TM_JOURNEY_PHASE3_START -->
<style id="tm-journey-terrain-style">
#tm-journey-gps-hud[hidden]{display:none!important}
#tm-journey-gps-hud{position:fixed;z-index:9400;bottom:22px;left:50%;
 transform:translateX(-50%);max-width:min(440px,calc(100vw - 20px));width:390px;
 border:1px solid #add0bb;border-radius:16px;background:#fff;color:#173f2e;
 box-shadow:0 12px 32px rgba(13,56,35,.25);padding:12px;display:flex;align-items:center;gap:12px}
#tm-journey-gps-status{flex:1;min-width:0;font-size:12px;line-height:1.55;overflow-wrap:anywhere}
#tm-journey-gps-status strong{display:block;font-size:13px}
#tm-journey-gps-stop{flex:none;border:1px solid #bdcec3;background:#ecf5ef;color:#14503a;
 border-radius:10px;padding:8px 12px;min-height:42px;font-weight:800}
#tm-journey-gps-hud button:focus-visible,#tm-offline-detail:focus-visible,#tm-gps-detail:focus-visible{outline:3px solid #d49b0c;outline-offset:2px}
@media(max-width:820px){
 #tm-journey-gps-hud{bottom:calc(84px + env(safe-area-inset-bottom,0px));width:calc(100vw - 20px)}
 #tm-offline-detail,#tm-gps-detail{min-height:44px}
}
</style>
<script id="tm-journey-terrain-js">
(function(){
 "use strict";
 if(window.TrekMapJourneyTerrain)return;
 var watchId=null,followId=null,marker=null,accuracyCircle=null,lastLoc=null,following=true;
 var currentCoords=[],hud=document.createElement('aside');
 hud.id='tm-journey-gps-hud';hud.hidden=true;hud.setAttribute('role','status');hud.setAttribute('aria-live','polite');
 var status=document.createElement('div');status.id='tm-journey-gps-status';
 var stopButton=document.createElement('button');stopButton.id='tm-journey-gps-stop';
 stopButton.type='button';stopButton.textContent='Arrêter';
 var centerButton=document.createElement('button');centerButton.id='tm-journey-gps-center';
 centerButton.type='button';centerButton.textContent='Centrer';centerButton.title='Recentrer la carte sur ma position GPS';
 hud.append(status,centerButton,stopButton);document.body.appendChild(hud);
 centerButton.addEventListener('click',function(){
   following=true;centerButton.textContent='Centrer';
   try{if(lastLoc&&typeof map!=='undefined'&&map)map.panTo(lastLoc,{animate:false})}catch(_){}
 });
 function coordsOf(t){
   var coords=t&&t.coords;
   if(!Array.isArray(coords)||coords.length<2||coords.length>50000)return [];
   if(!coords.every(function(p){return Array.isArray(p)&&p.length===2&&
      p.every(function(n){return n!==null&&n!==''&&typeof n!=='boolean'&&Number.isFinite(Number(n))})&&
      Math.abs(Number(p[0]))<=90&&Math.abs(Number(p[1]))<=180}))return [];
   return coords.map(function(p){return [Number(p[0]),Number(p[1])]});
 }
 function haversine(a,b){
   var r=Math.PI/180,dLat=(b[0]-a[0])*r,dLon=(b[1]-a[1])*r;
   var x=Math.sin(dLat/2)**2+Math.cos(a[0]*r)*Math.cos(b[0]*r)*Math.sin(dLon/2)**2;
   return 12742000*Math.atan2(Math.sqrt(x),Math.sqrt(Math.max(0,1-x)));
 }
 function nearestRoute(point,coords){
   if(coords.length<2)return null;
   var best={distance:Infinity,remaining:0},suffix=0,segments=[];
   var stride=Math.max(1,Math.ceil(coords.length/3000));
   var sampled=coords.filter(function(_,i){return i%stride===0});
   if(sampled[sampled.length-1]!==coords[coords.length-1])sampled.push(coords[coords.length-1]);
   for(var i=1;i<sampled.length;i++)segments.push(haversine(sampled[i-1],sampled[i]));
   for(var j=segments.length-1;j>=0;j--){
     var a=sampled[j],b=sampled[j+1],lat=point[0]*Math.PI/180;
     var ax=(a[1]-point[1])*Math.cos(lat)*111320,ay=(a[0]-point[0])*111320;
     var bx=(b[1]-point[1])*Math.cos(lat)*111320,by=(b[0]-point[0])*111320;
     var vx=bx-ax,vy=by-ay,den=vx*vx+vy*vy;
     var t=den?Math.max(0,Math.min(1,-(ax*vx+ay*vy)/den)):0;
     var dist=Math.hypot(ax+t*vx,ay+t*vy);
     if(dist<best.distance)best={distance:dist,remaining:suffix+(1-t)*segments[j],nextPoint:sampled[j+1]};
     suffix+=segments[j];
   }
   return best;
 }
 function notify(msg){if(typeof toast==='function')toast(msg)}
 function setStatus(title,info){
   status.replaceChildren();
   var head=document.createElement('strong');head.textContent=title;
   status.append(head,document.createTextNode(info||''));
 }
 function clearGPSLayer(){
   try{if(marker&&map?.hasLayer(marker))map.removeLayer(marker)}catch(_){}
   try{if(accuracyCircle&&map?.hasLayer(accuracyCircle))map.removeLayer(accuracyCircle)}catch(_){}
   marker=null;accuracyCircle=null;
 }
 function stop(){
   if(watchId!==null&&navigator.geolocation)navigator.geolocation.clearWatch(watchId);
   watchId=null;followId=null;currentCoords=[];lastLoc=null;following=true;centerButton.textContent='Centrer';clearGPSLayer();hud.hidden=true;
 }
 stopButton.addEventListener('click',stop);
 function onPosition(position){
   if(followId===null)return;
   var loc=[position.coords.latitude,position.coords.longitude];
   lastLoc=loc;
   if(!loc.every(Number.isFinite))return;
   var accuracy=Math.max(0,Number(position.coords.accuracy)||0);
   var target=nearestRoute(loc,currentCoords);
   if(!target)return;
   var tolerance=Math.max(100,accuracy*2);
   var away=target.distance>tolerance;
   var bearing=null;
   if(Array.isArray(target.nextPoint)&&target.nextPoint.length===2){
     var to=target.nextPoint,radians=Math.PI/180,dy=(to[1]-loc[1])*Math.cos(loc[0]*radians),dx=to[0]-loc[0];
     if(Math.abs(dy)+Math.abs(dx)>1e-8)bearing=(Math.atan2(dy,dx)*180/Math.PI+360)%360;
   }
   var cardinal=bearing===null?'':(['N','NE','E','SE','S','SO','O','NO'][Math.round(bearing/45)%8]);
   setStatus(accuracy>150?'Position GPS imprécise':away?'Écart possible du tracé':'Suivi GPS actif',
     'Distance au tracé ≈ '+Math.round(target.distance)+' m · Fin du tracé ≈ '+
       (target.remaining/1000).toFixed(1)+' km'+(accuracy>0?' · Précision GPS ≈ '+Math.round(accuracy)+' m':'')+
       (bearing!==null?' · Direction indicative du prochain segment : '+cardinal+' ('+Math.round(bearing)+'°)':'')+
       (away?' · Vérifie ta position sur une carte fiable, sans couper hors sentier.':'')+
       (accuracy>150?' · Écarte-toi des obstacles et vérifie la position.':''));
   try{
     if(typeof L==='undefined'||typeof map==='undefined'||!map)return;
     if(!marker)marker=L.circleMarker(loc,{radius:8,color:'#fff',weight:3,fillColor:'#0d7955',fillOpacity:1}).addTo(map);
     else marker.setLatLng(loc);
     if(!accuracyCircle)accuracyCircle=L.circle(loc,{radius:accuracy,color:'#268a61',weight:1,fillOpacity:.08}).addTo(map);
     else accuracyCircle.setLatLng(loc).setRadius(accuracy);
     if(window.innerWidth<=820&&following)map.panTo(loc,{animate:false});
   }catch(_){}
 }
 function start(t){
   var coords=coordsOf(t);
   if(coords.length<2){notify('Ce trek ne possède pas de tracé GPS exploitable.');return false}
   if(!window.isSecureContext||!navigator.geolocation){notify('GPS indisponible : HTTPS et autorisation de localisation sont nécessaires.');return false}
   stop();followId=Number(t.id);currentCoords=coords;
   try{
     if(typeof map!=='undefined'&&map&&!map._trekmapFollowBound){
       map._trekmapFollowBound=true;
       map.on('dragstart',function(){if(followId!==null){following=false;centerButton.textContent='Recentrer'}});
     }
   }catch(_){}
   hud.hidden=false;setStatus('Localisation en cours…','Autorise le GPS pour suivre ta position. Aucune position n’est transmise à TrekMap.');
   try{
     watchId=navigator.geolocation.watchPosition(onPosition,function(error){
       setStatus('GPS indisponible',error&&error.code===1?'Autorisation refusée. Arrête le suivi ou autorise la localisation.':'Impossible de déterminer la position. Réessaie à ciel ouvert.');
     },{enableHighAccuracy:true,maximumAge:10000,timeout:20000});
     return true;
   }catch(_){stop();notify('Impossible de lancer le GPS.');return false}
 }
 function escapeHTML(x){
   return String(x==null?'':x).replace(/[&<>"']/g,function(ch){
     return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];
   });
 }
 function offlineDocument(t){
   var coords=coordsOf(t);
   if(coords.length<2)throw Error('Aucune géométrie exploitable.');
   var stride=Math.max(1,Math.ceil(coords.length/2500));
   var route=coords.filter(function(_,i){return i%stride===0});
   if(route[route.length-1]!==coords[coords.length-1])route.push(coords[coords.length-1]);
   var latMin=Math.min(...route.map(function(p){return p[0]})),latMax=Math.max(...route.map(function(p){return p[0]}));
   var lonMin=Math.min(...route.map(function(p){return p[1]})),lonMax=Math.max(...route.map(function(p){return p[1]}));
   var lonFactor=Math.max(.01,Math.cos(((latMin+latMax)/2)*Math.PI/180));
   var dx=Math.max(.000001,(lonMax-lonMin)*lonFactor),dy=Math.max(.000001,latMax-latMin);
   var scale=340/Math.max(dx,dy);
   function xy(p){return [20+(p[1]-lonMin)*lonFactor*scale,380-(p[0]-latMin)*scale]}
   var points=route.map(function(p){var a=xy(p);return a[0].toFixed(1)+','+a[1].toFixed(1)}).join(' ');
   var a=xy(route[0]),b=xy(route[route.length-1]);
   var title=escapeHTML(t.name||'Trek'),region=escapeHTML(t.region||'France');
   var desc=escapeHTML(t.description||'Aucune description');
   var distance=Number.isFinite(Number(t.distance))&&t.distance!=null?Number(t.distance).toFixed(1)+' km':'Non renseignée';
   var days=Number.isFinite(Number(t.duration_days))&&t.duration_days!=null?String(t.duration_days)+' jours':'Non renseignée';
   return '<!doctype html><'+'html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+' · carnet hors connexion</title>'+
    '<style>body{font-family:system-ui;max-width:800px;margin:2rem auto;padding:0 1rem;color:#153e2b;background:#f4f8f5}main{background:white;border-radius:18px;padding:20px}svg{width:100%;height:auto;background:#e9f3ed;border:1px solid #bdd7c6;border-radius:12px}p{line-height:1.5}small{color:#5c6c62}</style></head><body><main>'+
    '<h1>'+title+'</h1><p>'+region+' · '+distance+' · '+escapeHTML(days)+'</p>'+
    '<h2>Tracé schématique, nord en haut</h2><svg viewBox="0 0 400 400" role="img" aria-label="Tracé géographique schématique sans fond topographique"><polyline fill="none" stroke="#146945" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" points="'+points+'"/>'+
    '<circle cx="'+a[0].toFixed(1)+'" cy="'+a[1].toFixed(1)+'" r="6" fill="#0976be"/><circle cx="'+b[0].toFixed(1)+'" cy="'+b[1].toFixed(1)+'" r="6" fill="#c64c33"/></svg>'+
    '<p><small>Bleu : départ · Rouge : arrivée. Document autonome sans connexion, ni fond IGN/OSM, ni guidage GPS. Il ne remplace pas une carte de terrain ou un GPX dans une application adaptée.</small></p>'+
    '<h2>Informations</h2><p>'+desc+'</p>'+
    '<h2>Coordonnées</h2><p>Départ : '+route[0].map(function(n){return n.toFixed(6)}).join(', ')+
    '<br>Arrivée : '+route[route.length-1].map(function(n){return n.toFixed(6)}).join(', ')+'</p>'+
    '<p><strong>Avant de partir :</strong> confirmer météo, eau potable, fermetures, nuitées et transports. Les informations peuvent évoluer.</p>'+
    '</main></'+'body></'+'html>';
 }
 function offline(t){
   try{
     var html=offlineDocument(t),blob=new Blob([html],{type:'text/html;charset=utf-8'});
     var url=URL.createObjectURL(blob),link=document.createElement('a');
     var filename=String(t.name||'trek').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').slice(0,60)||'trek';
     link.href=url;link.download=filename+'-hors-connexion.html';link.hidden=true;
     document.body.appendChild(link);try{link.click()}finally{link.remove();setTimeout(function(){URL.revokeObjectURL(url)},5000)}
     notify('Carnet téléchargé : tracé schématique hors connexion, sans fond de carte.');
     return true;
   }catch(e){notify(e.message||'Téléchargement hors connexion impossible.');return false}
 }
 function currentTrek(){
   try{return allTreks.find(function(t){return Number(t.id)===Number(currentDetail)})}catch(_){return null}
 }
 function enhanceDetail(){
   var actions=document.querySelector('#modal #export-detail')?.closest('.modal-actions');
   if(!actions||document.getElementById('tm-gps-detail'))return;
   var g=document.createElement('button');g.id='tm-gps-detail';g.type='button';g.className='ghost-btn';g.textContent='◎ Suivi GPS';
   var o=document.createElement('button');o.id='tm-offline-detail';o.type='button';o.className='ghost-btn';o.textContent='↓ Carnet hors connexion';
   g.addEventListener('click',function(){var t=currentTrek();if(t&&start(t))typeof closeModal==='function'&&closeModal()});
   o.addEventListener('click',function(){var t=currentTrek();if(t)offline(t)});
   actions.append(g,o);
 }
 var modal=document.getElementById('modal');
 if(modal)new MutationObserver(enhanceDetail).observe(modal,{childList:true,subtree:true});
 document.addEventListener('trekmap:detail-opened',function(e){
   if(followId!==null&&Number(e.detail?.id)!==followId)stop();
 });
 window.addEventListener('pagehide',stop);
 window.TrekMapJourneyTerrain={start:start,stop:stop,offline:offline,offlineDocument:offlineDocument,nearestRoute:nearestRoute};
 enhanceDetail();
})();
</script>
<!-- TM_JOURNEY_PHASE3_END -->'''
if html.count("</body>")!=1:raise SystemExit("Unexpected body marker")
p.write_text(html.replace("</body>",block+"\n</body>",1),encoding="utf-8")
print("Phase 3 : GPS volontaire et carnet graphique hors connexion")

from runpy import run_path
run_path(str(Path(__file__).with_name('apply_hiker_discovery.py')))
