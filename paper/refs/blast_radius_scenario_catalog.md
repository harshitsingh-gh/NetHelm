# NetBrace — Blast-Radius Scenario Catalog (v0 brainstorm)

> **Purpose.** 20 candidate scenarios for the NetBrace *safety / blast-radius*
> axis, drawn from the literature (NetConfEval, NetConfBench, NIKA, NetPress,
> Batfish docs, Forward Networks) — *not* from the current repo's toy setup.
>
> **Two corrections this catalog bakes in (per review feedback):**
> 1. **Topology is not fixed at 4 routers.** Scenarios below span leaf-spine
>    fabrics, multi-area OSPF, multi-AS eBGP, MPLS/L3VPN, campus 3-tier, and
>    anycast meshes — sized realistically (tens of nodes), often *parameterised*.
> 2. **Blast radius is not BGP-session loss.** It is a *multi-dimensional* delta
>    spanning control plane, data plane, security/segmentation, redundancy, and
>    intent. The single-protocol "session dropped" view is a special case.
>
> We do **not** pre-compute answers here. Each scenario lists how ground truth
> *would* be obtained and whether today's oracle (Batfish, static) can produce it,
> whether it needs a **live** emulator (containerlab/Mininet/Kathará), or is
> **hybrid**. Being honest about the oracle is the whole game — an ungradeable
> scenario is not a benchmark task.

---

## 0. The blast-radius dimension vocabulary

A prediction (and the oracle) is scored over a *set of typed elements*. The
current code scores D1–D3 only; the complex scenarios below force D4–D8.

| Dim | Name | Element examples | Static oracle (Batfish) |
|---|---|---|---|
| **D1** | Adjacencies/sessions lost | BGP session, OSPF/IS-IS adjacency, LDP, BFD | ✅ `bgpSessionStatus`, `ospfSessionCompatibility` |
| **D2** | Routes/prefixes lost or changed | RIB/FIB entry, specificity, next-hop, AS-path | ✅ `routes`, differential routes |
| **D3** | Reachability pairs lost | (src, dst-prefix, port) delivered→dropped | ✅ `differentialReachability`, `traceroute` |
| **D4** | Path / waypoint / intent change | traffic shifted to new path; must-transit node bypassed; LB path-count | ✅ `reachability(transitLocations)`, traceroute diff |
| **D5** | Redundancy / capacity reduction | ECMP members N→N−1; N+1→N; failover path gone | ✅ `multipathConsistency` + ECMP route count (steady state) |
| **D6** | Security / segmentation delta | newly permitted/denied flows; VRF/zone leak; firewall bypass | ✅ `searchFilters`/`testFilters`, per-VRF routes + reachability |
| **D7** | Forwarding anomaly introduced | loop, blackhole, multipath inconsistency | ✅ `detectLoops`, traceroute disposition (NULL/LOOP) |
| **D8** | Scale / resource overflow | route/FIB/label count vs device limit; convergence time | ⚠️ count from Batfish; *limit* needs spec; timing needs live |

**Out of static scope** (need live emulation or are not modeled): throughput /
microbursts / incast / queue buildup, transient microloops during convergence,
stateful-firewall session timing, FHRP failover dynamics, real DHCP/DNS, DoS
volume. These are flagged per-scenario as **LIVE** or **HYBRID**.

---

## 1. The 20 scenarios

Each: **topology**, **change/event** (the diff or injected fault), **why the
blast radius is non-obvious** (the trap), **dimensions scored**, **oracle**.

---

### S01 — Route-reflector / cluster failure in a non-full-mesh iBGP
- **Topology:** ISP backbone, 2 route reflectors + ~20 RR-clients, single AS (no full mesh). *Parameterised on client count.*
- **Change:** shut one RR, or corrupt its `cluster-id`, or remove a client's RR peering.
- **Why non-obvious:** naive answer = "one device down." Real blast = every prefix whose *only* advertised path traversed that RR disappears from a subset of clients; clients with a second RR are fine. Requires reasoning about RR reflection rules, not session count.
- **Dimensions:** D1, D2, D3, D5 (was there a backup RR path?).
- **Oracle:** Batfish (static) — `bgpRibRoutes` per node + `differentialReachability`.
- **Source:** NIKA "missing advertisements"; classic iBGP design.

