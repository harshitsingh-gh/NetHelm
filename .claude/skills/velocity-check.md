# /velocity-check — Are We Moving Fast Enough?

A frank assessment of research velocity. Compares actual progress to the fastest credible path to a submitted paper. Identifies and eliminates blockers.

## What "fast enough" means
- A workshop-ready paper (4–6 pages) needs: novel result + grader + at least 1 model baseline + methodology description
- Minimum viable: 1 novel task category (safety/blast-radius) + GPT-4o baseline + paper
- That is achievable in 6–10 weeks of focused work if the lab is up and tools are right
- We are currently in Week 2 (Jun 4, 2026) with a Sep 20 build deadline — 15 weeks left before CS221

## Process

1. Read `progress.md` and the current git log (`git log --oneline -30`).

2. Check the current state of the most critical path to a paper:
   - Is there a reproducible experiment that produces a result?
   - Is there a grader that works on at least one task category?
   - Is there a paper draft of any section?
   - Is there a result that would go into a figure or table?

3. Estimate: given what exists NOW, how many weeks to a submittable (4–6 page) paper? Be honest.

4. Identify the top 3 **velocity killers** — things that are taking time but not advancing toward the paper directly.

5. Identify the top 3 **velocity boosters** — actions that, if taken today, would most accelerate time-to-submission.

6. Check for open-source tools that could collapse the biggest time sinks. Search: "inspect-ai agent eval framework", "lm-evaluation-harness custom tasks", "batch LLM eval open source 2025 2026".

7. Output:

```
## Velocity Check — [date]

### Current state
- Last concrete research output: [what + when]
- Experiments producing results: [Y/N + description]
- Paper content drafted: [section names]
- Weeks to minimum viable submission: [N]

### VERDICT: ON TRACK / SLOW / STALLED

### Top 3 velocity killers (cut or shortcut these)
1. [thing] — [why it's killing velocity] — [how to shortcut]
2.
3.

### Top 3 velocity boosters (do these next)
1. [action] — [why it unblocks the most]
2.
3.

### Open-source tools that could help
[any tools found that replace custom build work]

### Recommended: are we building the right thing?
[honest assessment of whether current work is on the fastest path to a published paper]
```

## Usage
- `/velocity-check` — full assessment
- `/velocity-check tools` — focus only on open-source tools search
- `/velocity-check mvp` — what's the absolute minimum to get a paper in the next N weeks?
