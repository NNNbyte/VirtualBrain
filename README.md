# VirtualBrain: a controller-governed multi-agent research system for epilepsy treatment choice

VirtualBrain helps decide between surgery and neurostimulation in drug-resistant focal epilepsy. Specialised AI agents survey the evidence, curate patient cases and build virtual-brain models. They design and simulate treatments, and evaluate one another's work.

A deterministic controller governs every step. It admits each task against a frozen role profile and records every artifact in an append-only ledger. Each artifact is gated by a role other than its producer, and outcome labels stay sealed in a vault until predictions are frozen. The design follows the ScienceClaw framework in `framework/`.

> Research evidence on literature and virtual patients only. Nothing in this repository is a clinical recommendation.

## What is here

| Path | Contents |
|---|---|
| `system/controller.py`, `system/schemas.py` | Deterministic study controller (CLI): tasks, artifacts, gates, needs, repairs, vault, frozen releases |
| `system/profiles/` | Role profiles: permitted outputs, scope rules, budgets |
| `system/ui/` | Live dashboard (agents board, timeline, needs and gates, artifacts, skill/profile editor with history) — `python system/ui/server.py`, then http://127.0.0.1:8765 |
| `system/reports/` | Report generators (`study_report.py`, `study2_report.py`, `r4_report.py`) and the offline WebGL brain viewer `brain3d.py` |
| `system/tests/` | Controller invariant tests — `python -m unittest discover -s system/tests -v` |
| `.claude/agents/`, `.claude/skills/` | Role agents (R1 evidence, R2 curation, R3 virtual patient, R4 intervention design, R5 independent evaluation, RV review, R6 improvement) and their skills; `run-study` is the lead orchestrator |
| `.tools/` | CmdStan toolchain shim (`stan_env.py`) and GCP job wrapper (`gcp/gcp_run.py`, `gcp/vm_setup.sh`; set `GCP_PROJECT`, `GCP_ZONE`, `GCP_VM`) |
| `studies/study-001/`, `studies/study-002/` | Ledgers, frozen releases and committed artifacts of the two studies (vaults, raw data and work folders excluded) |
| `reports/` | Finished HTML reports: `study-001-summary.html`, `study-002-summary.html` (3D virtual patient, before/after simulations, truth check), `study-002-R4-simulations.html` |
| `presentation/` | Hackathon slides (`pitch.html`, `slides.html`), demo walkthrough (`demo/index.html`) and judging-criteria map |
| `comparison/` | Single-agent baseline vs multi-agent comparison (`comparison.md`, `comparison.html`) |
| `framework/` | The ScienceClaw implementation plan this system is built from |
| `data/*-manifest.csv` | sha256 manifests of the external data used (the data themselves are not included) |

## The two studies

### Study-001: real patients, literature and public data
- **Literature dossier.** 30 evidence claims comparing resection, laser ablation (LITT) and neurostimulation (RNS, ANT-DBS, VNS), each source-checked by an independent agent.
- **Case curation.** 10 patients curated from OpenNeuro ds004100, with every file re-hashed by the independent evaluator.
- **Modeling.** The virtual-brain inversion pipeline did not pass its qualification benchmark, so no patient model was used.

### Study-002: virtual patients from Wang et al. 2025
- **Data.** Wang et al. 2025 virtual-brain-twin data, with ground truth sealed in the vault.
- **Modeling.** Two inversion models were benchmarked on synthetic data and failed qualification.
- **Treatment simulations.** Exploratory simulations of resection/ablation and SEEG stimulation on the virtual patient used the paper's TVB model.
- **Truth check.** After the predictions were frozen, the check showed that the onset-zone estimate missed the true region. The treatment ranking could not be verified.
- **Review.** An independent clinical-engineering review accepted the dossier after two repair cycles.

Both studies report negative results honestly, because the controller's benchmarks and independent checks caught the failures before any claim was made.

## Reproduce

1. **Python environments.**
   - Python 3.11, plus mne, mne-bids and nibabel for case curation.
   - A modeling environment with tvb-library 2.10.0, cmdstanpy 1.3.0, numpy, scipy, nilearn and `vep-stim @ git+https://github.com/HuifangWang/VBT_INS_Stimulation@5367ef4`.
   - CmdStan 2.40 from conda-forge, set up through `.tools/stan_env.py`.
2. **External data, not included.** Fetch it yourself, then check it against the manifests in `data/`.
   - OpenNeuro ds004100 v1.1.3 (CC0).
   - Wang et al. 2025 repository files at commit 5367ef4 (Apache-2.0).
   - Code Ocean capsule 10.24433/CO.2143670.v1 (Patient 2 anatomy; data licence CC BY-NC).
3. **Run a study.** Start one with the `run-study` skill in Claude Code. Watch it on the dashboard and rebuild reports with the generators in `system/reports/`.

## Data, attribution and licences
- **Wang 2025 data.** Wang, H. E. et al. *Virtual brain twins for stimulation in epilepsy.* Nat. Comput. Sci. (2025), doi:10.1038/s43588-025-00841-6. The code and simulated data are on GitHub under Apache-2.0. The Patient 2 anatomy shown in `reports/study-002-summary.html` and the slides comes from Code Ocean capsule 10.24433/CO.2143670.v1, licensed CC BY-NC: attribution required, non-commercial use only.
- **OpenNeuro data.** ds004100 (HUP iEEG, CC0) and the other OpenNeuro datasets are referenced only by record. Study artifacts contain metadata and checksums, not recordings.
- **Excluded.** Sealed outcome vaults, raw recordings and agent work folders are not part of this repository.
- **Licence.** The code and documentation written for this project are released under the MIT License (see `LICENSE`). Third-party data and material keep their own licences as listed above; in particular, the Patient 2 anatomy embedded in `reports/study-002-summary.html` and the slides remains CC BY-NC (non-commercial use with attribution) and is not covered by the MIT License.
