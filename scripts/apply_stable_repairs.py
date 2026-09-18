from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r'\s*<!-- TREKMAP_STABLE_REPAIRS_START -->.*?<!-- TREKMAP_STABLE_REPAIRS_END -->\s*',
    '\n',
    html,
    flags=re.S,
)

block = r'''<!-- TREKMAP_STABLE_REPAIRS_START -->
<style id="trekmap-stable-repairs-css">
#tm-stable-favorites.is-active{background:#176b45!important;color:#fff!important;border-color:#176b45!important;box-shadow:0 10px 28px rgba(23,107,69,.28)!important}
#tm-stable-favorites.is-active .tm-stable-side-icon{background:rgba(255,255,255,.18)!important;color:#fff!important}
#tm-stable-drawer.tm-refreshing .tm-drawer-shell{box-shadow:0 18px 50px rgba(14,71,45,.24)!important}
#tm-stable-drawer.tm-refreshing .tm-stable-card{opacity:.78!important}
#tm-stable-track{scrollbar-gutter:stable!important}
.tm-stable-card.is-map-selected{border-color:#1b8d5e!important;box-shadow:0 0 0 3px rgba(27,141,94,.14),0 12px 28px rgba(17,59,40,.14)!important;transform:translateY(-2px)!important}
.tm-stable-card{position:relative!important}
.tm-stable-card:after{content:'Cliquer pour localiser';position:absolute;right:12px;bottom:9px;font-size:9px;font-weight:800;color:#4f7765;background:#eef7f2;border:1px solid #deeee5;border-radius:999px;padding:4px 7px;opacity:0;transform:translateY(2px);transition:.16s}
.tm-stable-card:hover:after,.tm-stable-card.is-map-selected:after{opacity:1;transform:none}

/* Filtres plus lisibles : les mêmes contrôles, rangés par fonction. */
#sidebar .filters{padding-top:56px!important}
#sidebar .filters .tm-filter-section-title{display:flex;align-items:center;gap:8px;margin:13px 0 8px;color:#345d4b;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase}
#sidebar .filters .tm-filter-section-title:first-of-type{margin-top:2px}
#sidebar .filters .tm-filter-section-title:after{content:'';height:1px;flex:1;background:#e4ede8}
#sidebar .filters .filter-row.tm-filter-group{padding:10px;background:rgba(247,250,248,.9);border:1px solid #e1ebe5;border-radius:14px;gap:10px!important}
#sidebar .filters .filter-row.tm-filter-group+.tm-filter-section-title{margin-top:15px}
#sidebar .filters .field label{margin-top:0!important;line-height:1.25}
#sidebar .filters .filter-actions{margin-top:15px!important;padding-top:13px!important;border-top:1px solid #e2ebe6!important}
#sidebar .filters .filter-actions button{min-height:44px!important}
#sidebar .filters #reset-filters{background:#f7faf8!important}
#sidebar .filters #upload-button{background:#e8f5ed!important;border-color:#cfe7da!important}

/* Tiroir de résultats un peu plus net visuellement. */
#tm-stable-drawer .tm-drawer-head{border-bottom:1px solid rgba(222,235,228,.9)!important}
#tm-stable-drawer.collapsed .tm-drawer-head{border-bottom:0!important}
#tm-stable-drawer .tm-drawer-title{letter-spacing:.005em!important}
#tm-stable-drawer .tm-drawer-count{min-width:30px;text-align:center}
</style>
<script id="trekmap-stable-repairs-js">
(function(){
  const visibleSearch=document.getElementById('tm-stable-search');
  const hiddenSearch=document.getElementById('search');
  const drawer=document.getElementById('tm-stable-drawer');
  const track=document.getElementById('tm-stable-track');
  const title=document.getElementById('tm-stable-drawer-title');
  const favoritesButton=document.getElementById('tm-stable-favorites');
  const mapPanel=document.getElementById('tm-map-options-panel');
  const mapOptions=document.getElementById('tm-map-options');
  let refreshTimer=null;

  function mode(){
    try{return typeof currentTab!=='undefined' ? currentTab : 'all'}catch(_){return 'all'}
  }

  function forceAllMode(){
    try{
      if(typeof currentTab!=='undefined')currentTab='all';
      document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab==='all'));
    }catch(_){}
    favoritesButton?.classList.remove('is-active');
  }

  function query(){return String(visibleSearch?.value||'').trim()}

  function drawerTitle(){
    const m=mode();
    const hasQuery=!!query();
    if(hasQuery){
      if(m==='favorites')return 'Recherche dans mes favoris';
      if(m==='mine')return 'Recherche dans mes treks';
      if(m==='private')return 'Recherche dans mes treks privés';
      return 'Résultats de recherche';
    }
    return ({favorites:'Mes favoris',mine:'Mes treks',private:'Mes treks privés',popular:'Treks populaires',all:'Treks populaires'})[m]||'Treks populaires';
  }

  function syncModeUi(){
    const m=mode();
    favoritesButton?.classList.toggle('is-active',m==='favorites');
    if(title)title.textContent=drawerTitle();
  }

  function refreshNow(){
    drawer?.classList.add('tm-refreshing');
    clearTimeout(refreshTimer);
    try{if(typeof applyFilters==='function')applyFilters()}catch(_){}
    drawer?.classList.remove('collapsed');
    refreshTimer=setTimeout(()=>{
      drawer?.classList.remove('tm-refreshing');
      syncModeUi();
    },170);
  }

  // Une nouvelle recherche est toujours une recherche globale.
  visibleSearch?.addEventListener('input',()=>{
    forceAllMode();
    if(hiddenSearch)hiddenSearch.value=visibleSearch.value;
    refreshNow();
  },true);

  document.addEventListener('click',e=>{
    if(e.target.closest('.tm-stable-suggestion'))forceAllMode();
  },true);

  document.getElementById('tm-home-search-btn')?.addEventListener('click',forceAllMode,true);
  document.getElementById('tm-home-search')?.addEventListener('keydown',e=>{if(e.key==='Enter')forceAllMode()},true);

  document.addEventListener('click',e=>{
    const id=e.target.closest('button')?.id;
    if(id==='profile-fav'||id==='profile-mine'){
      setTimeout(()=>{drawer?.classList.remove('collapsed');syncModeUi()},80);
    }
  });

  const oldList=document.getElementById('trek-list');
  if(oldList)new MutationObserver(()=>requestAnimationFrame(syncModeUi)).observe(oldList,{childList:true,subtree:true});
  if(track)new MutationObserver(()=>requestAnimationFrame(syncModeUi)).observe(track,{childList:true,subtree:true});

  function syncMapMenu(){
    document.body.classList.toggle('tm-map-menu-open',!!mapPanel?.classList.contains('tm-show'));
  }
  if(mapPanel)new MutationObserver(syncMapMenu).observe(mapPanel,{attributes:true,attributeFilter:['class','aria-hidden']});
  document.addEventListener('click',()=>setTimeout(syncMapMenu,0));
  document.addEventListener('keydown',e=>{if(e.key==='Escape')setTimeout(syncMapMenu,0)});

  ['region-filter','difficulty-filter','duration-filter','sort-filter','distance-range','distance-tolerance','elevation-range','elevation-tolerance'].forEach(id=>{
    const el=document.getElementById(id);
    const refresh=()=>{drawer?.classList.add('tm-refreshing');setTimeout(()=>{syncModeUi();drawer?.classList.remove('tm-refreshing')},120)};
    el?.addEventListener('input',refresh);
    el?.addEventListener('change',refresh);
  });

  document.getElementById('tm-stable-explore')?.addEventListener('click',()=>setTimeout(()=>{forceAllMode();syncModeUi()},0));
  favoritesButton?.addEventListener('click',()=>setTimeout(syncModeUi,50));

  // --- Navigation cartographique fiable ---
  function trekById(id){
    try{return Array.isArray(allTreks)?allTreks.find(t=>Number(t.id)===Number(id)):null}catch(_){return null}
  }

  function trekCoords(t){
    if(!t)return [];
    if(Array.isArray(t.coords)&&t.coords.length)return t.coords.filter(p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(Number(p[0]))&&Number.isFinite(Number(p[1]))).map(p=>[Number(p[0]),Number(p[1])]);
    const g=t.geometry;
    if(!g||!Array.isArray(g.coordinates))return [];
    const raw=g.type==='MultiLineString'?g.coordinates.flat():g.coordinates;
    return raw.filter(p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(Number(p[0]))&&Number.isFinite(Number(p[1]))).map(p=>[Number(p[1]),Number(p[0])]);
  }

  function mapPadding(){
    const desktop=window.innerWidth>760;
    const left=desktop?430:35;
    const bottom=drawer?.classList.contains('collapsed')?70:220;
    return {paddingTopLeft:[left,70],paddingBottomRight:[95,bottom]};
  }

  function zoomToTrek(id){
    const t=trekById(id);
    const coords=trekCoords(t);
    if(!coords.length)return;
    try{
      const bounds=L.latLngBounds(coords);
      if(!bounds.isValid())return;
      const opts={...mapPadding(),maxZoom:15,animate:true,duration:.75};
      if(typeof map.flyToBounds==='function')map.flyToBounds(bounds.pad(.10),opts);
      else map.fitBounds(bounds.pad(.10),opts);
      track?.querySelectorAll('.tm-stable-card').forEach(card=>card.classList.toggle('is-map-selected',Number(card.dataset.id)===Number(id)));
    }catch(_){}
  }

  // Le clic sur une carte de trek sert maintenant à la localiser sur la carte.
  // On intercepte l'ancien clic qui ouvrait directement la fiche, sinon le zoom serait caché par la modale.
  track?.addEventListener('click',e=>{
    const card=e.target.closest('.tm-stable-card');
    if(!card)return;
    e.preventDefault();
    e.stopImmediatePropagation();
    zoomToTrek(Number(card.dataset.id));
  },true);

  // Le bouton "Recentrer sur la France" ne doit pas dépendre des traces chargées.
  // L'ancien map-fit cadrait les treks, ce qui expliquait le comportement incorrect.
  document.addEventListener('click',e=>{
    const button=e.target.closest('[data-map-action="fit"]');
    if(!button)return;
    e.preventDefault();
    e.stopImmediatePropagation();
    try{
      const france=L.latLngBounds([[41.15,-5.5],[51.25,9.75]]);
      const desktop=window.innerWidth>760;
      const opts={
        paddingTopLeft:desktop?[430,55]:[25,55],
        paddingBottomRight:desktop?[90,210]:[25,200],
        maxZoom:6,
        animate:true,
        duration:.75
      };
      if(typeof map.flyToBounds==='function')map.flyToBounds(france,opts);else map.fitBounds(france,opts);
    }catch(_){try{map.setView([46.6,2.2],6)}catch(__){}}
    mapPanel?.classList.remove('tm-show');
    mapPanel?.setAttribute('aria-hidden','true');
    mapOptions?.setAttribute('aria-expanded','false');
    document.body.classList.remove('tm-map-menu-open');
  },true);

  // --- Organisation visuelle des filtres sans changer leurs IDs ni leurs événements ---
  function organizeFilters(){
    const filters=document.querySelector('#sidebar .filters');
    if(!filters||filters.dataset.tmOrganized==='1')return;
    const rows=[...filters.querySelectorAll(':scope > .filter-row')];
    const labels=[
      ['Critères principaux','Région et difficulté'],
      ['Distance','Distance cible et tolérance'],
      ['Dénivelé','Dénivelé cible et tolérance'],
      ['Organisation','Durée maximale et ordre des résultats']
    ];
    rows.forEach((row,i)=>{
      row.classList.add('tm-filter-group');
      const heading=document.createElement('div');
      heading.className='tm-filter-section-title';
      heading.textContent=labels[i]?.[0]||'Filtres';
      heading.title=labels[i]?.[1]||'';
      row.before(heading);
    });
    filters.dataset.tmOrganized='1';
  }

  organizeFilters();
  syncModeUi();
  syncMapMenu();
})();
</script>
<!-- TREKMAP_STABLE_REPAIRS_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap stable repairs applied')
