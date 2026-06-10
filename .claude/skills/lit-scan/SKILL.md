---
name: lit-scan
description: Scan for new LLM-for-networking and LLM-benchmark publications that could pre-empt NetHELM's novelty (especially the blast-radius axis) or should be cited, and update the landscape table. Use periodically — the field moves fast and scoop risk is real.
---

# /lit-scan — Literature & Scoop Scan

Detect anything that closes a NetHELM novelty gap (blast-radius/safety axis above
all) or that we must cite. Spawn the `research-standards-reviewer` (and optionally
`industry-expert`) to do the searching and assessment, or do it directly.

## Process

1. Read `paper/refs/landscape_table.md` and
   `temporary/networking_llm_benchmark_paper_plan.md` to know what's catalogued.
2. Search (WebSearch/WebFetch) across:
   - arXiv cs.NI + cs.LG: LLM + network config / management / agents / safety /
     blast radius
   - Recent citations of NetConfEval (CoNEXT'24), Cornetto (ETH 2026),
     NetConfBench (now **draft-01**), NetPress/**NetArena** (arXiv:2506.03231),
     NIKA (arXiv:2512.16381)
   - SIGCOMM/CoNEXT/IMC and NeurIPS/ICLR/ICML workshops (ML-for-Systems, LLM Agents)
3. For each new paper assess: does it **close** a surviving gap (esp. the safety/
   blast-radius axis)? Is it a **competitor** at the same scope? Is it **citable**
   related work?

## Output

```
## New Papers Found — [date]
### BLOCKERS (gap closures affecting our contribution claim)
[paper, venue, gap closed, recommended response]
### NEW RELATED WORK (should cite)
[paper, venue, 1-line summary, where to cite]
### COMPETITORS (same scope)
[paper, venue, overlap analysis]
### LANDSCAPE TABLE UPDATES NEEDED
[rows to add/modify]
```

If a BLOCKER is found (someone shipped a blast-radius/safety benchmark), say so
loudly and draft revised positioning immediately — this changes the plan. Ask
before editing `landscape_table.md` unless told to apply automatically.

## Usage
- `/lit-scan` — full scan
- `/lit-scan safety axis` — only blast-radius/safety pre-emption risk
- `/lit-scan quick` — arXiv last 30 days only
