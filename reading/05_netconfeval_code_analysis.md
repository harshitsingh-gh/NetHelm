# NetConfEval — code analysis (for NetHELM import)

> Source: `external/netconfeval/` (clone of `RedHatResearch/conext24-NetConfEval`),
> analyzed 2026-06-08. Paper: NetConfEval, CoNEXT'24 (doi 10.1145/3656296).
> HF dataset: `NetConfEval/NetConfEval`.

## 1. What it is

A 3-step benchmark for "can LLMs facilitate network configuration?" It is **not** a
blast-radius/safety benchmark — it tests *generation* (intent → spec → code →
config), so for NetHELM it is a **comparative baseline category (C — config
synthesis)**, not core. It is a clean, real, citable import target and a strong
cold-email/collaboration opener (KTH SEMLA + Red Hat authors).

## 2. Structure (the three steps)

| Step | File(s) | Task | Grader | Data |
|---|---|---|---|---|
| **1. Formal spec translation** | `step_1_formal_spec_translation.py`, `_conflict_detection.py`, `_conflict_distance.py`, `step_1_function_call.py` | NL requirements → formal spec (reachability / waypoint / load-balancing policies); also conflict detection & function/API-call variants | Structured diff vs. ground-truth spec (`deepdiff`); exact-match on policy fields | `assets/step_1_policies.csv` (548K) |
| **2. Code generation** | `step_2_code_gen.py` + `verifiers/step_2_verifier_detailed.py` | Spec → Python routing code | **Test-based**: runs generated code against unit tests | `assets/step_2_code_base` (16K), `assets/step_2_tests` (84K) |
| **3. Low-level config** | `step_3_low_level.py` + `prompts/step_3_low_level.py` | Requirements → device configs (FRR) | **Emulator validation in Kathará** (NOT containerlab) on 4 hand-picked Kathará-Labs scenarios (2× OSPF, RIP, BGP peering, fat-tree RIFT) | `assets/step_3_low_level` (6.2M of lab assets) |

## 3. How it's built (the coupling that makes import non-trivial)

- **LangChain-based.** `requirements.txt`: `langchain`, `langchain-community`,
  `langchain-openai`, `openai`, plus `chromadb` (RAG), `tiktoken`, `deepdiff`,
  `networkx`, `kathara`, `scikit-learn`.
- **Own model registry** at `netconfeval/common/model_configs.py` — per-family
  prompt builders (`_build_llama2_prompt`, `_build_mistral_instruct_prompt`,
  phind, etc.). Adding a model = editing this file. README documents
  `--model <id>` keyed off this registry; supports OpenAI, HF (`requirements-hf.txt`),
  and Ollama.
- **Native vs ad-hoc function calling** toggle (`-f 0/1`) — handles models without
  parallel tool-calling.
- **Verifier abstraction** at `foundation/verifier/verifier.py`; step-2 verifier is
  test-execution-based.
- Run entry: `./run_benchmark.sh -r <n_runs> -m <model_id> -f <0/1>`; they recommend
  **n_runs = 5** (matches our N≥5 bar).

## 4. What's reusable for NetHELM, and at what cost

| Asset | Reuse value | Import cost |
|---|---|---|
| **step_1 policy dataset** (`step_1_policies.csv`) + spec-diff grader | High — clean, deterministic, no emulator | **Low.** Wrap the CSV + `deepdiff` grader behind NetHELM's task interface; run models through *our* model layer. |
| **step_2 code-gen tests** | Medium — test-based grading is solid | **Medium.** Need to run generated code in a sandbox; reuse their tests. |
| **step_3 low-level configs** | Medium — real device configs, FRR | **High.** Depends on **Kathará**, a *different* emulator from our containerlab stack. Either stand up Kathará or port the 4 labs to containerlab. Defer. |
| **model_configs registry** | Low — we have our own model layer | Don't import; re-implement minimally. |

**Bottom line for the plan:** the cheap, high-value import is **step 1** (NL→spec,
deterministic grader) as NetHELM's category-C comparative baseline. Steps 2–3 are
real additional work (sandboxed code execution; a second emulator). This concretely
confirms the feasibility-doc point: "reuse, don't re-author" is *partly* cheap and
*partly* a real integration project — not a free import.

## 5. Relevance to the blast-radius-first paper

- **Not needed for v1.** The blast-radius axis stands alone. NetConfEval enters as
  the first comparative baseline when we widen toward full NetHELM.
- **Waypoint overlap (useful):** NetConfEval's step-1 *waypoint* policy and our **D4
  waypoint** dimension are conceptually adjacent — their spec is "traffic must pass
  through X"; our oracle scores violations of exactly that. Worth citing as related
  framing and possibly reusing their waypoint policy vocabulary for D4 task prompts.
- **Vendor scope:** step 3 is FRR-only — so NetConfEval does *not* give us the
  vendor-config dialect we need for D6 (filter). That still requires Arista/IOS
  (see `docs/vendor_images.md`).

## 6. Action items captured
- [ ] (v2) Wrap step_1 policies + spec grader as NetHELM category-C adapter.
- [ ] (v2) Decide Kathará-vs-port for step 3.
- [ ] (now) Borrow waypoint policy vocabulary for D4 prompts where it sharpens them.
- [ ] (outreach) NetConfEval authors = warm contact once the import runs.
