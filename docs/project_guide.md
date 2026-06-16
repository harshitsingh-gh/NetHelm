# NetBrace Project Guide

Everything about the codebase — what every file does, how the pipeline works,
and exactly how to run it end to end.

---

## 1. What this project is

**NetBrace** evaluates how well LLMs predict the "blast radius" of a network
configuration change — which BGP sessions, IP prefixes, and reachability paths
will break when a proposed diff is applied to a live network.

The pipeline has five stages:

```
generate tasks → oracle fills ground truth → model predicts → grade → report
```

The ground truth comes from Batfish (a static network analysis tool). The model
prediction is scored with precision/recall/F1 over three element types:
sessions, prefixes, reachability.

**Paper target:** "Can LLMs Predict the Blast-Radius of Network Configuration
Changes?" — HotNets 2026, submit July 15, 2026.

---

## 2. Repository layout

```
NetHelm/                           ← git repo root (project is called NetBrace)
├── netbrace/                      ← Python package (all source code)
│   ├── core/                      ← data contracts and pure utilities
│   │   ├── schemas.py             ← Pydantic models — the single source of truth
│   │   ├── jsonio.py              ← stable JSON read/write
│   │   ├── ids.py                 ← deterministic ID generation
│   │   └── hashing.py             ← SHA-256 helpers
│   ├── tasks/
│   │   └── safety/
│   │       ├── baseline_square4.py  ← verified 4-router FRR configs
│   │       └── generator.py         ← deterministic task generator
│   ├── topology/
│   │   └── patches.py             ← strict unified diff applier
│   ├── batfish/
│   │   └── oracle.py              ← Batfish ground-truth oracle
│   ├── graders/
│   │   ├── sets.py                ← pure set-comparison metrics
│   │   └── safety.py              ← the grader (calls sets.py)
│   ├── evals/
│   │   ├── parser.py              ← tolerant LLM output → BlastRadius parser
│   │   ├── run_fake.py            ← end-to-end pipeline with FakeModel
│   │   ├── inspect_safety.py      ← Inspect AI Task definition
│   │   └── scorers.py             ← Inspect AI scorer wrapping grade()
│   ├── models/
│   │   └── fake.py                ← FakeModel for pipeline testing
│   ├── storage/
│   │   ├── layout.py              ← write/load task suites to disk
│   │   └── run_store.py           ← persist model responses and scores
│   ├── reporting/
│   │   ├── summarize.py           ← aggregate results.csv → summary.json
│   │   └── figures.py             ← matplotlib bar chart PDF
│   ├── routers/
│   │   └── containerlab_readonly.py  ← read-only vtysh wrappers
│   ├── prompts/
│   │   └── safety_direct_v0.md    ← system prompt + task template
│   └── cli.py                     ← netbrace command-line interface
│
├── tests/
│   └── unit/                      ← 52 pytest unit tests (all pure, no I/O)
│
├── harness/
│   ├── lab/
│   │   ├── frr_square.clab.yml    ← containerlab topology definition
│   │   └── frr_square/configs/    ← FRR config files for live lab
│   └── venvs/                     ← Python virtualenvs (gitignored)
│       └── nethelm/               ← dev venv (activate this one)
│
├── runs/                          ← experiment outputs (gitignored)
├── tasks/                         ← sprint planning docs
├── paper/                         ← paper text and references
├── external/                      ← cloned external repos
│   └── netconfeval/
├── docs/
│   ├── project_guide.md           ← this file (architecture, end-to-end)
│   ├── authoring_topologies_and_scenarios.md  ← recipe: add new topologies/scenarios
│   └── batfish_oracle_runbook.md  ← Batfish setup and oracle verification
├── scripts/
│   ├── check_env.sh               ← environment sanity check
│   └── smoke_safety_v0.sh         ← end-to-end smoke test
├── plan.md                        ← technical design (authoritative)
├── HANDOFF.md                     ← implementation guide for the next session
├── pyproject.toml                 ← package config, deps, entry points
└── CLAUDE.md                      ← Claude Code context (goals, permissions)
```

