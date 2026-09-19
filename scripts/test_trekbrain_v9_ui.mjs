// Dependency-free DOM contract regression: the panel must not redraw itself.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const source = fs.readFileSync(new URL('./apply_trekbrain_v9_ui.py', import.meta.url), 'utf8');
const js = source.match(/<script id="trekmap-trekbrain-v9-js">([\s\S]*?)<\/script>/)[1];
let observer, panel, appends = 0;
const timers = [];
const controls = new Map();
function control(id) {
  if (!controls.has(id)) controls.set(id, {value: '', textContent: '', disabled: false,
    addEventListener(type, handler) { this[type] = handler; }, classList: {add() {}}});
  return controls.get(id);
}
const content = {
  querySelector() { return panel; },
  appendChild(node) { panel = node; appends++; observer(); },
};
let calls = 0;
const current = {decision_summary: {quality: 0, understood: '<img src=x onerror=alert(1)>', verified: [], uncertain: [], important: []},
  trekbrain: {version: 'trekbrain-v9'}, stages: [{distance_km: 12, water_notes: 'Fontaine'}]};
const window = {fetch: async (input) => {
  calls++;
  if (String(input).includes('/ai/ask')) return {ok: true, json: async () => ({answer: '<b>texte non interprété</b>', context: 'Données du parcours'})};
  return {ok: true, clone: () => ({json: async () => current})};
}};
const document = {
  getElementById(id) { if (id === 'tm-ai-content') return content; if (id === 'tm-ai-launch') return null; return control(id); },
  querySelector() { return null; }, querySelectorAll() { return []; },
  createElement() { return {innerHTML: '', remove() { panel = null; observer(); }}; },
};
const context = vm.createContext({window, document, fetch: (...args) => window.fetch(...args),
  MutationObserver: class { constructor(fn) { observer = fn; } observe() {} },
  setTimeout(fn) { timers.push(fn); return timers.length; }, clearTimeout() {}, AbortController,
});
vm.runInContext(js, context);
await window.fetch('/ai/plan');
await Promise.resolve();
for (let i = 0; timers.length && i < 12; i++) timers.shift()();
assert.equal(timers.length, 0, 'panel observer must settle');
assert.equal(appends, 1, 'only one panel is appended');
assert.ok(panel.innerHTML.includes('&lt;img'), 'plan text must be escaped');
assert.ok(panel.innerHTML.includes('<b>0</b>'), 'zero score must be displayed');
control('tm-v9-question').value = 'Eau au jour 1 ?';
await control('tm-v9-ask').submit({preventDefault() {}});
assert.ok(control('tm-v9-answer').textContent.includes('<b>texte non interprété</b>'));
assert.equal(control('tm-v9-ask-send').disabled, false);
assert.equal(calls, 2);
console.log('V9 UI: stable observer, escaped data, zero score, grounded dialogue OK');

if (process.argv[2]) {
  const html = fs.readFileSync(process.argv[2], 'utf8');
  for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) {
    if (match[1].trim()) new vm.Script(match[1]);
  }
  const inherited = html.match(/\/\/ TREKBRAIN_V9_RESEARCH_GUARD([\s\S]*?)\n  const observer=/);
  assert.ok(inherited, 'V9 must also guard inherited research panel');
  let researchPanel = null, researchAppends = 0;
  const researchContent = {querySelector() { return researchPanel; }, appendChild(node) { researchPanel = node; researchAppends++; }};
  const researchContext = vm.createContext({$: () => researchContent,
    lastAgentPlan: {agent: {brain: 'trekbrain-local'}, web_sources: []},
    esc: String, safeUrl: String,
    document: {createElement() { return {remove() { researchPanel = null; }}; }},
  });
  vm.runInContext(inherited[1] + '\nrenderResearch();renderResearch();renderResearch();', researchContext);
  assert.equal(researchAppends, 1, 'inherited observer must settle too');
  assert.equal((html.match(/TREKMAP_TREKBRAIN_V9_UI_START/g) || []).length, 1);
  console.log('Built UI: all scripts parse; inherited research observer stable');
}
