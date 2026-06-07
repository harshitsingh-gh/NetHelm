# HotNets 2026 Sprint Plan — Jun 4 → Jul 15, 2026

> **Created:** 2026-06-04
> **Deadline:** July 16, 2026 (HotNets 2026 submission)
> **Format:** Position paper, ~6 pages, networking audience
> **Venue:** HotNets 2026 — Workshop on Hot Topics in Networks, Nov 16–17 Salt Lake City
> **Why this matters:** HotNets explicitly rewards novel, speculative, thought-provoking early-stage work. The safety/blast-radius angle is confirmed open (no competitor paper as of Jun 2026). A position paper framing + preliminary Batfish results is sufficient. This is the fastest credible path to a published paper.

---

## The paper

**Working title:** "Can LLMs Predict the Blast-Radius of Network Configuration Changes? A Preliminary Evaluation"

**Thesis:** LLMs are being used to generate and apply network configuration changes, but their ability to predict the downstream topological impact of those changes — which sessions drop, which prefixes become unreachable — is completely unevaluated. We introduce a Batfish-based evaluation framework for this task and show preliminary results that frontier models fail at it.

**Contribution claim (3 bullets):**
1. We formalize the **network change blast-radius prediction** task: given a proposed config diff, enumerate the set {sessions, prefixes, interfaces, services} that Batfish predicts will be lost or degraded.
2. We introduce a small evaluation set (preliminary: ~20–50 hand-crafted tasks) with automatically gradeable ground truth from Batfish.
3. We show that GPT-4o (single-shot) performs poorly on this task (target: F1 ~30–60%), establishing a baseline and motivating the full NetBrace safety category.

**Why HotNets:** This is a 6-page position paper. We don't need the full 300-task set or the complete model fleet. We need a clear framing + a real preliminary result + a compelling argument for why this matters to the networking community.

---

## Sprint scope (what we're building in 6 weeks)

### What we need for the paper
- [ ] 20–50 safety tasks with Batfish ground truth (not 300)
- [ ] GPT-4o evaluation on those tasks
- [ ] One figure: precision/recall scatter or F1 bar chart per task type
- [ ] Paper draft: §1 Introduction, §2 Background/Gap, §3 Framework, §4 Preliminary Results, §5 Discussion

### What we are explicitly NOT building for HotNets
- The full normalized harness (Weeks 4–7 per execution plan)
- Full model fleet (save for NeurIPS workshop paper)
- NetConfEval reproduction (still useful for NeurIPS, defer for HotNets)
- Cornetto import (defer)
- NIKA import (defer)

---

## Week-by-week plan

### Week A: Jun 4–7 (this week — ~10 hrs available)
**Pivoting from NetConfEval reproduction to safety task creation**

- **Mon/Tue (3 hr):** Write `tasks/safety/generate_v0.py` — a parametric Jinja template generator that produces (topology, baseline-config, proposed-diff) triples. Start simple: BGP-only, FRR topology, 4 intent types:
  - `shut_neighbor`: shut a BGP neighbor → which sessions drop, which prefixes are lost
  - `add_prefix_filter`: add a deny prefix-list → which prefixes are filtered
  - `change_local_pref`: change LOCAL_PREF → does traffic shift, any loop?
  - `remove_network_statement`: remove a `network` statement → which prefixes are withdrawn

- **Wed/Thu (3 hr):** Wire Batfish to compute ground truth for each generated triple. Store as `tasks/safety/v0/{task_id}.json` with schema: `{topology, pre_config, proposed_diff, ground_truth: {sessions_lost, prefixes_lost, interfaces_affected}}`.

- **Fri/Sat (4 hr):** Generate first 20 tasks. Run Batfish on all 20. Hand-validate 5: does the Batfish prediction match what you'd expect?

**Deliverable:** 20 safety tasks with Batfish ground truth, 5 hand-validated.

### Week B: Jun 8–14 (~10 hrs)

- **Mon/Wed (3 hr):** Write `harness/graders/safety_simple.py` — given a model's predicted set of (sessions_lost, prefixes_lost), compute precision/recall/F1 against ground truth.

- **Sat (4 hr):** Write `harness/eval_gpt4o_safety.py` — single-shot GPT-4o evaluation on the 20 tasks. Prompt template: show the topology description + proposed diff, ask "which BGP sessions will be lost? Which prefixes become unreachable?" Parse model output, run grader. Save to `runs/2026-06-14_gpt4o_safety_v0/`.

