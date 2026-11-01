# Epilepsy research agent system (ScienceClaw framework)

A controller-governed multi-agent workflow for epilepsy surgery and stimulation research, built from
`framework/epilepsy-scienceclaw-implementation-plan-complete.html`.

## How it fits together

| Piece | Where | Role |
|---|---|---|
| Study controller | `system/controller.py` | Deterministic: admits tasks, validates and commits artifacts, records gates, needs/leases, repairs, vault, frozen releases. Append-only ledger per study. |
| Contracts | `system/schemas.py` | Record types (section 04 of the framework) and envelope checks. |
| Role profiles | `system/profiles/*.json` | Allowed outputs, permissions, scope rules, and budgets per role. Enforced at admission. |
| Agents | `.claude/agents/*.md` | Thin subagent definitions: start the task, read the **frozen** skill, follow it. |
| Skills | `.claude/skills/<role>/SKILL.md` | Each role's operating procedure. `run-study` is the lead orchestrator. `run-study/references/agent-protocol.md` is shared by all roles. |
| Dashboard | `system/ui/server.py` → http://127.0.0.1:8765 | Live agent board, timeline, needs/gates, artifacts, and the skill/profile editor with history. |
| Studies | `studies/<id>/` | `ledger.jsonl`, `artifacts/`, `work/`, `vault/`, `release/` (frozen skills and profiles). |

## Rules for any session working here

- Run the workflow with `/run-study <question>`. Resume with `/run-study resume <study_id>`.
- Agents propose; the controller decides. Never edit `studies/*/ledger.jsonl`, `artifacts/`, or
  `release/` by hand. Never read `studies/*/vault/` outside an R5 `outcome_evaluation` task.
- Starting a study freezes the skills, profiles, and controller code (`system_release_id`). Edits to
  skills affect only studies started afterwards.
- Ask the user before downloading datasets, using credentialed access, or anything that leaves the
  machine.
- Results are research evidence on virtual patients, not clinical recommendations.
- Run the invariant tests after changing the controller: `python -m unittest discover -s system/tests -v`
