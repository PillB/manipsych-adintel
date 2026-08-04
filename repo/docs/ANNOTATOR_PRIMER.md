# ManiPsych annotator primer: persuasion and manipulation in offer-oriented ads

Version: research-v3 training draft  
Audience: Spanish-speaking human reviewers and adjudicators  
Scope: text-first annotation of offer-oriented ads, with platform/image metadata as context only

## 1. Purpose and safety frame

Your job is not to judge the people in an ad. Your job is to mark communicative techniques in the text that could influence, pressure, mislead, or exploit a reader. The dataset contains sensitive offer-oriented ads. Work slowly, use the smallest text span that supports a label, and separate what the ad says from what you infer.

This campaign uses candidate council/model suggestions only as later review aids. Human reviewers must make independent first-pass decisions. A record with no persuasive or manipulative technique is a valid negative example.

## 2. Research anchors refreshed for this primer

- SemEval-2023 Task 3 formalized multilingual persuasion-technique detection and used a 23-technique taxonomy at paragraph level across nine languages, including Spanish surprise evaluation. We adapt that spirit to ad-level span annotation.
- The 2025/2026 computational persuasion survey treats persuasion as context-dependent and separates AI as persuader, persuadee, and judge. For our task, model predictions are judgment aids, not ground truth.
- Recent dataset-quality surveys emphasize annotator training, agreement reporting, adjudication, validation, and transparent quality management.
- Just-in-time annotation intervention work shows that feedback and domain hints can improve label precision without replacing human judgment.
- Azure Machine Learning data labeling emphasizes project-specific instructions, task queues, keyboard label selection, correction before submission, and caution that prelabels can be wrong.
- Label Studio and similar tools emphasize hotkeys, configurable interfaces, stable region/result IDs, exportability, and review workflows.
- Pedagogy used here: worked examples, contrastive examples, retrieval practice, immediate feedback during training, gradual fading of hints, and transfer exercises on fresh examples.

## 3. Core decision model

Use this four-step loop on every ad.

1. Read the whole ad once without labeling.
2. Ask: “What action, belief, or emotional state is the ad trying to produce?”
3. Select the smallest exact phrase that supports a technique.
4. Assign label plus intensity, manipulativeness, harm risk, explicitness, vulnerability target, and rationale.

Do not label:

- ordinary topic words without an influence function;
- contact metadata by itself;
- platform exposure signals as persuasive techniques;
- your suspicion unsupported by text;
- extraction artifacts as evidence of manipulation.

## 4. Scales

Persuasive intensity, 0–4:

- 0: no technique.
- 1: weak cue; ordinary marketing or vague appeal.
- 2: clear persuasive cue, low pressure.
- 3: strong persuasive cue or repeated/central cue.
- 4: dominant or forceful persuasion; technique drives the ad.

Manipulativeness, 0–3:

- 0: persuasion without manipulation.
- 1: mild pressure, ambiguity, or asymmetry.
- 2: clear exploitation of vulnerability, secrecy, dependency, or misleading assurance.
- 3: coercive, highly exploitative, or strongly concealed conditionality.

Harm risk, 0–3:

- 0: no plausible harm from the technique.
- 1: low risk; mostly informational or benign.
- 2: moderate risk; vulnerable target, secrecy, dependency, or risky exchange.
- 3: high risk; sexual/economic coercion, youth/student targeting, threats, or severe concealment.

Explicitness:

- explicit: phrase directly says the cue.
- implicit: phrase strongly implies the cue through euphemism or context.
- unclear: evidence is weak; use sparingly and explain the uncertainty.

## 5. The 20 project labels

Each label includes positive cues, negative boundaries, examples, and common variations. Examples are synthetic and intentionally short.

### 5.1 reciprocity_obligation

Meaning: Frames the advertiser as giving help, support, gifts, favors, or care in a way that can create a felt obligation.

Mark phrases such as “brindo apoyo”, “te ayudo”, “compensación”, “engreír”, “detallista”, or “puedo apoyarte”.

Do not mark every mention of money here if the text is mainly a direct exchange; that may be `conditional_financial_support`.

Example: “Puedo brindarte apoyo económico semanal.”  
Best span: “brindarte apoyo económico”

Variations: benevolent-helper framing, gift framing, rescue framing, generosity framing.

