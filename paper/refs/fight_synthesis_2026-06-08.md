# Fleet Fight — Synthesis & Decided Roadmap (2026-06-08)

> Turn-based adversarial debate over the whole NetHELM design. Round 1: attackers
> (network-architect, ml-eval-engineer) — both web-researched current practice.
> Round 2: defenders (batfish-oracle-engineer, scenario-author) + adjudicator
> (research-standards-reviewer, venue-calibrated to HotNets-first / NeurIPS-ED-later).
> This is the decided outcome. Full attacks/defenses are in the agents' transcripts;
> this is the spine.

## The verdict everyone converged on
The infrastructure + determinism rigor are publication-grade; the **framing
overclaimed** and two flagship details were wrong. Keep the task (damage-set
prediction) as the substrate, **promote the trap/calibration metric to co-headline**
(it is the genuine moat — NetPress/NetArena score action-safety, NIKA does
diagnosis, NetConfBench does synthesis; **none score hallucinated/false-positive
damage from a diff**). Do NOT pivot to intent-relative correctness or a full tools
arm — that abandons the one novelty for two crowded fronts before the deadline.

## CRITICAL PATH (adjudicator's HotNets-first ordering)
**MUST-FIX before submit:**
1. **NetPress == NetArena citation** (same paper, arXiv:2506.03231) — factual error. [DONE this session]
2. **clos_summary RFC 7938 claim** — the §5.2.3 mechanism needs a *link failure*; ours
   bakes a permanent spine2↔leaf3 gap. Cheap fix = relabel honestly (cite §3.2.2
   one-path property; drop the link-failure framing) [DONE this session]. Proper fix
   (queued) = symmetric Clos + `fork_snapshot(deactivate_interfaces=…)` link-down so
   it IS the §5.2.3 mechanism (oracle-engineer confirmed feasible w/ installed pybatfish).
3. **Modal-by-class baseline + oracle ceiling** — the validity floor; if LLMs don't
   beat "predict the modal blast for this class," the benchmark measures nothing.
   (Blocked on having ≥N instances/class → lands with the generators. Oracle-ceiling
   = the fake-echo, already exists.)
4. **N≥5 sweep, per-dimension mean±std aggregated AT THE SCENARIO LEVEL** (not pooled
   i.i.d.). This one sweep kills the single-sample gap, fixes stats *correctly without
   overkill*, produces the trap RATE, and replaces the pass/fail lottery with the
   per-dimension table. (Needs the $1000 model fleet; build the harness first.)
5. **false_session_alarm-RATE (±std) as the thesis figure** — aggregation already in
   `reporting.summarize_extended`; make it the headline number.
6. **Drop / mark-qualitative the unscored `reasoning` field** [DONE: kept CoT but
   documented unscored-qualitative — CoT helps models; the flank was "solicit-but-
   don't-score," closed by documenting].
7. **One scoping paragraph** ("static steady-state blast radius; transients out of
   scope") + **faithfulness-tier** per scenario + cut D8 scale CLAIMS to Tier-D
   "spec-annotated." [scoping + tiers DONE this session]

**SHOULD-FIX (HotNets-nice / NeurIPS-ED-must):**
- Tolerant/graded scorer (partial credit, severity weights) + report strict-vs-tolerant gap.
- Contamination: templated/held-out PRIMARY split + GROUNDED (incident) split reported
  separately + a perturbation-gap probe. (Lands with the generators.)
- Intent-as-first-class: add `IntentInvariant` + `IntentViolation` element (captures
  the `ipc_aggregate` "reachable but TE-intent broken" case the taxonomy can't). ~1 day.
- Idiomatize non-idiomatic ground truth: the lp_waypoint static-/30 iBGP next-hop
  plumbing → ship an eBGP idiomatic twin (or disclose as Tier-B). Don't buy cEOS yet.
- 5-axis taxonomy as a PAPER-PRESENTATION relabel (reachability / policy-intent /
  control-plane-integrity / blast-amplification / resilience-margin) — cosmetic,
  zero oracle change; add a blast-amplification derived metric (|D2∪D9|/|D1|).

**DO NOT (ruled overreach / over-pivot):**
- No two-stage hierarchical/Bayesian clustered bootstrap for HotNets (scenario-level
  mean±std is enough).
- No re-architecting D1–D9 into 5 axes in code (relabel in the paper only).
- No renaming away from "blast radius" (industry term + the hook) — scope it instead.
- No tools/agent arm or intent-relative-correctness pivot for v1 (future work).
- No hyperscale topology rebuilds (tier + scope claims instead).
- No LLM-judge-scored reasoning on the critical path (κ-validation project; defer).

## The honest paper sentence (defensible at HotNets after must-fixes 1–6)
"NetHELM introduces a Batfish-grounded, multi-dimensional scoring surface for the
steady-state blast radius of network config changes, and shows current LLMs — strong
on direct data-plane effects — systematically hallucinate BGP session loss and miss
second-order control-plane consequences at a measured rate (mean ± std, N≥5), failure
modes a session-only grader cannot surface and a modal-class baseline does not exhibit."

## KEEP (both sides agreed — don't burn the good)
Determinism doctrine (pinned digest + ≥10× gate + ship-snapshots); the TRAP mechanism
(the real novelty); local-fault scenarios; honesty-ledger discipline; tolerant parser;
canon normalization; frozen `sets.py`; D6 deferral; prompt-hygiene CI lint;
frequency-weighting.
