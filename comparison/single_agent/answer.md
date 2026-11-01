# Patient 2 (Wang et al. 2025 virtual brain twin): EZ estimate and treatment recommendation

**Scope note.** I had a 15-minute limit, so this is a fast analysis. I did **not** run the full Bayesian (Stan/BVEP) fit. The EZ comes from a source-imaging inversion of SEEG ictal activity. The simulations use the 2D Epileptor network equations from `vep_stim/stan/vep_mcmc.stan`, with the excitability values (x0) **assigned by hand** from the EZ ranking, not inferred. Treat this as a first pass. These are virtual-patient results, not clinical advice.

## Data and method
- Input: `dataSim/Patient2/P2_SEEG_ts_fit.npz`, with SEEG (191 bipolar channels x 1500 samples at 8 ms), gain (191x162), SC (162x162). Region names come from `VepMrtrixLut.txt`, where npz column i corresponds to LUT row i+1.
- Ictal window: samples 100-950 (about 0.8-7.6 s). Sample-to-sample activity is high there and nearly zero afterwards. The first ~50 samples are an initial transient and were excluded.
- Channel feature: total absolute variation over the ictal window, normalised. The most active channels were OR'10-11 (1.00), PM'1-2 (0.95), OR'11-12, PM'5-6/6-7/7-8, PM'4-5, PM'11-12, CR'2-3 and I'11-12.
- Region inversion: non-negative least squares of the channel feature onto the gain matrix, with a ridge penalty of 0.05. The fit correlation was r = 0.87. I checked it against a correlation ranking between normalised gain columns and channel activity. A plain unregularised inversion was unusable because the gain matrix is badly conditioned (cond about 5e6). Scripts: `ez.py` (failed attempt), `ez2.py`, and `ez3.py` (final). Log: `ez3_log.txt`.

## Estimated epileptogenic zone (ranked)
| Rank | npz col | Region | NNLS score | gain-corr |
|---|---|---|---|---|
| 1 | 9 | Left-Middle-frontal-sulcus | 1.00 | 0.70 |
| 2 | 12 | Left-F1-mesial-prefrontal | 0.97 | 0.65 |
| 3 | 93 | Right-F1-mesial-prefrontal | 0.86 | 0.60 |
| 4 | 15 | Left-F1-lateral-prefrontal | 0.55 | 0.82 |
| 5 | 10 | Left-SFS-rostral | 0.55 | 0.56 |
| 6 | 16 | Left-F1-lateral-premotor | 0.26 | 0.40 |
| 7 | 94 | Right-PreSMA | 0.17 | 0.46 |

My EZ estimate is ranks 1-3. Ranks 4-6 are the likely propagation zone. The network is a left-dominant dorsal and mesial prefrontal one. The right mesial prefrontal region (col 93) scores high, but this could be leakage across the midline, because the mesial frontal contacts see both hemispheres.

## Simulations (2D Epileptor network, K=1, 600 time units)
Setup: x0 = -1.6 for the EZ (cols 9, 12, 93), -2.0 for the propagation regions (cols 15, 10, 16), and -2.5 everywhere else. A region counts as seizing if x > 0.
| Scenario | Seizing regions |
|---|---|
| Baseline | 5 (cols 9, 10, 12, 15, 93) |
| Resect top-1 (col 9) | 4 |
| Resect top-3 (cols 9, 12, 93) | **0** |
| Resect top-6 | 0 |
| Stimulate top-3 with hyperpolarising current -0.5 or -1.0 | 5 (no effect) |
| Stimulate top-3 at -2.0 | **0** |
| Stimulate top-1 only at -2.0 | 4 |

## Recommendation
In silico, two options both remove seizures:
- resecting or ablating all three EZ regions
- strong inhibitory stimulation of all three EZ regions

Targeting only the top region does neither. I recommend **neurostimulation targeting the three EZ nodes** (multi-target or bilateral, e.g. TI or responsive stimulation) over resection, for two reasons:
1. The estimated EZ is **bilateral mesial prefrontal**, next to SMA and premotor cortex. Removing all three regions would mean bilateral mesial frontal surgery.
2. Stimulation reached the same simulated seizure freedom without removing tissue.

If the right mesial prefrontal node turns out to be leakage rather than a true source, the case for resection changes. Ablating the left-sided regions (cols 9 and 12, plus 15 and 10 if needed) would become a reasonable alternative. That should be checked by re-running the resection simulation without col 93.

Caveats:
- The stimulation effect needed a large amplitude, -2.0 in model units. Lower amplitudes failed, so the dose margin is narrow.
- Stimulation is modelled crudely as a constant current added to the x equation.

## Limitations
- The x0 values were not fitted. The simulation outcomes partly follow from how I set them, so they mainly test the network's response given my EZ hypothesis.
- No posterior or uncertainty is reported, and the Stan fit was skipped for time.
- I did not use `P2_TI_SEEG_ts_fit.npz` (the TI-stimulation recording) or the EEG files. The TI recording is the natural next check on how stimulation would work for this patient.
- I had no ground-truth EZ (none was among the allowed inputs), so I could not validate the ranking.
