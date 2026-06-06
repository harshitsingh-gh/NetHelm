# /run-netconfeval — Execute NetConfEval Experiments

Run NetConfEval experiments against a specified model, save outputs to `runs/`, and document results in `harness/grader_notes/netconfeval.md`.

## Prerequisites check (always verify before running)

1. Is the NetConfEval venv activated? Check `harness/venvs/netconfeval/` exists.
2. Is `OPENAI_API_KEY` (or relevant key) in environment?
3. Is the HuggingFace dataset reachable?
4. What's the estimated cost? Compute: steps × policy_types × n_runs × tokens/task × $/token

## Experiment modes

### Mode: smoke (default for first run)
- `--batch_size 1 --n_runs 1 --policy_types reachability`
- Single policy type, single run — confirms the loop works. Cost: < $1.
- Save to `runs/{date}_netconfeval_{model}_smoke/`

### Mode: step1 (full step 1)
- All policy types (reachability, waypoint, load_balancing), n_runs=3
- Covers formal-spec translation + function-call modes
- Cost estimate: ~$15–$30 GPT-4o

### Mode: step2 (code gen)
- Step 2: NL intent → Python routing code
- Cost: ~$20–$40 GPT-4o

### Mode: step3 (low-level FRR configs — DEFERRED)
- Requires Kathará + Docker. Do NOT run unless explicitly asked.
- Deferred to execution plan Week 5.

## Process

1. Check prerequisites.
2. Activate venv: `source harness/venvs/netconfeval/bin/activate`
3. Determine run_dir: `runs/{YYYY-MM-DD}_netconfeval_{model}_{mode}/`
4. Run the appropriate script with `--results_path {run_dir}`
5. Capture stdout+stderr to `{run_dir}/stdout.log`
6. After completion: parse the results JSON and print a summary table (policy_type × metric × score)
7. Compare against upstream paper's reported numbers (from `reading/05_netconfeval.md` if it exists, or the paper PDF)
8. Document differences > 5% as anomalies requiring investigation
9. Update `harness/grader_notes/netconfeval.md` with findings

## Saving results
Results JSONs should be committed. Raw model outputs > 10 MB should NOT be committed (add to .gitignore). Save a summary CSV instead.

## Usage
- `/run-netconfeval smoke gpt-4o` — minimal smoke test
- `/run-netconfeval step1 gpt-4o` — full step 1
- `/run-netconfeval step1 claude-sonnet-4-6` — step 1 with Claude
- `/run-netconfeval step2 gpt-4o` — code gen step
