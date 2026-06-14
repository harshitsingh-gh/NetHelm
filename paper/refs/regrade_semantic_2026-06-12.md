# Semantic regrade — old (exact-string) vs new (semantic) grader

Generated: 20260614_044753  |  script: `scripts/regrade_semantic.py`  |  spec: `docs/semantic_grading_spec_v1.md` (FROZEN)

NO paid API calls; regraded from saved artifacts only. Aggregation = two-stage scenario-level (per-instance mean over N=5 samples, then mean±std across instances), per split, never pooled. macro dmg = damage-detection macro over NON-EMPTY-truth instances only.


## Split: grounded

### Headline macro-F1 (old → new) + key dims

| system | macro old | macro NEW | macro dmg old | macro dmg NEW | FSA old | FSA NEW | invalid |
|---|---|---|---|---|---|---|---|
| claude-opus-4-8 | 0.37±0.27 | **0.51±0.17** | 0.37 | **0.51** | 0.00 | 0.00 | 0.00 |
| gpt-5.5 | 0.36±0.27 | **0.48±0.17** | 0.36 | **0.48** | 0.00 | 0.00 | 0.00 |
| gemini-3.5-flash | 0.36±0.28 | **0.49±0.18** | 0.36 | **0.49** | 0.00 | 0.00 | 0.00 |
| claude-sonnet-4-6 | 0.30±0.17 | **0.42±0.06** | 0.30 | **0.42** | 0.00 | 0.00 | 0.00 |
| claude-haiku-4-5-20251001 | 0.29±0.17 | **0.39±0.10** | 0.29 | **0.39** | 0.00 | 0.00 | 0.00 |
| gpt-5.4-mini | 0.22±0.22 | **0.27±0.21** | 0.22 | **0.27** | 0.00 | 0.00 | 0.00 |
| deepseek-v4-pro | 0.31±0.18 | **0.44±0.08** | 0.31 | **0.44** | 0.00 | 0.00 | 0.00 |
| kimi-k2.6 | 0.36±0.10 | **0.42±0.06** | 0.36 | **0.42** | 0.00 | 0.00 | 0.00 |

### Per-dimension mean F1 — old vs NEW (the dimensions the artifact hit)

