# NetHELM — real-evidence sweep (PRELIMINARY, N=5 grounded)

**Date:** 2026-06-09 (updated)
**Status:** PRELIMINARY — **N=5** samples, 2 Anthropic models, 12 hand-authored
scenarios, **grounded split**. This update raises the grounded sweep from N=3 to
**N=5** for Haiku (both conditions) and Sonnet (no_tools complete). The full sweep is
still gated on two things, both now ready in code: (1) a non-Anthropic vendor — the
**OpenAI (GPT-5) and Gemini (Gemini 2.5 Pro) providers are now wired and key-checked**
(see "PENDING: GPT + Gemini"), and (2) the **templated decontaminated split** with a
now-non-degenerate `modal_by_class` floor (the `--coarsen-class` fix, validated below).

> **Run-blocker (honest):** mid-update the **Anthropic credit balance was exhausted**
> (`invalid_request_error: credit balance too low`). As a result the **Sonnet `tools`
> condition is only 6/12 scenarios complete and is NOT reported as final**, and the
> **paid templated split could not be run at all**. Everything reported below is from
> calls that completed and parsed (invalid-output rate = 0.00). Total Anthropic spend
> this session = **$5.03** (cost-guarded; target ≤ $12, hard stop $20; smoke-first).

Run artifacts (this update): Haiku N=5 grounded both conditions =
`runs/sweep_20260609_023904/` (complete, with `summary.json`/`summary.md`); Sonnet
N=5 grounded = `runs/sweep_20260609_025324/` (no_tools complete = 60/60; tools partial
= 29/60, no summary written — recovered by re-aggregating `results.jsonl`).

---

## Setup

| field | value |
|---|---|
| Models | `claude-haiku-4-5-20251001`, `claude-sonnet-4-6` (exact API IDs, pinned in the run manifest) |
| Oracle | Batfish (`--oracle batfish`), real ground truth on the pinned digest |
| Scenarios | the 12 hand-authored mechanisms in `REGISTRY` (grounded split; the 96 generated Class-1 clones were excluded — one mechanism, would dominate and cost more) |
| Conditions | `no_tools` (configs + diff + intent only) and `tools` (SAME prompt + the PRE-change observed state: `show ip bgp summary` / `show ip route` from the PRE snapshot) |
| Samples | **N=5** per (scenario, model, condition) |
| Temperature | 0.7 |
| Calls (this update) | Haiku: 12 × 2 cond × 5 = **120** (complete). Sonnet: 60 no_tools (complete) + 29 tools (partial). All completed calls parsed; invalid-output rate = 0.00. |
| **Actual spend (session)** | **$5.03** total (Haiku $0.85; Sonnet $2.41 partial-A + $1.13 partial-retry; plus a $0.64 stalled first attempt). Cost-guarded: 1-call smoke ($0.0064 Haiku) → projected ≈ $5.7 for the planned (a)+(b); aborted (b) on credit exhaustion, not on the guard. |
| Aggregation | scenario-level two-stage (per-instance mean over N, then mean±std across the 12 instances); never pooled-i.i.d. |

Commands (run as two separate processes — one model each — to avoid the long-lived-client
socket stall observed when 240 sequential calls share one process):
```
# Haiku N=5 grounded, both conditions (COMPLETE):
python scripts/run_sweep.py --models anthropic/claude-haiku-4-5-20251001 \
  --oracle batfish --samples 5 --split grounded --condition no_tools,tools \
  --temperature 0.7 --seed 0
# Sonnet N=5 grounded (no_tools complete; tools partial — credits ran out):
python scripts/run_sweep.py --models anthropic/claude-sonnet-4-6 \
  --oracle batfish --samples 5 --split grounded --condition no_tools,tools \
  --temperature 0.7 --seed 0
```

