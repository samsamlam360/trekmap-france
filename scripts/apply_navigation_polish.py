from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r'\s*<!-- TREKMAP_NAVIGATION_POLISH_START -->.*?<!-- TREKMAP_NAVIGATION_POLISH_END -->\s*',
    '\n',
    html,
    flags=re.S,
)

block = r'''<!-- TREKMAP_NAVIGATION_POLISH_START -->
<style id="trekmap-navigation-polish-css">
/* Barre de résultats plus lisible et plus agréable à manipuler. */
#tm-stable-drawer .tm-drawer-shell{border-color:#cfe1d7!important;box-shadow:0 18px 48px rgba(10,54,35,.20)!important}
#tm-stable-track{scroll-behavior:auto!important;scroll-snap-type:x proximity!important;overscroll-behavior-x:contain!important;padding-bottom:12px!important}
#tm-stable-track .tm-stable-card{scroll-snap-align:start!important;cursor:pointer!important;user-select:none!important}
#tm-stable-track .tm-stable-card:hover{border-color:#73b18f!important;box-shadow:0 12px 28px rgba(20,91,57,.16)!important}
#tm-stable-track .tm-stable-card.is-map-selected{border-color:#168b59!important;background:#f7fcf9!important;box-shadow:0 0 0 3px rgba(22,139,89,.14),0 14px 30px rgba(20,91,57,.15)!important}
#tm-stable-track .tm-stable-card:after{content:'⌖ Zoomer sur ce trek'!important;opacity:1!important;transform:none!important;background:#edf7f1!important;color:#176b45!important}

/* Panneau de filtres repliable. */
#tm-filter-collapse{position:absolute!important;z-index:3!important;right:12px!important;top:10px!important;height:34px!important;border:1px solid #d8e6df!important;border-radius:11px!important;background:#eef6f1!important;color:#176b45!important;padding:0 11px!important;font-size:11px!important;font-weight:850!important;box-shadow:none!important}
#tm-filter-collapse:hover{background:#e3f1e9!important}
#sidebar .filters.tm-filters-collapsed{height:56px!important;min-height:56px!important;max-height:56px!important;overflow:hidden!important;padding:0!important}
#sidebar .filters.tm-filters-collapsed> *:not(#tm-filter-collapse){display:none!important}
#sidebar .filters.tm-filters-collapsed:before{top:18px!important}

/* L'import est maintenant dans la barre supérieure. */
#sidebar #upload-button{display:none!important}
#tm-stable-explore.tm-import-primary{background:#1b9d67!important;border-color:#42c88c!important;box-shadow:0 8px 20px rgba(12,99,63,.20)!important}
#tm-stable-explore.tm-import-primary:hover{background:#16875a!important}

@media(max-width:760px){
  #tm-filter-collapse{right:9px!important;top:9px!important;width:36px!important;padding:0!important;font-size:0!important}
  #tm-filter-collapse:after{content:'⌃';font-size:16px}
  #sidebar .filters.tm-filters-collapsed #tm-filter-collapse:after{content:'⌄'}
  #tm-stable-track .tm-stable-card:after{display:none!important}
}
</style>
<script id="trekmap-navigation-polish-js">
(function(){
  const track=document.getElementById('tm-stable-track');
  const drawer=document.getElementById('tm-stable-drawer');
  const filters=document.querySelector('#sidebar .filters');
  const topImport=document.getElementById('tm-stable-explore');

  // 1) Remplace Explorer par Importer un trek sans casser la logique historique.
  if(topImport){
    topImport.classList.add('tm-import-primary');
    topImport.title='Importer un trek depuis un fichier GPX';
    topImport.innerHTML='⇧ <span class="tm-stable-label">Importer un trek</span>';
  }
  document.addEventListener('click',e=>{
    const button=e.target.closest('#tm-stable-explore');
    if(!button)return;
    e.preventDefault();
    e.stopImmediatePropagation();
    try{
      if(typeof importGPX==='function')importGPX();
      else document.getElementById('upload-button')?.click();
    }catch(_){document.getElementById('upload-button')?.click()}
  },true);

  // 2) Filtres repliables. L'état est conservé entre deux visites.
  if(filters && !document.getElementById('tm-filter-collapse')){
    const toggle=document.createElement('button');
    toggle.type='button';
    toggle.id='tm-filter-collapse';
    toggle.setAttribute('aria-expanded','true');
    toggle.textContent='Replier';
    filters.prepend(toggle);
    const saved=localStorage.getItem('trekmap_filters_collapsed')==='1';
    if(saved){
      filters.classList.add('tm-filters-collapsed');
      toggle.setAttribute('aria-expanded','false');
      toggle.textContent='Afficher';
    }
    toggle.addEventListener('click',e=>{
      e.preventDefault();
      e.stopPropagation();
      const collapsed=filters.classList.toggle('tm-filters-collapsed');
      toggle.setAttribute('aria-expanded',String(!collapsed));
      toggle.textContent=collapsed?'Afficher':'Replier';
      localStorage.setItem('trekmap_filters_collapsed',collapsed?'1':'0');
      setTimeout(()=>{try{map.invalidateSize()}catch(_){}},80);
    });
  }

  // 3) Clic sur une carte du tiroir : zoom uniquement, sans ouvrir la fiche.
  // Le listener est placé sur document en capture, donc il passe avant les anciens handlers du tiroir.
  let pointerDown=null;
  let pointerMoved=false;
  document.addEventListener('pointerdown',e=>{
    const card=e.target.closest?.('.tm-stable-card');
    if(!card)return;
    pointerDown={x:e.clientX,y:e.clientY,id:Number(card.dataset.id)};
    pointerMoved=false;
  },true);
  document.addEventListener('pointermove',e=>{
    if(!pointerDown)return;
    if(Math.hypot(e.clientX-pointerDown.x,e.clientY-pointerDown.y)>7)pointerMoved=true;
  },true);
  document.addEventListener('pointerup',()=>{setTimeout(()=>{pointerDown=null},0)},true);

  document.addEventListener('click',e=>{
    const card=e.target.closest?.('.tm-stable-card');
    if(!card)return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if(pointerMoved){pointerMoved=false;return;}
    const id=Number(card.dataset.id);
    track?.querySelectorAll('.tm-stable-card').forEach(c=>c.classList.toggle('is-map-selected',Number(c.dataset.id)===id));
    try{
      const result=window.TrekMapZoomToTrek?.(id);
      if(result && typeof result.catch==='function')result.catch(()=>{});
    }catch(err){console.error('Zoom trek:',err)}
  },true);

  // 4) Molette verticale => défilement horizontal fluide de gauche à droite.
  // Visuellement les cartes passent de la droite vers la gauche quand on descend la molette.
  let wheelTarget=track?.scrollLeft||0;
  let wheelFrame=0;
  function animateWheel(){
    if(!track){wheelFrame=0;return}
    const diff=wheelTarget-track.scrollLeft;
    if(Math.abs(diff)<0.5){track.scrollLeft=wheelTarget;wheelFrame=0;return}
    track.scrollLeft+=diff*0.28;
    wheelFrame=requestAnimationFrame(animateWheel);
  }
  track?.addEventListener('wheel',e=>{
    if(Math.abs(e.deltaY)<=Math.abs(e.deltaX))return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const max=Math.max(0,track.scrollWidth-track.clientWidth);
    wheelTarget=Math.max(0,Math.min(max,wheelTarget+e.deltaY*1.35));
    if(!wheelFrame)wheelFrame=requestAnimationFrame(animateWheel);
  },{passive:false,capture:true});

  // Maintient les cartes accessibles après chaque rerendu des résultats.
  function decorateCards(){
    track?.querySelectorAll('.tm-stable-card').forEach(card=>{
      card.setAttribute('role','button');
      card.setAttribute('tabindex','0');
      card.setAttribute('aria-label','Zoomer sur '+(card.querySelector('strong')?.textContent||'ce trek'));
    });
  }
  if(track){
    new MutationObserver(()=>requestAnimationFrame(decorateCards)).observe(track,{childList:true,subtree:true});
    decorateCards();
  }
})();
</script>
<!-- TREKMAP_NAVIGATION_POLISH_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap navigation polish applied')
