# Single agent vs multi-agent (study-002): Patient 2 epileptogenic zone and treatment

Research on virtual patients from Wang et al. 2025. Not a clinical recommendation.

## Setup and integrity record

| Item | Value |
|---|---|
| Scoring criteria | `comparison/criteria.md`, sha256 `54ef973c2bc9799bc616767b47ed0da484babddc4b9964ae1f6c4f7afc0551f9`, fixed 12:18:21 (UTC−5) before the run and before the scorer read any truth or study-002 record |
| Baseline | One general-purpose subagent: no roles, no controller, no checker, 15-min cap. Local inputs only (P1/P2 npz, LUT, EMF, `data/wang-co2-ana`, the `vep_stim` package, CmdStan). No web access |
| Baseline run | Started 12:18:30, answer written 12:20:28, finished 12:20:44 (UTC−5). **2 min 11 s**, 12 tool calls, about 82k tokens. It used 2 of its 15 minutes |
| Baseline answer | `comparison/single_agent/answer.md`, sha256 `3f73e4fa66291553278f638450c463d08823cef31b94c9728f764c8bc75b6df3`, hashed at 12:20:44, before the truth was read |
| Leakage audit of the baseline | No tool input in its transcript touched `studies/`, `reports/`, `presentation/`, `system/`, `framework/`, `.claude/` or any `.pkl`. The npz files hold no truth keys (only `seeg`/`eeg`, `gain`, `SC`, `ch_names`, `time_steps`). A grep of `vep_stim` found no hard-coded onset-zone index |
| Truth | `studies/study-002/artifacts/A0043-OutcomeEvaluation/ez_recovery.json`: one true region, npz column 15, Left-F1-lateral-prefrontal |
| Multi-agent run | Ledger: study initialised 13:03:16 UTC, predictions frozen 17:06:11, vault opened 17:06:55, outcome evaluation A0043 at 17:13:42, dossier A0045/A0046 at 17:14:37. **4 h 11 min to the first dossier**, with review rounds still running at 17:22. 23 tasks, 53 artifacts, 33 gates, 5 repairs, plus a GCP VM. Setup before study initialisation is not in the ledger (the session estimate is about 5 h) |

## Scores (0–3, from `criteria.md`)

| # | Criterion | Single agent | Multi-agent | Better |
|---|---|---|---|---|
| 1 | Onset-zone recovery | **1**: true region ranked 4th of 7; declared EZ (top 3) precision 0, recall 0 | **0**: recall 0 in every window; true region ranked 46–159 of 162 | **Single agent** |
| 2 | Calibration and honesty | **2**: says the model is unvalidated, x0 was set by hand and there is no posterior, but still recommends a treatment | **3**: "EZ recovery not achieved", "best intervention not determinable", model reported as unqualified | Multi-agent |
| 3 | Error detection (4 known defects) | **0**: 0 of 4 | **3**: 4 of 4, plus the stimulation-induced seizure | Multi-agent |
| 4 | Validation on known-truth synthetic data | **0**: none | **3**: two benchmarks run; both failed, and the models were rejected | Multi-agent |
| 5 | Blinding and leakage control | **1**: no leakage, but no freeze by the system itself; the answer was hashed by the experimenter | **3**: predictions frozen (seq 205) before vault access (seq 214), hashed in the ledger | Multi-agent |
| 6 | Traceability and reproducibility | **1**: rerunnable scripts and a log; no hashes, no seeds | **3**: SHA256SUMS, seeds 1000+i, ledger, bit-exact rerun by R5 | Multi-agent |
| 7 | Treatment recommendation | **1**: simulated against a baseline, but circular (x0 set by hand from its own EZ guess); recommends stimulating 3 regions that do not include the true region | **3**: paired simulations reproduced by R5; ranking declared unverifiable once the true model showed no spontaneous seizure | Multi-agent |
| | **Total (max 21)** | **6** | **18** | |
| 8 | Wall clock and effort | **2 min 11 s**, 1 agent, 12 tool calls, local CPU | **4 h 11 min** (ledger), 23 tasks, 53 artifacts, GCP VM | **Single agent**, about 115 times faster |

## Evidence by criterion

### 1. Onset-zone recovery: the single agent did better

