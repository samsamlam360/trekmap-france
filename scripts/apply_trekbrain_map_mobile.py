"""Keep the hiking map visible on mobile while map legends stay discoverable.

Pure presentation: no request to ORS, Overpass, Photon, Gemini or Neon.
"""
from pathlib import Path
import re

html_path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")
html = re.sub(
    r"\s*<!-- TREKMAP_MOBILE_MAP_FOCUS_START -->.*?<!-- TREKMAP_MOBILE_MAP_FOCUS_END -->\s*",
    "\n", html, flags=re.S,
)
for marker in ("TREKMAP_ROUTE_DAY_CLARITY_V94", "TREKMAP_TREKBRAIN_V91_MAP_START"):
    if marker not in html:
        raise SystemExit("Map focus prerequisite missing: " + marker)

block = r'''<!-- TREKMAP_MOBILE_MAP_FOCUS_START -->
<style id="trekmap-mobile-map-focus-css">
@media(max-width:820px){
  /* Selected routes should not compete with an unrelated popular-treks drawer.
     Explore / filters / favorites remain available via the bottom navigation. */
  body:has(.tm-route-day-legend) #tm-unified-drawer{
    display:none!important;
  }
  /* Leaflet left controls (zoom etc.) and stage legend remain separated. */
  .leaflet-top.leaflet-left .tm-route-day-legend {
    margin-top:12px!important;margin-left:51px!important;
    min-width:0!important;width:max-content!important;
    max-width:min(208px,calc(100vw - 116px))!important;
    padding:5px 10px!important;background:rgba(255,255,255,.97)!important;
    border:1px solid #d4e4d9!important;border-radius:14px!important;
    box-shadow:0 4px 18px rgba(15,54,31,.14)!important;
  }
  .tm-route-day-details>summary{min-height:40px!important;font-size:13px!important}
  .tm-route-day-details[open] .tm-route-day-rows{
    display:grid!important;gap:5px;max-height:35dvh;overflow-y:auto;
    padding-top:7px;
  }
  .tm-route-day-details[open] .tm-route-day-row {
    display:flex;align-items:center;flex-wrap:wrap;
    min-height:37px!important;padding:6px!important;
  }
  .tm-route-day-legend .tm-route-day-row-text{font-size:12px!important}
  .leaflet-bottom.leaflet-right .tm-v91-legend {
    margin:0 10px calc(95px + env(safe-area-inset-bottom,0px)) 0!important;
    min-width:0!important;width:max-content!important;
    max-width:min(230px,calc(100vw - 24px))!important;
    max-height:40dvh!important;overflow:auto!important;
    border:1px solid #d2e4d8!important;border-radius:14px!important;
    background:rgba(255,255,255,.98)!important;
    box-shadow:0 5px 20px rgba(15,54,31,.15)!important;
  }
  .tm-v91-resource-details>summary{min-height:43px!important}
  .leaflet-popup-content-wrapper{
    max-width:min(350px,calc(100vw - 34px));
    max-height:min(65dvh,540px);overflow:auto;
  }
  .leaflet-popup-content{max-width:calc(100vw - 75px);margin:14px 15px}
  .leaflet-popup-close-button{
    min-width:38px;min-height:38px!important;
    display:grid;place-items:center;color:#1c513b!important;
  }
  /* A bottom navigation should never hide focused map popups or links. */
  .leaflet-container{scroll-padding-bottom:calc(115px + env(safe-area-inset-bottom,0px))}
}
@media(max-width:380px){
  .leaflet-top.leaflet-left .tm-route-day-legend {max-width:174px!important}
  .leaflet-bottom.leaflet-right .tm-v91-legend {margin-bottom:calc(87px + env(safe-area-inset-bottom,0px))!important}
}
</style>
<script id="trekmap-mobile-map-focus-js">
(function(){
  "use strict";
  /* Any gesture returns the controls to their compact form; details are
     still user-openable with a tap and keyboard, including after a pan. */
  var attempts=0;
  function bind(){
    if(typeof map==="undefined" || !map || typeof map.on!=="function"){
      if(++attempts<12)setTimeout(bind,350);
      return;
    }
    if(map._trekMapMobileFocusBound)return;
    map._trekMapMobileFocusBound=true;
    function collapse(){
      if(window.innerWidth>820)return;
      document.querySelectorAll(".tm-route-day-details[open],.tm-v91-resource-details[open]").forEach(function(detail){
        detail.open=false;
      });
    }
    map.on("movestart",collapse);
    map.on("zoomstart",collapse);
    map.on("popupopen",function(event){
      if(window.innerWidth>820)return;
      collapse();
      var popup=event.popup;
      if(!popup || !popup.getLatLng || !map.panInside)return;
      try{
        map.panInside(popup.getLatLng(),{
          paddingTopLeft:[18,120],
          paddingBottomRight:[18,140]
        });
      }catch(_){}
    });
  }
  bind();
})();
</script>
<!-- TREKMAP_MOBILE_MAP_FOCUS_END -->'''
if html.count("</body>") != 1:
    raise SystemExit("Unexpected body count")
html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekBrain compact mobile legends + popup safe areas installed")
