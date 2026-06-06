# /critique — Multi-Agent Research Critique

Perform a rigorous, multi-perspective peer review of the provided work (paper section, experimental result, claim, code, or methodology). This is research intended for publication; treat it accordingly.

## What you receive
The user will either paste the content to critique, or point you at a file path. If no content is specified, critique the most recently discussed work.

## Process

Spawn THREE parallel sub-agents, each with a distinct reviewer identity. Use the `Agent` tool to launch all three simultaneously in a single response. Provide each sub-agent with the full text of the work being critiqued plus their specific role.

### Sub-agent A — Technical Accuracy Reviewer
Role: Senior network engineer with 10+ years of BGP, OSPF, and network automation experience. Check:
- Every protocol claim (BGP, OSPF, ACL, QoS behavior) against RFC or vendor docs
- Every Batfish / pybatfish API usage for correctness
- Every containerlab / FRR config for validity
- Any "would X happen?" assertions about network behavior
- Experimental setup realism — would a real NOC engineer recognize this as a valid task?
Report: numbered list of issues, each with severity (BLOCKER / MAJOR / MINOR), the incorrect claim, and the correct fact with source.

### Sub-agent B — Experimental Rigor Reviewer  
Role: ML researcher familiar with benchmark paper methodology (HELM, BIG-Bench, SWE-bench). Check:
- Are evaluation metrics defined precisely and unambiguously?
- Is the grader deterministic? Are edge cases handled?
- Are sample sizes sufficient for the claimed confidence?
- Is contamination risk addressed (templated generation vs. training corpora)?
- Are statistical claims (means, F1 scores) backed by correct computation?
- Is inter-rater agreement reported where applicable?
- Would a NeurIPS D&B track reviewer accept this methodology section?
Report: numbered issues with severity, plus at least 3 concrete "reviewer will ask" questions.

### Sub-agent C — Novelty & Literature Reviewer
Role: Literature expert familiar with NetConfEval, Cornetto, NetConfBench, NetPress, NIKA, TeleQnA, HELM, and the LLM-for-networking survey corpus. Check:
- Does any claim of novelty hold against the existing landscape?
- Are citations accurate — does the cited paper actually say what is claimed?
- Are there missing citations (prior work that should be acknowledged)?
- Is positioning vs. prior work (§2 related work) honest and complete?
- Would Cornetto or NetConfEval authors dispute any claim?
Report: numbered issues with severity, plus any suggested additional citations.

## After all three sub-agents complete

Synthesize their reports into a single **Critique Report** with:

```
## Critique Report — [title/section being reviewed]
### BLOCKERS (must fix before submission)
### MAJOR ISSUES (should fix)
### MINOR ISSUES (consider fixing)
### REVIEWER QUESTIONS TO PRE-EMPT
### VERDICT: [ACCEPT / MAJOR REVISION / REJECT WITH RATIONALE]
```

Be direct. Do not soften findings. This work will be reviewed by people who know the field.

## Usage examples
- `/critique` — critique whatever was just discussed
- `/critique paper/draft_v1/03_methodology.md` — critique the methodology section
- `/critique "BGP sessions that match a deny prefix-list are silently dropped"` — fact-check a claim
