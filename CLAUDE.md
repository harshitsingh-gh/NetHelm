# NetHELM — Claude Code Context

## The real objective

**Publish a quality paper** at a respected ML or networking venue (NeurIPS/ICLR/ICML workshop, HotNets, NAIC@SIGCOMM, or equivalent). The paper is a credential, not an end in itself. It needs to be co-authored with an academic where possible — that is 10× more valuable than solo authorship for the intended downstream purpose.

**We are not married to NetHELM.** NetHELM is the current best vehicle. If a faster, cleaner, or more novel angle emerges — from the literature, from a collaborator, from a course project — we pivot. Velocity and quality are both paramount. Many papers are published daily; staying current on the landscape is an active responsibility.

**Hard deadline**: A submission must be in by **mid-2027** at the latest (targeting first available workshop cycle). Everything before that is build time.

---

## What NetHELM is (the current vehicle)

**NetHELM** evaluates LLMs and AI agents on network-engineering tasks. The HELM-style comparative framing imports existing benchmarks (NetConfEval, Cornetto, NIKA, TeleQnA/NetEval) into a unified harness, and introduces a novel **safety / blast-radius** axis: given a proposed config diff, score precision/recall vs. the set of BGP sessions, prefixes, interfaces, and services Batfish predicts will be lost.

Thesis: *"NetHELM: holistic comparative evaluation of LLMs and commercial network agents on network-engineering tasks, with a safety/blast-radius axis no prior benchmark scores."*

**Why it still makes sense as the vehicle:**
- Safety/blast-radius angle has no direct competitor yet (as of last check — verify with `/lit-scan`)
- Lab is already up (containerlab, FRR, Batfish)
- NetConfEval is already cloned and venv built
- Maps cleanly to the SOP thesis: "reliable tool-using AI agents for high-assurance infrastructure"
- Industry moat: potential Cisco DNM baseline no academic can replicate

**When to consider pivoting:**
- A competitor paper ships the safety axis before we publish
- A cleaner, faster paper opportunity surfaces from the literature scan
- A Stanford-connected collaborator has a better idea and will co-author

---

## Pivot options on the table (keep scanning for more)