---

## 3. Core data model

Everything is a Pydantic model from `netbrace/core/schemas.py`. Every artifact
written to disk goes through `netbrace/core/jsonio.py` (sorted-key JSON, stable
bytes).

### Key types

**`TaskSpec`** — one benchmark task. Contains:
- `task_id` — e.g. `safety.bgp.shut_neighbor.square4.0001`
- `topology` — node list, links, routing protocols
- `baseline` — one FRR config text per node (the converged baseline)
- `change` — unified diff patch + description + target nodes
- `watched_prefixes` — only these CIDR prefixes count for route scoring
- `oracle` — filled by Batfish; status (`pending`/`ready`/`error`) + `blast_radius`
- `meta` — is_trap flag (correct answer is "nothing breaks")

**`BlastRadius`** — what breaks when the change is applied:
- `sessions_lost: list[SessionLost]` — BGP sessions that go down
- `prefixes_lost: list[PrefixLost]` — routes that disappear from the RIB
- `reachability_lost: list[ReachabilityLost]` — src→dst pairs that lose connectivity

Each element has a `.key` property (stable string) used for set arithmetic.
`BlastRadius.normalized()` dedupes and sorts (call before comparing or storing).

**`ScoreRecord`** — grading output for one task:
- `status`: `pass` / `partial` / `fail` / `invalid`
- `macro_f1` — mean F1 across active element types
- `micro_f1` — F1 over pooled TP/FP/FN
- `exact_match` — prediction key-sets == ground truth key-sets
- `false_alarm` — trap task where model predicted impact when there was none
- `per_type` — per-element-type `TypeMetrics` (tp, fp, fn, precision, recall, f1)

---

## 4. The five pipeline stages in detail

### Stage 1: Generate tasks

**File:** `netbrace/tasks/safety/generator.py`

Produces `TaskSpec` objects deterministically from a `GenerationSpec(count,
intents)`. The baseline configs come from `baseline_square4.py` (4 FRR routers
already verified in Batfish). Two intents are implemented:

- **`shut_neighbor`**: removes all three `neighbor <peer_ip> ...` lines for one
  peer on one node. Expected blast: BGP session drops from both ends.
- **`remove_network`**: removes the `network 10.0.0.X/32` origination line on one
  node. Expected blast: the prefix is withdrawn from every peer's **BGP RIB**
  (a D9 event) — but it stays in the **main RIB** via the static route, so the
  v0 `prefixes_lost` (main-RIB) diff sees NOTHING. The v0 oracle therefore
  grades this change as an (incorrect) **empty** blast radius — a false-quiet.
  Grade it instead via `ExtendedOracle` + `bgp_watch_prefixes` (D9). The shipped
  v0 suite is `shut_neighbor`-only for this reason (see
  `tests/unit/test_v0_remove_network_guard.py`).

The generator produces (4×3) + 4 = 16 unique tasks for a full set (12
shut_neighbor + 4 remove_network). `--count` caps or extends by cycling through
combinations.

> **Design caveat (square4 BGP is forwarding-decorative).** The square4 baseline
> reaches every loopback via a full mesh of `/32` static routes (admin-distance 1),
> which shadow the iBGP-learned routes — so BGP **never installs to the main RIB**;
> the iBGP control plane is verified for *session/origination* behavior but the
> *forwarding* path rides the statics. A scenario on this baseline must therefore
> NOT claim a main-RIB / forwarding effect from a BGP-only change (that is exactly
> why `remove_network` is a v0 false-quiet above). Forwarding-effect scenarios use
> the IGP-backed (OSPF) baselines instead. The static-mesh-as-IGP is a deliberate
> determinism fixture, not idiomatic design.

