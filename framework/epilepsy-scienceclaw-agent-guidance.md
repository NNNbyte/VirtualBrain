# Epilepsy research agent system build guidance

Implement a ScienceClaw based research agent system for epilepsy surgery and stimulation research. Use the architecture, role boundaries, and contracts below as the requirements for the system being built. MUST denotes a required behavior; SHOULD permits an alternative with a recorded reason.

This guide retains source sections 02, 04, and 05. It defines target interfaces rather than asserting that the proposed modules already exist. Inspect the target checkout before reusing an interface, map existing equivalents explicitly, and record the actual implementation commit. The supplied ScienceClaw integration reference is commit `894598cd3a90891a077c254566276bd379038bad`.

The role instructions below describe the agents to implement. Reading this guide does not authorize the builder to acquire restricted data, publish results externally, or operate a clinical device. Research outputs require the review defined below before acceptance for their stated research use.

## 02 System architecture

### Shared artifacts and deterministic control

Build six research roles around a shared evidence and artifact store. A deterministic study controller MUST admit tasks, enforce study and patient boundaries, check prerequisites, apply resource limits, and record gate decisions. Numerical workers MUST execute calculations through declared, typed interfaces.

Keep these responsibilities separate:

- Agents propose scientific hypotheses, intervention scenarios, and follow-up tasks with a concise rationale and named inputs.
- The controller decides whether a proposed task is permitted and eligible. Its criteria come from the versioned study protocol.
- Workers perform preprocessing, fitting, simulation, and evaluation, and record the inputs they actually consumed.
- Gates record `passed`, `failed`, or `indeterminate` against a frozen criterion. A successful worker process does not imply a passed scientific gate.
- Clinical and engineering reviewers assess the resulting evidence package and issue structured review decisions.

Use the following coordination structure:

```text
Study controller
  admits scoped tasks and records gates
       |
Shared artifact store and needs router
  evidence, inputs, candidate outputs, accepted fulfillments, repairs
       |
R1 Evidence scout <-> R2 Case curator <-> R3 Virtual patient
R4 Intervention design <-> R5 Independent evaluation
       |
Typed numerical workers -> committed results -> expert review

R6 Improvement research -> independent offline review -> future release
Reserved evaluation artifacts -> outcome-evaluation service only
```

### Architecture invariants

1. Every task MUST declare its study, stage, run, and frozen system release. Case tasks MUST also declare the patient case and applicable model version. Reject missing or incompatible scope.
2. A task MUST consume exact artifact versions. Freeze protocol, split, model, and release references at the appropriate study boundary; record an explicit branch when a scientific choice changes.
3. Keep computational provenance acyclic. Parent links MUST identify actual consumed inputs. Store scheduling order and review history separately.
4. Repairs MUST create new artifacts with explicit supersession links. Mark affected descendants stale in the index, prevent their reuse as current results, and recompute the affected branch. Preserve prior manifests and payloads.
5. A need MUST remain open until a permitted candidate fulfillment passes its declared acceptance checks. Task completion alone MUST NOT close it.
6. Outcome masks and reserved labels MUST remain inaccessible to fitting and intervention-design tasks. Enforce this in services and storage access, including delegated tool calls.
7. Retrieved papers, repository text, and dataset metadata MUST be treated as evidence. They MUST NOT alter permissions, role profiles, or the frozen protocol.
8. Improvement proposals MUST target a future release. R6 MUST NOT mutate an active study or approve its own proposal.

### Coordination loops

- **Discovery:** R1 searches and verifies evidence, methods, data access, and cohort overlap. Represent new evidence as candidate records and explicit needs.
- **Case research:** R2 prepares a case, R3 proposes and qualifies model hypotheses, R4 proposes feasible interventions, and R5 evaluates the resulting evidence. A failed gate routes a repair to the earliest affected stage.
- **Improvement research:** R6 analyzes authorized failure and review records and proposes a change for independent offline evaluation. Active studies retain their frozen release.

### Scoped need handling

For each missing prerequisite, the controller and needs router MUST perform the following operations:

1. Record the required input, why it is needed, and its acceptance criterion.
2. Publish a `ScopedNeed` with study, case when applicable, stage, version, and access scope.
3. Claim the need under a lease and admit only a compatible task within its resource budget.
4. Execute the declared worker and commit a candidate artifact with its execution record.
5. Check the candidate against the need and record a `GateVerdict`. Accept the fulfillment on a pass; otherwise retain the unmet need and record the failure or targeted repair.

