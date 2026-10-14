/* Sitewide UI contract: no routing, account, persistence or export change. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const installer=fs.readFileSync('scripts/apply_sitewide_ux.py','utf8');
const mapInstaller=fs.readFileSync('scripts/apply_trekbrain_map_workspace.py','utf8');
const html=fs.readFileSync('frontend/index.html','utf8');
const css=installer.match(/<style id="trekmap-sitewide-ux-css">([\s\S]*?)<\/style>/)?.[1];
const js=installer.match(/<script id="trekmap-sitewide-ux-js">([\s\S]*?)<\/script>/)?.[1];
assert.ok(css&&js,'sitewide style and DOM enhancement must both be present');
new vm.Script(js,{filename:'trekmap-sitewide-ux.js'});
assert.ok(mapInstaller.includes('run_path(str(Path(__file__).with_name("apply_sitewide_ux.py")))'),
  'installer must run last in existing Render and CI build chain');
assert.ok(installer.includes('TREKMAP_BRAIN_ROUTE_WORKSPACE_START'),
  'do not apply sitewide CSS before map workspace is built');
assert.ok(installer.includes('html.count("</body>") != 1'),
  'fail rather than corrupt unexpected HTML');
assert.ok(css.includes('@media(max-width:820px)'),'mobile layout must be intentional');
assert.ok(css.includes('@media(max-width:380px)'),'320px phone layout must be considered');
assert.ok(css.includes('prefers-reduced-motion:reduce'),'respect OS motion preferences');
assert.ok(css.includes('focus-visible'),'keyboard focus must remain visible');
assert.ok(css.includes('min-height:44px'),'important touch targets have a real size');
assert.ok(css.includes('#tm-home') && css.includes('#tm-unified-topbar') &&
          css.includes('#tm-unified-drawer') && css.includes('#tm-ai-overlay') &&
          css.includes('#tm-brain-route-panel') && css.includes('#tm-mobile-nav'),
          'cover every major site section, not only TrekBrain');
assert.ok(js.includes('aria-expanded') && js.includes('aria-current') &&
          js.includes('aria-live'),'existing controls receive meaningful semantics');
assert.ok(!/\bfetch\s*\(|XMLHttpRequest|localStorage|\/ai\/plan/.test(js),
  'UX enhancement cannot use providers, change data or create extra requests');
assert.ok(!/\.remove\s*\(|\.replaceWith\s*\(|\.outerHTML\s*=/.test(js),
  'UX enhancement may not remove or replace existing controls');
const cssWithoutResponsiveLabels=css.replace(
  /#tm-top-actions button \.label \{ display:none!important \}/g,''
);
assert.ok(!/display\s*:\s*none\s*!important/.test(cssWithoutResponsiveLabels),
  'no buttons, panels or original functions may be hidden by this layer');
if(html.includes('TREKMAP_SITEWIDE_UX_START')){
  for(const token of ['TREKMAP_SITEWIDE_UX_START','id="trekmap-sitewide-ux-css"',
                     'id="trekmap-sitewide-ux-js"']){
    assert.equal(html.split(token).length-1,1,'idempotent installation: '+token);
  }
  for(const id of [
    'tm-unified-topbar','tm-unified-drawer','tm-mobile-nav',
    'tm-ai-overlay','tm-ai-save','tm-brain-route-panel','tm-main-search'
  ]){
    // Runtime-created controls are represented by JS IDs, not literal HTML tags.
    assert.ok(html.includes(id),'retained application control: '+id);
  }
}
console.log('SITEWIDE UX CONTRACT PASS: CSS/JS syntax, responsiveness, features and installer order');
