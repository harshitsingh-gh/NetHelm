# HANDOFF — NetBrace safety axis

> Read this before writing code. It is the resume point. The v0 single-dimension
> safety axis (D1–D3) is done and tested; the multi-dimensional extension
> (D4–D8) is built and partly oracle-backed on the `brainstorming-session`
> branch (PR #1). This file says exactly what exists, what is frozen, and what
> remains — in priority order.

---

## 0. Resume in 60 seconds

```bash
cd ~/projects/NetHelm
git checkout brainstorming-session              # PR #1; not yet merged to main
source harness/venvs/nethelm/bin/activate
bash scripts/repro_setup.sh                      # builds harness/venvs/nethelm/ (idempotent)
python -m pytest tests/unit -q                   # must print "889 passed, 5 skipped"
# Batfish must be up on 127.0.0.1:9996/9997 for any oracle/run command.
python scripts/run_extended_scenario.py --scenario blackhole   # zero-API smoke
```

Read `docs/multidimensional_blast_radius.md` first — it is the complete
end-to-end guide (dimensions, architecture, how to run, how to add scenarios,
results). This file only tracks status + remaining work.

---

## 1. Golden rules (unchanged — do not break)

1. **Never edit the frozen v0 core.** Other code and the suite hash depend on
   exact behavior. Add new modules instead (that is how all D4–D8 work was done):
   `core/schemas.py`, `core/jsonio.py`, `ids.py`, `hashing.py`,
   `graders/sets.py`, `graders/safety.py`, `evals/parser.py`,
   `topology/patches.py`, `tasks/safety/baseline_square4.py`,
   `tasks/safety/generator.py`, anything under `tests/unit/` that already passes.
2. **Run `pytest tests/unit -q` after every change.** Keep it green (889 passed, 5 skipped).
3. **Reuse the schemas / jsonio helpers.** Never `json.dump` a model by hand.
4. **Small, boring functions.** ~30 lines.
5. **No paid model API without human approval.** Always `--limit 1` / one call
   first, confirm cost < $10. (Real runs so far: Claude Haiku 4.5, pennies.)
6. **One command, one artifact** — every CLI/script prints the path it wrote.

---

## 2. What exists now (built + tested)

### v0 (D1–D3) — DONE, live-oracle verified
- Generator → suite → Batfish oracle → fake/real eval → grade → report.
- `netbrace/cli.py` (`safety generate|validate|oracle`, `eval fake|run`,
  `grade`, `report`). Committed v0 suite + oracle ground truth in
  `tasks/safety/v0/`. See `docs/project_guide.md`.

### Multi-dimensional (D4–D10) — built; D4/D5/D7–D10 oracle-backed; D6 deferred
| File | Role |
|---|---|
| `core/dimensions.py` | 7 new typed elements + `ExtendedBlastRadius` (composes v0 BlastRadius over D1–D10) |
| `graders/extended.py` | `grade_extended()` + `ExtendedScoreRecord` (reuses frozen `sets.py`) |
| `graders/semantic_sets.py` | semantic grader for D4/D7/D10-intent where exact-key match is too strict |
| `batfish/extended_oracle.py` | `ExtendedOracle.compute(scenario)` — **unified**, all dims on one snapshot pair; D1–D5, D7–D10 implemented; D6 returns [] (needs vendor config) |
| `tasks/safety/scenarios.py` | `Scenario` dataclass + `REGISTRY` (waypoint, blackhole, ecmp) |
| `tasks/safety/baseline_waypoint4.py` | D4 topology (2 disjoint paths) |
| `tasks/safety/baseline_ecmp4.py` | D5 topology (2 equal-cost paths) |
| `tasks/safety/scenario_blackhole.py` | D7 change on the square4 baseline |
| `evals/extended_parser.py` | tolerant raw-text → ExtendedBlastRadius (8-D) |
| `prompts/safety_extended_v0.md` | the 8-D output contract |
| `models/fake_extended.py` | zero-API ExtendedFakeModel + flat serializer |
| `scripts/run_extended_scenario.py` | prompt→model→parse→grade runner (fake or Claude) |
| `scripts/demo_extended_waypoint.py`, `demo_extended_blackhole.py` | focused demos |

Tests: `tests/unit/test_dimensions.py`, `test_extended_grader.py`,
`test_extended_parser.py`, `test_fake_extended.py`, `test_waypoint_baseline.py`,
`test_blackhole_scenario.py`, `test_ecmp_scenario.py`,
`test_scenarios_registry.py`, plus generator family tests for quiet-reroute
scenarios. **889 passed, 5 skipped.**

Verified facts (don't re-derive):
- Batfish column names match `oracle.py` (`Node`, `Remote_IP`, `VRF`,
  `Established_Status`; `Node`, `Network`, `VRF`, `Next_Hop_IP`).
- Blackhole disposition string is `NO_ROUTE`; delivered set is
  `{ACCEPTED, DELIVERED_TO_SUBNET, EXITS_NETWORK}`.
- The blackhole change's TRUE blast radius (unified oracle) is 4-D:
  `r1→10.0.0.4` + `r4→10.0.0.1` session losses, `r1` prefix `10.0.0.4/32`,
  `r1→10.0.0.4` reachability, and the `r1` blackhole.

---

## 3. What remains — in priority order

### P1 — Merge PR #1 to main
Branch `brainstorming-session`, PR #1. Review, then merge. Everything below is
extension work that can happen on new branches off main.

### P2 — Multi-sample × model-fleet sweep (this is the paper figure)
Current real-model numbers are **single Claude Haiku calls** — model output is
stochastic (the waypoint run hallucinated a redundancy loss on one sample). For
any number that goes in the paper:
- Run N≥5 samples per (scenario, model); report mean ± std of macro-F1 and the
  per-dimension P/R/F1.
- Fleet: at least `anthropic/claude-haiku-4-5-20251001`,
  `anthropic/claude-sonnet-4-6`, `openai/gpt-4o` (add `--model openai/...`
  support to `run_extended_scenario.py` — currently only `anthropic/` and
  `fake` are wired; the v0 `eval run` path uses Inspect for OpenAI).
- Add a `--samples N` flag to the runner and aggregate into a CSV +
  `reporting/` figure. Reuse `reporting/summarize.py` / `figures.py` patterns.
- Decide on a sampling temperature; record it in the run manifest.

### P3 — D6 (filter) oracle
Schema + grader + parser + prompt already handle `FilterDelta`. Missing: a
`compute_filter` that diffs ACL behavior. **Batfish does NOT model FRR ACLs as
interface packet filters**, so this needs a **vendor config** (Cisco IOS /
Arista / Juniper) snapshot. Plan:
- Add a small IOS/Arista baseline with an ACL applied to an interface (new
  `baseline_acl_*.py`); the change reorders/over-blocks an ACE (scenario S03/S04).
- `ExtendedOracle._filter_diff` via Batfish `searchFilters` differential →
  `FilterDelta(transition=permit_to_deny | deny_to_permit)`.
- This also unblocks a second config dialect in the harness (good for the paper).

### P4 — D8 (scale) oracle
`ScaleViolation` exists. Needs a per-device resource budget (FIB/RIB/label/TCAM
limit) as an annotation, then count installed routes pre/post and flag overflow.
Scenario S20 (de-aggregation). Pure-Batfish for the count; the *limit* is a spec
field — add `resource_limits: dict[node, dict[resource,int]]` to `Scenario`.

### P5 — Grader-validity (κ ≥ 0.7) for D4–D8
Per CLAUDE.md accuracy bar: hand-label a 100-task subset and check Cohen's κ
against the oracle for the new dimensions before publishing any number. D4/D6 are
the hard ones (subjective intent). Budget a labelling pass.

### P6 — Live-emulator (hybrid) scenarios
The catalog's hybrid scenarios (MTU/PMTUD blackhole, transient microloops,
stateful-firewall asymmetry, NAT data-plane, FIB overflow behavior) need
containerlab/Mininet, not static Batfish. Decide whether the paper needs them or
whether the static-gradeable set is enough for v1. NetPress/NIKA both pair a
generator with an emulator for exactly this.

### P7 — Generalize the v0 generator to new topologies (optional)
`tasks/safety/generator.py` is frozen and hardcodes square4. The new scenarios
bypass it (they build configs directly). If we want the full generate→suite→
oracle CLI flow for the new topologies, parameterize the baseline in a NEW
generator module (don't edit the frozen one).

### P8 — Wire extended path into the CLI / Inspect (optional)
`run_extended_scenario.py` is a standalone script. For parity with v0, add a
`netbrace eval extended` subcommand and/or an Inspect task + scorer for the 8-D
format (mirror `evals/inspect_safety.py` + `scorers.py`).

---

## 4. Gotchas / notes for whoever resumes

- **Model nondeterminism**: re-running a real model gives different predictions.
  Don't treat a single call as ground truth about the model — sample N.
- **The unified oracle is the source of truth**, not the per-dimension
  `compute_*` helpers (those are kept only for the focused demos). Use
  `ExtendedOracle.compute(scenario)`.
- **Adding a dimension to a scenario** = add the probe list to its `Scenario`
  builder in `scenarios.py`. Empty probe list → that dimension isn't scored.
- **Sanity gate for a new scenario**: `run_extended_scenario.py --scenario X`
  with the default fake oracle mode must be an exact pass (1.0). If not, the
  oracle and the fake serializer disagree — fix before trusting it.
- **`runs/` and `paper/figures/` are gitignored** — experiment outputs stay
  local and are reproducible from the scripts.
- Anthropic SDK is installed in the venv; `ANTHROPIC_API_KEY` must be exported
  to run a real model. OpenAI path not yet added to the extended runner.

---

## 5. Key references
- `docs/multidimensional_blast_radius.md` — full end-to-end guide (read first).
- `docs/authoring_topologies_and_scenarios.md` — build a verified topology.
- `paper/refs/blast_radius_scenario_catalog.md` — 20 scenarios + oracle ledger.
- `docs/project_guide.md` — v0 architecture. `docs/batfish_oracle_runbook.md` —
  Batfish setup. `plan.md` — original design + open questions.