- **Single agent.** The final ranking in `single_agent/ez3_log.txt` and `answer.md` is:

  | Rank | Column | Region |
  |---|---|---|
  | 1 | 9 | Left-Middle-frontal-sulcus |
  | 2 | 12 | Left-F1-mesial-prefrontal |
  | 3 | 93 | Right-F1-mesial-prefrontal |
  | **4** | **15** | **Left-F1-lateral-prefrontal** (the true region) |
  | 5 | 10 | Left-SFS-rostral |
  | 6 | 16 | Left-F1-lateral-premotor |
  | 7 | 94 | Right-PreSMA |

  The agent declared ranks 1–3 as the EZ, giving precision 0/3 and recall 0/1. Its "likely spread zone" is ranks 4–6. Counting EZ plus spread zone, recall is 1/1 and precision 1/6. Re-ranking `ez_score.npy` gives column 15 rank 4.
- **Multi-agent.** From A0043 `ez_recovery.json`:
  - Every frozen estimate has recall 0: A0018 (MAP), A0019 (NUTS), and both the "post" and "full" windows.
  - The true region's rank is 46 to 159 of 162.
  - The R3 hypothesis set A0017 did place column 15 among the 5 propagation candidates of hypothesis H1 (`true_ez_in_pz: true`). That level of performance is close to the single agent's.
- **Caveat: n = 1 patient.** Rank 4 from a regularised gain-matrix inversion may be partly luck. In the baseline's own log, column 15 also has the highest gain-correlation of the ten listed regions (0.816), but that is a post-hoc observation, and the agent did not choose that ranking.
- **What this shows.** The multi-agent Bayesian pipeline (2D Epileptor, Stan) did worse at localisation than a 2-minute source-imaging heuristic. Its main lesson ("model mismatch", A0046) is consistent with this.

### 2. Calibration and honesty

- **Single agent.** The answer opens with: "I did not run the full Bayesian (Stan/BVEP) fit … Treat this as a first pass." Its limitations section says the x0 values "were not fitted" and that it "could not validate the ranking". It still states a preferred treatment, and it reads its circular simulation as "both remove seizures". The caveats are honest, but the recommendation goes beyond the evidence.
- **Multi-agent.** A0046 says "EZ recovery … not achieved" and "Best virtual intervention: not determinable". The decision bundle A0045 lists "unqualified model" and its missing evidence. This matches what the evidence supports.

### 3. Error detection: 0 of 4 vs 4 of 4

| Defect | Single agent | Multi-agent |
|---|---|---|
| (a) Column-major likelihood skip in `vep_mcmc.stan` | Missed: it read `vep_mcmc.stan` (`sed -n 1,197p`) but did not flag the skip | Found: A0005, "loop (10*ns+1):(nt*ns) over column-major to_vector → drops first 10*ns/nt channels" |
| (b) Sampling rate per file (P2 is 125 Hz) | Not flagged as a defect. It did use 8-ms steps for P2 correctly, but never ran the package pipeline, so the 250 Hz assumption never mattered for it | Found: A0013 ("125 Hz if ms"), "Filter sampling rate hard-coded to 250 Hz", and "P1 100 Hz, P2 125 Hz" |
| (c) Double log of the observations | Missed | Found and fixed in R3's model: A0036/A0037 `vep_ar1.stan`, "Obs … NOT logged again (vep_mcmc.stan:27 double log)" |
| (d) Non-convergence or multimodality | Not applicable (no sampler run); not discussed | Found: A0037/A0042, x0 R-hat up to 4.7–6.4, 24 MAP optima with different top regions |

Other data problems:
- **Stimulation-induced seizure.** The multi-agent found that P2's seizure follows a 50 Hz stimulation train at about 0.5–3.5 s (A0017 H4, A0010). The single agent missed this. Its "ictal window" (0.8–7.6 s) includes the stimulation train, so part of its activity map is a stimulation-driven response.
- **Ill-conditioned gain matrix.** The single agent found that the gain matrix is badly conditioned (condition number about 5e6) and that an unregularised inversion is unusable. It also flagged possible cross-midline leakage for column 93. Both are real and useful observations.

### 4. Validation

- **Single agent.** It ran no synthetic test, and its answer says so.
- **Multi-agent.**
  - A0037 (v2) benchmark: planted EZ ranked 2nd, R-hat up to 4.7. Failed.
  - A0040 (v3) benchmark: P(EZ rank 1) = 0.012, and NUTS never finished warm-up. Failed.
  - R5 then ruled every model bundle "NOT QUALIFIED" (A0042).

  The validation worked: it stopped the multi-agent from claiming a model that did not work.

### 5. Blinding

