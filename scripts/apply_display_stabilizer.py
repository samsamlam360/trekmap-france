from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

# Idempotence : une seule couche de stabilisation finale.
html = re.sub(
    r'\s*<!-- TREKMAP_DISPLAY_STABILIZER_START -->.*?<!-- TREKMAP_DISPLAY_STABILIZER_END -->\s*',
    '\n', html, flags=re.S,
)

# La navigation-polish est devenue obsolète depuis que bottom_bar_repair possède
# l'import, le repli des filtres et la molette. La garder laisse du CSS concurrent.
html = re.sub(
    r'\s*<!-- TREKMAP_NAVIGATION_POLISH_START -->.*?<!-- TREKMAP_NAVIGATION_POLISH_END -->\s*',
    '\n', html, flags=re.S,
)

# Stable-repairs possédait encore un ancien listener de clic sur les cartes du tiroir.
# Il appelait stopImmediatePropagation avant bottom_bar_repair et empêchait donc
# l'ouverture moderne du trek. On retire uniquement ce handler historique.
html = re.sub(
    r'\n\s*// Le clic sur une carte de trek sert maintenant à la localiser sur la carte\..*?\n\s*track\?\.addEventListener\(\'click\',e=>\{.*?\n\s*\},true\);',
    '\n', html, flags=re.S,
)

