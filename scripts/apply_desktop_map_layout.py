"""TrekMap desktop map workspace, visual layer only. Installed after existing UI."""
from pathlib import Path
import re

path=Path(__file__).resolve().parents[1] / "frontend" / "index.html"
html=path.read_text(encoding="utf-8")
html=re.sub(r"\s*<!-- TREKMAP_DESKTOP_MAP_2026_START -->.*?<!-- TREKMAP_DESKTOP_MAP_2026_END -->\s*", "\n",html,flags=re.S)
for token in ("TREKMAP_UNIFIED_EXPERIENCE_START","TREKMAP_SITEWIDE_UX_START","tm-desktop-info","tm-drawer-nav"):
    if token not in html:
        raise SystemExit("Missing desktop map prerequisite: "+token)
block=r'''<!-- TREKMAP_DESKTOP_MAP_2026_START -->
<style id="trekmap-desktop-map-2026">
/* Build an actual map workspace without removing routes, controls or forms. */
#tm-brand .tm-brand-mark {background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.11);overflow:hidden;flex:0 0 auto}
#tm-brand .tm-brand-mark img {height:48px;width:42px;object-fit:contain;display:block}
#tm-brand .tm-brand-copy {letter-spacing:-.01em}
#tm-brand .tm-brand-copy strong {font-size:21px}
#tm-main-search-wrap {border:1px solid #d8e8df!important;border-radius:13px!important;box-shadow:0 5px 18px rgba(5,31,20,.09)!important}
#tm-main-search-wrap:focus-within {outline:0!important;border-color:#68b395!important;box-shadow:0 0 0 2px rgba(32,137,92,.19)!important}
#tm-main-search:focus,#tm-main-search:focus-visible {outline:none!important;box-shadow:none!important}
#tm-main-search::placeholder {font-size:14px}
/* Informational toast must never intercept modal close or map controls. */
.toast {pointer-events:none!important}
.tm-drawer-nav {position:absolute;top:4px;right:56px;z-index:3;display:flex;gap:5px}
.tm-drawer-nav button {display:grid;place-items:center;width:36px;height:36px;min-height:36px;padding:0;background:#f0f8f3;color:#145b3e;border:1px solid #d3e5d8;border-radius:10px;font-size:23px;font-weight:600;line-height:1;cursor:pointer}
.tm-drawer-nav button:hover:not(:disabled) {background:#dff2e6;border-color:#7bbaa0}
.tm-drawer-nav button:disabled {opacity:.4;cursor:default}
#tm-drawer-head {padding-right:145px!important}
#tm-drawer-head .tm-drawer-count {margin-left:auto}
#tm-drawer-track {scroll-behavior:smooth;scrollbar-color:#94b5a2 #eaf3ed;scrollbar-width:thin;touch-action:pan-x pan-y}
#tm-drawer-track .tm-trek-tile {user-select:none;-webkit-user-select:none;transition:border-color .15s,box-shadow .15s,background-color .15s}
#tm-drawer-track .tm-trek-tile.selected {background:#edfaf1!important;border:2px solid #168a5e!important}
#tm-drawer-track .tm-trek-tile:hover {transform:none;box-shadow:0 9px 25px rgba(17,78,47,.15)}
#tm-desktop-info {display:none}
.tm-info-overview,.tm-info-selected {background:rgba(255,255,255,.98);border:1px solid #d8e7dd;border-radius:18px;box-shadow:0 10px 28px rgba(15,54,33,.11);padding:13px}
.tm-info-overview {flex:0 0 auto}
.tm-info-landscape {height:95px;border-radius:13px;display:flex;align-items:flex-end;justify-content:space-between;gap:10px;padding:14px;background:linear-gradient(150deg,#97ccb1 5%,#247950 45%,#0b513b 100%);color:white;position:relative;overflow:hidden}
.tm-info-landscape:before {content:"";position:absolute;width:140px;height:98px;top:-32px;right:-20px;transform:rotate(-28deg);background:rgba(241,255,246,.23);border-radius:46%}
.tm-info-landscape span {font-size:40px;line-height:1;z-index:1}
.tm-info-landscape b {font-size:12px;z-index:1}
.tm-info-topline {font-size:10px;font-weight:900;letter-spacing:.12em;color:#4a8563;margin-top:10px}
.tm-info-overview h2 {font-size:19px;margin:4px 0 6px;color:#133e2b}
.tm-info-overview p {font-size:12px;line-height:1.5;color:#607268;margin:0 0 12px}
.tm-info-count {display:flex;align-items:center;gap:10px;border-top:1px solid #e4ede6;padding-top:11px}
.tm-info-count strong {font-size:28px;line-height:1;color:#136344}
.tm-info-count span {font-size:11px;color:#587264}
.tm-info-selected {min-height:170px;display:flex;flex-direction:column;min-width:0;overflow:auto}
.tm-info-selected .tm-info-topline {margin-top:2px}
.tm-info-empty {text-align:center;padding:18px 3px}
.tm-info-empty > span {display:block;font-size:37px;color:#1e8d5f;margin-bottom:8px}
.tm-info-empty b {font-size:14px;color:#173d2c}
.tm-info-empty p {font-size:12px;line-height:1.5;color:#658071;margin:7px 0}
.tm-info-trek-name {font-size:18px;font-weight:900;color:#153f2c;margin-top:10px;line-height:1.2}
.tm-info-region {font-size:12px;color:#668070;margin:7px 0}
.tm-info-kpis {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;margin-top:14px}
.tm-info-kpis div {padding:8px 4px;background:#f1f8f3;border-radius:9px;text-align:center}
.tm-info-kpis strong {display:block;font-size:12px;white-space:nowrap;color:#104b33}
.tm-info-kpis span {font-size:10px;color:#627669}
.tm-info-description {font-size:12px;line-height:1.55;color:#547261;word-break:break-word}
.tm-info-controls {display:flex;gap:8px;margin-top:auto;padding-top:10px}
.tm-info-controls[hidden] {display:none!important}
.tm-info-controls button {flex:1;min-width:0;min-height:42px;padding:7px 10px;font-size:12px;font-weight:800;color:#145a3e;background:#eaf5ed;border:1px solid #c2daca;border-radius:11px}
.tm-info-controls button:last-child {color:white;background:#117e55;border-color:#117e55}
.tm-info-controls button:hover {filter:brightness(.96)}
@media(min-width:1240px){
  :root{--tm-panel:310px;--tm-drawer:218px}
  #tm-unified-topbar{grid-template-columns:225px minmax(250px,500px) minmax(0,1fr)!important;gap:12px!important}
  #tm-main-search-wrap {max-width:500px}
  #sidebar {width:var(--tm-panel)!important;min-width:var(--tm-panel)!important}
  #sidebar .filters {border-radius:18px!important;background:#fff!important}
  #tm-unified-drawer {left:calc(var(--tm-panel) + 18px)!important;right:16px!important;bottom:12px!important;height:var(--tm-drawer)!important}
  #tm-unified-drawer.collapsed {height:44px!important}
  #tm-drawer-track {height:calc(var(--tm-drawer) - 48px)!important;gap:12px!important;padding:4px 14px 13px}
  #tm-drawer-track .tm-trek-tile {flex:0 0 233px!important;height:148px!important;padding:13px!important}
  #tm-desktop-info {display:flex;flex-direction:column;gap:12px;position:absolute;z-index:3300;right:16px;top:calc(var(--tm-top) + 20px);bottom:calc(var(--tm-drawer) + 25px);width:268px;pointer-events:auto}
  .map-tools {right:302px!important}
  .leaflet-control-zoom {margin-left:12px!important}
  body.tm-brain-route-mode #tm-desktop-info {display:none!important}
  body.tm-brain-route-mode .map-tools {right:16px!important}
}
@media(min-width:1240px) and (max-height:720px){
  .tm-info-landscape {height:65px}
  .tm-info-overview p {display:none}
  #tm-desktop-info {gap:7px}
  .tm-info-overview,.tm-info-selected {padding:10px}
}
@media(max-width:1239px) {
  /* On narrow desktop, retain the original functional map layout. */
  .tm-drawer-nav{right:53px}
}
@media(max-width:820px) {
  #tm-brand .tm-brand-mark img {height:39px;width:34px}
  #tm-drawer-head {padding-right:135px!important}
  .tm-drawer-nav {right:45px}
  .tm-drawer-nav button {width:32px;height:34px;min-height:34px}
  #tm-desktop-info {display:none!important}
  #tm-drawer-track {scroll-behavior:auto}
}

/* V2 mockup fidelity: three clear zones with spacious central map. */
@media(min-width:1240px){
  :root{--tm-panel:335px;--tm-drawer:224px}
  #tm-unified-topbar{grid-template-columns:245px minmax(275px,520px) minmax(0,1fr)!important;padding-inline:20px!important}
  #sidebar{width:var(--tm-panel)!important;min-width:var(--tm-panel)!important;left:16px!important}
  #sidebar .filters:not(.tm-collapsed){
    max-height:calc(100dvh - var(--tm-top) - 26px)!important;
    height:calc(100dvh - var(--tm-top) - 26px)!important;
    background:rgba(255,255,255,.985)!important;
    border:1px solid #d8e9df!important;
    border-radius:17px!important;
    box-shadow:0 12px 36px rgba(18,67,43,.13)!important;
    padding-inline:16px!important
  }
  #sidebar .filter-row{padding:9px!important;border-color:#e2ece5!important}
  #sidebar .tm-filter-section{font-size:10px!important;letter-spacing:.05em!important;margin-top:13px!important}
  #sidebar .filters .field label,#sidebar .filters .tm-criterion label{font-size:11px!important}
  .leaflet-left{left:calc(var(--tm-panel) + 23px)!important}
  #tm-unified-drawer{
    left:calc(var(--tm-panel) + 31px)!important;right:16px!important;bottom:12px!important;
    height:var(--tm-drawer)!important;
  }
  body.tm-filters-collapsed #tm-unified-drawer{left:calc(var(--tm-panel) + 31px)!important}
  #tm-unified-drawer .tm-drawer-shell{border-radius:16px!important;box-shadow:0 12px 34px rgba(17,56,39,.14)!important}
  #tm-drawer-head{height:46px!important}
  #tm-drawer-track{height:calc(var(--tm-drawer) - 49px)!important;padding:4px 12px 9px!important;gap:11px!important}
  #tm-drawer-track .tm-trek-tile{
    position:relative!important;flex:0 0 207px!important;height:164px!important;
    padding:7px!important;border-radius:12px!important;
    display:flex!important;flex-direction:column;align-items:stretch;overflow:hidden
  }
  #tm-drawer-track .tm-trek-tile strong{font-size:12px!important;margin:4px 1px 0!important;line-height:1.2}
  #tm-drawer-track .tm-trek-tile .region{font-size:10px!important;margin:2px 1px!important}
  #tm-drawer-track .tm-tile-chips{margin:4px 0!important;gap:4px}
  #tm-drawer-track .tm-chip{font-size:9px!important;padding:2px 5px!important}
  #tm-drawer-track .tm-tile-meta{font-size:10px!important;margin-top:1px!important}
  #tm-drawer-track .tm-tile-open{bottom:5px!important;right:8px!important;font-size:9px!important}
  #tm-drawer-track .tm-tile-landscape{
    height:69px!important;min-height:69px!important;display:block!important;
    border-radius:8px;background-image:url('/trek-scenery.svg');
    background-size:cover;background-position:center 55%;
    border:1px solid rgba(18,91,57,.10)
  }
  #tm-drawer-track .tm-tile-landscape-1{background-position:34% 38%;filter:hue-rotate(11deg)}
  #tm-drawer-track .tm-tile-landscape-2{background-position:78% 44%;filter:hue-rotate(33deg) saturate(.89)}
  #tm-drawer-track .tm-tile-landscape-3{background-position:57% 80%;filter:hue-rotate(-16deg)}
  #tm-drawer-track .tm-tile-landscape-4{background-position:85% 30%;filter:hue-rotate(68deg) saturate(.7)}
  #tm-desktop-info{
    width:283px!important;right:16px!important;top:calc(var(--tm-top) + 16px)!important;
    bottom:calc(var(--tm-drawer) + 25px)!important;gap:9px!important
  }
  .tm-info-overview,.tm-info-selected{border-radius:15px!important;padding:12px!important}
  .tm-info-overview h2{font-size:18px!important}
  .tm-info-overview p{font-size:11px!important;margin-bottom:6px!important}
  .tm-info-landscape{
    height:83px!important;background-image:linear-gradient(0deg,rgba(0,52,36,.55),transparent 72%),url('/trek-scenery.svg')!important;
    background-size:cover!important;background-position:center 55%!important;border-radius:11px!important
  }
  .tm-info-landscape:before{display:none!important}
  .tm-info-overview .tm-info-topline{margin-top:7px!important}
  .tm-info-count{padding-top:7px!important}
  .tm-info-count strong{font-size:24px!important}
  .tm-info-selected{flex:1 1 auto!important;min-height:145px!important;overflow-y:auto!important}
  .tm-info-selected .tm-info-topline{margin-bottom:1px!important}
  .tm-info-trek-name{margin-top:5px!important;font-size:15px!important}
  .tm-info-kpis{margin-top:8px!important}
  .tm-info-kpis div{padding:7px 2px!important}
  .tm-info-description{font-size:11px!important;line-height:1.45!important}
  .map-tools{right:310px!important}
  body.tm-brain-route-mode .map-tools{right:16px!important}
}
/* Preserve existing phone sheet, no extra desktop cards or panels on phones. */
@media(max-width:1239px){
  #tm-drawer-track .tm-tile-landscape{display:none}
}
</style>
<!-- TREKMAP_DESKTOP_MAP_2026_END -->'''
if html.count("</body>") != 1:
    raise SystemExit("Unexpected closing body marker")
html=html.replace("</body>",block+"\n</body>",1)
path.write_text(html,encoding="utf-8")
print("TrekMap desktop workspace, accessible carousel navigation and responsive map panels installed")
