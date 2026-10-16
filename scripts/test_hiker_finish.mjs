/* Contract for completed UX without inventing navigation or route guarantees. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const path=n=>'scripts/'+n;
const files=['apply_journey_phase1.py','apply_journey_phase2.py','apply_journey_phase3.py',
             'apply_hiker_discovery.py','apply_trekbrain_stage_notes.py'];
const all=files.map(x=>fs.readFileSync(path(x),'utf8'));
const js=all.map((content,i)=>{
 const m=content.match(/<script id="[^"]+">([\s\S]*?)<\/script>/);
 assert.ok(m,files[i]+' must contain JS');new vm.Script(m[1],{filename:files[i]});return m[1];
});
const core=fs.readFileSync('frontend/index.html','utf8');
const backend=fs.readFileSync('backend/main.py','utf8');
const unified=fs.readFileSync(path('apply_unified_experience.py'),'utf8');
const workspace=fs.readFileSync(path('apply_trekbrain_map_workspace.py'),'utf8');
const site=fs.readFileSync(path('apply_sitewide_ux.py'),'utf8');
assert.ok(all[1].includes('flex:0 0 20px!important') && all[1].includes('flex:1 1 0%!important'),
  'global full-width input rule must not squeeze text fields into the right edge');
assert.ok(all[0].includes('window.innerWidth>820?document.body:mobile') &&
  all[0].includes('body.tm-filterstrip-closed > #tm-journey-active-filters'),
  'active pills stay visible and rise when the toolbar is folded');
assert.ok(all[0].includes("id==='tm-rating-filter'"),
  'default Avis Toutes must not appear as a selected filter');
assert.ok(js[3].includes("pop.id='tm-quick-pace-popover'") && !js[3].includes("quick.click()"),
  'Km/jour needs isolated popover rather than opening all filters');
assert.ok(!all[1].includes("new MutationObserver(function(){enhance();progress()}"),'no modal mutation observer while typing');
assert.ok(core.includes("TrekMapJourneyPlanner?.refresh?.()"),'enhancer explicitly installed when the actual fiche opens');
assert.ok(all[1].includes('out.firstChild.textContent!==label'),'no continuous child text mutation');
assert.ok(js[1].includes('function openFor(t,data)')&&js[1].includes('function getDays()'),'real editable per-day UI');
assert.ok(core.includes('TrekMapJourneyPlanner?.openFor(t,d)'),'load day data on open');
assert.ok(core.includes('days:window.TrekMapJourneyPlanner?.getDays?.()||[]'),'submit with existing plan save');
assert.ok(backend.includes('days: list[dict] | None = None'),'optional backwards-compatible API');
assert.ok(backend.includes('if data.days is None:'),'legacy clients preserve existing day data');
assert.ok(backend.includes('"kind":"day"')&&backend.includes('day_rows'),'private JSONB saves');
assert.ok(!backend.includes('DROP TABLE trek_plans'),'never drop user plans');
assert.ok(js[3].includes('function paceMatches(t)'), 'pace filter');
assert.ok(core.includes('TrekMapHikerDetails?.paceMatches(t)')&&unified.includes('TrekMapHikerDetails?.paceMatches(t)'),'catalog and map parity');
assert.ok(core.includes('TrekMapHikerDetails?.augment(t)'),'detail source');
assert.ok(js[3].includes('function svgRoute(points)'),'route shape based on actual geometry');
assert.ok(!/fetch\s*\(/.test(js[3]),'discovery adds no paid/external API calls');
assert.ok(js[4].includes('localStorage.setItem')&&js[4].includes('showModal()'),'stage notes interactive and persistent on browser');
assert.ok(workspace.includes('getPlan:function(){return active?plan:null;}'),'stage editor can access current route');
assert.ok(workspace.includes('window.TrekMapStageEdit?.renderNotes(p,panel)'),'saved stage notes rendered');
assert.ok(site.includes('window.TrekMapStageEdit?.open?.(Number(day))'),'day adjustment uses editor instead of regeneration');
assert.ok(js[4].includes('tracé GPS restent inchangés'),'do not mislead users about the route');
assert.ok(all[2].includes("apply_hiker_discovery.py"),'build chain discovery');
assert.ok(all[3].includes("apply_trekbrain_stage_notes.py"),'build chain notes');

// Execute the daily-pace calculation against anonymous data.
const a=js[3].indexOf(' function paceValue(t){');
const b=js[3].indexOf(' var host=',a);
assert.ok(a>=0&&b>a);
const p=vm.runInNewContext(js[3].slice(a,b)+';paceValue');
assert.equal(p({distance:60,duration_days:3}),20);
assert.equal(p({distance:7,duration_days:0.5}),null);
assert.equal(p({distance:null,duration_days:2}),null);
assert.equal(p({distance:0,duration_days:3}),null);
assert.equal(p({distance:20,duration_days:0}),null);

// Route rendering has a bounded point count; malformed coords must not be projected.
const c=js[3].indexOf(' function safeCoords(t){');
const d=js[3].indexOf(' function augment(t){',c);
assert.ok(c>=0&&d>c);
const route=vm.runInNewContext(js[3].slice(c,d)+';({safeCoords,svgRoute})');
assert.equal(route.safeCoords({coords:[[45,2],[95,2]]}).length,1);
assert.ok(route.svgRoute([[45,2],[45.2,2.3]]).includes('<polyline'));
assert.ok(!route.svgRoute([]));
const built=fs.readFileSync('frontend/index.html','utf8');
if(built.includes('TM_HIKER_DISCOVERY_START')){
 for(const mark of ['TM_HIKER_DISCOVERY_START','TM_STAGE_NOTES_START']){
  assert.equal(built.split(mark).length-1,1,mark+' not duplicated');
 }
}
console.log('HIKER FINISH PASS: checklist deadlock, private day plans, km/day search, truthful previews, stage notes');
