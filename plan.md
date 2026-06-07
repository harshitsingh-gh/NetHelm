# NetBrace Safety Axis — Technical Plan (HotNets 2026)

> **Status:** Design — v2 (merged authoritative plan)
> **Created:** 2026-06-06
> **Supersedes:** the v1 of this file and `tasks/plan_2026-06-06_hotnets_implementation_blueprint.md`. Rationale for the merge is in [temporary/plan_analysis_earlier_vs_blueprint.md](temporary/plan_analysis_earlier_vs_blueprint.md).
> **Companion (strategy/calendar):** [tasks/plan_2026-06-04_hotnets_sprint.md](tasks/plan_2026-06-04_hotnets_sprint.md)
> **Paper:** "Can LLMs Predict the Blast-Radius of Network Configuration Changes? A Preliminary Evaluation" — HotNets 2026, submit July 15.

This document is the single source of truth for *how the system works*. It takes the **scope, oracle design, and evaluation science** from the earlier `plan.md`, and the **reproducibility spine, test suite, and data-model rigor** from the implementation blueprint. Where the two disagreed, the resolved decisions are marked **[DECISION]**.

---

## 0. Thesis in one sentence

Given a converged network and a proposed configuration change, can an LLM predict **which BGP sessions, prefixes, and reachability** the change will break — *before* it is applied? We generate such scenarios, compute the true impact with Batfish, ask an LLM to predict it, and score the prediction with precision/recall/F1. No prior benchmark scores this.

---

## 1. Scope

### In scope (what ships for HotNets)
- A **deterministic task generator**: `(topology, baseline configs, proposed diff)` → task JSON.
- A **Batfish ground-truth oracle** in differential mode, denoised by a watched-prefix set.
- An **LLM eval harness built on Inspect AI** — Inspect runs the models; we write the networking task + scorer.
- A **set-comparison grader**: precision/recall/F1 over predicted vs. true blast-radius, with trap/false-alarm handling.
- A **reproducibility spine**: Pydantic schemas, manifest + prompt hashing, git capture, cost logging.
- A **fake/replay model path** so the whole pipeline is developed and tested without API spend.
- 20 tasks (Week A) → 50 tasks (Week C); GPT-4o + Claude Sonnet; single-shot.

### Out of scope **[DECISION]** (deferred to the NeurIPS extension)
- **Router write/apply/rollback backend** — not on the `tasks → oracle → model → score → figure` path. Only *read-only* `show` helpers ship, for 5-task oracle validation.
- **A custom model runner** — Inspect AI provides the run loop, provider adapters, logging, and cost capture. We do not reimplement them.
- Multi-vendor (FRR only), the other 5 task categories (K/C/B/D/R), agentic/multi-turn, local models, Cisco DNM, a database.

> **Anti-goal:** building a platform instead of a paper. Every file must serve the five-stage pipeline. If it doesn't, it waits until after July 15.

---

## 2. The task, formally

A **task** is `T = (N, C₀, Δ)`:
- `N` — **topology**: nodes, links, addressing, AS layout.
- `C₀` — **baseline config set**, one per node, in a *converged* state (all intended BGP sessions ESTABLISHED, all intended prefixes reachable).
- `Δ` — **proposed diff**: a single localized change to one node (shut a neighbor, add a filter, …).

The **ground-truth blast-radius** `G` is the set of elements that degrade when `Δ` is applied:

```
G = {
  sessions_lost  : BGP sessions that go ESTABLISHED → not,
  prefixes_lost  : (node, prefix) entries removed from a node's RIB (watched prefixes only),
  reachability_lost : (src, dst) loopback pairs that become unreachable
}
```

The **model's job**: given `N`, `C₀`, `Δ`, output predicted `G_pred`. The model never sees Batfish.
The **score**: precision/recall/F1 of `G_pred` vs `G`, per element-type and aggregated.

> **[DECISION] The diff is given; the model predicts consequences.** Cleanest framing of "predict the blast radius," directly gradeable. The inverse (model writes a config, we score its safety) is a different task, deferred to v2.

---

## 3. Architecture — the model-free / eval seam