### 5.2 conditional_financial_support

Meaning: Money, help, gifts, housing, or benefits are conditional on companionship, intimacy, meetings, discretion, photos, or another demanded action.

Mark phrases such as “a cambio de”, “por compañía”, “por encuentros”, “si nos vemos te apoyo”.

Do not mark simple compensation without a demanded condition unless context clearly supplies the condition.

Example: “Apoyo a cambio de salidas discretas.”  
Best span: “a cambio de salidas discretas”

Variations: explicit exchange, implied arrangement, sugar-style arrangement, conditional help.

### 5.3 transactional_ambiguity

Meaning: Euphemistic or vague wording obscures the nature of the exchange.

Mark “trato”, “acuerdo”, “arreglo”, “compañía”, “momentos”, “algo discreto”, “beneficio mutuo” when they blur terms.

Do not mark vague wording if it is not connected to an exchange or persuasion.

Example: “Busco una señorita para un acuerdo discreto.”  
Best span: “acuerdo discreto”

Variations: euphemism, coded transaction, ambiguous intimacy, “mutual benefit” framing.

### 5.4 platform_migration

Meaning: Pushes the reader away from the platform into private channels, especially when paired with secrecy, urgency, or conditionality.

Mark “escríbeme por WhatsApp”, “háblame al privado”, “solo inbox”, “coordinamos fuera”.

Do not mark redacted contact tokens alone unless the surrounding phrase pressures migration.

Example: “Háblame al privado para coordinar.”  
Best span: “Háblame al privado”

Variations: off-platform migration, private-channel funnel, direct-message pressure.

### 5.5 privacy_or_secrecy_pressure

Meaning: Requests or promises secrecy, discretion, confidentiality, hidden meetings, or silence.

Mark “discreción”, “secreto”, “reservado”, “sin que nadie se entere”, “confidencial”.

Do not mark ordinary privacy policy language.

Example: “Total discreción y reserva.”  
Best span: “Total discreción”

Variations: mutual secrecy, reputational concealment, hidden relationship.

### 5.6 scarcity_or_urgency

Meaning: Creates time pressure or limited availability.

Mark “urgente”, “hoy”, “solo una”, “última oportunidad”, “rápido”.

Do not mark dates or availability schedules without pressure.

Example: “Necesito respuesta hoy mismo.”  
Best span: “hoy mismo”

Variations: deadline, limited slots, immediate need.

### 5.7 commitment_escalation

Meaning: Encourages recurring, ongoing, or increasing dependency.

Mark “constante”, “permanente”, “semanal”, “cada encuentro”, “vernos seguido”.

Do not mark stable relationship language unless it implies dependency or repeated exchange.

Example: “Te puedo apoyar de manera permanente.”  
Best span: “manera permanente”

Variations: repeat meetings, ongoing allowance, dependency ladder.

### 5.8 foot_in_the_door

Meaning: Starts with a small request or trial to make later escalation easier.

Mark “primero conversemos”, “solo una salida”, “probamos”, “sin compromiso” when it lowers resistance.

Do not mark ordinary introductions without later persuasive pressure.

Example: “Primero conversemos y luego vemos.”  
Best span: “Primero conversemos”

Variations: trial framing, low-commitment entry, gradual ask.

### 5.9 authority_or_status_appeal

Meaning: Uses status, profession, solvency, maturity, respectability, or power to persuade.

Mark “profesional”, “empresario”, “solvente”, “serio”, “maduro”, “con estabilidad”.

Do not mark demographic identity unless used as appeal.

Example: “Soy profesional solvente y serio.”  
Best span: “profesional solvente”

Variations: status proof, respectability cue, maturity cue.

### 5.10 social_proof

Meaning: Uses popularity, followers, testimonials, reactions, or “others do this” to persuade.

Mark “muchas chicas”, “todos ganan”, “tengo referencias”, “varias aceptaron”.

Do not mark platform follower metadata as a text span; put that in context only.

Example: “Tengo referencias de chicas que ya apoyé.”  
Best span: “Tengo referencias”

Variations: testimonial, popularity, norming.

### 5.11 exclusivity_or_special_treatment

Meaning: Offers or demands special, exclusive, privileged, or chosen status.

Mark “solo para ti”, “exclusiva”, “especial”, “trato preferente”.

Do not mark “solo” when it simply limits geography or age.

