# NetHELM Safety Axis — Technical Plan (HotNets 2026)

> **Status:** Design — v1
> **Created:** 2026-06-06
> **Scope:** The blast-radius prediction task only. This is the technical design behind the [HotNets sprint plan](tasks/plan_2026-06-04_hotnets_sprint.md). Strategy/velocity rationale lives there and in [temporary/plan_comparison.md](temporary/plan_comparison.md); this document is the *how it works*.
> **Paper:** "Can LLMs Predict the Blast-Radius of Network Configuration Changes? A Preliminary Evaluation"

---

## 0. The thesis in one sentence

Given a converged network and a proposed configuration change, can an LLM predict **which BGP sessions, prefixes, and reachability** the change will break — *before* it is applied? We build a pipeline that (a) generates such change scenarios, (b) computes the true impact with Batfish, (c) asks an LLM to predict the impact, and (d) scores the prediction with precision/recall/F1. No prior benchmark scores this.

---

## 1. What we are building (and not building)

### In scope
- A **task generator** that emits `(topology, baseline config set, proposed diff)` scenarios.
- A **ground-truth oracle**: Batfish in differential mode computes the exact blast-radius of each diff.
- An **LLM evaluation harness** built on **Inspect AI** (no custom runner/storage).
- A **scorer**: set-comparison precision/recall/F1 over the predicted vs. true blast-radius.
- A **results store**: Inspect AI's native `.eval` logs + a flattened CSV for the paper figure.
- 20–50 tasks, 2 models (GPT-4o, Claude Sonnet), single-shot.

### Explicitly NOT in scope (deferred to NeurIPS extension)
- Live containerlab in the grading loop — **Batfish static analysis is the oracle**; containers are used only to *validate the oracle* on a 5-task sample.
- Multi-vendor (FRR only for v1).
- The other 5 task categories (K/C/B/D/R).
- Custom harness code, model adapters, storage layer — Inspect AI provides all of it.
- Agentic/multi-turn — single-shot prediction only.

---

## 2. The task, formally

A **task** is a tuple `T = (N, C₀, Δ)` where:

- `N` — a **topology**: nodes, links, addressing, AS layout.
- `C₀` — the **baseline configuration set**: one config per node, in a *converged* state (all intended BGP sessions ESTABLISHED, all intended prefixes reachable). This is the "before."
- `Δ` — a **proposed diff**: a single, localized configuration change to one node (e.g., shut a neighbor, add a prefix filter).

The **ground-truth blast-radius** `G` is the set of network elements that degrade when `Δ` is applied:

```
G = {
  sessions_lost      : set of (node, peer) BGP sessions that go ESTABLISHED → not,
  prefixes_lost      : set of (node, prefix) entries removed from a node's RIB,
  reachability_lost  : set of (src, dst) loopback pairs that become unreachable
}
```

The **model's job**: given a natural-language + structured description of `N`, `C₀`, and `Δ`, output its predicted `G_pred`. The model never sees Batfish.

The **score**: precision, recall, F1 of `G_pred` against `G`, computed per element-type and aggregated.

> **Key design decision:** the diff is *given*; the model predicts *consequences*. This is the cleanest framing of "predict the blast radius" and is directly, automatically gradeable. (The inverse task — model generates a config, we score its safety — is config-synthesis safety, deferred to v2.)

---

## 3. System architecture

