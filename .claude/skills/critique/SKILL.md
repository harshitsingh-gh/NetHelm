---
name: critique
description: Rigorous multi-agent peer review of a NetHELM artifact (scenario, result, claim, code, or paper section) by convening the engineer fleet in parallel and synthesizing a blunt verdict. Use before anything is considered final.
---

# /critique — Multi-Agent Research Critique

Peer-review the target as adversarially as a real reviewer would. This is research
for publication; treat it accordingly. Soft review is worthless.

## What you receive
A pasted artifact or a file path. If none given, critique the most recently
discussed work.

## Process

Spawn THREE fleet subagents **in parallel in a single response** (via the `Agent`
tool), giving each the full artifact:

1. `subagent_type: noc-veteran` — networking correctness + real-world realism: is
   this how networks actually behave/fail? Protocol mechanics, Batfish usage,
   config validity, would an operator recognize it.
2. `subagent_type: research-standards-reviewer` — methodology + publication bar:
   metric precision, determinism, N≥5, κ, contamination, statistical validity,
   citation accuracy, novelty vs prior work. At least 3 "reviewer will ask"
   questions.
3. `subagent_type: red-team-critic` — break it: ambiguity, gaming, hidden
   assumptions, the one-sentence hostile rejection.

(For a paper-text critique, the industry-expert may be added as a 4th for currency.)

## Synthesis

After all complete, merge into one report:

```
## Critique Report — [artifact]
### BLOCKERS (must fix before it ships)
### MAJOR ISSUES (should fix)
### MINOR ISSUES (consider)
### REVIEWER QUESTIONS TO PRE-EMPT
### VERDICT: [ACCEPT | MAJOR REVISION | REJECT] + rationale
```

Do not soften. Reconcile disagreements between agents explicitly — if the
noc-veteran and red-team-critic conflict, say which is right and why.

## Usage
- `/critique` — critique what was just discussed
- `/critique paper/draft/03_methodology.md`
- `/critique "BGP sessions matching a deny prefix-list are silently dropped"`
