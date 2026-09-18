from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

# Idempotent final layout layer.
html = re.sub(
    r'\s*<!-- TREKMAP_FINAL_EXPLORER_START -->.*?<!-- TREKMAP_FINAL_EXPLORER_END -->\s*',
    '\n',
    html,
    flags=re.S,
)

block = r'''<!-- TREKMAP_FINAL_EXPLORER_START -->
<style id="trekmap-final-explorer-css">
/* The map now fills the whole explorer. The filter card floats over it. */
#app{position:relative!important;display:block!important}
#map{position:absolute!important;left:0!important;right:0!important;top:var(--tm-topbar-h,82px)!important;bottom:0!important;width:100%!important;height:auto!important;min-width:0!important}
.sidebar{position:absolute!important;z-index:2500!important;left:16px!important;top:calc(var(--tm-topbar-h,82px) + 16px)!important;width:390px!important;min-width:390px!important;height:auto!important;max-height:calc(100vh - var(--tm-topbar-h,82px) - 32px)!important;margin:0!important;padding:0!important;background:transparent!important;border:0!important;box-shadow:none!important;overflow:visible!important;display:block!important}
.sidebar.collapsed{transform:translateX(calc(-100% - 24px))!important;margin:0!important}

/* The old left search stays in the DOM as the search engine, but is no longer duplicated visually. */
#sidebar .search-wrap{display:none!important}
#sidebar .brand,#sidebar .account,#sidebar .tabs,#sidebar .list-head,#sidebar #trek-list{display:none!important}
#sidebar .filters{position:relative!important;display:block!important;flex:none!important;width:100%!important;max-height:min(540px,calc(100vh - var(--tm-topbar-h,82px) - 32px))!important;overflow:auto!important;margin:0!important;padding:59px 16px 17px!important;background:rgba(255,255,255,.97)!important;backdrop-filter:blur(18px)!important;border:1px solid #d8e6de!important;border-radius:22px!important;box-shadow:0 16px 44px rgba(10,50,33,.16)!important}
#sidebar .filters:before{content:"☷   Filtres de recherche"!important;position:absolute!important;left:19px!important;top:18px!important;font-size:15px!important;font-weight:900!important;color:#153d2d!important}
#sidebar .filters:after{content:""!important}
#sidebar .filter-row{gap:12px!important}
#sidebar .field label{font-size:10px!important;text-transform:uppercase!important;letter-spacing:.045em!important;color:#567064!important;font-weight:850!important;margin:10px 0 6px!important}
#sidebar .field select,#sidebar .field input{background:#fbfdfc!important;border:1px solid #d6e4dc!important;border-radius:12px!important;box-shadow:0 2px 8px rgba(14,55,37,.03)!important}
#sidebar .filter-actions{position:sticky!important;bottom:-17px!important;margin:17px -16px -17px!important;padding:12px 16px 15px!important;background:linear-gradient(180deg,rgba(255,255,255,.82),#fff 38%)!important;border-top:1px solid #e4ece7!important;z-index:4!important}

/* Better header logo, built as a proper lockup instead of stretching the old artwork. */
.tm-explorer-logo{overflow:visible!important;text-align:left!important}
.tm-brand-lockup{display:flex!important;align-items:center!important;gap:13px!important;min-width:0!important;color:#fff!important}
.tm-brand-symbol{width:104px!important;height:53px!important;flex:0 0 104px!important;display:block!important;filter:drop-shadow(0 3px 7px rgba(0,0,0,.12))}
.tm-brand-copy{display:flex!important;flex-direction:column!important;min-width:0!important;line-height:1!important}
.tm-brand-copy strong{font-size:28px!important;letter-spacing:-.045em!important;color:#fff!important;white-space:nowrap!important}
.tm-brand-copy strong em{font-style:normal!important;color:#38c67f!important}
.tm-brand-copy small{font-size:11px!important;letter-spacing:.015em!important;color:rgba(255,255,255,.72)!important;margin-top:6px!important;white-space:nowrap!important}

/* Main search inherits all search behaviour and gets autocomplete/clear controls. */
.tm-top-search{overflow:visible!important;isolation:isolate!important}
.tm-top-search:before{content:"";position:absolute;inset:0;border-radius:999px;background:#fff;z-index:-1}
#tm-top-search-input{padding-right:48px!important}
#tm-top-search-clear{position:absolute!important;right:9px!important;top:50%!important;transform:translateY(-50%)!important;width:34px!important;height:34px!important;border:0!important;border-radius:50%!important;background:transparent!important;color:#70847a!important;font-size:20px!important;line-height:1!important;display:none!important;align-items:center!important;justify-content:center!important;cursor:pointer!important}
#tm-top-search-clear.tm-visible{display:flex!important}#tm-top-search-clear:hover{background:#edf5f0!important;color:#176b45!important}
#tm-top-suggestions{position:absolute!important;left:9px!important;right:9px!important;top:58px!important;padding:7px!important;background:rgba(255,255,255,.98)!important;backdrop-filter:blur(18px)!important;border:1px solid #d7e5dd!important;border-radius:16px!important;box-shadow:0 18px 45px rgba(10,48,31,.20)!important;display:none!important;z-index:7000!important;overflow:hidden!important}
#tm-top-suggestions.tm-show{display:block!important}
.tm-top-suggestion{width:100%!important;border:0!important;background:transparent!important;border-radius:11px!important;padding:10px 11px!important;display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;text-align:left!important;color:#17372b!important;cursor:pointer!important}
.tm-top-suggestion:hover,.tm-top-suggestion.tm-active{background:#edf7f1!important}.tm-top-suggestion b{font-size:13px!important}.tm-top-suggestion small{font-size:10px!important;color:#708078!important;white-space:nowrap!important}

/* Account button opens the account/profile. Logout lives inside that profile. */
#tm-top-account{cursor:pointer!important;min-width:126px!important}
#tm-top-account:hover{background:rgba(255,255,255,.10)!important}
#tm-top-account .tm-account-caret{font-size:13px!important;opacity:.78!important;margin-left:2px!important}
.modal .danger-btn#profile-logout{background:#fff0f1!important;color:#a72b35!important;border:1px solid #ffd8dc!important;font-weight:800!important}

/* Live, smooth bottom results. */
#tm-results-drawer{left:424px!important;right:16px!important;bottom:14px!important;transition:height .28s cubic-bezier(.2,.8,.2,1),transform .28s cubic-bezier(.2,.8,.2,1)!important;will-change:height,transform!important}
#tm-results-drawer .tm-results-shell{transition:box-shadow .2s ease,background .2s ease!important}
#tm-results-drawer.tm-searching .tm-results-shell{box-shadow:0 18px 48px rgba(13,64,40,.23)!important}
#tm-results-drawer .tm-results-track{scroll-snap-type:x proximity!important;scroll-padding-left:14px!important;scrollbar-gutter:stable!important}
#tm-results-drawer .tm-result-card{scroll-snap-align:start!important;transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease,opacity .16s ease!important;content-visibility:auto!important;contain-intrinsic-size:285px 123px!important}
#tm-results-drawer.tm-refreshing .tm-result-card{opacity:.72!important}

/* Keep right controls clear of each other. */
.map-tools{right:16px!important;top:16px!important}
#tm-map-options-panel{right:0!important;left:auto!important;max-width:min(240px,calc(100vw - 32px))!important}
#tm-side-actions{right:16px!important;top:278px!important}
body.tm-map-menu-open #tm-side-actions{top:432px!important}

@media(max-width:900px){
  .sidebar{left:10px!important;top:calc(var(--tm-topbar-h,68px) + 10px)!important;width:min(390px,calc(100vw - 20px))!important;min-width:0!important;max-height:calc(100vh - var(--tm-topbar-h,68px) - 20px)!important}
  #sidebar .filters{max-height:calc(100vh - var(--tm-topbar-h,68px) - 20px)!important}
  #tm-results-drawer{left:10px!important;right:10px!important}
  .tm-brand-copy{display:none!important}.tm-brand-symbol{width:48px!important;height:42px!important;flex-basis:48px!important}
  #tm-top-account{min-width:40px!important}
}
</style>
<script id="trekmap-final-explorer-js">
(function(){
  const originalSearch=document.getElementById('search');
  const topSearch=document.getElementById('tm-top-search-input');
  const topWrap=topSearch?.closest('.tm-top-search');
  const drawer=document.getElementById('tm-results-drawer');

  // Replace the stretched image with a cleaner, responsive logo lockup.
  const logo=document.getElementById('tm-explorer-home');
  if(logo){
    logo.innerHTML='<span class="tm-brand-lockup"><svg class="tm-brand-symbol" viewBox="0 0 130 62" aria-hidden="true"><path d="M4 52 L31 15 L48 36 L66 8 L92 43" fill="none" stroke="white" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/><path d="M22 52 L36 34 L48 46 L63 27 L79 48" fill="none" stroke="#8be0b5" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M88 51 C98 42 96 31 105 25 C115 18 124 23 122 33 C120 42 109 45 101 51" fill="none" stroke="white" stroke-width="5" stroke-linecap="round"/><circle cx="106" cy="20" r="4.5" fill="white"/></svg><span class="tm-brand-copy"><strong>TrekMap <em>France</em></strong><small>Explorez · Randonnez · Partagez</small></span></span>';
  }

  // Add search helpers to the only visible search bar.
  if(topWrap && !document.getElementById('tm-top-search-clear')){
    const clear=document.createElement('button');
    clear.type='button';clear.id='tm-top-search-clear';clear.setAttribute('aria-label','Effacer la recherche');clear.textContent='×';
    const suggestions=document.createElement('div');suggestions.id='tm-top-suggestions';suggestions.setAttribute('role','listbox');
    topWrap.append(clear,suggestions);
  }
  const clear=document.getElementById('tm-top-search-clear');
  const suggestions=document.getElementById('tm-top-suggestions');
  let liveTimer=null;

  function queryValue(){return String(topSearch?.value||'').trim();}
  function normalized(v){try{return typeof norm==='function'?norm(v):String(v||'').toLowerCase().trim()}catch(_){return String(v||'').toLowerCase().trim()}}
  function syncAndSearch(immediate=false){
    if(!topSearch||!originalSearch)return;
    originalSearch.value=topSearch.value;
    clear?.classList.toggle('tm-visible',!!queryValue());
    drawer?.classList.add('tm-searching','tm-refreshing');
    clearTimeout(liveTimer);
    const run=()=>{
      try{
        if(typeof window.applyFilters==='function')window.applyFilters();
        else if(typeof applyFilters==='function')applyFilters();
        else originalSearch.dispatchEvent(new Event('input',{bubbles:true}));
      }catch(_){originalSearch.dispatchEvent(new Event('input',{bubbles:true}));}
      if(drawer){drawer.classList.add('tm-open');drawer.classList.remove('tm-collapsed');}
      setTimeout(()=>drawer?.classList.remove('tm-searching','tm-refreshing'),120);
      renderTopSuggestions();
    };
    if(immediate)run();else liveTimer=setTimeout(run,55);
  }
  function renderTopSuggestions(){
    if(!suggestions)return;
    const q=normalized(queryValue());
    if(!q){suggestions.classList.remove('tm-show');suggestions.innerHTML='';return;}
    let source=[];
    try{source=typeof allTreks!=='undefined'&&Array.isArray(allTreks)?allTreks:[]}catch(_){}
    let rows=source.map(t=>{
      let score=0;
      try{score=typeof searchScore==='function'?searchScore(t,q):0}catch(_){}
      if(!score){const hay=normalized((t.name||'')+' '+(t.region||'')+' '+(t.description||''));score=hay.includes(q)?1:0;}
      return {t,score};
    }).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0,6);
    suggestions.innerHTML=rows.map(x=>'<button type="button" class="tm-top-suggestion" data-id="'+Number(x.t.id)+'"><b>'+escapeHtml(x.t.name||'Trek')+'</b><small>'+escapeHtml(x.t.region||'France')+' · '+Number(x.t.distance||0).toFixed(1)+' km</small></button>').join('');
    suggestions.classList.toggle('tm-show',rows.length>0);
    suggestions.querySelectorAll('.tm-top-suggestion').forEach(btn=>btn.addEventListener('click',()=>{
      const id=Number(btn.dataset.id);const item=source.find(t=>Number(t.id)===id);
      if(item){topSearch.value=item.name||'';syncAndSearch(true);suggestions.classList.remove('tm-show');setTimeout(()=>{try{openDetail(id)}catch(_){}},70);}
    }));
  }
  function escapeHtml(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));}

  topSearch?.addEventListener('input',()=>syncAndSearch(false));
  topSearch?.addEventListener('focus',renderTopSuggestions);
  topSearch?.addEventListener('keydown',e=>{
    if(e.key==='Enter'){e.preventDefault();syncAndSearch(true);suggestions?.classList.remove('tm-show');}
    if(e.key==='Escape')suggestions?.classList.remove('tm-show');
  });
  clear?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();if(topSearch){topSearch.value='';syncAndSearch(true);topSearch.focus();}suggestions?.classList.remove('tm-show');});
  document.addEventListener('click',e=>{if(topWrap&&!topWrap.contains(e.target))suggestions?.classList.remove('tm-show');});
  clear?.classList.toggle('tm-visible',!!queryValue());

  // The top account button opens the profile when authenticated, otherwise the login dialog.
  const account=document.getElementById('tm-top-account');
  if(account){
    const oldName=document.getElementById('tm-top-account-name');
    let caret=account.querySelector('.tm-account-caret');
    if(!caret){caret=document.createElement('span');caret.className='tm-account-caret';caret.textContent='⌄';account.appendChild(caret);}
    account.addEventListener('click',function(e){
      e.preventDefault();e.stopImmediatePropagation();
      try{
        if(typeof currentUser!=='undefined'&&currentUser){openProfile();}
        else{authModal('login');}
      }catch(_){document.getElementById('account-button')?.click();}
    },true);
    if(oldName)oldName.title='Ouvrir mon compte';
  }

  // Make the drawer react immediately to filters too.
  const filterIds=['region-filter','difficulty-filter','duration-filter','sort-filter','distance-range','distance-tolerance','elevation-range','elevation-tolerance'];
  filterIds.forEach(id=>document.getElementById(id)?.addEventListener('input',()=>{
    drawer?.classList.add('tm-refreshing');
    setTimeout(()=>drawer?.classList.remove('tm-refreshing'),140);
  }));

  // Ensure Leaflet recalculates its canvas after converting the sidebar to a floating overlay.
  setTimeout(()=>{try{map?.invalidateSize?.()}catch(_){}},120);
})();
</script>
<!-- TREKMAP_FINAL_EXPLORER_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap final explorer fixes applied')
