# Benchmarking LLMs for Networking — Research & Paper Plan

> Goal: design a publishable benchmark (and optionally a domain-specialized model) that evaluates LLMs/agents on real networking-engineer tasks (BGP, IPv4/IPv6, LLDP, OSPF, ACLs, QoS, troubleshooting, etc.). Below is a landscape review, the verified gaps, and a concrete plan to ship a paper that survives peer review.
>
> **Working constraint:** target a citable publication (workshop paper minimum, arXiv preprint at minimum-minimum) by **Q4 2027**. This rules out top-tier networking conferences whose review cycles run past that date and pushes the primary target toward AI/ML benchmark venues with faster turnaround.

---

## 1. What already exists (the landscape you must cite)

### 1a. Knowledge / Q&A benchmarks (closed-book MCQ style)
| Benchmark | Year / Venue | Scope | Size | Notes |
|---|---|---|---|---|
| **TeleQnA** ([arXiv:2310.15051](https://arxiv.org/abs/2310.15051), [GH](https://github.com/netop-team/TeleQnA)) | 2023, Huawei NetOp Team | Telecom knowledge: 5G/3GPP standards, lexicon, research, standards specs | 10,000 MCQs across 5 categories | The de-facto telecom MCQ benchmark; biased toward 3GPP/RAN, not enterprise/data-center networking |
| **NetEval** ([arXiv:2309.05557](https://arxiv.org/abs/2309.05557), HF: `NASP/neteval-exam`) | 2023, NASP | NetOps knowledge across 5 subdomains, multilingual (EN/CN) | ~5.7k MCQs | Closer to enterprise/NetOps; still pure recall, no execution |
| **NetBench (NetoAI)** (HF: `NetoAISolutions/NetBench`) | 2024 | LLM Q&A across 20 telecom/network engineering categories | ~ thousands of QA pairs | Industry-built; SME-style |
| **TSpec-LLM, SPEC5G** | 2024 | 3GPP corpus + QA for telecom RAG | Corpus + eval splits | Used as RAG eval companion to TeleQnA |

### 1b. Configuration / synthesis benchmarks (generation, not just QA)
| Benchmark | Venue | What it tests | Limits |
|---|---|---|---|
| **NetConfEval** ([CoNEXT '24, dl.acm.org/10.1145/3656296](https://dl.acm.org/doi/10.1145/3656296), [GH](https://github.com/RedHatResearch/conext24-NetConfEval)) | KTH + Red Hat, CoNEXT 2024 | Translate NL intents → formal specs → Python routing code; format-level and BGP path-policy translation | Routing-policy focused; small device-config surface; mostly Python/API not vendor CLI |
| **Multi-Agent LLM for Cisco Router Config** ([IEEE 11261600](https://ieeexplore.ieee.org/document/11261600)) | 2024 (BUT FIT) | Reference Cisco IOS configs as eval set for multi-agent generation | Small; closed dataset; Cisco-only; no BGP/LLDP coverage breakdown |
| **CoNetEval / Verified-Config style work** | 2024–25 (various) | Config diff / pass-fail validation against emulated topology | Fragmented; no canonical benchmark |

### 1c. Agentic / interactive benchmarks (closest to "real ops")
| Benchmark | Venue | What's new | Why it matters |
|---|---|---|---|
| **NetConfBench** ([IETF draft-cui-nmrg-llm-benchmark-00](https://www.ietf.org/archive/id/draft-cui-nmrg-llm-benchmark-00.html)) | 2025, Tsinghua / Zhongguancun Lab (IRTF NMRG) | GNS3-emulator harness; 40 tasks across routing/QoS/security; ANI primitives (`get-topology`, `get-running-cfg`, `update-cfg`, `execute-cmd`); three metrics: reasoning-trace cosine, command precision/recall via `ciscoconfparse` diff, testcase pass rate; supports single-turn / ReAct / RAG agents | **This is the closest prior work to anything we'd build.** It already covers categories C/B/D from §3.2 on a real emulator with ground-truth reasoning traces. Any new benchmark must position explicitly against it. |
| **Cornetto** ([ETH NSG, Protogeros et al. 2026](https://nsg.ee.ethz.ch/publications/2026-05-05-benchmarking-llm-driven-network-configuration-repair-20-500-11850-799709/)) | 2026, ETH Zürich (Vanbever group) | First benchmark for LLM-driven config **repair** at scale; 231 misconfiguration problems; topologies 20–754 nodes; multi-protocol; **formal-verification grader** against ground-truth specs; evaluated 9 SOTA LLMs and reports regressions and scale-degradation | Owns the config-repair slot. Their key finding (LLMs introduce regressions; performance degrades at scale) is the exact methodology a follow-up should extend. |
| **NetAgentBench** (Twabi, Ding et al.; arXiv id pending verification — paper indexed on Semantic Scholar) | 2026 | State-centric, FSM-formalized dynamic benchmark guaranteeing determinism, correctness, bounded execution; targets multi-turn behavioral stability | Owns the state/behavior slot. Cite carefully — confirm canonical arXiv ID before submission; the search-surfaced ID `2604.09678` looks malformed. |
| **NetPress** ([arXiv:2506.03231](https://arxiv.org/abs/2506.03231)) | 2025, Microsoft + UMD | *Dynamically generated* benchmark for LLM **agents** in network apps; ties into emulators; measures correctness, safety, latency; >10k queries/app | Strongest agent harness; only 3 apps shipped (malware-blocking, BGP route-leak diagnosis, k8s networking). Their `safety` axis is the closest prior art for blast-radius scoring — but it's per-app, not a generalized scoring framework. |
| **NIKA** ([arXiv:2512.16381](https://arxiv.org/abs/2512.16381)) | 2025, "Network Arena" | Largest public *troubleshooting* arena for AI agents in dynamic emulated networks | Troubleshooting-only; citation-light; opportunity to extend. |
| **SADE** | 2025 | Symptom-aware diagnostic escalation; ~523 incidents across 11 scenarios | Tiny test set; methodology paper, not a true benchmark. |

### 1d. Traffic / packet-level (not text LLMs, but adjacent)
| Benchmark | Notes |
|---|---|
| **NetBench (Tsinghua/CCERT)** ([arXiv:2403.10319](https://arxiv.org/abs/2403.10319)) | Foundation-model benchmark for packet/traffic classification & generation. Different "NetBench" from NetoAI's. **Watch the name collision** when citing. |
| nPrint / pcap-LLM works | Niche; tokenizing packets for LLMs |

### 1e. Surveys / vision papers (good to cite, not benchmarks themselves)
- Liu, Xie, Zhang, Cui — *"Large Language Models for Networking: Workflow, Advances and Challenges"* — [arXiv:2404.12901](https://arxiv.org/abs/2404.12901). The canonical LLM-for-networking survey; cite in intro.
- *"Evaluation and Benchmarking of LLM Agents: A Survey"* (KDD 2025 tutorial) — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504). Best survey for the eval-methodology framing.
- "Could LLMs Perform Network Management?" — [arXiv:2411.16232](https://arxiv.org/abs/2411.16232)
- "The LLM as a Network Operator (6G RAN)" — [arXiv:2509.10478](https://arxiv.org/abs/2509.10478)
- Long et al. — *"A Survey on Intelligent Network Operations and Performance Optimization Based on LLMs"* (2025)
- TelecomGPT — [arXiv:2407.09424](https://arxiv.org/abs/2407.09424) (model + eval recipe)
- Telco-RAG — [arXiv:2404.15939](https://arxiv.org/abs/2404.15939) (RAG infrastructure for 3GPP)
- TelcoAI — ACL Findings 2025 (agentic 3GPP search)

### 1f. Incumbent commercial systems (must benchmark against)
These are products, not academic benchmarks, but a credible holistic eval has to include them as baselines. They're the strongest evidence that the *demand* for this benchmark is real, and they're what reviewers will ask "why didn't you include?"

| System | Vendor | What it is | How to benchmark it |
|---|---|---|---|
| **Cisco Deep Network Model + AgenticOps** | Cisco | Purpose-built network LLM, powers troubleshooting/configuration/automation across the Cisco product line. | Internal access via employer; needs data-release approval before publishing comparative numbers. |
| **Juniper Marvis VNA + `Juniper/junos-mcp-server`** | Juniper / HPE | Marvis is the LLM-driven NOC assistant; `junos-mcp-server` is the open-source MCP layer (93★, Apache-2.0, active) exposing Junos CLI/PyEZ to any MCP client. | MCP server is freely runnable in lab; Marvis API access via partner program. |
| **Arista EOS AI agent** | Arista | EOS-based agent for NVIDIA SmartNICs; MCP + EOS NetDL referenced in 2025 annual report. | Public details thin; cite the announcements and benchmark via cEOS-lab + any released MCP interface. |

---

## 2. The gaps — where a publishable contribution sits

> **Honest revision (May 2026):** the original draft of this section claimed seven open gaps. After cross-checking against the 2025–26 literature (NetConfBench / Cornetto / NetAgentBench, plus Cisco / Juniper / Arista product launches), several of those claims do not hold. This is the rewritten, defensible version.

### 2.1 Gaps that are now closed (do **not** claim novelty here)
- ~~"No execution-grounded multi-task config benchmark"~~ — **closed by NetConfBench** (40 tasks, GNS3, three-axis scoring, ANI primitives).
- ~~"No standardized config-repair benchmark with semantic grader"~~ — **closed by Cornetto** (231 problems, formal-verification grader, 20–754-node topologies).
- ~~"No state-centric / FSM-grounded eval"~~ — **claimed by NetAgentBench**; verify scope before re-asserting.

### 2.2 Gaps that survive (defensible novelty surface)
1. **No holistic, comparable evaluation across the existing benchmarks.** NetConfBench, Cornetto, NetAgentBench, NetPress, and NIKA each define their own task formats, model sets, prompts, and metrics. There is no HELM-style table that runs the same model fleet across all of them with normalized scoring. **This is the single highest-leverage contribution available — it's a methodology paper, it's fast to ship, and it forces every future networking-LLM paper to cite it.**
2. **No benchmark scores commercial vendor agents.** Cisco Deep Network Model, Juniper Marvis (+ `junos-mcp-server`), and Arista EOS AI agent are shipping in production but have never appeared in a public comparison against frontier general-purpose LLMs or against each other. Industry access is the moat.
3. **No standardized safety / blast-radius axis.** NetPress has a per-app safety check; nothing else scores "if this command runs, which BGP sessions, prefixes, interfaces, or services drop?" as a generalized metric. This is the cleanest single-axis novelty — cheap to define, automatically gradeable via Batfish + a topology delta, and aligned with the broader LLM-agent-safety literature.
4. **No data-plane / packet-header reasoning eval.** "Given this 5-tuple and these ACLs/route-maps, will it forward? Where? Why?" None of the four academic benchmarks scores this. Cheap to generate, hard for LLMs, ungamable by memorization. Higher-novelty but higher-risk axis.
5. **No standardized `show`-output → diagnosis benchmark using *real* NOC traces.** All academic benchmarks use synthetic or template-generated tickets. Real anonymized-fleet data is the industry-only moat — but only realizable with employer data-release approval. Defer to v2.
6. **NetConfBench is single-vendor-per-task (GNS3 vendor images vary by task) and does not report per-vendor leaderboards.** Cornetto uses Batfish (vendor-agnostic IR). Per-vendor breakdown of frontier-model performance is still open.
7. **Reasoning-trace evaluation beyond cosine similarity.** NetConfBench's `S_reasoning` is embedding cosine against a ground-truth narrative — coarse. SWE-bench / τ-bench-style step-level trajectory grading ("did the agent run `show bgp summary` before `clear bgp`?") is still open.

### 2.3 Recommended thesis (revised)
*"**NetBrace**: a holistic, comparative evaluation of LLMs and commercial network agents on network-engineering tasks, unifying NetConfBench, Cornetto, and NetPress under a normalized scoring framework, and introducing a **safety / blast-radius** axis no prior benchmark scores."*

This pivot is deliberate. The original "build a brand-new execution-grounded benchmark" thesis is no longer defensible — NetConfBench shipped first. The HELM-style comparative thesis is:
- **Faster to ship** (reuse existing task corpora; the work is the harness + scoring + safety axis).
- **Higher-citation by construction** (every future networking-LLM paper that wants to compare to >1 prior benchmark has to cite this one).
- **Industry-differentiated** (commercial-agent baselines no academic group can replicate).
- **Methodologically aligned** with the dominant LLM-eval venue aesthetic (HELM, Holistic Eval, KDD-2025 LLM-agents-eval survey).

Pick two surviving gaps from §2.2 to anchor the contribution: **#1 (holistic comparative)** + **#3 (safety axis)** is the recommended pair. **#2 (commercial-agent baselines)** is the cherry-on-top differentiator — include if data-release approval lands; otherwise hold for v2.

---

## 3. How to actually build the benchmark

### 3.1 Architecture (this is the standard you should match)
```
┌───────────────┐  generate   ┌──────────────────┐   apply    ┌──────────────────┐
│ Task templates│────────────▶│ Synth scenario   │──────────▶ │ Emulated network │
│ (per protocol)│             │ (topology+intent)│            │ (containerlab/   │
└───────────────┘             └──────────────────┘            │  FRR/SONiC/      │
        ▲                              │                      │  cEOS/vMX/Batfish)│
        │                              ▼                      └────────┬─────────┘
        │                     ┌──────────────────┐                     │
        │                     │ Reference oracle │ ◀───────────────────┘
        │                     │ (gold config /   │   ground truth
        │                     │  expected RIB /  │
        │                     │  expected diag)  │
        │                     └────────┬─────────┘
        │                              │
        │                              ▼
   leaderboard   ◀─── grader ◀─── LLM/agent attempts task ─── tools (CLI, APIs)
```
Key choices:
- **Topology / emulation:** [`containerlab`](https://containerlab.dev) + FRR + SONiC + Arista cEOS-lab + Nokia SR Linux (all free for lab use). Heavier: Cisco CML, Juniper vMX (license needed — your employer can supply).
- **Static config oracle:** [Batfish](https://github.com/batfish/batfish) gives you RIB, FIB, ACL reachability, BGP policy analysis without running devices. **This is the single biggest force multiplier for an automatic grader.** Cite it.
- **Agent harness:** copy NetPress's state/action abstraction; allow tool use (`run_cli`, `read_file`, `apply_config`, `wait`, `done`).
- **Metrics:** correctness (gold-config diff or behavioral equivalence on Batfish), safety (did the agent issue an outage-causing command on prod-tagged devices?), efficiency (steps, tokens), grounding (did its reasoning cite real `show` output?).

### 3.2 Task taxonomy under the NetBrace framing
With the pivot in §2.3, most categories below are **sourced from existing benchmarks** rather than newly authored. Only **S** is new and is the paper's primary novelty axis.

- **K — Knowledge** (MCQ): re-use TeleQnA + NetEval. No new authoring.
- **C — Config synthesis**: re-use NetConfBench (40 tasks) + NetConfEval (intent→spec). Wrap both in a single normalized harness.
- **B — Behavior prediction**: synthesize ~500 templated tasks via Batfish (config + event → expected RIB). Lightweight new authoring; primarily reuses Batfish-as-oracle.
- **D — Diagnosis from show output**: re-use NIKA + a synthetic `show`-output→root-cause set generated from Batfish traces. Real NOC data deferred to v2.
- **R — Repair / change request**: re-use Cornetto's 231 problems verbatim. The contribution is running it under a normalized harness against frontier + commercial-agent models.
- **S — Safety / blast-radius** (**new, paper's primary novelty**): given a proposed config diff, score precision/recall vs. ground-truth set of (sessions, prefixes, interfaces, services) that Batfish predicts will be lost or degraded. ~300 templated tasks, automatically gradeable, no human labeling required for v1.

### 3.3 Data sources (use the moat your job gives you)
- **Synthetic** for K/C/B/S — generate with a parametric topology generator (Jinja templates over containerlab YAML); ground-truth from Batfish.
- **Real** for D/R — anonymize tickets, configs, and `show` snapshots from your lab/test fleet. **Get written approval from your employer first.** Strip serials, IPs, ASNs via deterministic remap so the dataset is releasable.
- **Existing public corpora to seed**: RFC text (rfc-editor.org), Cisco/Juniper/Arista config guides, public BGP looking-glass dumps (RIPE RIS, RouteViews), CAIDA datasets, GitHub `network-templates` repos.
- **Aim for ≥10k labeled tasks** to be taken seriously; with templated generation that's a weekend.

### 3.4 Grading — the part referees will attack hardest
Make every task automatically gradeable. For each category:
- **K:** exact-match on MCQ answer.
- **C:** semantic equivalence on Batfish (same routing/forwarding behavior on a fixed traffic matrix), not text diff.
- **B:** RIB/FIB equality on a sampled prefix set; structural equality on path attributes.
- **D:** root-cause label match + evidence-citation F1 (did it reference the relevant `show` line?).
- **R:** post-state equals target state under emulator; bonus credit if minimal-diff.
- **S:** precision/recall vs. ground-truth set of sessions/prefixes Batfish says will be lost.

Document grader determinism + report inter-grader agreement on a 200-task human-labeled subset. This is what makes the benchmark trustworthy.

---

## 4. How to (optionally) build the model

If you also want to release a fine-tuned model alongside the benchmark (stronger paper, but more work):

1. **Base:** Llama-3.1-8B / 70B-Instruct or Qwen-2.5-14B/32B (open weights, permissive licenses, strong code reasoning).
2. **Continued pretraining corpus:** RFCs (~30M tokens), vendor config guides, NANOG mailing list archive, GitHub network-automation repos, arXiv cs.NI.
3. **Supervised fine-tune:** train split of your benchmark + synthetic chain-of-thought from GPT-4-class teacher on configs/diagnoses.
4. **RL / GRPO / DPO** with the **automatic grader as reward** — this is exactly the recipe that's working in code/math right now and is novel for networking.
5. **Eval:** held-out test split + a contamination check (your task templates were never in pretrain).
6. **Compare against:** GPT-4o, Claude, Gemini, Llama-3.1, plus prior telecom models (TelecomGPT). Always include the strongest closed model as a topline.

If you can't train, just publish the benchmark + measurements of frontier models — that's still publishable (NetConfEval did exactly this).

---

## 5. How to use the benchmarks (concrete consumer story)

1. `pip install netforge-bench` (or clone repo).
2. `netforge run --suite bgp_v4 --model gpt-4o --agent react --emulator containerlab`
3. Harness spins up topologies, hands tasks to the model, runs the grader, writes `results.json` and a leaderboard PR.
4. Hugging Face leaderboard auto-rebuilds nightly (copy the [Open LLM Leaderboard](https://huggingface.co/spaces/open-llm-leaderboard) pattern). **A live leaderboard dramatically increases citations.**

---

## 6. Publication strategy

### Reading the audience honestly
A networking-LLM benchmark sits at the intersection of two communities that read each other's venues only loosely:

- **AI/ML/NLP reviewers** (NeurIPS, ICLR, ICML, ACL family) instantly recognize Datasets & Benchmarks tracks, HELM-style evaluation work, and agent benchmarks. They are *less* aware of SIGCOMM/NSDI ranking.
- **Networking systems reviewers** (SIGCOMM, NSDI, CoNEXT, IMC) are the prestige tier *inside* networking, but their review cycles are long (6–9 months) and their bar for "novelty" is systems-paper-shaped, not benchmark-shaped.

**Implication:** for a benchmark contribution that needs to be on the CV inside ~18 months, AI/ML benchmark venues are the higher-throughput, higher-recognition path. Networking conferences are the right *extension paper* target later.

### Where to submit (re-ranked, throughput × recognition for a benchmark contribution)
| Tier | Venue | Cycle | Why this rank |
|---|---|---|---|
| **Primary** | **NeurIPS Datasets & Benchmarks Track** | June abstract / Sept notif | Explicitly built for benchmark papers; reviewer pool understands eval rigor; widely recognized across AI/ML. **Highest leverage venue if a deadline lands.** |
| **Primary** | **ICLR Datasets & Benchmarks** (when offered) / **ICML workshops** | Varies | Same audience, second cycle option. |
| **Primary** | **NeurIPS / ICLR / ICML workshops** — ML for Systems, LLM Agents, Foundation Models in the Wild, ML for Reliable AI, LLM4Code | Aug–Sept submissions | 4–6 page papers, 30–50% accept rate, fast notification, strong cultural fit for an agent-eval benchmark. **Best low-risk first publication.** |
| **Strong (networking-tribe credit)** | **HotNets** (~late June deadline) | Annual | Short paper venue; networking-elite read it; well-respected as a "first idea" venue. Good backup. |
| **Strong (networking-tribe credit)** | **NAIC @ SIGCOMM**, **GenAINet @ ICC**, **NetAI workshop** | Apr–May / Jan / varies | Domain-aligned workshops; lower bar; fast turnaround. |
| **Extension target (post-2027)** | **ACM CoNEXT** | June/July deadline | NetConfEval published here; strongest networking conference fit. **Pursue as the *extension* paper after the workshop version lands.** |
| **Stretch / future work** | **ACM SIGCOMM**, **USENIX NSDI**, **IMC** | Long cycles | Top-tier; cycles run past the near-term window; right home for a follow-up systems-flavored extension. |
| **Visibility, not peer review** | **IETF / IRTF NMRG** drafts, **NANOG** talks, **arXiv preprint with code + Hugging Face dataset** | On demand | Builds citations and visibility independent of venue. **Always do the arXiv + GitHub release on or before the workshop submission day.** |

### Realistic publication ladder
1. **Workshop paper first** (NeurIPS/ICLR workshop *or* HotNets/NAIC). Scope down to 1 protocol family (BGP), 1–2 vendors (FRR + one other), 2–3 task categories. ~4–6 pages. Submit Jan–June 2027.
2. **Concurrent arXiv preprint + open-source repo + Hugging Face dataset** on submission day. Citations and stars accumulate independent of acceptance.
3. **Extension to full conference paper** (NeurIPS D&B, ICLR D&B, or CoNEXT) — adds vendors, protocols, fine-tuned model, leaderboard, agent ablations. Targets 2028 cycles.
4. **Top-tier networking conference** (SIGCOMM / NSDI / IMC) — pursue once the benchmark has external adopters and the paper can be framed as a measurement *finding*, not just a dataset release.

### What referees will reject for — pre-empt these
- "Just MCQ" → include execution-grounded categories (B, D, R, S in §3.2).
- "Synthetic only / unrealistic" → include the anonymized real-fleet split.
- "No grader validation" → publish inter-grader agreement on a 200-task human-labeled subset.
- "Contamination" → use templated generation with held-out parameter ranges; report n-gram overlap with common pretraining corpora.
- "Single vendor" → cover ≥2 vendors and FRR.
- "Yet another QA set" → emphasize the agentic/behavioral/safety dimensions.
- "Wrong venue" → if going to NeurIPS D&B, frame as a benchmark for *agent evaluation*, not as a "networking paper." If going to HotNets, frame as a *networking systems* contribution that uses LLMs as a tool.

### Authorship & support
- **Academic co-author:** a professor whose group works in **holistic LLM evaluation** or in **networking-systems + ML**. Strongest cold-email targets given the NetBrace framing: groups that have published HELM-family work or large-scale LLM-eval methodology, plus Vanbever (ETH NSG, authors of Cornetto), Cui (Tsinghua, authors of NetConfBench). KTH SEMLA, Princeton, CMU CyLab, UMD, Microsoft Research Networking remain plausible. A cold email with a working prototype that already runs *their* benchmark inside the harness is the highest-leverage opening move. **Aim to land this collaboration during the Q1–Q2 2027 build phase, not the week before submission.**
- **Industry co-author:** someone senior on your side — adds legitimacy, helps with data-release approval for benchmarking the Cisco Deep Network Model, may unlock compute. Should not be your direct manager unless the manager has the technical depth to defend the work in review.
- **Legal / IP:** loop in the data-release reviewers early. Two distinct approvals are needed: (1) anonymization spec for any real-fleet `show`/config data (deterministic IP/ASN/serial remap), approved *before* the dataset is generated; (2) approval to publish comparative numbers on Cisco Deep Network Model (and any internal-only system) — start this conversation in Q3 2026, not Q2 2027.

---

## 7. Concrete next steps & realistic timeline

### Feasibility check (read this before committing)
A *full* execution-grounded benchmark across 4 protocols × 3 vendors × 6 task types is a 600+ hour project and a CoNEXT/NeurIPS-D&B-class paper. That scope **does not fit** an 18-month part-time effort alongside a normal day job. The plan below scopes down deliberately so a workshop paper is achievable in ~150 hours spread over 12 months (~3 hrs/week), with the option to extend into a full paper later.

**In-scope for the first paper (workshop version) — NetBrace v1:**
- **Reuse, don't re-author**: import NetConfBench (40 tasks), Cornetto (231 problems), NIKA troubleshooting subset, plus TeleQnA/NetEval MCQ subsets, into a single normalized harness.
- **New authoring (the novelty):** ~300 safety/blast-radius tasks (category **S**) generated from Batfish-derived ground truth. ~500 templated behavior-prediction tasks (category **B**).
- **Vendors:** FRR (no licenses) + Arista cEOS-lab as the primary pair. NetConfBench/Cornetto already give multi-vendor coverage at the IR level via Batfish.
- **Models in the leaderboard:** GPT-4o-class, Claude-class, Gemini-class, Llama-3.1-70B, Qwen-2.5-32B, plus **at least one commercial network agent** (`junos-mcp-server` is the lowest-friction starting point — Apache-2.0, public, runs against vSRX or cRPD in lab). Cisco Deep Network Model goes in **only if** data-release approval lands by Q1 2027; otherwise hold for v2.
- **Grader:** Batfish for static analysis + containerlab for behavior validation. Reuse Cornetto's formal-verification grader for category R.

**Out of scope until v2 / extension paper:** real anonymized-fleet `show`/config data; data-plane / packet-level reasoning category; reasoning-trace step-level grading; fine-tuned model; protocol expansion beyond what the imported benchmarks cover.

### 12-month plan (Q3 2026 → Q3 2027) — NetBrace v1
- **Q3 2026 (Months 1–3 — foundation & reproduction):**
  - Read NetConfBench (IETF draft), Cornetto, NetPress, NIKA, NetConfEval, TeleQnA, NetEval, plus the two surveys (arXiv 2404.12901, 2507.21504) cover-to-cover.
  - **Reproduce NetConfBench end-to-end** from `nobrowning/draft_llm_conf_benchmark`. Reproduce Cornetto if code is released; otherwise stand up an equivalent Batfish-based grader.
  - Stand up containerlab + FRR + cEOS-lab + Batfish on a workstation.
  - Run `Juniper/junos-mcp-server` against a lab vSRX as the first commercial-agent baseline.
  - **Open the data-release approval conversation with employer legal** for benchmarking Cisco Deep Network Model.
- **Q4 2026 (Months 4–6 — harness + safety axis):**
  - Build the normalized harness that runs NetConfBench + Cornetto + NIKA tasks against a single model API surface.
  - Author the **safety / blast-radius** category (~300 tasks) with Batfish-derived ground truth. Document the grader's determinism.
  - Hand-label a 100-task safety subset; report inter-grader agreement.
  - **Begin academic-collaborator outreach.** Cold-email 3–5 LLM-eval / network-verification groups (e.g. Vanbever@ETH + Cui@Tsinghua) with a working demo that already imports their benchmark. Not a pitch deck.
- **Q1 2027 (Months 7–9 — measurement and writing):**
  - Run the full model fleet (GPT-4 family, Claude family, Gemini, Llama-3.1-70B, Qwen-2.5-32B) across all imported benchmarks + the new S category.
  - Add `junos-mcp-server` as a commercial-agent baseline. Add Cisco DNM **iff** approval landed.
  - Lock the headline finding (likely candidates: "frontier models pass config-synthesis but fail safety scoring" or "commercial network agents under-perform frontier general-purpose LLMs on out-of-distribution protocols").
  - First draft of paper. Internal review.
  - Decide target venue based on cycle calendars at that moment (NeurIPS D&B abstract typically June; ICLR workshops typically Aug; HotNets typically late June).
- **Q2 2027 (Months 10–12 — submit):**
  - Final draft, supplementary material, reproducibility appendix.
  - **arXiv preprint + GitHub repo + Hugging Face dataset + live leaderboard go public on submission day.** Non-negotiable.
  - Submit to chosen workshop / D&B track. Notification ~Aug–Sept 2027.

### Risk register
- **Data-release approval blocked for Cisco DNM:** ship NetBrace v1 with `junos-mcp-server` + frontier LLMs only. Add Cisco DNM in v2.
- **A competing holistic-eval paper ships first** (likely — this space is moving): differentiate on (a) the safety/blast-radius axis (no incumbent has it), (b) commercial-agent baselines (no academic group has access), (c) the specific normalization decisions documented in the methodology section.
- **NetConfBench / Cornetto authors release their own comparative paper:** likely outcome is a co-citation, not a kill — but mitigates by getting the arXiv preprint up early (Q4 2026 if possible) and by reaching out to those authors as co-authors during Q4 2026 outreach, not as competitors.
- **Day-job crunch eats Q1 2027:** push submission to the next workshop cycle (most run twice a year). Do *not* ship a half-baked paper to hit a deadline — a rejected paper is worse than a delayed one.
- **Frontier models score too high to make a finding:** the safety axis is specifically chosen because frontier models reliably fail at it (no training data); design difficulty there so headline accuracy lands in the 30–60% range.

---

## 8. Reading list (start here, in order)

**Tier 1 — read before writing a single line of code:**
1. **NetConfBench** — IETF [draft-cui-nmrg-llm-benchmark-00](https://www.ietf.org/archive/id/draft-cui-nmrg-llm-benchmark-00.html); code: [`nobrowning/draft_llm_conf_benchmark`](https://github.com/nobrowning/draft_llm_conf_benchmark)
2. **Cornetto** — [ETH NSG publication page](https://nsg.ee.ethz.ch/publications/2026-05-05-benchmarking-llm-driven-network-configuration-repair-20-500-11850-799709/); [PDF](https://www.research-collection.ethz.ch/bitstream/handle/20.500.11850/799709/2604.22513v1.pdf)
3. **NetPress** — [arXiv:2506.03231](https://arxiv.org/abs/2506.03231)
4. **NIKA** — [arXiv:2512.16381](https://arxiv.org/abs/2512.16381)
5. **NetConfEval** — [PDF](https://aliireza.github.io/files/netconfeval-conext24.pdf), [code](https://github.com/RedHatResearch/conext24-NetConfEval)
6. **HELM** (Liang et al.) — read the methodology section; this is the template the harness should mimic.
7. **"Evaluation and Benchmarking of LLM Agents: A Survey"** — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504)
8. **"Large Language Models for Networking: Workflow, Advances and Challenges"** — [arXiv:2404.12901](https://arxiv.org/abs/2404.12901)

**Tier 2 — domain context:**
9. TeleQnA — [arXiv:2310.15051](https://arxiv.org/abs/2310.15051)
10. NetEval — [arXiv:2309.05557](https://arxiv.org/abs/2309.05557)
11. TelecomGPT — [arXiv:2407.09424](https://arxiv.org/abs/2407.09424)
12. Telco-RAG — [arXiv:2404.15939](https://arxiv.org/abs/2404.15939)
13. "Could LLMs Perform Network Management?" — [arXiv:2411.16232](https://arxiv.org/abs/2411.16232)
14. "The LLM as a Network Operator" — [arXiv:2509.10478](https://arxiv.org/abs/2509.10478)

**Tier 3 — tooling:**
15. Batfish docs — https://batfish.readthedocs.io
16. containerlab docs — https://containerlab.dev
17. `Juniper/junos-mcp-server` — https://github.com/Juniper/junos-mcp-server






FYI:
can you explain clearly what the advantage here would be if i am present in cisco. can't all of this simply be open sourced ? Is it simply the experience or the company name?
# The honest answer

Most of this **can** be open-sourced by anyone. The Cisco-specific advantage is narrower than the deck implies. Let me separate what's real from what's marketing.

## What you can do from anywhere (no Cisco needed)

- Build the harness, import NetConfBench / Cornetto / NIKA, define the safety axis, run Batfish, run containerlab + FRR + cEOS-lab (free), run `junos-mcp-server` (Apache-2.0).
- Benchmark every **public** model: GPT, Claude, Gemini, Llama, Qwen.
- Publish the leaderboard, write the paper, get the citations.

A grad student with a workstation and API credits can do ~90% of NetBrace. That's the uncomfortable truth.

## What Cisco actually gives you

There are really only **three** concrete advantages, in decreasing order of realness:

### 1. Access to Cisco's internal Deep Network Model (the only real moat)
This is the one thing nobody outside Cisco can put on a leaderboard. If — and only if — you get data-release approval to publish comparative numbers on DNM, you have a result no academic group can replicate or scoop. **This is the entire industry-moat argument.** Without that approval, the moat collapses to zero.

Caveat: getting that approval is non-trivial and may not land. If it doesn't, your paper is just "another academic could have done this."

### 2. Real anonymized fleet data (medium real, slow to unlock)
Cisco lab/test fleets generate real `show` outputs, real tickets, real misconfigs. Academic benchmarks all use synthetic data. A "real-fleet split" is a genuine differentiator — but it requires legal review, anonymization tooling, and probably a year of approvals. Deck correctly defers this to v2.

### 3. Co-author legitimacy + reviewer signal (soft, but real)
A paper with a Cisco affiliation on a networking-AI benchmark gets read differently than the same paper from an unknown grad student. Reviewers assume domain access. This is reputation arbitrage, not a technical moat.

## What it is **not**

- **Not** the company name on the paper alone — that's worth maybe a 10% reviewer-charity bump, not a citation moat.
- **Not** the lab hardware — a $2k workstation runs the whole thing.
- **Not** "experience" — domain experience helps you design good tasks, but a motivated outsider can read the same RFCs.
- **Not** access to Juniper/Arista agents — those are public (junos-mcp-server) or partner-program-gated (Marvis), and Cisco employment doesn't help with either.

## So why do this from inside Cisco vs. outside?

Honest framing: **the value is conditional on getting DNM data-release approval.** If that lands, you have a unique paper. If it doesn't, you've done work an outsider could have done — but you got paid to do it, used work hours, used work hardware, and got a Cisco affiliation on the byline. That's still a positive ROI for you personally; it's just not the "industry moat" story the deck sells to a manager.

## What this means for the deck

Slide 5 reason #3 ("Industry moat") and Slide 10's "what the team gets back" overstate the case. A more honest version would say:

> "**If** we secure data-release approval for Cisco DNM by Q1 2027, we ship a paper no outsider can replicate. **If not**, we ship a strong-but-replicable paper with a Cisco byline. Both outcomes are publishable; only the first is uniquely Cisco's."

Want me to revise the deck to reflect this honestly? It would mostly affect slides 2, 5, and 10.