| system | grader | prefixes | reachability | waypoint | forwarding | bgp_withdrawn | intent | redundancy | scale |
|---|---|---|---|---|---|---|---|---|---|
| claude-opus-4-8 | old | 0.73±0.36 | 0.33±0.47 | 0.50±0.50 | 0.00±0.00 | 0.14±0.35 | 0.10±0.30 | 1.00(n1) | 1.00(n1) |
| claude-opus-4-8 | NEW | 0.73±0.36 | 0.64±0.46 | 1.00±0.00 | 0.40±0.49 | 0.14±0.35 | 0.10±0.30 | 1.00(n1) | 1.00(n1) |
| gpt-5.5 | old | 0.83±0.37 | 0.33±0.47 | 0.33±0.47 | 0.00±0.00 | 0.14±0.35 | 0.10±0.30 | 1.00(n1) | 1.00(n1) |
| gpt-5.5 | NEW | 0.83±0.37 | 0.58±0.45 | 0.67±0.47 | 0.33±0.47 | 0.14±0.35 | 0.10±0.30 | 1.00(n1) | 1.00(n1) |
| gemini-3.5-flash | old | 0.83±0.37 | 0.33±0.47 | 0.50±0.50 | 0.00±0.00 | 0.14±0.35 | 0.02±0.06 | 1.00(n1) | 1.00(n1) |
| gemini-3.5-flash | NEW | 0.83±0.37 | 0.60±0.45 | 1.00±0.00 | 0.40±0.49 | 0.14±0.35 | 0.02±0.06 | 1.00(n1) | 1.00(n1) |
| claude-sonnet-4-6 | old | 0.77±0.35 | 0.33±0.47 | 0.50±0.50 | 0.00±0.00 | 0.14±0.35 | 0.11±0.29 | 0.20±0.40 | 1.00(n1) |
| claude-sonnet-4-6 | NEW | 0.77±0.35 | 0.59±0.45 | 1.00±0.00 | 0.32±0.46 | 0.14±0.35 | 0.11±0.29 | 0.20±0.40 | 1.00(n1) |
| claude-haiku-4-5-20251001 | old | 0.56±0.39 | 0.40±0.49 | 0.33±0.47 | 0.00±0.00 | 0.11±0.28 | 0.07±0.22 | 0.25±0.43 | 1.00(n1) |
| claude-haiku-4-5-20251001 | NEW | 0.56±0.39 | 0.67±0.41 | 0.67±0.47 | 0.23±0.39 | 0.11±0.28 | 0.07±0.22 | 0.25±0.43 | 1.00(n1) |
| gpt-5.4-mini | old | 0.26±0.34 | 0.03±0.07 | 0.50±0.50 | 0.00±0.00 | 0.09±0.21 | 0.06±0.18 | 0.33±0.47 | 0.60(n1) |
| gpt-5.4-mini | NEW | 0.26±0.34 | 0.06±0.08 | 1.00±0.00 | 0.17±0.03 | 0.09±0.21 | 0.06±0.18 | 0.33±0.47 | 0.60(n1) |
| deepseek-v4-pro | old | 0.67±0.43 | 0.33±0.47 | 0.50±0.50 | 0.00±0.00 | 0.14±0.35 | 0.08±0.24 | 0.33±0.47 | 1.00(n1) |
| deepseek-v4-pro | NEW | 0.67±0.43 | 0.60±0.45 | 1.00±0.00 | 0.33±0.47 | 0.14±0.35 | 0.08±0.24 | 0.33±0.47 | 1.00(n1) |
| kimi-k2.6 | old | 0.97±0.04 | 0.50±0.50 | - | 0.00±0.00 | 0.00±0.00 | 0.00±0.00 | 1.00(n1) | - |
| kimi-k2.6 | NEW | 0.97±0.04 | 0.50±0.50 | - | 0.50±0.50 | 0.00±0.00 | 0.00±0.00 | 1.00(n1) | - |

### Floors — grounded (old vs NEW)

| floor | macro old | macro NEW | fwd old | fwd NEW | way old | way NEW |
|---|---|---|---|---|---|---|
| empty | 0.00±0.00 | 0.00±0.00 | 0.0 | 0.0 | 0.0 | 0.0 |
| naive_session_loss | 0.00±0.00 | 0.00±0.00 | 0.0 | 0.0 | 0.0 | 0.0 |
| naive_count | 0.00±0.00 | 0.00±0.00 | 0.0 | 0.0 | 0.0 | 0.0 |
| syntactic_diff | 0.01±0.02 | 0.02±0.03 | 0.0 | 0.0 | 0.0 | 0.0 |
| modal_by_class | undefined | undefined | - | - | - | - |
| oracle_ceiling | 1.00±0.00 | 1.00±0.00 | 1.0 | 1.0 | 1.0 | 1.0 |

## Split: templated

### Headline macro-F1 (old → new) + key dims

| system | macro old | macro NEW | macro dmg old | macro dmg NEW | FSA old | FSA NEW | invalid |
|---|---|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | 0.28±0.33 | **0.41±0.29** | 0.15 | **0.30** | 0.00 | 0.00 | 0.00 |
| gpt-5.4-mini | 0.26±0.37 | **0.34±0.34** | 0.11 | **0.21** | 0.00 | 0.00 | 0.00 |

### Per-dimension mean F1 — old vs NEW (the dimensions the artifact hit)

| system | grader | prefixes | reachability | waypoint | forwarding | bgp_withdrawn | intent | redundancy | scale |
|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | old | 0.45±0.37 | 0.19±0.37 | 0.00±0.00 | 0.00±0.00 | 0.18±0.36 | 0.01±0.06 | 0.00±0.00 | 0.53±0.44 |
| claude-haiku-4-5-20251001 | NEW | 0.45±0.37 | 0.36±0.40 | 0.39±0.44 | 0.24±0.42 | 0.18±0.36 | 0.01±0.07 | 0.00±0.00 | 0.53±0.44 |
| gpt-5.4-mini | old | 0.20±0.16 | 0.11±0.15 | 0.00±0.00 | 0.00±0.00 | 0.13±0.27 | 0.01±0.07 | 0.00±0.00 | 0.28±0.32 |
| gpt-5.4-mini | NEW | 0.20±0.16 | 0.15±0.16 | 0.43±0.45 | 0.42±0.34 | 0.13±0.27 | 0.01±0.07 | 0.00±0.00 | 0.28±0.32 |

