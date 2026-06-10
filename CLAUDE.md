# NetHELM — Claude Code Context

## The objective

**Build and publish NetHELM**: a holistic benchmark for LLMs and AI agents on
network-engineering tasks, whose primary novel contribution is a **safety /
blast-radius axis** — given a proposed config diff, score precision/recall against
the set of BGP sessions, prefixes, interfaces, routes, waypoints, redundancy,
filters, and scale limits that an oracle (Batfish + emulation) predicts will be
lost or degraded.

Target: a citable publication (workshop / HotNets / NAIC@SIGCOMM minimum; arXiv
preprint + open repo + HF dataset at absolute minimum), with the full NetHELM
comparative framing (importing NetConfEval, Cornetto, NIKA, TeleQnA/NetEval) as the
v2/extension.

### Execution order (decided 2026-06-08)

1. **Finish the blast-radius axis end-to-end, first.** Sims, dockers, router
   configs, Batfish oracles, scenario catalog, question base (target **200–400**
   validated scenarios), full multi-model + multi-sample sweep, grader-validity
   (κ ≥ 0.7), figures, repo, paper. This is the durable novelty and it is already
   ~60% built. Ship this as the first paper.
2. **Then grow it into full NetHELM** — the harness is architected so importing the
   other benchmarks is configuration, not a rewrite. We own the whole NetHELM
   vision; we just ship its strongest part first.

The full reasoning, blockers, and the locked decisions live in
`temporary/full_nethelm_feasibility_and_blockers.md`. Read it once.

---

## The engineer fleet (how we work now)

NetHELM is built by a **fleet of specialist agents** that argue, criticize, and
revise each other's work. They run as **Claude Code subagents** (`.claude/agents/`)
under the Max-plan subscription — *not* the metered API. Spawn them with the
`Agent` tool. **Aggression and bluntness are encouraged**: soft review produces
weak benchmarks. Agents must tear into each other's work, name specific flaws, and
demand fixes. No politeness tax.

**Stay-current mandate (all agents):** the field moves weekly — every agent
web-researches (WebSearch/WebFetch) to confirm version/feature-sensitive knowledge
before acting (RFC/draft status, vendor syntax, model/API features, eval norms, tool
releases). Never rely on training-cutoff memory for anything that changes; cite
findings; route durable updates to the KB (`knowledge/corpus/`, noc-veteran curates).

| Subagent | Role | Drives / Gates |
|---|---|---|
| **noc-veteran** | 15-yr NRE. Questions EVERYTHING. Is this scenario real, necessary, or nonsense? Grounds every scenario in real outages (KB `noc/`). Web-researches freely. | **Drives the project.** Nothing enters the question base without surviving the veteran. |
| **industry-expert** | Networking standards authority. Ensures every config, protocol claim, and method reflects *current* RFCs, vendor syntax, and modern practice (SR, EVPN/VXLAN, RPKI, current LLM-eval norms). Web-researches latest. | Gates staleness and incorrectness. |
| **scenario-author** | Designs blast-radius scenarios: pre/post config diffs + claimed D1–D8 ground truth. | Produces the raw material; expects it to be torn apart. |
| **batfish-oracle-engineer** | Owns gradeability. Can Batfish/emulation actually compute the claimed ground truth? Knows Batfish modeling limits cold. | Rejects ungradeable scenarios or specifies the vendor-config workaround. |
| **sim-builder** | Containerlab/FRR/vendor topologies, Docker launch/clean, deterministic addressing, reproducibility. | Makes scenarios real and re-runnable. |
| **research-standards-reviewer** | Publication bar: N≥5 samples, κ, citations, novelty vs NetPress/NetConfBench, reproducibility. | Gates anything paper-bound. |
| **red-team-critic** | Pure adversary. Breaks everything. Rude on purpose. | Last line before "done." |
| **network-architect** | Routing-DESIGN authority (CCIE-Design level). Is a config CORRECT, IDIOMATIC, and convergent as intended — not just running? Owns the control plane at design level. | **Gates design-correctness** of ground-truth configs AND model config synthesis. |
| **ml-eval-engineer** | Owns the ML half: prompting / function-calling, model-API integration, metric design, sampling/stats, contamination, fine-tuning — makes the eval trustworthy. | Gates HOW models are run + HOW results are measured. |
| **netdevops-engineer** | The bridge: FRR/Containerlab/Kathará, config templating + **parameterized generators** (Plan-C scale), intent-based networking, imported-benchmark wiring. | Highest-leverage builder; turns a class into many verified instances. |
| **backend-engineer** | Harness solidity: scoring pipeline, run storage, reproducibility (pins/lockfiles/snapshots), CI, data handling, packaging. | Keeps the machinery correct, green, one-command reproducible. |
| **formal-verification-engineer** | OPTIONAL rigor: is the oracle ground truth PROVABLY sound? verification-based graders; formal-spec translation (NetConfEval). | Used for rigor-critical / research-grade correctness claims. |

