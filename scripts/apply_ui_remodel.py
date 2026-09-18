from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / 'frontend' / 'index.html'

html = html_path.read_text(encoding='utf-8')

# Production UI stylesheet
for asset_id in ('trekmap-remodel-css','trekmap-home-css'):
    html = re.sub(r'\s*<link id="' + asset_id + r'"[^>]*>', '', html)

html = html.replace('</head>',
    '<link id="trekmap-remodel-css" rel="stylesheet" href="/remodel.css">\n'
    '<link id="trekmap-home-css" rel="stylesheet" href="/home.css">\n'
    '</head>', 1)

# Remove previous generated homepage if a build is repeated.
html = re.sub(r'\s*<!-- TREKMAP_HOME_START -->.*?<!-- TREKMAP_HOME_END -->\s*', '\n', html, flags=re.S)

home = r'''<!-- TREKMAP_HOME_START -->
<div id="tm-home" aria-label="Accueil TrekMap France">
  <div class="tm-home-bg"></div>
  <header class="tm-home-nav">
    <a class="tm-logo" href="#" id="tm-home-logo"><img src="/logo-trekmap.svg" alt="TrekMap France" style="width:150px;height:auto;border-radius:10px"><span style="display:none">TrekMap <b>France</b></span></a>
    <nav class="tm-home-links">
      <button data-home-explore>Explorer</button>
      <button data-home-create>Créer un trek</button>
      <button data-home-account>Mon compte</button>
    </nav>
    <button class="tm-home-login" data-home-account>Connexion</button>
  </header>
  <main class="tm-home-main">
    <section class="tm-hero">
      <div class="tm-hero-copy">
        <span class="tm-kicker">LA FRANCE À VOTRE RYTHME</span>
        <h1>Le prochain sentier<br><em>commence ici.</em></h1>
        <p>Explore des treks, prépare ton itinéraire et crée tes propres parcours sur une carte pensée pour les randonneurs.</p>
        <div class="tm-hero-search">
          <span>⌕</span>
          <input id="tm-home-search" placeholder="Rechercher un trek, une région ou un lieu…" autocomplete="off">
          <button id="tm-home-search-btn">Explorer</button>
        </div>
        <div class="tm-quick">
          <button data-home-explore>Découvrir les randonnées</button>
          <button data-home-create>✦ Créer mon parcours</button>
        </div>
      </div>
      <div class="tm-hero-visual">
        <div class="tm-map-orb">
          <div class="tm-route r1"></div><div class="tm-route r2"></div><div class="tm-route r3"></div>
          <span class="tm-pin p1">●</span><span class="tm-pin p2">●</span><span class="tm-pin p3">●</span>
          <div class="tm-compass">N</div>
        </div>
        <div class="tm-floating-card tm-fc-top"><span>🥾</span><div><b>Des itinéraires</b><small>pour tous les niveaux</small></div></div>
        <div class="tm-floating-card tm-fc-bottom"><span>✦</span><div><b>Crée ton trek</b><small>Trace · Enregistre · Pars</small></div></div>
      </div>
    </section>
    <section class="tm-features">
      <article><span>🗺️</span><div><b>Explore</b><small>Trouve ton prochain itinéraire grâce à la carte et aux filtres.</small></div></article>
      <article><span>✏️</span><div><b>Crée</b><small>Trace ton parcours et calcule automatiquement l'itinéraire pédestre.</small></div></article>
      <article><span>🎒</span><div><b>Prépare</b><small>Enregistre tes favoris, tes plans et exporte tes traces en GPX.</small></div></article>
    </section>
    <section class="tm-discover">
      <div class="tm-section-head"><div><span class="tm-kicker">À DÉCOUVRIR</span><h2>Quelques idées pour commencer</h2></div><button data-home-explore>Voir tous les treks →</button></div>
      <div id="tm-featured" class="tm-featured"><div class="tm-featured-loading">Chargement des itinéraires…</div></div>
    </section>
    <section class="tm-stats-strip">
      <div><b id="tm-stat-treks">—</b><span>treks publics</span></div>
      <div><b id="tm-stat-distance">—</b><span>km de parcours</span></div>
      <div><b id="tm-stat-creators">—</b><span>créateurs</span></div>
      <div><b>100%</b><span>pensé pour la randonnée</span></div>
    </section>
  </main>
  <footer class="tm-home-footer"><span>🥾 TrekMap France</span><span>Explorer · Créer · Partir</span></footer>
</div>
<!-- TREKMAP_HOME_END -->
'''
html = html.replace('<div id="app">', home + '\n<div id="app">', 1)
html = html.replace('<h1>🥾 TrekMap France</h1>', '<h1 style="display:flex;align-items:center"><img src="/logo-trekmap.svg" alt="TrekMap France" style="width:185px;height:auto;border-radius:12px"></h1>', 1)

