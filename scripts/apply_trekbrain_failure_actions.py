"""Add actionable recovery controls to TrekBrain's failed-plan screen."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r"\s*<!-- TREKMAP_FAILURE_ACTIONS_V93_START -->.*?<!-- TREKMAP_FAILURE_ACTIONS_V93_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_API_ERROR_GUARD_V92" not in html:
    raise SystemExit("Le garde d'erreurs TrekBrain doit être installé avant les actions d'échec.")

block = r'''<!-- TREKMAP_FAILURE_ACTIONS_V93_START -->
<style id="trekmap-failure-actions-v93-css">
.tm-ai-failure-actions{margin-top:12px;padding:12px;border:1px solid #e6d8b8;border-radius:13px;background:#fffdf8}
.tm-ai-failure-actions-title{font-size:12px;font-weight:900;color:#5c4927;margin-bottom:4px}
.tm-ai-failure-actions-note{font-size:10px;line-height:1.45;color:#77684d;margin-bottom:10px}
.tm-ai-failure-buttons{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.tm-ai-failure-buttons button{min-height:43px;border-radius:11px;padding:8px 10px;font-size:11px;font-weight:900;cursor:pointer}
#tm-ai-failure-view{grid-column:1/-1;border:0;background:#116b49;color:#fff}
#tm-ai-failure-edit{border:1px solid #cddfd6;background:#fff;color:#315b49}
#tm-ai-failure-reset{border:1px solid #e2caca;background:#fff;color:#884747}
.tm-failed-preview-banner{padding:8px 10px;border-radius:10px;background:rgba(255,250,235,.96);border:1px solid #e0c88b;color:#664f20;box-shadow:0 4px 16px rgba(0,0,0,.16);font:800 12px/1.3 system-ui,sans-serif}
@media(max-width:520px){.tm-ai-failure-buttons{grid-template-columns:1fr}.tm-ai-failure-buttons button,#tm-ai-failure-view{grid-column:1}}
</style>
<script id="trekmap-failure-actions-v93-js">
(function(){
  if(window.__trekmapFailureActionsV93)return;window.__trekmapFailureActionsV93=true;
  const $=id=>document.getElementById(id);
  let lastFailure=null,failedLayer=null,failedBanner=null;

  const messageFrom=data=>{
    const detail=data&&data.detail;
    if(typeof detail==='string')return detail;
    if(detail&&typeof detail==='object'&&typeof detail.message==='string')return detail.message;
    if(data&&typeof data.message==='string')return data.message;
    return 'La préparation du trek a échoué.';
  };
  const previewFrom=data=>{
    const detail=data&&data.detail;
    const p=detail&&typeof detail==='object'?detail.failed_preview:null;
    if(!p||!Array.isArray(p.coords))return null;
    const coords=p.coords.map(x=>[Number(x?.[0]),Number(x?.[1])]).filter(x=>x.every(Number.isFinite));
    if(coords.length<2)return null;
    return {...p,coords};
  };

  function clearFailedMap(){
    try{if(failedLayer&&typeof map!=='undefined'&&map.hasLayer(failedLayer))map.removeLayer(failedLayer)}catch(_){}
    failedLayer=null;
    try{if(failedBanner&&typeof map!=='undefined')map.removeControl(failedBanner)}catch(_){}
    failedBanner=null;
  }

  function renderFailureActions(){
    const content=$('tm-ai-content');
    if(!content||!lastFailure||content.querySelector('#tm-ai-failure-actions'))return;
    const text=String(content.textContent||'').toLowerCase();
    if(!text.includes('impossible')&&!content.querySelector('.tm-ai-warning'))return;
    const box=document.createElement('section');box.id='tm-ai-failure-actions';box.className='tm-ai-failure-actions';
    box.innerHTML=`<div class="tm-ai-failure-actions-title">Que faire maintenant ?</div>
      <div class="tm-ai-failure-actions-note">Le premier bouton montre uniquement le dernier tracé provisoire calculé. Il peut être incomplet ou ne pas respecter toutes les contraintes et ne doit pas être considéré comme un itinéraire validé.</div>
      <div class="tm-ai-failure-buttons">
        <button id="tm-ai-failure-view" type="button">🗺️ Voir quand même le trek</button>
        <button id="tm-ai-failure-edit" type="button">✏️ Modifier la requête</button>
        <button id="tm-ai-failure-reset" type="button">🗑️ Nouvelle requête</button>
      </div>`;
    content.appendChild(box);
  }

  function backToForm(){
    const shell=document.querySelector('#tm-ai-overlay .tm-ai-shell');
    shell?.classList.remove('has-result');
    const side=document.querySelector('#tm-ai-overlay .tm-ai-side');
    try{side?.scrollTo({top:0,behavior:'smooth'})}catch(_){}
    setTimeout(()=>$('tm-ai-prompt')?.focus(),80);
  }

  function resetRequest(){
    clearFailedMap();
    const values={
      'tm-ai-prompt':'','tm-ai-region':'','tm-ai-days':'3','tm-ai-km':'18',
      'tm-ai-difficulty':'medium','tm-ai-route-type':'Boucle'
    };
    Object.entries(values).forEach(([id,value])=>{const el=$(id);if(el)el.value=value});
    ['tm-ai-transit','tm-ai-water','tm-ai-sleep','tm-ai-food'].forEach(id=>{const el=$(id);if(el)el.checked=true});
    const content=$('tm-ai-content');if(content)content.innerHTML='';
    const empty=$('tm-ai-empty');if(empty)empty.style.display='grid';
    $('tm-ai-progress')?.classList.remove('show');
    lastFailure=null;
    backToForm();
    if(typeof toast==='function')toast('Nouvelle requête prête.');
  }

  function showFailedPreview(){
    const p=lastFailure?.preview;
    if(!p||!Array.isArray(p.coords)||p.coords.length<2){
      if(typeof toast==='function')toast('Aucun tracé provisoire exploitable n’a été calculé pour cet échec.');
      return;
    }
    if(typeof map==='undefined'||typeof L==='undefined'){
      if(typeof toast==='function')toast('La carte n’est pas encore disponible.');
      return;
    }
    clearFailedMap();
    failedLayer=L.layerGroup();
    const line=L.polyline(p.coords,{weight:5,opacity:.9,dashArray:'9 7'}).addTo(failedLayer);
    failedLayer.addTo(map);
    try{map.fitBounds(line.getBounds().pad(.08),{padding:[24,24]})}catch(_){}
    failedBanner=L.control({position:'topright'});
    failedBanner.onAdd=()=>{const div=L.DomUtil.create('div','tm-failed-preview-banner');div.textContent='⚠️ Tracé provisoire non validé';L.DomEvent.disableClickPropagation(div);return div};
    failedBanner.addTo(map);
    $('tm-ai-close')?.click();
    setTimeout(()=>{try{map.invalidateSize()}catch(_){}},120);
    const km=Number(p.distance_km);
    const suffix=Number.isFinite(km)&&km>0?` · ${km.toFixed(1)} km`:'';
    if(typeof toast==='function')toast(`Tracé provisoire affiché${suffix}. Vérifie-le avant toute utilisation.`);
  }

  document.addEventListener('click',event=>{
    const view=event.target.closest('#tm-ai-failure-view');if(view){event.preventDefault();showFailedPreview();return}
    const edit=event.target.closest('#tm-ai-failure-edit');if(edit){event.preventDefault();backToForm();return}
    const reset=event.target.closest('#tm-ai-failure-reset');if(reset){event.preventDefault();resetRequest()}
  },true);

  const previous=window.fetch.bind(window);
  window.fetch=async function(input,init){
    const response=await previous(input,init);
    try{
      const url=String(typeof input==='string'?input:(input&&input.url)||'');
      if(url.includes('/ai/plan')){
        if(response.ok){lastFailure=null;clearFailedMap()}
        else response.clone().json().then(data=>{
          lastFailure={message:messageFrom(data),preview:previewFrom(data),status:response.status};
          setTimeout(renderFailureActions,60);setTimeout(renderFailureActions,220);
        }).catch(()=>{
          lastFailure={message:'La préparation du trek a échoué.',preview:null,status:response.status};
          setTimeout(renderFailureActions,100);
        });
      }
    }catch(_){}
    return response;
  };

  const content=$('tm-ai-content');
  if(content)new MutationObserver(()=>{if(lastFailure)setTimeout(renderFailureActions,20)}).observe(content,{childList:true,subtree:true});
})();
</script>
<!-- TREKMAP_FAILURE_ACTIONS_V93_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekBrain failed-plan actions applied")
