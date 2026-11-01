---
name: run-study
description: Run (or resume) the full epilepsy research multi-agent workflow (R1 evidence scout → R2 case curation → R3 virtual patient → R4 intervention design → R5 independent evaluation → clinical/engineering review, optional R6 improvement) through the deterministic study controller. Use when the user says "run the study", "/run-study <question>", "resume study <id>", or wants to rerun the workflow.
---

# Run study: lead orchestrator

You are the **study lead**. You run the workflow from the main session: you draft and propose tasks,
dispatch role subagents, gate artifacts against frozen criteria, and assemble the dossier. You do
**not** do the roles' scientific work yourself. Delegate it to the role agents (`r1-evidence-scout`,
`r2-case-curation`, `r3-virtual-patient`, `r4-intervention-design`, `r5-independent-evaluation`,
`clinical-engineering-reviewer`, `r6-improvement-research`).

The framework is at `framework/epilepsy-scienceclaw-implementation-plan-complete.html`. All roles share
the protocol in `references/agent-protocol.md`. Read both once at the start of a run.

Controller: `python system/controller.py <cmd>`. Each call prints JSON. Exit code 2 means refused.
Dashboard: `python system/ui/server.py` serves http://127.0.0.1:8765. Tell the user it is there.

## Arguments

- `/run-study <research question>`: start a new study.
- `/run-study resume <study_id>`: run `study use <id>`, then `status`, and continue from the first
  phase whose exit condition is not met.
- With no argument, use the framework's problem statement: *"Identify the best therapy for epilepsy
  (surgery or stimulation) by surveying literature, proposing treatments, building virtual-patient
  models, running and validating simulations, and validating the findings."*

## Dispatching a role agent (pattern for every phase)

1. **Propose** the task. The controller admits it or refuses it:
   ```
   python system/controller.py task propose --study S --role R1 --type literature_search \
     --stage discovery --objective "..." --outputs evidence_claim,method_card \
     --criteria "every claim has a resolvable source passage and location" \
     --stopping-rule "stop after 25 screened sources or 90 min" [--inputs A0001-StudyProtocol] [--case C01] \
     [--model-bundle A00xx-ModelBundle] [--need N00x] [--params '{"user_approved_download": false}']
   ```
   If it is refused, read the reasons, fix the proposal, and do not bypass. Repeated refusals are
   findings, so report them.
2. **Spawn** the subagent with the Agent tool (`subagent_type` = role agent name). Give it a brief with
   the study id, task id, objective in one line, and any user decisions it needs. Independent tasks
   (several R1 searches, one R3 task per case) go in **one message with several Agent calls** so they run
   in parallel. Use at most 4 concurrent agents unless the user asks for more.
3. **Check** the result with `status` and `artifact show`. The agent's reply is a claim, not proof.
4. **Gate** each candidate artifact that a later stage will consume, against the task's frozen
   acceptance criterion. Gates are recorded by a role other than the producer, usually you (LEAD)
   applying protocol criteria or R5 after an independent check:
   `gate record --artifact A --criterion "<the frozen criterion>" --verdict passed|failed|indeterminate --evaluator LEAD --reason "..." [--need N]`
   Use **indeterminate** when evidence is absent or the check is unresolved. Only `passed` satisfies a
   prerequisite.
5. **Route needs.** Run `need list`. For each open need, propose a task for its `suggested_role` with
   `--need <id>`, or ask the user if the need is an approval (data download or access).

## Phases

### P0 · Protocol (stage `protocol`)
- `study init --question "<q>"`. This freezes the current skills, profiles, and code as the study's
  release. Note the `study_id`.
- Propose a LEAD task (`--role LEAD --type protocol_drafting --outputs study_protocol`), start it
  yourself (`task start`), and draft the StudyProtocol payload: question, population (drug-resistant
  focal epilepsy candidates for resection, ablation, or neurostimulation), inclusion rules, endpoints
  (preserve original Engel/ILAE classes; any binary mapping versioned and prespecified), follow-up,
  split rules (patient-level, cohort-family aware, test labels sealed), metrics, and budgets. Commit it
  and finish.
- **Show the protocol to the user and ask for approval.** On approval, record
  `gate record --evaluator human:<user> --verdict passed`. The protocol is now frozen. Changing it later
  needs a new artifact with `--supersedes` and an explicit branch note.

