/* User-facing excessive-distance warnings must survive summary compression.
   No HTTP calls: execute isolated real front-end formatter functions. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const ai=fs.readFileSync('scripts/apply_ai_planner.py','utf8');
const map=fs.readFileSync('scripts/apply_trekbrain_map_workspace.py','utf8');
const aiScript=ai.match(/<script id="trekmap-ai-js">([\s\S]*?)<\/script>/)?.[1];
const mapScript=map.match(/<script id="trekbrain-route-workspace-js">([\s\S]*?)<\/script>/)?.[1];
assert.ok(aiScript&&mapScript,'both TrekBrain formatters must remain installed');
new vm.Script(aiScript);
new vm.Script(mapScript);
const aiStart=aiScript.indexOf('  function essentialChecks(p){');
const aiEnd=aiScript.indexOf('\n  function isViewpoint',aiStart);
assert.ok(aiStart>=0&&aiEnd>aiStart,'need existing AI summary formatter');
const render=vm.runInNewContext(aiScript.slice(aiStart,aiEnd)+
  '\nessentialChecks;',{'esc':String});
const mapStart=mapScript.indexOf('  function collectWarnings(p){');
const mapEnd=mapScript.indexOf('\n  function statusInfo(p){',mapStart);
assert.ok(mapStart>=0&&mapEnd>mapStart,'need actual map-warning formatter');
const mapWarnings=vm.runInNewContext(mapScript.slice(mapStart,mapEnd)+
  '\ncollectWarnings;',{
    count:value=>Math.max(0,Number(value)||0),
    unique:items=>Array.from(new Set(items)),
});
const plan={
  route_preview:{coords:[[48.36,-3.75],[48.42,-3.81]],fallback:false},
  planner:{distance_contract:{
    daily_target_km:16,actual_average_km:20.6,longest_day_km:20.6,
    target_exceeded:true,
    days_exceeding:[
      {day:1,distance_km:20.6,extra_pct:29,exceeds_limit:true},
      {day:2,distance_km:20.6,extra_pct:29,exceeds_limit:true}
    ]
  }},
  map_resources:{coverage:{water:'providers_unavailable',food:'providers_unavailable',
    days_without_water:[1,2],days_without_food:[1,2]}},
  logistics:{nights_missing:1,nights_transfer_required:0},
  stages:[
    {day:1,distance_km:20.6,safety_notes:'Distance au-dessus de l’objectif'},
    {day:2,distance_km:20.6,safety_notes:'Distance au-dessus de l’objectif'},
  ],
  confidence:{limitations:['Conditions météo non vérifiées.']}
};
const content=render(plan);
assert.ok(content.includes('Distance supérieure à votre objectif de 16 km/jour'),'requested target visible');
assert.ok(content.includes('J1 : 20.6 km')&&content.includes('J2 : 20.6 km'));
assert.ok(content.includes('Eau non vérifiée'));
assert.ok(content.includes('Ravitaillement non vérifié'));
assert.ok(content.includes('nuitée(s) sans hébergement'));
assert.ok(content.indexOf('Distance supérieure')<content.indexOf('Eau non vérifiée'),
  'distance safety must not be dropped if warning count is limited');
assert.ok(content.includes('role="note"'));
const mapText=Array.from(mapWarnings(plan));
assert.ok(mapText[0].includes('16 km/jour')&&mapText[0].includes('20.6 km'),
  'the map sidebar must also prioritize oversized distance');
assert.ok(mapText.some(x=>x.includes('Eau non vérifiée')));
assert.ok(mapText.some(x=>x.includes('Ravitaillement non vérifié')));
assert.ok(mapText.some(x=>x.includes('nuitée(s)')));
const valid={...plan,planner:{distance_contract:{target_exceeded:false,days_exceeding:[]}}};
assert.ok(!render(valid).includes('Distance supérieure'));
assert.ok(!Array.from(mapWarnings(valid)).some(x=>x.includes('Distance supérieure')));
assert.ok(!/fetch\s*\(|XMLHttpRequest|WebSocket/.test(aiScript.slice(aiStart,aiEnd)));
assert.ok(!/fetch\s*\(|XMLHttpRequest|WebSocket/.test(mapScript.slice(mapStart,mapEnd)));
console.log('TrekBrain short answer and map: real target mismatch prioritized; no fabricated routes or network calls: PASS');
