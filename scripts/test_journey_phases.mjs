/* Three additive user journey phases: syntax, safe contracts, and route math. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const phases=[1,2,3].map(n=>fs.readFileSync('scripts/apply_journey_phase'+n+'.py','utf8'));
for(let n=1;n<=3;n++){
 const p=phases[n-1],js=p.match(/<script id="tm-journey-[^"]+-js">([\s\S]*?)<\/script>/)?.[1];
 assert.ok(js,'Phase '+n+' has its own script');
 new vm.Script(js,{filename:'journey-phase'+n+'.js'});
 assert.ok(p.includes('TM_JOURNEY_PHASE'+n+'_START'));
 assert.ok(p.includes('TM_JOURNEY_PHASE'+n+'_END'));
 assert.ok(p.includes('html.count("</body>")!=1'),'fail closed on malformed HTML');
 assert.ok(!/fetch\s*\(|XMLHttpRequest/.test(js),'No extra providers / network calls in phase '+n);
}
assert.ok(phases[0].includes('dispatchEvent(new Event'), 'remove a filter uses real existing handlers');
assert.ok(phases[0].includes('tm-main-search-clear'), 'search chips use original reset');
assert.ok(phases[1].includes("id='tm-journey-plan-tools'"), 'preparation panel is additive');
assert.ok(phases[1].includes("existing.has(normalized(item))"),'templates avoid duplicates');
assert.ok(phases[1].includes("document.getElementById('checklist')"),'same real saved checklist');
assert.ok(!phases[1].includes('localStorage'),'checklist is saved only through original authenticated save');
assert.ok(phases[2].includes("navigator.geolocation.watchPosition"),'opt-in live GPS');
assert.ok(phases[2].includes("navigator.geolocation.clearWatch"),'tracking can be stopped');
assert.ok(phases[2].includes("window.addEventListener('pagehide',stop)"),'tracking stops on page hide');
assert.ok(phases[2].includes("isSecureContext"),'HTTPS required');
assert.ok(phases[2].includes("Aucune position"),'privacy wording is explicit');
assert.ok(phases[2].includes("sans fond topographique"),'offline map limitation is explicit');
assert.ok(phases[2].includes("URL.revokeObjectURL"),'download object URLs are cleaned up');
assert.ok(phases[0].includes('apply_journey_phase2.py'),'phase 2 is chained');
assert.ok(phases[1].includes('apply_journey_phase3.py'),'phase 3 is chained');

const js=phases[2].match(/<script id="tm-journey-terrain-js">([\s\S]*?)<\/script>/)[1];
const first=js.indexOf(' function coordsOf(t){');
const end=js.indexOf(' function notify(',first);
assert.ok(first>=0&&end>first);
const math=vm.runInNewContext(js.slice(first,end)+'; ({coordsOf,nearestRoute,haversine})');
assert.equal(math.coordsOf({coords:[[45,2],[45.01,2.1]]}).length,2);
assert.equal(math.coordsOf({coords:[[45,2],[95,2]]}).length,0);
assert.equal(math.coordsOf({coords:[[45,2],[true,2]]}).length,0);
assert.equal(math.coordsOf({coords:[[45,2],[null,2]]}).length,0);
assert.equal(math.coordsOf({coords:[[45,2]]}).length,0);
const r=math.nearestRoute([0,0.005],[[0,0],[0,0.01]]);
assert.ok(r.distance<1,'on-trail point should match');
assert.ok(r.remaining>500&&r.remaining<620,'remaining route should be ~556m');
const outside=math.nearestRoute([0.002,0.005],[[0,0],[0,0.01]]);
assert.ok(outside.distance>200,'off-trail point should be detected');
const unsafe=vm.runInNewContext(
 js.slice(first,end)+js.slice(js.indexOf(' function escapeHTML('),js.indexOf(' function offline(t){'))+
 '; ({offlineDocument})');
const doc=unsafe.offlineDocument({name:'<script>alert(1)</script>',region:'<img src=x>',
 description:'</body><script>evil()</script>',distance:3,duration_days:2,
 coords:[[45,2],[45.01,2.02],[45.03,2.03]]});
assert.ok(doc.startsWith('<!doctype html>'));
assert.ok(doc.includes('<svg'));
assert.ok(doc.includes('&lt;script&gt;'));
assert.ok(!doc.includes('<script>'));
assert.ok(!doc.includes('https://'),'offline document must have no external resource');
assert.ok(doc.includes('sans fond IGN/OSM'),'no implication of offline topographic tiles');
const built=fs.readFileSync('frontend/index.html','utf8');
if(built.includes('TM_JOURNEY_PHASE1_START')){
 for(let n=1;n<=3;n++){
  assert.equal(built.split('TM_JOURNEY_PHASE'+n+'_START').length-1,1,'no duplicate stage '+n);
  assert.ok(built.includes('TM_JOURNEY_PHASE'+n+'_END'),'stage '+n+' complete');
 }
}
console.log('JOURNEY 3 PHASES PASS: filters, preparation, GPS math, offline HTML sanitization and build');