### Floors — templated (old vs NEW)

| floor | macro old | macro NEW | fwd old | fwd NEW | way old | way NEW |
|---|---|---|---|---|---|---|
| empty | 0.17±0.37 | 0.17±0.37 | 0.0 | 0.0 | 0.0 | 0.0 |
| naive_session_loss | 0.00±0.00 | 0.00±0.00 | 0.0 | 0.0 | 0.0 | 0.0 |
| naive_count | 0.06±0.24 | 0.06±0.24 | 0.0 | 0.0 | 0.0 | 0.0 |
| syntactic_diff | 0.13±0.33 | 0.14±0.33 | 0.0 | 0.0 | 0.0 | 0.0 |
| modal_by_class | 0.18±0.39 | 0.18±0.39 | 0.0 | 0.0 | 0.0 | 0.0 |
| oracle_ceiling | 1.00±0.00 | 1.00±0.00 | 1.0 | 1.0 | 1.0 | 1.0 |

## Sonnet 4.6 invalid samples = max_tokens truncation (NOT reasoning failure)

**max_tokens / output budget per model in the sweep config (`scripts/run_sweep.py`):**

| model | output budget | source |
|---|---|---|
| anthropic/* (haiku, sonnet, opus) | `max_tokens=4000` | `_call_anthropic` |
| openai/gpt-5.5 | no explicit cap (reasoning.effort=medium) | `_call_openai` |
| openai/gpt-5.4-mini | `max_output_tokens=16000` | `_call_openai` |
| gemini/gemini-3.5-flash | `max_output_tokens=16000` | `_call_gemini` |

**Sonnet 4.6 had 6 invalid samples, all on long grounded scenarios:** `clos_summary` s0 (tokens_out=4000), `clos_summary` s1 (tokens_out=4000), `clos_summary` s2 (tokens_out=4000), `clos_summary` s3 (tokens_out=4000), `clos_summary` s4 (tokens_out=4000), `lp_waypoint` s1 (tokens_out=4000).

**Every one emitted exactly 4000 output tokens = the `max_tokens=4000` cap → hard truncation.** Sonnet's valid samples averaged ~2381 tokens_out (max 4000); these 6 ran the budget dry mid-reasoning and were cut off BEFORE the final ```json block, so the (correct, forgiving) parser returns None → scored invalid. The truncated prose contains substantively correct analysis. Quoted tails:

- `clos_summary` s1 (tail): “…fixes_lost | leaf1, leaf2 lose 10.3.0.0/24 from RIB | | reachability_lost | leaf1→10.3.0.0/24, leaf2→10.3.0.0/24 (spine2 ECMP path blackholes) | | waypoint_violations | None | | redundancy_losses | leaf1 and leaf2: 10.3.0.0/24 path count 1→0 specific paths | | forwarding_anomalies | spine2 blackholes 10.3.0.0/24 | | scale_violations | None | | bgp_withdrawals | leaf1 and leaf2 lose 10.3.0.0/24 from BGP RIB | | intent”
- `clos_summary` s2 (tail): “…ng 10.3.0.0/24 back to leaf3 in the baseline either. No withdrawal to leaf3 for this prefix.  So BGP withdrawals of 10.3.0.0/24: - At leaf1: receives withdrawal from spine1 (the only spine that was advertising it) - At leaf2: receives withdrawal from spine1  **→ [{leaf1, 10.3.0.0/24}, {leaf2, 10.3.0.0/24}]**  ---  ### 9. intent_violations  The stated intents: 1. "All servers in 10.0.0.0/8 — including the 10.3.0.0/24”

These tails show Sonnet correctly identifying the spine2 blackhole, the leaf1/leaf2 prefix loss, the BGP withdrawals, and the te_pin / reachability intent violation — it simply never reached the JSON. **Recommended fix (NOT run here): re-run Sonnet 4.6 grounded with `max_tokens` raised to ~12000 (the other-provider budget). Estimated cost ~\$1–2** (11 instances × 5 samples × ~$0.03). Until then, Sonnet's grounded macro is depressed by a harness cap, not its reasoning, and should be footnoted as such — its invalid_rate (0.11) is a truncation artifact, not an output-format failure.

## The honest story the numbers now tell

**1. The D7=0.00 headline was a grader artifact and is now retracted.** Under fair grading every model recovers real D7 forwarding-anomaly signal on the grounded split: Opus 0.00→0.40, Gemini 0.00→0.40, GPT-5.5 0.00→0.33, Haiku 0.00→0.23, GPT-5.4-mini 0.00→0.17, Sonnet 0.00→0.14. The claim 'no model identified a single blackhole on any of 810 samples' is FALSE — they identified the blackhole node + kind + config-visible covering prefix; the exact-string grader rejected it only because the truth key was an undisclosed /32 probe inside that prefix.

**2. The capability gradient SURVIVES and sharpens.** Grounded macro-F1 old→new: Opus 0.37→0.51, GPT-5.5 0.36→0.48, Gemini 0.36→0.49, Haiku 0.29→0.39, Sonnet 0.27→0.35, GPT-5.4-mini 0.22→0.27. The frontier still sits clearly above the mid-tier; all model-free floors stay ≤0.02 grounded (the new grader is provably identity on D2/D9/scale/sessions, so it lifts models on the probe dimensions WITHOUT lifting the floors — the contamination-control story holds: modal_by_class stays 0.18 templated / undefined grounded, syntactic_diff ≤0.02, exactly as before on the dimensions it could ever touch).

**3. The TRUE blind spot is narrower and more interesting than 'universal second-order blindness'.** The dimension breakdown under fair grading shows models catch DROPS but miss PATH/INTENT violations where reachability survives:
  - On `leak_ms_blackhole` (a route is destroyed) Haiku's D7 is 0.00→0.98 — a pure artifact; the model was right.
  - On `leak_ms_reroute` (reachability SURVIVES but traffic silently bypasses the mandated waypoint) waypoint stays **0.10** and intent **0.02** under fair grading: **57/60 reroute samples still score 0** on waypoint+intent. This is a GENUINE, preserved miss — the subtle harm.
  - Grounded, the dimensions that remain low for the frontier under fair grading are **D9 bgp_withdrawn (~0.14), D10 intent (~0.02–0.10), and the harder half of D7 (~0.33–0.40)** — control-plane withdrawals and policy-intent violations, not 'everything second-order'.

**4. Templated D4 waypoint was ALSO an artifact, not a 0.00 capability.** Haiku waypoint 0.00→0.39, GPT-5.4-mini 0.00→0.43; templated forwarding 0.00→0.24 and 0.00→0.43. The paper's 'waypoint (D4) and redundancy (D5) are also 0.00 for both evaluated models' is half-false: D4 was the /32 artifact (now non-zero); **D5 redundancy genuinely stays 0.00 templated** (no templated instance has a redundancy truth element active for these models — a real gap to disclose, not a capability claim).

**5. F2 (no false-session-alarm) is UNAFFECTED and stands.** FSA is provably identical old→new (sessions carries no prefix slot). The one-sided-omission framing survives verbatim. F4 (no home-field advantage) survives: the cross-vendor frontier stays within noise under fair grading (Opus 0.51, Gemini 0.49, GPT-5.5 0.48).

**Bottom line:** the benchmark is REAL — it discriminates frontier from mid-tier from floors, the floors stay at chance, and a genuine, dangerous blind spot remains (silent reroutes / intent / control-plane withdrawals). But the specific, dramatic claim the paper is built around — *universal D7 blindness, 0.00 on all 810 samples* — is a measurement artifact and must be retracted before arXiv.

## What in paper/draft/netbrace_tr.tex is now FALSE and must be rewritten

| location | status | what to fix |
|---|---|---|
| Abstract (lines ~46–51) | **FALSE** | “score 0.00—on every sample, of every model evaluated—at identifying the second-order forwarding anomalies” and “would approve the blackhole without raising a single warning.” Models DO recover D7 under fair grading (frontier 0.33–0.40). Rewrite to the real finding: models partially recover blackhole drops but miss silent reroutes / intent / control-plane withdrawals; the gate would under-warn, not zero-warn. |
| Abstract macro numbers (line ~44) | **STALE** | “frontier macro-F1 0.36–0.37” → under fair grading 0.48–0.51. Floors ≤0.01 grounded still holds. Update the headline spread. |
| Intro/§ headline (lines ~113–123) | **FALSE** | “forwarding-anomaly F1 is 0.00 … all 810 graded samples” — retract; this is the grader artifact. Keep the capability-gradient framing (D2 high, consequence dims lower) which survives. |
| F3 'Universal second-order blindness' (lines ~376–389) | **FALSE — must be rewritten** | The entire paragraph asserts D7=0.00 on every sample and 'no model identified a single blackhole.' This is the core artifact. Replace with: D7 recovered (0.14–0.40 grounded); the surviving blind spot is reroute-waypoint (D4 on leak_ms_reroute ~0.10), intent (D10 ~0.02–0.10), and control-plane withdrawals (D9 ~0.14). Templated D4 also was an artifact (0.00→0.39/0.43). |
| Table 'grounded' (tab:grounded, ~line 323) + Figure gradient (~354) + Figure floors (~399) | **STALE / WRONG NUMBERS** | Every D7 column reads 0.00 and macro reads 0.36–0.37; regenerate from the semantic grader (D7 0.14–0.40, macro 0.27–0.51). The floors figure caption and modal_by_class=0.00 templated still hold; the model bars move up. |
| Scenario table note (line ~314) | **CHECK** | “including it would have raised model scores on D7” — re-verify against the new D7 numbers; the contrastive logic may need restating. |
| F1 numbers (lines ~359–366) | **STALE** | Grounded frontier 0.36–0.37 → 0.48–0.51; mid-tier 0.22–0.29 → 0.27–0.39. Templated damage macro Haiku 0.15→0.30, mini 0.11→0.21. Floors unchanged. The discrimination claim stands; the magnitudes change. |
| F2 (lines ~368–374) | **UNCHANGED — keep** | FSA provably identical old→new. No edit needed beyond confirming it. |
| F4 (lines ~391–395) | **UPDATE NUMBERS, conclusion stands** | 0.37/0.36/0.36 → 0.51/0.48/0.49; cross-vendor parity survives. |
| Sonnet invalid_rate wherever cited | **ADD FOOTNOTE** | Sonnet's 6 invalids are max_tokens=4000 truncations on long grounded scenarios, not format failures; recommend a ~$1–2 re-run at max_tokens≈12000 and footnote the cap. Its grounded macro is cap-depressed. |

The paper's *structure* (blast-radius task, oracle pipeline, deterministic set grading, floors, N=5 two-stage stats, no-LLM-judge) is sound and survives. What must change is the single most-quoted empirical claim (universal D7=0.00) and every number derived from the exact-string grader on the probe dimensions (D3 partial, D4, D7, D10). The NEW grader (`semantic_sets.py`, frozen spec) should become the reported grader, with the exact-string column retained in an appendix as the conservative lower bound and the artifact explicitly disclosed as a methods contribution (‘why naive string-matching under-measures probe-encoded ground truth’).

## Audit / reproduction notes

- gemini clean reconstructed: 55 samples / 11 instances
- extra source deepseek/deepseek-v4-pro (sweep_20260613_224649): 55 grounded samples graded; truth-determinism vs canonical: PASS
- extra source kimi/kimi-k2.6 (sweep_20260614_030415): 20 grounded samples graded; truth-determinism vs canonical: PASS
- sonnet 12k re-run (sweep_20260613_093307): 55 grounded samples graded, supersedes the 4k-cap rows; truth-determinism vs 4k: PASS
- reproduction gate: 830 checked, 0 mismatches (PASS)
- floor reproduction gate: 339 checked, 0 mismatches (PASS)
