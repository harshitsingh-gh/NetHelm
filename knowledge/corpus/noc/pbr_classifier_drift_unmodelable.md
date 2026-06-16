# Policy-Based-Routing (PBR) Classifier Drift — real mechanism, NOT gradeable on the FRR/Batfish track (KILL)

## What the mechanism is (real-world)

Policy-based routing overrides the destination-based FIB for a **classified subset
of traffic**: a router matches a flow (by ACL, object-group, DSCP, class-map, source
address, or L4 port) and forwards it to a configured next-hop / nexthop-group,
*regardless of what the RIB says*. "Classifier drift" is the subtle second-order
version: a named ACL / object-group / DSCP / class-map referenced by an existing PBR
rule is edited, so the rule **starts (or stops) matching a victim flow** and steers
it off the intended waypoint — while the global RIB, all BGP sessions, all prefixes,
and ordinary destination traffic are unchanged. The intended "quiet" signature is
D4 (waypoint) + D10 (intent) violated for one sub-flow, with D1/D2/D3/D5/D7 empty.

This IS a real failure class. PBR + firewall PBR is widely deployed for
inspection-steering, dual-ISP egress selection, and DSCP-based TE, and vendor docs
and operator forums repeatedly flag rule-order / overlapping-match / asymmetric-route
foot-guns. (Cisco PBR config guides; Cato Networks PBR glossary; Cisco Community
"all traffic suddenly policy-routed after 7.0.2→7.0.4 upgrade".)

## Why it is a KILL for NetBrace v1 (two independent walls)

### Wall 1 — Batfish does not parse FRR/Cumulus PBR at all
- Empirical test on the pinned digest `batfish/allinone sha256:09817554db90`
  (== `:nethelm` == `:latest`), `CUMULUS_CONCATENATED` format with the FRR vendor
  parser engaged (non-PBR peers `PASSED`, PBR device `PARTIALLY_UNRECOGNIZED`):
  all PBR stanzas (`pbr-map`, `nexthop-group`, `set nexthop[-group]`, `match dscp`,
  interface `pbr-policy`) return `This syntax is unrecognized`. `definedStructures`
  shows ZERO PBR / nexthop-group structures.
- Independently confirmed against the Batfish source tree (master): the
  `cumulus_nclu` and `cumulus_concatenated` grammars contain bgp / routing /
  interface / stp rules but **no PBR grammar file and no nexthop-group / pbr-map /
  pbr-policy rule**. The only PBR support in Batfish is the Cisco/Juniper
  `ip policy route-map` dataplane path (`PbrWithTracerouteTest.java`,
  `TraceroutePolicyBasedRoutingTest.java`); `PBR_POLICY` is a Cisco IOS/NX-OS
  named-structure specifier, never produced by the FRR parser.
- Consequence: POST snapshot == PRE snapshot. Decisive dataplane test: traceroute
  with `dscps=[0]` vs `dscps=[46]` returns byte-identical traces; waypoint on path
  in BOTH. The mechanism is **DEAD, not quiet** — nothing fires, so there is
  nothing to grade. A deterministically-empty oracle is not a scenario.

### Wall 2 — the ExtendedOracle is destination-only
- All four traceroute call sites pass `headers={"dstIps": dst_ip}` only
  (`netbrace/batfish/oracle.py:143`; `netbrace/batfish/extended_oracle.py:159,172,332`).
  No `dscps` / `srcIps` / `dstPorts` / `ipProtocols` are threaded, so even a PBR
  construct that DID parse could not be graded per-flow — the D4 waypoint check is
  expressed per destination, not per classified 5-tuple.

## What it would take to make PBR gradeable (defer — do NOT build for v1)
1. A **vendor snapshot** (Arista cEOS / Cisco IOS / NX-OS) where Batfish models
   `ip policy route-map` PBR in the dataplane — verified empirically on that dialect,
   not assumed.
2. A **5-tuple oracle extension**: thread `dscps/srcIps/dstPorts/ipProtocols` through
   `HeaderConstraints` in `_accepted_traces` / `_flow_outcome` / `_waypoint_diff`,
   and express the D4 intent per classified flow. pybatfish `HeaderConstraints`
   already accepts these fields and traceroute honors them (that is how the DSCP
   no-op test was run) — the extension is mechanically easy but useless without (1).

## The quiet-half is ALREADY covered without PBR
The curated quiet-reroute family already produces a gradeable D4+D10 signature with
constructs Batfish DOES model — prefer these over PBR:
- `routemap_clause_fallthrough_silent_reroute.md` (first-match precedence)
- `community_driven_localpref_silent_reroute.md`
- `med_driven_quiet_reroute.md` / `drain_undrain_localpref_restore.md`
- `nexthop_self_quiet_reroute.md`
- `igp_metric_hotpotato_quiet_reroute.md`

## Grounding confidence (publication-honest)
PBR-drift has **no named public post-mortem**. Treat any incident grounding as
**analogous** (closest documented relative is the FlowSpec class — a BGP-propagated
filter — CenturyLink/Lumen Aug 2020, which is a LOUD D1/D2/D3 crash, NOT a quiet D4).
Do not cite PBR drift as a "documented outage."

## Verdict
KILL for the FRR/Batfish track. Real mechanism, invisible oracle. Revisit only as a
vendor-PBR scenario paired with the 5-tuple oracle extension above.

## Sources
- Batfish source tree (master), `org/batfish/grammar/cumulus_*` — no PBR grammar;
  `PbrWithTracerouteTest.java`, `TraceroutePolicyBasedRoutingTest.java` (Cisco/Juniper PBR only).
- Empirical Batfish test on pinned digest `sha256:09817554db90` (oracle-engineer + NOC-veteran).
- Cisco PBR config guides (IOS / Secure Firewall / C9000):
  https://www.cisco.com/c/en/us/td/docs/switches/lan/c9000/lyr3-fwd/pbr/policy-based-routing-configuration-guide/m-policy-based-routing-.html
- Cato Networks, "What Is Policy-Based Routing (PBR)?" (PBR misconfig risks: asymmetric routing, brittle failover):
  https://www.catonetworks.com/glossary/what-is-policy-based-routing/
- CenturyLink/Lumen BGP FlowSpec outage (nearest documented analog, LOUD class):
  knowledge/corpus/noc/centurylink_bgp_flowspec_aug2020.md
