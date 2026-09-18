from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r'\s*<!-- TREKMAP_PRODUCT_UPGRADE_START -->.*?<!-- TREKMAP_PRODUCT_UPGRADE_END -->\s*',
    '\n', html, flags=re.S,
)

block = r'''<!-- TREKMAP_PRODUCT_UPGRADE_START -->
<style id="trekmap-product-upgrade-css">
/* TrekMap 5.0 : détails, profil, mobile et états de production. */
#tm-product-status{position:absolute;z-index:6400;right:18px;bottom:16px;display:flex;align-items:center;gap:7px;background:rgba(255,255,255,.95);border:1px solid #d8e7df;border-radius:999px;padding:7px 10px;box-shadow:0 8px 24px rgba(17,58,39,.12);font-size:10px;font-weight:800;color:#4f665b;pointer-events:none}
#tm-product-status i{width:8px;height:8px;border-radius:50%;background:#27a36a;box-shadow:0 0 0 3px rgba(39,163,106,.12)}
#tm-product-status.is-offline i,#tm-product-status.is-error i{background:#c55258;box-shadow:0 0 0 3px rgba(197,82,88,.12)}
.tm-detail-upgrade{margin-top:16px;border-top:1px solid #e2ebe6;padding-top:15px}
.tm-detail-hero{height:190px;border-radius:18px;overflow:hidden;background:linear-gradient(135deg,#dcece3,#f2f8f5);margin:0 0 14px;display:grid;place-items:center;position:relative}.tm-detail-hero img{width:100%;height:100%;object-fit:cover}.tm-detail-hero-empty{font-size:13px;color:#5d7469;display:flex;align-items:center;gap:8px}.tm-detail-owner{font-size:12px;color:#708078;margin:5px 0 0}.tm-extra-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}.tm-extra-card{border:1px solid #e0eae4;background:#f8fbf9;border-radius:13px;padding:10px;min-height:60px}.tm-extra-card small{display:block;color:#718078;font-size:9px;text-transform:uppercase;letter-spacing:.05em;font-weight:850}.tm-extra-card b{display:block;margin-top:5px;font-size:12px;color:#244638}.tm-rating-box{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#f7faf8;border:1px solid #e0eae4;border-radius:14px;padding:10px 12px;margin:12px 0}.tm-stars{display:flex;gap:3px}.tm-star{border:0;background:transparent;font-size:22px;line-height:1;color:#c5d1cb;padding:1px 2px}.tm-star.is-on{color:#d39c21}.tm-rating-text{font-size:11px;color:#65746d}.tm-detail-actions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.tm-detail-actions button{border:1px solid #dce7e1;border-radius:11px;padding:9px 11px;background:#fff;color:#234d3a;font-weight:800}.tm-detail-actions button:hover{background:#edf7f1}.tm-pois{margin-top:12px}.tm-pois h4{margin:0 0 7px}.tm-poi-list{display:flex;flex-wrap:wrap;gap:6px}.tm-poi{font-size:10px;border:1px solid #dce8e1;border-radius:999px;padding:5px 8px;background:#f4f9f6;color:#406453}
.tm-profile-upgrade{margin-top:15px;border-top:1px solid #e1ebe5;padding-top:15px}.tm-profile-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.tm-profile-card{background:#f5faf7;border:1px solid #deebe4;border-radius:14px;padding:10px}.tm-profile-card small{display:block;color:#718078;font-size:9px;text-transform:uppercase}.tm-profile-card b{display:block;font-size:17px;margin-top:4px}.tm-library{margin-top:14px;display:grid;grid-template-columns:1fr 1fr;gap:10px}.tm-library-section{border:1px solid #e0e9e4;border-radius:14px;padding:10px;background:#fff}.tm-library-section h4{margin:0 0 8px;font-size:12px}.tm-library-row{border:0;background:#f7faf8;border-radius:10px;width:100%;text-align:left;padding:8px 9px;margin-top:5px;color:#244638}.tm-library-row:hover{background:#edf6f1}.tm-library-row b{display:block;font-size:11px}.tm-library-row small{font-size:9px;color:#74827b}
.tm-advanced-form{display:grid;grid-template-columns:1fr 1fr;gap:10px}.tm-advanced-form label{display:block;font-size:10px;font-weight:800;color:#62736b;margin-bottom:5px;text-transform:uppercase}.tm-advanced-form input,.tm-advanced-form select,.tm-advanced-form textarea{width:100%;border:1px solid #d8e4dd;border-radius:10px;padding:9px;background:#fff}.tm-advanced-form textarea{min-height:76px;resize:vertical}.tm-advanced-form .full{grid-column:1/-1}.tm-help{font-size:10px;color:#76867e;margin-top:5px;line-height:1.45}
.tm-import-preview{padding:12px;border:1px solid #dbe8e1;background:#f7faf8;border-radius:14px;margin:12px 0}.tm-import-preview strong{display:block}.tm-import-preview small{color:#6e7d75}.tm-mobile-sheet-handle{display:none}
@media(max-width:760px){
  #tm-product-status{display:none}.modal-backdrop{padding:0!important;align-items:flex-end!important}.modal{width:100%!important;max-height:92vh!important;border-radius:22px 22px 0 0!important;padding:16px!important}.tm-mobile-sheet-handle{display:block;width:48px;height:5px;background:#c7d7cf;border-radius:99px;margin:0 auto 12px}.detail-grid,.tm-extra-grid,.tm-profile-cards{grid-template-columns:1fr 1fr!important}.tm-library{grid-template-columns:1fr}.tm-detail-hero{height:150px}.tm-advanced-form{grid-template-columns:1fr}.tm-advanced-form .full{grid-column:auto}.tm-detail-actions button{flex:1 1 45%}.comments-list{max-height:210px!important}
  #tm-stable-drawer{height:170px!important}.tm-stable-card{flex-basis:min(78vw,280px)!important}.tm-drawer-head{padding:0 11px!important}.tm-drawer-title{max-width:50vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
}
@media(max-width:460px){.detail-grid,.tm-extra-grid,.tm-profile-cards{grid-template-columns:1fr 1fr!important}.tm-stable-actions button{min-width:38px}.tm-detail-actions button{flex-basis:100%}}
</style>
<script id="trekmap-product-upgrade-js">
(function(){
  const app=document.getElementById('app');
  if(!app)return;
  const api=()=>typeof API!=='undefined'?API:'';
  const getHeaders=(extra={},method='GET')=>{try{return typeof headers==='function'?headers(extra,method):extra}catch(_){return extra}};
  const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  let selectedMarkers=[];

  // Etat global de production et erreurs réseau compréhensibles.
  const status=document.createElement('div');
  status.id='tm-product-status';status.innerHTML='<i></i><span>TrekMap prêt</span>';app.appendChild(status);
  function setStatus(label,kind='ok'){status.className=kind==='ok'?'':'is-'+kind;status.querySelector('span').textContent=label}
  window.addEventListener('offline',()=>setStatus('Hors connexion','offline'));
  window.addEventListener('online',()=>{setStatus('Connexion rétablie');setTimeout(checkReady,300)});
  window.addEventListener('unhandledrejection',e=>{console.error('TrekMap promise:',e.reason);setStatus('Une fonction a rencontré une erreur','error')});
  window.addEventListener('error',e=>{if(e?.message){console.error('TrekMap UI:',e.message)}});
  async function checkReady(){try{const r=await fetch(api()+'/health/ready',{cache:'no-store'});const d=await r.json();setStatus(d.status==='ok'?'TrekMap prêt':'Service dégradé',d.status==='ok'?'ok':'error')}catch(_){setStatus('API indisponible','error')}}
  setTimeout(checkReady,900);

  function clearSelectedMarkers(){selectedMarkers.forEach(x=>{try{map.removeLayer(x)}catch(_){}});selectedMarkers=[]}
  function coordsFor(t){if(!t)return[];if(Array.isArray(t.coords)&&t.coords.length)return t.coords;try{if(t.geometry&&typeof geometryToLeaflet==='function')return geometryToLeaflet(t.geometry)}catch(_){}return[]}
  function showEndpoints(id){
    clearSelectedMarkers();
    let t=null;try{t=allTreks.find(x=>Number(x.id)===Number(id))}catch(_){}
    const coords=coordsFor(t);if(coords.length<2||typeof L==='undefined'||!map)return;
    const start=L.circleMarker(coords[0],{radius:7,color:'#0c6b45',weight:3,fillColor:'#fff',fillOpacity:1}).addTo(map).bindTooltip('Départ');
    const end=L.circleMarker(coords[coords.length-1],{radius:7,color:'#a74046',weight:3,fillColor:'#fff',fillOpacity:1}).addTo(map).bindTooltip('Arrivée');
    selectedMarkers=[start,end];
  }

  async function getExtras(id){try{const r=await fetch(api()+`/treks/${id}/extras`,{headers:getHeaders(),cache:'no-store'});if(!r.ok)return null;return await r.json()}catch(_){return null}}
  async function rateTrek(id,value){
    try{const r=await fetch(api()+`/treks/${id}/rating`,{method:'PUT',headers:getHeaders({'Content-Type':'application/json'},'PUT'),body:JSON.stringify({value})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Erreur');await enhanceDetail(id);if(typeof toast==='function')toast('Note enregistrée.')}catch(e){if(!window.currentUser&&typeof authModal==='function')authModal('login');else if(typeof toast==='function')toast(e.message||'Impossible de noter ce trek.')}
  }

  async function enhanceDetail(id){
    const modal=document.getElementById('modal');if(!modal||!document.getElementById('fav-detail'))return;
    modal.querySelector('.tm-detail-upgrade')?.remove();
    if(!modal.querySelector('.tm-mobile-sheet-handle'))modal.prepend(Object.assign(document.createElement('div'),{className:'tm-mobile-sheet-handle'}));
    let t=null;try{t=allTreks.find(x=>Number(x.id)===Number(id))}catch(_){}
    if(!t)return;
    const extras=await getExtras(id)||{rating:{average:0,count:0,mine:null},photos:[],points_of_interest:[]};
    const wrap=document.createElement('section');wrap.className='tm-detail-upgrade';
    const photo=Array.isArray(extras.photos)&&extras.photos[0]?extras.photos[0]:'';
    const rating=extras.rating||{average:0,count:0,mine:null};
    const stars=[1,2,3,4,5].map(v=>`<button type="button" class="tm-star ${v<=Math.round(Number(rating.mine||rating.average||0))?'is-on':''}" data-rate="${v}" title="Noter ${v}/5">★</button>`).join('');
    const pois=(extras.points_of_interest||[]).map(p=>`<span class="tm-poi">${escapeHtml(p.type||'Point')} · ${escapeHtml(p.name)}</span>`).join('');
    const owner=t.owner_username?`Créé par ${escapeHtml(t.owner_username)}`:'Créateur non renseigné';
    wrap.innerHTML=`
      <div class="tm-detail-hero">${photo?`<img src="${escapeHtml(photo)}" alt="Photo du trek" loading="lazy" referrerpolicy="no-referrer">`:'<div class="tm-detail-hero-empty">🥾 <span>Ajoute une photo de couverture dans les infos avancées.</span></div>'}</div>
      <div class="tm-detail-owner">${owner} · ${Number(t.view_count||0)} vue${Number(t.view_count||0)>1?'s':''}</div>
      <div class="tm-extra-grid">
        <div class="tm-extra-card"><small>Parcours</small><b>${escapeHtml(extras.route_type||'Non renseigné')}</b></div>
        <div class="tm-extra-card"><small>Saison</small><b>${escapeHtml(extras.best_season||'Toute l’année')}</b></div>
        <div class="tm-extra-card"><small>Départ</small><b>${escapeHtml(extras.start_name||'Début de trace')}</b></div>
        <div class="tm-extra-card"><small>Arrivée</small><b>${escapeHtml(extras.end_name||'Fin de trace')}</b></div>
      </div>
      <div class="tm-rating-box"><div class="tm-stars">${stars}</div><div class="tm-rating-text"><b>${Number(rating.average||0).toFixed(1)}/5</b> · ${Number(rating.count||0)} avis${rating.mine?' · ta note : '+rating.mine+'/5':''}</div></div>
      <div class="tm-detail-actions"><button type="button" id="tm-detail-map">⌖ Voir toute la trace</button><button type="button" id="tm-detail-plan">✓ Préparer</button><button type="button" id="tm-detail-download">⇩ Télécharger GPX</button>${currentUser&&(currentUser.is_admin||t.owner_id==null||Number(t.owner_id)===Number(currentUser.id))?'<button type="button" id="tm-detail-advanced">⚙ Infos avancées</button>':''}</div>
      ${pois?`<div class="tm-pois"><h4>Points d’intérêt</h4><div class="tm-poi-list">${pois}</div></div>`:''}`;
    const comments=modal.querySelector('.comments');if(comments)comments.before(wrap);else modal.appendChild(wrap);
    wrap.querySelectorAll('[data-rate]').forEach(b=>b.onclick=()=>rateTrek(id,Number(b.dataset.rate)));
    document.getElementById('tm-detail-map')?.addEventListener('click',()=>{closeModal();showEndpoints(id);const fn=window.TrekMapBottomBarZoom||window.TrekMapZoomToTrek;if(typeof fn==='function')fn(id)});
    document.getElementById('tm-detail-plan')?.addEventListener('click',()=>{if(typeof openPlan==='function')openPlan(id)});
    document.getElementById('tm-detail-download')?.addEventListener('click',()=>{if(typeof exportGPX==='function')exportGPX(id)});
    document.getElementById('tm-detail-advanced')?.addEventListener('click',()=>openAdvancedInfo(id,extras));
    showEndpoints(id);
  }

  function openAdvancedInfo(id,extras){
    const photos=Array.isArray(extras.photos)?extras.photos.join('\n'):'';
    const pois=Array.isArray(extras.points_of_interest)?extras.points_of_interest.map(p=>`${p.type||'Point'} | ${p.name}${Number.isFinite(Number(p.lat))?` | ${p.lat},${p.lon}`:''}`).join('\n'):'';
    openModal(`<div class="modal-head"><div><h2>Infos avancées</h2><div style="color:#718078">Complète la fiche sans modifier la trace.</div></div><button class="close" id="modal-close">✕</button></div><div class="tm-advanced-form"><div><label>Type de parcours</label><select id="tm-x-route"><option value="">Non renseigné</option>${['Boucle','Aller-retour','Traversée','Itinérance'].map(x=>`<option ${extras.route_type===x?'selected':''}>${x}</option>`).join('')}</select></div><div><label>Saison conseillée</label><input id="tm-x-season" maxlength="120" value="${escapeHtml(extras.best_season||'')}"></div><div><label>Départ</label><input id="tm-x-start" maxlength="180" value="${escapeHtml(extras.start_name||'')}"></div><div><label>Arrivée</label><input id="tm-x-end" maxlength="180" value="${escapeHtml(extras.end_name||'')}"></div><div class="full"><label>Photos HTTPS</label><textarea id="tm-x-photos" placeholder="Une URL https:// par ligne">${escapeHtml(photos)}</textarea><div class="tm-help">Jusqu’à 8 photos. Les images restent hébergées sur leur service d’origine.</div></div><div class="full"><label>Points d’intérêt</label><textarea id="tm-x-pois" placeholder="Refuge | Refuge du col | 45.123,6.456">${escapeHtml(pois)}</textarea><div class="tm-help">Format : type | nom | latitude,longitude. Les coordonnées sont facultatives.</div></div></div><div class="modal-actions"><button class="ghost-btn" id="tm-x-cancel">Annuler</button><button class="primary-btn" id="tm-x-save">Enregistrer</button></div>`);
    document.getElementById('modal-close').onclick=closeModal;document.getElementById('tm-x-cancel').onclick=closeModal;
    document.getElementById('tm-x-save').onclick=async()=>{
      const points=document.getElementById('tm-x-pois').value.split(/\n+/).map(line=>{const p=line.split('|').map(x=>x.trim());if(!p[1])return null;const out={type:p[0]||'Point',name:p[1]};if(p[2]){const c=p[2].split(',').map(Number);if(c.length===2&&c.every(Number.isFinite)){out.lat=c[0];out.lon=c[1]}}return out}).filter(Boolean);
      const payload={route_type:document.getElementById('tm-x-route').value,best_season:document.getElementById('tm-x-season').value,start_name:document.getElementById('tm-x-start').value,end_name:document.getElementById('tm-x-end').value,photos:document.getElementById('tm-x-photos').value.split(/\n+/).map(x=>x.trim()).filter(Boolean),points_of_interest:points};
      try{const r=await fetch(api()+`/treks/${id}/extras`,{method:'PUT',headers:getHeaders({'Content-Type':'application/json'},'PUT'),body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Erreur');closeModal();openDetail(id);if(typeof toast==='function')toast('Fiche enrichie.')}catch(e){if(typeof toast==='function')toast(e.message||'Impossible d’enregistrer.')}
    };
  }

  // La fiche d'origine reste la source fonctionnelle. On l'enrichit après son rendu.
  const originalOpenDetail=window.openDetail;
  if(typeof originalOpenDetail==='function')window.openDetail=function(id){originalOpenDetail(id);setTimeout(()=>enhanceDetail(id),40)};

  // Profil complet : statistiques + bibliothèque personnelle.
  async function enhanceProfile(){
    const modal=document.getElementById('modal');if(!modal||!document.getElementById('profile-logout'))return;
    modal.querySelector('.tm-profile-upgrade')?.remove();
    const wrap=document.createElement('section');wrap.className='tm-profile-upgrade';wrap.innerHTML='<div style="color:#718078;font-size:12px">Chargement de ta bibliothèque…</div>';modal.appendChild(wrap);
    try{
      const [statsR,libR]=await Promise.all([fetch(api()+'/auth/statistics',{headers:getHeaders(),cache:'no-store'}),fetch(api()+'/auth/library',{headers:getHeaders(),cache:'no-store'})]);
      const stats=statsR.ok?await statsR.json():{};const lib=libR.ok?await libR.json():{};const s=stats.treks||{};
      const rows=(items,empty)=>Array.isArray(items)&&items.length?items.slice(0,6).map(x=>`<button class="tm-library-row" data-open="${Number(x.id)}"><b>${escapeHtml(x.name)}</b><small>${escapeHtml(x.region||'France')} · ${Number(x.distance||0).toFixed(1)} km</small></button>`).join(''):`<div style="font-size:10px;color:#718078">${empty}</div>`;
      wrap.innerHTML=`<div class="tm-profile-cards"><div class="tm-profile-card"><small>Distance créée</small><b>${Number(s.distance_km||0).toFixed(1)} km</b></div><div class="tm-profile-card"><small>Vues reçues</small><b>${Number(s.views||0)}</b></div><div class="tm-profile-card"><small>Préparations</small><b>${Number(stats.plans||0)}</b></div><div class="tm-profile-card"><small>Notes données</small><b>${Number(lib.ratings||0)}</b></div></div><div class="tm-library"><div class="tm-library-section"><h4>Mes derniers treks</h4>${rows(lib.mine,'Aucun trek créé.')}</div><div class="tm-library-section"><h4>Mes favoris</h4>${rows(lib.favorites,'Aucun favori.')}</div><div class="tm-library-section"><h4>Treks préparés</h4>${rows(lib.plans,'Aucune préparation.')}</div><div class="tm-library-section"><h4>Activité</h4><div style="font-size:11px;color:#607169;line-height:1.7">⭐ ${Number(stats.favorites_received||0)} favori(s) reçu(s)<br>💬 ${Number(stats.comments_received||0)} commentaire(s) reçu(s)<br>↗ ${Number(s.elevation_m||0)} m de dénivelé cumulés</div></div></div>`;
      wrap.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>openDetail(Number(b.dataset.open)));
    }catch(_){wrap.innerHTML='<div style="color:#8a5558;font-size:11px">Bibliothèque temporairement indisponible.</div>'}
  }
  const originalOpenProfile=window.openProfile;
  if(typeof originalOpenProfile==='function')window.openProfile=function(){originalOpenProfile();setTimeout(enhanceProfile,100)};

  // Import GPX avec vraie étape de confirmation et retour direct vers l'édition.
  function installImportPreview(){
    const old=document.getElementById('gpx-file');if(!old||old.dataset.tmV5==='1')return;
    const input=old.cloneNode(true);input.dataset.tmV5='1';old.replaceWith(input);
    window.importGPX=function(){if(!currentUser){authModal('login');return}input.value='';input.click()};
    input.addEventListener('change',()=>{
      const file=input.files?.[0];if(!file)return;
      const mb=file.size/1024/1024;if(!/\.gpx$/i.test(file.name)){toast('Choisis un fichier .gpx');return}if(mb>25){toast('Ce GPX dépasse 25 Mo.');return}
      openModal(`<div class="modal-head"><div><h2>Importer un trek</h2><div style="color:#718078">Vérifie le fichier avant de l’ajouter.</div></div><button class="close" id="modal-close">✕</button></div><div class="tm-import-preview"><strong>${escapeHtml(file.name)}</strong><small>${mb.toFixed(2)} Mo · format GPX</small></div><p style="font-size:12px;color:#5f7067">Le trek sera importé en privé. Tu pourras ensuite renseigner la région, la difficulté, la description et décider de le rendre public.</p><div class="modal-actions"><button class="ghost-btn" id="tm-import-cancel">Annuler</button><button class="primary-btn" id="tm-import-confirm">Importer maintenant</button></div>`);
      document.getElementById('modal-close').onclick=closeModal;document.getElementById('tm-import-cancel').onclick=closeModal;
      document.getElementById('tm-import-confirm').onclick=async()=>{
        const btn=document.getElementById('tm-import-confirm');btn.disabled=true;btn.textContent='Import en cours…';
        try{const fd=new FormData();fd.append('file',file);const r=await fetch(api()+'/upload-gpx',{method:'POST',headers:getHeaders({},'POST'),body:fd});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Import impossible');closeModal();await loadTraces();if(typeof toast==='function')toast(d.message||'GPX importé.');setTimeout(()=>openEdit(Number(d.id)),120)}catch(e){btn.disabled=false;btn.textContent='Importer maintenant';if(typeof toast==='function')toast(e.message||'Import impossible.')}
      };
    });
  }
  installImportPreview();

  // Aide contextuelle sur les formulaires de création/modification existants.
  const modal=document.getElementById('modal');
  if(modal)new MutationObserver(()=>{
    if(document.getElementById('f-name')&&!document.getElementById('tm-form-help')){
      const grid=modal.querySelector('.form-grid');if(grid){const help=document.createElement('div');help.id='tm-form-help';help.className='full';help.style.cssText='background:#edf7f1;border:1px solid #d9ebe1;border-radius:12px;padding:9px 11px;color:#496457;font-size:11px';help.textContent='Conseil : donne un nom précis, vérifie la région et la durée. Les infos avancées (saison, type de parcours, photos, points d’intérêt) se complètent ensuite depuis la fiche du trek.';grid.appendChild(help)}
    }
  }).observe(modal,{childList:true,subtree:true});

  // Bouton de recentrage utile quand une fiche a ajouté les marqueurs départ/arrivée.
  document.addEventListener('click',e=>{if(e.target.closest?.('[data-map-action="fit"]'))clearSelectedMarkers()},true);
})();
</script>
<!-- TREKMAP_PRODUCT_UPGRADE_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap product upgrade applied')