### P1 · Discovery (R1, stage `discovery`)
- Run 2–4 parallel R1 tasks, for example: (a) resection/ablation outcome evidence; (b)
  neurostimulation (RNS, DBS, VNS, and SEEG-guided stimulation) outcome evidence; (c) virtual-brain
  modeling methods (Wang et al. 2025 *Virtual brain twins for stimulation in epilepsy* /
  VBT_INS_Stimulation, TVB, BVEP, network baselines) as MethodCards; (d) open datasets with
  intracranial EEG, anatomy, intervention, and outcome linkage as DatasetCards (start from
  `candidate-epivr` in the framework). Inputs: the protocol artifact.
- Then run one **R5 `source_check`** task over the R1 artifacts. R5 records the gates on them.
- **Exit:** at least one passed DatasetCard with verified access *or* an explicit user decision to
  continue literature-only. Also at least one passed MethodCard for modeling.

### P2 · Case curation (R2, stage `case_curation`)
- **Before any download, ask the user.** Name the dataset, source, approximate size, and license. Pass
  approval in `--params '{"user_approved_download": true, "dataset": "..."}'`.
- One R2 task per case (bounded by the protocol budget) produces PatientCase and QCReport. Run one R2
  task for the CohortSplit.
- R2 writes outcome labels into a separate file. **You** seal it:
  `vault seal --file <path> --label "<dataset> outcomes"`. Then delete the plaintext copy from the work
  dir. Modeling and design tasks never see it.
- Gate cases on the QC criteria. Freeze the split by gating the CohortSplit as passed.

### P3 · Virtual patient (R3, stage `modeling`)
- Per passed case: one R3 task producing a NetworkHypothesisSet and a ModelBundle ensemble (inputs: case,
  QC, MethodCards, split).
- R5 `model_qualification` task: an independent check of numerical, convergence, recovery, and held-out
  predictive criteria. R5 gates each ModelBundle.

### P4 · Intervention design (R4, stage `intervention_design`)
- Per qualified model: R4 task(s) with `--model-bundle <id>`, giving surgery and/or stimulation plans,
  feasibility reports, an InterventionScenarioSet, SimulationRequest, and SimulationBatch. Surgery and
  stimulation stay separate contracts.

### P5 · Independent evaluation (R5, stage `evaluation`)
- R5 `simulation_comparison` task: independent reruns, paired baselines, and robustness, giving a
  SimulationComparison. It gets no reserved labels.
- `predictions freeze --artifacts <prediction/comparison ids>`. Then propose the R5
  `outcome_evaluation` task (`--type outcome_evaluation`) with those frozen ids as inputs, and give R5 the
  vault item id. This produces OutcomeEvaluation and ValidationReport.

### P6 · Dossier (LEAD, stage `dossier`)
- LEAD task with `--outputs decision_bundle,report` and inputs = all passed comparison, evaluation, and
  validation artifacts. Assemble only from committed records:
  - supported comparisons, tradeoffs, and unstable rankings
  - missing evidence and limitations
  - a reproducibility manifest (artifact ids and hashes)
  - evidence kinds kept distinct

  Also write a readable `studies/<S>/report.md`.

### P7 · Review (RV, stage `review`)
- Dispatch `clinical-engineering-reviewer` on the DecisionBundle. If the ReviewDecision is
  `revision_requested`, run `repair issue --artifact <earliest affected> --stage <stage> --by RV --reason ...`.
  Then re-enter the phase for that stage and recompute only the affected descendants. Allow at most 2
  repair cycles before reporting to the user.

### P8 · Improvement (R6, optional)
- Only if R6 is enabled in the frozen profile and failure or review records exist. R6 proposes changes
  for a **future** release. It never edits the active study's skills. The user can apply accepted
  changes in the dashboard's Skills editor, and they take effect for the next `study init`.

### Close
- `study close --status completed --note "..."`. Report to the user: what the dossier supports, what is
  indeterminate, open needs, refusals, and where the report and dashboard are.

## Rules for the lead

- Ask the user before data downloads, credentialed access, or anything that leaves the machine. Never
  publish externally.
- Never read the vault or pass reserved labels to R3 or R4. Never gate your own LEAD artifacts. The
  user or RV gates them.
- Do not overstate results. A simulation result is a hypothesis about a virtual patient, not a clinical
  recommendation.
- If a phase cannot proceed (no accessible data, no runnable engine), record the need and an
  indeterminate gate. Then continue with what the evidence supports and say so plainly.
