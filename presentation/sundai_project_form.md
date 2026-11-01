# Sundai project form: draft text (Ayna)

Drafted from `presentation/slides.html` and the study records. Every number traces to a ledger or artifact.
Edit freely before saving. Field names are guesses until the edit form is visible after login.

## Title
Ayna

## Short description / tagline (≤ 150 chars)
A governed AI-agent collective that tests epilepsy surgery vs stimulation on virtual-brain twins, and says "not qualified" when it should.

## Full description

About 1 in 3 people with epilepsy keep having seizures despite medication. For them the choice is surgery, which can
stop seizures if the right tissue is found, or neurostimulation, which is safer but rarely stops them. No one can try
both on the same patient. Ayna asks whether a collective of AI agents can build and test virtual-brain twins for this
choice rigorously enough to trust what it says, and what it refuses to say.

**How it works.** Seven roles, each a Claude subagent with its own skill, tools, permissions and budget: R1 evidence
scout, R2 case curation, R3 virtual patient, R4 intervention design, R5 independent evaluation, RV clinical and
engineering review, and a lead that proposes work. Agents propose; a deterministic controller decides. It admits or
refuses each task against the role's profile, validates every artifact, accepts a gate only from a role other than
the producer, and writes everything to an append-only ledger. Ground truth is sealed in a vault that only the
evaluator can open, skills are frozen when a study starts, and agents post unmet needs for others to claim. A live
dashboard shows the agent board, timeline, needs and gates, artifacts, and an editable skill library.

**Study-001 (real data, 6 hours).** 32 source-checked literature claims; 10 intracranial-EEG patients curated from
OpenNeuro ds004100 without looking at outcomes; and an independent finding that the published Wang 2025 inversion
pipeline was not qualified (no convergence, planted focus top-ranked in only 29% of draws, 4 code defects). The system
stopped there: no simulations, no predictions, and the outcome vault stayed sealed. Across the study, other roles
recorded 101 gate decisions on agents' work; 14 did not pass, leading to 6 repair cycles, and the controller refused
3 mis-wired tasks.

**Study-002 (in progress, exploratory).** Uses Wang et al. 2025 virtual-brain-twin data. The ground truth for virtual
Patient 2 was sealed before any model was fitted. In exploratory simulations on a model that is not yet qualified,
removing the estimated epileptogenic + propagation zone cut seizing regions by a median of 3 and stopped all simulated
seizures in 5 of 12 fits, while the recorded SEEG pulse-train stimulation changed nothing. The caveats are recorded:
the primary window had no baseline seizures, the simulated baseline did not match the recording, and nothing has been
compared with the sealed truth yet. A faster v3 model is being qualified.

**Next.** Qualify v3, freeze predictions, and run a blinded vault evaluation; map the TI stimulation field onto the
patient; run the same protocol with a single agent to measure what the collective adds; share the controller and
skills with other teams.

Research evidence on virtual patients, not clinical recommendations.

## Tags (suggested)
Tech: Claude, multi-agent, Python, Stan, The Virtual Brain, WebGL
Domain: neuroscience, epilepsy, healthcare, AI for science

## Links
- Demo / slides: (local files `presentation/slides.html`, `presentation/demo/index.html`; no public URL yet)
- GitHub: (none known; add if you have one)

## Event
ScienceClaw hackathon, MIT Media Lab, Oct 30 – Nov 1, 2026 (A·04 open scientific challenge)
