# Study-001 dossier: surgery vs neurostimulation for drug-resistant focal epilepsy

**Status:** draft pending clinical-engineering review (RV). Research evidence only, not a clinical recommendation for any patient.
**Release:** `rel-823fa0c912cb` · **Protocol:** v1 (A0001) · **Built by:** LEAD task T0035 (repair cycle 1, after RV review A0101) from committed, gated records only. Supersedes A0099 and A0100.

Evidence kinds are kept apart throughout: **[lit]** = literature_reported (abstract-level), **[obs]** = observed_measurement in public data, **[sim]** = simulated_result on virtual or synthetic patients.

## 1. Answer to the study question

| Arm of the protocol question | Status | Basis |
|---|---|---|
| (a) Literature evidence on clinical outcomes | **Supported, with limits** | A0031, A0063 (passed), source checks A0061 and R5 gates on A0017–A0030 |
| (b) Patient-specific virtual-brain simulations | **Not done: pipeline not qualified** | A0098 (passed): vep-stim failed both benchmarks (A0095, A0097 failed) |
| Validation against held-out historical outcomes | **Not run** | No frozen predictions; vault items V008/V009 were never opened |

**What the evidence supports [lit]:**
- When a resectable focus is present, especially mesial temporal lobe epilepsy (MTLE), open temporal resection has the strongest evidence for seizure freedom. It is the only intervention with randomised evidence against continued medical therapy.
- Laser interstitial thermal therapy (LITT) gives somewhat lower seizure freedom with fewer complications. That gap is not significant after propensity matching in one pooled analysis, and no RCT exists.
- Neurostimulation (RNS, ANT-DBS, VNS) is palliative. It reduces median seizure frequency by roughly 40–75% in the trial families (up to 82% in the RNS post-approval cohort), depending on modality and follow-up, but seizure freedom is uncommon.
- No study reports clinical outcomes after model-guided therapeutic stimulation.

## 2. Supported comparisons [lit]

**Open resection (A0063)**
- Temporal resection vs medical therapy (2 RCT families, n = 118): 58% (A0017) to 73% (A0018) free of disabling seizures at 1–2 years, vs 8% and 0/23 on medication.
- Paediatric mixed-procedure RCT, kept separate per protocol: 77% vs 7% at 12 months (A0019).
- Long-term temporal resection: 66% (A0020) to 72.5% (A0027) seizure-free.
- All-procedure adult survival-based continuous seizure freedom: 52% at 5 years and 47% at 10 years (A0021).
- Extratemporal resection does worse: 46% occipital/parietal and 27% frontal (A0020); recurrence HR 2.0 vs anterior temporal resection (A0021).

**LITT in MTLE (A0063)**
- 53.4% (A0023) to 58.0% (A0022) Engel I at 12–24 months, from 3 primary-cohort families. One of them, SLATE (55.9%, A0024), is a Medtronic-funded conference abstract.
- No RCT.

**Neurostimulation (A0031), median % seizure reduction at ≥12 months**

| Modality | Reduction | Seizure freedom |
|---|---|---|
| RNS | 44–53% at 1–2 y in the pivotal family, 75% at 9 y; 67–82% in independent real-world and post-approval cohorts | 18–22% (≥12-month freedom) |
| ANT-DBS | 41–56% at 1–2 y, 69–75% at 5–7 y; registry responder rate 41% (intention-to-treat) | 16% (≥6-month freedom) |
| VNS | ~45% median at 12 months; ~50–63% responders in pooled/registry data | ~8% |

The VNS pooled and registry data include mixed epilepsy types.

**Model-guided stimulation**
- No clinical seizure-outcome study was found (A0016, A0031; need N001).
- Wang 2025 is a diagnostic EZ-network estimation framework, applied to 2 patients plus synthetic data (A0055); the authors note its computational cost and parameter sensitivity (A0056).
- The earlier retrospective VEP study reported precision 0.6 in 53 patients (A0057).

## 3. Tradeoffs [lit]
- **Resection vs LITT:**
  - LITT had fewer complications in all three comparative analyses (A0027, A0028, A0029).
  - Open resection had higher seizure freedom unmatched: 67.1% vs 52.5%, RR 0.78 (A0028); 72.5% vs 57.1% (A0027).
- **Resection risks:** memory decline in 36% after surgery in ERSET (A0018). Paediatric RCT serious adverse events 33%, hemiparesis 26% (A0019).
- **Neurostimulation:** gains grow over years of open-label follow-up but are confounded by attrition, ASM changes and programming changes. Only the short blinded phases were randomised (A0031).

