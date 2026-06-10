---
name: accuracy-check
description: Fast two-agent fact verification of a single networking claim, config, code snippet, or experimental result. Use when you need an authoritative yes/no with sources, not a full critique.
---

# /accuracy-check — Technical Fact Verification

Verify one claim/snippet/result. Single-agent verification has blind spots, so use
two perspectives.

## What you receive
A claim, config, code, or result. If none specified, check the most recently
discussed claim.

## Process

Spawn TWO subagents in parallel (`Agent` tool):

1. `subagent_type: noc-veteran` — **Primary verifier.** Reason through the protocol
   mechanics; check RFC/vendor docs and the KB (`./kb`); trace code; verify the
   computation. Confirm or refute with sources.
2. `subagent_type: red-team-critic` — **Devil's advocate.** Assume the claim is
   WRONG. Hunt corner cases, vendor-specific contradictions, RFC errata, tool
   limitations that break it.

(For a "is this current practice?" question, use `industry-expert` as the second
agent instead of red-team-critic.)

## Synthesis

```
## Accuracy Check — [claim]
VERDICT: [CORRECT | INCORRECT | PARTIALLY CORRECT | UNVERIFIABLE]
CONFIDENCE: [HIGH | MEDIUM | LOW]
EVIDENCE: [what confirms/refutes]
CAVEATS: [conditions under which it doesn't hold]
SOURCES: [RFC#, doc URLs, file paths]
```

For INCORRECT / PARTIALLY CORRECT, give the corrected version.

## Usage
- `/accuracy-check "LOCAL_PREF 200 is preferred over 100"`
- `/accuracy-check runs/<run>/query_output.txt`
- `/accuracy-check netbrace/graders/safety.py:45`