```
                         ┌──────────────────────────────────────────────┐
                         │            TASK GENERATOR                     │
                         │  generate_v0.py                               │
                         │                                               │
   topology specs ──────▶│  1. render baseline configs (Jinja → FRR)    │
   intent templates ────▶│  2. apply Δ → mutated configs                │
                         │  3. emit task JSON (N, C₀, Δ) + raw configs   │
                         └───────────────────┬──────────────────────────┘
                                             │  pre/ and post/ config dirs
                                             ▼
                         ┌──────────────────────────────────────────────┐
                         │         GROUND-TRUTH ORACLE                    │
                         │  oracle.py  (pybatfish)                        │
                         │                                               │
                         │  init_snapshot(pre)  → S0                      │
                         │  init_snapshot(post) → S1                      │
                         │  bgpSessionStatus(S1, ref=S0)  → Δ sessions    │
                         │  routes(S1, ref=S0)            → Δ prefixes    │
                         │  reachability diff             → Δ services    │
                         │                                               │
                         │  → writes ground_truth: G into task JSON       │
                         └───────────────────┬──────────────────────────┘
                                             │  tasks/safety/v0/{id}.json (complete)
                                             ▼
                         ┌──────────────────────────────────────────────┐
                         │        LLM EVAL HARNESS  (Inspect AI)         │
                         │  safety_task.py                               │
                         │                                               │
   json_dataset ────────▶│  @task → Dataset[Sample]                      │
                         │  solver: prompt template + generate()         │
   GPT-4o / Claude ─────▶│  model emits G_pred (strict JSON)             │
                         │  @scorer: parse → set P/R/F1 vs target G       │
                         └───────────────────┬──────────────────────────┘
                                             │  .eval log (per-sample scores + transcript)
                                             ▼
                         ┌──────────────────────────────────────────────┐
                         │           RESULTS / TRACKING                  │
                         │  inspect view  (interactive)                  │
                         │  export.py → runs/<date>_<model>/results.csv  │
                         │  figure.py  → paper/figures/f1_by_intent.pdf  │
                         └──────────────────────────────────────────────┘
```

Two halves with a clean seam: **everything left of the dotted line is deterministic and model-free** (generation + oracle), runs once, and is cached as task JSON. **Everything right is the model eval**, re-runnable per model with zero Batfish dependency. This means model runs are cheap, reproducible, and don't need the lab up.

---

## 4. Schemas

All schemas are JSON, one file per concept, validated with `jsonschema`. Versioned by a top-level `schema_version` field so the dataset format can evolve without silently breaking the grader.

### 4.1 Topology schema — `schemas/topology.schema.json`

Declarative, vendor-neutral. The generator renders this into FRR configs. Designed so we can swap the renderer for Arista cEOS later without touching topologies.

```json
{
  "schema_version": "topo-1",
  "topo_id": "rr_hier_8n",
  "description": "8-node iBGP route-reflector hierarchy, single AS",
  "asn_default": 65000,
  "nodes": [
    {
      "name": "rr1",
      "role": "route-reflector",         // route-reflector | client | edge | core
      "router_id": "10.0.0.1",
      "loopback": "10.0.0.1/32",
      "asn": 65000
    }
  ],
  "links": [
    {
      "a": {"node": "rr1", "iface": "eth1", "ip": "192.0.2.1/30"},
      "b": {"node": "c1",  "iface": "eth1", "ip": "192.0.2.2/30"}
    }
  ],
  "bgp": {
    "type": "ibgp-full-mesh",            // ibgp-full-mesh | ibgp-rr | ebgp | mixed
    "sessions": [
      {"local": "rr1", "peer": "c1", "peer_ip": "10.0.0.2",
       "rr_client": true, "next_hop_self": true, "update_source": "lo"}
    ],
    "originated_prefixes": [
      {"node": "c1", "prefix": "10.0.0.2/32"}
    ]
  },
  "static_routes": [
    {"node": "rr1", "dest": "10.0.0.2/32", "next_hop": "192.0.2.2"}
  ]
}
```

> Mirrors the verified `frr_square` lab exactly (AS 65000, /32 loopbacks, /30 links, static routes for loopback reachability so iBGP `update-source lo` sessions can form). The `role` and `bgp.type` fields are what let us scale to the harder topology levels (RR hierarchy, dual-homed eBGP) without new code.

### 4.2 Intent / diff schema — `schemas/intent.schema.json`

The catalog of change types. Each intent is a parametric mutation over a baseline. This is the axis of difficulty.

```json
{
  "schema_version": "intent-1",
  "intent_id": "shut_neighbor",
  "category": "bgp",                      // bgp | filter | policy | interface
  "params": {
    "node": "rr1",
    "neighbor_ip": "10.0.0.2"
  },
  "mutation": {                           // how the renderer edits the config
    "op": "add_lines",
    "target_block": "router bgp 65000",
    "lines": ["neighbor 10.0.0.2 shutdown"]
  },
  "nl_description": "Operator shuts down the BGP neighbor 10.0.0.2 on rr1 to drain it for maintenance.",
  "expected_blast_class": "session_and_dependent_prefixes"
}
```

**v0 intent catalog (the 4 we ship first):**