| Option | Velocity | Novelty | LOR/collab potential | Notes |
|---|---|---|---|---|
| **NetHELM safety-axis only** (strip the harness; just blast-radius + GPT-4o baseline) | Fast (2–3 mo) | High | Medium | Smallest possible paper that still has novelty. HotNets target. |
| **NetHELM full v1** | Slow (6–9 mo) | Medium (comparative framing) | High (imports others' work) | Original plan. Worth it if collab lands. |
| **CS224N/CS229 final project → paper** | Medium (starts Wi'27) | Variable | Very high (Stanford co-author path) | Best for LOR. But 8+ months away. |
| **Measurement paper: "LLMs fail at network change safety"** | Fast (2–3 mo) | High if first | Low | arXiv first, then extend. No harness needed, just Batfish + GPT-4o. |
| **OSS project → blog → citation target** | Very fast | None | None | Builds visibility, not a paper substitute |

---

## Current status (as of Jun 2026)

**Phase**: 1 — Summer co-effort (Jun 1 – Aug 23, 2026)  
**Current week**: Week 2 (Jun 1–7) — Reproduce NetConfEval  
**Hard constraint**: Math refresher (10 hrs/wk) runs in parallel Jun–Aug; this is non-negotiable. NetHELM gets the other 10–12 hrs/wk.

**Sep 20, 2026** is the last day for all build/experiment work before CS221 starts and eating into velocity.

**Completed:**
- FRR-square iBGP lab verified (4 nodes, 12 ESTABLISHED sessions)
- Batfish running, frr_square snapshot parses
- NetConfEval cloned + venv built

---

## The application picture (informs everything)

Target: **Stanford CS MS via HCP**, Autumn 2028, deadline ~Dec 2, 2027.

Three artifacts needed by Nov 2027:
1. **This paper** — workshop accept OR arXiv preprint with repo. Co-authored with Stanford person = 10× multiplier.
2. **OSS project** — generalized, public version of agentic orchestration work. GitHub-visible, quality README.
3. **Public talk** — PyData / MLSys / RAGOps / NANOG / any external technical venue.

Course path: CS221 (Au'26) → CS224N (Wi'27) → CS229 (Sp'27) → CS238/CS336 (Au'27, in-progress at submission).

Academic LOR path: CS224N or CS229 final project → build relationship with instructor/head TA → ask for LOR after grades post.

The paper co-authorship and the LOR are the same goal — find a Stanford-adjacent academic during CS224N/CS229, do excellent final project work that intersects their research, build from there. **NetHELM importing a prior benchmark (Cornetto, NIKA) is the cold-email opener — "I already ran your benchmark inside my harness."**

---

## Repository layout

```
NetHelm/
├── CLAUDE.md                       ← this file
├── README.md
├── progress.md                     ← weekly log (update weekly — this is also LOR/SOP material)
├── paper/
│   ├── refs/
│   │   ├── networking_llm_benchmark_paper_plan.md  ← landscape + strategy
│   │   ├── nethelm_execution_plan.md               ← week-by-week plan
│   │   └── landscape_table.md                      ← related work table
├── reading/                        ← paper reading notes
├── harness/
│   ├── lab/                        ← containerlab topologies
│   │   ├── frr_square.clab.yml     ← verified iBGP topology
│   ├── venvs/                      ← Python venvs (gitignored)
│   │   ├── batfish/
│   │   └── netconfeval/
│   └── grader_notes/
├── external/
│   └── netconfeval/                ← RedHatResearch/conext24-NetConfEval
├── runs/                           ← experiment outputs
│   └── 2026-05-27_batfish_frrsq/   ← Batfish baseline
├── tasks/                          ← sprint plans
└── temporary/                      ← planning docs (not committed to main)
```

---

## Task taxonomy (NetHELM v1 — current scope)

| Category | Label | Source | Grader | Status |
|---|---|---|---|---|
| Knowledge / Q&A | K | TeleQnA + NetEval | Exact-match MCQ | Import |
| Config synthesis | C | NetConfBench + NetConfEval | Batfish behavioral equiv | Reproducing (Wk 2–3) |
| Behavior prediction | B | Batfish-templated (~500) | RIB/FIB equality | Build (Wk 10) |
| Diagnosis from show | D | NIKA subset | Root-cause label match | Import (Wk 6) |
| Config repair | R | Cornetto 231 problems | Formal verification | Import (Wk 3) |
| **Safety / blast-radius** | **S** | **Novel — Batfish-derived (~300)** | **Precision/Recall over {sessions,prefixes,interfaces,services}** | **Build (Wks 8–9) — PRIMARY NOVELTY** |

**If velocity demands it:** ship Safety axis only (category S + 1–2 imported baselines) as a short paper. Everything else is extensible.

---

## Lab environment

**Host**: `hungrykirby` — Ubuntu 24.x, kernel 7.0.0-15-generic, 96 GB RAM, 2 TB disk.

**Installed and verified:**
- Docker 29.5.2, Containerlab 0.75.0
- FRR-square iBGP: `harness/lab/frr_square.clab.yml`
- Batfish `batfish/allinone:nethelm` — ports 9996/9997
- pybatfish venv: `harness/venvs/batfish/`
- NetConfEval: `external/netconfeval/`, venv at `harness/venvs/netconfeval/`

---

## Key external repos + papers

| Resource | Location | Role |
|---|---|---|
| NetConfEval | `external/netconfeval/` (cloned) | Primary reproduce target (Wk 2) |
| NetConfBench IETF draft | `draft_llm_conf_benchmark/` | Citation only |
| Cornetto (ETH NSG) | Check GitHub by Jun 8 | Config-repair grader (Wk 3); cold-email opener |
| NIKA | arXiv:2512.16381 | Troubleshooting import; cold-email opener |
| NetPress | arXiv:2506.03231 | Prior art for safety axis |
| Batfish | docker `batfish/allinone:nethelm` | Core grading oracle |
| junos-mcp-server | GitHub: Juniper/junos-mcp-server | Commercial-agent baseline |
| TeleQnA | HF: netop-team/TeleQnA | MCQ import |
| NetEval | HF: NASP/neteval-exam | MCQ import |

---

## Open-source velocity tools (check and use)

Evaluate these for replacing custom harness code. The goal is to ship a paper, not to build a framework:
- **lm-evaluation-harness** (EleutherAI) — does it have a task-plugin API for custom tool-use tasks?
- **inspect-ai** (UK AISI) — Python-native eval framework with agent support; check if it supports containerlab-backed tasks
- **Evals** (OpenAI) — check if extensible enough for agentic networking tasks
- **LangChain/LangSmith tracing** — for logging model runs without building custom storage
- **Batfish** itself as the CI-equivalent grader — already integrated

If any of these can replace `harness/runner.py` + `harness/storage.py` from the execution plan (Wk 4), use them. Don't build what exists.

---

## Accuracy requirements

**This is research. Peer-review is adversarial. Accuracy is non-negotiable.**

- Every networking protocol claim → verified against RFC or vendor docs
- Every experimental number → traceable to committed code + saved outputs
- Every citation → verified to exist and say what is claimed
- Grader validity → 100-task human-labeled subset, Cohen's κ ≥ 0.7
- When unsure → test it in the lab or find the RFC section

Run `/critique` on every paper section before it is considered final. Two independent sub-agents minimum.

---

## Model fleet (v1 targets)

**Cloud**: GPT-4o, Claude Sonnet/Opus (latest), Gemini 2.x Pro, GPT-4o-mini  
**Local (Wk 12)**: Llama-3.1-70B, Qwen-2.5-32B via vLLM on RunPod  
**Commercial agent**: `junos-mcp-server` + cRPD  
**Cisco DNM**: conditional on data-release (parallel track)

---

## Collaboration targets (cold-email opener: "I already ran your benchmark in my harness")

1. Laurent Vanbever, ETH Zürich — Cornetto author
2. Jianping Cui, Tsinghua — NetConfBench IETF draft author
3. Stanford CRFM adjacent — Percy Liang group, Tatsunori Hashimoto group
4. KTH SEMLA — NetConfEval authors (already running their code)
5. **CS224N/CS229 head TA or instructor** — this is the LOR path, not just a paper collab

**Strategy**: cold email only after working demo that imports their benchmark. Not before.

---

## Permissions

Full playground. Claude may freely: modify files, run Docker, containerlab, Python/pip, git, web requests, API calls. Ask before committing/pushing. Ask before API runs > $10.