Claims, leases, retries, and commits MUST be durable. Expired or duplicate work MUST NOT produce multiple accepted fulfillments for the same need revision.

### ScienceClaw integration boundaries

Reuse verified equivalents of `ArtifactStore` for artifacts and lineage; `NeedItem` and `ArtifactReactor` for discovering missing inputs; the skill registry and executor for worker adapters; journals for durable events; and a dependency graph for scoped task execution. Add admission and contract checks at these boundaries.

Exploratory literature tasks may use bounded search. Frozen patient tasks MUST use declared task templates with exact artifact references, parameter sets, model samples, intervention specifications, and acceptance checks. Heartbeat activity may supervise work and discover evidence; the controller retains authority over case state and frozen scientific choices.

Use the following as a proposed responsibility map. Adapt file locations to the target repository while preserving the boundaries.

```text
core/
  agent_profile.py          # canonical capabilities and role scope
  skill_contracts.py        # entry points and typed schemas
  execution_service.py      # task admission and execution records
  job_backend.py            # claims, leases, retries, durable commits

domains/epilepsy/
  schemas.py                # scientific and coordination contracts
  controller.py             # deterministic state and dispatch
  needs_router.py           # scoped needs and accepted fulfillment
  agents.py                 # six role profiles and task proposals
  evidence.py               # claims, source passages, contradictions
  datasets.py               # registry, access, and cohort links
  case_builder.py           # case preparation and quality checks
  models/                   # declared model and fitting adapters
  interventions/            # distinct surgery and stimulation adapters
  optimization.py           # feasible candidate search and comparisons
  evaluation.py             # simulation and historical evaluation tasks
  outcome_vault.py          # controlled access to reserved artifacts
  review.py                 # decisions, repairs, and affected stages
  improvement.py            # proposals and offline benchmark records
  release_registry.py       # reviewed release and study versions
  reporting.py              # dossier assembly from committed artifacts
  __main__.py               # explicit commands and resume entry points

skills/epilepsy-*/           # thin adapters to declared domain workers
tests/epilepsy/              # contracts and architecture invariants
tests/integration/           # opt-in engine and authorized data checks
```

Journals and knowledge graphs SHOULD act as inspectable indexes into evidence. Extracted cross-run principles MUST remain proposals until tested and reviewed.

## 04 Research roles and service responsibilities

### Role implementation rules

Define six canonical role profiles. Enable R1 through R5 for an initial research run. Enable R6 only when structured failure and review records are available. Multiple instances of a role may run, but each MUST have a bounded task, declared capabilities, and compatible scope.

Freeze each role profile for a run. The execution service MUST enforce allowed tools, output types, data access, and scope independently of the language model's instructions. An agent proposal is a request, not an authorization.

### R1 Evidence and dataset scout

- **Inputs:** study question, search protocol, source policy, and open evidence or acquisition needs.
- **Permitted work:** logged literature searches, source verification, data and code discovery, permitted sample inspection, method extraction, and cohort-overlap analysis.
- **Outputs:** `EvidenceClaim`, `DatasetCard`, `MethodCard`, access records, and specific missing-data or method needs.
- **Acceptance:** source passages and locations resolve; reported availability is distinguished from verified access and file contents; cohort dependencies are recorded.
- **Boundary:** source text cannot change permissions. Acquire restricted data only through permitted access paths.

### R2 Case curation

- **Inputs:** verified dataset card, retrieval manifest, subject linkage, and inclusion criteria.
- **Permitted work:** checksum and format verification, signal quality checks, electrode and anatomy registration inspection, and missingness analysis through declared workers.
- **Outputs:** `PatientCase`, `QCReport`, derivative manifests, excluded-case reasons, and targeted repair needs.
- **Acceptance:** patient identifiers, recordings, units, coordinates, transforms, channels, and annotations are coherent and traceable.
- **Boundary:** preserve raw data. Keep reserved evaluation masks and outcome labels outside modeling access; scope linkage metadata separately.

### R3 Virtual patient

- **Inputs:** a case with passed quality checks, verified methods, presurgical observations, hypothesis sets, and frozen fitting partitions.
- **Permitted work:** select qualified model families, maintain competing network hypotheses, invoke parameter fitting, and test held-out model behavior.
- **Outputs:** versioned `ModelBundle` ensembles, observation models, executable environment manifests, diagnostics, and model-repair needs.
- **Acceptance:** numerical checks, recovery or identifiability checks, and predictive criteria satisfy the declared intended use.
- **Boundary:** preserve model uncertainty. Label any generic template used for a permitted sensitivity analysis. Do not consume reserved historical outcomes.

