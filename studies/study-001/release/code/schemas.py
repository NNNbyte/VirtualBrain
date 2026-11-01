"""Scientific and coordination contracts for the epilepsy research system.

Mirrors section 04 of the framework ("Scientific and task contracts").
Validation is intentionally lightweight (stdlib only): it checks that each
payload carries the content the contract requires, and that the envelope's
scientific context is consistent with the artifact kind.
"""

SCHEMA_VERSION = "1.0"

EVIDENCE_KINDS = [
    "literature_reported",
    "observed_measurement",
    "fitted_estimate",
    "simulated_result",
    "clinical_follow_up",
    "not_applicable",
]

VALIDATION_STATES = ["unreviewed", "passed", "failed", "indeterminate"]
GATE_VERDICTS = ["passed", "failed", "indeterminate"]
MISSINGNESS = ["not_reported", "reported_absent", "not_accessible", "verified_present"]

# schema_name -> required payload keys. Keys may hold explicit unknown /
# missingness states, but they must be present rather than silently omitted.
RECORD_TYPES = {
    "StudyProtocol": ["question", "population", "inclusion_rules", "endpoints", "split_rules", "metrics", "budgets"],
    "EvidenceClaim": ["claim", "bibliographic_record", "supporting_passage", "passage_location",
                      "population_and_design", "endpoint", "evidence_kind", "contradictions", "study_family_id"],
    "DatasetCard": ["dataset_id", "study_family_id", "source_doi", "repository_url", "reported_subject_count",
                    "data_access", "verified_subject_count", "verified_modalities", "intervention_linkage",
                    "follow_up_definition", "eligibility"],
    "MethodCard": ["method_name", "primary_source", "required_inputs", "implementation_versions",
                   "supported_outputs", "validation_setting", "limitations", "reproduction_status"],
    "AccessRecord": ["resource", "access_path", "status", "conditions"],
    "PatientCase": ["case_id", "dataset_id", "sessions", "recordings", "checksums", "anatomy",
                    "coordinate_transforms", "channels", "montage", "events", "units"],
    "QCReport": ["case_id", "findings", "missingness", "verdict"],
    "DerivativeManifest": ["case_id", "derivatives", "worker"],
    "CohortSplit": ["development_ids", "test_ids", "cohort_families", "partitions", "label_access_policy", "split_hash"],
    "NetworkHypothesisSet": ["case_id", "hypotheses", "source_evidence", "priors", "unobserved_node_assumptions",
                             "discrimination_checks"],
    "ModelBundle": ["model_family", "implementation_versions", "consumed_case", "hypotheses", "fitting_partitions",
                    "observation_model", "parameters_or_posterior", "numerical_diagnostics", "convergence_checks",
                    "predictive_checks", "intended_use", "environment_manifest"],
    "SurgeryPlan": ["intervention_id", "intervention_class", "geometry", "physical_mapping", "constraints",
                    "feasibility_verdict"],
    "StimulationPlan": ["intervention_id", "intervention_class", "contacts_and_device", "physical_mapping",
                        "constraints", "feasibility_verdict"],
    "FeasibilityReport": ["intervention_id", "checks", "verdict"],
    "InterventionScenarioSet": ["plan_refs", "model_samples", "objectives", "controls", "uncertainty_sampling",
                                "stopping_criteria"],
    "SimulationRequest": ["plan_refs", "model_bundle_id", "model_samples", "worker_operation", "parameter_sets",
                          "paired_baselines", "stopping_criteria"],
    "SimulationBatch": ["model_samples", "candidate_ids", "seeds", "initial_states", "solver_settings",
                        "paired_baselines", "output_refs", "numerical_checks", "resource_use"],
    "CandidateComparisonProposal": ["candidates", "tradeoffs", "requested_validation"],
    "SimulationComparison": ["permitted_inputs", "freeze_manifest", "metrics", "uncertainty", "controls",
                             "evidence_level"],
    "OutcomeEvaluation": ["permitted_inputs", "freeze_manifest", "label_access_log", "metrics", "uncertainty",
                          "evidence_level"],
    "ValidationReport": ["criterion", "criterion_version", "evaluator", "evaluated_artifacts", "held_out_data",
                         "result", "uncertainty_method", "failure_cases", "verdict", "evidence_level"],
    "DecisionBundle": ["supported_comparisons", "tradeoffs", "unstable_rankings", "missing_evidence",
                       "limitations", "reproducibility_manifest", "review_refs", "release_status"],
    "ReviewDecision": ["reviewer_role", "decision", "intended_use", "affected_artifact_ids", "reason",
                       "repair_stage", "acceptance_checks"],
    "ImprovementProposal": ["failure_evidence", "exact_change", "parent_version", "anticipated_benefit",
                            "offline_test_protocol", "risks", "acceptance_criteria", "rollback"],
    "BenchmarkRun": ["proposal_id", "parent_version", "permitted_data", "test_protocol", "resource_conditions",
                     "regression_results", "uncertainty", "verdict"],
    "ReleaseRecord": ["accepted_proposals", "implementation_hash", "environment_hash", "independent_review",
                      "permitted_scope", "migration_notes", "rollback"],
    "Report": ["title", "body"],
}