## 4. Unstable or indeterminate rankings
- **LITT vs open resection:** significant in the unmatched comparisons (A0027, A0028), but not significant after propensity matching (RR 0.85, p = 0.30) or within TLE (A0028), and not significant for nontumoral epilepsy (p = 0.07, A0029). All three analyses share one study family.
- **Between neurostimulation modalities:** there is no head-to-head RCT, so any ordering of RNS, ANT-DBS and VNS is indirect (A0031).
- **Neurostimulation vs resection:** the endpoints differ (seizure reduction vs seizure freedom) and the populations differ (often non-resectable). The literature does not support a direct ranking.
- **Virtual-patient ranking of candidate interventions:** indeterminate. No qualified model existed, so no simulations were run.

## 5. Dataset landscape (rebuilt ranking, from passed DatasetCards)
The purpose was public iEEG plus electrode localisation plus intervention linkage plus a post-intervention outcome class. The cards below report outcome field names only.

**Outcome-label exposure (disclosure).** During discovery, R1 read participants files before they were sealed (now vault items V001–V007). Some outcome-derived aggregates are therefore on record:
- ds004100: S 36 / F 22, by therapy RESECTION S22 F7 and ABLATION S14 F15. These are in the superseded A0033 and A0058 and were visible to LEAD.
- 277 participants with a known outcome (A0040).
- 5 with no resection (A0035).
- A 10–46 month follow-up range (A0038).

No per-patient labels are on record outside the vault. The ds004100 split (A0071) was drawn by seed 20261101, and the cases were selected without outcomes by R2 (A0072), which consumed the corrected card A0070 rather than A0033. Even so, aggregate exposure is a leakage-risk path for any future outcome evaluation on this split (see §9).

| Rank | Dataset | Verified subjects | Localisation / intervention | Outcome field | Access | Card |
|---|---|---|---|---|---|---|
| 1 | OpenNeuro ds004100 v1.1.3 (HUP) | 57 | Contact coordinates (mm, MNI template; ICBM152 vs fsaverage to_verify); `resect`/`soz` tags in 57/57 | Engel 1–4 and S/F/NR (sealed) | CC0, 14.2 GB | A0070 |
| 2 | Omni-iEEG (Hugging Face) | 328 rows | Channel-level resection 0/1 | Binary Engel 1 vs 2+ only | Data licence not reported (to_verify), 159 GB | A0040 |
| 3 | OpenNeuro ds003498 (Zurich HFO) | 20 | Resection-zone contacts in clinical sheet | ILAE 1–6 | CC0, 48 GB | A0038 |
| 4 | OpenNeuro ds003029 (Fragility) | 35 | No coordinates; surgery type + free-text EZ region | Engel/ILAE, S/F/NR | CC0, 11.1 GB (one centre requires a DUA) | A0035 |
| 5 | OpenNeuro ds003876 v1.0.2 | 39 (10 RNS-treated) | No stimulation settings | Outcome "after surgery" (sealed) | CC0, 5.5 GB | A0065 |
| 6 | Kini 2019 virtual-resection cohort | 28 reported | Resected electrodes reported, not verified | Engel/ILAE reported | IEEG.org, access to_verify | A0034 |
| — | Wang 2025 dataSim | 2 (simulated) | SC + gain | None (simulated only) | Apache-2.0 repo | A0067 |

Omni-iEEG repackages HUP (58), Zurich (20), Multicenter (ds003029) and source-sink (ds003876) recordings. It therefore overlaps ranks 1, 3, 4 and 5 and is not independent of any of them (A0040). No public dataset links verified stimulation settings to outcomes (need N006).

## 6. Case curation [obs]
- **Cohort split:** ds004100 split by patient into 34 development and 22 test cases (A0071, split_hash `255216f5…`). HUP132 was excluded (no recordings) and HUP165 (no annotated seizure).
- **Cases chosen:** 10 cases selected without looking at outcomes (A0072). 6 are development (HUP105, HUP123, HUP126, HUP141, HUP151, HUP173) and 4 are test (HUP070, HUP114, HUP157, HUP166).
- **QC results:** all 20 PatientCase and QCReport records passed R5's independent re-check of all 254 files (A0094). Every QC report is accept_with_limits.
- **Limits R5 found:**
  - 21 of the 61 runs (41 ictal + 20 interictal) end with a constant EDF pad. All 21 are ictal, so this is 21 of 41 ictal runs, and the last 1 s of each ictal run should be dropped.
  - Contacts share identical coordinates in HUP126 and HUP114.
  - The coordinate template's identity is to_verify.

## 7. Virtual-patient modeling [sim]: not qualified
- **Method chosen:** vep-stim, Wang 2025 at commit 5367ef4, region-level Stan inversion (A0037, A0059). TVB Epileptor (A0039) and BVEP (A0041) were recorded as alternatives.
- **Reproduction benchmark, Wang simulated Patient 1 (A0079 passed, A0095 failed):**
  - No convergence: all 162 x0 have R-hat > 1.05 (max 4.24), and 592 of 600 draws hit the maximum tree depth.
  - The documented EZ, Left-O2, ranked 113th pooled and 4th in the best mode, with ~15 false positives.
  - Correcting the sampling rate and the likelihood bug did not change this.