Example: “Busco una chica exclusiva.”  
Best span: “chica exclusiva”

Variations: chosen-one framing, exclusivity, special access.

### 5.12 guilt_or_shame_pressure

Meaning: Uses shame, blame, moral pressure, or worthiness tests.

Mark “si eres seria de verdad”, “no hagas perder tiempo”, “no seas interesada”, “demuestra”.

Do not mark clear eligibility criteria unless phrased as moral pressure.

Example: “Solo chicas serias, no hagas perder el tiempo.”  
Best span: “no hagas perder el tiempo”

Variations: gatekeeping, shaming, moralized compliance.

### 5.13 fear_or_threat

Meaning: Uses threat, fear, intimidation, or negative consequences.

Mark “te arrepentirás”, “si no aceptas”, “puedo exponer”, “cuidado”.

Do not mark ordinary safety assurances here.

Example: “No cuentes nada o habrá problemas.”  
Best span: “habrá problemas”

Variations: coercive threat, exposure threat, intimidation.

### 5.14 deceptive_assurance

Meaning: Reassures in ways that may minimize risk, hide asymmetry, or overpromise safety.

Mark “100% seguro”, “sin riesgo”, “garantizado”, “no pasará nada”, especially with private exchange.

Do not mark reasonable safety logistics without overclaim.

Example: “Todo es 100% seguro y discreto.”  
Best span: “100% seguro”

Variations: false certainty, risk minimization, safety overclaim.

### 5.15 sexualized_appearance_condition

Meaning: Conditions acceptance or benefit on appearance, body, youth-coded attractiveness, photos, or sexualized presentation.

Mark “linda”, “delgada”, “atractiva”, “con fotos”, “buena presencia” when used as a condition or target.

Do not mark neutral self-description unless it pressures the reader.

Example: “Apoyo a chica linda y de buena presencia.”  
Best span: “linda y de buena presencia”

Variations: beauty gate, photo demand, body criterion.

### 5.16 age_or_youth_targeting

Meaning: Targets youth, young women, minors, or narrow young-age ranges.

Mark “18 a 20”, “joven”, “señorita”, “chica”, “colegiala” when youth is part of targeting.

Do not mark adult age ranges that are broad and not used as vulnerability cues unless context supports it.

Example: “Busco señorita de 18 a 22 años.”  
Best span: “18 a 22 años”

Variations: youth preference, school-coded youth, “primeriza”.

### 5.17 education_or_student_targeting

Meaning: Targets students, school/university status, tuition needs, or educational dependency.

Mark “estudiante”, “universitaria”, “colegiala”, “instituto”, “para tus estudios”.

Do not mark education as a neutral biography unless it is used to select or pressure.

Example: “Ayudo a universitaria con sus gastos.”  
Best span: “universitaria”

Variations: tuition pressure, student vulnerability, school status.

### 5.18 economic_vulnerability_targeting

Meaning: Targets financial hardship, debt, urgent need, poverty, joblessness, or economic dependence.

Mark “apuros económicos”, “necesite dinero”, “sin trabajo”, “deudas”, “malos momentos económicos”.

Do not mark generic payment if no vulnerability is invoked.

Example: “Si estás pasando apuros económicos, escríbeme.”  
Best span: “pasando apuros económicos”

Variations: hardship targeting, rescue from debt, urgent need.

### 5.19 family_obligation_targeting

Meaning: Uses children, family needs, caregiving duties, or family shame as leverage.

Mark “madre soltera”, “para tus hijos”, “ayudar a tu familia”, “gastos familiares”.

Do not mark family status if it is incidental and not persuasive.

Example: “Apoyo a madre soltera con gastos.”  
Best span: “madre soltera”

Variations: caregiving vulnerability, family duty, child-related need.

### 5.20 repetition_or_campaign_escalation

Meaning: Repeated posts, reposts, copy/paste campaigns, or text that escalates through repetition.

Mark textual cues such as “otra vez”, “sigo buscando”, “varias veces”, and use campaign context when the same advertiser/template repeats.

Do not mark every duplicated phrase inside one ad unless it creates pressure.

Example: “Sigo buscando chica para apoyo semanal.”  
Best span: “Sigo buscando”

Variations: repost pressure, campaign persistence, repeated ask.

## 6. Boundary cases

