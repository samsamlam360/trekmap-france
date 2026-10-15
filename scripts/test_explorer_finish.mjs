/* Regression contract: Explorer finishing layer must not replace TrekBrain, filter or map APIs. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync('scripts/apply_explorer_finish.py','utf8');
const inline=fs.readFileSync('scripts/apply_inline_filters.py','utf8');
const css=source.match(/<style id="trekmap-explorer-finish-css">([\s\S]*?)<\/style>/)?.[1];
const js=source.match(/<script id="trekmap-explorer-finish-js">([\s\S]*?)<\/script>/)?.[1];
assert.ok(css&&js,'Explorer finishing CSS and JS must be installed');
new vm.Script(js,{filename:'trekmap-explorer-finish.js'});
assert.ok(inline.includes('run_path(str(Path(__file__).with_name("apply_explorer_finish.py")))'),
          'new visual layer must run last, through the existing Render build chain');
for(const key of ['#tm-inline-filters','#tm-desktop-info','.tm-info-selected','.tm-info-overview',
                  '#tm-drawer-track','.tm-mini-route','@media(min-width:1240px)',
                  '@media(max-width:820px)'])assert.ok(css.includes(key),'missing '+key);
for(const key of ['tm-inline-difficulty','Difficulté','originalDraw.apply',
                  'originalRefresh.apply','trekmap:detail-opened',
                  'interactive:false','setStyle','pointerover','pointerout',
                  'tm-brain-route-mode','TrekMapExplorerFocus']){
  assert.ok(js.includes(key),'missing behavior '+key);
}
assert.ok(!/\bfetch\s*\(|XMLHttpRequest|\/ai\/plan|DATABASE_URL|localStorage/.test(js),
          'visual polish must not make external requests, modify persistence or AI planning');
assert.ok(!/window\.openDetail\s*=|window\.TrekMapOpenTrek\s*=/.test(js),
          'original opening and route selection must remain authoritative');
assert.ok(css.includes('#tm-desktop-info:not(.has-selection) .tm-info-selected') &&
          css.includes('#tm-desktop-info.has-selection .tm-info-overview'),
          'right rail must be contextual');
console.log('EXPLORER FINISH CONTRACT PASS: toolbar, cards, selected-only details, map focus');