**The loop (non-negotiable):** scenario-author proposes → noc-veteran asks "is this
even necessary / real?" → network-architect checks the design is correct + idiomatic
→ batfish-oracle-engineer confirms gradeability → industry-expert checks currency →
red-team-critic tries to break it → research-standards-reviewer checks it'll survive
review. The **ml-eval-engineer + backend-engineer** own the run/measure/reproduce
machinery; the **netdevops-engineer** builds the parameterized generators that scale
the question base; the **formal-verification-engineer** is pulled in for
correctness-rigor work. **Periodically convene the noc-veteran** to question whether
the scenarios are required, sensible, or nonsense — it web-researches to settle it.

**Smallest viable team** (per the team plan): network-architect + netdevops-engineer
(architect/automation hybrid) + ml-eval-engineer, with the noc-veteran as domain SME
+ ground-truth reviewer. That trio + SME covers most of the work.

**Review skills (multi-agent):** `/critique` (3-way peer review), `/accuracy-check`
(2-agent fact check), `/scenario-gate` (full gauntlet), `/design-review`
(architect-led config correctness/idiomaticity), `/eval-review` (ml-eval + standards
on methodology), `/lit-scan` (scoop watch).

There are also two **headless API equivalents** (`agents/validity_agent.py`,
`agents/research_agent.py`, run via `./validate-scenario` / `./research-check`) for
CI/batch use — but these are **metered API spend**; prefer the Max-plan subagents
for interactive development.

---

## Autonomy & budget (decided 2026-06-08)

- **Run free on this machine.** The entire VM (96 GB RAM, 2 TB disk, all CPU)
  belongs to this project. Launch/clean Docker, build sims, run Batfish, write
  files, run pytest, query the KB — **do not ask permission for routine local
  actions.** Permissions are pre-granted (`.claude/settings*.json`).
- **Paid model-under-test budget: $1000 approved.** Run paid evals (OpenAI /
  Gemini / Anthropic API for models-under-test, RunPod GPUs for local models)
  freely within this budget. **Log the cost of every paid run in its run manifest.**
  Flag a check-in when cumulative spend crosses each **$250** mark. Still do a
  `--limit 1` single-call sanity check before any large sweep.
- **Still ask before:** `git commit` / `push`; any single run plausibly > $250;
  anything that leaves this machine or is hard to reverse.

---

## Cisco DNM / data-release (revised strategy 2026-06-08)

