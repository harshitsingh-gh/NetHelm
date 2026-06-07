# NetBrace Progress

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

## Day 8 — 2026-05-27 (Wed) — Mid-Week-1 reset

Status update:
- Mon May 25 done: containerlab 0.75.0 + Docker 29.5.2 + FRR-square iBGP
  topology came up clean. Verification in
  [harness/lab/frr_square/verify_2026-05-25.txt](harness/lab/frr_square/verify_2026-05-25.txt).
  Four routers, twelve ESTABLISHED iBGP sessions, all four /32 loopbacks
  in every RIB.
- Tue May 26 (Batfish): **slipped** due to day-job load.
- Wed–Fri reading slots also at risk.

Recovery: compressed 3-day lab sprint Wed May 27 → Fri May 29 collapses
the missed Tue Batfish slot + Sat cEOS slot + Sat cRPD/junos-mcp-server
slot into the next three evenings (≈6 hr/day, dedicated MS-A2 host has
no other load). Detail in
[tasks/plan_2026-05-27_catchup.md](tasks/plan_2026-05-27_catchup.md).

Net effect:
- Phase 0 Week 1 lab deliverables (Batfish + cEOS + cRPD +
  junos-mcp-server smoketest) all land by Fri May 29 EOD.
- NetConfEval clone + venv jumps from Phase 1 Week 2 → Day 3 of this
  sprint to de-risk the Week 2 reproduce-NetConfEval slot.
- Sat May 30: revert to reading (NetPress+NIKA combined, HELM
  methodology) per execution plan.
- Sun May 31: `paper/outline_v0.md` + `paper/collab_targets.md` per
  execution plan. Still on track to start Phase 1 Jun 1.

Only real cut if the sprint slips: NetPress+NIKA reading moves to Sun
AM and `outline_v0.md` shrinks to skeleton-only.

Blockers:
- Arista cEOS image requires registered arista.com account; cRPD
  requires support.juniper.net account. Both being filed Wed evening so
  Thu/Fri downloads are unblocked.
- DNM legal ticket: re-ping scheduled in Day 2 of the sprint.

## Day 19 — 2026-06-07 (Sun) — Task C done; first full E2E run

Status update:
- **Task C (Batfish oracle) — DONE.** This was the last open task in the
  safety-axis MVP. Ran the full pipeline end-to-end against the live
  Batfish + 4-node FRR lab.
  - Verified pybatfish column names on a live snapshot against what
    `oracle.py` expects — they match (`Node`, `Remote_IP`, `VRF`,
    `Established_Status`; `Node`, `Network`, `VRF`). No oracle.py edit
    needed.
  - `netbrace safety generate --count 12 --out tasks/safety/v0`
  - `netbrace safety oracle --suite tasks/safety/v0 --host 127.0.0.1`
    → 12/12 `oracle.status=ready`, all `deterministic=True` (~45s).
  - `netbrace safety validate --suite tasks/safety/v0 --require-oracle` → OK.
  - Cross-checked one oracle output against live `vtysh show ip bgp
    summary` on clab-frrsq-r1 (3 ESTABLISHED peers) — agrees.
- **Oracle findings (sanity-correct):** shutting a neighbor drops the
  iBGP session on BOTH endpoints (Batfish reports it bidirectionally);
  `prefixes_lost` is empty because the watched loopbacks resolve via
  static routes (admin-distance 1) which survive the BGP drop. This is
  exactly the "is the model aware of the static backup?" subtlety the
  safety axis is designed to test.
- **Grader validated end-to-end, zero API spend** via FakeModel in three
  modes: oracle → macro-F1 1.0; empty → F1 0.0 (recall floor); garbage →
  F1 0.0 + invalid_rate 1.0 (parser correctly rejects). Artifacts in
  `runs/flow_oracle|empty|garbage/`, figure in
  `paper/figures/safety_f1_by_intent.pdf`.
- Unit tests still green: **52 passed.**
- **Docs:** added `docs/authoring_topologies_and_scenarios.md` — a
  recipe-style guide (deterministic addressing scheme + Batfish/clab
  verification GATEs) so a smaller model can add new topologies and
  scenarios reliably. Architecture overview remains
  `docs/project_guide.md`.

Not run (deliberate): real-model `eval run` (GPT-4o / Claude) — needs
human approval for paid API spend. Confirmed the path works for both
providers via Inspect AI (`--model openai/gpt-4o` or
`anthropic/claude-sonnet-4-6`).

Blockers:
- None. Next: human-approved 1-task real-model smoke (Claude or GPT-4o),
  then add a second intent + a trap scenario.