script = r'''<script id="trekmap-remodel-js">
(function(){
  function init(){
    const map=document.getElementById('map');
    if(map && !document.getElementById('tm-map-hint')){
      const hint=document.createElement('div');
      hint.id='tm-map-hint';
      hint.textContent='Sélectionne un trek pour afficher son parcours';
      map.appendChild(hint);
      setTimeout(()=>hint.classList.add('hide'),4500);
    }
    const sidebar=document.getElementById('sidebar');
    if(sidebar) sidebar.setAttribute('aria-label','Exploration TrekMap France');
    const search=document.getElementById('search');
    if(search) search.setAttribute('aria-label','Rechercher un trek ou une région');
    document.querySelectorAll('.map-tools button').forEach(b=>{
      if(!b.getAttribute('title')) b.setAttribute('title',b.textContent.trim());
    });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
</script>
<script id="trekmap-home-js">
(function(){
  const home=document.getElementById('tm-home');
  if(!home)return;
  const hide=()=>{home.classList.add('tm-hidden');document.body.style.overflow='hidden';};
  const show=()=>{home.classList.remove('tm-hidden');window.scrollTo(0,0);};
  const explore=(query)=>{
    const input=document.getElementById('search');
    hide();
    const side=document.getElementById('sidebar');
    if(side)side.classList.remove('collapsed');
    setTimeout(()=>{
      if(input&&query){input.value=query;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();}
      if(typeof window.applyFilters==='function')window.applyFilters();
    },80);
  };
  const create=()=>{hide();setTimeout(()=>document.getElementById('create-button')?.click(),100);};
  const account=()=>{hide();setTimeout(()=>document.getElementById('account-button')?.click(),100);};
  document.querySelectorAll('[data-home-explore]').forEach(b=>b.addEventListener('click',()=>explore('')));
  document.querySelectorAll('[data-home-create]').forEach(b=>b.addEventListener('click',create));
  document.querySelectorAll('[data-home-account]').forEach(b=>b.addEventListener('click',account));
  document.getElementById('tm-home-logo')?.addEventListener('click',e=>{e.preventDefault();show();});
  const hs=document.getElementById('tm-home-search'),hb=document.getElementById('tm-home-search-btn');
  const go=()=>explore(hs?.value.trim()||'');
  hb?.addEventListener('click',go);hs?.addEventListener('keydown',e=>{if(e.key==='Enter')go();});
  async function loadHomeData(){
    const base=String(window.TREKMAP_API||location.origin).replace(/\/$/,'');
    try{
      const [tr,st]=await Promise.all([fetch(base+'/treks',{cache:'no-store'}),fetch(base+'/statistics',{cache:'no-store'})]);
      const treks=await tr.json(), stats=await st.json();
      const list=Array.isArray(treks)?treks:[];
      const featured=list.slice().sort((a,b)=>(b.view_count||0)-(a.view_count||0)).slice(0,3);
      const box=document.getElementById('tm-featured');
      if(box)box.innerHTML=featured.length?featured.map(t=>'<article class="tm-f-card" data-trek-id="'+Number(t.id)+'"><div class="tm-f-top"><div><h3>'+esc(t.name)+'</h3><p>'+esc(t.region||'France')+'</p></div><span>🥾</span></div><div class="tm-f-badges"><span class="tm-f-badge">'+esc(({easy:'Facile',medium:'Moyen',hard:'Difficile',extreme:'Extrême'}[t.difficulty]||'Randonnée'))+'</span></div><div class="tm-f-meta"><span>📏 '+Number(t.distance||0).toFixed(1)+' km</span><span>↗ '+Math.round(t.elevation||0)+' m</span></div></article>').join(''):'<div class="tm-featured-loading">Les premiers itinéraires arrivent bientôt.</div>';
      box?.querySelectorAll('[data-trek-id]').forEach(c=>c.addEventListener('click',()=>{hide();setTimeout(()=>window.openDetail?.(Number(c.dataset.trekId)),100);}));
      set('tm-stat-treks',stats.treks??list.length);
      set('tm-stat-distance',Number(stats.distance_km||0).toLocaleString('fr-FR'));
      set('tm-stat-creators',stats.creators??'—');
    }catch(e){
      const box=document.getElementById('tm-featured');
      if(box)box.innerHTML='<div class="tm-featured-loading">Les itinéraires sont temporairement indisponibles.</div>';
    }
  }
  function set(id,v){const e=document.getElementById(id);if(e)e.textContent=v;}
  function esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[c]));}
  const originalOpenDetail=window.openDetail;
  if(typeof originalOpenDetail==='function' && !window.__trekmapDetailWrapped){
    window.openDetail=function(id){
      originalOpenDetail(id);
      setTimeout(()=>{
        const modal=document.getElementById('modal');
        if(modal)modal.classList.add('tm-detail-modern');
      },20);
    };
    window.__trekmapDetailWrapped=true;
  }
  window.TrekMapShowHome=show;window.TrekMapHideHome=hide;
  loadHomeData();
})();
</script>'''
map_old = '<div class="map-tools"><button id="map-toggle">☰ <span class="desktop-label">Liste</span></button><button id="map-fit">⌖ <span class="desktop-label">France</span></button><button id="api-status" title="État du serveur">● API</button><button id="locate-map">◎ <span class="desktop-label">Ma position</span></button><select id="map-layers"><option value="standard">Standard</option><option value="topo">Topographique</option><option value="satellite">Satellite</option></select><button id="map-fullscreen">⛶</button></div>'
map_new = '<div class="map-tools"><button id="tm-map-options" aria-expanded="false">⚙ Carte</button><div id="tm-map-options-panel" role="menu" aria-hidden="true"><label>Type de carte</label><select id="tm-map-layers-visible"><option value="standard">Standard</option><option value="topo">Topographique</option><option value="satellite">Satellite</option></select><button type="button" data-map-action="fit">⌖ Recentrer sur la France</button><button type="button" data-map-action="locate">◎ Ma position</button><button type="button" data-map-action="fullscreen">⛶ Plein écran</button><button type="button" data-map-action="api">● État de l’API</button></div></div><div id="tm-hidden-map-controls"><button id="map-toggle"></button><button id="map-fit"></button><button id="api-status"></button><button id="locate-map"></button><select id="map-layers"><option value="standard">Standard</option><option value="topo">Topographique</option><option value="satellite">Satellite</option></select><button id="map-fullscreen"></button></div>'
html = html.replace(map_old, map_new, 1)

html = re.sub(r'\s*<script id="trekmap-remodel-js">.*?</script>', '', html, flags=re.S)
html = re.sub(r'\s*<script id="trekmap-home-js">.*?</script>', '', html, flags=re.S)
html = html.replace('</body>', script + '\n</body>', 1)

html_path.write_text(html, encoding='utf-8')
print('TrekMap production UI applied')
