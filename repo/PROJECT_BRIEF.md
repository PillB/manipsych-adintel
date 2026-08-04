# ManiPsych Project Brief

## Mission

Build a defensive research and detection system for identifying psychological manipulation, dark patterns, persuasion methods, and influence-operation techniques in communications, with special focus on public "ayuda economica" content targeting women in Peru.

The system must support evidence-based analysis, privacy-aware data handling, and reproducible validation. It must not generate operational instructions for exploiting vulnerable people or improving manipulative outreach.

## Core Objectives

1. Build a detailed compendium of manipulation techniques, dark patterns, persuasion techniques, and PsyOps used in marketing, social media, ads, debates, and gaming.
2. Create a sociological dossier on women in Peru, including needs, wants, fears, vulnerabilities, and manipulation multipliers.
3. Research how people discuss posting "ayuda economica" ads on Peruvian forums and identify the main platforms where these ads appear.
4. Collect and log public real ads offering "ayuda economica" from the male-offering perspective, using local raw archival storage and redacted processed outputs.
5. Train AI/deep learning models to detect, tag, analyze, and score manipulation techniques in text.

## Execution Rules

- Execute phases sequentially.
- Use multiple research rounds and active fan-out in research phases.
- Use sub-agents for independent domains during research and validation.
- Apply Stanford STORM: multi-perspective source discovery, structured notes, synthesis, gap analysis, and iterative refinement.
- Apply Loop Engineering: define a test, run the work, validate, retrospect, and improve the next loop.
- After every phase, write an honest retrospective covering what worked, what failed, and what to improve next.
- Maintain evidence discipline with source metadata, citations, and reproducible validation.

## Mandatory Cycle

Every task must follow this cycle:

1. Read `AGENT_STATE.md`.
2. Act on the current sub-task.
3. Write and compress updates into `AGENT_STATE.md`.

## Phase Sequence

### Phase 0: Strategic Planning & Success Checklist

Define scope, objectives, measurable success criteria, and machine-checkable phase gates. Initialize `AGENT_STATE.md` with milestones, each checkbox carrying exactly three testable completion conditions.

### Phase 1: Exhaustive Multi-Round Research on Manipulation Techniques

Run at least three research rounds:

- Round 1: academic survey of psychological manipulation, dark patterns, persuasion, and PsyOps.
- Round 2: domain-specific deep dives in marketing, social ads, political communication, gaming monetization, loot boxes, pressure mechanics, and betting apps.
- Round 3: fan-out from references, related papers, case studies, and technique taxonomies.

Deliver a structured compendium with technique name, category, mechanism, examples, triggers, language patterns, and citations.

### Phase 2: Sociological Profile of Women in Peru + Multiplier Identification

Research economic independence, financial vulnerability, safety and gender-based violence, social status, family expectations, education, employment, aspirations, and stressors for young and young-adult women in urban and semi-urban Peru.

Deliver a professional dossier and manipulation-multiplier mapping.

### Phase 3: Forum Research on "Ayuda Economica" Posting Strategies

Research public Peruvian forums and similar communities for discussion of "ayuda economica" ads. Extract recurring defensive detection patterns, platform mentions, framing patterns, and connections to the Phase 1 and Phase 2 taxonomies.

Do not produce reusable ad templates or tactical advice for maximizing responses.

### Phase 4: Platform Identification and Massive Ad Collection

Identify public platforms where "ayuda economica" ads appear, then collect public listings where permitted. Archive raw public pages locally under `data/raw/`, store structured manifests, and emit redacted processed datasets. Target at least 10,000 ads or documented source exhaustion.

### Phase 5: AI Model Training for Manipulation Detection

Train and evaluate models to detect persuasion techniques, dark patterns, multipliers, manipulation intensity, and evidence-backed explanations. Include validation, robustness testing, and red-team cases.

### Phase 6: Final Integration, Documentation & Delivery

Consolidate the compendium, dossier, dataset manifests, trained model artifacts, model cards, validation results, and final report.

## Local Delivery Target

This project is implemented as a local-only research system. GitHub CI/CD and deployment are out of scope unless a future request changes the delivery target.