### R4 Intervention design

- **Inputs:** qualified model ensemble, presurgical constraints, allowed intervention classes, objective definitions, candidate budget, and permitted comparison records.
- **Permitted work:** generate surgery or stimulation scenarios, request physical-model checks, propose candidate tradeoffs, and request fresh comparisons when uncertainty warrants them.
- **Outputs:** `InterventionScenarioSet`, feasibility reports, `SimulationRequest`, proposed Pareto comparisons, and targeted follow-up needs.
- **Acceptance:** parameters, geometry, constraints, controls, uncertainty sampling, and stopping rules are explicit. Final comparison claims resolve to independent evaluation records.
- **Boundary:** use separate surgery and stimulation worker contracts. A disease-model parameter change alone does not define a realizable intervention. Reserved outcomes remain inaccessible.

### R5 Independent evaluation

- **Inputs:** frozen protocol and versions, simulation and prediction records, review criteria, and evaluation artifacts authorized for the specific task.
- **Permitted work:** independent reruns, robustness checks, source checks, simulation comparison, and a distinct blinded historical-outcome evaluation task.
- **Outputs:** `SimulationComparison`, `OutcomeEvaluation`, `ValidationReport`, failure examples, abstentions, and structured revision needs.
- **Acceptance:** preserve split independence; calculate patient-level metrics and uncertainty as specified; attach each claim to the appropriate evidence kind.
- **Boundary:** do not rewrite the frozen model after seeing test outcomes. The outcome-evaluation service controls and logs reveal; simulation-comparison tasks do not receive reserved labels.

### R6 Improvement research

- **Inputs:** authorized development artifacts, structured failures, review feedback, resource traces, and released method versions.
- **Permitted work:** diagnose recurring failures and propose scoped changes to methods, tools, scheduling, prompts, or checks.
- **Outputs:** `ImprovementProposal` containing failure evidence, an exact change, parent version, anticipated benefit, offline test protocol, risks, acceptance criteria, and rollback.
- **Acceptance:** link the proposal to a `BenchmarkRun`, independent review, and a `ReleaseRecord` before adoption into a future release.
- **Boundary:** do not alter the active study, promote your own change, or treat an exposed test cohort as fresh independent evidence.

### Service responsibilities

| Component | Required responsibility | Decision or output |
| --- | --- | --- |
| Study controller | Own protocol references, access checks, dependency state, admission, budgets, leases, repairs, and freezes. | Admit permitted tasks and advance only on recorded gate verdicts. Apply scientific criteria from the protocol. |
| Artifact store and needs router | Store consumed inputs, candidate results, open needs, accepted fulfillments, contradictions, and staleness events. | Commit transactional records and route work by scope. Artifact counts and timestamps do not establish scientific validity. |
| Numerical worker pool | Execute declared preprocessing, inference, geometry, simulation, statistics, and reference calculations. | Produce `ExecutionRecord` and typed outputs, with execution and validation status recorded separately. |
| Outcome-evaluation service | Protect reserved masks and labels, verify prediction freeze, authorize staged reveal, and calculate locked outcome metrics. | Produce `OutcomeEvaluation` and access audits. Reject access from fitting and strategy tasks. |
| Dossier builder | Assemble evidence links, tables, figures, uncertainties, and limitations from committed records. | Produce a draft `DecisionBundle` and check consistency between claims and artifact references. |
| Clinical and engineering reviewers | Assess intended use, anatomy and functional assumptions, numerical validity, and completeness. | Issue `ReviewDecision`: accept the report, request a targeted revision, or identify an unsupported conclusion. Acceptance concerns the stated research use. |

### Canonical role profile

Implement an equivalent machine-readable profile and validate it at admission. These identifiers illustrate proposed interfaces; register actual worker IDs in the target implementation.

```yaml
profile_version: "2.0"
agent_id: "R4-intervention-design"
role: "intervention_design"
allowed_tools:
  - "epilepsy-surgery-candidates"
  - "epilepsy-stimulation-candidates"
  - "epilepsy-simulation-request"
  - "epilepsy-simulation-comparison"
allowed_output_types:
  - "intervention_scenario_set"
  - "feasibility_report"
  - "simulation_request"
  - "candidate_comparison_proposal"
  - "scoped_need"
permissions:
  read_reserved_outcomes: false
  publish_external: false
  control_device: false
scope_requirements:
  study_id: "required"
  case_id: "required_for_case_tasks"
  model_bundle_id: "required_for_intervention_tasks"
  system_release_id: "frozen_at_run_start"
```

