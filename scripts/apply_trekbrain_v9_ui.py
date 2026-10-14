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
.tm-ux-analysis-details{border:0}
.tm-ux-analysis-details>summary{list-style:none;cursor:pointer;font-weight:850;color:#115b40;font-size:15px;display:flex;justify-content:space-between;gap:12px;min-height:48px;align-items:center}
.tm-ux-analysis-details>summary::-webkit-details-marker{display:none}
.tm-ux-analysis-details[open]>summary span{transform:rotate(180deg)}
.tm-ux-analysis-details>summary:focus-visible{outline:3px solid #ffbf47;outline-offset:3px;border-radius:7px}
.tm-ux-analysis-inner{padding-top:11px;border-top:1px solid #dbe8e0}
.tm-v9-panel:has(.tm-ux-analysis-details){padding:12px 17px;background:#fff;border:1px solid #dce8e1}
.tm-ux-analysis-details:not([open]){max-height:none}
.tm-v9-ask{margin-top:16px;display:grid;gap:8px}.tm-v9-ask label{font-size:14px}.tm-v9-ask input,.tm-v9-ask button{font-size:16px;min-height:44px;padding:8px;border:1px solid #cedfd6;border-radius:8px;max-width:100%;min-width:0}.tm-v9-answer{white-space:pre-wrap;font-size:14px;line-height:1.5;color:#355a49}
.tm-v9-readiness{padding:13px;border:1px solid #d4e2d9;border-radius:12px;background:#f7faf8;color:#284c39;font-size:14px;line-height:1.5;overflow-wrap:anywhere}
.tm-v9-readiness[data-status="incomplete"],.tm-v9-readiness[data-status="unknown"]{background:#fff9ed;border-color:#e4ce9e;color:#694b16}.tm-v9-readiness[data-status="refused"]{background:#fff2f0;border-color:#e8bbb5;color:#81382e}
.tm-v9-readiness h3{margin:0 0 6px;font-size:18px;color:inherit}.tm-v9-readiness p{margin:6px 0}.tm-v9-readiness ul{margin:10px 0;padding-left:21px}.tm-v9-readiness li{margin:7px 0}.tm-v9-readiness-actions{display:grid;gap:8px;margin-top:12px}.tm-v9-readiness-actions button{min-height:44px;padding:9px 12px;border:1px solid currentColor;border-radius:9px;background:#fff;color:inherit;font:inherit;font-weight:800;cursor:pointer}.tm-v9-readiness-actions button:focus-visible{outline:3px solid #ffbf47;outline-offset:3px}.tm-v9-readiness-actions small{display:block;font-size:13px;line-height:1.5}
.tm-ux-essentials>.tm-v9-readiness{margin-bottom:14px}
@media(max-width:820px){.tm-v9-grid{grid-template-columns:1fr}.tm-v9-down textarea{font-size:16px}.tm-v9-feedback button{min-height:44px}}
</style>
<script id="trekmap-trekbrain-v9-js">
(function(){
  if(window.__trekmapTrekBrainV9UI)return;window.__trekmapTrekBrainV9UI=true;
  const $=id=>document.getElementById(id);
  const endpoint=path=>(typeof API!=='undefined'?API:'')+path;
  const requestHeaders=(extra={},method='GET')=>{try{return typeof headers==='function'?headers(extra,method):extra}catch(_){return extra}};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  let current=null,feedbackSent=false,rendered=null;

  function readinessView(plan){
    const verdict=plan?.trip_readiness;
    const known=verdict&&['ready','incomplete','refused'].includes(verdict.status);
    const status=known?verdict.status:'unknown';
    const labels={ready:'Besoins confirmés',incomplete:'Préparation incomplète',refused:'Tracé refusé',unknown:'À vérifier'};
    const issues=known&&Array.isArray(verdict.issues)?verdict.issues.filter(x=>x&&typeof x==='object'):[];
    // Older plans keep their warnings visible even when their score is high.
    if(!known){
      const cover=plan?.map_resources?.coverage||{},log=plan?.logistics||{},distance=plan?.planner?.distance_contract||{};
      ['water','food'].forEach(requirement=>{
        const days=Array.isArray(cover['days_without_'+requirement])?cover['days_without_'+requirement]:[];
        if(days.length||['not_verified','providers_unavailable','partial'].includes(cover[requirement]))issues.push({requirement,days,detail:requirement==='water'?'Disponibilité de l’eau à confirmer.':'Commerces et provisions à vérifier.'});
      });
      const nights=Array.isArray(log.nights)?log.nights:[];
      const missing=nights.filter(x=>x?.status==='unresolved').map(x=>x.night);
      if(Number(log.nights_missing)>0||missing.length)issues.push({requirement:'accommodation',days:missing,detail:'Nuitées sans hébergement confirmé : '+(missing.length||Number(log.nights_missing))+'.'});
      const transfers=nights.filter(x=>x?.access_mode==='transfer_required').map(x=>x.night);
      if(Number(log.nights_transfer_required)>0||transfers.length)issues.push({requirement:'accommodation',days:transfers,detail:'Transferts vers les nuitées à organiser.'});
      if(distance.target_exceeded)issues.push({requirement:'distance',days:(distance.days_exceeding||[]).map(x=>x.day),detail:'Distance supérieure à l’objectif de '+distance.daily_target_km+' km/jour.'});
      (Array.isArray(plan?.side_requests)?plan.side_requests:[]).filter(x=>x?.required&&x.satisfied!==true).forEach(x=>issues.push({requirement:'objective',days:x.preferred_day?[x.preferred_day]:[],detail:'Objectif demandé non confirmé : '+String(x.request||x.text||x.kind||'objectif')}));
      const warnings=[...(Array.isArray(plan?.decision_summary?.important)?plan.decision_summary.important:[]),...(Array.isArray(plan?.trekbrain?.quality?.blockers)?plan.trekbrain.quality.blockers:[])];
      [...new Set(warnings.map(String))].forEach(detail=>issues.push({requirement:'other',detail,days:[]}));
    }
    const actions=known&&Array.isArray(verdict.actions)?verdict.actions.filter(x=>x?.type==='edit_request'):[];
    return {status,label:labels[status],routeValidated:known&&verdict.route_validated===true,issues,
      actions:actions.length?actions:[{type:'edit_request',label:'Modifier la requête',detail:'Ajuste ta demande dans le formulaire avant de lancer un nouveau calcul.'}]};
  }

  function readinessIssueText(issue){
    const titles={water:'Eau',food:'Ravitaillement',accommodation:'Nuitées',lodging:'Nuitées',logistics:'Nuitées',distance:'Distance',objective:'Objectif',objectives:'Objectif',side_request:'Objectif',transit:'Transports',route:'Tracé'};
    const requirement=String(issue.requirement||'other').toLowerCase();
    const days=[...new Set((Array.isArray(issue.days)?issue.days:[]).map(Number).filter(x=>Number.isInteger(x)&&x>=1&&x<=21))].sort((a,b)=>a-b);
    const where=days.length?' · '+(days.length===1?'jour ':'jours ')+days.join(', '):'';
    return (titles[requirement]||'Besoin à préparer')+where+' : '+String(issue.detail||issue.code||'Confirmation manquante.');
  }

  function readinessHTML(plan){
    const view=readinessView(plan);
    const groups=new Map();
    view.issues.forEach(issue=>{
      const req=String(issue.requirement||'other').toLowerCase();
      const group=['route','water','food'].includes(req)?req:['accommodation','lodging','logistics'].includes(req)?'nights':'other';
      if(!groups.has(group))groups.set(group,[]);
      const text=readinessIssueText(issue);if(!groups.get(group).includes(text))groups.get(group).push(text);
    });
    const text=view.status==='ready'?'Le tracé et les besoins demandés sont confirmés par les données du parcours.'
      :view.status==='incomplete'?(view.routeValidated?'Tracé pédestre validé. Les besoins ci-dessous restent à préparer.':'Les besoins ci-dessous restent à préparer et le tracé reste à vérifier.')
      :view.status==='refused'?'Le parcours ne remplit pas les contrôles de validation du tracé.'
      :'Le verdict de préparation manque pour ce parcours. Vérifie les besoins avant le départ.';
    return `<div class="tm-v9-readiness" data-status="${view.status}" role="region" aria-label="Préparation du trek"><h3>${esc(view.label)}</h3><p>${esc(text)}</p>
      ${groups.size?`<ul>${[...groups.values()].map(lines=>`<li>${lines.map(esc).join('<br>')}</li>`).join('')}</ul>`:''}
      <p>Vérifie les conditions actuelles, la potabilité de l’eau et les réservations avant le départ.</p>
      <div class="tm-v9-readiness-actions">${view.actions.map((action,i)=>`<div><button type="button" data-readiness-action="${i}">${esc(action.label||'Modifier la requête')}</button>${action.detail?`<small>${esc(action.detail)}</small>`:''}</div>`).join('')}</div></div>`;
  }

  function editReadinessRequest(plan,action={}){
    const changes=action.suggested_changes&&typeof action.suggested_changes==='object'?action.suggested_changes:{};
    const promptNode=$('tm-ai-prompt');
    const previous={days:Number(plan.effective_request?.days??plan.duration_days??$('tm-ai-days')?.value),daily_km:Number(plan.effective_request?.daily_km??plan.planner?.distance_contract?.daily_target_km??$('tm-ai-km')?.value)};
    const fields={prompt:'tm-ai-prompt',region:'tm-ai-region',days:'tm-ai-days',daily_km:'tm-ai-km',difficulty:'tm-ai-difficulty',route_type:'tm-ai-route-type'};
    const checks={require_transit:'tm-ai-transit',require_water:'tm-ai-water',require_accommodation:'tm-ai-sleep',require_food:'tm-ai-food'};
    let focusId='tm-ai-prompt',changed=false;
    Object.entries(fields).forEach(([key,id])=>{
      const node=$(id),value=changes[key];if(!node||value==null)return;
      if(key==='days'&&(!Number.isInteger(Number(value))||Number(value)<1||Number(value)>21))return;
      if(key==='daily_km'&&(!Number.isFinite(Number(value))||Number(value)<3||Number(value)>40))return;
      if(key==='difficulty'&&!['easy','medium','hard'].includes(value))return;
      if(key==='route_type'&&!['Boucle','Traversée','Itinérance','Aller-retour'].includes(value))return;
      node.value=String(value).slice(0,key==='prompt'?4000:120);
      if(!changed){focusId=id;changed=true}
    });
    Object.entries(checks).forEach(([key,id])=>{
      const node=$(id);if(node&&typeof changes[key]==='boolean'){node.checked=changes[key];if(!changed){focusId=id;changed=true}}
    });
    // Written constraints are authoritative in the planner. Align only the
    // unchanged target phrase when the user explicitly accepts this edit;
    // otherwise keep their newer text and focus it for review.
    let reviewText=false;
    if(promptNode&&changes.prompt==null){
      let text=String(promptNode.value||'');
      const targets=[['days',/\b(\d{1,2})\s*(jours?|j)\b/i],['daily_km',/\b(\d{1,2}(?:[.,]\d+)?)\s*km\s*(?:\/\s*|par\s+)?(?:jour|j)\b/i]];
      targets.forEach(([key,pattern])=>{
        const value=Number(changes[key]);
        if(changes[key]==null||!Number.isFinite(value)||(key==='days'?(!Number.isInteger(value)||value<1||value>21):(value<3||value>40)))return;
        const match=text.match(pattern);if(!match)return;
        const stated=Number(match[1].replace(',','.'));
        const explicit=key==='daily_km'&&(plan.planner?.distance_contract?.explicit_bounds===true||/(?:max(?:imum)?|minimum|pas\s+plus\s+de|moins\s+de|au\s+moins|entre)\s*$/i.test(text.slice(0,match.index)));
        if(stated!==previous[key]||explicit){reviewText=true;return}
        const replacement=key==='days'?`${value} jours`:`${value} km par jour`;
        text=text.slice(0,match.index)+replacement+text.slice(match.index+match[0].length);
      });
      promptNode.value=text;
    }
    if(reviewText){focusId='tm-ai-prompt';if(typeof toast==='function')toast('Adapte aussi la demande écrite : ses contraintes restent prioritaires.')}
    if(typeof window.TrekMapOpenAI==='function')window.TrekMapOpenAI();
    else{const overlay=$('tm-ai-overlay');overlay?.classList.add('open');overlay?.setAttribute('aria-hidden','false')}
    document.querySelector('#tm-ai-overlay .tm-ai-shell')?.classList.remove('has-result');
    setTimeout(()=>{
      const field=$(focusId),side=document.querySelector('#tm-ai-overlay .tm-ai-side');
      const advanced=field?.closest?.('details');if(advanced)advanced.open=true;
      try{side?.scrollTo({top:0,behavior:'auto'});field?.scrollIntoView?.({block:'nearest',behavior:'auto'})}catch(_){}
      field?.focus?.();
    },120);
  }

  const readinessBound=new WeakSet();
  function bindReadiness(host,plan){
    const actions=readinessView(plan).actions;
    (host?.querySelectorAll?.('[data-readiness-action]')||[]).forEach(button=>{
      if(readinessBound.has(button))return;readinessBound.add(button);
      button.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();editReadinessRequest(plan,actions[Number(button.dataset.readinessAction)]||{})});
    });
  }
  window.TrekMapTripReadiness={view:readinessView,html:readinessHTML,bind:bindReadiness,edit:editReadinessRequest};

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
    const hasAnalysis=d.quality!=null||!!tb.version;
    feedbackSent=false;
    const elapsed=Number(d.elapsed_ms||perf.total_ms||0);const seconds=elapsed?`${(elapsed/1000).toFixed(elapsed<10000?1:0)} s`:'?';
    const hypotheses=(tb.hypotheses||[]).length||1;
    const panel=document.createElement('section');panel.id='tm-v9-panel';panel.className='tm-v9-panel';
    panel.innerHTML=(content.querySelector('.tm-v9-readiness')?'':readinessHTML(current))+(hasAnalysis?`<details class="tm-ux-analysis-details" id="tm-ux-analysis-details"><summary>Voir l’analyse détaillée <span aria-hidden="true">⌄</span></summary><div class="tm-ux-analysis-inner"><div class="tm-v9-head"><div><h3>Décision TrekBrain</h3><p>${esc(d.understood||'Analyse du trek terminée.')}</p></div><div class="tm-v9-score"><b>${esc(d.quality??'?')}</b><span>/ 100</span></div></div>
      <div class="tm-v9-meta"><span class="tm-v9-chip">Stratégie <b>${esc(tb.strategy_label||tb.strategy||'équilibrée')}</b></span><span class="tm-v9-chip">Hypothèses <b>${esc(hypotheses)}</b></span><span class="tm-v9-chip">Préparation <b>${esc(seconds)}</b></span><span class="tm-v9-chip">Résultats bien classés <b>${esc(d.strong_sources??0)}</b></span></div>
      <p class="tm-v9-disclaimer">${esc(d.score_meaning||'Score de cohérence indicatif : ce n’est pas une garantie de sécurité.')} Les sources Web sont des pistes à consulter, pas des confirmations.</p>
      <div class="tm-v9-grid"><div class="tm-v9-col tm-v9-ok"><h4>✓ Confirmé par le calcul</h4>${items(d.verified)}</div><div class="tm-v9-col tm-v9-warn"><h4>? À vérifier</h4>${items(d.uncertain)}</div><div class="tm-v9-col tm-v9-bad"><h4>! Important</h4>${items(d.important)}</div></div>
      <form class="tm-v9-ask" id="tm-v9-ask"><label for="tm-v9-question">Une question sur ce trek ?</label><input id="tm-v9-question" maxlength="800" minlength="3" required placeholder="Ex. Où trouver de l’eau au jour 2 ?"><button id="tm-v9-ask-send" type="submit">Expliquer les données du parcours</button><div class="tm-v9-answer" id="tm-v9-answer" role="status" aria-live="polite"></div></form>
      ${current.learning_token?`<div class="tm-v9-feedback"><b>Cette proposition t'aide-t-elle vraiment ?</b><div class="tm-v9-feedback-row"><button type="button" id="tm-v9-up">👍 Pertinente</button><button type="button" id="tm-v9-down-btn">👎 À améliorer</button></div><div class="tm-v9-down" id="tm-v9-down"><textarea id="tm-v9-comment" maxlength="500" placeholder="Ex. étapes trop longues, mauvais choix de village, pas assez de nature…"></textarea><button type="button" id="tm-v9-send">Envoyer</button></div><div id="tm-v9-learned" class="tm-v9-learned"></div></div>`:''}</div></details>`:'');
    content.appendChild(panel);
    rendered=current;
    bindReadiness(content,current);
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
      try{const url=typeof input==='string'?input:(input&&input.url)||'';if(String(url).includes('/ai/plan'))response.clone().json().then(data=>{
        const plan=response.ok?data:data?.detail;
        if(plan&&typeof plan==='object'&&(plan.decision_summary||plan.trekbrain||plan.trip_readiness||plan.route_preview||plan.stages)){current=plan;feedbackSent=false;setTimeout(render,50)}
      }).catch(()=>{});}catch(_){ }
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
