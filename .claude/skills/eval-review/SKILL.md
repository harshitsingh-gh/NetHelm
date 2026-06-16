---
name: eval-review
description: Review the EVALUATION methodology — prompting/function-calling, scoring metrics, sampling/stats, baselines, contamination control, model integration, fine-tuning plans — for trustworthiness. Convenes the ml-eval-engineer (+ research-standards-reviewer for the publication bar). Use before any model sweep and on the grader/runner/prompt design.
---

# /eval-review — Is the measurement trustworthy, not ad hoc?

The networking skills check what's *correct*; this checks whether the *eval of
model behavior* is methodologically sound and would survive a benchmark-track
reviewer.

## What you receive
The eval surface to review: the prompt contract, the grader/metrics, the runner, a
proposed sweep, or a results table. If none given, review the current eval pipeline.

## Process
Spawn in parallel (via `Agent`):
1. `subagent_type: ml-eval-engineer` — prompting (incl. the no-outcome hygiene
   rule), native vs ad-hoc function calling, metric definitions + gameability, the
   trap metrics (`is_trap`/`false_session_alarm`), sampling N, baselines (empty /
   naive-session-loss / naive-count / random), contamination control, model
   integration, tracking-over-time.
2. `subagent_type: research-standards-reviewer` — the publication bar: N≥5, CIs,
   significance, grader validity (and where κ legitimately applies), novelty
   positioning, reproducibility, desk-reject risks.

## Synthesis
```
## Eval Review — <target>
### VERDICT: [SOUND | FIX-THEN-RUN | NOT-READY]
### PROMPTING / FUNCTION-CALLING   (contract, hygiene, leaks)
### METRICS                        (definitions, gameability, trap metrics, what to report)
### SAMPLING + STATS               (N, CIs, baselines, significance)
### CONTAMINATION                  (control + held-out/templated split)
### MINIMUM EXPERIMENTAL PACKAGE   (exact models, samples, baselines, stats to run)
```
Lead with whatever blocks a credible result; never green-light a sweep whose numbers
a reviewer would reject.

## Usage
- `/eval-review` (review the current pipeline before a sweep)
- `/eval-review netbrace/graders/extended.py`
- `/eval-review <a results table / proposed model-fleet plan>`