### S02 — OSPF→BGP redistribution filter tightened
- **Topology:** 2-AS, each AS runs OSPF internally; ASBR redistributes OSPF into BGP via route-map.
- **Change:** tighten/remove the redistribution route-map or a prefix-list it references.
- **Why non-obvious:** a one-line route-map edit silently withdraws a *class* of prefixes from BGP → propagates to the eBGP peer → remote-AS hosts lose reachability two hops away. Blast crosses an AS boundary.
- **Dimensions:** D2, D3 (cross-AS), D4.
- **Oracle:** Batfish — differential `routes` at ASBR + `differentialReachability` across ASes.
- **Source:** NetConfBench redistribution tasks; NIKA "missing advertisements."

### S03 — ACL edit that shadows / over-blocks (firewall)
- **Topology:** Campus 3-tier with edge firewall + DMZ; multiple subnets and an internet edge.
- **Change:** add/modify a `deny` ACE; or insert a rule that *shadows* a later permit.
- **Why non-obvious:** the intended deny also blocks unintended (src,dst,port) tuples; or the new rule never matches because an earlier rule shadows it (no-op trap). Must reason over the *header space*, not line count.
- **Dimensions:** D6 (primary), D3.
- **Oracle:** Batfish — `searchFilters` / differential `testFilters` over full header space (exact).
- **Source:** NetPress **MALT** (ACL/malware); NIKA "ACL blocking"; Forward Networks compliance.

### S04 — ACL/rule **reordering** that looks semantics-preserving
- **Topology:** Same as S03, single large ACL (50+ ACEs).
- **Change:** reorder ACEs, or migrate to a "refactored" ACL claimed equivalent.
- **Why non-obvious:** reordering changes which ACE matches for overlapping ranges → a subtle permit/deny delta. The *trap* is that the diff "looks clean."
- **Dimensions:** D6.
- **Oracle:** Batfish — differential `searchFilters` (returns the exact differing flow set). High value: Batfish does this exactly; humans cannot.
- **Source:** Batfish ACL-analysis notebook.

