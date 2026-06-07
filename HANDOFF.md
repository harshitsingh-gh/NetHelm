# HANDOFF — NetBrace Safety Axis Implementation

> **Read this fully before writing any code.** It tells you exactly what exists,
> what is already tested (and must NOT be changed), and the small, well-specified
> pieces you are responsible for. Your job is **simple glue code** around a core
> that is already written and verified. Do not redesign anything.
>
> The full design rationale is in **`plan.md`** (repo root). This file is the
> implementation guide. When in doubt, follow the function signatures here
> literally and keep the unit tests green.

---

## 1. Environment — do this first

A dev virtualenv already exists with the package installed editable:

```bash
# from the repo root /home/harshitsingh/projects/NetHelm
source harness/venvs/nethelm/bin/activate     # activate the venv
python -m pytest tests/unit -q                 # MUST print "52 passed" before you start
```

To re-create the venv if needed:

```bash
python3 -m venv harness/venvs/nethelm
harness/venvs/nethelm/bin/pip install -e ".[dev]"
```

Heavy deps (Batfish, Inspect, matplotlib) are optional extras:

```bash
harness/venvs/nethelm/bin/pip install -e ".[oracle]"   # pybatfish + pandas
harness/venvs/nethelm/bin/pip install -e ".[eval]"     # inspect-ai
harness/venvs/nethelm/bin/pip install -e ".[report]"   # matplotlib + pandas
```

---

## 2. Golden rules (follow these exactly)

1. **Never edit these files** — they are tested and other code depends on their exact
   behavior. If you think one needs changing, you are probably wrong; ask first.
   - `netbrace/core/schemas.py`
   - `netbrace/core/jsonio.py`, `ids.py`, `hashing.py`
   - `netbrace/graders/sets.py`, `netbrace/graders/safety.py`
   - `netbrace/evals/parser.py`
   - `netbrace/topology/patches.py`
   - `netbrace/tasks/safety/baseline_square4.py`, `generator.py`
   - anything under `tests/unit/`
2. **Run `python -m pytest tests/unit -q` after every change.** It must stay at
   "52 passed" (plus any new tests you add). If a number drops, revert your last edit.
3. **Reuse the existing schemas.** Every object you read or write is a Pydantic model
   from `netbrace.core.schemas`. Use `netbrace.core.jsonio.write_model` / `read_model`
   / `to_json` — never `json.dump` a model yourself.
4. **Keep functions small and boring.** No clever metaprogramming. ~30 lines max.
5. **Do not call a paid model API** until a human approves it. Any real run must be
   `--limit 1` first and cost < $10.
6. **One command, one artifact.** Every CLI subcommand prints the path it wrote.

---

## 3. What exists and is working (DO NOT REBUILD)

| File | What it gives you |
|---|---|
| `core/schemas.py` | `TaskSpec`, `BlastRadius`, `SessionLost`/`PrefixLost`/`ReachabilityLost`, `ModelPrediction`, `RunManifest`, `ScoreRecord`, `TypeMetrics`. |
| `core/jsonio.py` | `to_json`, `write_model`, `read_model` |
| `core/ids.py` | `task_id`, `run_id`, `prompt_id`, `slug` |
| `core/hashing.py` | `sha256_text`, `suite_hash` |
| `graders/safety.py` | `grade(prediction, ground_truth, ...) -> ScoreRecord` |
| `evals/parser.py` | `parse_prediction(raw_text) -> BlastRadius | None` |
| `topology/patches.py` | `apply_unified_diff(source, patch) -> str` |
| `tasks/safety/generator.py` | `generate(GenerationSpec(count, intents)) -> list[TaskSpec]` |
| `tasks/safety/baseline_square4.py` | 4-router configs, NODES, LOOPBACK_IP, WATCHED_PREFIXES, LINKS |
| `batfish/oracle.py` | `BatfishOracle(host).compute(task)` — written, needs live Batfish run |
| `storage/layout.py` | `write_suite`, `load_suite`, `write_task`, `load_task` |
| `storage/run_store.py` | `create_run`, `write_sample`, `write_results_csv`, `write_run_manifest` |
| `models/fake.py` | `FakeModel(mode)` — oracle/empty/garbage modes |
| `evals/run_fake.py` | `run_fake(suite_dir, run_id, mode)` — zero-API pipeline |
| `evals/scorers.py` | `blast_radius_scorer()` — Inspect AI scorer |
| `evals/inspect_safety.py` | `safety_task(suite_dir, limit)` — Inspect AI Task |
| `reporting/summarize.py` | `summarize(run_dir)` — writes `summary.json` |
| `reporting/figures.py` | `f1_by_intent(run_dir, out_pdf)` — bar chart PDF |
| `prompts/safety_direct_v0.md` | System prompt + Jinja2 task template |
| `cli.py` | `netbrace` CLI — generate, validate, oracle, fake, run, grade, report |
| `scripts/check_env.sh` | Environment sanity check |
| `scripts/smoke_safety_v0.sh` | End-to-end smoke test |
| `routers/containerlab_readonly.py` | Read-only vtysh wrappers for live FRR nodes |

**Data flow:**
```
generate() → TaskSpec(oracle=pending)
   → BatfishOracle.compute() fills oracle.blast_radius   [code done, needs lab run — Task C]
      → model predicts → parse_prediction()
         → grade()
            → write_results_csv() → summarize() → f1_by_intent()
```

---

## 4. TASK STATUS

### ✅ Task A — Storage layer · DONE
`netbrace/storage/layout.py` — 5 unit tests in `tests/unit/test_storage.py`

### ✅ Task B — CLI skeleton · DONE
`netbrace/cli.py` — all subcommands wired

