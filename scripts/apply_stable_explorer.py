from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(r'\s*<!-- TREKMAP_STABLE_EXPLORER_START -->.*?<!-- TREKMAP_STABLE_EXPLORER_END -->\s*', '\n', html, flags=re.S)

block = r'''<!-- TREKMAP_STABLE_EXPLORER_START -->
<style id="trekmap-stable-explorer-css">
:root{--tm-top:82px;--tm-left:390px}
html,body{height:100%;overflow:hidden!important}
#app{position:relative!important;display:block!important;height:100vh!important;padding-top:var(--tm-top)!important;background:#e7f0eb!important}
#map{position:absolute!important;inset:var(--tm-top) 0 0 0!important;width:100%!important;height:auto!important;min-width:0!important}
#bottom-nav{display:none!important}

/* top bar */
#tm-stable-topbar{position:absolute;z-index:6200;left:0;right:0;top:0;height:var(--tm-top);display:grid;grid-template-columns:330px minmax(320px,560px) 1fr;align-items:center;gap:22px;padding:9px 24px;background:linear-gradient(105deg,#074a34,#0a6546 58%,#07513a);box-shadow:0 8px 26px rgba(7,45,30,.23)}
#tm-stable-home{border:0;background:transparent;padding:0;display:flex;align-items:center;text-align:left;color:#fff;cursor:pointer;min-width:0}
.tm-stable-brand{display:flex;align-items:center;gap:12px;min-width:0}.tm-stable-brand svg{width:88px;height:50px;flex:0 0 88px;filter:drop-shadow(0 3px 7px rgba(0,0,0,.16))}.tm-stable-copy{display:flex;flex-direction:column;line-height:1}.tm-stable-copy strong{font-size:27px;letter-spacing:-.045em;white-space:nowrap}.tm-stable-copy strong em{font-style:normal;color:#43cf88}.tm-stable-copy small{margin-top:6px;font-size:11px;color:rgba(255,255,255,.72);white-space:nowrap}
#tm-stable-search-wrap{position:relative;height:50px;background:#fff;border-radius:999px;display:flex;align-items:center;box-shadow:0 8px 24px rgba(0,0,0,.14);z-index:2}
#tm-stable-search-wrap .tm-search-icon{padding-left:17px;color:#325f4d;font-size:18px}#tm-stable-search{width:100%;height:100%;border:0;outline:0;background:transparent;padding:0 44px 0 10px;font-size:14px;color:#17372b}#tm-stable-search-clear{position:absolute;right:8px;top:8px;width:34px;height:34px;border:0;border-radius:50%;background:transparent;color:#71837a;font-size:20px;display:none}#tm-stable-search-clear.show{display:block}#tm-stable-search-clear:hover{background:#edf5f0;color:#176b45}
#tm-stable-suggestions{position:absolute;left:7px;right:7px;top:57px;background:rgba(255,255,255,.99);border:1px solid #d8e6de;border-radius:15px;box-shadow:0 18px 44px rgba(10,48,31,.2);padding:7px;display:none;max-height:330px;overflow:auto}#tm-stable-suggestions.show{display:block}.tm-stable-suggestion{width:100%;border:0;background:transparent;border-radius:10px;padding:10px 11px;display:flex;justify-content:space-between;gap:14px;text-align:left;color:#17372b}.tm-stable-suggestion:hover{background:#edf7f1}.tm-stable-suggestion b{font-size:13px}.tm-stable-suggestion small{font-size:10px;color:#718078;white-space:nowrap}
#tm-stable-actions{display:flex;justify-content:flex-end;align-items:center;gap:10px;min-width:0}#tm-stable-actions button{height:45px;border-radius:999px;padding:0 17px;border:1px solid rgba(255,255,255,.42);background:rgba(255,255,255,.08);color:#fff;font-weight:800;display:flex;align-items:center;gap:8px;white-space:nowrap}#tm-stable-actions button:hover{background:rgba(255,255,255,.16)}#tm-stable-explore{background:#1b9d67!important;border-color:#37b97f!important}#tm-stable-account{border-color:transparent!important;background:transparent!important;padding-left:8px!important}.tm-stable-avatar{width:35px;height:35px;border-radius:50%;display:grid;place-items:center;background:#1a9b66;border:1px solid rgba(255,255,255,.2);font-weight:900}#tm-stable-account-name{max-width:120px;overflow:hidden;text-overflow:ellipsis}

/* floating filters only, map remains visible underneath */
.sidebar{position:absolute!important;z-index:2500!important;left:16px!important;top:calc(var(--tm-top) + 16px)!important;width:var(--tm-left)!important;min-width:var(--tm-left)!important;height:auto!important;max-height:calc(100vh - var(--tm-top) - 32px)!important;margin:0!important;padding:0!important;background:transparent!important;border:0!important;box-shadow:none!important;overflow:visible!important;display:block!important}
.sidebar.collapsed{transform:translateX(calc(-100% - 28px))!important;margin:0!important}
#sidebar .brand,#sidebar .account,#sidebar .search-wrap,#sidebar .tabs,#sidebar .list-head,#sidebar #trek-list{display:none!important}
#sidebar .filters{position:relative!important;display:block!important;width:100%!important;max-height:min(520px,calc(100vh - var(--tm-top) - 32px))!important;overflow:auto!important;margin:0!important;padding:58px 16px 16px!important;background:rgba(255,255,255,.97)!important;backdrop-filter:blur(18px)!important;border:1px solid #d7e6de!important;border-radius:22px!important;box-shadow:0 16px 44px rgba(10,50,33,.16)!important}
#sidebar .filters:before{content:"☷  Filtres"!important;position:absolute!important;left:19px!important;top:18px!important;font-size:15px!important;font-weight:900!important;color:#153d2d!important}
#sidebar .filters:after{content:""!important}.filter-row{gap:12px!important}.field label{font-size:10px!important;text-transform:uppercase!important;letter-spacing:.045em!important;color:#567064!important;font-weight:850!important;margin:10px 0 6px!important}.field select,.field input{background:#fbfdfc!important;border:1px solid #d6e4dc!important;border-radius:12px!important;min-height:42px!important}.field select:focus,.field input:focus{outline:0!important;border-color:#58a77d!important;box-shadow:0 0 0 3px rgba(38,155,105,.09)!important}input[type=range]{accent-color:#188d5d!important}.filter-actions{gap:9px!important;margin-top:15px!important}.filter-actions button{min-height:41px!important;border-radius:12px!important;font-weight:800!important}.filter-actions #create-button{display:none!important}.filter-actions #reset-filters{background:#f4f8f6!important;border:1px solid #dce8e1!important}.filter-actions #upload-button{background:#eaf6ef!important;color:#176b45!important;border:1px solid #d4eadd!important}

/* leaflet controls and map options */
.leaflet-left{left:416px!important}.leaflet-top{top:12px!important}.map-tools{position:absolute!important;left:auto!important;right:16px!important;top:16px!important;z-index:2800!important;display:block!important;max-width:250px!important}#tm-map-options{height:46px!important;min-width:108px!important;border:1px solid #d6e4dc!important;border-radius:14px!important;background:rgba(255,255,255,.97)!important;box-shadow:0 9px 26px rgba(15,50,34,.14)!important;padding:0 15px!important;color:#173e2d!important;font-weight:850!important}#tm-map-options-panel{position:absolute!important;top:54px!important;left:auto!important;right:0!important;width:232px!important;max-width:calc(100vw - 32px)!important;max-height:300px!important;overflow:auto!important;border-radius:17px!important;background:rgba(255,255,255,.99)!important;box-shadow:0 18px 44px rgba(12,47,31,.22)!important;padding:11px!important}#tm-map-options-panel button,#tm-map-options-panel select{width:100%!important;min-height:40px!important;border:1px solid #dce7e1!important;border-radius:11px!important;background:#fff!important;margin-bottom:7px!important;padding:8px 10px!important}
.map-legend{right:16px!important;bottom:205px!important}

/* right quick actions */
#tm-stable-side{position:absolute;z-index:2450;right:16px;top:275px;display:flex;flex-direction:column;gap:10px}#tm-stable-side button{width:74px;min-height:74px;border:1px solid #d8e6df;border-radius:19px;background:rgba(255,255,255,.96);box-shadow:0 10px 26px rgba(14,50,34,.15);color:#315548;padding:8px 5px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px}#tm-stable-side button:hover{transform:translateX(-2px);border-color:#96c4aa}.tm-stable-side-icon{width:32px;height:32px;border-radius:10px;background:#e7f4ec;color:#176b45;display:grid;place-items:center;font-size:17px;font-weight:900}#tm-stable-side b{font-size:11px}#tm-stable-side small{font-size:9px;color:#7b8a83}
body.tm-map-menu-open #tm-stable-side{top:430px}

/* bottom results */
#tm-stable-drawer{position:absolute;z-index:2400;left:424px;right:16px;bottom:14px;height:184px;transition:height .28s cubic-bezier(.2,.8,.2,1);pointer-events:auto}#tm-stable-drawer.collapsed{height:45px}#tm-stable-drawer .tm-drawer-shell{position:absolute;inset:0;background:rgba(252,254,253,.97);backdrop-filter:blur(18px);border:1px solid #d7e5dd;border-radius:22px;box-shadow:0 15px 42px rgba(14,51,34,.18);overflow:hidden}.tm-drawer-head{height:45px;width:100%;border:0;background:transparent;display:flex;align-items:center;gap:11px;padding:0 17px;color:#183c2d;text-align:left}.tm-drawer-grip{width:38px;height:4px;border-radius:99px;background:#a7bab0}.tm-drawer-title{font-size:13px;font-weight:900}.tm-drawer-count{margin-left:auto;font-size:11px;font-weight:850;color:#176b45;background:#e8f5ed;border:1px solid #d4eadf;border-radius:99px;padding:5px 9px}.tm-drawer-chevron{width:29px;height:29px;border-radius:9px;background:#e9f5ee;color:#176b45;display:grid;place-items:center;font-weight:900;transition:transform .22s}.collapsed .tm-drawer-chevron{transform:rotate(180deg)}#tm-stable-track{height:139px;display:flex;gap:13px;overflow-x:auto;overflow-y:hidden;padding:3px 14px 13px;scroll-behavior:smooth;scroll-snap-type:x proximity;overscroll-behavior-x:contain;cursor:grab}#tm-stable-track:active{cursor:grabbing}.collapsed #tm-stable-track{display:none}#tm-stable-track::-webkit-scrollbar{height:7px}#tm-stable-track::-webkit-scrollbar-thumb{background:#b9cfc3;border-radius:99px}.tm-stable-card{flex:0 0 285px;height:123px;scroll-snap-align:start;border:1px solid #dfeae4;border-radius:16px;background:#fff;box-shadow:0 4px 14px rgba(17,59,40,.065);padding:13px;cursor:pointer;transition:transform .17s,box-shadow .17s,border-color .17s}.tm-stable-card:hover{transform:translateY(-2px);border-color:#99c6ac;box-shadow:0 10px 25px rgba(17,59,40,.12)}.tm-stable-card-top{display:flex;gap:8px}.tm-stable-card-top strong{font-size:14px;line-height:1.2;flex:1;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.tm-stable-region{font-size:11px;color:#718078;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tm-stable-badges{display:flex;gap:5px;margin:10px 0}.tm-stable-badge{font-size:10px;padding:4px 7px;border-radius:99px;background:#edf6f1;color:#2c6049}.tm-stable-meta{font-size:11px;color:#5e6d65;display:flex;gap:10px;white-space:nowrap}.tm-stable-empty{min-width:100%;display:grid;place-items:center;color:#718078;font-size:13px}

@media(max-width:1000px){#tm-stable-topbar{grid-template-columns:230px minmax(220px,1fr) auto;gap:12px;padding:8px 12px}.tm-stable-copy small{display:none}.tm-stable-brand svg{width:70px;flex-basis:70px}.tm-stable-copy strong{font-size:22px}#tm-stable-actions button{padding:0 11px}.tm-stable-label{display:none}#tm-stable-account-name{display:none}.sidebar{width:min(370px,calc(100vw - 20px))!important;min-width:0!important}.leaflet-left{left:390px!important}#tm-stable-drawer{left:394px}}
@media(max-width:760px){:root{--tm-top:66px}#tm-stable-topbar{height:66px;grid-template-columns:46px 1fr auto;gap:7px;padding:7px 8px}.tm-stable-brand svg{width:44px;height:42px;flex-basis:44px}.tm-stable-copy{display:none}#tm-stable-search-wrap{height:43px}#tm-stable-actions{gap:4px}#tm-stable-actions button{width:39px;height:39px;padding:0;justify-content:center}#tm-stable-account{min-width:39px}.sidebar{left:10px!important;top:calc(var(--tm-top) + 10px)!important;width:min(370px,calc(100vw - 20px))!important;max-height:calc(100vh - var(--tm-top) - 20px)!important}.leaflet-left{left:0!important}.map-tools{right:10px!important;top:10px!important}#tm-stable-side{right:10px;top:auto;bottom:195px}body.tm-map-menu-open #tm-stable-side{top:auto;bottom:195px}#tm-stable-drawer{left:10px;right:10px;bottom:10px}.map-legend{bottom:205px!important;right:8px!important}}
</style>
<script id="trekmap-stable-explorer-js">
(function(){
  const app=document.getElementById('app');
  if(!app)return;

  // Remove experimental generated controls so only one set remains.
  document.getElementById('tm-explorer-topbar')?.remove();
  document.getElementById('tm-side-actions')?.remove();
  document.getElementById('tm-results-drawer')?.remove();

  const top=document.createElement('header');
  top.id='tm-stable-topbar';
  top.innerHTML='<button id="tm-stable-home" type="button" title="Retour à l’accueil"><span class="tm-stable-brand"><svg viewBox="0 0 120 60" aria-hidden="true"><path d="M4 50 L28 18 L43 36 L61 10 L83 43" fill="none" stroke="white" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 50 L34 34 L45 45 L60 28 L76 48" fill="none" stroke="#87deb1" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M82 50 C92 42 91 31 100 25 C109 19 116 24 114 33 C112 42 102 45 95 50" fill="none" stroke="white" stroke-width="5" stroke-linecap="round"/><circle cx="101" cy="20" r="4.5" fill="white"/></svg><span class="tm-stable-copy"><strong>TrekMap <em>France</em></strong><small>Explorez · Randonnez · Partagez</small></span></span></button><div id="tm-stable-search-wrap"><span class="tm-search-icon">⌕</span><input id="tm-stable-search" type="search" autocomplete="off" placeholder="Rechercher un trek, une région, un lieu…"><button id="tm-stable-search-clear" type="button" aria-label="Effacer">×</button><div id="tm-stable-suggestions"></div></div><div id="tm-stable-actions"><button id="tm-stable-explore" type="button">🗺 <span class="tm-stable-label">Explorer</span></button><button id="tm-stable-create" type="button">✦ <span class="tm-stable-label">Créer un trek</span></button><button id="tm-stable-account" type="button"><span class="tm-stable-avatar" id="tm-stable-avatar">C</span><span id="tm-stable-account-name">Connexion</span><span>⌄</span></button></div>';
  app.prepend(top);

  const side=document.createElement('aside');
  side.id='tm-stable-side';
  side.innerHTML='<button id="tm-stable-favorites" type="button"><span class="tm-stable-side-icon">★</span><b>Favoris</b><small>Mes treks</small></button><button id="tm-stable-stats" type="button"><span class="tm-stable-side-icon">▥</span><b>Stats</b><small>Activité</small></button>';
  app.appendChild(side);

  const drawer=document.createElement('section');
  drawer.id='tm-stable-drawer';
  drawer.innerHTML='<div class="tm-drawer-shell"><button class="tm-drawer-head" id="tm-stable-drawer-head" type="button"><span class="tm-drawer-grip"></span><span class="tm-drawer-title" id="tm-stable-drawer-title">Treks populaires</span><span class="tm-drawer-count" id="tm-stable-drawer-count">0</span><span class="tm-drawer-chevron">⌃</span></button><div id="tm-stable-track"></div></div>';
  app.appendChild(drawer);

  const hiddenSearch=document.getElementById('search');
  const search=document.getElementById('tm-stable-search');
  const clear=document.getElementById('tm-stable-search-clear');
  const suggestions=document.getElementById('tm-stable-suggestions');
  const track=document.getElementById('tm-stable-track');
  let searchTimer=null;

  function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));}
  function q(){return String(search?.value||'').trim();}
  function n(v){try{return typeof norm==='function'?norm(v):String(v||'').toLowerCase().trim()}catch(_){return String(v||'').toLowerCase().trim()}}

  function renderSuggestions(){
    if(!suggestions)return;
    const needle=n(q());
    if(!needle){suggestions.classList.remove('show');suggestions.innerHTML='';return;}
    let source=[];try{source=Array.isArray(allTreks)?allTreks:[]}catch(_){}
    const rows=source.map(t=>{let score=0;try{score=typeof searchScore==='function'?searchScore(t,needle):0}catch(_){}if(!score){const hay=n((t.name||'')+' '+(t.region||'')+' '+(t.description||''));score=hay.includes(needle)?1:0}return {t,score}}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0,6);
    suggestions.innerHTML=rows.map(x=>'<button type="button" class="tm-stable-suggestion" data-id="'+Number(x.t.id)+'"><b>'+esc(x.t.name||'Trek')+'</b><small>'+esc(x.t.region||'France')+' · '+Number(x.t.distance||0).toFixed(1)+' km</small></button>').join('');
    suggestions.classList.toggle('show',rows.length>0);
    suggestions.querySelectorAll('.tm-stable-suggestion').forEach(b=>b.onclick=()=>{const id=Number(b.dataset.id);const item=source.find(t=>Number(t.id)===id);if(item&&search){search.value=item.name||'';syncSearch(true);suggestions.classList.remove('show');setTimeout(()=>{try{openDetail(id)}catch(_){}},80)}});
  }

  function syncSearch(immediate=false){
    if(!hiddenSearch||!search)return;
    hiddenSearch.value=search.value;
    clear?.classList.toggle('show',!!q());
    clearTimeout(searchTimer);
    const run=()=>{hiddenSearch.dispatchEvent(new Event('input',{bubbles:true}));setTimeout(()=>{renderDrawer();renderSuggestions();},130)};
    if(immediate)run();else searchTimer=setTimeout(run,55);
  }

  function dataForDrawer(){
    let data=[];try{data=Array.isArray(filteredTreks)?filteredTreks.slice():[]}catch(_){}
    if(!q())data.sort((a,b)=>Number(b.view_count||b.views||0)-Number(a.view_count||a.views||0)||Number(b.favorite_count||b.favorites||0)-Number(a.favorite_count||a.favorites||0)||String(a.name||'').localeCompare(String(b.name||''),'fr'));
    return data;
  }
  function renderDrawer(){
    if(!track)return;
    const data=dataForDrawer();
    const title=document.getElementById('tm-stable-drawer-title');
    const count=document.getElementById('tm-stable-drawer-count');
    if(title)title.textContent=q()?'Résultats de recherche':'Treks populaires';
    if(count)count.textContent=data.length;
    if(!data.length){track.innerHTML='<div class="tm-stable-empty">Aucun trek ne correspond aux critères.</div>';return;}
    track.innerHTML=data.map(t=>'<article class="tm-stable-card" data-id="'+Number(t.id)+'"><div class="tm-stable-card-top"><strong>'+esc(t.name||'Trek')+'</strong><span>⌖</span></div><div class="tm-stable-region">'+esc(t.region||'France')+'</div><div class="tm-stable-badges"><span class="tm-stable-badge">'+esc(({easy:'Facile',medium:'Moyen',hard:'Difficile',extreme:'Extrême'}[t.difficulty]||'Moyen'))+'</span><span class="tm-stable-badge">'+(t.is_public?'Public':'Privé')+'</span></div><div class="tm-stable-meta"><span>📏 '+Number(t.distance||0).toFixed(1)+' km</span><span>↗ '+Math.round(t.elevation||0)+' m</span><span>⏱ '+(t.duration_days?Number(t.duration_days)+' j':'—')+'</span></div></article>').join('');
    track.querySelectorAll('.tm-stable-card').forEach(card=>card.onclick=()=>{try{openDetail(Number(card.dataset.id))}catch(_){}});
  }

  search?.addEventListener('input',()=>syncSearch(false));
  search?.addEventListener('focus',renderSuggestions);
  search?.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();syncSearch(true);suggestions?.classList.remove('show')}if(e.key==='Escape')suggestions?.classList.remove('show')});
  clear?.addEventListener('click',()=>{if(search){search.value='';syncSearch(true);search.focus()}suggestions?.classList.remove('show')});
  document.addEventListener('click',e=>{if(!document.getElementById('tm-stable-search-wrap')?.contains(e.target))suggestions?.classList.remove('show')});

  // Update bottom bar whenever the original rendering changes.
  const oldList=document.getElementById('trek-list');
  if(oldList)new MutationObserver(()=>requestAnimationFrame(renderDrawer)).observe(oldList,{childList:true,subtree:true});
  ['region-filter','difficulty-filter','duration-filter','sort-filter','distance-range','distance-tolerance','elevation-range','elevation-tolerance'].forEach(id=>{const el=document.getElementById(id);el?.addEventListener('input',()=>setTimeout(renderDrawer,30));el?.addEventListener('change',()=>setTimeout(renderDrawer,30))});

  document.getElementById('tm-stable-drawer-head')?.addEventListener('click',()=>drawer.classList.toggle('collapsed'));
  track?.addEventListener('wheel',e=>{if(Math.abs(e.deltaY)>Math.abs(e.deltaX)){e.preventDefault();track.scrollLeft+=e.deltaY}},{passive:false});
  let dragging=false,startX=0,startScroll=0;track?.addEventListener('pointerdown',e=>{dragging=true;startX=e.clientX;startScroll=track.scrollLeft;track.setPointerCapture?.(e.pointerId)});track?.addEventListener('pointermove',e=>{if(dragging)track.scrollLeft=startScroll-(e.clientX-startX)});track?.addEventListener('pointerup',()=>dragging=false);track?.addEventListener('pointercancel',()=>dragging=false);

  document.getElementById('tm-stable-home')?.addEventListener('click',()=>{if(typeof window.TrekMapShowHome==='function')window.TrekMapShowHome();else document.getElementById('tm-home')?.classList.remove('tm-hidden')});
  document.getElementById('tm-stable-explore')?.addEventListener('click',()=>{document.getElementById('tm-home')?.classList.add('tm-hidden');try{switchTab('all')}catch(_){}drawer.classList.remove('collapsed')});
  document.getElementById('tm-stable-create')?.addEventListener('click',()=>{try{if(currentUser)openCreate();else authModal('login')}catch(_){document.getElementById('create-button')?.click()}});
  document.getElementById('tm-stable-account')?.addEventListener('click',()=>{try{if(currentUser)openProfile();else authModal('login')}catch(_){document.getElementById('account-button')?.click()}});
  document.getElementById('tm-stable-favorites')?.addEventListener('click',()=>{try{if(!currentUser){authModal('login');return}switchTab('favorites');drawer.classList.remove('collapsed');setTimeout(renderDrawer,30)}catch(_){}});
  document.getElementById('tm-stable-stats')?.addEventListener('click',()=>{if(typeof window.TrekMapOpenStats==='function')window.TrekMapOpenStats()});

  // Restore legacy account button semantics: authenticated users see profile, logout remains inside profile.
  const legacyAccount=document.getElementById('account-button');
  if(legacyAccount)legacyAccount.onclick=()=>{try{if(currentUser)openProfile();else authModal('login')}catch(_){authModal('login')}};

  function syncAccount(){const name=(document.getElementById('account-name')?.textContent||'Mode visiteur').trim();const shown=name==='Mode visiteur'?'Connexion':name;const target=document.getElementById('tm-stable-account-name');const avatar=document.getElementById('tm-stable-avatar');if(target)target.textContent=shown;if(avatar)avatar.textContent=(shown==='Connexion'?'C':shown.slice(0,1).toUpperCase())}
  syncAccount();const accountName=document.getElementById('account-name');if(accountName)new MutationObserver(syncAccount).observe(accountName,{childList:true,subtree:true,characterData:true});

  // Keep quick actions away from map menu while open.
  const mapOptions=document.getElementById('tm-map-options');
  mapOptions?.addEventListener('click',()=>setTimeout(()=>{document.body.classList.toggle('tm-map-menu-open',document.getElementById('tm-map-options-panel')?.classList.contains('tm-show'))},0));
  document.addEventListener('click',()=>setTimeout(()=>{document.body.classList.toggle('tm-map-menu-open',document.getElementById('tm-map-options-panel')?.classList.contains('tm-show'))},0));

  // Home search also gets the same engine when entering explorer.
  const homeSearch=document.getElementById('tm-home-search');
  const homeButton=document.getElementById('tm-home-search-btn');
  const pushHomeSearch=()=>{if(search&&homeSearch){search.value=homeSearch.value;syncSearch(true)}};
  homeButton?.addEventListener('click',()=>setTimeout(pushHomeSearch,120));
  homeSearch?.addEventListener('keydown',e=>{if(e.key==='Enter')setTimeout(pushHomeSearch,120)});

  setTimeout(()=>{try{map.invalidateSize()}catch(_){}renderDrawer();clear?.classList.toggle('show',!!q())},180);
})();
</script>
<!-- TREKMAP_STABLE_EXPLORER_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap stable explorer applied')
