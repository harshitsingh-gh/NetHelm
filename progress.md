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
  junos-mcp-server smoketest) all land by Fri May 29 EOD.
- NetConfEval clone + venv jumps from Phase 1 Week 2 → Day 3 of this
  sprint to de-risk the Week 2 reproduce-NetConfEval slot.
- Sat May 30: revert to reading (NetPress+NIKA combined, HELM
  methodology) per execution plan.
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

## Day 19 (cont.) — 2026-06-07 — multi-dimensional blast-radius axis

Big step on the safety axis: moved it from "lost BGP sessions" to a real
multi-dimensional blast radius, on a `brainstorming-session` branch
(PR #1).

- Wrote a 20-scenario catalog from the literature (NetConfEval, NIKA,
  NetPress, Batfish docs, Forward Networks):
  `paper/refs/blast_radius_scenario_catalog.md`. Two reframings baked in:
  topologies vary and are parameterised (CLOS leaf-spine, ISP backbone,
  MPLS L3VPN, multi-area OSPF, campus, anycast) — not the 4-router square;
  and blast radius is 8-dimensional (D1-D8), with single-protocol session
  loss as one special case.
- Implemented the five new dimensions as typed elements + an extended
  grader, purely additively — the frozen v0 core was never edited.
  D4 waypoint, D5 redundancy/ECMP, D6 filter, D7 forwarding anomaly,
  D8 scale.
- Built **live Batfish oracles** for D4, D5, D7 on three new small
  verified topologies (waypoint4, ecmp4, and a blackhole change on
  square4). Then unified them: one oracle call computes every declared
  dimension on a single pre/post snapshot pair. This exposed that the
  blackhole "cleanup" is really a 4-D blast (2 session losses + prefix
  loss + reachability loss + blackhole).
- Wired the real-model path (8-D prompt contract + tolerant parser +
  runner) and ran Claude Haiku 4.5 as a model-under-test, one call per
  scenario:
    * ecmp      -> exact pass (macro_f1 1.0)
    * waypoint  -> partial 0.5 (caught the waypoint, hallucinated a
                   redundancy loss)
    * blackhole -> partial 0.5 (nailed the data-plane effects, missed the
                   second-order control-plane session/prefix loss)
  First concrete evidence for the thesis: a session-only grader scores the
  blackhole a perfect pass and misses the real damage; the model handles
  direct data-plane effects but misses second-order ones and sometimes
  hallucinates an inapplicable dimension.
- Tests grew 52 -> 91. Docs added: topology/scenario authoring guide,
  the scenario catalog, and a full end-to-end guide
  (`docs/multidimensional_blast_radius.md`).

Next (see HANDOFF.md for detail): D6 + D8 oracles, a multi-sample /
multi-model sweep (single calls are stochastic), grader-validity
labelling for the new dims, and merging PR #1.

## Day 20 — 2026-06-08 — Direction reset + engineer fleet + flagship class

Big day. Reframed the project and stood up the build machinery, then shipped
the first new failure class end-to-end.

- **Direction (decided with user):** own the whole NetHELM vision, but **finish
  the blast-radius axis end-to-end and publish it FIRST**, then grow into full
  NetHELM. Tokens were never the bottleneck; real blockers are model-eval $,
  human κ labels, a co-author, and Cisco DNM approval. DNM ticket deferred until
  there's a demo to show. $1000 approved strictly for the model-suite sweep.
  Full reasoning: `temporary/full_nethelm_feasibility_and_blockers.md`.
- **Engineer fleet (Max plan):** 7 Claude Code subagents in `.claude/agents/`
  (noc-veteran drives + questions everything; industry-expert; scenario-author;
  batfish-oracle-engineer; sim-builder; research-standards-reviewer;
  red-team-critic). Skills re-homed to proper format + new `/scenario-gate`.
  CLAUDE.md rewritten; private planning notes consolidated
  (moved to `temporary/`).
- **Catalog audit (fleet):** noc-veteran + industry-expert audited the 20-scenario
  catalog. Result + synthesis in `paper/refs/catalog_audit_2026-06-08.md`; locked
  v1 roster in `paper/refs/v1_question_base_plan.md` (scope = "deterministic
  modern layer": static BGP/policy spine + RPKI route-validity + EVPN Type-5;
  defer SRv6/deep-EVPN to v2 on determinism grounds).
- **Oracle determinism spec:** batfish-oracle-engineer verified per-class
  determinism against live Batfish (5× byte-identical) →
  `docs/oracle_determinism_spec_v1.md`. 8 classes safe to author now.
- **Flagship class built + verified:** Class 1 (internal routing-policy collapse,
  the Rogers/Facebook mechanism). `scenario_ipc.py` + `baseline_ipc3.py`,
  registered as `"ipc"`. Live oracle confirms D1=∅ (sessions stay UP — the trap),
  D2={r2 loses 203.0.113.0/24}, D3={r2→203.0.113.0/24 NO_ROUTE}. Sanity gate
  macro_f1=1.0 exact; empty-prediction scores 0.0. **Tests 91 → 96 green.**
  Generator design for ~8–12 instances documented (determinism-aware axes).

Next: red-team S-IPC-01, then replicate the class via its generator (~8–12
instances), then classes 2–8 of the spine; build the route-validity pure-function
oracle (class 9); run the EVPN Type-5 spike (class 10 in-or-out decision).

## Day 20 (cont.) — red-team gauntlet on the flagship → fixed + live-verified

red-team-critic attacked S-IPC-01 and found one serious error + real gaps; all fixed:
- **Accuracy defect at the source:** the KB Rogers file mischaracterized the 2022
  outage as a "silent withdrawal." CRTC/Xona confirm it was an **ACL filter
  removal → route flood → core overload/crash** (≈ the opposite). Rewrote
  `knowledge/corpus/noc/rogers_canada_outage_jul2022.md`, rebuilt the FAISS index,
  and **re-pointed Rogers to the D8 scale/overload class**. Class 1's grounding is
  now honestly Maintenance-Type-2 / operational lore (+ FB-2021 at the prefix
  level), **not** Rogers. Fixed the propagated claim in scenario/baseline/plan.
- **Tautological gate fixed:** `run_extended_scenario.py` now prints a
  DISCRIMINATION line (oracle vs empty-baseline) + a caveat that the echo 1.0 is a
  round-trip, not a correctness proof (correctness = the live Batfish oracle).
- **Determinism discriminator implemented (D9):** new typed element
  `BgpRouteWithdrawn` + `ExtendedOracle._bgp_rib_prefixes` (live finding: bgpRib
  `Status` is a LIST `['BEST']`, so a literal `=="BEST"` would match nothing).
  New `ipc_static` has-static sibling proves it: D9 fires (BGP withdrawal) while
  D2/D3 stay silent (static FIB survives) → distinguishable from a no-op. Tests
  **96 → 105**.
- **Live-FRR confirmation:** sim-builder deployed ipc3 on real FRR
  (`quay.io/frrouting/frr:10.6.1`) and verified all 7 points — sessions stay
  ESTABLISHED, r2 loses the prefix from RIB+FIB, loopbacks survive, r1/r3
  unaffected. **Live FRR matches the Batfish ground truth exactly.** Saved
  `harness/lab/ipc3/verify_2026-06-08.txt` + reusable `harness/lab/ipc3.clab.yml`.
  Lab cleaned (frrsq untouched).

Flagship is now red-teamed → fixed → live-verified, and the oracle has the D9
discriminator needed to replicate Class 1/3/4 safely. Next: build the real Class-1
parameterized generator (~8–12 instances), then spine classes 2–8.

## Day 20 (cont.) — Class-1 distinct structures (bounded-increment build)

A single mega-agent ("build 8–12 instances + generator + verify each") hit a stream
timeout — too big. Switched to **bounded, oracle-verified increments** (one
mechanism per run/edit), which is timeout-free and rigorous. Class 1 now has **4
genuinely distinct, live-verified blast STRUCTURES** (red-team's "distinct
mechanisms, not clones" bar):
- `ipc` (S-IPC-01) — coupled D2+D3, single node.
- `ipc_static` — D9 control-plane-only (static masks the data plane).
- `ipc_fanout` (S-IPC-02) — peer-group-wide, D2+D3 on 3 nodes (different cardinality).
- `ipc_aggregate` — D2 on the /25 more-specifics, **D3 silent** (surviving /24
  aggregate covers it) — the inverse of the flagship; grounded in RFC 4632 §5.3.
All discriminate (gap 1.00) and are deterministic (2× byte-identical). Suite
**105 → 116 green**. Also corrected a leftover Rogers reference in the `ipc`
docstring. Refinement: the "next-hop-resolver collapse" variant folds into the
dedicated next-hop-self spine class (#3), not Class 1 (avoids overlap).

Class-1 locus + difficulty variants (inbound-on-client; explicit-deny / wrong
le-ge bound — same ground truth, different config-reading difficulty) deferred to a
later mechanical pass. Next high-value build: **Class 2 (route leak, D4/D7)** — the
class that carries the multi-dimensional thesis (session+prefix counts give NO
signal).

## Day 20 (cont.) — Class 2 (route leak) first instance: thesis demonstrated

Built `leak_ms` (more-specific leak/hijack → blackhole) on the **first multi-AS
eBGP topology** (victim AS65001 — transit AS65002 — leaker AS65003). The leaker
originates a /25 of the victim's /24; LPM pulls transit's traffic to the leaker,
where it's blackholed. **Live-verified thesis property: D1 sessions_lost = ∅ AND
D2 prefixes_lost = ∅ (a route is ADDED) — yet D3 (transit→victim) + D7 (null_routed
@ leaker) fire.** The naive "count sessions/prefixes lost" view sees zero; the real
blast is data-plane only. This is the core argument for multi-dimensional scoring.
Grounded in Cloudflare-2019 + Telekom-Malaysia-2015. Discriminates (gap 1.00),
deterministic (2× byte-identical). Suite **116 → 123**. Methodology catch:
traceroute probes must target the host `/32`, not the `/24` network (Batfish
connected-subnet model) — locked by a unit test.

**Session state:** 8 registered scenarios, 123 tests. Class 1 (silent withdrawal)
= 4 distinct structures; Class 2 (route leak) = 1 thesis-carrying instance; plus
the original waypoint/blackhole/ecmp. Spine classes remaining: 3 (next-hop-self),
4 (RR failure), 5 (local-pref trap), 6 (ACL/VRF — VRF half on FRR, ACL half needs
vendor cEOS), 7 (anycast), 8 (mgmt lockout). Then modern layer (RPKI route-validity
class 9; EVPN Type-5 spike class 10), then multi-sample model-fleet sweep + κ.

## Day 20 (cont.) — timeout root-caused, NOC-veteran per-instance review, class 5

- **Timeout root-caused (no code bug):** a single oracle compute runs in **2.2s**;
  Batfish healthy. The earlier "timeout" was a *subagent stream idle-timeout* from
  over-scoping ONE agent with all 8–12 instances. Fix: bounded-increment builds
  (proven) + author pattern scenarios directly, reserve subagents for novel design.
- **NOC-veteran per-instance legitimacy review (the gate that had been skipped):**
  all 5 built scenarios ruled **LEGIT** (none lie about mechanics/grounding). Key
  finding: **5 scenarios = only 2 mechanisms** so far. Rule adopted: **new
  mechanisms only, no more implicit-deny variants.** Coverage correction: spine
  **class 3 (recursive next-hop) is ALREADY covered by `blackhole`.** Honesty
  ledger + build-next priority recorded in `paper/refs/v1_question_base_plan.md`.
- **Class 5 built (NEW mechanism): `lp_waypoint`** — a LOCAL_PREF change reroutes
  src→dst off the inspection waypoint. **D1=∅, D2=∅, D3=∅, only D4 fires** — the
  documented LLM trap (predicting a session drop on an attribute change). Distinct
  from the static-reroute `waypoint` (control-plane attribute vs FIB edit).
  Deterministic (2× byte-identical), discriminates, suite **123 → 133**.
- **New Batfish modeling note** captured in `docs/oracle_determinism_spec_v1.md`:
  FRR `next-hop-self` isn't honored by Batfish's iBGP next-hop rewrite → use static
  routes to egress /30s (as `lp_waypoint` does); verify RIB non-empty before
  trusting any new iBGP scenario's ground truth.

**Mechanism count now ~6 distinct** across the spine: implicit-deny withdrawal,
route leak (LPM blackhole), LOCAL_PREF waypoint shift, static-reroute waypoint,
recursive-next-hop blackhole, ECMP redundancy loss. 9 registered scenarios, 133
tests. Next new mechanisms: scale/overload (Rogers, D8), RR best-path hiding (class
4), anycast (class 7), mgmt-lockout (class 8).

## Day 20 (cont.) — lp_waypoint gauntlet (NOC+red-team) + KB expansion

- Gave **noc-veteran KB-write authority** (`.claude/agents/noc-veteran.md`: +Write/Edit
  + a "knowledge-base curation" role) so the project driver maintains the corpus.
- **lp_waypoint through the full gate:** NOC-veteran = LEGIT-but-note; red-team =
  FIX-THEN-SHIP and caught a **benchmark-validity bug — the prompt leaked the
  answer** (description stated "alt strictly preferred, LP 300>200"), so a model
  could score 1.0 by parroting. FIXED: prompt now states config-edit + intent only.
  **New global authoring rule** added to scenario-author: *prompt = config edit +
  intent ONLY, never the routing outcome.* Also fixed a docstring inaccuracy
  (route-map has no match clause) + dropped Cisco-only "weight" wording, and aligned
  the oracle's `_accepted_traces` with the shared `_DELIVERED` set (EXITS_NETWORK
  footgun). Re-verified: 133 tests, lp_waypoint D4-only + deterministic, waypoint
  unaffected, prompt-leak gone.
- **KB expanded (noc-veteran research, primary sources):** `knowledge/corpus/dc/`
  added — `hyperscaler_fabric_design.md` (Google Jupiter, Meta F16, RFC 7938,
  EVPN), `hyperscaler_dc_failure_modes.md` (8 change→blast classes mapped to D1–D8
  w/ real incidents), `dc_summarization_ecmp_pitfalls.md`. Index rebuilt.
- **Methodology TODOs recorded** (sweep/paper phase) in v1 plan: non-trivial
  baselines + `is_trap` scoring; pin pydantic in the batfish venv; disclose the
  next-hop-self Batfish gap + surface D9 in reporting.

**Next-build queue (now DC-grounded):** route-summarization conditional blackhole
(RFC 7938 §5.2.3), ECMP/multipath collapse, automation canary fat-finger (Meta
class), FIB/TCAM overflow (Rogers/D8), EVPN RT mismatch — plus spine classes 4/7/8.

## Day 20 (cont.) — Plan A (from the holistic critique) finished end-to-end

Closed the critique's cheap-critical gaps (the science-integrity fixes), 161→**183 tests**:
- **A1 prompt leaks + CI guard:** fixed the 3 leaking prompts (leak_ms, ipc_static,
  waypoint) and added `tests/unit/test_prompt_hygiene.py` (13 checks) — prompt
  hygiene is now a build gate, not a docstring note.
- **A2 trap metric wired:** `Scenario.is_trap` + `TRAP_SCENARIOS` → `grade_extended`
  (was dead code); new `false_session_alarm` metric (truth sessions=∅ ∧ pred
  sessions≠∅); runner now always prints the **empty** and **naive_session_loss**
  baselines. The naive baseline correctly trips `false_session_alarm` and scores 0
  on every scenario — the trap now discriminates and is measured.
- **A3 determinism gate (bg agent):** `ExtendedOracle.compute_checked` +
  `scripts/verify_determinism.py` → **11/11 scenarios ≥10× byte-identical**;
  Batfish image **pinned** (`batfish/allinone:nethelm` == sha256:09817554db90…)
  across CLAUDE.md + spec; `pydantic` added to the batfish venv lockfile.
- **A4 D6 honesty + prompt consistency:** `filter` (D6) excluded from `SCORED_TYPES`
  AND removed from the prompt (deferred — needs vendor config). Also caught that the
  prompt OMITTED D9 (`bgp_withdrawals`) while scoring it → added it, so the prompt
  now matches the exactly-8 scored dims (D1–D5, D7–D9).
- **A5 D3 semantics:** documented D3 = TOTAL reachability loss (all-traces); partial
  ECMP loss is D7 set-wise. (spec)
- **A6 per-dimension reporting:** `reporting.summarize_extended()` surfaces every
  scored dim incl. D8/D9 + false_session_alarm_rate. `ipc_static` D9 is
  output-visible → **GO (kept)**.

**First real-model evidence (4 Haiku smokes, N=1 each — validates the pipeline +
first thesis signal, NOT paper-grade):** lp_waypoint macro_f1=0.0 (predicted wrong
waypoint + hallucinated redundancy), leak_ms 0.0 (missed the LPM blackhole),
clos_summary 0.27 (partial), ipc_static 0.33 (flags the BGP withdrawal but
hallucinates data-plane loss the static backup prevents). All at/near the empty
baseline — the benchmark surfaces real failures. ~4 Haiku calls, pennies.
No dockers created (used existing pinned Batfish); docker clean.

**State: 11 scenarios, ~7 mechanisms, 8 scored dimensions, 183 tests, determinism
gate enforced (11/11), prompts leak-free + CI-guarded, trap metric live, ground
truth pinned.** The benchmark is now science-integrity-sound; the remaining gaps
are SCALE (real generators → ≥150 instances), the oracle-validity study (independent
human), and the full $1000 model sweep (Plan C).

## Day 20 (cont.) — clos_summary (DC summarization blackhole) built + gauntlet

Built `clos_summary` (RFC 7938 §5.2.3): a 2-spine/3-leaf eBGP Clos where summarizing
the underlay creates a **partial (½) ECMP blackhole**. Verified GT: **D1=∅; D2 the
specific /24 gone on leaf1/leaf2/spine2 (the /8 masks it — "D2 lies"); D3=∅ (one
ECMP half delivers — total-loss monitors stay green); D7 null_routed@spine2.** New
oracle capability: **set-wise D7** (`_forwarding_diff_setwise`/`_anomaly_set`) — "a
blackhole trace EXISTS in the post all-traces set" — the determinism-correct way to
grade partial ECMP blackholes (flow-level checks stay silent). New `Scenario.patches`
(multi-node change) + `forwarding_setwise` flag; both additive/opt-in. Suite **133→146**.

Gauntlet: NOC-veteran **REAL_AND_NECESSARY** (independently re-verified GT 2×;
"one of the strongest scenarios — first page of the paper"). Red-team **FIX-THEN-SHIP**
— GT/determinism (8× identical)/oracle code all sound, but caught a **paper-blocking
false causal story**: docstrings claimed "spine2 never learns the /24"; RIB dump shows
spine2 DOES learn it indirectly (leaves re-advertise it up). FIXED: docstrings now
state the true mechanism (summarization SUPPRESSES the /24 toward leaves → severs
spine2's indirect path → spine2 falls back to its /8 discard → blackhole). Also:
added a pre-delivery guard to `_forwarding_diff_setwise` (latent false-positive on
already-broken flows); softened the per-leaf "two half-blackholes" claim (D7 key is
source-agnostic → one network fact, leaves are witnesses); added a corpus cross-ref
note distinguishing the single-snapshot vs conditional summarization variants.
Re-verified: 146 tests, clos_summary GT unchanged, no regressions. Red-team note:
the `blackhole` FRR keyword in the diff is NOT a usable tell (on both spines, only
spine2 fires; a pattern-matcher over-predicts spine1 and is penalized).

**10 scenarios, ~7 distinct mechanisms** (added: DC summarization partial-ECMP
blackhole). Next: ECMP/multipath collapse, FIB/TCAM overflow (Rogers/D8 — new
dimension), spine classes 4/7/8.

## Day 20 (cont.) — D8 (scale/overflow) dimension + scale_deagg, full gauntlet

Built the **D8 scale dimension** (new axis) end to end + `scale_deagg` scenario:
de-aggregation (upstream drops a /16 summary, originates the constituent /24s) pushes
the edge's installed-route count past an annotated FIB budget → overflow. New oracle:
`_installed_route_count` + `_scale_violations` (count-vs-budget, opt-in via
`Scenario.resource_limits`). `ScaleViolation`/fake-model/parser were already wired
from the D4–D8 scaffolding. Grounded in 512k-Day (2014), Rogers (corrected), Trident
TCAM ceilings.

Gauntlet: NOC-veteran **REAL_AND_NECESSARY** (512k-Day canonical; new resource axis;
zero-loss-signal blast). Red-team **FIX-THEN-SHIP with a KILL SHOT** — all FIXED:
1. **Prompt leak (kill shot):** prose stated both the de-agg count AND the budget →
   solvable by arithmetic. Fixed: prose states config-edit + budget only; the model
   must count the /24s from the diff (verified no count literal in prose).
2. **D2 watch-set gerrymander:** the /16 genuinely leaves the RIB but was hidden to
   force "D2=∅". Fixed: /16 now watched; honest GT D2={edge,upstream ×/16}; thesis
   reframed to "benign-looking supernet→specifics SWAP (D3=∅) while the real blast is
   the D8 overflow."
3. **Oracle resource fan-out bug:** one route count was compared to every resource
   (fib/rib/label/acl_tcam). Fixed: route-count proxy applies to fib/rib only;
   label/acl_tcam not fired off it.
4. Disclosed the FIB-proxy limit (main-RIB row count, single-VRF, upper-bound) +
   budget as a lab-scaled datasheet-ceiling stand-in; threshold sweep audited in a test.
Re-verified: 161 tests, honest GT, deterministic 2×, discriminates, no regressions.

**11 scenarios, ~8 distinct mechanisms, D8 dimension live** (dimensions now scored:
D1,D2,D3,D4,D5,D7,D8,D9; D6 filter still needs vendor cEOS). Next: ECMP/multipath
collapse, spine classes 4 (RR best-path hiding) / 7 (anycast) / 8 (mgmt-lockout).
## Day 20 (cont.) — Team expansion + stay-current mandate + the fleet FIGHT

- **Fleet expanded 7→12 agents** (+ network-architect, ml-eval-engineer,
  netdevops-engineer, backend-engineer, formal-verification-engineer) + 2 skills
  (/design-review, /eval-review). All 12 carry a **stay-current web-research
  mandate** (the field moves weekly; verify version/feature-sensitive claims online,
  never from training memory).
- **Turn-based adversarial fight** over the whole design (attack → defend → adjudicate),
  all agents web-researching current practice. Synthesis + decided roadmap:
  `paper/refs/fight_synthesis_2026-06-08.md`. Verdict: infra/determinism are
  publication-grade; framing overclaimed + two flagship details wrong. KEEP the
  damage-set task; **promote trap/calibration to co-headline** (the real moat — no
  competitor scores *hallucinated* damage). DO NOT pivot to intent-relative/tools-arm
  (NetConfEval/NetArena lane) or build clustered-bootstrap stats for HotNets (overkill).
- **Cheap MUST-FIXes implemented this session** (the two auto-reject triggers + flanks):
  1. **NetPress == NetArena** (same paper, arXiv:2506.03231) — corrected the
     materially-wrong KB summary (`netpress_summary.md`, a Rogers-class error) +
     landscape_table; cite once. Index rebuilt.
  2. **clos_summary RFC relabel** — RFC 7938 §5.2.3's mechanism needs a *link
     failure*; ours bakes a fixed asymmetry. Docstrings now say "fixed-asymmetry
     instance of the §3.2.2 hazard," not the §5.2.3 link-failure case. Proper fix
     (symmetric Clos + `fork_snapshot` link-down) queued.
  3. Prompt: `reasoning` marked **unscored/qualitative**; "blast radius" **scoped** to
     static steady-state (transients out of scope).
  183 tests still green; no scenario ground truth changed (docstring/label/prompt only).
- **Roadmap (decided, prioritized in the synthesis doc):** [needs $] N≥5 model sweep
  with scenario-level mean±std + false_session_alarm-RATE as the thesis figure + the
  modal-by-class baseline (lands with generators); [build] real parameterized
  generators → ≥150 instances + contamination split; intent-as-first-class
  (IntentInvariant/IntentViolation — captures the ipc_aggregate gap); the clos
  link-down rebuild; eBGP idiomatic twin for lp_waypoint; tolerant scorer + 5-axis
  paper relabel (NeurIPS-ED extension). Target: HotNets-first.

## Day 20 (cont.) — intent dimension (D10) + the first real parameterized generator

Worked both fight-roadmap items in sequence (both touch the Scenario schema).

**(b) D10 intent — first-class, scored.** Added `IntentViolation` element +
`IntentInvariant` oracle-side schema (kinds: reachability/waypoint/isolation/
redundancy_floor/te_pin) + `_intent_diff` (reuses existing reachability/waypoint/
nexthop/per-VRF helpers), wired into the fake-model, parser, grader SCORED_TYPES,
and the prompt contract. **Canonical case proven:** ipc_aggregate now scores
`active=['prefixes','intent']` — the /25 te_pin intent is violated **while D3
reachability stays ∅** ("reachable but intent broken," which the old taxonomy
couldn't express). Opt-in no-op (empty invariants); intent_invariants are
ORACLE-SIDE ONLY (never shown to the model — prompt hygiene). Deterministic. 183→198.

**(a) First real parameterized generator (`generator_ipc.py`) — the scale unblock.**
Class-1 implicit-deny withdrawal as a generator over 6 determinism-safe axes
(k clients ∈{2,3,4} × one/all peers × out/in direction × prefix-class {plain,
has-static, aggregate} × match {implicit/explicit-deny/wrong-le}) = **96 distinct
axis combinations × ∞ seeds**. **Per-seed randomization of ASN/addressing/node-
names/customer-prefix = the contamination control** (mechanism fixed, instance
novel); seed-reproducible (verified: same seed→identical, diff seed→renumbered).
`provenance="templated"` field added (the PRIMARY decontaminated split; hand-authored
incident scenarios = GROUNDED split). Runner `--generated N --seed S` path enumerates
them through the same oracle+grader+baselines; `summarize_extended` aggregates them
unchanged. Verified: 34-instance stratified sweep ran clean (all deterministic, all
beat the naive baselines), 10× determinism gate on 3 representatives, all 96
round-trip in unit tests; network-architect design-lens blessed the configs (idiomatic
RFC 4456 RR iBGP). No dockers leaked; existing 11 registry scenarios unchanged.
Suite 198→**403** (+205, mostly the 96×2 parametrized structural tests).

**This unblocks three roadmap items at once:** scale (≥150 instances via seeds),
the modal-by-class baseline (now many instances per class), and the contamination
split (templated vs grounded). Remaining for the paper: the $1000 model sweep over
the generated PRIMARY split (scenario-level mean±std + trap-rate), then the validity
study. Note: full 10×-determinism-gating runs at sweep time on the chosen instances
(only a representative sample is gated now).

## Day 20 (cont.) — scenario CSV + sweep harness + modal-by-class + mgmt-lockout

Three deliverables, all verified; suite 403 → **434**.

**Scenario-inventory CSV** (`paper/refs/scenario_inventory.csv`, `scripts/scenario_inventory.py`):
107 rows — 11 hand-authored with **live Batfish ground truth** + 96 generated combos
(intended structure). Columns for human SME review: id, split, class, mechanism,
topology, change, intent, dims_fired, ground_truth (exact keys), fidelity_tier,
is_trap, grounding, oracle_verified. 8/11 hand-authored are traps; every scored dim
exercised. **This is the human-review starting point.**

**Sweep harness** (`scripts/run_sweep.py` + `netbrace/reporting/{baselines,sweep_aggregate,fake_oracle}.py`):
one command runs (instance × model × N samples) → **scenario-level two-stage stats**
(per-instance mean over N, then mean±std ACROSS instances — NOT pooled-i.i.d., per the
adjudicator's binding ruling), **templated vs grounded splits reported separately**,
per-dimension P/R/F1 table, and the **FSA_rate** (false-session-alarm rate) thesis
figure. Baselines: empty, naive_session_loss, naive_count, **modal_by_class** (the
validity floor — at ≥150 instances it collapses to ~0.04, the contamination-control
proof), oracle_ceiling. Fake-mode validated (zero API). Real-sweep command ready
(3 Claude models × 5 samples × ~161 instances ≈ $100–150; scalable to the full fleet
within the $1000). Pinned model IDs + per-run cost in the manifest. +31 tests.

**mgmt-plane lockout** (12th mechanism — noc-veteran's #1 missing class): jump—core—edge
iBGP; an outbound "cleanup" on core omits the device mgmt prefix toward the NOC
jump-host → **D1=∅, D2=∅ (zero customer prefixes), D3={jump→198.18.0.1}**. The
"I broke nothing customer-facing and it's still top-severity" inverted-reasoning trap.
Routing/VRF severance (not ACL → FRR-gradeable). Grounded in FB-2021/AWS-2021/
Rogers-2022/CF-2022 OOB dependency. Verified: oracle GT, determinism, discrimination,
prompt-hygiene lint passes. **Still owes the noc-veteran + red-team gate** (built, not
yet blessed). +10 tests.

**State: 12 mechanisms, 96-combo generator, 9 scored dimensions, 434 tests, sweep
harness ready.** Next: gate mgmt_lockout; then authorize the real $1000 sweep over the
generated PRIMARY split (the first real per-dimension + FSA-rate numbers).

## Day 20 (cont.) — mgmt_lockout CHECKPOINT (gate → fix → blessed)

Ran the owed review gate on mgmt_lockout. NOC-veteran: REAL_AND_NECESSARY (real class,
4 post-mortems, distinct inverted-severity trap). Red-team: FIX-THEN-SHIP (borderline
KILL) — reproduced live that it was **`ipc` with the victim prefix renamed**: same
ipc3 topology + same outbound-implicit-deny mechanism, and the "trap" (D2=∅) was
MANUFACTURED by hiding the mgmt prefix from the watched set; a dumb set-subtraction
scored 1.0 on its single key, and the management-severity insight was never graded
(prose only). The gate did exactly its job.

**Fixed (the class is real → fix, don't cut), using the new D10 intent dimension:**
- The "jump MUST retain management reachability" intent is now graded as D10
  IntentInvariants (oracle-side) — so the model must recognize the change violates a
  stated management-reachability INTENT, not just subtract prefixes.
- Thickened to 2 managed devices (≥2 D3 losses + ≥2 D10 violations), not 1 bit.
- Honest watched set (customer + 4 loopbacks watched and surviving → D2=∅ is real, not
  hidden). RFC-2544 benchmarking block → RFC 1918 mgmt addressing (172.16/16).
- Reframed honestly as a deliberate `ipc` sibling whose distinct value is the D10
  graded surface (like ipc_static's value is D9), not a new mechanism.
**Gameability closed (proven):** a reachability-only "set-subtraction" prediction now
scores macro_f1=0.5 / partial (intent f1=0.0) — it can no longer reach 1.0. New GT:
D1=∅, D2=∅, D3={2 jump→mgmt losses}, D10={2 intent violations}. Deterministic. Suite
434→**437**. Scenario inventory CSV regenerated with the new ground truth.

mgmt_lockout is now BLESSED (gated + fixed). 12 mechanisms, 9 scored dimensions.

## Day 21 — 2026-06-09 — End-to-end scrutiny + director deck

Fresh 4-lens strategic scrutiny (research-standards, industry-expert, red-team,
network-architect), all web-verified against the live 2026 landscape. Convergent
verdict in `paper/refs/scrutiny_2026-06-09.md`:
- **Direction NOVEL + ON-TREND.** Moat re-confirmed (no benchmark scores hallucinated
  damage from a diff); the 2026 agentic-NetOps survey (arXiv:2605.12729) names
  "predictive blast-radius estimation for LLM proposals" as an open gap.
- **Two decided changes:** (1) REFRAME as the "verification-wall pre-gate /
  autonomy-ladder rung-2→3 graduation test" + ADD a tools-allowed contrast (no-tools
  vs tools-allowed → paper is about the GAP); (2) STOP building scenarios — RUN THE
  FRONTIER SWEEP (the binding constraint; only N=1 Haiku smokes exist, floored at
  baseline). Target HotNets 2026 (deadline JULY 16). Need an independent human for the
  oracle-validity study; generate held-out variants for ≥2-3 other mechanisms; add one
  OSPF/IGP-underlay scenario (static next-hop resolution is non-idiomatic).
- **Director deck built:** `paper/NetHELM_director_briefing.pptx` (13 slides + speaker
  notes; trust-gate business framing; honest about stage; ask = small sweep budget +
  sanctioned time + start the Deep-Network-Model data-release conversation post-demo).
  Built via `scripts/build_director_deck.py` (python-pptx).

## Day 22 — 2026-06-10 — Fresh fleet audit + Plan-#1 harness fixes + 3 new generators

**Fresh 6-agent publication-safety audit** (new lead model; red-team, standards,
ml-eval, oracle, noc-veteran, architect — instructed to verify code/runs, not docs):
`paper/refs/audit_2026-06-10_publication_safety.md`. Verdict: science real, oracle
SOUND (leak_ms re-verified live, exact agreement), parser format-agnostic, novelty
intact — but NOT safe to publish as configured. Five kill/major classes: (K1)
modal_by_class degenerate (floor==ceiling 1.00, coarsen never run); (K2) decided
headline contradicted by data already in runs/ (FSA_rate=0.00, tools-gap≈0.01 —
"only 4 Haiku smokes" was stale); (K3) 7–8 mechanisms not 12/108, n=1 mean±std
cells; (K4) generated split never determinism-gated + gate script wedges Batfish +
sweep crashes on flakes; (M1-M8) blackhole CONTRIVED (static underlay IS the bug),
clos asymmetry, prompt-hygiene test is theater, stale registry, no raw persistence,
unpinned deps. Citation adjudication: NetPress→NetArena retitle CONFIRMED on live
arXiv (2506.03231); NIKA (2512.16381) is a SECOND "Arena"-titled paper — cite by ID;
the 2605.12729 "quote" is a paraphrase (fix). Decision: probe before narrative —
headline is an open empirical question; HotNets position-paper track.

**Plan item #1 executed (all free/local), suite 443 → 559 green:**
- K1 FIXED+verified: `--coarsen-class` default ON; modal_by_class skips singleton
  classes ("undefined" on grounded; 0.07–0.18 vs 1.00 ceiling on templated — first
  real validity floor). `syntactic_diff` regex baseline added (the red-team's
  zero-routing-knowledge floor: 0.00–0.02 measured — gameability now a number).
- K4 FIXED+verified: sweep ground truth via `compute_checked(runs=2)` + 3-attempt
  flake retry on fresh network names + quarantine.jsonl (never crashes a paid run);
  `verify_determinism.py` hardened (fresh network per scenario — the wedge fix —
  + flake retry + `--generated N`): re-ran clean, **12/12 ≥10× byte-identical**
  (`runs/determinism_20260610_003352/`).
- M5: registry refreshed (verified 2026-06-10): Opus 4.8 price was 3× overstated
  ($15/$75 = retired 4.1 rate; correct $5/$25); GPT-5.5 ($5/$30) replaces stale
  GPT-5 pin; Gemini 3.5 Pro NOT GA on API → 3.5 Flash is the pin; +gpt-5.4-mini,
  +vllm/qwen3-32b with a working `_call_vllm` (OpenAI-compatible endpoint).
  Estimated 6-model full sweep ≈ $90.
- M6: raw model outputs → `responses.jsonl`; `invalid` + `macro ci95` columns;
  n=1 dimension cells print "(n=1)" point estimates, never fake ±0.00.
- M8: `requirements-lock.txt` (pip freeze, 106 pins) + pyproject pointer.

**K3 attacked — 3 new parameterized generators (netdevops agents, all
oracle-verified live, 2× byte-identical per combo, prompt-hygiene clean):**
- `generator_leak.py` (Class-2): 3-AS leak, axes kind{ms_blackhole→D3+D7,
  ms_reroute→D4+D10 hijack-accepts-traffic} × scope{low/high/both /25}. D1=D2=∅
  thesis holds in all 6. +35 tests.
- `generator_lp.py` (Class-5, re-homed IDIOMATIC all-eBGP — closes audit M3, zero
  statics): knob{lp_raise_alt, lp_drop_way, prepend_way} × effect{bypass→D4-only,
  no_op→ALL-EMPTY GT (the predict-nothing calibration trap)}. KB finding: Batfish
  FRR model needs literal-ASN prepend (no `last-as`); RFC 8212 ebgp-requires-policy
  not modeled (disclose for live-emulator runs). +50 tests.
- `generator_scale.py` (Class-8): margin{over_clear, over_marginal=budget+1,
  under=trap} × supernet_fate{withdrawn→D2, kept→D2=∅}; counts verified at 3 seed
  bases. +17 tests.
- Wiring: additive `build_generated_suite_multi` (round-robin ipc/leak/lp/scale;
  `build_generated_suite` unchanged for pinned tests), generic `scenario_class`
  for gen_* families, fake-oracle branches for all three (+14 wiring tests).
  Sweep + determinism gate now consume the multi split. Fake sweep verified:
  templated split now fires waypoint/forwarding/scale/intent/D9 (was prefixes-only).
  **Templated split: 4 mechanisms, 96+6+6+6 structural combos × ∞ seeds.**
- Reporting note (lp agent): no-op/under traps make `empty` macro nonzero by
  design — report bypass-macro vs no_op-macro separately at sweep-analysis time.
- 48-instance multi-split ≥10× gate vs live Batfish: running (background).

Next (audit §6 order): probe sweep (~$10–30, 4 frontier models × 12 hand-authored
× N=3) to pick the headline BEFORE writing; /design-review on generator_scale
`kept` variant + generator_leak ms_reroute; fix/re-home `blackhole` (M1) + clos
link-down rebuild (M2); line up the independent κ labeler; live-FRR verify
clos_summary/leak_ms/lp_waypoint.

## Day 22 (cont.) — PRE-SPEND FREEZE GATE (user-demanded) → 8 more fixes → FROZEN

User refused to fund repeat runs; convened a 3-expert freeze gate (ml-eval,
network-architect, red-team) with one question: what changes after the first paid
call would waste money? The gate found a fresh KILL SHOT + 7 binding fixes, ALL
implemented and verified (suite 559 → 596 green):

- **KILL SHOT (red-team): the scenario NAME leaked into the prompt** as the
  topology header — generated names encode the answer category (no_op,
  ms_blackhole, under-kept...). Fixed: content-free `topology_<sha8>` label; NEW
  rendered-prompt hygiene gate (`test_prompt_rendered_hygiene.py`, 36 checks over
  the EXACT string models receive — the old field-level blocklist missed this).
- **gpt-5.5 would hard-crash** (rejects max_output_tokens on Responses API) →
  reasoning effort=medium + verbosity=low, no cap; gpt-5.4-mini cap 16000 (includes
  reasoning tokens); gemini 16000 (thinking counts against cap; temperature no
  longer sent); anthropic 1500→4000 (new tokenizer +30-35%).
- **Per-family temperature policy (binding):** anthropic/vllm/fake = 0.7
  (temp-0 N-sampling was wasted spend + fake CIs); openai/gemini = never sent.
  Manifest logs per-model resolved values. N=3 probe / N=5 sweep locked.
- **Prompt contract frozen:** in-JSON `reasoning` field DROPPED (double-pays CoT
  on reasoning models; truncation risk); one empty-skeleton schema example added;
  native pre-JSON thinking allowed (parser takes last fenced block — verified).
- **generator_scale is_trap mislabel:** under-kept (empty GT) is a calibration
  CONTROL, not a trap → `is_trap=not(under∧kept)`.
- **generator_lp route-map names leaked roles** (FROM_WAY_IN/FROM_ALT_IN telegraph
  waypoint-vs-bypass) → neutral RM_UPLINK1_IN/RM_UPLINK2_IN; all 6 combos re-gated
  10× live, GT structure unchanged.
- **Empty-GT macro inflation closed:** records tagged `gt_empty`; new
  `macro_f1_damage` aggregate + `macro dmg` table column (damage headline never
  blends calibration instances; verified: empty baseline 0.17 blended vs 0.00 dmg).
- **--limit N** (pre-flight cap) + **--exclude (default: blackhole)** wired.

**Architect freeze rulings (scenario set):** blackhole DROPPED from paid runs
(CONTRIVED; IGP rebuild = post-probe; grounded roster = 11 scenarios, honest count
6–7 mechanisms); clos_summary probe AS-IS (§3.2.2 disclosure; link-down rebuild =
full-sweep item); lp_waypoint stays grounded-with-disclosure (generator twin
carries idiomatic weight in templated); **leak_ms ALLOW_VICTIM_IN edit landed —
GT proven byte-identical pre/post (sha b1286e33… both, 10×)**; generator_scale
`kept` + generator_leak `ms_reroute` both BLESSED (real operator patterns).

**State: prompt contract + runner + scenario set FROZEN. 596 tests. 60-instance
≥10× gate green. Spend-safe.** Probe awaits: account funding (~$15: OpenAI $10,
Anthropic $5, Google postpaid) + $0.10 single-call sanity per provider, then
grounded-11 × N=3 × {haiku-4.5, gpt-5.4-mini, gemini-3.5-flash, gpt-5.5}.
Full-sweep n-generated must be ≥48 so templated modal classes have ≥2 members.

## Day 22 (cont.) — THE FRONTIER PROBE RAN. Headline decided by data.

Keys funded ($10/provider hard cap); spend gate updated. SDK currency check first
(claude-api skill + live docs): anthropic 0.107.1→0.109.1; openai/google-genai
already latest; **caught that Opus 4.8 REMOVED temperature (would 400)** → registry
`sampling:False` flag + omit-param path. No project keys needed for any provider.
Sanity --limit 1 per provider: anthropic clean ($0.014), openai clean (mini $0.004,
gpt-5.5 $0.21/call), gemini 503'd → exposed the red-team's predicted crash-after-
paid-calls mode → added model-call retry/skip guard (failures logged, excluded,
never crash or zero a paid run). Suite 596 green throughout.

**PROBE (audit §6 step 3): 4 models × 11 frozen grounded scenarios × N=3 =
132 paid samples, $5.71 total. Zero invalid (1 haiku max_tokens truncation, 3%),
zero provider failures.** Full verdict: `paper/refs/probe_results_2026-06-10.md`.
- Discrimination PROVEN: gpt-5.5 0.37 > gemini-3.5-flash 0.35 > haiku 0.29 >
  gpt-5.4-mini 0.17, all floors ≤0.01. The "everyone floors" kill-risk is retired.
- FSA = 0.00 / 132 samples: frontier models do NOT hallucinate session loss — the
  old co-headline is dead as a failure claim, reframed as the calibration
  counterpoint (they pass the D1 trap).
- **THE HEADLINE: 0/46 forwarding-anomaly samples detected by ANY model.**
  leak_ms + lp_waypoint = 0.00 universally; intent ≤0.04; D9 ≤0.14 — while
  frontier prefixes-F1 = 0.83 and ipc3_static = 1.00 (so it's not a format/
  comprehension artifact). Models read the RIB; they cannot see the blackhole.
- Spend ledger: anthropic $0.40, openai $3.34, google $1.97 (caps $10 each).

Next: full sweep (templated multi-mechanism split + Opus 4.8/Sonnet 4.6 arms,
~$6-8 more, within caps), then validity package (live-FRR thesis-carriers, κ
labeler) and the HotNets position-paper write-up around the F3 gradient.

## Day 22 (cont.) — Topology windfall: public-source hunt + v1-inclusion debate + build

User supplied 3 anonymized real-world topologies (internal Cisco xhaul/MEC slides;
provenance in temporary/ ONLY). Two workflows + a build:

**Public-source hunt (7-angle web sweep, all hits fetch-verified):** NO exact public
source exists (the specific deployment is unpublished); the role-vocab set, scale
table, and ASIC spellings (shared_LW_LDI/EM0/EM1) return ZERO public hits =
confirmed proprietary fingerprints. BUT every STRUCTURAL pattern maps to verified
citable public anchors (RFC 7938, Juniper 5G CSR xHaul SR JVD, IP Infusion ISIS-SR/
EVPN blog, IETF seamless-MPLS, RFC 4364§10/9889, US Pat 11,431,619, Cisco Live
BRKSPG-2208/2397 with the 16,384 ECMP-group ceiling found VERBATIM, CS168 Clos, Jain
SRLG, Azure RNG/MACSec, Meta/MS optical backbone). The silicon resolved to Cisco
8000/Silicon One Q200 + NCS5500/Jericho. Verdict: a scaled-down, fingerprint-free,
public-anchored synthetic version is safe AND citable.

**v1-inclusion debate (6 lenses, unanimous): V1-CASE-STUDY-ONLY.** Build ONE 6-node
OSPF-underlay topology (ospf_core6), grade it ONCE descriptively as an F3-replication
case study (NO table/CI/F1 — anything numbered drags the full κ/determinism/live-FRR
gate past July 16). Reject the 12-node TAP-lite for v1 (4 risk surfaces / 5-week
clock → v1.5/v2). NetConfEval ruling: the "newer draft" is NetConfBench
draft-01 (2-node, intent/functional, NO blast-radius) — no scoop, no urgency, no v2
cannibalization (v2 = task-family breadth, not one IGP topology); it's a velocity +
citation-currency signal only.

**Executed (free/local, this session):**
- Citation-currency fixes in landscape_table.md: NetConfBench -00→-01 (2-node,
  no-blast-radius characterization); NetConfEval pinned to CoNEXT 2024 / ACM ToN
  10.1145/3656296 (killed the "newer draft" conflation); NIKA/NetArena by arXiv ID.
- D8 public-budget disclosure appended to oracle_determinism_spec_v1.md (zero GT
  change): budgets now anchored to the public Cisco 16,384 ECMP-group ceiling +
  NVIDIA Cumulus exhaustion behavior + Broadcom FIB ranges; retires the
  "spec budget not silicon ceiling" criticism.
- Fingerprint kill-list enforced: tree grep (excl. temporary/) CLEAN; scrubbed an
  accidental term mention from the spec; verified temporary/ stays gitignored.
- paper/refs/ospf_core6_casestudy.md staged (framing + public anchors + provenance
  statement; verified-results block GATED on the build).
- temporary/topology_mining_plan_2026-06-10.md holds the full mining plan +
  kill-list + public anchors (private).

**In flight:** netdevops-engineer building+Batfish-verifying ospf_core6 with the hard
kill-switch gate (non-empty OSPF RIB + iBGP next-hop via OSPF not static + D1=∅ with
D2/D7 + 10× deterministic). PASS → case study ships in v1; FAIL → drop to v1.5,
disclose static underlay. Deferred to v1.5/v2: TAP-lite, Option-A/VRF, D6-via-IOS-XR
object-groups + 2nd dialect, SRLG-diversity oracle, ECMP-group graded D8.

## Day 22 (cont.) — ospf_core6 build → CLEAN KILL → dropped to v1.5

The kill-switch worked as designed. netdevops-engineer built the idiomatic 6-node
OSPF-underlay + iBGP-RR core and verified it on live Batfish:
- **PASSED (the valuable part):** 12 OSPF adj + 18 iBGP sessions ESTABLISHED; every
  loopback /32 in every node's OSPF RIB; customer prefix resolves recursively via
  OSPF (next-hop=edge2 loopback, resolved-by=['ospf'], ZERO `ip route` lines).
  **The static-next-hop crutch is killed at the design level** — retires audit-M1.
- **KILLED (the scenario):** the intended D1=∅ recursive-next-hop blackhole is
  STRUCTURALLY IMPOSSIBLE on a redundant 2-plane RR core (exhaustive: 42 cuts × 2
  next-hop baselines = 0 clean traps; cuts either reroute or fire D1). Agent dropped
  cleanly per the verdict rather than hack a result — no scenario/test/REGISTRY
  entry created; only the verified baseline kept.

**v1 consequence:** NO topology case study in v1; static underlay disclosed as a
limitation. **v1.5:** baseline_ospf_core6.py kept as the foundation; fix spec
recorded (separate data-plane next-hop from session loopback + engineer a customer-
attach SPOF disjoint from the victim's iBGP). Suite 596 green (unchanged — no
half-built scenario registered).

**KB findings recorded (docs/oracle_determinism_spec_v1.md):** (1) plain FRR
next-hop-self is a no-op for RR-reflected routes (Batfish-faithful; use route-map
`set ip next-hop`); (2) the 2-plane-core structural finding.

Net: the topology windfall produced, for v1, the citation-currency fixes + the D8
public-budget grounding + the verified crutch-killer baseline + 2 KB findings — all
free, all clean, none on the deadline path. The graded topology scenario is honestly
v1.5. The binding next action is unchanged: the full sweep.

## Day 23 — 2026-06-11 — FULL SWEEP COMPLETE (v1 main result)

Staged 3-run sweep within the hard $10/provider cap; consolidated in
paper/refs/full_sweep_results_2026-06-11.md. NO overspend (Anthropic $9.28, OpenAI
$9.41, Google $4.13 today). 60/60 instances 10×-determinism-gated first.
- Run A (both splits, N=5, n=48): haiku-4.5 + gpt-5.4-mini = the templated validity
  backbone. $4.50.
- Run B+C (grounded, N=5): sonnet-4-6 + gemini + opus-4-8 + gpt-5.5. $12.62; gemini
  hit transient 503s (38/55, guard fail-skipped — NOT a cap), topped up on Google
  headroom to N=5.

**RESULTS (6 models × 2 splits × N=5, ~700 samples):**
- **F3 headline now bulletproof:** forwarding-anomaly F1 = 0.00 for EVERY model on
  BOTH grounded and templated splits — universal second-order blindness. Templated
  adds waypoint=0.00 + redundancy=0.00. First-order prefixes read well (0.60-0.83).
- **F2:** FSA = 0.00 across all 6 models, both splits — no hallucinated session loss.
- **F1/validity (K1 resolved):** on templated damage instances, models 0.11-0.15 beat
  the modal-by-class memorizer floor (0.00) and all floors (≤0.07). Benchmark
  measures reasoning, not memorization — proven with real data.
- **F4 (NEW, circularity defense):** opus 0.37 ≈ gpt-5.5 0.36 ≈ gemini 0.35 — the
  Claude-built benchmark does NOT favor Claude; cross-vendor frontier parity.
- Caveats logged: gemini top-up; sonnet invalid 0.11 (raw saved); grounded per-dim
  n=1 cells are point estimates (templated carries the real N for fwd/D4/D5).

v1 experimental payload is DONE. Remaining for the paper: κ validity study (needs the
independent human/co-author — the gated $100-300 scale-up waits on it), prose draft,
figures, arXiv. Landscape citation currency + D8 public-budget grounding already done.