The verification-gate **reframe** (scrutiny change #1) is live in the prompt: the task
is framed as the pre-deployment trust gate ("predict the blast radius so an operator
can decide whether to trust the change before applying it") in BOTH conditions, without
leaking any outcome (the prompt-hygiene CI lint stays green).

---

## Headline table (grounded split, N=5, scenario-level mean ± std across 12 scenarios)

| system | macro_f1 | FSA_rate | invalid | N | notes |
|---|---|---|---|---|---|
| **haiku-4-5 @ no_tools** | 0.27 ± 0.20 | **0.00** | 0.00 | 5 | complete |
| **haiku-4-5 @ tools** | 0.26 ± 0.20 | **0.00** | 0.00 | 5 | complete |
| **sonnet-4-6 @ no_tools** | 0.32 ± 0.23 | **0.00** | 0.00 | 5 | complete |
| sonnet-4-6 @ tools | — | — | — | — | **6/12 scenarios only — NOT reported (credits out)** |
| empty (baseline) | 0.00 | 0.00 | — | — | recall floor |
| naive_session_loss (baseline) | 0.00 | **0.92** | — | — | trap strawman |
| naive_count (baseline) | 0.00 | 0.00 | — | — | first-order-only floor |
| modal_by_class (baseline) | 1.00 † | 0.00 | — | — | degenerate on grounded (see †) |
| oracle_ceiling (baseline) | 1.00 | 0.00 | — | — | topline |

macro_f1 SEM across the 12 scenarios ≈ 0.06–0.07 for each reported model×condition.

The N=5 numbers **reproduce the N=3 picture within noise** (Haiku no_tools 0.27 at both N;
Sonnet no_tools 0.32 at both N; FSA = 0.00 throughout). The tighter sampling did not move
the headline, which is the point of raising N — the effect is stable, not a small-N artifact.

† **`modal_by_class` is degenerate on the grounded split** and must NOT be read as a
floor here: each hand-authored scenario is its own class (one instance per class), so
"the modal blast of the class" trivially equals that scenario's ground truth → 1.00.
**This is now fixed for the templated split** by the new `--coarsen-class` flag
(`netbrace/reporting/baselines.py::scenario_class(..., coarsen=True)`): it collapses the
Class-1 label `k{k}-{filtered}-{direction}-{prefix}-{match}` to the structural pair
`{prefix}-{match}`, so at `--n-generated 24` the templated split has **8 classes × 3
instances each** and `modal_by_class` becomes a real strict-majority memorization floor.
**Validated (fake-oracle, free — NOT a model number):** on that coarsened templated split
`modal_by_class` macro_f1 = **0.07 ± 0.24** (vs oracle_ceiling 1.00) — a genuine LOW floor,
because the per-seed randomized addressing means modal keys almost never recur even within
a shared structural class. The paid templated run (below) was blocked by credit exhaustion.

---

## The GAP: does giving the model the current state help? (the key finding)

**No — at N=5 (Haiku, complete) the tools condition does not improve macro_f1.** Per
model, no_tools vs tools:

| model | no_tools macro_f1 | tools macro_f1 | Δ (tools − no_tools) |
|---|---|---|---|
| haiku-4-5 (N=5, complete) | 0.27 ± 0.20 | 0.26 ± 0.20 | **−0.01** |
| sonnet-4-6 (N=5 no_tools complete; **tools 6/12 — credits out**) | 0.32 ± 0.23 | *(incomplete)* | *(not computed)* |

> The Sonnet tools cell from the earlier N=3 run was 0.31 (Δ ≈ −0.01); the N=5 tools
> condition for Sonnet did not finish (6/12 scenarios) before credits were exhausted, so
> it is intentionally left blank rather than reported on partial coverage. The Haiku N=5
> result (Δ = −0.01, inside one SEM ≈ 0.06) reproduces the N=3 finding.

The Haiku delta is far inside one SEM (≈0.06) — indistinguishable from zero. **Handing the
model the current BGP session table and RIB it would otherwise have to recall did not
move the aggregate score.** Read against the scrutiny thesis: the bottleneck is NOT
"can't recall current state" — it is "can't *simulate the change*." The models already
infer steady state well enough from the configs; what they fail at is propagating a
policy/diff edit forward to its typed consequences. This is the HotNets-shaped insight
the panel wanted: **tools (here, one-shot state retrieval) are not the missing
ingredient** for blast-radius prediction. (A full agentic loop with the *post*-state
would trivially solve it — but that is just re-running Batfish, which is the point: the
value is the model's internal world-model, not its tool access.)

Per-scenario, tools occasionally helped and occasionally hurt (it is not uniformly
inert), which is itself informative:
- **sonnet `ipc3_static`: 0.36 → 0.73** (the one clear tools win — seeing the static
  backup route present in the PRE RIB helped it reason that the BGP withdrawal is
  control-plane-only). haiku on the same scenario went **0.50 → 0.00** (the extra state
  distracted it).
- **`ipc_aggregate`, `square4`, `ipc_fanout`**: tools *reduced* sonnet's score (more
  context → more spurious predictions on some samples).
The net wash hides real per-scenario movement in both directions — worth a larger-N look.

---

## Baseline separation (does the benchmark measure anything?)

- Both models **clear the `empty` / `naive_count` floor (0.00)** on macro_f1 — they are
  doing non-trivial prediction, not scoring on a harness artifact.
- **Neither model trips the trap.** FSA_rate = 0.00 for every completed model×condition
  cell (Haiku no_tools+tools, Sonnet no_tools; Sonnet tools also 0.00 on its 6/12),
  vs the `naive_session_loss` strawman at **0.92**. This is a genuinely good result and
  the cleanest positive finding: frontier models have *learned not to reflexively
  predict a BGP session drop* on a policy change. The documented "a BGP change → a
  session drops" reflex (the trap the whole false-session-alarm metric was built to
  catch) is essentially absent in Haiku-4.5 and Sonnet-4.6. The trap discriminates the
  strawman from the models exactly as designed.
- The models sit **far below `oracle_ceiling` (1.00)** at macro_f1 ≈ 0.25–0.32: lots of
  headroom, the task is hard but not impossible (it is discriminating — the failure mode
  the panel feared, "impossible for everyone, measures nothing", is not what we see;
  scores vary 0.00–0.73 across scenarios).

---

## Per-dimension breakdown (grounded split, N=5, mean F1 over scenarios where the dim is active)

Cells are the **N=5** numbers. `sonnet to` is **omitted** (tools condition only 6/12
scenarios — credits out — so a per-dim column would be over partial coverage).

| dim | haiku nt | haiku to | sonnet nt | reading |
|---|---|---|---|---|
| sessions (D1) | 0.00 | 0.00 | 0.67 | only ~1 scenario has a real D1; sonnet partial, haiku misses |
| prefixes (D2) | 0.48 | 0.44 | 0.58 | first-order loss — partial |
| reachability (D3) | 0.33 | 0.47 | 0.60 | first-order — partial |
| waypoint (D4) | 0.50 | 0.50 | 0.50 | flat — they get one waypoint scenario, miss the other |
| redundancy (D5) | 0.50 | 0.50 | 0.33 | thin (few active scenarios; high variance) |
| forwarding (D7) | 0.00 | 0.20 | 0.17 | **near-total miss** — the silent-blackhole second-order class |
| scale (D8) | 1.00 | 1.00 | 1.00 | scale_deagg's D8: both nail the FIB-overflow flag |
| bgp_withdrawn (D9) | 0.12 | 0.00 | 0.11 | **near-total miss** — the control-plane-only withdrawal |
| intent (D10) | 0.08 | 0.10 | 0.11 | **near-total miss** — the policy/intent violations |

The second-order dimensions are where the models fail, and they are exactly the ones
NetHELM exists to score:
- **D7 forwarding (~0.0–0.2), D9 bgp_withdrawn (~0.0–0.14), D10 intent (~0.0–0.09)** are
  near-zero. These are the "reachable-but-broken / control-plane-only / silent
  blackhole / intent-violated" effects a connectivity-only review (and, evidently, a
  frontier LLM) misses. **This is the benchmark's core justification, now with
  evidence:** models recover first-order loss (D2/D3, partial) and the explicit budget
  flag (D8), but cannot predict the second-order, longest-prefix-match / best-path /
  policy consequences.
