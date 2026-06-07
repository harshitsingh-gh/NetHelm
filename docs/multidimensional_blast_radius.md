# NetBrace — Multi-Dimensional Blast Radius (end-to-end guide)

This is the complete guide to the multi-dimensional blast-radius work on the
`brainstorming-session` branch: what it is, how every piece fits together, how to
run all of it (including a real model like Claude), how scenarios and ground
truth are defined and read, how to add your own, and the first real-model
results. It is self-contained — start here.

Related docs:
- `docs/project_guide.md` — the v0 architecture (D1–D3 only).
- `docs/authoring_topologies_and_scenarios.md` — how to build a verified topology.
- `paper/refs/blast_radius_scenario_catalog.md` — the 20-scenario research catalog.
- `docs/batfish_oracle_runbook.md` — Batfish setup.

---

## 1. The idea in one paragraph

A network change rarely breaks just "a BGP session." Its **blast radius** is
multi-dimensional: it can reroute traffic off a mandatory inspection node, halve
the redundant paths to a prefix, flip a firewall rule, or silently blackhole
traffic — often while every destination still *looks* reachable. NetBrace's
safety axis asks a model to predict that blast radius, and scores the prediction
with precision/recall/F1 against **Batfish-computed ground truth**. The v0 core
scored three dimensions; this branch adds five more and proves three of them
end-to-end with a live oracle and a real model.

**Why it matters:** a single-axis grader (the kind every prior benchmark uses)
*over-penalises* a model that reasons holistically and *under-reports* the true
damage of a change. The multi-dimensional oracle is the contribution — the
scoring surface, not the topology.

---

## 2. The eight dimensions

Every prediction and every ground truth is a set of *typed elements*. Each
element has a deterministic string `key`; grading is set precision/recall/F1 per
type, macro-averaged over the types that are non-empty in truth or prediction.

| Dim | Type key | Element (fields) | Oracle question | Status |
|---|---|---|---|---|
| D1 | `sessions` | `SessionLost(node, peer_ip, vrf)` | `bgpSessionStatus` diff | ✅ live |
| D2 | `prefixes` | `PrefixLost(node, prefix, vrf)` | `routes` diff (watched) | ✅ live |
| D3 | `reachability` | `ReachabilityLost(src_node, dst_prefix, vrf)` | `traceroute` delivered diff | ✅ live |
| D4 | `waypoint` | `WaypointViolation(src_node, dst_prefix, waypoint, vrf)` | `traceroute` transit check | ✅ live |
| D5 | `redundancy` | `RedundancyLoss(node, dst_prefix, before/after_paths)` | `routes` next-hop count drop | ✅ live |
| D6 | `filter` | `FilterDelta(node, src_ip, dst_ip, transition, proto, dport)` | `searchFilters` diff | ⛔ no oracle yet |
| D7 | `forwarding` | `ForwardingAnomaly(node, dst_prefix, kind)` | `traceroute` disposition | ✅ live |
| D8 | `scale` | `ScaleViolation(node, resource, limit, observed)` | route/FIB count vs spec | ⛔ no oracle yet |

D1–D3 live in the frozen `core/schemas.py` (`BlastRadius`). D4–D8 are added in
`core/dimensions.py` (`ExtendedBlastRadius`, which *composes* the v0
`BlastRadius` and adds the five new lists). Nothing in the v0 core was edited.

