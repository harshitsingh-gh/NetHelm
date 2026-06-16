---
name: design-review
description: Routing-design review of a config / baseline / scenario — is it not just parseable-and-running but CORRECT, IDIOMATIC, and convergent the way the intent requires? Convenes the network-architect (+ industry-expert for currency). Use on every new baseline/scenario config and to judge model-under-test config synthesis.
---

# /design-review — Is the routing DESIGN correct, not just running?

Behavioral grading (Batfish) and the NOC veteran tell you it *runs* and is *real*.
This skill answers the deeper question the benchmark actually depends on: **is the
routing design CORRECT, IDIOMATIC, and will it converge as the requirement
intended?**

## What you receive
A config, a baseline/scenario module, or a model-under-test config-synthesis output.
If none given, review the most recently authored config.

## Process
Spawn in parallel (via `Agent`):
1. `subagent_type: network-architect` — the core review: intent realization,
   idiomaticity, convergence/correctness-under-change, scale soundness. (For a
   model output: did it implement the intent design-correctly, or pass by luck?)
2. `subagent_type: industry-expert` — currency: is the design/syntax current
   practice (SR/EVPN/RPKI/modern DC) or a dated idiom?

(Add `batfish-oracle-engineer` if the question is whether the design is also
oracle-gradeable.)

## Synthesis
```
## Design Review — <target>
### DESIGN VERDICT: [CORRECT_IDIOMATIC | WORKS_BUT_NONIDIOMATIC | DESIGN_FLAW | WRONG]
### INTENT REALIZATION   (does it implement the requirement, or just look plausible?)
### IDIOMATICITY         (non-idiomatic constructs + the idiomatic form)
### CONVERGENCE / RISK   (will it converge as intended? latent partition/loop/hiding)
### CURRENCY             (dated vs current practice)
### FIX                  (the design-correct construction + the principle/RFC)
```
A benchmark whose ground-truth configs are works-by-accident or non-idiomatic
teaches the wrong thing — catch it here before it ships.

## Usage
- `/design-review netbrace/tasks/safety/baseline_clos_summary.py`
- `/design-review` (review the last authored config)
- `/design-review <a model's generated BGP config>` — judge synthesis correctness
