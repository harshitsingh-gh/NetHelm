# /paper-draft — Write + Auto-Critique a Paper Section

Write a section of the NetBrace paper, then immediately run /critique on it. This ensures no draft section reaches storage without a peer-review pass.

## What you receive
A section identifier and any notes or bullet points. Examples:
- `/paper-draft §3.2 task taxonomy` — draft the task taxonomy section
- `/paper-draft §4.3 safety results notes:"GPT-4o F1=0.41, Claude Opus F1=0.55"` — draft results with provided data

## Target venue context
- **Primary**: NeurIPS/ICLR workshop (4–6 pages, ~3500 words)
- **Tone**: HELM-style benchmark paper — precise, measurement-focused, honest about limitations
- **Not**: a systems paper, a position paper, or a tutorial

## Process

1. Read relevant prior content:
   - `paper/refs/networking_llm_benchmark_paper_plan.md` (strategy + framing)
   - `paper/refs/nethelm_execution_plan.md` (scope constraints)
   - `paper/refs/landscape_table.md` (related work)
   - Any existing draft sections in `paper/draft_v1/`
   - Relevant `reading/` notes
   - Any run outputs in `runs/` that provide numbers

2. Draft the section. Requirements:
   - Use present tense for describing the benchmark, past tense for experiments
   - Every quantitative claim must cite a specific file or source
   - Every related-work reference must match the landscape table
   - Contribution claims must match §2.2 surviving gaps only
   - Write at workshop-paper density: no padding, every sentence earns its place
   - Mark any unverified number as `[VERIFY: source]`
   - Mark any missing citation as `[CITE: description of needed reference]`

3. Save draft to `paper/draft_v1/{section_name}.md`

4. Immediately invoke the /critique skill on the draft.

5. Append the critique report to `paper/draft_v1/{section_name}_critique.md`

6. Present the critique summary and ask whether to proceed, revise, or defer.

## Section templates

### §1 Introduction
- Hook (½ page): real ops failure or high-stakes scenario — sanitized/synthetic
- Gap statement: existing benchmarks don't compare, no safety axis
- Contribution claim (3 bullets): holistic comparative, safety axis, commercial agent baseline
- Paper roadmap

### §2 Related Work
- Use `landscape_table.md` as spine
- Position: NetConfBench (importing), Cornetto (importing), NetPress (prior art for safety), NIKA (importing subset), HELM (methodology ancestor)
- Explicitly acknowledge closed gaps from §2.1 of strategy doc

### §3 Methodology
- §3.1 Harness architecture (the diagram in strategy doc §3.1)
- §3.2 Task taxonomy (the K/C/B/D/R/S table)
- §3.3 Grading (per category, automatic, deterministic)
- §3.4 Grader validity (human-labeled subset, Cohen's κ)

### §4 Results
- Lead with headline finding
- Per-category breakdown
- Commercial-agent comparison
- Single-shot vs ReAct ablation

### §5–§7 Discussion, Limitations, Conclusion
- Limitations MUST include: synthetic-only data, vendor coverage limited, no DNM (or note approval status), no step-level trace grading

## Usage
- `/paper-draft §1 intro` — write the introduction
- `/paper-draft §3.3 grading` — write the grading section  
- `/paper-draft §4 results numbers:"see runs/sweep_001/"` — write results section using run data