block = r'''<!-- TREKMAP_DISPLAY_STABILIZER_START -->
<style id="trekmap-display-stabilizer-css">
/*
  Couche finale d'affichage. Elle ne change pas les données ni les IDs historiques :
  elle tranche uniquement les conflits CSS accumulés entre les anciennes refontes.
*/
:root{--tm-top:82px;--tm-left:390px;--tm-drawer-h:184px}
html,body{width:100%;height:100%;margin:0;overflow:hidden!important}
body{min-width:0;background:#e8f1ec}
#app{position:relative!important;width:100%!important;height:100dvh!important;min-height:100vh!important;overflow:hidden!important;padding-top:var(--tm-top)!important;box-sizing:border-box!important}
#map{position:absolute!important;left:0!important;right:0!important;top:var(--tm-top)!important;bottom:0!important;width:auto!important;height:auto!important;min-width:0!important;min-height:0!important}

/* Ordre d'empilement cohérent. */
#tm-stable-drawer{z-index:3000!important}
.sidebar{z-index:3200!important}
#tm-stable-side{z-index:3300!important}
.map-tools{z-index:3400!important}
.leaflet-control-container{position:relative;z-index:2000}
#tm-stable-topbar{z-index:6000!important}
#tm-stable-suggestions{z-index:6100!important}
.toast{z-index:14000!important}
.modal-backdrop{z-index:12000!important}
#tm-home{z-index:15000!important}

/* Barre supérieure : aucune collision entre logo, recherche et actions. */
#tm-stable-topbar{box-sizing:border-box!important;grid-template-columns:minmax(220px,330px) minmax(260px,560px) minmax(300px,1fr)!important;gap:18px!important;padding:9px 20px!important;overflow:visible!important}
#tm-stable-home,#tm-stable-search-wrap,#tm-stable-actions{min-width:0!important}
#tm-stable-actions{overflow:visible!important;flex-wrap:nowrap!important}
#tm-stable-actions button{flex:0 0 auto!important;max-width:210px!important}
#tm-stable-search-wrap{width:100%!important;max-width:560px!important;justify-self:center!important}
#tm-stable-suggestions{max-height:min(330px,55vh)!important;overflow:auto!important}

/* Le statut normal n'a rien à faire au-dessus de la carte et du tiroir.
   Il réapparaît uniquement lorsqu'une erreur mérite l'attention. */
#tm-product-status{display:none!important;z-index:6500!important;top:calc(var(--tm-top) + 14px)!important;right:140px!important;bottom:auto!important}
#tm-product-status.is-error,#tm-product-status.is-offline{display:flex!important}

/* Filtres : hauteur bornée pour ne jamais passer derrière le tiroir. */
.sidebar{box-sizing:border-box!important;max-height:calc(100dvh - var(--tm-top) - 18px)!important}
#sidebar .filters{box-sizing:border-box!important;max-height:calc(100dvh - var(--tm-top) - var(--tm-drawer-h) - 46px)!important;overscroll-behavior:contain!important;scrollbar-width:thin}
#sidebar .filters::-webkit-scrollbar{width:7px}
#sidebar .filters::-webkit-scrollbar-thumb{background:#c7d8cf;border-radius:20px}
#sidebar .filters.tm-filters-collapsed{max-height:56px!important}
#tm-filter-collapse{display:flex!important;align-items:center!important;justify-content:center!important;white-space:nowrap!important}

/* Barre du bas : dimensions stables, texte non coupé, vrai défilement horizontal. */
#tm-stable-drawer{left:424px!important;right:16px!important;bottom:14px!important;height:var(--tm-drawer-h)!important;max-width:none!important;transition:left .22s ease,height .22s ease!important}
#tm-stable-drawer.collapsed{height:45px!important}
#tm-stable-drawer .tm-drawer-shell{overflow:hidden!important}
#tm-stable-track{box-sizing:border-box!important;width:100%!important;height:139px!important;overflow-x:auto!important;overflow-y:hidden!important;display:flex!important;flex-wrap:nowrap!important;gap:13px!important;scrollbar-gutter:auto!important;scroll-snap-type:x proximity!important}
#tm-stable-drawer.collapsed #tm-stable-track{display:none!important}
#tm-stable-track .tm-stable-card{box-sizing:border-box!important;min-width:190px!important;max-width:none!important;overflow:hidden!important}
#tm-stable-track .tm-stable-card strong{overflow:hidden!important;text-overflow:ellipsis!important}
#tm-stable-track .tm-stable-card:after{pointer-events:none!important;max-width:calc(100% - 20px)!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
body.tm-filters-compact #tm-stable-drawer{left:16px!important}

/* Contrôles carte et raccourcis : pas de chevauchement. */
.map-tools{right:16px!important;top:16px!important;max-width:min(250px,calc(100vw - 32px))!important}
#tm-map-options-panel{right:0!important;left:auto!important;max-width:min(250px,calc(100vw - 32px))!important;max-height:min(330px,calc(100dvh - var(--tm-top) - 90px))!important;overflow:auto!important}
#tm-stable-side{right:16px!important;top:275px!important}
body.tm-map-menu-open #tm-stable-side{top:430px!important}

/* Modales : le principal défaut visuel était l'overflow:hidden de la fiche moderne.
   Toutes les fiches/profils restent maintenant dans le viewport et sont scrollables. */
.modal-backdrop{box-sizing:border-box!important;padding:20px!important;overflow:auto!important;align-items:center!important;justify-content:center!important}
.modal{box-sizing:border-box!important;width:min(820px,calc(100vw - 40px))!important;max-width:820px!important;max-height:calc(100dvh - 40px)!important;overflow-x:hidden!important;overflow-y:auto!important;overscroll-behavior:contain!important;scrollbar-width:thin!important}
#modal.tm-detail-modern{overflow-y:auto!important;overflow-x:hidden!important;padding-bottom:0!important}
#modal.tm-detail-modern>.modal-head{position:relative!important;z-index:1!important}
#modal.tm-detail-modern>.tm-detail-upgrade{margin:16px 25px 0!important;padding-top:15px!important}
#modal.tm-detail-modern>.comments{margin-bottom:24px!important}
.tm-detail-hero{width:100%!important;max-width:100%!important}
.tm-detail-hero img{display:block!important}
.tm-extra-grid,.tm-profile-cards{min-width:0!important}
.tm-extra-card,.tm-profile-card,.tm-library-section{min-width:0!important;overflow:hidden!important}
.tm-extra-card b,.tm-library-row b,.tm-library-row small{overflow-wrap:anywhere!important}
.tm-profile-upgrade{margin:16px 0 0!important;padding-top:15px!important}
.tm-library{align-items:start!important}
.tm-advanced-form>*{min-width:0!important}
.tm-advanced-form input,.tm-advanced-form select,.tm-advanced-form textarea{box-sizing:border-box!important;max-width:100%!important}

/* Les anciens composants générés ne doivent jamais refaire surface. */
#tm-results-drawer,#tm-side-actions,#bottom-nav{display:none!important}

/* Tablettes : on gagne de la place sans écraser la recherche. */
@media(max-width:1200px){
  :root{--tm-left:350px}
  #tm-stable-topbar{grid-template-columns:220px minmax(230px,1fr) auto!important;gap:10px!important;padding-inline:12px!important}
  .tm-stable-copy small{display:none!important}
  .tm-stable-copy strong{font-size:21px!important}
  .tm-stable-brand svg{width:64px!important;flex-basis:64px!important}
  #tm-stable-actions button{padding-inline:11px!important}
  #sidebar{width:350px!important;min-width:350px!important}
  #tm-stable-drawer{left:374px!important}
  .leaflet-left{left:374px!important}
  body.tm-filters-compact #tm-stable-drawer{left:16px!important}
}

@media(max-width:900px){
  :root{--tm-top:70px;--tm-left:min(340px,calc(100vw - 24px));--tm-drawer-h:174px}
  #app{padding-top:var(--tm-top)!important}
  #map{top:var(--tm-top)!important}
  #tm-stable-topbar{height:var(--tm-top)!important;grid-template-columns:54px minmax(0,1fr) auto!important;gap:8px!important;padding:7px 9px!important}
  .tm-stable-brand svg{width:48px!important;height:44px!important;flex-basis:48px!important}
  .tm-stable-copy{display:none!important}
  #tm-stable-search-wrap{height:44px!important;max-width:none!important}
  #tm-stable-actions{gap:4px!important}
  #tm-stable-actions button{width:40px!important;height:40px!important;padding:0!important;justify-content:center!important;border-radius:12px!important}
  #tm-stable-actions .tm-stable-label,#tm-stable-account-name,#tm-stable-account>span:last-child{display:none!important}
  #tm-stable-account{min-width:40px!important}
  .sidebar{left:12px!important;top:calc(var(--tm-top) + 12px)!important;width:var(--tm-left)!important;min-width:0!important;max-width:calc(100vw - 24px)!important}
  #sidebar .filters{max-height:calc(100dvh - var(--tm-top) - var(--tm-drawer-h) - 38px)!important}
  #tm-stable-drawer,#tm-stable-drawer.collapsed{left:12px!important;right:12px!important}
  #tm-stable-drawer{bottom:10px!important}
  .leaflet-left{left:0!important}
  .map-tools{right:10px!important;top:10px!important}
  #tm-stable-side{right:10px!important;top:auto!important;bottom:calc(var(--tm-drawer-h) + 24px)!important;flex-direction:row!important}
  #tm-stable-side button{width:58px!important;min-height:58px!important;border-radius:16px!important}
  #tm-stable-side small{display:none!important}
  body.tm-map-menu-open #tm-stable-side{top:auto!important;bottom:calc(var(--tm-drawer-h) + 24px)!important}
  .map-legend{display:none!important}
  #tm-product-status.is-error,#tm-product-status.is-offline{top:calc(var(--tm-top) + 10px)!important;right:10px!important}
}

@media(max-width:760px){
  .modal-backdrop{padding:0!important;align-items:flex-end!important;overflow:hidden!important}
  .modal{width:100%!important;max-width:none!important;max-height:92dvh!important;border-radius:22px 22px 0 0!important;padding:16px!important;overflow-y:auto!important}
  #modal.tm-detail-modern{padding:0 0 16px!important}
  #modal.tm-detail-modern>.tm-detail-upgrade{margin:14px 16px 0!important}
  #modal.tm-detail-modern>.badges,#modal.tm-detail-modern>.detail-grid,#modal.tm-detail-modern>.detail-desc,#modal.tm-detail-modern>.modal-actions,#modal.tm-detail-modern>.comments{margin-left:16px!important;margin-right:16px!important}
  #modal.tm-detail-modern>.modal-head{padding:19px 16px 16px!important}
  .tm-library{grid-template-columns:1fr!important}
  .tm-profile-cards,.tm-extra-grid,.detail-grid{grid-template-columns:1fr 1fr!important}
  .tm-detail-actions{display:grid!important;grid-template-columns:1fr 1fr!important}
  .tm-detail-actions button{width:100%!important;min-width:0!important}
  #tm-stable-track .tm-stable-card{flex:0 0 min(78vw,280px)!important;min-width:220px!important}
  #tm-stable-drawer.collapsed{height:45px!important}
}

@media(max-width:480px){
  :root{--tm-drawer-h:165px}
  #tm-stable-search{font-size:12px!important;padding-right:36px!important}
  #tm-stable-actions button{width:36px!important;height:36px!important}
  .tm-stable-avatar{width:32px!important;height:32px!important}
  .tm-profile-cards,.tm-extra-grid,.detail-grid{grid-template-columns:1fr 1fr!important;gap:7px!important}
  .tm-detail-actions{grid-template-columns:1fr!important}
  #tm-stable-side{display:none!important}
  #tm-stable-track .tm-stable-card{flex-basis:min(82vw,270px)!important;min-width:210px!important}
}
</style>
<script id="trekmap-display-stabilizer-js">
(function(){
  const filters=document.querySelector('#sidebar .filters');
  const drawer=document.getElementById('tm-stable-drawer');
  const modal=document.getElementById('modal');
  const backdrop=document.getElementById('modal-backdrop');

  // Retire les anciens composants s'ils ont survécu à une ancienne construction.
  ['tm-results-drawer','tm-side-actions'].forEach(id=>document.getElementById(id)?.remove());

  function syncFilterLayout(){
    const compact=!!filters?.classList.contains('tm-filters-collapsed');
    document.body.classList.toggle('tm-filters-compact',compact);
    requestAnimationFrame(()=>{try{map.invalidateSize()}catch(_){}});
  }
  if(filters){
    new MutationObserver(syncFilterLayout).observe(filters,{attributes:true,attributeFilter:['class']});
    syncFilterLayout();
  }

  // Une modale ouverte ne doit jamais être derrière la barre du haut.
  function syncModal(){
    const open=!!backdrop&&getComputedStyle(backdrop).display!=='none';
    document.body.classList.toggle('tm-modal-open',open);
    if(open&&modal){
      modal.scrollTop=0;
      modal.querySelectorAll('.tm-mobile-sheet-handle').forEach((el,i)=>{if(i)el.remove()});
    }
  }
  if(backdrop)new MutationObserver(syncModal).observe(backdrop,{attributes:true,attributeFilter:['style','class']});

  // Les URL de photo externes peuvent mourir. Dans ce cas on affiche un vrai placeholder,
  // pas une icône d'image cassée digne d'un site de 2004.
  document.addEventListener('error',e=>{
    const img=e.target;
    if(!(img instanceof HTMLImageElement)||!img.closest('.tm-detail-hero'))return;
    const parent=img.parentElement;if(!parent)return;
    parent.innerHTML='<div class="tm-detail-hero-empty">🥾 <span>Photo indisponible pour ce trek.</span></div>';
  },true);

  // Les changements de viewport (rotation mobile, redimensionnement) recalculent Leaflet.
  let resizeTimer=0;
  window.addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=setTimeout(()=>{syncFilterLayout();try{map.invalidateSize()}catch(_){}},120);
  },{passive:true});

  // Empêche le tiroir de rester visuellement en état de chargement après une exception.
  window.addEventListener('unhandledrejection',()=>drawer?.classList.remove('tm-refreshing','tm-zooming'));
  window.addEventListener('error',()=>drawer?.classList.remove('tm-refreshing','tm-zooming'));

  syncModal();
})();
</script>
<!-- TREKMAP_DISPLAY_STABILIZER_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap display stabilizer applied')