- The hardest scenarios score **0.00 for every model in both conditions**:
  `clos_summary` (partial-ECMP summary blackhole), `leak_ms` (more-specific leak →
  LPM blackhole), `lp_waypoint` (LOCAL_PREF best-path egress flip). These are the
  pure second-order mechanisms — no session/prefix removed — and they are uniformly
  unsolved. Tools did not crack any of them.

---

## Honest narrative + headline findings (PRELIMINARY)

1. **Frontier models score macro_f1 ≈ 0.25–0.32 on typed blast-radius prediction** —
   well above the floor, far below the ceiling. The task is hard and discriminating.
2. **The trap is beaten: FSA_rate = 0.00.** Neither model false-alarms a BGP session
   loss; the naive strawman does so 92% of the time. The reflexive-session-drop failure
   mode the metric targets is absent in these two 2026 models. (This re-points the
   "where do LLMs fail" story away from over-alarming and toward *under-prediction of
   second-order damage*.)
3. **One-shot tool access (current session+RIB state) does not help** (Haiku N=5
   Δmacro ≈ −0.01, within noise; Sonnet tools N=5 incomplete). The deficit is
   change-*simulation*, not state-*recall*. This is
   the "tools necessary-but-not-sufficient" insight, with a concrete contrast: even with
   the operator's own pre-state in hand, the model cannot forward-propagate the diff to
   its second-order effects.
