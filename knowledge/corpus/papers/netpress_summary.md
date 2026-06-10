# NetPress / NetArena — Dynamic Benchmarks for AI Agents in Network Automation (arXiv:2506.03231)

> ACCURACY NOTE (corrected 2026-06-08, web-verified by the fleet): the prior version
> of this file was a placeholder that mis-described 2506.03231 as "automated network
> change impact assessment / methodology TBD." That was wrong. Corrected below.
> **NetPress and NetArena are the SAME paper** — arXiv:2506.03231 was retitled across
> versions from "NetPress: Dynamically Generated LLM Benchmarks for Network
> Applications" to **"NetArena: Dynamic Benchmarks for AI Agents in Network
> Automation"** (Microsoft + UMD; repo `github.com/Froot-NetSys/NetPress`). **Cite it
> ONCE.** Treating them as two distinct prior works is a factual error a networking PC
> will catch.

## What it actually is
A **dynamically generated benchmark for LLM AGENTS** acting in emulated network
applications. Three apps: **routing/BGP route-leak diagnosis, ACL/malware-blocking
("MALT"), and k8s networking**. Emulator-backed; the agent takes ACTIONS and is
graded on the outcome. Metrics: **correctness, safety, latency**; >10k queries/app.
Its dynamic generation is its headline anti-contamination contribution, and it
reports that better statistics took agent-vs-agent CI overlap from ~85% → 0%
(agent performance roughly 13–38%).

**Its "safety" axis** = does the agent's *remediation action* avoid causing
collateral damage *during execution* (binary rule/constraint adherence). It is the
closest prior art to a "safety" axis — but it is action-safety in an emulator, NOT
prediction of a typed damage-set from a static diff.

## Differentiation from NetHELM (the defensible novelty boundary)
- **NetArena:** agent executes actions in an emulator; safety = binary
  rule-adherence during execution; correctness via testcase outcomes.
- **NetHELM:** the model **predicts the TYPED, multi-dimensional damage SET** a
  proposed config change will cause, **from configs alone, no tool access**, scored
  with **per-dimension precision/recall** against a Batfish oracle — and is penalized
  for **hallucinated damage (precision/false-alarm)** as well as missed damage. **No
  prior benchmark — NetArena included — scores hallucinated/false-positive damage, or
  the documented "predict-session-loss-on-an-attribute-change" trap.** That
  calibration surface is the moat.

## How to position in the paper
Cite NetArena (arXiv:2506.03231) as the closest prior work on a network "safety"
metric, then draw the boundary: their safety = *execution action-safety*; ours =
*predictive, typed, calibrated blast-radius from a diff*. Do NOT claim "no prior work
scores safety" — that is false and gets desk-rejected. Claim the typed-set +
calibration framing, which is uncontested.

## Sources
- [arXiv:2506.03231 — NetPress / NetArena](https://arxiv.org/abs/2506.03231)
- repo: github.com/Froot-NetSys/NetPress