| `intent_id` | What it does | Why it's interesting for blast-radius |
|---|---|---|
| `shut_neighbor` | `neighbor X shutdown` | Direct session loss + *transitive* prefix loss for prefixes only reachable via that peer. LLMs miss the transitive part. |
| `add_prefix_filter` | `route-map` / `prefix-list` deny on a neighbor | Selective prefix loss; tests whether model reads the filter semantics. |
| `change_local_pref` | `set local-preference` in an inbound route-map | Often a *trap*: no blast radius (traffic shifts but nothing is lost). Tests false-positive rate. |
| `remove_network_statement` | drop a `network X` under address-family | Prefix withdrawn fleet-wide; every other node loses it. Wide blast radius from a one-line change. |

> `change_local_pref` is deliberately a near-zero-blast-radius case. A model that screams "outage!" at every diff scores terribly on it. This is how we separate models that *reason* from models that *pattern-match on scary keywords*.

### 4.3 Task schema — `schemas/task.schema.json`

The atomic unit. One file per task: `tasks/safety/v0/<task_id>.json`. Self-contained — carries everything the harness and grader need.

```json
{
  "schema_version": "task-1",
  "task_id": "v0_shut_neighbor_rrhier_0007",
  "topo_id": "rr_hier_8n",
  "intent_id": "shut_neighbor",
  "intent_params": {"node": "rr1", "neighbor_ip": "10.0.0.2"},

  "presentation": {
    "topology_summary": "8 routers in AS 65000. rr1/rr2 are route reflectors; c1..c6 are clients...",
    "device_configs": {                  // the configs the MODEL sees (baseline only)
      "rr1": "<FRR config text>",
      "c1": "<FRR config text>"
    },
    "proposed_change": "On rr1, add: `neighbor 10.0.0.2 shutdown`"
  },

  "artifacts": {                          // pointers for the oracle; NOT shown to model
    "pre_config_dir":  "tasks/safety/v0/_configs/v0_..._0007/pre",
    "post_config_dir": "tasks/safety/v0/_configs/v0_..._0007/post"
  },

  "ground_truth": {                       // filled by oracle.py — see 4.4
    "sessions_lost": [["rr1","10.0.0.2"], ["rr2","10.0.0.2"]],
    "prefixes_lost": [["c3","10.0.0.2/32"], ["c4","10.0.0.2/32"]],
    "reachability_lost": [["c3","10.0.0.2"], ["c4","10.0.0.2"]],
    "oracle": {
      "batfish_version": "...",
      "computed_at": "2026-06-..",
      "deterministic": true,             // verified: 3 reruns identical
      "snapshot_load_s": 0.27
    }
  },

  "meta": {
    "difficulty": "medium",
    "hand_validated": false,
    "is_trap": false                     // true for the no-blast-radius cases
  }
}
```

### 4.4 Ground-truth schema — embedded `ground_truth` block (above)

The canonical representation of `G`. Three sets, each a list of tuples, **sorted and deduplicated** so set comparison is order-independent. Normalization rules (enforced by `oracle.py`):

- Node names lowercased; prefixes in canonical CIDR (`10.0.0.2/32`, not `10.0.0.2`).
- A session is keyed by `(observing_node, peer_ip)` — directional, because a session loss is observed from both endpoints and we want both.
- `prefixes_lost[i] = (node, prefix)` means: prefix was in `node`'s main RIB in S0 and is absent in S1.
- `reachability_lost[i] = (src_node, dst_loopback_ip)` means: traceroute from src to dst succeeded in S0, fails in S1.

### 4.5 LLM interface — prompt contract + response schema

**Prompt** (rendered by the Inspect solver from `presentation`): system message sets the role and the *exact output contract*; user message carries topology summary, configs, and the proposed change.

**Response contract** — the model MUST return a single fenced JSON object:

```json
{
  "sessions_lost":     [["rr1","10.0.0.2"]],
  "prefixes_lost":     [["c3","10.0.0.2/32"]],
  "reachability_lost": [["c3","10.0.0.2"]],
  "reasoning": "rr1 reflects c2's prefix to clients; shutting it..."
}
```

