from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r'\s*<!-- TREKMAP_FUNCTIONAL_REPAIRS_START -->.*?<!-- TREKMAP_FUNCTIONAL_REPAIRS_END -->\s*',
    '\n', html, flags=re.S,
)

# La fiche produit récupère maintenant aussi les photos importées depuis l'appareil.
old_get_extras = "async function getExtras(id){try{const r=await fetch(api()+`/treks/${id}/extras`,{headers:getHeaders(),cache:'no-store'});if(!r.ok)return null;return await r.json()}catch(_){return null}}"
new_get_extras = "async function getExtras(id){try{const [r,p]=await Promise.all([fetch(api()+`/treks/${id}/extras`,{headers:getHeaders(),cache:'no-store'}),fetch(api()+`/treks/${id}/uploaded-photos`,{headers:getHeaders(),cache:'no-store'})]);if(!r.ok)return null;const d=await r.json();if(p.ok){const pd=await p.json();d.uploaded_photos=Array.isArray(pd.photos)?pd.photos:[]}return d}catch(_){return null}}"
html = html.replace(old_get_extras, new_get_extras)
html = html.replace(
    "const photo=Array.isArray(extras.photos)&&extras.photos[0]?extras.photos[0]:'';",
    "const photo=(Array.isArray(extras.uploaded_photos)&&extras.uploaded_photos[0]?.url)||((Array.isArray(extras.photos)&&extras.photos[0])?extras.photos[0]:'');",
)