**Do NOT file the data-release ticket yet.** Work politics: nobody supports what
they can't see. The sequence is **build the working blast-radius demo first**, then
approach coworkers / staff / leaders with concrete examples ("this is what we built,
this is what it shows, this is the support we need"). The KB and the running demo
are the artifacts that make that case. DNM access is the only true moat, but it is
earned *after* there is something to show, not before.

---

## Current status (as of 2026-06-08)

**Branch:** `brainstorming-session` (PR #1, not yet merged to main).

**Built + tested (~3,500 LOC, 91 unit tests green):**
- v0 safety axis (D1–D3): generator → suite → **live Batfish oracle** → eval →
  grade → report. Verified end-to-end on the 4-node FRR square lab.
- Multi-dimensional extension (D4–D8): built; **D4/D5/D7 oracle-backed** on
  waypoint, ECMP, and blackhole topologies. Unified oracle computes all declared
  dimensions on one pre/post snapshot pair.
- Real model runs (Claude Haiku 4.5, single calls) already demonstrate the thesis:
  a session-only grader scores a blackhole change a perfect pass while the model
  misses the second-order control-plane damage.
- 20-scenario catalog, local FAISS knowledge base (39 corpus files), full docs.

**Remaining for the blast-radius paper** (see `HANDOFF.md` for the priority list):
D6 (filter) oracle [needs a vendor config dialect], D8 (scale) oracle, the
200–400-scenario question base, multi-sample × model-fleet sweep, κ labelling,
optional live-emulator hybrids, merge PR #1.

---

## Task taxonomy

Blast-radius axis is 8-dimensional. **D = the blast-radius dimensions**, scored by
precision/recall over the affected set:

| Dim | What it scores | Oracle status |
|---|---|---|
| D1 | BGP/IGP sessions lost | ✅ live |
| D2 | Prefixes lost/withdrawn | ✅ live |
| D3 | Interfaces down | ✅ live |
| D4 | Waypoint / path-policy violations | ✅ live |
| D5 | Redundancy / ECMP loss | ✅ live |
| D6 | Filter (ACL) transitions permit↔deny | ⛔ needs vendor config (Batfish won't model FRR ACLs as packet filters) |
| D7 | Forwarding anomaly (blackhole/loop) | ✅ live |
| D8 | Scale / resource limit (FIB/RIB/TCAM) overflow | ⛔ needs per-device resource budgets |

Full-NetHELM categories (v2, imported): K (TeleQnA/NetEval MCQ), C (NetConfEval +
NetConfBench), R (Cornetto 231 repair), Diagnosis (NIKA). Architect for these now;
build them later.

---

## Lab environment

**Host**: Ubuntu 24.x, kernel 7.0.0-15-generic, 96 GB RAM, 2 TB disk — fully
dedicated to this project.

**Installed and verified:**
- Docker 29.5.2, Containerlab 0.75.0
- FRR-square iBGP: `harness/lab/frr_square.clab.yml` (4 nodes, 12 ESTABLISHED)
- Batfish `batfish/allinone:nethelm` (pinned `sha256:09817554db90…`) — ports 9996/9997.
  All ground truth is computed against this digest. Determinism gate:
  `scripts/verify_determinism.py` (11/11 scenarios ≥10× byte-identical).
- venv: `harness/venvs/nethelm/` (`pip install -e ".[oracle,knowledge,eval,report,dev]"`) — the canonical venv (has pydantic + pybatfish)
- NetConfEval: `external/netconfeval/` (cloned; analysis in `reading/`)

**Vendor images** (see `docs/vendor_images.md` for what to grab and why): Arista
cEOS-lab is the one image worth acquiring now (unblocks D6 filter + a 2nd vendor;
free with an arista.com account). Everything else defers.

---

## Tools

| Tool | What | Cost |
|---|---|---|
| `./kb "query" [--top N] [--source rfcs\|batfish\|noc\|vendor\|papers]` | Query the local FAISS knowledge base | **Free** (local embeddings) |
| `python -m knowledge.tools.build_index` | Rebuild the KB after adding corpus files | Free |
| `netbrace ...` (`safety generate\|validate\|oracle`, `eval fake\|run`, `grade`, `report`) | The benchmark CLI | Free unless `eval run` hits paid models |
| `./validate-scenario` / `./research-check` | Headless API agents (NOC veteran / standards reviewer) | **Metered API** — prefer subagents |
| `python -m pytest tests/unit -q` | Must stay green (91+) | Free |

**MCP servers:** none required for the build phase. Planned for the measurement
phase: `Juniper/junos-mcp-server` as the commercial-agent baseline (runs against
cRPD/vSRX). Add it to `.mcp.json` when we reach the agent-baseline experiments;
do not add it speculatively.

---

## Accuracy requirements

**This is research. Peer review is adversarial. Accuracy is non-negotiable.**

- Every protocol claim → verified against RFC or vendor docs (use `kb` + web).
- Every experimental number → traceable to committed code + saved outputs, N≥5
  samples, mean ± std, pinned model version, logged cost.
- Every citation → verified to exist and say what is claimed.
- Grader validity → human-labeled subset, Cohen's κ ≥ 0.7, before any number ships.
- When unsure → test it in the lab or find the RFC section.

Use the fleet for this: `/critique` (3-agent peer review), `/accuracy-check`
(2-agent fact verification), `/lit-scan` (novelty/scoop monitoring). Convene the
noc-veteran to question scenario necessity. No paper-bound artifact is "final"
until the standards-reviewer and red-team-critic have both had a pass.

---

## Model fleet (for the sweep)

**Cloud**: GPT-4o, GPT-4o-mini, Claude Sonnet/Opus (latest), Gemini 2.x Pro.
**Local** (RunPod/vLLM): Llama-3.1-70B, Qwen-2.5-32B.
**Commercial agent**: `junos-mcp-server` + cRPD (measurement phase).
Always include the strongest closed model as the topline; always pin versions.

---

## Repository layout

```
NetHELM/
├── CLAUDE.md                  ← this file
├── HANDOFF.md                 ← resume point: what's built/frozen/remaining
├── progress.md                ← running log (update as work lands)
├── netbrace/                  ← the package (legacy name; project = NetHELM)
│   ├── core/  graders/  batfish/  evals/  tasks/safety/  topology/
│   ├── models/  reporting/  storage/  routers/  cli.py
├── agents/                    ← headless API agents (validity/research) + KB glue
├── knowledge/                 ← local FAISS KB (corpus/ index/ tools/)
├── .claude/agents/            ← the Max-plan engineer fleet (subagents)
├── .claude/skills/            ← /critique /accuracy-check /lit-scan etc.
├── harness/lab/               ← containerlab topologies + venvs (gitignored)
├── external/netconfeval/      ← cloned import target (v2)
├── docs/                      ← runbooks + authoring guides + vendor_images.md
├── paper/refs/                ← landscape table + scenario catalog
├── reading/                   ← paper reading notes
├── runs/                      ← experiment outputs (gitignored)
├── tasks/safety/              ← committed task suites + sprint plans
└── temporary/                 ← planning docs (NOT committed to main; private goal lives here only)
```

---

## Hard rules (do not break)

1. **Never edit the frozen v0 core.** Add new modules; keep `pytest tests/unit -q`
   green (91+) after every change. (Details in `HANDOFF.md`.)
2. **Reuse schemas / jsonio helpers.** Never hand-roll JSON for a model.
3. **One command, one artifact** — every CLI/script prints the path it wrote.
4. **No single number from a single sample.** Stochastic models → N≥5.
5. **The unified `ExtendedOracle.compute(scenario)` is the source of truth**, not
   the per-dimension demo helpers.
6. **The private end-goal behind this project is recorded ONLY in `temporary/` and
   in Claude's memory — never anywhere else in the codebase.**
