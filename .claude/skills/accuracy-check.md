# /accuracy-check — Technical Fact Verification

Verify the technical accuracy of a specific claim, code snippet, or experimental result. Called when you need a quick authoritative answer, not a full critique.

## What you receive
A claim, code, config, or result to verify. If none specified, check the most recently discussed claim.

## Process

Spawn TWO parallel sub-agents for independent verification (single-agent verification has blind spots):

### Sub-agent 1 — Primary Verifier
Verify the claim using all available sources:
- Read relevant files in the repo (configs, code, Batfish query outputs)
- Search for the authoritative source (RFC, vendor documentation, Batfish docs, Python docs)
- If the claim is about network behavior: reason through it protocol-by-protocol
- If the claim is about code: trace the execution path
- If the claim is about an experimental result: verify the computation

### Sub-agent 2 — Devil's Advocate
Assume the claim is WRONG and look for evidence. Check:
- Corner cases and edge cases the primary verifier might miss
- Vendor-specific behavior that contradicts the general claim
- RFC errata or updates that qualify the claim
- Known bugs or limitations in the tools cited

## Synthesis
After both agents complete, synthesize:
```
## Accuracy Check — [claim]
VERDICT: [CORRECT / INCORRECT / PARTIALLY CORRECT / UNVERIFIABLE]
CONFIDENCE: [HIGH / MEDIUM / LOW]
EVIDENCE: [what confirms or refutes the claim]
CAVEATS: [conditions under which the claim might not hold]
SOURCES: [RFC numbers, doc links, file paths]
```

For INCORRECT or PARTIALLY CORRECT verdicts, provide the correct version.

## Usage
- `/accuracy-check "BGP route with LOCAL_PREF 200 is preferred over LOCAL_PREF 100"` — check a protocol fact
- `/accuracy-check runs/2026-05-27_batfish_frrsq/query_output.txt` — verify Batfish output is as expected
- `/accuracy-check harness/graders/safety.py:45` — verify code correctness at a line
