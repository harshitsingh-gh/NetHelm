# Oracle Determinism Spec — v1 classes (batfish-oracle-engineer, 2026-06-08)

> Gates the v1 question base (`paper/refs/v1_question_base_plan.md`). All verdicts
> verified against the live `batfish/allinone` container (port 9997) on the
> `runs/2026-05-27_batfish_frrsq/snapshot`, **5× byte-identical**. This doc is the
> authoring contract: build only what's marked safe; honor the per-class mitigations.

## Determinism doctrine (recap)
Batfish-static = deterministic by construction (symbolic RIB/FIB, pinned snapshot).
Live-FRR = deterministic only at **converged steady state**, behind an **N-run gate
(≥10 identical or quarantine) + settle-check (poll, never sleep) + pinned
router/cluster/RD/RT ids**, and **score set/count invariants, never chosen-path**.

**The N-run gate is now IMPLEMENTED and enforced:** `ExtendedOracle.compute_checked(
scenario, runs=10)` (raises `NonDeterministicOracleError` on drift) +
`scripts/verify_determinism.py` (runs all REGISTRY scenarios ≥10× and writes
`runs/determinism_<ts>/report.json`). As of 2026-06-08 **11/11 scenarios pass
≥10× byte-identical** (full `to_json`, not just key_sets — also catches payload drift).

