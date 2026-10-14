/* The desktop map stays a presentation layer over existing TrekMap functions. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const unified=fs.readFileSync('scripts/apply_unified_experience.py','utf8');
const site=fs.readFileSync('scripts/apply_sitewide_ux.py','utf8');
const layer=fs.readFileSync('scripts/apply_desktop_map_layout.py','utf8');
const brand=fs.readFileSync('frontend/brand-pin.svg','utf8');
const home=fs.readFileSync('frontend/logo-trekmap.svg','utf8');
const server=fs.readFileSync('backend/main_production.py','utf8');
assert.ok(unified.includes('<img src="/brand-pin.svg"'));
assert.ok(server.includes('@app.get("/brand-pin.svg"'));
assert.ok(brand.includes('<svg')&&home.includes('TrekMap')&&home.includes('France'));
for(const id of ['tm-desktop-info','tm-info-selected-content','tm-info-open-detail',
                 'tm-info-recenter','tm-drawer-nav','tm-drawer-track']){
  assert.ok(unified.includes(id),'missing '+id);
}
assert.ok(unified.includes('const previousScroll=track.scrollLeft'),'must preserve carousel scroll on selection');
assert.ok(unified.includes('track.scrollLeft=Math.min(previousScroll'),'must restore carousel position');
assert.ok(unified.includes('dragActive&&')||unified.includes('!dragActive||'),
          'pointer move must only count as drag while pressed');
assert.ok(unified.includes("e.pointerType!=='mouse'"),'native touch scroll must stay intact');
assert.ok(unified.includes('drawerDragging=false;'),'click state must recover after dragging');
assert.ok(unified.includes('data-scroll-dir="1"'),'next button is required');
assert.ok(unified.includes('openTrek(Number(card.dataset.id))'),'original detail opening stays connected');
assert.ok(unified.includes('window.openDetail?.(selectedId)'),'detail panel reuses real detail function');
assert.ok(unified.includes('window.openDetail(numeric)'),'do not lose original modal');
assert.ok(!/\bfetch\s*\(|\/treks\//.test(layer),'CSS layer cannot change API or routes');
assert.ok(site.includes('run_path(str(Path(__file__).with_name("apply_desktop_map_layout.py")))'),
          'desktop map installed as last style in Render/CI build');
assert.ok(layer.includes('@media(min-width:1240px)'),'large desktop map layout required');
assert.ok(layer.includes('@media(max-width:820px)'),'phone layout must be preserved');
assert.ok(layer.includes('#tm-main-search:focus-visible')&&layer.includes('outline:none'),
          'orange focus outline replaced without losing wrapper focus feedback');
const css=layer.match(/<style id="trekmap-desktop-map-2026">([\s\S]*?)<\/style>/)?.[1];
assert.ok(css);
assert.ok(!/\/\*\s*remove/.test(css));
for(const target of ['#tm-desktop-info','#tm-unified-drawer','.map-tools','#sidebar',
                     '#tm-brand','#tm-main-search-wrap'])assert.ok(css.includes(target));
console.log('DESKTOP MAP CONTRACT PASS: brand, trek selection, scroll, information panel, responsive');
