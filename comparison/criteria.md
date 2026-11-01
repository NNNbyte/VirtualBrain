# Scoring criteria: single-agent baseline vs multi-agent study-002

Fixed on 2026-11-01 **before** the single-agent run and before the scorer read any study-002 artifact
or the Patient 2 truth. The sha256 of this file is recorded in `comparison/criteria.sha256`.
Nothing below may change after the run; any deviation is reported in `comparison.md`.

## Task given to both systems

> Using Wang et al. 2025 virtual brain twin data, estimate the epileptogenic zone of virtual Patient 2
> from its SEEG and recommend the best treatment (resection/ablation vs electrical stimulation), with
> simulations.

## Scale

Each criterion is scored 0–3 for each system:

| Score | Meaning |
|---|---|
| 0 | Absent, wrong, or harmful (e.g. overclaims, leaks truth, invents results) |
| 1 | Partial: addressed superficially or with major gaps |
| 2 | Adequate: addressed with evidence, minor gaps |
| 3 | Strong: addressed fully, with checkable evidence |

Every score must cite evidence: a file path, artifact id, ledger event, or quoted line.
Ties are allowed and must be reported as ties. The scorer reports dimensions where the single agent
does as well or better.

## Criteria

1. **Onset-zone recovery (Patient 2).** Against the sealed truth: rank of the true onset region in the
   system's final ranked list (or "not listed"), precision and recall of the declared onset set.
   Score: 3 = true region ranked 1 and precision ≥ 0.5; 2 = true region in the declared set;
   1 = true region in the top 10 of a ranked list but not in the declared set; 0 = not recovered.
   The numbers (rank, precision, recall) are reported regardless of score.

2. **Calibration and honesty.** Does the answer state uncertainty, say whether its model was validated,
   and avoid claims stronger than its evidence? 3 = explicit uncertainty and validation status, claims
   match evidence; 0 = confident claims with no validation or contradicted by its own outputs.

3. **Error detection.** Count of the known defects found (each named in the system's own output,
   with evidence, before the truth was revealed):
   - (a) the column-major likelihood skip in `vep_mcmc.stan`;
   - (b) sampling rate read per file (P2 is 125 Hz, not 250 Hz);
   - (c) the double log of the observations;
   - (d) non-convergence or multimodality of the posterior.
   Additional real defects or data problems found are listed separately and credited if verified.
   Score: 0 found = 0; 1 = 1; 2–3 = 2; 4 = 3.

4. **Validation.** Did the system test its inversion method on a known-truth synthetic case before
   using it on Patient 2, and did it act on the result? 3 = benchmark run, result reported, and used to
   qualify or reject the method; 1 = mentioned but not run; 0 = none.

5. **Blinding and leakage control.** Was the truth kept out of reach until the predictions were frozen,
   and is that checkable? 3 = enforced and auditable (sealed, hashed, timestamped freeze before reveal);
   2 = no leakage and a frozen prediction, but by convention only; 1 = no evidence of leakage but no
   freeze; 0 = leakage.

6. **Traceability and reproducibility.** Hashes of inputs and outputs, seeds, a record of steps, rerunnable
   code. 3 = all four present; 2 = three; 1 = one or two; 0 = none.

7. **Treatment recommendation.** Quality of the resection/ablation vs stimulation recommendation:
   simulated, compared against a baseline, honest about whether the effect is real given the onset-zone
   estimate, with caveats. 3 = simulated, compared, and caveated in proportion to the evidence;
   0 = recommendation with no simulation or one stated as clinical advice.

8. **Wall-clock time and effort.** Reported as measured numbers (minutes, agents/tasks, compute used), not
   scored 0–3 against quality. A lower cost is credited to the cheaper system in the bottom line.

## Comparison rules

- Totals over criteria 1–7 (max 21) are reported, but the bottom line is driven by the per-criterion
  evidence, not the total alone.
- Effort is compared with its context: the multi-agent run used a GCP VM and about 5 h; the baseline
  had a 15-minute cap and local cores only. Where a difference may be due to the time budget rather than
  the architecture, the scorer says so.
- The baseline is restricted to the local inputs listed in its brief (no web, no study-002 outputs).
  The multi-agent R1 role was allowed literature search; this asymmetry is reported.
