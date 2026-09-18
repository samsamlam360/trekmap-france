from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

# Idempotent build step: remove a previous generated polish layer first.
html = re.sub(r'\s*<!-- TREKMAP_EXPLORER_POLISH_START -->.*?<!-- TREKMAP_EXPLORER_POLISH_END -->\s*', '\n', html, flags=re.S)

polish = r'''<!-- TREKMAP_EXPLORER_POLISH_START -->
<style id="trekmap-explorer-polish-css">
/* Explorer shell */
#app{padding-top:82px!important;background:#eef5f1}
#tm-explorer-topbar{position:absolute;z-index:5000;top:0;left:0;right:0;height:82px;display:flex;align-items:center;gap:24px;padding:10px 24px;background:linear-gradient(110deg,#0b4b34 0%,#0e6747 55%,#07543d 100%);box-shadow:0 9px 28px rgba(10,49,34,.20);overflow:hidden}
#tm-explorer-topbar:after{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 25% 150%,rgba(255,255,255,.12),transparent 34%),linear-gradient(145deg,transparent 0 72%,rgba(255,255,255,.035) 72% 100%)}
.tm-explorer-logo{position:relative;z-index:1;width:260px;min-width:260px;height:60px;border:0;background:transparent;padding:0;display:flex;align-items:center;justify-content:flex-start;border-radius:15px}
.tm-explorer-logo:hover{background:rgba(255,255,255,.08)}
.tm-explorer-logo img{width:250px;max-height:58px;object-fit:contain;object-position:left center;border-radius:12px}
.tm-top-search{position:relative;z-index:1;flex:1;max-width:540px;margin-left:auto;display:flex;align-items:center;background:#fff;border:1px solid rgba(255,255,255,.55);border-radius:999px;box-shadow:0 8px 24px rgba(0,0,0,.12);overflow:hidden}
.tm-top-search span{font-size:20px;color:#2d5d49;padding-left:17px}.tm-top-search input{width:100%;border:0;outline:0;background:transparent;padding:14px 16px 14px 10px;font-size:14px;color:#17372b}.tm-top-search input::placeholder{color:#7a8a83}
.tm-top-actions{position:relative;z-index:1;display:flex;align-items:center;gap:10px;margin-left:auto}
.tm-top-actions button{height:45px;border-radius:999px;padding:0 18px;border:1px solid rgba(255,255,255,.42);background:rgba(255,255,255,.08);color:#fff;font-weight:800;display:flex;align-items:center;gap:8px;white-space:nowrap;transition:.16s}
.tm-top-actions button:hover{background:rgba(255,255,255,.17);transform:translateY(-1px)}
#tm-top-explore{background:#1c9b65;border-color:#35b47e;box-shadow:0 7px 18px rgba(6,55,36,.22)}
#tm-top-account{padding:0 12px 0 8px;border-color:transparent;background:transparent}
.tm-top-avatar{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#1b9a65;color:#fff;font-weight:900;border:1px solid rgba(255,255,255,.20)}
#tm-top-account-name{max-width:130px;overflow:hidden;text-overflow:ellipsis}

/* Left panel: search and filters, no duplicate result list. */
.sidebar{width:420px!important;min-width:420px!important;height:100%!important;background:rgba(248,252,250,.97)!important;border-right:1px solid #d8e6de!important;box-shadow:12px 0 34px rgba(12,51,34,.11)!important;padding:14px!important;overflow:hidden!important;gap:12px}
.sidebar.collapsed{margin-left:-420px!important}
#sidebar .brand,#sidebar .account,#sidebar .tabs,#sidebar .list-head,#sidebar #trek-list{display:none!important}
.search-wrap{position:relative!important;margin:0!important;padding:56px 14px 14px!important;background:#fff!important;border:1px solid #dce9e2!important;border-radius:21px!important;box-shadow:0 8px 25px rgba(17,60,40,.08)!important}
.search-wrap:before{content:"⌕  Rechercher un trek";position:absolute;left:18px;top:16px;color:#173e2e;font-size:15px;font-weight:850;letter-spacing:-.01em}
.search{height:46px!important;padding:0 42px 0 14px!important;border:1px solid #d6e4dc!important;border-radius:13px!important;background:#fbfdfc!important;box-shadow:inset 0 1px 2px rgba(20,60,40,.025)!important;font-size:13px!important}
.search:focus{background:#fff!important;border-color:#54a67b!important;box-shadow:0 0 0 4px rgba(37,151,98,.10)!important}.clear-search{right:23px!important;top:67px!important}.suggestions{top:108px!important;left:14px!important;right:14px!important;border-radius:14px!important;box-shadow:0 15px 38px rgba(15,53,35,.15)!important}
.filters{position:relative!important;flex:1!important;min-height:0!important;overflow:auto!important;margin:0!important;padding:58px 14px 18px!important;background:#fff!important;border:1px solid #dce9e2!important;border-radius:21px!important;box-shadow:0 8px 25px rgba(17,60,40,.08)!important}
.filters:before{content:"☷  Filtres";position:absolute;left:18px;top:17px;color:#173e2e;font-size:15px;font-weight:850}
.filters::-webkit-scrollbar{width:7px}.filters::-webkit-scrollbar-thumb{background:#c0d2c8;border-radius:99px}.filters::-webkit-scrollbar-track{background:transparent}
.filter-row{gap:12px!important}.field label{font-size:10px!important;text-transform:uppercase!important;letter-spacing:.055em!important;color:#5f756b!important;font-weight:850!important;margin:9px 0 5px!important}.field select,.field input{border:1px solid #d9e6df!important;border-radius:12px!important;background:#fbfdfc!important;min-height:42px}.field select:focus,.field input:focus{outline:0!important;border-color:#5ba97f!important;box-shadow:0 0 0 3px rgba(37,151,98,.09)!important}
.filter-actions{gap:9px!important;margin-top:14px!important}.filter-actions button{border-radius:12px!important;min-height:42px!important;font-weight:800!important}.filter-actions #create-button{display:none!important}.filter-actions #reset-filters{background:#f4f8f6!important;border:1px solid #dde8e2!important}.filter-actions #upload-button{background:#eaf6ef!important;color:#176b45!important;border:1px solid #d4eadd!important}

/* Map menu: anchored safely inside the viewport. */
.map-tools{left:auto!important;right:18px!important;top:16px!important;max-width:none!important;display:block!important;z-index:2600!important}
#tm-map-options{min-width:92px!important;height:44px!important;border:1px solid #d5e4dc!important;border-radius:14px!important;background:rgba(255,255,255,.97)!important;box-shadow:0 9px 26px rgba(15,50,34,.14)!important;padding:0 15px!important;color:#173e2d!important;font-weight:850!important}
#tm-map-options-panel{top:52px!important;left:auto!important;right:0!important;width:min(240px,calc(100vw - 36px))!important;max-height:calc(100vh - 180px)!important;overflow:auto!important;border-radius:17px!important;box-shadow:0 18px 46px rgba(12,48,31,.20)!important;padding:11px!important}
#tm-map-options-panel button,#tm-map-options-panel select{min-height:40px!important;border-radius:11px!important;margin-bottom:7px!important}

/* Right actions: pleasant cards with enough clearance from the map menu. */
#tm-side-actions{right:18px!important;top:315px!important;bottom:auto!important;transform:none!important;gap:10px!important;z-index:2300!important}
#tm-side-actions button{width:76px!important;min-height:76px!important;border-radius:20px!important;background:rgba(255,255,255,.96)!important;border:1px solid #d8e6df!important;box-shadow:0 10px 26px rgba(15,52,35,.15)!important}
#tm-side-actions button:hover{transform:translateX(-3px)!important;box-shadow:0 15px 34px rgba(15,52,35,.20)!important}.tm-action-icon{background:linear-gradient(145deg,#eef8f2,#dff1e7)!important;color:#176b45!important}

/* Bottom trek drawer */
#tm-results-drawer{left:calc(420px + 18px)!important;right:18px!important;bottom:16px!important;z-index:2200!important}
#tm-results-drawer .tm-results-shell{border-radius:22px!important;background:rgba(252,254,253,.96)!important;backdrop-filter:blur(18px)!important;border:1px solid #d7e6de!important;box-shadow:0 15px 42px rgba(14,51,34,.18)!important}
#tm-results-drawer .tm-results-handle{height:46px!important;padding:0 17px!important}.tm-results-title{font-weight:900!important;color:#173b2d!important}.tm-results-count{background:#e8f5ed!important;border:1px solid #d5eadf!important}.tm-results-chevron{background:#e9f5ee!important;color:#176b45!important}
#tm-results-drawer .tm-result-card{border-radius:16px!important;border-color:#dfeae4!important;box-shadow:0 4px 15px rgba(18,60,41,.07)!important}
#tm-results-drawer .tm-result-card:hover{border-color:#96c4aa!important;box-shadow:0 11px 27px rgba(18,60,41,.13)!important}

@media(max-width:1050px){.tm-explorer-logo{width:205px;min-width:205px}.tm-explorer-logo img{width:195px}.tm-top-actions button{padding:0 13px}.tm-top-search{max-width:420px}}
@media(max-width:900px){#app{padding-top:68px!important}#tm-explorer-topbar{height:68px;padding:8px 10px;gap:8px}.tm-explorer-logo{width:54px;min-width:54px}.tm-explorer-logo img{width:54px;height:48px;object-fit:cover;object-position:left}.tm-top-search{margin:0;max-width:none}.tm-top-search input{padding:11px 8px;font-size:12px}.tm-top-actions{gap:5px}.tm-top-actions button{width:42px;padding:0;justify-content:center}.tm-top-actions button .tm-top-label,#tm-top-account-name{display:none}.sidebar{width:min(410px,94vw)!important;min-width:0!important}.sidebar.collapsed{margin-left:calc(-1 * min(410px,94vw))!important}#tm-results-drawer{left:10px!important;right:10px!important;bottom:10px!important}#tm-side-actions{right:10px!important;top:auto!important;bottom:198px!important}.map-tools{right:10px!important;top:10px!important}}
</style>
<script id="trekmap-explorer-polish-js">
(function(){
  const app=document.getElementById('app');
  if(!app)return;

  if(!document.getElementById('tm-explorer-topbar')){
    const bar=document.createElement('header');
    bar.id='tm-explorer-topbar';
    bar.innerHTML='<button class="tm-explorer-logo" id="tm-explorer-home" type="button" title="Retour à l’accueil"><img src="/logo-trekmap.svg" alt="TrekMap France"></button><label class="tm-top-search"><span aria-hidden="true">⌕</span><input id="tm-top-search-input" type="search" autocomplete="off" placeholder="Rechercher un trek, une région, un lieu…" aria-label="Rechercher un trek"></label><div class="tm-top-actions"><button id="tm-top-explore" type="button">🗺 <span class="tm-top-label">Explorer</span></button><button id="tm-top-create" type="button">✦ <span class="tm-top-label">Créer un trek</span></button><button id="tm-top-account" type="button"><span class="tm-top-avatar" id="tm-top-avatar">S</span><span id="tm-top-account-name">Compte</span>⌄</button></div>';
    app.prepend(bar);
  }

  const originalSearch=document.getElementById('search');
  const topSearch=document.getElementById('tm-top-search-input');
  let syncing=false;
  function syncTopFromLeft(){if(syncing||!topSearch||!originalSearch)return;syncing=true;topSearch.value=originalSearch.value||'';syncing=false;}
  function syncLeftFromTop(){if(syncing||!topSearch||!originalSearch)return;syncing=true;originalSearch.value=topSearch.value;originalSearch.dispatchEvent(new Event('input',{bubbles:true}));syncing=false;}
  topSearch?.addEventListener('input',syncLeftFromTop);
  topSearch?.addEventListener('keydown',e=>{if(e.key==='Enter'){syncLeftFromTop();document.getElementById('tm-results-drawer')?.classList.add('tm-open');document.getElementById('tm-results-drawer')?.classList.remove('tm-collapsed');}});
  originalSearch?.addEventListener('input',syncTopFromLeft);
  syncTopFromLeft();

  document.getElementById('tm-explorer-home')?.addEventListener('click',()=>{
    if(typeof window.TrekMapShowHome==='function')window.TrekMapShowHome();
    else document.getElementById('tm-home')?.classList.remove('tm-hidden');
  });
  document.getElementById('tm-top-explore')?.addEventListener('click',()=>{
    document.getElementById('tm-home')?.classList.add('tm-hidden');
    if(typeof window.switchTab==='function')window.switchTab('all');
    else document.querySelector('.tab[data-tab="all"]')?.click();
    document.getElementById('sidebar')?.classList.remove('collapsed');
  });
  document.getElementById('tm-top-create')?.addEventListener('click',()=>document.getElementById('create-button')?.click());
  document.getElementById('tm-top-account')?.addEventListener('click',()=>document.getElementById('account-button')?.click());

  function syncAccount(){
    const name=(document.getElementById('account-name')?.textContent||'Compte').trim();
    const target=document.getElementById('tm-top-account-name');
    const avatar=document.getElementById('tm-top-avatar');
    if(target)target.textContent=name==='Mode visiteur'?'Connexion':name;
    if(avatar)avatar.textContent=(name==='Mode visiteur'?'C':name.slice(0,1).toUpperCase());
  }
  syncAccount();
  const accountName=document.getElementById('account-name');
  if(accountName)new MutationObserver(syncAccount).observe(accountName,{childList:true,subtree:true,characterData:true});

  // Keep the old sidebar results permanently out of the visual layout.
  ['trek-list'].forEach(id=>{const el=document.getElementById(id);if(el)el.setAttribute('aria-hidden','true');});
})();
</script>
<!-- TREKMAP_EXPLORER_POLISH_END -->'''

html = html.replace('</body>', polish + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap explorer polish applied')
