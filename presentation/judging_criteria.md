# ScienceClaw hackathon: goals, judging criteria, and how our deck maps to them

Source: https://scienceclawhack.ai/ (Overview, Competition → Judging, FAQ), read on 2026-11-01 in the built-in browser.
The site links no separate rules or judging page; the rubric below is the one published on the main page.

## Event goals

- **Purpose:** explore when *decentralized collective intelligence* produces capabilities beyond a single agent or a
  conventional workflow. Collectives of specialised agents, models, simulations, sensors and lab tools that hold
  distinct knowledge, coordinate and adapt, and leave **traceable scientific artifacts, provenance, findings and unmet
  needs** the collective can build on, without one central planner prescribing the whole process.
- **Each project should demonstrate:** (1) **Problem**: difficult, open-ended, consequential; (2) **Functioning
  system**: a working agentic system, not a concept; (3) **Result**: what it actually accomplishes; (4) **Validation**:
  convincing evidence, benchmarks or real-world validation.
- "Science is the benchmark": success is a scientifically meaningful result supported by evidence, validation or
  measurable progress, not task completion.

## Tracks

One overall competition, no separate tracks. Challenge areas are entry points only:
A·01 Biology & Protein Design · A·02 Physical Agency · A·03 Manufacturing & Materials ·
**A·04 Open Scientific Challenge** (participant-defined problems). Our project fits A·04.

## Judging rubric (exact weights from the site)

| Criterion | Weight | What judges ask (from the site) |
|---|---|---|
| **C1 Problem Significance & Complexity** | 20% | How difficult, open-ended, consequential and scientifically meaningful is the problem? Does solving it meaningfully advance a scientific or technical goal? |
| **C2 Scientific/Technical Impact** | 25% | What was actually achieved? Is the result novel, meaningful, rigorous and potentially useful? |
| **C3 Decentralized Agency** | 20% | Are decision-making and capabilities meaningfully distributed across agents? Do agents have distinct information, resources or capabilities? Can they coordinate and adapt without a central planner prescribing the entire trajectory? |
| **C4 Collective Capability** | 25% | Does organizing agents collectively add measurable capability? Where possible, show a simple comparison: multi-agent vs single-agent, collaborative vs isolated, decentralized vs centralized. |
| **C5 Execution and Validation** | 10% | Is there a functioning system rather than a concept? Is its performance demonstrated with convincing evidence, benchmarks or real-world validation? |
| **Collaboration bonus** | up to +10 | Not part of the core score. Capabilities that materially strengthen other teams: a tool/agent reused by another team, data or experiments enabling another team's result, infrastructure that improves multiple systems, capabilities that propagate. |

Schedule constraint: hacking ends Sunday 1:00 PM (final slides due); presentations and judging 2:30 PM.

## Mapping: slides and demo segments → criteria

| # | Segment | Time | C1 | C2 | C3 | C4 | C5 | Bonus |
|---|---|---|:-:|:-:|:-:|:-:|:-:|:-:|
| S1 | Problem: drug-resistant epilepsy, surgery vs stimulation is a high-stakes, uncertain choice | 0:00–0:22 | ●● | | | | | |
| S2 | The collective: 7 roles with distinct tools/permissions, deterministic controller, ledger, gates, needs, sealed vault, frozen releases | 0:22–0:54 | | | ●● | ● | ● | ● |
| S3 | What the collective caught: 101 independent gate decisions, 14 not passed, 6 repairs, 3 refusals (collaborative vs producer-only proxy) | 0:54–1:19 | | ● | ● | ●● | ●● | |
| S4 | Study-001 results on real data: 32 source-checked claims, 10 curated real iEEG cases (SEEG + ECoG), pipeline independently found NOT qualified | 1:19–1:42 | | ●● | | ● | ●● | |
| S5 | Study-002: blinded virtual patient (ground truth sealed), interactive 3D cortex + SEEG + simulated seizure spread | 1:42–2:10 | ● | ●● | ● | | ● | |
| S6 | Study-002 before/after virtual treatment (exploratory, model not qualified) with every caveat on screen | 2:10–2:40 | | ●● | | | ●● | |
| S7 | Patient benefit, guardrails, next steps (qualify v3 → freeze → blinded vault evaluation; single- vs multi-agent run; share controller) | 2:40–3:00 | ●● | ● | | ● | | ●● |
| D1 | Demo: live dashboard for study-002 (Agents board, Timeline, Needs & gates, Artifacts, Skills editor) | ~30 s | | | ●● | ● | ●● | ● |
| D2 | Demo: study-001 HTML report (traceable figures, every number cites an artifact) | ~15 s | | ● | | ● | ●● | |
| D3 | Demo: before/after simulation + interactive 3D brain | ~20 s | ● | ●● | | | ● | |

●● = primary evidence for that criterion, ● = supporting.

## Honest gaps against the rubric

- **C4 needs a comparison.** We have not run a single-agent baseline on the same protocol. What we show is a
  *collaborative vs producer-only* proxy from the ledger: of 101 gate decisions in study-001, 14 did not pass an
  independent role's check (9 failed, 5 indeterminate). Without the gates, all 104 committed artifacts would have
  been accepted on the producer's word. A matched single-agent run is listed as next work (S7).
- **C3 has a lead role.** LEAD proposes tasks, but the controller (deterministic code) admits or refuses them against
  role profiles, gates are recorded by a role other than the producer, and agents post unmet needs that others claim.
  The trajectory adapted to evidence (study-001 skipped P4/P5 after R5 failed the model). It is not leaderless.
- **C2 for study-002 is exploratory.** The virtual-patient model is not qualified, the primary window had no baseline
  seizures, and the vault has not been opened, so no result is checked against ground truth yet.
- **Bonus:** nothing has been reused by another team yet. The controller, schemas and skills are reusable; S7 offers them.
