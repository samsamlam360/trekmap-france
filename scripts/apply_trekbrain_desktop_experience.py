"""An isolated, desktop-only TrekBrain workspace enhancement.

The mobile UI is deliberately untouched: every CSS rule is under >=821px
and the desktop navigation is inserted only while this media query matches.
No planning API, routing network requests or database operations.
"""
from pathlib import Path
import re

path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
html = path.read_text(encoding="utf-8")
html = re.sub(
    r"\s*<!-- TREKMAP_TREKBRAIN_DESKTOP_2026_START -->.*?<!-- TREKMAP_TREKBRAIN_DESKTOP_2026_END -->\s*",
    "\n", html, flags=re.S,
)
for prerequisite in (
    "TREKMAP_TREKBRAIN_UX_2026_START",
    "TREKMAP_MOBILE_MAP_FOCUS_START",
    "TREKMAP_SCENIC_PHOTOS_START",
):
    if prerequisite not in html:
        raise SystemExit("Missing previous TrekBrain UI layer: " + prerequisite)

block = r'''<!-- TREKMAP_TREKBRAIN_DESKTOP_2026_START -->
<style id="trekbrain-desktop-workspace-css">
/* Desktop only. Do not change existing 320-820px phone styling or behavior. */
@media screen and (min-width:821px) {
  #tm-ai-overlay {padding:24px}
  #tm-ai-overlay .tm-ai-shell {
    width:min(1600px,calc(100vw - 56px));
    max-width:none;
    height:min(94dvh,960px);
    max-height:calc(100dvh - 48px);
    grid-template-columns:clamp(342px,28vw,418px) minmax(0,1fr);
    border-radius:24px;
    background:#f4f8f5;
    border:1px solid #c9ded1;
    box-shadow:0 30px 100px rgba(9,36,24,.28);
  }
  #tm-ai-overlay .tm-ai-side {
    padding:29px 27px 42px;
    background:linear-gradient(160deg,#fff 78%,#f6faf7);
    border-right:1px solid #dce9df;
    min-width:0;
  }
  #tm-ai-overlay .tm-ai-result {
    padding:26px clamp(23px,2.7vw,46px) 40px;
    min-width:0;
    background:#f4f8f5;
  }
  #tm-ai-overlay .tm-ai-head h2 {font-size:clamp(27px,2vw,32px)}
  #tm-ai-overlay .tm-ai-head p {max-width:42ch}
  #tm-ai-overlay #tm-ai-prompt {min-height:148px}
  #tm-ai-overlay .tm-ux-examples {margin-bottom:22px}
  #tm-ai-overlay .tm-ux-example {min-height:44px}
  #tm-ai-overlay .tm-ai-titlebar h2 {
    font-size:clamp(25px,2.4vw,35px);
    max-width:28ch;
    text-wrap:balance;
  }
  #tm-ai-overlay .tm-ai-titlebar p {
    font-size:14px;line-height:1.6;max-width:65ch;
  }
  #tm-ai-overlay .tm-ai-badges {gap:9px}
  #tm-ai-overlay .tm-ai-stats {
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:12px;margin:20px 0;
  }
  #tm-ai-overlay .tm-ai-stat {
    padding:16px 17px;
    background:#fff;border:1px solid #d9e7dd;border-radius:14px;
  }
  #tm-ai-overlay .tm-ai-stat b {font-size:clamp(20px,1.65vw,26px)}
  #tm-ai-overlay .tm-ux-essentials {
    border:1px solid #cbdfd1;
    border-radius:17px;
    background:#fff;
    box-shadow:0 3px 18px rgba(21,66,40,.045);
    padding:20px;
  }
  #tm-ai-overlay .tm-ux-essentials h3 {font-size:19px}
  #tm-ai-overlay .tm-ux-status-grid {gap:11px}
  #tm-ai-overlay .tm-ux-status {padding:13px 14px;border-radius:12px}
  #tm-ai-overlay .tm-ux-status span {font-size:14px}
  #tm-ai-overlay .tm-ux-safety {padding:15px 16px}
  #tm-ai-overlay .tm-ai-section {margin-top:26px}
  #tm-ai-overlay .tm-ai-section h3 {font-size:19px}
  #tm-ai-overlay .tm-ai-stage {
    padding:17px 19px 18px;
    border-radius:15px;margin-bottom:12px;
    box-shadow:0 3px 10px rgba(15,71,43,.035);
  }
  #tm-ai-overlay .tm-ai-stage-head b {font-size:16px}
  #tm-ai-overlay .tm-ai-stage-head span {font-size:13px}
  #tm-ai-overlay .tm-ai-stage p {font-size:14px;line-height:1.6}
  #tm-ai-overlay .tm-ux-photo-media {height:185px}
  #tm-ai-overlay .tm-ux-view-info {padding:14px}
  #tm-ai-overlay .tm-ai-actions {
    position:sticky;
    bottom:-35px;
    z-index:7;
    gap:13px;
    padding:17px 0 11px;
    border-top:1px solid #d8e7dd;
    background:rgba(244,248,245,.97);
    backdrop-filter:blur(8px);
  }
  #tm-ai-overlay .tm-ai-actions button {min-height:50px;padding-inline:18px}
  #tm-ai-overlay .tm-ai-map-btn {background:#fff}
  #tm-ai-overlay .tm-ai-actions button:focus-visible,
  #tm-ai-overlay .tm-desk-contents button:focus-visible {
    outline:3px solid #e5a32c!important;outline-offset:3px;
  }
  #tm-ai-overlay .tm-ai-refine-box {padding:19px;margin-top:23px}
  #tm-ai-overlay .tm-v9-panel {background:#fff}
  /* A compact, keyboard accessible index. Content remains in original DOM. */
  #tm-ai-overlay .tm-desk-contents {
    display:flex;
    align-items:center;
    gap:8px;
    position:sticky;
    top:-26px;
    z-index:9;
    padding:12px 9px 13px;
    margin:-12px -10px 22px;
    overflow-x:auto;scrollbar-width:thin;
    background:rgba(244,248,245,.97);
    border-bottom:1px solid #dce8df;
    backdrop-filter:blur(12px);
  }
  #tm-ai-overlay .tm-desk-contents::before {
    content:"PARCOURIR";
    flex:0 0 auto;
    font-size:10px;letter-spacing:.10em;font-weight:850;
    color:#587767;margin-right:4px;
  }
  #tm-ai-overlay .tm-desk-contents button {
    flex:0 0 auto;
    min-height:40px;
    padding:9px 13px;
    border:1px solid #d2e5d8;
    border-radius:999px;
    background:#fff;color:#245c42;
    font-size:13px;font-weight:750;
    cursor:pointer;
  }
  #tm-ai-overlay .tm-desk-contents button:hover {
    border-color:#76b394;background:#eaf5ed;
  }
  #tm-ai-overlay .tm-desk-contents button[aria-current="location"] {
    color:#fff;background:#146342;border-color:#146342;
  }
  #tm-ai-overlay .tm-ai-result .tm-ai-titlebar,
  #tm-ai-overlay .tm-ai-result .tm-ux-essentials,
  #tm-ai-overlay .tm-ai-result .tm-ai-section,
  #tm-ai-overlay .tm-ai-result .tm-v9-panel {
    scroll-margin-top:92px;
  }
  /* Leaflet panels stay in opposite corners instead of hiding the map. */
  .leaflet-top.leaflet-left .tm-route-day-legend {
    margin-left:55px!important;
    margin-top:12px!important;
    max-width:min(255px,28vw)!important;
    max-height:min(42dvh,360px)!important;
    overflow-y:auto!important;
    padding:9px 12px!important;
    border-radius:14px!important;
    border:1px solid #cedfd3!important;
    background:rgba(255,255,255,.97)!important;
    box-shadow:0 6px 22px rgba(17,54,34,.15)!important;
  }
  .leaflet-bottom.leaflet-right .tm-v91-legend {
    margin:0 17px 22px 0!important;
    max-width:260px!important;
    max-height:min(42dvh,380px)!important;
    overflow:auto!important;
    border-radius:14px!important;
    border:1px solid #cedfd3!important;
    box-shadow:0 6px 22px rgba(17,54,34,.15)!important;
  }
  .tm-route-day-details > summary,
  .tm-v91-resource-details > summary {min-height:42px}
  .leaflet-popup-content-wrapper {
    max-width:min(430px,calc(100vw - 110px));
    max-height:min(66dvh,540px);
    overflow:auto;
  }
  .leaflet-popup-close-button {
    min-width:35px;min-height:35px;
  }
}
/* Readable cards on wide desktops, but no squeezed half-width cards on laptops. */
@media screen and (min-width:1360px) {
  #tm-ai-overlay .tm-ai-result .tm-ai-section:has(> .tm-ai-stage) {
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    align-items:stretch;
    gap:0 15px;
  }
  #tm-ai-overlay .tm-ai-result .tm-ai-section:has(> .tm-ai-stage) > h3 {
    grid-column:1/-1;
  }
  #tm-ai-overlay .tm-ai-result .tm-ai-section:has(> .tm-ai-stage) > .tm-ai-stage {
    min-width:0;
    align-self:stretch;
  }
}
@media screen and (min-width:1550px) {
  #tm-ai-overlay .tm-ux-status-grid {grid-template-columns:repeat(4,minmax(0,1fr))}
  #tm-ai-overlay .tm-ux-scenic-grid {grid-template-columns:repeat(3,minmax(0,1fr))}
}
@media screen and (min-width:821px) and (max-width:1100px) {
  #tm-ai-overlay {padding:12px}
  #tm-ai-overlay .tm-ai-shell {
    width:calc(100vw - 24px);
    height:calc(100dvh - 24px);
    max-height:calc(100dvh - 24px);
    grid-template-columns:minmax(285px,320px) minmax(0,1fr);
  }
  #tm-ai-overlay .tm-ai-side {padding:20px 16px 26px}
  #tm-ai-overlay .tm-ai-result {padding:20px 19px 30px}
  #tm-ai-overlay .tm-ai-stats {grid-template-columns:repeat(2,minmax(0,1fr))}
  #tm-ai-overlay .tm-desk-contents {top:-20px}
}
@media screen and (min-width:821px) and (max-height:650px) {
  #tm-ai-overlay .tm-ai-shell {
    height:calc(100dvh - 20px);
    max-height:calc(100dvh - 20px);
  }
}
@media (prefers-reduced-motion:reduce) and (min-width:821px) {
  #tm-ai-overlay .tm-desk-contents {scroll-behavior:auto}
}
</style>
<script id="trekbrain-desktop-workspace-js">
(function(){
  "use strict";
  var overlay=document.getElementById('tm-ai-overlay');
  if(!overlay || overlay.dataset.desktopWorkspaceReady==='true')return;
  var pane=overlay.querySelector('.tm-ai-result');
  var content=document.getElementById('tm-ai-content');
  if(!pane || !content)return;
  overlay.dataset.desktopWorkspaceReady='true';
  var nav=null,targets=[],lastTargets=[];
  function isDesktop(){return window.innerWidth>820;}
  function sections(){
    var result=[
      {label:'Résumé',node:content.querySelector('.tm-ai-titlebar')},
      {label:'À vérifier',node:content.querySelector('.tm-ux-essentials')}
    ];
    var stages=Array.prototype.find.call(
      content.querySelectorAll('.tm-ai-section'),
      function(section){return !!section.querySelector(':scope > .tm-ai-stage');}
    );
    result.push({label:'Étapes',node:stages});
    result.push({label:'Panoramas',node:content.querySelector('.tm-ux-scenic')});
    result.push({label:'Analyse',node:content.querySelector('#tm-v9-panel')});
    return result.filter(function(item){return !!item.node;});
  }
  function makeNav(){
    if(nav)return nav;
    nav=document.createElement('nav');
    nav.className='tm-desk-contents';
    nav.setAttribute('aria-label','Aller à une section du résultat TrekBrain');
    pane.insertBefore(nav,content);
    return nav;
  }
  function activeFromScroll(){
    if(!nav || !isDesktop() || !targets.length)return;
    var top=pane.getBoundingClientRect().top+120;
    var best=0;
    targets.forEach(function(item,i){
      if(item.node.getBoundingClientRect().top<=top)best=i;
    });
    nav.querySelectorAll('button').forEach(function(button,i){
      if(i===best)button.setAttribute('aria-current','location');
      else button.removeAttribute('aria-current');
    });
  }
  function jumpTo(item){
    var details=item.node.querySelector('.tm-ux-analysis-details');
    if(details)details.open=true;
    var targetTop=item.node.getBoundingClientRect().top;
    var viewportTop=pane.getBoundingClientRect().top;
    var destination=Math.max(0,pane.scrollTop+targetTop-viewportTop-82);
    var reduced=window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    pane.scrollTo({top:destination,behavior:reduced?'auto':'smooth'});
    item.node.setAttribute('tabindex','-1');
    item.node.focus({preventScroll:true});
  }
  function refresh(){
    if(!isDesktop()){
      if(nav){nav.remove();nav=null;}
      targets=[];lastTargets=[];
      return;
    }
    var next=sections();
    if(!next.length){if(nav)nav.hidden=true;targets=[];lastTargets=[];return;}
    makeNav().hidden=false;
    var unchanged=lastTargets.length===next.length &&
      next.every(function(item,i){
        return lastTargets[i]&&lastTargets[i].label===item.label &&
          lastTargets[i].node===item.node;
      });
    if(unchanged)return;
    nav.replaceChildren();
    targets=next;
    lastTargets=next.slice();
    next.forEach(function(item){
      var button=document.createElement('button');
      button.type='button';
      button.textContent=item.label;
      button.addEventListener('click',function(){jumpTo(item);});
      nav.appendChild(button);
    });
    activeFromScroll();
  }
  new MutationObserver(refresh).observe(content,{childList:true,subtree:true});
  pane.addEventListener('scroll',activeFromScroll,{passive:true});
  window.addEventListener('resize',refresh,{passive:true});
  refresh();
})();
</script>
<!-- TREKMAP_TREKBRAIN_DESKTOP_2026_END -->'''

if html.count("</body>") != 1:
    raise SystemExit("Unexpected closing body count")
html = html.replace("</body>", block + "\n</body>", 1)
path.write_text(html, encoding="utf-8")
print("TrekBrain desktop workspace applied (mobile <=820px preserved)")
