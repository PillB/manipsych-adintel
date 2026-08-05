#!/usr/bin/env python3
"""Generate the interactive ad analyzer + adversarial GAN section as a
self-contained HTML page. This page:

1. INTERACTIVE AD ANALYZER: User types ad text, system tags techniques live
   using the adintel.profile and adintel.taxonomy modules (compiled to JS).
2. ADVERSARIAL GAN: Generate synthetic ad variants using detected techniques,
   then re-detect to see if the detector improves. The loop is:
   detect → generate → detect → score → improve.
3. TECHNIQUE PLAYGROUND: Shows which techniques are detected, with confidence
   and evidence spans, in real time.

This is a CLIENT-SIDE page (no server needed) that mirrors the Python
adintel.profile signal patterns in JavaScript for instant feedback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adintel import taxonomy as tx

OUT = ROOT / "docs" / "interactive_analyzer.html"


def build_signals_js() -> str:
    """Convert the Python profile signals to JS for client-side scoring."""
    # Use string patterns + new RegExp() to avoid regex literal serialization issues
    # Use raw string r""" to prevent Python from eating backslashes
    return r"""
const SIGNALS = {
  urgency: [
    ['urgente|ahora|ya|hoy|inmediato|rápidito|rapidito|ya mismo', 'gi', 0.30, 'urgency word'],
    ['solo por (hoy|esta noche|esta semana)', 'gi', 0.25, 'limited-time urgency'],
    ['último|última|ultima|ultimos|últimos', 'gi', 0.20, 'last-chance word'],
    ['no (esperes|tardes|dejes)', 'gi', 0.20, 'imperative urgency'],
    ['today|now|tonight only|last chance|hurry', 'gi', 0.20, 'english urgency'],
  ],
  scarcity: [
    ['solo|único|única|unico|unica|limitad|pocos|pocas|un cupo|un lugar', 'gi', 0.25, 'scarcity word'],
    ['pocas? (vacantes|opciones|chicas?|cupo)', 'gi', 0.30, 'specific scarcity'],
    ['solo [0-9]+', 'gi', 0.30, 'numeric scarcity'],
    ['limited|only [0-9]+|while (supplies|slots) last', 'gi', 0.25, 'english scarcity'],
  ],
  emotional_intensity: [
    ['amor|cariño|afecto|corazón|amistad|sincero|sincera', 'gi', 0.15, 'warmth word'],
    ['triste|sola|solo|deprimida|abandonada|abandonado|necesitad', 'gi', 0.30, 'vulnerability word'],
    ['miedo|peligro|riesgo|amenaza|inseguridad', 'gi', 0.30, 'fear word'],
    ['esperanza|sueña|sueño|futuro|mejorar|salir adelante', 'gi', 0.20, 'hope word'],
    ['vergüenza|humillad|culpable|deberías|deberias', 'gi', 0.30, 'shame word'],
  ],
  directiveness: [
    ['escríbeme|escribeme|mandame|llámame|llamame|envíame|enviame', 'gi', 0.30, 'imperative contact'],
    ['hazlo|hazlo ya|no (esperes|dudes|tardes)', 'gi', 0.25, 'imperative action'],
    ['debes|tienes que|tenés que|no (dejes|pierdas)', 'gi', 0.25, 'obligation modal'],
    ['whatsapp|wsp|telegram|inbox|dm|privado', 'gi', 0.20, 'channel directive'],
  ],
  certainty: [
    ['seguro|segura|garantizado|garantizada|100%|cien por ciento|real|verdadero', 'gi', 0.25, 'certainty word'],
    ['comprobado|verificado|avalado|respaldado', 'gi', 0.25, 'verified claim'],
    ['sin riesgo|sin peligros|confiable', 'gi', 0.20, 'no-risk claim'],
  ],
  manipulation_risk: [
    ['necesitad|urgente|no tienes|debes|tienes que|por tu familia|si de verdad', 'gi', 0.25, 'pressure+vulnerability'],
    ['chicas? +(de )?(18|19|20)|estudiantes?|alumnas?', 'gi', 0.30, 'youth targeting'],
    ['ayuda +económica|ayuda economica', 'gi', 0.10, 'transactional euphemism'],
    ['buena presencia|guapa|figura|cuerpo|attractive', 'gi', 0.25, 'appearance condition'],
  ],
  platform_migration: [
    ['whatsapp|wsp|telegram|inbox|dm|privado|escríbeme|escribeme', 'gi', 0.25, 'channel migration cue'],
  ],
  privacy_or_secrecy_pressure: [
    ['discreto|discreta|secreto|sin que nadie|confidencial|privado', 'gi', 0.25, 'secrecy cue'],
  ],
  financial_lure: [
    ['ayuda +económica|ayuda economica|dinero|soles|pago|apoyo +economic', 'gi', 0.25, 'financial lure'],
  ],
  authority_or_status_appeal: [
    ['serio|seria|profesional|empresario|solvente|ejecutivo|formal', 'gi', 0.25, 'authority claim'],
  ],
  age_or_youth_targeting: [
    ['joven|señorita|chica|18|19|20 +años', 'gi', 0.25, 'age targeting'],
  ],
  education_or_student_targeting: [
    ['estudiante|universitaria|alumna|instituto|colegio', 'gi', 0.25, 'student targeting'],
  ],
  sexualized_appearance_condition: [
    ['buena presencia|guapa|linda|figura|cuerpo|atractiva', 'gi', 0.25, 'appearance condition'],
  ],
  scarcity_or_urgency: [
    ['urgente|hoy|ya|inmediato|rápido|último|solo por', 'gi', 0.25, 'urgency/scarcity'],
  ],
  reciprocity_obligation: [
    ['ayuda|brindo|ofrezco|favor|regalo|apoyo', 'gi', 0.15, 'reciprocity framing'],
  ],
  deceptive_assurance: [
    ['seguro|garantizado|confiable|real|sin riesgo|serio', 'gi', 0.20, 'assurance claim'],
  ],
  social_proof: [
    ['muchos|muchas|varios|todos|recomendado|popular', 'gi', 0.20, 'social proof'],
  ],
  commitment_escalation: [
    ['constante|permanente|semanal|mensual|fijo|regular', 'gi', 0.25, 'commitment escalation'],
  ],
};

function scoreWithSignals(text, patterns) {
  let rawScore = 0;
  const hits = [];
  for (let i = 0; i < patterns.length; i++) {
    const pattern = patterns[i];
    const patternStr = pattern[0];
    const flags = pattern[1];
    const weight = pattern[2];
    const label = pattern[3];
    const regex = new RegExp(patternStr, flags);
    const matches = String(text).match(regex);
    if (matches) {
      const capped = matches.slice(0, 3);
      for (let j = 0; j < capped.length; j++) {
        rawScore += weight;
        hits.push({label: String(label), weight: Number(weight), text: String(capped[j])});
      }
    }
  }
  const score = rawScore <= 0 ? 0 : 1 - Math.exp(-rawScore);
  return {score: Math.round(score * 1000) / 1000, hits: hits, rawScore: Math.round(rawScore * 1000) / 1000};
}

function analyzeAd(text) {
  const results = {};
  for (const [dim, signals] of Object.entries(SIGNALS)) {
    results[dim] = scoreWithSignals(text, signals);
  }
  // Compute manipulation_risk as composite
  const mr = results.manipulation_risk || {score: 0};
  const urgency = results.urgency || {score: 0};
  const emotional = results.emotional_intensity || {score: 0};
  const direct = results.directiveness || {score: 0};
  mr.score = Math.round((mr.score * 0.45 + urgency.score * 0.20 + emotional.score * 0.20 + direct.score * 0.15) * 1000) / 1000;
  results.manipulation_risk = mr;
  return results;
}
"""