```bash
netbrace safety generate --count 20 --out tasks/safety/v0
```

### Stage 2: Oracle fills ground truth

**File:** `netbrace/batfish/oracle.py`

For each task:
1. Materialises two snapshot directories in `/tmp` (baseline and post-change)
2. Initialises each in Batfish via pybatfish
3. Runs `bgpSessionStatus` on both; sessions in pre but not post → `sessions_lost`
4. Runs `routes` on both; prefixes in pre but not post, filtered to
   `watched_prefixes` → `prefixes_lost`
5. Optionally runs `traceroute` for `reachability_lost` (pass `--reachability`)
6. Writes result back to the task JSON file

```bash
netbrace safety oracle --suite tasks/safety/v0 --host 127.0.0.1
netbrace safety validate --suite tasks/safety/v0 --require-oracle
```

See `docs/batfish_oracle_runbook.md` for the full setup and verification guide.

### Stage 3: Model prediction

**Without API spend (FakeModel):**

`netbrace/models/fake.py` — `FakeModel` has three modes:
- `oracle` — echoes the task's `oracle.blast_radius` as a JSON block → F1=1.0
- `empty` — predicts empty blast radius → correct for trap tasks, F1=0 otherwise
- `garbage` — returns non-JSON text → grader marks `invalid`

```bash
netbrace eval fake --suite tasks/safety/v0 --run-id fake_oracle
netbrace eval fake --suite tasks/safety/v0 --run-id fake_garbage --mode garbage
```

**With a real model (Inspect AI):**

`netbrace/evals/inspect_safety.py` builds an Inspect AI `Task`. The dataset is
the suite. Each sample's `input` is the full prompt (topology + configs + diff)
built by `_build_prompt()`. The `target` is the oracle's `blast_radius` JSON.

```bash
export OPENAI_API_KEY=sk-...
netbrace eval run \
  --suite tasks/safety/v0 \
  --model openai/gpt-4o \
  --limit 1 \
  --run-id smoke_gpt4o
```

The system prompt and task template are in `netbrace/prompts/safety_direct_v0.md`.

### Stage 4: Parse and grade

**Parser:** `netbrace/evals/parser.py` — `parse_prediction(raw_text)`

Tolerant: extracts the last `\`\`\`json ... \`\`\`` block, or falls back to the
last balanced `{...}`. Accepts both dict-form and list-form elements. Returns
`None` only if no JSON object is found at all (→ grader marks `invalid`).

**Grader:** `netbrace/graders/safety.py` — `grade(prediction, ground_truth, ...)`

Pure function. Computes per-type precision/recall/F1 via `graders/sets.py`, then
takes macro-average over active types (types empty in both truth and prediction
are excluded). Special cases:
- `prediction is None` → `status = "invalid"`, `macro_f1 = 0.0`
- Trap task + truth empty + prediction non-empty → `false_alarm = True`
- Both empty → F1 = 1.0 (vacuous truth: "correctly predicted nothing breaks")
- `macro_f1 >= 0.80` → `status = "pass"`
- `macro_f1 > 0.0` → `status = "partial"`
- `macro_f1 == 0.0` → `status = "fail"`

**Run the grading loop:**

For fake runs, grading happens inside `run_fake.py` automatically.
For Inspect AI runs, grading happens in the Inspect scorer (`scorers.py`).
To re-grade an existing run's raw outputs:

```bash
netbrace grade --run runs/<run-id>
```

### Stage 5: Report

**File:** `netbrace/reporting/summarize.py`, `figures.py`

Reads `results.csv`. Writes `summary.json` with overall mean macro-F1,
per-intent mean F1, invalid rate, false alarm rate. Generates a bar chart PDF
grouped by intent (and by model if `results.csv` has a `model` column).

```bash
netbrace report --run runs/<run-id> --figures paper/figures
# outputs: paper/figures/safety_f1_by_intent.pdf
#          runs/<run-id>/summary.json
```

