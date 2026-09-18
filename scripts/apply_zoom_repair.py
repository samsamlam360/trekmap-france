from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

replacement = r'''  async function zoomToTrek(id){
    const numericId=Number(id);
    let t=trekById(numericId);

    function coordsFromGeometry(g){
      if(!g||!Array.isArray(g.coordinates))return [];
      const raw=g.type==='MultiLineString'?g.coordinates.flat():g.coordinates;
      return raw
        .filter(p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(Number(p[0]))&&Number.isFinite(Number(p[1])))
        .map(p=>[Number(p[1]),Number(p[0])]);
    }

    function coordsFromTrek(item){
      if(!item)return [];
      if(Array.isArray(item.coords)&&item.coords.length){
        const clean=item.coords
          .filter(p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(Number(p[0]))&&Number.isFinite(Number(p[1])))
          .map(p=>[Number(p[0]),Number(p[1])]);
        if(clean.length)return clean;
      }
      return coordsFromGeometry(item.geometry);
    }

    function coordsFromFeatures(){
      try{
        if(!Array.isArray(traceFeatures))return [];
        const feature=traceFeatures.find(f=>Number(f?.properties?.id)===numericId);
        return feature?coordsFromGeometry(feature.geometry):[];
      }catch(_){return []}
    }

    function boundsFromRenderedLayer(item){
      try{
        if(!trekLayerGroup||!item)return null;
        let found=null;
        trekLayerGroup.eachLayer(layer=>{
          if(found||typeof layer.getBounds!=='function')return;
          const tooltip=layer.getTooltip?.();
          const label=String(tooltip?.getContent?.()||'').trim();
          if(label===String(item.name||'').trim()){
            const b=layer.getBounds();
            if(b?.isValid?.())found=b;
          }
        });
        return found;
      }catch(_){return null}
    }

    let coords=coordsFromTrek(t);
    if(!coords.length)coords=coordsFromFeatures();

    if(!coords.length){
      try{
        const base=typeof API!=='undefined'?API:'';
        const response=await fetch(base+'/treks/'+numericId,{headers:typeof headers==='function'?headers():{},cache:'no-store'});
        if(response.ok){
          const fresh=await response.json();
          t=t||fresh;
          coords=coordsFromTrek(fresh);
        }
      }catch(_){}
    }

    try{
      map.invalidateSize();
      let bounds=coords.length?L.latLngBounds(coords):boundsFromRenderedLayer(t);
      if(!bounds||!bounds.isValid?.()){
        if(typeof toast==='function')toast('Impossible de localiser ce trek sur la carte.');
        return false;
      }

      const desktop=window.innerWidth>760;
      const sidebarVisible=desktop&&!document.getElementById('sidebar')?.classList.contains('collapsed');
      const drawerOpen=!document.getElementById('tm-stable-drawer')?.classList.contains('collapsed');
      const options={
        paddingTopLeft:desktop?[sidebarVisible?430:55,70]:[24,60],
        paddingBottomRight:desktop?[105,drawerOpen?220:80]:[24,drawerOpen?200:80],
        maxZoom:15,
        animate:true
      };

      map.fitBounds(bounds.pad(.12),options);
      if(map.getZoom()>15)map.setZoom(15,{animate:true});

      track?.querySelectorAll('.tm-stable-card').forEach(card=>{
        card.classList.toggle('is-map-selected',Number(card.dataset.id)===numericId);
      });
      return true;
    }catch(err){
      console.error('Zoom TrekMap:',err);
      if(typeof toast==='function')toast('Le zoom sur ce trek a échoué.');
      return false;
    }
  }

  // Le clic sur une carte'''

pattern = r"  function zoomToTrek\(id\)\{.*?\n  \}\n\n  // Le clic sur une carte"
html2, count = re.subn(pattern, replacement, html, count=1, flags=re.S)
if count != 1:
    raise SystemExit("La fonction zoomToTrek à remplacer est introuvable")

# Rend le point d'entrée testable et réutilisable sans changer le comportement du clic existant.
html2 = html2.replace(
    "  // Le clic sur une carte de trek sert maintenant à la localiser sur la carte.",
    "  window.TrekMapZoomToTrek=zoomToTrek;\n\n  // Le clic sur une carte de trek sert maintenant à la localiser sur la carte.",
    1,
)

html_path.write_text(html2, encoding="utf-8")
print("TrekMap zoom repair applied")
