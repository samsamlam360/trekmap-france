/* Offline contract for the optional photo and mobile map experience. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const photos=fs.readFileSync('scripts/apply_trekbrain_scenic_photos.py','utf8');
const map=fs.readFileSync('scripts/apply_trekbrain_map_mobile.py','utf8');
const route=fs.readFileSync('scripts/apply_route_day_clarity.py','utf8');
const resources=fs.readFileSync('scripts/apply_trekbrain_v9_map_ui.py','utf8');
const planner=fs.readFileSync('scripts/apply_ai_planner.py','utf8');
const photoJS=photos.match(/<script id="trekmap-scenic-photos-js">([\s\S]*?)<\/script>/)?.[1];
const focusJS=map.match(/<script id="trekmap-mobile-map-focus-js">([\s\S]*?)<\/script>/)?.[1];
assert.ok(photoJS&&focusJS,'both UI scripts must be installed');
new vm.Script(photoJS);
new vm.Script(focusJS);
assert.ok(photoJS.includes('iiprop=url%7Cextmetadata%7Cmime'),'licence and thumb metadata');
assert.ok(photoJS.includes('LicenseShortName'),'licence must be read');
assert.ok(photoJS.includes('safeThumb'),'only Wikimedia image hosts allowed');
assert.ok(photoJS.includes("lookups>=MAX_LOOKUPS"),'provider request budget');
assert.ok(photoJS.includes('IntersectionObserver'),'lazy image metadata lookup');
assert.ok(photoJS.includes('Photo : '),'visible author credit');
assert.ok(photoJS.includes('Crédits Wikimedia Commons'),'Commons attribution link');
assert.ok(photoJS.includes('if(!data)return'),'do not pretend unrelated image matches');
assert.ok(resources.includes("kind:'viewpoint'"),'scenic map marker exists');
assert.ok(resources.includes('data-commons-file'),'map popup supports exact photo refs');
assert.ok(planner.includes('scenicCards(p)'),'real scenic cards present in itinerary');
assert.ok(planner.includes('data-view-lat'),'cards locate the exact point on the map');
assert.ok(route.includes('tm-route-day-details'),'stage legend is collapsible');
assert.ok(resources.includes('tm-v91-resource-details'),'resource legend is collapsible');
assert.ok(map.includes('env(safe-area-inset-bottom'),'safe-area map margin');
assert.ok(map.includes('body:has(.tm-route-day-legend) #tm-unified-drawer'),'unrelated bottom drawer hidden');
assert.ok(map.includes('map.on("movestart"'),'auto-collapse when moving map');
assert.ok(!/openrouteservice|overpass|nominatim/i.test(photoJS+focusJS),'UI scripts do not invoke routing services');
assert.ok(!photoJS.includes('localStorage'),'privacy/cache stays in-memory');

if(fs.existsSync('frontend/index.html')){
  const html=fs.readFileSync('frontend/index.html','utf8');
  if(html.includes('TREKMAP_SCENIC_PHOTOS_START')){
    for(const marker of ['TREKMAP_SCENIC_PHOTOS_START','TREKMAP_MOBILE_MAP_FOCUS_START']){
      assert.equal(html.split(marker).length-1,1,marker+' duplicated');
    }
    for(const id of ['trekmap-scenic-photos-js','trekmap-mobile-map-focus-js']){
      assert.equal(html.split('id="'+id+'"').length-1,1,id+' duplicated');
    }
  }
}

// Exercise the real photo loader with a controlled MediaWiki response. This
// is deliberately OFFLINE and proves exact-source licensing/caching behavior.
const fakeWindow={};
const network=[];
const fakeDocument={
  getElementById(){return null},
  createTextNode(value){return {textContent:String(value)}},
  createElement(tag){
    if(tag==='img')return {tagName:'IMG',addEventListener(){}};
    return {tagName:tag.toUpperCase(),children:[],appendChild(child){this.children.push(child);}};
  },
};
const fakeFetch=async(url,options)=>{
  network.push(String(url));
  assert.equal(options.credentials,'omit');
  assert.ok(String(url).startsWith('https://commons.wikimedia.org/w/api.php'));
  return {
    ok:true,
    async json(){
      return {
        query:{
          pages:{
            1:{
              imageinfo:[{
                mime:'image/jpeg',
                thumburl:'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Example.jpg/620px-Example.jpg',
                extmetadata:{
                  LicenseShortName:{value:'CC BY-SA 4.0'},
                  Artist:{value:'Photographe de la commune'}
                }
              }]
            }
          }
        }
      };
    }
  };
};
const context=vm.createContext({
  window:fakeWindow,document:fakeDocument,fetch:fakeFetch,
  setTimeout,clearTimeout,AbortController,URL,console,
});
vm.runInContext(photoJS,context);
assert.ok(typeof fakeWindow.TrekViewPhotos?.hydrate==='function');
function cardFor(file){
  const holder={
    image:null,credit:null,
    replaceChildren(img){this.image=img},
    insertAdjacentElement(_position,item){this.credit=item},
  };
  const card={
    isConnected:true,
    dataset:{commonsFile:file,wikidata:''},
    querySelector(selector){
      if(selector==='.tm-ux-photo-media')return holder;
      if(selector==='.tm-ux-photo-credit')return holder.credit;
      return null;
    },
  };
  return {card,holder,root:{querySelectorAll(){return [card]}}};
}
const photo=cardFor('Mont Aiguille.jpg');
fakeWindow.TrekViewPhotos.hydrate(photo.root);
await new Promise(resolve=>setTimeout(resolve,10));
assert.equal(network.length,1,'only one Commons request for exact OSM file');
assert.equal(photo.holder.image?.loading,'lazy');
assert.equal(photo.holder.image?.src?.startsWith('https://upload.wikimedia.org/'),true);
assert.equal(photo.holder.credit?.className,'tm-ux-photo-credit');
assert.ok(photo.holder.credit.children.some(x=>x.textContent?.includes('CC BY-SA 4.0')));
assert.ok(photo.holder.credit.children.some(x=>x.textContent?.includes('Photographe de la commune')));
assert.ok(photo.holder.credit.children.some(x=>x.href?.startsWith('https://commons.wikimedia.org/wiki/File:')));
fakeWindow.TrekViewPhotos.hydrate(photo.root);
await new Promise(resolve=>setTimeout(resolve,5));
assert.equal(network.length,1,'image already loaded should not be re-fetched');
const noEvidence=cardFor('');
fakeWindow.TrekViewPhotos.hydrate(noEvidence.root);
await new Promise(resolve=>setTimeout(resolve,5));
assert.equal(network.length,1,'no reference must never trigger a guessed photo');
assert.equal(noEvidence.holder.image,null);
console.log('Commons photo: trusted thumbnail, author+license, in-memory cache and no false images PASS');

console.log('Mobile map and source-matched licensed scenic photos: static/offline UI checks PASS');
