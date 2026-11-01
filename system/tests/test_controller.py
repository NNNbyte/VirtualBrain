"""Contract and architecture-invariant tests for the study controller.

    python -m unittest discover -s system/tests -v
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import controller as ctl  # noqa: E402

PROTOCOL = {"question": "q", "population": "drug-resistant focal epilepsy", "inclusion_rules": [],
            "endpoints": ["Engel class at >=12 months"], "split_rules": "patient-level", "metrics": [],
            "budgets": {}}
CLAIM = {"claim": "c", "bibliographic_record": "doi:x", "supporting_passage": "p", "passage_location": "Table 2",
         "population_and_design": "cohort n=30", "endpoint": "Engel I", "evidence_kind": "literature_reported",
         "contradictions": [], "study_family_id": "fam-1"}


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = (ctl.STUDIES, ctl.CURRENT)
        ctl.STUDIES = Path(self.tmp.name) / "studies"
        ctl.CURRENT = ctl.STUDIES / ".current"
        code, out = self.run_cli("study", "init", "--question", "best therapy?", "--study-id", "s1")
        self.assertEqual(code, 0, out)

    def tearDown(self):
        ctl.STUDIES, ctl.CURRENT = self._orig
        self.tmp.cleanup()

    # helpers ---------------------------------------------------------------
    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ctl.main(list(argv))
        return code, json.loads(buf.getvalue())

    def payload(self, obj, name="p.json"):
        p = Path(self.tmp.name) / name
        p.write_text(json.dumps(obj))
        return str(p)

    def propose(self, role, outputs, *extra, stage="discovery", type_="t"):
        return self.run_cli("task", "propose", "--role", role, "--type", type_, "--objective", "o",
                            "--stage", stage, "--outputs", outputs, "--criteria", "crit",
                            "--stopping-rule", "stop", *extra)

    def admitted_task(self, role, outputs, *extra, **kw):
        code, out = self.propose(role, outputs, *extra, **kw)
        self.assertEqual(code, 0, out)
        tid = out["task_id"]
        self.assertEqual(self.run_cli("task", "start", "--task", tid)[0], 0)
        return tid

    def commit(self, tid, schema, obj, *extra):
        return self.run_cli("artifact", "commit", "--task", tid, "--schema", schema,
                            "--payload", self.payload(obj, f"{tid}-{schema}.json"), *extra)

    def passed_protocol(self):
        tid = self.admitted_task("LEAD", "study_protocol", stage="protocol")
        code, out = self.commit(tid, "StudyProtocol", PROTOCOL)
        self.assertEqual(code, 0, out)
        aid = out["artifact_id"]
        self.run_cli("task", "finish", "--task", tid, "--status", "succeeded")
        code, out = self.run_cli("gate", "record", "--artifact", aid, "--criterion", "approved", "--verdict",
                                 "passed", "--evaluator", "human:tester", "--reason", "ok")
        self.assertEqual(code, 0, out)
        return aid

    # tests -----------------------------------------------------------------
    def test_release_is_frozen_with_skills_and_profiles(self):
        d = ctl.STUDIES / "s1" / "release"
        self.assertTrue((d / "skills" / "r1-evidence-scout" / "SKILL.md").exists())
        self.assertTrue((d / "skills" / "run-study" / "references" / "agent-protocol.md").exists())
        self.assertTrue((d / "profiles" / "R4-intervention-design.json").exists())

    def test_role_cannot_produce_unpermitted_output(self):
        code, out = self.propose("R1", "model_bundle")
        self.assertEqual(code, 2)
        self.assertTrue(any("may not produce ModelBundle" in r for r in out["reasons"]))

    def test_case_and_intervention_scope_required(self):
        code, out = self.propose("R2", "patient_case", stage="case_curation")
        self.assertIn("case tasks must declare scope.case_id", out["reasons"])
        code, out = self.propose("R4", "simulation_request", "--case", "C1", stage="intervention_design")
        self.assertIn("intervention tasks must declare model_bundle_id", out["reasons"])

    def test_unreviewed_inputs_do_not_satisfy_prerequisites(self):
        tid = self.admitted_task("LEAD", "study_protocol", stage="protocol")
        aid = self.commit(tid, "StudyProtocol", PROTOCOL)[1]["artifact_id"]
        code, out = self.propose("R1", "evidence_claim", "--inputs", aid)
        self.assertEqual(code, 2)
        code, out = self.propose("R1", "evidence_claim", "--inputs", aid, "--allow-unreviewed", "exploratory")
        self.assertEqual(code, 0, out)

    def test_commit_validates_payload_consumed_and_self_gate(self):
        proto = self.passed_protocol()
        tid = self.admitted_task("R1", "evidence_claim", "--inputs", proto)
        code, out = self.commit(tid, "EvidenceClaim", {"claim": "only this"})
        self.assertEqual(code, 2)
        code, out = self.commit(tid, "EvidenceClaim", CLAIM, "--consumed", "A9999-Nope")
        self.assertEqual(code, 2)
        code, out = self.commit(tid, "EvidenceClaim", CLAIM, "--evidence-kind", "literature_reported")
        self.assertEqual(code, 0, out)
        aid = out["artifact_id"]
        code, out = self.run_cli("gate", "record", "--artifact", aid, "--criterion", "c", "--verdict", "passed",
                                 "--evaluator", "R1", "--reason", "mine")
        self.assertEqual(code, 2, "producer must not gate its own artifact")
        code, out = self.run_cli("gate", "record", "--artifact", aid, "--criterion", "c", "--verdict", "passed",
                                 "--evaluator", "R5", "--reason", "source resolves")
        self.assertEqual(code, 0, out)

    def test_need_closes_only_on_passed_gate_and_once(self):
        proto = self.passed_protocol()
        nid = self.run_cli("need", "open", "--requester", "R3", "--missing", "method card", "--why", "w",
                           "--criterion", "c", "--stage", "discovery", "--target-role", "R1")[1]["need"]["need_id"]
        tid = self.admitted_task("R1", "evidence_claim", "--inputs", proto, "--need", nid)
        a1 = self.commit(tid, "EvidenceClaim", CLAIM)[1]["artifact_id"]
        a2 = self.commit(tid, "EvidenceClaim", CLAIM)[1]["artifact_id"]
        self.run_cli("task", "finish", "--task", tid, "--status", "succeeded")
        g = ["--criterion", "c", "--evaluator", "R5", "--reason", "r", "--need", nid]
        self.assertEqual(self.run_cli("gate", "record", "--artifact", a1, "--verdict", "indeterminate", *g)[0], 0)
        st = ctl.load_state(ctl.STUDIES / "s1")
        self.assertEqual(st["needs"][nid]["state"], "open", "task completion alone must not close a need")
        self.assertEqual(self.run_cli("gate", "record", "--artifact", a1, "--verdict", "passed", *g)[0], 0)
        self.assertEqual(self.run_cli("gate", "record", "--artifact", a2, "--verdict", "passed", *g)[0], 2,
                         "a need revision may have only one accepted fulfillment")

    def test_repair_marks_descendants_stale_and_blocks_reuse(self):
        proto = self.passed_protocol()
        t1 = self.admitted_task("R1", "evidence_claim", "--inputs", proto)
        claim = self.commit(t1, "EvidenceClaim", CLAIM)[1]["artifact_id"]
        self.run_cli("gate", "record", "--artifact", claim, "--criterion", "c", "--verdict", "passed",
                     "--evaluator", "R5", "--reason", "r")
        t2 = self.admitted_task("R1", "evidence_claim", "--inputs", f"{proto},{claim}")
        child = self.commit(t2, "EvidenceClaim", CLAIM)[1]["artifact_id"]
        code, out = self.run_cli("repair", "issue", "--artifact", claim, "--reason", "wrong passage",
                                 "--stage", "discovery", "--by", "RV")
        self.assertEqual(code, 0, out)
        self.assertEqual(set(out["stale"]), {claim, child})
        code, out = self.propose("R1", "evidence_claim", "--inputs", claim)
        self.assertEqual(code, 2)
        self.assertTrue(any("stale" in r for r in out["reasons"]))

    def test_report_may_cite_artifacts_from_its_own_task(self):
        proto = self.passed_protocol()
        tid = self.admitted_task("R1", "evidence_claim,report", "--inputs", proto)
        claim = self.commit(tid, "EvidenceClaim", CLAIM)[1]["artifact_id"]
        code, out = self.commit(tid, "Report", {"title": "t", "body": "b"}, "--consumed", f"{proto},{claim}")
        self.assertEqual(code, 0, out)
        other = self.admitted_task("R1", "report", "--inputs", proto)
        code, out = self.commit(other, "Report", {"title": "t", "body": "b"}, "--consumed", claim)
        self.assertEqual(code, 2, "another task's artifact must still be an admitted input")

    def test_repair_leaves_evaluation_records_standing(self):
        proto = self.passed_protocol()
        t1 = self.admitted_task("R1", "evidence_claim", "--inputs", proto)
        claim = self.commit(t1, "EvidenceClaim", CLAIM)[1]["artifact_id"]
        self.run_cli("gate", "record", "--artifact", claim, "--criterion", "c", "--verdict", "passed",
                     "--evaluator", "R5", "--reason", "r")
        t2 = self.admitted_task("R5", "validation_report", "--inputs", f"{proto},{claim}", stage="evaluation")
        report = {k: "x" for k in ctl.schemas.RECORD_TYPES["ValidationReport"]}
        vr = self.commit(t2, "ValidationReport", report)[1]["artifact_id"]
        code, out = self.run_cli("repair", "issue", "--artifact", claim, "--reason", "wrong passage",
                                 "--stage", "discovery", "--by", "RV")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["stale"], [claim])
        self.assertFalse(ctl.load_state(ctl.STUDIES / "s1")["artifacts"][vr]["stale"])

    def test_reserved_outcomes_only_for_r5_after_freeze(self):
        proto = self.passed_protocol()
        outcomes = self.payload({"C1": "Engel I"}, "outcomes.json")
        item = self.run_cli("vault", "seal", "--file", outcomes, "--label", "outcomes")[1]["item_id"]
        code, out = self.propose("R3", "model_bundle", "--case", "C1", "--inputs", proto,
                                 stage="evaluation", type_="outcome_evaluation")
        self.assertEqual(code, 2)
        code, out = self.propose("R5", "outcome_evaluation", "--inputs", proto,
                                 stage="evaluation", type_="outcome_evaluation")
        self.assertEqual(code, 2)
        self.assertTrue(any("frozen" in r for r in out["reasons"]))
        # a non-outcome R5 task cannot reveal
        other = self.admitted_task("R5", "validation_report", "--inputs", proto, stage="evaluation")
        self.assertEqual(self.run_cli("vault", "reveal", "--task", other, "--item", item)[0], 2)
        self.run_cli("predictions", "freeze", "--artifacts", proto)
        tid = self.admitted_task("R5", "outcome_evaluation", "--inputs", proto,
                                 stage="evaluation", type_="outcome_evaluation")
        code, out = self.run_cli("vault", "reveal", "--task", tid, "--item", item)
        self.assertEqual(code, 0, out)
        st = ctl.load_state(ctl.STUDIES / "s1")
        self.assertEqual([e["type"] for e in st["vault"]["audit"]], ["vault_access_denied", "vault_access_granted"])

    def test_disabled_role_and_budget(self):
        code, out = self.propose("R6", "improvement_proposal", stage="improvement")
        self.assertTrue(any("disabled" in r for r in out["reasons"]))
        for _ in range(10):  # LEAD budget is 10 tasks per run
            self.assertEqual(self.propose("LEAD", "report", stage="dossier")[0], 0)
        code, out = self.propose("LEAD", "report", stage="dossier")
        self.assertTrue(any("budget" in r for r in out["reasons"]))

    def test_dashboard_state_shows_running_agent(self):
        tid = self.admitted_task("R1", "evidence_claim")
        self.run_cli("task", "log", "--task", tid, "--msg", "searching")
        st = ctl.load_state(ctl.STUDIES / "s1")
        r1 = st["agents"]["R1-evidence-scout"]
        self.assertEqual(r1["status"], "running")
        self.assertEqual(st["tasks"][tid]["progress"][0]["msg"], "searching")


if __name__ == "__main__":
    unittest.main()
