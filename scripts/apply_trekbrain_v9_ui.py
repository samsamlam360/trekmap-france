from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

# V9 replaces the V8 learning panel instead of stacking another block below it.
html = re.sub(
    r"\s*<!-- TREKMAP_TREKBRAIN_UI_START -->.*?<!-- TREKMAP_TREKBRAIN_UI_END -->\s*",
    "\n",
    html,
    flags=re.S,
)
html = re.sub(
    r"\s*<!-- TREKMAP_TREKBRAIN_V9_UI_START -->.*?<!-- TREKMAP_TREKBRAIN_V9_UI_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_REASONING_AGENT_UI_START" not in html:
    raise SystemExit("L'interface Agent doit être construite avant TrekBrain v9.")

# The inherited research panel also observes its own child insertions. Patch
# only the V9 build output: the V8 generator remains byte-for-byte unchanged.
if "TREKBRAIN_V9_RESEARCH_GUARD" not in html:
    original = """  function renderResearch(){
    const content=$('tm-ai-content');if(!content||!lastAgentPlan)return;"""
    replacement = """  // TREKBRAIN_V9_RESEARCH_GUARD
  let renderedResearchPlan=null;
  function renderResearch(){
    const content=$('tm-ai-content');if(!content||!lastAgentPlan)return;
    if(renderedResearchPlan===lastAgentPlan&&content.querySelector('#tm-agent-research'))return;"""
    if original not in html or "    content.appendChild(section);" not in html:
        raise SystemExit("Le panneau de recherche a changé : vérifier le correctif V9 avant construction.")
    html = html.replace(original, replacement, 1)
    html = html.replace("    content.appendChild(section);", "    content.appendChild(section);\n    renderedResearchPlan=lastAgentPlan;", 1)

block = r'''<!-- TREKMAP_TREKBRAIN_V9_UI_START -->
<style id="trekmap-trekbrain-v9-css">
.tm-v9-panel{margin-top:14px;padding:13px;border:1px solid #d6e5dd;border-radius:14px;background:#fff}
.tm-v9-head{display:flex;align-items:flex-start;gap:10px}.tm-v9-head>div{flex:1}.tm-v9-head h3{margin:0;color:#214b39;font-size:15px}.tm-v9-head p{margin:4px 0 0;color:#708178;font-size:9px;line-height:1.4}
.tm-v9-score{min-width:58px;text-align:center;padding:7px 8px;border-radius:10px;background:#eaf6f0;color:#1e6548}.tm-v9-score b{display:block;font-size:17px}.tm-v9-score span{display:block;font-size:8px;font-weight:800;text-transform:uppercase}
.tm-v9-meta{display:flex;flex-wrap:wrap;gap:5px;margin:10px 0}.tm-v9-chip{padding:5px 7px;border:1px solid #dce7e1;border-radius:8px;background:#f9fbfa;color:#52695e;font-size:9px}.tm-v9-chip b{color:#244d3b}
.tm-v9-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:9px}.tm-v9-col{min-width:0;padding:9px;border-radius:11px;border:1px solid #e0e8e4;background:#fafcfb}.tm-v9-col h4{margin:0 0 7px;font-size:10px}.tm-v9-ok h4{color:#236447}.tm-v9-warn h4{color:#8b641f}.tm-v9-bad h4{color:#8a4048}.tm-v9-item{padding:6px 0;border-top:1px solid #edf2ef;color:#5b6f65;font-size:9px;line-height:1.35}.tm-v9-item:first-of-type{border-top:0;padding-top:0}.tm-v9-empty{color:#8a9991;font-size:9px}
.tm-v9-feedback{margin-top:10px;padding-top:10px;border-top:1px solid #e0e9e4}.tm-v9-feedback b{display:block;margin-bottom:7px;color:#355a49;font-size:10px}.tm-v9-feedback-row{display:flex;gap:6px}.tm-v9-feedback button{min-height:37px;border:1px solid #cedfd6;border-radius:9px;background:#fff;color:#365c4b;padding:0 10px;font-weight:850;font-size:10px}.tm-v9-feedback button:disabled{opacity:.55}.tm-v9-down{display:none;margin-top:7px}.tm-v9-down.show{display:block}.tm-v9-down textarea{width:100%;min-height:60px;padding:8px;border:1px solid #d3e1da;border-radius:9px;background:#fff;resize:vertical;font-size:11px}.tm-v9-down button{margin-top:6px;background:#116b49;color:#fff;border:0}.tm-v9-learned{display:none;margin-top:7px;padding:7px 8px;border-radius:8px;background:#e4f4eb;color:#2a654c;font-size:9px}.tm-v9-learned.show{display:block}
.tm-v9-head p,.tm-v9-chip,.tm-v9-item,.tm-v9-empty,.tm-v9-feedback b,.tm-v9-feedback button,.tm-v9-learned,.tm-v9-col h4,.tm-v9-disclaimer{font-size:14px;line-height:1.5}.tm-v9-disclaimer{color:#52695e}.tm-v9-feedback-row{flex-wrap:wrap}
.tm-v9-ask{margin-top:16px;display:grid;gap:8px}.tm-v9-ask label{font-size:14px}.tm-v9-ask input,.tm-v9-ask button{font-size:16px;min-height:44px;padding:8px;border:1px solid #cedfd6;border-radius:8px;max-width:100%;min-width:0}.tm-v9-answer{white-space:pre-wrap;font-size:14px;line-height:1.5;color:#355a49}
@media(max-width:820px){.tm-v9-grid{grid-template-columns:1fr}.tm-v9-down textarea{font-size:16px}.tm-v9-feedback button{min-height:44px}}
</style>
<script id="trekmap-trekbrain-v9-js">
(function(){
  const $=id=>document.getElementById(id);
  const endpoint=path=>(typeof API!=='undefined'?API:'')+path;
  const requestHeaders=(extra={},method='GET')=>{try{return typeof headers==='function'?headers(extra,method):extra}catch(_){return extra}};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  let current=null,feedbackSent=false,rendered=null;

  function setLabels(){
    const launch=$('tm-ai-launch');if(launch){const label=launch.querySelector('.label');if(label)label.textContent='TrekBrain'}
    const title=document.querySelector('#tm-ai-overlay .tm-ai-head h2');if(title)title.textContent='🧠 TrekBrain';
    const note=document.querySelector('#tm-ai-overlay .tm-ai-note');if(note)note.textContent='Assistant spécialisé : calcul d’itinéraires, recherche de sources et contrôles de cohérence. Les conditions réelles restent à vérifier avant le départ.';
  }
  setLabels();

  function items(values){
    const list=(values||[]).filter(Boolean).slice(0,5);
    return list.length?list.map(x=>`<div class="tm-v9-item">${esc(x)}</div>`).join(''):'<div class="tm-v9-empty">Rien de particulier.</div>';
  }

  async function feedback(rating,comment=''){
    if(!current?.learning_token||feedbackSent)return;
    document.querySelectorAll('.tm-v9-feedback button').forEach(b=>b.disabled=true);
    try{
      const r=await fetch(endpoint('/ai/feedback'),{method:'POST',headers:requestHeaders({'Content-Type':'application/json'},'POST'),body:JSON.stringify({token:current.learning_token,rating,comment})});
      const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||'Apprentissage indisponible');
      feedbackSent=true;const msg=$('tm-v9-learned');if(msg){msg.textContent=d.message||'TrekBrain a appris de ce retour.';msg.classList.add('show')}
      if(typeof toast==='function')toast(d.message||'TrekBrain a appris de ce retour.');
    }catch(err){document.querySelectorAll('.tm-v9-feedback button').forEach(b=>b.disabled=false);if(typeof toast==='function')toast(err.message||'Retour impossible.');}
  }

  async function ask(event){
    event.preventDefault();
    const question=($('tm-v9-question')?.value||'').trim();
    const output=$('tm-v9-answer'),button=$('tm-v9-ask-send'),snapshot=current;
    if(!output||question.length<3||!snapshot)return;
    button.disabled=true;output.textContent='Lecture du parcours…';
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),12000);
    try{
      const body={question,stages:(snapshot.stages||[]).slice(0,21).map(s=>({distance_km:s.distance_km??null,overnight:s.overnight||'',water_notes:s.water_notes||''})),transport:snapshot.transport||{},limitations:(snapshot.confidence?.limitations||[]).slice(0,12)};
      const response=await fetch(endpoint('/ai/ask'),{method:'POST',headers:requestHeaders({'Content-Type':'application/json'},'POST'),body:JSON.stringify(body),signal:controller.signal});
      const data=await response.json();if(!response.ok)throw new Error('Impossible de lire ce parcours pour le moment.');
      if(current===snapshot)output.textContent=(data.context?data.context+'\n\n':'')+data.answer;
    }catch(err){if(current===snapshot)output.textContent=err.name==='AbortError'?'Réponse trop lente. Tu peux réessayer.':err.message;}
    finally{clearTimeout(timer);button.disabled=false;}
  }

  function render(){
    const content=$('tm-ai-content');if(!content||!current)return;
    if(rendered===current&&content.querySelector('#tm-v9-panel'))return;
    content.querySelector('#tm-v9-panel')?.remove();
    const d=current.decision_summary||{};const tb=current.trekbrain||{};const perf=(current.agent||{}).performance||{};
    if(d.quality==null&&!tb.version)return;
    feedbackSent=false;
    const elapsed=Number(d.elapsed_ms||perf.total_ms||0);const seconds=elapsed?`${(elapsed/1000).toFixed(elapsed<10000?1:0)} s`:'?';
    const hypotheses=(tb.hypotheses||[]).length||1;
    const panel=document.createElement('section');panel.id='tm-v9-panel';panel.className='tm-v9-panel';
    panel.innerHTML=`<div class="tm-v9-head"><div><h3>🧭 Décision TrekBrain</h3><p>${esc(d.understood||'Analyse du trek terminée.')}</p></div><div class="tm-v9-score"><b>${esc(d.quality??'?')}</b><span>/ 100</span></div></div>
      <div class="tm-v9-meta"><span class="tm-v9-chip">Stratégie <b>${esc(tb.strategy_label||tb.strategy||'équilibrée')}</b></span><span class="tm-v9-chip">Hypothèses <b>${esc(hypotheses)}</b></span><span class="tm-v9-chip">Préparation <b>${esc(seconds)}</b></span><span class="tm-v9-chip">Résultats bien classés <b>${esc(d.strong_sources??0)}</b></span></div>
      <p class="tm-v9-disclaimer">${esc(d.score_meaning||'Score de cohérence indicatif : ce n’est pas une garantie de sécurité.')} Les sources Web sont des pistes à consulter, pas des confirmations.</p>
      <div class="tm-v9-grid"><div class="tm-v9-col tm-v9-ok"><h4>✓ Confirmé par le calcul</h4>${items(d.verified)}</div><div class="tm-v9-col tm-v9-warn"><h4>? À vérifier</h4>${items(d.uncertain)}</div><div class="tm-v9-col tm-v9-bad"><h4>! Important</h4>${items(d.important)}</div></div>
      <form class="tm-v9-ask" id="tm-v9-ask"><label for="tm-v9-question">Une question sur ce trek ?</label><input id="tm-v9-question" maxlength="800" minlength="3" required placeholder="Ex. Où trouver de l’eau au jour 2 ?"><button id="tm-v9-ask-send" type="submit">Expliquer les données du parcours</button><div class="tm-v9-answer" id="tm-v9-answer" role="status" aria-live="polite"></div></form>
      ${current.learning_token?`<div class="tm-v9-feedback"><b>Cette proposition t'aide-t-elle vraiment ?</b><div class="tm-v9-feedback-row"><button type="button" id="tm-v9-up">👍 Pertinente</button><button type="button" id="tm-v9-down-btn">👎 À améliorer</button></div><div class="tm-v9-down" id="tm-v9-down"><textarea id="tm-v9-comment" maxlength="500" placeholder="Ex. étapes trop longues, mauvais choix de village, pas assez de nature…"></textarea><button type="button" id="tm-v9-send">Envoyer</button></div><div id="tm-v9-learned" class="tm-v9-learned"></div></div>`:''}`;
    content.appendChild(panel);
    rendered=current;
    $('tm-v9-ask')?.addEventListener('submit',ask);
    $('tm-v9-up')?.addEventListener('click',()=>feedback('up'));
    $('tm-v9-down-btn')?.addEventListener('click',()=>$('tm-v9-down')?.classList.add('show'));
    $('tm-v9-send')?.addEventListener('click',()=>feedback('down',($('tm-v9-comment')?.value||'').trim()));
  }

  if(!window.__trekmapTrekBrainV9FetchWrapped){
    window.__trekmapTrekBrainV9FetchWrapped=true;
    const previous=window.fetch.bind(window);
    window.fetch=async function(input,init){
      const response=await previous(input,init);
      try{const url=typeof input==='string'?input:(input&&input.url)||'';if(response.ok&&String(url).includes('/ai/plan'))response.clone().json().then(data=>{if(data&&typeof data==='object'&&(data.decision_summary||data.trekbrain)){current=data;feedbackSent=false;setTimeout(render,50)}}).catch(()=>{});}catch(_){ }
      return response;
    };
  }
  const content=$('tm-ai-content');if(content)new MutationObserver(()=>{if(current)setTimeout(render,0)}).observe(content,{childList:true,subtree:false});
})();
</script>
<!-- TREKMAP_TREKBRAIN_V9_UI_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekBrain v9 precision UI applied")
