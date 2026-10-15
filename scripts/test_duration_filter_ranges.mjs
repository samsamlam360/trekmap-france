/* Contract for duration filter: mutually exclusive intervals on all TrekMap views. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html=fs.readFileSync('frontend/index.html','utf8');
const unified=fs.readFileSync('scripts/apply_unified_experience.py','utf8');
const select=html.match(/<select id="duration-filter">([\s\S]*?)<\/select>/)?.[1];
assert.ok(select, 'the existing duration filter must remain available');

const options=[...select.matchAll(/<option value="([^"]*)">([^<]+)<\/option>/g)];
const expected=['','1-2','3-5','6-7','8-14','15-30','31+'];
assert.deepEqual(options.map(x=>x[1]),expected,'duration bins must cover all lengths, with no upper ceiling');
assert.equal(options[0][2],'Toutes les durées');
assert.ok(!html.includes('Durée max'),'the old cumulative-limit label must disappear');
assert.ok(!select.includes('≤'),'intervals must replace the old less-than-or-equal choices');

const helper=html.match(/function matchesDurationRange\(durationDays,range\)\{[\s\S]*?\n\}/)?.[0];
assert.ok(helper,'duration range helper must exist in base application script');
const matches=vm.runInNewContext(helper+';matchesDurationRange');
assert.equal(matches(12,''),true,'all lengths is a genuine no-filter option');
assert.equal(matches(null,''),true,'all lengths keeps missing legacy values');
for(const duration of [null,undefined,0,0.5,NaN,Infinity,'pas connu']){
 for(const range of expected.slice(1)){
   assert.equal(matches(duration,range),false,'invalid/sub-day duration excluded from selected bin: '+String(duration));
 }
}

const cases=[
  [1,'1-2'],[1.25,'1-2'],[2,'1-2'],
  [2.25,'3-5'],[3,'3-5'],[5,'3-5'],
  [5.25,'6-7'],[6,'6-7'],[7,'6-7'],
  [7.25,'8-14'],[8,'8-14'],[14,'8-14'],
  [14.25,'15-30'],[15,'15-30'],[30,'15-30'],
  [30.25,'31+'],[31,'31+'],[120,'31+'],
];
for(const [duration,expectedBin] of cases){
 const hits=expected.slice(1).filter(range=>matches(duration,range));
 assert.deepEqual(hits,[expectedBin],'every valid duration belongs to exactly one interval: '+duration);
}
// Probe quarter-day granularity across the entire allowed 365-day storage window.
for(let duration=1;duration<=365;duration+=0.25){
 const count=expected.slice(1).filter(range=>matches(duration,range)).length;
 assert.equal(count,1,'no gap or overlap at '+duration+' days');
}

const expectedInvocation='matchesDurationRange(t.duration_days,dur)';
assert.ok(html.includes(expectedInvocation),'the original list and map must use the new interval helper');
assert.ok(unified.includes(expectedInvocation),'unified UI list and map must use the same interval helper');
assert.ok(html.includes("'duration-filter').value=''"),'reset must clear duration selection');
if(html.includes('id="trekmap-unified-js"')){
 assert.ok(html.split(expectedInvocation).length>=3,'the built application must include the new logic in both scripts');
}
console.log('DURATION INTERVALS PASS: 6 non-overlapping intervals, quarter-days, reset and both views');
