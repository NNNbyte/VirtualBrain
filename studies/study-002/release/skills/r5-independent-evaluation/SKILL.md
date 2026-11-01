---
name: r5-independent-evaluation
description: R5 Independent evaluation for the epilepsy research system. Source checks, model qualification, independent simulation reruns and robustness (SimulationComparison), and the separate blinded historical-outcome evaluation (OutcomeEvaluation) through the audited outcome vault; records gate verdicts and ValidationReports.
disable-model-invocation: true
---

# R5 · Independent evaluation

First read `../run-study/references/agent-protocol.md`.

You are the independent check. Your task type tells you which job you are doing. **Never** mix them.

## Task types

### `source_check`: gate R1 evidence
For each input artifact, re-open the cited source and confirm that the passage and location resolve,
that population, design, and endpoint are correctly transcribed, and that reported and verified fields are
kept apart. Record a gate per artifact:
`gate record --artifact A --criterion "<frozen criterion from the task>" --verdict passed|failed|indeterminate --evaluator R5 --reason "..."`
Commit one ValidationReport summarising the check.

### `model_qualification`: gate R3 model bundles
Independently rerun or reload the model from its `environment_manifest`. Verify convergence, numerical
stability, recovery and identifiability, and held-out presurgical predictive checks against the declared
intended use. Gate each ModelBundle and commit a ValidationReport.

### `simulation_comparison`: independent reruns, no reserved labels
Re-execute a subset of SimulationBatch entries from their recorded seeds and settings and compare against
R4's outputs (reproducibility). Run robustness checks across model samples and hypotheses. Compute
paired effects with uncertainty. Commit a **SimulationComparison** (`--evidence-kind simulated_result`)
with a freeze manifest (hashes of everything evaluated) and an evidence level. Flag unstable rankings.

### `outcome_evaluation`: blinded historical outcomes (vault)
Only after the lead has frozen predictions. The task inputs are the frozen ids.
1. Confirm in `status` that your inputs appear in `frozen_predictions`.
2. `vault reveal --task <T> --item <V>`. This access is audited. Read the outcome file only for this
   task and do not copy it elsewhere.
3. Compute locked, patient-level metrics as the protocol specifies (for example concordance between
   model-recommended and delivered intervention versus Engel/ILAE class), with uncertainty (bootstrap
   CI) and abstentions. Preserve the original outcome categories.
4. Commit **OutcomeEvaluation** (`--evidence-kind clinical_follow_up`, consumed = frozen predictions +
   vault item id) and a **ValidationReport**.

## Boundaries
Do not rewrite or refit a frozen model after seeing outcomes. Simulation-comparison tasks never receive
reserved labels. Do not gate artifacts you produced. Preserve split independence. Multiple papers or
agents reusing the same patients are not independent evidence.
