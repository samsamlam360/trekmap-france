/* Contract: "Plein écran" must be real map exploration, reversible and free. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync('scripts/apply_immersive_map.py','utf8');
const js=source.match(/<script id="trekmap-immersive-map-js">([\s\S]*?)<\/script>/)?.[1];
const css=source.match(/<style id="trekmap-immersive-map-css">([\s\S]*?)<\/style>/)?.[1];
assert.ok(js&&css,'Missing last UI layer');
new vm.Script(js,{filename:'trekmap-immersive-map.js'});
for(const element of ['tm-map-immersive','tm-immersive-list-open','tm-map-immersive-actions',
  'tm-map-immersive-exit','tm-map-immersive-list','tm-unified-topbar','tm-unified-drawer',
  'tm-map-control-dock','tm-desktop-info','tm-mobile-nav','map.invalidateSize']){
  assert.ok(js.includes(element)||css.includes(element),element+' absent');
}
for(const control of ['document.documentElement','document.exitFullscreen',
  'fullscreenchange','Escape','aria-pressed','document.fullscreenElement',
  'requestedNative','stopImmediatePropagation']){
  assert.ok(js.includes(control),'Fullscreen behavior missing '+control);
}
assert.ok(css.includes('body.tm-map-immersive #map')&&
          css.includes('body.tm-map-immersive.tm-immersive-list-open #tm-unified-drawer'),
          'Mode should expand map and allow showing the original drawer');
assert.ok(css.includes('#tm-unified-drawer.collapsed')&&css.includes('height:44px!important'),
  'Immersive bottom chevron must collapse to the small header');
assert.ok(js.includes('fullscreenRoot.requestFullscreen') &&
          js.includes('document.documentElement'),
  'Native fullscreen must include sibling detail modals, not only the map');
assert.ok(!js.includes('app.requestFullscreen('),
  'Fullscreening #app would hide the detail modal outside the fullscreen top layer');
for(const tag of ['tm-map-immersive-detail','trekmap:detail-opened','trekmap:detail-cleared',
                  'selectedTrekId','window.openDetail(id)']){
  assert.ok(js.includes(tag),'Immersive trek detail button must work at all breakpoints: '+tag);
}
assert.ok(css.includes('#tm-map-immersive-actions #tm-map-immersive-detail[hidden]'),
  'No fiche button unless a trek is selected');
assert.ok(!/\bfetch\s*\(|XMLHttpRequest|DATABASE_URL|\/ai\/plan|\/treks\/|localStorage/.test(js),
          'Map immersion must never call network, write to Neon or change persisted state');
const predecessor=fs.readFileSync('scripts/apply_explorer_map_tools.py','utf8');
assert.ok(predecessor.includes('run_path(str(Path(__file__).with_name("apply_immersive_map.py")))'),
          'Immersive mode must be final Render layer');
console.log('IMMERSIVE MAP CONTRACT PASS: fullscreen, CSS fallback, original drawer, exit and safety');
