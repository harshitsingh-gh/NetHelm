# NetHELM v1 Blast-Radius Question Base — Build Plan (LOCKED 2026-06-08)

> Source of truth for the v1 question base. Derived from the fleet audit
> (`catalog_audit_2026-06-08.md`) + Harshit's decisions. **Scope choice: the
> "deterministic modern layer."** Everything here is either Batfish-static
> (deterministic by construction) or live-FRR **converged-state** behind an N-run
> determinism gate. Non-deterministic modern stack is deferred to v2 *on purpose*.
>
> **Framing for the paper:** report as **failure CLASSES × parameterized generators**,
> NOT a raw scenario count. Target ≈ **150–220 graded instances** across ~14–16
> classes, frequency-weighted by real-world outage body-count.

## Determinism doctrine (the publication-defense; applies to every scenario)
1. **Prefer Batfish-static** — symbolic RIB/FIB from a pinned snapshot; identical every run.
2. **Live-FRR allowed only at converged steady state**, behind:
   - **N-run determinism gate (≥10 runs, identical ground truth or quarantine).**
   - **Settle-checks** (poll-until-converged), never fixed sleeps.
   - **Tie-break handling** (fixed router-ids/seeds; or score set-level invariants).
3. **Never score** transient/timing/tie-break effects as exact-set ground truth.
4. **Pin** all image tags + Batfish version; **ship** snapshots for recompute.

## v1 STATIC SPINE (Batfish-deterministic) — frequency-weighted

