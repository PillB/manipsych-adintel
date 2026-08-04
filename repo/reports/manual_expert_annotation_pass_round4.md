# Manual AI expert annotation pass — round 4

Date: 2026-07-09  
Mode: no-code expert annotation judgment  
Record reviewed: `h_f4fc363a9b8f997059ec332d2ec0effd3960edf30c9f677131a8a9061e43fd81`

## Why this pass was created

The user identified a Spanish localization issue: the existing automated council annotation captured `apoyo económico` but missed `apoyo económica`, a gender-agreement/orthographic error that is semantically the same support expression. This pass uses expert annotation judgment rather than rule output to correct the record and identify broader omission classes.

## Source text

```text
Brindó apoyo económica a señorita por compañía a e
Joven profesional brinda apoyo económico semanal a señorita estudiante de buen trato. Por compañía a lugares por elegir. Seguridad y discreción[REDACTED_CONTACT]
```

## Expert correction summary

The existing annotation was directionally correct but incomplete. The missing span is not a minor cosmetic issue: the title line combines support, youth-coded targeting, and conditional companionship. A Spanish localization-aware annotator should read `apoyo económica` as a typo/gender mismatch for `apoyo económico` and annotate it.

Manual expert overlay saved at:

`data/annotation/expert_manual_review_round4.jsonl`

## Corrected span inventory

| Span | Offsets | Label | Intensity | Manip | Harm | Rationale |
|---|---:|---|---:|---:|---:|---|
| `Brindó apoyo económica` | `[0,22]` | `reciprocity_obligation` | 3 | 2 | 2 | Typo/gender mismatch still frames economic support as help. |
| `por compañía` | `[34,46]` | `conditional_financial_support` | 4 | 3 | 3 | Directly conditions support on companionship. |
| `señorita` | `[25,33]` | `age_or_youth_targeting` | 3 | 2 | 2 | Youth-coded gendered target term. |
| `Joven profesional` | `[51,68]` | `authority_or_status_appeal` | 2 | 1 | 1 | Status/credibility framing. |
| `apoyo económico` | `[76,91]` | `reciprocity_obligation` | 3 | 2 | 2 | Economic support framed as help. |
| `semanal` | `[92,99]` | `commitment_escalation` | 3 | 2 | 2 | Weekly recurrence may create dependency. |
| `señorita` | `[102,110]` | `age_or_youth_targeting` | 3 | 2 | 2 | Repeated youth-coded target term. |
| `estudiante` | `[111,121]` | `education_or_student_targeting` | 3 | 2 | 2 | Student vulnerability target. |
| `buen trato` | `[125,135]` | `transactional_ambiguity` | 3 | 2 | 2 | Euphemistic softening of implied arrangement. |
| `Por compañía` | `[137,149]` | `conditional_financial_support` | 4 | 3 | 3 | Repeated direct exchange condition. |
| `discreción` | `[184,194]` | `privacy_or_secrecy_pressure` | 3 | 2 | 2 | Concealment in conditional arrangement. |
| `[REDACTED_CONTACT]` | `[194,212]` | `platform_migration` | 2 | 1 | 1 | Direct contact channel; label only because it functions as migration in this ad context. |

## Omission taxonomy for wider review

These are the error classes that should be reviewed by human/expert annotators across the corpus:

1. Gender mismatch: `apoyo económica`, `ayuda económico`, `trato discreta`, `reservado/reservada`.
2. Accent omission: `economico`, `discrecion`, `compania`, `situacion`.
3. Repeated-letter or swapped-letter typos: `economomico`, `nesecito`, `discrecionn`, `wasap/guasap`.
4. Informal platform slang: `wsp`, `wasap`, `guasap`, `pv`, `priv`, `imbox`, `msj`.
5. Conditionality abbreviations: `x compañía`, `x encuentros`, `a cambio`, `acambio`, `beneficio mutuo`.
6. Euphemistic exchange terms: `trato`, `arreglo`, `acuerdo`, `apoyo mutuo`, `buen trato`, `compartir momentos`.
7. Youth/student variants: `señorita`, `chica`, `jovencita`, `chibola`, `primeriza`, `universitaria`, `colegiala`.
8. Economic vulnerability variants: `apuros`, `urgencias`, `misia/misio`, `sin trabajo`, `deudas`, `gastos`, `alquiler`.
9. Safety/deceptive assurance variants: `100% seguro`, `real`, `serio`, `sin riesgo`, `nada malo`, `con respeto`.
10. Secrecy variants: `discreción`, `reserva`, `calladita`, `privado`, `entre nosotros`.

## Research-grounded interpretation

This ad combines several techniques described in the project primer:

- Reciprocity/support framing creates felt obligation.
- Conditional financial support turns aid into an exchange.
- Youth/student targeting increases vulnerability risk.
- Recurring weekly support can escalate dependency.
- Discretion adds concealment pressure.
- Status framing increases credibility/asymmetry.

The corrected expert document remains `gold=false` because it is an AI expert overlay, not two-human adjudicated gold.