- **Sun (3 hr):** Run the evaluation. Compute F1 per task, overall. Check if result is in the 20–70% F1 range (useful result). If >80%, tasks are too easy — make harder. If <10%, tasks are too hard or the prompt is wrong.

**Deliverable:** GPT-4o baseline scores on 20 safety tasks, saved.

### Week C: Jun 15–21 (~10 hrs)

- **Mon/Wed (3 hr):** Scale to 50 tasks. Add OSPF-based tasks (link-down event → which routes are withdrawn) if FRR lab supports it. Add one more model: Claude Sonnet. Run both.

- **Sat (4 hr):** Build the figure: F1 comparison (GPT-4o vs Claude) per task type as a bar chart. Export as PDF. Store in `paper/figures/`.

- **Sun (3 hr):** Write §3 Framework draft (task formalization, Batfish as oracle, grading methodology).

**Deliverable:** 50 tasks + 2-model baseline + figure + §3 draft.

### Week D: Jun 22–28 (~10 hrs)

- **All week:** Write the paper. Structure:
  - §1 Introduction: hook (a real outage caused by a misconfigured BGP policy), gap statement, contribution bullets, roadmap
  - §2 Background: network change management today, LLMs entering the loop, what "blast radius" means in this context, why existing benchmarks don't measure this
  - §3 Evaluation Framework: task formalization, Batfish oracle, grader, dataset statistics
  - §4 Preliminary Results: F1 scores, failure mode analysis (which kinds of changes do models get wrong?)
  - §5 Discussion + Future Work: how this extends to the full NetBrace safety category, invitation for the community to build on this

**Deliverable:** Full draft v0 of the 6-page paper. Run `/critique` on it.

### Week E: Jun 29 – Jul 5 (~8 hrs — holiday weekend)

- Incorporate critique findings. Address the top 3 BLOCKER items.
- Run `/lit-scan` to confirm no new competitor has appeared.
- Send draft to 1 internal reviewer (senior Cisco engineer, technical accuracy check).

**Deliverable:** Draft v1 circulating to reviewer.

### Week F: Jul 6–12 (~10 hrs)

- Process reviewer feedback.
- Polish: tighten §1, verify all numbers, check all citations.
- Run `/critique` again on final draft.
- Finalize figures (publication quality PDF/PNG).
- Write `paper/hotnets2026/abstract.md` for the submission system.

**Deliverable:** Submission-ready draft.

### Week G: Jul 13–15 (2–3 hrs buffer)
- Final pass. Submit July 15 (1 day before deadline — never submit on deadline day).

---

## What happens after HotNets

- If accepted: camera-ready Oct 23. Talk prepared for Nov 16–17. This is the "public talk" artifact.
- If rejected: revise with reviewer feedback → submit to NeurIPS 2026 workshop (Aug 29) with more results. Rejection from HotNets is normal — position papers have high variance.
- Regardless: arXiv preprint goes up on submission day (Jul 15). Citations accumulate independently of acceptance.

---

## Tools to use (no building from scratch)

- **Batfish**: already running for ground truth computation
- **Inspect AI** (UK AISI inspect-ai package): evaluate whether it can replace custom harness code for the GPT-4o/Claude evaluation loop. `pip install inspect-ai`. If it can replace `eval_gpt4o_safety.py` in <2 hrs, use it.
- **pybatfish + Jinja2**: template generation already proven in the lab
- **anthropic SDK + openai SDK**: direct API calls for model evaluation

---

## Risk register

| Risk | P | Mitigation |
|---|---|---|
| Batfish doesn't support all the diff types we need | Medium | Test the shut_neighbor and add_prefix_filter cases this week; if Batfish struggles, narrow to BGP-only |
| GPT-4o scores >80% F1 (tasks too easy) | Low | Make diffs more complex (multi-hop impact, multi-vendor) |
| GPT-4o scores <10% F1 (prompt/task design broken) | Medium | Hand-trace one failure, fix the prompt template |
| A competitor paper appears before Jul 15 | Low | Run `/lit-scan` weekly; if competitor appears, pivot the HotNets paper to comparative framing |
| Math refresher conflict | Low | This sprint uses Mon/Wed/Fri + Sat AM. Math gets Tue/Thu + Sat PM + Sun AM. Lane discipline holds. |
| Cisco crunch takes the sprint | Medium | If >3 days lost: narrow to 20 tasks only, drop OSPF tasks, submit with GPT-4o only |