### Persuasion versus manipulation

Persuasion can be open and non-exploitative: “Busco amistad con respeto.” Manipulation adds concealment, pressure, vulnerability targeting, dependency, deception, or coercive asymmetry: “Te ayudo si aceptas vernos en secreto.”

### Context versus span

If an ad is promoted, has followers, or has images, record that as context. Do not label those as text spans unless the text itself says “mucha gente me recomienda” or similar.

### Multiple labels on one phrase

Overlaps are allowed. “Apoyo semanal a estudiante discreta” can support:

- “Apoyo semanal” = reciprocity + commitment escalation.
- “estudiante” = education/student targeting.
- “discreta” = privacy/secrecy pressure.

### Negative examples

If no span meets a label definition, mark the document as negative and set intensity/manipulativeness/harm to 0. Write a rationale such as “No persuasive or manipulative technique beyond neutral ad content.”

## 7. Worked examples

### Example A

Text: “Apoyo económico a universitaria que esté pasando apuros, a cambio de salidas discretas.”

Correct spans:

- “Apoyo económico” → reciprocity_obligation, intensity 3.
- “universitaria” → education_or_student_targeting, harm 2.
- “pasando apuros” → economic_vulnerability_targeting, harm 3.
- “a cambio de salidas discretas” → conditional_financial_support, manipulativeness 3, harm 3.
- “discretas” → privacy_or_secrecy_pressure, manipulativeness 2.

Common mistake: labeling the whole sentence once. Use smaller spans so adjudicators can see the evidence.

### Example B

Text: “Soy profesional serio. Busco conversación y amistad sin compromiso.”

Possible span:

- “profesional serio” → authority_or_status_appeal, intensity 1 or 2 if used to persuade.

Do not invent conditionality if none is present.

### Example C

Text: “Solo una chica linda, 18 a 22, con total reserva. Pago semanal.”

Correct spans:

- “Solo una” → scarcity_or_urgency or exclusivity_or_special_treatment depending on context.
- “linda” → sexualized_appearance_condition.
- “18 a 22” → age_or_youth_targeting.
- “total reserva” → privacy_or_secrecy_pressure.
- “semanal” → commitment_escalation.

## 8. Practice exercises

For each item, select labels before looking at feedback.

1. “Te puedo ayudar con tus gastos si aceptas vernos en privado.”
   - Expected: reciprocity_obligation, conditional_financial_support, economic_vulnerability_targeting, platform/privacy if “privado” means secrecy.

2. “Busco mujer para amistad, sin pagos ni condiciones.”
   - Expected: likely negative; possibly no spans.

3. “Universitaria joven, escribeme hoy, total discreción.”
   - Expected: education_or_student_targeting, age_or_youth_targeting, scarcity_or_urgency, privacy_or_secrecy_pressure.

4. “Soy empresario solvente, puedo engreírte con regalos.”
   - Expected: authority_or_status_appeal, reciprocity_obligation; manipulativeness depends on conditionality.

5. “No hagas perder tiempo; solo chicas serias que sepan guardar secreto.”
   - Expected: guilt_or_shame_pressure, privacy_or_secrecy_pressure, possibly exclusivity/gatekeeping.

## 9. Reviewer quality checklist

Before submitting:

- Every span resolves exactly to selected text.
- Offsets are zero-based and end-exclusive.
- Overlapping spans are separate annotations.
- You did not use model/council suggestions before independent submission.
- Context signals are not mislabeled as techniques.
- Rationale explains why the label applies.
- Document scales match the highest-risk evidence.
- Negative examples are explicitly marked.

## 10. Adjudicator checklist

When comparing reviewers:

- Resolve boundary disagreements first, then label disagreements.
- Prefer smallest sufficient span unless broader phrasing is necessary.
- Preserve multi-label overlap when both labels are defensible.
- Escalate repeated ambiguity to guideline revision.
- Track drift by source, label, round, and reviewer.

## 11. Source notes

This primer is grounded in current research and tool practice: SemEval-2023 Task 3; computational persuasion survey accepted to ACM Computing Surveys; dataset annotation quality management research; LabelAId just-in-time annotation interventions; Azure Machine Learning data labeling documentation; Label Studio hotkeys/export documentation; and standard instructional scaffolding practices such as worked examples, prompts, feedback, fading, and transfer.
