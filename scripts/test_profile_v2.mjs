import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const ui=fs.readFileSync('scripts/apply_profile_v2.py','utf8');
const api=fs.readFileSync('backend/profile_v2.py','utf8');
const entry=fs.readFileSync('backend/app_v5.py','utf8');
const site=fs.readFileSync('scripts/apply_sitewide_ux.py','utf8');
const html=fs.readFileSync('frontend/index.html','utf8');

assert.ok(site.includes('run_path(str(Path(__file__).with_name("apply_profile_v2.py")))'),
 'profile is built into main page without modifying existing core HTML');
assert.ok(entry.includes('app.router.routes.extend(profile_v2.router.routes)'),
 'profile backend registered in production');
const js=ui.match(/<script id="tm-profile-v2-script">([\s\S]*?)<\/script>/)?.[1];
const css=ui.match(/<style id="tm-profile-v2-style">([\s\S]*?)<\/style>/)?.[1];
assert.ok(js && css,'both profile JS and CSS exist');
new vm.Script(js,{filename:'trekmap-profile-v2.js'});
assert.ok(css.includes('@media(max-width:780px)')&&css.includes('focus-visible'),
 'mobile responsive and keyboard accessibility');
for(const section of ['Tableau de bord','Mes aventures','Carnet','Collections','Préférences']){
 assert.ok(ui.includes(section),'missing '+section);
}
for(const feature of [
 "openProfile=open", "tm-p-journey-form", "tm-p-settings-form",
 "tm-p-collection-create", "tm-p-plan-editor", "tm-ai-profile-defaults",
 "window.openDetail", "data-p-checklist-save", "data-p-share", "publicOpen"
]){
 assert.ok(ui.includes(feature),'missing profile feature '+feature);
}
for(const path of [
 '/v2','/v2/journeys/{trek_id}','/v2/collections','/v2/collections/{collection_id}',
 '/v2/collections/{collection_id}/treks/{trek_id}','/public/{username}'
])assert.ok(api.includes(path),'missing API endpoint '+path);
assert.ok(api.includes('Depends(core.current_user)'),'private endpoints need authentication');
assert.ok(api.includes('t.is_public OR t.owner_id=:u')||api.includes('is_public OR owner_id=:uid'),
 'private trek access must be validated');
assert.ok(api.includes('AND p.public_profile=TRUE'),'public profile explicit opt-in');
assert.ok(api.includes('t.is_public=TRUE'),'public profile only shows public treks');
assert.ok(api.includes('photo_urls') && api.includes('u.scheme != "https"'),'photo links validated');
assert.ok(api.includes('j["status"] == "completed"'),
 'only completed journeys count toward real walked stats');
assert.ok(api.includes('CREATE TABLE IF NOT EXISTS')&&
 !api.includes('DROP TABLE')&&!api.includes('TRUNCATE')&&!api.includes('ALTER TABLE'),
 'profile schema must be purely additive');
assert.ok(!/document\.querySelectorAll\(['"]\.tm-trek-tile/.test(js),
 'profile must not mutate existing map route cards');
assert.ok(js.includes("revealPanel('tm-p-journey-card')"),
 'the À découvrir button must reveal and focus its editor');
assert.ok(js.includes("revealPanel('tm-p-collection-content')"),
 'opening a collection must bring its contents into view');
assert.ok(js.includes('data-p-collection-manage') && js.includes('data-p-open-trek'),
 'collection members must have both prepare and open-detail actions');
assert.ok(js.includes("request('/treks/'+id,'GET')"),
 'collection-only public treks must be loaded into the map catalogue');
assert.ok(js.includes('const accountTreks=function()'),
 'profile helper cannot shadow explorer allTreks array');
assert.ok(css.includes('tm-p-collection-entry') &&
 css.includes('#tm-p-collection-content'),'collection must have interactive visual selection');
assert.ok(js.includes('window.openProfile=open'),'existing account entrypoint retained');
assert.ok(js.includes('typeof closeModal'),'legacy modal remains available');
assert.ok(!/fetch\s*\(\s*['"]https?:\/\//.test(js),'no third-party service added');
if(html.includes('TREKMAP_PROFILE_V2_START')) {
 assert.equal(html.split('TREKMAP_PROFILE_V2_START').length-1,1,'idempotent install');
}
console.log('PROFILE V2 CONTRACT PASS: private by default, full profile, TrekBrain and legacy compatibility');
