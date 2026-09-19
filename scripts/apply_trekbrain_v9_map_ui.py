"""TrekBrain v9.1 map resources, refinement memory and saved-trek updates."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r"\s*<!-- TREKMAP_TREKBRAIN_V91_MAP_START -->.*?<!-- TREKMAP_TREKBRAIN_V91_MAP_END -->\s*",
    "\n",
    html,
    flags=re.S,
)
if "TREKMAP_TREKBRAIN_V9_UI_START" not in html:
    raise SystemExit("TrekBrain v9 UI doit être construite avant la couche cartographique v9.1.")

block = r'''<!-- TREKMAP_TREKBRAIN_V91_MAP_START -->
<style id="trekmap-trekbrain-v91-map-css">
.tm-v91-resource-icon{background:transparent!important;border:0!important}
.tm-v91-resource-icon span{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:#fff;border:2px solid #174f3a;box-shadow:0 2px 9px rgba(0,0,0,.26);font-size:17px;line-height:1}
.tm-v91-resource-icon.water span{border-color:#2376a8}.tm-v91-resource-icon.camping span{border-color:#4b7f39}.tm-v91-resource-icon.refuge span{border-color:#77572f}.tm-v91-resource-icon.station span{border-color:#754aa5}.tm-v91-resource-icon.transport span{border-color:#b26b24}.tm-v91-resource-icon.trail span{border-color:#365f49}
.tm-v91-legend{min-width:176px;padding:9px 10px;border-radius:12px;background:rgba(255,255,255,.96);box-shadow:0 5px 20px rgba(0,0,0,.18);font:600 12px/1.25 system-ui,sans-serif;color:#29473a}
.tm-v91-legend b{display:block;margin-bottom:6px}.tm-v91-legend label{display:flex;align-items:center;gap:6px;margin:5px 0;cursor:pointer}.tm-v91-legend input{accent-color:#176b4b}.tm-v91-legend small{display:block;margin-top:5px;color:#65776e;font-weight:500;line-height:1.3}
.tm-v91-map-summary{margin:10px 0;padding:9px 10px;border:1px solid #dce8e1;border-radius:10px;background:#f8fbf9;color:#466257;font-size:13px;line-height:1.45}.tm-v91-map-summary b{color:#224d3a}
</style>
<script id="trekmap-trekbrain-v91-map-js">
(function(){
  if(window.__trekmapTrekBrainV91Map)return;window.__trekmapTrekBrainV91Map=true;
  const $=id=>document.getElementById(id);
  const endpoint=path=>(typeof API!=='undefined'?API:'')+path;
  const authHeaders=(extra={},method='GET')=>{try{return typeof headers==='function'?headers(extra,method):extra}catch(_){return extra}};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const safeUrl=v=>{try{const u=new URL(String(v||''));return ['http:','https:'].includes(u.protocol)?u.href:''}catch(_){return''}};
  const meta={
    water:{emoji:'🚰',label:'Eau'},camping:{emoji:'⛺',label:'Campings'},refuge:{emoji:'🏠',label:'Refuges'},
    station:{emoji:'🚉',label:'Gares'},transport:{emoji:'🚌',label:'Bus / transports'},trail:{emoji:'🥾',label:'Sentiers nommés'}
  };
  let current=null,basePrompt='',history=[],savedTrekId=null,legend=null;
  const groups={};

  function clearGroups(){
    try{Object.values(groups).forEach(g=>{if(g&&typeof map!=='undefined'&&map.hasLayer(g))map.removeLayer(g)})}catch(_){}
    Object.keys(groups).forEach(k=>delete groups[k]);
    try{if(legend&&typeof map!=='undefined')map.removeControl(legend)}catch(_){}legend=null;
  }

  function fallbackPoints(plan){
    const out=[];
    (plan?.water||[]).forEach(x=>out.push({...x,kind:'water',type:"Point d'eau"}));
    (plan?.accommodations||[]).forEach(x=>out.push({...x,kind:String(x.type||'').toLowerCase().includes('camp')?'camping':'refuge'}));
    (plan?.points_of_interest||[]).forEach(x=>{const t=String(x.type||'').toLowerCase();if(t.includes('transport'))out.push({...x,kind:/gare|station|train/i.test(x.name||'')?'station':'transport'});if(t.includes('balis'))out.push({...x,kind:'trail'})});
    return out;
  }

  function pointsFor(plan){
    const pts=Array.isArray(plan?.map_resources?.points)?plan.map_resources.points:fallbackPoints(plan);
    return pts.filter(p=>meta[p.kind]&&Number.isFinite(Number(p.lat))&&Number.isFinite(Number(p.lon)));
  }

  function popupHtml(p){
    const m=meta[p.kind]||{emoji:'•',label:p.type||'Point'};
    const source=safeUrl(p.source_url);
    return `<div style="min-width:190px"><b>${m.emoji} ${esc(p.name||m.label)}</b><br><span>${esc(m.label)}${p.route_day?` · jour ${Number(p.route_day)}`:''}</span>${Number.isFinite(Number(p.distance_to_route_km))?`<br><small>À ${Number(p.distance_to_route_km).toFixed(1)} km du tracé</small>`:''}${p.notes?`<br><small>${esc(p.notes)}</small>`:''}${source?`<br><a href="${esc(source)}" target="_blank" rel="noopener noreferrer">Voir la source cartographique</a>`:''}</div>`;
  }

  function drawResources(plan){
    if(typeof map==='undefined'||typeof L==='undefined')return;
    const pts=pointsFor(plan);clearGroups();if(!pts.length)return;
    Object.keys(meta).forEach(kind=>groups[kind]=L.layerGroup());
    pts.forEach(p=>{
      const m=meta[p.kind];
      const icon=L.divIcon({className:`tm-v91-resource-icon ${p.kind}`,html:`<span>${m.emoji}</span>`,iconSize:[30,30],iconAnchor:[15,15],popupAnchor:[0,-16]});
      L.marker([Number(p.lat),Number(p.lon)],{icon,title:p.name||m.label}).bindPopup(popupHtml(p)).addTo(groups[p.kind]);
    });
    Object.values(groups).forEach(g=>g.addTo(map));
    const counts={};pts.forEach(p=>counts[p.kind]=(counts[p.kind]||0)+1);
    legend=L.control({position:'bottomright'});
    legend.onAdd=()=>{
      const div=L.DomUtil.create('div','tm-v91-legend');
      div.innerHTML='<b>Repères TrekBrain</b>'+Object.keys(meta).filter(k=>counts[k]).map(k=>`<label><input type="checkbox" data-v91-kind="${k}" checked> <span>${meta[k].emoji} ${meta[k].label} (${counts[k]})</span></label>`).join('')+'<small>Points proches du tracé. Vérifie les conditions actuelles avant de partir.</small>';
      L.DomEvent.disableClickPropagation(div);L.DomEvent.disableScrollPropagation(div);
      div.addEventListener('change',e=>{const input=e.target.closest('[data-v91-kind]');if(!input)return;const g=groups[input.dataset.v91Kind];if(!g)return;input.checked?g.addTo(map):map.removeLayer(g)});
      return div;
    };
    legend.addTo(map);
  }

  function resourceSummary(){
    const panel=$('tm-v9-panel');if(!panel||!current)return;
    panel.querySelector('.tm-v91-map-summary')?.remove();
    const pts=pointsFor(current);if(!pts.length)return;
    const counts={};pts.forEach(p=>counts[p.kind]=(counts[p.kind]||0)+1);
    const parts=Object.keys(meta).filter(k=>counts[k]).map(k=>`${meta[k].emoji} ${meta[k].label}: ${counts[k]}`);
    const box=document.createElement('div');box.className='tm-v91-map-summary';box.innerHTML=`<b>Repères ajoutés sur la carte</b><br>${parts.map(esc).join(' · ')}<br><small>Chaque point est filtré selon sa proximité avec le tracé et, quand possible, associé à un jour.</small>`;
    const ask=panel.querySelector('.tm-v9-ask');ask?panel.insertBefore(box,ask):panel.appendChild(box);
  }

  function descriptionFor(plan){return [plan?.summary||'',...(plan?.stages||[]).map(s=>`Jour ${s.day}: ${s.title} — ${s.distance_km} km, +${s.elevation_gain_m} m.`)].join('\n')}
  function extrasFor(plan){
    const base=(plan?.points_of_interest||[]).map(p=>({name:p.name||'Point',type:p.type||'Point',lat:Number(p.lat),lon:Number(p.lon)}));
    const resources=pointsFor(plan).map(p=>({name:p.name||'Point',type:(meta[p.kind]?.label||p.type||'Point'),lat:Number(p.lat),lon:Number(p.lon)}));
    const merged=[],seen=new Set();[...base,...resources].forEach(p=>{if(!Number.isFinite(p.lat)||!Number.isFinite(p.lon))return;const key=`${p.name}|${p.lat.toFixed(5)}|${p.lon.toFixed(5)}`;if(seen.has(key))return;seen.add(key);merged.push(p)});
    return {route_type:plan?.route_type||'',best_season:plan?.best_season||'',start_name:plan?.start?.name||'',end_name:plan?.end?.name||'',photos:[],points_of_interest:merged.slice(0,50)};
  }

  async function updateSavedPlan(){
    if(!savedTrekId||!current)return;
    const btn=$('tm-ai-save');if(btn){btn.disabled=true;btn.textContent='Mise à jour…'}
    try{
      const waypoints=(current.waypoints||[]).map(p=>[Number(p.lat),Number(p.lon)]).filter(p=>p.every(Number.isFinite));
      if(waypoints.length<2)throw new Error('Le plan ne contient pas assez de waypoints.');
      const payload={name:current.title||'Trek IA',region:current.region||'Non renseignée',difficulty:current.difficulty||'medium',description:descriptionFor(current),duration_days:Number(current.duration_days||1),coords:waypoints};
      const r=await fetch(endpoint(`/treks/${Number(savedTrekId)}/ai-redraw`),{method:'PUT',headers:authHeaders({'Content-Type':'application/json'},'PUT'),body:JSON.stringify(payload)});
      const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||'Mise à jour du trek impossible.');
      await fetch(endpoint(`/treks/${Number(savedTrekId)}/extras`),{method:'PUT',headers:authHeaders({'Content-Type':'application/json'},'PUT'),body:JSON.stringify(extrasFor(current))});
      try{await loadTraces()}catch(_){};if(typeof toast==='function')toast('Trek recalculé et mis à jour sans créer de doublon.');
      setTimeout(()=>{try{window.TrekMapOpenTrek?.(Number(savedTrekId))}catch(_){}},100);
    }catch(err){if(typeof toast==='function')toast(err.message||'Mise à jour impossible.');}
    finally{decorateSaveButton()}
  }

  function decorateSaveButton(){const b=$('tm-ai-save');if(!b)return;b.disabled=false;if(savedTrekId)b.textContent='Mettre à jour ce trek dans TrekMap'}

  const previous=window.fetch.bind(window);
  window.fetch=async function(input,init){
    let nextInit=init;const url=String(typeof input==='string'?input:(input&&input.url)||'');
    try{
      if(url.includes('/ai/plan')&&nextInit?.body){
        const body=JSON.parse(String(nextInit.body));
        const prompt=String(body.prompt||'').trim();
        if(body.current_plan){
          if(prompt)history.push(prompt);history=history.slice(-4);
          const memory=[basePrompt,...history.map((x,i)=>`Modification ${i+1}: ${x}`)].filter(Boolean).join('\n');
          if(memory)body.prompt=memory.slice(0,3900);
        }else{
          basePrompt=prompt;history=[];savedTrekId=null;clearGroups();
        }
        nextInit={...nextInit,body:JSON.stringify(body)};
      }
    }catch(_){}
    const response=await previous(input,nextInit);
    try{
      if(response.ok&&url.includes('/ai/plan'))response.clone().json().then(data=>{if(data&&typeof data==='object'){current=data;setTimeout(()=>{drawResources(data);resourceSummary();decorateSaveButton()},80)}}).catch(()=>{});
      if(response.ok&&/\/treks\/draw(?:\?|$)/.test(url))response.clone().json().then(data=>{if(data?.id){savedTrekId=Number(data.id);setTimeout(decorateSaveButton,120)}}).catch(()=>{});
    }catch(_){}
    return response;
  };

  document.addEventListener('click',e=>{
    const preview=e.target.closest('#tm-ai-preview');if(preview&&current)setTimeout(()=>drawResources(current),60);
    const save=e.target.closest('#tm-ai-save');if(save&&savedTrekId&&current){e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();updateSavedPlan()}
  },true);

  const content=$('tm-ai-content');if(content)new MutationObserver(()=>{if(current)setTimeout(()=>{resourceSummary();decorateSaveButton()},20)}).observe(content,{childList:true,subtree:false});
})();
</script>
<!-- TREKMAP_TREKBRAIN_V91_MAP_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekBrain v9.1 map resources and refinement memory applied")
