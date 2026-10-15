"""Finish the map-first Explorer presentation without changing its data contracts.

This idempotent layer runs after the inline filters and all profile, TrekBrain
and desktop layers. It preserves the original filter inputs and Leaflet routes.
"""
from pathlib import Path
import re

path=Path(__file__).resolve().parents[1]/"frontend"/"index.html"
html=path.read_text(encoding="utf-8")
html=re.sub(
    r"\s*<!-- TREKMAP_EXPLORER_FINISH_START -->.*?<!-- TREKMAP_EXPLORER_FINISH_END -->\s*",
    "\n",html,flags=re.S,
)
for marker in ("TREKMAP_INLINE_FILTERS_2026_START","TREKMAP_DESKTOP_MAP_2026_START",
               "TREKMAP_PROFILE_V2_START","TREKMAP_BRAIN_ROUTE_WORKSPACE_START"):
    if marker not in html:
        raise SystemExit("Explorer finishing layer missing prerequisite: "+marker)

block=r'''<!-- TREKMAP_EXPLORER_FINISH_START -->
<style id="trekmap-explorer-finish-css">
/* Accessible floating toolbar composed of the ORIGINAL live filter controls. */
@media(min-width:821px){
  #tm-inline-filters{
    padding:6px!important;gap:4px!important;min-height:54px!important;
    border:1px solid rgba(213,232,218,.98)!important;border-radius:17px!important;
    background:rgba(255,255,255,.96)!important;
    box-shadow:0 11px 32px rgba(7,48,29,.17)!important;
    backdrop-filter:blur(18px)!important;
    -webkit-backdrop-filter:blur(18px)!important
  }
  #tm-inline-filters :is(select,button){
    height:40px!important;min-height:40px!important;
    box-shadow:none!important;border-radius:11px!important;
    border:1px solid transparent!important;background:transparent!important;
    color:#244f3a!important;font-size:12px!important;font-weight:750!important
  }
  #tm-inline-filters select{
    min-width:142px!important;max-width:200px!important;
    padding-inline:10px 8px!important;
    text-overflow:ellipsis!important;
    background:#f5f9f6!important;
    border-color:#e2ece6!important
  }
  #tm-inline-filters :is(select,button):hover{
    background:#eaf5ee!important;border-color:#b7dcc4!important
  }
  #tm-inline-filters select[data-active="true"]{
    background:#e0f3e8!important;border-color:#78b897!important
  }
  #tm-inline-filters #tm-inline-advanced{
    background:#0b8057!important;border-color:#0b8057!important;
    color:white!important;padding-inline:15px!important;
    box-shadow:0 2px 6px rgba(11,83,53,.12)!important
  }
  #tm-inline-filters #tm-inline-advanced:hover,
  #tm-inline-filters #tm-inline-advanced[aria-expanded="true"]{
    background:#076b49!important
  }
  #tm-inline-filters :is(button,select):focus-visible{
    outline:3px solid #efb93b!important;outline-offset:2px!important
  }
  /* Keep one lightweight total when idle; show a single actionable trek when selected. */
  #tm-desktop-info{gap:0!important}
  #tm-desktop-info:not(.has-selection) .tm-info-selected{display:none!important}
  #tm-desktop-info.has-selection .tm-info-overview{display:none!important}
  #tm-desktop-info:not(.has-selection){width:202px!important}
  #tm-desktop-info:not(.has-selection) .tm-info-overview{
    padding:10px 13px!important;border-radius:15px!important
  }
  #tm-desktop-info:not(.has-selection) .tm-info-overview :is(.tm-info-landscape,.tm-info-topline,h2,p){
    display:none!important
  }
  #tm-desktop-info:not(.has-selection) .tm-info-count{
    border:0!important;padding:0!important;gap:9px!important
  }
  #tm-desktop-info:not(.has-selection) .tm-info-count strong{font-size:24px!important}
  #tm-desktop-info:not(.has-selection) .tm-info-count span{
    font-size:12px!important;color:#426d55!important;font-weight:750!important
  }
  #tm-desktop-info.has-selection .tm-info-selected{
    max-height:min(330px,calc(100dvh - var(--tm-top) - var(--tm-drawer) - 40px))!important;
    border-radius:16px!important;
    box-shadow:0 16px 35px rgba(8,53,32,.16)!important
  }
  .tm-info-trek-name{font-size:17px!important;line-height:1.28!important}
  .tm-info-kpis strong{font-size:12px!important}
  .tm-info-controls button{min-height:42px!important}
}
@media(min-width:1240px){
  :root{--tm-drawer:208px}
  #tm-unified-drawer:not(.collapsed){height:var(--tm-drawer)!important}
  #tm-unified-drawer .tm-drawer-shell{border-radius:19px!important}
  #tm-drawer-head{height:43px!important}
  #tm-drawer-track{
    height:calc(var(--tm-drawer) - 45px)!important;
    gap:12px!important;padding:5px 13px 11px!important
  }
  #tm-drawer-track .tm-trek-tile{
    flex:0 0 222px!important;height:149px!important;padding:9px 11px!important;
    border-radius:13px!important
  }
  #tm-drawer-track .tm-tile-landscape{
    height:46px!important;min-height:46px!important;border-radius:9px!important
  }
  #tm-drawer-track .tm-mini-route{max-height:46px!important}
  #tm-drawer-track .tm-trek-tile strong{
    font-size:13px!important;line-height:1.23!important;margin-top:6px!important
  }
  #tm-drawer-track .tm-trek-tile .region{font-size:11px!important;margin-top:3px!important}
  #tm-drawer-track .tm-tile-chips{margin:5px 0 3px!important}
  #tm-drawer-track .tm-chip{font-size:10px!important;padding:2px 6px!important}
  #tm-drawer-track .tm-tile-meta{font-size:11px!important;gap:9px!important}
  #tm-drawer-track .tm-tile-open{font-size:10px!important;right:10px!important;bottom:5px!important}
  #tm-drawer-track .tm-trek-tile:hover{
    border-color:#6fae8b!important;background:#f7fcf8!important
  }
  #tm-drawer-track .tm-trek-tile.selected{
    background:#ecf8f0!important;border-color:#0f8758!important
  }
  #tm-desktop-info.has-selection{width:254px!important}
  #tm-desktop-info:not(.has-selection) + .map-tools{right:230px!important}
}
@media(min-width:821px) and (max-width:1239px){
  #tm-inline-filters{max-width:calc(100vw - 28px)!important}
  #tm-inline-filters select{min-width:138px!important}
}
/* Mobile's real bottom sheet, controls and TrekBrain overlay are unchanged. */
@media(max-width:820px){
  #tm-inline-filters{display:none!important}
}
</style>
<script id="trekmap-explorer-finish-js">
(function(){
  "use strict";
  var quick=document.getElementById('tm-inline-difficulty');
  if(quick){
    // The mirrored default "Toutes" was ambiguous without a field label.
    function setDifficultyLabel(){
      var item=quick.querySelector('option[value=""]');
      if(item&&item.textContent!=='Difficulté')item.textContent='Difficulté';
    }
    setDifficultyLabel();
    new MutationObserver(setDifficultyLabel).observe(quick,{childList:true});
  }

  // Preserve the original map traces and click/tooltip behavior. No new
  // route geometry or routing requests: temporarily restyle Leaflet layers.
  if(typeof window.drawTrace!=='function'||typeof window.refreshTraceStyles!=='function'||
     typeof L==='undefined'||typeof map==='undefined'||!map||
     typeof trekLayerGroup==='undefined'||!trekLayerGroup)return;

  var originalDraw=window.drawTrace;
  var originalRefresh=window.refreshTraceStyles;
  var lines=new Map(),selected=null,hovered=null;
  var glow=L.layerGroup().addTo(map);
  var track=document.getElementById('tm-drawer-track');
  function focusId(){return hovered!=null?hovered:selected}
  function focusRoute(){
    glow.clearLayers();
    var id=focusId();
    if(document.body.classList.contains('tm-brain-route-mode'))id=null;
    lines.forEach(function(line){
      var orig=line._tmOriginalStyle;
      if(!orig)return;
      line.setStyle(id==null?orig:{
        color:line._tmTrekId===id?'#086644':'#789b8b',
        weight:line._tmTrekId===id?5:2.5,
        opacity:line._tmTrekId===id?1:.32
      });
    });
    var target=id==null?null:lines.get(id);
    if(!target||!target.getLatLngs)return;
    var points=target.getLatLngs();
    if(!points||points.length<2)return;
    // Two noninteractive strokes create a visible outline even with
    // Leaflet Canvas rendering and never steal a native route click.
    L.polyline(points,{color:'#ffffff',weight:11,opacity:.94,
      lineCap:'round',lineJoin:'round',interactive:false}).addTo(glow);
    L.polyline(points,{color:'#06875a',weight:6.4,opacity:1,
      lineCap:'round',lineJoin:'round',interactive:false}).addTo(glow);
  }
  window.drawTrace=function(t,visible){
    var before=trekLayerGroup.getLayers().length;
    var value=originalDraw.apply(this,arguments);
    var layers=trekLayerGroup.getLayers();
    if(layers.length<=before)return value;
    var line=layers[layers.length-1],id=Number(t.id);
    if(!Number.isFinite(id)||typeof line.setStyle!=='function')return value;
    line._tmTrekId=id;
    line._tmOriginalStyle={
      color:line.options.color,weight:line.options.weight,opacity:line.options.opacity
    };
    lines.set(id,line);
    line.on('mouseover',function(){if(window.innerWidth>820){hovered=id;focusRoute()}});
    line.on('mouseout',function(){if(hovered===id){hovered=null;focusRoute()}});
    return value;
  };
  window.refreshTraceStyles=function(){
    lines.clear();
    glow.clearLayers();
    var result=originalRefresh.apply(this,arguments);
    focusRoute();
    return result;
  };
  if(track){
    track.addEventListener('pointerover',function(e){
      if(window.innerWidth<=820)return;
      var card=e.target.closest('.tm-trek-tile');
      if(!card||e.relatedTarget&&card.contains(e.relatedTarget))return;
      var id=Number(card.dataset.id);
      if(Number.isFinite(id)){hovered=id;focusRoute()}
    });
    track.addEventListener('pointerout',function(e){
      var card=e.target.closest('.tm-trek-tile');
      if(card&&e.relatedTarget&&card.contains(e.relatedTarget))return;
      if(hovered!=null){hovered=null;focusRoute()}
    });
    track.addEventListener('focusin',function(e){
      var card=e.target.closest('.tm-trek-tile'),id=Number(card&&card.dataset.id);
      if(card&&Number.isFinite(id)&&window.innerWidth>820){hovered=id;focusRoute()}
    });
    track.addEventListener('focusout',function(e){
      if(e.target.closest('.tm-trek-tile')){hovered=null;focusRoute()}
    });
  }
  document.addEventListener('trekmap:detail-opened',function(e){
    var id=Number(e.detail&&e.detail.id);
    if(Number.isFinite(id)){selected=id;hovered=null;focusRoute()}
  });
  new MutationObserver(function(){
    if(document.body.classList.contains('tm-brain-route-mode')){
      if(glow.getLayers().length)focusRoute();
    }else if(selected!=null)focusRoute();
  }).observe(document.body,{attributes:true,attributeFilter:['class']});
  window.addEventListener('resize',function(){
    if(window.innerWidth<=820&&hovered!=null){hovered=null;focusRoute()}
  });
  // Register traces that already existed before the last UI installer ran.
  if(trekLayerGroup.getLayers().length)window.refreshTraceStyles();
  window.TrekMapExplorerFocus={getSelected:function(){return selected},
    getFocused:function(){return focusId()},getLayerCount:function(){return lines.size},
    getGlowLayerCount:function(){return glow.getLayers().length}};
})();
</script>
<!-- TREKMAP_EXPLORER_FINISH_END -->'''
if html.count("</body>")!=1:
    raise SystemExit("Unexpected </body> marker")
html=html.replace("</body>",block+"\n</body>",1)
path.write_text(html,encoding="utf-8")
print("Explorer finishing touches installed after all current UI layers")
