# NetConfBench Code Skim

## Repo URL

https://github.com/nobrowning/draft_llm_conf_benchmark

## Verdict (2026-05-24)

**No code exists.** This repository is the IETF Internet-Draft markdown source
for `draft-cui-nmrg-llm-benchmark` (IRTF Network Management Research Group),
generated from `martinthomson/internet-draft-template`. Contents:

- `draft-cui-nmrg-llm-benchmark.md` — the draft itself
- `.github/workflows/` — Martin Thomson's standard draft-publishing CI
- `README.md` — boilerplate "Internet-Draft Template Repository"

Repo stats: 0 stars, 1 contributor (Chenguang Du), last commit ~7 months ago.
No `tasks/`, no grader, no model adapters, no `requirements.txt`, no shell
script. Nothing to clone-and-run.

### Implication for NetBrace

- Treat NetConfBench as a **taxonomy / scoping reference only** — cite the
  draft for its 40-task categorization and the three proposed metrics, but
  do not try to "reproduce" or import its corpus, because no corpus exists
  in code form. If the authors release tasks later, revisit.
- The runnable Tier 1 config-gen benchmark we actually want is
  **NetConfEval** (Wang, Scazzariello, Farshin, Ferlin, Kostić, Chiesa —
  Proc. ACM Netw. 2024 / CoNEXT'24) at
  https://github.com/RedHatResearch/conext24-NetConfEval. That repo has:
  `run_benchmark.sh`, four step scripts (`step_1_formal_spec_translation.py`,
  `step_1_function_call.py`, `step_2_code_gen.py`, `step_3_low_level.py`),
  OpenAI/HuggingFace/Ollama adapters via LangChain, HF dataset
  `NetConfEval/NetConfEval`, Kathará+FRR for the low-level config experiment,
  MIT license, 36 stars, Python 95% / Shell 5%.
- **Action:** the execution plan's Week 2 "Reproduce NetConfBench" slot is
  reassigned to "Reproduce NetConfEval." See
  [../paper/refs/nethelm_execution_plan.md](../paper/refs/nethelm_execution_plan.md).
- No need to file an issue against the draft repo or contact authors — the
  draft is doing what an IETF draft is supposed to do (specify, not ship code).

## What still belongs in NetBrace from the draft

- The 40-task taxonomy as a *checklist of capabilities a config-gen
  benchmark should cover* — useful as a comparator column in
  [../paper/refs/landscape_table.md](../paper/refs/landscape_table.md).
- The three metric families (syntactic / semantic / functional) as prior
  art when motivating NetBrace's metric design in paper §3.

## Questions resolved

1. **How many tasks are checked into the repo?** Zero — only the draft text
   that describes 40 hypothetical tasks.
2. **Are golden answers included?** No.
3. **Is the grading deterministic?** N/A — no grader exists.
4. **Can one task run without full GNS3 setup?** N/A — nothing runs.
5. **Can we wrap their tasks without modifying their code?** N/A.