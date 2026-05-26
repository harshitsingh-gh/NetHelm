# NetHELM Progress

## Day 1 — 2026-05-20

Goal:
- Create repo skeleton.
- Start NetConfBench reading.
- Produce first benchmark note.

Deliverable target:
- reading/01_netconfbench.md
- paper/refs/landscape_table.md initial stub

Blockers:
- None yet.

## Day 5 — 2026-05-24 (Week 0 close-out)

Status update:
- Secured MS-A2-based sim host: 2 TB disk, 96 GB RAM. Enough for
  containerlab + Batfish + cEOS-lab + cRPD + vLLM-32B-4bit locally.
  RunPod on-demand for ≥70B models and ReAct sweeps. **Phase 0 Week 1
  lab stand-up is unblocked.**
- Cisco day-job ramp + sim procurement consumed reading hours; Week 0
  reading deliverables partially incomplete (have stubs for #01
  NetConfBench and #01b code-skim; missing #02 Cornetto, #03 NetPress,
  #04 NIKA, #05 NetConfEval, #06 HELM-methodology).
- **Repo correction:** confirmed `nobrowning/draft_llm_conf_benchmark`
  is only an IETF draft (no code). Reassigned Week 2 in execution plan
  from "Reproduce NetConfBench" → "Reproduce NetConfEval"
  (`RedHatResearch/conext24-NetConfEval`). NetConfBench retained as
  taxonomy citation only. See
  [reading/01b_netconfbench_code_skim.md](reading/01b_netconfbench_code_skim.md)
  for the verdict and
  [paper/refs/nethelm_execution_plan.md](paper/refs/nethelm_execution_plan.md)
  for the swapped Week 2 / Week 5.
- DNM data-release ticket with Cisco legal: **not yet filed.**

Recovery plan for the rest of Week 0 + Week 1 (no Phase 1 slip):

| Day | Hours | Task |
|---|---|---|
| Sun May 24 (today) | 4 | Read NetConfEval paper end-to-end + skim the repo's `netconfeval/` source tree. Notes → `reading/05_netconfeval.md`. This is now the Tier-1 runnable, so it gets priority over Cornetto today. |
| Sun May 24 (today) | 2 | File the DNM data-release ticket with Cisco legal. First ping is what matters. |
| Mon May 25 (Memorial Day, 5 hr) | 5 | Per plan: install containerlab + FRR square topology on MS-A2 box. `harness/lab/frr_square.clab.yml`. Verify iBGP. |
| Tue May 26 (1.5 hr) | 1.5 | Tier 1 #02 Cornetto paper notes → `reading/02_cornetto.md`. Defer Batfish install to Wed. |
| Wed May 27 (1.5 hr) | 1.5 | Install Batfish (Docker) on MS-A2; parse `frr_square` configs; one pybatfish query. |
| Thu May 28 (1.5 hr) | 1.5 | Tier 1 #03 NetPress + #04 NIKA combined note `reading/03_netpress_nika.md` (collapse two notes into one to recover an evening). |
| Fri May 29 (1.5 hr) | 1.5 | Tier 1 #06 HELM methodology notes → `reading/06_helm_methodology.md`. Skip LLMs-for-Networking survey for now — already absorbed. |
| Sat May 30 (6 hr) | 6 | Per plan: cEOS-lab + Juniper cRPD + `junos-mcp-server` smoketest → `harness/lab/junos_mcp_smoketest.md`. |
| Sun May 31 (5 hr) | 5 | Per plan: `paper/outline_v0.md` + `paper/collab_targets.md`. Populate `paper/refs/landscape_table.md` while NetConfEval is fresh. Re-ping DNM legal ticket. |

**Net effect:** Week 0 reading deliverables land by end of Week 1 (Fri
May 29) instead of Sun May 24. Phase 1 starts on time Jun 1 with no
scope cut. The collapsed NetPress+NIKA note and the dropped
LLMs-for-Networking survey are the only real cuts.

Blockers:
- None hardware-side (MS-A2 + RunPod cover everything).
- Pending: DNM legal ticket (own action item, will file today).