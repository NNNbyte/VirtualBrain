---
name: r3-virtual-patient
description: R3 Virtual patient for the epilepsy research system. Maintains competing seizure-network hypotheses and fits virtual-brain models (Wang et al. 2025 VBT / VBT_INS_Stimulation, TVB Epileptor, optional BVEP, network baseline); produces NetworkHypothesisSet and ModelBundle ensembles with diagnostics.
disable-model-invocation: true
---

# R3 · Virtual patient

First read `../run-study/references/agent-protocol.md`.

## Modeling basis
Use Wang et al. (2025), *Virtual brain twins for stimulation in epilepsy*, and its VBT_INS_Stimulation
software and published code and data capsules as the primary modeling and simulation basis. Use the
passed MethodCard for exact repo and version. Alternatives: a reproducible network baseline (for example
Epileptor-based network on the patient connectome), The Virtual Brain (TVB), and optional Bayesian
Virtual Epileptic Patient (BVEP) inference.

## Inputs
A case with passed QC, passed MethodCards, presurgical observations (SEEG onset and propagation,
anatomy, connectome), and the frozen fitting partition from the CohortSplit. **Never** reserved outcomes.

## Qualification benchmark (before any patient)
A `model_benchmark` task comes first, with `--case SYN-<name>`. Patient fitting starts only after R5 has
gated its ModelBundle as passed.
- Plant a known epileptogenic zone with a recorded seed. Log the full generating parameter map with
  `task log` **before any fit**.
- Simulate through the **full** pipeline: raw-like signals, then your feature extraction, then the
  likelihood. Do not generate features directly; that skips the feature code.
- Fit two arms. One uses the generating connectome; the other uses the template connectome you will use
  for patients.
- Pass: the planted EZ ranks 1st, x0 R-hat < 1.05 for every region, and false positives are reported.
  If the generating-connectome arm fails, the pipeline is not qualified. Stop and report; do not tune
  against patients.

## Signal handling
- Read the sampling rate from **each file** (time steps, EDF header, sidecar). Never assume a rate from
  example code; vep-stim notebooks hard-code 250 Hz, which matched none of the Wang files (100 and
  125 Hz).
- Check the observation model against the residuals. An iid likelihood on autocorrelated noise biases
  the fit; report residual autocorrelation and model it if it is large.
- Package code is not trusted by default. When you patch it, patch a copy in your work dir, record the
  diff, and check the patched log density against an independent re-implementation.

## Procedure
1. **Hypotheses:** commit a NetworkHypothesisSet with alternative epileptogenic-zone and propagation
   hypotheses, their source evidence (SEEG markings, imaging), priors, unobserved-node assumptions, and
   the checks that would discriminate them.
2. **Environment:** verify the engine is runnable (`pip show tvb-library`, clone the VBT repo at a
   pinned commit, record `--code-commit` and `--env-digest`). If it cannot run, open a need and commit
   nothing pretending to be a fit.
3. **Fit** each hypothesis on the fitting partition only. Use several seeds and chains. Record
   parameters or posterior, observation model, numerical diagnostics, **convergence checks** (R-hat,
   ESS, divergences, or optimizer convergence), recovery or identifiability on synthetic data, and
   posterior predictive checks against held-out *presurgical* seizures, not outcomes.
4. Commit a **ModelBundle** ensemble (`--evidence-kind fitted_estimate`, `--case`). Include an
   `environment_manifest` (exact commands, versions, seeds) and attach large outputs with `--attach`.
   Set `intended_use`, for example "rank candidate interventions on this virtual patient; not a clinical
   prediction".
5. Preserve uncertainty. Keep competing hypotheses whose fit is comparable rather than picking one. If
   you use a generic template connectome for a sensitivity analysis, label it as such.

## Acceptance
Numerical, convergence, recovery, and identifiability checks and predictive criteria satisfy the declared
intended use. R5 checks this independently.

## Boundaries
No reserved outcomes, ever. A fitted posterior is not a calibrated probability of seizure freedom.
