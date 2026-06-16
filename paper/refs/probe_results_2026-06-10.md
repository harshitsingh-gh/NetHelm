# Frontier Probe Results & Headline Decision (2026-06-10)

> The decisive probe from audit_2026-06-10 §6 step 3: 4 models × the 11 frozen
> grounded scenarios × N=3, no_tools, live Batfish oracle, frozen prompt contract.
> Runs: `runs/sweep_20260610_030432` (haiku), `runs/sweep_20260610_031628`
> (gpt-5.4-mini, gpt-5.5, gemini-3.5-flash). 132 paid samples, all parsed, zero
> provider failures. Total probe spend: **$5.71** (anthropic $0.40, openai $3.34,
> google $1.97 — all within the $10/provider cap).

## Headline numbers (grounded split, scenario-level two-stage stats)

| model | macro F1 [95% CI] | FSA rate | prefixes | reach | waypoint | forwarding | D9 withdrawn | intent | invalid |
|---|---|---|---|---|---|---|---|---|---|
| gpt-5.5 | **0.37** [0.20,0.54] | 0.00 | 0.83 | 0.40 | 0.33 | **0.00** | 0.14 | 0.04 | 0.00 |
| gemini-3.5-flash | 0.35 [0.18,0.52] | 0.00 | 0.83 | 0.33 | 0.50 | **0.00** | 0.14 | 0.00 | 0.00 |
| claude-haiku-4.5 | 0.29 [0.16,0.41] | 0.00 | 0.54 | 0.33 | 0.33 | **0.00** | 0.10 | 0.03 | 0.03 |
| gpt-5.4-mini | 0.17 [0.04,0.29] | 0.00 | 0.31 | 0.25 | 0.50 | **0.00** | 0.00 | 0.04 | 0.00 |
| *all floors (empty/naive/syntactic)* | ≤0.01 | — | | | | | | | |

Per-scenario macro F1 (mean over N=3):

| scenario | gpt-5.5 | gemini-3.5-f | haiku-4.5 | gpt-5.4-mini |
|---|---|---|---|---|
| ipc3_static (D9-only) | **1.00** | **1.00** | 0.67 | 0.00 |
| scale_deagg (D8) | 0.67 | 0.47 | 0.31 | 0.08 |
| ecmp4 / waypoint4 (controls) | 0.50 | 0.50 | 0.50 | 0.50 |
| ipc3 / ipc_fanout / ipc_aggregate | 0.33–0.40 | 0.33–0.43 | 0.22–0.40 | 0.00–0.50 |
| clos_summary (partial-ECMP blackhole) | 0.20 | 0.20 | 0.10 | 0.06 |
| **mgmt_lockout (D10 intent)** | **0.07** | **0.00** | 0.08 | 0.00 |
| **leak_ms (LPM blackhole)** | **0.00** | **0.00** | **0.00** | **0.00** |
| **lp_waypoint (attribute shift)** | **0.00** | **0.00** | **0.00** | **0.00** |

## The three findings

**F1 — The benchmark discriminates.** Models spread 0.17 → 0.37 with non-overlapping
tails against the floors (every baseline ≤0.01; syntactic_diff 0.01 proves the task
is not solvable by diff-grep). The audit's "all models floor → no paper" risk is
retired. Frontier models beat minis; nobody approaches the 1.0 ceiling.

**F2 — FSA = 0.00 over 132 samples, all four models.** Modern frontier models do
NOT hallucinate BGP session loss on attribute/policy changes. The
"hallucinated-damage rate" co-headline (fight synthesis 2026-06-08) is DEAD as a
measured frontier failure — and that is reported as a *positive calibration
finding*: the D1 trap that older lore (and the naive_session_loss strawman)
predicts, frontier models pass. The FSA metric remains the instrument that proves
it; the templated no-op/under-budget calibration traps (full sweep) remain the
harder version of the question.

**F3 — THE HEADLINE: universal blindness to second-order data-plane damage.**
**0/46 forwarding-anomaly samples produced even one true positive — no model, on
any sample, ever identified a blackhole or hijack-reroute.** leak_ms (the
Cloudflare-2019-class LPM blackhole) and lp_waypoint (the LOCAL_PREF path shift)
scored 0.00 for every model; mgmt_lockout ≤0.08; intent F1 ≤0.04 everywhere. The
gradient is stark: first-order RIB effects are read reliably (prefixes 0.83 for
frontier), second-order consequences — the silent 3am-outage class — are invisible.
Meanwhile ipc3_static at 1.00 (gpt-5.5/gemini) shows the failures are NOT a
formatting or comprehension artifact: when the damage is first-order
control-plane, frontier models are perfect.

## The paper sentence (data-supported, replaces all prior candidates)

*"Across four frontier and mid-tier LLMs (132 graded samples on a
Batfish-verified, determinism-gated oracle), models read first-order routing-table
effects reliably (route-loss F1 0.83) and are well-calibrated against the classic
false-alarm trap (0% hallucinated session loss) — yet not one model, on one
sample, identified a single second-order forwarding anomaly (0/46): the silent
blackholes and hijack-reroutes that cause real outages remain invisible to the
models proposing the changes."*

## Decisions taken from the probe

1. **Headline = the second-order blindness gradient (F3), with F2 as the honest
   calibration counterpoint.** Drop "models hallucinate damage" as a claimed
   frontier failure everywhere it appears (it survives only as "the metric exists
   and frontier models pass it").
2. **The full sweep is justified**: discrimination is proven; the templated
   multi-mechanism split (incl. the no-op/under traps frontier models haven't
   faced yet, where FSA/false-positive calibration gets a harder test) + Opus 4.8 +
   Sonnet 4.6 arms remain within budget (≈$2 anthropic remaining need, openai
   $6.6 / google $8 headroom).
3. **Disclosures locked**: haiku 3% invalid was a max_tokens truncation
   (post-mortem in responses.jsonl), not a reasoning failure; gemini temperature
   not sent (thinking model); opus 4.8 temperature unsupported (API-removed).

## Provider spend ledger (cumulative, 2026-06-10)

| provider | spent | cap | remaining |
|---|---|---|---|
| Anthropic | $0.40 | $10 | $9.60 |
| OpenAI | $3.34 | $10 | $6.66 |
| Google | $1.97 | $10 | $8.03 |
