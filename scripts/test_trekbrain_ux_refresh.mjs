/* TrekBrain v9 UX: dependency-free design and integration regressions.
   All checks are static or compile-only: no network, routing or Neon queries. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('./apply_trekbrain_ux_refresh.py',import.meta.url),'utf8');
const css=source.match(/<style id="trekbrain-evidence-ux-css">([\s\S]*?)<\/style>/)?.[1];
const script=source.match(/<script id="trekbrain-evidence-ux-js">([\s\S]*?)<\/script>/)?.[1];
assert.ok(css && script, 'the complete UX layer needs a scoped style and JS');
new vm.Script(script,{filename:'trekbrain-evidence-ux.js'});
assert.ok(source.includes('TREKMAP_TREKBRAIN_UX_2026_START'));
assert.ok(source.includes('TREKMAP_TREKBRAIN_UX_2026_END'));
assert.ok(source.includes('TREKMAP_TREKBRAIN_SCROLL_UI_START'));
assert.ok(css.includes('#tm-ai-overlay .tm-ai-field label'));
assert.ok(css.includes('font-size:16px'), 'avoid iOS auto-zoom and tiny form fonts');
assert.ok(css.includes('min-height:48px'), 'accessible touch targets');
assert.ok(css.includes('focus-visible'), 'visible keyboard focus');
assert.ok(css.includes('prefers-reduced-motion'), 'respect reduced-motion setting');
assert.ok(css.includes('@media(max-width:820px)'), 'mobile rules');
assert.ok(css.includes('.tm-ai-stage'), 'daily walking stages remain readable');
assert.ok(css.includes('.tm-v9-panel'), 'TrekBrain evidence panel remains readable');
assert.ok(css.includes('tm-ux-advanced'), 'secondary criteria should be available on demand');
assert.ok(script.includes('advancedFields.appendChild(difficulty.closest(".tm-ai-field"))'));
assert.ok(script.includes('advancedFields.appendChild(routeType.closest(".tm-ai-field"))'));
assert.ok(script.includes('body.appendChild(checks)'), 'all four resource checkboxes retained');
assert.ok(script.includes('prompt.dispatchEvent(new Event("input"'), 'examples must update the actual form');
assert.ok(script.includes('if(region)region.value=choice.region'));
assert.ok(script.includes('if(days)days.value=choice.days'));
assert.ok(script.includes('if(km)km.value=choice.km'));
assert.ok(script.includes('getClientRects().length'), 'focus only visible elements');
assert.ok(script.includes('lastTrigger.focus()'), 'restore focus after closing');
assert.ok(css.includes('.tm-ux-selected'), 'collapsed options should show their active settings');
assert.ok(script.includes('selected.id="tm-ux-settings-summary"'), 'active criteria overview needs a stable ID');
assert.ok(script.includes('requirementIds.filter('), 'criteria are based on real checkboxes');
assert.ok(script.includes('checks.querySelectorAll("input[type=checkbox]")'), 'checkbox changes update the overview');
assert.ok(script.includes('input.addEventListener("change",updateSummary)'), 'changed criteria must refresh the overview');
assert.ok(script.includes('updateSummary();'), 'initial defaults must be shown');
assert.ok(script.includes('visible.indexOf(document.activeElement)<0'), 'recover escaped keyboard focus');
assert.ok(script.includes('document.addEventListener("keydown",function(event)'), 'trap Tab from the document when the modal is open');
assert.ok(script.includes('  },true);'), 'keyboard trap should run in capture phase');
assert.ok(!script.includes('summary.setAttribute("aria-label"'), 'native summary and selected values must be announced');

assert.ok(script.includes('originalBack.click()'), 'mobile results should allow one-tap editing');
assert.ok(script.includes('originalClose.click()'), 'mobile results must offer a visible close action');
assert.ok(css.includes('tm-ux-mobile-result-nav'), 'mobile result navigation must be visibly styled');
assert.ok(!/\/ai\/plan|\/treks\/draw|fetch\(/.test(script), 'presentation layer must never issue planning/network requests');
for(const id of [
  'tm-ai-prompt','tm-ai-region','tm-ai-days','tm-ai-km','tm-ai-difficulty',
  'tm-ai-route-type','tm-ai-generate',
])assert.ok(script.includes(id),id+' must retain existing controls');
// Close and back buttons are owned by the existing modal renderer, not the
// presentation-only enhancement. Their IDs must survive the built HTML.


const render=fs.readFileSync('render.yaml','utf8');
assert.ok(render.includes('python scripts/apply_trekbrain_scroll_ui.py && python scripts/apply_trekbrain_ux_refresh.py && python scripts/render_preflight.py'),
  'production must install UX after scrolling layer');
for(const workflow of [
  '.github/workflows/render-strict-preflight.yml',
  '.github/workflows/trekbrain-scroll-ui.yml',
  '.github/workflows/trekbrain-v9.yml',
]) {
  const yaml=fs.readFileSync(workflow,'utf8');
  assert.ok(yaml.includes('python scripts/apply_trekbrain_ux_refresh.py'),workflow);
  assert.ok(yaml.includes('node scripts/test_trekbrain_ux_refresh.mjs'),workflow+' should run the UX regression');
}
const html=fs.readFileSync('frontend/index.html','utf8');
const count=(text)=>(html.match(new RegExp(text,'g'))||[]).length;
if(count('TREKMAP_TREKBRAIN_UX_2026_START')) {
  assert.equal(count('TREKMAP_TREKBRAIN_UX_2026_START'),1);
  assert.equal(count('trekbrain-evidence-ux-css'),1);
  assert.equal(count('trekbrain-evidence-ux-js'),1);
  for(const id of [
    'tm-ai-prompt','tm-ai-region','tm-ai-days','tm-ai-km','tm-ai-difficulty',
    'tm-ai-route-type','tm-ai-transit','tm-ai-water','tm-ai-sleep','tm-ai-food',
    'tm-ai-generate','tm-ai-result','tm-ai-content',
  ])assert.equal(count('id="'+id+'"'),1,'form or output control lost: '+id);
}
console.log('TrekBrain UX: source preserved, progressive settings, mobile touch, keyboard, no routing changes: PASS');
