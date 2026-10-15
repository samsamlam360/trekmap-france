/* Protect public open-license imports from being shown as flat hikes by mistake. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html=fs.readFileSync('frontend/index.html','utf8');
const unified=fs.readFileSync('scripts/apply_unified_experience.py','utf8');
const helper=html.match(/function trekElevationKnown\(t\)[^\n]+\nfunction trekElevationLabel\(t\)[^\n]+/);
assert.ok(helper,'Public map needs truthful ascent label helpers');
const context=vm.createContext({});
vm.runInContext(helper[0],context);
const noAscent={elevation:0,description:'Dénivelé non renseigné (0 ne signifie pas terrain plat).'};
assert.equal(vm.runInContext('trekElevationLabel',context)(noAscent),'Non renseigné');
assert.equal(vm.runInContext('trekElevationLabel',context)({elevation:230,description:''}),'230 m');
assert.equal(vm.runInContext('trekElevationLabel',context)({elevation:0,description:''}),'0 m');
assert.ok(html.includes('!trekElevationKnown(t)||Math.abs(Number(t.elevation||0)-elev)'),
  'Elevated trail filters must exclude records with unknown ascent');
assert.ok(html.includes('Number(!trekElevationKnown(a.t))-Number(!trekElevationKnown(b.t))'),
  'Numeric elevation sort must move unknown values to the end');
assert.ok(unified.includes("function elevationKnown(t)")&&unified.includes('Non renseigné'));
assert.ok(unified.includes('!elevationKnown(t)||Math.abs(Number(t.elevation||0)-elev)'));
assert.ok(unified.includes('Number(!elevationKnown(a))-Number(!elevationKnown(b))'));
const reference=String.fromCharCode(36)+'{elevationLabel(t)}';
assert.ok(unified.includes('↗ '+reference),'Carousel should show honest ascent label');
assert.ok(unified.includes(reference+'</strong>'),'Selected-trek details should show honest ascent label');
console.log('ELEVATION UNKNOWN CONTRACT PASS: cards, filters and sorted panels');
