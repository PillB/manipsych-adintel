#!/usr/bin/env python3
"""Generate a local, self-contained human annotation GUI.

The GUI is deliberately static/privacy-preserving: it reads embedded campaign
data, stores drafts in browser localStorage, and exports deterministic JSONL for
later import into the project SQLite store. Human reviewers see no council/model
suggestions until they submit their independent review for the selected record.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = ROOT / "data/annotation/documents.jsonl"
DEFAULT_SUGGESTIONS = ROOT / "data/annotation/council_resolved_annotations.jsonl"
DEFAULT_SCHEMA = ROOT / "data/annotation/label_schema.json"
DEFAULT_PRIMER = ROOT / "docs/ANNOTATOR_PRIMER.md"
DEFAULT_OUT = ROOT / "annotation_app/index.html"


LABEL_HELP = {
    "reciprocity_obligation": "Help, support, gifts, favors, or care framed to create obligation.",
    "conditional_financial_support": "Money or benefit conditional on companionship, intimacy, meetings, photos, or secrecy.",
    "transactional_ambiguity": "Euphemistic or vague exchange wording such as acuerdo, trato, beneficio mutuo.",
    "platform_migration": "Pressure to move to private/off-platform channels.",
    "privacy_or_secrecy_pressure": "Requests or promises discretion, secrecy, reserve, or concealment.",
    "scarcity_or_urgency": "Time pressure, limited availability, or urgent response framing.",
    "commitment_escalation": "Recurring or ongoing arrangement that may create dependency.",
    "foot_in_the_door": "Small initial ask or trial framed to reduce resistance.",
    "authority_or_status_appeal": "Profession, solvency, maturity, seriousness, or status used as appeal.",
    "social_proof": "References, popularity, testimonials, or many others participating.",
    "exclusivity_or_special_treatment": "Exclusive, special, chosen, or preferential status.",
    "guilt_or_shame_pressure": "Shame, blame, gatekeeping, or moral pressure.",
    "fear_or_threat": "Threat, intimidation, exposure, or negative consequences.",
    "deceptive_assurance": "Overconfident safety/risk-minimizing claims such as 100% seguro.",
    "sexualized_appearance_condition": "Appearance, body, photos, or sexualized presentation as condition/target.",
    "age_or_youth_targeting": "Youth, young women, minors, or narrow young-age targeting.",
    "education_or_student_targeting": "Student/school/university status or tuition dependency.",
    "economic_vulnerability_targeting": "Financial hardship, debt, urgent need, unemployment, or economic dependency.",
    "family_obligation_targeting": "Children, caregiving, family duty, or family expenses used as leverage.",
    "repetition_or_campaign_escalation": "Reposted/repeated campaign or persistence cues.",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def markdown_to_html(md: str) -> str:
    """Small deterministic Markdown subset renderer for the local tutorial."""
    lines = md.splitlines()
    out: list[str] = []
    list_open = False
    in_code = False
    code_lines: list[str] = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_list()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            close_list()
            continue
        if line.startswith("#"):
            close_list()
            level = min(4, len(line) - len(line.lstrip("#")))
            text = line[level:].strip()
            out.append(f"<h{level}>{html.escape(text)}</h{level}>")
            continue
        if line.startswith("- "):
            if not list_open:
                out.append("<ul>")
                list_open = True
            out.append("<li>" + html.escape(line[2:].strip()) + "</li>")
            continue
        if len(line) > 3 and line[0].isdigit() and ". " in line[:5]:
            close_list()
            out.append("<p>" + html.escape(line) + "</p>")
            continue
        close_list()
        out.append("<p>" + html.escape(line) + "</p>")
    close_list()
    return "\n".join(out)


def build_payload(docs_path: Path, suggestions_path: Path, schema_path: Path, primer_path: Path, limit: int | None) -> dict:
    docs = load_jsonl(docs_path)
    if limit:
        docs = docs[:limit]
    wanted = {doc["record_id"] for doc in docs}
    suggestions = {}
    for row in load_jsonl(suggestions_path):
        if row["record_id"] in wanted:
            suggestions[row["record_id"]] = {
                "accepted_round": row.get("accepted_round"),
                "agreement": row.get("agreement"),
                "document": row.get("document", {}),
                "spans": row.get("spans", []),
            }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    primer_md = primer_path.read_text(encoding="utf-8")
    primer_hash = hashlib.sha256(primer_md.encode("utf-8")).hexdigest()
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "docs": docs,
        "suggestions": suggestions,
        "schema": schema,
        "label_help": LABEL_HELP,
        "primer_html": markdown_to_html(primer_md),
        "primer_hash": primer_hash,
        "source_paths": {
            "documents": str(docs_path),
            "suggestions": str(suggestions_path),
            "schema": str(schema_path),
            "primer": str(primer_path),
        },
    }


def safe_json_script(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render(payload: dict, out: Path) -> None:
    page = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ManiPsych human annotation studio</title>
<style>
:root{--ink:#18231f;--muted:#66736f;--paper:#f7f5ee;--card:#fffefa;--line:#d8d0c2;--green:#2d6b4c;--amber:#c7812d;--red:#b4453c;--blue:#315d8c;--violet:#6b50a2;--shadow:0 18px 45px #17201d18}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#fff8e8,#eef4ef);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);overflow-x:hidden}button,input,select,textarea{font:inherit}button{cursor:pointer}.small{font-size:12px;color:var(--muted);line-height:1.45}.small,#docHead,#contextBox,.spanrow,.qitem{overflow-wrap:anywhere}.top{position:sticky;top:0;z-index:5;background:linear-gradient(135deg,#12201b,#2e563f);color:white;padding:14px min(4vw,52px);box-shadow:0 10px 32px #0002}.top h1{margin:0;font-size:clamp(24px,4vw,42px)}.toprow{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.btn,.chip{border:1px solid #ffffff42;background:#ffffff16;color:inherit;border-radius:999px;padding:8px 11px;font-weight:800;font-size:12px}.btn.dark{background:#17201d;color:white;border-color:#17201d}.btn.light{background:white;color:#17201d;border-color:var(--line)}.btn.warn{background:#fff1d9;color:#6f3b00;border-color:#edc98c}.shell{padding:16px min(4vw,52px);display:grid;grid-template-columns:310px minmax(360px,1fr) 390px;gap:14px;max-width:100vw;overflow-x:hidden}.panel{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:14px;box-shadow:var(--shadow);min-width:0}.panel h2,.panel h3{margin:0 0 8px}.queue{max-height:72vh;overflow:auto;display:grid;gap:8px}.qitem{width:100%;text-align:left;border:1px solid var(--line);background:white;border-radius:14px;padding:10px}.qitem[aria-current=true]{outline:3px solid #9bc4aa}.control{width:100%;border:1px solid var(--line);background:white;border-radius:12px;padding:9px 10px;margin:4px 0 10px}.text{white-space:pre-wrap;line-height:2.05;font-size:17px;max-height:64vh;overflow:auto;border:1px solid var(--line);background:white;border-radius:18px;padding:18px}.seg{border-radius:5px;padding:2px 1px;background:linear-gradient(transparent 56%,#f7cf78 56%,#f7cf78 72%,transparent 72%)}.seg.manip{background:linear-gradient(transparent 52%,#eda49d 52%,#eda49d 70%,transparent 70%),linear-gradient(transparent 74%,#93c5fd 74%,#93c5fd 88%,transparent 88%)}.row{display:grid;grid-template-columns:1fr 1fr;gap:8px}.spans{max-height:25vh;overflow:auto}.spanrow{border-bottom:1px solid #eee5d6;padding:9px 0}.labelgrid{display:grid;grid-template-columns:1fr;gap:6px;max-height:220px;overflow:auto}.labelbtn{border:1px solid var(--line);background:white;border-radius:12px;padding:8px;text-align:left}.labelbtn.active{background:#e7f2ea;border-color:#6aa078}.status{display:flex;gap:7px;flex-wrap:wrap;margin:8px 0}.tag{display:inline-flex;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:850;background:#eef2ef;color:#1f3a2e}.tag.red{background:#fae0dc;color:#7b241d}.tag.blue{background:#e2edf9;color:#213d65}.tag.amber{background:#f7ead7;color:#744512}.modal{position:fixed;inset:0;background:#0b1511cc;display:none;z-index:10;align-items:center;justify-content:center;padding:20px}.modal.open{display:flex}.dialog{background:#fffefa;color:var(--ink);border-radius:24px;max-width:1120px;width:100%;max-height:90vh;overflow:auto;box-shadow:0 30px 80px #0008}.dialog-head{position:sticky;top:0;background:#fffefa;border-bottom:1px solid var(--line);padding:14px 18px;display:flex;align-items:center;justify-content:space-between;gap:10px}.tutorial{padding:18px;display:grid;grid-template-columns:260px 1fr;gap:18px}.steps{position:sticky;top:70px;align-self:start;display:grid;gap:8px}.stepbtn{border:1px solid var(--line);background:white;border-radius:12px;padding:10px;text-align:left}.stepbtn.active{border-color:#6aa078;background:#e7f2ea}.lesson{line-height:1.62}.lesson h1{font-size:30px}.lesson h2{border-top:1px solid #eee2d4;padding-top:14px}.quiz{border:1px solid var(--line);border-radius:18px;padding:14px;background:#f8f4ea}.hidden{display:none!important}.suggestion{opacity:.92;border-left:4px solid var(--violet);padding-left:8px}.toast{position:fixed;right:16px;bottom:16px;background:#17201d;color:white;border-radius:14px;padding:12px 14px;box-shadow:var(--shadow);opacity:0;transform:translateY(8px);transition:.2s;z-index:20}.toast.show{opacity:1;transform:translateY(0)}.meter{height:9px;background:#e9e0d1;border-radius:999px;overflow:hidden}.meter>i{display:block;height:100%;background:linear-gradient(90deg,var(--green),var(--amber),var(--red))}
@media(max-width:1180px){.shell{grid-template-columns:290px 1fr}.right{grid-column:1/-1}.tutorial{grid-template-columns:1fr}.steps{position:static;grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.shell{display:block;padding:12px}.panel{margin-bottom:12px}.toprow{align-items:flex-start}.text{max-height:none}.row{grid-template-columns:1fr}.steps{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body>
<header class="top">
  <div class="toprow">
    <div><div class="small" style="color:#bde4cd">Human-first annotation · local browser storage · suggestions hidden until submit</div><h1>ManiPsych annotation studio</h1></div>
    <div><button id="openTutorial" class="btn" type="button">Training tutorial</button> <button id="exportBtn" class="btn" type="button">Export JSONL</button></div>
  </div>
</header>
<main class="shell">
  <aside class="panel">
    <h2>Work queue</h2>
    <label class="small" for="reviewer">Reviewer ID</label><input id="reviewer" class="control" value="reviewer_a">
    <label class="small" for="search">Search</label><input id="search" class="control" placeholder="record, label, text">
    <label class="small" for="platform">Platform</label><select id="platform" class="control"><option value="">All</option></select>
    <div class="status"><span id="progressTag" class="tag blue">0 reviewed</span><span id="savedTag" class="tag">autosave ready</span></div>
    <div class="meter" aria-label="Progress"><i id="progressBar" style="width:0%"></i></div>
    <p class="small">Shortcuts: / search, n/p next/previous, 1–9 label, s save draft, Enter submit, ? tutorial.</p>
    <div id="queue" class="queue" role="listbox" aria-label="Annotation queue"></div>
  </aside>
  <section class="panel">
    <div id="docHead"></div>
    <div id="textPanel" class="text" tabindex="0" aria-label="Ad text for span selection"></div>
    <div class="status">
      <button id="addSpan" class="btn dark" type="button">Add selected span</button>
      <button id="undo" class="btn light" type="button">Undo</button>
      <button id="redo" class="btn light" type="button">Redo</button>
      <button id="negative" class="btn warn" type="button">Mark negative</button>
      <button id="saveDraft" class="btn light" type="button">Save draft</button>
      <button id="submitReview" class="btn dark" type="button">Submit independent review</button>
    </div>
    <div id="selectionInfo" class="small">Select text, choose a label, then add the span.</div>
    <h3>Current spans</h3><div id="spanList" class="spans"></div>
  </section>
  <aside class="panel right">
    <h2>Annotation controls</h2>
    <label class="small" for="label">Selected label</label><select id="label" class="control"></select>
    <div id="labelGrid" class="labelgrid"></div>
    <div class="row">
      <label class="small">Intensity 0–4<input id="intensity" class="control" type="number" min="0" max="4" value="3" aria-label="Intensity 0 to 4"></label>
      <label class="small">Manip 0–3<input id="manip" class="control" type="number" min="0" max="3" value="2" aria-label="Manipulativeness 0 to 3"></label>
      <label class="small">Harm 0–3<input id="harm" class="control" type="number" min="0" max="3" value="2" aria-label="Harm risk 0 to 3"></label>
      <label class="small">Explicitness<select id="explicitness" class="control" aria-label="Explicitness"><option>explicit</option><option>implicit</option><option>unclear</option></select></label>
    </div>
    <label class="small" for="vulnerability">Vulnerability target</label><input id="vulnerability" class="control" placeholder="economic, student, age_youth">
    <label class="small" for="rationale">Rationale</label><textarea id="rationale" class="control" rows="4" placeholder="Why this exact span supports the label"></textarea>
    <h3>Guideline lookup</h3><div id="help" class="small"></div>
    <h3>Context layer</h3><div id="contextBox" class="small"></div>
    <h3>Suggestions after submit</h3><div id="suggestions" class="small"></div>
  </aside>
</main>
<section id="tutorialModal" class="modal" aria-modal="true" role="dialog" aria-label="Annotator training tutorial">
  <div class="dialog">
    <div class="dialog-head"><h2 style="margin:0">Annotator training tutorial</h2><div><button id="completeTraining" class="btn dark" type="button">Complete training</button> <button id="closeTutorial" class="btn light" type="button">Close</button></div></div>
    <div class="tutorial"><nav id="tutorialSteps" class="steps" aria-label="Tutorial sections"></nav><article id="lesson" class="lesson"></article></div>
  </div>
</section>
<div id="toast" class="toast" role="status" aria-live="polite"></div>
<script id="appData" type="application/json">__DATA__</script>
<script>
const payload = JSON.parse(document.getElementById('appData').textContent);
const docs = payload.docs, suggestions = payload.suggestions, schema = payload.schema, labelHelp = payload.label_help;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let idx=0, currentRows=[], spans=[], redoStack=[], historyStack=[], selectedLabel=schema.labels[0], selectedRange=null, negative=false;
const key = () => `manipsych.annotation.${$('reviewer').value.trim()||'reviewer'}`;
const state = () => JSON.parse(localStorage.getItem(key())||'{}');
function setState(s){localStorage.setItem(key(), JSON.stringify(s));}
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1700)}
function recordState(){historyStack.push(JSON.stringify({spans,negative})); if(historyStack.length>80) historyStack.shift(); redoStack=[];}
function restore(serial){const s=JSON.parse(serial); spans=s.spans||[]; negative=!!s.negative; renderDoc();}
function currentDoc(){return currentRows[idx] || docs[0];}
function savedFor(id){return state()[id] || {state:'unreviewed',spans:[],document:{}};}
function saveRecord(status='draft'){
  const doc=currentDoc(), s=state();
  const document={persuasive_intensity:maxVal('intensity',4),manipulativeness:maxVal('manip',3),harm_risk:maxVal('harm',3),explicitness:$('explicitness').value,negative_example:negative,adjudication_state:status==='submitted'?'reviewed':'unreviewed'};
  s[doc.record_id]={record_id:doc.record_id,reviewer_id:$('reviewer').value.trim()||'reviewer',layer:'human',state:status,text_hash:doc.text_hash,updated_at:new Date().toISOString(),document,spans};
  setState(s); $('savedTag').textContent=status==='submitted'?'submitted':'draft saved'; updateProgress(); renderQueue(); renderSuggestions(); toast(status==='submitted'?'Submitted; suggestions unlocked for this ad':'Draft saved locally');
}
function maxVal(id,max){return Math.max(0,Math.min(max,Number($(id).value)||0))}
function renderFilters(){
  const plats=[...new Set(docs.map(d=>d.platform))].sort();
  $('platform').innerHTML='<option value="">All</option>'+plats.map(p=>`<option>${esc(p)}</option>`).join('');
  $('label').innerHTML=schema.labels.map(l=>`<option>${esc(l)}</option>`).join('');
  $('labelGrid').innerHTML=schema.labels.map((l,i)=>`<button class="labelbtn" data-label="${esc(l)}" type="button"><b>${i<9?i+1+'. ':''}${esc(l.replaceAll('_',' '))}</b><br><span class="small">${esc(labelHelp[l]||'')}</span></button>`).join('');
}
function rows(){
  const q=$('search').value.toLowerCase(), p=$('platform').value;
  return docs.filter(d=>(!p||d.platform===p)&&(!q||(d.record_id+' '+d.text+' '+d.platform).toLowerCase().includes(q)));
}
function renderQueue(){
  currentRows=rows(); if(idx>=currentRows.length) idx=0;
  const s=state();
  $('queue').innerHTML=currentRows.slice(0,300).map((d,i)=>`<button class="qitem" role="option" aria-current="${i===idx}" onclick="selectDoc(${i})"><div class="small">#${i+1} · ${esc(d.platform)} · ${esc(d.split)} · ${savedFor(d.record_id).state}</div><b>${esc(d.text.split('\\n')[0].slice(0,90))}</b></button>`).join('');
  updateProgress();
}
window.selectDoc=i=>{saveRecord('draft'); idx=i; loadDoc();};
function loadDoc(){
  const doc=currentDoc(), saved=savedFor(doc.record_id);
  spans=structuredClone(saved.spans||[]); negative=!!saved.document?.negative_example; historyStack=[]; redoStack=[]; renderDoc(); renderQueue();
}
function activeClass(span){return ['conditional_financial_support','economic_vulnerability_targeting','privacy_or_secrecy_pressure','guilt_or_shame_pressure','deceptive_assurance','fear_or_threat'].includes(span.label)?'seg manip':'seg'}
function renderText(text, marks){
  const cuts=new Set([0,text.length]); marks.forEach(s=>(s.segments||[]).forEach(([a,b])=>{if(a>=0&&b<=text.length&&a<b){cuts.add(a);cuts.add(b)}}));
  const pts=[...cuts].sort((a,b)=>a-b); let out='';
  for(let i=0;i<pts.length-1;i++){const a=pts[i],b=pts[i+1],piece=text.slice(a,b); if(!piece) continue; const active=marks.filter(s=>(s.segments||[]).some(([x,y])=>a>=x&&b<=y)); out+=active.length?`<span class="${active.some(s=>activeClass(s).includes('manip'))?'seg manip':'seg'}" title="${esc(active.map(s=>s.label).join(', '))}">${esc(piece)}</span>`:esc(piece);}
  return out;
}
function renderDoc(){
  const doc=currentDoc();
  $('docHead').innerHTML=`<div class="small">${esc(doc.record_id)} · ${esc(doc.platform)} · ${esc(doc.split)} · hash ${esc(doc.text_hash.slice(0,12))}</div><h2 style="margin:.2rem 0">${esc(doc.text.split('\\n')[0])}</h2><div class="status"><span class="tag blue">${spans.length} spans</span><span class="tag ${negative?'amber':''}">${negative?'negative example':'positive/unknown'}</span></div>`;
  $('textPanel').innerHTML=renderText(doc.text,spans);
  $('spanList').innerHTML=spans.map((s,i)=>`<div class="spanrow"><span class="tag ${activeClass(s).includes('manip')?'red':'amber'}">${i+1}. ${esc(s.label)}</span><p>${esc(s.exact_text)}</p><p class="small">offsets ${esc(JSON.stringify(s.segments))} · intensity ${s.intensity} · manip ${s.manipulativeness} · harm ${s.harm_risk} · ${esc(s.rationale||'')}</p><button class="btn light" type="button" onclick="deleteSpan(${i})">Delete</button></div>`).join('')||'<p class="small">No spans yet.</p>';
  $('contextBox').innerHTML=Object.entries(doc.context||{}).map(([k,v])=>`<div><b>${esc(k)}</b>: ${esc(JSON.stringify(v))}</div>`).join('');
  renderSuggestions(); updateSelectionInfo();
}
window.deleteSpan=i=>{recordState(); spans.splice(i,1); negative=false; renderDoc(); saveRecord('draft')};
function setLabel(label){selectedLabel=label;$('label').value=label;document.querySelectorAll('.labelbtn').forEach(b=>b.classList.toggle('active',b.dataset.label===label));$('help').innerHTML=`<b>${esc(label)}</b><p>${esc(labelHelp[label]||'')}</p>`}
function offsetFor(node,offset){
  const root=$('textPanel'); const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT); let pos=0,n;
  while(n=walker.nextNode()){if(n===node)return pos+offset;pos+=n.nodeValue.length} return 0;
}
function captureSelection(){
  const sel=window.getSelection(); if(!sel||sel.rangeCount===0||sel.isCollapsed){selectedRange=null;updateSelectionInfo();return}
  const r=sel.getRangeAt(0); if(!$('textPanel').contains(r.commonAncestorContainer)){selectedRange=null;updateSelectionInfo();return}
  let a=offsetFor(r.startContainer,r.startOffset), b=offsetFor(r.endContainer,r.endOffset); if(a>b)[a,b]=[b,a];
  const doc=currentDoc(), exact=doc.text.slice(a,b); selectedRange=exact.trim()?{start:a,end:b,exact}:null; updateSelectionInfo();
}
window.__annotationTestSelect=(a,b)=>{const doc=currentDoc(); selectedRange={start:a,end:b,exact:doc.text.slice(a,b)}; updateSelectionInfo();};
function updateSelectionInfo(){ $('selectionInfo').textContent=selectedRange?`Selected [${selectedRange.start}, ${selectedRange.end}): “${selectedRange.exact.slice(0,120)}”`:'Select text, choose a label, then add the span.'; }
function addSelectedSpan(){
  if(!selectedRange){toast('Select text first');return}
  const doc=currentDoc(), exact=doc.text.slice(selectedRange.start,selectedRange.end);
  if(exact!==selectedRange.exact){toast('Selection changed; reselect');return}
  recordState(); spans.push({label:selectedLabel,segments:[[selectedRange.start,selectedRange.end]],exact_text:exact,rationale:$('rationale').value.trim(),intensity:maxVal('intensity',4),manipulativeness:maxVal('manip',3),harm_risk:maxVal('harm',3),explicitness:$('explicitness').value,vulnerability_target:$('vulnerability').value.trim(),provenance:$('reviewer').value.trim()||'reviewer'});
  negative=false; selectedRange=null; window.getSelection()?.removeAllRanges(); renderDoc(); saveRecord('draft');
}
function renderSuggestions(){
  const doc=currentDoc(), saved=savedFor(doc.record_id), sug=suggestions[doc.record_id];
  if(saved.state!=='submitted'){$('suggestions').innerHTML='<p>Hidden until this reviewer submits an independent review for this ad.</p>';return}
  if(!sug){$('suggestions').innerHTML='<p>No council suggestions embedded.</p>';return}
  $('suggestions').innerHTML=`<p class="suggestion">Council round ${esc(sug.accepted_round)} · agreement ${esc(sug.agreement)} · ${sug.spans.length} spans</p>`+sug.spans.slice(0,20).map((s,i)=>`<div class="spanrow"><b>${i+1}. ${esc(s.label)}</b><br>${esc(s.exact_text)}<br><span class="small">${esc(s.rationale||'')}</span></div>`).join('');
}
function updateProgress(){
  const s=state(), total=docs.length, submitted=docs.filter(d=>s[d.record_id]?.state==='submitted').length;
  $('progressTag').textContent=`${submitted}/${total} submitted`; $('progressBar').style.width=`${(submitted/Math.max(1,total))*100}%`;
}
function exportJsonl(){
  const rows=Object.values(state()).filter(r=>r.record_id).sort((a,b)=>a.record_id.localeCompare(b.record_id));
  const text=rows.map(r=>JSON.stringify(r)).join('\\n')+'\\n';
  const blob=new Blob([text],{type:'application/jsonl'}), url=URL.createObjectURL(blob), a=document.createElement('a');
  a.href=url; a.download=`manipsych_${$('reviewer').value.trim()||'reviewer'}_annotations.jsonl`; a.click(); URL.revokeObjectURL(url); toast(`Exported ${rows.length} records`);
}
const tutorialSections=[
  ['Mission','<h1>Start here</h1><p>This tutorial trains independent human review. Suggestions stay hidden until you submit the current ad.</p><div class="quiz"><b>Rule:</b> label exact evidence, not suspicion. Context signals stay separate.</div>'],
  ['Scales','<h2>Scales</h2><p>Intensity 0–4 measures persuasive force. Manipulativeness 0–3 measures pressure, concealment, vulnerability exploitation, or coercion. Harm 0–3 measures plausible risk.</p><p>Use the highest-risk span to guide document-level values.</p>'],
  ['Labels',payload.primer_html],
  ['Practice','<h2>Practice</h2><div class="quiz"><p><b>Item:</b> “Apoyo a universitaria con apuros, a cambio de salidas discretas.”</p><button class="btn dark" onclick="document.getElementById(\\'quizAnswer\\').classList.toggle(\\'hidden\\')">Show answer</button><div id="quizAnswer" class="hidden"><ul><li>Apoyo: reciprocity_obligation</li><li>universitaria: education_or_student_targeting</li><li>apuros: economic_vulnerability_targeting</li><li>a cambio de salidas: conditional_financial_support</li><li>discretas: privacy_or_secrecy_pressure</li></ul></div></div>'],
  ['Workflow','<h2>Workflow</h2><ol><li>Read the whole ad.</li><li>Select the smallest supporting phrase.</li><li>Choose label and scales.</li><li>Add span, save draft, then submit.</li><li>Only after submit, compare suggestions.</li></ol>']
];
function renderTutorial(i=0){$('tutorialSteps').innerHTML=tutorialSections.map((s,j)=>`<button class="stepbtn ${i===j?'active':''}" onclick="renderTutorial(${j})">${j+1}. ${esc(s[0])}</button>`).join('');$('lesson').innerHTML=tutorialSections[i][1];}
$('textPanel').addEventListener('mouseup',captureSelection); $('textPanel').addEventListener('keyup',captureSelection);
$('addSpan').onclick=addSelectedSpan; $('saveDraft').onclick=()=>saveRecord('draft'); $('submitReview').onclick=()=>saveRecord('submitted'); $('negative').onclick=()=>{recordState();spans=[];negative=true;renderDoc();saveRecord('draft')}; $('exportBtn').onclick=exportJsonl;
$('undo').onclick=()=>{if(historyStack.length){redoStack.push(JSON.stringify({spans,negative}));restore(historyStack.pop())}}; $('redo').onclick=()=>{if(redoStack.length){historyStack.push(JSON.stringify({spans,negative}));restore(redoStack.pop())}};
$('reviewer').addEventListener('change',()=>{loadDoc();renderQueue()}); ['search','platform'].forEach(id=>$(id).addEventListener('input',()=>{idx=0;renderQueue();loadDoc()})); $('label').addEventListener('change',e=>setLabel(e.target.value));
$('labelGrid').addEventListener('click',e=>{const b=e.target.closest('.labelbtn'); if(b)setLabel(b.dataset.label)});
$('openTutorial').onclick=()=>{$('tutorialModal').classList.add('open');renderTutorial(0)}; $('closeTutorial').onclick=()=>{$('tutorialModal').classList.remove('open')}; $('completeTraining').onclick=()=>{localStorage.setItem('manipsych.training.complete',payload.primer_hash);$('tutorialModal').classList.remove('open');toast('Training marked complete')};
document.addEventListener('keydown',e=>{const typing=['INPUT','TEXTAREA','SELECT'].includes(e.target?.tagName); if(e.key==='Escape'){document.activeElement?.blur?.();return} if(e.key==='?'&&!typing){$('openTutorial').click()} if(e.key==='/'&&!typing){e.preventDefault();$('search').focus()} if(typing)return; if(e.key==='n'){saveRecord('draft');idx=Math.min(idx+1,currentRows.length-1);loadDoc()} if(e.key==='p'){saveRecord('draft');idx=Math.max(idx-1,0);loadDoc()} if(e.key==='s'){saveRecord('draft')} if(e.key==='Enter'){saveRecord('submitted')} if(/^[1-9]$/.test(e.key)){const l=schema.labels[Number(e.key)-1]; if(l)setLabel(l)}});
renderFilters(); setLabel(selectedLabel); renderQueue(); loadDoc(); if(localStorage.getItem('manipsych.training.complete')!==payload.primer_hash){$('tutorialModal').classList.add('open');renderTutorial(0)}
</script>
</body>
</html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page.replace("__DATA__", safe_json_script(payload)), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--suggestions", type=Path, default=DEFAULT_SUGGESTIONS)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--primer", type=Path, default=DEFAULT_PRIMER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None, help="Optional record limit for lightweight test builds")
    args = parser.parse_args()
    payload = build_payload(args.documents, args.suggestions, args.schema, args.primer, args.limit)
    render(payload, args.out)
    print(json.dumps({"out": str(args.out), "records": len(payload["docs"]), "primer_hash": payload["primer_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
