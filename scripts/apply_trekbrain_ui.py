from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r"\s*<!-- TREKMAP_TREKBRAIN_UI_START -->.*?<!-- TREKMAP_TREKBRAIN_UI_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_REASONING_AGENT_UI_START" not in html:
    raise SystemExit("L'interface Agent v7 doit être construite avant TrekBrain v8.")

block = r'''<!-- TREKMAP_TREKBRAIN_UI_START -->
<style id="trekmap-trekbrain-css">
.tm-trekbrain-panel{margin-top:15px;padding:12px;border:1px solid #d8e7df;border-radius:13px;background:linear-gradient(145deg,#f8fcfa,#eef8f3)}
.tm-trekbrain-head{display:flex;align-items:flex-start;gap:9px}.tm-trekbrain-head>div{flex:1}
.tm-trekbrain-head h3{margin:0;color:#214b39;font-size:14px}.tm-trekbrain-head p{margin:4px 0 0;color:#687c71;font-size:9px;line-height:1.4}
.tm-trekbrain-badge{white-space:nowrap;padding:5px 7px;border-radius:999px;background:#dff2e8;color:#1e6245;font-size:9px;font-weight:900}
.tm-trekbrain-meta{display:flex;flex-wrap:wrap;gap:5px;margin:9px 0}.tm-trekbrain-chip{padding:5px 7px;border-radius:8px;background:#fff;border:1px solid #dce8e2;color:#526c60;font-size:9px}
.tm-trekbrain-feedback{margin-top:9px;padding-top:9px;border-top:1px solid #d9e6df}.tm-trekbrain-feedback b{display:block;font-size:10px;color:#355a49;margin-bottom:6px}
.tm-trekbrain-feedback-row{display:flex;gap:6px}.tm-trekbrain-feedback button{min-height:36px;border:1px solid #cedfd6;border-radius:9px;background:#fff;color:#365c4b;padding:0 10px;font-weight:850;font-size:10px}
.tm-trekbrain-feedback button:hover{background:#f2f8f5}.tm-trekbrain-feedback button:disabled{opacity:.55}
.tm-trekbrain-downbox{display:none;margin-top:7px}.tm-trekbrain-downbox.show{display:block}.tm-trekbrain-downbox textarea{width:100%;min-height:58px;padding:8px;border:1px solid #d3e1da;border-radius:9px;background:#fff;resize:vertical;font-size:11px}.tm-trekbrain-downbox button{margin-top:6px;background:#116b49;color:#fff;border:0}
.tm-trekbrain-learned{display:none;margin-top:7px;padding:7px 8px;border-radius:8px;background:#e4f4eb;color:#2a654c;font-size:9px}.tm-trekbrain-learned.show{display:block}
@media(max-width:820px){.tm-trekbrain-downbox textarea{font-size:16px}.tm-trekbrain-feedback button{min-height:42px}}
</style>
<script id="trekmap-trekbrain-js">
(function(){
  const $=id=>document.getElementById(id);
  const endpoint=path=>(typeof API!=='undefined'?API:'')+path;
  const requestHeaders=(extra={},method='GET')=>{try{return typeof headers==='function'?headers(extra,method):extra}catch(_){return extra}};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  let current=null,feedbackSent=false;

  async function sendFeedback(rating,comment=''){
    if(!current?.learning_token||feedbackSent)return;
    const buttons=document.querySelectorAll('.tm-trekbrain-feedback button');buttons.forEach(b=>b.disabled=true);
    try{
      const r=await fetch(endpoint('/ai/feedback'),{method:'POST',headers:requestHeaders({'Content-Type':'application/json'},'POST'),body:JSON.stringify({token:current.learning_token,rating,comment})});
      const d=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(d.detail||'Apprentissage indisponible');
      feedbackSent=true;
      const msg=$('tm-trekbrain-learned');
      if(msg){msg.textContent=d.message||'TrekBrain a appris de ce retour.';msg.classList.add('show')}
      if(typeof toast==='function')toast(d.message||'TrekBrain a appris de ce retour.');
    }catch(err){
      buttons.forEach(b=>b.disabled=false);
      if(typeof toast==='function')toast(err.message||'Impossible d’enregistrer le retour.');
    }
  }

  function render(){
    const content=$('tm-ai-content');if(!content||!current)return;
    content.querySelector('#tm-trekbrain-panel')?.remove();
    const tb=current.trekbrain||{};const local=(current.agent||{}).local_learning_brain||{};
    if(!tb.version&&!current.learning_token)return;
    feedbackSent=false;
    const model=tb.model||{};const quality=tb.quality||{};const hypotheses=tb.hypotheses||[];
    const panel=document.createElement('section');panel.id='tm-trekbrain-panel';panel.className='tm-trekbrain-panel';
    panel.innerHTML=`<div class="tm-trekbrain-head"><div><h3>🧠 TrekBrain apprend</h3><p>Mini-modèle TrekMap local. Il compare des stratégies et ajuste ses choix grâce aux retours, sans stocker le texte complet de ta demande.</p></div><span class="tm-trekbrain-badge">${esc(tb.version||'v8')}</span></div>
      <div class="tm-trekbrain-meta">
        <span class="tm-trekbrain-chip">Stratégie : <b>${esc(tb.strategy_label||tb.strategy||'équilibrée')}</b></span>
        <span class="tm-trekbrain-chip">Auto-évaluation : <b>${esc(quality.score??local.quality??'?')}/100</b></span>
        <span class="tm-trekbrain-chip">Hypothèses : <b>${esc(hypotheses.length||local.hypotheses_compared||1)}</b></span>
        <span class="tm-trekbrain-chip">Apprentissages perso : <b>${esc(model.personal_samples??local.personal_samples??0)}</b></span>
      </div>
      ${current.learning_token?`<div class="tm-trekbrain-feedback"><b>Est-ce que cette proposition est pertinente ?</b><div class="tm-trekbrain-feedback-row"><button type="button" id="tm-trekbrain-up">👍 Pertinent</button><button type="button" id="tm-trekbrain-down">👎 À améliorer</button></div><div class="tm-trekbrain-downbox" id="tm-trekbrain-downbox"><textarea id="tm-trekbrain-comment" maxlength="500" placeholder="Facultatif : qu’est-ce qui n’allait pas ? Ex. trop de route, étapes mal équilibrées, pas assez sauvage…"></textarea><button type="button" id="tm-trekbrain-send-down">Envoyer le retour</button></div><div id="tm-trekbrain-learned" class="tm-trekbrain-learned"></div></div>`:''}`;
    content.appendChild(panel);
    $('tm-trekbrain-up')?.addEventListener('click',()=>sendFeedback('up'));
    $('tm-trekbrain-down')?.addEventListener('click',()=>$('tm-trekbrain-downbox')?.classList.add('show'));
    $('tm-trekbrain-send-down')?.addEventListener('click',()=>sendFeedback('down',($('tm-trekbrain-comment')?.value||'').trim()));
  }

  if(!window.__trekmapTrekBrainFetchWrapped){
    window.__trekmapTrekBrainFetchWrapped=true;
    const previousFetch=window.fetch.bind(window);
    window.fetch=async function(input,init){
      const response=await previousFetch(input,init);
      try{
        const url=typeof input==='string'?input:(input&&input.url)||'';
        if(String(url).includes('/ai/plan')){
          response.clone().json().then(data=>{
            if(data&&typeof data==='object'&&(data.trekbrain||data.learning_token)){current=data;feedbackSent=false;setTimeout(render,80)}
          }).catch(()=>{});
        }
      }catch(_){ }
      return response;
    };
  }
  const content=$('tm-ai-content');if(content)new MutationObserver(()=>{if(current)setTimeout(render,0)}).observe(content,{childList:true,subtree:false});
})();
</script>
<!-- TREKMAP_TREKBRAIN_UI_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekBrain v8 learning UI applied")