### ✅ Task C — Run the oracle on the lab host · DONE (2026-06-07)

Ran end-to-end against live Batfish + 4-node FRR lab. Column names verified
against `oracle.py` expectations (matched — no edit needed). 12-task v0 suite:
all `oracle.status=ready`, all `deterministic=True`. Cross-checked vs live
`vtysh show ip bgp summary`. See `progress.md` Day 19. Original procedure:

1. Ensure Batfish is running on ports 9996/9997. `pip install -e ".[oracle]"`.
2. **Verify column names FIRST (critical):** run ONE shut_neighbor task in a Python
   shell, print `df.columns.tolist()` for the `bgpSessionStatus` and `routes` frames.
   Expected: `Node`, `Remote_IP`, `Established_Status`, `Network`, `VRF`. If any
   differ, fix them in `oracle.py` and re-run `pytest tests/unit -q`.
3. Run:
   ```bash
   netbrace safety generate --count 12 --out tasks/safety/v0
   netbrace safety oracle --suite tasks/safety/v0 --host 127.0.0.1
   netbrace safety validate --suite tasks/safety/v0 --require-oracle
   ```
4. Manually inspect 1-2 oracle outputs vs `show ip bgp summary` from the live router.
5. Resolve plan.md §14 Q2/Q3: does removing neighbor lines drop the session? Does the
   RIB change? Whatever Batfish says IS ground truth.

### ✅ Task D — Fake model + run store · DONE
`netbrace/models/fake.py`, `netbrace/storage/run_store.py`, `netbrace/evals/run_fake.py`
4 unit tests in `tests/unit/test_run_store.py`

### ✅ Task E — Reporting · DONE
`netbrace/reporting/summarize.py`, `netbrace/reporting/figures.py`

### ✅ Task F — Inspect AI integration · DONE
`netbrace/evals/inspect_safety.py`, `netbrace/evals/scorers.py`

Acceptance (human approves spend):
```bash
netbrace eval run --suite tasks/safety/v0 --model openai/gpt-4o --limit 1 --run-id smoke_gpt4o
```

### ✅ Task G — Prompt template · DONE
`netbrace/prompts/safety_direct_v0.md`

### ✅ Task H — Scripts + read-only lab helper · DONE
`scripts/check_env.sh`, `scripts/smoke_safety_v0.sh`, `netbrace/routers/containerlab_readonly.py`

---

## 5. Definition of done

```bash
source harness/venvs/nethelm/bin/activate
python -m pytest tests/unit -q                                       # 52+ green
netbrace safety generate --count 12 --out tasks/safety/v0
netbrace safety oracle   --suite tasks/safety/v0 --host 127.0.0.1   # Task C (lab)
netbrace safety validate --suite tasks/safety/v0 --require-oracle
netbrace eval fake       --suite tasks/safety/v0 --run-id fake_check
netbrace eval run        --suite tasks/safety/v0 --model openai/gpt-4o --limit 1 --run-id smoke
netbrace report          --run runs/smoke --figures paper/figures
```

Only **Task C** remains. Everything else is done and smoke-tested.

## 6. If you get stuck

- Unit test red after your change → revert; the core is correct.
- Batfish column name mismatch → `df.columns.tolist()` and adjust `oracle.py`.
- Model output won't parse → expected; it scores `invalid`. Do not loosen the parser.
- Networking question (does this change break that session?) → lab question, ask a human.

---

## 7. Session completed (2026-06-07)

### What was done:

1. **Full project rename** `nethelm` → `netbrace`: Python package directory,
   all imports, pyproject.toml entry points, all markdown files. Schema version
   Literal strings (`nethelm.task.v0` etc.) intentionally preserved as JSON
   protocol identifiers.

2. **Task A — Storage** (`netbrace/storage/layout.py`):
   `write_suite`, `load_suite`, `write_task`, `load_task`. Suite hash in manifest.json.

3. **Task B — CLI** (`netbrace/cli.py`):
   Full argparse CLI. Commands: `safety generate`, `safety validate`, `safety oracle`,
   `eval fake`, `eval run`, `grade`, `report`. All wired to their implementation.

4. **Task D — Fake model + run store**:
   - `netbrace/models/fake.py`: FakeModel with oracle/empty/garbage modes.
   - `netbrace/storage/run_store.py`: create_run, write_sample, write_results_csv,
     write_run_manifest.
   - `netbrace/evals/run_fake.py`: zero-API end-to-end grading loop.

5. **Task E — Reporting**:
   - `netbrace/reporting/summarize.py`: aggregates + summary.json.
   - `netbrace/reporting/figures.py`: matplotlib bar chart PDF.

6. **Task F — Inspect AI integration**:
   - `netbrace/evals/scorers.py`: blast_radius_scorer() wrapping grade().
   - `netbrace/evals/inspect_safety.py`: safety_task(), _build_prompt(), system prompt.

7. **Task G — Prompt template** (`netbrace/prompts/safety_direct_v0.md`):
   System contract + Jinja2 task template under one page.

8. **Task H — Scripts + lab helper**:
   - `scripts/check_env.sh`: python, import, Batfish port, CLI.
   - `scripts/smoke_safety_v0.sh`: generate → fake eval → report assertions.
   - `netbrace/routers/containerlab_readonly.py`: show_bgp_summary, show_ip_route,
     show_running_config, show_bgp_neighbors (READ ONLY, subprocess/vtysh).

### Test baseline: **52 passed** (was 42 before this session; +10 new)

### End-to-end smoke: `bash scripts/smoke_safety_v0.sh` — PASS

### Remaining: Task C (oracle) — needs `batfish/allinone:netbrace` container running.
