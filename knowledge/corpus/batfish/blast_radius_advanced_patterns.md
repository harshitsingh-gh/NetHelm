# Advanced Blast Radius Scenario Patterns (BGP/OSPF)

## Overview
These patterns extend the basic blast_radius_patterns.md with higher-complexity scenarios involving multi-hop failure chains, architectural interactions, and cases where session/prefix metrics are insufficient.

---

## Pattern 11: Route Reflector Cluster Partition
**Scenario**: In an iBGP network with two RR clusters, the link between the two clusters fails (or the inter-cluster eBGP session goes down).

**Topology**: 
- Cluster 1: RR1 + clients C1, C2
- Cluster 2: RR2 + clients C3, C4
- Inter-cluster: RR1 ↔ RR2 (iBGP session between clusters)

**Pre**: Inter-cluster link up; all prefixes visible to all clients.
**Post**: Inter-cluster link (or RR1-RR2 session) removed.

**Expected blast radius**:
- D1: 1 session lost (RR1-RR2)
- D2: Prefixes originated in Cluster 1 are withdrawn from Cluster 2 clients and vice versa
- D3: Reachability between clusters degrades to zero (no path between C1 and C3)
- D5: Redundancy fully eliminated for inter-cluster paths

**Why D1 undercounts**: D1=1 (one session). But the actual impact is D2=hundreds of prefixes lost and D3=full partition. This illustrates why session count alone is a terrible blast-radius metric.

**Batfish modellability**: YES — Batfish models RR topology correctly. Remove the RR-RR session, run bgpRib on each cluster to confirm prefix isolation.

---

## Pattern 12: iBGP Split-Horizon Violation (Missing Route Reflector)
**Scenario**: A full-mesh iBGP is converted to RR topology, but one router is missed and remains a standalone iBGP speaker connected only to non-RR clients.

**Mechanism**: Standard iBGP split-horizon rule: a route learned from an iBGP peer is NOT re-advertised to other iBGP peers (only to eBGP peers). Without RR, the forgotten router cannot learn routes from clients it's not directly meshed with.

**Expected blast radius**:
- D2: Prefixes only available via the forgotten router's iBGP peers become invisible
- D3: Destinations reachable only via the forgotten router's paths become unreachable
- D1: Sessions remain ESTABLISHED — the bug is invisible at the session level

**Real-world relevance**: This is a common operational error when migrating from full-mesh to RR. The session-level monitoring shows all green; route-level monitoring (D2) catches it.

---

## Pattern 13: RTBH (Remotely Triggered Black Hole) Misconfiguration
**Scenario**: RTBH is used for DDoS mitigation. A route is tagged with community 65535:666 (RTBH community) and redistributed via BGP to trigger null-routing on all edge routers.

**Pre**: Normal routing; target IP 203.0.113.1/32 reachable.
**Post**: `203.0.113.1/32 via Null0` announced with community 65535:666. All edge routers accept and install null route.

**Expected blast radius (intended)**:
- D3: Target IP unreachable from outside (intentional, to stop DDoS)

**Expected blast radius (accidental, wrong prefix)**:
- D3: If the wrong prefix (e.g., a /24 instead of /32, or the wrong IP entirely) is used, legitimate traffic is black-holed
- D2: Prefix appears in RIB but points to Null0 → effectively unreachable
- The blast radius scales with prefix length: a /24 RTBH blackholes 256 addresses

**Batfish modellability**: YES — Batfish models static routes to Null0 and shows traceroute disposition as NO_ROUTE (black hole). Route-map community matching to trigger Null0 is also modeled.

**LLM failure mode**: LLMs often cannot distinguish between an RTBH on the correct /32 (minimal blast radius) vs. an RTBH on the wrong /24 (256x blast radius). They need to reason about prefix specificity.

---

## Pattern 14: BGP Conditional Advertisement Failure
**Scenario**: `neighbor X advertise-map MAP1 exist-map MAP2` — conditional advertisement where PREFIX_A is only advertised to X if PREFIX_B exists in the RIB.

**Pre**: PREFIX_B exists in RIB; PREFIX_A conditionally advertised to X.
**Post**: PREFIX_B removed (e.g., primary path fails). Conditional advertisement stops. X loses PREFIX_A.

