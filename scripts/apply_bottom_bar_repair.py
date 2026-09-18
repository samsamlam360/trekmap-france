from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

# Supprime un éventuel ancien correctif puis retire le JS de navigation précédent,
# qui installait plusieurs listeners concurrents sur la barre du bas.
html = re.sub(
    r'\s*<!-- TREKMAP_BOTTOM_BAR_REPAIR_START -->.*?<!-- TREKMAP_BOTTOM_BAR_REPAIR_END -->\s*',
    '\n',
    html,
    flags=re.S,
)
html = re.sub(
    r'\s*<script id="trekmap-navigation-polish-js">.*?</script>\s*',
    '\n',
    html,
    flags=re.S,
)

block = r'''<!-- TREKMAP_BOTTOM_BAR_REPAIR_START -->
<style id="trekmap-bottom-bar-repair-css">
#tm-stable-track{scroll-behavior:auto!important;overscroll-behavior-x:contain!important;touch-action:pan-x!important}
#tm-stable-track .tm-stable-card{cursor:pointer!important;user-select:none!important;position:relative!important}
#tm-stable-track .tm-stable-card.is-map-selected{border-color:#128456!important;background:#f5fbf7!important;box-shadow:0 0 0 3px rgba(18,132,86,.15),0 14px 30px rgba(17,59,40,.16)!important;transform:translateY(-2px)!important}
#tm-stable-track .tm-stable-card:after{content:'⌖ Voir sur la carte'!important;position:absolute!important;right:10px!important;bottom:8px!important;font-size:9px!important;font-weight:850!important;color:#176b45!important;background:#edf7f1!important;border:1px solid #dceee4!important;border-radius:999px!important;padding:4px 7px!important;opacity:1!important;transform:none!important}
#tm-stable-drawer.tm-zooming .tm-drawer-shell{box-shadow:0 18px 52px rgba(10,70,42,.26)!important}
#tm-filter-collapse{position:absolute!important;z-index:5!important;right:12px!important;top:10px!important;height:34px!important;border:1px solid #d8e6df!important;border-radius:11px!important;background:#eef6f1!important;color:#176b45!important;padding:0 11px!important;font-size:11px!important;font-weight:850!important}
#sidebar .filters.tm-filters-collapsed{height:56px!important;min-height:56px!important;max-height:56px!important;overflow:hidden!important;padding:0!important}
#sidebar .filters.tm-filters-collapsed>*:not(#tm-filter-collapse){display:none!important}
#sidebar #upload-button{display:none!important}
#tm-stable-explore.tm-import-primary{background:#1b9d67!important;border-color:#42c88c!important}
@media(max-width:760px){#tm-stable-track .tm-stable-card:after{display:none!important}}
</style>
<script id="trekmap-bottom-bar-repair-js">
(function(){
  const track=document.getElementById('tm-stable-track');
  const drawer=document.getElementById('tm-stable-drawer');
  const filters=document.querySelector('#sidebar .filters');
  const topImport=document.getElementById('tm-stable-explore');
  if(!track)return;

  // Le bouton supérieur reste l'unique point d'entrée visible pour l'import GPX.
  if(topImport){
    topImport.classList.add('tm-import-primary');
    topImport.title='Importer un trek depuis un fichier GPX';
    topImport.innerHTML='⇧ <span class="tm-stable-label">Importer un trek</span>';
  }
  document.addEventListener('click',e=>{
    const button=e.target.closest?.('#tm-stable-explore');
    if(!button)return;
    e.preventDefault();
    e.stopImmediatePropagation();
    try{
      if(typeof importGPX==='function')importGPX();
      else document.getElementById('upload-button')?.click();
    }catch(err){
      console.error('Import GPX:',err);
      document.getElementById('upload-button')?.click();
    }
  },true);

  // Panneau de filtres repliable.
  if(filters&&!document.getElementById('tm-filter-collapse')){
    const toggle=document.createElement('button');
    toggle.type='button';
    toggle.id='tm-filter-collapse';
    filters.prepend(toggle);
    const applyState=collapsed=>{
      filters.classList.toggle('tm-filters-collapsed',collapsed);
      toggle.setAttribute('aria-expanded',String(!collapsed));
      toggle.textContent=collapsed?'Afficher':'Replier';
      setTimeout(()=>{try{map.invalidateSize()}catch(_){}},60);
    };
    applyState(localStorage.getItem('trekmap_filters_collapsed')==='1');
    toggle.addEventListener('click',e=>{
      e.preventDefault();
      e.stopPropagation();
      const collapsed=!filters.classList.contains('tm-filters-collapsed');
      localStorage.setItem('trekmap_filters_collapsed',collapsed?'1':'0');
      applyState(collapsed);
    });
  }

  function trekById(id){
    try{return Array.isArray(allTreks)?allTreks.find(t=>Number(t.id)===Number(id)):null}catch(_){return null}
  }
  function coordsFromGeometry(g){
    if(!g||!Array.isArray(g.coordinates))return [];
    const raw=g.type==='MultiLineString'?g.coordinates.flat():g.coordinates;
    return raw.filter(p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(Number(p[0]))&&Number.isFinite(Number(p[1])))
      .map(p=>[Number(p[1]),Number(p[0])]);
  }
  function coordsFromTrek(t){
    if(!t)return [];
    if(Array.isArray(t.coords)&&t.coords.length){
      const clean=t.coords.filter(p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(Number(p[0]))&&Number.isFinite(Number(p[1])))
        .map(p=>[Number(p[0]),Number(p[1])]);
      if(clean.length)return clean;
    }
    return coordsFromGeometry(t.geometry);
  }
  function coordsFromFeatures(id){
    try{
      if(!Array.isArray(traceFeatures))return [];
      const feature=traceFeatures.find(f=>Number(f?.properties?.id)===Number(id));
      return feature?coordsFromGeometry(feature.geometry):[];
    }catch(_){return []}
  }
  function boundsFromLayer(t){
    try{
      if(!trekLayerGroup||!t)return null;
      let found=null;
      trekLayerGroup.eachLayer(layer=>{
        if(found||typeof layer.getBounds!=='function')return;
        const label=String(layer.getTooltip?.()?.getContent?.()||'').trim();
        if(label===String(t.name||'').trim()){
          const b=layer.getBounds();
          if(b?.isValid?.())found=b;
        }
      });
      return found;
    }catch(_){return null}
  }

  async function zoomToBottomTrek(id){
    const numericId=Number(id);
    if(!Number.isFinite(numericId))return false;
    drawer?.classList.add('tm-zooming');
    let trek=trekById(numericId);
    let coords=coordsFromTrek(trek);
    if(!coords.length)coords=coordsFromFeatures(numericId);

    if(!coords.length){
      try{
        const base=typeof API!=='undefined'?API:'';
        const r=await fetch(base+'/treks/'+numericId,{headers:typeof headers==='function'?headers():{},cache:'no-store'});
        if(r.ok){
          const fresh=await r.json();
          trek=trek||fresh;
          coords=coordsFromTrek(fresh);
        }
      }catch(err){console.warn('Chargement du trek pour zoom:',err)}
    }

    try{
      map.invalidateSize();
      if(coords.length===1){
        map.setView(coords[0],15,{animate:true});
      }else{
        let bounds=coords.length>1?L.latLngBounds(coords):boundsFromLayer(trek);
        if(!bounds||!bounds.isValid?.()){
          if(typeof toast==='function')toast('Impossible de localiser ce trek sur la carte.');
          drawer?.classList.remove('tm-zooming');
          return false;
        }
        const desktop=window.innerWidth>760;
        const filtersCollapsed=filters?.classList.contains('tm-filters-collapsed');
        const drawerCollapsed=drawer?.classList.contains('collapsed');
        map.fitBounds(bounds.pad(.10),{
          paddingTopLeft:desktop?[filtersCollapsed?70:430,70]:[24,60],
          paddingBottomRight:desktop?[105,drawerCollapsed?80:215]:[24,drawerCollapsed?80:190],
          maxZoom:15,
          animate:true
        });
      }
      track.querySelectorAll('.tm-stable-card').forEach(card=>{
        card.classList.toggle('is-map-selected',Number(card.dataset.id)===numericId);
      });
      setTimeout(()=>drawer?.classList.remove('tm-zooming'),260);
      return true;
    }catch(err){
      console.error('Zoom barre du bas:',err);
      if(typeof toast==='function')toast('Le zoom sur ce trek a échoué.');
      drawer?.classList.remove('tm-zooming');
      return false;
    }
  }
  window.TrekMapBottomBarZoom=zoomToBottomTrek;

  // Un clic normal zoome. Un glissement horizontal ne déclenche pas de zoom.
  let dragStart=null;
  let dragged=false;
  track.addEventListener('pointerdown',e=>{
    if(!e.target.closest?.('.tm-stable-card'))return;
    dragStart={x:e.clientX,y:e.clientY};
    dragged=false;
  },true);
  track.addEventListener('pointermove',e=>{
    if(!dragStart)return;
    if(Math.hypot(e.clientX-dragStart.x,e.clientY-dragStart.y)>8)dragged=true;
  },true);
  track.addEventListener('pointercancel',()=>{dragStart=null;dragged=false},true);
  track.addEventListener('pointerup',()=>{setTimeout(()=>{dragStart=null},0)},true);

  track.addEventListener('click',e=>{
    const card=e.target.closest?.('.tm-stable-card');
    if(!card)return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    if(dragged){dragged=false;return;}
    zoomToBottomTrek(Number(card.dataset.id));
  },true);

  track.addEventListener('keydown',e=>{
    const card=e.target.closest?.('.tm-stable-card');
    if(!card||!(e.key==='Enter'||e.key===' '))return;
    e.preventDefault();
    zoomToBottomTrek(Number(card.dataset.id));
  },true);

  // Molette verticale = déplacement horizontal. Delta positif fait entrer les cartes de droite.
  track.addEventListener('wheel',e=>{
    if(track.scrollWidth<=track.clientWidth)return;
    const raw=Math.abs(e.deltaY)>=Math.abs(e.deltaX)?e.deltaY:e.deltaX;
    if(!raw)return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    const unit=e.deltaMode===1?24:e.deltaMode===2?track.clientWidth:1;
    const max=Math.max(0,track.scrollWidth-track.clientWidth);
    track.scrollLeft=Math.max(0,Math.min(max,track.scrollLeft+raw*unit*1.15));
  },{passive:false,capture:true});

  function decorateCards(){
    track.querySelectorAll('.tm-stable-card').forEach(card=>{
      card.setAttribute('role','button');
      card.setAttribute('tabindex','0');
      card.setAttribute('aria-label','Zoomer sur '+(card.querySelector('strong')?.textContent||'ce trek'));
    });
  }
  new MutationObserver(()=>requestAnimationFrame(decorateCards)).observe(track,{childList:true,subtree:true});
  decorateCards();
})();
</script>
<!-- TREKMAP_BOTTOM_BAR_REPAIR_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap bottom bar repair applied')