---

## 5. Disk layout for a run

```
runs/<run-id>/
├── tasks/
│   └── safety.bgp.shut_neighbor.square4.0001/
│       ├── response.raw.txt        ← raw model output text
│       ├── response.parsed.json    ← parsed BlastRadius (or "{}")
│       └── score.json              ← ScoreRecord
├── results.csv                     ← one row per task, all scores
├── summary.json                    ← aggregates (written by report)
└── run_manifest.json               ← metadata (model, suite hash, etc.)
```

---

## 6. Environment setup from scratch

```bash
# 1. Clone the repo (directory is still called NetHelm)
cd ~/projects/NetHelm

# 2. Create and activate the dev venv
python3 -m venv harness/venvs/nethelm
source harness/venvs/nethelm/bin/activate

# 3. Install the package + dev deps
pip install -e ".[dev]"

# 4. Verify
python -m pytest tests/unit -q          # must print "52 passed"
netbrace --help                          # must show the CLI

# 5. Install heavy deps when needed
pip install -e ".[oracle]"   # pybatfish + pandas (needs Batfish container)
pip install -e ".[eval]"     # inspect-ai (needs API key)
pip install -e ".[report]"   # matplotlib + pandas (always safe to install)
```

---

## 7. End-to-end run commands

### Without API spend (full pipeline test)

```bash
source harness/venvs/nethelm/bin/activate
pip install -e ".[report]"

# Generate 20 tasks
netbrace safety generate --count 20 --out tasks/safety/v0

# Validate structure (no oracle yet)
netbrace safety validate --suite tasks/safety/v0

# Run fake eval — oracle mode (predicts ground truth perfectly)
netbrace eval fake --suite tasks/safety/v0 --run-id fake_oracle

# Report
netbrace report --run runs/fake_oracle --figures paper/figures
cat runs/fake_oracle/results.csv | head -5
# Expected: all macro_f1=1.0
```

### With Batfish (ground truth)

```bash
# See docs/batfish_oracle_runbook.md for full setup
docker run -d --name batfish -p 9996:9996 -p 9997:9997 batfish/allinone:nethelm
pip install -e ".[oracle]"

netbrace safety oracle --suite tasks/safety/v0 --host 127.0.0.1
netbrace safety validate --suite tasks/safety/v0 --require-oracle

# Fake eval now uses real ground truth
netbrace eval fake --suite tasks/safety/v0 --run-id fake_gt_check
```

### With a real model (GPT-4o, 1-task smoke)

```bash
pip install -e ".[eval]"
export OPENAI_API_KEY=sk-...

# Must have run oracle first (--require-oracle must pass)
netbrace eval run \
  --suite tasks/safety/v0 \
  --model openai/gpt-4o \
  --limit 1 \
  --run-id smoke_gpt4o

# Inspect viewer
inspect view --log-dir runs/smoke_gpt4o/logs

# Report
netbrace report --run runs/smoke_gpt4o --figures paper/figures
```

### Smoke script (CI-equivalent, no API, no Batfish)

```bash
bash scripts/smoke_safety_v0.sh
# Runs: generate 3 → validate → fake eval → report → assert PDF exists
```

---

## 8. CLI reference

