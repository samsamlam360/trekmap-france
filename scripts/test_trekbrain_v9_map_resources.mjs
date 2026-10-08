/* Live v9 map script executed against a tiny Leaflet/DOM harness.
   Verify that returned, source-linked food/lodging are not silently filtered
   out of map markers, legend, and their per-day popups. Network-free. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const path = process.argv[2] || 'frontend/index.html';
const html = fs.readFileSync(path, 'utf8');
const match = html.match(/<script id="trekmap-trekbrain-v91-map-js">([\s\S]*?)<\/script>/);
assert.ok(match, 'v9.1 map must be present after production UI build');

const markers = [];
const legends = [];
const map = {
  hasLayer: () => false,
  removeLayer: () => {},
  removeControl: () => {},
};
const L = {
  layerGroup: () => ({addTo() {return this;}}),
  divIcon: options => options,
  marker: (coords, options) => ({
    bindPopup(content) {
      markers.push({coords, options, popup: content});
      return this;
    },
    addTo() {return this;},
  }),
  control: () => ({
    onAdd: null,
    addTo() {
      if (typeof this.onAdd === 'function') this.onAdd();
      return this;
    },
  }),
  DomUtil: {create: () => {
    const node = {addEventListener() {}};
    Object.defineProperty(node, 'innerHTML', {set(value) {legends.push(value);}});
    return node;
  }},
  DomEvent: {disableClickPropagation() {}, disableScrollPropagation() {}},
};
const plan = {
  map_resources: {points: [
    {kind: 'food', name: 'Épicerie sourcée', lat: 45.01, lon: 5.01,
     route_day: 2, distance_to_route_km: 0.7,
     source_url: 'https://www.openstreetmap.org/node/123'},
    {kind: 'lodging', name: 'Gîte sourcé', lat: 45.02, lon: 5.02,
     route_day: 1, source_url: 'https://www.openstreetmap.org/node/456'},
    {kind: 'water', name: 'Source', lat: 45.03, lon: 5.03,
     route_day: 1, source_url: 'https://www.openstreetmap.org/node/789'},
    {kind: 'food', name: 'Coordonnées invalides', lat: 'wrong', lon: 5.01},
  ]},
};
const window = {
  fetch: async () => ({
    ok: true,
    clone: () => ({json: async () => plan}),
  }),
};
const notices = [];
const panel = {
  querySelector: () => null,
  appendChild: node => notices.push(node.innerHTML),
};
const document = {
  getElementById: id => id === 'tm-v9-panel' ? panel : null,
  createElement: () => ({}),
  addEventListener() {},
};
vm.runInNewContext(match[1], {
  window, document, map, L, URL,
  setTimeout: fn => fn(),
  MutationObserver: class {observe() {}},
});

await window.fetch('/ai/plan', {method: 'POST'});
await new Promise(resolve => setImmediate(resolve));

assert.equal(markers.length, 3, JSON.stringify(markers));
const kinds = markers.map(x => x.options.icon.className.split(' ').at(-1));
assert.deepEqual(kinds.sort(), ['food', 'lodging', 'water']);
assert.ok(markers.some(x => x.popup.includes('Épicerie sourcée') &&
  x.popup.includes('jour 2') && x.popup.includes('openstreetmap.org/node/123')));
assert.ok(markers.some(x => x.popup.includes('Gîte sourcé')));
assert.ok(legends.some(x => x.includes('Ravitaillement (1)') &&
  x.includes('Hébergements (1)') && x.includes('Eau (1)')),
  JSON.stringify(legends));

// A failed provider with no marker must still produce a visible warning.
plan.map_resources = {points: [], coverage: {food: 'providers_unavailable'}};
await window.fetch('/ai/plan', {method: 'POST'});
await new Promise(resolve => setImmediate(resolve));
assert.ok(notices.some(x => x.includes('Ravitaillement non confirmé') &&
  x.includes('cartographiques indisponibles')), JSON.stringify(notices));

// A real shop on one stage must not suppress warnings for unserved days.
plan.map_resources = {
  points: [{kind: 'food', name: 'Épicerie au départ', lat: 45.01,
    lon: 5.01, route_day: 1,
    source_url: 'https://www.openstreetmap.org/node/123'}],
  coverage: {food: 'partial', days_without_food: [2, 3]},
};
await window.fetch('/ai/plan', {method: 'POST'});
await new Promise(resolve => setImmediate(resolve));
assert.ok(notices.some(x => x.includes('Ravitaillement partiel') &&
  x.includes('2, 3')), JSON.stringify(notices));

// Water source gaps are independent of grocery availability.
plan.map_resources = {
  points: [{kind: 'water', name: 'Fontaine au départ', lat: 45.01,
    lon: 5.01, route_day: 1,
    source_url: 'https://www.openstreetmap.org/node/789'}],
  coverage: {food: 'not_requested', water: 'partial', days_without_water: [2]},
};
await window.fetch('/ai/plan', {method: 'POST'});
await new Promise(resolve => setImmediate(resolve));
assert.ok(notices.some(x => x.includes('Eau non vérifiée') &&
  x.includes('2')), JSON.stringify(notices));

plan.map_resources = {
  points: [],
  coverage: {food: 'not_requested', water: 'not_verified', days_without_water: [1]},
};
await window.fetch('/ai/plan', {method: 'POST'});
await new Promise(resolve => setImmediate(resolve));
assert.ok(notices.some(x => x.includes('Eau non confirmée') &&
  x.includes('Aucun point d’eau OSM confirmé')), JSON.stringify(notices));

console.log('TrekBrain v9 sourced food/water, source failures and per-stage coverage warnings: PASS');