4. **The miss is concentrated in D7/D9/D10** — the second-order/control-plane/intent
   dimensions that are NetHELM's reason to exist. The pure second-order scenarios
   (clos_summary, leak_ms, lp_waypoint) are 0.00 across the board.

### What a full sweep would firm up
- **N≥5 (Haiku now complete; Sonnet no_tools complete) and ≥4 models incl. a
  non-Anthropic.** The non-Anthropic vendors are **wired and key-checked**: GPT-5
  (`gpt-5-2025-08-07`) and Gemini 2.5 Pro (`gemini-2.5-pro`). One command fires them
  (see "PENDING: GPT + Gemini"). Still need: cross-vendor calls + tighter bootstrap CIs.
- **The templated decontaminated split**, where `modal_by_class` is now a real
  memorization floor via `--coarsen-class` (validated 0.07 on fake GT; the paid model
  run is the only missing piece — credits out).
- **A risk–coverage / calibrated-abstention curve** (scrutiny step 2): at the confidence
  an operator needs, what fraction can be auto-approved? Needs per-prediction confidence,
  not yet emitted.
- **Significance vs the floors**: macro_f1 ≈ 0.3 vs 0.00 is large, but report a
  bootstrap/t CI per model in the paper.

### Caveats specific to this run
- `modal_by_class = 1.00` is an artifact of the single-instance grounded split (see †);
  do not cite it as a floor. The **templated** split now has a real floor
  (`--coarsen-class`, validated at 0.07 on fake-oracle GT).
- A handful of Sonnet `tools` calls hit the 1500-token output cap; outputs still parsed
  (invalid_rate = 0.00) but a truncated tail could slightly understate Sonnet-tools.
  Worth raising max_tokens for the headline run.
- 12 scenarios / 9 active dims means several per-dimension cells rest on 1–3 scenarios
  (D1, D5 especially) — high variance; mechanism-level, not population-level, evidence.
- **Sonnet `tools` (N=5) and the entire paid templated split are MISSING because the
  Anthropic credit balance was exhausted mid-run.** They are not estimated or filled in.

---

## Templated vs grounded — the contamination comparison (DESIGN READY, RUN BLOCKED)

