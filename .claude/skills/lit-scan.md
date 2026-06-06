# /lit-scan — Literature Scan for New Papers

Scan for new publications in the LLM-for-networking and LLM-benchmark spaces that may have appeared since the landscape table was last updated. Update `paper/refs/landscape_table.md` with findings.

## Process

1. Read `paper/refs/landscape_table.md` and `paper/refs/networking_llm_benchmark_paper_plan.md` to understand what's already catalogued.

2. Search for new papers across these dimensions using WebSearch and WebFetch:
   - arXiv cs.NI + cs.LG (LLM + networking, network configuration, network management, LLM agents network)
   - Semantic Scholar for recent citations of: NetConfEval (CoNEXT'24), Cornetto (ETH 2026), NIKA (arXiv:2512.16381), NetPress (arXiv:2506.03231)
   - SIGCOMM 2025/2026, CoNEXT 2025, IMC 2025 proceedings for relevant papers
   - NeurIPS/ICLR/ICML 2025/2026 workshops: ML-for-Systems, LLM Agents

3. For each new paper found, assess:
   - Does it **close a gap** claimed in §2.2 of the strategy doc? If so, this must be flagged as a BLOCKER — the contribution claim needs updating.
   - Does it **cite NetConfEval/Cornetto** in a way that's relevant to our positioning?
   - Is it **citable** as related work?
   - Does it represent a **new competitor** to NetHELM's scope?

4. Output a structured report:
   ```
   ## New Papers Found — [date]
   
   ### BLOCKERS (gap closures that affect contribution claims)
   [paper, venue, what gap it closes, recommended response]
   
   ### NEW RELATED WORK (should cite)
   [paper, venue, 1-sentence summary, which section to cite in]
   
   ### COMPETITORS (same scope)
   [paper, venue, overlap analysis]
   
   ### LANDSCAPE TABLE UPDATES NEEDED
   [specific rows to add/modify in landscape_table.md]
   ```

5. If BLOCKER items are found, immediately draft updated positioning language for §2.2 of the strategy doc and flag for review.

6. Ask before modifying `landscape_table.md` unless the user says to apply automatically.

## Usage
- `/lit-scan` — full scan
- `/lit-scan safety axis` — scan only for papers relevant to the blast-radius / safety contribution
- `/lit-scan quick` — just check arXiv last 30 days, no deep citation search
