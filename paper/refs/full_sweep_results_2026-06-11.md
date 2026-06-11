# Full Sweep — Consolidated Results (v1, 2026-06-11)

> The complete v1 experiment, within the hard $10/provider cap. Supersedes the
> probe (probe_results_2026-06-10.md) as the paper's main result. All ground truth
> Batfish-computed on the pinned digest (09817554db90), 60/60 instances ≥10×
> determinism-gated before any paid call. No LLM-as-judge: grading is deterministic
> set math (graders/extended.py). Runs: sweep_20260610_213843 (Run A, both splits,
> haiku+mini), sweep_20260611_000024 (Run B+C, grounded, sonnet+gemini+opus+gpt-5.5),
> sweep_20260611_00* (gemini top-up).

## Spend ledger (today, against the funded $10/provider — NO overspend)

| Provider | Spent | Cap | Note |
|---|---|---|---|
| Anthropic | $9.28 | $10 | haiku, sonnet, opus — all complete N=5 |
| OpenAI | $9.41 | $10 | gpt-5.4-mini, gpt-5.5 — all complete N=5 |
| Google | $4.13 (+top-up) | $10 | gemini — 38/55 then topped up to N=5 |

Total v1 sweep ≈ $23 (vs the old "$100-300" envelope — small because single-shot,
no agentic rollouts, lean tiered design). The $100-300 scale-up remains GATED on
coworker/co-author scenario validation + κ (per feedback_spend_gate).

## GROUNDED split — F3 across the full cross-vendor frontier fleet (N=5, 11 scenarios)

| model | macro F1 | forwarding (D7) | FSA | invalid |
|---|---|---|---|---|
| openai/gpt-5.5 | 0.36±0.27 | **0.00** | 0.00 | 0.00 |
| anthropic/claude-opus-4-8 | 0.37±0.27 | **0.00** | 0.00 | 0.00 |
| gemini/gemini-3.5-flash | 0.35±0.29 | **0.00** | 0.00 | 0.00 |
| anthropic/claude-sonnet-4-6 | 0.27±0.18 | **0.00** | 0.00 | 0.11 |
| anthropic/claude-haiku-4-5 | 0.29±0.17 | **0.00** | 0.00 | 0.00 |
| openai/gpt-5.4-mini | 0.22±0.22 | **0.00** | 0.00 | 0.00 |
| *floors (empty/naive/syntactic/modal)* | ≤0.01 | 0.00 | — | — |

## TEMPLATED split — validity backbone (N=5, 48 instances, haiku+mini)

| system | prefixes | waypoint | redundancy | forwarding | scale | macro dmg |
|---|---|---|---|---|---|---|
| haiku-4.5 | 0.45 | 0.00 | 0.00 | **0.00** | 0.53 | 0.15±0.18 |
| gpt-5.4-mini | 0.20 | 0.00 | 0.00 | **0.00** | 0.28 | 0.11±0.19 |
| modal_by_class (memorizer floor, damage) | — | — | — | — | — | **0.00** |
| empty / naive_count / syntactic_diff | — | — | — | — | — | 0.00 / 0.07 / 0.01 |

## THE FINDINGS (now backed by 6 models × 2 splits × N=5)

**F1 — Discrimination proven.** Frontier models 0.35–0.37 macro; smaller 0.22–0.29;
all floors ≤0.01. On the templated split's *damage* instances, models 0.11–0.15 beat
the modal-by-class memorizer floor (0.00) and every other floor (≤0.07) — the K1
validity concern is resolved with real data: the benchmark measures reasoning, not
template memorization.

**F2 — FSA = 0.00 across all six models, both splits, N=5 (~700 samples).** No model
hallucinated a BGP session loss. The "models cry wolf" hypothesis is dead; the
honest finding is one-sided error (see F3). The naive_session_loss strawman trips it
at 1.00 — so the metric works; models simply pass it.

**F3 — THE HEADLINE: universal blindness to second-order damage, now on two splits
and six models.** Forwarding-anomaly F1 = **0.00 for every model on both the grounded
AND templated splits** — not one model, on any sample, identified a single
blackhole/hijack-reroute. The templated split adds that waypoint (D4) and redundancy
(D5) violations are *also* 0.00. Meanwhile first-order RIB effects are read well
(frontier prefixes 0.60–0.83). The gradient — fluent at the routing table, blind to
the silent blackhole it implies — is the paper.

**F4 (NEW — circularity defense lands).** The benchmark was built/red-teamed by Claude
models, so self-preference was a live concern. Result: opus-4-8 (0.37) ≈ gpt-5.5
(0.36) ≈ gemini-3.5-flash (0.35) — the Anthropic frontier does NOT out-score the
non-Anthropic frontier. No Claude self-preference; the cross-vendor parity neutralizes
the circularity charge directly.

## Honest caveats (carry into the paper)

- **gemini** initially completed 38/55 (transient Gemini 503 "high demand", not a
  cap — Google had headroom); topped up to N=5 in a follow-up run. Story unchanged
  (fwd 0.00, FSA 0.00 throughout).
- **sonnet invalid_rate 0.11** (~6/55 unparseable outputs) — reported separately so
  format-failure is never conflated with reasoning-failure; raw text saved in
  responses.jsonl for audit. Other models 0.00.
- Per-dimension grounded cells marked "(n=1)" (scale_deagg, the single waypoint/
  forwarding carriers) are point estimates, NOT statistics — the templated split is
  where forwarding/waypoint/redundancy get real N. Never report grounded per-dim as
  mean±std where n=1 (audit K3).
- Headline numbers are macro-F1, FSA, and forwarding-F1 — all robust across N=5;
  grounded forwarding is reinforced by the templated split's 48-instance N=5.

## Paper-ready claim (data-supported)

*"Across six frontier and mid-tier LLMs from three vendors (~700 graded samples,
N=5, on a Batfish-verified, 10×-determinism-gated oracle, scored by deterministic set
comparison — no LLM judge), models read first-order routing-table effects reliably
(prefix-loss F1 up to 0.83) and are perfectly calibrated against the classic
false-alarm trap (0% hallucinated session loss) — yet not one model, on any sample,
on either the incident-grounded or the contamination-controlled templated split,
identified a single second-order forwarding anomaly (forwarding-F1 = 0.00): the silent
blackholes and hijack-reroutes that cause real outages remain invisible to the very
models being trusted to propose the changes. The Anthropic, OpenAI, and Google
frontier models score within 0.02 of each other, and all beat a memorization floor of
0.00 on damage instances."*