Parsing rules (in the scorer, tolerant by design so we grade *prediction quality* not *JSON skill*):
- Extract the last ```json fenced block; fall back to the last `{...}` span.
- Coerce single IPs to `/32`, lowercase nodes, dedupe.
- Missing key → empty set (counts as "predicted nothing" for that type).
- Unparseable output → score 0 on all types, flagged `parse_fail: true` in metadata (tracked separately so we can report parse-failure rate honestly).

### 4.6 Scoring schema — `Score` value written by the `@scorer`

```json
{
  "value": 0.57,                          // headline = macro-F1 across the 3 types
  "answer": "<model JSON>",
  "metadata": {
    "per_type": {
      "sessions":     {"tp":1,"fp":0,"fn":1,"precision":1.0,"recall":0.5,"f1":0.667},
      "prefixes":     {"tp":2,"fp":1,"fn":0,"precision":0.667,"recall":1.0,"f1":0.8},
      "reachability": {"tp":0,"fp":0,"fn":2,"precision":0.0,"recall":0.0,"f1":0.0}
    },
    "macro_f1": 0.57,
    "micro_f1": 0.61,                     // pooled tp/fp/fn across types
    "exact_match": false,                 // G_pred == G exactly
    "parse_fail": false,
    "is_trap": false
  }
}
```

> For trap tasks (empty `G`), precision/recall are undefined by the standard formula. Rule: if `G` is empty and `G_pred` is empty → F1 = 1.0 (correctly predicted "no impact"); if `G` empty and `G_pred` non-empty → F1 = 0.0 (false alarm). Tracked separately as `false_alarm_rate`.

### 4.7 Run / tracking schema

Inspect AI writes a `.eval` log per run (per-sample scores, full transcript, model params, token counts, cost) into `runs/<date>_<model>_safety/logs/`. We add one derived artifact for the paper:

```
runs/2026-06-14_gpt4o_safety_v0/
├── logs/                       # native Inspect .eval files (source of truth)
├── results.csv                 # flattened: task_id, intent_id, model, macro_f1,
│                               #   per-type p/r/f1, parse_fail, is_trap, tokens, cost
└── summary.json                # aggregates: mean F1 overall + per intent_id + per model
```

`export.py` reads the `.eval` log via `inspect_ai.log.read_eval_log` and writes `results.csv` — never hand-rolled, always derived from the immutable log.

---

## 5. The ground-truth oracle (how Batfish gives us truth for free)

This is the load-bearing idea of the whole paper. Batfish models the control plane statically: feed it configs, it computes the resulting BGP sessions, RIBs, and forwarding — **without booting a single router**. Snapshot load is ~0.27s (measured on `frr_square`).

For each task, `oracle.py`:

1. Builds **two snapshots** from the generated configs:
   - `S0` = baseline (`pre/` config dir)
   - `S1` = baseline + Δ (`post/` config dir)
2. Runs Batfish **differential questions** — every question accepts `snapshot=` and `reference_snapshot=`:
   ```python
   sess = bf.q.bgpSessionStatus().answer(snapshot=S1, reference_snapshot=S0).frame()
   rts  = bf.q.routes().answer(snapshot=S1, reference_snapshot=S0).frame()
   ```
   Differential mode returns only the rows that **changed** between snapshots, tagged with which snapshot they came from. Sessions that flipped ESTABLISHED→not and routes that vanished *are* the blast radius — computed, not guessed.
3. For `reachability_lost`, runs `traceroute` between all loopback pairs on both snapshots and diffs the success set (cheaper alternative under evaluation: `differentialReachability`).
4. Normalizes into the `ground_truth` block (4.4) and writes it back into the task JSON.

**Determinism guarantee:** each ground truth is computed 3× and required to be byte-identical; non-deterministic tasks are dropped. Batfish is deterministic by construction, so this is a guard against generator bugs, not against Batfish.

**Oracle validation (the κ check, scaled down for HotNets):** for 5 tasks, stand up the *actual* `frr_square`-style topology in containerlab, apply Δ live, and confirm the real `show ip bgp summary` / RIB matches Batfish's prediction. This is the "we checked the oracle against reality" paragraph reviewers will want. Full Cohen's κ over 100 tasks is deferred to the NeurIPS extension.

References: [Batfish differential questions](https://batfish.readthedocs.io/en/latest/notebooks/differentialQuestions.html), [forwarding change validation](https://batfish.readthedocs.io/en/latest/notebooks/linked/introduction-to-forwarding-change-validation.html), [bgpSessionStatus](https://batfish.readthedocs.io/en/stable/notebooks/linked/introduction-to-bgp-analysis.html).

---

## 6. The grader

Pure set arithmetic, no ML, fully deterministic — exactly what a reviewer wants for a benchmark.

For each element type `t ∈ {sessions, prefixes, reachability}`:
```
TP = |G_pred[t] ∩ G[t]|
FP = |G_pred[t] \ G[t]|
FN = |G[t] \ G_pred[t]|
precision = TP / (TP + FP)      # 0 if denom 0
recall    = TP / (TP + FN)      # 0 if denom 0
f1        = 2PR / (P + R)       # 0 if denom 0
```
- **macro-F1** = mean of the three per-type F1s → the headline number.
- **micro-F1** = pooled TP/FP/FN across types → secondary.
- **exact_match** = `G_pred == G` → the hardest bar, reported as a second column.

Trap handling per 4.6. Everything lands in the `Score.metadata` so the paper figure can break F1 down by intent type and show the false-alarm column.

---

## 7. Inspect AI integration (what we write vs. what we get free)

We get free: model adapters (OpenAI, Anthropic, Google), retries/rate-limits, cost+token logging, parallel sampling, the `.eval` log format, and `inspect view` (an interactive transcript browser — invaluable for failure analysis in §4 of the paper).

We write three small files:

```python
# harness/safety/safety_task.py
from inspect_ai import task, Task
from inspect_ai.dataset import json_dataset, FieldSpec
from inspect_ai.solver import generate, system_message, prompt_template