**Dimension semantics (so D3 isn't mis-read):** **D3 reachability = TOTAL loss** — a
flow is "reachability lost" only if EVERY trace fails (Batfish's any-trace-delivers
collapse). **Partial loss (one ECMP path blackholes, another delivers) is captured by
D7 set-wise** (`forwarding_setwise=True`), NOT by D3. This split is deliberate: it
keeps both dimensions deterministic and unambiguous. **D6 (filter) is DEFERRED** —
not scored, not solicited in the prompt (needs a vendor-config oracle); the scored set
is D1–D5, D7–D9.

## Verified Batfish facts (2026-06-08)
- Present: `bgpSessionStatus` (`Established_Status=="ESTABLISHED"`), `routes`
  (cols incl. `Next_Hop` AND `Next_Hop_IP` — oracle keys on `Next_Hop_IP`, OK),
  `bgpRib` (`Status,AS_Path,Local_Pref,Communities,Cluster_List,Originator_Id`),
  `searchFilters`/`compareFilters`/`filterLineReachability`, `detectLoops`,
  `differentialReachability`, `bidirectionalTraceroute`, `evpnRib`,
  `testRoutePolicies`/`searchRoutePolicies`.
- **No RPKI/ROV question exists** in Batfish. Class 9 is a Python pure-function oracle.
- **FRR interface ACLs are NOT modeled** as packet filters → D6 ACL needs vendor config.
- **FRR `neighbor X next-hop-self` is NOT honored** by Batfish's iBGP next-hop
  rewrite (it leaves the eBGP link IP), so an iBGP receiver may drop the route as
  unresolvable and a dimension can silently go empty. Workaround (used in
  `lp_waypoint`): give the receiver static routes to the egress link /30s so the
  real eBGP next-hops resolve (matches the static-backup addressing doctrine).
  Verify any new iBGP scenario's RIB is non-empty before trusting its ground truth.
- **PINNED Batfish image (2026-06-08):** `batfish/allinone:nethelm` ==
  `sha256:09817554db90e2f2674b72562c2d659427094187de0a3dfc23534ab58bf26207`
  (the `:latest` and `:nethelm` tags both resolve to this digest). All ground truth
  is computed against this digest; recompute against it. (runbook §Step2 column list
  is stale — it's missing `Next_Hop`.)

## Per-class verdicts

| # | Class | Verdict | Oracle | Score invariant / mitigation |
|---|---|---|---|---|
| 1 | **Internal routing-policy collapse** | STATIC-DET | `bgpRib` BEST-set diff (D2) + `bgpSessionStatus` (D1 = ∅, the trap) + `traceroute`→`NO_ROUTE` (D3) | prefix-list/route-map **only** (no FRR ACL); assert post-RIB actually differs |
| 2 | **Route leak / more-specific** | STATIC-DET | `bgpRib` specificity-aware **set** diff + `bidirectionalTraceroute` (D4/D7) | score the route **set**, never count; pin router-ids |
| 3 | **next-hop-self / recursive** | STATIC-DET | discriminator: `bgpRib` present ∧ `routes` (FIB) absent → `NO_ROUTE` | lost-set from `routes()` (FIB), not bgpRib; IGP must not carry ext next-hops |
| 4 | **RR / cluster failure** | STATIC-DET | per-client `bgpRib` set diff + D5 path-count | score set membership + path **count**, not chosen path; pin cluster-ids |
| 5 | **local-pref/MED empty-blast trap** | STATIC-DET | D1–D3 = ∅ (the trap); `traceroute` path diff → D4; path-count → D5 | generate **strict** preference (no equal-cost ties); `_waypoint_diff` all-traces invariant |
| 6 | **ACL / VRF segmentation** | SPLIT | VRF half: per-VRF `routes`/`differentialReachability` (FRR ✅). ACL half: `searchFilters`/`compareFilters` → needs **IOS/EOS/Juniper** config | author VRF-leak now; tag ACL instances NEEDS_VENDOR_CONFIG |
| 7 | **Anycast withdrawal** | STATIC-DET* | per-source `traceroute` nearest-origin (D4) + `differentialReachability` sole-origin (D3); capacity D5 = annotation | *only with **strict-distance** topologies; else score sole-origin D3 only |
| 8 | **Mgmt-plane lockout** (NEW) | STATIC-DET | `differentialReachability`(jumphost→mgmt-IP) / D3 `reachability_flows` | author as **routing/VRF** severance (not interface ACL) to stay on FRR |
| 9 | **RPKI/ROV route-validity** | STATIC-DET **(pure-function annotation, NOT Batfish)** | Python `rov_validity(bgpRib_rows, roa_set)` per RFC 6811 → VALID/INVALID/NOT_FOUND; Batfish only computes downstream D2/D3 once the ROV-drop is materialized into the post snapshot | ship the ROA set in the scenario spec; **label honestly as annotation oracle** |
| 10 | **EVPN Type-5 RT-leak** | LIVE-CONVERGED-DET **(spike required)** | `evpnRib` (static, if it parses FRR 10.6) or converged `show bgp l2vpn evpn` per-VRF (live) | Type-5 **import-set only**; N-run gate ≥10 + settle-check; **defer if spike fails** |

## What to build, in order
**Safe to author NOW (static, proven):** Classes 1, 2, 3, 4, 5, 7, 8 + VRF-half of 6.
Start with **Class 1 (flagship)**.
**Needs oracle module first:** Class 9 (route-validity pure-function grader + unit test);
ACL-half of 6 (vendor baseline).
**Spike before committing:** Class 10 (1-day: static `evpnRib` parse OR live ≥10/10 gate); else v2.
**Hard rejections as set-ground-truth (score classification / static sub-element only):**
max-prefix runtime teardown, BFD-risk, S13 oscillation, S20 TCAM-eviction identity,
LIVE-only halves of S05/S17/S19.

## New oracle code (all additive; keep `pytest tests/unit -q` = 91 green)
1. `ExtendedOracle._bgp_rib_prefixes(snapshot)` (filter `Status=="BEST"`) — the
   "advertised-but-unresolvable" discriminator for classes 1/3/4.
2. `ExtendedOracle._filter_diff` — wire `searchFilters`/`compareFilters` → `FilterDelta`
   (D6), behind a `filter_intents` probe; vendor-config scenarios only.
3. **route-validity element + grader (class 9):** `ValidityFlip{prefix, origin_as, from, to}`
   on D6 + `rov_validity(...)` per RFC 6811 + unit test with a fixed ROA set. **Most
   scrutinized addition — label "annotation oracle, not Batfish."**
4. mgmt-lockout: no new code — reuse D3 `reachability_flows=[(jumphost, mgmt_ip)]`.
5. Generalize `compute_with_determinism_check` to `ExtendedBlastRadius` (≥10-run gate)
   for the live EVPN path.
6. EVPN Type-5 (only if class 10 survives the spike).

Sanity gate for every new dim: macro_f1 = 1.0 under the fake-oracle echo before any model runs.

---

## D8 scale-budget grounding — public hardware anchors (added 2026-06-10)

> Pre-approved zero-ground-truth disclosure upgrade (inclusion-debate verdict §5).
> Retires the "spec budget not silicon ceiling" criticism of the fabricated D8
> `budget=20` annotations by grounding the *magnitudes* in CITABLE PUBLIC vendor
> docs. The oracle code and computed ground truth are UNCHANGED — this is a
> citation + a limitations-paragraph sentence only; the freeze holds.

D8 budgets remain operator-supplied annotations (Batfish counts installed
routes/next-hop-sets; it does not read silicon tables). What changes is that the
budget magnitudes we use are now anchored to publicly documented ceilings, so the
disclosure reads "lab-scaled instance of a real, cited hardware limit" rather than
"arbitrary number":

- **ECMP-group ceiling:** Cisco 8000 / Silicon One Q200 `stage1_lb_group`
  **Estimated Max Entries: 16384** (Q100 = 8192), documented verbatim in PUBLIC
  Cisco Live decks BRKSPG-2208 and TACSPG-2001; the LWLDI→SHLDI→FEC→ECMP_FEC
  recursive-resolution chain is in BRKSPG-2397. ECMP-group SHARING (multiple
  prefixes sharing one group resource) is the documented optimization
  (US Patent 11,431,619, "Hierarchical ECMP control plane for dense topologies").
- **FIB/route ceiling:** Broadcom Trident-class ~64–72k and Jericho/Qumran
  external-TCAM ranges (public datasheets / NVIDIA Cumulus + Broadcom public docs).
- **ECMP exhaustion BEHAVIOR (the blast):** NVIDIA Cumulus documents that once the
  max ECMP routes are installed, **new ECMP routes log an error and are NOT
  installed** — i.e. silent FIB-install failure on overflow, the exact D8 blast.

Limitations-paragraph sentence (paper): *"D8 resource budgets are operator-supplied
annotations whose magnitudes are anchored to publicly documented hardware ceilings
(e.g. the 16,384-entry ECMP-group table on a current merchant/Silicon-One profile);
Batfish supplies the deterministic installed count, the ceiling is a cited spec
value, and instances are lab-scaled — no proprietary deployment figure is used."*

DO NOT use any source-deck-specific numbers (the demand figures, the encap-table
counts) or the proprietary ASIC table/optimization names — those are fingerprints
on the kill-list in `temporary/topology_mining_plan_2026-06-10.md` (the ONLY place
they may appear). Use only the public ceiling magnitudes above, scaled down and
randomized per instance.

---

## Batfish modeling note — RR next-hop-self (added 2026-06-10, ospf_core6 build)

Plain FRR `neighbor X next-hop-self` is a **no-op for route-reflector-REFLECTED
routes** — a route reflected to a client keeps the originator's next-hop, not the
RR's. This is real vendor behavior (NVIDIA Cumulus / Cisco docs) and Batfish mirrors
it faithfully. To force the RR's own address as the next-hop on reflected routes
(idiomatic in some designs), use an outbound route-map `set ip next-hop` toward
clients — Batfish honors that. Relevant for any future RR-based iBGP scenario: do
NOT assume `next-hop-self` rewrites reflected-route next-hops; verify the resolving
next-hop's protocol in the PRE snapshot before trusting the ground truth.

## ospf_core6 structural finding (added 2026-06-10) — why a redundant 2-plane RR
core cannot host a D1=∅ recursive-next-hop blackhole

On a healthy redundant 2-plane RR core, the customer prefix's iBGP next-hop is
reachable through the SAME underlay paths that carry the victim's iBGP sessions, so a
single/double OSPF cut either (a) reroutes (prefix survives, dead scenario) or (b)
strands a node (an iBGP session drops → D1 fires, breaking the trap). Exhaustive
sweep (42 cuts × 2 next-hop baselines) found 0 clean traps. The idiomatic OSPF
baseline itself (non-empty RIB, recursive-OSPF resolution, zero statics) is VERIFIED
and kept (`baseline_ospf_core6.py`) as the v1.5 foundation. The v1.5 fix: separate
the data-plane next-hop from the session loopback and engineer a single OSPF SPOF on
a customer-attach path disjoint from the victim's iBGP path.
