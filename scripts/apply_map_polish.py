from pathlib import Path
import base64
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
logo_path = root / "frontend" / "logo-trekmap.svg"
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

logo_src = ""
if logo_path.exists():
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    logo_src = f"data:image/svg+xml;base64,{encoded}"

block = r'''<!-- TREKMAP_MAP_POLISH_START -->
<style id="trekmap-map-polish-css">
/* Petits ajustements carte/recherche demandés après la refonte mobile. */
#tm-map-brand-logo{display:none}
@media(max-width:820px){
  #tm-map-brand-logo{
    position:absolute;z-index:1450;top:10px;right:10px;
    display:flex;align-items:center;justify-content:center;
    min-width:92px;height:44px;padding:5px 9px;
    border:1px solid rgba(216,229,222,.96);border-radius:13px;
    background:rgba(255,255,255,.96);box-shadow:0 8px 22px rgba(12,53,36,.16);
    backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)
  }
  #tm-map-brand-logo img{display:block;max-width:100px;max-height:32px;width:auto;height:auto}
  #tm-map-brand-logo .tm-map-brand-fallback{font-weight:900;font-size:12px;color:#116b49;white-space:nowrap}
  .map-tools{top:62px!important}
}
.tm-drawer-count{white-space:nowrap}
</style>
<script id="trekmap-map-polish-js">
(function(){
  const $=id=>document.getElementById(id);

  // Logo TrekMap visible sur la carte mobile, comme avant la refonte.
  const mapEl=$('map');
  if(mapEl && !$('tm-map-brand-logo')){
    const brand=document.createElement('button');
    brand.id='tm-map-brand-logo';
    brand.type='button';
    brand.setAttribute('aria-label','TrekMap France - accueil');
    brand.innerHTML=__LOGO_HTML__;
    brand.addEventListener('click',e=>{
      e.preventDefault();e.stopPropagation();
      if(typeof window.TrekMapShowHome==='function')window.TrekMapShowHome();
      else $('tm-brand')?.click();
    });
    brand.addEventListener('pointerdown',e=>e.stopPropagation());
    mapEl.appendChild(brand);
  }

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

logo_html = (
    f'<img src="{logo_src}" alt="TrekMap France">'
    if logo_src
    else '<span class="tm-map-brand-fallback">🥾 TrekMap France</span>'
)
block = block.replace("__LOGO_HTML__", repr(logo_html))
html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekMap map polish applied")