- **Single agent.** It never had access to the truth. That came from the experimenter's brief, not from anything the agent did. It did not freeze or hash its answer; I hashed it before reading the truth.
- **Multi-agent.** The ledger records `predictions_frozen` (seq 205, 17:06:11) over A0017–A0019 and A0034, followed by `vault_access_granted` to R5 only (seq 214, 17:06:55). A0045 records the freeze hash `1fcf288a…`. The controller enforced and audited the blinding.

### 6. Traceability

- **Single agent.** It left `ez.py`, `ez2.py`, `ez3.py` and `ez3_log.txt`, and `ez3.py` reruns end to end. It recorded no input or output hashes. Its simulations are deterministic, but it did not record a seed policy or environment.
- **Multi-agent.** It has per-artifact manifests and SHA256SUMS, a `pip_freeze`, and seeds `1000+i`. Every step is in a 306-event ledger. R5 reproduced A0038 bit for bit (A0041).

### 7. Treatment recommendation

- **Single agent.**
  - **Setup.** A 2D Epileptor network with x0 set by hand: −1.6 on its EZ, −2.0 on the spread zone, −2.5 elsewhere.
  - **Results.** Resecting the top 3 regions, or stimulating them at −2.0, gave 0 seizing regions. It therefore recommends stimulating columns 9, 12 and 93.
  - **Problems.** The simulation is circular, because the outcome follows from the hand-set x0. The targets exclude the true region. And against the truth, P2's true model does not seize spontaneously (A0043), so its baseline of 5 seizing regions is not the patient's behaviour.
  - **Credit.** It did give caveats: a narrow dose margin, a crude stimulation model, and possible leakage for column 93.
- **Multi-agent.**
  - **Setup.** Paired simulations on fitted-model samples (A0038), reproduced by R5 (A0041).
  - **Results.** Ablating EZ plus PZ gave a median of −3.0 seizing regions; the 50 Hz pulse train gave no benefit.
  - **Conclusion.** After the reveal, it found that the true model does not seize spontaneously, that rank concordance is undefined, and that all 9 predicted reductions had the wrong sign (A0043). It made no recommendation, and that is the right call.
- **Overall.** Neither system produced a treatment choice that holds up. Only the multi-agent knew it hadn't.

### 8. Effort

- **Wall clock:** 2 min 11 s vs about 4 h 11 min, roughly 115 times longer for the multi-agent.
- **Resources:** the multi-agent also used a GCP VM for MCMC and many agent sessions.
- **Fairness note:** much of the multi-agent's time went into benchmarks that failed, and into the repairs and reviews that caught defects. That time pays for criteria 3–6. It is not a cost of getting the localisation wrong.
- **The baseline stopped itself.** It used 2 of its 15 minutes. A longer budget might have let it run the Stan fit. In that case it would have used the same pipeline that has the four defects, without anyone checking it.

## Fairness caveats

- **One patient, one baseline run.** The localisation result (criterion 1) rests on a single region in a single patient. A second baseline run could rank it differently.
- **Unequal web access.** The baseline was denied the web, while the multi-agent's R1 used literature search.
- **Different budgets.** The budgets differ by about 100 times, as the brief intended.
- **Timing of the scorer's knowledge.** I wrote the criteria before I read the truth, but I already knew the truth's column and name from the task brief when I wrote them. The criteria do not mention it, and the thresholds were not tuned to it.
- **The study is still active.** Review tasks T0027 and later were still running at 17:22 UTC. I scored the dossier A0045/A0046 and the later checks available at that time.

## Bottom line

The multi-agent system scored 18/21 and the single agent 6/21. The difference comes almost entirely from process, not from the answer:
- The multi-agent found all four known pipeline defects and the stimulation-induced seizure.
- It tested its models on synthetic data and rejected them when they failed.
- It kept the truth sealed until its predictions were frozen.
- It made every simulation reproducible.
- It reported a negative result honestly instead of recommending a treatment.

The single agent did better in two places:
- **Localisation.** The true onset region was ranked 4th, inside its stated spread zone. The multi-agent's frozen estimates ranked it 46th to 159th.
- **Speed.** It finished in about 2 minutes instead of about 4 hours.

The single agent's recommendation is not supported by its evidence. Its simulations were circular, its targets missed the true region, and it found none of the defects. A reader would get no warning from the system itself; only the true answer exposes those problems.

The fair claim for the hackathon: in this test, the multi-agent design does not find the onset zone better. What it adds is **knowing when its answer can't be trusted**, with an auditable record of why. A cheap source-imaging baseline gave a better localisation on this one patient. It should be added to the multi-agent pipeline as a benchmarked comparator.