@task
def blast_radius(version: str = "v0") -> Task:
    return Task(
        dataset=json_dataset(
            f"tasks/safety/{version}/_index.jsonl",
            FieldSpec(input="presentation", target="ground_truth", id="task_id",
                      metadata=["intent_id", "topo_id", "meta"]),
        ),
        solver=[system_message(SAFETY_CONTRACT), prompt_template(TASK_TEMPLATE), generate()],
        scorer=blast_radius_scorer(),
    )
```

```python
# harness/safety/scorer.py
from inspect_ai.scorer import scorer, Score, Target, mean, stderr
from inspect_ai.solver import TaskState

@scorer(metrics=[mean(), stderr()])
def blast_radius_scorer():
    async def score(state: TaskState, target: Target) -> Score:
        pred = parse_prediction(state.output.completion)   # tolerant parser, 4.5
        truth = json.loads(target.text)                    # ground_truth block
        per_type, macro_f1 = prf1(pred, truth)             # §6
        return Score(value=macro_f1, answer=state.output.completion,
                     metadata={"per_type": per_type, ...})
    return score
```

```python
# harness/safety/prompts.py   — SAFETY_CONTRACT + TASK_TEMPLATE (4.5)
```

Run:
```bash
inspect eval harness/safety/safety_task.py --model openai/gpt-4o      --log-dir runs/2026-06-14_gpt4o_safety_v0/logs
inspect eval harness/safety/safety_task.py --model anthropic/claude-3-7-sonnet-latest --log-dir runs/.../logs
inspect view --log-dir runs/2026-06-14_gpt4o_safety_v0/logs        # failure analysis
```

Sources: [Inspect AI](https://inspect.aisi.org.uk/), [datasets](https://inspect.aisi.org.uk/datasets.html), [scorers](https://inspect.aisi.org.uk/scorers.html).

---

## 8. Directory layout

```
NetHelm/
├── plan.md                         ← this file
├── schemas/
│   ├── topology.schema.json
│   ├── intent.schema.json
│   ├── task.schema.json
│   └── prediction.schema.json
├── topologies/
│   ├── frr_square.topo.json        ← the verified 4-node lab, as a topo spec
│   └── rr_hier_8n.topo.json        ← Level-2 RR hierarchy
├── intents/
│   ├── shut_neighbor.intent.json
│   ├── add_prefix_filter.intent.json
│   ├── change_local_pref.intent.json
│   └── remove_network_statement.intent.json
├── harness/
│   ├── safety/
│   │   ├── generate_v0.py          ← Jinja renderer: topo+intent → pre/post FRR configs + task JSON
│   │   ├── oracle.py               ← pybatfish differential → ground_truth
│   │   ├── safety_task.py          ← Inspect @task
│   │   ├── scorer.py               ← Inspect @scorer (P/R/F1)
│   │   ├── prompts.py
│   │   └── export.py               ← .eval log → results.csv + summary.json
│   ├── templates/                  ← Jinja2 FRR config templates
│   │   ├── frr_base.conf.j2
│   │   └── interfaces.j2
│   └── venvs/{batfish,netconfeval} ← existing
├── tasks/safety/v0/
│   ├── _index.jsonl                ← one line per task (Inspect dataset)
│   ├── _configs/<task_id>/{pre,post}/
│   └── <task_id>.json              ← full task w/ ground truth
└── runs/<date>_<model>_safety_v0/  ← Inspect logs + results.csv + figure
```

---

## 9. Build sequence (maps to the HotNets sprint weeks)

| Step | File(s) | Output | Sprint slot |
|---|---|---|---|
| 1 | `schemas/*.json` | Frozen schemas, validated | Week A Mon |
| 2 | `topologies/frr_square.topo.json` + `templates/*.j2` + `generate_v0.py` | Re-render the verified lab from a topo spec; configs Batfish-parse | Week A Mon/Tue |
| 3 | `intents/*.json` + mutation engine in `generate_v0.py` | 4 intents apply cleanly, post-configs parse | Week A Tue/Wed |
| 4 | `oracle.py` | `ground_truth` populated; determinism check passes | Week A Wed/Thu |
| 5 | generate 20 tasks; hand-validate 5 (incl. 1 live containerlab check) | `tasks/safety/v0/` with 20 graded tasks | Week A Fri/Sat |
| 6 | `safety_task.py` + `scorer.py` + `prompts.py` | `inspect eval` runs end-to-end on 1 task | Week B Mon/Wed |
| 7 | full GPT-4o run + `export.py` | `results.csv`, mean F1 in 20–70% band | Week B Sat/Sun |
| 8 | add `rr_hier_8n`, scale to 50, add Claude | 50 tasks × 2 models | Week C |
| 9 | `figure.py` | `f1_by_intent.pdf` | Week C Sat |

**Sanity gate after Step 7:** if GPT-4o macro-F1 > 80%, tasks are too easy (add transitive-impact intents, bigger topologies); if < 10%, the prompt contract or parser is broken (inspect the transcript via `inspect view`). Target band: **20–70%**.

---

## 10. Determinism, validity, and what reviewers will attack

| Reviewer objection | Our answer (built into the design) |
|---|---|
| "Ground truth is just another model's guess" | Batfish is a formal static analyzer, not an LLM; differential output is deterministic; we validate 5 tasks against live containerlab. |
| "Synthetic tasks are unrealistic" | Topologies mirror real iBGP-RR designs; intents are real maintenance actions (drain a neighbor, add a filter). NOC-sourced scenarios are a stated extension. |
| "Grader is gameable / fuzzy" | Pure set P/R/F1, exact-match column, tolerant parser scored separately so JSON-format failures don't masquerade as reasoning failures. |
| "Models just need better prompting" | Single-shot is the stated scope; the contract is explicit and identical across models; `change_local_pref` traps catch keyword-panic strategies. |
| "n=20 is too small" | Position paper / preliminary by HotNets norms; 50 by camera-ready; the *framework* is the contribution, the numbers are the motivation. |
| "Determinism not shown" | 3× recompute identity check, dropped if non-identical; Batfish version pinned in every `ground_truth` block. |

---

## 11. Open technical questions (resolve during Week A)

1. **`differentialReachability` vs. pairwise `traceroute` diff** for `reachability_lost` — the former is one call but its semantics over loopback-to-loopback need confirming on FRR snapshots. Default to pairwise traceroute diff if unsure; it's slower but unambiguous.
2. **Does Batfish model `neighbor shutdown` on FRR** as session-down (vs. parse-and-ignore)? Must verify in Step 4 — if not, switch the `shut_neighbor` mutation to removing the `neighbor remote-as` line, which Batfish definitely models.
3. **iBGP transitive prefix loss** — confirm Batfish withdraws a client's prefix from other clients when the reflector is shut (RR hierarchy), since that transitive effect is the part LLMs miss and thus our most valuable signal.
4. **FRR vs. Cumulus parse format** — Batfish parses these configs as Cumulus FRR; confirm `route-map`/`prefix-list` semantics for `add_prefix_filter` are modeled, else narrow v0 to BGP-session intents only.

These four are exactly the `shut_neighbor` / `add_prefix_filter` checks the [sprint risk register](tasks/plan_2026-06-04_hotnets_sprint.md) flags for Week A. Resolve them before scaling past 5 tasks.

---

## 12. First action

Step 1–2: freeze the schemas and re-render `frr_square` from a topo spec, proving the generator produces Batfish-parseable configs identical in behavior to the hand-built lab. Everything else builds on that single proof.