```
netbrace safety generate  --count N --out DIR
    Generate N tasks, write to DIR. Prints DIR path.

netbrace safety validate  --suite DIR [--require-oracle]
    Check structural consistency of every task.
    --require-oracle: also assert oracle.status=="ready" for all tasks.
    Exits nonzero if any problem.

netbrace safety oracle    --suite DIR --host H [--reachability]
    Run BatfishOracle against a live Batfish at host H.
    Fills oracle.blast_radius and sets oracle.status="ready" (or "error").
    --reachability: also compute traceroute-based reachability_lost (slow).

netbrace eval fake        --suite DIR --run-id ID [--mode oracle|empty|garbage]
    Run FakeModel over the suite and grade. Writes runs/<ID>/results.csv.
    Mode 'oracle' echoes ground truth → F1=1.0.
    Mode 'garbage' → all invalid.

netbrace eval run         --suite DIR --model MODEL --run-id ID [--limit N]
    Run a real model via Inspect AI. MODEL format: provider/name
    (e.g. openai/gpt-4o, anthropic/claude-sonnet-4-6).
    Requires API key as env var. --limit caps tasks processed.

netbrace grade            --run DIR
    Re-read all response.raw.txt files in runs/<ID>/tasks/ and re-write
    results.csv. Use if you changed the grader and want to regrade.

netbrace report           --run DIR --figures DIR
    Read results.csv, write summary.json + safety_f1_by_intent.pdf.
    Requires [report] extras.
```

---

## 9. Test suite

```
tests/unit/
├── test_schemas.py     — canonicalization, key generation, round-trips, consistency
├── test_patches.py     — unified diff applier correctness and error handling
├── test_grader.py      — set metrics + grade() all branches (pass/partial/fail/invalid/trap)
├── test_parser.py      — parse_prediction() with fenced JSON, lists, bare objects, malformed
├── test_generator.py   — count, uniqueness, determinism, patch round-trips, consistency
├── test_storage.py     — write_suite/load_suite round-trip, manifest hash, sorted index
└── test_run_store.py   — FakeModel modes, write_sample, write_results_csv columns
```

Run:

```bash
python -m pytest tests/unit -q         # must be 52 passed
python -m pytest tests/unit -v         # verbose names
python -m pytest tests/unit -k grader  # filter by name
```

The tests are **pure** — no I/O, no Batfish, no API keys. They run anywhere and
run in under 0.1 seconds.

---

## 10. Files that must never be edited (their tests are the spec)

These files encode invariants that the rest of the system depends on:

| File | What must not change |
|------|----------------------|
| `core/schemas.py` | Data types, field names, key formats, canonicalization logic |
| `core/jsonio.py` | Output byte format (suite hashes depend on it) |
| `core/ids.py` | ID format (task filenames depend on it) |
| `core/hashing.py` | Hash algorithm (manifest reproducibility) |
| `graders/sets.py` | Precision/recall/F1 arithmetic |
| `graders/safety.py` | Grade status ladder, macro/micro aggregation |
| `evals/parser.py` | Parser behaviour (invalid vs wrong is a research metric) |
| `topology/patches.py` | Patch applier strictness (generator self-checks against it) |
| `tasks/safety/baseline_square4.py` | Config text (Batfish verified; changes invalidate all oracle results) |
| `tasks/safety/generator.py` | Determinism and task structure |
| `tests/unit/` | Tests themselves are the acceptance criteria |

If you think one needs changing, check plan.md §4 first.

---

## 11. How oracle outputs and model scores relate to the paper

The paper claims: *"we score LLM blast-radius predictions with precision/recall/F1
over BGP sessions, prefixes, and reachability — no prior benchmark does this."*

The chain of evidence for that claim:

1. `generator.py` produces a task from verified configs → stored in `tasks/safety/v0/`
2. `oracle.py` computes ground truth via Batfish → stored in `task.oracle.blast_radius`
3. The model receives the prompt (built by `inspect_safety._build_prompt`)
4. `parser.py` extracts a BlastRadius from the model output
5. `graders/safety.py` scores it → stored in `score.json`
6. `results.csv` aggregates all scores
7. `summary.json` + `safety_f1_by_intent.pdf` go into the paper

Every number in the paper is traceable to:
- A committed task file in `tasks/safety/v0/`
- An oracle result stored in that task file
- A run directory in `runs/<run-id>/`
- A git commit hash captured in `run_manifest.json`

Before finalising any paper number, run the grader-validity check:
100-task human-labelled subset, Cohen's κ ≥ 0.7 (see plan.md §9).
