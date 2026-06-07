# NetBrace Execution Plan — Week-by-Week (May 2026 → Submission)

> **Companion to:** [networking_llm_benchmark_paper_plan.md](networking_llm_benchmark_paper_plan.md) (strategy/scope) and [../test/stanford_math_refresher_summer_2026.md](../test/stanford_math_refresher_summer_2026.md) (parallel summer load).
> **Author:** Harshit Singh.
> **Today:** Tue May 19, 2026.
> **Pre-quarter deadline:** Sun Sep 20, 2026 (CS221 starts ~Sep 21, 2026).
> **Submission target:** workshop cycle in Q2 2027 (NeurIPS/ICLR/ICML LLM-agents or HotNets); arXiv same day.

---

## 0. Operating principles

1. **Frontload everything build-shaped before Au'26 quarter starts.** Once CS221 is live, the only NetBrace work that's realistic is writing, revisions, and one model rerun per week. Build / debug / data-gen *must* be done by Sep 20.
2. **Scope is locked to NetBrace v1** as defined in §7 of the strategy doc: import NetConfBench + Cornetto + NIKA + TeleQnA/NetEval, author the new Safety / blast-radius category (~300 tasks) + Behavior-prediction category (~500 templated), benchmark frontier models + `junos-mcp-server`. **No data-plane category, no fine-tuned model, no real-fleet data in v1.** If you find yourself adding scope mid-summer, stop and re-read this line.
3. **The math refresher (Jun 1 – Aug 23, 10 hrs/wk) is non-negotiable.** Stanford admission > paper. If the two collide, the paper slips a week.
4. **Cisco day job is the third lane.** Default budget = 40 hrs/wk Cisco + 10 hrs/wk math (summer) + 10–18 hrs/wk NetBrace. Total 60–68 hrs/wk for the summer. Sustainable for 16 weeks; not longer. Plan reflects that.
5. **One deliverable per week, in a repo, with a commit.** No deliverable = the week didn't happen. Repo: `~/netbrace/`.
6. **Data-release approval for Cisco DNM is a parallel track, started in Week 1 and re-pinged monthly.** If it lands, DNM goes in the leaderboard. If it doesn't, ship without it — the paper still stands.
7. **Track everything in a single `progress.md` at the repo root.** One line per week: deliverable, hours spent, blocker (if any). This is also LOR / SOP / Cisco-promo material.

### Time budget by phase
| Phase | Span | Weeks | NetBrace hrs/wk | Total NetBrace hrs | Concurrent load |
|---|---|---|---|---|---|
| **0 — Pre-summer sprint** | May 19 – May 31 | 2 (partial wk 1) | 15–20 | ~35 | Cisco only |
| **1 — Summer co-effort** | Jun 1 – Aug 23 | 12 | 10–12 | ~130 | Math refresher (10 hrs/wk) |
| **2 — Final push** | Aug 24 – Sep 20 | 4 | 18–22 | ~80 | Math buffer wk Aug 24–30 only |
| **3 — Au'26 quarter (ease-off)** | Sep 21 – Dec 13 | 12 | 4 | ~48 | CS221 (~15–20 hrs/wk) |
| **4 — Wi'27 quarter** | Jan 4 – Mar 21, 2027 | 11 | 3 | ~33 | CS224N (~20–25 hrs/wk) |
| **5 — Sp'27 quarter (submit)** | Mar 29 – Jun 13, 2027 | 11 | 4 | ~44 | CS229 (~25 hrs/wk) — **slip the paper, not CS229** |
| **Total NetBrace** | — | — | — | **~370 hrs** | — |

This is ~2.5× the strategy doc's "150 hr workshop paper" estimate, which is intentional: the strategy doc was a floor; this plan funds the safety-axis novelty, model fleet, and one full rewrite.

---

# PHASE 0 — Pre-summer sprint (May 19 – May 31, 2026)

> **Goal:** finish all reading, stand up the lab, decide collaborator targets, *before* math refresher eats your weekends.
> **Capacity:** ~15–20 hrs/wk NetBrace. Cisco is the only competing lane.

### Week 0 (Tue May 19 – Sun May 24) — Foundations & repo

**Daily plan (weekdays = 1.5 hr eve, weekends = 5–6 hr blocks):**