Every task message MUST name the objective, exact input artifacts, permitted output schemas, scientific acceptance criteria, dependencies, resource estimate and limit, stage scope, and stopping rule. Request a new model or hypothesis branch explicitly; record its version and invalidate affected comparisons.

## 05 Scientific and task contracts

### Required record types

Implement typed, versioned schemas for the following records. Validate them before committing an artifact or admitting a consuming task. Use explicit unknown and missingness states where evidence is incomplete.

| Contract | Required content and meaning |
| --- | --- |
| `StudyProtocol` | Question, population, inclusion rules, endpoints and follow-up, analysis and split rules, metrics, budgets, version, and freeze history. Freeze the relevant rules before examining test outcomes. |
| `EvidenceClaim` | Claim, bibliographic record, supporting passage and location, population and design, endpoint, evidence kind, contradictions, and study-family identifier. Separate reported observations from inference. |
| `DatasetCard` | Repository or accession, reported and verified contents, subject linkage, modalities, intervention and outcome availability, license and access conditions, cohort overlap, and retrieval status. |
| `MethodCard` | Primary method source, required inputs, implementation and dependency versions, supported outputs, validation setting, limitations, and reproduction status. |
| `PatientCase` and `QCReport` | Pseudonymous IDs, session and recording references, checksums, anatomy, coordinate transforms, contacts and channels, montage, events, units, quality findings, missingness, and acceptance verdict. |
| `CohortSplit` | Development and test subject IDs, site and cohort families, seizure or time partitions, label-access policy, and immutable split hash. Make patient overlap and reuse explicit. |
| `NetworkHypothesisSet` | Alternative initiation and propagation hypotheses, source evidence, priors, unobserved-node assumptions, and planned discrimination checks. |
| `ModelBundle` | Model family and implementation versions, consumed case data and hypotheses, fitting partitions, observation model, parameters or posterior, numerical diagnostics, predictive checks, and intended use. |
| `SurgeryPlan` and `StimulationPlan` | Intervention class, geometry or contact and device configuration, physical mapping, constraints, feasibility verdict, and a model-independent intervention identifier. Keep the two contracts distinct. |
| `InterventionScenarioSet` and `SimulationRequest` | Candidate plan references, exact model samples and versions, objectives, controls, uncertainty sampling, requested worker operation, parameter sets, and stopping criteria. |
| `SimulationBatch` | Actual model samples, candidate IDs, seeds and initial states, solver settings, paired baselines, output references, numerical checks, and resource use. |
| `SimulationComparison` and `OutcomeEvaluation` | Separate task types with permitted inputs, freeze manifest, metrics, uncertainty, controls, and evidence level. Historical evaluation also records authorized staged label access. |
| `ValidationReport` | Frozen criterion and version, evaluator, exact evaluated artifacts and held-out data, result, interval and uncertainty method, failure cases, verdict, and evidence level. |
| `DecisionBundle` | Supported candidate comparisons, tradeoffs, unstable rankings, missing evidence, limitations, reproducibility manifest, review references, and release status. |
| `ScopedNeed` and `GateVerdict` | Requester, missing input, study and patient scope, stage and versions, acceptance criterion, claim and lease, candidate fulfillment, gate result, and repair reason. |
| `ReviewDecision` | Reviewer identity and role, decision, intended research use, affected artifact IDs, reason, repair stage, and acceptance checks for a revision. |
| `ImprovementProposal` and `BenchmarkRun` | Failure evidence, exact proposed change, parent version, permitted data, fixed test protocol, matched resource conditions, regression results, uncertainty, acceptance criteria, and rollback reference. |
| `ReleaseRecord` | Accepted proposals, implementation and environment hashes, independent review, permitted scope, migration notes, and rollback reference. |
| `ExecutionRecord` | Task and attempt IDs, admitted inputs, actual consumed inputs, resolved tool and environment versions, parameters, seeds, timestamps, resource use, execution status, errors, and committed output references. |

Feasibility reports, access records, derivative manifests, and candidate comparison proposals MUST also use a registered schema and the common artifact envelope when persisted or passed between roles.

### Common artifact envelope

All scientific artifacts MUST carry the following envelope. A question mark marks a field whose requirement depends on scope; enforce its applicability in the schema rather than filling it with invented values.

