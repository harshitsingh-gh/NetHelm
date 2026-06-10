---
name: scenario-gate
description: Run a proposed blast-radius scenario through the full engineer-fleet gauntlet (author → noc-veteran necessity check → oracle gradeability → industry currency → red-team break → standards review) before it enters the question base. This is the core NetHELM development loop.
---

# /scenario-gate — The full fleet gauntlet for one scenario

No scenario enters the NetHELM question base until it survives this gauntlet.
Convene the fleet in sequence (each stage can kill or send back the scenario);
let the agents be blunt and let them disagree — reconcile explicitly.

## What you receive
A scenario idea, a `Scenario` builder, or a pre/post config pair. If none given,
use the most recently proposed scenario.

## The gauntlet (run in order; loop back on any FAIL)

1. **scenario-author** — if only an idea was given, produce the full scenario:
   topology, change, intent prompt, claimed D1–D8, causal chain, grounding.
2. **noc-veteran** — necessity & realism gate. Is this real, necessary, non-trivial,
   and mechanically correct? Verdict must be REAL_AND_NECESSARY to proceed.
   (REAL_BUT_REDUNDANT / TOO_EASY / NONSENSE / WRONG_MECHANICS → back to step 1.)
3. **batfish-oracle-engineer** — gradeability gate. Can the oracle compute the
   claimed ground truth exactly and deterministically? Note any vendor-config (D6)
   or resource-budget (D8) or emulator need. NOT_GRADEABLE → back to step 1.
4. **industry-expert** — currency gate. Is the config/protocol/method current and
   correct? STALE/DEPRECATED/WRONG → fix.
5. **red-team-critic** — break gate. Ambiguity, gaming, hidden assumptions, the
   hostile one-sentence rejection. Any surviving BREAK → fix.
6. **research-standards-reviewer** — only if this scenario contributes to a
   paper-bound result: determinism, gradeability proof, contribution framing.

## Sanity gate (mechanical, always)
`python scripts/run_extended_scenario.py --scenario <id>` in fake-oracle mode must
score exactly 1.0 (oracle and fake serializer agree). Then a live Batfish run for
the gradeable dims. If fake mode ≠ 1.0, the oracle and scenario disagree — fix
before trusting anything.

## Output

```
## Scenario Gate — <id>
STAGE RESULTS:
  author: ...   noc-veteran: <verdict>   oracle: <verdict>
  industry: <verdict>   red-team: <verdict>   standards: <verdict/NA>
SANITY GATE: fake=<score> live-batfish=<pass/fail>
DECISION: [ADMIT to question base | REVISE (reasons) | KILL (reasons)]
```

## Usage
- `/scenario-gate` — gate the last proposed scenario
- `/scenario-gate "remove next-hop-self on the iBGP RR in a CLOS fabric"`
- `/scenario-gate netbrace/tasks/safety/scenario_blackhole.py`