- **Tue May 19 (today, 2 hr):** create `~/netbrace/` repo (private GitHub or Bitbucket initially; flip public on submission day). Subfolders: `reading/`, `harness/`, `tasks/`, `runs/`, `paper/`, `progress.md`. Pull strategy doc + this plan into `paper/refs/` for fast lookup. Open data-release ticket with Cisco legal for DNM benchmarking (separate from any anonymized-fleet ask — those are different reviews per §6).
- **Wed May 20 (1.5 hr):** Tier 1 reading #1 — NetConfBench IETF draft end-to-end. Notes in `reading/01_netconfbench.md` (≤2 pages: scope, 40 tasks taxonomy, 3 metrics, ANI primitives, what's reusable, what's not).
- **Thu May 21 (1.5 hr):** Skim `nobrowning/draft_llm_conf_benchmark` repo — README, top-level structure, what's runnable. Don't run yet. Notes go in same file.
- **Fri May 22 (1.5 hr):** Tier 1 #2 — Cornetto paper end-to-end. Notes in `reading/02_cornetto.md`. Focus: their Batfish-based grader, the 231-problem taxonomy, the regression-at-scale finding.
- **Sat May 23 (5 hr block):** Tier 1 #3 NetPress + #4 NIKA. Notes in `reading/03_netpress.md`, `reading/04_nika.md`. Then sketch the comparison table (§2.1 of strategy doc) in `paper/refs/landscape_table.md` with your own column headers — "what we import," "what we replace," "what we add."
- **Sun May 24 (5 hr block):** Tier 1 #5 NetConfEval + #6 HELM methodology section. HELM is the template for §3 of your paper — pay attention to how they structure the metric taxonomy and the scenarios table. Notes in `reading/05_netconfeval.md`, `reading/06_helm_methodology.md`.

**Deliverable:** `reading/` folder with 6 short notes; `paper/refs/landscape_table.md` populated; data-release ticket filed.

### Week 1 (Mon May 25 – Sun May 31) — Lab stand-up & last reading

