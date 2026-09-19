"""Add clear start/end markers, daily colors and coherent route selection.

When a saved trek is selected, its normal green overview trace is hidden so the
per-day colored trace is the only route shown. Clicking the map away from the
selected route exits selection and restores the normal green overview.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r"\s*<!-- TREKMAP_ROUTE_DAY_VISUALS_START -->.*?<!-- TREKMAP_ROUTE_DAY_VISUALS_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_AI_EXPERIENCE_START" not in html:
    raise SystemExit("L'interface TrekMap AI doit être construite avant les couleurs par jour.")

block = r'''<!-- TREKMAP_ROUTE_DAY_VISUALS_START -->
<style id="trekmap-route-day-visuals-css">
.tm-route-endpoint{background:transparent!important;border:0!important}
.tm-route-endpoint span{
  display:grid;place-items:center;width:34px;height:34px;border-radius:50%;
  border:3px solid #fff;color:#fff;font:900 14px/1 system-ui,sans-serif;
  box-shadow:0 3px 12px rgba(0,0,0,.32)
}
.tm-route-endpoint.tm-route-start span{background:#166534}
.tm-route-endpoint.tm-route-end span{background:#b42318}
.tm-route-endpoint.tm-route-both span{background:#7048a8;width:40px}
.tm-route-day-legend{
  min-width:150px;max-height:190px;overflow:auto;padding:9px 10px;
  border-radius:12px;background:rgba(255,255,255,.96);box-shadow:0 5px 20px rgba(0,0,0,.18);
  color:#29473a;font:700 12px/1.3 system-ui,sans-serif
}
.tm-route-day-legend b{display:block;margin-bottom:6px}.tm-route-day-row{display:flex;align-items:center;gap:7px;margin:4px 0;white-space:nowrap}
.tm-route-day-swatch{display:inline-block;width:24px;height:5px;border-radius:99px;flex:0 0 auto}
.tm-route-day-legend small{display:block;margin-top:7px;color:#66786f;font-weight:600;line-height:1.35}
@media(max-width:820px){.tm-route-day-legend{margin-bottom:64px!important;max-height:150px;font-size:11px}}
</style>
<script id="trekmap-route-day-visuals-js">
(function(){
  if(window.__trekmapRouteDayVisuals)return;window.__trekmapRouteDayVisuals=true;
  const palette=['#1565c0','#d32f2f','#2e7d32','#ef6c00','#7b1fa2','#00838f','#c2185b','#5d4037','#455a64','#9e9d24','#3949ab','#ad1457','#00796b','#6a1b9a'];
  let aiPlan=null,aiGroup=null,selectedGroup=null,manualEndpoints=null,aiLegend=null,selectedLegend=null;
  let selectedTrekId=null,routeClickGuard=false,mapExitBound=false;

  const cleanCoords=coords=>(Array.isArray(coords)?coords:[]).map(p=>[Number(p?.[0]),Number(p?.[1])]).filter(p=>p.every(Number.isFinite)&&Math.abs(p[0])<=90&&Math.abs(p[1])<=180);
  function km(a,b){
    const r=Math.PI/180,lat1=a[0]*r,lat2=b[0]*r,dlat=(b[0]-a[0])*r,dlon=(b[1]-a[1])*r;
    const h=Math.sin(dlat/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dlon/2)**2;
    return 6371.0088*2*Math.asin(Math.min(1,Math.sqrt(h)));
  }
  function dayWeights(values,count){
    const raw=(values||[]).map(Number).filter(x=>Number.isFinite(x)&&x>0);
    if(raw.length)return raw.slice(0,21);
    const n=Math.max(1,Math.min(21,Math.round(Number(count)||1)));
    return Array.from({length:n},()=>1);
  }
  function splitRoute(coords,weights){
    const pts=cleanCoords(coords),w=dayWeights(weights,1);if(pts.length<2)return[];if(w.length<=1)return[pts];
    const edge=[];let total=0;for(let i=1;i<pts.length;i++){const d=km(pts[i-1],pts[i]);edge.push(d);total+=d}
    if(!(total>0))return[pts];
    const sum=w.reduce((a,b)=>a+b,0);let acc=0;const thresholds=w.slice(0,-1).map(x=>(acc+=x)/sum*total);
    const out=[[pts[0]]];let day=0,walked=0,next=thresholds[0]??Infinity;
    for(let i=1;i<pts.length;i++){
      const a=pts[i-1],b=pts[i],len=edge[i-1];
      while(day<w.length-1&&next<=walked+len+1e-9){
        const f=len>0?Math.max(0,Math.min(1,(next-walked)/len)):1;
        const cut=[a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f];
        out[day].push(cut);day++;out[day]=[cut];next=thresholds[day]??Infinity;
      }
      out[day].push(b);walked+=len;
    }
    return out.filter(x=>x.length>=2);
  }
  function icon(kind){
    const both=kind==='both',label=both?'D/A':kind==='start'?'D':'A';
    return L.divIcon({className:`tm-route-endpoint tm-route-${kind}`,html:`<span>${label}</span>`,iconSize:[both?40:34,34],iconAnchor:[both?20:17,17],popupAnchor:[0,-18]});
  }
  function addEndpoints(group,coords,names={}){
    if(!coords.length)return;const start=coords[0],end=coords[coords.length-1],same=km(start,end)<0.05;
    if(same){L.marker(start,{icon:icon('both'),zIndexOffset:1100,title:'Départ et arrivée'}).bindPopup(`<b>Départ et arrivée</b>${names.start?`<br>${String(names.start)}`:''}`).addTo(group);return}
    L.marker(start,{icon:icon('start'),zIndexOffset:1100,title:'Départ'}).bindPopup(`<b>Départ</b>${names.start?`<br>${String(names.start)}`:''}`).addTo(group);
    L.marker(end,{icon:icon('end'),zIndexOffset:1100,title:'Arrivée'}).bindPopup(`<b>Arrivée</b>${names.end?`<br>${String(names.end)}`:''}`).addTo(group);
  }
  function clearControl(control){try{if(control&&typeof map!=='undefined')map.removeControl(control)}catch(_){}return null}
  function makeLegend(segments,title){
    const control=L.control({position:'bottomleft'});control.onAdd=()=>{
      const div=L.DomUtil.create('div','tm-route-day-legend');
      div.innerHTML=`<b>${title}</b>`+segments.map((_,i)=>`<div class="tm-route-day-row"><span class="tm-route-day-swatch" style="background:${palette[i%palette.length]}"></span>Jour ${i+1}</div>`).join('')+'<small><b style="display:inline;color:#166534">D</b> départ · <b style="display:inline;color:#b42318">A</b> arrivée</small>';
      L.DomEvent.disableClickPropagation(div);L.DomEvent.disableScrollPropagation(div);return div;
    };control.addTo(map);return control;
  }
  function protectSelectedInteraction(layer){
    if(!layer||typeof layer.on!=='function')return;
    layer.on('click',e=>{
      routeClickGuard=true;
      try{if(e?.originalEvent)L.DomEvent.stopPropagation(e.originalEvent)}catch(_){}
      setTimeout(()=>{routeClickGuard=false},80);
    });
  }
  function render(kind,coords,weights,names,fit=false){
    if(typeof map==='undefined'||typeof L==='undefined')return;const pts=cleanCoords(coords);if(pts.length<2)return;
    if(kind==='ai'){try{if(aiGroup)map.removeLayer(aiGroup)}catch(_){}aiLegend=clearControl(aiLegend)}
    else{try{if(selectedGroup)map.removeLayer(selectedGroup)}catch(_){}selectedLegend=clearControl(selectedLegend)}
    const segments=splitRoute(pts,weights),group=L.featureGroup().addTo(map);
    segments.forEach((seg,i)=>L.polyline(seg,{color:palette[i%palette.length],weight:7,opacity:.96,lineCap:'round',lineJoin:'round'}).bindTooltip(`Jour ${i+1}`,{sticky:true}).addTo(group));
    addEndpoints(group,pts,names||{});
    if(kind==='selected')group.eachLayer(protectSelectedInteraction);
    const legend=makeLegend(segments,segments.length>1?'Étapes du trek':'Tracé du trek');
    if(kind==='ai'){aiGroup=group;aiLegend=legend}else{selectedGroup=group;selectedLegend=legend}
    if(fit){const bounds=group.getBounds();if(bounds.isValid())map.fitBounds(bounds.pad(.12),{maxZoom:15,paddingTopLeft:[25,70],paddingBottomRight:[25,110],animate:true})}
  }
  function planWeights(plan){
    const stages=Array.isArray(plan?.stages)?plan.stages:[];
    return dayWeights(stages.map(s=>s?.distance_km),stages.length||plan?.duration_days||1);
  }
  function savedWeights(t){
    const text=String(t?.description||''),matches=[];const rx=/Jour\s+\d+\s*:[^\n]*?[—-]\s*([\d.,]+)\s*km/gi;let m;
    while((m=rx.exec(text))!==null){const n=Number(String(m[1]).replace(',','.'));if(Number.isFinite(n)&&n>0)matches.push(n)}
    return dayWeights(matches,matches.length||t?.duration_days||1);
  }
  function renderAi(plan,fit=true){
    const coords=plan?.route_preview?.coords||[];render('ai',coords,planWeights(plan),{start:plan?.start?.name||'',end:plan?.end?.name||''},fit);
  }
  function savedCoords(t){
    if(Array.isArray(t?.coords)&&t.coords.length>1)return t.coords;
    try{return typeof geometryToLeaflet==='function'?geometryToLeaflet(t?.geometry):[]}catch(_){return[]}
  }
  function removeLegacySelectedLine(){
    try{if(typeof detailLayer!=='undefined'&&detailLayer){map.removeLayer(detailLayer);detailLayer=null}}catch(_){}
  }
  function renderSaved(t,fit=true){
    try{if(aiGroup)map.removeLayer(aiGroup)}catch(_){}aiGroup=null;aiLegend=clearControl(aiLegend);
    removeLegacySelectedLine();
    render('selected',savedCoords(t),savedWeights(t),{start:t?.start_name||t?.name||'',end:t?.end_name||''},fit);
  }
  function renderManualEndpoints(){
    if(typeof map==='undefined'||typeof L==='undefined'||typeof drawCoords==='undefined')return;
    try{if(manualEndpoints)map.removeLayer(manualEndpoints)}catch(_){}manualEndpoints=null;
    const pts=cleanCoords(drawCoords);if(!pts.length)return;manualEndpoints=L.featureGroup().addTo(map);
    if(pts.length===1)L.marker(pts[0],{icon:icon('start'),zIndexOffset:1200,title:'Départ'}).bindPopup('<b>Départ</b>').addTo(manualEndpoints);
    else addEndpoints(manualEndpoints,pts,{});
  }
  function exitSelectedTrek(){
    if(selectedTrekId===null)return;
    try{if(selectedGroup)map.removeLayer(selectedGroup)}catch(_){}selectedGroup=null;
    selectedLegend=clearControl(selectedLegend);removeLegacySelectedLine();
    selectedTrekId=null;
    try{if(typeof currentDetail!=='undefined')currentDetail=null}catch(_){}
    try{if(typeof refreshTraceStyles==='function')refreshTraceStyles()}catch(_){}
  }
  function bindMapExit(){
    if(mapExitBound)return;
    if(typeof map==='undefined'||!map||typeof map.on!=='function'){setTimeout(bindMapExit,120);return}
    mapExitBound=true;
    map.on('click',()=>{
      if(selectedTrekId===null)return;
      if(routeClickGuard){routeClickGuard=false;return}
      try{if(typeof drawMode!=='undefined'&&drawMode)return}catch(_){}
      exitSelectedTrek();
    });
  }

  if(!window.__trekmapRouteDayFetchWrapped){
    window.__trekmapRouteDayFetchWrapped=true;const previous=window.fetch.bind(window);
    window.fetch=async function(input,init){
      const response=await previous(input,init);try{const url=String(typeof input==='string'?input:(input&&input.url)||'');if(response.ok&&url.includes('/ai/plan'))response.clone().json().then(data=>{if(data&&typeof data==='object'){aiPlan=data}}).catch(()=>{});}catch(_){}return response;
    };
  }
  document.addEventListener('click',e=>{if(e.target.closest('#tm-ai-preview')&&aiPlan)setTimeout(()=>renderAi(aiPlan,true),70)},false);

  try{
    if(typeof drawTrace==='function'){
      const originalDrawTrace=drawTrace;
      drawTrace=function(t,highlight){
        if(selectedTrekId!==null&&Number(t?.id)===Number(selectedTrekId))return;
        return originalDrawTrace.apply(this,arguments);
      };
      window.drawTrace=drawTrace;
    }
  }catch(_){}
  try{
    if(typeof openDetail==='function'){
      const originalOpenDetail=openDetail;
      openDetail=function(id){
        selectedTrekId=Number(id);routeClickGuard=true;setTimeout(()=>{routeClickGuard=false},120);
        const value=originalOpenDetail.apply(this,arguments);
        setTimeout(()=>{
          try{
            removeLegacySelectedLine();
            if(typeof refreshTraceStyles==='function')refreshTraceStyles();
            const t=(typeof allTreks!=='undefined'?allTreks:[]).find(x=>Number(x.id)===Number(id));
            if(t)renderSaved(t,true);
          }catch(_){}
        },30);
        return value;
      };
      window.openDetail=openDetail;
    }
  }catch(_){}
  try{
    if(typeof redrawDraft==='function'){
      const originalRedrawDraft=redrawDraft;
      redrawDraft=function(){const value=originalRedrawDraft.apply(this,arguments);setTimeout(renderManualEndpoints,0);return value};window.redrawDraft=redrawDraft;
    }
    if(typeof clearDrawingLayers==='function'){
      const originalClearDrawingLayers=clearDrawingLayers;
      clearDrawingLayers=function(){const value=originalClearDrawingLayers.apply(this,arguments);try{if(manualEndpoints)map.removeLayer(manualEndpoints)}catch(_){}manualEndpoints=null;return value};window.clearDrawingLayers=clearDrawingLayers;
    }
  }catch(_){}
  window.TrekMapExitSelectedTrek=exitSelectedTrek;
  bindMapExit();
})();
</script>
<!-- TREKMAP_ROUTE_DAY_VISUALS_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekMap route day colors + coherent selection behavior applied")
