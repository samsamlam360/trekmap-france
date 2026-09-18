from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r"\s*<!-- TREKMAP_AI_EXPERIENCE_START -->.*?<!-- TREKMAP_AI_EXPERIENCE_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_UNIFIED_EXPERIENCE_START" not in html:
    raise SystemExit("La couche unifiée TrekMap doit être construite avant TrekMap AI.")

block = r'''<!-- TREKMAP_AI_EXPERIENCE_START -->
<style id="trekmap-ai-css">
#tm-ai-launch{
  height:42px;border:1px solid #6ce0a5!important;border-radius:12px;
  background:linear-gradient(135deg,#1e9365,#0f7652)!important;color:#fff!important;
  padding:0 13px;font-weight:900;white-space:nowrap;display:flex;align-items:center;gap:7px;
  box-shadow:0 7px 20px rgba(17,107,73,.22)
}
#tm-ai-launch:hover{filter:brightness(1.05)}
#tm-ai-overlay{
  position:fixed;z-index:16000;inset:0;display:none;
  background:rgba(5,27,18,.58);backdrop-filter:blur(5px);-webkit-backdrop-filter:blur(5px);
  padding:18px
}
#tm-ai-overlay.open{display:flex;align-items:center;justify-content:center}
.tm-ai-shell{
  width:min(1120px,100%);max-height:calc(100dvh - 36px);overflow:hidden;
  display:grid;grid-template-columns:minmax(310px,390px) minmax(0,1fr);
  background:#f7faf8;border:1px solid #dbe7e0;border-radius:24px;
  box-shadow:0 30px 100px rgba(0,0,0,.34)
}
.tm-ai-side,.tm-ai-result{min-width:0;overflow:auto}
.tm-ai-side{padding:19px;background:#fff;border-right:1px solid #e1e9e4}
.tm-ai-result{padding:19px 20px 24px}
.tm-ai-head{display:flex;align-items:flex-start;gap:10px;margin-bottom:15px}
.tm-ai-head>div{flex:1}.tm-ai-head h2{margin:0;font-size:24px;color:#173b2e;letter-spacing:-.04em}
.tm-ai-head p{margin:5px 0 0;color:#6c7e76;font-size:11px;line-height:1.45}
#tm-ai-close{width:40px;height:40px;border:1px solid #dbe7e0;border-radius:12px;background:#f3f7f5;color:#4b6559;font-size:18px}
.tm-ai-field{margin-bottom:10px}.tm-ai-field label{display:block;margin-bottom:5px;color:#60746a;font-size:9px;font-weight:900;text-transform:uppercase;letter-spacing:.04em}
.tm-ai-field input,.tm-ai-field select,.tm-ai-field textarea{
  width:100%;border:1px solid #d5e2db;border-radius:11px;background:#fff;color:#203d31;
  padding:10px;outline:0
}
.tm-ai-field input:focus,.tm-ai-field select:focus,.tm-ai-field textarea:focus{border-color:#6ab18c;box-shadow:0 0 0 3px rgba(30,147,101,.09)}
.tm-ai-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.tm-ai-checks{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:9px 0 12px}
.tm-ai-check{display:flex;align-items:center;gap:7px;min-height:38px;padding:7px 9px;border:1px solid #e0e9e4;border-radius:10px;background:#f8fbf9;color:#486358;font-size:11px}
.tm-ai-check input{accent-color:#1e9365}
#tm-ai-generate,#tm-ai-refine,#tm-ai-save{
  min-height:44px;border:0;border-radius:11px;background:#116b49;color:#fff;padding:0 14px;font-weight:900
}
#tm-ai-generate{width:100%;font-size:13px}
.tm-ai-secondary{width:100%;min-height:42px;margin-top:7px;border:1px solid #d7e4dd;border-radius:11px;background:#fff;color:#375d4c;font-weight:850}
.tm-ai-note{margin-top:10px;padding:9px 10px;border-radius:10px;background:#eef6f2;color:#587067;font-size:10px;line-height:1.45}
.tm-ai-empty{min-height:440px;display:grid;place-items:center;text-align:center;color:#6b7d75}
.tm-ai-empty .icon{display:block;font-size:44px;margin-bottom:10px}
.tm-ai-progress{display:none;min-height:440px;place-items:center;text-align:center}
.tm-ai-progress.show{display:grid}.tm-ai-progress-ring{width:64px;height:64px;border-radius:50%;border:5px solid #dbeae2;border-top-color:#1e9365;animation:tm-ai-spin .8s linear infinite;margin:auto}
@keyframes tm-ai-spin{to{transform:rotate(360deg)}}
.tm-ai-progress h3{margin:16px 0 5px}.tm-ai-progress p{margin:0;color:#687c72;font-size:12px}
.tm-ai-titlebar{display:flex;gap:12px;align-items:flex-start}.tm-ai-titlebar>div{flex:1}
.tm-ai-titlebar h2{margin:0;color:#173b2e;font-size:26px;letter-spacing:-.04em}.tm-ai-titlebar p{color:#61756b;line-height:1.5}
.tm-ai-badges{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 15px}.tm-ai-badge{padding:6px 9px;border-radius:99px;background:#e9f5ef;color:#2f654f;font-size:10px;font-weight:850}
.tm-ai-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}
.tm-ai-stat{padding:11px;border:1px solid #dfe9e3;border-radius:12px;background:#fff}.tm-ai-stat small,.tm-ai-stat b{display:block}.tm-ai-stat small{color:#73857c;font-size:8px;text-transform:uppercase;font-weight:900}.tm-ai-stat b{margin-top:4px;font-size:15px}
.tm-ai-section{margin-top:16px}.tm-ai-section h3{margin:0 0 8px;font-size:15px;color:#264d3d}
.tm-ai-stage{padding:11px;margin-bottom:8px;border:1px solid #dfe9e3;border-radius:13px;background:#fff}.tm-ai-stage-head{display:flex;justify-content:space-between;gap:8px}.tm-ai-stage-head b{font-size:13px}.tm-ai-stage-head span{color:#1b7653;font-size:10px;font-weight:900}.tm-ai-stage p{margin:7px 0 0;color:#60736a;font-size:11px;line-height:1.45}
.tm-ai-list{display:grid;gap:6px}.tm-ai-item{padding:9px 10px;border:1px solid #e0e9e4;border-radius:10px;background:#fff;font-size:11px}.tm-ai-item small{display:block;color:#71837a;margin-top:3px}
.tm-ai-warning{padding:10px;border-radius:11px;background:#fff4df;border:1px solid #efd9aa;color:#71582a;font-size:11px;line-height:1.45}
.tm-ai-water-ok{color:#16714f}.tm-ai-water-unknown{color:#9a6b16}.tm-ai-water-no{color:#a64c54}
.tm-ai-source{display:block;padding:8px 9px;margin-bottom:5px;border:1px solid #e0e9e4;border-radius:9px;background:#fff;color:#176b4b;text-decoration:none;font-size:10px}
.tm-ai-actions{position:sticky;bottom:-20px;display:flex;gap:8px;margin-top:16px;padding:12px 0 4px;background:linear-gradient(transparent,#f7faf8 22%)}
#tm-ai-save{flex:1}.tm-ai-map-btn{min-height:44px;border:1px solid #cfe0d6;border-radius:11px;background:#fff;color:#315b49;font-weight:900;padding:0 13px}
.tm-ai-refine-box{margin-top:14px;padding:11px;border:1px solid #dfe9e3;border-radius:13px;background:#fff}.tm-ai-refine-box textarea{width:100%;min-height:70px;border:1px solid #d5e2db;border-radius:10px;padding:9px;resize:vertical}.tm-ai-refine-actions{display:flex;justify-content:flex-end;margin-top:7px}
#tm-ai-refine:disabled,#tm-ai-generate:disabled,#tm-ai-save:disabled{opacity:.55;cursor:wait}

@media(max-width:820px){
  #tm-ai-launch{display:none!important}
  #tm-ai-overlay{padding:0;align-items:flex-end!important}
  .tm-ai-shell{width:100%;height:min(94dvh,900px);max-height:calc(100dvh - env(safe-area-inset-top,0px));display:block;border-radius:24px 24px 0 0}
  .tm-ai-side,.tm-ai-result{height:100%;padding:15px 14px calc(18px + env(safe-area-inset-bottom,0px))}
  .tm-ai-result{display:none}
  .tm-ai-shell.has-result .tm-ai-side{display:none}.tm-ai-shell.has-result .tm-ai-result{display:block}
  .tm-ai-shell:before{content:"";position:absolute;z-index:2;top:7px;left:50%;width:42px;height:4px;border-radius:99px;background:#c5d2cc;transform:translateX(-50%)}
  .tm-ai-head{padding-top:7px}.tm-ai-field input,.tm-ai-field select,.tm-ai-field textarea,.tm-ai-refine-box textarea{font-size:16px}
  .tm-ai-stats{grid-template-columns:1fr 1fr}.tm-ai-titlebar h2{font-size:22px}
  .tm-ai-actions{bottom:calc(-18px - env(safe-area-inset-bottom,0px));padding-bottom:calc(8px + env(safe-area-inset-bottom,0px))}
}
</style>
<script id="trekmap-ai-js">
(function(){
  const $=id=>document.getElementById(id);
  const api=()=>typeof API!=='undefined'?API:'';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const safeUrl=v=>{try{const u=new URL(String(v||''));return ['http:','https:'].includes(u.protocol)?u.href:''}catch(_){return''}};
  const authHeaders=(extra={},method='GET')=>{try{return typeof headers==='function'?headers(extra,method):extra}catch(_){return extra}};
  const difficultyLabel={easy:'Facile',medium:'Moyen',hard:'Difficile'};
  let currentPlan=null,previewLayer=null,progressTimer=null;

  const actions=$('tm-top-actions');
  if(actions&&!$('tm-ai-launch')){
    const b=document.createElement('button');b.id='tm-ai-launch';b.type='button';b.innerHTML='✨ <span class="label">Trek IA</span>';
    actions.prepend(b);
  }

  const mobileCreate=document.querySelector('#tm-mobile-nav [data-mobile-action="create"]');
  if(mobileCreate){
    mobileCreate.dataset.mobileAction='ai';
    mobileCreate.classList.add('create');
    mobileCreate.innerHTML='<span class="tm-m-icon">✨</span><span>IA</span>';
  }

  const overlay=document.createElement('div');overlay.id='tm-ai-overlay';overlay.setAttribute('aria-hidden','true');
  overlay.innerHTML=`<div class="tm-ai-shell" role="dialog" aria-modal="true" aria-label="TrekMap AI">
    <section class="tm-ai-side">
      <div class="tm-ai-head"><div><h2>✨ TrekMap AI</h2><p>Décris ton trek. L'IA recherche les lieux, vérifie la logistique et fait calculer le vrai tracé.</p></div><button id="tm-ai-close" type="button">✕</button></div>
      <div class="tm-ai-field"><label>Ta demande</label><textarea id="tm-ai-prompt" rows="5" placeholder="Ex. 4 jours dans les Pyrénées, 18 km/jour, départ accessible en train, camping ou refuge chaque soir, beaux panoramas..."></textarea></div>
      <div class="tm-ai-grid">
        <div class="tm-ai-field"><label>Région / massif</label><input id="tm-ai-region" placeholder="Pyrénées, Vercors..."></div>
        <div class="tm-ai-field"><label>Jours</label><input id="tm-ai-days" type="number" min="1" max="21" value="3"></div>
        <div class="tm-ai-field"><label>Km / jour cible</label><input id="tm-ai-km" type="number" min="3" max="40" step="1" value="18"></div>
        <div class="tm-ai-field"><label>Difficulté</label><select id="tm-ai-difficulty"><option value="easy">Facile</option><option value="medium" selected>Moyen</option><option value="hard">Difficile</option></select></div>
        <div class="tm-ai-field" style="grid-column:1/-1"><label>Type</label><select id="tm-ai-route-type"><option>Boucle</option><option>Traversée</option><option>Itinérance</option><option>Aller-retour</option></select></div>
      </div>
      <div class="tm-ai-checks">
        <label class="tm-ai-check"><input id="tm-ai-transit" type="checkbox" checked> Train / bus</label>
        <label class="tm-ai-check"><input id="tm-ai-water" type="checkbox" checked> Eau</label>
        <label class="tm-ai-check"><input id="tm-ai-sleep" type="checkbox" checked> Nuitées</label>
        <label class="tm-ai-check"><input id="tm-ai-food" type="checkbox" checked> Ravitaillement</label>
      </div>
      <button id="tm-ai-generate" type="button">✨ Préparer mon trek</button>
      <button id="tm-ai-manual" class="tm-ai-secondary" type="button">＋ Créer manuellement / importer un GPX</button>
      <div class="tm-ai-note">TrekMap AI aide à préparer. Les fermetures, météo, horaires et conditions de terrain peuvent changer : vérifie toujours les sources récentes avant le départ.</div>
    </section>
    <section class="tm-ai-result" id="tm-ai-result">
      <div class="tm-ai-empty" id="tm-ai-empty"><div><span class="icon">🗺️</span><b>Ton itinéraire apparaîtra ici.</b><div style="margin-top:6px;font-size:11px">L'IA vérifiera d'abord les données utiles plutôt que d'inventer une ligne sur une carte.</div></div></div>
      <div class="tm-ai-progress" id="tm-ai-progress"><div><div class="tm-ai-progress-ring"></div><h3>Préparation du trek</h3><p id="tm-ai-progress-text">Analyse de ta demande…</p></div></div>
      <div id="tm-ai-content"></div>
    </section>
  </div>`;
  document.body.appendChild(overlay);

  const shell=overlay.querySelector('.tm-ai-shell');
  function openAI(){
    overlay.classList.add('open');overlay.setAttribute('aria-hidden','false');
    if(window.innerWidth<=820)shell.classList.toggle('has-result',!!currentPlan);
    setTimeout(()=>$('tm-ai-prompt')?.focus(),80);
  }
  function closeAI(){overlay.classList.remove('open');overlay.setAttribute('aria-hidden','true')}
  $('tm-ai-launch')?.addEventListener('click',openAI);
  $('tm-ai-close').onclick=closeAI;
  overlay.addEventListener('click',e=>{if(e.target===overlay)closeAI()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&overlay.classList.contains('open'))closeAI()});

  $('tm-mobile-nav')?.addEventListener('click',e=>{
    const b=e.target.closest('[data-mobile-action="ai"]');if(!b)return;
    e.preventDefault();e.stopImmediatePropagation();openAI();
  },true);

  $('tm-ai-manual').onclick=()=>{
    closeAI();
    if(window.innerWidth<=820){
      if(confirm('OK : tracer sur la carte. Annuler : importer un fichier GPX.'))$('tm-create-btn')?.click();
      else $('tm-import-btn')?.click();
    }else $('tm-create-btn')?.click();
  };

  function showProgress(show){
    $('tm-ai-empty').style.display='none';$('tm-ai-content').innerHTML='';
    $('tm-ai-progress').classList.toggle('show',show);
    clearInterval(progressTimer);
    if(show){
      const steps=['Analyse de ta demande…','Recherche de lieux réels…','Vérification des points d’eau et nuitées…','Recherche des accès train et bus…','Calcul du tracé pédestre…','Vérification des étapes et des sources…'];
      let i=0;$('tm-ai-progress-text').textContent=steps[0];
      progressTimer=setInterval(()=>{$('tm-ai-progress-text').textContent=steps[++i%steps.length]},2400);
    }
  }

  function requestPayload(refineText=''){
    const basePrompt=String($('tm-ai-prompt').value||'').trim();
    return {
      prompt:refineText||basePrompt,
      region:String($('tm-ai-region').value||'').trim(),
      days:Number($('tm-ai-days').value||3),
      daily_km:Number($('tm-ai-km').value||18),
      difficulty:$('tm-ai-difficulty').value,
      route_type:$('tm-ai-route-type').value,
      require_transit:$('tm-ai-transit').checked,
      require_water:$('tm-ai-water').checked,
      require_accommodation:$('tm-ai-sleep').checked,
      require_food:$('tm-ai-food').checked,
      current_plan:refineText?currentPlan:null
    };
  }

  async function generate(payload){
    if(!payload.prompt||payload.prompt.length<8){typeof toast==='function'&&toast('Décris un peu plus le trek souhaité.');return}
    showProgress(true);shell.classList.add('has-result');$('tm-ai-generate').disabled=true;
    try{
      const r=await fetch(api()+'/ai/plan',{method:'POST',headers:authHeaders({'Content-Type':'application/json'},'POST'),body:JSON.stringify(payload)});
      const d=await r.json().catch(()=>({}));
      if(r.status===401){closeAI();$('tm-account-btn')?.click();throw new Error('Connecte-toi pour utiliser TrekMap AI.')}
      if(!r.ok)throw new Error(d.detail||'La préparation IA a échoué.');
      currentPlan=d;renderPlan(d);previewPlan(d,true);
    }catch(e){
      $('tm-ai-progress').classList.remove('show');
      $('tm-ai-content').innerHTML=`<div class="tm-ai-warning"><b>Impossible de préparer ce trek.</b><br>${esc(e.message||'Erreur inconnue')}</div>`;
    }finally{
      clearInterval(progressTimer);$('tm-ai-generate').disabled=false;
    }
  }

  $('tm-ai-generate').onclick=()=>generate(requestPayload());

  function waterLabel(status){return status==='potable_referenced'?['Eau potable référencée','tm-ai-water-ok']:status==='not_potable'?['Non potable','tm-ai-water-no']:['Potabilité non confirmée','tm-ai-water-unknown']}
  function sourceLink(s){const url=safeUrl(s?.url);return url?`<a class="tm-ai-source" href="${esc(url)}" target="_blank" rel="noopener noreferrer"><b>${esc(s.title||'Source')}</b><br>${esc(s.purpose||'')}</a>`:''}

  function renderPlan(p){
    $('tm-ai-progress').classList.remove('show');$('tm-ai-empty').style.display='none';
    const route=p.route_preview||{},stages=Array.isArray(p.stages)?p.stages:[],water=Array.isArray(p.water)?p.water:[],accom=Array.isArray(p.accommodations)?p.accommodations:[],pois=Array.isArray(p.points_of_interest)?p.points_of_interest:[],sources=Array.isArray(p.sources)?p.sources:[];
    const limitations=p.confidence?.limitations||[];
    $('tm-ai-content').innerHTML=`
      <div class="tm-ai-titlebar"><div><h2>${esc(p.title||'Trek proposé')}</h2><p>${esc(p.summary||'')}</p></div><button class="tm-ai-map-btn" id="tm-ai-back" type="button">← Modifier</button></div>
      <div class="tm-ai-badges"><span class="tm-ai-badge">${esc(p.region||'France')}</span><span class="tm-ai-badge">${esc(difficultyLabel[p.difficulty]||p.difficulty||'Moyen')}</span><span class="tm-ai-badge">${esc(p.route_type||'Trek')}</span><span class="tm-ai-badge">${esc(p.best_season||'Saison à vérifier')}</span></div>
      <div class="tm-ai-stats">
        <div class="tm-ai-stat"><small>Distance vérifiée</small><b>${Number(route.distance_km||0).toFixed(1)} km</b></div>
        <div class="tm-ai-stat"><small>Dénivelé +</small><b>${Math.round(route.elevation_gain_m||0)} m</b></div>
        <div class="tm-ai-stat"><small>Durée</small><b>${Number(p.duration_days||stages.length||0)} j</b></div>
        <div class="tm-ai-stat"><small>Confiance</small><b>${esc(p.confidence?.overall||'—')}</b></div>
      </div>
      ${route.warning?`<div class="tm-ai-warning"><b>Routage :</b> ${esc(route.warning)}</div>`:''}
      <section class="tm-ai-section"><h3>Étapes</h3>${stages.map(s=>`<article class="tm-ai-stage"><div class="tm-ai-stage-head"><b>Jour ${Number(s.day||0)} · ${esc(s.title||'Étape')}</b><span>${Number(s.distance_km||0).toFixed(1)} km · +${Math.round(s.elevation_gain_m||0)} m</span></div><p><b>${esc(s.from_name||'')}</b> → <b>${esc(s.to_name||'')}</b></p><p>🌙 ${esc(s.overnight||'À vérifier')}</p><p>🚰 ${esc(s.water_notes||'')}</p><p>🥖 ${esc(s.food_notes||'')}</p>${s.highlights?.length?`<p>🌄 ${s.highlights.map(esc).join(' · ')}</p>`:''}${s.safety_notes?`<p>⚠️ ${esc(s.safety_notes)}</p>`:''}</article>`).join('')}</section>
      ${water.length?`<section class="tm-ai-section"><h3>Eau</h3><div class="tm-ai-list">${water.map(w=>{const z=waterLabel(w.status);return `<div class="tm-ai-item"><b>${esc(w.name)}</b> · <span class="${z[1]}">${z[0]}</span><small>${esc(w.notes||'')}</small></div>`}).join('')}</div></section>`:''}
      ${accom.length?`<section class="tm-ai-section"><h3>Nuitées</h3><div class="tm-ai-list">${accom.map(a=>`<div class="tm-ai-item"><b>${esc(a.name)}</b> · ${esc(a.type)}<small>${esc(a.notes||'')}</small></div>`).join('')}</div></section>`:''}
      ${pois.length?`<section class="tm-ai-section"><h3>Points d'intérêt</h3><div class="tm-ai-list">${pois.slice(0,12).map(x=>`<div class="tm-ai-item"><b>${esc(x.name)}</b><small>${esc(x.type)}</small></div>`).join('')}</div></section>`:''}
      <section class="tm-ai-section"><h3>Transports</h3><div class="tm-ai-item"><b>Aller</b><small>${esc(p.transport?.outbound||'À vérifier')}</small></div><div class="tm-ai-item"><b>Retour</b><small>${esc(p.transport?.return||'À vérifier')}</small></div><div class="tm-ai-item"><small>${esc(p.transport?.notes||'')}</small></div></section>
      ${limitations.length?`<section class="tm-ai-section"><h3>À vérifier avant de partir</h3><div class="tm-ai-warning">${limitations.map(x=>'• '+esc(x)).join('<br>')}</div></section>`:''}
      ${sources.length?`<section class="tm-ai-section"><h3>Sources</h3>${sources.map(sourceLink).join('')}</section>`:''}
      <div class="tm-ai-refine-box"><b style="font-size:12px">Modifier avec l'IA</b><textarea id="tm-ai-refine-text" placeholder="Ex. raccourcis le jour 2, trouve une arrivée avec une gare, privilégie les campings..."></textarea><div class="tm-ai-refine-actions"><button id="tm-ai-refine" type="button">✨ Recalculer</button></div></div>
      <div class="tm-ai-actions"><button class="tm-ai-map-btn" id="tm-ai-preview" type="button">🗺️ Voir sur la carte</button><button id="tm-ai-save" type="button">Enregistrer dans TrekMap</button></div>`;
    $('tm-ai-back').onclick=()=>shell.classList.remove('has-result');
    $('tm-ai-preview').onclick=()=>{previewPlan(p,true);closeAI()};
    $('tm-ai-refine').onclick=()=>{const txt=String($('tm-ai-refine-text').value||'').trim();if(txt.length<5){typeof toast==='function'&&toast('Indique la modification souhaitée.');return}generate(requestPayload(txt))};
    $('tm-ai-save').onclick=savePlan;
  }

  function previewPlan(p,fit){
    const coords=p?.route_preview?.coords;if(!Array.isArray(coords)||coords.length<2)return;
    try{
      if(previewLayer)map.removeLayer(previewLayer);
      previewLayer=L.polyline(coords,{weight:6,opacity:.92,dashArray:'10 7'}).addTo(map);
      if(fit)map.fitBounds(previewLayer.getBounds(),{paddingTopLeft:[25,70],paddingBottomRight:[25,210],maxZoom:15,animate:true});
    }catch(e){console.warn('Aperçu IA indisponible',e)}
  }

  async function savePlan(){
    if(!currentPlan)return;
    const btn=$('tm-ai-save');btn.disabled=true;btn.textContent='Enregistrement…';
    try{
      const waypoints=(currentPlan.waypoints||[]).map(p=>[Number(p.lat),Number(p.lon)]).filter(p=>p.every(Number.isFinite));
      if(waypoints.length<2)throw new Error('Le plan ne contient pas assez de waypoints.');
      const description=[currentPlan.summary||'',...(currentPlan.stages||[]).map(s=>`Jour ${s.day}: ${s.title} — ${s.distance_km} km, +${s.elevation_gain_m} m.`)].join('\n');
      const r=await fetch(api()+'/treks/draw',{method:'POST',headers:authHeaders({'Content-Type':'application/json'},'POST'),body:JSON.stringify({
        name:currentPlan.title||'Trek IA',region:currentPlan.region||'Non renseignée',difficulty:currentPlan.difficulty||'medium',
        description,is_public:false,duration_days:Number(currentPlan.duration_days||1),coords:waypoints
      })});
      const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||'Création du trek impossible.');
      const extras={
        route_type:currentPlan.route_type||'',best_season:currentPlan.best_season||'',
        start_name:currentPlan.start?.name||'',end_name:currentPlan.end?.name||'',photos:[],
        points_of_interest:(currentPlan.points_of_interest||[]).slice(0,30).map(p=>({name:p.name||'Point',type:p.type||'Point',lat:Number(p.lat),lon:Number(p.lon)}))
      };
      await fetch(api()+`/treks/${Number(d.id)}/extras`,{method:'PUT',headers:authHeaders({'Content-Type':'application/json'},'PUT'),body:JSON.stringify(extras)});
      try{await loadTraces()}catch(_){}
      closeAI();if(typeof toast==='function')toast('Trek IA enregistré en privé. Vérifie-le puis publie-le quand il est prêt.');
      setTimeout(()=>{try{window.TrekMapOpenTrek?.(Number(d.id))}catch(_){}},120);
    }catch(e){if(typeof toast==='function')toast(e.message||'Enregistrement impossible.');}
    finally{if(btn){btn.disabled=false;btn.textContent='Enregistrer dans TrekMap'}}
  }

  window.TrekMapOpenAI=openAI;
})();
</script>
<!-- TREKMAP_AI_EXPERIENCE_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekMap AI experience applied")