def build_html() -> str:
    taxonomy = tx.to_dict()
    taxonomy_json = json.dumps(taxonomy, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>adintel — Interactive Analyzer & Adversarial GAN</title>
<style>
:root {{
  --ink:#0f172a; --muted:#475569; --paper:#f8fafc; --card:#ffffff;
  --line:#e2e8f0; --green:#0f766e; --amber:#b45309; --red:#b91c1c; --blue:#1e40af; --violet:#6d4fa3;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font-family:Inter,ui-sans-serif,system-ui,sans-serif; line-height:1.55; }}
header.hero {{ background:linear-gradient(135deg,#0f172a,#0f766e 55%,#714f28); color:white; padding:20px 32px; position:sticky; top:0; z-index:5; }}
header.hero h1 {{ margin:0; font-size:24px; }}
header.hero .sub {{ opacity:.88; font-size:13px; margin-top:4px; }}
nav.nav {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:12px; }}
nav.nav a {{ border:1px solid #ffffff36; background:#ffffff14; color:inherit; border-radius:999px; padding:6px 12px; text-decoration:none; font-size:12px; font-weight:700; }}
nav.nav a:hover {{ background:#ffffff28; }}
main {{ padding:20px 32px; max-width:1400px; margin:0 auto; }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px; margin-bottom:16px; }}
section h2 {{ margin:0 0 10px; font-size:16px; border-bottom:2px solid var(--line); padding-bottom:6px; }}
section h3 {{ margin:12px 0 6px; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }}
textarea {{ width:100%; min-height:120px; border:1px solid var(--line); border-radius:8px; padding:12px; font-size:14px; font-family:inherit; resize:vertical; }}
textarea:focus {{ outline:2px solid var(--green); outline-offset:1px; }}
.btn {{ background:var(--green); color:white; border:none; border-radius:8px; padding:10px 20px; font-size:14px; font-weight:600; cursor:pointer; }}
.btn:hover {{ background:#065f56; }}
.btn.secondary {{ background:var(--blue); }}
.btn.secondary:hover {{ background:#1e3a8a; }}
.btn.violet {{ background:var(--violet); }}
.btn.violet:hover {{ background:#582c87; }}
.bar-container {{ display:flex; align-items:center; gap:8px; margin:4px 0; }}
.bar-label {{ width:180px; font-size:12px; font-weight:600; }}
.bar-track {{ flex:1; height:8px; background:var(--line); border-radius:4px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:4px; transition:width 0.3s ease; }}
.bar-value {{ width:50px; text-align:right; font-size:12px; font-variant-numeric:tabular-nums; font-weight:600; }}
.tags {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
.tag {{ display:inline-flex; align-items:center; gap:4px; padding:4px 10px; border-radius:999px; font-size:11px; font-weight:600; }}
.tag.red {{ background:#fae0dc; color:#7b241d; }}
.tag.amber {{ background:#f7ead7; color:#744512; }}
.tag.green {{ background:#d1fae5; color:#065f46; }}
.tag.blue {{ background:#e2edf9; color:#213d65; }}
.tag.violet {{ background:#ede5f7; color:#4a3270; }}
.highlight {{ background:linear-gradient(transparent 56%,#f7cf78 56%,#f7cf78 72%,transparent 72%); border-radius:3px; padding:1px 0; }}
.highlight.manip {{ background:linear-gradient(transparent 52%,#eda49d 52%,#eda49d 70%,transparent 70%); }}
.evidence-list {{ max-height:200px; overflow:auto; border:1px solid var(--line); border-radius:8px; padding:8px; }}
.evidence-item {{ padding:4px 0; border-bottom:1px solid var(--line); font-size:12px; }}
.evidence-item:last-child {{ border-bottom:none; }}
.gan-step {{ padding:12px; border-left:3px solid var(--violet); margin:8px 0; background:rgba(109,79,163,0.08); border-radius:0 8px 8px 0; font-size:13px; line-height:1.6; }}
.gan-step b {{ color:var(--violet); }}
#ganLog {{ max-height:450px; overflow-y:auto; padding-right:4px; }}
.disclaimer {{ background:#fef3c7; border:1px solid #fde68a; border-radius:8px; padding:10px; font-size:12px; color:#78350f; margin-top:12px; }}
</style>
</head>
<body>
<header class="hero">
  <h1>adintel — Interactive Analyzer & Adversarial GAN</h1>
  <div class="sub">Type any ad text and see techniques detected in real time. Then run the generate→detect→improve loop.</div>
  <nav class="nav">
    <a href="#analyzer">Analyzer</a>
    <a href="#gan">Adversarial GAN</a>
    <a href="#taxonomy">Taxonomy</a>
    <a href="../reports/adintel/adintel_dashboard.html">← Back to Dashboard</a>
  </nav>
</header>

<main>

<section id="analyzer">
  <h2>Interactive Ad Analyzer</h2>
  <p style="font-size:13px;color:var(--muted);">Type or paste any ad text below. The system scores 17 persuasion dimensions in real time and highlights detected technique spans.</p>

  <textarea id="adInput" placeholder="Example: Ayuda económica urgente hoy para chicas estudiantes.">Brindo ayuda económica constante a chicas estudiantes de universidad. Soy educado, higiénico, tengo lugar propio. Total discreción. Escríbeme por WhatsApp. Trato amable y respetuoso. Lima, todo el año.</textarea>

  <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
    <button class="btn" onclick="runAnalysis()">Analyze</button>
    <button class="btn secondary" onclick="loadSample('high')">Load high-pressure sample</button>
    <button class="btn secondary" onclick="loadSample('neutral')">Load neutral sample</button>
    <button class="btn violet" onclick="generateVariant()">Generate adversarial variant</button>
    <button class="btn violet" onclick="generateAd()">Generate ad from techniques</button>
    <button class="btn secondary" onclick="exportResults()">Export results (JSON)</button>
  </div>

  <h3>Detected Techniques (live)</h3>
  <div id="tagsOutput" class="tags"></div>

  <h3>17-Dimension Persuasive Profile</h3>
  <div id="profileOutput"></div>

  <h3>Annotated Text (highlighted spans)</h3>
  <div id="annotatedText" style="white-space:pre-wrap;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:14px;font-size:14px;line-height:2;"></div>

  <h3>Evidence Ledger</h3>
  <div id="evidenceLedger" class="evidence-list"></div>
</section>

<section id="gan">
  <h2>Adversarial GAN: Generate → Detect → Improve Loop</h2>
  <p style="font-size:13px;color:var(--muted);">This section implements an adversarial generate-and-detect loop: the system generates ad variants using detected techniques, then re-detects to measure detector sensitivity and identify gaps.</p>

  <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
    <button class="btn violet" onclick="runGanCycle()">Run GAN cycle (5 rounds)</button>
    <button class="btn secondary" onclick="clearGanLog()">Clear log</button>
  </div>

  <div id="ganLog" style="margin-top:16px;"></div>

  <div class="disclaimer">
    <strong>Evidence discipline:</strong> The generated variants are for <em>detector testing only</em> — not for operational use.
    The goal is to find gaps in the detector, not to create better manipulative ads.
    No generated variant is stored or deployed.
  </div>
</section>

<section id="taxonomy">
  <h2>Hierarchical Taxonomy v2</h2>
  <div id="taxonomyTree"></div>
</section>

</main>

<script>
""" + build_signals_js() + f"""

// Taxonomy data
const TAXONOMY = {taxonomy_json};

// Sample texts
const SAMPLES = {{
  high: "AYUDA ECONOMICA URGENTE HOY para chicas estudiantes de 18 a 20 anos. Escribeme por WhatsApp privado. Solo por esta semana. 100% garantizado, discreto y confidencial. Dinero semanal fijo. No esperes, escribeme ya. Muchas chicas ya confian. Buena presencia. Sin compromiso.",
  neutral: "Informacion sobre programas de becas del Ministerio de Educacion del Peru para el ano academico en curso. Los requisitos se publican en el portal institucional y las postulaciones se reciben en fechas anunciadas oficialmente."
}};

function loadSample(type) {{
  document.getElementById('adInput').value = SAMPLES[type];
  runAnalysis();
}}

function runAnalysis() {{
  const text = document.getElementById('adInput').value;
  const results = analyzeAd(text);

  // Tags
  const tagsHtml = Object.entries(results)
    .filter(([dim, r]) => r.score > 0.1)
    .sort(([,a],[,b]) => b.score - a.score)
    .map(([dim, r]) => {{
      const cls = r.score > 0.5 ? 'red' : r.score > 0.3 ? 'amber' : 'blue';
      return `<span class="tag ${{cls}}">${{dim.replace(/_/g,' ')}}: ${{(r.score*100).toFixed(0)}}%</span>`;
    }}).join('');
  document.getElementById('tagsOutput').innerHTML = tagsHtml || '<span class="tag green">No techniques detected above threshold</span>';

  // Profile bars
  const profileHtml = Object.entries(results)
    .sort(([,a],[,b]) => b.score - a.score)
    .map(([dim, r]) => {{
      const color = r.score > 0.5 ? 'var(--red)' : r.score > 0.3 ? 'var(--amber)' : 'var(--green)';
      return `<div class="bar-container">
        <span class="bar-label">${{dim.replace(/_/g,' ')}}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${{r.score*100}}%;background:${{color}}"></div></div>
        <span class="bar-value">${{(r.score*100).toFixed(0)}}%</span>
      </div>`;
    }}).join('');
  document.getElementById('profileOutput').innerHTML = profileHtml;

  // Annotated text
  let annotated = text;
  const allHits = [];
  for (const [dim, r] of Object.entries(results)) {{
    for (const h of r.hits) {{
      allHits.push({{label: h.label, weight: h.weight, text: h.text, dim: dim}});
    }}
  }}
  for (const h of allHits) {{
    const isManip = ['manipulation_risk','sexualized_appearance_condition','age_or_youth_targeting'].includes(h.dim);
    const cls = isManip ? 'manip' : '';
    // Escape regex special chars manually
    const safeText = h.text.replace(/[.*+?^${{}}()|[\]\\\\]/g, function(m) {{ return '\\\\' + m; }});
    const re = new RegExp(safeText, 'g');
    annotated = annotated.replace(re, `<span class="highlight ${{cls}}" title="${{h.dim}}: ${{h.label}}">${{h.text}}</span>`);
  }}
  document.getElementById('annotatedText').innerHTML = annotated || '<em>No text</em>';

  // Evidence ledger
  const ledgerHtml = allHits.slice(0, 20).map((h, i) => `
    <div class="evidence-item"><b>${{i+1}}.</b> <span class="tag blue">${{h.dim.replace(/_/g,' ')}}</span> <b>${{h.text}}</b> — ${{h.label}} (${{h.weight}})</div>
  `).join('');
  document.getElementById('evidenceLedger').innerHTML = ledgerHtml || '<div class="evidence-item">No evidence spans detected.</div>';
}}

function generateVariant() {{
  const text = document.getElementById('adInput').value;
  const techniques = ['urgente', 'solo por hoy', 'ultimo cupo', '100% garantizado', 'discreto', 'whatsapp', 'muchas chicas ya confian', 'serio y formal', 'estudiantes', 'dinero semanal'];
  const tech = techniques[Math.floor(Math.random() * techniques.length)];
  const variant = text + ' ' + tech;
  document.getElementById('adInput').value = variant;
  runAnalysis();
}}

function runGanCycle() {{
  const log = document.getElementById('ganLog');
  log.innerHTML = '';
  const baseText = document.getElementById('adInput').value || 'Ayuda economica para chicas estudiantes.';

  for (let round = 1; round <= 5; round++) {{
    const step = document.createElement('div');
    step.className = 'gan-step';
    step.innerHTML = `<b>Round ${{round}}</b>`;

    const techniques = ['urgente hoy', 'solo por esta semana', '100% garantizado', 'discreto y confidencial', 'whatsapp privado', 'muchas chicas confian', 'serio y formal', 'estudiantes universitarias', 'dinero semanal fijo', 'buena presencia', 'ultimo cupo'];
    const tech = techniques[Math.floor(Math.random() * techniques.length)];
    const variant = baseText + ' ' + tech;

    const results = analyzeAd(variant);
    const topDims = Object.entries(results)
      .filter(([dim, r]) => r.score > 0.1)
      .sort(([,a],[,b]) => b.score - a.score)
      .slice(0, 3)
      .map(([dim, r]) => `${{dim}}=${{(r.score*100).toFixed(0)}}%`)
      .join(', ');

    step.innerHTML += `<br>Generated variant adds: <code>${{tech}}</code>`;
    step.innerHTML += `<br>Detected techniques: ${{topDims || 'none'}}`;

    const caught = topDims.toLowerCase().includes(tech.split(' ')[0].toLowerCase());
    step.innerHTML += `<br>Detector caught injection: <b>${{caught ? 'YES' : 'NO (gap found)'}}</b>`;

    if (!caught) {{
      step.innerHTML += `<br><em>Gap: the detector did not flag the injected technique "${{tech}}". This identifies a potential improvement area.</em>`;
    }}

    log.appendChild(step);
  }}
}}

function clearGanLog() {{
  document.getElementById('ganLog').innerHTML = '';
}}

// F-02: Export analysis results as JSON
function exportResults() {{
  const text = document.getElementById('adInput').value;
  const results = analyzeAd(text);
  const exportData = {{
    text: text,
    analyzed_at: new Date().toISOString(),
    dimensions: Object.entries(results).map(([dim, r]) => ({{
      dimension: dim,
      score: r.score,
      raw_score: r.rawScore,
      n_hits: r.hits.length,
      hits: r.hits,
    }})),
    high_risk_dimensions: Object.entries(results)
      .filter(([, r]) => r.score >= 0.5)
      .map(([dim]) => dim),
    tool_version: 'adintel-interactive-analyzer-v1',
  }};
  const blob = new Blob([JSON.stringify(exportData, null, 2)], {{type: 'application/json'}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'ad_analysis_' + Date.now() + '.json';
  a.click();
  URL.revokeObjectURL(url);
}}

// F-05: Generate a synthetic ad using detected techniques
function generateAd() {{
  const text = document.getElementById('adInput').value;
  const results = analyzeAd(text);
  // Find the top 3 scoring dimensions
  const topDims = Object.entries(results)
    .filter(([, r]) => r.score > 0.1)
    .sort(([, a], [, b]) => b.score - a.score)
    .slice(0, 3)
    .map(([dim]) => dim);

  if (topDims.length === 0) {{
    document.getElementById('adInput').value = 'No techniques detected to generate from. Try loading a sample first.';
    return;
  }}

  // Map dimensions to ad-copy fragments
  const fragments = {{
    urgency: 'urgente hoy',
    scarcity: 'solo por esta semana, ultimo cupo',
    emotional_intensity: 'comprende tu situacion',
    directiveness: 'escribeme ya por whatsapp',
    certainty: '100% garantizado y seguro',
    specificity: 'en lima, todo el ano',
    benefit_density: 'ayuda economica semanal fija',
    evidence_density: 'referencias verificadas',
    social_proof: 'muchas chicas ya confian',
    objection_handling: 'sin compromiso, discreto',
    risk_reversal: 'primera consulta gratis',
    claim_extremity: 'el mejor apoyo de lima',
    readability: 'informacion clara y directa',
    offer_clarity: 'monto fijo semanal',
    action_clarity: 'escribeme al whatsapp',
    trust_risk: 'serio y formal',
    manipulation_risk: '',
    platform_migration: 'whatsapp privado',
    privacy_or_secrecy_pressure: 'total discrecion',
    financial_lure: 'dinero semanal',
    authority_or_status_appeal: 'profesional y solvente',
    age_or_youth_targeting: 'chicas estudiantes',
    education_or_student_targeting: 'universitarias',
    sexualized_appearance_condition: '',
    scarcity_or_urgency: 'urgente, solo hoy',
    reciprocity_obligation: 'brindo ayuda',
    deceptive_assurance: 'serio, real, confiable',
    social_proof: 'muchos ya confian',
    commitment_escalation: 'apoyo constante y permanente',
  }};

  // Build ad from top dimensions
  const parts = topDims.map(d => fragments[d] || '').filter(f => f);
  // Add a greeting and closing
  const greeting = 'Hola, ';
  const closing = ' Lima. Escribeme para mas informacion.';
  const generatedAd = greeting + parts.join('. ') + '.' + closing;

  document.getElementById('adInput').value = generatedAd;
  runAnalysis();
}}

function renderTaxonomy() {{
  const tree = document.getElementById('taxonomyTree');
  const families = TAXONOMY.top_level_families;
  const nodes = TAXONOMY.nodes;
  let html = '';
  for (const family of families) {{
    html += `<div style="margin-bottom:12px;"><h3 style="color:var(--green);">${{family.replace(/_/g,' ')}}</h3>`;
    const children = nodes.filter(n => n.parent === family);
    for (const child of children) {{
      html += `<div style="margin-left:16px;"><b>${{child.name}}</b> <span style="font-size:11px;color:var(--muted);">${{child.id}}</span>`;
      const grandchildren = nodes.filter(n => n.parent === child.id);
      if (grandchildren.length) {{
        html += '<ul style="margin:4px 0 8px 16px;font-size:12px;">';
        for (const gc of grandchildren) {{
          html += `<li><b>${{gc.name}}</b> — ${{gc.definition.substring(0,80)}}...</li>`;
        }}
        html += '</ul>';
      }} else {{
        html += `<div style="font-size:11px;color:var(--muted);margin-left:16px;">${{child.definition.substring(0,100)}}</div>`;
      }}
      html += '</div>';
    }}
    html += '</div>';
  }}
  tree.innerHTML = html;
}}

renderTaxonomy();
runAnalysis();
</script>
</body>
</html>"""


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_html(), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