# Snake-case aliases used in role profiles (framework example uses these).
OUTPUT_TYPE_ALIASES = {
    "evidence_claim": "EvidenceClaim", "dataset_card": "DatasetCard", "method_card": "MethodCard",
    "access_record": "AccessRecord", "patient_case": "PatientCase", "qc_report": "QCReport",
    "derivative_manifest": "DerivativeManifest", "cohort_split": "CohortSplit",
    "network_hypothesis_set": "NetworkHypothesisSet", "model_bundle": "ModelBundle",
    "surgery_plan": "SurgeryPlan", "stimulation_plan": "StimulationPlan", "feasibility_report": "FeasibilityReport",
    "intervention_scenario_set": "InterventionScenarioSet", "simulation_request": "SimulationRequest",
    "simulation_batch": "SimulationBatch", "candidate_comparison_proposal": "CandidateComparisonProposal",
    "simulation_comparison": "SimulationComparison", "outcome_evaluation": "OutcomeEvaluation",
    "validation_report": "ValidationReport", "decision_bundle": "DecisionBundle", "review_decision": "ReviewDecision",
    "improvement_proposal": "ImprovementProposal", "benchmark_run": "BenchmarkRun", "release_record": "ReleaseRecord",
    "study_protocol": "StudyProtocol", "report": "Report",
}

CASE_SCHEMAS = {"PatientCase", "QCReport", "DerivativeManifest", "NetworkHypothesisSet", "ModelBundle",
                "SurgeryPlan", "StimulationPlan", "FeasibilityReport", "InterventionScenarioSet",
                "SimulationRequest", "SimulationBatch"}
SIGNAL_SCHEMAS = {"PatientCase", "DerivativeManifest"}
GEOMETRY_SCHEMAS = {"SurgeryPlan", "StimulationPlan"}


def canonical(schema):
    return OUTPUT_TYPE_ALIASES.get(schema, schema)


def validate_payload(schema_name, payload):
    """Return a list of problems; empty means the payload satisfies the contract."""
    schema_name = canonical(schema_name)
    if schema_name not in RECORD_TYPES:
        return [f"unknown schema '{schema_name}'"]
    if not isinstance(payload, dict):
        return ["payload must be a JSON object"]
    missing = [k for k in RECORD_TYPES[schema_name] if k not in payload]
    problems = [f"missing required field '{k}' (use an explicit unknown/missingness value instead)" for k in missing]
    if schema_name == "EvidenceClaim" and payload.get("evidence_kind") not in EVIDENCE_KINDS:
        problems.append(f"evidence_kind must be one of {EVIDENCE_KINDS}")
    return problems


def validate_context(schema_name, envelope):
    """Scope and scientific-context checks from the common artifact envelope rules."""
    schema_name = canonical(schema_name)
    ctx = envelope.get("scientific_context", {})
    problems = []
    if schema_name in CASE_SCHEMAS and not envelope.get("case_id"):
        problems.append("case artifacts must declare case_id")
    if schema_name in SIGNAL_SCHEMAS:
        for k in ("sample_rate_hz", "time_window", "signal_units", "reference_montage"):
            if ctx.get(k) in (None, ""):
                problems.append(f"signal artifact requires scientific_context.{k}")
    if schema_name in GEOMETRY_SCHEMAS:
        for k in ("coordinate_frame", "coordinate_units", "transform_chain_id"):
            if ctx.get(k) in (None, ""):
                problems.append(f"geometry artifact requires scientific_context.{k}")
    if ctx.get("evidence_kind") not in EVIDENCE_KINDS:
        problems.append(f"scientific_context.evidence_kind must be one of {EVIDENCE_KINDS}")
    return problems
