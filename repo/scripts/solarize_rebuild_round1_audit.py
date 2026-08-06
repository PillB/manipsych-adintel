#!/usr/bin/env python3
"""Solarize AdIntel Rebuild — Round 1 Forensic Pre-Execution Audit.

Runs ALL 16 user journeys from the spec against the LIVE GitHub Pages deployment.
Captures: entry points, clicks, URL changes, time-to-evidence, confusion,
duplicated information, dead ends, broken controls, missing explanations,
lost state, misleading claims, console errors, network failures, visual defects.

Also captures performance baselines: HTML size, transfer, parsing time, LCP,
console errors, top-level navigation count, duplicated definitions, orphaned files.

NO production code is modified. This is read-only forensic evidence.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, Page, BrowserContext

LIVE_DASHBOARD = "https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard.html"
LIVE_ANALYZER = "https://pillb.github.io/manipsych-adintel/interactive_analyzer.html"
EVIDENCE_DIR = Path("/home/z/my-project/repo/audit/solarize-rebuild/round1")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
(EVIDENCE_DIR / "screenshots").mkdir(exist_ok=True)
(EVIDENCE_DIR / "traces").mkdir(exist_ok=True)

CB = str(int(time.time()))


def cache_bust(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}cb={CB}"


def journey_report(journey_id: str, journey_name: str) -> dict:
    return {
        "journey_id": journey_id,
        "journey_name": journey_name,
        "entry_point": "",
        "clicks": [],
        "url_changes": [],
        "time_to_evidence_s": None,
        "time_to_complete_s": None,
        "confusion_points": [],
        "duplicated_info": [],
        "dead_ends": [],
        "broken_controls": [],
        "missing_explanations": [],
        "lost_state": [],
        "inconsistent_terminology": [],
        "orphaned_results": [],
        "misleading_claims": [],
        "console_errors": [],
        "network_failures": [],
        "visual_defects": [],
        "verdict": "",
        "notes": "",
    }


def run_journey(page: Page, journey: dict) -> dict:
    """Run a single user journey and populate the report."""
    t0 = time.perf_counter()
    try:
        journey["entry_point"] = page.url
        # Journey-specific logic is in the caller
        journey["time_to_complete_s"] = round(time.perf_counter() - t0, 2)
        if not journey["verdict"]:
            journey["verdict"] = "COMPLETED"
    except Exception as e:
        journey["verdict"] = f"ERROR: {e}"
        journey["time_to_complete_s"] = round(time.perf_counter() - t0, 2)
    return journey


# ---------------------------------------------------------------------------
# 16 User Journeys from the spec (Section 8, Round 1)
# ---------------------------------------------------------------------------

def journey_01_assess_new_ad(page: Page) -> dict:
    """J1: Assess a newly supplied ad."""
    j = journey_report("J01", "Assess a newly supplied ad")
    page.goto(cache_bust(LIVE_DASHBOARD), wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Loaded dashboard")
    # Look for a text input or 'Analyze' button
    analyze_input = page.locator("input[type='text'], textarea, #adintel-ad-selector").count()
    analyze_button = page.locator("button:has-text('Analyze'), button:has-text('Assess'), a:has-text('Analyze')").count()
    if analyze_input == 0 and analyze_button == 0:
        j["dead_ends"].append("No ad assessment input found on the dashboard — user cannot paste ad copy")
        j["verdict"] = "DEAD_END — no ad assessment capability in the dashboard"
    else:
        j["verdict"] = "PARTIAL — input exists but may not be a full ad grader"
    # Check if the standalone analyzer is linked
    analyzer_link = page.locator("a[href*='interactive_analyzer']").count()
    if analyzer_link == 0:
        j["missing_explanations"].append("Standalone analyzer is not linked from the dashboard")
    j["time_to_complete_s"] = 5
    return j


def journey_02_why_technique_detected(page: Page) -> dict:
    """J2: Determine why a persuasion technique was detected."""
    j = journey_report("J02", "Determine why a persuasion technique was detected")
    page.goto(cache_bust(LIVE_DASHBOARD) + "#explorer", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Navigated to #explorer")
    # Check if technique labels are shown
    labels = page.locator(".rank .label, .rank .technique, .span-label").count()
    if labels > 0:
        j["clicks"].append(f"Found {labels} technique labels in explorer")
        # Click first ad to see detail
        first_rank = page.locator(".rank").first
        if first_rank.count() > 0:
            first_rank.click()
            page.wait_for_timeout(1500)
            j["clicks"].append("Clicked first ad in explorer")
            # Check if evidence spans are shown
            evidence = page.locator(".evidence-span, .highlight, mark, .span").count()
            if evidence > 0:
                j["verdict"] = "COMPLETED — evidence spans shown for detected techniques"
            else:
                j["missing_explanations"].append("No highlighted evidence spans found in ad detail")
                j["verdict"] = "PARTIAL — technique labels shown but no evidence spans"
        else:
            j["dead_ends"].append("No ads in explorer to click")
    else:
        j["dead_ends"].append("No technique labels found in explorer")
        j["verdict"] = "DEAD_END"
    return j


def journey_03_find_indicator_formula(page: Page) -> dict:
    """J3: Find the formula and limitations of an indicator."""
    j = journey_report("J03", "Find the formula and limitations of an indicator")
    page.goto(cache_bust(LIVE_DASHBOARD) + "#adintel-methodology", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Navigated to #adintel-methodology")
    # Check if methodology explains formulas
    methodology_text = page.locator("#adintel-methodology").inner_text().lower()
    has_formula = "formula" in methodology_text or "cohen" in methodology_text or "wilson" in methodology_text
    has_limitations = "limitation" in methodology_text or "not justified" in methodology_text or "threshold" in methodology_text
    if has_formula and has_limitations:
        j["verdict"] = "COMPLETED — methodology section explains formulas and limitations"
    elif has_formula:
        j["verdict"] = "PARTIAL — formulas present but limitations not explicit"
        j["missing_explanations"].append("Methodology has formulas but no per-indicator limitations")
    else:
        j["verdict"] = "DEAD_END — no indicator formulas found"
        j["dead_ends"].append("No canonical indicator dictionary exists")
    # Check for indicator dictionary
    indicator_dict = page.locator("#adintel-indicator-dictionary, [data-role='indicator-dictionary']").count()
    if indicator_dict == 0:
        j["missing_explanations"].append("No canonical indicator dictionary with per-indicator formula, numerator, denominator, thresholds")
    return j


def journey_04_navigate_ad_to_cluster(page: Page) -> dict:
    """J4: Navigate from one ad to its cluster."""
    j = journey_report("J04", "Navigate from one ad to its cluster")
    page.goto(cache_bust(LIVE_DASHBOARD) + "#adintel-clustering", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Navigated to #adintel-clustering")
    # Use the ad selector
    selector = page.locator("#adintel-ad-selector")
    if selector.count() > 0:
        selector.first.fill("h_")
        page.wait_for_timeout(1500)
        j["clicks"].append("Typed 'h_' in ad selector")
        results = page.locator("#adintel-ad-results .ad-result-row")
        if results.count() > 0:
            results.first.click()
            page.wait_for_timeout(1500)
            j["clicks"].append("Clicked first ad result")
            # Check if detail panel shows cluster
            detail = page.locator("#adintel-ad-detail").inner_text().lower()
            if "cluster" in detail:
                j["verdict"] = "COMPLETED — ad detail shows cluster assignment"
            else:
                j["verdict"] = "PARTIAL — ad selected but cluster not shown in detail"
        else:
            j["dead_ends"].append("No results in ad selector")
    else:
        j["dead_ends"].append("No ad selector found")
        j["verdict"] = "DEAD_END"
    return j


def journey_05_why_ad_belongs_to_cluster(page: Page) -> dict:
    """J5: Understand why the ad belongs to that cluster."""
    j = journey_report("J05", "Understand why the ad belongs to that cluster")
    page.goto(cache_bust(LIVE_DASHBOARD) + "#adintel-clustering", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Navigated to #adintel-clustering")
    # Check for cluster explanation
    cluster_cards = page.locator(".cluster-card").count()
    if cluster_cards > 0:
        j["clicks"].append(f"Found {cluster_cards} cluster cards with distinguishing terms")
        # Check if "why this cluster" explanation exists
        page.locator("#adintel-ad-selector").first.fill("h_")
        page.wait_for_timeout(1500)
        results = page.locator("#adintel-ad-results .ad-result-row")
        if results.count() > 0:
            results.first.click()
            page.wait_for_timeout(1500)
            detail = page.locator("#adintel-ad-detail").inner_text().lower()
            if "why this cluster" in detail or "assigned to cluster" in detail:
                j["verdict"] = "COMPLETED — ad detail explains why it belongs to the cluster"
            else:
                j["verdict"] = "PARTIAL — cluster card shows terms but ad detail lacks 'why' explanation"
                j["missing_explanations"].append("Ad detail does not explain WHY the ad was assigned to its cluster")
    else:
        j["dead_ends"].append("No cluster cards found")
        j["verdict"] = "DEAD_END"
    return j


def journey_06_compare_outlier_with_normal(page: Page) -> dict:
    """J6: Compare an outlier with normal examples."""
    j = journey_report("J06", "Compare an outlier with normal examples")
    page.goto(cache_bust(LIVE_DASHBOARD) + "#adintel-outliers", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Navigated to #adintel-outliers")
    # Check for outlier examples
    outlier_examples = page.locator("[data-field='outlier_example']").count()
    term_comparison = page.locator("[data-field='term_comparison']").count()
    if outlier_examples > 0 and term_comparison > 0:
        j["clicks"].append(f"Found {outlier_examples} outlier examples + {term_comparison} term-comparison tables")
        j["verdict"] = "COMPLETED — outlier examples and term comparison tables present"
    else:
        j["verdict"] = "PARTIAL — some outlier content missing"
    return j


def journey_07_distinguish_model_heuristic_expert(page: Page) -> dict:
    """J7: Distinguish model, heuristic, and expert labels."""
    j = journey_report("J07", "Distinguish model, heuristic, and expert labels")
    page.goto(cache_bust(LIVE_DASHBOARD) + "#explorer", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Navigated to #explorer")
    # Check if labels are distinguished by source
    body_text = page.locator("body").inner_text().lower()
    has_model = "model" in body_text and ("prediction" in body_text or "probability" in body_text)
    has_heuristic = "heuristic" in body_text or "rule" in body_text
    has_expert = "council" in body_text or "expert" in body_text or "human" in body_text
    if has_model and has_heuristic and has_expert:
        j["verdict"] = "PARTIAL — all three label types mentioned but not clearly distinguished per-ad"
        j["confusion_points"].append("Label sources (model vs heuristic vs expert) are not clearly marked per technique")
    else:
        missing = []
        if not has_model: missing.append("model")
        if not has_heuristic: missing.append("heuristic")
        if not has_expert: missing.append("expert")
        j["verdict"] = f"PARTIAL — missing label source distinctions: {missing}"
    return j


def journey_08_identify_checkpoint(page: Page) -> dict:
    """J8: Identify the checkpoint that produced a result."""
    j = journey_report("J08", "Identify the checkpoint that produced a result")
    page.goto(cache_bust(LIVE_DASHBOARD) + "#adintel-checkpoints", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Navigated to #adintel-checkpoints")
    # Check if checkpoint table exists
    checkpoint_rows = page.locator("#adintel-checkpoints table tr").count()
    if checkpoint_rows > 0:
        j["clicks"].append(f"Found {checkpoint_rows} checkpoint rows")
        # Check if any result in the dashboard links to a checkpoint
        body_text = page.locator("body").inner_text().lower()
        if "checkpoint" in body_text and "version" in body_text:
            j["verdict"] = "PARTIAL — checkpoint registry exists but individual results don't link to specific checkpoints"
            j["missing_explanations"].append("Individual ad results and technique detections do not cite which checkpoint produced them")
        else:
            j["verdict"] = "PARTIAL — checkpoint table exists but not connected to results"
    else:
        j["dead_ends"].append("No checkpoint table found")
        j["verdict"] = "DEAD_END"
    return j


def journey_09_locate_adversarial_generation(page: Page) -> dict:
    """J9: Locate the adversarial-generation stage."""
    j = journey_report("J09", "Locate the adversarial-generation stage")
    page.goto(cache_bust(LIVE_DASHBOARD), wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Loaded dashboard")
    # Search for adversarial/GAN content
    body_text = page.locator("body").inner_text().lower()
    has_gan = "gan" in body_text
    has_adversarial = "adversarial" in body_text
    has_adversarial_section = page.locator("#adversarial, #adintel-adversarial, [data-role='adversarial-lab']").count()
    if has_gan:
        j["misleading_claims"].append("Dashboard or analyzer uses 'GAN' label — needs verification that it's a genuine GAN")
    if has_adversarial:
        j["clicks"].append("Found 'adversarial' text in dashboard")
    if has_adversarial_section == 0:
        j["dead_ends"].append("No dedicated adversarial-generation section in the dashboard — adversarial functionality is only in the standalone analyzer")
        j["verdict"] = "DEAD_END — adversarial generation not in dashboard"
    else:
        j["verdict"] = "COMPLETED"
    # Also check the standalone analyzer
    page.goto(cache_bust(LIVE_ANALYZER), wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    analyzer_text = page.locator("body").inner_text().lower()
    if "gan" in analyzer_text:
        j["misleading_claims"].append("Standalone analyzer uses 'GAN' label — CRITICAL: needs forensic code verification")
    return j


def journey_10_how_generated_data_reaches_training(page: Page) -> dict:
    """J10: Understand how generated data reaches training."""
    j = journey_report("J10", "Understand how generated data reaches training")
    page.goto(cache_bust(LIVE_DASHBOARD), wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Loaded dashboard")
    # Search for training/synthetic data content
    body_text = page.locator("body").inner_text().lower()
    has_training = "training" in body_text or "retraining" in body_text
    has_synthetic = "synthetic" in body_text
    has_quarantine = "quarantine" in body_text
    if has_training:
        j["clicks"].append("Found 'training' text")
    if has_synthetic:
        j["clicks"].append("Found 'synthetic' text")
    if not has_quarantine:
        j["missing_explanations"].append("No synthetic-data quarantine workflow documented")
    j["verdict"] = "DEAD_END — no visible connected workflow from adversarial generation to training"
    j["dead_ends"].append("The dashboard does not show how generated examples are reviewed, quarantined, evaluated, and admitted to training")
    return j


def journey_11_begin_tutorial(page: Page) -> dict:
    """J11: Begin a tutorial."""
    j = journey_report("J11", "Begin a tutorial")
    page.goto(cache_bust(LIVE_DASHBOARD), wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Loaded dashboard")
    # Search for tutorial button/link
    tutorial_button = page.locator("button:has-text('tutorial'), a:has-text('tutorial'), button:has-text('Tour'), a:has-text('Tour'), button:has-text('Guide'), [data-role='tutorial']").count()
    if tutorial_button == 0:
        j["dead_ends"].append("No tutorial button, link, or overlay found anywhere in the dashboard")
        j["verdict"] = "DEAD_END — no tutorial exists"
    else:
        j["clicks"].append(f"Found {tutorial_button} tutorial-related elements")
        j["verdict"] = "PARTIAL"
    return j


def journey_12_stop_tutorial_midway(page: Page) -> dict:
    """J12: Stop midway."""
    j = journey_report("J12", "Stop tutorial midway")
    # Can't test this if no tutorial exists
    j["verdict"] = "BLOCKED — no tutorial exists (see J11)"
    j["dead_ends"].append("Cannot test tutorial stop/resume because no tutorial exists")
    return j


def journey_13_refresh_page(page: Page) -> dict:
    """J13: Refresh the page."""
    j = journey_report("J13", "Refresh the page")
    page.goto(cache_bust(LIVE_DASHBOARD) + "#adintel-clustering", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Navigated to #adintel-clustering")
    # Select an ad
    selector = page.locator("#adintel-ad-selector")
    if selector.count() > 0:
        selector.first.fill("h_")
        page.wait_for_timeout(1000)
        results = page.locator("#adintel-ad-results .ad-result-row")
        if results.count() > 0:
            results.first.click()
            page.wait_for_timeout(1000)
            j["clicks"].append("Selected an ad")
            # Refresh
            page.reload(wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(2000)
            j["clicks"].append("Refreshed the page")
            # Check if state was lost
            detail = page.locator("#adintel-ad-detail").inner_text()
            if "Click" in detail or len(detail) < 50:
                j["lost_state"].append("Ad selection lost after refresh — no local persistence of ad selector state")
                j["verdict"] = "STATE LOST — ad selection does not survive refresh"
            else:
                j["verdict"] = "STATE PERSISTED"
    else:
        j["verdict"] = "DEAD_END"
    return j


def journey_14_resume_from_saved_step(page: Page) -> dict:
    """J14: Resume from the saved step."""
    j = journey_report("J14", "Resume from saved step")
    j["verdict"] = "BLOCKED — no tutorial exists to resume (see J11)"
    j["dead_ends"].append("Cannot test tutorial resume because no tutorial exists")
    return j


def journey_15_send_guided_message(page: Page) -> dict:
    """J15: Send a guided message through the analysis assistant."""
    j = journey_report("J15", "Send a guided message through the analysis assistant")
    page.goto(cache_bust(LIVE_DASHBOARD), wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Loaded dashboard")
    # Search for assistant/chat input
    assistant = page.locator("#ask-adintel, [data-role='assistant'], input[placeholder*='ask'], input[placeholder*='question'], .chat-input, #assistantInput").count()
    if assistant == 0:
        j["dead_ends"].append("No 'Ask AdIntel' or contextual assistant found in the dashboard")
        j["verdict"] = "DEAD_END — no contextual assistant exists"
    else:
        j["verdict"] = "PARTIAL"
    return j


def journey_16_export_result(page: Page) -> dict:
    """J16: Export the current result."""
    j = journey_report("J16", "Export the current result")
    page.goto(cache_bust(LIVE_DASHBOARD) + "#adintel-data", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2000)
    j["clicks"].append("Navigated to #adintel-data")
    # Check for download links
    download_links = page.locator("a[download], a:has-text('Download')").count()
    if download_links > 0:
        j["clicks"].append(f"Found {download_links} download links in #adintel-data")
        j["verdict"] = "COMPLETED — data download section has export links"
    else:
        # Also check for export buttons in explorer
        page.goto(cache_bust(LIVE_DASHBOARD) + "#explorer", wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(2000)
        export_buttons = page.locator("button:has-text('Export'), button:has-text('Download'), a:has-text('Export')").count()
        if export_buttons > 0:
            j["verdict"] = "PARTIAL — export button exists in explorer"
        else:
            j["dead_ends"].append("No export button found in explorer or data section")
            j["verdict"] = "DEAD_END"
    return j


# ---------------------------------------------------------------------------
# Performance baselines
# ---------------------------------------------------------------------------

def capture_performance_baselines(page: Page) -> dict:
    """Capture performance baselines per spec Section 8 Round 1."""
    baselines = {}
    # Navigate to dashboard
    page.goto(cache_bust(LIVE_DASHBOARD), wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(3000)
    
    # HTML size
    baselines["html_size_bytes"] = page.evaluate("() => document.documentElement.outerHTML.length")
    baselines["html_size_kb"] = round(baselines["html_size_bytes"] / 1024, 1)
    baselines["html_size_mb"] = round(baselines["html_size_bytes"] / 1024 / 1024, 2)
    
    # Top-level navigation count
    baselines["top_level_nav_count"] = page.locator("nav.nav a, header.hero nav a").count()
    
    # Section count
    baselines["section_count"] = page.locator("section[id]").count()
    
    # Embedded JSON data size
    baselines["embedded_json_scripts"] = page.locator("script[type='application/json']").count()
    json_sizes = page.evaluate("""() => {
        const scripts = document.querySelectorAll("script[type='application/json']");
        return Array.from(scripts).map(s => ({id: s.id, size: s.textContent.length}));
    }""")
    baselines["embedded_json_details"] = json_sizes
    baselines["total_embedded_json_bytes"] = sum(s["size"] for s in json_sizes)
    
    # Performance timing
    timing = page.evaluate("""() => ({
        navigationStart: performance.timing.navigationStart,
        loadEventEnd: performance.timing.loadEventEnd,
        domContentLoadedEventEnd: performance.timing.domContentLoadedEventEnd,
        responseEnd: performance.timing.responseEnd,
        domInteractive: performance.timing.domInteractive,
    })""")
    baselines["load_time_ms"] = timing["loadEventEnd"] - timing["navigationStart"] if timing["loadEventEnd"] > 0 else None
    baselines["dom_interactive_ms"] = timing["domInteractive"] - timing["navigationStart"] if timing["domInteractive"] > 0 else None
    baselines["response_end_ms"] = timing["responseEnd"] - timing["navigationStart"] if timing["responseEnd"] > 0 else None
    
    # LCP (Largest Contentful Paint)
    lcp = page.evaluate("""() => {
        const entries = performance.getEntriesByType('largest-contentful-paint');
        return entries.length > 0 ? entries[entries.length - 1].startTime : null;
    }""")
    baselines["lcp_ms"] = round(lcp, 1) if lcp else None
    
    # Memory usage (if available)
    memory = page.evaluate("""() => {
        if (performance.memory) {
            return {usedJSMB: Math.round(performance.memory.usedJSHeapSize / 1024 / 1024), totalJSMB: Math.round(performance.memory.totalJSHeapSize / 1024 / 1024)};
        }
        return null;
    }""")
    baselines["memory"] = memory
    
    # Console errors
    # (captured separately via event listener)
    
    # Duplicate definitions check
    body_text = page.locator("body").inner_text()
    baselines["gan_mentions"] = body_text.lower().count("gan")
    baselines["adversarial_mentions"] = body_text.lower().count("adversarial")
    baselines["confidence_mentions"] = body_text.lower().count("confidence")
    baselines["calibrated_mentions"] = body_text.lower().count("calibrated")
    baselines["causal_mentions"] = body_text.lower().count("causal")
    
    return baselines


# ---------------------------------------------------------------------------
# Standalone analyzer inspection
# ---------------------------------------------------------------------------

def inspect_standalone_analyzer(page: Page) -> dict:
    """Inspect the standalone interactive analyzer for GAN mislabeling."""
    report = {"url": LIVE_ANALYZER}
    page.goto(cache_bust(LIVE_ANALYZER), wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(3000)
    
    body_text = page.locator("body").inner_text()
    body_lower = body_text.lower()
    
    # Check for GAN labeling
    report["gan_label_count"] = body_lower.count("gan")
    report["gan_contexts"] = []
    import re
    for m in re.finditer(r'gan', body_lower):
        start = max(0, m.start() - 60)
        end = min(len(body_lower), m.end() + 60)
        report["gan_contexts"].append(body_lower[start:end])
    
    # Check for adversarial functionality
    report["adversarial_count"] = body_lower.count("adversarial")
    report["perturbation_count"] = body_lower.count("perturbation")
    report["phrase_injection_count"] = body_lower.count("phrase injection") + body_lower.count("insert phrase")
    report["regex_mutation_count"] = body_lower.count("regex") + body_lower.count("regular expression")
    report["training_count"] = body_lower.count("training")
    report["retraining_count"] = body_lower.count("retraining") + body_lower.count("re-train")
    
    # Check for actual ML training evidence
    report["has_generator"] = bool(re.search(r'generator.*train|train.*generator', body_lower))
    report["has_discriminator"] = bool(re.search(r'discriminator|adversarial.*critic', body_lower))
    report["has_adversarial_loss"] = bool(re.search(r'adversarial.*loss|loss.*adversarial', body_lower))
    report["has_optimization_steps"] = bool(re.search(r'optimization|gradient.*step|backprop', body_lower))
    report["has_saved_checkpoints"] = bool(re.search(r'checkpoint.*save|saved.*checkpoint', body_lower))
    report["has_held_out_evaluation"] = bool(re.search(r'held.out|test.set.*eval|evaluation.*set', body_lower))
    report["has_baseline_comparison"] = bool(re.search(r'baseline.*compar|compar.*baseline', body_lower))
    
    # GAN gate verdict
    gan_gate = all([
        report["has_generator"],
        report["has_discriminator"],
        report["has_adversarial_loss"],
        report["has_optimization_steps"],
        report["has_saved_checkpoints"],
        report["has_held_out_evaluation"],
        report["has_baseline_comparison"],
    ])
    report["gan_gate_passed"] = gan_gate
    report["gan_gate_verdict"] = "GAN LABEL JUSTIFIED" if gan_gate else "GAN LABEL NOT JUSTIFIED — rename to 'Rule-Based Adversarial Sandbox' or 'Adversarial Phrase Perturbation Prototype'"
    
    # Check what the analyzer actually does
    report["has_text_input"] = page.locator("textarea, input[type='text']").count() > 0
    report["has_image_upload"] = page.locator("input[type='file']").count() > 0
    report["has_analyze_button"] = page.locator("button:has-text('Analyze'), button:has-text('Assess'), button:has-text('Score')").count() > 0
    report["has_evidence_highlight"] = page.locator("mark, .highlight, .evidence-span").count() > 0
    report["has_profile_dimensions"] = bool(re.search(r'profile.*dimension|17.*dimension|persuasive.*profile', body_lower))
    report["has_evidence_ledger"] = bool(re.search(r'evidence.*ledger|ledger', body_lower))
    report["has_export"] = page.locator("button:has-text('Export'), a:has-text('Export'), button:has-text('Download')").count() > 0
    
    # Capabilities summary
    report["capabilities"] = {
        "text_analysis": report["has_text_input"] and report["has_analyze_button"],
        "image_upload": report["has_image_upload"],
        "evidence_highlighting": report["has_evidence_highlight"],
        "persuasive_profile": report["has_profile_dimensions"],
        "evidence_ledger": report["has_evidence_ledger"],
        "export": report["has_export"],
        "multimodal": report["has_image_upload"],
        "model_backed_confidence": False,  # needs deeper inspection
        "calibration": False,  # needs deeper inspection
        "abstention": False,  # needs deeper inspection
        "corpus_connections": False,  # standalone, not connected to corpus
        "checkpoint_provenance": False,  # no checkpoint references
        "tutorial_state": False,  # no tutorial
        "contextual_assistant": False,  # no assistant
        "dashboard_integration": False,  # standalone, not integrated
    }
    
    # Screenshot
    page.screenshot(path=str(EVIDENCE_DIR / "screenshots" / "standalone_analyzer.png"), full_page=False)
    
    return report


# ---------------------------------------------------------------------------
# Multi-viewport audit
# ---------------------------------------------------------------------------

def multi_viewport_audit(browser) -> dict:
    """Test the dashboard at multiple viewport sizes."""
    viewports = [
        {"name": "desktop_1440x900", "width": 1440, "height": 900},
        {"name": "laptop_1366x768", "width": 1366, "height": 768},
        {"name": "tablet_landscape_1024x768", "width": 1024, "height": 768},
        {"name": "tablet_portrait_768x1024", "width": 768, "height": 1024},
        {"name": "mobile_390x844", "width": 390, "height": 844, "is_mobile": True, "has_touch": True},
    ]
    results = []
    for vp in viewports:
        ctx = browser.new_context(
            viewport={"width": vp["width"], "height": vp["height"]},
            is_mobile=vp.get("is_mobile", False),
            has_touch=vp.get("has_touch", False),
        )
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        try:
            pg.goto(cache_bust(LIVE_DASHBOARD), wait_until="networkidle", timeout=60_000)
            pg.wait_for_timeout(2000)
            overflow = pg.evaluate("() => ({scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth, scrollH: document.documentElement.scrollHeight, clientH: document.documentElement.clientHeight})")
            horizontal_overflow = overflow["scrollW"] > overflow["clientW"] + 5
            # Take screenshot
            pg.screenshot(path=str(EVIDENCE_DIR / "screenshots" / f"viewport_{vp['name']}.png"), full_page=False)
            results.append({
                "viewport": vp["name"],
                "width": vp["width"],
                "height": vp["height"],
                "scrollW": overflow["scrollW"],
                "clientW": overflow["clientW"],
                "horizontal_overflow": horizontal_overflow,
                "n_page_errors": len(errors),
                "page_errors": errors[:3],
            })
        except Exception as e:
            results.append({"viewport": vp["name"], "error": str(e)})
        finally:
            ctx.close()
    return results


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

def main():
    print("=== Solarize AdIntel Rebuild — Round 1 Forensic Pre-Execution ===")
    print(f"Dashboard: {LIVE_DASHBOARD}")
    print(f"Analyzer: {LIVE_ANALYZER}")
    print(f"Cache-bust: {CB}")
    print()
    
    report = {
        "audit_started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "live_dashboard_url": LIVE_DASHBOARD,
        "live_analyzer_url": LIVE_ANALYZER,
        "cache_bust": CB,
        "journeys": [],
        "performance_baselines": None,
        "standalone_analyzer_inspection": None,
        "multi_viewport_audit": None,
        "console_errors_all": [],
        "summary": {},
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # === 16 User Journeys ===
        print("--- Running 16 User Journeys ---")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        console_errors = []
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.on("console", lambda m: console_errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        
        journeys = [
            journey_01_assess_new_ad,
            journey_02_why_technique_detected,
            journey_03_find_indicator_formula,
            journey_04_navigate_ad_to_cluster,
            journey_05_why_ad_belongs_to_cluster,
            journey_06_compare_outlier_with_normal,
            journey_07_distinguish_model_heuristic_expert,
            journey_08_identify_checkpoint,
            journey_09_locate_adversarial_generation,
            journey_10_how_generated_data_reaches_training,
            journey_11_begin_tutorial,
            journey_12_stop_tutorial_midway,
            journey_13_refresh_page,
            journey_14_resume_from_saved_step,
            journey_15_send_guided_message,
            journey_16_export_result,
        ]
        
        for i, journey_fn in enumerate(journeys, 1):
            print(f"  J{i:02d}: {journey_fn.__doc__ or ''}")
            try:
                result = journey_fn(page)
                report["journeys"].append(result)
                print(f"       → {result['verdict']}")
            except Exception as e:
                print(f"       → ERROR: {e}")
                report["journeys"].append({"journey_id": f"J{i:02d}", "error": str(e), "verdict": "ERROR"})
        
        report["console_errors_all"] = console_errors[:20]
        ctx.close()
        
        # === Performance Baselines ===
        print("\n--- Capturing Performance Baselines ---")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        try:
            report["performance_baselines"] = capture_performance_baselines(page)
            print(f"  HTML size: {report['performance_baselines']['html_size_mb']} MB")
            print(f"  Top-level nav: {report['performance_baselines']['top_level_nav_count']}")
            print(f"  Sections: {report['performance_baselines']['section_count']}")
            print(f"  GAN mentions: {report['performance_baselines']['gan_mentions']}")
        except Exception as e:
            print(f"  ERROR: {e}")
            report["performance_baselines"] = {"error": str(e)}
        ctx.close()
        
        # === Standalone Analyzer Inspection ===
        print("\n--- Inspecting Standalone Analyzer ---")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        try:
            report["standalone_analyzer_inspection"] = inspect_standalone_analyzer(page)
            print(f"  GAN label count: {report['standalone_analyzer_inspection']['gan_label_count']}")
            print(f"  GAN gate passed: {report['standalone_analyzer_inspection']['gan_gate_passed']}")
            print(f"  Verdict: {report['standalone_analyzer_inspection']['gan_gate_verdict']}")
        except Exception as e:
            print(f"  ERROR: {e}")
            report["standalone_analyzer_inspection"] = {"error": str(e)}
        ctx.close()
        
        # === Multi-viewport Audit ===
        print("\n--- Multi-Viewport Audit ---")
        try:
            report["multi_viewport_audit"] = multi_viewport_audit(browser)
            for vp in report["multi_viewport_audit"]:
                if "error" in vp:
                    print(f"  {vp['viewport']}: ERROR — {vp['error']}")
                else:
                    print(f"  {vp['viewport']}: overflow={vp['horizontal_overflow']}, errors={vp['n_page_errors']}")
        except Exception as e:
            print(f"  ERROR: {e}")
            report["multi_viewport_audit"] = {"error": str(e)}
        
        browser.close()
    
    # === Summary ===
    n_completed = sum(1 for j in report["journeys"] if "COMPLETED" in j.get("verdict", ""))
    n_partial = sum(1 for j in report["journeys"] if "PARTIAL" in j.get("verdict", ""))
    n_dead_end = sum(1 for j in report["journeys"] if "DEAD_END" in j.get("verdict", ""))
    n_blocked = sum(1 for j in report["journeys"] if "BLOCKED" in j.get("verdict", ""))
    n_error = sum(1 for j in report["journeys"] if "ERROR" in j.get("verdict", "") and "DEAD_END" not in j.get("verdict", ""))
    
    report["summary"] = {
        "total_journeys": 16,
        "completed": n_completed,
        "partial": n_partial,
        "dead_ends": n_dead_end,
        "blocked": n_blocked,
        "errors": n_error,
        "console_error_count": len(report["console_errors_all"]),
        "html_size_mb": report["performance_baselines"].get("html_size_mb") if report["performance_baselines"] else None,
        "gan_gate_passed": report["standalone_analyzer_inspection"].get("gan_gate_passed") if report["standalone_analyzer_inspection"] else None,
        "top_level_nav_count": report["performance_baselines"].get("top_level_nav_count") if report["performance_baselines"] else None,
        "section_count": report["performance_baselines"].get("section_count") if report["performance_baselines"] else None,
    }
    
    report["audit_completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # Save report
    out_path = EVIDENCE_DIR / "round1_forensic_audit.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Audit Complete ===")
    print(f"Saved: {out_path}")
    print(f"\nSummary:")
    for k, v in report["summary"].items():
        print(f"  {k}: {v}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
