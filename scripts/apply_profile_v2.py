"""Install a standalone, accessible personal hiking profile after the existing site UI.

Original account, passwords, TrekBrain, saved routes and mobile flows stay intact.
"""
from pathlib import Path
import re

path=Path(__file__).resolve().parents[1]/"frontend"/"index.html"
html=path.read_text(encoding="utf-8")
html=re.sub(r"\s*<!-- TREKMAP_PROFILE_V2_START -->.*?<!-- TREKMAP_PROFILE_V2_END -->\s*","\n",html,flags=re.S)
for k in ("TREKMAP_UNIFIED_EXPERIENCE_START","TREKMAP_SITEWIDE_UX_START"):
    if k not in html:
        raise SystemExit("Missing UI prerequisite: "+k)
block=r'''<!-- TREKMAP_PROFILE_V2_START -->
<style id="tm-profile-v2-style">
#tm-profile-v2[hidden]{display:none!important}
#tm-profile-v2{position:fixed;inset:0;z-index:18000;background:#f3f8f5;color:#153b2b;
  font-family:inherit;overflow-y:auto;overscroll-behavior:contain}
#tm-profile-v2 *{box-sizing:border-box}
.tm-p-shell{max-width:1370px;margin:0 auto;min-height:100dvh;display:grid;grid-template-columns:240px minmax(0,1fr);gap:22px;padding:20px}
.tm-p-nav{position:sticky;top:20px;align-self:start;background:#0c4b36;color:#e6f8ef;border-radius:22px;padding:22px 14px;min-height:calc(100dvh - 40px)}
.tm-p-brand{display:flex;align-items:center;gap:10px;font-weight:900;font-size:20px;margin:4px 8px 25px}
.tm-p-brand img{width:32px;height:38px}
.tm-p-nav button{width:100%;text-align:left;display:flex;gap:10px;align-items:center;padding:12px 14px;margin-bottom:4px;background:transparent;color:#d9eee2;border:1px solid transparent;border-radius:12px;font-size:13px;font-weight:750;min-height:44px}
.tm-p-nav button:hover,.tm-p-nav button.active{background:rgba(228,252,234,.15);border-color:rgba(230,255,241,.18);color:#fff}
.tm-p-nav .tm-p-exit{margin-top:27px;background:#e9f8ed;color:#12573d;justify-content:center}
.tm-p-main{min-width:0}
.tm-p-hero{display:flex;align-items:center;gap:18px;background:linear-gradient(115deg,#11583c,#238160);
  border-radius:20px;padding:25px 29px;color:#fff;min-height:140px}
.tm-p-avatar{flex:0 0 auto;width:74px;height:74px;border-radius:22px;display:grid;place-items:center;
  background:#e9f7ed;color:#126143;font-size:38px;border:2px solid rgba(255,255,255,.7)}
.tm-p-hero h1{font-size:clamp(21px,2.3vw,32px);margin:0 0 5px}
.tm-p-hero p{margin:0;color:#e3f2e9;font-size:13px;line-height:1.5}
.tm-p-banner{font-size:11px;color:#e3f7e8;margin-top:8px}
.tm-p-content{padding:24px 0 45px}
.tm-p-heading{font-size:21px;margin:0 0 16px;font-weight:900}
.tm-p-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:20px}
.tm-p-card{background:#fff;border:1px solid #dce9df;border-radius:17px;padding:19px;min-width:0;
  box-shadow:0 4px 14px rgba(15,73,43,.035)}
.tm-p-metric strong{display:block;font-size:26px;color:#106646;font-variant-numeric:tabular-nums}
.tm-p-metric span{display:block;font-size:12px;color:#60806b;margin-top:4px}
.tm-p-cols{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(240px,1fr);gap:16px}
.tm-p-card h3{font-size:16px;margin:0 0 14px;color:#173e2c}
.tm-p-muted{color:#668170;font-size:12px;line-height:1.55}
.tm-p-list{display:grid;gap:9px}
.tm-p-item{width:100%;min-width:0;text-align:left;padding:12px;border-radius:12px;border:1px solid #dfece1;
  background:#fbfdfb;display:flex;align-items:center;justify-content:space-between;gap:12px}
.tm-p-item:hover{background:#edf7f1;border-color:#7dbca0}
.tm-p-project-row.is-selected .tm-p-item,.tm-p-item.is-selected,.tm-p-collection-entry[aria-pressed="true"]{
  border-color:#148052;background:#e8f6ee;box-shadow:inset 3px 0 #148052
}
.tm-p-collection-entry{cursor:pointer;font:inherit}
.tm-p-collection-entry:focus-visible{outline:3px solid #ecb747!important;outline-offset:2px}
.tm-p-section-label{font-size:12px;font-weight:850;color:#245f42;margin:15px 0 9px}
.tm-p-item .tm-p-inline{justify-content:flex-end;gap:6px}
.tm-p-item .tm-p-inline .tm-p-btn{min-height:36px;padding:7px 9px}
#tm-p-journey-card,#tm-p-collection-content{scroll-margin-top:85px}
@media(max-width:780px){#tm-p-journey-card,#tm-p-collection-content{scroll-margin-top:72px}}

.tm-p-item b{display:block;font-size:13px;color:#1b4a34}
.tm-p-item small{font-size:11px;color:#668070;display:block;margin-top:3px}
.tm-p-pill{background:#e6f4ec;border-radius:50px;color:#1b7551;padding:5px 8px;white-space:nowrap;font-size:10px}
.tm-p-section{margin-bottom:16px}
.tm-p-btn{border:1px solid #bcdbca;background:#eaf5ed;color:#135b3c;border-radius:11px;
  min-height:42px;padding:8px 13px;font-weight:800;font-size:12px}
.tm-p-btn:hover{background:#d9efdf}
.tm-p-btn.primary{background:#137b52;color:white;border-color:#137b52}
.tm-p-btn.danger{background:#fff1f1;color:#a62f32;border-color:#f1c6c6}
.tm-p-inline{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.tm-p-form{display:grid;gap:12px}
.tm-p-form label{display:grid;gap:6px;font-size:12px;font-weight:750;color:#365d46}
.tm-p-form :is(input,textarea,select){width:100%;padding:10px 11px;border:1px solid #bbd6c4;
  border-radius:11px;background:#fff;color:#153b2b;min-height:42px;font:inherit;font-size:13px}
.tm-p-form textarea{resize:vertical;min-height:75px}
.tm-p-form input[type=checkbox]{width:auto;min-height:auto;margin:0 8px 0 0;accent-color:#128359}
.tm-p-form .tm-p-check{display:flex;align-items:center;font-weight:550}
.tm-p-form .tm-p-two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}
.tm-p-form .tm-p-two[hidden]{display:none!important}
.tm-p-card .tm-p-save-msg{margin-top:8px;font-size:12px;color:#155f40}
.tm-p-callout{background:#edf7ef;border:1px solid #cfe5d3;padding:12px 14px;border-radius:12px;
  color:#416b52;font-size:12px;line-height:1.5;margin:12px 0}
.tm-p-checkline{display:flex;align-items:center;gap:9px;min-height:46px;padding:5px 0;border-bottom:1px solid #e9f0ea;min-width:0}
.tm-p-checkline input[type=checkbox]{accent-color:#14885d;width:20px;height:20px;flex:none;cursor:pointer}
.tm-p-checkline input[type=text]{min-width:0;flex:1;width:auto;padding:10px 11px;min-height:44px;border-radius:9px;border:1px solid #bad5c5;background:#fff;color:#16462f;font:inherit;font-size:14px;box-sizing:border-box}
.tm-p-checkline button{min-height:44px;min-width:44px;flex:none;border:1px solid #d8e6dc;border-radius:9px;background:#fff;color:#9e3030;cursor:pointer;font-size:19px}
.tm-p-checkline :is(input,button):focus-visible{outline:3px solid #d7a11c;outline-offset:2px}
.tm-p-badges{display:flex;gap:8px;flex-wrap:wrap}
.tm-p-badges span{border:1px solid #cce6d4;background:#eaf8ed;color:#226e4c;
  padding:9px 12px;border-radius:10px;font-size:12px}
.tm-p-photos{display:flex;flex-wrap:wrap;gap:7px}
.tm-p-photos a{font-size:12px;color:#176c4d;text-decoration:underline}
.tm-p-photos img{display:block;width:105px;height:80px;object-fit:cover;border-radius:10px;border:1px solid #c7ddcd}
.tm-p-local-photo{display:flex;align-items:center;gap:10px;min-height:60px;padding:9px;border:1px dashed #a8cfb5;border-radius:12px;background:#f3f9f5;color:#557462;font-size:12px}
.tm-p-local-photo img{width:108px;height:85px;object-fit:cover;border-radius:9px}
.tm-p-form input[type=file]{padding:9px;background:#f8fbf9}
.tm-p-form input[type=file]::file-selector-button{border:0;border-radius:8px;padding:8px;margin-right:10px;background:#e1f2e8;color:#176b45;font-weight:800}
.tm-p-close-mobile{display:none}
#tm-profile-v2 :is(button,input,textarea,select,a):focus-visible{outline:3px solid #ecb747!important;outline-offset:2px}
@media(max-width:1050px){.tm-p-shell{grid-template-columns:200px 1fr;gap:12px;padding:12px}
  .tm-p-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.tm-p-cols{grid-template-columns:1fr}
  .tm-p-nav{padding:14px 8px}}
@media(max-width:780px){
  .tm-p-shell{display:block;padding:0 12px 24px}
  /* Android status bar: keep profile controls below system icons even in edge-to-edge WebView. */
  .tm-p-nav{position:sticky;top:0;z-index:3;border-radius:0 0 15px 15px;min-height:0;
    padding:max(48px, calc(env(safe-area-inset-top, 0px) + 12px)) 9px 12px;
    display:flex;align-items:center;gap:8px;overflow-x:auto;overflow-y:hidden;
    -webkit-overflow-scrolling:touch;scrollbar-width:thin;touch-action:pan-x;scroll-padding-inline:12px}
  .tm-p-nav .tm-p-brand{display:none}
  .tm-p-nav button{width:auto;white-space:nowrap;flex:0 0 auto;font-size:13px;margin:0;padding:11px 14px;min-height:48px;touch-action:manipulation}
  .tm-p-nav .tm-p-exit{margin:0}
  .tm-p-hero{margin-top:12px;border-radius:16px;padding:18px;gap:11px;min-height:110px}
  .tm-p-avatar{width:56px;height:56px;font-size:30px;border-radius:16px}
  .tm-p-content{padding:15px 0 35px}
  .tm-p-grid{gap:8px}.tm-p-card{padding:13px;border-radius:13px}
  .tm-p-metric strong{font-size:22px}
  .tm-p-form .tm-p-two{grid-template-columns:1fr}
}
@media(prefers-reduced-motion:reduce){#tm-profile-v2 *{scroll-behavior:auto!important;transition:none!important}}
</style>
<div id="tm-profile-v2" hidden aria-label="Mon espace randonnée">
  <div class="tm-p-shell">
    <nav class="tm-p-nav" aria-label="Rubriques du profil">
      <div class="tm-p-brand"><img src="/brand-pin.svg" alt=""> TrekMap</div>
      <button type="button" data-p-tab="home" class="active">⌂ Tableau de bord</button>
      <button type="button" data-p-tab="projects">⌖ Mes aventures</button>
      <button type="button" data-p-tab="downloads">⬇ Treks téléchargés</button>
      <button type="button" data-p-tab="journal">▤ Carnet</button>
      <button type="button" data-p-tab="collections">♡ Collections</button>
      <button type="button" data-p-tab="preferences">⚙ Préférences</button>
      <button type="button" id="tm-p-exit" class="tm-p-exit">← Revenir à la carte</button>
    </nav>
    <main class="tm-p-main"><section id="tm-p-hero" class="tm-p-hero"></section>
    <section id="tm-p-content" class="tm-p-content" aria-live="polite"></section></main>
  </div>
</div>
<script id="tm-profile-v2-script">
(function(){
'use strict';
const root=document.getElementById('tm-profile-v2');
if(!root)return;
const content=root.querySelector('#tm-p-content'),hero=root.querySelector('#tm-p-hero');
const avatarIcons={mountain:'⛰',compass:'◈',tent:'⛺',forest:'♣',hiker:'♙'};
const statusNames={planned:'À découvrir',preparing:'En préparation',ready:'Prêt',completed:'Terminé'};
let model=null,tab='home',selected=null,plan=null,profileLoading=false;
 let downloadedRoutes=[],downloadStatus='loading';
let previousFocus=null;
function e(s){return String(s==null?'':s).replace(/[&<>'"]/g,function(x){return {'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[x]})}
function el(id){return root.querySelector('#'+id)}
function num(v){return Number.isFinite(Number(v))?Number(v):0}
function announce(s){if(typeof toast==='function')toast(s)}
async function api(path,method,body){
  const h=(typeof headers==='function')?headers(method&&method!=='GET'?{'Content-Type':'application/json'}:{},method||'GET'):{'Content-Type':'application/json'};
  const r=await fetch('/profile/'+path,{method:method||'GET',headers:h,credentials:'include',body:body==null?undefined:JSON.stringify(body),cache:'no-store'});
  const d=await r.json().catch(function(){return {}});
  if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Opération indisponible ('+r.status+')');
  return d;
}
async function request(path,method,body){
  const h=(typeof headers==='function')?headers(method&&method!=='GET'?{'Content-Type':'application/json'}:{},method||'GET'):{'Content-Type':'application/json'};
  const r=await fetch(path,{method:method||'GET',headers:h,credentials:'include',body:body==null?undefined:JSON.stringify(body),cache:'no-store'});
  const d=await r.json().catch(function(){return {}});
  if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Opération indisponible ('+r.status+')');
  return d;
}
const accountTreks=function(){
  if(!model)return[];
  const m=new Map();
  (model.treks||[]).concat(model.favorites||[])
    .concat((model.journeys||[]).map(function(j){return {id:j.trek_id,name:j.name,region:j.region,distance:j.distance,elevation:j.elevation,is_public:j.is_public}}))
    .concat((model.collections||[]).flatMap(function(collection){return collection.treks||[]}))
    .forEach(function(t){
      const id=Number(t.id);
      if(!Number.isSafeInteger(id)||id<=0)return;
      const previous=m.get(id)||{};
      // Collection entries contain only id/name/region, never discard the
      // richer distance, ascent or ownership information from actual treks.
      m.set(id,{...previous,...t,
        distance:t.distance==null?previous.distance:t.distance,
        elevation:t.elevation==null?previous.elevation:t.elevation});
    });
  return [...m.values()];
};
function journey(id){return (model&&model.journeys||[]).find(function(j){return Number(j.trek_id)===Number(id)})}
/* Photo locale compressée sur le téléphone ou PC avant sauvegarde privée. */
async function localPhotoData(file){
 if(!file)throw Error('Choisis une image.');
 if(!/^image\/(jpeg|png|webp|heic|heif)$/i.test(file.type))throw Error('Choisis une image JPG, PNG, WebP ou HEIC.');
 if(file.size>12*1024*1024)throw Error('Photo trop volumineuse (12 Mo maximum avant compression).');
 const objectUrl=URL.createObjectURL(file);
 let image;
 try{
  image=await new Promise(function(resolve,reject){
   const im=new Image();
   im.onload=function(){resolve(im)};
   im.onerror=function(){reject(Error('Ce format d’image n’est pas pris en charge par ton navigateur. Utilise JPG ou PNG.'))};
   im.src=objectUrl;
  });
 }finally{URL.revokeObjectURL(objectUrl)}
 if(!image.naturalWidth||!image.naturalHeight)throw Error('Image illisible.');
 for(const limit of [960,800,680,540,420]){
  const ratio=Math.min(1,limit/Math.max(image.naturalWidth,image.naturalHeight));
  const canvas=document.createElement('canvas');
  canvas.width=Math.max(1,Math.round(image.naturalWidth*ratio));
  canvas.height=Math.max(1,Math.round(image.naturalHeight*ratio));
  const ctx=canvas.getContext('2d');
  if(!ctx)throw Error('Compression de la photo indisponible.');
  ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.drawImage(image,0,0,canvas.width,canvas.height);
  for(const quality of [.8,.68,.54]){
   const data=canvas.toDataURL('image/jpeg',quality);
   if(data.startsWith('data:image/jpeg;base64,')&&data.length<=130000)return data;
  }
 }
 throw Error('Photo trop détaillée pour le stockage gratuit. Essaie une autre image.');
}
function card(t,actions){
  return '<div class="tm-p-item"><div><b>'+e(t.name)+'</b><small>'+e(t.region||'France')+' · '+num(t.distance).toFixed(1)+' km</small></div>'+
    (actions||'<button class="tm-p-btn" data-p-select="'+Number(t.id)+'">Gérer</button>')+'</div>';
}
function resetAfterUpdate(next){
  model=next;render();
}
function load(){
  return api('v2').then(function(x){model=x;return x});
}
function nav(){
  root.querySelectorAll('[data-p-tab]').forEach(function(b){b.classList.toggle('active',b.dataset.pTab===tab);b.setAttribute('aria-current',b.dataset.pTab===tab?'page':'false')});
  const active=root.querySelector('[data-p-tab].active');if(active&&tab!=='home')active.scrollIntoView({inline:'nearest',block:'nearest'});
}
function head(){
  if(!model){hero.innerHTML='<div>Chargement du profil…</div>';return}
  const s=model.settings||{},u=model.user||{},isPublic=s.public_profile===true;
  hero.innerHTML='<div class="tm-p-avatar" aria-hidden="true">'+(avatarIcons[s.avatar]||'⛰')+'</div><div>'+
    '<h1>'+e(u.username)+'</h1><p>'+e(s.bio||'Ton espace personnel pour découvrir et préparer tes randonnées.')+'</p>'+
    '<div class="tm-p-banner">'+(isPublic?'Profil public activé':'Profil privé · visible par toi uniquement')+'</div></div>';
}
function home(){
  const s=model.stats||{},unfinished=(model.journeys||[]).filter(function(j){return j.status!=='completed'}).slice(0,5);
  const recent=model.treks.slice(0,5);
  let metrics=[['Mes treks',s.total],['Mes favoris',s.favorites],['Sorties effectuées',s.completed],['Km réellement parcourus',s.actual_km]];
  return '<h2 class="tm-p-heading">Tableau de bord</h2><div class="tm-p-grid">'+metrics.map(function(m){
     return '<div class="tm-p-card tm-p-metric"><strong>'+e(m[1])+'</strong><span>'+e(m[0])+'</span></div>'
  }).join('')+'</div><div class="tm-p-cols"><div class="tm-p-card"><h3>Mes prochaines aventures</h3><div class="tm-p-list">'+
  (unfinished.length?unfinished.map(function(j){return card({id:j.trek_id,name:j.name,region:j.region,distance:j.distance})}).join(''):
    '<p class="tm-p-muted">Aucun projet suivi pour le moment. Ouvre « Mes aventures » pour commencer.</p>')+
  '</div><div style="margin-top:12px"><button class="tm-p-btn primary" data-p-go="projects">Organiser mes treks</button></div></div>'+
  '<div class="tm-p-card"><h3>Mes treks récents</h3><div class="tm-p-list">'+
  (recent.length?recent.map(function(t){return card(t)}).join(''):'<p class="tm-p-muted">Aucun trek créé pour le moment.</p>')+
  '</div><div class="tm-p-callout">Les statistiques de marche ne comptent que les sorties que tu as réellement marquées « Terminées ».</div></div></div>';
}
function projects(){
  const treks=accountTreks();
  const ownedIds=new Set((model.treks||[]).map(function(t){return Number(t.id)}));
  const favoriteIds=new Set((model.favorites||[]).map(function(t){return Number(t.id)}));
  const current=selected!=null?treks.find(function(t){return Number(t.id)===Number(selected)}):null;
  const j=current?journey(current.id):null;
  const photos=j&&j.photo_urls||[];
  const localPhoto=photos.find(function(u){return /^data:image\/(jpeg|webp);base64,/.test(u)})||'';
  const photoLinks=photos.filter(function(u){return /^https:\/\//.test(u)});
  const st=j&&j.status||'planned';
  let panel='';
  if(current){
    panel='<div id="tm-p-journey-card" class="tm-p-card" tabindex="-1"><h3>'+e(current.name)+'</h3>'+
      '<div class="tm-p-muted">'+e(current.region)+' · '+num(current.distance).toFixed(1)+' km</div>'+
      '<form id="tm-p-journey-form" class="tm-p-form" style="margin-top:14px">'+
      '<label>État de cette aventure<select name="status"><option value="planned">À découvrir</option><option value="preparing">En préparation</option><option value="ready">Prêt</option><option value="completed">Terminé</option></select></label>'+
      '<label>Notes personnelles<textarea name="notes" maxlength="2000" placeholder="Idées, impressions, informations utiles…">'+e(j&&j.notes||'')+'</textarea></label>'+
      '<div id="tm-p-completion" class="tm-p-two" '+(st==='completed'?'':'hidden')+'>'+
        '<label>Date de la sortie<input type="date" name="completed_on" value="'+e(j&&j.completed_on||'')+'"></label>'+
        '<label>Distance parcourue (km)<input type="number" min="0" max="20000" step=".1" name="actual_distance_km" value="'+e(j?.actual_distance_km==null?'':j.actual_distance_km)+'"></label>'+
        '<label>Dénivelé réel (m)<input type="number" min="0" max="150000" name="actual_ascent_m" value="'+e(j?.actual_ascent_m==null?'':j.actual_ascent_m)+'"></label>'+
        '<label>Note de la sortie<select name="rating"><option value="">Sans note</option>'+
           [1,2,3,4,5].map(function(x){return '<option value="'+x+'">'+x+'/5</option>'}).join('')+'</select></label></div>'+
      '<label>Ajouter une photo depuis ton appareil<input type="file" name="local_photo" accept="image/jpeg,image/png,image/webp,image/heic,image/heif"></label>'+
      '<div class="tm-p-local-photo" id="tm-p-local-photo-preview">'+(localPhoto?'<img src="'+e(localPhoto)+'" alt="Photo enregistrée">':'<span>Aucune photo personnelle ajoutée.</span>')+'</div>'+
      (localPhoto?'<label class="tm-p-check"><input type="checkbox" name="remove_photo"> Supprimer cette photo</label>':'')+
      '<label>Liens de photos facultatifs (HTTPS, maximum 5 au total)<textarea name="photos" placeholder="https://…" maxlength="2100">'+e(photoLinks.join('\n'))+'</textarea></label>'+
      '<div class="tm-p-inline"><button type="submit" class="tm-p-btn primary">Enregistrer mon aventure</button>'+
      '<button type="button" class="tm-p-btn" data-p-plan="'+Number(current.id)+'">Checklist et préparation</button>'+
      '<button type="button" class="tm-p-btn" data-p-open-trek="'+Number(current.id)+'">Voir la fiche du trek</button></div></form>'+
      '<div id="tm-p-plan-editor"></div></div>';
  }else panel='<div class="tm-p-card"><h3>Choisir un trek</h3><p class="tm-p-muted">Sélectionne un trek créé ou mis en favori pour suivre sa préparation, renseigner ton carnet et accéder à sa checklist.</p></div>';
  return '<div class="tm-p-inline" style="justify-content:space-between;margin-bottom:14px;gap:12px;align-items:center">'+
    '<h2 class="tm-p-heading" style="margin:0">Mes aventures</h2>'+
    '<button type="button" class="tm-p-btn primary" data-p-go="downloads">⬇ Treks téléchargés</button></div>'+
    '<div class="tm-p-cols"><div class="tm-p-card">'+
    '<h3>Mes treks</h3><div class="tm-p-list">'+(treks.length?treks.map(function(t){
       const j=journey(t.id),tag=statusNames[j&&j.status||'planned'];
       const origin=(ownedIds.has(Number(t.id))?'created ':'')+(favoriteIds.has(Number(t.id))?'favorite ':'')+(!ownedIds.has(Number(t.id))&&!favoriteIds.has(Number(t.id))?'other':'');
       return '<div data-p-origin="'+origin.trim()+'" class="tm-p-project-row'+(Number(selected)===Number(t.id)?' is-selected':'')+'">'+
         card(t,'<button type="button" class="tm-p-btn" data-p-select="'+Number(t.id)+'" aria-pressed="'+
         (Number(selected)===Number(t.id)?'true':'false')+'" aria-label="Ouvrir '+e(t.name)+' dans Mes aventures">'+e(tag)+' →</button>')+'</div>';
    }).join(''):'<p class="tm-p-muted">Crée un trek ou ajoute un itinéraire aux favoris pour le retrouver ici.</p>')+
    '</div></div>'+panel+'</div>';
}
function journal(){
  const rows=model.journeys.filter(function(j){return j.status==='completed'});
  return '<div class="tm-p-inline" style="justify-content:space-between;gap:10px;margin-bottom:16px"><h2 class="tm-p-heading" style="margin:0">Mon carnet de randonnée</h2>'+
    '<button type="button" class="tm-p-btn primary" data-p-offline-journal="1">▤ Mes traces GPS et photos Android</button></div>'+
    '<div class="tm-p-card">'+
    '<p class="tm-p-muted">Ce carnet est privé par défaut. Les kilomètres et dénivelés reposent sur tes relevés, pas sur les estimations du planificateur.</p>'+
    '<div class="tm-p-list" style="margin-top:15px">'+(rows.length?rows.map(function(j){
      return '<div class="tm-p-item"><div><b>'+e(j.name)+'</b><small>'+e(j.region)+' · '+e(j.completed_on||'Date non indiquée')+' · '+
        (j.actual_distance_km==null?'Distance non renseignée':num(j.actual_distance_km).toFixed(1)+' km')+
        (j.rating?' · '+j.rating+'/5':'')+'</small><small>'+e(j.notes||'')+'</small>'+
        '<div class="tm-p-photos">'+(j.photo_urls||[]).map(function(u,i){return /^data:image\/(jpeg|webp);base64,/.test(u)?'<img loading="lazy" src="'+e(u)+'" alt="Photo de randonnée '+(i+1)+'">':'<a target="_blank" rel="noopener noreferrer nofollow" href="'+e(u)+'">Photo '+(i+1)+' ↗</a>'}).join('')+'</div></div>'+
        '<button class="tm-p-btn" data-p-select="'+Number(j.trek_id)+'">Modifier</button></div>';
    }).join(''):'<p class="tm-p-muted">Aucune aventure terminée déclarée. Tu peux en marquer une dans « Mes aventures ».</p>')+
    '</div></div><div class="tm-p-card" style="margin-top:15px"><h3>Mes accomplissements</h3><div class="tm-p-badges">'+
    (model.achievements.length?model.achievements.map(function(x){return '<span>✦ '+e(x)+'</span>'}).join(''):
      '<span>Ton premier badge sera attribué après une sortie terminée.</span>')+'</div></div>';
}
function collections(){
  const collections=model.collections||[], available=accountTreks();
  const chosen=selected!=null?collections.find(function(x){return Number(x.id)===Number(selected)}):null;
  const entries=collections.length?collections.map(function(item){
    const active=chosen&&Number(chosen.id)===Number(item.id);
    return '<button type="button" class="tm-p-item tm-p-collection-entry'+(active?' is-selected':'')+
      '" aria-pressed="'+(active?'true':'false')+'" data-p-collection="'+Number(item.id)+'">'+
      '<span><b>'+e(item.name)+'</b><small>'+(item.treks||[]).length+' trek(s)</small></span>'+
      '<span class="tm-p-pill">Ouvrir →</span></button>';
  }).join(''):'<p class="tm-p-muted">Aucune collection enregistrée.</p>';
  let panel='<div id="tm-p-collection-content" class="tm-p-card" tabindex="-1"><h3>Contenu de la collection</h3>'+
    '<p class="tm-p-muted">Choisis une collection pour consulter ses treks, ouvrir leurs fiches ou en ajouter de nouveaux.</p></div>';
  if(chosen){
    const stored=Array.isArray(chosen.treks)?chosen.treks:[];
    const ids=new Set(stored.map(function(t){return Number(t.id)}));
    const candidates=available.filter(function(t){return !ids.has(Number(t.id))});
    const storedRows=stored.length?stored.map(function(t){
      return '<div class="tm-p-item"><div><b>'+e(t.name)+'</b><small>'+e(t.region||'France')+'</small></div>'+
        '<div class="tm-p-inline">'+
          '<button type="button" class="tm-p-btn primary" data-p-open-trek="'+Number(t.id)+'">Voir le trek ↗</button>'+
          '<button type="button" class="tm-p-btn" data-p-collection-manage="'+Number(t.id)+'">Préparer</button>'+
          '<button type="button" class="tm-p-btn" data-p-toggle-collection="'+Number(chosen.id)+'" data-trek="'+Number(t.id)+'" data-in="1">Retirer</button>'+
        '</div></div>';
    }).join(''):'<p class="tm-p-muted">Cette collection est vide. Ajoute un trek ci-dessous pour le retrouver ici.</p>';
    panel='<div id="tm-p-collection-content" class="tm-p-card" tabindex="-1">'+
      '<h3>'+e(chosen.name)+'</h3><p class="tm-p-muted">'+stored.length+' trek(s) dans cette collection</p>'+
      '<div class="tm-p-inline" style="margin:11px 0 15px">'+
        '<button type="button" class="tm-p-btn" data-p-rename="'+Number(chosen.id)+'">Renommer</button>'+
        '<button type="button" class="tm-p-btn danger" data-p-delete-collection="'+Number(chosen.id)+'">Supprimer la collection</button>'+
      '</div><div class="tm-p-section-label">Mes treks enregistrés</div>'+
      '<div class="tm-p-list">'+storedRows+'</div>'+
      '<div class="tm-p-section-label">Ajouter un trek à cette collection</div>'+
      '<div class="tm-p-list">'+(candidates.length?candidates.map(function(t){
        return '<div class="tm-p-item"><div><b>'+e(t.name)+'</b><small>'+e(t.region||'France')+'</small></div>'+
          '<button type="button" class="tm-p-btn" data-p-toggle-collection="'+Number(chosen.id)+'" data-trek="'+Number(t.id)+'" data-in="0">+ Ajouter</button></div>';
      }).join(''):'<p class="tm-p-muted">Tous les treks disponibles sont déjà dans cette collection.</p>')+
      '</div></div>';
  }
  return '<h2 class="tm-p-heading">Mes collections</h2><div class="tm-p-cols">'+
    '<div class="tm-p-card"><h3>Classer mes idées de randonnée</h3>'+
      '<form id="tm-p-collection-create" class="tm-p-inline">'+
        '<input aria-label="Nom de la nouvelle collection" name="name" placeholder="Ex. Treks en montagne" maxlength="70" required>'+
        '<button class="tm-p-btn primary" type="submit">Créer</button></form>'+
      '<div class="tm-p-list" style="margin-top:14px">'+entries+'</div></div>'+panel+'</div>';
}
function downloads(){
  const native=window.Capacitor?.Plugins?.TrekMapNativeGPS;
  let body;
  if(!native?.listOfflineRoutes){
    body='<p class="tm-p-muted">Les treks téléchargés sont uniquement accessibles dans l’application Android, sur le téléphone où ils ont été enregistrés.</p>';
  }else if(downloadStatus==='loading'){
    body='<p class="tm-p-muted" role="status">Lecture des treks téléchargés…</p>';
  }else if(downloadStatus==='error'){
    body='<p class="tm-p-muted" role="alert">Impossible de lire tes treks téléchargés sur ce téléphone.</p>';
  }else if(!downloadedRoutes.length){
    body='<p class="tm-p-muted">Aucun trek sauvegardé. Ouvre un trek, entre dans Mode randonnée puis choisis « Enregistrer pour Android hors réseau ».</p>';
  }else {
    body='<div class="tm-p-list">'+downloadedRoutes.map(function(r){
      const n=Math.max(1,Number(r.sections)||1);
      return '<div class="tm-p-item"><div><b>'+e(r.name||'Randonnée')+'</b>'+
        '<small>'+e(r.region||'France')+' · '+n+' section'+(n>1?'s':'')+' cartographique'+(n>1?'s':'')+'</small>'+
        '<small>Tracé enregistré. Vérifie la couverture de la carte avant ton départ.</small></div>'+
        '<div class="tm-p-inline"><button type="button" class="tm-p-btn primary" data-p-offline-open="'+e(r.id)+'">Ouvrir</button>'+
        '<button type="button" class="tm-p-btn" data-p-offline-download="'+e(r.id)+'">Télécharger la carte</button></div></div>';
    }).join('')+'</div>';
  }
  return '<h2 class="tm-p-heading">Treks téléchargés</h2><div class="tm-p-card">'+
    '<h3>Mes randonnées hors connexion</h3><button type="button" class="tm-p-btn primary" data-p-offline-map="1">🗺️ Ouvrir la carte de tous mes treks</button><p class="tm-p-muted">Les fichiers restent sur cet appareil, sans synchronisation Neon. Pour les grands treks, prépare la carte section par section, avant d’activer le mode avion.</p>'+
    body+'<div style="margin-top:14px"><button type="button" class="tm-p-btn" data-p-offline-refresh="1">↻ Actualiser la liste</button></div></div>';
}
async function refreshDownloads(){
  const native=window.Capacitor?.Plugins?.TrekMapNativeGPS;
  downloadedRoutes=[];downloadStatus='loading';
  if(tab==='downloads')render();
  if(!native?.listOfflineRoutes){downloadStatus='unsupported';if(tab==='downloads')render();return}
  try{
    const d=await native.listOfflineRoutes();
    downloadedRoutes=Array.isArray(d?.routes)?d.routes.filter(function(r){return r&&typeof r.id==='string'&&r.id.length>0}):[];
    downloadStatus='ready';
  }catch(err){downloadStatus='error'}
  if(tab==='downloads'&&!root.hidden)render();
}
function preferences(){
 const s=model.settings||{},p=s.preferences||{},icons=Object.keys(avatarIcons);
 return '<h2 class="tm-p-heading">Mes préférences et ma confidentialité</h2><div class="tm-p-cols">'+
   '<div class="tm-p-card"><form id="tm-p-settings-form" class="tm-p-form">'+
   '<h3>Mon profil</h3><label>Avatar<select name="avatar">'+icons.map(function(x){return '<option value="'+x+'">'+avatarIcons[x]+' '+e(x)+'</option>'}).join('')+'</select></label>'+
   '<label>Présentation courte<textarea name="bio" maxlength="280" placeholder="Quelles randonnées aimes-tu ?">'+e(s.bio||'')+'</textarea></label>'+
   '<h3>Préférences TrekBrain</h3><div class="tm-p-two">'+
   '<label>Distance préférée (km/jour)<input name="daily_km" type="number" min="3" max="40" step=".5" value="'+e(p.daily_km==null?18:p.daily_km)+'"></label>'+
   '<label>Niveau<select name="difficulty"><option value="easy">Facile</option><option value="medium">Moyen</option><option value="hard">Difficile</option></select></label>'+
   '<label>Hébergement<select name="lodging"><option value="any">Indifférent</option><option value="camping">Camping</option><option value="refuge">Refuge</option><option value="hotel">Hôtel / gîte</option></select></label>'+
   '<label>Type de parcours<select name="route_type"><option>Boucle</option><option>Traversée</option><option>Itinérance</option><option>Aller-retour</option></select></label></div>'+
   '<label class="tm-p-check"><input name="transit" type="checkbox"> Favoriser train et bus</label>'+
   '<label class="tm-p-check"><input name="water" type="checkbox"> Rechercher l’eau</label>'+
   '<label class="tm-p-check"><input name="food" type="checkbox"> Rechercher le ravitaillement</label>'+
   '<label class="tm-p-check"><input name="sleep" type="checkbox"> Prévoir les nuitées</label>'+
   '<h3>Visibilité</h3><label class="tm-p-check"><input name="public_profile" type="checkbox"> Activer un profil public</label>'+
   '<label class="tm-p-check"><input name="share_completed" type="checkbox"> Partager les noms de mes sorties terminées (treks publics uniquement)</label>'+
   '<div class="tm-p-callout">Sans activation, ton profil, tes notes, tes dates de sortie et tes préparations restent privés. Même en profil public, jamais d’email, de journal personnel ni de date de randonnée.</div>'+
   '<div class="tm-p-inline"><button type="submit" class="tm-p-btn primary">Enregistrer les préférences</button>'+
   '<button type="button" class="tm-p-btn" data-p-password="1">Mot de passe</button>'+
   '<button type="button" class="tm-p-btn danger" data-p-logout="1">Déconnexion</button></div></form></div>'+
   '<div class="tm-p-card"><h3>Partager mon profil</h3><p class="tm-p-muted">La publication est facultative et désactivée par défaut. Les photos ne sont jamais publiées automatiquement.</p>'+
   '<div class="tm-p-callout">'+(s.public_profile?'Ton profil est public. Copie le lien ci-dessous.':'Ton profil est privé.')+'</div>'+
   (s.public_profile?'<div class="tm-p-inline"><button class="tm-p-btn" data-p-share="1">Copier le lien public</button><button class="tm-p-btn" data-p-preview="1">Aperçu public</button></div>':'')+
   '<p class="tm-p-muted" style="margin-top:18px">Les liens photos ouvrent des sites externes. Ne partage pas de photos contenant des informations personnelles si tu ne le souhaites pas.</p></div></div>';
}
function render(){
 nav();head();if(!model){content.innerHTML='<div class="tm-p-card">Chargement…</div>';return}
 content.innerHTML=({home:home,projects:projects,journal:journal,collections:collections,downloads:downloads,preferences:preferences}[tab]||home)();
 if(tab==='projects'&&selected!=null){
  const j=journey(selected)||{},f=el('tm-p-journey-form');
  if(f){f.elements.status.value=j.status||'planned';f.elements.rating.value=j.rating||''}
 }
 if(tab==='preferences'){
  const s=model.settings||{},p=s.preferences||{},f=el('tm-p-settings-form');
  if(f){
   f.elements.avatar.value=s.avatar||'mountain';
   f.elements.difficulty.value=p.difficulty||'medium';
   f.elements.lodging.value=p.lodging||'any';
   f.elements.route_type.value=p.route_type||'Boucle';
   ['transit','water','food','sleep'].forEach(function(k){f.elements[k].checked=p[k]!==false});
   f.elements.public_profile.checked=!!s.public_profile;
   f.elements.share_completed.checked=!!s.share_completed;
  }
 }
}
function revealPanel(id){
  const target=el(id);
  if(!target)return;
  target.scrollIntoView({block:'start',behavior:'instant'});
  target.focus({preventScroll:true});
}
async function openTrekFromProfile(value){
  const id=Number(value);
  if(!Number.isSafeInteger(id)||id<=0){announce('Identifiant de trek invalide.');return}
  try{
    // A collection may contain a public trek that is neither owned nor favorited.
    // In that case the current map catalogue may not have it yet.
    if(typeof allTreks!=='undefined'&&Array.isArray(allTreks)&&
       !allTreks.some(function(t){return Number(t.id)===id})){
      const detail=await request('/treks/'+id,'GET');
      allTreks.push(detail);
    }
    if(typeof window.openDetail!=='function')throw Error('La fiche du trek est indisponible.');
    close();
    window.openDetail(id);
  }catch(err){announce('Impossible d’ouvrir ce trek. '+(err.message||''))}
}
function close(){
 root.hidden=true;model=null;plan=null;document.body.style.removeProperty('overflow');
 if(previousFocus&&previousFocus.focus)previousFocus.focus();
}
async function open(){
 if(typeof currentUser!=='undefined'&&!currentUser){if(typeof authModal==='function')authModal('login');return}
 previousFocus=document.activeElement;
 root.querySelectorAll('[data-p-tab]').forEach(function(b){b.hidden=false});
 if(typeof closeModal==='function')closeModal();
 root.hidden=false;root.setAttribute('role','dialog');root.setAttribute('aria-modal','true');
 document.body.style.overflow='hidden';tab='home';selected=null;model=null;render();
 const profileNav=root.querySelector('.tm-p-nav');
 if(profileNav)profileNav.scrollLeft=0;
 const firstTab=root.querySelector('[data-p-tab="home"]');
 if(firstTab)firstTab.focus({preventScroll:true});
 try{await load();render()}catch(err){content.innerHTML='<div class="tm-p-card"><h2>Profil temporairement inaccessible</h2><p>'+e(err.message)+'</p><button class="tm-p-btn" data-p-retry="1">Réessayer</button></div>'}
}
window.openProfile=open;
window.TrekMapProfileV2={open:open,close:close};
root.addEventListener('click',async function(event){
 const button=event.target.closest('button');if(!button)return;
 const id=button.dataset.pTab;
 if(id){tab=id;selected=null;plan=null;render();
   if(id==='home'){const n=root.querySelector('.tm-p-nav');if(n)n.scrollLeft=0}
   if(id==='downloads')refreshDownloads();
   return}
 if(button.id==='tm-p-exit'){close();return}
 if(button.dataset.pGo){tab=button.dataset.pGo;selected=null;render();if(tab==='downloads')await refreshDownloads();return}
 if(button.dataset.pRetry){await open();return}
  if(button.dataset.pOfflineMap){
    const native=window.Capacitor?.Plugins?.TrekMapNativeGPS;
    try{if(!native?.openOfflineMap)throw Error('Mets à jour l’application Android');
      await native.openOfflineMap()}
    catch(err){announce('Carte indisponible : '+(err.message||err))}
    return;
  }
  if(button.dataset.pOfflineJournal){
    const native=window.Capacitor?.Plugins?.TrekMapNativeGPS;
    try{if(!native?.openOfflineJournal)throw Error('Mets à jour l’application Android');
      await native.openOfflineJournal()}
    catch(err){announce('Carnet GPS indisponible : '+(err.message||err))}
    return;
  }
  if(button.dataset.pOfflineRefresh){await refreshDownloads();return}
  if(button.dataset.pOfflineOpen){
    const native=window.Capacitor?.Plugins?.TrekMapNativeGPS;
    try{if(!native?.openOfflineRoute)throw Error('Fonction réservée à Android');
      await (native.openOfflineMap?.({id:button.dataset.pOfflineOpen})||native.openOfflineRoute({id:button.dataset.pOfflineOpen}))}
    catch(err){announce('Ouverture indisponible : '+(err.message||err))}
    return;
  }
  if(button.dataset.pOfflineDownload){
    const native=window.Capacitor?.Plugins?.TrekMapNativeGPS;
    try{if(!native?.openOfflineDownload)throw Error('Fonction réservée à Android');
      await native.openOfflineDownload({id:button.dataset.pOfflineDownload})}
    catch(err){announce('Téléchargement indisponible : '+(err.message||err))}
    return;
  }
 if(button.dataset.pSelect){selected=Number(button.dataset.pSelect);tab='projects';plan=null;render();revealPanel('tm-p-journey-card');return}
 if(button.dataset.pCollection){selected=Number(button.dataset.pCollection);tab='collections';render();revealPanel('tm-p-collection-content');return}
 if(button.dataset.pCollectionManage){selected=Number(button.dataset.pCollectionManage);tab='projects';plan=null;render();revealPanel('tm-p-journey-card');return}
 if(button.dataset.pOpenTrek){await openTrekFromProfile(button.dataset.pOpenTrek);return}
 if(button.dataset.pPassword){close();if(typeof window.openPassword==='function')window.openPassword();return}
 if(button.dataset.pLogout){close();if(typeof window.logout==='function')window.logout();return}
 if(button.dataset.pShare){
  const url=location.origin+location.pathname+'?profil='+encodeURIComponent(model.user.username);
  try{await navigator.clipboard.writeText(url);announce('Lien public copié.')}catch(err){window.prompt('Copie ce lien',url)}return;
 }
 if(button.dataset.pPreview){await publicOpen(model.user.username);return}
 try{
  if(button.dataset.pPlan){await planOpen(Number(button.dataset.pPlan));return}
  if(button.dataset.pCheckremove!==undefined){
   const idx=Number(button.dataset.pCheckremove);
   if(plan&&Number.isInteger(idx)&&idx>=0&&idx<plan.checklist.length){
     plan.checklist.splice(idx,1);drawPlan();
   }
   return;
  }
  if(button.dataset.pChecklistAdd){
   const i=el('tm-p-new-item');
   if(!plan||!i)return;
   const text=i.value.trim().slice(0,200);
   if(!text){i.focus();announce('Écris un élément avant de l’ajouter.');return}
   if(plan.checklist.length>=100){announce('La checklist ne peut pas dépasser 100 éléments.');return}
   plan.checklist.push({text:text,done:false});drawPlan();
   const entry=el('tm-p-plan-editor')?.querySelector('[data-p-checktext="'+(plan.checklist.length-1)+'"]');
   entry?.focus();return;
  }
  if(button.dataset.pChecklistSave){
   if(!plan)return;
   const savedId=Number(selected);
   button.disabled=true;
   try{
     const body={notes:plan.notes||'',checklist:plan.checklist,days:plan.days===undefined?null:plan.days};
     await request('/treks/'+savedId+'/plan','PUT',body);
     // Round-trip the actual stored state; confirm edits remain when reopened.
     const saved=await request('/treks/'+savedId+'/plan','GET');
     if(!Array.isArray(saved.checklist))throw Error('Impossible de relire la checklist enregistrée.');
     plan=saved;drawPlan();announce('Checklist enregistrée et vérifiée.');
   }finally{button.disabled=false}
   return;
  }
  if(button.dataset.pDeleteCollection){
   if(!confirm('Supprimer cette collection ? Les treks resteront enregistrés.'))return;
   await api('v2/collections/'+button.dataset.pDeleteCollection,'DELETE');selected=null;await load();render();return;
  }
  if(button.dataset.pRename){
   const collection=model.collections.find(function(x){return x.id===Number(button.dataset.pRename)});
   const name=prompt('Nouveau nom',collection&&collection.name||'');
   if(name&&name.trim()){await api('v2/collections/'+button.dataset.pRename,'PUT',{name:name.trim()});await load();render()}return;
  }
  if(button.dataset.pToggleCollection){
   await api('v2/collections/'+button.dataset.pToggleCollection+'/treks/'+button.dataset.trek,
    button.dataset.in==='1'?'DELETE':'PUT');await load();render();return;
  }
 }catch(err){announce(err.message)}
});
root.addEventListener('change',function(ev){
 if(ev.target.name==='status'){const f=el('tm-p-journey-form'),d=el('tm-p-completion');if(f&&d)d.hidden=f.elements.status.value!=='completed'}
 if(ev.target.name==='local_photo'){
  const preview=el('tm-p-local-photo-preview'),file=ev.target.files&&ev.target.files[0];
  if(!preview||!file)return;
  if(!/^image\/(jpeg|png|webp|heic|heif)$/i.test(file.type)||file.size>12*1024*1024){
   ev.target.value='';announce('Choisis une image JPG, PNG, WebP ou HEIC de moins de 12 Mo.');return;
  }
  const url=URL.createObjectURL(file),img=document.createElement('img');
  img.alt='Aperçu de la photo choisie';
  img.onload=function(){URL.revokeObjectURL(url)};
  img.onerror=function(){URL.revokeObjectURL(url);preview.textContent='Impossible de prévisualiser ce format.'};
  img.src=url;preview.replaceChildren(img);
 }
 if(ev.target.matches('[data-p-checkindex]')&&plan){
   const idx=Number(ev.target.dataset.pCheckindex);
   if(Number.isInteger(idx)&&idx>=0&&idx<plan.checklist.length)
     plan.checklist[idx].done=ev.target.checked;
 }
});
// Update the draft as the user types. Never redraw during input, which would
// destroy focus, the caret position or a phone's composing keyboard.
root.addEventListener('input',function(ev){
 const field=ev.target.closest?.('[data-p-checktext]');
 if(!field||!plan)return;
 const idx=Number(field.dataset.pChecktext);
 if(Number.isInteger(idx)&&idx>=0&&idx<plan.checklist.length)
   plan.checklist[idx].text=String(field.value||'').slice(0,200);
});
root.addEventListener('keydown',function(ev){
 if(ev.key==='Enter'&&ev.target.id==='tm-p-new-item'){
   ev.preventDefault();
   root.querySelector('[data-p-checklist-add]')?.click();
 }
});
root.addEventListener('submit',async function(ev){
 ev.preventDefault();const f=ev.target;
 try{
  if(f.id==='tm-p-journey-form'){
   const st=f.elements.status.value;
   const urls=f.elements.photos.value.trim().split(/\n+/).map(function(x){return x.trim()}).filter(Boolean);
   const chosen=f.elements.local_photo.files&&f.elements.local_photo.files[0];
   const saved=journey(selected)?.photo_urls||[];
   const previous=saved.find(function(x){return /^data:image\/(jpeg|webp);base64,/.test(x)});
   if(chosen)urls.unshift(await localPhotoData(chosen));
   else if(previous&&!f.elements.remove_photo?.checked)urls.unshift(previous);
   if(urls.length>5)throw Error('Maximum 5 photos par aventure, liens compris.');
   const d={status:st,notes:f.elements.notes.value,completed_on:st==='completed'?(f.elements.completed_on.value||null):null,
    actual_distance_km:st==='completed'&&f.elements.actual_distance_km.value!==''?Number(f.elements.actual_distance_km.value):null,
    actual_ascent_m:st==='completed'&&f.elements.actual_ascent_m.value!==''?Number(f.elements.actual_ascent_m.value):null,
    rating:st==='completed'&&f.elements.rating.value?Number(f.elements.rating.value):null,photo_urls:urls};
   await api('v2/journeys/'+Number(selected),'PUT',d);await load();render();announce('Aventure enregistrée.');return;
  }
  if(f.id==='tm-p-collection-create'){
   await api('v2/collections','POST',{name:f.elements.name.value.trim()});await load();render();announce('Collection créée.');return;
  }
  if(f.id==='tm-p-settings-form'){
   const keys=['transit','water','food','sleep'],p={daily_km:Number(f.elements.daily_km.value),
       difficulty:f.elements.difficulty.value,lodging:f.elements.lodging.value,route_type:f.elements.route_type.value};
   keys.forEach(function(k){p[k]=f.elements[k].checked});
   await api('v2','PUT',{bio:f.elements.bio.value,avatar:f.elements.avatar.value,
        public_profile:f.elements.public_profile.checked,share_completed:f.elements.share_completed.checked,preferences:p});
   await load();render();announce('Préférences enregistrées.');return;
  }
 }catch(err){announce(err.message)}
});
async function planOpen(tid){
 selected=tid;
 plan=await request('/treks/'+tid+'/plan','GET');
 if(!Array.isArray(plan.checklist))plan.checklist=[];
 drawPlan();
}
function drawPlan(){
 const area=el('tm-p-plan-editor');if(!area||!plan)return;
 area.innerHTML='<div class="tm-p-card" style="margin-top:12px;padding:12px"><h3>Checklist de préparation</h3>'+
 '<div class="tm-p-list">'+plan.checklist.map(function(x,i){
  return '<div class="tm-p-checkline">'+
    '<input type="checkbox" data-p-checkindex="'+i+'" aria-label="Élément terminé : '+e(x.text||'')+'" '+(x.done?'checked':'')+'>'+
    '<input type="text" data-p-checktext="'+i+'" value="'+e(x.text||'')+'" maxlength="200" aria-label="Modifier l’élément '+(i+1)+'" autocomplete="off" placeholder="Écris ici…">'+
    '<button type="button" data-p-checkremove="'+i+'" aria-label="Supprimer l’élément '+(i+1)+'">×</button></div>';
 }).join('')+'</div><div class="tm-p-inline" style="margin-top:12px"><input id="tm-p-new-item" placeholder="Ajouter un élément" maxlength="200">'+
 '<button class="tm-p-btn" data-p-checklist-add="1">Ajouter</button><button class="tm-p-btn primary" data-p-checklist-save="1">Enregistrer la checklist</button></div>'+
 '<p class="tm-p-muted">Modifie directement le texte des lignes, coche les éléments terminés, puis enregistre. La liste est personnelle et synchronisée avec la fiche trek.</p></div>';
}
async function publicOpen(username){
 try{
  const x=await api('public/'+encodeURIComponent(username),'GET');
  root.hidden=false;document.body.style.overflow='hidden';
  hero.innerHTML='<div class="tm-p-avatar">'+(avatarIcons[x.avatar]||'⛰')+'</div><div><h1>'+e(x.username)+'</h1><p>'+e(x.bio||'Profil de randonneur')+'</p><div class="tm-p-banner">Profil partagé volontairement</div></div>';
  content.innerHTML='<h2 class="tm-p-heading">Treks publics</h2><div class="tm-p-card tm-p-list">'+
    (x.treks.length?x.treks.map(function(t){return card(t,'')}).join(''):'<p class="tm-p-muted">Aucun trek public.</p>')+
    '</div><div class="tm-p-card" style="margin-top:13px"><h3>Sorties partagées</h3>'+
    (x.completed.length?x.completed.map(function(t){return '<div class="tm-p-item">'+e(t.name)+'</div>'}).join(''):
      '<p class="tm-p-muted">Aucune sortie rendue publique.</p>')+'</div>';
  root.querySelectorAll('[data-p-tab]').forEach(function(b){b.hidden=true});
 }catch(err){announce(err.message)}
}
document.addEventListener('keydown',function(ev){if(ev.key==='Escape'&&!root.hidden){ev.preventDefault();close()}});
const query=new URLSearchParams(location.search).get('profil');
if(query&&query.length<=80){
  document.addEventListener('DOMContentLoaded',function(){previousFocus=document.activeElement;publicOpen(query)}, {once:true});
}
/* Explicit TrekBrain integration, never overwrite a user's current request.
   The stored defaults can be applied by the hiker through a visible button. */
function attachBrainButton(){
 const modal=document.getElementById('tm-ai-overlay');
 if(!modal||document.getElementById('tm-ai-profile-defaults'))return;
 const before=modal.querySelector('#tm-ai-generate');
 if(!before)return;
 const b=document.createElement('button');
 b.type='button';b.id='tm-ai-profile-defaults';b.className='tm-ai-secondary';
 b.textContent='⌖ Appliquer mes préférences du profil';
 before.parentNode.insertBefore(b,before);
 b.addEventListener('click',async function(){
  try{
   const d=model&&model.settings?model:await load();
   const p=d.settings&&d.settings.preferences||{};
   const field=function(id){return document.getElementById(id)};
   if(p.daily_km!=null&&field('tm-ai-km'))field('tm-ai-km').value=p.daily_km;
   if(p.difficulty&&field('tm-ai-difficulty'))field('tm-ai-difficulty').value=p.difficulty;
   if(p.route_type&&field('tm-ai-route-type'))field('tm-ai-route-type').value=p.route_type;
   const checks={transit:'tm-ai-transit',water:'tm-ai-water',food:'tm-ai-food',sleep:'tm-ai-sleep'};
   Object.keys(checks).forEach(function(k){if(typeof p[k]==='boolean'&&field(checks[k]))field(checks[k]).checked=p[k]});
   const prompt=field('tm-ai-prompt');
   if(prompt&&p.lodging&&p.lodging!=='any'){
     const sentence='Hébergement souhaité : '+({camping:'camping',refuge:'refuge',hotel:'hôtel ou gîte'}[p.lodging]||p.lodging)+'.';
     if(!prompt.value.includes(sentence))prompt.value=(prompt.value.trim()+'\n'+sentence).trim();
     prompt.dispatchEvent(new Event('input',{bubbles:true}));
   }
   announce('Préférences TrekBrain appliquées.');
  }catch(err){announce('Connecte-toi pour utiliser tes préférences personnelles.')}
 });
}
document.addEventListener('click',function(ev){
 if(ev.target.closest&&ev.target.closest('#tm-ai-launch,[data-mobile-action="ai"],#tm-ai-overlay [data-workspace-action="modify"]'))
   setTimeout(attachBrainButton,90);
},true);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attachBrainButton,{once:true});
else attachBrainButton();
})();
</script>
<!-- TREKMAP_PROFILE_V2_END -->'''
if html.count("</body>")!=1:
    raise SystemExit("Unexpected body marker count")
html=html.replace("</body>",block+"\n</body>",1)
path.write_text(html,encoding="utf-8")
print("TrekMap profile v2 installed without replacing legacy account/password/route handlers")

# Apply the map-first Explorer layout after the existing profile and desktop CSS.
# This is the last UI installer reached by the Render build.
from runpy import run_path
run_path(str(Path(__file__).with_name("apply_inline_filters.py")))
