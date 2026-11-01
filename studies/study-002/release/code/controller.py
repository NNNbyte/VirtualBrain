"""Deterministic study controller for the epilepsy research agent system.

Agents propose; this controller decides. It owns task admission, artifact
commits (common envelope + lineage), gate verdicts, scoped needs with leases,
repairs/staleness, the reserved-outcome vault, and frozen releases.

Everything is recorded in an append-only ledger (studies/<id>/ledger.jsonl);
current state is a replay of that ledger. Stdlib only.

Usage:  python system/controller.py <command> [options]     (see --help)
All commands print JSON. Exit code 0 = ok, 2 = refused by a rule, 1 = error.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schemas  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STUDIES = ROOT / "studies"
SKILLS = ROOT / ".claude" / "skills"
PROFILES = ROOT / "system" / "profiles"
CURRENT = STUDIES / ".current"

INTERVENTION_SCHEMAS = {"InterventionScenarioSet", "SimulationRequest", "SimulationBatch"}
GATE_ROLES_FORBIDDEN_SELF = True  # an artifact is never gated by its own producer role


class Refused(Exception):
    def __init__(self, reasons):
        self.reasons = reasons if isinstance(reasons, list) else [reasons]
        super().__init__("; ".join(self.reasons))


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return sha256_bytes(Path(p).read_bytes())


def canon_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# --------------------------------------------------------------------- release

def release_sources():
    """Files that define a system release: skills, role profiles, controller code."""
    files = []
    if SKILLS.exists():
        files += sorted(p for p in SKILLS.rglob("*") if p.is_file())
    files += sorted(PROFILES.glob("*.json"))
    files += sorted((ROOT / "system").glob("*.py"))
    return files


def compute_release_id(files=None):
    h = hashlib.sha256()
    for p in files or release_sources():
        h.update(p.relative_to(ROOT).as_posix().encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return "rel-" + h.hexdigest()[:12]


def freeze_release(study_dir):
    files = release_sources()
    rid = compute_release_id(files)
    rdir = study_dir / "release"
    manifest = {"release_id": rid, "frozen_at": now(), "files": {}}
    for p in files:
        rel = p.relative_to(ROOT)
        if rel.parts[0] == ".claude":
            dest = rdir / "skills" / rel.relative_to(".claude/skills")
        elif rel.parts[1] == "profiles":
            dest = rdir / "profiles" / p.name
        else:
            dest = rdir / "code" / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        manifest["files"][rel.as_posix()] = sha256_file(p)
    (rdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return rid


def frozen_profiles(study_dir):
    out = {}
    for p in sorted((study_dir / "release" / "profiles").glob("*.json")):
        prof = json.loads(p.read_text(encoding="utf-8"))
        out[prof["agent_id"]] = prof
    return out


def live_profiles():
    return {json.loads(p.read_text(encoding="utf-8"))["agent_id"]: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(PROFILES.glob("*.json"))}


def resolve_role(profiles, role):
    """Accept agent_id ('R4-intervention-design'), short code ('R4') or role name."""
    for aid, p in profiles.items():
        if role in (aid, p["role"], aid.split("-")[0]):
            return aid
    raise Refused(f"unknown role '{role}'")


# ---------------------------------------------------------------------- ledger

def study_dir(study_id):
    if not study_id:
        if not CURRENT.exists():
            raise Refused("no --study given and no current study; run `study init` first")
        study_id = CURRENT.read_text().strip()
    d = STUDIES / study_id
    if not (d / "study.json").exists():
        raise Refused(f"study '{study_id}' does not exist")
    return d


class Lock:
    def __init__(self, d):
        self.path = d / ".lock"

    def __enter__(self):
        deadline = time.time() + 20
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 30:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    raise RuntimeError(f"could not acquire {self.path}")
                time.sleep(0.05)

    def __exit__(self, *a):
        self.path.unlink(missing_ok=True)


def read_ledger(d):
    p = d / "ledger.jsonl"
    if not p.exists():
        return []
    events = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def append(d, event_type, **data):
    ev = {"seq": None, "ts": now(), "type": event_type, **data}
    p = d / "ledger.jsonl"
    seq = 1
    if p.exists():
        with p.open(encoding="utf-8") as f:
            seq += sum(1 for _ in f)
    ev["seq"] = seq
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=True) + "\n")
    return ev


# ----------------------------------------------------------------------- state

def load_state(d):
    """Replay the ledger into current state. Also used by the dashboard."""
    meta = json.loads((d / "study.json").read_text(encoding="utf-8"))
    st = {"study": meta, "tasks": {}, "artifacts": {}, "needs": {}, "gates": [], "repairs": [],
          "vault": {"items": {}, "audit": []}, "frozen_predictions": [], "events": [], "refusals": []}
    t_now = dt.datetime.now(dt.timezone.utc)
    for ev in read_ledger(d):
        st["events"].append(ev)
        t = ev["type"]
        if t == "task_proposed":
            st["tasks"][ev["task"]["task_id"]] = {**ev["task"], "state": "proposed", "progress": [],
                                                  "proposed_at": ev["ts"]}
        elif t == "task_admitted":
            st["tasks"][ev["task_id"]]["state"] = "admitted"
        elif t == "task_refused":
            st["tasks"][ev["task_id"]].update(state="refused", refusal=ev["reasons"])
            st["refusals"].append(ev)
        elif t == "task_started":
            st["tasks"][ev["task_id"]].update(state="running", instance=ev.get("instance"), started_at=ev["ts"],
                                              attempt=ev.get("attempt", 1))
        elif t == "task_progress":
            st["tasks"][ev["task_id"]]["progress"].append({"ts": ev["ts"], "msg": ev["msg"]})
        elif t == "task_finished":
            st["tasks"][ev["task_id"]].update(state=ev["status"], finished_at=ev["ts"], summary=ev.get("summary"))
        elif t == "artifact_committed":
            a = ev["envelope"]
            st["artifacts"][a["artifact_id"]] = {**a, "effective_validation": a["validation_status"],
                                                 "stale": False, "gates": [], "superseded_by": None}
        elif t == "gate_recorded":
            st["gates"].append(ev)
            art = st["artifacts"].get(ev["artifact_id"])
            if art:
                art["effective_validation"] = ev["verdict"]
                art["gates"].append(ev)
        elif t == "artifact_stale":
            if ev["artifact_id"] in st["artifacts"]:
                st["artifacts"][ev["artifact_id"]]["stale"] = True
                st["artifacts"][ev["artifact_id"]]["stale_reason"] = ev.get("reason")
        elif t == "artifact_superseded":
            if ev["artifact_id"] in st["artifacts"]:
                st["artifacts"][ev["artifact_id"]]["superseded_by"] = ev["by"]
        elif t == "repair_issued":
            st["repairs"].append(ev)
        elif t == "need_opened":
            st["needs"][ev["need"]["need_id"]] = {**ev["need"], "state": "open", "claim": None,
                                                  "fulfillment": None, "attempts": []}
        elif t == "need_claimed":
            st["needs"][ev["need_id"]]["claim"] = {"role": ev["role"], "lease_id": ev["lease_id"],
                                                   "expires_at": ev["expires_at"]}
        elif t == "need_released":
            st["needs"][ev["need_id"]]["claim"] = None
        elif t == "need_attempt_failed":
            st["needs"][ev["need_id"]]["attempts"].append(ev)
        elif t == "need_fulfilled":
            st["needs"][ev["need_id"]].update(state="fulfilled", fulfillment=ev["artifact_id"])
        elif t == "need_reopened":
            st["needs"][ev["need_id"]].update(state="open", fulfillment=None, revision=ev["revision"])
        elif t == "vault_sealed":
            st["vault"]["items"][ev["item_id"]] = {k: ev[k] for k in ("item_id", "label", "sha256", "ts")}
        elif t in ("vault_access_granted", "vault_access_denied"):
            st["vault"]["audit"].append(ev)
        elif t == "predictions_frozen":
            st["frozen_predictions"].append(ev)
    for n in st["needs"].values():  # expire leases
        c = n["claim"]
        if c and dt.datetime.fromisoformat(c["expires_at"]) < t_now:
            n["claim"] = None
            n["lease_expired"] = True
    st["agents"] = agent_activity(d, st)
    return st


def agent_activity(d, st):
    try:
        profs = frozen_profiles(d)
    except Exception:
        profs = live_profiles()
    out = {}
    for aid, p in profs.items():
        tasks = [t for t in st["tasks"].values() if t["assigned_role"] == aid]
        running = [t for t in tasks if t["state"] == "running"]
        queued = [t for t in tasks if t["state"] == "admitted"]
        last = max(tasks, key=lambda t: t.get("finished_at") or t.get("started_at") or t["proposed_at"], default=None)
        status = "running" if running else ("queued" if queued else ("disabled" if not p.get("enabled") else "idle"))
        out[aid] = {"agent_id": aid, "display_name": p.get("display_name", aid), "color": p.get("color"),
                    "enabled": p.get("enabled", True), "status": status,
                    "running": [t["task_id"] for t in running], "queued": [t["task_id"] for t in queued],
                    "last_task": last["task_id"] if last else None,
                    "counts": {s: sum(1 for t in tasks if t["state"] == s)
                               for s in ("succeeded", "failed", "abstained", "refused", "running", "admitted")},
                    "budget": p.get("budget", {}).get("max_tasks_per_run")}
    return out


def descendants(st, artifact_id):
    """Artifacts derived from artifact_id. Evaluation records that consumed it are skipped, not marked."""
    out, frontier = [], [artifact_id]
    while frontier:
        cur = frontier.pop()
        for a in st["artifacts"].values():
            if a["schema_name"] in schemas.EVALUATION_SCHEMAS:
                continue
            if cur in a["consumed_artifact_ids"] and a["artifact_id"] not in out:
                out.append(a["artifact_id"])
                frontier.append(a["artifact_id"])
    return out


def next_id(st, key, prefix, width=4):
    return f"{prefix}{len(st[key]) + 1:0{width}d}"


# -------------------------------------------------------------------- commands

def cmd_study_init(a):
    STUDIES.mkdir(exist_ok=True)
    sid = a.study_id or "study-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = STUDIES / sid
    if (d / "study.json").exists():
        raise Refused(f"study '{sid}' already exists (use --study {sid} with other commands to resume)")
    for sub in ("artifacts", "work", "vault"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    rid = freeze_release(d)
    meta = {"study_id": sid, "question": a.question, "created_at": now(), "system_release_id": rid,
            "protocol_version": "v1", "run_id": "run-1", "status": "active"}
    (d / "study.json").write_text(json.dumps(meta, indent=2))
    CURRENT.write_text(sid)
    with Lock(d):
        append(d, "study_initialized", study=meta)
    return {"ok": True, "study_id": sid, "system_release_id": rid, "study_dir": str(d),
            "frozen_skills_dir": str(d / "release" / "skills")}


def cmd_study_list(a):
    out = []
    for p in sorted(STUDIES.glob("*/study.json")) if STUDIES.exists() else []:
        out.append(json.loads(p.read_text(encoding="utf-8")))
    cur = CURRENT.read_text().strip() if CURRENT.exists() else None
    return {"current": cur, "studies": out}


def cmd_study_use(a):
    study_dir(a.study_id)
    CURRENT.write_text(a.study_id)
    return {"ok": True, "current": a.study_id}


def cmd_study_close(a):
    d = study_dir(a.study)
    with Lock(d):
        meta = json.loads((d / "study.json").read_text(encoding="utf-8"))
        meta["status"] = a.status
        (d / "study.json").write_text(json.dumps(meta, indent=2))
        append(d, "study_status", status=a.status, note=a.note)
    return {"ok": True, "status": a.status}


def cmd_status(a):
    d = study_dir(a.study)
    st = load_state(d)
    live = compute_release_id()
    return {
        "study": st["study"],
        "live_release_id": live,
        "release_drift": live != st["study"]["system_release_id"],
        "agents": st["agents"],
        "tasks": {k: {f: v.get(f) for f in ("task_type", "assigned_role", "state", "objective", "stage", "case_id")}
                  for k, v in st["tasks"].items()},
        "open_needs": [n for n in st["needs"].values() if n["state"] == "open"],
        "artifacts": {k: {"schema": v["schema_name"], "producer": v["producer_role"],
                          "validation": v["effective_validation"], "stale": v["stale"],
                          "case_id": v.get("case_id"), "consumed": v["consumed_artifact_ids"]}
                      for k, v in st["artifacts"].items()},
        "frozen_predictions": [e["artifact_ids"] for e in st["frozen_predictions"]],
    }


def _split(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def admission_check(d, st, task):
    meta = st["study"]
    reasons = []
    profs = frozen_profiles(d)
    try:
        aid = resolve_role(profs, task["assigned_role"])
    except Refused as e:
        return e.reasons
    task["assigned_role"] = aid
    prof = profs[aid]
    if meta.get("status") != "active":
        reasons.append(f"study status is '{meta.get('status')}', not active")
    if not prof.get("enabled", True):
        reasons.append(f"role {aid} is disabled in the frozen release")
    if task["scope"]["system_release_id"] != meta["system_release_id"]:
        reasons.append("task release does not match the study's frozen release")
    if not task["scope"].get("stage"):
        reasons.append("scope.stage is required")
    if not task.get("objective"):
        reasons.append("objective is required")
    if not task["scientific_acceptance_criteria"]:
        reasons.append("at least one scientific acceptance criterion is required")
    if not task.get("stopping_rule"):
        reasons.append("stopping_rule is required")
    allowed = {schemas.canonical(x) for x in prof["allowed_output_types"]}
    # scoped needs are published with `need open`, not committed as artifacts
    outs = [schemas.canonical(x) for x in task["permitted_output_schemas"]
            if x not in ("scoped_need", "ScopedNeed")]
    if not outs:
        reasons.append("permitted_output_schemas must name at least one artifact schema")
    for o in outs:
        if o not in schemas.RECORD_TYPES:
            reasons.append(f"unknown output schema '{o}'")
        elif o not in allowed:
            reasons.append(f"{aid} may not produce {o}")
    task["permitted_output_schemas"] = outs
    case_task = any(o in schemas.CASE_SCHEMAS for o in outs)
    if case_task and prof["scope_requirements"].get("case_id") == "required_for_case_tasks" and not task["scope"].get("case_id"):
        reasons.append("case tasks must declare scope.case_id")
    if any(o in INTERVENTION_SCHEMAS for o in outs) and \
            prof["scope_requirements"].get("model_bundle_id") == "required_for_intervention_tasks" and not task.get("model_bundle_id"):
        reasons.append("intervention tasks must declare model_bundle_id")
    if task.get("model_bundle_id") and task["model_bundle_id"] not in task["input_artifact_ids"]:
        task["input_artifact_ids"].append(task["model_bundle_id"])
    # inputs: exist, current, passed (unless exploratory with explicit reason)
    for iid in task["input_artifact_ids"]:
        art = st["artifacts"].get(iid)
        if not art:
            reasons.append(f"input {iid} does not exist")
            continue
        if art["stale"] or art["superseded_by"]:
            reasons.append(f"input {iid} is stale/superseded and may not be reused as current")
        ev = art["effective_validation"]
        if ev != "passed" and not task.get("allow_unreviewed_inputs"):
            reasons.append(f"input {iid} has validation '{ev}'; only passed inputs satisfy a prerequisite "
                           "(use --allow-unreviewed REASON for exploratory work)")
        if art.get("access_classification") == "reserved" and task["task_type"] != "outcome_evaluation":
            reasons.append(f"input {iid} is reserved; only outcome_evaluation tasks may consume it")
        if task["scope"].get("case_id") and art.get("case_id") and art["case_id"] != task["scope"]["case_id"]:
            reasons.append(f"input {iid} belongs to case {art['case_id']}, not {task['scope']['case_id']}")
    # reserved outcome access
    if task["task_type"] == "outcome_evaluation":
        if not prof["permissions"].get("read_reserved_outcomes") or \
                "outcome_evaluation" not in prof.get("reserved_outcome_task_types", []):
            reasons.append(f"{aid} is not permitted to run outcome_evaluation tasks")
        frozen = {x for e in st["frozen_predictions"] for x in e["artifact_ids"]}
        unfrozen = [i for i in task["input_artifact_ids"] if i not in frozen
                    and st["artifacts"].get(i, {}).get("access_classification") != "reserved"]
        if unfrozen:
            reasons.append(f"predictions must be frozen before outcome evaluation; not frozen: {unfrozen}")
    # dependencies
    for dep in task["dependency_task_ids"]:
        dt_ = st["tasks"].get(dep)
        if not dt_ or dt_["state"] != "succeeded":
            reasons.append(f"dependency {dep} has not succeeded")
    # budget
    used = sum(1 for t in st["tasks"].values() if t["assigned_role"] == aid
               and t["state"] not in ("refused", "proposed"))
    limit = prof.get("budget", {}).get("max_tasks_per_run")
    if limit is not None and used >= limit:
        reasons.append(f"{aid} budget exhausted ({used}/{limit} tasks)")
    # needs
    if task.get("need_id"):
        n = st["needs"].get(task["need_id"])
        if not n:
            reasons.append(f"need {task['need_id']} does not exist")
        elif n["state"] != "open":
            reasons.append(f"need {task['need_id']} is {n['state']}")
        elif n["claim"] and n["claim"]["role"] != aid:
            reasons.append(f"need {task['need_id']} is leased to {n['claim']['role']}")
    # R6 boundary
    if prof["scope_requirements"].get("system_release_id") == "future_release_only" and \
            task.get("target_release", "future") != "future":
        reasons.append("improvement tasks may only target a future release")
    return reasons


def cmd_task_propose(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        meta = st["study"]
        task = {
            "task_id": next_id(st, "tasks", "T"),
            "task_type": a.type, "objective": a.objective,
            "requester_role": a.requester, "assigned_role": a.role, "role_profile_version": "2.0",
            "scope": {"study_id": meta["study_id"], "case_id": a.case, "stage": a.stage,
                      "run_id": meta["run_id"], "system_release_id": meta["system_release_id"]},
            "case_id": a.case, "stage": a.stage,
            "protocol_version": meta["protocol_version"], "cohort_split_id": a.split,
            "model_bundle_id": a.model_bundle,
            "input_artifact_ids": _split(a.inputs), "dependency_task_ids": _split(a.depends),
            "permitted_output_schemas": _split(a.outputs),
            "worker_id": a.worker, "worker_contract_version": "1.0",
            "parameters": json.loads(a.params) if a.params else {},
            "scientific_acceptance_criteria": [c for c in (a.criteria or [])],
            "resource_estimate": a.estimate, "resource_limit": a.limit, "stopping_rule": a.stopping_rule,
            "access_classification": "internal", "permitted_destinations": ["study_store"],
            "need_id": a.need, "need_revision": None, "lease_id": None,
            "allow_unreviewed_inputs": a.allow_unreviewed, "rationale": a.rationale,
        }
        reasons = admission_check(d, st, task)
        if not reasons and task["need_id"]:
            n = st["needs"][task["need_id"]]
            task["need_revision"] = n.get("revision", 1)
            lease = _claim(d, task["need_id"], task["assigned_role"], 120)
            task["lease_id"] = lease["lease_id"]
        append(d, "task_proposed", task=task)
        if reasons:
            append(d, "task_refused", task_id=task["task_id"], reasons=reasons)
            raise Refused([f"task {task['task_id']} refused"] + reasons)
        append(d, "task_admitted", task_id=task["task_id"])
    return {"ok": True, "admitted": True, "task_id": task["task_id"], "assigned_role": task["assigned_role"],
            "task": task}


def cmd_task_start(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        t = st["tasks"].get(a.task)
        if not t:
            raise Refused(f"task {a.task} does not exist")
        if t["state"] not in ("admitted", "failed") or (t["state"] == "failed" and not a.retry):
            raise Refused(f"task {a.task} is '{t['state']}', not admitted (pass --retry to retry a failed task)")
        prof = frozen_profiles(d)[t["assigned_role"]]
        attempt = t.get("attempt", 0) + 1
        append(d, "task_started", task_id=a.task, instance=a.instance, attempt=attempt)
    skill = d / "release" / "skills" / prof["skill"] / "SKILL.md"
    work = d / "work" / a.task
    work.mkdir(parents=True, exist_ok=True)
    (work / "task.json").write_text(json.dumps(t, indent=2))
    return {"ok": True, "task_id": a.task, "attempt": attempt, "frozen_skill_path": str(skill),
            "work_dir": str(work), "task": t,
            "reminder": "Read and follow the frozen skill. Log progress with `task log`, commit outputs with "
                        "`artifact commit`, then `task finish`."}


def cmd_task_log(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        if a.task not in st["tasks"]:
            raise Refused(f"task {a.task} does not exist")
        append(d, "task_progress", task_id=a.task, msg=a.msg)
    return {"ok": True}


def cmd_task_finish(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        t = st["tasks"].get(a.task)
        if not t or t["state"] != "running":
            raise Refused(f"task {a.task} is not running")
        append(d, "task_finished", task_id=a.task, status=a.status, summary=a.summary)
        if t.get("need_id") and t.get("lease_id"):
            append(d, "need_released", need_id=t["need_id"], reason=f"task {a.task} finished")
    return {"ok": True, "task_id": a.task, "execution_status": a.status,
            "note": "Execution status is recorded separately; a scientific gate still has to pass."}


def cmd_task_show(a):
    d = study_dir(a.study)
    st = load_state(d)
    if a.task not in st["tasks"]:
        raise Refused(f"task {a.task} does not exist")
    return st["tasks"][a.task]


def _parse_context(items):
    ctx = {}
    for kv in items or []:
        k, _, v = kv.partition("=")
        try:
            ctx[k] = json.loads(v)
        except json.JSONDecodeError:
            ctx[k] = v
    return ctx


def cmd_artifact_commit(a):
    d = study_dir(a.study)
    payload_path = Path(a.payload)
    payload_bytes = payload_path.read_bytes()
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError as e:
        raise Refused(f"payload is not valid JSON: {e}")
    schema = schemas.canonical(a.schema)
    with Lock(d):
        st = load_state(d)
        t = st["tasks"].get(a.task)
        reasons = []
        if not t or t["state"] != "running":
            raise Refused(f"task {a.task} is not running; artifacts are committed from a running task")
        if schema not in t["permitted_output_schemas"]:
            reasons.append(f"{schema} is not among task's permitted outputs {t['permitted_output_schemas']}")
        consumed = _split(a.consumed) if a.consumed is not None else list(t["input_artifact_ids"])
        granted = {e["item_id"] for e in st["vault"]["audit"]
                   if e["type"] == "vault_access_granted" and e["task_id"] == a.task}
        own = {x["artifact_id"] for x in st["artifacts"].values() if x["task_id"] == a.task}
        for c in consumed:
            if c not in t["input_artifact_ids"] and c not in granted and c not in own:
                reasons.append(f"consumed {c} was neither an admitted input of {a.task} nor committed by it")
        reasons += schemas.validate_payload(schema, payload)
        ctx = _parse_context(a.context)
        ctx.setdefault("evidence_kind", a.evidence_kind)
        aid = f"A{len(st['artifacts']) + 1:04d}-{schema}"
        env = {
            "artifact_id": aid, "schema_name": schema, "schema_version": schemas.SCHEMA_VERSION,
            "study_id": st["study"]["study_id"], "cohort_id": a.cohort, "case_id": a.case or t.get("case_id"),
            "session_id": a.session, "run_id": st["study"]["run_id"], "task_id": a.task,
            "system_release_id": st["study"]["system_release_id"], "protocol_version": st["study"]["protocol_version"],
            "model_bundle_id": t.get("model_bundle_id"),
            "producer_role": t["assigned_role"], "tool_id": a.tool or t.get("worker_id"), "tool_version": a.tool_version,
            "code_commit": a.code_commit, "environment_digest": a.env_digest,
            "consumed_artifact_ids": consumed,
            "input_manifest_hash": sha256_bytes(canon_json(sorted(
                st["artifacts"][c]["manifest_hash"] for c in consumed if c in st["artifacts"])).encode()),
            "payload_refs": [],
            "scientific_context": ctx,
            "execution_status": "succeeded",
            "validation_status": "unreviewed",
            "access_classification": a.access, "permitted_destinations": ["study_store"],
            "created_at": now(), "supersedes_id": a.supersedes, "title": a.title,
        }
        reasons += schemas.validate_context(schema, env)
        if a.supersedes and a.supersedes not in st["artifacts"]:
            reasons.append(f"supersedes {a.supersedes} does not exist")
        if reasons:
            append(d, "artifact_rejected", task_id=a.task, schema=schema, reasons=reasons)
            raise Refused(["artifact rejected"] + reasons)
        adir = d / "artifacts" / aid
        adir.mkdir(parents=True)
        dest = adir / ("payload" + payload_path.suffix)
        dest.write_bytes(payload_bytes)
        for extra in a.attach or []:
            ep = Path(extra)
            shutil.copy2(ep, adir / ep.name)
            env["payload_refs"].append({"uri": f"artifacts/{aid}/{ep.name}", "media_type": "application/octet-stream",
                                        "sha256": sha256_file(ep), "byte_size": ep.stat().st_size})
        env["payload_refs"].insert(0, {"uri": f"artifacts/{aid}/{dest.name}", "media_type": "application/json",
                                       "sha256": sha256_bytes(payload_bytes), "byte_size": len(payload_bytes)})
        env["manifest_hash"] = sha256_bytes(canon_json(env).encode())  # hash excludes its own field
        (adir / "manifest.json").write_text(json.dumps(env, indent=2))
        append(d, "artifact_committed", envelope=env)
        stale = []
        if a.supersedes:
            append(d, "artifact_superseded", artifact_id=a.supersedes, by=aid)
            for x in [a.supersedes] + descendants(st, a.supersedes):
                append(d, "artifact_stale", artifact_id=x, reason=f"superseded by {aid}")
                stale.append(x)
    return {"ok": True, "artifact_id": aid, "manifest_hash": env["manifest_hash"], "marked_stale": stale,
            "validation_status": "unreviewed"}


def cmd_artifact_show(a):
    d = study_dir(a.study)
    st = load_state(d)
    art = st["artifacts"].get(a.artifact)
    if not art:
        raise Refused(f"artifact {a.artifact} does not exist")
    if art["access_classification"] == "reserved":
        return {"envelope": art, "payload": "<reserved: access only via vault reveal in an outcome_evaluation task>"}
    p = d / art["payload_refs"][0]["uri"]
    return {"envelope": art, "payload": json.loads(p.read_text(encoding="utf-8")) if a.payload else str(p)}


def cmd_artifact_list(a):
    d = study_dir(a.study)
    st = load_state(d)
    rows = []
    for x in st["artifacts"].values():
        if a.schema and x["schema_name"] != schemas.canonical(a.schema):
            continue
        rows.append({"artifact_id": x["artifact_id"], "schema": x["schema_name"], "producer": x["producer_role"],
                     "case_id": x.get("case_id"), "validation": x["effective_validation"], "stale": x["stale"],
                     "title": x.get("title")})
    return {"artifacts": rows}


def cmd_gate_record(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        art = st["artifacts"].get(a.artifact)
        reasons = []
        if not art:
            raise Refused(f"artifact {a.artifact} does not exist")
        profs = frozen_profiles(d)
        # humans (e.g. a clinician gating from the dashboard) sign as "human:<name>"
        evaluator = a.evaluator if a.evaluator.startswith("human:") else resolve_role(profs, a.evaluator)
        if GATE_ROLES_FORBIDDEN_SELF and evaluator == art["producer_role"]:
            reasons.append("an artifact may not be gated by the role that produced it")
        if art["stale"]:
            reasons.append("artifact is stale; gate the repaired version instead")
        if a.need:
            n = st["needs"].get(a.need)
            if not n:
                reasons.append(f"need {a.need} does not exist")
            elif n["state"] == "fulfilled":
                reasons.append(f"need {a.need} already has an accepted fulfillment ({n['fulfillment']})")
        if reasons:
            raise Refused(reasons)
        append(d, "gate_recorded", artifact_id=a.artifact, criterion=a.criterion, verdict=a.verdict,
               evaluator=evaluator, reason=a.reason, need_id=a.need)
        fulfilled = False
        if a.need:
            if a.verdict == "passed":
                append(d, "need_fulfilled", need_id=a.need, artifact_id=a.artifact)
                fulfilled = True
            else:
                append(d, "need_attempt_failed", need_id=a.need, artifact_id=a.artifact, verdict=a.verdict,
                       reason=a.reason)
    return {"ok": True, "artifact_id": a.artifact, "verdict": a.verdict, "need_fulfilled": fulfilled}


def _claim(d, need_id, role, minutes):
    lease = {"lease_id": f"L-{need_id}-{int(time.time())}",
             "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)).replace(microsecond=0).isoformat()}
    append(d, "need_claimed", need_id=need_id, role=role, **lease)
    return lease


def cmd_need_open(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        profs = frozen_profiles(d)
        need = {"need_id": next_id(st, "needs", "N", 3), "requester": resolve_role(profs, a.requester),
                "missing_input": a.missing, "why": a.why, "acceptance_criterion": a.criterion,
                "study_id": st["study"]["study_id"], "case_id": a.case, "stage": a.stage,
                "suggested_role": resolve_role(profs, a.target_role) if a.target_role else None,
                "system_release_id": st["study"]["system_release_id"], "access_scope": a.access,
                "revision": 1, "opened_at": now()}
        append(d, "need_opened", need=need)
    return {"ok": True, "need": need}


def cmd_need_claim(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        n = st["needs"].get(a.need)
        if not n or n["state"] != "open":
            raise Refused(f"need {a.need} is not open")
        role = resolve_role(frozen_profiles(d), a.role)
        if n["claim"] and n["claim"]["role"] != role:
            raise Refused(f"need {a.need} is leased to {n['claim']['role']} until {n['claim']['expires_at']}")
        lease = _claim(d, a.need, role, a.minutes)
    return {"ok": True, **lease}


def cmd_need_list(a):
    d = study_dir(a.study)
    st = load_state(d)
    return {"needs": [n for n in st["needs"].values() if a.all or n["state"] == "open"]}


def cmd_repair(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        if a.artifact not in st["artifacts"]:
            raise Refused(f"artifact {a.artifact} does not exist")
        affected = [a.artifact] + descendants(st, a.artifact)
        by = resolve_role(frozen_profiles(d), a.by)
        append(d, "repair_issued", artifact_id=a.artifact, reason=a.reason, stage=a.stage, by=by, affected=affected)
        for x in affected:
            append(d, "artifact_stale", artifact_id=x, reason=f"repair of {a.artifact}: {a.reason}")
        art = st["artifacts"][a.artifact]
        need = {"need_id": next_id(st, "needs", "N", 3), "requester": by,
                "missing_input": f"repaired replacement for {a.artifact} ({art['schema_name']})",
                "why": a.reason, "acceptance_criterion": a.criterion or "repair addresses the stated reason and passes the original gate criterion",
                "study_id": st["study"]["study_id"], "case_id": art.get("case_id"), "stage": a.stage,
                "suggested_role": art["producer_role"], "system_release_id": st["study"]["system_release_id"],
                "access_scope": "internal", "revision": 1, "opened_at": now(), "repair_of": a.artifact}
        append(d, "need_opened", need=need)
    return {"ok": True, "stale": affected, "repair_need": need["need_id"],
            "note": "Recompute affected descendants and issue new validation records before reuse."}


def cmd_predictions_freeze(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        ids = _split(a.artifacts)
        missing = [i for i in ids if i not in st["artifacts"]]
        if missing:
            raise Refused(f"unknown artifacts {missing}")
        h = sha256_bytes(canon_json(sorted(st["artifacts"][i]["manifest_hash"] for i in ids)).encode())
        append(d, "predictions_frozen", artifact_ids=ids, freeze_hash=h, by=a.by)
    return {"ok": True, "freeze_hash": h, "artifact_ids": ids}


def cmd_vault_seal(a):
    d = study_dir(a.study)
    src = Path(a.file)
    with Lock(d):
        st = load_state(d)
        item = f"V{len(st['vault']['items']) + 1:03d}"
        dest = d / "vault" / f"{item}{src.suffix}"
        shutil.copy2(src, dest)
        append(d, "vault_sealed", item_id=item, label=a.label, sha256=sha256_file(dest))
    return {"ok": True, "item_id": item, "note": "Reserved outcome sealed. Only outcome_evaluation tasks can reveal it."}


def cmd_vault_reveal(a):
    d = study_dir(a.study)
    with Lock(d):
        st = load_state(d)
        t = st["tasks"].get(a.task)
        reasons = []
        if not t or t["state"] != "running":
            reasons.append(f"task {a.task} is not running")
        else:
            prof = frozen_profiles(d)[t["assigned_role"]]
            if t["task_type"] != "outcome_evaluation":
                reasons.append(f"task type '{t['task_type']}' may not access reserved outcomes")
            if not prof["permissions"].get("read_reserved_outcomes"):
                reasons.append(f"{t['assigned_role']} lacks read_reserved_outcomes")
        if a.item not in st["vault"]["items"]:
            reasons.append(f"vault item {a.item} does not exist")
        if reasons:
            append(d, "vault_access_denied", task_id=a.task, item_id=a.item, reasons=reasons)
            raise Refused(reasons)
        append(d, "vault_access_granted", task_id=a.task, item_id=a.item, role=t["assigned_role"])
    path = next((d / "vault").glob(f"{a.item}.*"), None) or (d / "vault" / a.item)
    return {"ok": True, "path": str(path), "logged": True}


def cmd_release_check(a):
    d = study_dir(a.study)
    man = json.loads((d / "release" / "manifest.json").read_text())
    changed = []
    for p in release_sources():
        rel = p.relative_to(ROOT).as_posix()
        if man["files"].get(rel) != sha256_file(p):
            changed.append(rel)
    changed += [r for r in man["files"] if not (ROOT / r).exists()]
    return {"frozen_release_id": man["release_id"], "live_release_id": compute_release_id(),
            "changed_since_freeze": changed,
            "note": "Active studies keep their frozen release; changes apply to studies initialized later."}


# ------------------------------------------------------------------------- cli

def build_parser():
    p = argparse.ArgumentParser(prog="controller.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="group", required=True)

    def add(group, name, fn, help_):
        if group not in groups:
            groups[group] = sub.add_parser(group).add_subparsers(dest="action", required=True)
        g = groups[group]
        sp = g.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        if not (group == "study" and name in ("init", "list", "use")):
            sp.add_argument("--study", help="study id (defaults to the current study)")
        return sp

    groups = {}
    s = add("study", "init", cmd_study_init, "create a study and freeze the current release")
    s.add_argument("--question", required=True)
    s.add_argument("--study-id")
    add("study", "list", cmd_study_list, "list studies")
    s = add("study", "use", cmd_study_use, "set the current study")
    s.add_argument("study_id")
    s = add("study", "close", cmd_study_close, "mark study completed/paused/aborted")
    s.add_argument("--status", choices=["active", "paused", "completed", "aborted"], required=True)
    s.add_argument("--note")
    sp = sub.add_parser("status", help="summary of the study state")
    sp.add_argument("--study")
    sp.set_defaults(fn=cmd_status)

    s = add("task", "propose", cmd_task_propose, "propose a task; the controller admits or refuses it")
    s.add_argument("--role", required=True, help="assigned role, e.g. R1")
    s.add_argument("--requester", default="LEAD")
    s.add_argument("--type", required=True, help="task type, e.g. literature_search, outcome_evaluation")
    s.add_argument("--objective", required=True)
    s.add_argument("--stage", required=True)
    s.add_argument("--case")
    s.add_argument("--split")
    s.add_argument("--model-bundle")
    s.add_argument("--inputs", help="comma-separated exact artifact ids")
    s.add_argument("--depends", help="comma-separated task ids")
    s.add_argument("--outputs", required=True, help="comma-separated permitted output schemas")
    s.add_argument("--worker")
    s.add_argument("--params", help="JSON object")
    s.add_argument("--criteria", action="append", help="scientific acceptance criterion (repeatable)")
    s.add_argument("--estimate")
    s.add_argument("--limit")
    s.add_argument("--stopping-rule", required=True)
    s.add_argument("--need")
    s.add_argument("--rationale")
    s.add_argument("--allow-unreviewed", metavar="REASON",
                   help="exploratory task may consume unreviewed inputs; give the reason")
    s = add("task", "start", cmd_task_start, "start an admitted task; prints the frozen skill path")
    s.add_argument("--task", required=True)
    s.add_argument("--instance", default="agent")
    s.add_argument("--retry", action="store_true")
    s = add("task", "log", cmd_task_log, "record progress (shown live in the dashboard)")
    s.add_argument("--task", required=True)
    s.add_argument("--msg", required=True)
    s = add("task", "finish", cmd_task_finish, "record execution status")
    s.add_argument("--task", required=True)
    s.add_argument("--status", choices=["succeeded", "failed", "abstained"], required=True)
    s.add_argument("--summary")
    s = add("task", "show", cmd_task_show, "show a task")
    s.add_argument("--task", required=True)

    s = add("artifact", "commit", cmd_artifact_commit, "commit a candidate artifact from a running task")
    s.add_argument("--task", required=True)
    s.add_argument("--schema", required=True)
    s.add_argument("--payload", required=True, help="path to JSON payload")
    s.add_argument("--title")
    s.add_argument("--consumed", help="actual consumed artifact ids (default: all task inputs)")
    s.add_argument("--evidence-kind", default="not_applicable", choices=schemas.EVIDENCE_KINDS)
    s.add_argument("--context", action="append", help="scientific_context key=value (repeatable)")
    s.add_argument("--case")
    s.add_argument("--cohort")
    s.add_argument("--session")
    s.add_argument("--tool")
    s.add_argument("--tool-version")
    s.add_argument("--code-commit")
    s.add_argument("--env-digest")
    s.add_argument("--supersedes")
    s.add_argument("--access", default="internal", choices=["internal", "reserved"])
    s.add_argument("--attach", action="append", help="extra payload file (repeatable)")
    s = add("artifact", "show", cmd_artifact_show, "show an artifact envelope (and payload)")
    s.add_argument("--artifact", required=True)
    s.add_argument("--payload", action="store_true")
    s = add("artifact", "list", cmd_artifact_list, "list artifacts")
    s.add_argument("--schema")

    s = add("gate", "record", cmd_gate_record, "record a gate verdict against a frozen criterion")
    s.add_argument("--artifact", required=True)
    s.add_argument("--criterion", required=True)
    s.add_argument("--verdict", choices=schemas.GATE_VERDICTS, required=True)
    s.add_argument("--evaluator", required=True)
    s.add_argument("--reason", required=True)
    s.add_argument("--need", help="need this artifact is a candidate fulfillment for")

    s = add("need", "open", cmd_need_open, "publish a scoped need")
    s.add_argument("--requester", required=True)
    s.add_argument("--missing", required=True)
    s.add_argument("--why", required=True)
    s.add_argument("--criterion", required=True)
    s.add_argument("--stage", required=True)
    s.add_argument("--case")
    s.add_argument("--target-role")
    s.add_argument("--access", default="internal")
    s = add("need", "claim", cmd_need_claim, "claim a need under a lease")
    s.add_argument("--need", required=True)
    s.add_argument("--role", required=True)
    s.add_argument("--minutes", type=int, default=60)
    s = add("need", "list", cmd_need_list, "list needs")
    s.add_argument("--all", action="store_true")

    s = add("repair", "issue", cmd_repair, "mark an artifact and its descendants stale and open a repair need")
    s.add_argument("--artifact", required=True)
    s.add_argument("--reason", required=True)
    s.add_argument("--stage", required=True)
    s.add_argument("--by", required=True)
    s.add_argument("--criterion")

    s = add("predictions", "freeze", cmd_predictions_freeze, "freeze predictions before outcome evaluation")
    s.add_argument("--artifacts", required=True)
    s.add_argument("--by", default="LEAD")
    s = add("vault", "seal", cmd_vault_seal, "seal a reserved outcome file")
    s.add_argument("--file", required=True)
    s.add_argument("--label", required=True)
    s = add("vault", "reveal", cmd_vault_reveal, "reveal a vault item to an outcome_evaluation task (audited)")
    s.add_argument("--task", required=True)
    s.add_argument("--item", required=True)

    add("release", "check", cmd_release_check, "compare live skills/profiles with the study's frozen release")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        out = args.fn(args)
        print(json.dumps(out, indent=2, ensure_ascii=True))
        return 0
    except Refused as e:
        print(json.dumps({"ok": False, "refused": True, "reasons": e.reasons}, indent=2, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
