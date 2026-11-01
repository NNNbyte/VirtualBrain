---
name: r2-case-curation
description: R2 Case curation for the epilepsy research system. Verifies retrieved data (checksums, formats), signal quality, electrode/anatomy registration and missingness; produces PatientCase, QCReport, DerivativeManifest and CohortSplit artifacts while keeping outcome labels out of modeling access.
disable-model-invocation: true
---

# R2 · Case curation

First read `../run-study/references/agent-protocol.md`.

## Mission
Turn a verified dataset into **coherent, traceable patient cases** with honest quality reports. Raw data
is preserved. Outcomes stay out of modeling's reach.

## Inputs
A passed DatasetCard, a retrieval manifest (or user-approved download parameters), subject linkage, and
inclusion criteria from the protocol.

## Procedure
1. Check `parameters.user_approved_download`. If it is false and data is not already local, open a need
   (dataset, size, license) and finish `abstained`.
2. Retrieve into `work_dir/raw/` (never modify raw files). Record sha256 for every file.
3. Write small Python worker scripts in `work_dir/` for format checks (BIDS/EDF/BrainVision/MAT), units,
   sampling rate, channel lists, montage, events/annotations, and coordinates (frame, units, transform
   chain). Use `mne`/`mne-bids`/`nibabel` if installed. Check with `pip show` and record versions. If a
   library is missing, request installation in a need rather than silently degrading.
4. Signal QC: flat or noisy channels, line noise, discontinuities, annotation coherence, and seizure-onset
   markings. Anatomy QC: contacts inside the brain, transform consistency, and atlas labels.
5. Commit per case:
   - **PatientCase** with pseudonymous `case_id`. Use the `--case` flag and context `sample_rate_hz`,
     `time_window`, `signal_units`, `reference_montage`, `coordinate_frame`, `coordinate_units`, and
     `transform_chain_id`.
   - **QCReport** with `verdict`: `accept`, `accept_with_limits`, or `exclude` with reasons.
   - **DerivativeManifest** for any derived files (filtered, epoched, or connectivity).
6. **Outcomes:** put post-intervention outcome labels (Engel/ILAE, % reduction, follow-up) into
   `work_dir/outcomes_to_seal.json` **only**. Do not include them in any committed artifact. Tell the lead
   the path so it can be sealed in the vault. Linkage metadata (which intervention was delivered) may be
   recorded separately if the protocol allows.
7. **CohortSplit** (when tasked): development and test ids at patient level, cohort families and sites,
   seizure or time partitions, label-access policy, and `split_hash` = sha256 of the sorted id lists.
   Make patient overlap with other datasets explicit.

## Acceptance
Patient ids, recordings, units, coordinates, transforms, channels, and annotations are coherent and
traceable to checksummed raw files. Exclusions have reasons.

## Boundaries
Preserve raw data. No outcome labels in modeling-accessible artifacts. Scope linkage metadata
separately. No bulk downloads without recorded user approval.
