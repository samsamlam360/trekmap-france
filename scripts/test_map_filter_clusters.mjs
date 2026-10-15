/* No paid providers, no duplicate map geometry, real UI filters only. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const src=fs.readFileSync('scripts/apply_explorer_map_tools.py','utf8');
const js=src.match(/<script id="trekmap-map-tools-v2-js">([\s\S]*?)<\/script>/)?.[1];
const css=src.match(/<style id="trekmap-map-tools-v2-css">([\s\S]*?)<\/style>/)?.[1];
assert.ok(js&&css);
new vm.Script(js,{filename:'trekmap-map-tools-v2.js'});
for(const token of ['tm-search-filter-toggle','tm-inline-sort','tm-inline-route',
 'tm-map-filter-popover','distance-range','distance-tolerance','elevation-range',
 'elevation-tolerance','duration-filter','map.on','TrekMapClearSelectedTrek',
 'tm-brain-route-mode','TrekMapClusters','getCounts','bubblingMouseEvents:false',
 'clusterLayer','filteredTreks','requestAnimationFrame']){
 assert.ok(js.includes(token),'Missing '+token);
}
assert.ok(css.includes('tm-trek-cluster')&&css.includes('tm-filterstrip-closed'));
assert.ok(!/\bfetch\s*\(|XMLHttpRequest|\/treks\/geojson|\/ai\/plan|DATABASE_URL|window\.TrekMapOpenTrek\s*=/.test(js),
  'No external endpoints, DB modification or replacement of original route opening');
const finish=fs.readFileSync('scripts/apply_explorer_finish.py','utf8');
assert.ok(finish.includes('run_path(str(Path(__file__).with_name("apply_explorer_map_tools.py")))'),
 'Render must install controls as final layer');
assert.ok(finish.includes('trekmap:detail-cleared'),'clear the native selected route glow');
const unified=fs.readFileSync('scripts/apply_unified_experience.py','utf8');
for(const t of ['function clearSelectedTrek()','window.TrekMapClearSelectedTrek=clearSelectedTrek',
                "new CustomEvent('trekmap:detail-cleared')"])assert.ok(unified.includes(t));
console.log('MAP TOOLS CONTRACT PASS: collapse, isolated quick controls, cluster counts and safe map deselection');
