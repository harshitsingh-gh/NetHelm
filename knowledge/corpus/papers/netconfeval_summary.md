# NetConfEval — LLM Network Configuration Evaluation (ConExt 2024)

## Citation
Ye Luo, Yiping Mao, Minlan Yu, Laurent Vanbever.
"NetConfEval: Can LLMs Facilitate Network Configuration?" 
ACM CoNEXT 2024 (December 2024).
arXiv: [to be verified]
GitHub: RedHatResearch/conext24-NetConfEval

## Core Claim
LLMs struggle at network configuration generation tasks that require precise, syntactically correct, and semantically correct router configurations. The paper introduces a benchmark with five task categories and evaluates GPT-3.5, GPT-4, and CodeLlama.

## Task Categories
1. **Prefix-list generation**: Generate Cisco IOS prefix-lists matching a set of IP prefixes
2. **Route-map generation**: Generate route-maps with match/set clauses
3. **BGP policy generation**: Full BGP neighbor configuration with policy
4. **OSPF configuration**: Basic OSPF area/interface configuration
5. **ACL generation**: Access control list generation

## Evaluation Method
- Functional correctness via Batfish (where applicable)
- Syntactic correctness via config parsing
- Human labeling for a subset

## Key Findings
- GPT-4 achieves ~60–70% syntactic correctness; lower on semantic correctness
- Models frequently generate plausible-looking but wrong configurations
- Smaller models (CodeLlama-7B) perform significantly worse
- Chain-of-thought prompting improves performance marginally

## Relevance to NetHELM
- **Reproduced in Week 2**: NetConfEval is the primary reproduce target for NetHELM v1
- **Config synthesis (C) tasks**: NetHELM imports this as category C
- **Batfish grading**: Their use of Batfish for semantic correctness is the same approach as NetHELM's oracle
- **Cold email**: Laurent Vanbever (ETH Zürich) is a primary collaboration target; "I reproduced your NetConfEval benchmark in my harness" is the opener

## What NetHELM Adds Beyond NetConfEval
- Safety/blast-radius axis (entirely absent from NetConfEval)
- Multi-dimensional scoring (D1–D8)
- Multi-model comparative evaluation (GPT-4o, Claude, Gemini)
- Unified harness importing multiple benchmarks
