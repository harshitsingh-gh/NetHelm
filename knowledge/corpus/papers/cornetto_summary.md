# Cornetto — Network Configuration Repair Benchmark (ETH Zürich NSG)

## Citation
Authors from ETH Zürich Network Systems Group (Laurent Vanbever's group).
231 configuration repair problems across real network topologies.
GitHub: [verify current URL from ETH NSG GitHub]

## Core Contribution
Cornetto is a benchmark of 231 network configuration problems that require repair. Each problem consists of:
- A broken network configuration
- A specification of intended behavior
- The correct repaired configuration (ground truth)

## Evaluation
- Formal verification using Batfish and/or network verification tools
- Structural comparison of generated vs. ground-truth configs
- Focus on semantic correctness, not just syntactic

## Scope of Problems
- BGP policy misconfigurations
- OSPF area/metric errors
- Access control list errors
- Missing/wrong route-map configurations
- Prefix list scope errors

## Relevance to NetHELM
- **Config repair (R) tasks**: NetHELM imports Cornetto as category R
- **Cold email**: This is the primary opener for Laurent Vanbever contact (same group as NetConfEval)
- **Formal verification grader**: Cornetto's grading approach can validate NetHELM's config repair scoring

## What to Verify Before Using
- Confirm current GitHub URL (search "cornetto network configuration ETH")
- Check license (must be compatible with research use)
- Verify which config formats are supported (IOS, JunOS, etc.)
- Run a subset in NetHELM harness before claiming integration

## Cold Email Strategy
"I've integrated both NetConfEval (from your ConEXT 2024 paper) and Cornetto (from your network repair work) into a unified evaluation harness called NetHELM. I'm evaluating GPT-4o, Claude, and Gemini across your benchmarks plus a novel safety/blast-radius axis. Would you be interested in discussing the results?"
