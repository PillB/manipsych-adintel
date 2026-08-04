#!/usr/bin/env python3
"""Render a self-contained interactive HTML model-understanding report."""

from __future__ import annotations

import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


LABEL_NAMES = {
    "scarcity_urgency_pressure": "Urgency pressure",
    "reciprocity_obligation": "Reciprocity",
    "platform_migration": "Private-channel migration",
    "safety_and_privacy_multiplier": "Secrecy / privacy",
    "financial_emergency_multiplier": "Financial vulnerability",
    "confirmshaming_guilt_pressure": "Guilt pressure",
    "commitment_consistency_foot_in_door": "Incremental commitment",
    "education_and_career_aspiration_multiplier": "Education aspiration",
    "family_care_obligation_multiplier": "Family obligation",
    "status_and_respectability_multiplier": "Status / respectability",
    "paid_or_promoted_visibility_signal": "Paid / promoted",
    "repeat_or_high_volume_poster_signal": "Repeat poster",
    "social_engagement_signal": "Social engagement",
}


def _safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _fmt_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "n/a"


def render_html_report(
    ranking: dict[str, object],
    model_report: dict[str, object],
    rebuild_summary: dict[str, object],
    path: Path,
) -> None:
    rows = list(ranking.get("top_records", []))[:25]
    evaluation = model_report.get("evaluation_metrics", {})
    training = model_report.get("training_data", {})
    reject_counts = rebuild_summary.get("reject_counts", {})
    platform_counts = rebuild_summary.get("platform_counts", {})
    finding_counts = Counter(
        finding["tag"]
        for row in rows
        for finding in row.get("rule_findings", [])
        if finding.get("tag")
    )
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data = {
        "rows": rows,
        "labelNames": LABEL_NAMES,
        "platformCounts": platform_counts,
        "rejectCounts": reject_counts,
        "findingCounts": finding_counts,
        "metrics": evaluation,
    }
    total_raw = int(rebuild_summary.get("raw_files_scanned", 0))
    total_clean = int(rebuild_summary.get("records_written", 0))
    rejected = max(0, total_raw - total_clean)
    macro_f1 = float(evaluation.get("macro_f1", 0))
    micro_f1 = float(evaluation.get("micro_f1", 0))
    accuracy = float(evaluation.get("accuracy", 0))
    html_doc = f"""<!doctype html>
<html lang="en" class="scroll-smooth">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="Interactive audit of manipulation-risk ranking, model behavior, and data quality.">
  <title>ManiPsych | Model Intelligence Report</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    :root{{--ink:#17201d;--muted:#65716c;--paper:#f4f5f2;--panel:#fff;--line:#dce1dc;--red:#c83e4d;--amber:#d78a20;--green:#18755b;--blue:#3273a8}}
    *{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif;letter-spacing:0}}
    .shell{{max-width:1440px;margin:auto;padding:0 24px}} .panel{{background:var(--panel);border:1px solid var(--line);border-radius:8px}}
    .eyebrow{{font-size:11px;font-weight:750;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
    .metric{{font-variant-numeric:tabular-nums}} .tabular{{font-variant-numeric:tabular-nums}}
    .nav-link{{color:#4b5752;text-decoration:none;padding:8px 10px;border-radius:6px}} .nav-link:hover,.nav-link:focus-visible{{background:#e8ebe7;color:#111}}
    .risk-bar{{height:7px;background:#e8ebe7;border-radius:5px;overflow:hidden}} .risk-fill{{height:100%;background:linear-gradient(90deg,#d78a20,#c83e4d);transform-origin:left;animation:grow .7s ease-out both}}
    .chip{{display:inline-flex;align-items:center;gap:5px;padding:4px 7px;border:1px solid var(--line);border-radius:5px;background:#f8f9f7;font-size:12px}}
    .evidence{{background:#fff0a6;border-bottom:2px solid #d78a20;padding:0 2px;border-radius:2px}}
    .ad-row{{transition:background-color .16s ease,border-color .16s ease,transform .16s ease}} .ad-row:hover{{border-color:#aeb8b1;transform:translateY(-1px)}}
    .pipeline-node{{transition:transform .2s ease,box-shadow .2s ease}} .pipeline-node:hover{{transform:translateY(-3px);box-shadow:0 8px 20px #17201d12}}
    .fade-in{{animation:fade .45s ease-out both}} .delay-1{{animation-delay:.08s}} .delay-2{{animation-delay:.16s}}
    .chart-row{{display:grid;grid-template-columns:minmax(120px,1fr) 3fr 48px;align-items:center;gap:10px;margin:10px 0;font-size:13px}}
    .chart-track{{height:10px;background:#edf0ec;border-radius:3px;overflow:hidden}} .chart-fill{{height:100%;background:#3273a8;border-radius:3px}}
    dialog{{width:min(820px,calc(100% - 24px));max-height:90vh;padding:0;border:0;border-radius:8px;box-shadow:0 24px 80px #0005}} dialog::backdrop{{background:#17201db8;backdrop-filter:blur(2px)}}
    button,input,select{{font:inherit}} button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{{outline:3px solid #6aa9d5;outline-offset:2px}}
    .sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
    @keyframes grow{{from{{transform:scaleX(0)}}}} @keyframes fade{{from{{opacity:0;transform:translateY(7px)}}}}
    @media(max-width:760px){{.shell{{padding:0 14px}} .desktop-nav{{display:none!important}} #motionToggle{{padding:6px 8px;font-size:11px}} .chart-row{{grid-template-columns:110px 1fr 40px}}}}
    @media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto!important}} *,*::before,*::after{{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}}}
    @media print{{header,.controls,.detail-button{{display:none!important}} body{{background:#fff}} .panel{{break-inside:avoid}}}}
  </style>
</head>
<body>
<a href="#main" class="sr-only focus:not-sr-only">Skip to report</a>
<header class="sticky top-0 z-30 border-b border-[#dce1dc] bg-[#f4f5f2]/95 backdrop-blur">
  <div class="shell flex h-14 items-center justify-between gap-4">
    <a href="#overview" class="flex items-center gap-3 no-underline text-[#17201d]" aria-label="ManiPsych report home">
      <span class="grid h-8 w-8 place-items-center rounded-md bg-[#17201d] text-sm font-bold text-white">MP</span>
      <span><b>Model Intelligence</b><span class="hidden text-sm text-[#65716c] sm:inline"> / Ads audit</span></span>
    </a>
    <nav class="desktop-nav flex items-center gap-1 text-sm" aria-label="Report sections">
      <a class="nav-link" href="#pipeline">Pipeline</a><a class="nav-link" href="#health">Health</a><a class="nav-link" href="#rankings">Top 25</a><a class="nav-link" href="#method">Method</a>
    </nav>
    <button id="motionToggle" class="rounded-md border border-[#cbd2cc] bg-white px-3 py-1.5 text-xs font-semibold" type="button" aria-pressed="false">Pause motion</button>
  </div>
</header>
<main id="main">
  <section id="overview" class="border-b border-[#dce1dc] bg-white">
    <div class="shell grid min-h-[430px] content-center gap-10 py-16 lg:grid-cols-[1.35fr_.65fr]">
      <div class="fade-in">
        <p class="eyebrow">Defensive OSINT · Model audit · {html.escape(generated_at)}</p>
        <h1 class="mt-4 max-w-4xl text-4xl font-semibold leading-[1.05] md:text-6xl">How the system ranks persuasion and manipulation risk</h1>
        <p class="mt-6 max-w-3xl text-lg leading-8 text-[#53605b]">Trace each record from public-page collection through validation, redaction, weak supervision, ensemble scoring, and local evidence. This report separates observed evidence from model inference and makes uncertainty visible.</p>
        <div class="mt-7 flex flex-wrap gap-3">
          <a href="#rankings" class="rounded-md bg-[#17201d] px-4 py-2.5 text-sm font-semibold text-white no-underline">Inspect top-ranked ads</a>
          <a href="#method" class="rounded-md border border-[#bdc6bf] bg-white px-4 py-2.5 text-sm font-semibold text-[#17201d] no-underline">Review score method</a>
        </div>
      </div>
      <aside class="panel fade-in delay-1 p-6" aria-label="Report status">
        <div class="flex items-start justify-between"><div><p class="eyebrow">Audit status</p><p class="mt-2 text-xl font-semibold">Exploratory baseline</p></div><span class="rounded bg-[#fff1d6] px-2 py-1 text-xs font-bold text-[#86520b]">NOT CALIBRATED</span></div>
        <dl class="mt-8 grid grid-cols-2 gap-x-5 gap-y-6">
          <div><dt class="text-xs text-[#65716c]">Scored records</dt><dd class="metric mt-1 text-3xl font-semibold">{_fmt_int(ranking.get("total_records_scored"))}</dd></div>
          <div><dt class="text-xs text-[#65716c]">Top set shown</dt><dd class="metric mt-1 text-3xl font-semibold">{len(rows)}</dd></div>
          <div><dt class="text-xs text-[#65716c]">Macro F1</dt><dd class="metric mt-1 text-3xl font-semibold">{macro_f1:.3f}</dd></div>
          <div><dt class="text-xs text-[#65716c]">Platforms</dt><dd class="metric mt-1 text-3xl font-semibold">{len(platform_counts)}</dd></div>
        </dl>
        <p class="mt-7 border-t border-[#dce1dc] pt-5 text-sm leading-6 text-[#65716c]">Human-adjudicated labels and probability calibration are still required before operational use.</p>
      </aside>
    </div>
  </section>

  <section id="pipeline" class="py-16">
    <div class="shell">
      <p class="eyebrow">Data lineage</p><div class="mt-2 flex flex-wrap items-end justify-between gap-4"><h2 class="text-3xl font-semibold">From websites to ranked evidence</h2><p class="max-w-xl text-sm text-[#65716c]">Select a stage for inputs, outputs, controls, and failure signals.</p></div>
      <div class="mt-8 grid gap-3 md:grid-cols-2 xl:grid-cols-6" role="list" aria-label="Processing pipeline">
        {''.join(_pipeline_node(*node) for node in [
          ("01","Collect","Public HTML","2,372 files","blue"),
          ("02","Validate","Reject invalid","783 filtered","amber"),
          ("03","Protect","Redact + hash","PII removed","green"),
          ("04","Structure","JSONL manifest","1,589 records","blue"),
          ("05","Model","Rules + TF-IDF","13 labels","amber"),
          ("06","Explain","Rank + evidence","Top 25","green"),
        ])}
      </div>
      <div id="pipelineDetail" class="panel mt-4 min-h-[116px] p-5" aria-live="polite"><p class="eyebrow">Stage 01 · Collection</p><p class="mt-2 font-semibold">Public HTML archive</p><p class="mt-1 text-sm text-[#65716c]">Inputs are public, non-login pages from Locanto, Doplim, and publicly indexed Facebook content. Raw pages remain local.</p></div>
    </div>
  </section>

  <section id="health" class="border-y border-[#dce1dc] bg-white py-16">
    <div class="shell">
      <p class="eyebrow">Observability</p><h2 class="mt-2 text-3xl font-semibold">Data and model health</h2>
      <div class="mt-8 grid gap-4 md:grid-cols-3">
        {_metric_card("Ingestion yield", f"{(total_clean / total_raw * 100 if total_raw else 0):.1f}%", f"{total_clean:,} accepted / {total_raw:,} scanned", "green")}
        {_metric_card("Macro / micro F1", f"{macro_f1:.3f} / {micro_f1:.3f}", "Weak-label holdout; per-label balance differs", "blue")}
        {_metric_card("Exact-match accuracy", f"{accuracy:.3f}", "Strict multilabel metric; use with F1", "amber")}
      </div>
      <div class="mt-4 grid gap-4 lg:grid-cols-2">
        <div class="panel p-6"><div class="flex items-center justify-between"><div><p class="eyebrow">Coverage</p><h3 class="mt-1 text-lg font-semibold">Accepted records by platform</h3></div><span class="text-xs text-[#65716c]">{total_clean:,} total</span></div><div id="platformChart" class="mt-5" role="img" aria-label="Bar chart of accepted records by platform"></div></div>
        <div class="panel p-6"><div class="flex items-center justify-between"><div><p class="eyebrow">Quality gates</p><h3 class="mt-1 text-lg font-semibold">Rejected raw pages by reason</h3></div><span class="text-xs text-[#65716c]">{rejected:,} total</span></div><div id="rejectChart" class="mt-5" role="img" aria-label="Bar chart of rejected pages by reason"></div></div>
      </div>
      <div class="mt-4 grid gap-4 lg:grid-cols-[1.25fr_.75fr]">
        <div class="panel p-6"><p class="eyebrow">Top-set behavior</p><h3 class="mt-1 text-lg font-semibold">Observed rule evidence in the top 25</h3><div id="findingChart" class="mt-5"></div></div>
        <div class="panel border-l-4 border-l-[#d78a20] p-6"><p class="eyebrow">Known limitations</p><ul class="mt-4 space-y-3 text-sm leading-6 text-[#53605b]"><li><b>Weak labels:</b> rules generated training targets; metrics are not independent human validation.</li><li><b>Platform skew:</b> Locanto dominates the corpus, so repeated phrasing can inflate confidence.</li><li><b>Calibration absent:</b> probabilities rank relative evidence; they are not real-world likelihoods.</li><li><b>Text-only blind spots:</b> image-only persuasion and nuanced slang can be missed.</li></ul></div>
      </div>
    </div>
  </section>

  <section id="rankings" class="py-16">
    <div class="shell">
      <p class="eyebrow">Local explanations</p><h2 class="mt-2 text-3xl font-semibold">Top 25 ranked ads</h2>
      <div class="controls panel sticky top-[68px] z-20 mt-7 grid gap-3 p-3 md:grid-cols-[1fr_180px_180px_auto]">
        <label><span class="sr-only">Search ads and labels</span><input id="searchInput" type="search" placeholder="Search title, evidence, label…" class="h-10 w-full rounded-md border border-[#cbd2cc] bg-white px-3 text-sm"></label>
        <label><span class="sr-only">Filter platform</span><select id="platformFilter" class="h-10 w-full rounded-md border border-[#cbd2cc] bg-white px-3 text-sm"><option value="">All platforms</option></select></label>
        <label><span class="sr-only">Minimum risk score</span><select id="scoreFilter" class="h-10 w-full rounded-md border border-[#cbd2cc] bg-white px-3 text-sm"><option value="0">Any score</option><option value=".8">Score ≥ 0.80</option><option value=".85">Score ≥ 0.85</option></select></label>
        <button id="resetFilters" type="button" class="h-10 rounded-md border border-[#bdc6bf] bg-white px-4 text-sm font-semibold">Reset</button>
      </div>
      <div class="mt-4 flex items-center justify-between text-sm text-[#65716c]"><p id="resultCount" aria-live="polite"></p><p>Score: 0 low → 1 high</p></div>
      <div id="adList" class="mt-4 space-y-3"></div>
      <div id="emptyState" class="panel mt-4 hidden p-10 text-center"><p class="font-semibold">No ads match these filters.</p><button class="mt-3 text-sm underline" type="button" onclick="resetFilters()">Clear filters</button></div>
    </div>
  </section>

  <section id="method" class="border-t border-[#dce1dc] bg-[#17201d] py-16 text-white">
    <div class="shell grid gap-10 lg:grid-cols-[1fr_1fr]">
      <div><p class="eyebrow !text-[#9ca9a3]">Scoring method</p><h2 class="mt-2 text-3xl font-semibold">An interpretable hybrid, not a verdict</h2><p class="mt-5 max-w-xl leading-7 text-[#c7cfca]">The ranking combines deterministic evidence with a weak-supervised text classifier and aggregate context. The score orders review priority; it does not establish intent, harm, or identity.</p></div>
      <div class="grid gap-3 sm:grid-cols-2">
        {_weight_card("45%","Rule score","Matched phrases with visible evidence")}
        {_weight_card("35%","Model signal","Mean of top four discriminative labels")}
        {_weight_card("12%","Context signal","Highest visibility / engagement probability")}
        {_weight_card("8%","Record quality","Extraction completeness and source quality")}
      </div>
    </div>
    <div class="shell mt-10"><div class="rounded-md border border-[#3b4742] p-5 text-sm text-[#c7cfca]"><b class="text-white">Excluded from discriminative averaging:</b> ubiquitous financial-help and reciprocity labels, plus context labels. This reduces mechanical score inflation. Source text is redacted; identifiers are hashed.</div></div>
  </section>
</main>

<dialog id="detailDialog" aria-labelledby="dialogTitle"><div id="dialogContent"></div></dialog>
<footer class="border-t border-[#dce1dc] bg-white py-8"><div class="shell flex flex-wrap justify-between gap-4 text-xs text-[#65716c]"><p>ManiPsych defensive research report · Generated {html.escape(generated_at)}</p><p id="runtimeStatus">Runtime checks pending</p></div></footer>

<script id="reportData" type="application/json">{_safe_json(data)}</script>
<script>
const DATA=JSON.parse(document.getElementById('reportData').textContent);
const state={{query:'',platform:'',minScore:0}};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const label=s=>DATA.labelNames[s]||String(s).replaceAll('_',' ');
const pct=n=>`${{Math.round(Number(n)*100)}}%`;
const riskColor=n=>n>=.85?'#c83e4d':n>=.75?'#d78a20':'#3273a8';
function barChart(id,obj,color='#3273a8'){{
 const root=document.getElementById(id), entries=Object.entries(obj).sort((a,b)=>b[1]-a[1]), max=Math.max(...entries.map(x=>x[1]),1);
 root.innerHTML=entries.map(([k,v])=>`<div class="chart-row"><span title="${{esc(k)}}">${{esc(label(k))}}</span><div class="chart-track"><div class="chart-fill" style="width:${{v/max*100}}%;background:${{color}}"></div></div><b class="tabular text-right">${{v}}</b></div>`).join('');
}}
function highlighted(row){{
 let text=esc(row.excerpt), terms=[...new Set((row.rule_findings||[]).flatMap(x=>x.evidence||[]))].sort((a,b)=>b.length-a.length);
 for(const term of terms){{if(!term)continue; const rx=new RegExp(`(${{term.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&')}})`,'giu'); text=text.replace(rx,'<mark class="evidence">$1</mark>')}}
 return text;
}}
function renderRows(){{
 const q=state.query.toLowerCase();
 const rows=DATA.rows.filter(r=>!state.platform||r.source_platform===state.platform).filter(r=>r.overall_score>=state.minScore).filter(r=>!q||JSON.stringify(r).toLowerCase().includes(q));
 document.getElementById('resultCount').textContent=`Showing ${{rows.length}} of ${{DATA.rows.length}} records`;
 document.getElementById('emptyState').classList.toggle('hidden',rows.length>0);
 document.getElementById('adList').innerHTML=rows.map(r=>{{
  const rank=DATA.rows.indexOf(r)+1;
  return `<article class="ad-row panel p-5" data-record="${{esc(r.record_id)}}">
   <div class="grid gap-5 lg:grid-cols-[60px_1fr_190px]">
    <div><span class="eyebrow">Rank</span><p class="metric mt-1 text-3xl font-semibold">${{rank.toString().padStart(2,'0')}}</p></div>
    <div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><span class="chip">${{esc(r.source_platform)}}</span>${{(r.rule_findings||[]).slice(0,3).map(f=>`<span class="chip">${{esc(label(f.tag))}}</span>`).join('')}}</div>
     <h3 class="mt-3 text-lg font-semibold leading-6">${{esc(r.title)}}</h3><p class="mt-3 text-sm leading-7 text-[#53605b]">${{highlighted(r)}}</p>
     <button class="detail-button mt-4 text-sm font-semibold text-[#245f8c] underline decoration-[#9fc5df] underline-offset-4" onclick="openDetail('${{esc(r.record_id)}}')">Open full explanation</button>
    </div>
    <div class="border-t border-[#dce1dc] pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0"><div class="flex items-end justify-between"><span class="eyebrow">Overall risk</span><b class="metric text-3xl" style="color:${{riskColor(r.overall_score)}}">${{r.overall_score.toFixed(3)}}</b></div><div class="risk-bar mt-3"><div class="risk-fill" style="width:${{r.overall_score*100}}%"></div></div>
     <dl class="mt-5 space-y-2 text-xs"><div class="flex justify-between"><dt class="text-[#65716c]">Rule evidence</dt><dd class="font-semibold">${{Number(r.rule_score).toFixed(2)}}</dd></div><div class="flex justify-between"><dt class="text-[#65716c]">Record quality</dt><dd class="font-semibold">${{Number(r.quality_score).toFixed(2)}}</dd></div><div class="flex justify-between"><dt class="text-[#65716c]">Evidence tags</dt><dd class="font-semibold">${{r.rule_findings.length}}</dd></div></dl>
    </div>
   </div></article>`}}).join('');
}}
function openDetail(id){{
 const r=DATA.rows.find(x=>x.record_id===id), d=document.getElementById('detailDialog');
 document.getElementById('dialogContent').innerHTML=`<div class="sticky top-0 flex items-center justify-between border-b border-[#dce1dc] bg-white p-5"><div><p class="eyebrow">Rank ${{DATA.rows.indexOf(r)+1}} · local explanation</p><h2 id="dialogTitle" class="mt-1 font-semibold">${{esc(r.title)}}</h2></div><button onclick="document.getElementById('detailDialog').close()" class="grid h-9 w-9 place-items-center rounded-md border" aria-label="Close explanation">×</button></div>
 <div class="p-5"><div class="grid gap-3 sm:grid-cols-3"><div class="panel p-4"><p class="eyebrow">Overall</p><p class="metric mt-1 text-3xl font-semibold">${{r.overall_score.toFixed(3)}}</p></div><div class="panel p-4"><p class="eyebrow">Rule score</p><p class="metric mt-1 text-3xl font-semibold">${{Number(r.rule_score).toFixed(2)}}</p></div><div class="panel p-4"><p class="eyebrow">Quality</p><p class="metric mt-1 text-3xl font-semibold">${{Number(r.quality_score).toFixed(2)}}</p></div></div>
 <section class="mt-6"><p class="eyebrow">Annotated source excerpt</p><p class="mt-3 rounded-md bg-[#f4f5f2] p-4 text-sm leading-7">${{highlighted(r)}}</p><p class="mt-2 text-xs text-[#65716c]">Yellow marks are deterministic rule matches. Contact information is redacted.</p></section>
 <div class="mt-6 grid gap-6 md:grid-cols-2"><section><p class="eyebrow">Observed rule evidence</p><div class="mt-3 space-y-3">${{r.rule_findings.map(f=>`<div class="panel p-3"><div class="flex justify-between gap-2"><b class="text-sm">${{esc(label(f.tag))}}</b><span class="tabular text-xs">${{f.weight.toFixed(2)}} weight</span></div><p class="mt-1 text-xs text-[#65716c]">${{esc(f.rationale)}}</p><p class="mt-2 text-xs">Matched: ${{f.evidence.map(esc).join(', ')}}</p></div>`).join('')}}</div></section>
 <section><p class="eyebrow">Model-inferred labels</p><div class="mt-3 space-y-3">${{r.top_model_labels.map(x=>`<div><div class="mb-1 flex justify-between text-xs"><span>${{esc(label(x.label))}}</span><b>${{pct(x.probability)}}</b></div><div class="chart-track"><div class="chart-fill" style="width:${{x.probability*100}}%"></div></div></div>`).join('')}}<p class="mt-4 text-xs leading-5 text-[#65716c]">Probabilities are uncalibrated weak-supervision outputs and should be interpreted comparatively.</p></section></div>
 <section class="mt-6"><p class="eyebrow">Context and provenance</p><div class="mt-3 flex flex-wrap gap-2">${{r.context_model_labels.map(x=>`<span class="chip">${{esc(label(x.label))}} · ${{pct(x.probability)}}</span>`).join('')}}${{Object.entries(r.metadata_signals||{{}}).map(([k,v])=>`<span class="chip">${{esc(label(k))}} · ${{esc(v)}}</span>`).join('')}}</div><p class="mt-4 break-all font-mono text-[11px] text-[#65716c]">${{esc(r.record_id)}}</p></section></div>`;
 d.showModal();
}}
function resetFilters(){{document.getElementById('searchInput').value='';document.getElementById('platformFilter').value='';document.getElementById('scoreFilter').value='0';Object.assign(state,{{query:'',platform:'',minScore:0}});renderRows()}}
window.resetFilters=resetFilters; window.openDetail=openDetail;
const platformSelect=document.getElementById('platformFilter');
[...new Set(DATA.rows.map(x=>x.source_platform))].sort().forEach(x=>platformSelect.add(new Option(x,x)));
document.getElementById('searchInput').addEventListener('input',e=>{{state.query=e.target.value;renderRows()}});
platformSelect.addEventListener('change',e=>{{state.platform=e.target.value;renderRows()}});
document.getElementById('scoreFilter').addEventListener('change',e=>{{state.minScore=Number(e.target.value);renderRows()}});
document.getElementById('resetFilters').addEventListener('click',resetFilters);
const details=[
 ['Stage 01 · Collection','Public HTML archive','Inputs are public, non-login pages from Locanto, Doplim, and publicly indexed Facebook content. Raw pages remain local.'],
 ['Stage 02 · Validation','Reject blank, blocked, duplicate, and off-target pages','Coherence checks identify interstitials, tiny/corrupt pages, seeker-only content, low body text, and normalized duplicates.'],
 ['Stage 03 · Protection','PII redaction and stable hashing','Phone numbers, email addresses, and contact handles are redacted. Source and record identifiers are represented by hashes.'],
 ['Stage 04 · Structuring','Normalized JSONL manifest','Titles, redacted bodies, platform family, quality indicators, visibility markers, and aggregate engagement become structured fields.'],
 ['Stage 05 · Modeling','Hybrid rule and TF-IDF ensemble','Deterministic phrase rules provide evidence spans. One-vs-rest logistic regressions provide multilabel text probabilities; context metadata adds visibility signals.'],
 ['Stage 06 · Explanation','Ranked review queue with local evidence','A weighted score prioritizes review. The report separates direct matches, model inference, context, provenance, and known uncertainty.']
];
document.querySelectorAll('[data-stage]').forEach((el,i)=>el.addEventListener('click',()=>{{const x=details[i];document.getElementById('pipelineDetail').innerHTML=`<p class="eyebrow">${{x[0]}}</p><p class="mt-2 font-semibold">${{x[1]}}</p><p class="mt-1 text-sm text-[#65716c]">${{x[2]}}</p>`}}));
let paused=false;document.getElementById('motionToggle').addEventListener('click',e=>{{paused=!paused;document.documentElement.style.setProperty('--motion',paused?'paused':'running');document.querySelectorAll('*').forEach(x=>x.style.animationPlayState=paused?'paused':'running');e.currentTarget.textContent=paused?'Resume motion':'Pause motion';e.currentTarget.setAttribute('aria-pressed',String(paused))}});
document.getElementById('detailDialog').addEventListener('click',e=>{{if(e.target===e.currentTarget)e.currentTarget.close()}});
barChart('platformChart',DATA.platformCounts,'#18755b');barChart('rejectChart',DATA.rejectCounts,'#d78a20');barChart('findingChart',DATA.findingCounts,'#c83e4d');renderRows();
const checks=[DATA.rows.length===25,DATA.rows.every(r=>Array.isArray(r.rule_findings)),DATA.rows.every(r=>typeof r.overall_score==='number')];
document.getElementById('runtimeStatus').textContent=checks.every(Boolean)?'Runtime data checks: passed':'Runtime data checks: attention required';
</script>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")


def _pipeline_node(number: str, title: str, subtitle: str, stat: str, color: str) -> str:
    colors = {"blue": "#3273a8", "amber": "#d78a20", "green": "#18755b"}
    return f"""<button type="button" data-stage="{number}" class="pipeline-node panel min-h-[152px] p-5 text-left" role="listitem">
      <span class="eyebrow">{html.escape(number)}</span><span class="mt-4 block h-1 w-10 rounded" style="background:{colors[color]}"></span>
      <b class="mt-4 block">{html.escape(title)}</b><span class="mt-1 block text-xs text-[#65716c]">{html.escape(subtitle)}</span><span class="mt-3 block text-sm font-semibold">{html.escape(stat)}</span>
    </button>"""


def _metric_card(label: str, value: str, detail: str, color: str) -> str:
    colors = {"blue": "#3273a8", "amber": "#d78a20", "green": "#18755b"}
    return f"""<div class="panel border-t-4 p-5" style="border-top-color:{colors[color]}"><p class="eyebrow">{html.escape(label)}</p><p class="metric mt-2 text-3xl font-semibold">{html.escape(value)}</p><p class="mt-2 text-xs text-[#65716c]">{html.escape(detail)}</p></div>"""


def _weight_card(weight: str, label: str, detail: str) -> str:
    return f"""<div class="rounded-md border border-[#3b4742] p-4"><p class="metric text-2xl font-semibold">{html.escape(weight)}</p><p class="mt-1 text-sm font-semibold">{html.escape(label)}</p><p class="mt-1 text-xs leading-5 text-[#9ca9a3]">{html.escape(detail)}</p></div>"""
