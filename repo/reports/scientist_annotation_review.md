# Scientist annotation review

Status: candidate council annotations reviewed against persuasion/manipulation literature. These are not human-adjudicated gold labels.

## Online research anchors

- [SemEval-2023 Task 3](https://aclanthology.org/2023.semeval-1.317/): Multilingual persuasion-technique detection; supports paragraph/span-level technique annotation.
- [MentalManip](https://arxiv.org/abs/2405.16584): Manipulation is context-dependent and should include techniques plus vulnerabilities targeted.
- [Cialdini, Harnessing the Science of Persuasion](https://hbr.org/2001/10/harnessing-the-science-of-persuasion): Reciprocity, commitment/consistency, social proof, authority, liking, and scarcity persuasion principles.
- [Dark Patterns at Scale](https://arxiv.org/abs/1907.07032): Separates coercion, steering, deception, and potential harm; supports explicit manipulativeness scoring.
- [FTC, Bringing Dark Patterns to Light](https://www.ftc.gov/reports/bringing-dark-patterns-light): Regulatory synthesis of manipulative design practices, autonomy impairment, tricking/trapping, and hidden costs.
- [Fine-Grained Analysis of Propaganda in News Articles](https://arxiv.org/abs/1910.02517): Supports fragment-level explainable spans instead of document-only noisy labels.
- [A Survey on Computational Propaganda Detection](https://arxiv.org/abs/2007.08024): Supports combining text signals with campaign/account coordination and micro-targeting context.
- [Consumer Manipulation via Online Behavioral Advertising](https://arxiv.org/abs/2401.00205): Frames manipulation as exploitation of decision-making vulnerabilities in targeted advertising.
- [End-user perspective on dark patterns](https://arxiv.org/abs/2104.12653): Shows awareness alone may not let users resist manipulative designs; supports harm-risk separation.
- [A Comprehensive Study on Dark Patterns](https://arxiv.org/abs/2412.09147): Large consolidated taxonomy; motivates broader detection beyond a few canonical dark-pattern types.
- [Persuasion principles in phishing survey](https://arxiv.org/abs/2412.18488): Connects reciprocity, authority, scarcity, commitment, liking, and social proof to social-engineering risk.
- [Persuasive technology workplace systematic review](https://arxiv.org/abs/2201.00329): Supports distinguishing persuasion, feedback, prompts, and employer/agent agenda alignment.
- [Fogg Behavior Model / persuasive technology](https://dl.acm.org/doi/10.1145/1541948.1541999): Motivation, ability, and prompt/trigger framing; supports urgency and private-contact prompts as behavior triggers.
- [Persuasion Knowledge Model](https://academic.oup.com/jcr/article-abstract/21/1/1/1797193): Supports reporting uncertainty and not treating model extraction quality as evidence of manipulation.

## Validation findings

- Coverage gate passed: every one of 5,717 ads has a resolved council suggestion set.
- Consensus gate passed for candidate use: all resolved rows come from the latest accepted council round available per record.
- Research-v2 taxonomy applied: direct-contact prompts, urgency, vulnerability, repetition, social proof, fear/loss, and gatekeeping cues were broadened from the expanded literature review.
- Taxonomy fix retained: generic ayuda/apoyo spans are `reciprocity_obligation`; `a cambio/si/por sexo-intimidad` spans are `conditional_financial_support`.
- Research alignment is adequate for candidate modeling: spans include technique labels, vulnerability targets, intensity, manipulativeness, harm risk, and provenance.
- Main unresolved limitation: image pixels are not archived, so image-only persuasion cannot be validated.
- Schema gate passed: no labels outside the 20-label pilot schema were found.

## Counts

- Records: 5717
- Resolved candidate spans: 33720
- Records with zero spans: 5
- Platform counts: `{"ciudadanuncios": 1303, "doplim": 2824, "evisos": 2, "facebook": 26, "locanto": 1562}`
- Consensus rounds: `{"3": 5717}`

## Label distribution

- `reciprocity_obligation`: 9737
- `age_or_youth_targeting`: 6548
- `authority_or_status_appeal`: 2833
- `privacy_or_secrecy_pressure`: 2704
- `education_or_student_targeting`: 2277
- `economic_vulnerability_targeting`: 2238
- `conditional_financial_support`: 1624
- `platform_migration`: 1573
- `family_obligation_targeting`: 1012
- `sexualized_appearance_condition`: 875
- `commitment_escalation`: 636
- `transactional_ambiguity`: 533
- `scarcity_or_urgency`: 362
- `deceptive_assurance`: 271
- `exclusivity_or_special_treatment`: 258
- `foot_in_the_door`: 118
- `repetition_or_campaign_escalation`: 89
- `guilt_or_shame_pressure`: 23
- `social_proof`: 8
- `fear_or_threat`: 1

## Required fixes applied

- Corrected the reciprocal-help vs conditional-exchange label inversion in the council runner.
- Expanded research anchors from 5 to 15 sources across persuasion, propaganda/NLP, dark patterns, consumer vulnerability, social engineering, and persuasive technology.
- Added a research-v2 council round with broader cues for direct contact, urgency, social proof, fear/loss, gatekeeping, repetition/campaign escalation, and conditional sexual/companionship exchange.
- Recomputed consensus signatures and re-exported resolved council annotations from the latest accepted round.

## Remaining restrictions

- Do not call these labels gold until two blinded human reviews and adjudication are complete.
- Do not claim independent model validity from candidate-label metrics.
- Treat Facebook and Evisos as undersized challenge cohorts.
- Treat image-derived conclusions as unavailable unless image pixels are archived later.