```
   topology specs ─┐
   intent specs  ──┤   ┌──────────── TASK GENERATOR (netbrace safety generate) ───────────┐
                   └──▶│ render baseline FRR (Jinja) → apply Δ → pre/ and post/ configs   │
                       │ emit TaskSpec JSON (validated against Pydantic schema)            │
                       └───────────────────────────────┬─────────────────────────────────┘
                                                        │
                       ┌──────────── ORACLE (netbrace safety oracle) ──────────────────────┐
                       │ Batfish DIFFERENTIAL: q.answer(snapshot=S1, reference_snapshot=S0)│
                       │ filter to watched prefixes → normalize → BlastRadius (stable keys)│
                       │ 3× determinism check; write into TaskSpec.oracle                  │
                       └───────────────────────────────┬─────────────────────────────────┘
        ============== model-free, deterministic, cached ===│=== model eval, re-runnable ===
                                                        │
                       ┌──────────── EVAL (Inspect AI; netbrace eval run) ─────────────────┐
   GPT-4o / Claude ───▶│ json_dataset(TaskSpec) → solver(prompt+generate) → G_pred         │
                       │ @scorer = netbrace grader (set P/R/F1, trap, invalid-vs-fail)      │
                       │ Inspect .eval log = source of truth (transcript, tokens, cost)    │
                       └───────────────────────────────┬─────────────────────────────────┘
                                                        │
                       ┌──────────── REPORT (netbrace report) ─────────────────────────────┐
                       │ read .eval log → RunManifest + results.csv + failure_modes.csv    │
                       │ → paper/figures/safety_f1_by_intent.pdf                           │
                       └──────────────────────────────────────────────────────────────────┘
```

**[DECISION] Inspect AI is central, not a fast-follow.** It owns the run loop, provider adapters, logging, caching, cost capture, and the `inspect view` transcript browser. Our `RunManifest` is a *thin export* of the Inspect log for paper reproducibility — never a parallel runner. Left of the seam is deterministic and model-free (runs once, cached); right of the seam needs no Batfish and no lab.

---

## 4. Data contracts

**[DECISION]** Pydantic v2 models in `netbrace/core/schemas.py` are the source of truth; JSON Schema is generated from them into `schemas/`. Every artifact on disk round-trips through these models. Keys are **fully-qualified strings** (VRF-safe), not bare tuples, so the same schema survives the move to multi-VRF / eBGP.

### 4.1 Stable IDs
```
task_id   : safety.<protocol>.<intent>.<topo_family>.<index>   e.g. safety.bgp.shut_neighbor.square4.0001
run_id    : YYYY-MM-DD_<model_slug>_<suite>_<solver>           e.g. 2026-06-14_gpt4o_safety_v0_direct
prompt_id : safety_direct_v0:<sha256[:12]>
snapshot  : <task_id>:pre | <task_id>:post
```

### 4.2 TaskSpec — `schemas/task.schema.json`
Self-contained; carries everything to regenerate the prompt, rebuild snapshots, and re-grade.
```json
{
  "schema_version": "netbrace.task.v0",
  "task_id": "safety.bgp.shut_neighbor.square4.0001",
  "family": "bgp", "intent": "shut_neighbor", "difficulty": "easy", "seed": 1,
  "topology": {"name": "square4", "nodes": ["r1","r2","r3","r4"],
               "links": [{"a_node":"r1","a_intf":"eth1","b_node":"r2","b_intf":"eth1"}],
               "routing_protocols": ["bgp"]},
  "baseline": {"config_format": "frr", "configs": {"r1": "...", "r2": "..."}},
  "change": {"change_id": "change.r1.shut_10_0_0_2", "format": "unified_diff",
             "target_nodes": ["r1"], "patch": "--- r1.conf\n+++ r1.conf\n...",
             "description": "Shut down the BGP neighbor 10.0.0.2 on r1 to drain it."},
  "watched_prefixes": ["10.0.0.1/32","10.0.0.2/32","10.0.0.3/32","10.0.0.4/32"],
  "presentation": {"prompt_template_id": "safety_direct_v0",
                   "operator_question": "Which BGP sessions and prefixes are lost after this change?"},
  "oracle": {"status": "ready", "engine": "batfish", "engine_version": "...",
             "computed_at": "...", "blast_radius": { /* §4.3 */ }},
  "meta": {"is_trap": false, "hand_validated": false, "source": "generated"}
}
```
**Validation rules:** `schema_version` exact; `task_id` matches filename; config node names ⊆ topology nodes; `change.target_nodes` valid; patch applies cleanly; prompt template exists; if `oracle.status == ready`, blast-radius is non-empty **unless** `meta.is_trap == true`.

