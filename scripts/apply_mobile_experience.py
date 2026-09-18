from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

# Idempotent: a rebuild must never stack several mobile layers.
html = re.sub(
    r"\s*<!-- TREKMAP_MOBILE_EXPERIENCE_START -->.*?<!-- TREKMAP_MOBILE_EXPERIENCE_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_UNIFIED_EXPERIENCE_START" not in html:
    raise SystemExit("La couche unifiée TrekMap doit être construite avant la couche mobile.")

mobile = r'''<!-- TREKMAP_MOBILE_EXPERIENCE_START -->
<style id="trekmap-mobile-css">
/* Mobile UX 2.0: navigation tactile, safe areas, bottom sheets et création sur carte. */
#tm-mobile-nav,#tm-mobile-create-sheet{display:none}

@media(max-width:820px){
  :root{
    --tm-top:calc(64px + env(safe-area-inset-top,0px));
    --tm-mobile-nav-h:66px;
    --tm-mobile-drawer-h:158px;
    --tm-panel:100vw;
    --tm-drawer:var(--tm-mobile-drawer-h)
  }
  html,body,#app{width:100%;height:100%;overscroll-behavior:none}
  body{touch-action:manipulation;-webkit-tap-highlight-color:transparent}
  #app{height:100dvh!important;min-height:100dvh!important}
  #map{inset:var(--tm-top) 0 0 0!important}

  /* En haut, on ne garde que l'identité et la recherche. Les actions vivent en bas. */
  #tm-unified-topbar{
    height:var(--tm-top)!important;
    grid-template-columns:42px minmax(0,1fr)!important;
    gap:7px!important;
    padding:calc(7px + env(safe-area-inset-top,0px)) 8px 7px!important;
    align-items:end!important;
  }
  #tm-top-actions{display:none!important}
  .tm-brand-mark{width:40px!important;height:42px!important;border-radius:12px!important}
  #tm-main-search-wrap{height:42px!important;border-radius:13px!important;box-shadow:0 6px 18px rgba(0,0,0,.14)!important}
  #tm-main-search{font-size:16px!important;padding-right:42px!important}
  #tm-main-suggestions{
    position:fixed!important;
    z-index:13000!important;
    left:8px!important;right:8px!important;
    top:calc(var(--tm-top) + 6px)!important;
    max-height:min(52dvh,420px)!important;
    border-radius:16px!important;
    box-shadow:0 18px 44px rgba(7,40,27,.24)!important;
  }
  .tm-suggest{min-height:48px!important;padding:10px 12px!important}
  .tm-suggest b{font-size:13px!important}.tm-suggest small{font-size:11px!important}

  /* Barre de navigation mobile persistante. */
  #tm-mobile-nav{
    position:absolute;z-index:9200;
    left:8px;right:8px;bottom:calc(7px + env(safe-area-inset-bottom,0px));
    height:var(--tm-mobile-nav-h);
    display:grid;grid-template-columns:repeat(5,1fr);align-items:center;
    padding:5px 6px;
    background:rgba(255,255,255,.96);
    border:1px solid rgba(210,226,217,.95);
    border-radius:20px;
    box-shadow:0 14px 38px rgba(9,45,30,.22);
    backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)
  }
  .tm-mobile-nav-btn{
    min-width:0;height:54px;border:0;border-radius:14px;background:transparent;
    display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;
    color:#61756b;font-size:9px;font-weight:850;letter-spacing:.01em
  }
  .tm-mobile-nav-btn .tm-m-icon{font-size:20px;line-height:1}
  .tm-mobile-nav-btn.active{background:#eaf6ef;color:var(--tm-green)}
  .tm-mobile-nav-btn.create{
    width:54px;justify-self:center;border-radius:18px;
    background:linear-gradient(145deg,#116b49,#1e9365);color:#fff;
    box-shadow:0 7px 18px rgba(17,107,73,.28)
  }
  .tm-mobile-nav-btn.create .tm-m-icon{font-size:25px}

  /* Les résultats deviennent un carousel juste au-dessus de la navigation. */
  #tm-unified-drawer{
    left:8px!important;right:8px!important;
    bottom:calc(var(--tm-mobile-nav-h) + 15px + env(safe-area-inset-bottom,0px))!important;
    height:var(--tm-mobile-drawer-h)!important;
    transition:height .2s ease,bottom .2s ease!important
  }
  #tm-unified-drawer.collapsed{height:46px!important}
  .tm-drawer-shell{border-radius:18px!important}
  #tm-drawer-head{height:46px!important;padding:0 12px!important;touch-action:manipulation}
  #tm-drawer-track{
    height:112px!important;gap:8px!important;padding:2px 10px 10px!important;
    scroll-snap-type:x mandatory!important;scroll-padding-inline:10px;
    -webkit-overflow-scrolling:touch;touch-action:pan-x
  }
  .tm-trek-tile{
    flex:0 0 min(82vw,300px)!important;height:102px!important;
    padding:10px 11px!important;border-radius:13px!important;scroll-snap-align:start!important
  }
  .tm-trek-tile strong{font-size:13px!important}.tm-trek-tile .region{font-size:10px!important}
  .tm-tile-chips{margin:6px 0!important}.tm-tile-meta{font-size:10px!important}
  .tm-tile-open{display:none!important}

  /* Les filtres ne flottent plus sur la carte : ils montent comme une bottom-sheet. */
  .sidebar{
    position:fixed!important;z-index:11500!important;
    inset:var(--tm-top) 0 0 0!important;
    width:100%!important;min-width:0!important;max-height:none!important;height:auto!important;
    display:flex!important;align-items:flex-end!important;
    margin:0!important;padding:0!important;
    background:rgba(5,28,19,.45)!important;
    opacity:0!important;visibility:hidden!important;pointer-events:none!important;
    transition:opacity .18s ease,visibility .18s ease!important
  }
  body.tm-mobile-filters-open .sidebar{opacity:1!important;visibility:visible!important;pointer-events:auto!important}
  #sidebar .filters{
    position:relative!important;left:auto!important;right:auto!important;top:auto!important;bottom:auto!important;
    width:100%!important;max-width:none!important;height:auto!important;
    max-height:min(78dvh,760px)!important;
    margin:0!important;padding:0 14px calc(18px + env(safe-area-inset-bottom,0px))!important;
    background:#fff!important;border:0!important;border-radius:24px 24px 0 0!important;
    box-shadow:0 -16px 48px rgba(5,35,23,.24)!important;
    overflow:auto!important;overscroll-behavior:contain;
    transform:translateY(105%)!important;
    transition:transform .24s cubic-bezier(.2,.8,.2,1)!important
  }
  body.tm-mobile-filters-open #sidebar .filters{transform:translateY(0)!important}
  #sidebar .filters.tm-collapsed{height:auto!important;min-height:0!important;max-height:min(78dvh,760px)!important;padding:0 14px calc(18px + env(safe-area-inset-bottom,0px))!important}
  #sidebar .filters.tm-collapsed>*:not(#tm-filter-head){display:block!important}
  #sidebar .filters.tm-collapsed>.filter-row{display:grid!important}
  #sidebar .filters.tm-collapsed>#tm-criteria-filters{display:grid!important}
  #sidebar .filters.tm-collapsed>.filter-actions{display:flex!important}
  #tm-filter-head{
    position:sticky!important;z-index:3!important;left:auto!important;right:auto!important;top:0!important;
    height:56px!important;margin:0 -14px 8px!important;padding:8px 14px!important;
    background:rgba(255,255,255,.97)!important;border-bottom:1px solid #edf1ef!important;
    backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)
  }
  #tm-filter-head:before{content:"";position:absolute;top:6px;left:50%;width:40px;height:4px;border-radius:99px;background:#c6d3cc;transform:translateX(-50%)}
  #tm-filter-head strong{font-size:16px!important;padding-top:7px}
  #tm-filter-toggle{min-width:72px!important;height:38px!important;margin-top:6px!important;font-size:11px!important}
  .tm-filter-section{font-size:10px!important;margin-top:14px!important}
  .filter-row,#tm-criteria-filters{grid-template-columns:1fr 1fr!important;gap:9px!important;padding:10px!important}
  .field label,.tm-criterion label{font-size:10px!important}
  .field select,.field input,.tm-criterion select,.tm-criterion input{min-height:46px!important;font-size:16px!important;border-radius:11px!important}
  .filter-actions button{min-height:46px!important;font-size:13px!important}

  /* Menu de création : tracer ou importer sans sacrifier une place dans la barre du bas. */
  #tm-mobile-create-sheet{
    position:fixed;z-index:12500;inset:0;display:flex;align-items:flex-end;
    background:rgba(5,28,19,.48);opacity:0;visibility:hidden;pointer-events:none;
    transition:opacity .18s ease,visibility .18s ease
  }
  #tm-mobile-create-sheet.open{opacity:1;visibility:visible;pointer-events:auto}
  .tm-mobile-create-card{
    width:100%;padding:10px 14px calc(18px + env(safe-area-inset-bottom,0px));
    background:#fff;border-radius:24px 24px 0 0;
    box-shadow:0 -16px 48px rgba(5,35,23,.24);
    transform:translateY(105%);transition:transform .22s cubic-bezier(.2,.8,.2,1)
  }
  #tm-mobile-create-sheet.open .tm-mobile-create-card{transform:translateY(0)}
  .tm-mobile-sheet-grip{width:42px;height:4px;border-radius:99px;background:#c6d3cc;margin:0 auto 10px}
  .tm-mobile-create-card h3{margin:6px 2px 12px;font-size:18px;color:#18382c}
  .tm-mobile-create-choice{
    width:100%;min-height:64px;margin-top:8px;border:1px solid #dfe9e3;border-radius:15px;
    background:#f8fbf9;color:#23483a;padding:10px 12px;display:flex;align-items:center;gap:12px;text-align:left
  }
  .tm-mobile-create-choice .icon{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;background:#e8f5ee;color:var(--tm-green);font-size:22px}
  .tm-mobile-create-choice b,.tm-mobile-create-choice small{display:block}.tm-mobile-create-choice small{margin-top:3px;color:#718078;font-size:11px}

  /* Options de carte et contrôles adaptés au pouce. */
  .map-tools{right:8px!important;top:8px!important;max-width:210px!important}
  #tm-map-options{height:44px!important;min-width:44px!important;padding:0 11px!important;font-size:12px!important}
  #tm-map-options-panel{width:min(250px,calc(100vw - 16px))!important;right:0!important}
  #tm-map-options-panel select,#tm-map-options-panel button{min-height:44px!important;font-size:13px!important}
  .leaflet-control-zoom a{width:38px!important;height:38px!important;line-height:38px!important;font-size:20px!important}

  /* Le mode tracé devient une bottom-sheet et libère la carte. */
  .draw-panel{
    position:absolute!important;z-index:10000!important;
    left:8px!important;right:8px!important;top:auto!important;
    bottom:calc(9px + env(safe-area-inset-bottom,0px))!important;
    width:auto!important;max-height:46dvh!important;overflow:auto!important;
    transform:none!important;border-radius:18px!important;padding:12px!important
  }
  .draw-actions button{min-height:44px!important;padding:9px 13px!important}
  body.tm-mobile-drawing #tm-mobile-nav,body.tm-mobile-drawing #tm-unified-drawer{display:none!important}

  /* Modales et formulaires : grandes cibles tactiles, pas de zoom automatique iOS. */
  .modal-backdrop{padding:0!important;align-items:flex-end!important;overflow:hidden!important}
  .modal{
    width:100%!important;max-width:none!important;
    max-height:calc(94dvh - env(safe-area-inset-top,0px))!important;
    border-radius:24px 24px 0 0!important;
    padding:16px 14px calc(18px + env(safe-area-inset-bottom,0px))!important;
    overscroll-behavior:contain!important
  }
  .modal:before{content:"";display:block;width:42px;height:4px;border-radius:99px;background:#c6d3cc;margin:-5px auto 11px}
  .modal-head{position:sticky!important;top:-16px!important;z-index:3!important;background:#fff!important;padding:9px 0 8px!important;margin-bottom:10px!important}
  .modal-head h2{font-size:21px!important}.close{width:44px!important;height:44px!important;flex:0 0 44px!important;font-size:18px!important}
  .form-grid,.tm-unified-grid{grid-template-columns:1fr!important}
  .full{grid-column:auto!important}
  .form-field input,.form-field select,.form-field textarea,.tm-u-field input,.tm-u-field select,.tm-u-field textarea{min-height:46px!important;font-size:16px!important}
  .modal-actions{position:sticky!important;bottom:calc(-18px - env(safe-area-inset-bottom,0px))!important;background:#fff!important;padding:10px 0 calc(8px + env(safe-area-inset-bottom,0px))!important;margin-top:12px!important}
  .modal-actions button,.primary-btn,.ghost-btn,.danger-btn{min-height:44px!important}
  .detail-grid,.tm-detail-criteria{grid-template-columns:1fr 1fr!important}
  .tm-detail-hero{height:min(45vw,220px)!important}
  .tm-gallery,.tm-photo-preview{grid-template-columns:repeat(2,1fr)!important}
  .tm-star{min-width:36px!important;min-height:40px!important;font-size:25px!important}
  .comment-form{flex-direction:column!important;align-items:stretch!important}.comment-form textarea{font-size:16px!important}

  /* Toasts visibles sans passer sous les zones système. */
  .toast{top:calc(var(--tm-top) + 8px)!important;left:10px!important;right:10px!important;max-width:none!important;text-align:center!important}

  /* Accueil mobile plus compact et lisible. */
  #tm-home{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
  .tm-home-nav{padding:12px 14px!important}.tm-logo img{width:128px!important}.tm-home-login{min-height:42px!important}
  .tm-home-main{padding:0 14px 28px!important}.tm-hero{display:block!important;padding-top:28px!important}.tm-hero h1{font-size:clamp(38px,12vw,52px)!important;margin-bottom:14px!important}.tm-hero-copy>p{font-size:15px!important}
  .tm-hero-search{margin-top:18px!important}.tm-hero-search input{font-size:16px!important}.tm-hero-search button{min-height:44px!important}
  .tm-hero-visual{height:300px!important;margin-top:10px!important}.tm-map-orb{width:min(300px,78vw)!important;height:min(300px,78vw)!important}
  .tm-features,.tm-featured{grid-template-columns:1fr!important}.tm-stats-strip{grid-template-columns:1fr 1fr!important;padding:15px!important}

  body.tm-mobile-keyboard #tm-mobile-nav,body.tm-mobile-keyboard #tm-unified-drawer{display:none!important}
}

@media(max-width:520px){
  .filter-row,#tm-criteria-filters{grid-template-columns:1fr!important}
  .tm-mobile-nav-btn{font-size:8px!important}
  .tm-mobile-nav-btn .tm-m-icon{font-size:19px!important}
  .tm-trek-tile{flex-basis:84vw!important}
  .detail-grid,.tm-detail-criteria{grid-template-columns:1fr 1fr!important}
}

@media(max-width:820px) and (orientation:landscape){
  :root{--tm-top:calc(56px + env(safe-area-inset-top,0px));--tm-mobile-nav-h:58px;--tm-mobile-drawer-h:126px}
  #tm-unified-topbar{padding-top:calc(5px + env(safe-area-inset-top,0px))!important;padding-bottom:5px!important}.tm-brand-mark,#tm-main-search-wrap{height:38px!important}
  #tm-drawer-track{height:80px!important}.tm-trek-tile{height:72px!important}.tm-tile-chips{display:none!important}
  .tm-mobile-nav-btn{height:46px!important}.tm-mobile-nav-btn.create{width:48px!important}
  #sidebar .filters{max-height:86dvh!important}.tm-hero-visual{display:none!important}
}
</style>
<script id="trekmap-mobile-js">
(function(){
  const app=document.getElementById('app');
  if(!app||document.getElementById('tm-mobile-nav'))return;
  const $=id=>document.getElementById(id);
  const mq=window.matchMedia('(max-width:820px)');
  const body=document.body;

  const nav=document.createElement('nav');
  nav.id='tm-mobile-nav';
  nav.setAttribute('aria-label','Navigation mobile TrekMap');
  nav.innerHTML=`
    <button class="tm-mobile-nav-btn active" type="button" data-mobile-action="explore"><span class="tm-m-icon">⌖</span><span>Explorer</span></button>
    <button class="tm-mobile-nav-btn" type="button" data-mobile-action="filters"><span class="tm-m-icon">≡</span><span>Filtres</span></button>
    <button class="tm-mobile-nav-btn create" type="button" data-mobile-action="create"><span class="tm-m-icon">＋</span><span>Créer</span></button>
    <button class="tm-mobile-nav-btn" type="button" data-mobile-action="favorites"><span class="tm-m-icon">★</span><span>Favoris</span></button>
    <button class="tm-mobile-nav-btn" type="button" data-mobile-action="profile"><span class="tm-m-icon">●</span><span>Profil</span></button>`;
  app.appendChild(nav);

  const createSheet=document.createElement('div');
  createSheet.id='tm-mobile-create-sheet';
  createSheet.setAttribute('aria-hidden','true');
  createSheet.innerHTML=`<div class="tm-mobile-create-card" role="dialog" aria-modal="true" aria-label="Créer ou importer un trek">
    <div class="tm-mobile-sheet-grip"></div><h3>Ajouter un trek</h3>
    <button class="tm-mobile-create-choice" type="button" data-mobile-create="draw"><span class="icon">✎</span><span><b>Tracer sur la carte</b><small>Place des points et laisse TrekMap calculer l'itinéraire.</small></span></button>
    <button class="tm-mobile-create-choice" type="button" data-mobile-create="import"><span class="icon">⇧</span><span><b>Importer un fichier GPX</b><small>Ajoute une trace enregistrée depuis une montre ou une autre application.</small></span></button>
  </div>`;
  document.body.appendChild(createSheet);

  function mobile(){return mq.matches}
  function setActive(action){nav.querySelectorAll('[data-mobile-action]').forEach(b=>b.classList.toggle('active',b.dataset.mobileAction===action))}
  function closeCreate(){createSheet.classList.remove('open');createSheet.setAttribute('aria-hidden','true')}
  function openCreateSheet(){
    if(!mobile())return;
    closeFilters();
    createSheet.classList.add('open');createSheet.setAttribute('aria-hidden','false');
  }
  function closeFilters(){body.classList.remove('tm-mobile-filters-open')}
  function openFilters(){
    if(!mobile())return;
    closeCreate();
    const filters=document.querySelector('#sidebar .filters');
    filters?.classList.remove('tm-collapsed');
    body.classList.remove('tm-filters-collapsed');
    const toggle=$('tm-filter-toggle');if(toggle)toggle.textContent='Fermer';
    body.classList.add('tm-mobile-filters-open');
    $('tm-unified-drawer')?.classList.add('collapsed');
  }
  function showExplore(){
    closeFilters();closeCreate();
    try{window.TrekMapHideHome?.()}catch(_){}
    const all=document.querySelector('.tab[data-tab="all"]');
    if(all)all.click();
    else try{window.switchTab?.('all')}catch(_){}
    $('tm-unified-drawer')?.classList.remove('collapsed');
    setActive('explore');
  }

  nav.addEventListener('click',e=>{
    const btn=e.target.closest('[data-mobile-action]');if(!btn)return;
    const action=btn.dataset.mobileAction;
    if(action==='explore')showExplore();
    else if(action==='filters'){openFilters();setActive('filters')}
    else if(action==='create'){openCreateSheet();setActive('create')}
    else if(action==='favorites'){closeFilters();closeCreate();$('tm-favorites-btn')?.click();setActive('favorites')}
    else if(action==='profile'){closeFilters();closeCreate();$('tm-account-btn')?.click();setActive('profile')}
  });

  createSheet.addEventListener('click',e=>{
    if(e.target===createSheet){closeCreate();setActive('explore');return}
    const choice=e.target.closest('[data-mobile-create]');if(!choice)return;
    closeCreate();
    if(choice.dataset.mobileCreate==='draw')$('tm-create-btn')?.click();
    if(choice.dataset.mobileCreate==='import')$('tm-import-btn')?.click();
    setActive('explore');
  });

  const sidebar=$('sidebar');
  sidebar?.addEventListener('click',e=>{if(mobile()&&e.target===sidebar){closeFilters();setActive('explore')}});
  $('tm-filter-toggle')?.addEventListener('click',e=>{
    if(!mobile())return;
    e.preventDefault();e.stopImmediatePropagation();closeFilters();setActive('explore');
  },true);

  document.addEventListener('keydown',e=>{
    if(e.key!=='Escape')return;
    if(createSheet.classList.contains('open')){closeCreate();setActive('explore')}
    if(body.classList.contains('tm-mobile-filters-open')){closeFilters();setActive('explore')}
  });

  // Le panneau de dessin pilote automatiquement l'espace disponible sur téléphone.
  const drawPanel=$('draw-panel');
  if(drawPanel){
    const syncDrawing=()=>body.classList.toggle('tm-mobile-drawing',mobile()&&drawPanel.classList.contains('active'));
    new MutationObserver(syncDrawing).observe(drawPanel,{attributes:true,attributeFilter:['class','style']});
    syncDrawing();
  }

  // Quand le clavier virtuel prend la moitié de l'écran, on masque ce qui gênerait la saisie.
  if(window.visualViewport){
    const syncKeyboard=()=>{
      if(!mobile()){body.classList.remove('tm-mobile-keyboard');return}
      const ratio=window.visualViewport.height/Math.max(window.innerHeight,1);
      body.classList.toggle('tm-mobile-keyboard',ratio<0.72);
    };
    window.visualViewport.addEventListener('resize',syncKeyboard);
    window.visualViewport.addEventListener('scroll',syncKeyboard);
    syncKeyboard();
  }

  function syncResponsive(){
    if(!mobile()){
      closeFilters();closeCreate();body.classList.remove('tm-mobile-keyboard','tm-mobile-drawing');
      const toggle=$('tm-filter-toggle');if(toggle)toggle.textContent=document.querySelector('#sidebar .filters')?.classList.contains('tm-collapsed')?'Afficher':'Replier';
    }else{
      const toggle=$('tm-filter-toggle');if(toggle)toggle.textContent='Fermer';
    }
    try{map.invalidateSize()}catch(_){}
  }
  mq.addEventListener?.('change',syncResponsive);
  window.addEventListener('orientationchange',()=>setTimeout(syncResponsive,120));
  syncResponsive();
})();
</script>
<!-- TREKMAP_MOBILE_EXPERIENCE_END -->'''

html = html.replace("</body>", mobile + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekMap mobile experience applied")
