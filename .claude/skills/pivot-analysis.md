# /pivot-analysis — Evaluate Whether to Stay the Course or Pivot

Given the current state of the research and the landscape, evaluate whether NetHELM is still the fastest path to a published paper, or whether a pivot would get there faster.

## When to run this
- After a lit-scan turns up a potential competitor
- When a new paper opportunity becomes visible  
- When the current work is falling significantly behind schedule
- Monthly, as a standing check

## Process

Spawn TWO parallel sub-agents:

### Sub-agent A — "Stay the course" advocate
Build the strongest case for continuing with NetHELM as-is. Address:
- What has already been built and would be lost in a pivot?
- What is the current estimated time to a submittable paper on the current path?
- Does the safety/blast-radius angle still appear novel (check landscape table)?
- Is the current trajectory consistent with the Sep 20 build deadline?
- What would the paper's contribution claim look like if submitted tomorrow?

### Sub-agent B — "Pivot" advocate
Build the strongest case for changing direction. Address:
- What faster paper opportunities exist in the current landscape?
- Is there a stripped-down version of the current work that gets to submission faster?
- Has any competitor shipped the primary novelty claim?
- Are there open-source tools that collapse months of build work into days?
- What would a "minimum viable paper" look like that still satisfies the publication goal?

## Synthesis

After both agents report, synthesize into:

```
## Pivot Analysis — [date]

### Current path
- Estimated weeks to submission-ready paper: [N]
- Primary novelty claim: [claim]
- Competitor risk: [HIGH/MEDIUM/LOW] — [rationale]
- Blocker count: [N blockers]

### Fastest alternative path
- What it is: [description]
- Estimated weeks to submission-ready paper: [N]  
- Trade-off vs. current path: [what you gain / what you lose]

### VERDICT: STAY / PIVOT / STRIP DOWN
[Rationale — specifically addressing the thesis fit for the application SOP]

### If PIVOT or STRIP DOWN: recommended next 3 actions
1. [action]
2. [action]
3. [action]
```

## Usage
- `/pivot-analysis` — full analysis
- `/pivot-analysis competitor:"[paper title]"` — triggered by a specific new paper
- `/pivot-analysis velocity` — focus only on time-to-submission estimate