- **Mon May 25 — Memorial Day (5 hr block):** Install containerlab on workstation. Build a 4-router FRR topology (square, full mesh iBGP) from a containerlab YAML you wrote yourself. `harness/lab/frr_square.clab.yml`. Verify BGP comes up; capture `show ip bgp` from each.
- **Tue May 26 (1.5 hr):** Install Batfish (Docker). Run it against the `frr_square` configs. Verify it parses + you can query routes via pybatfish.
- **Wed May 27 (1.5 hr):** Pull Arista cEOS-lab image (you have Arista relationship via Cisco — get an EOS account; image is free for lab use). Add one cEOS node to the topology. Reverify.
- **Thu May 28 (1.5 hr):** Tier 1 #7 — *Evaluation and Benchmarking of LLM Agents: A Survey* (arXiv:2507.21504). Notes in `reading/07_llm_agent_eval_survey.md`. Pull out: which metric families are accepted, what reviewers expect for grader-validity claims.
- **Fri May 29 (1.5 hr):** Tier 1 #8 — *LLMs for Networking* survey (arXiv:2404.12901). Skim — you've already absorbed the field. 1-page note in `reading/08_llm_networking_survey.md`.
- **Sat May 30 (6 hr block):** Install `Juniper/junos-mcp-server` against Juniper cRPD container (cRPD is free). Get one MCP-driven `show route` round-trip working. Capture transcript to `harness/lab/junos_mcp_smoketest.md`. **This is the commercial-agent baseline pipeline. Get it working *before* summer.**
- **Sun May 31 (5 hr block):** Write `paper/outline_v0.md` — section headings only, 1-line abstract, 3-sentence contribution claim. Decide author list (you + manager? + cold-target academic by Q4'26). Pick **collaborator outreach shortlist** (≤5 names) in `paper/collab_targets.md`: candidates are Vanbever (ETH, Cornetto), Cui (Tsinghua, NetConfBench), HELM/CRFM-aesthetic LLM-eval groups at Stanford / Princeton / CMU / UMD. **Do not email yet** — wait until you have a working demo (Week 8 / Aug).

**Deliverable:** lab works end-to-end (FRR + cEOS + cRPD + Batfish + junos-mcp-server smoketest); `paper/outline_v0.md`; `paper/collab_targets.md`. Ping legal on DNM ticket.

---

# PHASE 1 — Summer co-effort (Jun 1 – Aug 23, 2026)

> **Goal:** by Aug 23, have a working harness that runs ≥2 imported benchmarks against ≥3 frontier models + 1 commercial agent, plus first 50 hand-authored Safety tasks.
> **Capacity:** 10–12 hrs/wk NetBrace (Cisco 40 + math 10 + NetBrace 10–12 = ~62 hrs/wk, sustainable).
> **Recommended schedule:** Mon/Wed/Fri evenings 1.5 hr each (4.5 hr) + Sat morning 3 hr + Sun morning 3 hr = 10.5 hr/wk. Math gets Tue/Thu eve + Sat afternoon + Sun afternoon.
> **Holiday handling:** Jul 4 (Sat) is a no-work day; absorb the lost 3 hr into Sun.

### Week 2 (Jun 1 – Jun 7) — Reproduce NetConfEval

> **Plan correction (2026-05-24):** the original Week 2 target was NetConfBench, but `nobrowning/draft_llm_conf_benchmark` is an IETF draft with no code (see [../../reading/01b_netconfbench_code_skim.md](../../reading/01b_netconfbench_code_skim.md)). The runnable config-gen benchmark we actually want is **NetConfEval** (RedHatResearch/conext24-NetConfEval, CoNEXT'24). NetConfBench remains a citation/taxonomy source only.

- **Mon/Wed/Fri (4.5 hr):** Clone `RedHatResearch/conext24-NetConfEval`. Set up its env (Python ≥3.10, `requirements.txt`). Pull the HF dataset `NetConfEval/NetConfEval`. Run `step_1_formal_spec_translation.py` against GPT-4o on a single policy type, `--batch_size 1`, `--n_run 1` to confirm the loop works end-to-end.
- **Sat (3 hr):** Run all three step-1 / step-2 experiments (formal-spec, function-call, code-gen) against GPT-4o with `--n_runs 1` across the full policy set. Save outputs under `runs/2026-06-07_netconfeval_gpt4o/`. Step-3 (low-level configs, requires Docker + Kathará) is **deferred to Week 5** — don't fight it this week.
- **Sun (3 hr):** Read `netconfeval/common/model_configs.py` and the step scripts' grading logic. Document in `harness/grader_notes/netconfeval.md` what each step's pass/fail actually computes (exact-match? AST-equality? Kathará runtime check?). Identify what needs renormalizing to share metric definitions with Cornetto's grader in Week 3.

**Deliverable:** NetConfEval steps 1–2 reproduce on your box; grader internals documented; step-3 (Kathará/Docker) scoped for Week 5.

### Week 3 (Jun 8 – Jun 14) — Reproduce Cornetto (or build equivalent)

- **Mon/Wed/Fri (4.5 hr):** Check Cornetto code release status (ETH NSG GitHub or paper appendix). If released: clone + run. If not released by Jun 8: build an equivalent Batfish-based grader from the paper description for a 10-problem subset of your own making. Don't wait.
- **Sat (3 hr):** Run Cornetto (or your subset) end-to-end against GPT-4o. Save to `runs/2026-06-14_cornetto_gpt4o.json`.
- **Sun (3 hr):** Write `harness/grader_notes/cornetto.md` — formal-verification grader, what it actually checks, what it can't.

**Deliverable:** Config-repair grader running, even if on a smaller problem set than full Cornetto.

### Week 4 (Jun 15 – Jun 21) — Harness skeleton: unified model API

- **Mon/Wed/Fri (4.5 hr):** Build `harness/models/` with a single `Model` interface: `__call__(messages, tools=None) -> Response`. Implement adapters for OpenAI, Anthropic, Google, plus a `LocalVLLM` stub for Llama/Qwen. Implement a `MCPClientModel` adapter that wraps `junos-mcp-server`-style agents so they look like a model to the harness.
- **Sat (3 hr):** Build `harness/runner.py` — given a `Task`, a `Model`, and an `Agent` (single-shot / ReAct / RAG), runs the loop, logs trace, returns `Run` object. Unit-test against one NetConfEval step-1 task.
- **Sun (3 hr):** Build `harness/storage.py` — write each run to `runs/{benchmark}/{model}/{task_id}.json`. Idempotent re-runs. Cache hits.

**Deliverable:** `python -m netbrace.run --benchmark netconfeval --model gpt-4o --task t1` works and writes a result file.

### Week 5 (Jun 22 – Jun 28) — Harness: import NetConfEval fully (incl. step-3 low-level)

- **Mon/Wed/Fri (4.5 hr):** Write `tasks/netconfeval/loader.py` — converts each step's prompts + expected outputs into your normalized `Task` schema (`{id, category, prompt, oracle_inputs, grader_config}`). Cover all four policy types × all three step scripts loadable as distinct task families.
- **Sat (3 hr):** Stand up Kathará + Docker on the MS-A2 box and run `step_3_low_level.py --mode rag` against GPT-4o on the four Kathará scenarios (OSPF single-area, OSPF multi-area, RIP, BGP peering). This is the slow one — start it in the morning. Wire its FRR-runtime grader into `harness/graders/netconfeval.py`.
- **Sun (3 hr):** Re-run last week's GPT-4o results through your harness; numbers should match upstream within rounding. Write `tasks/netconfeval/README.md`. This is paper §3.2 material — keep it polished.

**Deliverable:** All four NetConfEval experiment families run end-to-end inside your harness, scores match upstream.

### Week 6 (Jun 29 – Jul 5) — Harness: import Cornetto + NIKA

- **Mon/Wed/Fri (4.5 hr):** Write `tasks/cornetto/loader.py` for whatever subset you have (full 231 if code released; your subset otherwise). Wire grader.
- **Sat (Jul 4 holiday — light day, 1.5 hr):** Skim NIKA paper one more time; clone their repo if released; pick a 50-task subset that runs on containerlab.
- **Sun (3 hr — absorbs Sat's lost hours, total ~6 hr):** Write `tasks/nika/loader.py` for the 50-task subset. Wire grader. Re-run GPT-4o end-to-end across all three benchmarks.

**Deliverable:** Three benchmarks (NetConfBench, Cornetto-subset, NIKA-subset) all run through the unified harness against GPT-4o.

### Week 7 (Jul 6 – Jul 12) — Harness: MCQ imports (TeleQnA + NetEval) and ReAct agent

- **Mon/Wed/Fri (4.5 hr):** TeleQnA + NetEval MCQ loaders — these are trivial (text in, A/B/C/D out). Just exact-match grader. Sample 500 MCQs from each to keep eval cost finite.
- **Sat (3 hr):** Build `harness/agents/react.py` — a minimal ReAct loop with tool calls (`run_cli`, `read_file`, `apply_config`, `wait`, `done`). Test against one NetConfBench task. Cap steps at 15, tokens at 50k.
- **Sun (3 hr):** Build `harness/agents/single_shot.py` (trivial — already most of what you have). Document the agent contract in `harness/agents/README.md`.

**Deliverable:** All five categories' imports running. Two agents (single-shot, ReAct). One model (GPT-4o) end-to-end on the full v1 imported corpus.

**Mid-summer checkpoint (Sun Jul 12):** if Weeks 2–7 slipped >1 week total, **cut NIKA from v1** and recover in Week 8. Don't carry slip into the safety-axis weeks — those are the novelty and cannot be shortchanged.

### Week 8 (Jul 13 – Jul 19) — Safety axis design + first 50 tasks

- **Mon/Wed/Fri (4.5 hr):** Write `paper/safety_axis_design.md` — formal definition of blast-radius: given proposed config diff `Δ`, ground-truth set `G = {sessions, prefixes, interfaces, services}` that Batfish predicts will be lost or degraded relative to pre-diff state. Define precision, recall, F1 over `G`. Decide whether the model outputs (a) the diff and you compute `G_pred` via Batfish on the diffed config, or (b) the model directly enumerates `G_pred`. **Recommend (a) — harder to game and matches the realistic task.**
- **Sat (4 hr):** Build the task generator: parametric Jinja templates over containerlab topologies + intent templates ("redistribute connected into BGP", "shut interface", "change prefix-list", "reorder route-map clauses"). Generate first 50 (topology, baseline-config, proposed-diff) triples. Run Batfish to compute ground-truth `G` for each. Save to `tasks/safety/v1/`.
- **Sun (2 hr):** Write `tasks/safety/README.md`. Sanity-check 5 tasks by hand: does Batfish's predicted blast-radius match what you'd predict yourself? If <80% agreement, the templates have bugs — fix before scaling.

**Deliverable:** 50 safety tasks with ground-truth, hand-validated.

### Week 9 (Jul 20 – Jul 26) — Safety axis: scale to 300 + grader

- **Mon/Wed/Fri (4.5 hr):** Expand templates to hit 4 protocol families (BGP, OSPF, static, ACL) × ~12 intent templates × ~7 topology variations ≈ 336 tasks. Filter for grader determinism (Batfish must produce same `G` on 3 reruns); drop any nondeterministic ones.
- **Sat (3 hr):** Write `harness/graders/safety.py` — given `Run` (proposed diff) + task's pre-diff config + ground-truth `G`, applies diff, runs Batfish, computes `G_pred`, returns precision/recall/F1.
- **Sun (3 hr):** Smoke-run GPT-4o single-shot on the full 300 safety tasks. Expect ~30–60% F1 — that's the design target (frontier models reliably underperform here because no training data). If F1 >85%, tasks are too easy — increase intent complexity. If F1 <10%, tasks are too hard — simplify.

**Deliverable:** ~300 safety tasks, grader works, GPT-4o baseline lands in 30–60% F1 range.

### Week 10 (Jul 27 – Aug 2) — Behavior-prediction axis (~500 tasks)

- **Mon/Wed/Fri (4.5 hr):** Templated generator for category B: `(config, event) → expected RIB/FIB diff`. Events = link down, prefix advertised/withdrawn, neighbor reset. Ground-truth via Batfish + a tiny container-lab differential check on a 50-task validation slice.
- **Sat (3 hr):** Generate ~500 tasks. Build `harness/graders/behavior.py` — RIB equality on sampled prefix set, structural equality on path attributes. Smoke-run GPT-4o.
- **Sun (3 hr):** Hand-validate 30 tasks. Write `tasks/behavior/README.md`.

**Deliverable:** ~500 behavior-prediction tasks with grader; smoke-run done.

### Week 11 (Aug 3 – Aug 9) — Multi-model fleet: cloud APIs

- **Mon/Wed/Fri (4.5 hr):** Add adapters / API keys / rate-limit handling for: GPT-4o, GPT-4o-mini, Claude Sonnet (latest), Claude Opus (latest), Gemini 2.x Pro. Each gets a smoke test on 5 tasks per category. Log token/cost per task to `runs/_meta/cost_log.csv`.
- **Sat (3 hr):** Kick off **full single-shot run** of all 5 models × all 5 categories (K + C + B + D + S + R). Budget: ~$400–600 total cost. Start it Sat morning so it runs through the weekend; check on it Sun evening.
- **Sun (3 hr):** Triage failures (rate limits, schema errors, OOM on long-context). Re-run failed tasks. Lock results to `runs/sweep_001/`.

**Deliverable:** First full sweep across 5 cloud models, single-shot agent.

### Week 12 (Aug 10 – Aug 16) — Local-model fleet + ReAct sweep

- **Mon/Wed/Fri (4.5 hr):** Stand up vLLM serving for Llama-3.1-70B-Instruct and Qwen-2.5-32B-Instruct on whatever GPU you can borrow (Cisco internal? RunPod? Lambda? Decide by Tue.). Add `vLLMModel` adapter. Smoke-test.
- **Sat (3 hr):** Run both local models, single-shot, all categories. Save to `runs/sweep_002/`.
- **Sun (3 hr):** Kick off ReAct sweep — same models × same categories but with the ReAct agent. This is the expensive run (more tokens per task). Start Sun evening, runs overnight + Monday.

**Deliverable:** Local models scored; ReAct sweep launched.

### Week 13 (Aug 17 – Aug 23) — Commercial agent baseline + first results writeup

- **Mon/Wed/Fri (4.5 hr):** Wrap `junos-mcp-server` as an agent in the harness. Run it on the subset of tasks it can actually attempt (Junos-syntax tasks only — that's the honest comparison). Document the protocol/vendor restriction in `paper/commercial_agents.md`.
- **Sat (3 hr):** Pull all `runs/sweep_*` into one pandas notebook. Build the v0 leaderboard table — model × category × metric. Save to `paper/figures/leaderboard_v0.{png,csv}`.
- **Sun (3 hr):** Write `paper/results_v0.md` — bullets: top-3 headline findings, top-3 surprises, top-3 things that look like grader bugs. **One of these must become the paper's headline finding.** Most-likely candidates per strategy doc §7 Q1'27: "frontier models pass config-synthesis but fail safety" or "commercial network agents under-perform frontier general-purpose LLMs on out-of-distribution protocols."

**Deliverable:** End-of-summer milestone — full harness, full sweep across ≥6 models, commercial-agent baseline, v0 leaderboard, headline-finding shortlist.

**End-of-summer checkpoint (Sun Aug 23):**
- If you have: harness + ≥3 imported benchmarks + safety axis + ≥4 models scored + headline shortlist → **on track**, proceed to Phase 2 with writing focus.
- If you have: harness + ≥2 imported benchmarks + safety axis + 1 model scored → **behind but recoverable**; Phase 2 becomes "finish scoring, write later." Push collaborator outreach to Sep.
- If you have less than that → **descope**: drop Cornetto and behavior-prediction from v1; ship NetConfBench + Safety + MCQ as a tighter HotNets-shaped paper.

---

# PHASE 2 — Final pre-quarter push (Aug 24 – Sep 20, 2026)

> **Goal:** by Sep 20, have (a) full first draft of the paper, (b) all model runs locked, (c) collaborator outreach done.
> **Capacity:** math refresher buffer week Aug 24–30 only, then math done. **NetBrace gets 18–22 hrs/wk for 4 weeks.** Cisco still 40 hrs.
> **Recommended schedule:** weekdays 2 hr eve (10) + Sat 6 hr + Sun 6 hr = 22 hr/wk.

### Week 14 (Aug 24 – Aug 30) — Writing: §1 Intro, §2 Related Work, §3 Methodology

- **Mon–Fri (10 hr):** §1 Intro draft. ½ page hook (a real ops failure — sanitized), ½ page contribution claim (3 bullets: holistic comparative, safety axis, commercial-agent baseline), ½ page paper roadmap. **Single most-rewritten section of the paper — don't over-polish v1.**
- **Sat (6 hr):** §2 Related Work draft. The landscape table from Week 0 becomes the spine. Position against NetConfBench (importing), Cornetto (importing), NetPress (orthogonal — different scope), NIKA (importing subset), HELM (methodology ancestor).
- **Sun (6 hr):** §3 Methodology draft. Sub-sections: 3.1 harness architecture, 3.2 task taxonomy, 3.3 grading (per-category), 3.4 grader-validity (defer numbers to §4). Use the strategy doc §3.4 as the skeleton.

**Deliverable:** `paper/draft_v1/{01_intro,02_related,03_methodology}.md`. Wordcount ≥3.5 pages combined.

### Week 15 (Aug 31 – Sep 6) — Writing: §4 Results, regenerate figures

- **Mon–Fri (10 hr):** Lock results. Rerun any flaky model from Phase 1. Generate final leaderboard table + per-category radar plots. Save publication-quality PNGs/PDFs to `paper/figures/`.
- **Sat (6 hr):** §4 Results draft. Lead with the headline finding. Then per-category breakdown. Then commercial-agent comparison. Then ablations (single-shot vs ReAct).
- **Sun (6 hr):** §4 continued — write the safety-axis subsection at full depth; this is the novelty, do it justice. Include the precision/recall scatter across models + a confusion-style breakdown of which `(sessions, prefixes, interfaces, services)` categories each model misses.

**Deliverable:** `paper/draft_v1/04_results.md` + all final figures.

### Week 16 (Sep 7 – Sep 13) — Writing: §5 Discussion, §6 Limitations, §7 Conclusion + grader-validity human eval

- **Mon–Fri (10 hr):** Hand-label 100 safety tasks for grader validity (this is the §3.4 reviewer-bait number). 2 raters: you + one Cisco engineer who will do it for a coffee debt. Compute Cohen's kappa against the Batfish grader. Target κ ≥0.7.
- **Sat (6 hr):** §5 Discussion + §6 Limitations + §7 Conclusion drafts. Limitations section *must* include: synthetic-only data, vendor coverage limited to 2, no Cisco DNM (or note if it landed), no reasoning-trace step-level grading, no fine-tuned model.
- **Sun (6 hr):** **Collaborator outreach.** With a working demo + draft in hand, email the ≤5 names on `paper/collab_targets.md`. Personalized 6-sentence emails. Attach the leaderboard figure and one paragraph from §1. **Goal: 1 academic co-author signed up by Oct.** If zero responses by end of Sep, escalate via shared Stanford contacts or industry network in Phase 3.

**Deliverable:** Complete §1–§7 draft (~12–14 pages workshop-format, will trim later). Outreach sent.

### Week 17 (Sep 14 – Sep 20) — Internal review, repo cleanup, "freeze v1"

- **Mon–Fri (10 hr):** Self-review the draft top-to-bottom; mark every TODO / `[CITE]` / "verify this number." Fix what you can in 30 min each; ticket the rest in `paper/v1_review_tickets.md`.
- **Sat (6 hr):** Repo cleanup — README, install instructions, `netbrace run --help` works, one example task ships green. Add `LICENSE` (Apache-2.0). Add `CITATION.cff`. Tag `v1.0-draft`.
- **Sun (6 hr):** Hand the draft to 2 readers: (a) a senior Cisco engineer (technical accuracy on the network-engineering claims), (b) a friend in academia or industry who's written workshop papers (does the contribution claim land in 60 seconds?). Give them a 3-week window to return comments (back by ~Oct 11).

**Deliverable:** **v1 frozen.** Draft sent to 2 reviewers. Repo presentable. CS221 starts in 24 hours — pivot mode.

---

# PHASE 3 — Au'26 quarter (Sep 21 – Dec 13, 2026): ease-off

> **Reality check:** CS221 problem sets eat weekends. NetBrace is now in **maintenance mode**: ~4 hrs/wk total, only on the lower-CS221-load weeks.
> **Schedule:** Saturday morning, 3–4 hr block, weekly. **Skip the week of any CS221 midterm or major PS deadline.**

| Week (academic) | Date span | NetBrace activity |
|---|---|---|
| Au wk 1 (Sep 21–27) | CS221 starts | **No NetBrace.** Settle into CS221 rhythm. |
| Au wk 2 (Sep 28–Oct 4) | — | Process reviewer A comments (Cisco eng). |
| Au wk 3 (Oct 5–11) | — | Process reviewer B comments (academia/industry). |
| Au wk 4 (Oct 12–18) | CS221 PS likely | **Skip or 2 hr only.** Triage collaborator-outreach replies. |
| Au wk 5 (Oct 19–25) | — | Identify 1 follow-up experiment from reviewer feedback; run it. |
| Au wk 6 (Oct 26–Nov 1) | CS221 midterm likely | **Skip.** |
| Au wk 7 (Nov 2–8) | — | Apply collaborator's feedback (if signed up). Run any model that's been released since Aug. |
| Au wk 8 (Nov 9–15) | — | Rewrite §1 Intro top-to-bottom; this section *always* needs another pass. |
| Au wk 9 (Nov 16–22) | — | Decide submission venue. Check current cycle deadlines for: NeurIPS LLM-agents/ML-for-Systems/FM-in-the-Wild workshops (likely Aug–Sep, may have closed); ICLR workshops (Jan–Feb); HotNets (late June); NAIC@SIGCOMM (Apr–May); GenAINet (varies). Pick the **next available** with notification before Jun'27. Document choice in `paper/venue_decision.md`. |
| Au wk 10 (Nov 23–29) | Thanksgiving | Light. Reread §4 Results with fresh eyes; line-edit pass. |
| Au wk 11 (Nov 30–Dec 6) | CS221 final approaching | **Skip.** |
| Au wk 12 (Dec 7–13) | CS221 finals week | **Skip.** |
| Winter break (Dec 14–Jan 3) | No quarter | **3 high-leverage days: Dec 19, Dec 27, Jan 2.** Each = full incorporation pass. Add any model released in 2026-Q4. |

**Phase 3 deliverable:** v2 draft with reviewer comments incorporated, venue chosen, ≥1 follow-up experiment added.

---

# PHASE 4 — Wi'27 quarter (Jan 4 – Mar 21, 2027): polish

> **CS224N is heavier than CS221.** Final project = LOR-bait. **Do not let NetBrace eat CS224N project time.**
> **Schedule:** Saturday morning, 2–3 hr block. Weekly.

| Week | Activity |
|---|---|
| Wi wks 1–4 (Jan 4–31) | Final v2 → v3 pass. Rerun model fleet with whatever's SOTA in Jan 2027 (Claude/Gemini/GPT will have moved). Update leaderboard. |
| Wi wks 5–8 (Feb 1–28) | If venue is ICLR workshop: **submit early-Feb.** Polish appendix, reproducibility section, dataset card. arXiv preprint goes live submission day. Repo flips public. |
| Wi wks 9–11 (Mar 1–21) | If submitted: rest from NetBrace. If venue is later (NAIC/HotNets/NeurIPS), continue light polish. |

**Phase 4 deliverable (best case):** workshop submission + arXiv preprint + public repo + Hugging Face dataset card.

---

# PHASE 5 — Sp'27 quarter (Mar 29 – Jun 13, 2027): submit or revise

> **CS229 is the heaviest course.** Per the Stanford plan: an A in CS229 outranks the paper. **If forced to choose, slip the paper to the next workshop cycle.**

| Scenario | Action |
|---|---|
| **Submitted in Wi'27, accepted** | Camera-ready in Sp'27 (typically 2–4 weeks); attend workshop summer 2027. Start CoNEXT/NeurIPS-D&B extension paper outline. |
| **Submitted in Wi'27, rejected** | Address top-3 reviewer concerns. Resubmit to next workshop cycle (HotNets June, NAIC summer). Don't change the thesis. |
| **Didn't submit in Wi'27** | HotNets late-June deadline is the target. April = final experiments, May = writing sprint (10 hrs/wk in May only), early June = submission. |

---

# Appendix A — Math-refresher coordination (Jun 1 – Aug 23)

The math refresher (10 hrs/wk) and NetBrace summer (10–12 hrs/wk) share the same weekday eve / weekend block budget. **Lane discipline:**

| Day | Math block | NetBrace block |
|---|---|---|
| Mon | — | 1.5 hr eve |
| Tue | 1.5 hr eve | — |
| Wed | — | 1.5 hr eve |
| Thu | 1.5 hr eve | — |
| Fri | — | 1.5 hr eve |
| Sat | Afternoon 2 hr (math deliverable) | Morning 3 hr (NetBrace week's main code) |
| Sun | Afternoon 2 hr (math deliverable) | Morning 3 hr (NetBrace week's writing/grader) |

**Hard rule: do not let NetBrace eat a math deliverable, ever.** A missed math week compounds badly (each week builds on the prior); a missed NetBrace week is recoverable. If a week breaks, drop NetBrace scope (one fewer model in this week's sweep, one fewer task batch) — never math.

---

# Appendix B — Decision points / kill criteria

Track these in `progress.md` and revisit each week.

1. **(Week 4, Jun 21):** if reproducing NetConfBench took >2x budget, the rest of the plan is unrealistic — **descope to NetConfBench-only**.
2. **(Week 9, Jul 26):** if safety-axis GPT-4o F1 lands >85% or <10% after task-difficulty tuning, the axis is broken — **rescope the safety category or replace with a different novelty axis** (most likely fallback: reasoning-trace step-level grading per strategy §2.2 #7).
3. **(Week 13, Aug 23):** if no headline finding has emerged from the v0 leaderboard, the comparative thesis is at risk — **shift framing** to a measurement paper around safety alone ("frontier LLMs cannot predict blast-radius of network changes"), which is still publishable as a HotNets short paper.
4. **(Week 16, Sep 13):** if zero collaborator-outreach responses, **escalate via shared contacts**, not by sending more cold emails.
5. **(End of Au'26 quarter):** if CS221 grade is at risk (any homework <A-), **suspend NetBrace entirely for Wi'27** and accept HotNets June'27 as the submission target.
6. **(Sp'27, anytime):** if CS229 grade is at risk, **slip the paper one cycle.** No exceptions. The transcript line is worth more to Stanford admission than any one workshop paper.

---

# Appendix C — Cost / resource budget

| Item | Estimate | Notes |
|---|---|---|
| Cloud LLM API spend (Phase 1+2) | $800–$1500 | Most in Weeks 11–12 + Wi'27 rerun. Get Cisco to expense if possible; if not, personal. |
| GPU rental for Llama/Qwen | $200–$500 | RunPod/Lambda spot. Or borrow Cisco GPU. |
| Workstation upgrades | $0–$500 | Existing box should suffice; +32 GB RAM iff Batfish OOMs at scale. |
| Conference reg / travel (if accepted) | $1000–$2500 | Workshop registration + travel — often Cisco-expensable for first-author paper with Cisco affiliation. Confirm policy now. |
| **Total out-of-pocket worst case** | **~$5000** | Worth it. |

---

# Appendix D — What success looks like by Sep 20, 2026

Checklist for the Phase 2 freeze:

- [ ] Repo `~/netbrace/` has a working `netbrace run` CLI.
- [ ] ≥5 cloud models + ≥2 local models scored across ≥4 categories.
- [ ] Safety axis: ~300 tasks, hand-validated, GPT-4o F1 in 30–60% range.
- [ ] Behavior axis: ~500 tasks, smoke-run done.
- [ ] At least one commercial agent (junos-mcp-server) scored on its valid subset.
- [ ] Draft paper §1–§7 complete, ≥12 pages.
- [ ] 100-task safety grader-validity human eval done, κ reported.
- [ ] Collaborator outreach emails sent to ≤5 targets.
- [ ] Repo has README, LICENSE, CITATION, example task.
- [ ] 2 internal reviewers have the draft.
- [ ] Cisco DNM data-release ticket: status known (approved / pending / denied).
- [ ] `progress.md` shows ≥17 weekly entries with deliverables.

Hit ≥9/12 → on track. Hit ≥6/12 → workshop-paper-viable but tight. <6/12 → descope per Appendix B kill criteria.
