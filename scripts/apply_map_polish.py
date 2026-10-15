from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

# Idempotent: un rebuild ne doit pas empiler plusieurs fois ces petits ajustements.
html = re.sub(
    r"\s*<!-- TREKMAP_MAP_POLISH_START -->.*?<!-- TREKMAP_MAP_POLISH_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_UNIFIED_EXPERIENCE_START" not in html:
    raise SystemExit("La couche unifiée TrekMap doit être construite avant les ajustements de carte.")

block = r'''<!-- TREKMAP_MAP_POLISH_START -->
<style id="trekmap-map-polish-css">
/* Petits ajustements carte/recherche demandés après la refonte mobile. */
@media(max-width:820px){
  .map-tools{top:62px!important}
}
.tm-drawer-count{white-space:nowrap}
</style>
<script id="trekmap-map-polish-js">
(function(){
  const $=id=>document.getElementById(id);

  // Plages adaptées aux treks longue distance.
  const distance=$('distance-range');
  const distanceTolerance=$('distance-tolerance');
  const elevation=$('elevation-range');
  const elevationTolerance=$('elevation-tolerance');
  if(distance){distance.max='1000';distance.step='5'}
  if(distanceTolerance){distanceTolerance.max='500';distanceTolerance.step='5'}
  if(elevation){elevation.max='20000';elevation.step='50'}
  if(elevationTolerance){elevationTolerance.max='10000';elevationTolerance.step='50'}

  // Le badge du tiroir reflète toujours le nombre exact de treks réellement affichés.
  const track=$('tm-drawer-track');
  const count=$('tm-drawer-count');
  function syncResultCount(){
    if(!track||!count)return;
    const n=track.querySelectorAll('.tm-trek-tile').length;
    count.textContent=n+' trek'+(n>1?'s':'');
    count.setAttribute('aria-label',n+' trek'+(n>1?'s':'')+' dans les résultats');
  }
  if(track&&count){
    new MutationObserver(syncResultCount).observe(track,{childList:true,subtree:true});
    requestAnimationFrame(syncResultCount);
  }
})();
</script>
<!-- TREKMAP_MAP_POLISH_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekMap map polish applied")