- **Synthetic recovery benchmark, planted Right-Amygdala EZ on Patient 2's connectome (A0096 passed, A0097 failed):**
  - With the matching connectome: x0 R-hat max 1.96; the EZ is top in only 29% of draws; 3 false positives; the sub-threshold propagation zone was estimated as EZ-like.
  - With Patient 1's connectome as a template: the EZ ranked 1st in all chains, but there was still no convergence.
- **R5 verdict (A0098):** the pipeline is not qualified for template-connectome fitting of HUP patients. The causes are mainly at the pipeline level:
  - amplitude vs EZ-extent non-identifiability;
  - offset and amplitude priors that conflict with realistic feature levels;
  - an iid observation model fitted to autocorrelated (AR(1)) noise, which accounts for ~1470 of the ~2700 log-posterior units by which the planted truth sits below every chain (the offset and amplitude priors account for ~1200);
  - a multimodal posterior.

  Short runs and saturated tree depth add to it.
- **Package defects found** (patched only in a work-dir copy):
  - The likelihood loop skips the first SEEG channels instead of the first time points.
  - Feature filters hard-code 250 Hz, but the files are 100 Hz (P1) and 125 Hz (P2).
  - Noise padding creates step artefacts.
  - Zero-padding at the window end distorts the last samples (fixed by reflect padding).
- **Consequence:** P3 patient modeling, P4 intervention design and P5 simulation comparison and outcome evaluation were not run (need N014). Predictions were never frozen, and the sealed outcome items were never revealed.

## 8. Missing evidence (open needs)
- **N001:** clinical outcomes after model-guided therapeutic stimulation.
- **N002 / N003:** full-text checks of late-timepoint denominators (RNS/DBS) and of LITT meta-analysis follow-up.
- **N004 / N011 / N013:** Wang 2025 Code Ocean capsule contents, reference fits and the Patient 1 generating configuration.
- **N006:** no dataset links stimulation settings to outcomes.
- **N010:** ds003876 sealed clinical files for the RNS subgroup.
- **N014:** a qualified inversion pipeline plus an MNI template connectome.
- **N008** is administratively open: its replacement, A0070, was accepted through N012.
- **N015 / N016:** repair needs for this dossier revision (A0099, A0100). They close when RV passes the superseding records.

## 9. Limitations
- All literature evidence is abstract-level; no full texts were read. Late-timepoint denominators and responder definitions are unverified.
- The VNS pooled and registry evidence includes generalised epilepsy, which does not match the protocol population.
- Cross-modality comparisons are indirect.
- No virtual-patient evidence was produced. The benchmarks used one planted EZ and one seed, and the synthetic test bypassed the feature pipeline.
- Only 10 of 56 eligible ds004100 cases were curated (budget). The coordinate template identity is unresolved.
- **Outcome exposure:** dataset-level outcome aggregates (§5) were seen by discovery roles and LEAD before sealing. Any future outcome evaluation on the ds004100 split should treat model or design choices made after that exposure as potentially informed by those aggregates. The cleanest fix is to fix all model choices in a protocol amendment before fitting and to report this exposure.
- Two controller design gaps were recorded for the next release:
  - A summary report cannot cite artifacts committed in its own task.
  - `repair issue` marks consuming ValidationReports stale too eagerly.

## 10. Reproducibility
- **Software:**
  - Release `rel-823fa0c912cb` (frozen skills, profiles, controller).
  - Python 3.11 with mne 1.13.2 and mne-bids 0.20.0.
  - `.venv-model` with tvb-library 2.10.0, cmdstanpy 1.3.0 and vep-stim 0.1.0a1 @ 5367ef4.
  - CmdStan 2.40 (conda-forge).
- **Environment digests:**
  - Main environment: `09f20829…` (R2 case curation, R1 corrected cards) and `3b6061dd…` (A0070, HUP157 onward).
  - Earlier R1 literature environment: `bf039753…`.
  - Model environment: `a3a5df5e…` (A0079–A0098).
- **Data:** ds004100 v1.1.3 retrieval manifest sha256 `62e8da45…`; cohort split_hash `255216f5…`.
- **Seeds:**
  - 20261101: cohort split and case selection (A0071, A0072).
  - 20261101: also the VBT-P1 feature noise in T0026 (L-BFGS starts 1000–1019, NUTS 12345).
  - 20261129: planted truth for the synthetic benchmark (A0096/A0097).
- **Records:** the DecisionBundle's `reproducibility_manifest` lists every artifact this report cites, with its schema, gate status, manifest hash and environment digest. That includes the EvidenceClaims A0017–A0030, the 20 PatientCase/QCReport records A0073–A0093, and the failed ModelBundles A0095 and A0097.
