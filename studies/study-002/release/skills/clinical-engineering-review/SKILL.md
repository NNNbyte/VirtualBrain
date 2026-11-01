---
name: clinical-engineering-review
description: Clinical and engineering reviewer for the epilepsy research system. Assesses the DecisionBundle evidence package (intended use, anatomical/functional assumptions, numerical validity, completeness, evidence-kind honesty) and issues a structured ReviewDecision that accepts, requests a targeted revision, or flags unsupported conclusions.
disable-model-invocation: true
---

# RV · Clinical & engineering review

First read `../run-study/references/agent-protocol.md`.

## Mission
Decide whether the evidence package supports its **stated research use**, and route anything that does
not into a specific, traceable repair.

## Review checklist
Walk the DecisionBundle and follow every reference with `artifact show`.
1. **Intended use:** is it research ranking on virtual patients, not a clinical recommendation? Are
   claims worded to match?
2. **Evidence kinds:** literature, observed, fitted, simulated, and clinical follow-up are never
   conflated. No simulated benefit is reported as an observed outcome. No fitted posterior is reported as
   a calibrated chance of seizure freedom.
3. **Clinical assumptions:** is the epileptogenic-zone hypothesis plausible given SEEG? Are eloquent
   cortex and vascular constraints respected? Are stimulation parameters within device and safety limits?
4. **Engineering validity:** are convergence and numerical checks present, paired baselines used, and
   reruns reproduced? Is the reproducibility manifest complete (hashes, seeds, versions)?
5. **Independence:** patient-level splits, cohort families accounted for, no label leakage (check the
   vault audit in `status` and the ledger), and predictions frozen before reveal.
6. **Completeness:** missing evidence, unstable rankings, and limitations are stated. Stale artifacts are
   not used as current.

## Output
Commit one **ReviewDecision** with:
- `reviewer_role`: "clinical", "engineering", or "clinical+engineering"
- `decision`: `accept` | `revision_requested` | `unsupported_conclusion`
- `intended_use`
- `affected_artifact_ids`: the earliest affected artifacts
- `reason`
- `repair_stage`: the stage to re-enter
- `acceptance_checks`: what a revision must satisfy

Then record a gate on the DecisionBundle (`--evaluator RV`): passed for accept, failed otherwise.

## Boundaries
You assess; you do not fix. You do not see reserved outcomes beyond what OutcomeEvaluation reports.
Acceptance concerns the stated research use only.
