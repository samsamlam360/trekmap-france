"""Transform the unused native fullscreen button into a functional map focus mode.

Installs last in the Render UI pipeline. Presentation only: all existing
Leaflet layers, active filters, route selection, and Neon data are unchanged.
"""
from pathlib import Path
import re

path=Path(__file__).resolve().parents[1]/"frontend"/"index.html"
html=path.read_text(encoding="utf-8")
html=re.sub(
    r"\s*<!-- TREKMAP_IMMERSIVE_MAP_START -->.*?<!-- TREKMAP_IMMERSIVE_MAP_END -->\s*",
    "\n",html,flags=re.S)
for marker in ("TREKMAP_MAP_TOOLS_2026_START","TREKMAP_EXPLORER_FINISH_START",
               "TREKMAP_UNIFIED_EXPERIENCE_START"):
    if marker not in html:
        raise SystemExit("Immersive map prerequisite missing: "+marker)

block=r'''<!-- TREKMAP_IMMERSIVE_MAP_START -->
<style id="trekmap-immersive-map-css">
/* Full page of CARTOGRAPHY rather than a bare Leaflet element. */
body.tm-map-immersive #app{
  width:100vw!important;height:100dvh!important;min-height:100dvh!important;
  padding:0!important;overflow:hidden!important;background:#e3ede6!important
}
body.tm-map-immersive #map{
  position:absolute!important;inset:0!important;top:0!important;
  right:0!important;bottom:0!important;left:0!important;
  width:100%!important;height:100%!important;min-height:100%!important
}
body.tm-map-immersive #tm-unified-topbar,
body.tm-map-immersive #tm-inline-filters,
body.tm-map-immersive #tm-mobile-nav,
body.tm-map-immersive #tm-mobile-filter-bar,
body.tm-map-immersive #tm-search-filter-group,
body.tm-map-immersive #tm-unified-drawer,
body.tm-map-immersive #sidebar{
  display:none!important;pointer-events:none!important
}
body.tm-map-immersive.tm-immersive-list-open #tm-unified-drawer{
  display:block!important;pointer-events:auto!important;
  position:absolute!important;left:16px!important;right:16px!important;
  bottom:12px!important;width:auto!important;height:var(--tm-drawer)!important;
  z-index:5300!important;visibility:visible!important;opacity:1!important
}
body.tm-map-immersive.tm-immersive-list-open #tm-unified-drawer.collapsed{
  /* Keep the 44px header at the BOTTOM when its chevron is clicked. */
  height:44px!important;min-height:0!important
}
body.tm-map-immersive.tm-immersive-list-open #tm-unified-drawer.collapsed #tm-drawer-track{
  display:none!important;visibility:hidden!important;pointer-events:none!important
}
body.tm-map-immersive.tm-immersive-list-open #tm-unified-drawer:not(.collapsed) #tm-drawer-track{
  display:flex!important;visibility:visible!important
}
body.tm-map-immersive #tm-map-control-dock{
  top:14px!important;left:14px!important;right:auto!important;z-index:6600!important
}
body.tm-map-immersive #tm-desktop-info{
  top:16px!important;right:16px!important;bottom:16px!important;
  max-height:calc(100dvh - 32px)!important;z-index:5200!important
}
body.tm-map-immersive.tm-immersive-list-open #tm-desktop-info{
  bottom:calc(var(--tm-drawer) + 22px)!important
}
body.tm-map-immersive .leaflet-top{top:12px!important}
body.tm-map-immersive .leaflet-top.leaflet-left{left:14px!important}
body.tm-map-immersive .leaflet-top.leaflet-left .tm-route-day-legend{
  margin-left:0!important;margin-top:102px!important
}
#tm-map-immersive-actions{
  display:none;position:absolute;z-index:7300;top:16px;left:140px;
  align-items:center;gap:7px;max-width:calc(100vw - 155px)
}
body.tm-map-immersive #tm-map-immersive-actions{display:flex}
#tm-map-immersive-actions button{
  display:inline-flex;align-items:center;justify-content:center;gap:7px;
  min-height:43px;border:1px solid #c4decf;border-radius:12px;
  background:rgba(255,255,255,.97);color:#0d573b;white-space:nowrap;
  box-shadow:0 7px 23px rgba(5,48,27,.17);padding:0 14px;
  font:800 12px/1.2 Inter,system-ui,sans-serif;cursor:pointer
}
#tm-map-immersive-actions #tm-map-immersive-detail[hidden]{display:none!important}
#tm-map-immersive-exit{background:#0b8058!important;border-color:#0b8058!important;
  color:white!important}
#tm-map-immersive-actions button:hover{filter:brightness(.96)}
#tm-map-immersive-actions button:focus-visible{outline:3px solid #ffbc43;outline-offset:2px}
#tm-map-immersive-list[aria-pressed="true"]{background:#e4f4eb;border-color:#68ac88}
@media(max-width:820px){
  body.tm-map-immersive #tm-map-control-dock{top:10px!important;left:10px!important}
  body.tm-map-immersive #tm-desktop-info{display:none!important}
  body.tm-map-immersive #tm-route-day-legend{max-width:calc(100vw - 24px)!important}
  body.tm-map-immersive #tm-map-immersive-actions{top:12px;left:auto;right:10px;gap:5px}
  #tm-map-immersive-actions button{min-height:40px;padding:0 9px;font-size:11px}
  body.tm-map-immersive.tm-immersive-list-open #tm-unified-drawer{
    left:10px!important;right:10px!important;bottom:10px!important
  }
}
@media(max-width:370px){
  #tm-map-immersive-actions button{font-size:10px;padding:0 7px}
}
</style>
<script id="trekmap-immersive-map-js">
(function(){
  'use strict';
  var app=document.getElementById('app'),root=document.body;
  var nativeButton=document.getElementById('map-fullscreen');
  var menuButton=document.querySelector('[data-map-action="fullscreen"]');
  var optionsPanel=document.getElementById('tm-map-options-panel');
  var mapOptions=document.getElementById('tm-map-options');
  var drawer=document.getElementById('tm-unified-drawer');
  if(!app||!nativeButton||!menuButton||typeof map==='undefined'||!map)return;
  var buttons=document.createElement('div');
  buttons.id='tm-map-immersive-actions';
  buttons.setAttribute('role','group');
  buttons.setAttribute('aria-label','Mode carte immersive');
  buttons.innerHTML=
    '<button type="button" id="tm-map-immersive-list" aria-pressed="false"'+
    ' aria-controls="tm-unified-drawer">☷ Treks</button>'+
    '<button type="button" id="tm-map-immersive-detail" hidden'+
    ' aria-label="Ouvrir la fiche complète du trek sélectionné">↗ Fiche</button>'+
    '<button type="button" id="tm-map-immersive-exit" aria-label="Quitter le mode carte">✕ Quitter</button>';
  app.appendChild(buttons);
  var exit=buttons.querySelector('#tm-map-immersive-exit');
  var list=buttons.querySelector('#tm-map-immersive-list');
  var detail=buttons.querySelector('#tm-map-immersive-detail');
  var hadCollapsed=false,requestedNative=false;
  function selectedTrekId(){
    var focus=window.TrekMapExplorerFocus;
    var id=focus&&typeof focus.getSelected==='function'?focus.getSelected():null;
    if(id==null){
      var card=document.querySelector('#tm-drawer-track .tm-trek-tile.selected');
      id=card?card.dataset.id:null;
    }
    var num=Number(id);
    return id!=null&&Number.isFinite(num)?num:null;
  }
  function syncDetail(){
    detail.hidden=selectedTrekId()===null;
  }
  detail.addEventListener('click',function(){
    var id=selectedTrekId();
    if(id!==null&&typeof window.openDetail==='function')window.openDetail(id);
  });
  document.addEventListener('trekmap:detail-opened',syncDetail);
  document.addEventListener('trekmap:detail-cleared',syncDetail);
  menuButton.textContent='⛶ Mode carte immersif';
  menuButton.setAttribute('aria-label','Afficher la carte sans les panneaux, avec accès aux treks');
  nativeButton.setAttribute('aria-label','Activer ou quitter le mode carte immersif');
  function invalidate(){
    // Leaflet needs to recompute its dimensions on BOTH entry and exit.
    requestAnimationFrame(function(){
      map.invalidateSize({pan:false,debounceMoveend:true});
      requestAnimationFrame(function(){map.invalidateSize({pan:false})});
    });
  }
  function closeMenu(){
    optionsPanel&&optionsPanel.classList.remove('tm-show');
    optionsPanel&&optionsPanel.setAttribute('aria-hidden','true');
    mapOptions&&mapOptions.setAttribute('aria-expanded','false');
  }
  function reflect(){
    var on=root.classList.contains('tm-map-immersive');
    menuButton.textContent=on?'⛶ Quitter le mode carte':'⛶ Mode carte immersif';
    menuButton.setAttribute('aria-pressed',String(on));
    list.setAttribute('aria-pressed',String(root.classList.contains('tm-immersive-list-open')&&
      drawer&&!drawer.classList.contains('collapsed')));
  }
  function leave(){
    if(!root.classList.contains('tm-map-immersive'))return;
    root.classList.remove('tm-map-immersive','tm-immersive-list-open');
    if(drawer)drawer.classList.toggle('collapsed',hadCollapsed);
    var fullscreen=document.fullscreenElement;
    requestedNative=false;
    if(fullscreen&&document.exitFullscreen){
      try{var response=document.exitFullscreen();if(response&&response.catch)response.catch(function(){})}
      catch(_){}
    }
    reflect();invalidate();
  }
  function enter(){
    if(root.classList.contains('tm-brain-route-mode'))return;
    if(root.classList.contains('tm-map-immersive'))return;
    hadCollapsed=!!(drawer&&drawer.classList.contains('collapsed'));
    root.classList.remove('tm-immersive-list-open');
    root.classList.add('tm-map-immersive');
    syncDetail();reflect();closeMenu();invalidate();
    // Use the DOCUMENT root as native fullscreen target. Modal dialogs and
    // toast messages are siblings of #app; fullscreening only #app made the
    // "Voir la fiche" dialog invisible despite its being open.
    // The CSS focus mode remains a fallback on restricted browsers.
    var fullscreenRoot=document.documentElement;
    if(typeof fullscreenRoot.requestFullscreen==='function'){
      try{
        var response=fullscreenRoot.requestFullscreen({navigationUI:'hide'});
        requestedNative=true;
        if(response&&response.then)response.then(invalidate).catch(function(){
          requestedNative=false;invalidate();
        });
      }catch(_){requestedNative=false}
    }
  }
  function toggle(){if(root.classList.contains('tm-map-immersive'))leave();else enter()}
  nativeButton.onclick=toggle;
  // The old menu has multiple adapter listeners; capture at window prevents
  // a duplicated click toggling the same state twice.
  window.addEventListener('click',function(event){
    if(!event.target.closest('[data-map-action="fullscreen"]'))return;
    event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();
    toggle();closeMenu();
  },true);
  exit.addEventListener('click',leave);
  list.addEventListener('click',function(){
    var on=!root.classList.contains('tm-immersive-list-open');
    root.classList.toggle('tm-immersive-list-open',on);
    if(on&&drawer)drawer.classList.remove('collapsed');
    reflect();invalidate();
  });
  var drawerHead=document.getElementById('tm-drawer-head');
  if(drawerHead){
    // The existing header already toggles .collapsed. Reflect that state in
    // the immersive Treks button, without adding a duplicate click handler.
    drawerHead.addEventListener('click',function(){
      requestAnimationFrame(function(){
        list.setAttribute('aria-pressed',String(
          root.classList.contains('tm-immersive-list-open')&&
          drawer&&!drawer.classList.contains('collapsed')));
      });
    });
  }
  document.addEventListener('fullscreenchange',function(){
    // Esc leaves browser fullscreen: restore every part of the original UI.
    if(root.classList.contains('tm-map-immersive')&&requestedNative&&!document.fullscreenElement)leave();
    else invalidate();
  });
  document.addEventListener('keydown',function(event){
    if(event.key==='Escape'&&root.classList.contains('tm-map-immersive')){
      event.preventDefault();leave();
    }
  });
  new MutationObserver(function(){
    if(root.classList.contains('tm-brain-route-mode')&&
       root.classList.contains('tm-map-immersive'))leave();
  }).observe(root,{attributes:true,attributeFilter:['class']});
  window.TrekMapImmersive={
    enter:enter,leave:leave,isActive:function(){return root.classList.contains('tm-map-immersive')},
    isListOpen:function(){return root.classList.contains('tm-immersive-list-open')}
  };
  syncDetail();
  reflect();
})();
</script>
<!-- TREKMAP_IMMERSIVE_MAP_END -->'''
if html.count("</body>")!=1:raise SystemExit("Unexpected closing body")
html=html.replace("</body>",block+"\n</body>",1)
path.write_text(html,encoding="utf-8")
print("Immersive map focus mode installed last")