This is the key new result the methodology needs and the one piece this update could
**not** purchase. The mechanism is in place; only the paid calls are missing.

**Why it matters.** The 12 grounded scenarios encode public-incident *mechanisms* that may
be in training data; the templated split generates fresh, **per-seed randomized** instances
of the same Class-1 mechanism (private ASNs, randomized loopback/link/customer blocks,
randomized node names — `generator_ipc._draw_params`). If a model scores **similarly** on
templated vs grounded, that is evidence it is *reasoning about the mechanism*, not
*recalling a memorized public incident*. A large grounded > templated gap would indicate
contamination/inflation. **This comparison is the contamination control.**

**What is ready now (no further code needed):**
- The templated split runs through the identical oracle + grader + prompt contract.
- `modal_by_class` is now a **genuine LOW floor** on the templated split via
  `--coarsen-class` (8 classes × 3 instances at `--n-generated 24`; fake-oracle macro_f1
  = 0.07, far below the 1.00 it degenerates to on grounded). So the templated table will
  have a real memorization floor to read the models against.

**What is missing:** the paid Haiku/Sonnet templated calls (credits out). Planned config
was `--split templated --n-generated 24 --coarsen-class --samples 3 --condition no_tools`
(N=3 to control cost on the larger instance count). Exact reproduce command:

```
# Templated split (contamination control) — Haiku + Sonnet, when Anthropic credits exist:
python scripts/run_sweep.py \
  --models anthropic/claude-haiku-4-5-20251001,anthropic/claude-sonnet-4-6 \
  --oracle batfish --split templated --n-generated 24 --coarsen-class \
  --samples 3 --condition no_tools --temperature 0.7 --seed 0
```

The contamination verdict (templated ≈ grounded?) is **pending this run**.

---

## PENDING: GPT + Gemini (cross-vendor — WIRED + KEY-CHECKED, not run)

Both non-Anthropic providers are now wired into `scripts/run_sweep.py` and fail-fast if
their key is absent (verified: a keyless call raises `OPENAI_API_KEY not set` /
`GEMINI_API_KEY (or GOOGLE_API_KEY) not set` before any spend):

| vendor | registry key | exact model ID | list price (in/out per 1M) | path |
|---|---|---|---|---|
| OpenAI | `openai/gpt-5-2025-08-07` | `gpt-5-2025-08-07` | $1.25 / $10.00 | `_call_openai` (Responses API; key `OPENAI_API_KEY`) |
| Google | `gemini/gemini-2.5-pro` | `gemini-2.5-pro` | $1.25 / $10.00 | `_call_gemini` (`google-genai`; key `GEMINI_API_KEY` or `GOOGLE_API_KEY`) |

Both use the same `_build_prompt` contract, the same `parse_extended_prediction` path,
and log per-call tokens + USD into the manifest exactly like the Anthropic path. Libraries
`openai` and `google-genai` are installed in `harness/venvs/nethelm`.

**THE EXACT ONE COMMAND to fire the cross-vendor completion** once `OPENAI_API_KEY` and
`GEMINI_API_KEY` are set (Batfish up on 9997). This runs both new vendors over the N=5
grounded sweep (both conditions) **and** the contamination-control templated split in one
invocation; run each vendor as its own process if you hit the long-client socket stall:

```
OPENAI_API_KEY=... GEMINI_API_KEY=... \
python scripts/run_sweep.py \
  --models openai/gpt-5-2025-08-07,gemini/gemini-2.5-pro \
  --oracle batfish --samples 5 --split both --n-generated 24 --coarsen-class \
  --condition no_tools,tools --temperature 0.7 --seed 0
```

(Pre-flight cost guard: do a 1-call smoke first; at ~$1.25/$10 per 1M and ~3k in / ~1k out
per call, expect roughly $0.013/call → the grounded N=5 both-conditions block per vendor is
~120 calls ≈ $1.6/vendor, plus the templated block. Keep the ≤ $12 target / $20 hard stop.)