D6 needs a vendor config (Batfish doesn't model FRR ACLs as packet filters) and
D8 needs a per-device resource budget — so they have schema + grader + parser but
no `compute_*` oracle yet.

---

## 3. End-to-end architecture

```
 Scenario  ──►  ExtendedOracle.compute()  ──►  ExtendedBlastRadius   (ground truth)
 (registry)        live Batfish                       │
     │                                                │
     │  _build_prompt()                               │
     ▼                                                ▼
  prompt  ──►  model (fake | Claude)  ──►  raw text  ──►  parse_extended_prediction()
                                                                 │
                                                                 ▼
                                                         ExtendedBlastRadius  (prediction)
                                                                 │
                          grade_extended(prediction, ground_truth)
                                                                 ▼
                                            ExtendedScoreRecord (per-type P/R/F1, macro, micro)
```

Component → file:

| Stage | File |
|---|---|
| Scenario definition + registry | `netbrace/tasks/safety/scenarios.py` |
| Topologies (baselines + changes) | `netbrace/tasks/safety/baseline_waypoint4.py`, `baseline_ecmp4.py`, `scenario_blackhole.py` |
| Ground-truth oracle (live Batfish) | `netbrace/batfish/extended_oracle.py` |
| Element types | `netbrace/core/dimensions.py` |
| Grader | `netbrace/graders/extended.py` |
| Prompt contract | `netbrace/prompts/safety_extended_v0.md` |
| Output parser | `netbrace/evals/extended_parser.py` |
| Fake model (zero-API) | `netbrace/models/fake_extended.py` |
| Runner (prompt→model→parse→grade) | `scripts/run_extended_scenario.py` |
| Focused demos | `scripts/demo_extended_waypoint.py`, `demo_extended_blackhole.py` |

---

## 4. How ground truth is computed (the unified oracle)

`ExtendedOracle.compute(scenario)` does it all on **one pair of snapshots**:

1. Materialise the **pre** configs and the **post** configs (baseline with the
   change patch applied to the target node) into two Batfish snapshots.
2. **D1** — established BGP sessions in pre minus post → `SessionLost`.
3. **D2** — RIB prefixes in pre minus post, filtered to `watched_prefixes` →
   `PrefixLost`.
4. **D3** — for each `reachability_flows` (src, dst): delivered pre, not post →
   `ReachabilityLost`.
5. **D4** — for each `waypoint_intents` (src, dst, W): every accepted pre-trace
   transits W but some post-trace does not → `WaypointViolation`.
6. **D5** — for each `redundancy_targets` (node, dst): installed next-hop count
   drops but stays ≥1 → `RedundancyLoss`.
7. **D7** — for each `forwarding_flows` (src, dst): delivered pre, dropped post
   with disposition NO_ROUTE/NULL_ROUTED/LOOP → `ForwardingAnomaly`.

**Why "unified" matters (a real bug we hit):** an earlier per-dimension oracle
computed only D7 for the blackhole scenario, leaving D1–D3 empty. Claude
correctly predicted *both* the blackhole and the reachability loss — but the
reachability prediction was scored as a false alarm because the single-axis
ground truth didn't contain it. The unified oracle computes every declared
dimension, so the ground truth is the *complete* true blast radius and holistic
predictions are credited correctly.

**Determinism:** Batfish is a static analyzer; the same snapshots give the same
answer. (The v0 oracle has a determinism gate, `plan.md §5`; quarantine any
scenario whose output varies across runs.)

---

## 5. How to read a scenario

A `Scenario` (in `scenarios.py`) is a plain dataclass:

```python
Scenario(
    name="waypoint4",                 # topology name
    nodes=["src","way","alt","dst"],
    pre_configs={...},                # {node: FRR config text} — the baseline
    change_target="src",             # which node the patch edits
    patch="<unified diff>",          # the proposed change
    description="...",               # human summary (goes in the prompt)
    intents_text="src->10.0.0.4/32 MUST transit `way`.",
    watched_prefixes=["10.0.0.4/32"],          # D2 scored over these
    reachability_flows=[("src","10.0.0.4/32")],# D3 (src, dst) to test
    waypoint_intents=[("src","10.0.0.4/32","way")], # D4 (src, dst, must-transit)
    redundancy_targets=[],            # D5 (node, dst)
    forwarding_flows=[],              # D7 (src, dst)
)
```

The **probe lists decide which dimensions get ground truth.** Empty list → that
dimension is simply not scored for this scenario. D1 (sessions) is always
computed (it's a cheap whole-network query).

The three shipped scenarios (each demonstrates a dimension invisible to a
session-only view):

| Key | Topology | Change | Headline dimension | True blast radius (Batfish) |
|---|---|---|---|---|
| `waypoint` | 4-node, two disjoint paths | reroute src→dst off `way` onto `alt` | **D4** | waypoint violation only (still reachable) |
| `ecmp` | 4-node, two equal-cost paths | remove one of src's two static routes | **D5** | redundancy 2→1 (still reachable) |
| `blackhole` | square4 iBGP mesh | remove r1's static route to 10.0.0.4 | **D7** | **4-D**: 2 sessions + 1 prefix + 1 reachability + 1 blackhole |

The blackhole is the instructive one: a one-line "cleanup" of a seemingly
redundant static route severs the recursive next-hop for r1's iBGP route to
10.0.0.4, which Batfish shows cascading into a session drop (both directions), a
RIB prefix loss, a reachability loss, and a silent blackhole.

---

## 6. How to run everything

### 6.1 Setup
```bash
cd ~/projects/NetHelm
source harness/venvs/nethelm/bin/activate
pip install -e ".[oracle]"        # pybatfish + pandas (needs Batfish running)
# Batfish container should already be up on 127.0.0.1:9996/9997
python -m pytest tests/unit -q    # 91 passed
```

### 6.2 Unit tests (pure, no Batfish, no API)
```bash
python -m pytest tests/unit -q
```

### 6.3 Zero-API end-to-end (fake model proves the loop)
```bash
# oracle mode = perfect predictor -> exact pass; empty = naive miss; garbage = invalid
python scripts/run_extended_scenario.py --scenario waypoint              # macro_f1=1.0
python scripts/run_extended_scenario.py --scenario blackhole --mode empty # fail (naive)
python scripts/run_extended_scenario.py --scenario ecmp                   # macro_f1=1.0
```

### 6.4 Focused single-dimension demos (write artifacts to runs/)
```bash
python scripts/demo_extended_waypoint.py     # D4, shows v0 grader is blind
python scripts/demo_extended_blackhole.py    # D7
```

### 6.5 Run a REAL model (Claude) — costs money
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
# cheapest model:
python scripts/run_extended_scenario.py --scenario waypoint \
    --model anthropic/claude-haiku-4-5-20251001
# other ids: anthropic/claude-sonnet-4-6, anthropic/claude-opus-4-8
```
Each scenario is one short call (pennies on Haiku). Outputs land in
`runs/run_ext_<scenario>_<model>/`:
- `prompt.txt` — exactly what was sent
- `response.raw.txt` — the model's raw answer
- `score.json` — the graded `ExtendedScoreRecord` (per-type P/R/F1)

---

## 7. How to add a new scenario

1. **Build a verified topology** following
   `docs/authoring_topologies_and_scenarios.md` (deterministic addressing +
   Batfish/containerlab GATEs). Put the baseline + change in a new
   `netbrace/tasks/safety/baseline_<name>.py` (mirror `baseline_waypoint4.py`):
   export `NODES`, `LOOPBACK_IP`, `LINKS`, `CHANGE_TARGET`, `baseline_configs()`,
   and `change_patch()`.
2. **Register it** in `scenarios.py`: add a builder returning a `Scenario` with
   the probe lists for the dimensions you want scored, and an entry in `REGISTRY`.
3. **Verify ground truth**:
   ```bash
   python scripts/run_extended_scenario.py --scenario <name>   # fake oracle -> 1.0
   ```
   If oracle mode isn't an exact pass, the oracle and the fake serializer
   disagree — fix before trusting it.
4. (Optional) add a pure unit test mirroring `test_ecmp_scenario.py`.

You do **not** hand-write the answer — the oracle computes it. To add a brand-new
*dimension*, add the element to `core/dimensions.py` and a `_<dim>_diff` helper to
`extended_oracle.py`; the grader and parser already iterate all eight types.

---

## 8. First real-model results (Claude Haiku 4.5)

One call per scenario, graded against the **unified** oracle. (Model output is
stochastic; these are single-sample runs — a real benchmark would average N.)

| Scenario | Dims in truth | status | macro F1 | What Haiku did |
|---|---|---|---|---|
| ecmp | redundancy | **pass** | 1.00 | exact — caught the D5 redundancy loss |
| waypoint | waypoint | partial | 0.50 | caught D4 exactly, but **hallucinated** a redundancy loss (FP) |
| blackhole | sessions×2, prefix, reachability, forwarding | partial | 0.50 | got the data-plane (reachability + blackhole) **exactly**, but **missed** the second-order control-plane effects (2 session losses + 1 prefix loss) |

Per-dimension detail for blackhole: `reachability` f1=1.0, `forwarding` f1=1.0,
`sessions` f1=0.0 (2 FN), `prefixes` f1=0.0 (1 FN).

**Reading of these numbers (paper-relevant):**
- Even the cheapest model reasons well about **direct, data-plane** effects.
- It **misses second-order, control-plane** consequences (a blackhole's induced
  session/prefix loss) — and sometimes **hallucinates** a dimension that doesn't
  apply. These are precisely the failure modes a multi-dimensional benchmark is
  built to surface; a session-only benchmark would score the blackhole case a
  perfect pass and miss the story entirely.
- The 0.5 on `blackhole` is now a **genuine model limitation**, not the earlier
  oracle artifact — the difference the unified oracle makes.

---

## 9. What is NOT done (honesty ledger)

- **D6 (filter) and D8 (scale)** have schema + grader + parser + prompt, but no
  `compute_*` oracle. D6 needs a vendor (non-FRR) config; D8 needs a device
  resource budget. See the catalog for the gradeability ledger.
- **Hybrid scenarios** in the catalog (MTU/PMTUD, transient microloops, stateful
  firewalls, NAT) need a live emulator (containerlab/Mininet) for their
  data-plane signal — Batfish static analysis can't model them.
- **No multi-sample / multi-model sweep yet.** Results above are single Haiku
  calls. A paper figure needs N samples × the model fleet.
- **Grader-validity (κ ≥ 0.7)** human labelling not yet done for D4–D8.

---

## 10. Commit map (this branch)

| Commit | What |
|---|---|
| Task C | live Batfish v0 oracle + authoring guide |
| Brainstorm | 20-scenario catalog + D4–D8 schema/grader |
| D4 | waypoint oracle (live) |
| D7 | blackhole oracle (live) |
| parser+prompt+runner | real-model path |
| D5 | redundancy/ECMP oracle |
| unified oracle | all dims on one snapshot pair + scenario registry |

Unit tests grew 52 → 91, all green; the frozen v0 core was never edited.
