# Ultra-review 2026-06-15 — aggressive multi-lens adversarial review (impl + paper)

7 hostile lenses (gaming, distinctness, oracle, methodology, standards, reality, paper-claims)
tore into the entire quiet-half implementation (13 generators + oracle + tests) and the paper
(`netbrace_tr.tex` + refs), reproducing on the live oracle. Verify pass partly cut short by a
session limit; the CRITICALs below are cross-lens-corroborated and/or reproduced from committed
artifacts. **Verdict: implementation is individually sound; the benchmark-as-a-measurement and the
paper are NOT yet — all fixable, and caught BEFORE wiring into the paper/sweep.**

## CONFIRMED CRITICALs

- **C1 — Damage-half ground truth is a constant; the headline metric is saturable.** Every bypass
  fires byte-identical `{waypoint, intent}`; every no_op empty (proven by the `runs/oracle_verify_*`
  artifacts). A blind "always predict {waypoint,intent}" predictor scores **damage-macro = 1.000**;
  "models score 0.00" only shows models default to empty under uncertainty — cannot distinguish
  "can't reason" from "stayed silent". One-sentence desk-reject. [gaming CV-1, CV-4]
- **C2 — D10 (intent) is a 1:1 copy of D4 (waypoint)** — one bit reported as two dimensions.
  [CV-4, independently CONFIRMED_MATERIAL]
- **C3 — Positional tell defeats the no_op control on `nexthop_elim` + `community_lp`** (bypass edits
  the waypoint node, no_op edits a different node) → a "diff touches the intent's node" heuristic
  solves them with zero routing reasoning. [MD-03 CONFIRMED_MATERIAL/CRITICAL; standards F5]
- **C4 — `igp_metric`, `igp_summary`, `rr_bestpath` present the model a byte-identical `ip ospf cost
  10->200` diff** → indistinguishable model-facing inputs; "13 cause-distinct" collapses toward ~9.
  [MD-01, CV-6, reality F1]
- **C5 — `origin_code` fires for the WRONG mechanism**: bgpRib proves the winner flips on MED 200->50,
  not ORIGIN; the diff bundles a SET_MED teardown. The `runs/` verification only checks the
  signature + determinism, never the *cause* → it rubber-stamps a mislabeled mechanism. [CV-3, MD-04,
  standards F4, reality F3, paper F7 — every lens]
- **C6 — The 13 generators are orphan code; the published headline rests on the OLD 6-reseed
  `leak_ms_reroute`** (one mechanism). The F3 table is not reproducible from committed artifacts for
  6/8 models; significance (paired t, p=0.045) is over 6 near-clones of one mechanism. [EVAL-01,
  EVAL-04, CV-8, standards F1/F3, paper F1/F2]
- **C7 — Grader-dependent on an unvalidated D4/D10 canonicalization; Cohen's κ≥0.7 NOT done.**
  [standards F2, paper F1, EVAL-09]

## HIGHs
- Waypoint check is forward-only + all-or-nothing-ECMP → the silent-reroute / security framing
  overclaims; scope to "forward strict-path waypoint violation". [MD-05, standards F6, paper F5]
- No human-expert hardness baseline → "models fail" is uninterpretable. [paper F8]
- Determinism gate never run on the no_op controls. [CV-7]

## GENUINELY SOLID (conceded by the reviewers)
- Incident grounding strong + honest — every load-bearing citation web-verified checks out; corpus
  self-flags war-story vs documented. Novelty holds; no concurrent scoop. [reality lens, standards F9]
- Individual configs correct, idiomatic, convergent-as-intended. [MD-08]
- `redistribute_ad` + `agg_collapse` are genuinely distinct, real keep-mechanisms; `igp_metric` is
  the robust flagship (blind baseline = 0.000 on it). [reality F7]

## PRIORITIZED FIXES
1. **C1/C2 (metric):** drop the damage-only macro on a one-bit task; require the model to name the
   NEW egress/path/causal line (instance-specific GT a constant can't guess), or report a balanced
   trap-vs-no_op decision (balanced-accuracy/MCC; constant = 0.5). Collapse or differentiate D10.
2. **C3 (tells):** rebuild `nexthop_elim` + `community_lp` to edit the SAME node+construct (the
   `igp_metric` standard); randomize node names so the role index isn't recoverable; report a
   blind-baseline floor as a mandatory number.
3. **C5:** drop or rebuild `origin_code` single-cause; ADD a cause-assertion to the verification
   harness (which attribute decides), not just the signature.
4. **C4:** present igp_metric/igp_summary/rr_bestpath by control-plane LOCUS honestly, or
   differentiate the model-visible diff; don't count as 3 independent tasks.
5. **C6/C7:** wire the 13 into the sweep + run the fleet before any "class" claim; do the κ study;
   recompute stats over distinct mechanisms (not reseeds); make every table artifact-reproducible.

Full per-finding detail + reproductions: workflow run wf_9eb31fb2-e5c (transcript dir under the
session subagents/workflows/). Verify pass to be completed after the session-limit reset.