block = r'''<!-- TREKMAP_FUNCTIONAL_REPAIRS_START -->
<style id="trekmap-functional-repairs-css">
/* Recherche enrichie */
#tm-advanced-filter-title{display:flex;align-items:center;gap:8px;margin:15px 0 8px;color:#345d4b;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase}
#tm-advanced-filter-title:after{content:"";height:1px;flex:1;background:#e4ede8}
#tm-advanced-filters{display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:10px;background:rgba(247,250,248,.92);border:1px solid #e1ebe5;border-radius:14px}
#tm-advanced-filters .tm-af-field{min-width:0}
#tm-advanced-filters .tm-af-field.tm-wide{grid-column:1/-1}
#tm-advanced-filters label{display:block;font-size:9px;text-transform:uppercase;letter-spacing:.045em;color:#567064;font-weight:850;margin:0 0 5px}
#tm-advanced-filters select,#tm-advanced-filters input{box-sizing:border-box;width:100%;height:39px;border:1px solid #d6e4dc;border-radius:10px;background:#fff;padding:0 9px;color:#244638;outline:0}
#tm-advanced-filters select:focus,#tm-advanced-filters input:focus{border-color:#58a77d;box-shadow:0 0 0 3px rgba(38,155,105,.09)}
.tm-stable-card .tm-criteria-line{display:flex;gap:5px;min-width:0;margin-top:5px;overflow:hidden}
.tm-stable-card .tm-criteria-chip{font-size:9px;line-height:1;border-radius:99px;padding:4px 6px;background:#f2f7f4;color:#527060;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:110px}

/* Photos locales */
.tm-local-photo-box{margin-top:12px;padding:12px;border:1px solid #dce8e1;border-radius:14px;background:#f7faf8}
.tm-local-photo-box>label{display:block;font-weight:850;color:#345d4b;font-size:11px;margin-bottom:7px}
#tm-local-photo-input{width:100%;border:1px dashed #9fc7b2;border-radius:12px;background:#fff;padding:12px;color:#456656}
.tm-local-photo-help{font-size:10px;color:#728078;margin-top:6px;line-height:1.4}
.tm-uploaded-photo-grid,#tm-local-previews{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.tm-uploaded-photo,.tm-local-preview{position:relative;aspect-ratio:4/3;border-radius:11px;overflow:hidden;background:#e8f1ec;border:1px solid #d7e5dd}
.tm-uploaded-photo img,.tm-local-preview img{width:100%;height:100%;object-fit:cover;display:block}
.tm-uploaded-photo button{position:absolute;top:5px;right:5px;width:27px;height:27px;border:0;border-radius:50%;background:rgba(20,35,28,.82);color:white;font-weight:900}
.tm-upload-progress{font-size:11px;color:#176b45;font-weight:800;margin-top:8px;display:none}

@media(max-width:760px){
  #tm-advanced-filters{grid-template-columns:1fr 1fr}
  .tm-uploaded-photo-grid,#tm-local-previews{grid-template-columns:repeat(3,1fr)}
}
@media(max-width:460px){
  #tm-advanced-filters{grid-template-columns:1fr}
  #tm-advanced-filters .tm-af-field.tm-wide{grid-column:auto}
  .tm-uploaded-photo-grid,#tm-local-previews{grid-template-columns:repeat(2,1fr)}
}
</style>
<script id="trekmap-functional-repairs-js">
(function(){
  const track=document.getElementById('tm-stable-track');
  const drawer=document.getElementById('tm-stable-drawer');
  const filters=document.querySelector('#sidebar .filters');
  const visibleSearch=document.getElementById('tm-stable-search');
  const hiddenSearch=document.getElementById('search');
  const title=document.getElementById('tm-stable-drawer-title');
  const count=document.getElementById('tm-stable-drawer-count');
  const suggestions=document.getElementById('tm-stable-suggestions');
  if(!track||!filters)return;

  const api=()=>typeof API!=='undefined'?API:'';
  const getHeaders=(extra={},method='GET')=>{try{return typeof headers==='function'?headers(extra,method):extra}catch(_){return extra}};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const normText=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const criteria=new Map();
  let criteriaLoaded=false;
  let criteriaLoading=false;
  let renderTimer=null;
  let lastCriteriaFetch=0;

  function all(){try{return Array.isArray(allTreks)?allTreks:[]}catch(_){return []}}
  function currentMode(){try{return typeof currentTab!=='undefined'?currentTab:'all'}catch(_){return'all'}}
  function user(){try{return currentUser||null}catch(_){return null}}
  function query(){return String(visibleSearch?.value||hiddenSearch?.value||'').trim()}
  function byId(id){return criteria.get(Number(id))||{route_type:'',best_season:'',start_name:'',end_name:'',points_of_interest:[],rating_average:0,rating_count:0,has_photo:false}}

  async function loadCriteria(force=false){
    const now=Date.now();if(criteriaLoading||(!force&&criteriaLoaded&&now-lastCriteriaFetch<4000))return;
    criteriaLoading=true;lastCriteriaFetch=now;
    try{
      const r=await fetch(api()+'/catalog/criteria',{headers:getHeaders(),cache:'no-store'});
      if(!r.ok)throw new Error('catalog');
      const d=await r.json();criteria.clear();
      (Array.isArray(d.items)?d.items:[]).forEach(x=>criteria.set(Number(x.id),x));
      criteriaLoaded=true;
    }catch(e){console.warn('Critères TrekMap indisponibles',e)}finally{criteriaLoading=false;scheduleRender(0)}
  }

  function installAdvancedFilters(){
    if(document.getElementById('tm-advanced-filters'))return;
    const actions=filters.querySelector('.filter-actions');
    const heading=document.createElement('div');heading.id='tm-advanced-filter-title';heading.textContent='Critères du trek';
    const box=document.createElement('div');box.id='tm-advanced-filters';box.innerHTML=`
      <div class="tm-af-field"><label>Type de parcours</label><select id="tm-route-filter"><option value="">Tous</option><option>Boucle</option><option>Aller-retour</option><option>Traversée</option><option>Itinérance</option></select></div>
      <div class="tm-af-field"><label>Saison</label><select id="tm-season-filter"><option value="">Toutes</option><option value="printemps">Printemps</option><option value="ete">Été</option><option value="automne">Automne</option><option value="hiver">Hiver</option></select></div>
      <div class="tm-af-field"><label>Note minimale</label><select id="tm-rating-filter"><option value="0">Toutes</option><option value="3">3★ et +</option><option value="4">4★ et +</option><option value="4.5">4,5★ et +</option></select></div>
      <div class="tm-af-field"><label>Photos</label><select id="tm-photo-filter"><option value="">Toutes</option><option value="yes">Avec photo</option><option value="no">Sans photo</option></select></div>
      <div class="tm-af-field tm-wide"><label>Départ, arrivée ou point d’intérêt</label><input id="tm-place-filter" type="search" placeholder="Ex. refuge, Chamonix, lac…" autocomplete="off"></div>`;
    if(actions){actions.before(heading,box)}else filters.append(heading,box);
    box.querySelectorAll('select,input').forEach(el=>{el.addEventListener('input',()=>scheduleRender(20));el.addEventListener('change',()=>scheduleRender(20))});
    document.getElementById('reset-filters')?.addEventListener('click',()=>setTimeout(()=>{box.querySelectorAll('select').forEach(x=>x.selectedIndex=0);const p=document.getElementById('tm-place-filter');if(p)p.value='';scheduleRender(30)},0));
  }

  function poitext(x){return Array.isArray(x.points_of_interest)?x.points_of_interest.map(p=>(p?.type||'')+' '+(p?.name||'')).join(' '):''}
  function searchHaystack(t,x){return normText([t.name,t.region,t.description,x.route_type,x.best_season,x.start_name,x.end_name,poitext(x)].join(' '))}

  function matches(t){
    const x=byId(t.id);const u=user();const mode=currentMode();
    if(mode==='favorites'&&!t.is_favorite)return false;
    if(mode==='mine'&&(!u||Number(t.owner_id)!==Number(u.id)))return false;
    if(mode==='private'&&(!u||Number(t.owner_id)!==Number(u.id)||t.is_public))return false;

    const region=document.getElementById('region-filter')?.value||'';
    const difficulty=document.getElementById('difficulty-filter')?.value||'';
    if(region&&normText(t.region)!==normText(region))return false;
    if(difficulty&&String(t.difficulty)!==difficulty)return false;

    const dist=Number(document.getElementById('distance-range')?.value||0);
    const distTol=Number(document.getElementById('distance-tolerance')?.value||0);
    if(dist>0&&Math.abs(Number(t.distance||0)-dist)>distTol)return false;
    const elev=Number(document.getElementById('elevation-range')?.value||0);
    const elevTol=Number(document.getElementById('elevation-tolerance')?.value||0);
    if(elev>0&&Math.abs(Number(t.elevation||0)-elev)>elevTol)return false;
    const duration=Number(document.getElementById('duration-filter')?.value||0);
    if(duration>0&&Number(t.duration_days||Infinity)>duration)return false;

    const route=document.getElementById('tm-route-filter')?.value||'';
    const season=document.getElementById('tm-season-filter')?.value||'';
    const rating=Number(document.getElementById('tm-rating-filter')?.value||0);
    const photo=document.getElementById('tm-photo-filter')?.value||'';
    const place=normText(document.getElementById('tm-place-filter')?.value||'');
    if(route&&normText(x.route_type)!==normText(route))return false;
    if(season&&!normText(x.best_season).includes(normText(season)))return false;
    if(rating>0&&Number(x.rating_average||0)<rating)return false;
    if(photo==='yes'&&!x.has_photo)return false;
    if(photo==='no'&&x.has_photo)return false;
    if(place&&!normText([x.start_name,x.end_name,poitext(x)].join(' ')).includes(place))return false;

    const tokens=normText(query()).split(/\s+/).filter(Boolean);
    if(tokens.length){const hay=searchHaystack(t,x);if(!tokens.every(token=>hay.includes(token)))return false}
    return true;
  }

  function score(t){
    const q=normText(query());if(!q)return 0;const x=byId(t.id);const name=normText(t.name);const hay=searchHaystack(t,x);
    if(name===q)return 100;if(name.startsWith(q))return 80;if(name.includes(q))return 60;if(hay.includes(q))return 30;return 10;
  }

  function sorted(data){
    const sort=document.getElementById('sort-filter')?.value||'relevance';
    return data.sort((a,b)=>{
      if(sort==='distance')return Number(a.distance||0)-Number(b.distance||0);
      if(sort==='elevation')return Number(a.elevation||0)-Number(b.elevation||0);
      if(sort==='duration')return Number(a.duration_days||Infinity)-Number(b.duration_days||Infinity);
      if(sort==='popular')return Number(b.view_count||0)-Number(a.view_count||0)||Number(b.favorite_count||0)-Number(a.favorite_count||0);
      if(query())return score(b)-score(a)||String(a.name||'').localeCompare(String(b.name||''),'fr');
      return Number(b.view_count||0)-Number(a.view_count||0)||Number(byId(b.id).rating_average||0)-Number(byId(a.id).rating_average||0)||String(a.name||'').localeCompare(String(b.name||''),'fr');
    });
  }

  function advancedActive(){return !!(document.getElementById('tm-route-filter')?.value||document.getElementById('tm-season-filter')?.value||Number(document.getElementById('tm-rating-filter')?.value||0)||document.getElementById('tm-photo-filter')?.value||document.getElementById('tm-place-filter')?.value)}
  function drawerTitle(){const mode=currentMode();if(query()||advancedActive())return 'Résultats de recherche';return ({favorites:'Mes favoris',mine:'Mes treks',private:'Mes treks privés'})[mode]||'Treks populaires'}

  function renderAdvancedSuggestions(data){
    if(!suggestions||!query())return;
    const rows=data.slice(0,6);if(!rows.length){suggestions.classList.remove('show');return}
    suggestions.innerHTML=rows.map(t=>'<button type="button" class="tm-stable-suggestion tm-advanced-suggestion" data-id="'+Number(t.id)+'"><b>'+esc(t.name||'Trek')+'</b><small>'+esc(t.region||'France')+' · '+Number(t.distance||0).toFixed(1)+' km</small></button>').join('');
    suggestions.classList.add('show');
  }

  function renderResults(){
    let data=sorted(all().filter(matches));
    try{filteredTreks=data.slice()}catch(_){}
    if(title)title.textContent=drawerTitle();if(count)count.textContent=data.length;
    if(!data.length){track.innerHTML='<div class="tm-stable-empty">Aucun trek ne correspond à tous les critères.</div>';renderAdvancedSuggestions([]);return}
    track.innerHTML=data.map(t=>{const x=byId(t.id);const chips=[];if(x.route_type)chips.push('<span class="tm-criteria-chip">'+esc(x.route_type)+'</span>');if(x.best_season)chips.push('<span class="tm-criteria-chip">'+esc(x.best_season)+'</span>');if(Number(x.rating_count||0)>0)chips.push('<span class="tm-criteria-chip">★ '+Number(x.rating_average||0).toFixed(1)+'</span>');return '<article class="tm-stable-card" data-id="'+Number(t.id)+'" role="button" tabindex="0"><div class="tm-stable-card-top"><strong>'+esc(t.name||'Trek')+'</strong><span>⌖</span></div><div class="tm-stable-region">'+esc(t.region||'France')+'</div><div class="tm-stable-badges"><span class="tm-stable-badge">'+esc(({easy:'Facile',medium:'Moyen',hard:'Difficile',extreme:'Extrême'}[t.difficulty]||'Moyen'))+'</span><span class="tm-stable-badge">'+(t.is_public?'Public':'Privé')+'</span></div><div class="tm-stable-meta"><span>📏 '+Number(t.distance||0).toFixed(1)+' km</span><span>↗ '+Math.round(t.elevation||0)+' m</span><span>⏱ '+(t.duration_days?Number(t.duration_days)+' j':'—')+'</span></div>'+(chips.length?'<div class="tm-criteria-line">'+chips.slice(0,3).join('')+'</div>':'')+'</article>'}).join('');
    renderAdvancedSuggestions(data);
  }
  function scheduleRender(delay=90){clearTimeout(renderTimer);renderTimer=setTimeout(renderResults,delay)}

  async function ensureTrek(id){
    const numericId=Number(id);let t=all().find(x=>Number(x.id)===numericId);
    if(t&&Array.isArray(t.coords)&&t.coords.length)return t;
    try{
      const r=await fetch(api()+'/treks/'+numericId,{headers:getHeaders(),cache:'no-store'});if(!r.ok)return t||null;const fresh=await r.json();
      if(t)Object.assign(t,fresh);else{try{allTreks.push(fresh);t=fresh}catch(_){t=fresh}}
      return t;
    }catch(_){return t||null}
  }

  async function openTrekRobust(id){
    const numericId=Number(id);if(!Number.isFinite(numericId))return false;
    const t=await ensureTrek(numericId);if(!t){if(typeof toast==='function')toast('Impossible de charger ce trek.');return false}
    try{if(typeof window.TrekMapBottomBarZoom==='function')await window.TrekMapBottomBarZoom(numericId)}catch(_){}
    try{
      if(typeof window.openDetail==='function'){window.openDetail(numericId);return true}
      if(typeof openDetail==='function'){openDetail(numericId);return true}
    }catch(e){console.error('Ouverture trek:',e)}
    if(typeof toast==='function')toast('La fiche du trek n’a pas pu être ouverte.');return false;
  }
  window.TrekMapOpenTrekRobust=openTrekRobust;

  // Capture au niveau document : elle passe avant les anciens listeners du tiroir.
  let pointerStart=null;let moved=false;
  document.addEventListener('pointerdown',e=>{const card=e.target.closest?.('#tm-stable-track .tm-stable-card');if(card){pointerStart={x:e.clientX,y:e.clientY};moved=false}},true);
  document.addEventListener('pointermove',e=>{if(pointerStart&&Math.hypot(e.clientX-pointerStart.x,e.clientY-pointerStart.y)>9)moved=true},true);
  document.addEventListener('pointerup',()=>setTimeout(()=>{pointerStart=null},0),true);
  document.addEventListener('click',e=>{const card=e.target.closest?.('#tm-stable-track .tm-stable-card');if(!card)return;e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();if(moved){moved=false;return}openTrekRobust(Number(card.dataset.id))},true);
  document.addEventListener('keydown',e=>{const card=e.target.closest?.('#tm-stable-track .tm-stable-card');if(!card||!(e.key==='Enter'||e.key===' '))return;e.preventDefault();e.stopImmediatePropagation();openTrekRobust(Number(card.dataset.id))},true);

  async function fetchExtrasAndPhotos(id){
    const [er,pr]=await Promise.all([fetch(api()+`/treks/${id}/extras`,{headers:getHeaders(),cache:'no-store'}),fetch(api()+`/treks/${id}/uploaded-photos`,{headers:getHeaders(),cache:'no-store'})]);
    const extras=er.ok?await er.json():{};const pd=pr.ok?await pr.json():{photos:[]};extras.uploaded_photos=Array.isArray(pd.photos)?pd.photos:[];return extras;
  }

  function localPhotoCard(p,id){return `<div class="tm-uploaded-photo" data-photo="${Number(p.id)}"><img src="${esc(p.url)}" alt="${esc(p.filename||'Photo')}" loading="lazy"><button type="button" data-delete-photo="${Number(p.id)}" title="Supprimer">×</button></div>`}

  async function openAdvancedLocal(id){
    if(typeof openModal!=='function')return;
    let extras={};try{extras=await fetchExtrasAndPhotos(id)}catch(_){}
    const photos=Array.isArray(extras.uploaded_photos)?extras.uploaded_photos:[];
    openModal(`<div class="modal-head"><div><h2>Informations du trek</h2><div style="color:#718078">Critères de recherche et photos.</div></div><button class="close" id="modal-close">✕</button></div><div class="tm-advanced-form"><div><label>Type de parcours</label><select id="tm-x-route"><option value="">Non renseigné</option>${['Boucle','Aller-retour','Traversée','Itinérance'].map(x=>`<option ${extras.route_type===x?'selected':''}>${x}</option>`).join('')}</select></div><div><label>Saison conseillée</label><input id="tm-x-season" maxlength="120" value="${esc(extras.best_season||'')}" placeholder="Ex. été, mai à octobre"></div><div><label>Départ</label><input id="tm-x-start" maxlength="180" value="${esc(extras.start_name||'')}"></div><div><label>Arrivée</label><input id="tm-x-end" maxlength="180" value="${esc(extras.end_name||'')}"></div><div class="full"><label>Points d’intérêt</label><textarea id="tm-x-pois" placeholder="Refuge | Refuge du col | 45.123,6.456">${esc((extras.points_of_interest||[]).map(p=>`${p.type||'Point'} | ${p.name||''}${Number.isFinite(Number(p.lat))?` | ${p.lat},${p.lon}`:''}`).join('\n'))}</textarea><div class="tm-help">Format : type | nom | latitude,longitude. Les points d’intérêt sont aussi pris en compte par la recherche.</div></div></div><div class="tm-local-photo-box"><label>Photos depuis tes fichiers</label><input id="tm-local-photo-input" type="file" accept="image/jpeg,image/png,image/webp" multiple><div class="tm-local-photo-help">JPG, PNG ou WEBP · 8 Mo maximum par image · 8 photos maximum par trek.</div><div class="tm-uploaded-photo-grid" id="tm-uploaded-photo-grid">${photos.map(p=>localPhotoCard(p,id)).join('')}</div><div id="tm-local-previews"></div><div class="tm-upload-progress" id="tm-upload-progress"></div></div><div class="modal-actions"><button class="ghost-btn" id="tm-x-cancel">Annuler</button><button class="primary-btn" id="tm-x-save">Enregistrer</button></div>`);
    document.getElementById('modal-close').onclick=closeModal;document.getElementById('tm-x-cancel').onclick=closeModal;
    const fileInput=document.getElementById('tm-local-photo-input');const previews=document.getElementById('tm-local-previews');
    fileInput?.addEventListener('change',()=>{previews.innerHTML='';[...(fileInput.files||[])].forEach(file=>{if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>8*1024*1024)return;const url=URL.createObjectURL(file);const box=document.createElement('div');box.className='tm-local-preview';box.innerHTML=`<img src="${url}" alt="Aperçu">`;previews.appendChild(box)})});
    document.getElementById('tm-uploaded-photo-grid')?.addEventListener('click',async e=>{const b=e.target.closest('[data-delete-photo]');if(!b)return;const pid=Number(b.dataset.deletePhoto);b.disabled=true;try{const r=await fetch(api()+`/treks/${id}/photos/${pid}`,{method:'DELETE',headers:getHeaders({},'DELETE')});if(!r.ok)throw 0;b.closest('.tm-uploaded-photo')?.remove();await loadCriteria(true)}catch(_){b.disabled=false;if(typeof toast==='function')toast('Impossible de supprimer la photo.')}});
    document.getElementById('tm-x-save').onclick=async()=>{
      const button=document.getElementById('tm-x-save');const progress=document.getElementById('tm-upload-progress');button.disabled=true;progress.style.display='block';progress.textContent='Enregistrement des informations…';
      const points=document.getElementById('tm-x-pois').value.split(/\n+/).map(line=>{const p=line.split('|').map(x=>x.trim());if(!p[1])return null;const out={type:p[0]||'Point',name:p[1]};if(p[2]){const c=p[2].split(',').map(Number);if(c.length===2&&c.every(Number.isFinite)){out.lat=c[0];out.lon=c[1]}}return out}).filter(Boolean);
      const payload={route_type:document.getElementById('tm-x-route').value,best_season:document.getElementById('tm-x-season').value,start_name:document.getElementById('tm-x-start').value,end_name:document.getElementById('tm-x-end').value,photos:Array.isArray(extras.photos)?extras.photos:[],points_of_interest:points};
      try{
        const meta=await fetch(api()+`/treks/${id}/extras`,{method:'PUT',headers:getHeaders({'Content-Type':'application/json'},'PUT'),body:JSON.stringify(payload)});const md=await meta.json().catch(()=>({}));if(!meta.ok)throw new Error(md.detail||'Impossible d’enregistrer les critères.');
        const files=[...(fileInput?.files||[])];for(let i=0;i<files.length;i++){const f=files[i];if(!['image/jpeg','image/png','image/webp'].includes(f.type))throw new Error('Une image n’est pas au format JPG, PNG ou WEBP.');if(f.size>8*1024*1024)throw new Error('Une photo dépasse 8 Mo.');progress.textContent=`Envoi photo ${i+1}/${files.length}…`;const fd=new FormData();fd.append('file',f);const r=await fetch(api()+`/treks/${id}/photos`,{method:'POST',headers:getHeaders({},'POST'),body:fd});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||'Envoi de la photo impossible.')}
        await loadCriteria(true);closeModal();if(typeof toast==='function')toast('Trek mis à jour.');setTimeout(()=>openTrekRobust(id),100);
      }catch(e){button.disabled=false;progress.textContent=e.message||'Erreur pendant l’enregistrement.';if(typeof toast==='function')toast(e.message||'Enregistrement impossible.')}
    };
  }

  // Remplace l'ancien éditeur d'URLs photo par un vrai sélecteur de fichiers.
  document.addEventListener('click',e=>{const b=e.target.closest?.('#tm-detail-advanced');if(!b)return;e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();let id=null;try{id=Number(currentDetail)}catch(_){}if(Number.isFinite(id))openAdvancedLocal(id)},true);

  installAdvancedFilters();
  visibleSearch?.addEventListener('input',()=>scheduleRender(180));
  hiddenSearch?.addEventListener('input',()=>scheduleRender(180));
  ['region-filter','difficulty-filter','duration-filter','sort-filter','distance-range','distance-tolerance','elevation-range','elevation-tolerance'].forEach(id=>{const el=document.getElementById(id);el?.addEventListener('input',()=>scheduleRender(70));el?.addEventListener('change',()=>scheduleRender(70))});
  document.addEventListener('click',e=>{if(e.target.closest?.('#tm-stable-favorites,#profile-fav,#profile-mine,.tab'))setTimeout(()=>scheduleRender(0),80)});
  const oldList=document.getElementById('trek-list');if(oldList)new MutationObserver(()=>scheduleRender(80)).observe(oldList,{childList:true,subtree:true});
  new MutationObserver(()=>{if(document.getElementById('tm-detail-upgrade'))loadCriteria(false)}).observe(document.getElementById('modal'),{childList:true,subtree:true});

  loadCriteria(true);setTimeout(()=>scheduleRender(0),300);
})();
</script>
<!-- TREKMAP_FUNCTIONAL_REPAIRS_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap functional repairs applied')
