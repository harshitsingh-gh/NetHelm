# /workshop-deadlines — Check Upcoming Paper Submission Deadlines

Search for and report upcoming submission deadlines at relevant venues. Used to maintain awareness of the submission calendar and make sure we don't miss a window.

## Target venues (in priority order)

### Primary — AI/ML venues (highest citation, best fit for benchmark paper)
- NeurIPS workshops (ML for Systems, LLM Agents, Foundation Models in the Wild, Behavioral ML)
- ICLR workshops
- ICML workshops  
- NeurIPS / ICLR / ICML Datasets & Benchmarks tracks

### Strong — Networking venues (domain credibility)
- HotNets (annual, typically late June deadline)
- NAIC @ SIGCOMM (April–May deadline)
- GenAINet @ ICC (varies)
- NetAI @ SIGCOMM

### Stretch — Full conferences (post-2027)
- ACM CoNEXT (June/July deadline)
- USENIX NSDI
- ACM SIGCOMM, IMC

## Process

1. Search the web for current deadlines at all venues above. Search: "[venue] 2026 call for papers", "[venue] 2027 call for papers deadline".

2. For each venue found with an open or upcoming deadline within the next 6 months:
   - Report exact submission deadline
   - Report notification date
   - Report page limit
   - Report whether it's a good fit for a benchmark/measurement paper

3. Flag any deadline within 8 weeks as URGENT.

4. Output a sorted deadline calendar:

```
## Workshop/Venue Deadlines — [scan date]

### URGENT (< 8 weeks)
[venue | deadline | notification | pages | fit-score 1-5]

### UPCOMING (8–20 weeks)
[same format]

### LATER (> 20 weeks, worth tracking)
[same format]

### KEY GAPS IN INTELLIGENCE
[venues where we couldn't find current cycle info]
```

5. Given the current state of the work, identify the **single best next submission target** — the earliest deadline where we could have a quality paper ready.

## Usage
- `/workshop-deadlines` — full calendar scan
- `/workshop-deadlines urgent` — only deadlines in the next 8 weeks
- `/workshop-deadlines [venue]` — check a specific venue