### 4.3 BlastRadius — stable keyed sets (the canonical `G`)
Scoring keys are stable strings; human labels are extra metadata, never the key.
```json
{
  "sessions_lost": [
    {"key": "bgp|vrf=default|node=r1|peer_ip=10.0.0.2",
     "node": "r1", "vrf": "default", "peer_ip": "10.0.0.2"}],
  "prefixes_lost": [
    {"key": "route|node=r3|vrf=default|prefix=10.0.0.2/32",
     "node": "r3", "vrf": "default", "prefix": "10.0.0.2/32"}],
  "reachability_lost": [
    {"key": "reach|src=r3|dst=10.0.0.2/32|vrf=default",
     "src_node": "r3", "dst_prefix": "10.0.0.2/32", "vrf": "default"}]
}
```
Normalization (enforced by the oracle): nodes lowercased; prefixes canonical CIDR; sessions keyed by `(observing_node, peer_ip)` so a loss seen from both ends yields both rows; lists sorted + deduped so comparison is order-independent.

> **[DECISION] Sessions / prefixes / reachability score for v0.** `interfaces_affected` and `services_affected` stay in the schema (so the paper can discuss extension) but are not scored in v0.

### 4.4 ModelPrediction — `schemas/prediction.schema.json`
Mirrors `G` plus non-scored `confidence`/`rationale`. The parser is **forgiving about endpoint order, strict about node/prefix validity**: a predicted node or prefix that doesn't exist in the topology is dropped and counted toward a `hallucinated_refs` metric.

### 4.5 RunManifest — the reproducibility record (thin export of the Inspect log)
```json
{
  "schema_version": "netbrace.run_manifest.v0",
  "run_id": "2026-06-14_gpt4o_safety_v0_direct",
  "suite_id": "safety/v0", "suite_hash": "<sha256 of task set>",
  "git_commit": "c579cef", "git_dirty": false,
  "model": {"provider": "openai", "model_name": "gpt-4o", "temperature": 0.0,
            "max_output_tokens": 4096},
  "prompt_id": "safety_direct_v0:abc123def456",
  "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
  "environment": {"python": "...", "inspect_ai": "...", "pybatfish": "...", "batfish": "..."},
  "created_at": "...", "command": "netbrace eval run ..."
}
```
No secrets, no API keys, no full env dumps are ever written.

---

## 5. The oracle (Batfish gives us truth for free)

Batfish models the control plane statically — feed it configs, it computes resulting sessions, RIBs, forwarding, with no routers booted (snapshot load ≈ 0.27 s, measured on `frr_square`). For each task, `netbrace/batfish/oracle.py`:

1. Materialize `pre/` (baseline) and `post/` (baseline + patch) config dirs.
2. Init Batfish snapshots `S0`, `S1`; assert both **parse clean** (`fileParseStatus`, `initIssues`) — a parse failure fails loudly and dumps debug.
3. **[DECISION] Differential questions + watched-prefix filter** (composes the two plans):
   ```python
   sess = bf.q.bgpSessionStatus().answer(snapshot=S1, reference_snapshot=S0).frame()
   rts  = bf.q.routes().answer(snapshot=S1, reference_snapshot=S0).frame()
   ```
   Differential mode returns only *changed* rows. Keep session rows that went ESTABLISHED→not; keep route rows that were present in `S0`, absent in `S1`, **and whose prefix ∈ `watched_prefixes`** (kills connected/transit clutter).
4. `reachability_lost`: pairwise `traceroute` over watched loopback pairs on both snapshots, diff the success set. (`differentialReachability` evaluated as a faster alternative — see §13 Q1.)
5. Normalize → `BlastRadius` (§4.3); write into `TaskSpec.oracle`.

**Determinism gate:** compute each task's `BlastRadius` 3×, hash the normalized output; any task with inconsistent hashes is quarantined, not shipped. Batfish is deterministic, so this catches *generator* bugs.

**Oracle validation (scaled-down κ):** for 5 tasks, stand the topology up live in containerlab, apply `Δ`, and confirm real `show ip bgp summary` / RIB matches Batfish. This is the "we checked the oracle against reality" paragraph reviewers want. Full 100-task Cohen's κ → NeurIPS extension.

