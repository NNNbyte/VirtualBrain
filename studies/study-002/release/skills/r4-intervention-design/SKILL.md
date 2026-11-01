---
name: r4-intervention-design
description: R4 Intervention design for the epilepsy research system. Generates feasible surgery (resection/ablation) and stimulation (contacts, waveform, device) scenarios on a qualified virtual-patient model, checks physical feasibility, and specifies explicit simulation requests and batches with paired baselines.
disable-model-invocation: true
---

# R4 · Intervention design

First read `../run-study/references/agent-protocol.md`.

## Mission
Propose **realizable** interventions and turn every candidate comparison into an explicit, reproducible
computation. A changed disease-model parameter is not an intervention.

## Inputs
A passed ModelBundle (`model_bundle_id` in the task), presurgical constraints (eloquent cortex, vascular,
and contact positions), allowed intervention classes, objective definitions, candidate budget, and
permitted comparison records. **Never** reserved outcomes.

## Procedure
1. **Surgery candidates** → **SurgeryPlan**. Use the `surgery` contract: resection or laser-ablation
   geometry in patient space with `--context coordinate_frame=... coordinate_units=mm transform_chain_id=...`,
   mapping to model nodes, constraints, and feasibility verdict. Give each a model-independent
   `intervention_id`.
2. **Stimulation candidates** → **StimulationPlan**. Use the `stimulation` contract: contacts, device,
   waveform (amplitude, frequency, pulse width, duration), physical mapping to model nodes (field or
   volume-of-tissue estimate), safety limits, and feasibility verdict. Follow the VBT_INS_Stimulation
   approach where applicable.
3. **FeasibilityReport** per plan: physical-model checks, charge density, and anatomical constraints.
   Infeasible candidates are recorded, not dropped.
4. **InterventionScenarioSet** with plan refs, exact model samples (posterior draws or ensemble members),
   objectives (for example seizure-propagation suppression versus tissue removed or charge delivered),
   controls (no intervention, sham, and the clinically delivered intervention if known *from presurgical
   planning*, not outcome), uncertainty sampling, and stopping criteria.
5. **SimulationRequest**, then run it with your worker script and commit a **SimulationBatch**
   (`--evidence-kind simulated_result`). Include actual samples, seeds, initial states, solver settings,
   **paired baselines** (same sample and seed with and without intervention), output refs, numerical
   checks, and resource use.
6. Optional **CandidateComparisonProposal**: tradeoffs and a Pareto view. If ranking is unstable under
   uncertainty, request fresh validation samples rather than claiming a winner. Final comparison claims
   must come from R5's independent records.

## Boundaries
Separate surgery and stimulation contracts. No reserved outcomes. No device control. Do not tune the model
toward a preferred intervention. If a model change is needed, open a need for R3, which creates a new model
branch.