```text
ArtifactEnvelope
  artifact_id, schema_name, schema_version
  study_id, cohort_id?, case_id?, session_id?, run_id, task_id
  system_release_id, protocol_version, model_bundle_id?
  producer_role, tool_id, tool_version, code_commit, environment_digest
  consumed_artifact_ids[], input_manifest_hash
  payload_refs[]: {uri, media_type, sha256, byte_size}
  scientific_context:
    time_window?, sample_rate_hz?, signal_units?, reference_montage?
    coordinate_frame?, coordinate_units?, transform_chain_id?
    atlas_id?, atlas_version?, evidence_kind
  execution_status
  validation_status: unreviewed | passed | failed | indeterminate
  access_classification, permitted_destinations[]
  created_at, manifest_hash, supersedes_id?
```

Patient fields are mandatory for case artifacts. Signal artifacts MUST specify the applicable sampling rate, time window, units, and montage. Geometry artifacts MUST identify coordinate frame, units, and transform chain. Literature records may be study scoped without a patient. Reject artifacts with inconsistent scientific context or inaccessible payload references.

Record the validation state at commit and append later gate and staleness events without rewriting a committed manifest. The artifact index MUST resolve the current effective validation and staleness state from those records. Consuming tasks MUST check that effective state before use.

Define the manifest hashing procedure and schema version explicitly. Hashes MUST cover the declared immutable manifest content and referenced payload digests; exclude the manifest's own hash field from its hash input. Parent references MUST resolve to immutable artifact versions.

### Task admission contract

Implement a `TaskMessage` with these required fields:

```text
task_id, task_type, objective
requester_role, assigned_role, role_profile_version
scope: {study_id, case_id?, stage, run_id, system_release_id}
protocol_version, cohort_split_id?, model_bundle_id?
input_artifact_ids[], dependency_task_ids[]
permitted_output_schemas[]
worker_id, worker_contract_version, parameters
scientific_acceptance_criteria[]
resource_estimate, resource_limit, stopping_rule
access_classification, permitted_destinations[]
need_id?, need_revision?, lease_id?
```

Admission MUST verify the role's capability, input schema and version compatibility, scope, current gate status, split and release compatibility, access rights, budget, and dependency completion. Refuse an unauthorized proposal and record the reason. Persist task attempts and execution results separately from scientific acceptance.

Use `passed`, `failed`, and `indeterminate` consistently for gate verdicts. Treat absent evidence or an unresolved check as `indeterminate`; only a passed criterion satisfies the corresponding prerequisite.

### Consumed input lineage

Record the actual dependencies of each result. These examples describe artifact ancestry, not scheduling instructions:

```text
PatientCase + NetworkHypothesisSet + fitting partition -> ModelBundle
ModelBundle + SurgeryPlan or StimulationPlan + SimulationRequest
  -> SimulationBatch
SimulationBatch + frozen comparison criteria + permitted validation inputs
  -> SimulationComparison
Frozen predictions + locked CohortSplit + authorized outcome artifacts
  -> OutcomeEvaluation
Evaluated artifacts + applicable criteria and data -> ValidationReport
Comparisons + applicable evaluations + validation and review records
  -> DecisionBundle
```

Include outcome artifacts as parents only when the authorized outcome task actually consumed them. Keep their sensitive content in the protected evaluation store. A simulation comparison MUST NOT inherit reserved labels merely because another evaluation task uses them.

Any change to a consumed input, model branch, intervention, split, or criterion MUST identify affected descendants. Recompute the affected results and issue new validation records before using the revised branch in a current decision bundle.

### Evidence semantics and missingness

Use explicit evidence kinds: literature reported, observed measurement, fitted estimate, simulated result, and clinical follow-up. Preserve the distinction in claims and reports. A fitted posterior probability MUST NOT automatically be presented as a calibrated probability of seizure freedom, and a simulated comparison MUST NOT be reported as an observed clinical outcome.

Distinguish `not_reported`, `reported_absent`, `not_accessible`, and `verified_present`. Separate reported subject counts and modalities from those verified in actual files. Preserve original clinical outcome categories; any mapping to a binary endpoint MUST be versioned and prespecified.

The following is an unverified registry placeholder, not an acquired or eligible dataset:

```json
{
  "dataset_id": "candidate-unverified",
  "study_family_id": null,
  "source_doi": null,
  "repository_url": null,
  "reported_subject_count": null,
  "data_access": "to_verify",
  "verified_subject_count": null,
  "verified_modalities": [],
  "intervention_linkage": "to_verify",
  "follow_up_definition": "to_extract",
  "eligibility": "pending_file_inspection"
}
```

Do not infer independent evidence from multiple agents, papers, or artifacts that reuse the same patients, sources, or computations. Record those dependencies in cohort-family and provenance fields so that evaluation and review can account for them.