**Expected blast radius**:
- D2: PREFIX_A withdrawn from X (and X's peers via normal BGP propagation)
- D3: Destinations behind PREFIX_A become unreachable at X
- D1: Sessions unaffected

**Real-world use**: Conditional advertisement is used to implement failover: advertise a prefix to a backup provider only when the primary path is down. If misconfigured (exist-map matches wrong prefix), the advertisement may permanently stop or never start.

**Batfish limitation**: Batfish models conditional advertisement based on the config syntax, but may not accurately simulate the dynamic nature of the exist-map check under all conditions.

---

## Pattern 15: BGP MED Oscillation (Persistent Route Churn)
**Scenario**: Two ASes each receive routes from the same third AS with different MEDs via different paths. `bgp always-compare-med` is enabled on one but not the other.

**Mechanism**: MED is only compared between routes from the same neighboring AS by default. With `always-compare-med`, MED is compared across all paths. This can create situations where path selection oscillates based on which routes are received first, leading to routing instability.

**Expected blast radius**:
- D7: Forwarding path changes continuously (oscillation)
- D4: Waypoint alternates between two paths
- D1/D2: Zero (sessions up, prefixes present)

**Operational impact**: MED oscillation is subtle — sessions stay up, prefixes stay in table, but traffic paths change unpredictably. Packetloss can appear randomly as traffic shifts between paths with different capacities.

---

## Pattern 16: Aggregation (Summary Route) Covering Withdrawn Component
**Scenario**: `aggregate-address 10.0.0.0/8 summary-only` on a router. The aggregate covers multiple more-specific prefixes from different sources.

**Pre**: All more-specifics present; aggregate and more-specifics advertised.
**Post**: One more-specific (10.1.0.0/16) is withdrawn from the RIB. With `summary-only`, the /8 aggregate suppresses more-specifics — the aggregate is still announced but the more-specific is gone.

**Expected blast radius**:
- If the aggregate covers 10.1.0.0/16: peers still see 10.0.0.0/8, so 10.1.x.x appears reachable
- But the traffic is now blackholed internally if 10.1.0.0/16 has no valid path
- D3: Actual reachability to 10.1.x.x fails even though D2 shows no prefix loss

**This is a dangerous scenario**: the aggregate masks the withdrawal. D2 shows zero lost prefixes; D3 reveals the black hole.

**LLM failure mode**: LLMs rarely understand the interaction between `aggregate-address summary-only` and component prefix withdrawal.

---

## Pattern 17: Recursive Next-Hop Chain Failure (Multi-Hop)
**Scenario**: 
- BGP prefix P has next-hop N1
- N1 is resolved via OSPF route to N2
- N2 is resolved via a static route to interface eth0
- eth0 goes down

**Failure chain**: eth0 down → static route to N2 removed → OSPF route to N1 loses next-hop → BGP next-hop N1 unresolvable → BGP prefix P withdrawn from FIB.

**Expected blast radius**:
- D2: All BGP prefixes whose next-hop chain includes eth0 are withdrawn
- D3: All destinations behind those prefixes unreachable
- D1: BGP sessions remain ESTABLISHED (TCP connection unaffected by routing changes if TCP session doesn't depend on the same path)

**Why this is hard for LLMs**: The chain of causation spans three protocol layers (static → OSPF → BGP). The model must trace the dependency chain. GPT-4o struggles with multi-hop chains of more than 2 steps.

**Batfish modellability**: Batfish CAN model this if the static route is in the config. It will show the BGP next-hop as unresolvable and the prefix as not installed.

---

## Pattern 18: OSPF Redistribution Into BGP With Tag Mismatch
**Scenario**: OSPF routes are redistributed into BGP. A tag is set on OSPF redistribution to prevent feedback loops. A mis-applied `match tag` causes some OSPF routes to not be redistributed.

**Pre**: `redistribute ospf 1 route-map OSPF_TO_BGP`; route-map matches all OSPF routes.
**Post**: Route-map modified to `match tag 100` (intended to only redistribute tagged routes); but most OSPF routes have no tag → not redistributed.

**Expected blast radius**:
- D2: Most OSPF-originated prefixes disappear from BGP table
- D3: Destinations only reachable via OSPF redistribution become unreachable from BGP domain
- D1: Zero sessions affected

---

## Pattern 19: VRF Route Leak (L3VPN Misconfiguration)
**Scenario**: In an MPLS L3VPN environment, two VRFs share a route-target by mistake, causing routes from VRF_CUSTOMER_A to appear in VRF_CUSTOMER_B.

**Pre**: VRF_A export RT=65001:100; VRF_B import RT=65001:200. No overlap.
**Post**: VRF_B import RT accidentally changed to include 65001:100.

**Expected blast radius**:
- D6: Filter/policy change — VRF_B now imports routes it shouldn't
- D4: Traffic from VRF_B destined for addresses that overlap with VRF_A prefixes may be misdirected into VRF_A's forwarding table
- Security implication: Customer A's traffic may be visible to Customer B (VPN isolation breach)

---

## Pattern 20: BGP Attribute Corruption (MED Too Large)
**Scenario**: A route-map sets MED to a very large value (e.g., 4294967295) or an invalid value. BGP neighbor receives the route; depending on platform, either accepts it, sends NOTIFICATION, or drops the session.

**Expected blast radius**:
- Platform-dependent: some platforms accept any 32-bit MED value; others reject it
- If rejected with NOTIFICATION: D1 = 1 session lost
- If accepted: D7 = forwarding path changes (traffic now avoids this path because MED is worst possible)

**LLM relevance**: Tests whether the LLM understands that attribute manipulation can cause session teardown depending on platform — a platform-awareness gap that pure RFC knowledge doesn't cover.

---

## Summary: Dimensions and Which Scenarios Each Detects

| Pattern | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 |
|---|---|---|---|---|---|---|---|---|
| 1. Neighbor removal | ✓ | ✓ | ✓ | | ✓ | | | |
| 2. LOCAL_PREF change | | | | ✓ | | | ✓ | |
| 3. Static route removal | | ✓ | ✓ | | | | | |
| 11. RR cluster partition | ✓ | ✓ | ✓ | | ✓ | | | |
| 12. iBGP split-horizon | | ✓ | ✓ | | | | | |
| 13. RTBH | | | ✓ | | | | | |
| 14. Conditional advertisement | | ✓ | ✓ | | | | | |
| 15. MED oscillation | | | | ✓ | | | ✓ | |
| 16. Aggregate masking | | | ✓ | | | | | |
| 17. Recursive next-hop chain | | ✓ | ✓ | | | | | |
| 18. OSPF redistribution tag | | ✓ | ✓ | | | | | |
| 19. VRF route leak | | | | ✓ | | ✓ | | |
| 20. Attribute corruption | ✓ | | | | | | ✓ | |

**Key insight**: Scenarios 11–20 all require multi-dimensional reasoning. Session-only evaluation (D1) would miss 80% of these.
