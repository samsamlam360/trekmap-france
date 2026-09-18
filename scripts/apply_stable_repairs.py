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

  // Important: une nouvelle recherche est toujours une recherche globale.
  // Cela évite qu'un ancien mode Favoris / Mes treks / Privés masque les résultats.
  visibleSearch?.addEventListener('input',()=>{
    forceAllMode();
    if(hiddenSearch)hiddenSearch.value=visibleSearch.value;
    refreshNow();
  },true);

  // Les suggestions lancent elles aussi une recherche globale, même si Favoris était actif.
  document.addEventListener('click',e=>{
    if(e.target.closest('.tm-stable-suggestion'))forceAllMode();
  },true);

  // Une recherche lancée depuis l'accueil doit également sortir d'un ancien onglet spécial.
  document.getElementById('tm-home-search-btn')?.addEventListener('click',forceAllMode,true);
  document.getElementById('tm-home-search')?.addEventListener('keydown',e=>{if(e.key==='Enter')forceAllMode()},true);

  // Les actions du profil changent de contexte : on ouvre le tiroir et on resynchronise son titre.
  document.addEventListener('click',e=>{
    const id=e.target.closest('button')?.id;
    if(id==='profile-fav'||id==='profile-mine'){
      setTimeout(()=>{drawer?.classList.remove('collapsed');syncModeUi()},80);
    }
  });

  // Après un rendu de la liste historique, le tiroir et son libellé doivent rester cohérents.
  const oldList=document.getElementById('trek-list');
  if(oldList)new MutationObserver(()=>requestAnimationFrame(syncModeUi)).observe(oldList,{childList:true,subtree:true});
  if(track)new MutationObserver(()=>requestAnimationFrame(syncModeUi)).observe(track,{childList:true,subtree:true});

  // Le menu Carte pouvait laisser les boutons de droite décalés après fermeture hors du bouton.
  function syncMapMenu(){
    document.body.classList.toggle('tm-map-menu-open',!!mapPanel?.classList.contains('tm-show'));
  }
  if(mapPanel)new MutationObserver(syncMapMenu).observe(mapPanel,{attributes:true,attributeFilter:['class','aria-hidden']});
  document.addEventListener('click',()=>setTimeout(syncMapMenu,0));
  document.addEventListener('keydown',e=>{if(e.key==='Escape')setTimeout(syncMapMenu,0)});

  // Les filtres restent instantanés et le tiroir ne doit jamais afficher un état périmé.
  ['region-filter','difficulty-filter','duration-filter','sort-filter','distance-range','distance-tolerance','elevation-range','elevation-tolerance'].forEach(id=>{
    const el=document.getElementById(id);
    const refresh=()=>{drawer?.classList.add('tm-refreshing');setTimeout(()=>{syncModeUi();drawer?.classList.remove('tm-refreshing')},120)};
    el?.addEventListener('input',refresh);
    el?.addEventListener('change',refresh);
  });

  // Le bouton Explorer rétablit explicitement le contexte général.
  document.getElementById('tm-stable-explore')?.addEventListener('click',()=>setTimeout(()=>{forceAllMode();syncModeUi()},0));
  favoritesButton?.addEventListener('click',()=>setTimeout(syncModeUi,50));

  syncModeUi();
  syncMapMenu();
})();
</script>
<!-- TREKMAP_STABLE_REPAIRS_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap stable repairs applied')