| # | Failure class | Real grounding | dims | ~inst | status |
|---|---|---|---|---|---|
| 1 | **Internal routing-policy silent withdrawal** (outbound route-map/prefix-list implicit-deny withdraws a needed prefix; sessions UP, RIB empties) — **FLAGSHIP** | Maint. Type 2 / op-lore; FB Oct'21 (prefix-level) — **NOT Rogers** (see below) | D1(∅),D2,D3 | 8–12 | built (S-IPC-01) |
| 2 | **Route leak / more-specific / mis-origination** (session+prefix count give NO signal — justifies multi-dim thesis) | Cloudflare'19, Telekom Malaysia'15 | D4,D7,D2 | 6–10 | new |
| 3 | **next-hop-self / recursive-resolution silent killer** (S08 generalized) | Rogers pattern, lore | D2,D3 | 5–6 | extend S08 |
| 4 | **RR / cluster failure** (S01) | iBGP scaling | D1,D2,D3,D5 | 6–8 | extend S01 |
| 5 | **local-pref/MED "empty blast" trap** (S10 — documented LLM failure: predicts session loss on attribute change) | network_change_management.md | D4,D5,D6 | 6–8 | extend S10 |
| 6 | **ACL / VRF segmentation delta** (S03 + S07; **S04 absorbed**) | NIKA, Forward Networks | D6,D3 | 8–10 | extend |
| 7 | **Anycast withdrawal** (S16 = Cloudflare Jun'22 non-linear blast) | cloudflare_dc_outage_jun2022 | D4,D5,D3 | 4–6 | extend S16 |
| 8 | **Management-plane / OOB lockout** (NOC-jumphost → device mgmt-IP severed) — **NEW, novel, cheap** | Facebook'21, Cloudflare'22 | D3(mgmt) | 3–4 | new |

> **Rogers Jul'22 grounds the SCALE/overload class, not class 1.** Corrected
> 2026-06-08: Rogers was an ACL-filter *removal* → route *flood* → core *overload/
> crash* (CRTC/Xona). That is the real-world flagship for the D8 scale/overload
> class (de-aggregation / FIB-TCAM / `maximum-prefix`), modeled via a per-device
> route/resource budget. See the corrected `knowledge/corpus/noc/rogers_canada_outage_jul2022.md`.

### Second wave (still Batfish-static)
max-prefix teardown (3–4; incl. `warning-only` vs default-teardown trap); OSPF area /
MTU control-plane (S05/S12, 4–6); recursive/Null0 blackhole (S15, 3–4); prefix-list
ordering / implicit-deny traps (4–6); **BFD-risk classification** (3–4 — config-reasoning
"latent risk", graded as classification, NOT a steady-state set delta).

## v1 DETERMINISTIC MODERN LAYER (credibility, kept deterministic)

| # | Class | Why deterministic | dims | ~inst |
|---|---|---|---|---|
| 9 | **RPKI/ROV route-validity flip** (policy edit flips a route VALID→INVALID, or drops INVALID) — adds the new **route-validity** typed element to D6 | **Pure function** of (route, ROA-set) — annotation-driven, no live timing | D6(validity),D2 | 8–12 |
| 10 | **EVPN Type-5 RT-leak** (RT typo → tenant can't import, or imports another tenant's prefixes) — maps onto class 6 | **Converged-state** RIB; FRR 10.6 + N-run gate | D6,D2,D3 per-VRF | 6–10 |

## DEFERRED TO v2 (deferred *because* non-deterministic / weak-oracle)
SRv6 / SR-TE / TI-LFA (microloop + backup-timing nondeterminism); deep EVPN Type-2
MAC-mobility / DF election (sequence + tie-break races); all LIVE-only-transient
(PMTUD blackhole, stateful-FW asymmetry, transient microloops); MLAG/L2; NTP/cert;
SD-WAN. Plus the **input-format axis** (CLI / YANG-NETCONF / intent) as a fast-follow
once the spine is gradeable.

## Cross-cutting work
- Add **`route-validity` typed element** to D6 (schema + grader + parser) — additive,
  keep `pytest tests/unit -q` green.
- **Merges:** fold S04→S03, S14→S06 in the catalog.
- **Oracle-honesty fixes:** S13 (no oscillation claim), S20 (count threshold only).
- **Citation fixes:** NetPress→**NetArena**; NetConfBench→**draft-01**; NIKA→**640/5/54**.
- **Generator framing:** each class = a parameterized generator over topology
  (size, which device/peer, with/without backup, AF), not hand-authored one-offs.

## Build order
1. **Oracle determinism spec** for all v1 classes (batfish-oracle-engineer) ← gating.
2. **Class 1 (flagship)** author → `/scenario-gate` → oracle → tests.
3. Classes 2–8 (spine), then 9–10 (modern layer), then second wave.
4. Multi-sample × model-fleet sweep ($1000, models-under-test) once the suite is built.
5. κ ≥ 0.7 labelling pass before any number ships.

## Fleet review log + honesty ledger (2026-06-08)

**NOC-veteran per-instance verdict:** all 5 built scenarios (ipc, ipc_static,
ipc_fanout, ipc_aggregate, leak_ms) ruled **LEGIT** — none rotten, none lie about
mechanics or grounding. BUT: **5 scenarios = only 2 mechanisms** (4 are the same
outbound-implicit-deny mechanism exposing different oracle dimensions). "A reviewer
counts mechanisms, not files."

**RULE adopted:** no more parameter-tweaked siblings of the implicit-deny mechanism.
Every new scenario from here must be a NEW mechanism, not a cardinality/variant of
Class 1. (ipc_fanout is explicitly the *cardinality* variant; that's the cap.)

**Coverage correction:** spine **class 3 (recursive next-hop / next-hop-self) is
ALREADY covered** by the existing `blackhole` scenario (removing a static strands a
BGP next-hop → NO_ROUTE). Don't rebuild it.

**Honesty ledger (fold into the paper when writing):**
- `ipc_static`: value is entirely in **D9 being a scored dimension** (confirmed it
  is). TODO: surface D9 in `reporting/` + the paper metric table, else it reads as
  a no-op.
- `leak_ms`: disclose (a) the `blackhole` static models the leak's **worst case**;
  the real Cloudflare-2019 event was congestion-based degradation, not a clean
  null-route; (b) the 3-AS chain demonstrates the **LPM mechanism**, not global
  blast propagation.
- `ipc_aggregate`: disclose that D3=∅ is the **reachability** truth, but
  **TE/multihoming intent is broken** (outside Batfish's model) — don't let it read
  as "no harm."

**Build-next priority (NEW mechanisms, NOC-ranked, KB-grounded):**
1. **Clean D4 waypoint shift** via BGP attribute (LOCAL_PREF/MED) — reroute through
   an unintended node with NO session/prefix loss. This is spine class 5 (the
   documented LLM failure: models wrongly predict session loss on attribute
   changes) AND the dimension Cloudflare/TM are actually classified under. We
   currently have NO clean D4-via-attribute instance. **Highest value.**
2. Scale/overload (Rogers Jul-2022, D8) — stop disclaiming the class; document the
   Batfish limit (count vs runtime).
3. RR best-path hiding / partial visibility (RFC 4456, class 4).

## Fleet review log — lp_waypoint (class 5) + KB expansion (2026-06-08)

**lp_waypoint** (LOCAL_PREF waypoint shift): NOC-veteran **LEGIT-BUT-NEEDS-NOTE**;
red-team **FIX-THEN-SHIP** — found and we FIXED:
- **Prompt leaked the answer** (description stated "alt strictly preferred, LP 300>200").
  Fixed: prompt now states the config edit + intent only. **New global authoring
  rule added to scenario-author: prompt = config edit + intent ONLY, never the
  routing outcome.** (Re-audit other scenarios' descriptions against this.)
- Docstring said the route-map sets LP "on the customer prefix" — actually no match
  clause (all dst-inbound routes). Fixed + dropped Cisco-only "weight" wording.
- Oracle `_accepted_traces` didn't match `EXITS_NETWORK` — aligned to the shared
  `_DELIVERED` set (latent footgun for future waypoint scenarios). Re-verified
  waypoint + lp_waypoint unaffected. Determinism 10/10 (red-team confirmed).

**Open methodology TODOs (sweep/paper phase, not per-scenario blockers):**
- **Non-trivial baselines + `is_trap`:** the runner reports only oracle-vs-empty
  discrimination. For trap scenarios it must also report a per-dim heuristic
  baseline (e.g. D4-only guess) and a **naive-session-loss (D1) baseline**, and
  grade traps with `is_trap=True` so a model FALLING for the trap (predicting D1
  loss) is measured/penalized, not just ignored. Applies to all trap scenarios.
- **Pin `pydantic` (+pytest/anthropic/openai) in `harness/venvs/batfish/`** — it was
  missing; the oracle couldn't import there until installed this session.
- **Paper limitations:** disclose the FRR `next-hop-self` Batfish gap (lp_waypoint
  uses static routes to egress /30s) and surface D9 in `reporting/`.

**KB expanded:** `knowledge/corpus/dc/` added (NOC-veteran research, primary
sources) — `hyperscaler_fabric_design.md`, `hyperscaler_dc_failure_modes.md`,
`dc_summarization_ecmp_pitfalls.md`. Index rebuilt. **Top DC scenarios to build
next** (from the research): (1) underlay route-summarization → conditional partial
blackhole on later link failure [RFC 7938 §5.2.3], (2) ECMP/multipath collapse
(maximum-paths 1 / drop multipath-relax / add-path), (3) automation/CI fat-finger
that passes canary but is wrong fleet-wide (Meta Oct-2021 class), (4) FIB/TCAM
overflow (Rogers/scale, D8), (5) EVPN RT mismatch → tenant partition.
