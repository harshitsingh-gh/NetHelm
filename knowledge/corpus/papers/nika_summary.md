# NIKA — Network Incident and Knowledge Assessment (arXiv 2024)

## Citation
arXiv:2512.16381 (December 2024).
Authors: [verify from arXiv]

## Core Contribution
NIKA is a benchmark for network troubleshooting and incident diagnosis. It tests LLMs on their ability to identify root causes of network incidents given symptom descriptions (e.g., show commands, syslog output, topology descriptions).

## Task Structure
- Input: network incident description (symptoms, show output, topology context)
- Output: root cause label (from a fixed taxonomy)
- Grading: root-cause label match (exact or fuzzy)

## Incident Categories
- BGP session flaps and causes (timer mismatch, authentication failure, hold-timer expiry)
- OSPF adjacency failures (MTU mismatch, area ID mismatch, authentication, subnet mismatch)
- Reachability failures (black hole, wrong route, policy block)
- Interface/L2 failures (duplex mismatch, native VLAN, STP issues)
- QoS and performance issues

## Key Findings
- LLMs perform well on textbook-style single-root-cause incidents
- Performance degrades significantly on multi-fault incidents
- Models tend toward common causes (e.g., "authentication mismatch") even when other causes are more likely given the symptoms

## Relevance to NetHELM
- **Diagnosis (D) tasks**: NetHELM imports NIKA as category D (planned for Week 6)
- **Root-cause label grader**: NIKA's exact-match grader is directly importable
- **Multi-fault scenarios**: NIKA's multi-fault finding is relevant to blast-radius complexity analysis
- **Collaboration target**: NIKA authors as cold-email target

## What to Verify Before Using
- arXiv:2512.16381 — confirm paper still available and accessible
- Dataset availability (HuggingFace or GitHub link)
- License for benchmark use
- Exact taxonomy of root-cause labels for grader implementation