### S05 — MTU change on a transit link
- **Topology:** ISP backbone, several P/PE routers, OSPF core.
- **Change:** lower interface MTU (or jumbo mismatch) on a core link.
- **Why non-obvious:** OSPF requires matching MTU → adjacency drops → reroute or partition (control-plane blast). Separately, large-packet/PMTUD flows blackhole even where the route still exists (data-plane blast the route diff won't show).
- **Dimensions:** D1 (OSPF adj), D2/D3 (reroute), and a **LIVE**-only PMTUD blackhole component.
- **Oracle:** HYBRID — Batfish for adjacency+reroute; containerlab for the data-plane PMTUD effect.
- **Source:** NIKA "fragmentation/MTU disabled."

### S06 — ECMP member removal in a leaf-spine fabric
- **Topology:** CLOS data center, 4 spines × 8 leaves, eBGP-to-the-host or iBGP underlay.
- **Change:** remove one spine uplink route (link drain or route-map filter) on some leaves.
- **Why non-obvious:** reachability is *unchanged* (ECMP reroutes) → naive blast = empty. Real blast = capacity cut by 1/k **and** a possible *multipath inconsistency* (the surviving paths traverse a leaf with a different ACL/policy → some flows now dropped). The "nothing broke" trap.
- **Dimensions:** D5 (path-count), D7 (multipath inconsistency), D4.
- **Oracle:** Batfish — `multipathConsistency` + ECMP route-count diff (steady state). Transient microloop is **LIVE**.
- **Source:** NetConfEval load-balancing intent; CLOS operations.

### S07 — VRF route-target leak (MPLS L3VPN)
- **Topology:** MPLS core, 3 PEs, multiple VRFs (e.g. `RED`, `BLUE`, `SHARED`) with import/export route-targets, CE per site.
- **Change:** add/remove an `import`/`export` RT, or a route-leak between VRFs.
- **Why non-obvious:** two opposite blasts — (a) *security*: prefixes cross a VRF boundary that must stay isolated (segmentation breach); (b) *availability*: an intended shared-services leak breaks. Per-VRF reasoning.
- **Dimensions:** D6 (segmentation), D2/D3 per-VRF.
- **Oracle:** Batfish — per-VRF `routes` + `reachability`; differential.
- **Source:** Forward Networks segmentation/compliance; L3VPN design.

### S08 — `next-hop-self` removed on a border router
- **Topology:** Single AS: 2 border routers (eBGP to upstream) + internal iBGP routers; IGP carries only internal links, **not** the external next-hops.
- **Change:** remove `neighbor … next-hop-self` on a border router.
- **Why non-obvious:** no session drops, all prefixes still "present" at the border — but internal routers receive an *unresolvable* external next-hop, so every eBGP-learned route is invalid/hidden internally → internet reachability collapses from the core. Classic silent killer.
- **Dimensions:** D2 (valid vs hidden), D3 (internal→internet).
- **Oracle:** Batfish — `routes` with next-hop resolution + `differentialReachability` from internal nodes.
- **Source:** Operational lore; NIKA "blackhole/missing route."

### S09 — BGP community stripped/rewritten, downstream policy reacts
- **Topology:** 3 ASes: customer → ISP → upstream; ISP applies local-pref/no-export on customer communities.
- **Change:** customer (or ISP ingress) strips or rewrites a community used downstream.
- **Why non-obvious:** no local session/route change, but an upstream AS now treats the route with different local-pref / honours/ignores no-export → path shift or reachability change *several hops away, in another administrative domain.*
- **Dimensions:** D4 (path), D2/D3 (downstream), D6 (no-export scope).
- **Oracle:** Batfish — community-aware `routes` + cross-AS reachability/traceroute. (Requires modeling all 3 ASes.)
- **Source:** NetConfBench policy tasks; inter-domain routing.

### S10 — Local-pref / MED change reroutes onto a constrained path (intent trap)
- **Topology:** Dual-homed edge AS with two upstreams (primary/backup), or multi-exit.
- **Change:** raise local-pref on the *backup* exit (or MED change) — **no session/route lost.**
- **Why non-obvious:** naive blast = empty (a true trap by D1–D3). Real blast = *all* egress shifts to one path, violating a load-balance/waypoint intent, creating asymmetry, and removing the redundancy margin.
- **Dimensions:** D4 (path shift), D5 (redundancy), D6 (if a must-inspect waypoint is now bypassed).
- **Oracle:** Batfish — `traceroute` path diff + `reachability(transitLocations=…)` for waypoint.
- **Source:** NetConfEval **waypoint**; Forward Networks intent checks.

### S11 — Aggregate / `summary-only` suppresses more-specifics
- **Topology:** Aggregation router advertising a supernet to peers, with more-specifics for traffic engineering of multihomed customers.
- **Change:** add `aggregate-address … summary-only` (or a prefix-list dropping the specifics).
- **Why non-obvious:** the supernet still reaches everything *in aggregate*, so coarse reachability looks fine — but multihomed customers lose the granular routing that pinned them to the right path → suboptimal/asymmetric routing or a blackhole for a de-multihomed prefix.
- **Dimensions:** D2 (specificity), D4 (path), D3 (edge cases).
- **Oracle:** Batfish — `routes` specificity diff + `traceroute` for affected specifics.
- **Source:** BGP aggregation pitfalls.

### S12 — Multi-area OSPF: interface moved to wrong area / ABR change
- **Topology:** Multi-area OSPF (area 0 + 2 stub/NSSA areas), 2 ABRs.
- **Change:** move an interface into a different area, make a link passive, or break the only ABR path to area 0 (discontiguous area).
- **Why non-obvious:** inter-area routes vanish or reroute through a virtual-link that may not exist; a discontiguous area silently loses connectivity to the backbone. Area semantics, not link state.
- **Dimensions:** D1 (adj), D2 (inter-area LSAs), D3.
- **Oracle:** Batfish — OSPF session/area questions + `routes` + reachability.
- **Source:** NIKA "OSPF area errors."

### S13 — Mutual redistribution loop (OSPF ↔ BGP or two IGPs)
- **Topology:** Two routing domains with two redistribution points (dual ASBRs), no route tagging/filtering.
- **Change:** enable mutual redistribution at both points (or remove a deny-tag filter).
- **Why non-obvious:** routes loop back into the origin domain with worse metrics → suboptimal paths, potential forwarding loops, route oscillation. Feedback reasoning across two boundaries.
- **Dimensions:** D7 (loops), D2 (wrong best path), D4.
- **Oracle:** Batfish — `detectLoops` + `routes`; *oscillation/instability* is **LIVE**.
- **Source:** Redistribution anti-patterns; NIKA "data-plane loops."

### S14 — Spine drain in CLOS under maintenance (capacity vs partition)
- **Topology:** CLOS DC, parameterised k spines × m leaves.
- **Change:** drain (admin-down/AS-prepend/route filter) one spine for maintenance.
- **Why non-obvious:** if every leaf is dual-attached → only capacity loss (D5); but if any leaf's prefix had a *unique* path via that spine (asymmetric wiring/misconfig) → partition (D3). Same change, different blast depending on topology instance — forces topology-aware reasoning.
- **Dimensions:** D5 (capacity), D3 (partition edge cases), D7 (transient loop = LIVE).
- **Oracle:** Batfish — reachability + ECMP count (steady state); microloop **LIVE**.
- **Source:** DC operations; NetPress safety axis.

### S15 — Static route / recursive next-hop blackhole
- **Topology:** Enterprise edge with default + specific statics; a summarised null route.
- **Change:** add a static whose next-hop becomes unresolvable, or a `Null0` summary while a more-specific is withdrawn.
- **Why non-obvious:** traffic to covered prefixes is silently blackholed (dropped, not error); coarse "route exists" checks pass.
- **Dimensions (abstract hazard):** D7 (blackhole), D3.
- **Dimensions (as implemented — `scenario_blackhole.py` on square4):** **D1×2, D2, D3, D7.** The removed static is also how `r1` reaches `r4`'s loopback (10.0.0.4) — the *peering address* of the loopback-sourced `r1↔r4` iBGP session — so removing it tears down that session (both endpoints → D1=2) and `r1` loses `10.0.0.4/32` from its RIB (D2) in addition to the recursive-next-hop blackhole (D7) + reachability loss (D3). Verified live (HANDOFF.md). The implemented instance is LOUD, not the quiet single-node blackhole the abstract entry suggests.
- **Oracle:** Batfish — `traceroute` disposition (NULL_ROUTED / DELIVERED) + routes + BGP session status.
- **Source:** NIKA "blackhole routes."

### S16 — Anycast origin withdrawn at one site
- **Topology:** Multi-site anycast (same prefix originated from 3 PoPs), eBGP to a transit mesh.
- **Change:** stop originating the anycast prefix at one PoP (or shut its uplink).
- **Why non-obvious:** reachability is *preserved* (other PoPs serve it) → naive blast empty. Real blast = every client homed to that PoP shifts to the next-nearest (latency + capacity blast), and a region with that as sole origin loses service.
- **Dimensions:** D4 (catchment shift), D5 (capacity), D3 (sole-origin regions).
- **Oracle:** Batfish — `traceroute` nearest-origin per source + reachability; capacity is an annotation.
- **Source:** Anycast/CDN operations.

### S17 — Routing change breaks stateful-firewall symmetry
- **Topology:** Enterprise with redundant paths through a stateful firewall pair.
- **Change:** a metric/policy change makes forward and return paths diverge (asymmetric).
- **Why non-obvious:** both directions are individually "reachable," yet the firewall drops the asymmetric return → flow breaks. Needs *bidirectional + stateful* reasoning, which plain reachability misses.
- **Dimensions:** D4 (asymmetry), D3 (effective), D6.
- **Oracle:** HYBRID — Batfish bidirectional traceroute exposes asymmetry; the *stateful drop* needs a live firewall (containerlab nftables/PAN).
- **Source:** Asymmetric-routing incidents; Forward Networks path analysis.

### S18 — Waypoint bypass: traffic skips the inspection chain (security)
- **Topology:** Network with a mandatory service chain (IDS/firewall) on the intended path between two zones.
- **Change:** a new/shorter route, or removing a `set next-hop`/PBR, lets traffic bypass the inspection device.
- **Why non-obvious:** connectivity *improves* (looks good!) but a compliance/segmentation intent ("all inter-zone traffic must transit the IDS") is now violated — a security regression with zero availability symptom.
- **Dimensions:** D6 (intent/compliance), D4 (waypoint).
- **Oracle:** Batfish — `reachability(transitLocations=IDS)` differential (flows that no longer transit).
- **Source:** NetConfEval waypoint; Forward Networks intent checks; NetPress safety.

### S19 — NAT rule change (exposure or loss)
- **Topology:** Edge with PAT overload + a few static NATs to DMZ services.
- **Change:** modify/remove a static NAT or change the pool.
- **Why non-obvious:** removes external reachability to one service *or* unintentionally exposes an internal host; internal↔internal is unaffected, so it's easy to miss the external-facing delta.
- **Dimensions:** D6 (exposure), D3 (external→service).
- **Oracle:** HYBRID — Batfish NAT modeling is limited; prefer containerlab data-plane for ground truth, Batfish where supported.
- **Source:** NIKA/NetPress MALT; edge operations.

### S20 — De-aggregation / table-size overflow (scale)
- **Topology:** Edge receiving a full-table-like feed; downstream device with a modeled FIB/route limit; or enabling BGP `additional-paths`.
- **Change:** remove a summarisation upstream (de-aggregation) or enable add-path, multiplying installed routes.
- **Why non-obvious:** everything is "reachable" until the route count crosses the device's FIB/TCAM limit → silent install failures / selective drops on the *constrained* device only. Blast depends on a per-device resource budget, not on the change alone.
- **Dimensions:** D8 (scale), then cascading D2/D3 on the overflowing device.
- **Oracle:** Batfish for the route-count delta; the *limit* is a per-device spec annotation; actual drop behaviour is **LIVE**.
- **Source:** FIB/TCAM exhaustion incidents; NetPress latency/safety framing.

---

## 2. Coverage matrix (diversity check)

| Scenario | Topology family | Protocol focus | Dims | Oracle |
|---|---|---|---|---|
| S01 RR failure | ISP backbone | iBGP/RR | D1-3,5 | Batfish |
| S02 redistribution filter | Multi-AS + OSPF | OSPF↔BGP | D2-4 | Batfish |
| S03 ACL over-block | Campus 3-tier | ACL/data-plane | D6,3 | Batfish |
| S04 ACL reorder | Campus | ACL | D6 | Batfish |
| S05 MTU | ISP backbone | OSPF + data-plane | D1-3 | Hybrid |
| S06 ECMP member | CLOS DC | BGP/ECMP | D5,7,4 | Batfish(+live) |
| S07 VRF leak | MPLS L3VPN | VPNv4/RT | D6,2-3 | Batfish |
| S08 next-hop-self | Single AS border | iBGP/IGP | D2-3 | Batfish |
| S09 community | 3-AS | BGP policy | D4,2-3,6 | Batfish |
| S10 local-pref trap | Dual-homed edge | BGP TE | D4,5,6 | Batfish |
| S11 aggregate | Aggregation | BGP | D2,4,3 | Batfish |
| S12 OSPF area | Multi-area OSPF | OSPF | D1-3 | Batfish |
| S13 redistribution loop | Dual ASBR | OSPF/BGP | D7,2,4 | Batfish(+live) |
| S14 spine drain | CLOS DC | BGP/ECMP | D5,3,7 | Batfish(+live) |
| S15 static blackhole | Enterprise edge | static | D7,3 | Batfish |
| S16 anycast withdraw | Multi-site anycast | eBGP/anycast | D4,5,3 | Batfish |
| S17 asymmetric+stateful | Redundant firewall | routing+FW | D4,3,6 | Hybrid |
| S18 waypoint bypass | Service chain | PBR/intent | D6,4 | Batfish |
| S19 NAT | Edge/DMZ | NAT | D6,3 | Hybrid |
| S20 de-aggregation scale | Edge + limited FIB | BGP/scale | D8,2-3 | Batfish(+spec/live) |

Families covered: ISP backbone, multi-AS eBGP, CLOS/leaf-spine DC, MPLS L3VPN,
campus 3-tier, multi-area OSPF, dual-homed edge, anycast, service-chain/DMZ.
Protocols: BGP (iBGP/eBGP/RR/communities/TE), OSPF (areas, MTU, redistribution),
static, MPLS/VPNv4, ACL/header-space, NAT, ECMP/multipath, PBR/intent. **None
require the 4-router square; most are parameterised in size.**

---

## 3. Implementation notes / honesty ledger

- **Static-gradeable today (Batfish only):** S01, S02, S03, S04, S07, S08, S09,
  S10, S11, S12, S15, S16, S18. These are the fastest path to a paper — pick
  ~6–8 spanning D4/D5/D6/D7 to *prove the multi-dimensional thesis* beyond D1–D3.
- **Need a live emulator (containerlab/Mininet/Kathará) for the real signal:**
  the data-plane/transient parts of S05, S06, S14, S13, S17, S19, S20. NetPress
  and NIKA both pair generation with an emulator for exactly this reason; that is
  the strongest design (static oracle for the cheap dims, live for the rest).
- **Determinism gate still applies** (plan.md §5): any scenario whose Batfish
  output is not identical across repeated runs is quarantined.
- **Grader extension required:** the current grader scores D1–D3 (sessions,
  prefixes, reachability). D4 (path/waypoint), D5 (ECMP/redundancy count), D6
  (filter/segmentation delta), D7 (loops/blackholes), D8 (scale) each need a
  typed element + a set-comparison rule in `graders/`. This is the real research
  contribution: *the scoring surface*, not the topology.
- **κ ≥ 0.7 human-label check** (CLAUDE.md) is harder for D4/D6 — budget a
  labelling pass on a 100-task subset before any number goes in the paper.

---

## 4. Sources

- NetConfEval (CoNEXT'24) — intent → formal spec (reachability / waypoint /
  load-balancing), conflict detection: `external/netconfeval/`.
- NetConfBench IETF draft (draft-cui-nmrg-llm-benchmark) — 40-task taxonomy,
  syntactic/semantic/functional metrics: `draft_llm_conf_benchmark/`.
- NIKA — *A Network Arena for Benchmarking AI Agents on Network Troubleshooting*,
  arXiv:2512.16381 (5 topologies, 6 fault families, 54 issues).
  https://arxiv.org/abs/2512.16381
- NetPress — *Dynamically Generated LLM Benchmarks for Network Applications*,
  arXiv:2506.03231; code https://github.com/Froot-NetSys/NetPress
  (correctness/safety/latency; route, ACL/malware, k8s; emulator-backed).
- Batfish forwarding & change validation (differentialReachability, transit
  locations, detectLoops, multipathConsistency, searchFilters):
  https://batfish.readthedocs.io/en/latest/notebooks/linked/introduction-to-forwarding-change-validation.html
  and https://batfish.readthedocs.io/en/latest/notebooks/linked/analyzing-acls-and-firewall-rules.html
- Forward Networks — blast-radius identification & intent checks (industry
  multi-dimensional framing):
  https://www.forwardnetworks.com/blog/lf/use-case-blast-radius-identification-and-isolation/
</content>
