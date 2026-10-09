"""Progressive, accessible TrekBrain v9 interface: presentation only.

No changes to planning requests, route data, Neon or external providers.
The original input IDs remain in the DOM so the existing planner scripts work.
Repeatable after the existing render build chain without duplicate UI blocks.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")
html = re.sub(
    r"\s*<!-- TREKMAP_TREKBRAIN_UX_2026_START -->.*?<!-- TREKMAP_TREKBRAIN_UX_2026_END -->\s*",
    "\n", html, flags=re.S,
)
for marker in (
    "TREKMAP_TREKBRAIN_V9_UI_START",
    "TREKMAP_TREKBRAIN_SCROLL_UI_START",
    "TREKMAP_AI_EXPERIENCE_START",
):
    if marker not in html:
        raise SystemExit("Missing prerequisite TrekBrain UI layer: " + marker)

block = r'''<!-- TREKMAP_TREKBRAIN_UX_2026_START -->
<style id="trekbrain-evidence-ux-css">
/* Scope EVERY rule to the TrekBrain dialog so TrekMap navigation stays intact.
   Research: NN/g progressive disclosure, Baymard form usability, WCAG 2.2. */
#tm-ai-overlay {
  --tb-ink:#152e24;
  --tb-green:#115b40;
  --tb-green-dark:#0c4933;
  --tb-muted:#476257;
  --tb-border:#d5e4db;
  --tb-canvas:#f4f8f5;
  --tb-highlight:#eaf5ed;
  --tb-focus:#ffbf47;
  background:rgba(7,27,19,.68);
}
#tm-ai-overlay .tm-ai-shell {
  background:var(--tb-canvas);
  border:1px solid #b9d4c3;
  border-radius:22px;
  grid-template-columns:minmax(340px,370px) minmax(0,1fr);
  box-shadow:0 28px 90px rgba(1,24,12,.28);
}
#tm-ai-overlay .tm-ai-side {
  background:#fff;
  padding:24px 23px 30px;
  border-right:1px solid var(--tb-border);
}
#tm-ai-overlay .tm-ai-result {
  background:var(--tb-canvas);
  padding:27px 28px 40px;
  color:var(--tb-ink);
}
#tm-ai-overlay .tm-ai-head {align-items:flex-start;gap:14px;margin-bottom:23px}
#tm-ai-overlay .tm-ai-head h2 {font-size:29px;line-height:1.12;letter-spacing:-.045em;color:#123e2c}
#tm-ai-overlay .tm-ai-head p {font-size:14px;line-height:1.6;color:var(--tb-muted);max-width:36ch}
#tm-ai-overlay .tm-ux-kicker {
  display:inline-flex;gap:6px;align-items:center;
  font-size:11px;font-weight:850;letter-spacing:.09em;text-transform:uppercase;
  color:#165f44;background:#e8f5ed;border:1px solid #c4e3d1;
  padding:6px 10px;margin:0 0 12px;border-radius:999px;
}
#tm-ai-overlay #tm-ai-close {
  min-width:48px;min-height:48px;height:48px;width:48px;
  background:#f5f8f5;color:var(--tb-ink);border-color:#cbded0;
  flex:none;font-size:22px;
}
#tm-ai-overlay .tm-ux-hint {color:var(--tb-muted);font-size:13px;line-height:1.55;margin:6px 0 9px}
#tm-ai-overlay .tm-ai-field {margin-bottom:14px}
#tm-ai-overlay .tm-ai-field label {
  display:block;font-size:14px;line-height:1.45;color:#264638;
  font-weight:750;letter-spacing:0;text-transform:none;margin-bottom:7px;
}
#tm-ai-overlay .tm-ai-field input,
#tm-ai-overlay .tm-ai-field select,
#tm-ai-overlay .tm-ai-field textarea {
  font-size:16px;line-height:1.5;min-height:49px;
  padding:12px 13px;border:1.5px solid #bbd1c3;
  border-radius:12px;background:#fff;color:var(--tb-ink);
  box-shadow:none;transition:border-color .12s,box-shadow .12s;
}
#tm-ai-overlay #tm-ai-prompt {min-height:128px;resize:vertical}
#tm-ai-overlay .tm-ai-field input::placeholder,
#tm-ai-overlay .tm-ai-field textarea::placeholder {color:#657c70;opacity:1}
#tm-ai-overlay .tm-ux-examples {margin:1px 0 21px}
#tm-ai-overlay .tm-ux-examples-label {font-size:12px;font-weight:800;color:var(--tb-muted);margin-bottom:8px}
#tm-ai-overlay .tm-ux-examples-row {display:flex;gap:7px;flex-wrap:wrap}
#tm-ai-overlay .tm-ux-example {
  min-height:43px;padding:9px 12px;border:1px solid #bad8c8;
  border-radius:12px;background:#eef7f1;color:#164e37;
  font-size:13px;line-height:1.3;font-weight:700;cursor:pointer;
  text-align:left;white-space:normal;
}
#tm-ai-overlay .tm-ux-example:hover {background:#dff1e5;border-color:#77b28c}
#tm-ai-overlay .tm-ai-grid {grid-template-columns:1fr 1fr;gap:11px}
#tm-ai-overlay .tm-ai-grid>.tm-ai-field:first-child {grid-column:1/-1}
#tm-ai-overlay .tm-ux-advanced {
  margin:4px 0 18px;border:1px solid var(--tb-border);border-radius:14px;
  background:#f8faf8;overflow:hidden;
}
#tm-ai-overlay .tm-ux-advanced summary {
  cursor:pointer;list-style:none;display:flex;align-items:center;
  justify-content:space-between;gap:12px;min-height:50px;
  padding:12px 14px;font-size:14px;line-height:1.4;font-weight:800;color:#174d38;
}
#tm-ai-overlay .tm-ux-advanced summary::-webkit-details-marker {display:none}
#tm-ai-overlay .tm-ux-advanced summary::after {content:"＋";font-size:18px;font-weight:600}
#tm-ai-overlay .tm-ux-advanced[open] summary::after {content:"−"}
#tm-ai-overlay .tm-ux-advanced-body {border-top:1px solid var(--tb-border);padding:16px 13px 12px}
#tm-ai-overlay .tm-ux-advanced-fields {display:grid;grid-template-columns:1fr 1fr;gap:10px}
#tm-ai-overlay .tm-ux-advanced .tm-ai-field[style] {grid-column:auto!important}
#tm-ai-overlay .tm-ai-checks {margin:4px 0 0;gap:9px}
#tm-ai-overlay .tm-ai-check {
  min-height:48px;gap:10px;font-size:14px;line-height:1.4;
  border-color:#d0e2d6;background:white;padding:10px 11px;
  color:#264c38;
}
#tm-ai-overlay .tm-ai-check input {width:19px;height:19px;flex:none}
#tm-ai-overlay #tm-ai-generate {
  position:sticky;bottom:8px;z-index:3;width:100%;min-height:54px;
  background:var(--tb-green);font-size:16px;letter-spacing:0;
  border-radius:13px;box-shadow:0 8px 20px rgba(15,78,50,.20);
}
#tm-ai-overlay #tm-ai-generate:hover:not(:disabled) {background:var(--tb-green-dark)}
#tm-ai-overlay .tm-ux-cta-help {font-size:12px;color:#4c6858;text-align:center;margin:9px 0 13px;line-height:1.4}
#tm-ai-overlay #tm-ai-manual {
  color:var(--tb-green-dark);min-height:48px;font-size:14px;
  border:1px solid #ccdfd1;line-height:1.4;
}
#tm-ai-overlay .tm-ai-note {
  background:#edf4ef;border:1px solid #d4e4da;color:#36594b;
  font-size:13px;line-height:1.6;padding:12px 13px;margin-top:15px;
}
#tm-ai-overlay .tm-ai-empty {padding:32px 20px;min-height:310px;color:var(--tb-muted)}
#tm-ai-overlay .tm-ai-empty b {font-size:20px;line-height:1.35;color:#234c38}
#tm-ai-overlay .tm-ai-empty .icon {font-size:48px}
#tm-ai-overlay .tm-ai-progress {min-height:310px}
#tm-ai-overlay .tm-ai-progress h3 {font-size:20px;color:var(--tb-ink)}
#tm-ai-overlay .tm-ai-progress p {font-size:14px;line-height:1.6;color:var(--tb-muted)}
#tm-ai-overlay .tm-ai-titlebar {gap:14px;align-items:center}
#tm-ai-overlay .tm-ai-titlebar h2 {font-size:27px;line-height:1.2;color:var(--tb-ink)}
#tm-ai-overlay .tm-ai-titlebar p {font-size:14px;line-height:1.6;color:var(--tb-muted)}
#tm-ai-overlay .tm-ai-badges {gap:8px;margin:13px 0 18px}
#tm-ai-overlay .tm-ai-badge {font-size:12px;padding:7px 10px;color:#1c5d40}
#tm-ai-overlay .tm-ai-stats {gap:10px;margin:16px 0 20px}
#tm-ai-overlay .tm-ai-stat {padding:16px 13px;border-radius:14px;border-color:#d7e6dc}
#tm-ai-overlay .tm-ai-stat small {font-size:12px;line-height:1.4;color:#536c5e;font-weight:700;letter-spacing:0;text-transform:none}
#tm-ai-overlay .tm-ai-stat b {font-size:20px;color:#153b2a}
#tm-ai-overlay .tm-ai-section {margin-top:25px}
#tm-ai-overlay .tm-ai-section h3 {font-size:18px;line-height:1.4;color:#1b4c35;margin-bottom:10px}
#tm-ai-overlay .tm-ai-stage {
  position:relative;background:#fff;
  padding:16px 17px 17px 19px;border-radius:15px;
  border:1px solid #d7e6dc;border-left:4px solid #25825c;
}
#tm-ai-overlay .tm-ai-stage-head {align-items:baseline;flex-wrap:wrap}
#tm-ai-overlay .tm-ai-stage-head b {font-size:16px;line-height:1.45;color:var(--tb-ink)}
#tm-ai-overlay .tm-ai-stage-head span {font-size:13px;line-height:1.4;font-weight:750;color:#176347}
#tm-ai-overlay .tm-ai-stage p {font-size:14px;line-height:1.6;color:#385648;margin-top:8px}
#tm-ai-overlay .tm-ai-item {font-size:14px;line-height:1.6;padding:13px;border-color:#d7e6dc}
#tm-ai-overlay .tm-ai-item small {font-size:13px;line-height:1.55;color:#526e60}
#tm-ai-overlay .tm-ai-source,#tm-ai-overlay .tm-agent-source {
  min-height:44px;padding:11px;font-size:14px;line-height:1.5;
  border-radius:12px;color:#12573c;
}
#tm-ai-overlay .tm-ai-warning {
  font-size:14px;line-height:1.6;padding:14px 15px;
  color:#6b4211;background:#fff6e8;border-color:#e6c58b;
}
#tm-ai-overlay .tm-ai-actions {
  gap:10px;flex-wrap:wrap;
  background:linear-gradient(transparent,#f4f8f5 27%);
}
#tm-ai-overlay .tm-ai-actions button,
#tm-ai-overlay .tm-ai-map-btn,
#tm-ai-overlay #tm-ai-refine {
  min-height:48px;font-size:14px;border-radius:12px;line-height:1.4;
}
#tm-ai-overlay .tm-ai-map-btn {border-color:#b9d5c6;color:#145a3d}
#tm-ai-overlay #tm-ai-save,#tm-ai-overlay #tm-ai-refine {background:var(--tb-green);font-size:14px}
#tm-ai-overlay .tm-ai-refine-box {border-color:#d2e4d7;padding:16px;border-radius:15px}
#tm-ai-overlay .tm-ai-refine-box textarea {font-size:16px;min-height:95px;line-height:1.5}
#tm-ai-overlay .tm-v9-panel {border-radius:16px;border-color:#d0e3d5;padding:18px}
#tm-ai-overlay .tm-v9-head h3 {font-size:18px;line-height:1.4}
#tm-ai-overlay .tm-v9-score {padding:10px 12px}
#tm-ai-overlay .tm-v9-score b {font-size:24px}
#tm-ai-overlay .tm-v9-score span {font-size:12px}
#tm-ai-overlay .tm-v9-chip {font-size:13px;padding:7px 9px}
#tm-ai-overlay .tm-v9-grid {gap:10px}
#tm-ai-overlay .tm-v9-col {padding:12px;background:#fff;border-radius:12px}
#tm-ai-overlay .tm-v9-col h4 {font-size:14px;line-height:1.45}
#tm-ai-overlay .tm-v9-item,#tm-ai-overlay .tm-v9-empty {font-size:13px;line-height:1.55}
#tm-ai-overlay .tm-v9-feedback button,
#tm-ai-overlay .tm-v9-ask button {min-height:48px}
#tm-ai-overlay .tm-agent-q label {font-size:14px}
#tm-ai-overlay .tm-agent-q small {font-size:13px}
#tm-ai-overlay .tm-agent-q-option {min-height:44px;font-size:13px}
#tm-ai-overlay .tm-agent-research-meta {font-size:13px}
#tm-ai-overlay .tm-agent-source b {font-size:14px}
#tm-ai-overlay .tm-agent-source span {font-size:13px}
#tm-ai-overlay button:focus-visible,
#tm-ai-overlay input:focus-visible,
#tm-ai-overlay select:focus-visible,
#tm-ai-overlay textarea:focus-visible,
#tm-ai-overlay summary:focus-visible,
#tm-ai-overlay a:focus-visible {
  outline:3px solid var(--tb-focus)!important;outline-offset:3px;
}
@media(max-width:1040px) and (min-width:821px){
  #tm-ai-overlay .tm-ai-shell {grid-template-columns:minmax(295px,335px) minmax(0,1fr)}
  #tm-ai-overlay .tm-ai-side {padding:20px 17px}
  #tm-ai-overlay .tm-ai-result {padding:21px}
}
@media(max-width:820px){
  #tm-ai-overlay {padding:0!important}
  #tm-ai-overlay .tm-ai-shell {
    border:0;border-radius:20px 20px 0 0;
    height:calc(100dvh - env(safe-area-inset-top,0px) - 8px);
    max-height:calc(100dvh - env(safe-area-inset-top,0px));
    width:100%;
  }
  #tm-ai-overlay .tm-ai-side,
  #tm-ai-overlay .tm-ai-result {
    padding:25px 17px calc(32px + env(safe-area-inset-bottom,0px));
  }
  #tm-ai-overlay .tm-ai-head h2 {font-size:28px}
  #tm-ai-overlay .tm-ai-head {margin-bottom:20px}
  #tm-ai-overlay .tm-ai-stats {grid-template-columns:1fr 1fr}
  #tm-ai-overlay .tm-ai-titlebar {flex-wrap:wrap}
  #tm-ai-overlay #tm-ai-back {order:-1;flex:0 0 auto}
  #tm-ai-overlay .tm-v9-grid {grid-template-columns:1fr}
  #tm-ai-overlay .tm-ai-actions {padding-bottom:calc(12px + env(safe-area-inset-bottom,0px))}
  #tm-ai-overlay .tm-ai-checks {grid-template-columns:1fr 1fr}
}
@media(max-width:380px){
  #tm-ai-overlay .tm-ai-grid {grid-template-columns:1fr 1fr}
  #tm-ai-overlay .tm-ux-advanced-fields {grid-template-columns:1fr}
  #tm-ai-overlay .tm-ai-checks {grid-template-columns:1fr}
  #tm-ai-overlay .tm-ai-side,#tm-ai-overlay .tm-ai-result {padding-inline:14px}
  #tm-ai-overlay .tm-ai-stats {grid-template-columns:1fr 1fr}
}
@media(prefers-reduced-motion:reduce) {
  #tm-ai-overlay *,#tm-ai-overlay *::before,#tm-ai-overlay *::after {
    animation-duration:.01ms!important;transition-duration:.01ms!important;
    scroll-behavior:auto!important;
  }
}
</style>
<script id="trekbrain-evidence-ux-js">
(function(){
  "use strict";
  var overlay=document.getElementById("tm-ai-overlay");
  if(!overlay || overlay.dataset.tbEvidenceUx==="ready") return;
  var side=overlay.querySelector(".tm-ai-side");
  var result=overlay.querySelector(".tm-ai-result");
  var grid=side&&side.querySelector(".tm-ai-grid");
  var generate=document.getElementById("tm-ai-generate");
  var prompt=document.getElementById("tm-ai-prompt");
  if(!side || !result || !grid || !generate || !prompt) return;
  overlay.dataset.tbEvidenceUx="ready";
  var el=function(tag,className,text){
    var node=document.createElement(tag);
    if(className)node.className=className;
    if(text!==undefined)node.textContent=text;
    return node;
  };
  var title=side.querySelector(".tm-ai-head h2");
  if(title){
    var kicker=el("span","tm-ux-kicker","● Ton assistant randonnée");
    title.parentNode.insertBefore(kicker,title);
  }
  var modal=overlay.querySelector(".tm-ai-shell[role=dialog]");
  if(modal){
    modal.setAttribute("aria-label","TrekBrain, préparer et vérifier une randonnée");
    modal.setAttribute("aria-describedby","tm-ux-form-help");
  }
  var head=side.querySelector(".tm-ai-head p");
  if(head)head.textContent="Imagine ton itinéraire. TrekBrain cherche un parcours et vérifie les ressources utiles.";
  var fields=side.querySelectorAll(".tm-ai-field");
  Array.prototype.forEach.call(fields,function(field){
    var label=field.querySelector("label");
    var input=field.querySelector("input,select,textarea");
    if(label && input && input.id)label.htmlFor=input.id;
  });
  var region=document.getElementById("tm-ai-region");
  var days=document.getElementById("tm-ai-days");
  var km=document.getElementById("tm-ai-km");
  var regionLabel=region&&region.closest(".tm-ai-field").querySelector("label");
  if(regionLabel)regionLabel.textContent="Région ou massif (facultatif)";
  var daysLabel=days&&days.closest(".tm-ai-field").querySelector("label");
  if(daysLabel)daysLabel.textContent="Nombre de jours";
  var kmLabel=km&&km.closest(".tm-ai-field").querySelector("label");
  if(kmLabel)kmLabel.textContent="Kilomètres par jour";
  var promptLabel=prompt.closest(".tm-ai-field").querySelector("label");
  if(promptLabel)promptLabel.textContent="Décris ton trek";
  var help=el("p","tm-ux-hint","Un exemple suffit. Tu peux préciser les paysages, le rythme ou les transports.");
  help.id="tm-ux-form-help";
  prompt.setAttribute("aria-describedby",help.id);
  prompt.closest(".tm-ai-field").insertBefore(help,prompt);
  prompt.placeholder="Ex. Trois jours dans le Vercors, 16 km par jour, de beaux sentiers et un refuge le soir.";
  var examples=el("div","tm-ux-examples");
  var exampleLabel=el("div","tm-ux-examples-label","Pour commencer rapidement");
  var exampleRow=el("div","tm-ux-examples-row");
  var choices=[
    {label:"⛰️ Montagne",region:"Vercors",days:"3",km:"16",route:"Boucle",
      prompt:"Je cherche une boucle de 3 jours dans le Vercors, environ 16 km par jour, avec de beaux panoramas, de l'eau et un hébergement chaque soir."},
    {label:"🌿 Nature facile",region:"Morvan",days:"2",km:"12",route:"Boucle",
      prompt:"Propose une boucle de 2 jours dans le Morvan, environ 12 km par jour, avec des paysages calmes, de l'eau et du ravitaillement."},
    {label:"🚆 Sans voiture",region:"",days:"4",km:"18",route:"Traversée",
      prompt:"Je veux une traversée de 4 jours en France, environ 18 km par jour, avec une gare au départ et une à l'arrivée, de l'eau et des nuitées."}
  ];
  choices.forEach(function(choice){
    var button=el("button","tm-ux-example",choice.label);
    button.type="button";
    button.setAttribute("aria-label","Utiliser l'exemple "+choice.label.replace(/[⛰️🌿🚆]/gu,"").trim());
    button.addEventListener("click",function(){
      prompt.value=choice.prompt;
      if(region)region.value=choice.region;
      if(days)days.value=choice.days;
      if(km)km.value=choice.km;
      var route=document.getElementById("tm-ai-route-type");
      if(route)route.value=choice.route;
      prompt.focus();
      prompt.setSelectionRange(prompt.value.length,prompt.value.length);
      prompt.dispatchEvent(new Event("input",{bubbles:true}));
    });
    exampleRow.appendChild(button);
  });
  examples.appendChild(exampleLabel);
  examples.appendChild(exampleRow);
  prompt.closest(".tm-ai-field").insertAdjacentElement("afterend",examples);

  /* Keep all existing form IDs and default values. Only their visual grouping changes. */
  var difficulty=document.getElementById("tm-ai-difficulty");
  var routeType=document.getElementById("tm-ai-route-type");
  var checks=side.querySelector(".tm-ai-checks");
  if(difficulty && routeType && checks){
    var advanced=el("details","tm-ux-advanced");
    advanced.id="tm-ux-advanced";
    var summary=el("summary","","Personnaliser mon trek");
    summary.setAttribute("aria-label","Afficher les critères avancés et les ressources recherchées");
    var body=el("div","tm-ux-advanced-body");
    var advancedFields=el("div","tm-ux-advanced-fields");
    advancedFields.appendChild(difficulty.closest(".tm-ai-field"));
    advancedFields.appendChild(routeType.closest(".tm-ai-field"));
    body.appendChild(advancedFields);
    body.appendChild(checks);
    advanced.appendChild(summary);
    advanced.appendChild(body);
    side.insertBefore(advanced,generate);
  }
  var ctaHelp=el("p","tm-ux-cta-help","Gratuit · aucun itinéraire n'est garanti sans vérification du terrain.");
  generate.insertAdjacentElement("afterend",ctaHelp);
  generate.textContent="Créer mon itinéraire  →";
  var empty=document.getElementById("tm-ai-empty");
  if(empty){
    var bold=empty.querySelector("b");
    if(bold)bold.textContent="Ton aventure commence ici";
    var detail=empty.querySelector("div div");
    if(detail)detail.textContent="Décris ton trek à gauche. Le parcours et ses étapes apparaîtront ici.";
  }
  var progress=document.getElementById("tm-ai-progress");
  if(progress){
    progress.setAttribute("role","status");
    progress.setAttribute("aria-label","Préparation de ton itinéraire en cours");
    var changing=document.getElementById("tm-ai-progress-text");
    if(changing)changing.setAttribute("aria-live","off");
  }
  var lastTrigger=null;
  document.addEventListener("click",function(ev){
    var target=ev.target;
    if(!target || !target.closest)return;
    var opener=target.closest("#tm-ai-launch, #tm-mobile-nav [data-mobile-action=ai]");
    if(opener)lastTrigger=opener;
  },true);
  var wasOpen=overlay.classList.contains("open");
  new MutationObserver(function(){
    var opened=overlay.classList.contains("open");
    if(opened===wasOpen)return;
    wasOpen=opened;
    if(opened){
      setTimeout(function(){
        if(!overlay.classList.contains("open"))return;
        var onResult=window.innerWidth<=820&&overlay.querySelector(".tm-ai-shell.has-result");
        var target=onResult?document.getElementById("tm-ai-back"):prompt;
        if(target && target.getClientRects().length)target.focus();
      },100);
    }else if(lastTrigger && lastTrigger.isConnected){
      setTimeout(function(){lastTrigger.focus();},0);
    }
  }).observe(overlay,{attributes:true,attributeFilter:["class"]});
})();
</script>
<!-- TREKMAP_TREKBRAIN_UX_2026_END -->'''

if html.count("</body>") != 1:
    raise SystemExit("Unexpected TrekMap body marker")
html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekBrain research-informed responsive UX installed, one isolated block")
