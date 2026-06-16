# NetBrace Landscape Table
> Last updated: 2026-06-10 (citation-currency pass per inclusion-debate verdict)

## Primary benchmarks (import or position against)

| Benchmark | Venue / Year | What it tests | NetBrace relationship | Gap remaining |
|---|---|---|---|---|
| **NetConfBench** (Cui et al., IETF **draft-cui-nmrg-llm-benchmark-01**, 2025-12-30, expires 2026-07-03) | IRTF NMRG, 2025 | IETF **framework/definitions** draft (not a runnable competing benchmark): worked example is a **2-node** line (NewYork–Washington); scores **intent achievement + functional correctness**; ANI primitives; ReAct/RAG agents. **Explicitly does NOT score change-safety / blast radius / disruption impact.** | Import task taxonomy; citation only (no code). Its 2-node example + no-blast-radius scope is itself a differentiator sentence for NetHELM | No blast-radius/false-positive-penalized damage metric; toy-scale example |
| **NetConfEval** (Marouf et al., **CoNEXT 2024; ACM ToN DOI 10.1145/3656296**; repo `RedHatResearch/conext24-NetConfEval`) | CoNEXT 2024 (KTH + Red Hat) | NL intent → formal spec → Python routing code; 3 steps; Kathará FRR runtime grader. **NOT re-versioned** — the "newer draft" in 2025–26 discourse is NetConfBench-01 above, a separate IETF artifact; do not conflate. | **Primary reproduce/import target (v2)** — KTH authors = cold-email target | Routing-policy / config-synthesis focused; no config-change impact prediction |
| **CORNETTO** (Protogeros, Asadli, Hoffman, Vanbever — **arXiv:2604.22513**; PDF-verified 2026-06-12 via 2606.06212 which evaluates ON it) | ETH NSG, 2026 | Config repair at scale; 231 scenarios; Topology Zoo, ≤754 nodes / 200K config lines; 27 fault types; Fix Score (efficacy) + **Regression score (their "safety" = specs an APPLIED fix breaks, computed BY the verifier)** | Import repair category; **cold-email opener to Vanbever group**. Differentiator: they score verifier-checked repair; we score the MODEL'S OWN damage foresight | No pre-change typed-damage prediction; verifier is teammate, not referee |
| **NetPress / NetArena** (Microsoft + UMD) — SAME paper, retitled NetPress→NetArena; cite ONCE | arXiv:2506.03231, 2025 | Dynamic agentic benchmark (route/ACL-MALT/k8s); >10k queries; correctness + **safety (execution action-safety, binary rule-adherence)** + latency | Closest prior "safety" axis — but it's *agent action-safety in an emulator*, NOT typed-damage-set prediction from a diff | Does NOT score *predicted/hallucinated* damage (precision/false-alarm) — NetHELM's moat |
| **NIKA** (arXiv:2512.16381 — cite by ID, NOT by "Arena"; a *second*, distinct arena-titled paper from NetArena 2506.03231) | arXiv:2512.16381, 2025 | Troubleshooting/RCA arena; incidents on dynamic emulated networks. Future work names **Batfish-validated remediation prediction** — the closest scoop neighbor (different axis: diagnosis, not pre-change damage). | Import troubleshooting subset (v2); defend by shipping first | Troubleshooting/RCA-only; no config-change blast-radius |
| **NetAgentBench** (Twabi et al.) | arXiv:2604.09678, **April 2026** ⚠️ NEW | FSM-formalized dynamic benchmark; multi-turn config tasks; 300 benchmark runs; 21–39% "exploration meltdown" rate | **Competitor for config-eval framing** — does NOT cover safety/blast-radius; cite as related work | No pre-change impact prediction; correctness-only grader |
| **TeleQnA** (Huawei NetOp) | arXiv:2310.15051, 2023 | 10k MCQs; 5G/3GPP standards; telecom knowledge | Import MCQ category | 3GPP-biased; not enterprise routing |
| **NetEval** (NASP) | arXiv:2309.05557, 2023 | ~5.7k MCQs; NetOps; multilingual | Import MCQ category | Pure recall, no execution |

## Adjacent work (cite but don't import)

| Paper | Venue | Relevance | How to position |
|---|---|---|---|
| **BGPShield** (arXiv:2511.14467) | 2025 | LLM-based BGP *anomaly detection* (routing hijacks, misconfigs) | Different goal: detection on live traffic, not pre-change impact prediction |
| **NetLLM** (SIGCOMM 2024) | SIGCOMM 2024 | RL-style networking tasks (video streaming, job scheduling) | Different domain; not config management |
| HELM (Liang et al.) | ICML 2022 (TMLR) | Holistic LLM evaluation methodology — **the template** | Cite as methodology ancestor; note: HELM entered maintenance mode June 1, 2026 |
| LLMs for Networking survey | arXiv:2404.12901 | Canonical survey; cite in intro | Background citation |
| LLM Agent Eval survey | arXiv:2507.21504 | KDD 2025 tutorial; benchmark methodology reference | Methodology citation |

## What is genuinely novel about the safety/blast-radius axis

**No paper has formalized or benchmarked an LLM's ability to predict the topological impact of a proposed network configuration change BEFORE it is applied.**

Specifically: given a proposed config diff, which BGP sessions will go down? Which prefixes become unreachable? Which interfaces will be affected? Which downstream services will be degraded?

- NetAgentBench, NetConfBench, NetConfEval: evaluate *correctness* of generated configs (does it match intent?) but do NOT model downstream topological impact
- NetPress: closest prior art — per-application safety check — but not a generalized framework
- BGPShield: detects anomalies in live routing behavior — not pre-change prediction
- The "blast radius" term in 2025–26 literature refers to LLM agent containment (prompt injection blast radius) — distinct from network-change blast radius

**This gap is confirmed open as of June 2026.** It is the primary novelty claim. Protect it.

## Upcoming submission deadlines

| Venue | Deadline | Format | Fit |
|---|---|---|---|
| **HotNets 2026** | **July 16, 2026** ⚠️ 6 WEEKS AWAY | Position paper, ~6 pages | HIGH — networking audience, position paper format perfect for early-stage safety framing |
| NeurIPS 2026 workshops | **Aug 29, 2026** (if workshop accepted Jul 11) | 4–8 pages | HIGH — LLM eval/agentic workshops expected; notification July 11 |
| ICLR 2027 workshops | ~Jan 2027 (predicted) | 4–8 pages | HIGH — longer horizon |
| SIGCOMM 2027 | ~Jan 2027 (predicted) | Full paper | STRETCH — post-HotNets/NeurIPS |