Refs: [Batfish differential questions](https://batfish.readthedocs.io/en/latest/notebooks/differentialQuestions.html), [forwarding change validation](https://batfish.readthedocs.io/en/latest/notebooks/linked/introduction-to-forwarding-change-validation.html), [bgpSessionStatus](https://batfish.readthedocs.io/en/stable/notebooks/linked/introduction-to-bgp-analysis.html).

---

## 6. The grader

Pure set arithmetic, fully deterministic, unit-tested before any model runs. For each type `t ∈ {sessions, prefixes, reachability}`:
```
TP=|Gpred[t]∩G[t]|  FP=|Gpred[t]\G[t]|  FN=|G[t]\Gpred[t]|
precision=TP/(TP+FP)  recall=TP/(TP+FN)  f1=2PR/(P+R)   (0 if denom 0)
```
- **macro-F1** = mean of the three per-type F1s → headline number.
- **micro-F1** = pooled TP/FP/FN → secondary.
- **exact_match** = `G_pred == G` → reported as a second column.

**Trap / empty-set rules** (the science from plan A):
- `G` empty ∧ `G_pred` empty → F1 = 1.0 (correctly predicted "no impact").
- `G` empty ∧ `G_pred` non-empty → F1 = 0.0, counted toward **`false_alarm_rate`**.
- `change_local_pref` traps deliberately have empty `G`; they separate models that *reason* from models that *panic at scary keywords*. This is a headline result, not an afterthought.

**[DECISION] Invalid ≠ wrong.** Unparseable / schema-violating output → status `invalid`, F1 = 0 in the aggregate, but tracked in a separate **`invalid_rate`** so a model's JSON-formatting failures never masquerade as reasoning failures. Status ladder: `pass` (exact or F1≥0.8) · `partial` (0<F1<0.8) · `fail` (valid, F1=0) · `invalid` · `error`.

Outputs feed a **failure-mode table by intent** (missing vs. extra sessions/prefixes per intent) for the §4 results narrative.

---

## 7. Inspect AI integration — three small files

We get free: provider adapters (OpenAI/Anthropic/Google), retries, rate-limits, token+cost logging, parallel sampling, the `.eval` log, and `inspect view`. We write:

```python
# netbrace/evals/inspect_safety.py
@task
def blast_radius(suite: str = "v0") -> Task:
    return Task(
        dataset=json_dataset(f"tasks/safety/{suite}/_index.jsonl",
            FieldSpec(input="presentation", target="oracle", id="task_id",
                      metadata=["intent","family","meta","watched_prefixes"])),
        solver=[system_message(SAFETY_CONTRACT), prompt_template(TASK_TEMPLATE), generate()],
        scorer=blast_radius_scorer(),
    )

# netbrace/evals/scorers.py
@scorer(metrics=[mean(), stderr()])
def blast_radius_scorer():
    async def score(state, target):
        pred = parse_prediction(state.output.completion)     # tolerant, §4.4
        G    = BlastRadius.model_validate_json(target.text)   # canonical truth
        per_type, macro_f1, flags = grade(pred, G)            # §6
        return Score(value=macro_f1, answer=state.output.completion,
                     metadata={"per_type": per_type, **flags})
    return score

# netbrace/prompts/safety_direct_v0.md  — SAFETY_CONTRACT + TASK_TEMPLATE (versioned, hashed)
```

Run (the `netbrace` CLI wraps these; raw Inspect also works):
```bash
netbrace eval run  --suite tasks/safety/v0 --model openai/gpt-4o --run-id 2026-06-14_gpt4o_safety_v0_direct
netbrace grade     --run runs/2026-06-14_gpt4o_safety_v0_direct
inspect view      --log-dir runs/2026-06-14_gpt4o_safety_v0_direct/logs   # failure analysis
```
Refs: [Inspect AI](https://inspect.aisi.org.uk/), [datasets](https://inspect.aisi.org.uk/datasets.html), [scorers](https://inspect.aisi.org.uk/scorers.html).

---

## 8. Package layout (thin — no runner, no router backend for v0)

```
NetBrace/
├── plan.md                     ← this file
├── pyproject.toml              ← netbrace package (replaces ad-hoc requirements)
├── schemas/                    ← JSON Schema generated from Pydantic
│   ├── task.schema.json  prediction.schema.json  blastradius.schema.json
├── netbrace/
│   ├── cli.py                  ← `netbrace` (Typer): generate · validate · oracle · eval · grade · report · lab
│   ├── core/                   ← schemas.py (Pydantic)  jsonio.py  ids.py  hashing.py
│   ├── tasks/safety/           ← generator.py  templates.py  validate.py  (+ Jinja in templates/)
│   ├── topology/               ← model.py  patches.py (unified-diff apply)  frr.py (renderer)
│   ├── batfish/                ← client.py  oracle.py  normalize.py
│   ├── models/                 ← fake.py  replay.py   (API-free dev; real calls go through Inspect)
│   ├── evals/                  ← inspect_safety.py  scorers.py
│   ├── graders/                ← sets.py  safety.py  (pure, unit-tested)
│   ├── prompts/                ← safety_direct_v0.md
│   ├── routers/                ← containerlab_readonly.py  (show-commands ONLY, for 5-task validation)
│   └── reporting/              ← summarize.py  figures.py
├── tasks/safety/v0/            ← _index.jsonl  manifest.json  _configs/<task_id>/{pre,post}/  <task_id>.json
├── runs/<run_id>/              ← logs/ (Inspect .eval)  manifest.json  results.csv  failure_modes.csv
├── tests/                      ← unit/  fixtures/  integration/   (§10)
└── scripts/                    ← start_batfish.sh  check_env.sh  smoke_safety_v0.sh
```
`external/netconfeval/` is untouched during the sprint.

---

## 9. CLI surface (stable, paste-into-README)

```bash
netbrace env check
netbrace safety generate --suite v0 --count 20 --seed 20260606 --out tasks/safety/v0
netbrace safety validate --suite tasks/safety/v0 [--require-oracle]
netbrace safety oracle   --suite tasks/safety/v0 --batfish-host 127.0.0.1 --overwrite
netbrace eval fake       --suite tasks/safety/v0 --run-id fake_safety_v0      # API-free E2E
netbrace eval run        --suite tasks/safety/v0 --model openai/gpt-4o --limit 3 --run-id smoke_gpt4o
netbrace grade           --run runs/<run_id>
netbrace report          --run runs/<run_id> --figures paper/figures
netbrace lab exec        --node r1 --cmd "vtysh -c 'show bgp summary'"        # read-only validation
```
Every command: `--verbose`, non-zero exit on validation failure, prints the artifact path it wrote.

---

## 10. Test strategy **[DECISION: no model run before schemas / patching / oracle / grader have unit coverage]**

**Unit (macOS, no Docker) — `pytest tests/unit`:**
`test_task_schema_round_trip` · `test_task_id_matches_filename` · `test_prediction_rejects_unknown_node` · `test_apply_unified_diff_success` · `test_apply_unified_diff_rejects_bad_context` · `test_blastradius_key_normalization_endpoint_order` · `test_score_sets_{exact,missing,extra,empty_empty}` · `test_trap_empty_pred_scores_1` · `test_trap_nonempty_pred_false_alarm` · `test_invalid_json_is_invalid_not_crash` · `test_macro_micro_f1` · `test_manifest_hash_stable`.

**Batfish integration — `pytest -m batfish` (lab host):**
`test_frr_square_parses` · `test_bgp_sessions_detected_pre` · `test_oracle_shut_neighbor_loses_session` · `test_oracle_remove_network_loses_prefix` · `test_oracle_deterministic_three_runs`.

**Containerlab — `pytest -m containerlab` (lab host, pre-run smoke only):** deploy/exec/destroy `frr_square`, confirm ESTABLISHED sessions.

**Fake/replay E2E — `scripts/smoke_safety_v0.sh`:** generate 3 tasks → oracle → fake model emits exact/partial/invalid → grade → assert summary has `pass=1, partial=1, invalid=1`. No API key required.

Golden fixtures live in `tests/fixtures/` (a minimal task, a valid prediction, an invalid-node prediction, an FRR baseline + a neighbor-removed patch).

---

## 11. Build order — vertical slice first, mapped to the sprint

Each step ends with a runnable command and a saved artifact. **Do not waterfall** — get one ugly-but-correct `generate → oracle → fake-model → grade → figure` slice working, then harden.

| Step | Deliverable | Proof command | Sprint slot |
|---|---|---|---|
| 0 | `pyproject.toml` + package skeleton + Pydantic schemas + unit tests | `pytest tests/unit -q` · `netbrace --help` | Wk A Mon |
| 1 | Generator: `square4` FRR from verified lab shape; `shut_neighbor` + `remove_network`; patch apply | `netbrace safety generate --count 5` · `netbrace safety validate` | Wk A Mon/Tue |
| 2 | Batfish oracle (differential + watched-prefix) + determinism gate | `netbrace safety oracle` · `pytest -m batfish` | Wk A Wed/Thu |
| 3 | Grader + fake/replay E2E | `bash scripts/smoke_safety_v0.sh` | Wk A Thu |
| 4 | 20 tasks; hand-validate 5 (incl. 1 live containerlab check) | `tasks/safety/v0/` populated | Wk A Fri/Sat |
| 5 | Inspect task + scorer + prompt; 1-task real GPT-4o smoke (<$10) | `netbrace eval run --limit 1` | Wk B Mon/Wed |
| 6 | Full GPT-4o run + report | `netbrace report` → `results.csv` | Wk B Sat/Sun |
| 7 | Add `rr_hier_8n` + `add_prefix_filter` + `change_local_pref` trap; scale to 50; add Claude | 50 tasks × 2 models | Wk C |
| 8 | `safety_f1_by_intent.pdf` + failure-mode table | `paper/figures/` | Wk C Sat |

**Sanity gate after Step 6:** GPT-4o macro-F1 should land in **20–70%**. >80% → tasks too easy (add transitive-withdrawal, route-map ordering, next-hop-self). <10% → prompt/parser broken (inspect via `inspect view`).

---

## 12. Reproducibility rules (non-negotiable — accuracy mandate)

1. Every number in the paper comes from a committed script/CLI command.
2. Every task JSON validates before evaluation.
3. Every oracle result is reproducible from baseline config + patch, and passed the 3× determinism gate.
4. Every model result preserves raw output, parsed output, score, prompt-id, and model metadata (via the Inspect log + `RunManifest`).
5. Every scoring rule has a unit test.
6. No HotNets-v0 ground truth depends on live router state — Batfish is the oracle; routers are validation only.
7. Router write tools are opt-in and out of scope for v0; agents (future) get read-only tools and never see post-change oracle output.
8. Never hand-edit a run summary — fix the reporter and rerun.
9. Prefer deleting/quarantining a broken generated task over salvaging an ambiguous one.

---

## 13. What reviewers will attack — and our built-in answer

| Objection | Answer |
|---|---|
| "Ground truth is just another model's guess" | Batfish is a formal static analyzer; differential output is deterministic (3× gate); validated against live containerlab on 5 tasks. |
| "Synthetic = unrealistic" | Topologies mirror real iBGP-RR designs; intents are real maintenance actions (drain a neighbor, add a filter). NOC-sourced scenarios are a stated extension. |
| "Grader is fuzzy / gameable" | Pure set P/R/F1 over stable keys; exact-match column; `invalid` tracked separately from `fail`; hallucinated refs counted. |
| "Just prompt it better" | Single-shot is the declared condition; identical contract across models; `change_local_pref` traps catch keyword-panic. |
| "n=20 is too small" | Position-paper norm; 50 by camera-ready; the *framework + the trap finding* is the contribution, the numbers motivate it. |
| "Not reproducible" | Suite hash + prompt hash + git commit in every `RunManifest`; figures regenerate from logs; pinned Batfish/Inspect versions. |

---

## 14. Open technical questions (resolve in Week A, before scaling past 5 tasks)

1. **`differentialReachability` vs. pairwise-`traceroute` diff** for `reachability_lost` — confirm the former's loopback-to-loopback semantics on FRR snapshots; default to pairwise traceroute if unsure.
2. **Does Batfish model FRR `neighbor shutdown`** as session-down (vs. parse-and-ignore)? If ignored, switch the `shut_neighbor` mutation to *removing* the `neighbor … remote-as` line, which Batfish definitely models.
3. **iBGP transitive prefix loss** — confirm Batfish withdraws a client's prefix from other clients when the reflector is shut (RR hierarchy); this transitive effect is the highest-value signal because LLMs miss it.
4. **FRR vs. Cumulus parse format + `route-map`/`prefix-list` semantics** — confirm modeled for `add_prefix_filter`; else narrow v0 to BGP-session intents.

---

## 15. First action

**Step 0–1:** `pyproject.toml`, Pydantic schemas + unit tests, and the generator re-rendering `frr_square` from a spec — proving the generator produces Batfish-parseable configs identical in behavior to the verified hand-built lab. That single proof is what everything else stands on.
