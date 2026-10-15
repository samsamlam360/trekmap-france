"""Last UI layer: map clusters, clear selection, and contextual seven-filter toolbar.

No new dependencies, network calls, database changes or paid map services.
Installs after the existing TrekBrain and profile layers; idempotent on rebuild.
"""
from pathlib import Path
import re

p=Path(__file__).resolve().parents[1]/"frontend"/"index.html"
html=p.read_text(encoding="utf-8")
html=re.sub(r"\s*<!-- TREKMAP_MAP_TOOLS_2026_START -->.*?<!-- TREKMAP_MAP_TOOLS_2026_END -->\s*","\n",html,flags=re.S)
for marker in ("TREKMAP_INLINE_FILTERS_2026_START","TREKMAP_EXPLORER_FINISH_START","TREKMAP_PROFILE_V2_START"):
    if marker not in html:
        raise SystemExit("Map tools require "+marker)
block=r'''<!-- TREKMAP_MAP_TOOLS_2026_START -->
<style id="trekmap-map-tools-v2-css">
/* A single button beside SEARCH expands the compact seven-filter toolbar. */
#tm-search-filter-group{display:flex;align-items:center;gap:9px;min-width:0;width:100%}
#tm-search-filter-group #tm-main-search-wrap{flex:1 1 auto;width:auto;min-width:0}
#tm-search-filter-toggle{
  display:flex;gap:7px;align-items:center;justify-content:center;flex:0 0 auto;
  height:46px;min-width:102px;border:1px solid rgba(255,255,255,.30);
  border-radius:12px;background:#12835d;color:#fff;font-size:13px;font-weight:850;
  cursor:pointer;transition:background .15s
}
#tm-search-filter-toggle:hover{background:#0c6f4d}
#tm-search-filter-toggle:focus-visible{outline:3px solid #ffd66b;outline-offset:2px}
#tm-search-filter-toggle[aria-expanded="true"]{background:#096744}
#tm-search-filter-toggle .tm-filter-chevron{font-size:15px;transition:transform .15s}
#tm-search-filter-toggle[aria-expanded="true"] .tm-filter-chevron{transform:rotate(180deg)}
@media(min-width:1240px){
  #tm-unified-topbar{grid-template-columns:235px minmax(400px,610px) minmax(0,1fr)!important}
}
@media(min-width:821px) and (max-width:1239px){
  #tm-search-filter-toggle{min-width:46px;width:46px;padding:0}
  #tm-search-filter-toggle .tm-filter-name{display:none}
}
@media(min-width:821px){
  body.tm-filterstrip-closed #tm-inline-filters{display:none!important}
  #tm-inline-filters{max-width:calc(100vw - 25px)!important;scrollbar-width:none}
  #tm-inline-filters #tm-inline-advanced{display:none!important}
  #tm-inline-filters .tm-inline-field{display:flex;align-items:center;gap:5px;
    padding:0 6px;border:1px solid #e1ece4;border-radius:11px;background:#f5f9f6;
    flex:0 0 auto;white-space:nowrap}
  #tm-inline-filters .tm-inline-field span{font-size:11px;color:#456f58;font-weight:800}
  #tm-inline-filters .tm-inline-field select{min-width:88px!important;max-width:126px!important;
    padding:0 3px!important;border:0!important;background:transparent!important}
  #tm-inline-filters .tm-inline-extra[aria-expanded="true"]{
    background:#e2f4e9!important;border-color:#5ca785!important}
  #tm-map-filter-popover{
    position:fixed;z-index:8000;width:282px;max-width:calc(100vw - 24px);
    border:1px solid #ccdfd2;background:#fff;border-radius:17px;
    padding:14px 16px 15px;box-shadow:0 18px 42px rgba(8,44,28,.23);
    color:#184932;font:inherit
  }
  #tm-map-filter-popover[hidden]{display:none!important}
  #tm-map-filter-popover .tm-mini-head{display:flex;align-items:center;justify-content:space-between;
    font-size:14px;font-weight:850;margin-bottom:13px}
  #tm-map-filter-popover .tm-mini-dismiss{border:0;background:#ecf5ef;cursor:pointer;
    color:#145a3e;border-radius:8px;width:30px;height:30px;font-size:18px}
  #tm-map-filter-popover .tm-mini-control{display:grid;gap:9px;margin:12px 0}
  #tm-map-filter-popover .tm-mini-control label{font-size:12px;font-weight:780;color:#315944}
  #tm-map-filter-popover .tm-mini-value{float:right;color:#10774e;font-weight:850}
  #tm-map-filter-popover input[type=range]{width:100%;accent-color:#15865d;cursor:pointer}
  #tm-map-filter-popover select{min-height:42px;width:100%;padding:7px 11px;border:1px solid #bfd8c7;
    border-radius:10px;background:white;color:#144b31}
  #tm-map-filter-popover :is(button,input,select):focus-visible{
    outline:3px solid #eeb13a;outline-offset:2px}
}
@media(max-width:820px){
  #tm-search-filter-toggle{display:none!important}
  #tm-map-filter-popover{display:none!important}
}
/* Clusters are view-only markers. The underlying authentic trekking lines remain intact. */
.tm-trek-cluster-icon{background:none!important;border:0!important}
.tm-trek-cluster{
  display:grid;place-items:center;width:42px;height:42px;border-radius:50%;
  border:3px solid white;background:#087a52;color:white;
  box-shadow:0 2px 0 rgba(4,67,42,.3),0 0 0 5px rgba(22,137,84,.20),0 4px 17px rgba(4,47,29,.25);
  font-size:15px;font-weight:900;line-height:1;cursor:pointer}
.tm-trek-cluster[data-count="single"]{width:32px;height:32px;font-size:12px;
  background:#237c5d;box-shadow:0 0 0 3px rgba(15,117,78,.15),0 4px 13px rgba(4,47,29,.22)}
.tm-trek-cluster-icon:focus-visible .tm-trek-cluster{outline:3px solid #f6ae33}
.tm-trek-cluster-list{display:grid;gap:5px;min-width:190px;max-width:280px}
.tm-trek-cluster-list b{font-size:13px;margin-bottom:4px}
.tm-trek-cluster-list button{padding:7px;text-align:left;border:1px solid #daeadf;border-radius:8px;
  background:#f5faf6;color:#11583b;font-size:12px;cursor:pointer}
</style>
<script id="trekmap-map-tools-v2-js">
(function(){
  'use strict';
  var $=function(id){return document.getElementById(id)};
  var strip=$('tm-inline-filters'),top=$('tm-unified-topbar'),search=$('tm-main-search-wrap');
  var side=$('sidebar');
  if(!strip||!top||!search||!side||!$('sort-filter')||!$('tm-route-filter'))return;
  var group=document.createElement('div');group.id='tm-search-filter-group';
  search.parentNode.insertBefore(group,search);group.appendChild(search);
  var show=document.createElement('button');show.type='button';show.id='tm-search-filter-toggle';
  show.setAttribute('aria-controls','tm-inline-filters');show.setAttribute('aria-expanded','false');
  show.innerHTML='<span aria-hidden="true">☷</span><span class="tm-filter-name">Filtres</span>'+
    '<span class="tm-filter-chevron" aria-hidden="true">⌄</span>';
  group.appendChild(show);
  // A new session begins with a clear map, rather than a permanent second header.
  document.body.classList.add('tm-filterstrip-closed');
  function closeMini(){
    pop.hidden=true;pop.replaceChildren();
    strip.querySelectorAll('.tm-inline-extra').forEach(function(b){b.setAttribute('aria-expanded','false')});
  }
  function setExpanded(value){
    if(value&&document.body.classList.contains('tm-brain-route-mode'))return;
    document.body.classList.toggle('tm-filterstrip-closed',!value);
    show.setAttribute('aria-expanded',String(value));if(!value)closeMini();
  }
  show.addEventListener('click',function(){setExpanded(document.body.classList.contains('tm-filterstrip-closed'))});
  var advanced=$('tm-inline-advanced');
  if(advanced)advanced.hidden=true;
  var mirrorNames=[['sort-filter','tm-inline-sort','Trier par'],['tm-route-filter','tm-inline-route','Parcours']];
  mirrorNames.forEach(function(entry){
    var original=$(entry[0]),field=document.createElement('label'),select=document.createElement('select');
    field.className='tm-inline-field';field.setAttribute('aria-label',entry[2]);
    var name=document.createElement('span');name.textContent=entry[2];field.appendChild(name);
    select.id=entry[1];select.setAttribute('aria-label',entry[2]);field.appendChild(select);
    strip.appendChild(field);
    function synchronize(){
      var signature=Array.from(original.options).map(function(o){return o.value+'|'+o.textContent}).join('\u0001');
      if(select.dataset.signature!==signature){
        select.replaceChildren.apply(select,Array.from(original.options).map(function(o){return o.cloneNode(true)}));
        select.dataset.signature=signature;
      }
      if(select.value!==original.value)select.value=original.value;
    }
    select.addEventListener('change',function(){
      original.value=select.value;original.dispatchEvent(new Event('change',{bubbles:true}));
    });
    original.addEventListener('change',synchronize);
    new MutationObserver(synchronize).observe(original,{childList:true,subtree:true});
    synchronize();
  });
  var pop=document.createElement('div');pop.id='tm-map-filter-popover';pop.hidden=true;
  pop.setAttribute('role','dialog');pop.setAttribute('aria-label','Régler un filtre');
  document.body.appendChild(pop);
  var modes={
    'distance-range':{title:'Distance',ids:['distance-range','distance-tolerance'],
      labels:['Distance cible','Écart autorisé']},
    'elevation-range':{title:'Dénivelé',ids:['elevation-range','elevation-tolerance'],
      labels:['Dénivelé cible','Écart autorisé']},
    'duration-filter':{title:'Durée',ids:['duration-filter'],labels:['Durée maximale']}
  };
  function openMini(button){
    var config=modes[button.dataset.filterTarget];if(!config)return;
    var already=!pop.hidden&&pop.dataset.mode===button.dataset.filterTarget;
    closeMini();if(already)return;
    pop.dataset.mode=button.dataset.filterTarget;pop.hidden=false;
    button.setAttribute('aria-expanded','true');
    var head=document.createElement('div');head.className='tm-mini-head';
    var title=document.createElement('strong');title.textContent=config.title;head.appendChild(title);
    var close=document.createElement('button');close.type='button';close.className='tm-mini-dismiss';
    close.setAttribute('aria-label','Fermer '+config.title);close.textContent='×';close.onclick=function(){closeMini();button.focus()};
    head.appendChild(close);pop.appendChild(head);
    config.ids.forEach(function(id,index){
      var source=$(id);if(!source)return;
      var wrap=document.createElement('div');wrap.className='tm-mini-control';
      var label=document.createElement('label');label.textContent=config.labels[index];
      var val=document.createElement('span');val.className='tm-mini-value';label.appendChild(val);
      var input=source.cloneNode(true);input.removeAttribute('id');input.removeAttribute('name');
      input.value=source.value;input.setAttribute('aria-label',config.labels[index]);
      if(input.tagName==='SELECT'){
        input.replaceChildren.apply(input,Array.from(source.options).map(function(o){return o.cloneNode(true)}));
        input.value=source.value;
      }
      function valueLabel(){
        var n=Number(input.value);
        if(input.type==='range')val.textContent=n===0&&index===0?'Toutes':(index===1?'± ':'')+
          input.value+(config.title==='Distance'?' km':' m');
        else val.textContent='';
      }
      function copy(){
        source.value=input.value;source.dispatchEvent(new Event(input.type==='range'?'input':'change',{bubbles:true}));valueLabel();
      }
      input.addEventListener(input.type==='range'?'input':'change',copy);
      source.addEventListener('input',function(){if(!pop.hidden&&pop.dataset.mode===button.dataset.filterTarget){
        input.value=source.value;valueLabel()
      }},{signal:miniAbort.signal});
      wrap.appendChild(label);wrap.appendChild(input);pop.appendChild(wrap);valueLabel();
    });
    var rect=button.getBoundingClientRect();
    pop.style.top=Math.min(window.innerHeight-250,rect.bottom+9)+'px';
    pop.style.left=Math.max(12,Math.min(window.innerWidth-294,rect.left))+'px';
  }
  var miniAbort=new AbortController();
  strip.addEventListener('click',function(e){
    var btn=e.target.closest('.tm-inline-extra[data-filter-target]');
    if(!btn)return;
    // Capture before old bubbling listeners, which used to open every filter.
    e.preventDefault();e.stopImmediatePropagation();
    miniAbort.abort();miniAbort=new AbortController();
    openMini(btn);
  },true);
  document.addEventListener('pointerdown',function(e){
    if(pop.hidden)return;
    if(pop.contains(e.target)||e.target.closest('.tm-inline-extra'))return;closeMini();
  },true);
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'){
      if(!pop.hidden){closeMini();return}
      if(!document.body.classList.contains('tm-filterstrip-closed'))setExpanded(false);
    }
  });
  window.addEventListener('resize',function(){closeMini();if(window.innerWidth<=820)setExpanded(false)});
  new MutationObserver(function(){
    if(document.body.classList.contains('tm-brain-route-mode')&&
       !document.body.classList.contains('tm-filterstrip-closed'))setExpanded(false);
  }).observe(document.body,{attributes:true,attributeFilter:['class']});
  window.TrekMapQuickFilters={
    expand:setExpanded,
    isExpanded:function(){return !document.body.classList.contains('tm-filterstrip-closed')},
    isMiniOpen:function(){return !pop.hidden},
    openMiniFor:function(id){var b=strip.querySelector('[data-filter-target="'+id+'"]');if(b)openMini(b)}
  };

  // Prevent a click on the map background from leaving an unrelated trek
  // selected. Keep drawing mode and the separate TrekBrain map untouched.
  if(typeof map==='undefined'||!map||typeof L==='undefined'||typeof trekLayerGroup==='undefined')return;
  map.on('click',function(e){
    if(document.body.classList.contains('tm-brain-route-mode'))return;
    if(typeof drawMode!=='undefined'&&drawMode)return;
    if(e.sourceTarget&&e.sourceTarget!==map)return;
    if(typeof window.TrekMapClearSelectedTrek==='function')window.TrekMapClearSelectedTrek();
  });
  function stopBubbling(){
    trekLayerGroup.eachLayer(function(line){if(line.options)line.options.bubblingMouseEvents=false});
  }
  stopBubbling();

  // A representative point per real route. Clustering uses screen pixels at
  // the current zoom so badges progressively split as the user zooms in.
  var clusterLayer=L.layerGroup().addTo(map);
  var currentClusters=[],clusterScheduled=false;
  function coordinates(t){
    if(Array.isArray(t.coords)&&t.coords.length>=2)return t.coords.filter(function(p){
      return Array.isArray(p)&&p.length>=2&&Number.isFinite(Number(p[0]))&&Number.isFinite(Number(p[1]))
    });
    if(typeof geometryToLeaflet==='function')return geometryToLeaflet(t.geometry);
    return [];
  }
  function featured(t){
    var pts=coordinates(t);if(pts.length<2)return null;
    // midpoint of the real sequence rather than a fictitious town/POI
    var at=pts[Math.floor(pts.length/2)];
    return L.latLng(Number(at[0]),Number(at[1]));
  }
  function data(){
    var current=typeof filteredTreks!=='undefined'&&Array.isArray(filteredTreks)?filteredTreks:[];
    var seen=new Set();return current.filter(function(t){
      var id=Number(t.id);if(!Number.isFinite(id)||seen.has(id))return false;
      seen.add(id);return !!featured(t)
    });
  }
  function clusterNow(){
    clusterScheduled=false;clusterLayer.clearLayers();currentClusters=[];
    if(document.body.classList.contains('tm-brain-route-mode')||map.getZoom()>10)return;
    var treks=data(),radius=map.getZoom()<=6?69:map.getZoom()<=8?57:45;
    // Stable greedy pixel groups; no extra map provider or plugin.
    treks.forEach(function(t){
      var point=featured(t);if(!point)return;
      var pixel=map.latLngToLayerPoint(point),near=null,best=radius*radius;
      currentClusters.forEach(function(g){
        var dx=g.pixel.x-pixel.x,dy=g.pixel.y-pixel.y,d2=dx*dx+dy*dy;
        if(d2<best){best=d2;near=g}
      });
      if(near){
        near.ids.push(Number(t.id));near.treks.push(t);near.points.push(point);
        var n=near.ids.length;
        near.pixel=L.point(near.pixel.x+(pixel.x-near.pixel.x)/n,
                           near.pixel.y+(pixel.y-near.pixel.y)/n);
      }else currentClusters.push({ids:[Number(t.id)],treks:[t],points:[point],pixel:pixel});
    });
    currentClusters.forEach(function(group){
      var count=group.ids.length,center=map.layerPointToLatLng(group.pixel);
      var icon=L.divIcon({className:'tm-trek-cluster-icon',
        html:'<span class="tm-trek-cluster" data-count="'+(count===1?'single':'multiple')+'">'+count+'</span>',
        iconSize:[count===1?32:42,count===1?32:42],iconAnchor:[count===1?16:21,count===1?16:21]});
      var marker=L.marker(center,{icon:icon,keyboard:true,bubblingMouseEvents:false,
        title:count+' trek'+(count>1?'s':'')+' dans cette zone'});
      marker.on('click',function(){
        if(count===1){if(window.TrekMapOpenTrek)window.TrekMapOpenTrek(group.ids[0]);return}
        var zoom=map.getZoom(),bounds=L.latLngBounds(group.points);
        if(zoom<10){
          map.fitBounds(bounds.pad(.6),{maxZoom:Math.min(11,zoom+3),animate:true});
          if(map.getZoom()<=zoom)map.setView(center,zoom+2);
        }else{
          var content=document.createElement('div');content.className='tm-trek-cluster-list';
          var title=document.createElement('b');title.textContent=count+' treks dans cette zone';
          content.appendChild(title);
          group.treks.forEach(function(t){
            var b=document.createElement('button');b.type='button';b.textContent=t.name||'Trek';
            b.addEventListener('click',function(){map.closePopup();if(window.TrekMapOpenTrek)window.TrekMapOpenTrek(Number(t.id))});
            content.appendChild(b);
          });
          L.popup({maxWidth:295}).setLatLng(center).setContent(content).openOn(map);
        }
      });
      marker.addTo(clusterLayer);
    });
    stopBubbling();
  }
  function scheduleCluster(){
    if(clusterScheduled)return;clusterScheduled=true;
    requestAnimationFrame(clusterNow);
  }
  map.on('zoomend moveend',scheduleCluster);
  var track=$('tm-drawer-track');
  if(track)new MutationObserver(scheduleCluster).observe(track,{childList:true});
  new MutationObserver(function(){scheduleCluster()}).observe(document.body,
    {attributes:true,attributeFilter:['class']});
  document.addEventListener('trekmap:detail-cleared',scheduleCluster);
  scheduleCluster();
  window.TrekMapClusters={
    refresh:scheduleCluster,
    getCounts:function(){return currentClusters.map(function(g){return g.ids.length})},
    getTotal:function(){return currentClusters.reduce(function(s,g){return s+g.ids.length},0)},
    getMarkerCount:function(){return clusterLayer.getLayers().length}
  };
})();
</script>
<!-- TREKMAP_MAP_TOOLS_2026_END -->'''
if html.count("</body>")!=1:raise SystemExit("Unexpected HTML body")
html=html.replace("</body>",block+"\n</body>",1)
p.write_text(html,encoding="utf-8")
print("Map clusters and contextual filters installed")
