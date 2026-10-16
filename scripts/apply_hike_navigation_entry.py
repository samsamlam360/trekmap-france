"""Install trek navigation entry point after the final TrekBrain UI chain."""
from pathlib import Path
import re
p=Path(__file__).resolve().parents[1]/'frontend'/'index.html'
html=p.read_text(encoding='utf-8')
html=re.sub(r'\s*<!-- TM_HIKER_NAV_ENTRY_START -->.*?<!-- TM_HIKER_NAV_ENTRY_END -->\s*','\n',html,flags=re.S)
if 'TM_STAGE_NOTES_START' not in html:raise SystemExit('Navigation entry prerequisites absent')
block='''<!-- TM_HIKER_NAV_ENTRY_START -->
<script id="tm-hiker-nav-entry">
(function(){
 "use strict";
 if(window.TrekMapHikingNavigation)return;
 function clean(t){
  if(!t||!Array.isArray(t.coords)||t.coords.length<2||t.coords.length>60000)return null;
  if(!t.coords.every(function(p){return Array.isArray(p)&&p.length>=2&&
    [p[0],p[1]].every(function(x){return typeof x==='number'&&Number.isFinite(x)})&&
    Math.abs(p[0])<=85&&Math.abs(p[1])<=180}))return null;
  return {id:String(t.id||'trek'),name:String(t.name||'Randonnée').slice(0,120),
          region:String(t.region||'').slice(0,100),
          coords:t.coords.map(function(p){return [p[0],p[1]]})};
 }
 function open(t){
  var data=clean(t);
  if(!data){if(typeof toast==='function')toast('Ce trek ne possède pas de tracé navigable.');return false}
  try{
    localStorage.setItem('tm-navigation-route-v1',JSON.stringify(data));
  }catch(_){if(typeof toast==='function')toast('Stockage de cet appareil saturé. Impossible de préparer le mode randonnée.');return false}
  // A pre-v1026 service worker cached /randonnee forever, even while online.
  // Query-busting forces that old worker to miss the stale page in its cache;
  // the new worker also replaces the canonical page whenever online.
  window.location.assign('/randonnee?fresh=network-first-20261016');return true;
 }
 window.TrekMapHikingNavigation={open:open,clean:clean};
})();
</script>
<!-- TM_HIKER_NAV_ENTRY_END -->'''
if html.count('</body>')!=1:raise SystemExit('unexpected html body closing')
p.write_text(html.replace('</body>',block+'\n</body>',1),encoding='utf-8')
print('Offline hike navigation entry installed')
